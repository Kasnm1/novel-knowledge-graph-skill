#!/usr/bin/env python3
"""Validate accuracy-preserving retrieval coverage receipts.

This gate deliberately validates retrieval sufficiency, not story truth. It is
dependency-free so every canonical run can execute the current installed Skill unchanged.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


LEVELS = {"R0": 0, "R1": 1, "R2": 2, "R3": 3, "R4": 4, "R5": 5}
MINIMUM_LEVEL = {
    "local_explicit": "R1",
    "temporal_state": "R2",
    "cross_chapter": "R3",
    "global_aggregate": "R4",
    "negative_or_universal": "R4",
}
CONFIRMING_RESULTS = {"confirmed", "confirmed_absent", "found", "no_change"}
ALLOWED_RESULTS = CONFIRMING_RESULTS | {"not_found_in_scope", "unresolved"}
HIGH_RISK_TRIGGERS = {
    "identity",
    "intimacy",
    "foreshadowing_payoff",
    "knowledge_state",
    "first_last_only_never",
    "correction",
}


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def validate_receipt(receipt: Any, source: str) -> list[str]:
    errors: list[str] = []
    if not isinstance(receipt, dict):
        return [f"{source}: receipt must be a JSON object"]

    scope = receipt.get("claim_scope")
    level = receipt.get("retrieval_level")
    result = receipt.get("result_semantics")
    closure_complete = receipt.get("closure_complete")
    needs_expansion = receipt.get("needs_expanded_retrieval")
    opened = _as_list(receipt.get("evidence_ids_opened"))
    triggers = set(_as_list(receipt.get("escalation_triggers")))

    if not receipt.get("receipt_id"):
        errors.append(f"{source}: missing receipt_id")
    if not receipt.get("source_fingerprint"):
        errors.append(f"{source}: missing source_fingerprint")
    if not receipt.get("snapshot_id"):
        errors.append(f"{source}: missing snapshot_id")
    if scope not in MINIMUM_LEVEL:
        errors.append(f"{source}: unknown claim_scope {scope!r}")
    if level not in LEVELS:
        errors.append(f"{source}: unknown retrieval_level {level!r}")
    if not isinstance(closure_complete, bool):
        errors.append(f"{source}: closure_complete must be boolean")
    if not isinstance(needs_expansion, bool):
        errors.append(f"{source}: needs_expanded_retrieval must be boolean")
    if result not in ALLOWED_RESULTS:
        errors.append(f"{source}: unknown result_semantics {result!r}")

    if scope in MINIMUM_LEVEL and level in LEVELS:
        required = MINIMUM_LEVEL[scope]
        if LEVELS[level] < LEVELS[required]:
            errors.append(
                f"{source}: {scope} requires at least {required}, got {level}"
            )

    if result in CONFIRMING_RESULTS and closure_complete is not True:
        errors.append(f"{source}: confirming result requires closure_complete=true")
    if result in CONFIRMING_RESULTS and needs_expansion is True:
        errors.append(
            f"{source}: confirming result forbidden while needs_expanded_retrieval=true"
        )
    if scope == "negative_or_universal" and result in CONFIRMING_RESULTS:
        if level not in {"R4", "R5"}:
            errors.append(f"{source}: negative/universal confirmation requires R4 or R5")
        if not _as_list(receipt.get("indexes_used")):
            errors.append(f"{source}: negative/universal confirmation requires indexes_used")
        if not _as_list(receipt.get("chapter_ranges_searched")):
            errors.append(
                f"{source}: negative/universal confirmation requires chapter_ranges_searched"
            )
    if result == "confirmed_absent" and scope != "negative_or_universal":
        errors.append(f"{source}: confirmed_absent requires negative_or_universal scope")
    if scope in {"local_explicit", "cross_chapter"}:
        if result in CONFIRMING_RESULTS and not opened:
            errors.append(f"{source}: confirmed {scope} claim requires opened evidence")
    if triggers.intersection(HIGH_RISK_TRIGGERS) and result in CONFIRMING_RESULTS:
        direct_evidence_triggers = triggers - {"first_last_only_never"}
        first_last_positive = (
            "first_last_only_never" in triggers and result != "confirmed_absent"
        )
        if (direct_evidence_triggers or first_last_positive) and not opened:
            errors.append(f"{source}: high-risk confirmation requires opened evidence")
        if closure_complete is not True:
            errors.append(f"{source}: high-risk confirmation requires complete closure")
    if result == "not_found_in_scope" and closure_complete is True:
        errors.append(
            f"{source}: complete closure must use an explicit confirmed/unresolved result, "
            "not not_found_in_scope"
        )

    return errors


def load_receipts(path: Path) -> list[tuple[dict[str, Any], str]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, list):
        return [(item, f"{path}[{index}]") for index, item in enumerate(data)]
    if isinstance(data, dict) and isinstance(data.get("coverage_receipts"), list):
        return [
            (item, f"{path}.coverage_receipts[{index}]")
            for index, item in enumerate(data["coverage_receipts"])
        ]
    return [(data, str(path))]


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Audit context-retrieval coverage receipts before merge"
    )
    parser.add_argument("receipts", nargs="+", type=Path)
    args = parser.parse_args()

    errors: list[str] = []
    for path in args.receipts:
        try:
            for receipt, source in load_receipts(path):
                errors.extend(validate_receipt(receipt, source))
        except (OSError, json.JSONDecodeError) as exc:
            errors.append(f"{path}: {exc}")

    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1
    print(f"context coverage audit passed: {len(args.receipts)} file(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
