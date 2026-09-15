from __future__ import annotations

from typing import Any, Mapping

from nkg.core.runtime import GraphRuntime, chapter_value, records

CANONICAL_ARRAYS = (
    "entities", "events", "relations", "state_changes", "romance_routes", "intimate_acts",
    "level_conversions", "character_traits", "chapter_summaries", "story_arcs", "item_roles",
    "commitments", "foreshadowing", "review_issues",
)


def _evidence_ids(value: Any, out: list[str]) -> None:
    if isinstance(value, Mapping):
        for key, item in value.items():
            if key.endswith("evidence_ids") and isinstance(item, list):
                out.extend(ref for ref in item if isinstance(ref, str))
            else:
                _evidence_ids(item, out)
    elif isinstance(value, list):
        for item in value:
            _evidence_ids(item, out)


def build_provenance_index(graph: Mapping[str, Any]) -> dict[str, Any]:
    runtime = GraphRuntime(graph)
    facts: dict[str, Any] = {}
    missing_evidence: set[str] = set()
    for array in CANONICAL_ARRAYS:
        for row in records(graph.get(array)):
            record_id = row.get("id")
            if not isinstance(record_id, str):
                continue
            refs: list[str] = []
            _evidence_ids(row, refs)
            refs = list(dict.fromkeys(refs))
            evidence = []
            for ref in refs:
                source = runtime.evidence_record(ref)
                if source is None:
                    missing_evidence.add(ref)
                    evidence.append({"id": ref, "missing": True})
                else:
                    evidence.append({
                        "id": ref,
                        "chapter": source.get("chapter"),
                        "source_line_start": source.get("source_line_start"),
                        "source_line_end": source.get("source_line_end"),
                    })
            first = next(
                (chapter_value(row.get(key)) for key in ("chapter", "first_chapter", "valid_from", "created_chapter", "planted_chapter", "chapter_start") if chapter_value(row.get(key)) is not None),
                None,
            )
            end = next(
                (chapter_value(row.get(key)) for key in ("valid_to", "resolved_chapter", "payoff_chapter", "chapter_end", "end_chapter") if chapter_value(row.get(key)) is not None),
                None,
            )
            facts[record_id] = {
                "array": array,
                "first_visible_chapter": first,
                "end_chapter": end,
                "confidence": row.get("confidence"),
                "evidence_ids": refs,
                "evidence": evidence,
            }
    return {
        "schema_version": 1,
        "derived_only": True,
        "fact_count": len(facts),
        "facts": facts,
        "missing_evidence_ids": sorted(missing_evidence),
        "contract": "Pointers into canonical graph/evidence only; never a second fact source.",
    }
