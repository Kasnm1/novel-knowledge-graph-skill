from __future__ import annotations

import unittest

from build_results_facts import ARRAYS, fact_gate_failures, intimacy_coverage
from required_fields import ARRAY_KINDS


class BuildResultsFactsTests(unittest.TestCase):
    def test_facts_arrays_match_schema_and_include_item_roles(self) -> None:
        self.assertEqual(set(ARRAYS), set(ARRAY_KINDS))
        self.assertIn("item_roles", ARRAYS)

    def test_canonical_intimacy_event_is_not_silently_green(self) -> None:
        graph = {
            "events": [{"id": "ev1", "type": "intimacy", "chapter": 7}],
            "intimate_acts": [],
            "review_issues": [],
        }
        result = intimacy_coverage(graph)
        self.assertEqual(result["intimate_contact_events"], 1)
        self.assertEqual(result["intimate_contact_events_unsilenced"], 1)
        failures = fact_gate_failures({
            "expected_kinds_empty": ("", 0),
            "intimate_contact_events_unsilenced": ("", 1),
        })
        self.assertEqual(len(failures), 1)
        self.assertIn("intimacy", failures[0])

    def test_act_or_explicit_issue_satisfies_gate_and_legacy_alias_is_counted(self) -> None:
        graph = {
            "events": [
                {"id": "ev1", "type": "intimacy", "chapter": 7},
                {"id": "ev2", "type": "intimate_contact", "chapter": 8},
            ],
            "intimate_acts": [{"id": "ia1", "chapter": 7}],
            "review_issues": [{"id": "ri1", "related_ids": ["ev2"]}],
        }
        result = intimacy_coverage(graph)
        self.assertEqual(result["intimate_contact_events"], 2)
        self.assertEqual(result["intimate_contact_events_unsilenced"], 0)


if __name__ == "__main__":
    unittest.main()
