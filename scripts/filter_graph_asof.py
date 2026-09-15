#!/usr/bin/env python3
"""Create a strict spoiler-safe canonical-graph snapshot as of chapter N.

The canonical graph stays immutable. This module closes every known temporal
surface before any derived view is built: names/aliases, summaries, attributes,
current_state, style observations, relation/commitment status, evidence and all
chapter-bound arrays. Unknown temporal provenance is removed in strict mode and
reported without echoing hidden prose.
"""
from __future__ import annotations

import argparse
import json
from copy import deepcopy
from pathlib import Path
from typing import Any, Iterable

from io_utils import atomic_write_json

CHAPTER_FIELDS = (
    "chapter", "first_chapter", "created_chapter", "chapter_start", "valid_from",
    "planted_chapter", "first_meeting_chapter", "ambiguity_started_chapter",
)
PROSE_TEMPORAL_FIELDS = ("summary", "description")


def recs(value: Any) -> list[dict[str, Any]]:
    return [item for item in value if isinstance(item, dict)] if isinstance(value, list) else []


def _chapter(value: Any) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def first_visible_chapter(record: dict[str, Any]) -> int | None:
    values = [_chapter(record.get(field)) for field in CHAPTER_FIELDS]
    present = [value for value in values if value is not None]
    return min(present) if present else None


def visible_record(record: dict[str, Any], chapter: int, *, strict_unknown: bool = False) -> bool:
    start = first_visible_chapter(record)
    return (not strict_unknown) if start is None else start <= chapter


def _meta_lookup(mapping: Any, entity_id: str, key: str | None = None) -> int | None:
    if not isinstance(mapping, dict):
        return None
    if key is None:
        return _chapter(mapping.get(entity_id))
    nested = mapping.get(entity_id)
    return _chapter(nested.get(key)) if isinstance(nested, dict) else None


def _history_value(history: Any, chapter: int, value_keys: Iterable[str]) -> Any:
    rows: list[tuple[int, str, dict[str, Any]]] = []
    for row in recs(history):
        start = _chapter(row.get("valid_from"))
        if start is None:
            start = _chapter(row.get("chapter"))
        if start is None or start > chapter:
            continue
        rows.append((start, str(row.get("id") or ""), row))
    if not rows:
        return None
    chosen = max(rows, key=lambda item: (item[0], item[1]))[2]
    for key in value_keys:
        if key in chosen:
            return deepcopy(chosen.get(key))
    return None


def _filter_history(history: Any, chapter: int) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for row in recs(history):
        start = _chapter(row.get("valid_from"))
        if start is None:
            start = _chapter(row.get("chapter"))
        if start is not None and start > chapter:
            continue
        copied = deepcopy(row)
        end = _chapter(copied.get("valid_to"))
        if end is not None and end > chapter:
            copied["valid_to"] = None
        result.append(copied)
    return result


def _safe_name(
    entity: dict[str, Any],
    chapter: int,
    meta: dict[str, Any],
    gaps: list[str],
    strict: bool,
    terminal_chapter: int | None,
) -> str:
    entity_id = str(entity.get("id") or "")
    value = _history_value(entity.get("name_history"), chapter, ("name", "value"))
    if isinstance(value, str) and value.strip():
        return value.strip()
    name_first = _chapter(entity.get("name_first_chapter"))
    if name_first is None:
        name_first = _meta_lookup(meta.get("name_first_chapter"), entity_id)
    if name_first is not None:
        if name_first > chapter:
            return f"[{entity.get('type') or 'entity'}:{entity_id}]"
        return str(entity.get("name") or entity_id)
    if strict and terminal_chapter is not None and chapter < terminal_chapter:
        gaps.append(f"entity:{entity_id}:canonical_name:untimed")
        return f"[{entity.get('type') or 'entity'}:{entity_id}]"
    return str(entity.get("name") or entity_id)


def _filter_aliases(entity: dict[str, Any], chapter: int, meta: dict[str, Any], gaps: list[str], strict: bool) -> None:
    entity_id = str(entity.get("id") or "")
    alias_meta = meta.get("alias_first_chapter")
    for field in ("aliases", "historical_names", "titles"):
        values = entity.get(field)
        if not isinstance(values, list):
            continue
        kept: list[Any] = []
        unknown_count = 0
        for value in values:
            if isinstance(value, dict):
                start = first_visible_chapter(value)
                if start is None:
                    start = _chapter(value.get("first_chapter"))
                if start is None and strict:
                    unknown_count += 1
                    continue
                if start is not None and start > chapter:
                    continue
                copied = deepcopy(value)
                end = _chapter(copied.get("valid_to"))
                if end is not None and end > chapter:
                    copied["valid_to"] = None
                kept.append(copied)
                continue
            if not isinstance(value, str):
                continue
            start = None
            if isinstance(alias_meta, dict):
                nested = alias_meta.get(entity_id)
                if isinstance(nested, dict):
                    start = _chapter(nested.get(value))
            if start is None and strict:
                unknown_count += 1
                continue
            if start is None or start <= chapter:
                kept.append(value)
        if unknown_count:
            gaps.append(f"entity:{entity_id}:{field}:untimed:{unknown_count}")
        entity[field] = kept


def _project_entity_prose(entity: dict[str, Any], chapter: int, meta: dict[str, Any], gaps: list[str], strict: bool) -> None:
    entity_id = str(entity.get("id") or "")
    for field in PROSE_TEMPORAL_FIELDS:
        history = entity.get(f"{field}_history")
        history_value = _history_value(history, chapter, (field, "value", "text"))
        if history_value is not None:
            entity[field] = history_value
            entity[f"{field}_history"] = _filter_history(history, chapter)
        else:
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
        for timing_key in (f"{field}_chapter", f"{field}_first_chapter"):
            value = _chapter(entity.get(timing_key))
            if value is not None and value > chapter:
                entity.pop(timing_key, None)


def _project_attributes(entity: dict[str, Any], chapter: int, meta: dict[str, Any], gaps: list[str], strict: bool) -> None:
    entity_id = str(entity.get("id") or "")
    history = recs(entity.get("attribute_history")) + recs(entity.get("attributes_history"))
    reconstructed: dict[str, Any] = {}
    for row in sorted(history, key=lambda item: (_chapter(item.get("chapter")) or _chapter(item.get("valid_from")) or 0, str(item.get("id") or ""))):
        start = _chapter(row.get("chapter"))
        if start is None:
            start = _chapter(row.get("valid_from"))
        if start is None or start > chapter:
            continue
        key = row.get("key") or row.get("attribute")
        if isinstance(key, str):
            reconstructed[key] = deepcopy(row.get("value"))
    raw = entity.get("attributes")
    unknown = 0
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
            elif first is None:
                unknown += 1
    if unknown:
        gaps.append(f"entity:{entity_id}:attributes:untimed:{unknown}")
    entity["attributes"] = reconstructed
    if history:
        entity["attribute_history"] = _filter_history(history, chapter)
    entity.pop("attributes_history", None)
    entity.pop("current_state", None)


def _scrub_evidence_refs(value: Any, allowed: set[str]) -> Any:
    """Recursively remove evidence references that are outside the snapshot."""
    if isinstance(value, dict):
        for key, item in list(value.items()):
            if key.endswith("evidence_ids") and isinstance(item, list):
                value[key] = [ref for ref in item if ref in allowed]
            else:
                _scrub_evidence_refs(item, allowed)
    elif isinstance(value, list):
        for item in value:
            _scrub_evidence_refs(item, allowed)
    return value


def _commitment_asof(row: dict[str, Any], chapter: int) -> None:
    observations = [deepcopy(obs) for obs in recs(row.get("observations")) if _chapter(obs.get("chapter")) is None or obs["chapter"] <= chapter]
    observations.sort(key=lambda obs: (_chapter(obs.get("chapter")) or 0, str(obs.get("id") or "")))
    row["observations"] = observations
    resolved = _chapter(row.get("resolved_chapter"))
    if resolved is not None and resolved > chapter:
        row["resolved_chapter"] = None
        row["resolution"] = None
    visible_status = next((obs.get("status") for obs in reversed(observations) if isinstance(obs.get("status"), str)), None)
    if visible_status:
        row["status"] = visible_status
    elif resolved is None or resolved > chapter:
        row["status"] = "active"


def _relation_asof(row: dict[str, Any], chapter: int) -> None:
    observations: list[dict[str, Any]] = []
    for obs in recs(row.get("observations")):
        at = _chapter(obs.get("chapter"))
        if at is not None and at > chapter:
            continue
        copied = deepcopy(obs)
        obs_end = _chapter(copied.get("valid_to"))
        if obs_end is not None and obs_end > chapter:
            copied["valid_to"] = None
        observations.append(copied)
    observations.sort(key=lambda obs: (_chapter(obs.get("chapter")) or 0, str(obs.get("id") or "")))
    row["observations"] = observations
    end = _chapter(row.get("valid_to"))
    if end is not None and end > chapter:
        row.pop("valid_to", None)
    visible_status = next((obs.get("status") for obs in reversed(observations) if isinstance(obs.get("status"), str)), None)
    if visible_status:
        row["status"] = visible_status
    elif end is not None and end > chapter and row.get("status") not in {None, "active", "uncertain"}:
        row["status"] = "active"


def _scrub_temporal_metadata(meta: dict[str, Any], chapter: int) -> None:
    for field in ("name_first_chapter", "summary_first_chapter", "description_first_chapter"):
        mapping = meta.get(field)
        if isinstance(mapping, dict):
            meta[field] = {key: value for key, value in mapping.items() if _chapter(value) is not None and value <= chapter}
    for field in ("alias_first_chapter", "attribute_first_chapter"):
        mapping = meta.get(field)
        if not isinstance(mapping, dict):
            continue
        cleaned: dict[str, dict[str, int]] = {}
        for entity_id, nested in mapping.items():
            if not isinstance(nested, dict):
                continue
            kept = {key: value for key, value in nested.items() if _chapter(value) is not None and value <= chapter}
            if kept:
                cleaned[entity_id] = kept
        meta[field] = cleaned


def filter_graph(graph: dict[str, Any], chapter: int, *, strict: bool = True) -> dict[str, Any]:
    if not isinstance(chapter, int) or isinstance(chapter, bool) or chapter < 0:
        raise ValueError("chapter must be a non-negative integer")
    out = deepcopy(graph)
    meta = out.get("metadata") if isinstance(out.get("metadata"), dict) else {}
    original_end = _chapter(meta.get("chapter_end"))
    gaps: list[str] = []

    entities: list[dict[str, Any]] = []
    for entity in recs(out.get("entities")):
        first = _chapter(entity.get("first_chapter"))
        if first is not None and first > chapter:
            continue
        entity["name"] = _safe_name(entity, chapter, meta, gaps, strict, original_end)
        entity["name_history"] = _filter_history(entity.get("name_history"), chapter)
        name_first = _chapter(entity.get("name_first_chapter"))
        if name_first is not None and name_first > chapter:
            entity.pop("name_first_chapter", None)
        _filter_aliases(entity, chapter, meta, gaps, strict)
        _project_entity_prose(entity, chapter, meta, gaps, strict)
        _project_attributes(entity, chapter, meta, gaps, strict)
        entities.append(entity)
    out["entities"] = entities
    entity_ids = {entity.get("id") for entity in entities}

    evidence = [row for row in recs(out.get("evidence")) if _chapter(row.get("chapter")) is None or row["chapter"] <= chapter]
    out["evidence"] = evidence
    evidence_ids = {row.get("id") for row in evidence if isinstance(row.get("id"), str)}

    events: list[dict[str, Any]] = []
    for event in recs(out.get("events")):
        at = _chapter(event.get("chapter"))
        if at is not None and at > chapter:
            continue
        event["participant_ids"] = [ref for ref in event.get("participant_ids", []) if ref in entity_ids] if isinstance(event.get("participant_ids"), list) else []
        if event.get("location_id") not in entity_ids:
            event.pop("location_id", None)
        events.append(event)
    out["events"] = events
    event_ids = {event.get("id") for event in events}

    relations: list[dict[str, Any]] = []
    for relation in recs(out.get("relations")):
        if relation.get("source_id") not in entity_ids or relation.get("target_id") not in entity_ids:
            continue
        start = _chapter(relation.get("valid_from"))
        if start is not None and start > chapter:
            continue
        _relation_asof(relation, chapter)
        relations.append(relation)
    out["relations"] = relations

    state_changes: list[dict[str, Any]] = []
    for change in recs(out.get("state_changes")):
        if change.get("entity_id") not in entity_ids:
            continue
        at = _chapter(change.get("chapter"))
        if at is not None and at > chapter:
            continue
        if change.get("target_id") is not None and change.get("target_id") not in entity_ids:
            continue
        end = _chapter(change.get("end_chapter"))
        if end is not None and end > chapter:
            change.pop("end_chapter", None)
        state_changes.append(change)
    out["state_changes"] = state_changes

    for key in ("intimate_acts", "level_conversions", "character_traits", "chapter_summaries", "item_roles", "commitments", "review_issues"):
        rows: list[dict[str, Any]] = []
        for row in recs(out.get(key)):
            if not visible_record(row, chapter, strict_unknown=False):
                continue
            if key == "commitments":
                _commitment_asof(row, chapter)
            elif key == "item_roles":
                end = _chapter(row.get("valid_to"))
                if end is not None and end > chapter:
                    row.pop("valid_to", None)
            rows.append(row)
        out[key] = rows

    routes: list[dict[str, Any]] = []
    for route in recs(out.get("romance_routes")):
        first = _chapter(route.get("first_meeting_chapter"))
        if first is not None and first > chapter:
            continue
        for chapter_field, evidence_field in (
            ("confirmed_chapter", "confirmed_evidence_ids"),
            ("first_sex_chapter", "first_sex_evidence_ids"),
            ("ambiguity_started_chapter", "ambiguity_evidence_ids"),
        ):
            value = _chapter(route.get(chapter_field))
            if value is not None and value > chapter:
                route[chapter_field] = None
                route[evidence_field] = []
        confirmed = _chapter(route.get("confirmed_chapter"))
        intimacy = _chapter(route.get("first_sex_chapter"))
        ambiguity = _chapter(route.get("ambiguity_started_chapter"))
        if confirmed is not None and confirmed <= chapter:
            route["status"] = "confirmed_relationship"
        elif intimacy is not None and intimacy <= chapter:
            route["status"] = "provisional_intimate"
        elif ambiguity is not None and ambiguity <= chapter:
            route["status"] = "ambiguous"
        else:
            route["status"] = "uncertain"
        routes.append(route)
    out["romance_routes"] = routes

    arcs: list[dict[str, Any]] = []
    for arc in recs(out.get("story_arcs")):
        start = _chapter(arc.get("chapter_start"))
        if start is not None and start > chapter:
            continue
        end = _chapter(arc.get("chapter_end"))
        if end is not None and end > chapter:
            arc["chapter_end"] = None
            if arc.get("status") in {"closed", "complete", "completed", "resolved"}:
                arc["status"] = "active"
        if isinstance(arc.get("event_ids"), list):
            arc["event_ids"] = [ref for ref in arc["event_ids"] if ref in event_ids]
        arcs.append(arc)
    out["story_arcs"] = arcs

    foreshadowing: list[dict[str, Any]] = []
    for clue in recs(out.get("foreshadowing")):
        planted = _chapter(clue.get("planted_chapter"))
        if planted is not None and planted > chapter:
            continue
        progression = [row for row in recs(clue.get("progression")) if _chapter(row.get("chapter")) is None or row["chapter"] <= chapter]
        clue["progression"] = progression
        payoff = _chapter(clue.get("payoff_chapter"))
        if payoff is not None and payoff > chapter:
            clue["payoff_chapter"] = None
            clue.pop("payoff_event_id", None)
            visible_status = next((row.get("status") for row in reversed(progression) if isinstance(row.get("status"), str)), None)
            clue["status"] = visible_status or "open"
        foreshadowing.append(clue)
    out["foreshadowing"] = foreshadowing

    style_rows: list[dict[str, Any]] = []
    for observation in recs(out.get("style_observations")):
        start = first_visible_chapter(observation)
        if start is None:
            start = _chapter(observation.get("chapter_start"))
        if start is None and strict:
            gaps.append("style_observation:untimed")
            continue
        if start is not None and start > chapter:
            continue
        copied = deepcopy(observation)
        end = _chapter(copied.get("chapter_end"))
        if end is not None and end > chapter:
            copied["chapter_end"] = chapter
        style_rows.append(copied)
    if "style_observations" in out:
        out["style_observations"] = style_rows

    # A final recursive pass prevents nested observations/facets from retaining
    # evidence IDs whose evidence record is outside the reader-safe snapshot.
    _scrub_evidence_refs(out, evidence_ids)
    _scrub_temporal_metadata(meta, chapter)
    meta["spoiler_cutoff_chapter"] = chapter
    meta["spoiler_strict"] = strict
    meta["temporal_provenance_gaps"] = sorted(set(gaps))
    analyzed = [value for value in meta.get("analyzed_chapters", []) if isinstance(value, int) and value <= chapter]
    meta["analyzed_chapters"] = analyzed
    if analyzed:
        meta["chapter_start"], meta["chapter_end"] = min(analyzed), max(analyzed)
    else:
        meta["chapter_end"] = min(chapter, original_end) if isinstance(original_end, int) else chapter
    out["metadata"] = meta
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--graph", required=True, type=Path)
    parser.add_argument("--chapter", required=True, type=int)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--compat", action="store_true", help="Retain untimed legacy prose/aliases instead of strict spoiler closure")
    args = parser.parse_args()
    graph = json.loads(args.graph.read_text(encoding="utf-8"))
    filtered = filter_graph(graph, args.chapter, strict=not args.compat)
    atomic_write_json(args.output, filtered, trailing_newline=False)
    print(json.dumps({
        "output": str(args.output),
        "chapter": args.chapter,
        "entities": len(filtered.get("entities", [])),
        "events": len(filtered.get("events", [])),
        "temporal_provenance_gaps": len(filtered.get("metadata", {}).get("temporal_provenance_gaps", [])),
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
