"""Tests for cross-chapter reconciliation and the editorial layer."""
from __future__ import annotations

import copy
import unittest

from apply_corrections import apply_corrections
from nkg.workflow.editorial import editorial_outputs, validate_editorial
from nkg.workflow.reconcile import decisions_to_corrections, reconcile_candidates


def graph() -> dict:
    return {
        "metadata": {"analyzed_chapters": list(range(1, 21))},
        "entities": [
            {"id": "char_hero", "type": "character", "name": "秦朝", "first_chapter": 1},
            {"id": "char_mentor", "type": "character", "name": "罗德", "first_chapter": 1},
            {"id": "char_mentor2", "type": "character", "name": "魔神", "aliases": ["罗德"], "first_chapter": 3},
            {"id": "char_su", "type": "character", "name": "苏姬", "first_chapter": 1},
            {"id": "item_sword", "type": "item", "name": "邪王剑", "first_chapter": 2},
            {"id": "loc_town", "type": "location", "name": "苏南", "first_chapter": 1},
        ],
        "events": [
            {"id": "e5", "chapter": 5, "title": "罗德复仇道士", "description": "罗德终于向臭道士复仇",
             "participant_ids": ["char_mentor", "char_hero"]},
            {"id": "e9", "chapter": 9, "title": "罗德陨落", "participant_ids": ["char_mentor"]},
        ],
        "state_changes": [
            {"id": "s9", "entity_id": "char_mentor", "facet": "health", "chapter": 9,
             "after": {"value": None, "label": "陨落"}},
        ],
        "relations": [
            {"id": "r1", "source_id": "char_mentor", "target_id": "char_hero", "relation_type": "teacher_of",
             "valid_from": 1, "status": "active"},
        ],
        "foreshadowing": [{"id": "fs1", "label": "罗德向臭道士复仇", "observation": "罗德誓要复仇臭道士",
                           "planted_chapter": 1, "related_entity_ids": ["char_mentor"], "status": "open"}],
        "commitments": [],
        "romance_routes": [{"id": "rr", "protagonist_id": "char_hero", "character_id": "char_su",
                            "status": "confirmed_relationship", "confirmed_chapter": None}],
        "intimate_acts": [],
        "evidence": [{"id": "ev1", "chapter": 1, "quote": "x"}, {"id": "ev5", "chapter": 5, "quote": "y"}],
        "chapter_summaries": [{"id": "cs1", "chapter": 1, "summary": "s"}, {"id": "cs5", "chapter": 5, "summary": "s"}],
    }


class ReconcileTests(unittest.TestCase):
    def test_candidates_cover_every_kind(self):
        kinds = {c["kind"] for c in reconcile_candidates(graph())}
        self.assertEqual(kinds, {"foreshadow_payoff", "relation_close", "romance_milestone", "duplicate_entity",
                                 "categorize", "hierarchy"})

    def test_revived_character_does_not_close_relations(self):
        g = graph()
        g["events"].append({"id": "e15", "chapter": 15, "title": "罗德归来", "participant_ids": ["char_mentor"]})
        self.assertNotIn("relation_close", {c["kind"] for c in reconcile_candidates(g)})

    def test_decisions_become_guarded_corrections_that_replay(self):
        g = graph()
        candidates = reconcile_candidates(g)
        payoff = next(c for c in candidates if c["kind"] == "foreshadow_payoff")
        close = next(c for c in candidates if c["kind"] == "relation_close")
        dup = next(c for c in candidates if c["kind"] == "duplicate_entity")
        decisions = [
            {"candidate_id": payoff["id"], "decision": "apply", "reason": "第5章复仇", "evidence_ids": ["ev5"],
             "set": {"payoff_chapter": 5, "payoff_event_id": "e5", "status": "resolved"}},
            {"candidate_id": close["id"], "decision": "apply", "set": {"valid_to": 9, "close_reason": "death"}},
            {"candidate_id": dup["id"], "decision": "apply", "keep": "char_mentor", "merge": "char_mentor2"},
        ]
        result = decisions_to_corrections(g, candidates, decisions, reviewer="test")
        self.assertEqual(result["id_map"], ["char_mentor2=char_mentor"])
        self.assertEqual(len(result["corrections"]), 5)
        fixed, report = apply_corrections(copy.deepcopy(g), result["corrections"])
        self.assertTrue(report["success"])
        self.assertEqual(fixed["foreshadowing"][0]["payoff_chapter"], 5)
        self.assertEqual(fixed["relations"][0]["valid_to"], 9)


class EditorialTests(unittest.TestCase):
    def editorial(self):
        return {
            "arcs": [{"id": "arc_1", "title": "开局", "chapter_start": 1, "chapter_end": 10, "status": "resolved",
                      "phase": "setup", "event_ids": ["e5"], "entity_ids": ["char_hero"], "evidence_ids": ["ev1"]}],
            "chapter_arcs": {"1": ["arc_1"], "5": ["arc_1"]},
            "profiles": {"char_hero": {"tier": "protagonist",
                                       "headlines": [{"text": "落魄保安", "valid_from": 1, "evidence_ids": ["ev1"]}],
                                       "arc_bios": {"arc_1": "从失业青年到魔神宿主。"}}},
            "arc_recaps": {"arc_1": {"text": "……", "key_event_ids": ["e5"]}},
        }

    def test_valid_editorial_splits_into_fragment_and_hints(self):
        self.assertEqual(validate_editorial(self.editorial(), graph()), [])
        frag, hints = editorial_outputs(self.editorial(), graph(), fragment="fragment-09", marker="f09")
        self.assertTrue(frag["metadata"]["supplementary"])
        self.assertEqual(frag["story_arcs"][0]["parent_arc_id"], None)
        self.assertEqual(frag["chapter_summaries"], [{"id": "cs1", "chapter": 1, "arc_ids": ["arc_1"]},
                                                     {"id": "cs5", "chapter": 5, "arc_ids": ["arc_1"]}])
        self.assertEqual(hints["profiles"]["char_hero"]["tier"], "protagonist")

    def test_invalid_editorial_is_rejected(self):
        bad = self.editorial()
        bad["arcs"][0]["parent_arc_id"] = "arc_missing"
        bad["profiles"]["char_hero"]["tier"] = "hero"
        bad["profiles"]["char_hero"]["headlines"][0]["evidence_ids"] = []
        errors = validate_editorial(bad, graph())
        self.assertEqual(len(errors), 3)


if __name__ == "__main__":
    unittest.main()
