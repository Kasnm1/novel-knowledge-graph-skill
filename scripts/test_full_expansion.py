from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from build_expansion_candidates import structural_candidates
from build_expansion_dashboard import build_html
from compare_runs import metrics
from derive_novel_views import build_views
from filter_graph_asof import filter_graph
from gc_run import candidates


class FullExpansionTests(unittest.TestCase):
    def graph(self):
        return {
            "metadata": {"title": "fixture", "chapter_start": 1, "chapter_end": 5,
                         "analyzed_chapters": [1, 2, 3, 4, 5], "protagonist_ids": ["char_h"]},
            "entities": [
                {"id": "char_h", "type": "character", "name": "主角", "first_chapter": 1, "tags": ["protagonist"]},
                {"id": "char_a", "type": "character", "name": "甲", "first_chapter": 1},
                {"id": "char_b", "type": "character", "name": "乙", "first_chapter": 1},
                {"id": "skill_s", "type": "skill", "name": "步法", "first_chapter": 1, "categories": [{"id": "movement"}]},
                {"id": "item_i", "type": "item", "name": "灵石", "first_chapter": 1, "tags": ["rarity/common", "supply/repeatable"]},
                {"id": "loc_l", "type": "location", "name": "城", "first_chapter": 1},
                {"id": "loc_w", "type": "location", "name": "界", "first_chapter": 1},
                {"id": "org_o", "type": "organization", "name": "宗门", "first_chapter": 1},
                {"id": "secret_s", "type": "concept", "name": "秘密", "first_chapter": 1, "categories": [{"id": "secret"}]},
                {"id": "rule_r", "type": "concept", "name": "门规", "first_chapter": 1, "categories": [{"id": "rule"}]},
            ],
            "events": [
                {"id": "ev1", "type": "encounter", "chapter": 1, "title": "相遇", "description": "", "participant_ids": ["char_a", "char_b"], "location_id": "loc_l", "evidence_ids": ["e1"]},
                {"id": "ev2", "type": "encounter", "chapter": 2, "title": "再遇", "description": "", "participant_ids": ["char_a", "char_b"], "location_id": "loc_l", "evidence_ids": ["e2"]},
                {"id": "ev3", "type": "battle", "chapter": 3, "title": "一战", "description": "", "participant_ids": ["char_h", "char_a"], "location_id": "loc_l", "evidence_ids": ["e3"],
                 "combat": {"kind": "duel", "participants": [{"entity_id": "char_h", "side": "A", "outcome": "victory"}, {"entity_id": "char_a", "side": "B", "outcome": "defeat"}], "resolution": "decisive"}},
                {"id": "ev4", "type": "revelation", "chapter": 4, "title": "揭示", "description": "", "participant_ids": ["char_h", "char_b"], "evidence_ids": ["e4"],
                 "information": {"revealer_id": "char_h", "audience_ids": ["char_b"], "secret_ids": ["secret_s"], "mode": "reveal"}},
                {"id": "ev5", "type": "payoff", "chapter": 5, "title": "兑现", "description": "", "participant_ids": ["char_h"], "evidence_ids": ["e5"], "payoff": {"kind": "reversal", "setup_ids": ["fs1"]}},
            ],
            "relations": [
                {"id": "rl1", "source_id": "loc_l", "target_id": "loc_w", "relation_type": "located_in", "valid_from": 1, "status": "active", "evidence_ids": ["e1"]},
                {"id": "rl2", "source_id": "loc_l", "target_id": "org_o", "relation_type": "controlled_by", "valid_from": 1, "status": "active", "evidence_ids": ["e1"]},
                {"id": "rl3", "source_id": "char_h", "target_id": "char_b", "relation_type": "owes_favor_to", "valid_from": 2, "status": "active", "strength": 2, "evidence_ids": ["e2"]},
            ],
            "state_changes": [
                {"id": "sc1", "entity_id": "char_h", "facet": "境界", "action": "upgraded", "chapter": 2, "before": 1, "after": 2, "reason": "", "evidence_ids": ["e2"], "confidence": "explicit"},
                {"id": "sc2", "entity_id": "char_h", "facet": "境界", "action": "upgraded", "chapter": 5, "before": 2, "after": 9, "reason": "", "evidence_ids": ["e5"], "confidence": "explicit"},
                {"id": "sc3", "entity_id": "char_b", "facet": "knowledge", "action": "gained", "chapter": 4, "target_id": "secret_s", "before": False, "after": True, "reason": "", "evidence_ids": ["e4"], "confidence": "explicit"},
            ],
            "foreshadowing": [{"id": "fs1", "label": "伏笔", "status": "resolved", "planted_chapter": 1, "payoff_chapter": 5, "observation": "", "interpretation": "", "related_entity_ids": ["char_h"], "evidence_ids": ["e1"], "confidence": "explicit"}],
            "evidence": [{"id": f"e{i}", "chapter": i, "quote": "abcdefghijklmnop", "source_line_start": 1, "source_line_end": 1} for i in range(1, 6)],
            "review_issues": [],
            "item_roles": [{"id": "ir1", "item_id": "item_i", "entity_id": "char_h", "role": "holder", "valid_from": 3, "action": "gained", "cause_event_id": "ev3", "evidence_ids": ["e3"], "confidence": "explicit"}],
            "chapter_summaries": [{"id": f"cs{i}", "chapter": i, "summary": "x", "evidence_ids": [f"e{i}"], "scene_count": 1, "cliffhanger_type": "none", "pov_entity_ids": ["char_h"], "story_time": f"第{i}日"} for i in range(1, 6)],
            "commitments": [{"id": "cm1", "kind": "promise", "promisor_ids": ["char_h"], "counterparty_ids": ["char_b"], "terms": "会回来", "created_chapter": 1, "deadline_chapter": None, "deadline_story_time": None, "stake_ids": [], "status": "fulfilled", "resolved_chapter": 5, "resolution": "完成", "observations": [{"chapter": 5, "status": "fulfilled", "evidence_ids": ["e5"]}], "evidence_ids": ["e1"], "confidence": "explicit"}],
            "romance_routes": [], "intimate_acts": [], "level_conversions": [], "character_traits": [], "story_arcs": [],
        }

    def test_full_views_present(self):
        views = build_views(self.graph(), gap_threshold=2)
        for key in ("achievements", "combat_records", "resources", "world", "cooccurrence", "relation_timeline", "commitments", "favor_ledger", "knowledge", "foreshadowing", "levels", "chapter_rhythm", "romance", "snapshot_changes", "mortality", "inheritance", "economy", "rules", "payoffs", "narrative"):
            self.assertIn(key, views)
        self.assertEqual(views["combat_records"][0]["protagonist_level"]["境界"], 2)
        self.assertEqual(views["foreshadowing"]["rows"][0]["span"], 4)
        self.assertTrue(views["knowledge"]["propagation"])
        self.assertTrue(views["favor_ledger"])
        self.assertTrue(views["cooccurrence"]["relation_gap_candidates"])

    def test_spoiler_filter_removes_future(self):
        filtered = filter_graph(self.graph(), 3)
        self.assertTrue(all(e["chapter"] <= 3 for e in filtered["events"]))
        self.assertIsNone(filtered["commitments"][0]["resolved_chapter"])
        self.assertEqual(filtered["commitments"][0]["status"], "active")
        self.assertIsNone(filtered["foreshadowing"][0]["payoff_chapter"])

    def test_candidates_do_not_create_facts(self):
        rows = structural_candidates(self.graph(), relation_gap_threshold=2)
        kinds = {r["candidate_kind"] for r in rows}
        self.assertIn("side_relation", kinds)
        self.assertTrue(all(r["status"] == "unresolved" for r in rows))

    def test_dashboard_contains_all_major_views(self):
        text = build_html(build_views(self.graph(), gap_threshold=2))
        for marker in ("世界地图", "伏笔甘特带", "知情不对称", "感情线里程碑", "死亡 / 复活", "恩怨账本", "章节节奏心电图"):
            self.assertIn(marker, text)

    def test_compare_metrics_and_gc_dry_candidates(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            graph_path = root / "run" / "graph.json"; graph_path.parent.mkdir(); graph_path.write_text(json.dumps(self.graph(), ensure_ascii=False), encoding="utf-8")
            m = metrics(graph_path)
            self.assertEqual(m["chapters"], 5)
            junk = root / "run" / "__pycache__"; junk.mkdir(); (junk / "a.pyc").write_bytes(b"x")
            self.assertIn(junk, candidates(root))


if __name__ == "__main__":
    unittest.main()
