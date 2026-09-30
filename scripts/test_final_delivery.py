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

from testing_fixtures import FUTURE, fixture_graph  # noqa: E402,F401


class FinalDeliveryTests(unittest.TestCase):
    def test_asof_snapshot_closes_future_state_and_text(self):
        snap=derive_asof_views(fixture_graph(),5)
        self.assertNotIn(FUTURE,json.dumps(snap,ensure_ascii=False))
        hero=next(e for e in snap["graph"]["entities"] if e["id"]=="hero")
        self.assertEqual(hero["name"],"早期名"); self.assertNotIn("summary",hero); self.assertNotIn("future_rank",hero.get("attributes",{}))
        cm=snap["views"]["commitments"][0]; self.assertEqual(cm["status"],"active"); self.assertIsNone(cm.get("resolved_chapter"))
        self.assertEqual(snap["views"]["resources"]["items"][0]["current_quantities"]["hero"],1)
        self.assertEqual(snap["views"]["skills"][0]["holders"],[])
        self.assertEqual(snap["views"]["narrative"]["character_voice"],[])

    def test_strict_graph_output_contains_no_future_marker(self):
        self.assertNotIn(FUTURE,json.dumps(filter_graph(fixture_graph(),5,strict=True),ensure_ascii=False))

    def test_candidate_receipt_reports_missing_and_cutoff(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td); ch1=root/"ch1.txt"; ch1.write_text("他承诺一定会回来。",encoding="utf-8"); ch9=root/"ch9.txt"; ch9.write_text(FUTURE+" 他发誓。",encoding="utf-8")
            index=root/"chapters.jsonl"; index.write_text("\n".join([json.dumps({"chapter":1,"text_path":str(ch1)},ensure_ascii=False),json.dumps({"chapter":2,"text_path":str(root/'missing.txt')},ensure_ascii=False),json.dumps({"chapter":9,"text_path":str(ch9)},ensure_ascii=False)]),encoding="utf-8")
            result=build_output(fixture_graph(),chapters_jsonl=index,cutoff=5,max_hits=1); audit=result["audit"]["text_scan"]
            self.assertEqual(audit["cutoff"],5); self.assertEqual(audit["actual_read_chapters"],1); self.assertEqual(len(audit["missing_or_unreadable"]),1); self.assertFalse(result["audit"]["complete"])
            self.assertNotIn(FUTURE,json.dumps(result,ensure_ascii=False)); self.assertIn("total_hits",audit["per_kind"]["commitment"]); self.assertIn("truncated",audit["per_kind"]["commitment"])
            self.assertEqual(result["audit"]["review_progress"]["total"],len(result["candidates"]))

    def test_candidate_progress_is_carried_forward(self):
        base=build_output(fixture_graph()); self.assertTrue(base["candidates"]); base["candidates"][0]["status"]="confirmed"; base["candidates"][0]["review_note"]="checked"
        later=build_output(fixture_graph(),previous=base); self.assertEqual(later["candidates"][0]["status"],"confirmed"); self.assertEqual(later["candidates"][0]["review_note"],"checked")

    def test_overlapping_evidence_highlight_preserves_both_ids(self):
        rendered=highlight("abcdef",[{"id":"a","quote":"abcd"},{"id":"b","quote":"bcde"}])
        self.assertIn('data-eids="a b"',rendered); self.assertIn(">bcd</mark>",rendered)

    def test_gc_plan_deduplicates_parent_child_and_restores(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td); parent=root/"run"/"_archive"; parent.mkdir(parents=True); child=parent/"nested.tmp"; child.write_text("payload",encoding="utf-8"); archive=root/"_gc_archive"/"case"
            plan=build_plan(root,archive); sources=[op["source"] for op in plan["operations"]]; self.assertIn("run/_archive",sources); self.assertNotIn("run/_archive/nested.tmp",sources)
            applied=apply_plan(root,archive,plan); self.assertEqual(applied["status"],"applied"); self.assertFalse(parent.exists()); verify_for_purge(root,archive)
            restored=restore(root,archive); self.assertEqual(restored["status"],"restored"); self.assertTrue(child.exists())

    def test_gc_apply_failure_rolls_back_prior_moves(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td); good=root/"a.tmp"; good.write_text("good",encoding="utf-8"); archive=root/"_gc_archive"/"failcase"
            # Build a real current-schema plan so the first move has a valid
            # fingerprint, then append a source that disappears before apply.
            plan=build_plan(root,archive)
            plan["operations"].append({"source":"missing.tmp","destination":"_gc_archive/failcase/missing.tmp","fingerprint":{"path":"missing.tmp","kind":"file","size":0,"sha256":"e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"},"status":"planned"})
            with self.assertRaises(FileNotFoundError): apply_plan(root,archive,plan)
            self.assertTrue(good.exists()); self.assertEqual(load_manifest(archive,root)["status"],"rolled_back")


if __name__=="__main__": unittest.main()
