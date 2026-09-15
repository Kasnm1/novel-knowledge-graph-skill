"""Focused contract tests for derived dashboard collection views."""

from __future__ import annotations

import copy
import json
import unittest

from derive_collection_views import CollectionViewError, derive_collection_views


class CollectionViewsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.graph = {
            "entities": [
                {"id": "hero", "type": "character", "name": "主角", "first_chapter": 1},
                {"id": "friend", "type": "character", "name": "朋友", "first_chapter": 1},
                {"id": "rival", "type": "character", "name": "对手", "first_chapter": 2, "last_chapter": 4},
                {"id": "sword", "type": "item", "name": "剑", "first_chapter": 1},
            ],
            "relations": [
                {"id": "rel_friend", "source_id": "hero", "target_id": "friend", "relation_type": "friend_of", "valid_from": 1, "evidence_ids": ["ev1"]},
                {"id": "rel_enemy", "source_id": "hero", "target_id": "rival", "relation_type": "enemy_of", "valid_from": 2, "valid_to": 4, "evidence_ids": ["ev2"]},
                {"id": "rel_unproven", "source_id": "hero", "target_id": "sword", "relation_type": "owns", "valid_from": 1, "evidence_ids": []},
            ],
            "story_arcs": [
                {"id": "arc_main", "title": "主线", "chapter_start": 1, "chapter_end": 8, "entity_ids": ["hero", "friend"]},
                {"id": "arc_parallel", "title": "并行线", "chapter_start": 3, "chapter_end": 6, "parent_arc_id": "arc_main", "entity_ids": ["hero", "rival"]},
            ],
            "evidence": [{"id": "ev1"}, {"id": "ev2"}],
        }

    def test_set_algebra_refs_relations_arcs_and_membership_reasons(self) -> None:
        views = {
            "collections": [
                {"id": "characters", "label": "人物", "expression": {"type": "character"}, "display": {"order": 2}},
                {"id": "hero_friends", "label": "主角朋友", "expression": {"relation": {"relation_type": "friend_of", "with_id": "hero", "role": "other"}}},
                {"id": "arc_cast", "label": "主线角色", "expression": {"arc": {"id": "arc_main", "include_descendants": True}}},
                {"id": "intersection", "label": "交集", "expression": {"and": [{"collection": "characters"}, {"collection": "arc_cast"}]}},
                {"id": "union", "label": "并集", "expression": {"or": [{"collection": "hero_friends"}, {"explicit_members": ["rival", "friend"]}]}},
                {"id": "not_friends", "label": "非朋友", "expression": {"not": {"collection": "hero_friends"}}},
            ]
        }
        original_graph, original_views = copy.deepcopy(self.graph), copy.deepcopy(views)
        result = derive_collection_views(self.graph, views)
        by_id = {row["id"]: row for row in result["collections"]}
        self.assertEqual([row["entity_id"] for row in by_id["hero_friends"]["members"]], ["friend"])
        self.assertEqual([row["entity_id"] for row in by_id["arc_cast"]["members"]], ["friend", "hero", "rival"])
        self.assertEqual([row["entity_id"] for row in by_id["intersection"]["members"]], ["friend", "hero", "rival"])
        self.assertEqual([row["entity_id"] for row in by_id["union"]["members"]], ["friend", "rival"])
        self.assertEqual([row["entity_id"] for row in by_id["not_friends"]["members"]], ["hero", "rival", "sword"])
        self.assertEqual(result["memberships"]["friend"]["collection_ids"], ["arc_cast", "characters", "hero_friends", "intersection", "union"])
        self.assertTrue(any(reason["operator"] == "relation" for reason in by_id["hero_friends"]["members"][0]["matched_by"]))
        self.assertTrue(any(reason["operator"] == "explicit_members" for reason in by_id["union"]["members"][0]["matched_by"]))
        self.assertEqual(self.graph, original_graph)
        self.assertEqual(views, original_views)
        json.dumps(result, ensure_ascii=False)

    def test_active_at_filters_relation_interval_and_entity_interval(self) -> None:
        views = {
            "collections": [
                {"id": "active_entities", "label": "第5章活跃", "expression": {"active_at": 5}},
                {"id": "active_enemy", "label": "第3章敌人", "expression": {"active_at": {"chapter": 3, "where": {"relation": {"relation_type": "enemy_of", "with_id": "hero", "role": "other"}}}}},
                {"id": "expired_enemy", "label": "第5章敌人", "expression": {"active_at": {"chapter": 5, "expression": {"relation": "enemy_of"}}}},
            ]
        }
        result = derive_collection_views(self.graph, views)
        by_id = {row["id"]: row for row in result["collections"]}
        self.assertEqual([row["entity_id"] for row in by_id["active_entities"]["members"]], ["friend", "hero", "sword"])
        self.assertEqual([row["entity_id"] for row in by_id["active_enemy"]["members"]], ["rival"])
        self.assertEqual(by_id["expired_enemy"]["members"], [])

    def test_rejects_unknown_missing_and_circular_references(self) -> None:
        cases = [
            ({"collections": [{"id": "bad", "label": "坏", "expression": {"mystery": "x"}}]}, "未知"),
            ({"collections": [{"id": "bad", "label": "坏", "expression": {"collection": "missing"}}]}, "不存在"),
            ({"collections": [
                {"id": "a", "label": "甲", "expression": {"collection": "b"}},
                {"id": "b", "label": "乙", "expression": {"collection": "a"}},
            ]}, "循环"),
        ]
        for views, message in cases:
            with self.subTest(message=message):
                with self.assertRaisesRegex(CollectionViewError, message):
                    derive_collection_views(self.graph, views)

    def test_rejects_unknown_entity_references_and_unproven_relation_membership(self) -> None:
        bad_views = {"collections": [{"id": "bad", "label": "坏", "expression": {"explicit_members": ["missing"]}}]}
        with self.assertRaisesRegex(CollectionViewError, "不存在"):
            derive_collection_views(self.graph, bad_views)
        views = {"collections": [{"id": "unproven", "label": "无证据", "expression": {"relation": "owns"}}]}
        result = derive_collection_views(self.graph, views)
        self.assertEqual(result["collections"][0]["members"], [])


if __name__ == "__main__":
    unittest.main()
