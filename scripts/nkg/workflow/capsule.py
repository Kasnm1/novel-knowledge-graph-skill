"""The state capsule handed to the worker auditing one chapter.

A worker cannot confirm or update a character's state without being told what
that state was. The capsule is the state *before* the chapter — the graph closed
at chapter N-1 — for the entities likely to appear in chapter N, plus the open
threads they are part of. The audit card's `state_check` must answer every
obligation listed here: update the facet, confirm it unchanged, or mark the
character not present.

The capsule is derived and disposable; it never writes facts back.
"""

from __future__ import annotations

from typing import Any, Iterable, Mapping

import snapshot
from nkg.core.records import chapter_value, records
from nkg.temporal.asof import filter_graph, relation_active

CHECKED_FACETS = ("identity", "location", "health", "emotion", "goal", "affiliation")


def mentioned_entities(graph: Mapping[str, Any], text: str, *, min_hits: int = 1) -> list[tuple[str, int]]:
    """Entities whose name or alias occurs in `text`, most-mentioned first."""
    counts = []
    for entity in records(graph.get("entities")):
        forms = [f for f in [entity.get("name"), *(entity.get("aliases") or [])] if isinstance(f, str) and len(f) >= 2]
        hits = sum(text.count(f) for f in forms)
        if hits >= min_hits:
            counts.append((entity["id"], hits))
    return sorted(counts, key=lambda item: (-item[1], item[0]))


def _value(value: Any) -> Any:
    if isinstance(value, dict) and ("label" in value or "value" in value):
        return value.get("label") if value.get("label") is not None else value.get("value")
    return value


def _recent(rows: list[dict[str, Any]], key: str, limit: int) -> list[dict[str, Any]]:
    return sorted(rows, key=lambda r: r.get(key) or 0, reverse=True)[:limit]


def build_chapter_capsule(graph: Mapping[str, Any], chapter: int, *, text: str | None = None,
                          candidate_ids: Iterable[str] = (), max_entities: int = 40,
                          max_threads: int = 15) -> dict[str, Any]:
    """State as of chapter-1 for the entities chapter `chapter` is likely to involve."""
    as_of = max(chapter - 1, 0)
    closed = filter_graph(dict(graph), as_of, strict=False)
    entities = {e["id"]: e for e in records(closed.get("entities")) if isinstance(e.get("id"), str)}
    protagonists = [e["id"] for e in entities.values() if "protagonist" in (e.get("tags") or [])]

    ranked: list[str] = [i for i in candidate_ids if i in entities]
    if text:
        ranked += [i for i, _ in mentioned_entities(closed, text) if i not in ranked]
    ranked += [i for i in protagonists if i not in ranked]
    chosen = ranked[:max_entities]

    events = sorted(records(closed.get("events")), key=lambda e: (e.get("chapter") or 0, str(e.get("id"))))
    last_seen: dict[str, tuple[int, str]] = {}
    for event in events:
        for pid in event.get("participant_ids") or []:
            last_seen[pid] = (event.get("chapter"), str(event.get("title") or ""))

    rows = []
    for entity_id in chosen:
        entity = entities[entity_id]
        state = snapshot.dynamic_state_for_entity(closed, entity_id, as_of)
        facets = {}
        changes = sorted((c for c in records(closed.get("state_changes")) if c.get("entity_id") == entity_id),
                         key=lambda c: (c.get("chapter") or 0, str(c.get("id") or "")))
        for change in changes:
            end = chapter_value(change.get("end_chapter"))
            if change.get("facet") != "level" and (end is None or end >= as_of):
                facets[change["facet"]] = {"value": _value(change.get("after")), "since": change.get("chapter")}
        relations = [
            {"other": r["target_id"] if r["source_id"] == entity_id else r["source_id"],
             "type": r.get("relation_type"), "since": r.get("valid_from")}
            for r in state["relations"] if relation_active(r, as_of)
        ]
        rows.append({
            "id": entity_id, "type": entity.get("type"), "name": entity.get("name"),
            "aliases": entity.get("aliases") or [],
            "names_in_chapter": [n for n in [entity.get("name"), *(entity.get("aliases") or [])]
                                 if text and isinstance(n, str) and n in text] if text else None,
            "last_seen": {"chapter": last_seen[entity_id][0], "event": last_seen[entity_id][1]} if entity_id in last_seen else None,
            "levels": {axis: _value(v) for axis, v in state["levels"].items()},
            "facets": facets,
            "relations": relations[:20],
            "holdings": [{"item": r.get("item_id"), "role": r.get("role")} for r in state["item_roles"]],
            "state_check": list(CHECKED_FACETS) if entity.get("type") == "character" else [],
        })

    chosen_set = set(chosen)
    open_threads = {
        "foreshadowing": _recent([
            {"id": f.get("id"), "label": f.get("label"), "planted": f.get("planted_chapter"),
             "entities": [e for e in f.get("related_entity_ids") or [] if e in chosen_set]}
            for f in records(closed.get("foreshadowing"))
            if not chapter_value(f.get("payoff_chapter")) and chosen_set & set(f.get("related_entity_ids") or [])
        ], "planted", max_threads),
        "commitments": _recent([
            {"id": c.get("id"), "kind": c.get("kind"), "terms": c.get("terms"), "created": c.get("created_chapter")}
            for c in records(closed.get("commitments"))
            if not chapter_value(c.get("resolved_chapter"))
            and chosen_set & set((c.get("promisor_ids") or []) + (c.get("counterparty_ids") or []))
        ], "created", max_threads),
        "romance_routes": [
            {"id": r.get("id"), "character": r.get("character_id"), "status": r.get("status")}
            for r in records(closed.get("romance_routes")) if r.get("character_id") in chosen_set
        ],
    }
    previous = next((s for s in records(closed.get("chapter_summaries")) if s.get("chapter") == as_of), None)
    return {
        "schema": "chapter-capsule/v1",
        "chapter": chapter,
        "state_as_of": as_of,
        "previous_chapter_summary": previous.get("summary") if previous else None,
        "entities": rows,
        "open_threads": open_threads,
        "obligations": "For every present character, answer each state_check facet in the audit card: "
                       "record a change, or mark confirmed_unchanged. Close any relation, route or thread this chapter ends.",
    }
