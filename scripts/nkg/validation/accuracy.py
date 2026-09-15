from __future__ import annotations

from collections import defaultdict
from typing import Any, Mapping

DEFAULT_ARRAYS = (
    "entities", "events", "relations", "state_changes", "romance_routes", "intimate_acts",
    "level_conversions", "character_traits", "chapter_summaries", "story_arcs", "item_roles",
    "commitments", "foreshadowing", "evidence", "review_issues",
)


def _records(value: object) -> list[dict[str, Any]]:
    return [row for row in value if isinstance(row, dict)] if isinstance(value, list) else []


def _ids(graph: Mapping[str, Any], array: str) -> set[str]:
    return {str(row["id"]) for row in _records(graph.get(array)) if isinstance(row.get("id"), str)}


def _evidence_links(graph: Mapping[str, Any]) -> dict[tuple[str, str], set[str]]:
    result: dict[tuple[str, str], set[str]] = {}
    for array in DEFAULT_ARRAYS:
        for row in _records(graph.get(array)):
            record_id = row.get("id")
            if not isinstance(record_id, str):
                continue
            refs: set[str] = set()
            for key, value in row.items():
                if key.endswith("evidence_ids") and isinstance(value, list):
                    refs.update(ref for ref in value if isinstance(ref, str))
            result[(array, record_id)] = refs
    return result


def _candidate_ids(value: Mapping[str, Any]) -> tuple[set[str], set[str]]:
    rows = _records(value.get("candidates")) or _records(value.get("candidate_records"))
    all_ids: set[str] = set()
    high_risk: set[str] = set()
    for row in rows:
        cid = row.get("id") or row.get("candidate_id")
        if not isinstance(cid, str):
            continue
        all_ids.add(cid)
        if row.get("mandatory") is True or row.get("high_risk") is True or str(row.get("risk") or "").lower() in {"high", "critical"}:
            high_risk.add(cid)
    return all_ids, high_risk


def compare_outputs(baseline: Mapping[str, Any], optimized: Mapping[str, Any]) -> dict[str, Any]:
    """Fail-closed accuracy regression comparison for token/retrieval optimizations.

    The optimized run may add facts, but it may not silently lose baseline IDs,
    high-risk candidates, or evidence links. This intentionally favors recall;
    semantic gold fixtures can layer stricter field-by-field checks on top.
    """
    arrays: dict[str, Any] = {}
    missing_records: list[dict[str, str]] = []
    extra_records: list[dict[str, str]] = []
    total_base = total_opt = intersection = 0
    for array in DEFAULT_ARRAYS:
        base_ids, opt_ids = _ids(baseline, array), _ids(optimized, array)
        missing, extra = sorted(base_ids - opt_ids), sorted(opt_ids - base_ids)
        arrays[array] = {
            "baseline": len(base_ids),
            "optimized": len(opt_ids),
            "missing": missing,
            "extra": extra,
        }
        missing_records.extend({"array": array, "id": value} for value in missing)
        extra_records.extend({"array": array, "id": value} for value in extra)
        total_base += len(base_ids)
        total_opt += len(opt_ids)
        intersection += len(base_ids & opt_ids)

    base_links, opt_links = _evidence_links(baseline), _evidence_links(optimized)
    evidence_regressions: list[dict[str, Any]] = []
    for key, refs in base_links.items():
        if key not in opt_links:
            continue
        missing_refs = sorted(refs - opt_links[key])
        if missing_refs:
            evidence_regressions.append({"array": key[0], "id": key[1], "missing_evidence_ids": missing_refs})

    base_candidates, base_high = _candidate_ids(baseline)
    opt_candidates, _ = _candidate_ids(optimized)
    missing_candidates = sorted(base_candidates - opt_candidates)
    missing_high_risk = sorted(base_high - opt_candidates)

    recall = 1.0 if total_base == 0 else intersection / total_base
    precision = 1.0 if total_opt == 0 else intersection / total_opt
    valid = not missing_records and not evidence_regressions and not missing_high_risk
    return {
        "valid": valid,
        "fact_recall": recall,
        "baseline_fact_precision_against_ids": precision,
        "candidate_recall": 1.0 if not base_candidates else len(base_candidates & opt_candidates) / len(base_candidates),
        "high_risk_candidate_recall": 1.0 if not base_high else len(base_high & opt_candidates) / len(base_high),
        "missing_records": missing_records,
        "extra_records": extra_records,
        "evidence_regressions": evidence_regressions,
        "missing_candidates": missing_candidates,
        "missing_high_risk_candidates": missing_high_risk,
        "arrays": arrays,
        "gate": {
            "fact_recall_must_equal": 1.0,
            "high_risk_candidate_recall_must_equal": 1.0,
            "evidence_linkage_must_not_drop": True,
        },
    }
