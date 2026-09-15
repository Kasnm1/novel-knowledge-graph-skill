#!/usr/bin/env python3
"""Contract tests for run_contracts.py using a disposable run directory."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from run_contracts import build_contracts, sha256_file


class RunContractsTests(unittest.TestCase):
    def write_json(self, path: Path, data: object) -> None:
        path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

    def fixture(self, run: Path) -> None:
        self.write_json(run / "graph.json", {"metadata": {"title": "Example", "chapter_start": 1, "chapter_end": 4, "analyzed_chapters": [1]}})
        self.write_json(run / "validation.json", {"valid": True})
        self.write_json(run / "source_manifest.json", {"title": "Example", "source_sha256": "a" * 64, "prepared_chapters": [1, 2, 3, 4], "missing_chapters": [3]})
        self.write_json(run / "display-vocabulary.json", {"entity_types": {"character": "Character"}})

    def test_prepared_is_not_promoted_to_analyzed_and_human_fields_survive(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            run = Path(root) / "example-ch001-004"
            run.mkdir()
            self.fixture(run)
            self.write_json(run / "book-profile.json", {"human_note": "keep me", "approval": {"status": "draft"}})
            result = build_contracts(run)
            rows = {row["chapter"]: row for row in result["coverage"]["chapters"]}
            self.assertTrue(rows[1]["prepared"])
            self.assertTrue(rows[1]["analyzed"])
            self.assertTrue(rows[1]["validated"])
            self.assertTrue(rows[2]["prepared"])
            self.assertFalse(rows[2]["analyzed"])
            self.assertFalse(rows[2]["validated"])
            self.assertTrue(rows[3]["excluded"])
            self.assertEqual(result["book_profile"]["human_note"], "keep me")
            self.assertFalse(result["snapshot"]["approval"]["approved"])

    def test_directory_mismatch_is_warned_and_hashes_are_present(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            run = Path(root) / "example-ch001-009"
            run.mkdir()
            self.fixture(run)
            result = build_contracts(run, approval_status="approved", approved_by="reviewer")
            self.assertTrue(any("chapter end 9" in warning for warning in result["snapshot"]["warnings"]))
            hashes = result["snapshot"]["artifacts"]
            self.assertEqual(set(hashes), {"source", "graph", "validation", "toolchain", "profile", "coverage"})
            self.assertTrue(all(len(value) == 64 for value in hashes.values()))
            self.assertTrue(result["snapshot"]["approval"]["approved"])
            self.assertEqual(hashes["profile"], sha256_file(run / "book-profile.json"))


if __name__ == "__main__":
    unittest.main()
