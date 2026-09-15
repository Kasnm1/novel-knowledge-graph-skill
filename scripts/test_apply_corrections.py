#!/usr/bin/env python3
"""Transactional correction tests for apply_corrections.py."""

from __future__ import annotations

import copy
import unittest

from apply_corrections import apply_corrections, value_hash


class ApplyCorrectionsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.graph = {
            "metadata": {"title": "Example"},
            "entities": [{"id": "char_a", "name": "A", "friend_ids": ["char_b"]}, {"id": "char_b", "name": "B"}],
            "events": [{"id": "event_1", "participant_ids": ["char_a", "char_b"]}],
        }

    def test_replay_rekey_and_append_are_idempotent(self) -> None:
        before_a = value_hash(self.graph["entities"][0])
        renamed = copy.deepcopy(self.graph["entities"][0])
        renamed["name"] = "Alice"
        renamed_hash = value_hash(renamed)
        corrections = [
            {"correction_id": "c-replace", "operation": "replace", "collection": "entities", "record_id": "char_a", "path": "name", "value": "Alice", "before_hash": before_a, "after_hash": renamed_hash},
            {"correction_id": "c-rekey", "operation": "rekey", "collection": "entities", "record_id": "char_b", "new_id": "char_beta"},
            {"correction_id": "c-append", "operation": "append", "collection": "events", "value": {"id": "event_2", "participant_ids": ["char_beta"]}},
        ]
        output, report = apply_corrections(self.graph, corrections)
        self.assertEqual(self.graph["entities"][0]["name"], "A")
        self.assertEqual(output["entities"][0]["name"], "Alice")
        self.assertEqual(output["entities"][0]["friend_ids"], ["char_beta"])
        self.assertEqual(output["events"][0]["participant_ids"], ["char_a", "char_beta"])
        self.assertEqual([item["status"] for item in report["corrections"]], ["applied", "applied", "applied"])
        replay, replay_report = apply_corrections(output, corrections)
        self.assertEqual(replay, output)
        self.assertTrue(all(item["status"] == "already_applied" for item in replay_report["corrections"]))

    def test_hash_conflict_leaves_transaction_uncommitted(self) -> None:
        original = copy.deepcopy(self.graph)
        corrections = [
            {"correction_id": "c-good", "operation": "replace", "collection": "entities", "record_id": "char_a", "path": "name", "value": "Alice"},
            {"correction_id": "c-bad", "operation": "retract", "collection": "entities", "record_id": "char_b", "before_hash": "not-a-real-hash"},
        ]
        with self.assertRaisesRegex(ValueError, "before_hash conflict"):
            apply_corrections(self.graph, corrections)
        self.assertEqual(self.graph, original)


if __name__ == "__main__":
    unittest.main()
