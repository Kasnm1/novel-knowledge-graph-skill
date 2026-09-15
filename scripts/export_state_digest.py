#!/usr/bin/env python3
"""Export a compact "state as of chapter N" digest for extraction passes.

The digest now projects the graph through the shared temporal filter first.
Known future names, aliases, summaries and timed attributes therefore cannot
leak backwards into a continuation prompt. ``strict=False`` intentionally keeps
legacy untimed fields: this is an internal extraction aid, not a public
spoiler-safe artifact.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

from filter_graph_asof import filter_graph
from io_utils import atomic_write_text

FACET_ORDER = (
    "identity", "title", "level", "attribute", "skill", "martial_soul", "possession",
    "affiliation", "location", "health", "knowledge", "goal", "emotion", "relationship",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--graph", required=True, type=Path)
    parser.add_argument("--chapter", required=True, type=int)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--entity-type", action="append", default=[], help="Restrict to a type; repeatable")
    parser.add_argument("--only-changed", action="store_true", help="Skip entities with no records at all")
    parser.add_argument(
        "--mentioned-in",
        metavar="START-END",
        help="Keep only entities whose visible names/aliases appear in these chapters",
    )
    parser.add_argument("--chapters-dir", type=Path, help="Prepared chapter directory, for --mentioned-in")
    parser.add_argument(
        "--foreshadowing",
        action="store_true",
        help="Emit the foreshadowing digest instead: which clues are still open at the snapshot",
    )
    return parser.parse_args()


def foreshadowing_digest(graph: dict, chapter: int) -> list[str]:
    rows = []
    for record in graph.get("foreshadowing", []):
        if not isinstance(record, dict):
            continue
        planted = record.get("planted_chapter")
        if not isinstance(planted, int) or planted > chapter:
            continue
        status = str(record.get("status") or "open")
        if status in {"resolved", "partially_resolved", "false_lead", "paid_off"}:
            continue
        label = record.get("label") or record.get("observation") or ""
        rows.append((planted, record.get("id"), status, str(label)[:70]))
    rows.sort()
    lines = [f"# 第 {chapter} 章末未回收伏笔速查（{len(rows)} 条）", ""]
    lines.append(
        "你的章节若出现某条伏笔的**推进或回收文本**，按 EXTRACTION-SPEC.md 的「字段级补充」写法引用下表 ID："
        "只写 id 与 status／payoff_chapter／payoff_event_id／progression 等新推进的字段，"
        "不要复制 observation／interpretation／evidence_ids。已 resolved 的条目不可再次回收；没有新文本就不许改状态。"
    )
    lines.append("")
    for planted, clue_id, status, label in rows:
        lines.append(f"- `{clue_id}`（{status}，第{planted}章埋设）{label}")
    lines.append("")
    return lines


def render(value: object) -> str:
    if value is None:
        return "（无）"
    if isinstance(value, bool):
        return "是" if value else "否"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, dict):
        label = value.get("label", value.get("名称"))
        number = value.get("value")
        if label is not None and number is not None and label != number:
            return f"{label}（{number}）"
        return str(label if label is not None else number)
    if isinstance(value, list):
        return "、".join(render(item) for item in value)
    return str(value)


def _parse_window(value: str) -> tuple[int, int]:
    low, sep, high = value.partition("-")
    if not sep:
        raise ValueError("--mentioned-in must be START-END")
    start, end = int(low), int(high)
    if start > end:
        raise ValueError("--mentioned-in START must not exceed END")
    return start, end


def _alias_strings(entity: dict) -> list[str]:
    values: list[str] = []
    for raw in entity.get("aliases") or []:
        alias = raw.get("name") if isinstance(raw, dict) else raw
        if isinstance(alias, str) and alias:
            values.append(alias)
    return values


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    args = parse_args()
    raw_graph = json.loads(args.graph.resolve().read_text(encoding="utf-8"))
    chapter = args.chapter
    graph = filter_graph(raw_graph, chapter, strict=False)

    if args.foreshadowing:
        lines = foreshadowing_digest(graph, chapter)
        atomic_write_text(args.output, "\n".join(lines) + "\n")
        print(f"chapter {chapter}: foreshadowing digest -> {args.output.resolve()}")
        return 0

    entities = {e["id"]: e for e in graph.get("entities", []) if isinstance(e, dict) and isinstance(e.get("id"), str)}
    names = {entity_id: entity.get("name", entity_id) for entity_id, entity in entities.items()}

    mentioned: set[str] | None = None
    if args.mentioned_in:
        if not args.chapters_dir:
            raise SystemExit("--mentioned-in requires --chapters-dir")
        try:
            low, high = _parse_window(args.mentioned_in)
        except (TypeError, ValueError) as exc:
            raise SystemExit(str(exc)) from exc
        chapters_dir = args.chapters_dir.resolve()
        blob_parts: list[str] = []
        for number in range(low, high + 1):
            path = chapters_dir / f"{number:03d}.txt"
            if path.is_file():
                blob_parts.append(path.read_text(encoding="utf-8"))
        blob = "".join(blob_parts)
        mentioned = set()
        for entity_id, entity in entities.items():
            spellings = [str(entity.get("name") or ""), *_alias_strings(entity)]
            if any(spelling and spelling in blob for spelling in spellings):
                mentioned.add(entity_id)

    latest: dict[str, dict[str, tuple[object, int, str]]] = defaultdict(dict)
    for change in sorted(
        (row for row in graph.get("state_changes", []) if isinstance(row, dict)),
        key=lambda row: (row.get("chapter", 0), str(row.get("id") or "")),
    ):
        at = change.get("chapter")
        if not isinstance(at, int) or at > chapter:
            continue
        entity_id = change.get("entity_id")
        if entity_id not in entities:
            continue
        target = change.get("target_id")
        facet = str(change.get("facet"))
        key = f"{facet}·{names.get(target, target)}" if target else facet
        latest[entity_id][key] = (change.get("after"), at, facet)

    relations: dict[str, list[tuple[str, str, int]]] = defaultdict(list)
    for relation in graph.get("relations", []):
        if not isinstance(relation, dict):
            continue
        start = relation.get("valid_from")
        end = relation.get("valid_to")
        if not isinstance(start, int) or start > chapter:
            continue
        if isinstance(end, int) and end < chapter:
            continue
        source, target = relation.get("source_id"), relation.get("target_id")
        for owner, other in ((source, target), (target, source)):
            if owner in entities:
                relations[owner].append((str(relation.get("relation_type")), str(names.get(other, other)), start))

    lines = [f"# 第 {chapter} 章末状态速查", ""]
    lines.append(
        "这是你负责范围**开始之前**的既有状态。写 `before` 时以此为准，不要凭空猜。"
        f"本表未列的实体，说明它在第 {chapter} 章前没有任何状态变化记录。"
    )
    lines.append("")

    wanted = set(args.entity_type) if args.entity_type else None
    entity_count = 0
    for entity_id in sorted(entities, key=lambda key: (entities[key].get("first_chapter") or 0, key)):
        entity = entities[entity_id]
        if wanted and entity.get("type") not in wanted:
            continue
        if mentioned is not None and entity_id not in mentioned:
            continue
        rows = latest.get(entity_id, {})
        rels = relations.get(entity_id, [])
        attributes = entity.get("attributes") or {}
        if args.only_changed and not rows and not rels and not attributes:
            continue
        if (entity.get("first_chapter") or 0) > chapter and not rows:
            continue
        entity_count += 1
        lines.append(f"## {entity.get('name')}（`{entity_id}`，{entity.get('type')}）")
        if attributes:
            rendered = "；".join(f"{key}={render(value)}" for key, value in attributes.items())
            lines.append(f"- 固定属性：{rendered}")
        order = {facet: index for index, facet in enumerate(FACET_ORDER)}

        def facet_rank(item: tuple[str, tuple[object, int, str]]) -> tuple[int, str]:
            facet = item[0].split("·", 1)[0]
            return order.get(facet, len(FACET_ORDER)), item[0]

        for composite, (value, at, _facet) in sorted(rows.items(), key=facet_rank):
            facet = composite.split("·", 1)[0]
            label = composite.split("·", 1)[1] if "·" in composite else ""
            suffix = f"（{label}）" if label else ""
            lines.append(f"- {facet}{suffix}：{render(value)}　←第 {at} 章")
        if rels:
            grouped: dict[str, list[str]] = defaultdict(list)
            for relation_type, other, _start in rels:
                grouped[relation_type].append(other)
            rendered = "；".join(f"{key}：{'、'.join(sorted(set(values)))}" for key, values in sorted(grouped.items()))
            lines.append(f"- 既有关系：{rendered}")
        lines.append("")

    atomic_write_text(args.output, "\n".join(lines) + "\n")
    print(f"chapter {chapter}: {entity_count} entities -> {args.output.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
