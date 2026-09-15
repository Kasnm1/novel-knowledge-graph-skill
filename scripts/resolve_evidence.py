#!/usr/bin/env python3
"""分片证据预处理：修 JSON 引号、定位原文行号、纠正引文的章节归属。

这个脚本把拆书时最容易犯的三个错误一次性挡住：

1. 中文里误用 ASCII 双引号 -> JSON 直接解析失败
2. 引文只有 chapter + quote，缺 source_line_start/end -> validate 过不了
3. 引文的 chapter 标错（实际在别的章） -> 引文审计失败

用法：
    python resolve_evidence.py <fragment.json> [...]
    python resolve_evidence.py fragments/*.json --auto-chapter
    python resolve_evidence.py fragments/*.json --run-dir runs/mybook

默认就地写回。加 --dry-run 只看不写。
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path


def repair_inner_quotes(text: str) -> str:
    """把 JSON 字符串内部误用的 ASCII 双引号，成对替换为中文引号。

    判别规则：字符串内的 " 如果后面（跳过空白）不是 : , } ] 或换行，
    那它就是内容引号而不是结构引号。
    """
    out: list[str] = []
    i, n = 0, len(text)
    in_str = False
    toggle = True
    while i < n:
        c = text[i]
        if c == "\\" and in_str and i + 1 < n:
            out.append(c)
            out.append(text[i + 1])
            i += 2
            continue
        if c == '"':
            if not in_str:
                in_str = True
                out.append(c)
            else:
                j = i + 1
                while j < n and text[j] in " \t":
                    j += 1
                if j >= n or text[j] in ":,}]" or text[j] == "\n":
                    in_str = False
                    out.append(c)
                else:
                    out.append("\u201c" if toggle else "\u201d")
                    toggle = not toggle
        else:
            if c == "\n":
                in_str = False
            out.append(c)
        i += 1
    return "".join(out)


def load_json(path: Path) -> tuple[object, bool]:
    """读取 JSON；失败时尝试修复内容引号。返回 (数据, 是否修复过)。"""
    raw = path.read_text(encoding="utf-8")
    try:
        return json.loads(raw), False
    except json.JSONDecodeError:
        fixed = repair_inner_quotes(raw)
        try:
            return json.loads(fixed), True
        except json.JSONDecodeError as exc:
            raise SystemExit(f"{path.name}: JSON 无法解析，且自动修复失败 -> {exc}")


def norm(s: str) -> str:
    return re.sub(r"\s+", "", (s or "").replace("\ufeff", ""))


def main() -> int:
    ap = argparse.ArgumentParser(description="分片证据预处理")
    ap.add_argument("fragments", nargs="+", type=Path)
    ap.add_argument("--run-dir", type=Path, default=None,
                    help="run 目录（含 chapters.jsonl）。默认取 fragment 的上级目录的上级")
    ap.add_argument("--auto-chapter", action="store_true",
                    help="引文在标注章节找不到时，自动改用实际所在的章节")
    ap.add_argument("--dry-run", action="store_true", help="只报告不写回")
    args = ap.parse_args()

    def run_dir_for(fp: Path) -> Path:
        return args.run_dir or fp.resolve().parent.parent

    cache_dir: dict[Path, dict] = {}

    def load_run(rd: Path) -> dict:
        if rd not in cache_dir:
            idx = rd / "chapters.jsonl"
            if not idx.is_file():
                raise SystemExit(f"找不到章节索引：{idx}")
            rows = {}
            for line in idx.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    r = json.loads(line)
                    rows[r["chapter"]] = r
            cache_dir[rd] = {"rows": rows, "lines": {}}
        return cache_dir[rd]

    def lines_of(rd: Path, ch: int) -> tuple[list[str], int]:
        run = load_run(rd)
        if ch not in run["rows"]:
            return [], 0
        if ch not in run["lines"]:
            p = Path(run["rows"][ch]["text_path"])
            if not p.is_absolute():
                p = rd / p
            run["lines"][ch] = p.read_text(encoding="utf-8").splitlines()
        return run["lines"][ch], run["rows"][ch]["source_line_start"]

    rc = 0
    for fp in args.fragments:
        if not fp.is_file():
            print(f"!! 跳过（不存在）：{fp}", file=sys.stderr)
            rc = 1
            continue
        rd = run_dir_for(fp)
        frag, repaired = load_json(fp)
        if repaired:
            print(f"  ✓ {fp.name}: 已自动修复内部引号")

        ev = frag.get("evidence", []) or []
        located = fixed_ch = relocated = 0
        for e in ev:
            if not isinstance(e, dict):
                # 补充分片里会出现指向别片的占位符（`"EV_P2"`、`"IA_ALL"`），它们
                # 是数组元素但不是记录。`merge_graph.py` 早就忽略非对象元素，本脚本
                # 却直接 `e.get` 崩掉 —— 同一个分片于是「合并没事、回填炸」。两个脚本
                # 必须同口径：跳过并报告，不算错误（合并阶段也确实丢掉了它们）。
                print(f"  ! {fp.name}: 跳过非对象 evidence 元素 {e!r}", file=sys.stderr)
                continue
            ch, q = e.get("chapter"), e.get("quote", "")
            if ch is None or not q:
                print(f"  !! {fp.name}: {e.get('id')} 缺 chapter 或 quote", file=sys.stderr)
                rc = 1
                continue

            lines, base = lines_of(rd, ch)
            nq = norm(q)
            row = load_run(rd)["rows"].get(ch)
            hit = next((i for i, ln in enumerate(lines) if nq in norm(ln)), None)

            # 已经填过行号，不等于行号还有效。章界一旦被切分改动（本次：源文件里
            # 「第220章我早有准备 第221章赞美」是一行双标题，拆成两章后第 220 章
            # 从 45033-45143 缩到 45033-45090），旧行号会静默越界：validate_graph
            # 报 chapter_line_mismatch，而这里原先把「有行号」当作「已处理」直接
            # 跳过，于是「纠正章节」恒为 0，越界的行号永远没人修。
            if e.get("source_line_start") and e.get("source_line_end"):
                if row is not None and hit is not None:
                    lo, hi = row["source_line_start"], row["source_line_end"]
                    if lo <= e["source_line_start"] <= hi and lo <= e["source_line_end"] <= hi:
                        continue  # 行号仍落在本章内，保持不动（重定位会带来行号漂移）
                relocated += 1
                print(
                    f"  ~ {fp.name}: {e.get('id')} 行号 {e.get('source_line_start')} 在第{ch}章已失效，重新定位",
                    file=sys.stderr,
                )

            if hit is None:
                # 全库搜索：报告引文实际所在的章节
                found = None
                for other in sorted(load_run(rd)["rows"]):
                    if other == ch:
                        continue
                    olines, _ = lines_of(rd, other)
                    if any(nq in norm(ln) for ln in olines):
                        found = other
                        break
                if found is None:
                    print(f"  !! {fp.name}: {e.get('id')} 全库找不到引文：{q[:36]}", file=sys.stderr)
                    rc = 1
                    continue
                print(f"  → {fp.name}: {e.get('id')} 标为第{ch}章，实际在第{found}章", file=sys.stderr)
                if args.auto_chapter:
                    e["chapter"] = found
                    lines, base = lines_of(rd, found)
                    hit = next(i for i, ln in enumerate(lines) if nq in norm(ln))
                    fixed_ch += 1
                else:
                    print(f"       （加 --auto-chapter 可自动纠正）", file=sys.stderr)
                    rc = 1
                    continue

            e["source_line_start"] = base + hit
            e["source_line_end"] = base + hit
            located += 1

        if not args.dry_run:
            fp.write_text(json.dumps(frag, ensure_ascii=False, indent=2), encoding="utf-8")
        tag = "（dry-run，未写回）" if args.dry_run else ""
        print(
            f"  {fp.name}: 定位 {located} 条（其中失效重定位 {relocated} 条），"
            f"纠正章节 {fixed_ch} 条，共 {len(ev)} 条 {tag}"
        )

    return rc


if __name__ == "__main__":
    raise SystemExit(main())
