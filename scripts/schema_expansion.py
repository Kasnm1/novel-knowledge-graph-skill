#!/usr/bin/env python3
"""Install the expansion record contract into legacy pipeline modules at runtime.

The repository historically centralised required fields in ``required_fields``
but older releases do not know ``commitments`` yet. Wrappers import this module
before invoking the legacy merge/check scripts, preserving compatibility while
keeping the new top-level record type singular.
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
    import required_fields

    required_fields.REQUIRED["commitment"] = COMMITMENT_REQUIRED
    required_fields.REQUIRED_KEYS["commitment"] = COMMITMENT_REQUIRED_KEYS
    required_fields.ARRAY_KINDS["commitments"] = "commitment"
