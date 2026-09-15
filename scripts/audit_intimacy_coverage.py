#!/usr/bin/env python3
"""Find chapters whose text carries intimacy signals but that have no
`intimate_acts` record — the check whose absence let 第334章 go unrecorded.

Why this exists
---------------
`intimate_acts` is filled by hand, per fragment. Nothing compares it against the
source. So a scene can be written up as a plain `intimate_contact` event (or as
nothing at all) and stay invisible: in 《我的狐仙老婆》 the graph held 15 records
starting at 第31章, while 第334章 — 刘弈与西川洋子 in the washroom, explicitly
described with 交合 / 泄了几次身 / 攀上巅峰 / 最终爆发 — was recorded only as an
event, and its partner had no `romance_route` either. `第381章` even says
「品尝过**一次**双修运动之后」, so the count itself was checkable.

This script does the comparison mechanically: scan every chapter for markers,
then report the chapters that carry signals but have no record, and the records
that carry no signal (both directions are defects — a record with no supporting
wording is as suspect as a scene with no record).

Markers are tiered on purpose. Tier A almost only appears in an intercourse
scene, so a Tier-A hit without a record is a must-read. Tier B is suggestive
(bare skin, groping, kissing) and a hit is a should-read. Tier C is noise-level
and is only counted, never printed, to keep the report readable.

Output is a review list, not a verdict: a hit means "a human should read this
chapter", exactly like `rollup_levels.py`'s `candidate_gaps`.

Usage
-----
    python audit_intimacy_coverage.py --run-dir runs/我的狐仙老婆-full
    python audit_intimacy_coverage.py --run-dir <run> --chapter-end 550 --json out.json
    python audit_intimacy_coverage.py --run-dir <run> --context 90   # 附带原文片段
"""

from __future__ import annotations

import argparse
import io
import json
import os
import re
import sys

# Tier A — 近乎只出现在性交场景
TIER_A: tuple[str, ...] = (
    "长驱直入", "交合", "结合的下半身", "下半身结合", "做爱", "鱼水之欢",
    "翻云覆雨", "春宵一刻", "进入了她的身体", "进入了她", "破身", "破处",
    "初夜", "合体七七四十九", "大战七七四十九",
)

# Tier B — 暗示性场景（裸露、抚摸、亲吻、床上）
TIER_B: tuple[str, ...] = (
    "啪啪", "双修", "合体", "高潮", "呻吟", "娇喘", "赤裸", "脱光",
    "一丝不挂", "肌肤相亲", "压在床上", "压在身下", "扔到床上", "压了上去",
    "含住", "蓓蕾", "乳房", "乳头", "私处", "下体", "内裤", "胸衣",
    "褪下", "褪掉", "抚摸", "揉", "吮", "舔", "深吻", "湿吻", "舌吻",
)

# Tier C — 只计数，不打印（拥抱、搂、亲脸）
TIER_C: tuple[str, ...] = ("拥抱", "搂", "亲吻", "亲了", "抱住", "牵手")


def load_chapters(run_dir: str) -> list[tuple[int, str]]:
    """Return [(chapter, text)] sorted by chapter, from <run>/chapters/*.txt."""
    root = os.path.join(run_dir, "chapters")
    if not os.path.isdir(root):
        raise SystemExit(f"找不到章节目录：{root}")
    out: list[tuple[int, str]] = []
    for name in os.listdir(root):
        if not name.endswith(".txt"):
            continue
        stem = name[:-4]
        if not stem.isdigit():
            continue
        # 章节文件名是 001.txt … 1319.txt —— 必须取完整数字，
        # 用 name[:3] 会把 1000.txt 读成第 100 章（本脚本第一版就是这么错的）。
        n = int(stem)
        path = os.path.join(root, name)
        with io.open(path, encoding="utf-8", errors="replace") as fh:
            out.append((n, fh.read()))
    out.sort(key=lambda item: item[0])
    return out


def hits(text: str, markers: tuple[str, ...]) -> dict[str, int]:
    found: dict[str, int] = {}
    for marker in markers:
        count = text.count(marker)
        if count:
            found[marker] = count
    return found


def context_of(text: str, markers: tuple[str, ...], width: int) -> list[str]:
    """One snippet per marker occurrence, de-duplicated by rough position."""
    out: list[tuple[int, str, str]] = []
    for marker in markers:
        for match in re.finditer(re.escape(marker), text):
            start = max(0, match.start() - width)
            end = min(len(text), match.end() + width)
            snippet = text[start:end].replace("\n", " ").replace("\u3000", "").strip()
            out.append((match.start(), marker, snippet))
    seen: set[tuple[str, int]] = set()
    lines: list[str] = []
    for pos, marker, snippet in sorted(out):
        key = (marker, pos // 120)
        if key in seen:
            continue
        seen.add(key)
        lines.append(f"    [{marker}] …{snippet}…")
    return lines


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--run-dir", required=True)
    ap.add_argument("--chapter-end", type=int, default=None,
                    help="只审到该章（默认取 metadata.chapter_end，即图谱自己的分析范围）")
    ap.add_argument("--context", type=int, default=0,
                    help=">0 时打印原文片段，宽度为该值（字符）")
    ap.add_argument("--json", dest="json_out", default=None, help="把候选清单写成 JSON")
    args = ap.parse_args()

    graph_path = os.path.join(args.run_dir, "graph.json")
    with io.open(graph_path, encoding="utf-8") as fh:
        graph = json.load(fh)

    meta = graph.get("metadata") or {}
    chapter_end = args.chapter_end
    if chapter_end is None:
        chapter_end = meta.get("chapter_end")
    if not isinstance(chapter_end, int):
        raise SystemExit("图谱没有 metadata.chapter_end，请用 --chapter-end 指定")

    records = graph.get("intimate_acts") or []
    recorded: dict[int, list[dict]] = {}
    for record in records:
        chapter = record.get("chapter")
        if isinstance(chapter, int):
            recorded.setdefault(chapter, []).append(record)

    events_by_chapter: dict[int, list[str]] = {}
    for event in graph.get("events") or []:
        chapter = event.get("chapter")
        if isinstance(chapter, int) and event.get("type") in ("intimate_contact", "intimacy"):
            events_by_chapter.setdefault(chapter, []).append(event.get("title") or event.get("id") or "?")

    chapters = load_chapters(args.run_dir)
    in_range = [(n, t) for n, t in chapters if n <= chapter_end]

    print(f"审计窗口：1—{chapter_end} 章（磁盘上共 {len(chapters)} 章，"
          f"跳过 {len(chapters) - len(in_range)} 章）")
    print(f"既有 intimate_acts：{len(records)} 条，分布在 {len(recorded)} 个章节"
          f"（第 {min(recorded) if recorded else '-'}—{max(recorded) if recorded else '-'} 章）")
    print()

    tier_a_gap: list[dict] = []
    tier_b_gap: list[dict] = []
    recorded_no_signal: list[dict] = []

    for chapter, text in in_range:
        a = hits(text, TIER_A)
        b = hits(text, TIER_B)
        c = hits(text, TIER_C)
        has_record = chapter in recorded
        if a and not has_record:
            tier_a_gap.append({"chapter": chapter, "tier_a": a, "tier_b": b, "tier_c": c,
                               "intimate_events": events_by_chapter.get(chapter, [])})
        elif b and not has_record:
            tier_b_gap.append({"chapter": chapter, "tier_a": a, "tier_b": b, "tier_c": c,
                               "intimate_events": events_by_chapter.get(chapter, [])})
        if has_record and not a and not b:
            recorded_no_signal.append({
                "chapter": chapter,
                "acts": [r.get("act_type") for r in recorded[chapter]],
                "tier_c": c,
            })

    def dump(title: str, rows: list[dict], with_context: bool, text_of: dict[int, str]) -> None:
        print(f"===== {title}：{len(rows)} 章 =====")
        if not rows:
            print("  （无）")
        for row in rows:
            chapter = row["chapter"]
            marks = []
            if row.get("tier_a"):
                marks.append("A:" + ",".join(row["tier_a"]))
            if row.get("tier_b"):
                top = sorted(row["tier_b"].items(), key=lambda kv: -kv[1])[:6]
                marks.append("B:" + ",".join(f"{k}×{v}" for k, v in top))
            if row.get("tier_c"):
                marks.append("C:" + ",".join(row["tier_c"]))
            print(f"  第 {chapter} 章　{'　'.join(marks)}")
            if row.get("intimate_events"):
                print(f"      已有 intimate 事件：{'；'.join(row['intimate_events'])}")
            if with_context:
                for line in context_of(text_of[chapter], TIER_A + TIER_B, args.context):
                    print(line)
        print()

    text_of = dict(in_range)
    dump("Tier A 命中但无亲密行为记录（必读）", tier_a_gap, args.context > 0, text_of)
    dump("Tier B 命中但无亲密行为记录（需读）", tier_b_gap, args.context > 0, text_of)
    dump("有记录却无文本信号（记录可能挂错章）", recorded_no_signal, False, text_of)

    print("===== 已记录章节的信号对照 =====")
    for chapter in sorted(recorded):
        text = text_of.get(chapter)
        if text is None:
            print(f"  第 {chapter} 章　⚠️ 超出审计窗口或无原文")
            continue
        a = hits(text, TIER_A)
        b = hits(text, TIER_B)
        acts = ",".join(str(r.get("act_type")) for r in recorded[chapter])
        flag = "" if (a or b) else "　⚠️ 原文无信号"
        print(f"  第 {chapter} 章　{acts}　A:{list(a)}　B:{list(b)}{flag}")

    if args.json_out:
        payload = {
            "chapter_end": chapter_end,
            "chapters_on_disk": len(chapters),
            "chapters_scanned": len(in_range),
            "chapters_skipped_out_of_window": len(chapters) - len(in_range),
            "records_total": len(records),
            "recorded_chapters": sorted(recorded),
            "tier_a_gap": tier_a_gap,
            "tier_b_gap": tier_b_gap,
            "recorded_no_signal": recorded_no_signal,
        }
        with io.open(args.json_out, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, ensure_ascii=False, indent=1)
        print(f"\n候选清单已写入 {args.json_out}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
