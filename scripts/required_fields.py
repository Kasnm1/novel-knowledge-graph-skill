#!/usr/bin/env python3
"""Shared required-field contract for fragment and merged-graph validation.

`REQUIRED` values must be non-empty. `REQUIRED_KEYS` must exist but may be null
or empty where the schema explicitly allows that.  Keep this module as the one
source used by both pre-merge and post-merge gates.
"""
from __future__ import annotations

REQUIRED: dict[str, tuple[str, ...]] = {
    "evidence": ("id", "chapter", "quote", "source_line_start", "source_line_end"),
    "entity": ("id", "type", "name", "first_chapter", "evidence_ids"),
    "event": (
        "id", "type", "chapter", "title", "description", "participant_ids", "evidence_ids",
    ),
    "relation": (
        "id", "source_id", "target_id", "relation_type", "valid_from", "status", "evidence_ids",
    ),
    "state_change": (
        "id", "entity_id", "facet", "action", "chapter", "reason", "evidence_ids", "confidence",
    ),
    "romance_route": (
        "id", "protagonist_id", "character_id", "status", "inclusion_basis", "consent_context",
        "first_meeting_chapter", "first_meeting_evidence_ids",
        "ambiguity_started_chapter", "ambiguity_evidence_ids", "confidence",
    ),
    "intimate_act": ("id", "chapter", "act_type", "description", "confidence"),
    "level_conversion": ("id", "chapter", "from", "to", "relation", "description"),
    "character_trait": (
        "id", "entity_id", "facet", "statement", "chapter", "evidence_ids", "confidence",
    ),
    "chapter_summary": ("id", "chapter", "summary", "evidence_ids"),
    "story_arc": ("id", "title", "chapter_start", "status", "evidence_ids"),
    "item_role": (
        "id", "item_id", "entity_id", "role", "valid_from", "action",
        "evidence_ids", "confidence",
    ),
    "commitment": (
        "id", "kind", "promisor_ids", "counterparty_ids", "terms",
        "created_chapter", "status", "evidence_ids", "confidence",
    ),
    "foreshadowing": (
        "id", "label", "status", "planted_chapter", "observation",
        "interpretation", "related_entity_ids", "evidence_ids", "confidence",
    ),
    "review_issue": ("id", "severity", "category", "description", "chapter"),
}

REQUIRED_KEYS: dict[str, tuple[str, ...]] = {
    "romance_route": (
        "confirmed_chapter", "confirmed_evidence_ids", "first_sex_chapter",
        "first_sex_evidence_ids", "notes",
    ),
    "review_issue": ("related_ids",),
    "story_arc": (
        "chapter_end", "parent_arc_id", "phase", "event_ids", "entity_ids", "turning_point_ids",
    ),
    "commitment": (
        "deadline_chapter", "deadline_story_time", "stake_ids",
        "resolved_chapter", "resolution", "observations",
    ),
}

ARRAY_KINDS: dict[str, str] = {
    "entities": "entity",
    "events": "event",
    "relations": "relation",
    "state_changes": "state_change",
    "romance_routes": "romance_route",
    "intimate_acts": "intimate_act",
    "level_conversions": "level_conversion",
    "character_traits": "character_trait",
    "chapter_summaries": "chapter_summary",
    "story_arcs": "story_arc",
    "item_roles": "item_role",
    "commitments": "commitment",
    "foreshadowing": "foreshadowing",
    "evidence": "evidence",
    "review_issues": "review_issue",
}

EXPECTED_NON_EMPTY: tuple[str, ...] = ("character_traits",)

CONFIDENCE: frozenset[str] = frozenset({"explicit", "inferred", "uncertain"})

DERIVED: dict[str, tuple[str, ...]] = {
    "evidence": ("source_line_start", "source_line_end"),
}


def is_blank(value: object) -> bool:
    """Match validate_graph.require(): None, empty string and empty list are blank."""
    return value is None or value == "" or value == []
