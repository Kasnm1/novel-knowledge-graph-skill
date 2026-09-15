#!/usr/bin/env python3
"""Validation and coverage contracts for the growth/world expansion.

This module adds no second source of truth.  It validates optional structures in
``graph.json`` and reports denominators so an empty input can never masquerade as
"0 errors / complete".
"""
from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable

from controlled_vocab import (
    CLIFFHANGER_TYPES,
    COMBAT_KINDS,
    COMBAT_OUTCOMES,
    COMBAT_RESOLUTIONS,
    COMMITMENT_KINDS,
    COMMITMENT_STATUSES,
    CONCEPT_CATEGORIES,
    INFORMATION_MODES,
    PAYOFF_KINDS,
    RELATION_EXTENSION_TYPES,
    SKILL_CATEGORIES,
    category_ids,
    resource_tag_parts,
)

CONFIDENCE = {"explicit", "inferred", "uncertain"}


def _records(value: object) -> list[dict[str, Any]]:
    return [item for item in value if isinstance(item, dict)] if isinstance(value, list) else []


def _idset(graph: dict[str, Any], arrays: Iterable[str]) -> set[str]:
    result: set[str] = set()
    for name in arrays:
        for record in _records(graph.get(name)):
            rid = record.get("id")
            if isinstance(rid, str) and rid:
                result.add(rid)
    return result


def validate_graph_extensions(graph: dict[str, Any]) -> dict[str, Any]:
    errors: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    observations: list[dict[str, Any]] = []

    def add(bucket: list[dict[str, Any]], code: str, message: str, record_id: str | None = None) -> None:
        row: dict[str, Any] = {"code": code, "message": message}
        if record_id:
            row["record_id"] = record_id
        bucket.append(row)

    entities = _records(graph.get("entities"))
    events = _records(graph.get("events"))
    relations = _records(graph.get("relations"))
    evidence = _records(graph.get("evidence"))
    item_roles = _records(graph.get("item_roles"))
    summaries = _records(graph.get("chapter_summaries"))
    commitments_raw = graph.get("commitments", [])
    if "commitments" in graph and not isinstance(commitments_raw, list):
        add(errors, "bad_commitments_array", "commitments must be an array when present")
        commitments: list[dict[str, Any]] = []
    else:
        commitments = _records(commitments_raw)

    entity_ids = {r.get("id") for r in entities if isinstance(r.get("id"), str)}
    evidence_ids = {r.get("id") for r in evidence if isinstance(r.get("id"), str)}
    event_ids = {r.get("id") for r in events if isinstance(r.get("id"), str)}
    known_fact_ids = _idset(
        graph,
        (
            "entities", "events", "relations", "state_changes", "foreshadowing", "evidence",
            "review_issues", "romance_routes", "intimate_acts", "level_conversions",
            "character_traits", "chapter_summaries", "item_roles", "story_arcs", "commitments",
        ),
    )

    # Cross-array ID uniqueness now includes commitments, even before the base
    # validator learns this optional array.
    all_ids: list[str] = []
    for name, value in graph.items():
        if not isinstance(value, list):
            continue
        for record in _records(value):
            rid = record.get("id")
            if isinstance(rid, str) and rid:
                all_ids.append(rid)
    for rid, count in Counter(all_ids).items():
        if count > 1:
            add(errors, "duplicate_id_extended", f"ID appears {count} times across graph arrays", rid)

    # commitments ---------------------------------------------------------
    required = (
        "id", "kind", "promisor_ids", "counterparty_ids", "terms", "created_chapter",
        "status", "evidence_ids", "confidence",
    )
    for record in commitments:
        rid = str(record.get("id") or "<commitment without id>")
        for field in required:
            value = record.get(field)
            if value in (None, "", []):
                add(errors, "commitment_missing_field", f"commitment.{field} is required", rid)
        if record.get("kind") not in COMMITMENT_KINDS:
            add(errors, "bad_commitment_kind", f"unknown commitment kind: {record.get('kind')!r}", rid)
        if record.get("status") not in COMMITMENT_STATUSES:
            add(errors, "bad_commitment_status", f"unknown commitment status: {record.get('status')!r}", rid)
        if record.get("confidence") not in CONFIDENCE:
            add(errors, "bad_commitment_confidence", f"unknown confidence: {record.get('confidence')!r}", rid)
        for field in ("promisor_ids", "counterparty_ids"):
            value = record.get(field)
            if not isinstance(value, list) or any(ref not in entity_ids for ref in value if isinstance(ref, str)):
                add(errors, "bad_commitment_party", f"{field} must contain known entity IDs", rid)
        stake_ids = record.get("stake_ids", [])
        if not isinstance(stake_ids, list):
            add(errors, "bad_commitment_stakes", "stake_ids must be an array", rid)
        else:
            for ref in stake_ids:
                if isinstance(ref, str) and ref not in known_fact_ids:
                    add(errors, "bad_commitment_stake_ref", f"unknown stake ID: {ref}", rid)
        refs = record.get("evidence_ids")
        if not isinstance(refs, list) or not refs:
            add(errors, "missing_commitment_evidence", "commitment requires evidence_ids", rid)
        else:
            for ref in refs:
                if ref not in evidence_ids:
                    add(errors, "bad_commitment_evidence_ref", f"unknown evidence ID: {ref}", rid)
        created = record.get("created_chapter")
        deadline = record.get("deadline_chapter")
        resolved = record.get("resolved_chapter")
        if deadline is not None and (not isinstance(deadline, int) or isinstance(deadline, bool)):
            add(errors, "bad_commitment_deadline", "deadline_chapter must be integer or null", rid)
        if isinstance(created, int) and isinstance(resolved, int) and resolved < created:
            add(errors, "commitment_time_reversal", "resolved_chapter precedes created_chapter", rid)
        terminal = record.get("status") in {"fulfilled", "broken", "expired", "waived"}
        if terminal and not isinstance(resolved, int):
            add(warnings, "terminal_commitment_without_resolution_chapter", "terminal commitment should record resolved_chapter", rid)
        observations_value = record.get("observations", [])
        if observations_value is not None and not isinstance(observations_value, list):
            add(errors, "bad_commitment_observations", "observations must be an array", rid)
        elif isinstance(observations_value, list):
            previous_chapter = record.get("created_chapter") if isinstance(record.get("created_chapter"), int) else -1
            for observation in observations_value:
                if not isinstance(observation, dict):
                    add(errors, "bad_commitment_observation", "commitment observation must be an object", rid)
                    continue
                och = observation.get("chapter")
                if not isinstance(och, int):
                    add(errors, "bad_commitment_observation_chapter", "commitment observation requires integer chapter", rid)
                elif och < previous_chapter:
                    add(errors, "commitment_observation_time_reversal", "commitment observations must be chronological", rid)
                else:
                    previous_chapter = och
                ostatus = observation.get("status")
                if ostatus is not None and ostatus not in COMMITMENT_STATUSES:
                    add(errors, "bad_commitment_observation_status", f"unknown observation status: {ostatus!r}", rid)
                for ref in observation.get("evidence_ids", []) if isinstance(observation.get("evidence_ids"), list) else []:
                    if ref not in evidence_ids:
                        add(errors, "bad_commitment_observation_evidence", f"unknown observation evidence: {ref}", rid)

    # event facets --------------------------------------------------------
    battle_events = [e for e in events if e.get("type") == "battle"]
    structured_battles = 0
    transaction_events = 0
    mortality_events = 0
    information_events = 0
    payoff_events = 0
    for event in events:
        rid = str(event.get("id") or "<event without id>")
        combat = event.get("combat")
        if combat is not None:
            if not isinstance(combat, dict):
                add(errors, "bad_combat_facet", "events[].combat must be an object", rid)
            else:
                structured_battles += 1
                kind = combat.get("kind")
                if kind is not None and kind not in COMBAT_KINDS:
                    add(errors, "bad_combat_kind", f"unknown combat kind: {kind!r}", rid)
                resolution = combat.get("resolution")
                if resolution is not None and resolution not in COMBAT_RESOLUTIONS:
                    add(errors, "bad_combat_resolution", f"unknown combat resolution: {resolution!r}", rid)
                participants = combat.get("participants")
                if not isinstance(participants, list) or not participants:
                    add(errors, "combat_missing_participants", "combat.participants must be a non-empty array", rid)
                else:
                    seen: set[str] = set()
                    for participant in participants:
                        if not isinstance(participant, dict):
                            add(errors, "bad_combat_participant", "combat participant must be an object", rid)
                            continue
                        entity_id = participant.get("entity_id")
                        if entity_id not in entity_ids:
                            add(errors, "bad_combat_entity", f"unknown combat participant: {entity_id!r}", rid)
                        if isinstance(entity_id, str):
                            if entity_id in seen:
                                add(errors, "duplicate_combat_participant", f"duplicate combat participant: {entity_id}", rid)
                            seen.add(entity_id)
                        outcome = participant.get("outcome")
                        if outcome not in COMBAT_OUTCOMES:
                            add(errors, "bad_combat_outcome", f"unknown combat outcome: {outcome!r}", rid)
                        for forbidden in ("level", "realm", "cultivation_level", "level_at_battle"):
                            if forbidden in participant:
                                add(warnings, "combat_embeds_level_snapshot", f"{forbidden} duplicates temporal state; derive it at event.chapter", rid)
                for field in ("stake_ids", "killed_ids"):
                    value = combat.get(field, [])
                    if value is not None and not isinstance(value, list):
                        add(errors, "bad_combat_refs", f"combat.{field} must be an array", rid)
                    elif isinstance(value, list):
                        for ref in value:
                            if isinstance(ref, str) and ref not in known_fact_ids:
                                add(errors, "bad_combat_ref", f"unknown combat.{field} reference: {ref}", rid)
        if event.get("type") == "battle" and combat is None:
            add(observations, "battle_without_combat", "battle event has no structured combat facet", rid)

        transaction = event.get("transaction")
        if transaction is not None:
            transaction_events += 1
            if not isinstance(transaction, dict):
                add(errors, "bad_transaction_facet", "events[].transaction must be an object", rid)
            else:
                for field in ("buyer_ids", "seller_ids", "item_ids"):
                    value = transaction.get(field, [])
                    if value is not None and not isinstance(value, list):
                        add(errors, "bad_transaction_refs", f"transaction.{field} must be an array", rid)
                    elif isinstance(value, list):
                        for ref in value:
                            if isinstance(ref, str) and ref not in entity_ids:
                                add(errors, "bad_transaction_ref", f"unknown transaction.{field} entity: {ref}", rid)
                currency = transaction.get("currency_id")
                if currency is not None and currency not in entity_ids:
                    add(errors, "bad_transaction_currency", f"unknown transaction currency: {currency}", rid)

        mortality = event.get("mortality")
        if mortality is not None:
            mortality_events += 1
            if not isinstance(mortality, dict):
                add(errors, "bad_mortality_facet", "events[].mortality must be an object", rid)
            else:
                for field in ("deceased_ids", "killer_ids", "witness_ids"):
                    value = mortality.get(field, [])
                    if value is not None and not isinstance(value, list):
                        add(errors, "bad_mortality_refs", f"mortality.{field} must be an array", rid)
                    elif isinstance(value, list):
                        for ref in value:
                            if isinstance(ref, str) and ref not in entity_ids:
                                add(errors, "bad_mortality_ref", f"unknown mortality.{field} entity: {ref}", rid)

        information = event.get("information")
        if information is not None:
            information_events += 1
            if not isinstance(information, dict):
                add(errors, "bad_information_facet", "events[].information must be an object", rid)
            else:
                mode = information.get("mode")
                if mode is not None and mode not in INFORMATION_MODES:
                    add(errors, "bad_information_mode", f"unknown information mode: {mode!r}", rid)
                for field in ("audience_ids", "secret_ids"):
                    value = information.get(field, [])
                    if value is not None and not isinstance(value, list):
                        add(errors, "bad_information_refs", f"information.{field} must be an array", rid)
                    elif isinstance(value, list):
                        for ref in value:
                            if isinstance(ref, str) and ref not in entity_ids:
                                add(errors, "bad_information_ref", f"unknown information.{field} entity: {ref}", rid)
                revealer = information.get("revealer_id")
                if revealer is not None and revealer not in entity_ids:
                    add(errors, "bad_information_revealer", f"unknown information revealer: {revealer}", rid)

        payoff = event.get("payoff")
        if payoff is not None:
            payoff_events += 1
            if not isinstance(payoff, dict):
                add(errors, "bad_payoff_facet", "events[].payoff must be an object", rid)
            else:
                kind = payoff.get("kind")
                if kind is not None and kind not in PAYOFF_KINDS:
                    add(errors, "bad_payoff_kind", f"unknown payoff kind: {kind!r}", rid)
                setup_ids = payoff.get("setup_ids", [])
                if not isinstance(setup_ids, list):
                    add(errors, "bad_payoff_setup_ids", "payoff.setup_ids must be an array", rid)
                else:
                    for ref in setup_ids:
                        if isinstance(ref, str) and ref not in known_fact_ids:
                            add(errors, "bad_payoff_setup_ref", f"unknown payoff setup: {ref}", rid)

    # entity classifications ---------------------------------------------
    skill_entities = [e for e in entities if e.get("type") == "skill"]
    classified_skills = 0
    for entity in skill_entities:
        rid = str(entity.get("id") or "<skill without id>")
        cats = category_ids(entity.get("categories"))
        if cats:
            classified_skills += 1
        for category in cats:
            if category not in SKILL_CATEGORIES:
                add(errors, "unknown_skill_category", f"unknown skill category: {category}", rid)

    concept_entities = [e for e in entities if e.get("type") == "concept"]
    for entity in concept_entities:
        rid = str(entity.get("id") or "<concept without id>")
        for category in category_ids(entity.get("categories")):
            if category not in CONCEPT_CATEGORIES:
                add(errors, "unknown_concept_category", f"unknown concept category: {category}", rid)

    item_entities = [e for e in entities if e.get("type") == "item"]
    resource_tagged_items = 0
    for entity in item_entities:
        rarity, supply, malformed = resource_tag_parts(entity.get("tags"))
        if rarity or supply:
            resource_tagged_items += 1
        for tag in malformed:
            add(errors, "bad_resource_tag", f"invalid reserved resource tag: {tag}", str(entity.get("id") or ""))

    # chapter narrative fields -------------------------------------------
    for summary in summaries:
        rid = str(summary.get("id") or "<chapter summary without id>")
        pov = summary.get("pov_entity_ids")
        if pov is not None:
            if not isinstance(pov, list):
                add(errors, "bad_pov_entity_ids", "pov_entity_ids must be an array", rid)
            else:
                for ref in pov:
                    if ref not in entity_ids:
                        add(errors, "bad_pov_entity_ref", f"unknown POV entity: {ref}", rid)
        scene_count = summary.get("scene_count")
        if scene_count is not None and (not isinstance(scene_count, int) or isinstance(scene_count, bool) or scene_count < 0):
            add(errors, "bad_scene_count", "scene_count must be a non-negative integer", rid)
        cliff = summary.get("cliffhanger_type")
        if cliff is not None and cliff not in CLIFFHANGER_TYPES:
            add(errors, "bad_cliffhanger_type", f"unknown cliffhanger_type: {cliff!r}", rid)
        story_time = summary.get("story_time")
        if story_time is not None and not isinstance(story_time, (str, dict)):
            add(errors, "bad_story_time", "story_time must be a source-faithful string or object", rid)

    # relation extensions -------------------------------------------------
    extension_relations = 0
    location_ids = {e.get("id") for e in entities if e.get("type") == "location"}
    organization_ids = {e.get("id") for e in entities if e.get("type") == "organization"}
    for relation in relations:
        rtype = relation.get("relation_type")
        if rtype not in RELATION_EXTENSION_TYPES:
            continue
        extension_relations += 1
        rid = str(relation.get("id") or "<relation without id>")
        if rtype == "owes_favor_to" and relation.get("strength") not in (1, 2, 3):
            add(errors, "bad_favor_strength", "owes_favor_to requires strength 1..3", rid)
        if rtype == "controlled_by":
            if relation.get("source_id") not in location_ids or relation.get("target_id") not in organization_ids:
                add(errors, "bad_control_relation", "controlled_by must be location -> organization", rid)

    # coverage denominators ----------------------------------------------
    hierarchy_children = {
        r.get("source_id") for r in relations
        if r.get("relation_type") in {"located_in", "part_of"} and r.get("source_id") in location_ids
    }
    event_locations = sum(1 for e in events if e.get("location_id") in location_ids)
    item_roles_with_cause = sum(1 for role in item_roles if role.get("cause_event_id") in event_ids)
    # Side-character relation coverage: repeated co-occurrence is only a candidate,
    # never a fact. The denominator therefore measures review work, not relations.
    character_ids = {e.get("id") for e in entities if e.get("type") == "character"}
    pair_counts: Counter[tuple[str, str]] = Counter()
    for event in events:
        people = sorted(set(event.get("participant_ids") or []) & character_ids) if isinstance(event.get("participant_ids"), list) else []
        for i in range(len(people)):
            for j in range(i + 1, len(people)):
                pair_counts[(people[i], people[j])] += 1
    related_pairs = {tuple(sorted((r.get("source_id"), r.get("target_id")))) for r in relations if r.get("source_id") in character_ids and r.get("target_id") in character_ids}
    side_candidates = {pair for pair, count in pair_counts.items() if count >= 3}
    side_resolved = {pair for pair in side_candidates if pair in related_pairs}
    secret_ids = {e.get("id") for e in concept_entities if "secret" in category_ids(e.get("categories"))}
    knowledge_targets = {c.get("target_id") for c in _records(graph.get("state_changes")) if str(c.get("facet") or "").lower() in {"knowledge", "知情", "秘密知情", "知道"}}
    coverage = {
        "battle_combat": {"covered": structured_battles, "total": len(battle_events)},
        "skill_categories": {"covered": classified_skills, "total": len(skill_entities)},
        "location_hierarchy": {"covered": len(hierarchy_children), "total": len(location_ids)},
        "event_location": {"covered": event_locations, "total": len(events)},
        "item_role_cause": {"covered": item_roles_with_cause, "total": len(item_roles)},
        "chapter_summaries": {
            "covered": len({s.get("chapter") for s in summaries if isinstance(s.get("chapter"), int)}),
            "total": len(graph.get("metadata", {}).get("analyzed_chapters", [])) if isinstance(graph.get("metadata"), dict) else 0,
        },
        "resource_tags": {"covered": resource_tagged_items, "total": len(item_entities)},
        "side_character_relations": {"covered": len(side_resolved), "total": len(side_candidates)},
        "secret_knowledge": {"covered": len(secret_ids & knowledge_targets), "total": len(secret_ids)},
        "commitment_lifecycle": {"covered": sum(1 for c in commitments if c.get("status") not in {None, "uncertain"}), "total": len(commitments)},
    }
    for name, row in coverage.items():
        total = row["total"]
        row["ratio"] = (row["covered"] / total) if total else None
        if total == 0:
            add(observations, "coverage_empty_input", f"{name}: denominator is 0; this is not a completeness pass")

    return {
        "valid": not errors,
        "error_count": len(errors),
        "warning_count": len(warnings),
        "observation_count": len(observations),
        "errors": errors,
        "warnings": warnings,
        "observations": observations,
        "coverage": coverage,
        "counts": {
            "commitments": len(commitments),
            "combat_facets": structured_battles,
            "transaction_facets": transaction_events,
            "mortality_facets": mortality_events,
            "information_facets": information_events,
            "payoff_facets": payoff_events,
            "extension_relations": extension_relations,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--graph", required=True, type=Path)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    graph = json.loads(args.graph.read_text(encoding="utf-8"))
    report = validate_graph_extensions(graph)
    text = json.dumps(report, ensure_ascii=False, indent=2)
    if args.report:
        args.report.write_text(text, encoding="utf-8")
    print(text)
    return 0 if report["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
