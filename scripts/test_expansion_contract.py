from __future__ import annotations

import unittest

from derive_novel_views import build_views
from extension_contracts import validate_graph_extensions


class ExpansionContractTests(unittest.TestCase):
    def fixture(self):
        return {
            "metadata": {
                "title": "fixture", "chapter_start": 1, "chapter_end": 4,
                "analyzed_chapters": [1, 2, 3, 4], "protagonist_ids": ["char_hero"],
            },
            "entities": [
                {"id": "char_hero", "type": "character", "name": "主角"},
                {"id": "char_enemy", "type": "character", "name": "对手"},
                {"id": "skill_step", "type": "skill", "name": "流云步", "categories": [{"id": "movement", "primary": True}]},
                {"id": "item_stone", "type": "item", "name": "灵石", "tags": ["rarity/common", "supply/repeatable"]},
                {"id": "loc_city", "type": "location", "name": "青云城"},
                {"id": "loc_world", "type": "location", "name": "玄界"},
                {"id": "org_sect", "type": "organization", "name": "青云宗"},
                {"id": "secret_birth", "type": "concept", "name": "身世秘密", "categories": [{"id": "secret"}]},
            ],
            "events": [
                {
                    "id": "event_battle", "type": "battle", "chapter": 3, "title": "城门一战",
                    "description": "主角取胜", "participant_ids": ["char_hero", "char_enemy"],
                    "location_id": "loc_city", "evidence_ids": ["ev_battle"],
                    "combat": {
                        "kind": "duel", "resolution": "decisive", "stake_ids": ["item_stone"],
                        "participants": [
                            {"entity_id": "char_hero", "side": "A", "outcome": "victory"},
                            {"entity_id": "char_enemy", "side": "B", "outcome": "defeat"},
                        ],
                    },
                }
            ],
            "relations": [
                {"id": "rel_city_world", "source_id": "loc_city", "target_id": "loc_world", "relation_type": "located_in", "valid_from": 1},
                {"id": "rel_control", "source_id": "loc_city", "target_id": "org_sect", "relation_type": "controlled_by", "valid_from": 1},
            ],
            "state_changes": [
                {"id": "sc_level", "entity_id": "char_hero", "facet": "境界", "action": "upgraded", "chapter": 2, "before": "炼体一重", "after": "炼体二重"},
                {"id": "sc_know", "entity_id": "char_enemy", "facet": "knowledge", "action": "gained", "chapter": 4, "target_id": "secret_birth", "after": True},
            ],
            "foreshadowing": [],
            "evidence": [
                {"id": "ev_battle", "chapter": 3},
                {"id": "ev_item", "chapter": 3},
                {"id": "ev_commit", "chapter": 1},
            ],
            "review_issues": [],
            "item_roles": [
                {"id": "ir_stone", "item_id": "item_stone", "entity_id": "char_hero", "role": "holder", "valid_from": 3, "action": "gained", "cause_event_id": "event_battle", "evidence_ids": ["ev_item"]},
            ],
            "chapter_summaries": [
                {"id": "cs3", "chapter": 3, "summary": "主角在青云城战胜对手。", "evidence_ids": ["ev_battle"], "pov_entity_ids": ["char_hero"], "scene_count": 1, "cliffhanger_type": "none", "story_time": "当日"}
            ],
            "commitments": [
                {
                    "id": "commit_001", "kind": "wager", "promisor_ids": ["char_hero"],
                    "counterparty_ids": ["char_enemy"], "terms": "三章内分胜负", "created_chapter": 1,
                    "deadline_chapter": 3, "deadline_story_time": None, "stake_ids": ["item_stone"],
                    "status": "fulfilled", "resolved_chapter": 3, "resolution": "主角取胜",
                    "observations": [{"chapter": 3, "status": "fulfilled", "evidence_ids": ["ev_battle"]}],
                    "evidence_ids": ["ev_commit"], "confidence": "explicit",
                }
            ],
        }

    def test_extension_contract_valid(self):
        report = validate_graph_extensions(self.fixture())
        self.assertTrue(report["valid"], report["errors"])
        self.assertEqual(report["coverage"]["battle_combat"]["ratio"], 1.0)
        self.assertEqual(report["coverage"]["skill_categories"]["ratio"], 1.0)

    def test_views_use_battle_time_level(self):
        views = build_views(self.fixture())
        self.assertEqual(len(views["combat_records"]), 1)
        self.assertEqual(views["combat_records"][0]["protagonist_level"]["境界"], "炼体二重")
        self.assertTrue(any(row["category"] == "combat" for row in views["achievements"]))
        self.assertTrue(any(row["category"] == "item" for row in views["achievements"]))
        self.assertEqual(views["world"]["map_mode"], "topology")

    def test_invalid_vocab_is_rejected(self):
        graph = self.fixture()
        graph["entities"][2]["categories"] = [{"id": "super_attack"}]
        graph["commitments"][0]["status"] = "done"
        report = validate_graph_extensions(graph)
        codes = {row["code"] for row in report["errors"]}
        self.assertIn("unknown_skill_category", codes)
        self.assertIn("bad_commitment_status", codes)


if __name__ == "__main__":
    unittest.main()
