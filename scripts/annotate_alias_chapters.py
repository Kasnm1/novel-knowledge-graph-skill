#!/usr/bin/env python3
"""Record the earliest analysed chapter in which each name appears in the text.

Both renderers print an entity's canonical name and its aliases. That makes a
rename -- or simply a nickname the narrator coins later -- leak the later name
into an earlier "截至第 N 章" view: at N=200 the panel for 橘子 listed the aliases
太子妃 and 未来太子妃, neither of which the text uses before chapters 243 and 270.
The as-of obligation belongs to the renderer (see `audit_asof_prose.py`), so the
renderer needs to know when each name enters the text.

The **canonical name is dated too**, not only the aliases. A character who speaks
unnamed before the narrator names her is the common case in these books: 黄凌
talks back at 274 and is only named at 275, 四头 leads the 华黑帮 men at 272 and
is only named at 276. Dating aliases alone leaves that half of the obligation
ungated -- the prose can use a name the reader has not met yet and no check
notices. Only **proper-noun entity types** are dated (`PROPER_NOUN_TYPES`):
a `concept` called 武魂 or 修仙 is an ordinary noun that appears in prose from
the first page, and dating it would report every plain mention as a leak.
(`graph.json` metadata keeps the historical key name `alias_first_chapter`
because both renderers and the audits read it.)

This script derives that once from the chapter files and stores it in
`metadata.alias_first_chapter` as `{name: chapter}`. A name whose string never
appears anywhere in the analysed range is **omitted**: absence is not evidence of
lateness, and hiding a label we cannot date would be an unfounded claim. Numeric
and ASCII-punctuation tokens are omitted too (see `asof_names.is_name_like`).

Idempotent, and a no-op on the graph when the map is already current.

    python scripts/annotate_alias_chapters.py --graph runs/<book>/graph.json \
        --chapters-jsonl runs/<book>/chapters.jsonl --write

Without `--write` it prints the map and leaves the graph untouched. Exits 0.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from asof_names import is_name_like


def read_chapters(path: Path) -> list[tuple[int, Path]]:
    """(chapter number, text path) pairs, in file order."""
    rows: list[tuple[int, Path]] = []
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            record = json.loads(line)
            try:
                number = int(record["chapter"])
            except (KeyError, TypeError, ValueError):
                continue
            text_path = record.get("text_path")
            if text_path:
                rows.append((number, Path(text_path)))
    return rows


# 只有「专名型」实体才定年。`concept` / `skill` / `martial_soul` / `title` / `level_axis`
# 的名字是**普通名词**：斗罗的「武魂」（第2章首见）、狐仙的「修仙」（第4章首见）在正文里
# 天天出现，把它们定年之后，子串匹配会把第 1 章面板里任何一句含「武魂」的叙述都报成未来
# 名称泄露——而那句叙述本身完全没有泄露任何名字。as-of 名称义务针对的是**专名**：一个先
# 以「一个女孩」出场、第 275 章才被点名的人物，第 274 章写「黄凌」才是泄露。
PROPER_NOUN_TYPES = {"character", "item", "organization", "location", "creature"}


def collect_aliases(graph: dict) -> set[str]:
    """每个名字 → 首次出现的章。含正式名与别名，但只收专名型实体。

    纯数字／纯 ASCII 符号型别名（小三的对讲机代号「02」）交给 `asof_names.is_name_like`
    挡掉：渲染器的 as-of 名称判定是子串匹配，「02」会在「第202章」「2002年」里命中，
    报出并不存在的未来名称泄露。这类称呼仍然留在实体的 summary / attributes 里。
    """
    wanted: set[str] = set()
    for entity in graph.get("entities") or []:
        if entity.get("type") not in PROPER_NOUN_TYPES:
            continue
        name = entity.get("name") or ""
        if name and is_name_like(str(name)):
            wanted.add(str(name))
        for alias in entity.get("aliases") or []:
            if alias and alias != name and is_name_like(str(alias)):
                wanted.add(str(alias))
    return wanted


def build_map(graph: dict, chapters: list[tuple[int, Path]]) -> dict[str, int]:
    """Earliest chapter whose text contains each alias. Stops scanning a chapter
    early once nothing is left to find."""
    analyzed = {int(n) for n in (graph.get("metadata", {}).get("analyzed_chapters") or [])}
    wanted = collect_aliases(graph)
    found: dict[str, int] = {}
    for number, text_path in sorted(chapters):
        if analyzed and number not in analyzed:
            continue
        if not wanted:
            break
        try:
            text = text_path.read_text(encoding="utf-8")
        except OSError as error:
            print(f"  跳过第 {number} 章：{error}", file=sys.stderr)
            continue
        for alias in list(wanted):
            if alias in text:
                found[alias] = number
                wanted.discard(alias)
    return dict(sorted(found.items()))


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--graph", required=True, type=Path)
    parser.add_argument("--chapters-jsonl", required=True, type=Path)
    parser.add_argument("--write", action="store_true", help="Write the map back into the graph's metadata")
    args = parser.parse_args()

    graph = json.loads(args.graph.read_text(encoding="utf-8"))
    mapping = build_map(graph, read_chapters(args.chapters_jsonl))

    dated = len(mapping)
    total = len(collect_aliases(graph))
    print(f"名称 {total} 个（正式名 + 别名），其中 {dated} 个在分析范围内找到原文出处，{total - dated} 个无法定年（保持始终可见）")

    if args.write:
        metadata = graph.setdefault("metadata", {})
        if metadata.get("alias_first_chapter") != mapping:
            metadata["alias_first_chapter"] = mapping
            args.graph.write_text(
                json.dumps(graph, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
            )
            print(f"已写入 {args.graph.name} 的 metadata.alias_first_chapter")
        else:
            print("metadata.alias_first_chapter 已是最新，未改动")
    else:
        for alias, chapter in list(mapping.items())[:20]:
            print(f"  {alias} -> 第 {chapter} 章")
        if dated > 20:
            print(f"  …（共 {dated} 条）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
