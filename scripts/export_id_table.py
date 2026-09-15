#!/usr/bin/env python3
"""Export the existing graph's entity ID table, for a continuation run's spec.

When a run is extended into later chapters, every new pass must reuse the IDs of
entities that already exist. Left to invent their own, passes produce
`char_xuanshui_dan` and `item_xuanshui_dan` for one thing, and the divergence is
only visible after merging. This script writes the canonical table straight from
`graph.json`, so the spec cannot drift from the graph it continues.

Also lists the vocabulary values the graph already uses, so a new pass picks
existing spellings instead of inventing near-synonyms.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

VOCABULARY_GROUPS = (
    "relation_type",
    "facet",
    "action",
    "confidence",
    "status",
    "inclusion_basis",
    "consent_context",
    "progression_kind",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--graph", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path, help="Markdown table path")
    parser.add_argument("--chapter-end", type=int, help="Last analyzed chapter, for the header")
    return parser.parse_args()


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    args = parse_args()
    graph = json.loads(args.graph.resolve().read_text(encoding="utf-8"))
    entities = [e for e in graph.get("entities", []) if isinstance(e, dict)]

    by_type: dict[str, list[dict]] = defaultdict(list)
    for entity in entities:
        by_type[str(entity.get("type"))].append(entity)
    for group in by_type.values():
        group.sort(key=lambda e: (e.get("first_chapter") or 0, str(e.get("id"))))

    lines: list[str] = []
    scope = graph.get("metadata", {})
    first = scope.get("chapter_start", "?")
    last = args.chapter_end or scope.get("chapter_end", "?")
    lines.append(f"# 已有实体 ID 表（第 {first}-{last} 章，从 graph.json 生成）")
    lines.append("")
    lines.append(
        f"共 {len(entities)} 个实体。**新分片必须复用下表 ID**，不得为同一实体另造 ID；"
        "表中没有的实体才按命名规则新建。"
    )
    lines.append("")
    for entity_type in sorted(by_type):
        group = by_type[entity_type]
        lines.append(f"## {entity_type}（{len(group)}）")
        lines.append("")
        lines.append("| ID | 名称 | 别名 | 首见章 |")
        lines.append("|---|---|---|---|")
        for entity in group:
            aliases = entity.get("aliases") or []
            alias_text = "、".join(str(a) for a in aliases) if isinstance(aliases, list) else str(aliases)
            lines.append(
                f"| `{entity.get('id')}` | {entity.get('name')} | {alias_text or '—'} | {entity.get('first_chapter')} |"
            )
        lines.append("")

    # Vocabulary actually in use, so new records reuse these spellings.
    used: dict[str, set[str]] = defaultdict(set)
    for record in graph.get("relations", []):
        if isinstance(record, dict):
            used["relation_type"].add(str(record.get("relation_type")))
            if record.get("status"):
                used["status"].add(str(record["status"]))
    for record in graph.get("state_changes", []):
        if isinstance(record, dict):
            used["facet"].add(str(record.get("facet")))
            used["action"].add(str(record.get("action")))
            if record.get("confidence"):
                used["confidence"].add(str(record["confidence"]))
    for record in graph.get("foreshadowing", []):
        if isinstance(record, dict):
            if record.get("status"):
                used["status"].add(str(record["status"]))
            for step in record.get("progression") or []:
                if isinstance(step, dict) and step.get("kind"):
                    used["progression_kind"].add(str(step["kind"]))
    for record in graph.get("intimate_acts", []):
        if isinstance(record, dict):
            if record.get("act_type"):
                used["intimacy_act_type"].add(str(record["act_type"]))
            if record.get("consent"):
                used["consent_context"].add(str(record["consent"]))
            if record.get("ejaculation_site"):
                used["ejaculation_site"].add(str(record["ejaculation_site"]))
    for record in graph.get("romance_routes", []):
        if isinstance(record, dict):
            if record.get("status"):
                used["status"].add(str(record["status"]))
            if record.get("inclusion_basis"):
                used["inclusion_basis"].add(str(record["inclusion_basis"]))
            if record.get("consent_context"):
                used["consent_context"].add(str(record["consent_context"]))

    lines.append("## 已有枚举取值（新记录优先复用这些写法）")
    lines.append("")
    for group in VOCABULARY_GROUPS:
        values = sorted(v for v in used.get(group, set()) if v and v != "None")
        if values:
            lines.append(f"- `{group}`：{'、'.join(values)}")
    lines.append("")

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"entities: {len(entities)}")
    for entity_type in sorted(by_type):
        print(f"  {entity_type}: {len(by_type[entity_type])}")
    print(f"wrote {args.output.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
