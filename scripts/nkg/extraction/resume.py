from __future__ import annotations

from typing import Any, Iterable, Mapping

from nkg.core.runtime import GraphRuntime, chapter_value
from nkg.temporal.checkpoints import graph_fingerprint


def build_resume_capsule(
    graph: Mapping[str, Any],
    *,
    chapter: int,
    previous_chapter: int | None = None,
    candidates: Iterable[Mapping[str, Any]] = (),
    recent_window: int = 25,
) -> dict[str, Any]:
    """Compact deterministic continuation index, never an independent fact store."""
    runtime = GraphRuntime(graph)
    start = max(0, (previous_chapter + 1) if previous_chapter is not None else chapter - max(1, recent_window) + 1)
    changed_entities: set[str] = set()
    changed_record_ids: list[str] = []
    for change in runtime.state_changes:
        at = chapter_value(change.get("chapter"))
        if at is None or at < start or at > chapter:
            continue
        if isinstance(change.get("entity_id"), str):
            changed_entities.add(change["entity_id"])
        if isinstance(change.get("id"), str):
            changed_record_ids.append(change["id"])
    for event in runtime.events_between(start, chapter):
        for entity_id in event.get("participant_ids", []) if isinstance(event.get("participant_ids"), list) else []:
            if isinstance(entity_id, str):
                changed_entities.add(entity_id)

    open_commitments = []
    for row in runtime.commitments:
        created = chapter_value(row.get("created_chapter"))
        if created is not None and created > chapter:
            continue
        resolved = chapter_value(row.get("resolved_chapter"))
        if resolved is None or resolved > chapter:
            if isinstance(row.get("id"), str):
                open_commitments.append(row["id"])

    open_foreshadowing = []
    for row in runtime.foreshadowing:
        planted = chapter_value(row.get("planted_chapter"))
        payoff = chapter_value(row.get("payoff_chapter"))
        if planted is not None and planted <= chapter and (payoff is None or payoff > chapter):
            if isinstance(row.get("id"), str):
                open_foreshadowing.append(row["id"])

    unresolved_candidates = []
    for row in candidates:
        if not isinstance(row, Mapping):
            continue
        status = str(row.get("status") or "unresolved").lower()
        cid = row.get("id") or row.get("candidate_id")
        if status == "unresolved" and isinstance(cid, str):
            unresolved_candidates.append(cid)

    active_relations = []
    for row in runtime.relations:
        start_ch = chapter_value(row.get("valid_from"))
        end_ch = chapter_value(row.get("valid_to"))
        if (start_ch is None or start_ch <= chapter) and (end_ch is None or chapter <= end_ch):
            if isinstance(row.get("id"), str):
                active_relations.append(row["id"])

    return {
        "schema_version": 2,
        "snapshot_chapter": chapter,
        "previous_chapter": previous_chapter,
        "graph_fingerprint": graph_fingerprint(graph),
        "active_entity_ids": sorted(changed_entities),
        "active_relation_ids": sorted(active_relations),
        "open_commitment_ids": sorted(open_commitments),
        "open_foreshadowing_ids": sorted(open_foreshadowing),
        "unresolved_candidate_ids": sorted(set(unresolved_candidates)),
        "changed_since_previous": sorted(set(changed_record_ids)),
        "contract": {
            "derived_only": True,
            "use_as_index_not_fact_source": True,
            "expand_on_conflict": "canonical_graph_and_evidence",
        },
    }
