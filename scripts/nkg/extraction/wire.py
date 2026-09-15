from __future__ import annotations

from copy import deepcopy
from typing import Any, Mapping

# Only mechanically empty optional fields may be omitted from the model-facing
# wire representation. Semantic fields, evidence IDs and confidence are never
# defaulted because doing so could invent meaning.
EMPTY_DEFAULTS: dict[str, dict[str, Any]] = {
    "commitments": {
        "deadline_chapter": None,
        "deadline_story_time": None,
        "stake_ids": [],
        "resolved_chapter": None,
        "resolution": None,
        "observations": [],
    },
    "romance_routes": {
        "confirmed_chapter": None,
        "confirmed_evidence_ids": [],
        "first_sex_chapter": None,
        "first_sex_evidence_ids": [],
        "notes": "",
    },
    "story_arcs": {
        "chapter_end": None,
        "parent_arc_id": None,
        "phase": None,
        "event_ids": [],
        "entity_ids": [],
        "turning_point_ids": [],
    },
    "review_issues": {"related_ids": []},
}


def compact_fragment(fragment: Mapping[str, Any]) -> dict[str, Any]:
    """Remove only schema-known empty optional defaults from a fragment copy."""
    out = deepcopy(dict(fragment))
    for array, defaults in EMPTY_DEFAULTS.items():
        rows = out.get(array)
        if not isinstance(rows, list):
            continue
        for row in rows:
            if not isinstance(row, dict):
                continue
            for key, default in defaults.items():
                if key in row and row[key] == default:
                    row.pop(key)
    meta = out.setdefault("metadata", {}) if isinstance(out.get("metadata", {}), dict) else {}
    meta["wire_format"] = "nkg-delta-v1"
    out["metadata"] = meta
    return out


def expand_fragment(fragment: Mapping[str, Any]) -> dict[str, Any]:
    """Restore mechanical optional defaults without inventing semantic values."""
    out = deepcopy(dict(fragment))
    for array, defaults in EMPTY_DEFAULTS.items():
        rows = out.get(array)
        if not isinstance(rows, list):
            continue
        for row in rows:
            if not isinstance(row, dict):
                continue
            for key, default in defaults.items():
                row.setdefault(key, deepcopy(default))
    if isinstance(out.get("metadata"), dict):
        out["metadata"].pop("wire_format", None)
    return out
