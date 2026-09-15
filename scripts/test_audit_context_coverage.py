from __future__ import annotations

import unittest

from audit_context_coverage import validate_receipt


def receipt(**updates):
    value = {
        "receipt_id": "cov_1",
        "claim_scope": "local_explicit",
        "retrieval_level": "R1",
        "source_fingerprint": "src",
        "snapshot_id": "snap",
        "evidence_ids_opened": ["ev_1"],
        "indexes_used": [],
        "escalation_triggers": [],
        "needs_expanded_retrieval": False,
        "closure_complete": True,
        "result_semantics": "confirmed",
    }
    value.update(updates)
    return value


class ContextCoverageTests(unittest.TestCase):
    def test_local_confirmed_passes_with_opened_evidence(self):
        self.assertEqual(validate_receipt(receipt(), "case"), [])

    def test_partial_search_cannot_confirm(self):
        errors = validate_receipt(
            receipt(closure_complete=False, result_semantics="confirmed"), "case"
        )
        self.assertTrue(any("closure_complete" in error for error in errors))

    def test_negative_claim_requires_global_index(self):
        errors = validate_receipt(
            receipt(
                claim_scope="negative_or_universal",
                retrieval_level="R4",
                indexes_used=[],
            ),
            "case",
        )
        self.assertTrue(any("indexes_used" in error for error in errors))

    def test_confirmed_absence_uses_coverage_not_fabricated_evidence(self):
        value = receipt(
            claim_scope="negative_or_universal",
            retrieval_level="R4",
            result_semantics="confirmed_absent",
            evidence_ids_opened=[],
            indexes_used=["events_by_type"],
            chapter_ranges_searched=[[1, 100]],
        )
        self.assertEqual(validate_receipt(value, "case"), [])

    def test_expansion_blocks_confirmation(self):
        errors = validate_receipt(
            receipt(needs_expanded_retrieval=True), "case"
        )
        self.assertTrue(any("needs_expanded_retrieval" in error for error in errors))

    def test_temporal_state_requires_r2(self):
        errors = validate_receipt(
            receipt(claim_scope="temporal_state", retrieval_level="R1"), "case"
        )
        self.assertTrue(any("requires at least R2" in error for error in errors))


if __name__ == "__main__":
    unittest.main()
