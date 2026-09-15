from __future__ import annotations

from typing import Any, Mapping

from nkg.core.runtime import chapter_value, records


def _chapter_end(graph: Mapping[str, Any]) -> int:
    metadata = graph.get("metadata") if isinstance(graph.get("metadata"), Mapping) else {}
    value = chapter_value(metadata.get("chapter_end"))
    return value if value is not None else 0


def _entity_map(graph: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        str(row["id"]): dict(row)
        for row in records(graph.get("entities"))
        if isinstance(row.get("id"), str)
    }


def _evidence_chapters(graph: Mapping[str, Any]) -> dict[str, int]:
    out: dict[str, int] = {}
    for row in records(graph.get("evidence")):
        evid = row.get("id")
        chapter = chapter_value(row.get("chapter"))
        if isinstance(evid, str) and chapter is not None:
            out[evid] = chapter
    return out


def _attribute_first_chapter(graph: Mapping[str, Any], entity: Mapping[str, Any], key: str) -> int | None:
    metadata = graph.get("metadata") if isinstance(graph.get("metadata"), Mapping) else {}
    by_entity = metadata.get("attribute_first_chapter") if isinstance(metadata.get("attribute_first_chapter"), Mapping) else {}
    entity_map = by_entity.get(entity.get("id")) if isinstance(by_entity, Mapping) else None
    if isinstance(entity_map, Mapping):
        value = chapter_value(entity_map.get(key))
        if value is not None:
            return value
    found: list[int] = []
    for field in ("attribute_history", "attributes_history"):
        for row in records(entity.get(field)):
            row_key = row.get("key") if isinstance(row.get("key"), str) else row.get("attribute")
            if row_key != key:
                continue
            chapter = chapter_value(row.get("chapter"))
            if chapter is None:
                chapter = chapter_value(row.get("valid_from"))
            if chapter is not None:
                found.append(chapter)
    return min(found) if found else None


def _interval(row: Mapping[str, Any], *, default_from: int) -> tuple[int, int | None]:
    start = chapter_value(row.get("valid_from"))
    if start is None:
        start = default_from
    end = chapter_value(row.get("valid_to"))
    return start, end


def build_entity_profiles(graph: Mapping[str, Any], hints: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Normalize AI-authored display hints without turning them into story facts.

    The function deliberately does not contain entity-type -> important-field maps.
    It validates identity/time/evidence boundaries and leaves semantic importance to
    the hint author. Consumers may fall back to the entity's currently visible
    attributes when no AI hint exists.
    """
    entities = _entity_map(graph)
    evidence_chapters = _evidence_chapters(graph)
    graph_end = _chapter_end(graph)
    raw_profiles = hints.get("profiles") if isinstance(hints, Mapping) and isinstance(hints.get("profiles"), Mapping) else {}
    issues: list[dict[str, Any]] = []
    profiles: dict[str, Any] = {}

    for entity_id, entity in entities.items():
        first = chapter_value(entity.get("first_chapter"))
        if first is None:
            first = 0
        raw = raw_profiles.get(entity_id) if isinstance(raw_profiles, Mapping) else None
        raw = raw if isinstance(raw, Mapping) else {}

        important: list[dict[str, Any]] = []
        for index, item in enumerate(raw.get("important_attributes", []) if isinstance(raw.get("important_attributes"), list) else []):
            if not isinstance(item, Mapping):
                issues.append({"code": "bad_display_attribute", "entity_id": entity_id, "index": index})
                continue
            source_key = item.get("source_key")
            if not isinstance(source_key, str) or not source_key:
                issues.append({"code": "missing_display_source_key", "entity_id": entity_id, "index": index})
                continue
            attrs = entity.get("attributes") if isinstance(entity.get("attributes"), Mapping) else {}
            history_keys = {
                row.get("key") if isinstance(row.get("key"), str) else row.get("attribute")
                for field in ("attribute_history", "attributes_history")
                for row in records(entity.get(field))
            }
            if source_key not in attrs and source_key not in history_keys:
                issues.append({"code": "unknown_display_source_key", "entity_id": entity_id, "source_key": source_key})
                continue
            inferred_first = _attribute_first_chapter(graph, entity, source_key)
            # Unknown legacy timing is deliberately conservative: the hint appears
            # only at the graph end instead of leaking a future attribute label.
            default_from = inferred_first if inferred_first is not None else graph_end
            valid_from, valid_to = _interval(item, default_from=default_from)
            important.append({
                "source_key": source_key,
                "label": str(item.get("label") or source_key),
                "valid_from": valid_from,
                "valid_to": valid_to,
                "reason": str(item.get("reason") or ""),
            })

        headlines: list[dict[str, Any]] = []
        raw_headlines = raw.get("headlines", []) if isinstance(raw.get("headlines"), list) else []
        for index, item in enumerate(raw_headlines):
            if not isinstance(item, Mapping) or not isinstance(item.get("text"), str) or not item.get("text"):
                issues.append({"code": "bad_display_headline", "entity_id": entity_id, "index": index})
                continue
            refs = [ref for ref in item.get("evidence_ids", []) if isinstance(ref, str)] if isinstance(item.get("evidence_ids"), list) else []
            missing = [ref for ref in refs if ref not in evidence_chapters]
            if missing:
                issues.append({"code": "unknown_display_evidence", "entity_id": entity_id, "evidence_ids": missing})
            evidence_start = min((evidence_chapters[ref] for ref in refs if ref in evidence_chapters), default=None)
            default_from = evidence_start if evidence_start is not None else graph_end
            valid_from, valid_to = _interval(item, default_from=default_from)
            headlines.append({
                "text": item["text"],
                "valid_from": valid_from,
                "valid_to": valid_to,
                "evidence_ids": refs,
            })

        badges: list[dict[str, Any]] = []
        for index, item in enumerate(raw.get("badges", []) if isinstance(raw.get("badges"), list) else []):
            if not isinstance(item, Mapping) or not isinstance(item.get("label"), str) or not item.get("label"):
                issues.append({"code": "bad_display_badge", "entity_id": entity_id, "index": index})
                continue
            valid_from, valid_to = _interval(item, default_from=first)
            badges.append({"label": item["label"], "valid_from": valid_from, "valid_to": valid_to})

        profiles[entity_id] = {
            "entity_id": entity_id,
            "first_chapter": first,
            "headlines": sorted(headlines, key=lambda row: row["valid_from"]),
            "important_attributes": sorted(important, key=lambda row: row["valid_from"]),
            "badges": sorted(badges, key=lambda row: row["valid_from"]),
            "ai_authored": bool(raw),
        }

    for entity_id in raw_profiles if isinstance(raw_profiles, Mapping) else ():
        if entity_id not in entities:
            issues.append({"code": "unknown_display_entity", "entity_id": entity_id})

    return {
        "schema_version": 1,
        "derived_only": True,
        "profiles": profiles,
        "issues": issues,
        "ai_profile_count": sum(1 for profile in profiles.values() if profile["ai_authored"]),
        "contract": "AI chooses semantic importance; code enforces identity, timing and evidence boundaries only.",
    }
