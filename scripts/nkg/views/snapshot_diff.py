from __future__ import annotations

from typing import Any, Mapping

from nkg.core.runtime import GraphRuntime, records

TRACKED_ARRAYS = ("entities", "events", "relations", "commitments", "foreshadowing", "item_roles")


def _ids(graph: Mapping[str, Any], array: str) -> set[str]:
    return {str(row["id"]) for row in records(graph.get(array)) if isinstance(row.get("id"), str)}


def diff_snapshots(before: Mapping[str, Any], after: Mapping[str, Any]) -> dict[str, Any]:
    """Compare two already-scoped canonical snapshots without inventing facts."""
    changes: dict[str, Any] = {}
    for array in TRACKED_ARRAYS:
        left, right = _ids(before, array), _ids(after, array)
        changes[array] = {
            "added_ids": sorted(right - left),
            "removed_ids": sorted(left - right),
            "added_count": len(right - left),
            "removed_count": len(left - right),
        }

    left_runtime, right_runtime = GraphRuntime(before), GraphRuntime(after)
    common_entities = set(left_runtime.entity_by_id) & set(right_runtime.entity_by_id)
    state_changes: list[dict[str, Any]] = []
    before_chapter = int(before.get("metadata", {}).get("chapter_end") or 0) if isinstance(before.get("metadata"), dict) else 0
    after_chapter = int(after.get("metadata", {}).get("chapter_end") or 0) if isinstance(after.get("metadata"), dict) else 0
    for entity_id in sorted(common_entities):
        left_state = left_runtime.state_at(entity_id, before_chapter)
        right_state = right_runtime.state_at(entity_id, after_chapter)
        facets = set(left_state) | set(right_state)
        for facet in sorted(facets):
            left_value = left_state.get(facet, {}).get("value")
            right_value = right_state.get(facet, {}).get("value")
            if left_value != right_value:
                state_changes.append({
                    "entity_id": entity_id,
                    "entity": right_runtime.name(entity_id),
                    "facet": facet,
                    "before": left_value,
                    "after": right_value,
                    "after_record_id": right_state.get(facet, {}).get("record_id"),
                })

    return {
        "from_chapter": before_chapter,
        "to_chapter": after_chapter,
        "arrays": changes,
        "state_changes": state_changes,
        "summary": {
            "new_entities": changes["entities"]["added_count"],
            "new_events": changes["events"]["added_count"],
            "new_relations": changes["relations"]["added_count"],
            "new_commitments": changes["commitments"]["added_count"],
            "new_foreshadowing": changes["foreshadowing"]["added_count"],
            "changed_state_facets": len(state_changes),
        },
    }
