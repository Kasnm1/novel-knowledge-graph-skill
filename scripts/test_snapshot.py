"""Focused regression tests for the chapter snapshot derivation kernel."""

from __future__ import annotations

import copy
import json
import unittest

from snapshot import (
    active_relations,
    build_snapshot,
    dynamic_state_for_entity,
    levels_at,
    ownership_at,
    state_at,
    state_changes_at,
)


class SnapshotTests(unittest.TestCase):
    """Exercise temporal replay without depending on a particular novel run."""

    def setUp(self) -> None:
        """Create a compact graph containing modern and legacy-compatible data."""

        self.graph = {
            "metadata": {"title": "Test"},
            "entities": [
                {
                    "id": "char_a",
                    "type": "character",
                    "name": "A",
                    "aliases": ["Future alias"],
                    "summary": "Complete future-aware summary",
                    "attributes": {"secret": "future revelation"},
                    "current_state": {"legacy_only": "kept"},
                },
                {"id": "char_b", "type": "character", "name": "B"},
                {"id": "char_c", "type": "character", "name": "C"},
                {"id": "item_ring", "type": "item", "name": "Ring"},
                {"id": "item_key", "type": "item", "name": "Key"},
                {"id": "axis_power", "type": "level_axis", "name": "Power"},
            ],
            "relations": [
                {"id": "rel_old", "source_id": "char_a", "target_id": "char_b", "relation_type": "friend_of", "valid_from": 1, "valid_to": 3},
                {"id": "rel_new", "source_id": "char_a", "target_id": "char_c", "relation_type": "rival_of", "valid_from": 4},
                {"id": "rel_owner", "source_id": "char_a", "target_id": "item_ring", "relation_type": "owns", "valid_from": 1},
                {"id": "rel_legacy", "source_id": "char_a", "target_id": "item_key", "relation_type": "uses"},
            ],
            "state_changes": [
                {"id": "sc_health_1", "entity_id": "char_a", "facet": "health", "action": "changed", "chapter": 1, "before": None, "after": "well"},
                {"id": "sc_health_2", "entity_id": "char_a", "facet": "health", "action": "damaged", "chapter": 2, "end_chapter": 3, "before": "well", "after": "hurt"},
                {"id": "sc_level_a", "entity_id": "char_a", "target_id": "axis_power", "facet": "level", "action": "gained", "chapter": 2, "before": None, "after": {"value": 1, "label": "one"}},
                {"id": "sc_level_b", "entity_id": "char_a", "target_id": "axis_power", "facet": "level", "action": "upgraded", "chapter": 4, "before": {"value": 1}, "after": {"value": 2, "label": "two"}},
                {"id": "sc_level_z", "entity_id": "char_a", "target_id": "axis_power", "facet": "level", "action": "upgraded", "chapter": 4, "before": {"value": 2}, "after": {"value": 3, "label": "three"}},
                {"id": "sc_pos_gain", "entity_id": "char_a", "target_id": "item_ring", "facet": "possession", "action": "gained", "chapter": 2, "before": None, "after": {"holder_id": "char_a"}},
                {"id": "sc_pos_transfer", "entity_id": "char_a", "target_id": "item_ring", "facet": "possession", "action": "transferred", "chapter": 4, "before": {"holder_id": "char_a"}, "after": {"holder_id": "char_b"}},
                {"id": "sc_pos_loss", "entity_id": "char_b", "target_id": "item_ring", "facet": "possession", "action": "lost", "chapter": 6, "before": {"holder_id": "char_b"}, "after": None},
            ],
            "item_roles": [
                {"id": "ir_user", "item_id": "item_ring", "entity_id": "char_c", "role": "user", "valid_from": 5},
            ],
            "evidence": [{"id": "ev_future", "chapter": 99, "quote": "future proof"}],
            "foreshadowing": [{"id": "fs_1", "planted_chapter": 2, "status": "resolved", "payoff_chapter": 99, "resolution": "future payoff"}],
        }

    def test_relation_validity_is_inclusive_and_legacy_start_is_supported(self) -> None:
        """Relations start and end on their named chapters."""

        self.assertEqual([r["id"] for r in active_relations(self.graph, "char_a", 3)], ["rel_legacy", "rel_old", "rel_owner"])
        self.assertEqual([r["id"] for r in active_relations(self.graph, "char_a", 4)], ["rel_legacy", "rel_owner", "rel_new"])

    def test_state_replay_uses_end_chapter_and_legacy_fallback(self) -> None:
        """Temporary effects expire and expose the prior active value again."""

        self.assertEqual(state_at(self.graph, "char_a", "health", 3), "hurt")
        self.assertEqual(state_at(self.graph, "char_a", "health", 4), "well")
        self.assertEqual(state_at(self.graph, "char_a", "legacy_only", 1), "kept")
        embedded = {"id": "x", "current_state": {"mood": "calm"}}
        self.assertEqual(state_at(embedded, "mood", 10), "calm")

    def test_active_state_change_records_exclude_future_and_expired_rows(self) -> None:
        """Consumers receive only records that are active at the snapshot."""

        at_four = [row["id"] for row in state_changes_at(self.graph, 4)]
        self.assertNotIn("sc_health_2", at_four)
        self.assertNotIn("sc_pos_loss", at_four)
        self.assertIn("sc_level_z", at_four)

    def test_possession_gain_transfer_loss_and_explicit_roles(self) -> None:
        """Possession changes override stale open relations and merge item roles."""

        at_two = {(row["entity_id"], row["role"]) for row in ownership_at(self.graph, "item_ring", 2)}
        self.assertEqual(at_two, {("char_a", "owner"), ("char_a", "holder")})
        at_five = {(row["entity_id"], row["role"]) for row in ownership_at(self.graph, "item_ring", 5)}
        self.assertEqual(at_five, {("char_b", "holder"), ("char_c", "user")})
        at_six = {(row["entity_id"], row["role"]) for row in ownership_at(self.graph, "item_ring", 6)}
        self.assertEqual(at_six, {("char_c", "user")})

    def test_levels_are_axis_mapped_and_stably_sorted(self) -> None:
        """Same-chapter changes resolve by record ID after chapter ordering."""

        self.assertEqual(levels_at(self.graph, "char_a", 2)["axis_power"]["value"], 1)
        self.assertEqual(levels_at(self.graph, "char_a", 4)["axis_power"]["value"], 3)

    def test_snapshot_keeps_future_static_material_and_input_unchanged(self) -> None:
        """Snapshotting derives state but never becomes a spoiler filter or mutation."""

        original = copy.deepcopy(self.graph)
        snapshot = build_snapshot(self.graph, 1)
        entity = next(item for item in snapshot["entities"] if item["id"] == "char_a")
        self.assertEqual(entity["summary"], "Complete future-aware summary")
        self.assertEqual(entity["aliases"], ["Future alias"])
        self.assertEqual(entity["attributes"]["secret"], "future revelation")
        self.assertEqual(snapshot["evidence"][0]["chapter"], 99)
        self.assertEqual(snapshot["foreshadowing"][0]["payoff_chapter"], 99)
        self.assertEqual(snapshot["dynamic_state"]["char_a"]["facets"]["health"], "well")
        self.assertEqual(snapshot["snapshot_chapter"], 1)
        self.assertEqual(self.graph, original)
        json.dumps(snapshot)

    def test_dynamic_state_has_documented_sections(self) -> None:
        """The aggregate view exposes facets, relations, item roles, and levels."""

        dynamic = dynamic_state_for_entity(self.graph, "char_b", 5)
        self.assertEqual(set(dynamic), {"entity_id", "chapter", "facets", "relations", "item_roles", "levels", "story_arcs"})
        self.assertEqual(dynamic["item_roles"][0]["item_id"], "item_ring")


if __name__ == "__main__":
    unittest.main()
