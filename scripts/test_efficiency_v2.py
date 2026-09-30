from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from nkg.core.cache import build_cache_key, sha256_file, verify_artifact_manifest
from nkg.core.provenance import build_provenance_index
from nkg.workflow.planner import plan_audit
from nkg.extraction.resume import build_resume_capsule
from nkg.extraction.wire import compact_fragment, expand_fragment
from testing_fixtures import fixture_graph


class ChunkingTests(unittest.TestCase):
    def test_units_keep_whole_chapters_and_mark_oversize(self):
        rows = [
            {"chapter": 1, "text": "a" * 10},
            {"chapter": 2, "text": "b" * 10},
            {"chapter": 3, "text": "c" * 100},
            {"chapter": 4, "text": "d" * 10},
        ]
        units = plan_audit(rows, target_chars=25, max_chapters=10, densities={})["units"]
        self.assertEqual(units[0]["chapters"], [1, 2])
        self.assertEqual(units[1]["chapters"], [3])
        self.assertTrue(units[1]["oversize_single_chapter"])
        self.assertFalse(units[0]["oversize_single_chapter"])


class ResumeAndWireTests(unittest.TestCase):
    def test_resume_capsule_is_pointer_only_and_tracks_open_work(self):
        graph = fixture_graph()
        capsule = build_resume_capsule(graph, chapter=5, candidates=[{"id": "cand", "status": "unresolved"}])
        self.assertTrue(capsule["contract"]["derived_only"])
        self.assertIn("cm", capsule["open_commitment_ids"])
        self.assertIn("cand", capsule["unresolved_candidate_ids"])
        self.assertEqual(capsule["snapshot_chapter"], 5)

    def test_wire_roundtrip_restores_only_mechanical_defaults(self):
        fragment = {
            "metadata": {},
            "commitments": [{
                "id": "c", "kind": "promise", "promisor_ids": ["a"], "counterparty_ids": ["b"],
                "terms": "x", "created_chapter": 1, "deadline_chapter": None, "deadline_story_time": None,
                "stake_ids": [], "status": "active", "resolved_chapter": None, "resolution": None,
                "observations": [], "evidence_ids": ["e"], "confidence": "explicit",
            }],
        }
        compact = compact_fragment(fragment)
        self.assertNotIn("deadline_chapter", compact["commitments"][0])
        self.assertEqual(compact["commitments"][0]["evidence_ids"], ["e"])
        self.assertEqual(compact["commitments"][0]["confidence"], "explicit")
        expanded = expand_fragment(compact)
        self.assertEqual(expanded["commitments"][0]["deadline_chapter"], None)
        self.assertEqual(expanded["commitments"][0]["observations"], [])


class ProvenanceAndCacheTests(unittest.TestCase):
    def test_provenance_index_resolves_nested_evidence_fields(self):
        graph = fixture_graph()
        result = build_provenance_index(graph)
        self.assertTrue(result["derived_only"])
        self.assertIn("cm", result["facts"])
        self.assertIn("e1", result["facts"]["cm"]["evidence_ids"])
        self.assertEqual(result["missing_evidence_ids"], [])

    def test_cache_key_and_artifact_verification_are_fingerprint_strict(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            source = root / "source.json"; source.write_text("{}", encoding="utf-8")
            impl = root / "impl.py"; impl.write_text("x=1\n", encoding="utf-8")
            artifact = root / "out.json"; artifact.write_text("ok", encoding="utf-8")
            key1, _ = build_cache_key(input_files={"source": source}, parameters={"cutoff": 1}, implementation_files=[impl])
            key2, _ = build_cache_key(input_files={"source": source}, parameters={"cutoff": 1}, implementation_files=[impl])
            self.assertEqual(key1, key2)
            manifest = {"status": "complete", "artifacts": [{"path": str(artifact), "sha256": sha256_file(artifact)}]}
            self.assertTrue(verify_artifact_manifest(manifest)[0])
            artifact.write_text("tampered", encoding="utf-8")
            self.assertFalse(verify_artifact_manifest(manifest)[0])
            impl.write_text("x=2\n", encoding="utf-8")
            key3, _ = build_cache_key(input_files={"source": source}, parameters={"cutoff": 1}, implementation_files=[impl])
            self.assertNotEqual(key1, key3)


if __name__ == "__main__":
    unittest.main()
