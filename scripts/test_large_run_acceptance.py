from __future__ import annotations

import time
import tracemalloc
import unittest

from derive_asof_views import derive_asof_views


class LargeRunAcceptanceTests(unittest.TestCase):
    def make_graph(self) -> dict:
        people = [
            {"id": f"c{i:03d}", "type": "character", "name": f"角色{i:03d}", "first_chapter": 1, "evidence_ids": []}
            for i in range(450)
        ]
        people[0]["tags"] = ["protagonist"]
        locations = [
            {"id": f"l{i:02d}", "type": "location", "name": f"地点{i:02d}", "first_chapter": 1, "evidence_ids": []}
            for i in range(40)
        ]
        events = []
        for chapter in range(1, 1201):
            for offset in range(2):
                left = (chapter * 3 + offset) % 450
                right = (left + 17 + offset) % 450
                events.append({
                    "id": f"ev{chapter:04d}_{offset}", "type": "encounter", "chapter": chapter,
                    "title": f"事件{chapter}-{offset}", "description": "fixture",
                    "participant_ids": [f"c{left:03d}", f"c{right:03d}"],
                    "location_id": f"l{chapter % 40:02d}", "evidence_ids": [],
                })
        relations = []
        for i in range(449):
            relations.append({
                "id": f"rel{i:03d}", "source_id": f"c{i:03d}", "target_id": f"c{i+1:03d}",
                "relation_type": "acquaintance_of", "valid_from": 1, "status": "active", "evidence_ids": [],
            })
        for i in range(40):
            relations.append({
                "id": f"locrel{i:02d}", "source_id": f"l{i:02d}", "target_id": f"l{(i+1)%40:02d}",
                "relation_type": "part_of", "valid_from": 1, "status": "active", "evidence_ids": [],
            })
        state_changes = []
        for chapter in range(10, 1201, 10):
            state_changes.append({
                "id": f"lvl{chapter:04d}", "entity_id": "c000", "facet": "境界", "action": "upgraded",
                "chapter": chapter, "before": chapter // 10 - 1, "after": chapter // 10,
                "reason": "fixture", "evidence_ids": [], "confidence": "explicit",
            })
        return {
            "metadata": {"title": "large-fixture", "chapter_start": 1, "chapter_end": 1200, "analyzed_chapters": list(range(1, 1201)), "protagonist_ids": ["c000"]},
            "entities": people + locations,
            "events": events,
            "relations": relations,
            "state_changes": state_changes,
            "romance_routes": [], "foreshadowing": [], "evidence": [], "review_issues": [], "intimate_acts": [],
            "level_conversions": [], "character_traits": [], "chapter_summaries": [], "item_roles": [], "story_arcs": [],
            "commitments": [], "style_observations": [],
        }

    def test_1200_chapter_450_character_snapshot_budget(self):
        graph = self.make_graph()
        tracemalloc.start()
        started = time.perf_counter()
        snapshot = derive_asof_views(graph, 1000, gap_threshold=4, strict=False)
        elapsed = time.perf_counter() - started
        _, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        self.assertEqual(snapshot["chapter"], 1000)
        self.assertEqual(len(snapshot["graph"]["entities"]), 490)
        self.assertEqual(len(snapshot["graph"]["events"]), 2000)
        # Deliberately generous CI ceilings: catch accidental quadratic explosions,
        # not harmless runner-to-runner variance.
        self.assertLess(elapsed, 20.0, f"large-run derivation took {elapsed:.2f}s")
        self.assertLess(peak, 512 * 1024 * 1024, f"peak memory {peak / 1024 / 1024:.1f} MiB")


if __name__ == "__main__":
    unittest.main()
