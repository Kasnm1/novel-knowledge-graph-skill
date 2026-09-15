from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from required_fields import ARRAY_KINDS, REQUIRED, REQUIRED_KEYS
from snapshot import build_snapshot, story_arcs_intersecting


SCRIPTS = Path(__file__).resolve().parent


def graph_fixture() -> dict:
    return {
        "metadata": {
            "title": "Arc test", "source_file": "book.txt", "source_sha256": "0" * 64,
            "chapter_start": 1, "chapter_end": 3, "analyzed_chapters": [1, 2, 3],
            "generated_at": "2026-09-15T00:00:00+00:00",
        },
        "entities": [{"id": "char_a", "type": "character", "name": "A", "first_chapter": 1, "evidence_ids": ["ev1"]}],
        "events": [{"id": "event_turn", "type": "other", "chapter": 2, "title": "Turn", "description": "Turning point", "participant_ids": ["char_a"], "evidence_ids": ["ev1"]}],
        "relations": [], "state_changes": [], "foreshadowing": [], "review_issues": [],
        "evidence": [{"id": "ev1", "chapter": 1, "quote": "evidence text", "source_line_start": 1, "source_line_end": 1}],
        "story_arcs": [
            {"id": "arc_a", "title": "Long", "chapter_start": 1, "chapter_end": 3, "parent_arc_id": None, "status": "active", "phase": "development", "event_ids": ["event_turn"], "entity_ids": ["char_a"], "turning_point_ids": ["event_turn"], "evidence_ids": ["ev1"]},
            {"id": "arc_b", "title": "Nested", "chapter_start": 2, "chapter_end": None, "parent_arc_id": "arc_a", "status": "open", "phase": "escalation", "event_ids": [], "entity_ids": ["char_a"], "turning_point_ids": [], "evidence_ids": ["ev1"]},
        ],
        "chapter_summaries": [{"id": "sum2", "chapter": 2, "summary": "A sufficiently long chapter summary for validation.", "arc_ids": ["arc_a", "arc_b"], "dominant_arc_id": "arc_b", "narrative_phase": "escalation", "evidence_ids": ["ev1"]}],
    }


class StoryArcContractTests(unittest.TestCase):
    def test_story_arcs_are_first_class_and_overlap_in_snapshots(self) -> None:
        self.assertEqual(ARRAY_KINDS["story_arcs"], "story_arc")
        self.assertIn("chapter_start", REQUIRED["story_arc"])
        self.assertIn("parent_arc_id", REQUIRED_KEYS["story_arc"])
        graph = graph_fixture()
        self.assertEqual([row["id"] for row in story_arcs_intersecting(graph, 2)], ["arc_a", "arc_b"])
        snapshot = build_snapshot(graph, 2)
        self.assertEqual({row["id"] for row in snapshot["active_story_arcs"]}, {"arc_a", "arc_b"})
        self.assertEqual({row["id"] for row in snapshot["dynamic_state"]["char_a"]["story_arcs"]}, {"arc_a", "arc_b"})

    def test_validator_accepts_overlap_and_rejects_parent_cycles(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "graph.json"
            path.write_text(json.dumps(graph_fixture()), encoding="utf-8")
            valid = subprocess.run([sys.executable, str(SCRIPTS / "validate_graph.py"), "--graph", str(path)], capture_output=True, text=True, encoding="utf-8")
            self.assertEqual(valid.returncode, 0, valid.stdout + valid.stderr)
            broken = graph_fixture()
            broken["story_arcs"][0]["parent_arc_id"] = "arc_b"
            path.write_text(json.dumps(broken), encoding="utf-8")
            invalid = subprocess.run([sys.executable, str(SCRIPTS / "validate_graph.py"), "--graph", str(path)], capture_output=True, text=True, encoding="utf-8")
            self.assertNotEqual(invalid.returncode, 0)
            self.assertIn("cyclic_arc_parent", invalid.stdout)

    def test_broad_intimacy_candidate_requires_route_or_explicit_exclusion(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "graph.json"
            graph = graph_fixture()
            graph["metadata"]["protagonist_ids"] = ["char_a"]
            graph["entities"].append({"id": "char_b", "type": "character", "name": "B", "first_chapter": 1, "evidence_ids": ["ev1"]})
            graph["intimate_acts"] = [{"id": "ia1", "chapter": 2, "act_type": "kiss", "description": "A kisses B.", "initiator_ids": ["char_a"], "recipient_ids": ["char_b"], "observer_ids": [], "consent": "uncertain", "confidence": "explicit", "evidence_ids": ["ev1"]}]
            path.write_text(json.dumps(graph), encoding="utf-8")
            missing = subprocess.run([sys.executable, str(SCRIPTS / "validate_graph.py"), "--graph", str(path)], capture_output=True, text=True, encoding="utf-8")
            self.assertIn("missing_romance_route_candidate", missing.stdout)
            graph["romance_routes"] = [{
                "id": "rom_ab", "protagonist_id": "char_a", "character_id": "char_b",
                "status": "excluded_nonromantic", "inclusion_basis": "intimate_contact",
                "consent_context": "uncertain", "first_meeting_chapter": 1,
                "first_meeting_evidence_ids": ["ev1"], "ambiguity_started_chapter": 1,
                "ambiguity_evidence_ids": ["ev1"], "confirmed_chapter": None,
                "confirmed_evidence_ids": [], "first_sex_chapter": None,
                "first_sex_evidence_ids": [], "notes": "contextual exclusion", "confidence": "explicit",
            }]
            path.write_text(json.dumps(graph), encoding="utf-8")
            covered = subprocess.run([sys.executable, str(SCRIPTS / "validate_graph.py"), "--graph", str(path)], capture_output=True, text=True, encoding="utf-8")
            self.assertNotIn("missing_romance_route_candidate", covered.stdout)


if __name__ == "__main__":
    unittest.main()
