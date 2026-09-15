from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from build_expansion_artifacts import run_step
from export_ai_bundle import main as export_bundle
from filter_graph_asof import filter_graph
from gc_run import candidates
from merge_graph_expanded import main as merge_expanded


FUTURE = "CODE_AUDIT_FUTURE_991"


def temporal_graph() -> dict:
    return {
        "metadata": {
            "title": "audit",
            "chapter_start": 1,
            "chapter_end": 10,
            "analyzed_chapters": list(range(1, 11)),
            "name_first_chapter": {"hero": 1, "ally": 1},
            "summary_first_chapter": {"hero": 8},
            "attribute_first_chapter": {"hero": {"rank": 8}},
        },
        "entities": [
            {
                "id": "hero",
                "type": "character",
                "name": "Hero",
                "name_history": [{"chapter": 1, "name": "Hero"}],
                "first_chapter": 1,
                "summary": FUTURE,
                "attributes": {"rank": FUTURE},
                "evidence_ids": ["e1"],
            },
            {"id": "ally", "type": "character", "name": "Ally", "name_first_chapter": 1, "first_chapter": 1, "evidence_ids": ["e1"]},
        ],
        "events": [],
        "relations": [
            {
                "id": "r1",
                "source_id": "hero",
                "target_id": "ally",
                "relation_type": "friend_of",
                "valid_from": 1,
                "valid_to": 9,
                "status": "ended",
                "observations": [
                    {"chapter": 1, "status": "active", "evidence_ids": ["e1"]},
                    {"chapter": 9, "status": "ended", "evidence_ids": ["e9"]},
                ],
                "evidence_ids": ["e1", "e9"],
            }
        ],
        "state_changes": [],
        "romance_routes": [
            {
                "id": "rr1",
                "protagonist_id": "hero",
                "character_id": "ally",
                "status": "spouse",
                "inclusion_basis": "romantic_ambiguity",
                "consent_context": "unknown",
                "first_meeting_chapter": 1,
                "first_meeting_evidence_ids": ["e1"],
                "ambiguity_started_chapter": 3,
                "ambiguity_evidence_ids": ["e3"],
                "confirmed_chapter": 8,
                "confirmed_evidence_ids": ["e8"],
                "first_sex_chapter": None,
                "first_sex_evidence_ids": [],
                "notes": "",
                "confidence": "explicit",
            }
        ],
        "intimate_acts": [],
        "level_conversions": [],
        "character_traits": [],
        "chapter_summaries": [],
        "story_arcs": [],
        "item_roles": [],
        "commitments": [
            {
                "id": "c1",
                "kind": "promise",
                "promisor_ids": ["hero"],
                "counterparty_ids": ["ally"],
                "terms": "return",
                "created_chapter": 2,
                "deadline_chapter": None,
                "deadline_story_time": None,
                "stake_ids": [],
                "status": "fulfilled",
                "resolved_chapter": 8,
                "resolution": "done",
                "observations": [{"chapter": 8, "status": "fulfilled", "evidence_ids": ["e8"]}],
                "evidence_ids": ["e2", "e8"],
                "confidence": "explicit",
            }
        ],
        "foreshadowing": [],
        "evidence": [
            {"id": f"e{chapter}", "chapter": chapter, "quote": f"evidence chapter {chapter} text long enough", "source_line_start": 1, "source_line_end": 1}
            for chapter in range(1, 11)
        ],
        "review_issues": [],
    }


class TemporalKernelAuditTests(unittest.TestCase):
    def test_relation_status_comes_from_visible_observation(self):
        snap = filter_graph(temporal_graph(), 5, strict=True)
        relation = snap["relations"][0]
        self.assertEqual(relation["status"], "active")
        self.assertNotIn("valid_to", relation)
        self.assertEqual([row["chapter"] for row in relation["observations"]], [1])
        self.assertNotIn("e9", json.dumps(relation, ensure_ascii=False))

    def test_romance_status_remains_in_canonical_vocabulary(self):
        early = filter_graph(temporal_graph(), 2, strict=True)["romance_routes"][0]
        ambiguous = filter_graph(temporal_graph(), 5, strict=True)["romance_routes"][0]
        confirmed = filter_graph(temporal_graph(), 8, strict=True)["romance_routes"][0]
        self.assertEqual(early["status"], "uncertain")
        self.assertEqual(ambiguous["status"], "ambiguous")
        self.assertEqual(confirmed["status"], "confirmed_relationship")

    def test_strict_snapshot_recursively_removes_future_evidence_refs(self):
        snap = filter_graph(temporal_graph(), 5, strict=True)
        text = json.dumps(snap, ensure_ascii=False)
        self.assertNotIn('"e8"', text)
        self.assertNotIn('"e9"', text)
        self.assertNotIn(FUTURE, text)


class ExportAuditTests(unittest.TestCase):
    def test_ai_bundle_cutoff_is_closed_and_includes_commitments(self):
        graph = temporal_graph()
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            graph_path = root / "graph.json"
            validation_path = root / "validation.json"
            out = root / "bundle"
            graph_path.write_text(json.dumps(graph, ensure_ascii=False), encoding="utf-8")
            validation_path.write_text(json.dumps({"record_counts": {}}), encoding="utf-8")
            self.assertEqual(export_bundle([
                "--graph", str(graph_path),
                "--validation", str(validation_path),
                "--output-dir", str(out),
                "--cutoff", "5",
            ]), 0)
            all_text = "\n".join(path.read_text(encoding="utf-8") for path in out.rglob("*") if path.is_file())
            self.assertNotIn(FUTURE, all_text)
            self.assertTrue((out / "COMMITMENTS.md").is_file())
            self.assertIn("return", (out / "COMMITMENTS.md").read_text(encoding="utf-8"))
            manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["spoiler_cutoff_chapter"], 5)
            self.assertEqual(manifest["record_counts"]["commitments"], 1)

    def test_state_digest_drops_known_future_entity_fields(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            graph_path = root / "graph.json"
            output = root / "digest.md"
            graph_path.write_text(json.dumps(temporal_graph(), ensure_ascii=False), encoding="utf-8")
            script = Path(__file__).with_name("export_state_digest.py")
            proc = subprocess.run(
                [sys.executable, str(script), "--graph", str(graph_path), "--chapter", "5", "--output", str(output)],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertNotIn(FUTURE, output.read_text(encoding="utf-8"))


class MergeAndBuildAuditTests(unittest.TestCase):
    def test_expanded_merge_preserves_known_relation_close_without_monkey_patch(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            f1, f2, output = root / "f1.json", root / "f2.json", root / "graph.json"
            base = {
                "metadata": {"chapter_start": 1, "chapter_end": 5, "analyzed_chapters": [1, 2, 3, 4, 5]},
                "entities": [
                    {"id": "a", "type": "character", "name": "A", "first_chapter": 1, "evidence_ids": ["e1"]},
                    {"id": "b", "type": "character", "name": "B", "first_chapter": 1, "evidence_ids": ["e1"]},
                ],
                "evidence": [{"id": "e1", "chapter": 1, "quote": "long enough evidence quote", "source_line_start": 1, "source_line_end": 1}],
            }
            one = dict(base)
            one["relations"] = [{"id": "r_closed", "source_id": "a", "target_id": "b", "relation_type": "friend_of", "valid_from": 1, "valid_to": 4, "status": "ended", "evidence_ids": ["e1"]}]
            one["commitments"] = [{"id": "c1", "kind": "promise", "promisor_ids": ["a"], "counterparty_ids": ["b"], "terms": "x", "created_chapter": 1, "deadline_chapter": None, "deadline_story_time": None, "stake_ids": [], "status": "active", "resolved_chapter": None, "resolution": None, "observations": [], "evidence_ids": ["e1"], "confidence": "explicit"}]
            two = {"metadata": base["metadata"], "relations": [{"id": "r_open", "source_id": "a", "target_id": "b", "relation_type": "friend_of", "valid_from": 3, "status": "active", "evidence_ids": ["e1"]}], "commitments": [{"id": "c1", "observations": [{"chapter": 3, "status": "active", "evidence_ids": ["e1"]}]}]}
            f1.write_text(json.dumps(one, ensure_ascii=False), encoding="utf-8")
            f2.write_text(json.dumps(two, ensure_ascii=False), encoding="utf-8")
            self.assertEqual(merge_expanded(["--input", str(f1), str(f2), "--output", str(output)]), 0)
            graph = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(graph["relations"][0]["valid_to"], 4)
            self.assertEqual(len(graph["commitments"]), 1)
            self.assertEqual(graph["metadata"]["merge_engine"], "expanded-subprocess-v2")

    def test_build_step_timeout_is_recorded(self):
        manifest = {"steps": []}
        code = run_step(
            "sleep",
            [sys.executable, "-c", "import time; time.sleep(2)"],
            manifest,
            timeout=0.05,
        )
        self.assertEqual(code, 124)
        self.assertTrue(manifest["steps"][0]["timed_out"])
        self.assertGreaterEqual(manifest["steps"][0]["duration_ms"], 0)


@unittest.skipUnless(hasattr(os, "symlink"), "symlinks unavailable")
class GcAuditTests(unittest.TestCase):
    def test_gc_never_follows_candidate_symlink_outside_root(self):
        with tempfile.TemporaryDirectory() as td, tempfile.TemporaryDirectory() as external_td:
            root = Path(td)
            outside = Path(external_td)
            (outside / "keep.txt").write_text("external", encoding="utf-8")
            link = root / "__pycache__"
            try:
                link.symlink_to(outside, target_is_directory=True)
            except OSError as exc:
                self.skipTest(str(exc))
            self.assertNotIn(link, candidates(root))
            self.assertEqual((outside / "keep.txt").read_text(encoding="utf-8"), "external")


if __name__ == "__main__":
    unittest.main()
