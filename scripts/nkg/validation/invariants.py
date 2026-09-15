from __future__ import annotations

from collections import defaultdict
from typing import Any, Mapping

from nkg.core.runtime import GraphRuntime, chapter_value, records

RESET_ACTIONS = {"reset", "replaced", "transformed", "unknown", "corrected", "revived", "restored"}
FLASHBACK_TAGS = {"flashback", "backstory", "reported_history", "prophecy"}


def _issue(level: str, code: str, message: str, *record_ids: str) -> dict[str, Any]:
    return {
        "level": level,
        "code": code,
        "message": message,
        "record_ids": [value for value in record_ids if value],
    }


def _state_chain_issues(runtime: GraphRuntime) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    for (entity_id, facet), rows in runtime.state_changes_by_entity_facet.items():
        previous: Mapping[str, Any] | None = None
        for row in rows:
            if previous is not None:
                prior_after = previous.get("after")
                current_before = row.get("before")
                if (
                    prior_after not in (None, "", [], {})
                    and current_before not in (None, "", [], {})
                    and prior_after != current_before
                    and str(row.get("action") or "").lower() not in RESET_ACTIONS
                ):
                    issues.append(_issue(
                        "warning",
                        "state_chain_discontinuity",
                        f"{entity_id}.{facet} before={current_before!r} does not continue prior after={prior_after!r}",
                        str(previous.get("id") or ""),
                        str(row.get("id") or ""),
                    ))
            previous = row
    return issues


def _relation_interval_issues(runtime: GraphRuntime) -> list[dict[str, Any]]:
    buckets: dict[tuple[str, str, str], list[Mapping[str, Any]]] = defaultdict(list)
    for row in runtime.relations:
        source, target = str(row.get("source_id") or ""), str(row.get("target_id") or "")
        relation_type = str(row.get("relation_type") or "")
        buckets[(source, target, relation_type)].append(row)
    issues: list[dict[str, Any]] = []
    for key, rows in buckets.items():
        rows = sorted(rows, key=lambda r: (chapter_value(r.get("valid_from")) or 0, str(r.get("id") or "")))
        for left, right in zip(rows, rows[1:]):
            left_start = chapter_value(left.get("valid_from"))
            right_start = chapter_value(right.get("valid_from"))
            left_end = chapter_value(left.get("valid_to"))
            if left_start is None or right_start is None:
                continue
            if left_end is not None and right_start <= left_end and left.get("episode_id") != right.get("episode_id"):
                issues.append(_issue(
                    "warning",
                    "overlapping_relation_episodes",
                    f"relation {key[0]} -> {key[1]} ({key[2]}) has overlapping episodes",
                    str(left.get("id") or ""),
                    str(right.get("id") or ""),
                ))
            if left_end is not None and left_end < left_start:
                issues.append(_issue(
                    "error",
                    "invalid_relation_interval",
                    f"relation valid_to {left_end} precedes valid_from {left_start}",
                    str(left.get("id") or ""),
                ))
    return issues


def _mortality_issues(runtime: GraphRuntime) -> list[dict[str, Any]]:
    deaths: dict[str, list[tuple[int, str]]] = defaultdict(list)
    revivals: dict[str, list[int]] = defaultdict(list)
    for event in runtime.events:
        facet = event.get("mortality")
        if not isinstance(facet, dict):
            continue
        chapter = chapter_value(event.get("chapter"))
        if chapter is None:
            continue
        for entity_id in facet.get("deceased_ids", []) if isinstance(facet.get("deceased_ids"), list) else []:
            if isinstance(entity_id, str):
                deaths[entity_id].append((chapter, str(event.get("id") or "")))
        for entity_id in facet.get("revived_ids", []) if isinstance(facet.get("revived_ids"), list) else []:
            if isinstance(entity_id, str):
                revivals[entity_id].append(chapter)
    for change in runtime.state_changes:
        if str(change.get("facet") or "").lower() not in {"health", "生命", "生死", "存活状态"}:
            continue
        value = str(change.get("after") or "").lower()
        if value in {"alive", "revived", "resurrected", "复活", "存活", "生还"} and isinstance(change.get("entity_id"), str):
            chapter = chapter_value(change.get("chapter"))
            if chapter is not None:
                revivals[change["entity_id"]].append(chapter)

    issues: list[dict[str, Any]] = []
    for entity_id, entries in deaths.items():
        for death_chapter, death_event in entries:
            next_revival = min((value for value in revivals.get(entity_id, []) if value > death_chapter), default=None)
            for event in runtime.events_for(entity_id, death_chapter + 1, (next_revival - 1) if next_revival else None):
                tags = set(event.get("tags") or []) if isinstance(event.get("tags"), list) else set()
                if tags & FLASHBACK_TAGS:
                    continue
                issues.append(_issue(
                    "warning",
                    "possible_post_death_activity",
                    f"{entity_id} appears in chapter {event.get('chapter')} after a recorded death and before a recorded revival; inspect story-time/flashback semantics",
                    death_event,
                    str(event.get("id") or ""),
                ))
                break
    return issues


def _territory_issues(runtime: GraphRuntime) -> list[dict[str, Any]]:
    by_location: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for row in runtime.relations:
        if row.get("relation_type") == "controlled_by" and isinstance(row.get("source_id"), str):
            by_location[row["source_id"]].append(row)
    issues: list[dict[str, Any]] = []
    for location_id, rows in by_location.items():
        rows = sorted(rows, key=lambda r: (chapter_value(r.get("valid_from")) or 0, str(r.get("id") or "")))
        for left, right in zip(rows, rows[1:]):
            lstart, rstart = chapter_value(left.get("valid_from")), chapter_value(right.get("valid_from"))
            lend = chapter_value(left.get("valid_to"))
            if lstart is None or rstart is None:
                continue
            if (lend is None or rstart <= lend) and left.get("target_id") != right.get("target_id"):
                issues.append(_issue(
                    "warning",
                    "overlapping_territory_control",
                    f"{location_id} has overlapping controlled_by intervals; confirm shared control or close the earlier interval",
                    str(left.get("id") or ""),
                    str(right.get("id") or ""),
                ))
    return issues


def validate_invariants(graph: Mapping[str, Any]) -> dict[str, Any]:
    runtime = GraphRuntime(graph)
    issues = [
        *_state_chain_issues(runtime),
        *_relation_interval_issues(runtime),
        *_mortality_issues(runtime),
        *_territory_issues(runtime),
    ]
    errors = [row for row in issues if row["level"] == "error"]
    warnings = [row for row in issues if row["level"] == "warning"]
    counts: dict[str, int] = defaultdict(int)
    for row in issues:
        counts[row["code"]] += 1
    return {
        "valid": not errors,
        "error_count": len(errors),
        "warning_count": len(warnings),
        "counts": dict(sorted(counts.items())),
        "errors": errors,
        "warnings": warnings,
        "runtime_stats": runtime.stats.__dict__,
    }
