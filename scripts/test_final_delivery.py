from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from build_expansion_candidates import build_output
from build_reader_overlay import highlight
from derive_asof_views import derive_asof_views
from filter_graph_asof import filter_graph
from gc_run import apply_plan, build_plan, load_manifest, restore, verify_for_purge


FUTURE = "FUTURE_MARKER_777"


def fixture_graph() -> dict:
    evidence = [
        {"id": f"e{i}", "chapter": i, "quote": f"chapter {i} evidence text long enough", "source_line_start": 1, "source_line_end": 1}
        for i in range(1, 10)
    ]
    return {
        "metadata": {
            "title": "final-delivery-fixture",
            "chapter_start": 1,
            "chapter_end": 9,
            "analyzed_chapters": list(range(1, 10)),
            "protagonist_ids": ["hero"],
            "alias_first_chapter": {"hero": {FUTURE: 8}},
            "summary_first_chapter": {"hero": 8},
            "attribute_first_chapter": {"hero": {"future_rank": 8}},
        },
        "entities": [
            {
                "id": "hero", "type": "character", "name": "最终正式名", "name_first_chapter": 8,
                "name_history": [{"valid_from": 1, "valid_to": 7, "name": "早期名"}, {"valid_from": 8, "name": "最终正式名"}],
                "aliases": [FUTURE], "first_chapter": 1, "summary": FUTURE,
                "attributes": {"future_rank": FUTURE},
                "attribute_history": [{"id": "ah1", "chapter": 2, "key": "realm", "value": "early"}],
                "tags": ["protagonist"], "evidence_ids": ["e1"],
            },
            {"id": "ally", "type": "character", "name": "同伴", "first_chapter": 1, "evidence_ids": ["e1"]},
            {"id": "skill", "type": "skill", "name": "身法", "first_chapter": 1, "categories": [{"id": "movement"}], "evidence_ids": ["e1"]},
            {"id": "item", "type": "item", "name": "灵石", "first_chapter": 1, "tags": ["rarity/common", "supply/repeatable"], "evidence_ids": ["e1"]},
            {"id": "loc", "type": "location", "name": "城", "first_chapter": 1, "evidence_ids": ["e1"]},
            {"id": "world", "type": "location", "name": "世界", "first_chapter": 1, "evidence_ids": ["e1"]},
        ],
        "events": [
            {"id": "ev2", "type": "encounter", "chapter": 2, "title": "早期事件", "description": "早期", "participant_ids": ["hero", "ally"], "location_id": "loc", "evidence_ids": ["e2"]},
            {"id": "ev8", "type": "payoff", "chapter": 8, "title": FUTURE, "description": FUTURE, "participant_ids": ["hero"], "evidence_ids": ["e8"], "payoff": {"kind": "reversal", "setup_ids": []}},
        ],
        "relations": [
            {"id": "rel_loc", "source_id": "loc", "target_id": "world", "relation_type": "located_in", "valid_from": 1, "status": "active", "evidence_ids": ["e1"]},
            {"id": "rel_skill", "source_id": "hero", "target_id": "skill", "relation_type": "uses", "valid_from": 8, "status": "active", "evidence_ids": ["e8"]},
        ],
        "state_changes": [
            {"id": "q2", "entity_id": "hero", "target_id": "item", "facet": "inventory_quantity", "action": "gained", "chapter": 2, "before": 0, "after": 1, "reason": "获得", "evidence_ids": ["e2"], "confidence": "explicit"},
            {"id": "q8", "entity_id": "hero", "target_id": "item", "facet": "inventory_quantity", "action": "gained", "chapter": 8, "before": 1, "after": 99, "reason": FUTURE, "evidence_ids": ["e8"], "confidence": "explicit"},
        ],
        "item_roles": [
            {"id": "ir2", "item_id": "item", "entity_id": "hero", "role": "holder", "valid_from": 2, "action": "gained", "cause_event_id": "ev2", "evidence_ids": ["e2"], "confidence": "explicit"},
        ],
        "commitments": [
            {"id": "cm", "kind": "promise", "promisor_ids": ["hero"], "counterparty_ids": ["ally"], "terms": "会回来", "created_chapter": 1,
             "deadline_chapter": None, "deadline_story_time": None, "stake_ids": [], "status": "fulfilled", "resolved_chapter": 8, "resolution": FUTURE,
             "observations": [{"chapter": 8, "status": "fulfilled", "evidence_ids": ["e8"]}], "evidence_ids": ["e1"], "confidence": "explicit"}
        ],
        "style_observations": [
            {"id": "voice8", "entity_id": "hero", "chapter": 8, "observation": FUTURE, "evidence_ids": ["e8"]}
        ],
        "chapter_summaries": [
            {"id": "cs2", "chapter": 2, "summary": "early summary", "evidence_ids": ["e2"], "pov_entity_ids": ["hero"], "scene_count": 1, "cliffhanger_type": "none"},
            {"id": "cs8", "chapter": 8, "summary": FUTURE, "evidence_ids": ["e8"], "pov_entity_ids": ["hero"], "scene_count": 1, "cliffhanger_type": "reversal"},
        ],
        "evidence": evidence,
        "romance_routes": [], "intimate_acts": [], "level_conversions": [], "character_traits": [],
        "story_arcs": [], "foreshadowing": [], "review_issues": [],
    }


class FinalDeliveryTests(unittest.TestCase):
    def test_asof_snapshot_closes_future_state_and_text(self):
        snap = derive_asof_views(fixture_graph(), 5)
        dumped = json.dumps(snap, ensure_ascii=False)
        self.assertNotIn(FUTURE, dumped)
        hero = next(e for e in snap["graph"]["entities"] if e["id"] == "hero")
        self.assertEqual(hero["name"], "早期名")
        self.assertNotIn("summary", hero)
        self.assertNotIn("future_rank", hero.get("attributes", {}))
        commitment = snap["views"]["commitments"][0]
        self.assertEqual(commitment["status"], "active")
        self.assertIsNone(commitment.get("resolved_chapter"))
        resource = snap["views"]["resources"]["items"][0]
        self.assertEqual(resource["current_quantities"]["hero"], 1)
        skill = snap["views"]["skills"][0]
        self.assertEqual(skill["holders"], [])
        self.assertEqual(snap["views"]["narrative"]["character_voice"], [])

    def test_strict_graph_output_contains_no_future_marker(self):
        filtered = filter_graph(fixture_graph(), 5, strict=True)
        self.assertNotIn(FUTURE, json.dumps(filtered, ensure_ascii=False))

    def test_candidate_receipt_reports_missing_and_cutoff(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            ch1 = root / "ch1.txt"; ch1.write_text("他承诺一定会回来。", encoding="utf-8")
            ch9 = root / "ch9.txt"; ch9.write_text(FUTURE + " 他发誓。", encoding="utf-8")
            index = root / "chapters.jsonl"
            index.write_text("\n".join([
                json.dumps({"chapter": 1, "text_path": str(ch1)}, ensure_ascii=False),
                json.dumps({"chapter": 2, "text_path": str(root / 'missing.txt')}, ensure_ascii=False),
                json.dumps({"chapter": 9, "text_path": str(ch9)}, ensure_ascii=False),
            ]), encoding="utf-8")
            result = build_output(fixture_graph(), chapters_jsonl=index, cutoff=5, max_hits=1)
            audit = result["audit"]["text_scan"]
            self.assertEqual(audit["cutoff"], 5)
            self.assertEqual(audit["actual_read_chapters"], 1)
            self.assertEqual(len(audit["missing_or_unreadable"]), 1)
            self.assertFalse(result["audit"]["complete"])
            self.assertNotIn(FUTURE, json.dumps(result, ensure_ascii=False))
            self.assertIn("total_hits", audit["per_kind"]["commitment"])
            self.assertIn("truncated", audit["per_kind"]["commitment"])
            self.assertEqual(result["audit"]["review_progress"]["total"], len(result["candidates"]))

    def test_candidate_progress_is_carried_forward(self):
        base = build_output(fixture_graph())
        self.assertTrue(base["candidates"])
        base["candidates"][0]["status"] = "confirmed"
        base["candidates"][0]["review_note"] = "checked"
        later = build_output(fixture_graph(), previous=base)
        self.assertEqual(later["candidates"][0]["status"], "confirmed")
        self.assertEqual(later["candidates"][0]["review_note"], "checked")

    def test_overlapping_evidence_highlight_preserves_both_ids(self):
        rendered = highlight("abcdef", [{"id": "a", "quote": "abcd"}, {"id": "b", "quote": "bcde"}])
        self.assertIn('data-eids="a b"', rendered)
        self.assertIn("abc", rendered)

    def test_gc_plan_deduplicates_parent_child_and_restores(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            parent = root / "run" / "_archive"; parent.mkdir(parents=True)
            child = parent / "nested.tmp"; child.write_text("payload", encoding="utf-8")
            archive = root / "_gc_archive" / "case"
            plan = build_plan(root, archive)
            sources = [op["source"] for op in plan["operations"]]
            self.assertIn("run/_archive", sources)
            self.assertNotIn("run/_archive/nested.tmp", sources)
            applied = apply_plan(root, archive, plan)
            self.assertEqual(applied["status"], "applied")
            self.assertFalse(parent.exists())
            verify_for_purge(root, archive)
            restored = restore(root, archive)
            self.assertEqual(restored["status"], "restored")
            self.assertTrue(child.exists())

    def test_gc_apply_failure_rolls_back_prior_moves(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            good = root / "a.tmp"; good.write_text("good", encoding="utf-8")
            archive = root / "_gc_archive" / "failcase"
            plan = {
                "schema_version": 2, "root": str(root.resolve()), "archive": str(archive.resolve()), "status": "planned",
                "created_at": "fixture", "bytes": 4,
                "operations": [
                    {"source": "a.tmp", "destination": "_gc_archive/failcase/a.tmp", "fingerprint": {"path": "a.tmp", "kind": "file", "size": 4, "sha256": ""}, "status": "planned"},
                    {"source": "missing.tmp", "destination": "_gc_archive/failcase/missing.tmp", "fingerprint": {"path": "missing.tmp", "kind": "file", "size": 0, "sha256": ""}, "status": "planned"},
                ],
            }
            with self.assertRaises(FileNotFoundError):
                apply_plan(root, archive, plan)
            self.assertTrue(good.exists())
            manifest = load_manifest(archive, root)
            self.assertEqual(manifest["status"], "rolled_back")


if __name__ == "__main__":
    unittest.main()
