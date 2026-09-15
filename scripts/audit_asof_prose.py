#!/usr/bin/env python3
"""List prose that names a chapter *later* than the record it belongs to.

A record is anchored to one chapter -- a state change's `chapter`, a
foreshadowing's `planted_chapter`, an event's `chapter` -- and the as-of view
("截至第 N 章") filters records by exactly that anchor. Prose is different: it is
hand-written analyst commentary, and it routinely names a *later* chapter.
A state change's `reason` says which chapter confirms the change; a
foreshadowing's `observation` says where the clue pays off; a relation's
`description` says when it ends.

The anchor filter cannot see that. At N=17 the panel happily rendered

    第 17 章：…丹田处凝聚出第一颗星璇；第 22 章进一步明确第一颗星璇已被开启。

because the record's own chapter is 17. The sentence hands the reader a fact
from chapter 22 -- future information, in a view whose whole purpose is to show
only what is known by chapter N.

**This is not a data error.** The note is accurate and its payoff linkage is the
most valuable thing the graph stores; rewriting it would destroy information.
The obligation is on the *renderer*: any field listed here must be routed through
the as-of scrub (`asOf` in `build_dashboard.py`) so that a view short of the last
analysed chapter withholds the note instead of printing the future. This script
exists so that when a new prose field is added to the panel, or a new round starts
writing notes that cite later chapters, you can see which fields carry the
obligation -- `verify_chapter_views.py` only probes a handful of entities at a
handful of snapshots, so it can miss a field nothing happens to render.

    python scripts/audit_asof_prose.py --graph runs/<book-range>/graph.json
    python scripts/audit_asof_prose.py --graph runs/<book-range>/graph.json --json audit.json

``scan()`` is importable, so `build_results_facts.py` quotes these same numbers
rather than re-implementing the walk.

Informational: always exits 0. The anchors are printed so you can tell a genuine
future citation from a record whose own chapter is simply missing.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

from asof_names import LateNameIndex

CHAPTER_TOKEN = re.compile(r"第\s*(\d+)\s*章")

# The fields the panel renders as prose. `quote` is deliberately absent: it is
# verbatim source text and is never rewritten or withheld.
PROSE_FIELDS = (
    "description", "reason", "observation", "interpretation",
    "summary", "resolution", "notes", "title", "label", "note",
    # 人物特征的断言是散文，而且**天生容易写进未来**：基线记在首次出场那一章，
    # 而作者很自然会顺手写「第 40 章剪短头发」——那就是第 1 章视图里出现第 40 章
    # 的事实。`statement` 与上面那些字段同类，必须走同一套 as-of 义务。
    "statement",
)

ARRAYS = (
    "entities", "events", "relations", "state_changes",
    "foreshadowing", "review_issues", "romance_routes",
    # 漏掉它，`character_traits.statement` 就永远不在审计范围内——2026-09-14 发现
    # （当时该数组是 0 条，所以漏掉也看不出来；补数据之前必须先把这一行补上，
    # 否则补进去的就是一批没有门禁的散文）。
    "character_traits",
    "item_roles",
    "chapter_summaries",
    "intimate_acts",
    "level_conversions",
    "story_arcs",
)

# The field that anchors each array. `romance_routes` has no single anchor: its
# milestones each carry their own chapter, so the earliest one is used.
ANCHORS = (
    "chapter", "planted_chapter", "first_chapter", "valid_from",
    "first_meeting_chapter",
)


def anchor(record: dict) -> int | None:
    """The chapter the record belongs to, or None when it has no anchor."""
    values = [record.get(key) for key in ANCHORS]
    numbers = [v for v in values if isinstance(v, int)]
    return min(numbers) if numbers else None


def scan(graph: dict) -> dict:
    """Count prose that cites a chapter, or a name, later than its own anchor.

    Two ways prose can reach into the future, and the renderer has to withhold
    both:

    * a chapter number -- 「…；第 22 章进一步明确…」 on a chapter-17 record;
    * a **name the text has not used yet** -- a rename leaks just as easily.
      `metadata.alias_first_chapter` (written by `annotate_alias_chapters.py`)
      dates every alias, so a note that says 「以命运之眼观察外界」 on a
      chapter-150 record is visible as a future citation even though it carries
      no chapter number at all.

    The name half uses `asof_names.LateNameIndex`, not a substring test: an
    alias is frequently part of a longer, legitimately visible name (`鲸胶`
    inside `万年鲸胶`), and counting those as future citations made this report
    41/233 noise at chapter 200 and 17/21 at chapter 290. See that module.

    Returns a dict so callers (``build_results_facts.py``) can quote the same
    numbers the CLI prints instead of re-implementing the walk.
    """
    alias_chapter = (graph.get("metadata") or {}).get("alias_first_chapter") or {}
    # 每个锚点一份名字索引，且**按需**构造：先做便宜的字符串包含判断，命中之后
    # 才建索引做边界检查。索引构造要枚举「包含该别名的可见名」，逐锚点全建会白花
    # 几十秒，而绝大多数记录根本不含晚期别名。
    index_cache: dict[int, LateNameIndex] = {}

    def precise_late_names(own: int, text: str) -> list[str]:
        candidates = [n for n, c in alias_chapter.items() if c > own and n in text]
        if not candidates:
            return []
        index = index_cache.get(own)
        if index is None:
            index = LateNameIndex(graph.get("entities") or [], alias_chapter, own)
            index_cache[own] = index
        return sorted(index.hits(text))

    by_field: Counter[tuple[str, str]] = Counter()
    by_field_records: defaultdict[tuple[str, str], list[tuple[str, int, list[int]]]] = defaultdict(list)
    name_by_field: Counter[tuple[str, str]] = Counter()
    name_records: defaultdict[tuple[str, str], list[tuple[str, int, list[str]]]] = defaultdict(list)
    unanchored: list[str] = []
    scanned = 0

    for array in ARRAYS:
        for record in graph.get(array, []) or []:
            if not isinstance(record, dict):
                continue
            scanned += 1
            own = anchor(record)
            if own is None:
                unanchored.append(f"{array}.{record.get('id')}")
                continue
            for field in PROSE_FIELDS:
                text = record.get(field)
                if not isinstance(text, str):
                    continue
                future = sorted({int(m) for m in CHAPTER_TOKEN.findall(text) if int(m) > own})
                if future:
                    by_field[(array, field)] += 1
                    by_field_records[(array, field)].append((record["id"], own, future))
                late_names = precise_late_names(own, text)
                if late_names:
                    name_by_field[(array, field)] += 1
                    name_records[(array, field)].append((record["id"], own, late_names))

    return {
        "scanned_records": scanned,
        "total": sum(by_field.values()),
        "group_count": len(by_field),
        "groups": {
            f"{array}.{field}": {
                "count": count,
                "records": [
                    {"id": rid, "anchor_chapter": own, "future_chapters": future}
                    for rid, own, future in sorted(by_field_records[(array, field)], key=lambda x: x[1])
                ],
            }
            for (array, field), count in sorted(by_field.items(), key=lambda kv: (-kv[1], kv[0]))
        },
        "name_total": sum(name_by_field.values()),
        "name_group_count": len(name_by_field),
        "name_groups": {
            f"{array}.{field}": {
                "count": count,
                "records": [
                    {"id": rid, "anchor_chapter": own, "future_names": names}
                    for rid, own, names in sorted(name_records[(array, field)], key=lambda x: x[1])
                ],
            }
            for (array, field), count in sorted(name_by_field.items(), key=lambda kv: (-kv[1], kv[0]))
        },
        "alias_first_chapter_size": len(alias_chapter),
        "unanchored": unanchored,
    }


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--graph", required=True, type=Path, help="Merged graph.json")
    parser.add_argument("--json", type=Path, help="Write the scan as JSON to this path")
    args = parser.parse_args()

    graph = json.loads(args.graph.read_text(encoding="utf-8"))
    report = scan(graph)

    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    total = report["total"]
    print(f"# 正文引用「晚于自身章节」审计：{args.graph.name}")
    print(f"扫描 {report['scanned_records']} 条记录")
    print()

    if not total:
        print("未发现：没有正文字段引用晚于自身锚点的章节。")
        return 0

    print(f"命中 {total} 处，涉及 {report['group_count']} 个「数组·字段」组合：")
    print()
    for key, group in report["groups"].items():
        print(f"## {key}：{group['count']} 条")
        for record in group["records"]:
            print(f"   {record['id']:44s} 锚点第 {record['anchor_chapter']:4d} 章 → 引用 {record['future_chapters']}")
        print()

    print("以上每条都是**渲染层的义务**，不是数据错误：")
    print("  · 注记准确，且「线索在哪一章兑现」是图谱最有价值的信息，不应改写；")
    print("  · 但 as-of 视图（chapter < 最后分析章）必须把它隐去，否则读者会在第 17 章读到第 22 章的事实。")
    print("  · 检查 `build_dashboard.py` 里这些字段是否都经 `asOf()` 输出；漏掉一个，")
    print("    `verify_chapter_views.py` 只有在恰好探到该实体、该快照时才会发现。")

    name_total = report["name_total"]
    print()
    print(f"# 正文引用「尚未出现的名称」：{name_total} 处，"
          f"涉及 {report['name_group_count']} 个「数组·字段」组合"
          f"（别名定年表 {report['alias_first_chapter_size']} 条）")
    if not name_total:
        print("未发现：没有正文字段点名晚于自身锚点的别名／新名。")
    else:
        for key, group in report["name_groups"].items():
            print(f"## {key}：{group['count']} 条")
            for record in group["records"]:
                names = "、".join(record["future_names"])
                print(f"   {record['id']:44s} 锚点第 {record['anchor_chapter']:4d} 章 → 点名 {names}")
            print()
        print("这类命中不含任何章节号，只靠 `第 X 章` 正则是抓不到的——")
        print("改名（王冬→王冬儿）、新称号（太子妃）、新魂灵名都会从注记里漏进早期快照。")
        print("同样按渲染层义务处理：`asOf()` 与 `names_future_chapter()` 都要认名称。")

    unanchored = report["unanchored"]
    if unanchored:
        print()
        print(f"另有 {len(unanchored)} 条记录没有可用锚点，未参与判定：")
        for note in unanchored[:20]:
            print(f"   {note}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
