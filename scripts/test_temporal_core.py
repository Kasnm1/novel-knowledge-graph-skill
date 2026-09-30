"""Regression tests for the single as-of implementation (nkg.temporal.asof)."""
from __future__ import annotations

import copy
import unittest

import snapshot
from nkg.core.runtime import GraphRuntime
from nkg.temporal.asof import filter_graph, relation_active
from nkg.views.snapshot_diff import diff_snapshots


def graph() -> dict:
    ev = [{"id": f"e{c}", "chapter": c, "quote": f"chapter {c} evidence text long enough"} for c in range(1, 11)]
    return {
        "metadata": {"title": "t", "chapter_start": 1, "chapter_end": 10, "analyzed_chapters": list(range(1, 11)),
                     "alias_first_chapter": {"小甲": 3, "hero": {"甲哥": 6}}},
        "entities": [
            {"id": "hero", "type": "character", "name": "甲", "first_chapter": 1, "aliases": ["小甲", "甲哥"],
             "evidence_ids": ["e1"]},
            {"id": "ally", "type": "character", "name": "乙", "first_chapter": 1, "evidence_ids": ["e1"]},
            {"id": "foe", "type": "character", "name": "丙", "first_chapter": 2, "evidence_ids": ["e2"]},
            {"id": "sword", "type": "item", "name": "剑", "first_chapter": 2, "evidence_ids": ["e2"]},
            {"id": "axis_a", "type": "level_axis", "name": "甲轴", "first_chapter": 1, "evidence_ids": ["e1"]},
            {"id": "axis_b", "type": "level_axis", "name": "乙轴", "first_chapter": 1, "evidence_ids": ["e1"]},
        ],
        "events": [
            {"id": "ev2", "type": "battle", "chapter": 2, "title": "t", "description": "d",
             "participant_ids": ["hero", "foe"], "evidence_ids": ["e2"]},
            {"id": "ev_untimed", "type": "battle", "title": "t", "description": "d",
             "participant_ids": ["hero"], "evidence_ids": []},
        ],
        "relations": [
            {"id": "r1", "source_id": "hero", "target_id": "foe", "relation_type": "enemy_of", "valid_from": 2,
             "valid_to": 5, "status": "ended", "evidence_ids": ["e2"]},
        ],
        "state_changes": [
            {"id": "s1", "entity_id": "hero", "facet": "level", "target_id": "axis_a", "chapter": 2,
             "after": {"value": 1, "label": "A1"}, "evidence_ids": ["e2"]},
            {"id": "s2", "entity_id": "hero", "facet": "level", "target_id": "axis_b", "chapter": 3,
             "after": {"value": 1, "label": "B1"}, "evidence_ids": ["e3"]},
        ],
        "item_roles": [{"id": "ir", "item_id": "sword", "entity_id": "hero", "role": "holder", "valid_from": 2,
                        "action": "gained", "evidence_ids": ["e2"], "confidence": "explicit"}],
        "romance_routes": [
            {"id": "rr1", "protagonist_id": "hero", "character_id": "ally", "status": "spouse",
             "first_meeting_chapter": 1, "ambiguity_started_chapter": 3, "confirmed_chapter": 6,
             "first_sex_chapter": None, "ambiguity_evidence_ids": ["e3"], "confirmed_evidence_ids": ["e6"]},
            {"id": "rr2", "protagonist_id": "hero", "character_id": "foe", "status": "excluded_nonromantic",
             "first_meeting_chapter": 2, "ambiguity_started_chapter": 7, "ambiguity_evidence_ids": ["e7"]},
        ],
        "evidence": ev,
        "foreshadowing": [], "review_issues": [], "commitments": [], "chapter_summaries": [],
        "intimate_acts": [], "character_traits": [], "level_conversions": [], "story_arcs": [],
    }


class TemporalCoreTests(unittest.TestCase):
    def test_final_romance_status_survives_full_range_and_is_not_announced_early(self):
        routes = lambda n: {r["id"]: r["status"] for r in filter_graph(graph(), n)["romance_routes"]}
        self.assertEqual(routes(10)["rr1"], "spouse")
        self.assertEqual(routes(7)["rr1"], "confirmed_relationship")
        self.assertEqual(routes(4)["rr1"], "ambiguous")

    def test_romance_classification_holds_from_first_chapter(self):
        routes = {r["id"]: r["status"] for r in filter_graph(graph(), 2)["romance_routes"]}
        self.assertEqual(routes["rr2"], "excluded_nonromantic")

    def test_both_alias_map_shapes_are_read(self):
        hero = lambda n: next(e for e in filter_graph(graph(), n)["entities"] if e["id"] == "hero")
        self.assertEqual(hero(2)["aliases"], [])
        self.assertEqual(hero(4)["aliases"], ["小甲"])      # flat map
        self.assertEqual(hero(7)["aliases"], ["小甲", "甲哥"])  # nested map

    def test_strict_mode_drops_untimed_story_records_and_reports_them(self):
        strict = filter_graph(graph(), 10, strict=True)
        self.assertNotIn("ev_untimed", {e["id"] for e in strict["events"]})
        self.assertIn("events:untimed:1", strict["metadata"]["temporal_provenance_gaps"])
        compat = filter_graph(graph(), 10, strict=False)
        self.assertIn("ev_untimed", {e["id"] for e in compat["events"]})

    def test_relation_interval_is_inclusive_and_shared_by_snapshot(self):
        rel = graph()["relations"][0]
        self.assertTrue(relation_active(rel, 5))
        self.assertFalse(relation_active(rel, 6))
        self.assertFalse(relation_active(rel, 1))
        self.assertEqual(len(snapshot.active_relations(graph(), "hero", 5)), 1)
        self.assertEqual(snapshot.active_relations(graph(), "hero", 6), [])

    def test_runtime_state_keeps_each_level_axis(self):
        state = GraphRuntime(graph()).state_at("hero", 5)
        self.assertEqual(state["level@axis_a"]["value"], {"value": 1, "label": "A1"})
        self.assertEqual(state["level@axis_b"]["value"], {"value": 1, "label": "B1"})

    def test_diff_uses_the_requested_cut_not_the_last_analysed_chapter(self):
        g = graph()
        g["metadata"]["analyzed_chapters"] = [1, 2, 3, 4, 8, 9, 10]
        diff = diff_snapshots(filter_graph(g, 3), filter_graph(g, 6))
        self.assertEqual((diff["from_chapter"], diff["to_chapter"]), (3, 6))

    def test_indexed_build_snapshot_matches_per_entity_derivation(self):
        g = graph()
        built = snapshot.build_snapshot(g, 6)["dynamic_state"]
        for entity in g["entities"]:
            self.assertEqual(built[entity["id"]], snapshot.dynamic_state_for_entity(g, entity["id"], 6), entity["id"])

    def test_relation_stance_replays_by_chapter(self):
        g = graph()
        g["relations"].append({"id": "r2", "source_id": "hero", "target_id": "ally", "relation_type": "sworn_sibling_of",
                               "valid_from": 1, "status": "active", "stance": "warm", "evidence_ids": ["e1"],
                               "observations": [{"chapter": 6, "stance": "contempt", "description": "反目",
                                                 "evidence_ids": ["e6"]}]})
        stance = lambda n: next(r for r in filter_graph(g, n)["relations"] if r["id"] == "r2")["stance"]
        self.assertEqual(stance(3), "warm")
        self.assertEqual(stance(7), "contempt")

    def test_canonical_graph_is_not_mutated(self):
        g = graph()
        before = copy.deepcopy(g)
        filter_graph(g, 4)
        snapshot.build_snapshot(g, 4)
        self.assertEqual(g, before)


if __name__ == "__main__":
    unittest.main()
