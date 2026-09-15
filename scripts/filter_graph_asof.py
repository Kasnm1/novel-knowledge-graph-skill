#!/usr/bin/env python3
"""Create a strict spoiler-safe canonical-graph snapshot as of chapter N.

The canonical graph stays immutable. This module closes every known temporal
surface before any derived view is built: names/aliases, summaries, attributes,
current_state, style observations, relation/commitment status, evidence and all
chapter-bound arrays. Unknown temporal provenance is removed in strict mode and
reported under ``metadata.temporal_provenance_gaps`` instead of being allowed to
leak future prose.
"""
from __future__ import annotations

import argparse
import json
from copy import deepcopy
from pathlib import Path
from typing import Any, Iterable

CHAPTER_FIELDS = (
    "chapter", "first_chapter", "created_chapter", "chapter_start", "valid_from",
    "planted_chapter", "first_meeting_chapter", "ambiguity_started_chapter",
)
PROSE_TEMPORAL_FIELDS = ("summary", "description")


def recs(value: Any) -> list[dict[str, Any]]:
    return [x for x in value if isinstance(x, dict)] if isinstance(value, list) else []


def _chapter(value: Any) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def first_visible_chapter(record: dict[str, Any]) -> int | None:
    values = [_chapter(record.get(field)) for field in CHAPTER_FIELDS]
    values = [value for value in values if value is not None]
    return min(values) if values else None


def visible_record(record: dict[str, Any], chapter: int, *, strict_unknown: bool = False) -> bool:
    start = first_visible_chapter(record)
    if start is None:
        return not strict_unknown
    return start <= chapter


def _meta_lookup(mapping: Any, entity_id: str, key: str | None = None) -> int | None:
    if not isinstance(mapping, dict):
        return None
    if key is None:
        value = mapping.get(entity_id)
        return _chapter(value)
    nested = mapping.get(entity_id)
    if isinstance(nested, dict):
        return _chapter(nested.get(key))
    return _chapter(mapping.get(key))


def _history_value(history: Any, chapter: int, value_keys: Iterable[str]) -> Any:
    rows = []
    for row in recs(history):
        start = _chapter(row.get("valid_from"))
        if start is None:
            start = _chapter(row.get("chapter"))
        if start is None or start > chapter:
            continue
        rows.append((start, str(row.get("id") or ""), row))
    if not rows:
        return None
    row = max(rows, key=lambda item: (item[0], item[1]))[2]
    for key in value_keys:
        if key in row:
            return deepcopy(row.get(key))
    return None


def _filter_history(history: Any, chapter: int) -> list[dict[str, Any]]:
    out = []
    for row in recs(history):
        start = _chapter(row.get("valid_from"))
        if start is None:
            start = _chapter(row.get("chapter"))
        if start is not None and start > chapter:
            continue
        copy = deepcopy(row)
        if _chapter(copy.get("valid_to")) is not None and copy["valid_to"] > chapter:
            copy["valid_to"] = None
        out.append(copy)
    return out


def _safe_name(entity: dict[str, Any], chapter: int, meta: dict[str, Any], gaps: list[str]) -> str:
    entity_id = str(entity.get("id") or "")
    value = _history_value(entity.get("name_history"), chapter, ("name", "value"))
    if isinstance(value, str) and value.strip():
        return value.strip()
    name_first = _chapter(entity.get("name_first_chapter"))
    if name_first is None:
        name_first = _meta_lookup(meta.get("name_first_chapter"), entity_id)
    if name_first is not None and name_first > chapter:
        gaps.append(f"entity:{entity_id}:canonical_name_after_cutoff")
        return f"[{entity.get('type') or 'entity'}:{entity_id}]"
    return str(entity.get("name") or entity_id)


def _filter_aliases(entity: dict[str, Any], chapter: int, meta: dict[str, Any], gaps: list[str], strict: bool) -> None:
    entity_id = str(entity.get("id") or "")
    alias_meta = meta.get("alias_first_chapter")
    for field in ("aliases", "historical_names", "titles"):
        values = entity.get(field)
        if not isinstance(values, list):
            continue
        kept = []
        for value in values:
            if isinstance(value, dict):
                start = first_visible_chapter(value)
                if start is None:
                    start = _chapter(value.get("first_chapter"))
                if start is None and strict:
                    gaps.append(f"entity:{entity_id}:{field}:untimed")
                    continue
                if start is not None and start > chapter:
                    continue
                copy = deepcopy(value)
                if _chapter(copy.get("valid_to")) is not None and copy["valid_to"] > chapter:
                    copy["valid_to"] = None
                kept.append(copy)
                continue
            if not isinstance(value, str):
                continue
            start = None
            if isinstance(alias_meta, dict):
                nested = alias_meta.get(entity_id)
                if isinstance(nested, dict):
                    start = _chapter(nested.get(value))
                if start is None:
                    start = _chapter(alias_meta.get(value))
            if start is None and strict:
                gaps.append(f"entity:{entity_id}:{field}:{value}:untimed")
                continue
            if start is None or start <= chapter:
                kept.append(value)
        entity[field] = kept


def _project_entity_prose(entity: dict[str, Any], chapter: int, meta: dict[str, Any], gaps: list[str], strict: bool) -> None:
    entity_id = str(entity.get("id") or "")
    for field in PROSE_TEMPORAL_FIELDS:
        history = entity.get(f"{field}_history")
        hist_value = _history_value(history, chapter, (field, "value", "text"))
        if hist_value is not None:
            entity[field] = hist_value
            entity[f"{field}_history"] = _filter_history(history, chapter)
            continue
        first = _chapter(entity.get(f"{field}_chapter"))
        if first is None:
            first = _chapter(entity.get(f"{field}_first_chapter"))
        if first is None:
            first = _meta_lookup(meta.get(f"{field}_first_chapter"), entity_id)
        if first is not None and first > chapter:
            entity.pop(field, None)
        elif field in entity and strict and first is None:
            gaps.append(f"entity:{entity_id}:{field}:untimed")
            entity.pop(field, None)


def _project_attributes(entity: dict[str, Any], chapter: int, meta: dict[str, Any], gaps: list[str], strict: bool) -> None:
    entity_id = str(entity.get("id") or "")
    history = recs(entity.get("attribute_history")) + recs(entity.get("attributes_history"))
    reconstructed: dict[str, Any] = {}
    for row in sorted(history, key=lambda r: (_chapter(r.get("chapter")) or _chapter(r.get("valid_from")) or 0, str(r.get("id") or ""))):
        start = _chapter(row.get("chapter"))
        if start is None:
            start = _chapter(row.get("valid_from"))
        if start is None or start > chapter:
            continue
        key = row.get("key") or row.get("attribute")
        if isinstance(key, str):
            reconstructed[key] = deepcopy(row.get("value"))
    raw = entity.get("attributes")
    if isinstance(raw, dict):
        first_map = meta.get("attribute_first_chapter")
        for key, value in raw.items():
            if key in reconstructed:
                continue
            first = _meta_lookup(first_map, entity_id, key)
            if first is not None and first <= chapter:
                reconstructed[key] = deepcopy(value)
            elif first is None and not strict:
                reconstructed[key] = deepcopy(value)
            elif first is None and strict:
                gaps.append(f"entity:{entity_id}:attribute:{key}:untimed")
    entity["attributes"] = reconstructed
    if history:
        entity["attribute_history"] = _filter_history(history, chapter)
    entity.pop("attributes_history", None)
    entity.pop("current_state", None)


def _filter_evidence_ids(record: dict[str, Any], evidence_ids: set[str]) -> None:
    if isinstance(record.get("evidence_ids"), list):
        record["evidence_ids"] = [x for x in record["evidence_ids"] if x in evidence_ids]


def _commitment_asof(row: dict[str, Any], chapter: int) -> None:
    observations = [o for o in recs(row.get("observations")) if _chapter(o.get("chapter")) is None or o["chapter"] <= chapter]
    observations.sort(key=lambda o: (_chapter(o.get("chapter")) or 0, str(o.get("id") or "")))
    row["observations"] = observations
    resolved = _chapter(row.get("resolved_chapter"))
    if resolved is not None and resolved > chapter:
        row["resolved_chapter"] = None
        row["resolution"] = None
    observed_status = next((o.get("status") for o in reversed(observations) if isinstance(o.get("status"), str)), None)
    if observed_status:
        row["status"] = observed_status
    elif resolved is None or resolved > chapter:
        row["status"] = "active"


def filter_graph(graph: dict[str, Any], chapter: int, *, strict: bool = True) -> dict[str, Any]:
    if not isinstance(chapter, int) or isinstance(chapter, bool) or chapter < 0:
        raise ValueError("chapter must be a non-negative integer")
    out = deepcopy(graph)
    meta = out.get("metadata") if isinstance(out.get("metadata"), dict) else {}
    gaps: list[str] = []

    entities = []
    for entity in recs(out.get("entities")):
        if _chapter(entity.get("first_chapter")) is not None and entity["first_chapter"] > chapter:
            continue
        entity["name"] = _safe_name(entity, chapter, meta, gaps)
        entity["name_history"] = _filter_history(entity.get("name_history"), chapter)
        _filter_aliases(entity, chapter, meta, gaps, strict)
        _project_entity_prose(entity, chapter, meta, gaps, strict)
        _project_attributes(entity, chapter, meta, gaps, strict)
        entities.append(entity)
    out["entities"] = entities
    entity_ids = {e.get("id") for e in entities}

    evidence = [e for e in recs(out.get("evidence")) if _chapter(e.get("chapter")) is None or e["chapter"] <= chapter]
    out["evidence"] = evidence
    evidence_ids = {e.get("id") for e in evidence if isinstance(e.get("id"), str)}

    events = []
    for event in recs(out.get("events")):
        if _chapter(event.get("chapter")) is not None and event["chapter"] > chapter:
            continue
        event["participant_ids"] = [x for x in event.get("participant_ids", []) if x in entity_ids] if isinstance(event.get("participant_ids"), list) else []
        if event.get("location_id") not in entity_ids:
            event.pop("location_id", None)
        _filter_evidence_ids(event, evidence_ids)
        events.append(event)
    out["events"] = events
    event_ids = {e.get("id") for e in events}

    relations = []
    for relation in recs(out.get("relations")):
        if relation.get("source_id") not in entity_ids or relation.get("target_id") not in entity_ids:
            continue
        start = _chapter(relation.get("valid_from"))
        if start is not None and start > chapter:
            continue
        original_end = _chapter(relation.get("valid_to"))
        relation["observations"] = [o for o in recs(relation.get("observations")) if _chapter(o.get("chapter")) is None or o["chapter"] <= chapter]
        _filter_evidence_ids(relation, evidence_ids)
        if original_end is not None and original_end > chapter:
            relation.pop("valid_to", None)
            if relation.get("status") not in {None, "active", "uncertain"}:
                relation["status"] = "active"
        relations.append(relation)
    out["relations"] = relations

    state_changes = []
    for change in recs(out.get("state_changes")):
        if change.get("entity_id") not in entity_ids:
            continue
        if _chapter(change.get("chapter")) is not None and change["chapter"] > chapter:
            continue
        if change.get("target_id") is not None and change.get("target_id") not in entity_ids:
            continue
        _filter_evidence_ids(change, evidence_ids)
        if _chapter(change.get("end_chapter")) is not None and change["end_chapter"] > chapter:
            change.pop("end_chapter", None)
        state_changes.append(change)
    out["state_changes"] = state_changes

    generic = (
        "intimate_acts", "level_conversions", "character_traits", "chapter_summaries",
        "item_roles", "commitments", "review_issues",
    )
    for key in generic:
        filtered = []
        for row in recs(out.get(key)):
            if not visible_record(row, chapter, strict_unknown=False):
                continue
            _filter_evidence_ids(row, evidence_ids)
            if key == "commitments":
                _commitment_asof(row, chapter)
            elif key == "item_roles" and _chapter(row.get("valid_to")) is not None and row["valid_to"] > chapter:
                row.pop("valid_to", None)
            filtered.append(row)
        out[key] = filtered

    routes = []
    for route in recs(out.get("romance_routes")):
        first = _chapter(route.get("first_meeting_chapter"))
        if first is not None and first > chapter:
            continue
        ambiguity = _chapter(route.get("ambiguity_started_chapter"))
        confirmed = _chapter(route.get("confirmed_chapter"))
        intimacy = _chapter(route.get("first_sex_chapter"))
        for chfield, evfield in (("confirmed_chapter", "confirmed_evidence_ids"), ("first_sex_chapter", "first_sex_evidence_ids"), ("ambiguity_started_chapter", "ambiguity_evidence_ids")):
            value = _chapter(route.get(chfield))
            if value is not None and value > chapter:
                route[chfield] = None
                route[evfield] = []
        if confirmed is not None and confirmed <= chapter:
            route["status"] = "confirmed"
        elif ambiguity is not None and ambiguity <= chapter:
            route["status"] = "ambiguous"
        else:
            route["status"] = "introduced"
        if intimacy is not None and intimacy > chapter:
            route["first_sex_chapter"] = None
            route["first_sex_evidence_ids"] = []
        routes.append(route)
    out["romance_routes"] = routes

    arcs = []
    for arc in recs(out.get("story_arcs")):
        start = _chapter(arc.get("chapter_start"))
        if start is not None and start > chapter:
            continue
        if _chapter(arc.get("chapter_end")) is not None and arc["chapter_end"] > chapter:
            arc["chapter_end"] = None
            if arc.get("status") in {"closed", "complete", "completed", "resolved"}:
                arc["status"] = "active"
        arc["event_ids"] = [x for x in arc.get("event_ids", []) if x in event_ids] if isinstance(arc.get("event_ids"), list) else []
        arcs.append(arc)
    out["story_arcs"] = arcs

    fs_rows = []
    for fs in recs(out.get("foreshadowing")):
        planted = _chapter(fs.get("planted_chapter"))
        if planted is not None and planted > chapter:
            continue
        payoff = _chapter(fs.get("payoff_chapter"))
        if payoff is not None and payoff > chapter:
            fs["payoff_chapter"] = None
            if fs.get("status") in {"resolved", "paid_off"}:
                fs["status"] = "active"
        fs["progression"] = [p for p in recs(fs.get("progression")) if _chapter(p.get("chapter")) is None or p["chapter"] <= chapter]
        _filter_evidence_ids(fs, evidence_ids)
        fs_rows.append(fs)
    out["foreshadowing"] = fs_rows

    style_rows = []
    for obs in recs(out.get("style_observations")):
        start = first_visible_chapter(obs)
        if start is None:
            start = _chapter(obs.get("chapter_start"))
        if start is None and strict:
            gaps.append(f"style_observation:{obs.get('id') or '?'}:untimed")
            continue
        if start is not None and start > chapter:
            continue
        copy = deepcopy(obs)
        if _chapter(copy.get("chapter_end")) is not None and copy["chapter_end"] > chapter:
            copy["chapter_end"] = chapter
        _filter_evidence_ids(copy, evidence_ids)
        style_rows.append(copy)
    if "style_observations" in out:
        out["style_observations"] = style_rows

    meta["spoiler_cutoff_chapter"] = chapter
    meta["spoiler_strict"] = strict
    meta["temporal_provenance_gaps"] = sorted(set(gaps))
    analyzed = [c for c in meta.get("analyzed_chapters", []) if isinstance(c, int) and c <= chapter]
    meta["analyzed_chapters"] = analyzed
    if analyzed:
        meta["chapter_start"], meta["chapter_end"] = min(analyzed), max(analyzed)
    else:
        end = meta.get("chapter_end")
        meta["chapter_end"] = min(chapter, end) if isinstance(end, int) else chapter
    out["metadata"] = meta
    return out


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--graph", required=True, type=Path)
    p.add_argument("--chapter", required=True, type=int)
    p.add_argument("--output", required=True, type=Path)
    p.add_argument("--compat", action="store_true", help="Retain untimed legacy prose/aliases instead of strict spoiler closure")
    args = p.parse_args()
    graph = json.loads(args.graph.read_text(encoding="utf-8"))
    filtered = filter_graph(graph, args.chapter, strict=not args.compat)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(filtered, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({
        "output": str(args.output), "chapter": args.chapter,
        "entities": len(filtered.get("entities", [])), "events": len(filtered.get("events", [])),
        "temporal_provenance_gaps": len(filtered.get("metadata", {}).get("temporal_provenance_gaps", [])),
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
