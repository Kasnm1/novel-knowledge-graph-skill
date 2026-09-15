#!/usr/bin/env python3
"""Create a spoiler-safe derived graph visible only through chapter N.

This never mutates the canonical graph.  It filters future entities, events,
evidence, relations, state changes, milestones, aliases/name-history and payoff
information before rendering so hidden records cannot leak through search,
tooltips or counters.
"""
from __future__ import annotations

import argparse
import json
from copy import deepcopy
from pathlib import Path
from typing import Any

CHAPTER_FIELDS = (
    "chapter", "first_chapter", "created_chapter", "chapter_start", "valid_from",
    "planted_chapter", "first_meeting_chapter", "ambiguity_started_chapter",
)


def recs(value: Any) -> list[dict[str, Any]]:
    return [x for x in value if isinstance(x, dict)] if isinstance(value, list) else []


def first_visible_chapter(record: dict[str, Any]) -> int | None:
    values = [record.get(f) for f in CHAPTER_FIELDS if isinstance(record.get(f), int)]
    return min(values) if values else None


def visible_record(record: dict[str, Any], chapter: int) -> bool:
    start = first_visible_chapter(record)
    return start is None or start <= chapter


def filter_name_history(entity: dict[str, Any], chapter: int) -> None:
    history = []
    for row in recs(entity.get("name_history")):
        start = row.get("valid_from")
        if isinstance(start, int) and start > chapter:
            continue
        copied = deepcopy(row)
        if isinstance(copied.get("valid_to"), int) and copied["valid_to"] > chapter:
            copied["valid_to"] = None
        history.append(copied)
    entity["name_history"] = history
    # Alias strings have no chapter themselves.  If alias_first_chapter exists,
    # use it; otherwise retain for compatibility rather than inventing timing.


def filter_graph(graph: dict[str, Any], chapter: int) -> dict[str, Any]:
    out = deepcopy(graph)
    meta = out.get("metadata") if isinstance(out.get("metadata"), dict) else {}
    alias_first = meta.get("alias_first_chapter") if isinstance(meta.get("alias_first_chapter"), dict) else {}

    entities = []
    for entity in recs(out.get("entities")):
        if isinstance(entity.get("first_chapter"), int) and entity["first_chapter"] > chapter:
            continue
        filter_name_history(entity, chapter)
        for field in ("aliases", "historical_names", "titles"):
            values = entity.get(field)
            if isinstance(values, list):
                entity[field] = [v for v in values if not isinstance(v, str) or not isinstance(alias_first.get(v), int) or alias_first[v] <= chapter]
        entities.append(entity)
    out["entities"] = entities
    entity_ids = {e.get("id") for e in entities}

    evidence = [e for e in recs(out.get("evidence")) if not isinstance(e.get("chapter"), int) or e["chapter"] <= chapter]
    out["evidence"] = evidence
    evidence_ids = {e.get("id") for e in evidence}

    events = [e for e in recs(out.get("events")) if not isinstance(e.get("chapter"), int) or e["chapter"] <= chapter]
    for event in events:
        event["participant_ids"] = [x for x in event.get("participant_ids", []) if x in entity_ids] if isinstance(event.get("participant_ids"), list) else []
        if event.get("location_id") not in entity_ids:
            event.pop("location_id", None)
        event["evidence_ids"] = [x for x in event.get("evidence_ids", []) if x in evidence_ids]
        payoff = event.get("payoff")
        if isinstance(payoff, dict):
            payoff["setup_ids"] = list(payoff.get("setup_ids") or [])
    out["events"] = events
    event_ids = {e.get("id") for e in events}

    relations = []
    for relation in recs(out.get("relations")):
        if relation.get("source_id") not in entity_ids or relation.get("target_id") not in entity_ids:
            continue
        if isinstance(relation.get("valid_from"), int) and relation["valid_from"] > chapter:
            continue
        relation["evidence_ids"] = [x for x in relation.get("evidence_ids", []) if x in evidence_ids]
        relation["observations"] = [o for o in recs(relation.get("observations")) if not isinstance(o.get("chapter"), int) or o["chapter"] <= chapter]
        if isinstance(relation.get("valid_to"), int) and relation["valid_to"] > chapter:
            relation.pop("valid_to", None)
        relations.append(relation)
    out["relations"] = relations

    state_changes = []
    for change in recs(out.get("state_changes")):
        if change.get("entity_id") not in entity_ids:
            continue
        if isinstance(change.get("chapter"), int) and change["chapter"] > chapter:
            continue
        if change.get("target_id") is not None and change.get("target_id") not in entity_ids:
            continue
        change["evidence_ids"] = [x for x in change.get("evidence_ids", []) if x in evidence_ids]
        if isinstance(change.get("end_chapter"), int) and change["end_chapter"] > chapter:
            change.pop("end_chapter", None)
        state_changes.append(change)
    out["state_changes"] = state_changes

    # Generic arrays whose primary chapter can be determined mechanically.
    for key in ("intimate_acts", "level_conversions", "character_traits", "chapter_summaries", "item_roles", "commitments", "review_issues"):
        filtered = []
        for row in recs(out.get(key)):
            if not visible_record(row, chapter):
                continue
            row["evidence_ids"] = [x for x in row.get("evidence_ids", []) if x in evidence_ids] if isinstance(row.get("evidence_ids"), list) else row.get("evidence_ids")
            if key == "commitments":
                row["observations"] = [o for o in recs(row.get("observations")) if not isinstance(o.get("chapter"), int) or o["chapter"] <= chapter]
                if isinstance(row.get("resolved_chapter"), int) and row["resolved_chapter"] > chapter:
                    row["resolved_chapter"] = None; row["resolution"] = None
                    if row.get("status") not in {"active", "uncertain"}: row["status"] = "active"
            filtered.append(row)
        out[key] = filtered

    routes = []
    for route in recs(out.get("romance_routes")):
        first = route.get("first_meeting_chapter")
        if isinstance(first, int) and first > chapter:
            continue
        for chfield, evfield in (("confirmed_chapter", "confirmed_evidence_ids"), ("first_sex_chapter", "first_sex_evidence_ids"), ("ambiguity_started_chapter", "ambiguity_evidence_ids")):
            if isinstance(route.get(chfield), int) and route[chfield] > chapter:
                route[chfield] = None; route[evfield] = []
        routes.append(route)
    out["romance_routes"] = routes

    arcs = []
    for arc in recs(out.get("story_arcs")):
        if isinstance(arc.get("chapter_start"), int) and arc["chapter_start"] > chapter:
            continue
        if isinstance(arc.get("chapter_end"), int) and arc["chapter_end"] > chapter:
            arc["chapter_end"] = None
        arc["event_ids"] = [x for x in arc.get("event_ids", []) if x in event_ids] if isinstance(arc.get("event_ids"), list) else []
        arcs.append(arc)
    out["story_arcs"] = arcs

    fs_rows = []
    for fs in recs(out.get("foreshadowing")):
        if isinstance(fs.get("planted_chapter"), int) and fs["planted_chapter"] > chapter:
            continue
        if isinstance(fs.get("payoff_chapter"), int) and fs["payoff_chapter"] > chapter:
            fs["payoff_chapter"] = None
            if fs.get("status") in {"resolved", "paid_off"}: fs["status"] = "active"
        fs["progression"] = [p for p in recs(fs.get("progression")) if not isinstance(p.get("chapter"), int) or p["chapter"] <= chapter]
        fs_rows.append(fs)
    out["foreshadowing"] = fs_rows

    meta["spoiler_cutoff_chapter"] = chapter
    analyzed = [c for c in meta.get("analyzed_chapters", []) if isinstance(c, int) and c <= chapter]
    meta["analyzed_chapters"] = analyzed
    if analyzed:
        meta["chapter_start"], meta["chapter_end"] = min(analyzed), max(analyzed)
    else:
        meta["chapter_end"] = min(chapter, meta.get("chapter_end", chapter) if isinstance(meta.get("chapter_end"), int) else chapter)
    out["metadata"] = meta
    return out


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--graph", required=True, type=Path)
    p.add_argument("--chapter", required=True, type=int)
    p.add_argument("--output", required=True, type=Path)
    args = p.parse_args()
    graph = json.loads(args.graph.read_text(encoding="utf-8"))
    filtered = filter_graph(graph, args.chapter)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(filtered, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"output": str(args.output), "chapter": args.chapter, "entities": len(filtered.get("entities", [])), "events": len(filtered.get("events", []))}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
