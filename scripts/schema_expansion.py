#!/usr/bin/env python3
"""Compatibility shim for pre-expansion callers.

The commitment contract now lives directly in ``required_fields.py``. Older
wrappers imported ``install_required_fields`` to mutate that module at runtime;
keeping this no-op assertion preserves their import surface without hidden
process-global schema changes.
"""
from __future__ import annotations

COMMITMENT_REQUIRED = (
    "id", "kind", "promisor_ids", "counterparty_ids", "terms",
    "created_chapter", "status", "evidence_ids", "confidence",
)
COMMITMENT_REQUIRED_KEYS = (
    "deadline_chapter", "deadline_story_time", "stake_ids",
    "resolved_chapter", "resolution", "observations",
)


def install_required_fields() -> None:
    """Verify the canonical registry instead of mutating it."""
    import required_fields

    if required_fields.REQUIRED.get("commitment") != COMMITMENT_REQUIRED:
        raise RuntimeError("required_fields.REQUIRED commitment contract drifted")
    if required_fields.REQUIRED_KEYS.get("commitment") != COMMITMENT_REQUIRED_KEYS:
        raise RuntimeError("required_fields.REQUIRED_KEYS commitment contract drifted")
    if required_fields.ARRAY_KINDS.get("commitments") != "commitment":
        raise RuntimeError("required_fields.ARRAY_KINDS is missing commitments")
