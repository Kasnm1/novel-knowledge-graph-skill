from __future__ import annotations

import unittest

from validate_style_observations import StyleObservationError, validate_style_observations


class StyleObservationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.graph = {
            "entities": [{"id": "char_a", "type": "character"}],
            "story_arcs": [{"id": "arc_a"}],
            "evidence": [{"id": "ev1"}],
        }

    def test_valid_dimensions_are_sorted_and_evidence_backed(self) -> None:
        rows = validate_style_observations({"observations": [{
            "id": "sty1", "scope": "character", "entity_id": "char_a", "dimension": "speech",
            "claim": "Uses short restrained clauses.", "chapter_start": 1, "chapter_end": 20,
            "stability": "contextual", "confidence": "inferred", "evidence_ids": ["ev1"], "counterexamples": [],
        }]}, self.graph)
        self.assertEqual(rows[0]["id"], "sty1")

    def test_missing_evidence_and_bad_scope_fail(self) -> None:
        with self.assertRaises(StyleObservationError):
            validate_style_observations({"observations": [{
                "id": "sty1", "scope": "character", "entity_id": "missing", "dimension": "speech",
                "claim": "Claim", "chapter_start": 1, "chapter_end": 2, "stability": "stable",
                "confidence": "explicit", "evidence_ids": [], "counterexamples": [],
            }]}, self.graph)


if __name__ == "__main__":
    unittest.main()
