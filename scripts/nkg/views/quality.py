from __future__ import annotations

from typing import Any, Mapping

from nkg.core.runtime import GraphRuntime, records
from nkg.validation.invariants import validate_invariants

EVIDENCE_BEARING = (
    "entities", "events", "relations", "state_changes", "romance_routes", "intimate_acts",
    "character_traits", "story_arcs", "item_roles", "commitments", "foreshadowing",
)


def _has_evidence(value: Any) -> bool:
    if isinstance(value, Mapping):
        for key, item in value.items():
            if key.endswith("evidence_ids") and isinstance(item, list) and any(isinstance(ref, str) and ref for ref in item):
                return True
            if _has_evidence(item):
                return True
    elif isinstance(value, list):
        return any(_has_evidence(item) for item in value)
    return False


def build_quality_summary(graph: Mapping[str, Any]) -> dict[str, Any]:
    """Deterministic audit metrics; quality indicators are views, never story facts."""
    runtime = GraphRuntime(graph)
    evidence_rows = total_rows = 0
    by_array: dict[str, Any] = {}
    for array in EVIDENCE_BEARING:
        rows = records(graph.get(array))
        with_evidence = sum(1 for row in rows if _has_evidence(row))
        total_rows += len(rows)
        evidence_rows += with_evidence
        by_array[array] = {
            "records": len(rows),
            "with_evidence_refs": with_evidence,
            "evidence_reference_ratio": None if not rows else with_evidence / len(rows),
        }

    review_issues = records(graph.get("review_issues"))
    unresolved = [row for row in review_issues if str(row.get("status") or "unresolved").lower() not in {"resolved", "excluded", "closed", "confirmed"}]
    metadata = graph.get("metadata") if isinstance(graph.get("metadata"), dict) else {}
    provenance_gaps = list(metadata.get("temporal_provenance_gaps") or []) if isinstance(metadata.get("temporal_provenance_gaps"), list) else []
    invariants = validate_invariants(graph)
    return {
        "derived_only": True,
        "runtime_stats": runtime.stats.__dict__,
        "evidence": {
            "records_evaluated": total_rows,
            "records_with_evidence_refs": evidence_rows,
            "ratio": None if total_rows == 0 else evidence_rows / total_rows,
            "by_array": by_array,
        },
        "temporal_provenance": {"gap_count": len(provenance_gaps), "gaps": provenance_gaps},
        "review": {"issue_count": len(review_issues), "unresolved_count": len(unresolved), "unresolved_ids": [row.get("id") for row in unresolved if isinstance(row.get("id"), str)]},
        "invariants": invariants,
        "attention_required": bool(invariants["error_count"] or invariants["warning_count"] or provenance_gaps or unresolved),
        "interpretation": "Audit indicators describe provenance/completeness risk; they are not probabilities that story facts are true.",
    }
