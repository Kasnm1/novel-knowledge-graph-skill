#!/usr/bin/env python3
"""Audit reader-facing prose for text the reader should never see.

Both renderers clean their prose on the way out (`reader_prose.strip_process_text`), so a
hit here is **not** a leak in the delivered artifact — it is a record whose stored text is
carrying process bookkeeping. Cleaning at render time keeps the graph honest and the page
readable, but it also means the junk stays on disk and cannot be found by reading the page.
This script is the counterpart: it names the records so they can be fixed at the source.

Measured across the nine runs in this project, the recurring offenders are:

* the merge's own journal — `本条由主 Agent 从 N 条分片记录合并（rom_A01、…）`, appended once
  per consolidation, frequently duplicated two or three times in one field;
* hand-off instructions to the operator — `请主 Agent 裁决`, `交由主 Agent 合并补填`,
  `请由更早分片补充`;
* per-fragment bookkeeping — `本分片…留空`, `（依据固定实体表说明）`, `[rom_su_ji 第1章]`;
* English machine keys left in Chinese sentences — `first_sex_chapter`, `consent_context`,
  `altered_state`, `one_sided`, `status`.

Exit status: 0 when clean, 1 when anything is reported, so it can gate a run.

    python scripts/audit_reader_prose.py --run-dir runs/<book-range>
    python scripts/audit_reader_prose.py --all --strict
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from reader_prose import (  # noqa: E402
    FIELD_LABELS,
    FALLBACK_ENUM_LABELS,
    FRAGMENT_LOCAL_ID,
    FRAGMENT_TAG,
    ID_PREFIXES,
    PROCESS_SENTENCES,
    strip_process_text,
)

# Reader-facing prose fields. `quote` is never listed: source text is verbatim evidence.
PROSE_FIELDS = (
    "description", "reason", "observation", "interpretation", "summary",
    "resolution", "title", "label", "note", "notes", "detail", "conclusion",
)

# Any record-shaped token; used to spot IDs the resolvers cannot label.
ANY_ID = re.compile(r"\b(?:" + "|".join(ID_PREFIXES) + r")_[A-Za-z0-9_]{2,}\b")
# A Latin token is only suspicious when it looks like an internal identifier.
# Plain English words are legitimate content in a Chinese novel -- `ipad`, `VIP`, `KTV`
# all appear in the corpus as story words, and flagging them buried the real findings.
INTERNAL_LATIN = re.compile(
    r"\b[A-Za-z][A-Za-z0-9]*_[A-Za-z0-9_]+\b"      # snake_case / 内部键
    r"|\bfragment-\d+\b"                            # 分片文件名
    r"|\b[A-Za-z_][A-Za-z0-9_]*\.py\b"               # 脚本名
)

# `review_issues` 是写给分析者看的：它本来就该说「合并时需注意」「请人工裁决」。
# 把这些与故事简介同等对待，只会让真问题淹没在噪音里。
ANALYST_ARRAYS = {"review_issues"}


def load_enum_labels(run_dir: Path) -> dict[str, str]:
    """Flatten the book's display vocabulary into `enum value -> label`."""
    labels: dict[str, str] = dict(FALLBACK_ENUM_LABELS)
    path = run_dir / "display-vocabulary.json"
    if not path.is_file():
        embedded = None
        graph_path = run_dir / "graph.json"
        if graph_path.is_file():
            try:
                embedded = (json.loads(graph_path.read_text(encoding="utf-8"))
                            .get("metadata") or {}).get("display_vocabulary")
            except (OSError, json.JSONDecodeError):
                embedded = None
        if not isinstance(embedded, dict):
            return labels
        vocabulary = embedded
    else:
        try:
            vocabulary = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            print(f"  !! display-vocabulary.json 解析失败: {exc}")
            return labels
    for entries in vocabulary.values():
        if isinstance(entries, dict):
            for key, value in entries.items():
                if isinstance(value, str):
                    labels.setdefault(str(key), value)
                elif isinstance(value, dict) and isinstance(value.get("label"), str):
                    labels.setdefault(str(key), value["label"])
    return labels


def walk_prose(node: object, path: str, out: list[tuple[str, str, str, str]]) -> None:
    """Collect prose fields, remembering which top-level array each record came from."""
    if isinstance(node, dict):
        record_id = node.get("id")
        for key, value in node.items():
            here = f"{path}.{key}"
            if isinstance(value, str) and key in PROSE_FIELDS:
                out.append((str(record_id) if record_id else here, key, value, path))
            else:
                walk_prose(value, here, out)
    elif isinstance(node, list):
        for index, item in enumerate(node):
            walk_prose(item, f"{path}[{index}]", out)


def audit_run(run_dir: Path, threshold: float, show: int) -> dict:
    graph_path = run_dir / "graph.json"
    if not graph_path.is_file():
        return {"run": run_dir.name, "skipped": True}
    graph = json.loads(graph_path.read_text(encoding="utf-8"))
    enum_labels = load_enum_labels(run_dir)

    prose: list[tuple[str, str, str, str]] = []
    for array_name in ("entities", "events", "relations", "state_changes",
                       "foreshadowing", "evidence", "romance_routes", "intimate_acts",
                       "level_conversions", "review_issues"):
        walk_prose(graph.get(array_name) or [], array_name, prose)

    findings: list[dict] = []
    for record_id, field, text, array_name in prose:
        cleaned = strip_process_text(text, enum_labels)
        reasons: list[str] = []

        if any(p.search(FRAGMENT_TAG.sub("", text)) for p in PROCESS_SENTENCES):
            reasons.append("含整理过程文字")
        if FRAGMENT_TAG.search(text):
            reasons.append("含分片标记")
        if FRAGMENT_LOCAL_ID.search(text):
            reasons.append("含无法解析的分片局部 ID")
        for raw in list(FIELD_LABELS) + list(FALLBACK_ENUM_LABELS):
            if re.search(rf"(?<![A-Za-z0-9_]){re.escape(raw)}(?![A-Za-z0-9_])", text):
                reasons.append(f"含内部键「{raw}」")
                break
        stray = [t for t in INTERNAL_LATIN.findall(text) if not ANY_ID.fullmatch(t)]
        if stray:
            reasons.append(f"含内部标识（{stray[0]}）")
        if text.strip() and not cleaned:
            reasons.append("清洗后为空（整段都是整理注记）")
        elif text.strip() and len(text) >= 60 and len(cleaned) < len(text) * threshold:
            reasons.append(f"清洗后仅剩 {len(cleaned)}/{len(text)} 字")

        if reasons:
            # walk_prose 传进来的是 "review_issues[0]" 这种带下标的路径，先取数组名再判。
            root = str(array_name).split("[", 1)[0]
            scope = "分析面" if root in ANALYST_ARRAYS else "故事面"
            findings.append({
                "record": record_id, "field": field, "reasons": sorted(set(reasons)),
                "before": len(text), "after": len(cleaned), "sample": text[:110],
                "scope": scope,
            })

    return {
        "run": run_dir.name,
        "prose_fields": len(prose),
        "findings": findings,
        "total_chars": sum(len(t) for _, _, t, _a in prose),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="审计读者可见散文里的整理注记与内部键")
    parser.add_argument("--run-dir", type=Path, help="单个 run 目录")
    parser.add_argument("--all", action="store_true", help="审计 runs/ 下所有 run")
    parser.add_argument("--runs-root", type=Path, default=Path("runs"), help="runs 根目录")
    parser.add_argument("--threshold", type=float, default=0.25,
                        help="清洗后不足原文该比例时报告（默认 0.25）")
    parser.add_argument("--show", type=int, default=6, help="每个 run 打印多少条")
    parser.add_argument("--json", type=Path, help="把结果写成 JSON")
    parser.add_argument("--strict", action="store_true", help="有发现时以非零码退出")
    args = parser.parse_args()

    if args.all:
        runs = sorted(p for p in args.runs_root.iterdir() if (p / "graph.json").is_file())
    elif args.run_dir:
        runs = [args.run_dir]
    else:
        parser.error("需要 --run-dir 或 --all")

    reports = [audit_run(run, args.threshold, args.show) for run in runs]

    grand = 0
    for report in reports:
        if report.get("skipped"):
            print(f"-- {report['run']}: 无 graph.json，跳过")
            continue
        findings = report["findings"]
        story = [f for f in findings if f.get("scope") == "故事面"]
        analyst = [f for f in findings if f.get("scope") != "故事面"]
        grand += len(story)
        mark = "★" if story else " "
        print(f"{mark} {report['run']:28s} 散文 {report['prose_fields']:5d} 处 / "
              f"{report['total_chars']:7d} 字 | 故事面需回源 {len(story):4d}｜分析面 {len(analyst):4d}")
        for item in story[:args.show]:
            print(f"    [{item['field']}] {item['record']}  {item['before']}→{item['after']} 字"
                  f"  {'；'.join(item['reasons'])}")
            print(f"        {item['sample']}")
        if len(findings) > args.show:
            print(f"    …另有 {len(findings) - args.show} 条")

    print()
    print(f"合计故事面需回源的记录：{grand}（分析面另行列出，不计入门禁）")
    print("注意：渲染器只认识一部分内部词汇——`fragment-N`、脚本名、已登记的字段键。")
    print("      其余内部标识（例如没登记过的 snake_case 键）渲染器不认识，会**原样递给读者**，")
    print("      所以这里列出的记录要按交付物泄漏对待，而不只是「存盘文字不整洁」。")
    print("      （原先这句写的是「渲染器已在输出时清洗」，对未登记的键不成立，2026-09-14 更正。）")
    print("修法：改写产生这些文字的记录（是内容修订），不要只改渲染器。")

    if args.json:
        args.json.resolve().write_text(
            json.dumps(reports, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"明细已写入 {args.json}")

    return 1 if (grand and args.strict) else 0


if __name__ == "__main__":
    raise SystemExit(main())
