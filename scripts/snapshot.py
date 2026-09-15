#!/usr/bin/env python3
"""Derive chapter-specific dynamic views from a temporal novel graph.

The source ``graph.json`` remains the only truth.  This module never mutates it
and deliberately does not implement spoiler filtering: entity summaries,
attributes, aliases, evidence, and complete foreshadowing records remain
available in snapshots regardless of the selected chapter.  Only the derived
dynamic view is replayed to the requested chapter.

All public functions return JSON-serializable values and use only the Python
standard library.  Relations and bounded state changes use inclusive end
chapters.  State changes are replayed in stable ``(chapter, id)`` order.
"""

from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path
from typing import Any, Iterable, Mapping


_REMOVAL_ACTIONS = {
    "forgotten",
    "left",
    "lost",
    "removed",
    "relinquished",
}
_POSSESSION_RELATIONS = {
    "owns": "owner",
    "uses": "user",
    "custodian_of": "custodian",
    "holds": "holder",
}
_ROLE_ALIASES = {
    "owns": "owner",
    "owner": "owner",
    "owned_by": "owner",
    "uses": "user",
    "user": "user",
    "used_by": "user",
    "custodian": "custodian",
    "custodian_of": "custodian",
    "holder": "holder",
    "holds": "holder",
}


def _as_chapter(value: Any, default: int | None = None) -> int | None:
    """Return an integer chapter while rejecting booleans and malformed values."""

    return value if isinstance(value, int) and not isinstance(value, bool) else default


def _require_chapter(chapter: Any) -> int:
    """Validate and return a non-negative snapshot chapter."""

    value = _as_chapter(chapter)
    if value is None or value < 0:
        raise ValueError("chapter must be a non-negative integer")
    return value


def _records(value: Any) -> list[dict[str, Any]]:
    """Return only mapping records from a legacy or current array field."""

    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _entity_id(entity: str | Mapping[str, Any]) -> str:
    """Resolve an entity ID from an ID string or entity mapping."""

    if isinstance(entity, str):
        return entity
    value = entity.get("id")
    if isinstance(value, str):
        return value
    raise ValueError("entity must be an entity ID or a mapping with a string id")


def _entity_record(graph: Mapping[str, Any], entity: str | Mapping[str, Any]) -> Mapping[str, Any]:
    """Find the canonical entity mapping, falling back to a supplied mapping."""

    entity_id = _entity_id(entity)
    for candidate in _records(graph.get("entities")):
        if candidate.get("id") == entity_id:
            return candidate
    return entity if isinstance(entity, Mapping) else {"id": entity_id}


def _change_key(change: Mapping[str, Any]) -> tuple[int, str]:
    """Return the deterministic replay key required by the graph contract."""

    return (_as_chapter(change.get("chapter"), 0) or 0, str(change.get("id") or ""))


def _active_change(change: Mapping[str, Any], chapter: int) -> bool:
    """Return whether a state-change effect is in force at ``chapter``."""

    start = _as_chapter(change.get("chapter"))
    if start is None or start > chapter:
        return False
    end = _as_chapter(change.get("end_chapter"))
    return end is None or chapter <= end


def state_changes_at(graph: Mapping[str, Any], chapter: int) -> list[dict[str, Any]]:
    """Return the state-change records that are active at ``chapter``.

    The returned records keep their original evidence and prose, but are copied
    so callers cannot mutate the graph while formatting a derived view.
    """

    snapshot_chapter = _require_chapter(chapter)
    return [
        copy.deepcopy(change)
        for change in sorted(_records(graph.get("state_changes")), key=_change_key)
        if _active_change(change, snapshot_chapter)
    ]


def story_arcs_intersecting(
    graph: Mapping[str, Any], chapter_start: int, chapter_end: int | None = None
) -> list[dict[str, Any]]:
    """Return every arc intersecting an inclusive chapter window.

    Overlap and nesting are preserved. An open-ended arc is bounded only for the
    intersection test and remains open-ended in the returned copied record.
    """

    start = _require_chapter(chapter_start)
    end = start if chapter_end is None else _require_chapter(chapter_end)
    if start > end:
        raise ValueError("chapter_start must not exceed chapter_end")
    matches: list[dict[str, Any]] = []
    for arc in _records(graph.get("story_arcs")):
        arc_start = _as_chapter(arc.get("chapter_start"))
        arc_end = _as_chapter(arc.get("chapter_end"), 2**31 - 1)
        if arc_start is not None and arc_end is not None and max(start, arc_start) <= min(end, arc_end):
            matches.append(copy.deepcopy(arc))
    return sorted(
        matches,
        key=lambda arc: (
            arc.get("parent_arc_id") is not None,
            _as_chapter(arc.get("chapter_start"), 0) or 0,
            _as_chapter(arc.get("chapter_end"), 2**31 - 1) or 2**31 - 1,
            str(arc.get("id") or ""),
        ),
    )


def _change_value(change: Mapping[str, Any]) -> Any:
    """Derive a change's resulting value, including sparse legacy records."""

    if "after" in change:
        return copy.deepcopy(change.get("after"))
    if str(change.get("action") or "").lower() in _REMOVAL_ACTIONS:
        return None
    if change.get("target_id") is not None:
        return copy.deepcopy(change.get("target_id"))
    return None


def _legacy_state(entity: Mapping[str, Any], facet: str) -> tuple[bool, Any]:
    """Read a legacy ``current_state`` facet only when no history exists."""

    current = entity.get("current_state")
    if isinstance(current, Mapping) and facet in current:
        return True, copy.deepcopy(current[facet])
    return False, None


def state_at(
    graph_or_entity: Mapping[str, Any],
    entity_or_facet: str | Mapping[str, Any],
    facet_or_chapter: str | int,
    chapter: int | None = None,
) -> Any:
    """Return one entity facet's value at a chapter.

    Two call forms are supported for convenience and legacy data::

        state_at(graph, entity_id_or_mapping, facet, chapter)
        state_at(entity_mapping, facet, chapter)

    The three-argument form reads optional entity-local ``state_changes``.
    For ordinary scalar facets the return value is the latest active ``after``
    value.  If changes on the facet have ``target_id`` values, the result is a
    mapping from target ID to value.  A rare mixture of targeted and untargeted
    changes returns ``{"value": ..., "targets": {...}}``.  ``current_state``
    is only a compatibility fallback when the facet has no temporal records at
    all, preventing a latest-state field from overriding replayable history.
    """

    if chapter is None:
        entity = graph_or_entity
        facet = str(entity_or_facet)
        snapshot_chapter = _require_chapter(facet_or_chapter)
        graph: Mapping[str, Any] = {
            "entities": [entity],
            "state_changes": entity.get("state_changes", []),
        }
    else:
        graph = graph_or_entity
        entity = entity_or_facet
        facet = str(facet_or_chapter)
        snapshot_chapter = _require_chapter(chapter)

    entity_id = _entity_id(entity)
    entity_record = _entity_record(graph, entity)
    matching = [
        change
        for change in _records(graph.get("state_changes"))
        if change.get("entity_id") == entity_id and str(change.get("facet")) == facet
    ]
    if not matching:
        found, value = _legacy_state(entity_record, facet)
        return value if found else None

    active = sorted(
        (change for change in matching if _active_change(change, snapshot_chapter)),
        key=_change_key,
    )
    if not active:
        return None

    untargeted = [change for change in active if not isinstance(change.get("target_id"), str)]
    targeted: dict[str, Any] = {}
    for change in active:
        target_id = change.get("target_id")
        if isinstance(target_id, str):
            targeted[target_id] = _change_value(change)

    scalar = _change_value(untargeted[-1]) if untargeted else None
    if targeted and untargeted:
        return {"value": scalar, "targets": targeted}
    if targeted:
        return targeted
    return scalar


def active_relations(
    graph: Mapping[str, Any], entity_id: str | Mapping[str, Any], chapter: int
) -> list[dict[str, Any]]:
    """Return relations involving an entity that are active at a chapter.

    ``valid_from`` defaults to chapter zero for legacy graphs and ``valid_to``
    is inclusive.  Status text is intentionally not used as a time source: the
    schema defines validity through the interval fields.  Returned records are
    deep copies sorted by ``(valid_from, id)``.
    """

    snapshot_chapter = _require_chapter(chapter)
    wanted = _entity_id(entity_id)
    result = []
    for relation in _records(graph.get("relations")):
        if wanted not in (relation.get("source_id"), relation.get("target_id")):
            continue
        start = _as_chapter(relation.get("valid_from"), 0) or 0
        end = _as_chapter(relation.get("valid_to"))
        if start <= snapshot_chapter and (end is None or snapshot_chapter <= end):
            result.append(copy.deepcopy(relation))
    result.sort(key=lambda item: (_as_chapter(item.get("valid_from"), 0) or 0, str(item.get("id") or "")))
    return result


def _normal_role(value: Any, default: str = "holder") -> str:
    """Normalize old relation and item-role vocabulary."""

    text = str(value or default).lower()
    return _ROLE_ALIASES.get(text, text)


def _role_refs(value: Any, default_entity: str | None = None) -> list[tuple[str, str]]:
    """Extract ``(entity_id, role)`` pairs from possession before/after values."""

    result: list[tuple[str, str]] = []
    if isinstance(value, str):
        return [(value, "holder")]
    if isinstance(value, list):
        for item in value:
            result.extend(_role_refs(item, default_entity))
        return result
    if isinstance(value, Mapping):
        named = {
            "owner_id": "owner",
            "user_id": "user",
            "custodian_id": "custodian",
            "holder_id": "holder",
        }
        for key, role in named.items():
            ref = value.get(key)
            if isinstance(ref, str):
                result.append((ref, role))
            elif isinstance(ref, list):
                result.extend((item, role) for item in ref if isinstance(item, str))
        generic = next(
            (value.get(key) for key in ("entity_id", "character_id", "possessor_id") if isinstance(value.get(key), str)),
            None,
        )
        if generic:
            result.append((generic, _normal_role(value.get("role"))))
        return result
    return [(default_entity, "holder")] if default_entity else []


def _iter_item_roles(graph: Mapping[str, Any]) -> Iterable[dict[str, Any]]:
    """Yield normalized records from supported top-level ``item_roles`` shapes."""

    raw = graph.get("item_roles")
    if isinstance(raw, list):
        yield from (copy.deepcopy(item) for item in raw if isinstance(item, dict))
        return
    if not isinstance(raw, Mapping):
        return
    for item_id, value in raw.items():
        if isinstance(value, list):
            for index, entry in enumerate(value):
                if isinstance(entry, str):
                    yield {"id": f"item_role:{item_id}:{index}", "item_id": item_id, "entity_id": entry, "role": "owner"}
                elif isinstance(entry, Mapping):
                    yield {"item_id": item_id, **copy.deepcopy(dict(entry))}
        elif isinstance(value, Mapping):
            record_keys = {"entity_id", "character_id", "owner_id", "holder_id", "user_id", "custodian_id"}
            if record_keys.intersection(value):
                yield {"item_id": item_id, **copy.deepcopy(dict(value))}
            else:
                for role, holders in value.items():
                    refs = holders if isinstance(holders, list) else [holders]
                    for index, holder in enumerate(refs):
                        if isinstance(holder, str):
                            yield {
                                "id": f"item_role:{item_id}:{role}:{index}",
                                "item_id": item_id,
                                "entity_id": holder,
                                "role": role,
                            }


def ownership_at(graph: Mapping[str, Any], item_id: str | Mapping[str, Any], chapter: int) -> list[dict[str, Any]]:
    """Return current people/agents and their roles for an item.

    The result is a sorted list of ``entity_id``, normalized ``role``
    (``owner``, ``user``, ``custodian``, or ``holder``), ``since_chapter``,
    and provenance ``source``/``source_id``.  Legacy ``owns``, ``uses``,
    ``custodian_of``, and ``holds`` relations are replayed first, then
    ``possession`` state changes in stable chapter/ID order.  Optional
    top-level ``item_roles`` records are merged at higher same-chapter
    precedence.  Transfers remove the old role holder and add the new one.
    End chapters are inclusive, so expiry is applied in the following chapter.
    """

    snapshot_chapter = _require_chapter(chapter)
    wanted_item = _entity_id(item_id)
    events: list[tuple[int, int, str, str, str, str, str]] = []

    def add_event(at: int, priority: int, record_id: str, operation: str, entity: str, role: str, source: str) -> None:
        if at <= snapshot_chapter:
            events.append((at, priority, record_id, operation, entity, _normal_role(role), source))

    for relation in _records(graph.get("relations")):
        role = _POSSESSION_RELATIONS.get(str(relation.get("relation_type") or "").lower())
        if role is None or relation.get("target_id") != wanted_item:
            continue
        holder_id = relation.get("source_id")
        if not isinstance(holder_id, str):
            continue
        start = _as_chapter(relation.get("valid_from"), 0) or 0
        record_id = str(relation.get("id") or "")
        add_event(start, 0, record_id, "add", holder_id, role, "relation")
        end = _as_chapter(relation.get("valid_to"))
        if end is not None:
            add_event(end + 1, 0, record_id, "remove", holder_id, role, "relation")

    for change in sorted(_records(graph.get("state_changes")), key=_change_key):
        if change.get("facet") != "possession" or change.get("target_id") != wanted_item:
            continue
        start = _as_chapter(change.get("chapter"))
        entity = change.get("entity_id")
        if start is None or not isinstance(entity, str):
            continue
        record_id = str(change.get("id") or "")
        action = str(change.get("action") or "").lower()
        before_refs = _role_refs(change.get("before"), entity)
        after_refs = _role_refs(change.get("after"), entity)
        if action in _REMOVAL_ACTIONS or ("after" in change and change.get("after") is None):
            refs = before_refs or [(entity, "holder")]
            for holder, role in refs:
                add_event(start, 1, record_id, "remove_entity", holder, role, "state_change")
        elif action == "transferred":
            for holder, role in before_refs or [(entity, "holder")]:
                add_event(start, 1, record_id, "remove_entity", holder, role, "state_change")
            for holder, role in after_refs:
                add_event(start, 1, record_id, "add", holder, role, "state_change")
        else:
            for holder, role in after_refs or [(entity, "holder")]:
                add_event(start, 1, record_id, "add", holder, role, "state_change")

        end = _as_chapter(change.get("end_chapter"))
        if end is not None:
            for holder, role in after_refs or [(entity, "holder")]:
                add_event(end + 1, 1, record_id, "remove", holder, role, "state_change")
            for holder, role in before_refs:
                add_event(end + 1, 1, record_id, "add", holder, role, "state_change")

    for role_record in _iter_item_roles(graph):
        if role_record.get("item_id") != wanted_item:
            continue
        start = _as_chapter(role_record.get("valid_from"), _as_chapter(role_record.get("chapter"), 0)) or 0
        record_id = str(role_record.get("id") or "")
        refs = _role_refs(role_record, None)
        if not refs:
            continue
        status = str(role_record.get("status") or "active").lower()
        for holder, inferred_role in refs:
            role = _normal_role(role_record.get("role"), inferred_role)
            add_event(start, 2, record_id, "remove" if status in {"ended", "inactive", "lost"} else "add", holder, role, "item_role")
            end = _as_chapter(role_record.get("valid_to"), _as_chapter(role_record.get("end_chapter")))
            if end is not None:
                add_event(end + 1, 2, record_id, "remove", holder, role, "item_role")

    current: dict[tuple[str, str], dict[str, Any]] = {}
    for at, priority, record_id, operation, entity, role, source in sorted(
        events, key=lambda event: (event[0], event[1], event[2], 0 if event[3].startswith("remove") else 1)
    ):
        if operation == "remove_entity":
            for key in [key for key in current if key[0] == entity]:
                current.pop(key, None)
        elif operation == "remove":
            current.pop((entity, role), None)
        else:
            current[(entity, role)] = {
                "entity_id": entity,
                "role": role,
                "since_chapter": at,
                "source": source,
                "source_id": record_id or None,
            }
    return [current[key] for key in sorted(current)]


def levels_at(graph: Mapping[str, Any], entity_id: str | Mapping[str, Any], chapter: int) -> dict[str, Any]:
    """Return the entity's level value on each axis at a chapter.

    The mapping key is ``target_id`` (the level-axis entity ID), or ``level``
    for legacy un-targeted changes.  Each value is the latest active ``after``
    value on that axis.  Stable ``(chapter, id)`` ordering resolves same-chapter
    updates.  A legacy ``current_state.level`` is used only when no replayable
    level history exists.
    """

    snapshot_chapter = _require_chapter(chapter)
    wanted = _entity_id(entity_id)
    matching = [
        change
        for change in _records(graph.get("state_changes"))
        if change.get("entity_id") == wanted and change.get("facet") == "level"
    ]
    result: dict[str, Any] = {}
    for change in sorted((item for item in matching if _active_change(item, snapshot_chapter)), key=_change_key):
        axis = change.get("target_id") if isinstance(change.get("target_id"), str) else "level"
        result[axis] = _change_value(change)
    if not matching:
        found, value = _legacy_state(_entity_record(graph, entity_id), "level")
        if found:
            result["level"] = value
    return result


def dynamic_state_for_entity(
    graph: Mapping[str, Any], entity_id: str | Mapping[str, Any], chapter: int
) -> dict[str, Any]:
    """Build the complete chapter-derived dynamic view for one entity.

    The JSON-serializable result has ``entity_id``, ``chapter``, ``facets``,
    ``relations``, ``item_roles``, ``levels``, and every intersecting
    ``story_arcs`` membership. For an item, ``item_roles``
    describes its current holders/users.  For another entity it describes the
    current roles that entity has for all known item entities.
    """

    snapshot_chapter = _require_chapter(chapter)
    wanted = _entity_id(entity_id)
    entity = _entity_record(graph, entity_id)
    facet_names = {
        str(change.get("facet"))
        for change in _records(graph.get("state_changes"))
        if change.get("entity_id") == wanted and change.get("facet") is not None
    }
    current = entity.get("current_state")
    if isinstance(current, Mapping):
        facet_names.update(str(key) for key in current)
    facets = {
        facet: state_at(graph, wanted, facet, snapshot_chapter)
        for facet in sorted(facet_names)
        if facet != "level"
    }

    if entity.get("type") == "item":
        roles = ownership_at(graph, wanted, snapshot_chapter)
    else:
        roles = []
        item_ids = {
            item.get("id")
            for item in _records(graph.get("entities"))
            if item.get("type") == "item" and isinstance(item.get("id"), str)
        }
        item_ids.update(
            relation.get("target_id")
            for relation in _records(graph.get("relations"))
            if relation.get("relation_type") in _POSSESSION_RELATIONS
            and isinstance(relation.get("target_id"), str)
        )
        item_ids.update(
            change.get("target_id")
            for change in _records(graph.get("state_changes"))
            if change.get("facet") == "possession" and isinstance(change.get("target_id"), str)
        )
        item_ids.update(
            record.get("item_id") for record in _iter_item_roles(graph) if isinstance(record.get("item_id"), str)
        )
        for candidate_item in sorted(item_ids):
            for role in ownership_at(graph, candidate_item, snapshot_chapter):
                if role.get("entity_id") == wanted:
                    roles.append({"item_id": candidate_item, **role})

    arcs = [
        arc for arc in story_arcs_intersecting(graph, snapshot_chapter)
        if wanted in (arc.get("entity_ids") or [])
    ]
    return {
        "entity_id": wanted,
        "chapter": snapshot_chapter,
        "facets": facets,
        "relations": active_relations(graph, wanted, snapshot_chapter),
        "item_roles": roles,
        "levels": levels_at(graph, wanted, snapshot_chapter),
        "story_arcs": arcs,
    }


def build_snapshot(graph: Mapping[str, Any], chapter: int) -> dict[str, Any]:
    """Return a full graph copy plus chapter-derived state for every entity.

    The copy retains every original top-level record and every entity field,
    including future-facing summaries, attributes, aliases, evidence, and
    foreshadowing/payoff details.  It adds ``snapshot_chapter`` and a top-level
    ``dynamic_state`` mapping keyed by entity ID.  The input is never mutated;
    callers should treat the result as a disposable view, not persisted truth.
    """

    snapshot_chapter = _require_chapter(chapter)
    result = copy.deepcopy(dict(graph))
    result["snapshot_chapter"] = snapshot_chapter
    result["dynamic_state"] = {
        entity["id"]: dynamic_state_for_entity(graph, entity["id"], snapshot_chapter)
        for entity in _records(graph.get("entities"))
        if isinstance(entity.get("id"), str)
    }
    result["active_story_arcs"] = story_arcs_intersecting(graph, snapshot_chapter)
    return result


def _parse_args() -> argparse.Namespace:
    """Parse the small debugging command-line interface."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--graph", required=True, type=Path, help="UTF-8 graph.json input")
    parser.add_argument("--chapter", required=True, type=int, help="Inclusive snapshot chapter")
    parser.add_argument("--entity", help="Emit only this entity's dynamic state")
    parser.add_argument("--output", type=Path, help="Write JSON here instead of stdout")
    return parser.parse_args()


def main() -> int:
    """Run the optional JSON debugging CLI and return its process exit code."""

    args = _parse_args()
    graph = json.loads(args.graph.resolve().read_text(encoding="utf-8"))
    payload = (
        dynamic_state_for_entity(graph, args.entity, args.chapter)
        if args.entity
        else build_snapshot(graph, args.chapter)
    )
    rendered = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    else:
        print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
