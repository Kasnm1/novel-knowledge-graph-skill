#!/usr/bin/env python3
"""Generate evidence-review candidates for legacy runs without inventing facts.

The scanner uses graph structure and, optionally, prepared chapter text. Every
candidate is explicitly unresolved until a later evidence-closure pass confirms
or excludes it.
"""
from __future__ import annotations

import argparse
import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from controlled_vocab import category_ids

PATTERNS = {
    "commitment": re.compile(r"(答应|承诺|发誓|立誓|约定|赌约|赌一把|三年之约|一定会|必将)"),
    "secret": re.compile(r"(秘密|真相|隐瞒|身份|不能告诉|别让.*知道|瞒着|泄露)"),
    "mortality": re.compile(r"(死了|死亡|身亡|陨落|被杀|杀死|复活|重生|还魂|死而复生)"),
}


def recs(value: Any) -> list[dict[str, Any]]:
    return [x for x in value if isinstance(x, dict)] if isinstance(value, list) else []


def structural_candidates(graph: dict[str, Any], relation_gap_threshold: int = 3) -> list[dict[str, Any]]:
    entities = recs(graph.get("entities"))
    events = recs(graph.get("events"))
    relations = recs(graph.get("relations"))
    roles = recs(graph.get("item_roles"))
    ids_by_type: dict[str, set[str]] = defaultdict(set)
    for entity in entities:
        if isinstance(entity.get("id"), str):
            ids_by_type[str(entity.get("type"))].add(entity["id"])
    out: list[dict[str, Any]] = []

    def add(kind, record_id, reason, chapter=None, related_ids=None):
        out.append({
            "candidate_kind": kind, "record_id": record_id, "chapter": chapter,
            "related_ids": related_ids or [], "reason": reason, "status": "unresolved",
        })

    for entity in entities:
        if entity.get("type") == "skill" and not category_ids(entity.get("categories")):
            add("skill_category", entity.get("id"), "技能尚无受控分类", entity.get("first_chapter"), [entity.get("id")])

    parents = {r.get("source_id") for r in relations if r.get("relation_type") in {"located_in", "part_of"}}
    for entity_id in ids_by_type["location"]:
        if entity_id not in parents:
            add("location_hierarchy", entity_id, "地点尚无 located_in/part_of 父级；顶层地点需人工明确", related_ids=[entity_id])

    for event in events:
        if event.get("type") == "battle" and not isinstance(event.get("combat"), dict):
            add("combat_structure", event.get("id"), "battle 事件尚未结构化胜负/阵营", event.get("chapter"), list(event.get("participant_ids") or []))
        if not event.get("location_id"):
            add("event_location", event.get("id"), "事件尚无 location_id", event.get("chapter"), list(event.get("participant_ids") or []))

    for role in roles:
        if not role.get("cause_event_id"):
            add("item_role_cause", role.get("id"), "物品获得/转移尚未连接 cause_event_id", role.get("valid_from"), [role.get("item_id"), role.get("entity_id")])

    characters = ids_by_type["character"]
    counts: Counter[tuple[str, str]] = Counter()
    pair_events: dict[tuple[str, str], list[str]] = defaultdict(list)
    for event in events:
        people = sorted(set(event.get("participant_ids") or []) & characters) if isinstance(event.get("participant_ids"), list) else []
        for i in range(len(people)):
            for j in range(i + 1, len(people)):
                key = (people[i], people[j])
                counts[key] += 1
                if isinstance(event.get("id"), str):
                    pair_events[key].append(event["id"])
    related = {
        tuple(sorted((r.get("source_id"), r.get("target_id"))))
        for r in relations if r.get("source_id") in characters and r.get("target_id") in characters
    }
    for pair, count in counts.items():
        if count >= relation_gap_threshold and pair not in related:
            add("side_relation", ":".join(pair), f"共同事件 {count} 次但无人物关系边", related_ids=list(pair) + pair_events[pair][:10])
    return out


def text_candidates(chapters_jsonl: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line in chapters_jsonl.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        item = json.loads(line)
        chapter = item.get("chapter")
        path = Path(item.get("text_path", ""))
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        for kind, pattern in PATTERNS.items():
            for match in list(pattern.finditer(text))[:20]:
                lo = max(0, match.start() - 60)
                hi = min(len(text), match.end() + 100)
                rows.append({
                    "candidate_kind": kind, "chapter": chapter, "record_id": None,
                    "related_ids": [], "reason": "source_keyword_candidate",
                    "snippet": text[lo:hi].replace("\n", " "), "status": "unresolved",
                })
    return rows


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--graph", required=True, type=Path)
    p.add_argument("--output", required=True, type=Path)
    p.add_argument("--chapters-jsonl", type=Path)
    p.add_argument("--relation-gap-threshold", type=int, default=3)
    args = p.parse_args()
    graph = json.loads(args.graph.read_text(encoding="utf-8"))
    rows = structural_candidates(graph, max(1, args.relation_gap_threshold))
    if args.chapters_jsonl and args.chapters_jsonl.exists():
        rows.extend(text_candidates(args.chapters_jsonl))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps({
        "candidates": rows,
        "counts": dict(Counter(row["candidate_kind"] for row in rows)),
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"output": str(args.output), "candidates": len(rows)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
