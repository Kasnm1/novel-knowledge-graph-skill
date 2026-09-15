from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import build_expansion_artifacts
import gc_run


class DeliveryFailureTests(unittest.TestCase):
    def test_one_command_build_fails_when_candidate_scan_fails(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            graph = root / "graph.json"
            graph.write_text("{}", encoding="utf-8")
            out = root / "out"

            # Inject the failure by semantic step name rather than subprocess
            # position. The build may legitimately add validation/quality/cache
            # steps without changing the contract under test: candidate failure
            # must propagate to the top-level result.
            def fake_run_step(name, cmd, manifest, timeout=None):
                return 2 if name == "candidates" else 0

            with patch.object(build_expansion_artifacts, "run_step", side_effect=fake_run_step), patch(
                "sys.argv", ["build_expansion_artifacts.py", "--graph", str(graph), "--output-dir", str(out)]
            ):
                rc = build_expansion_artifacts.main()
            self.assertEqual(rc, 1)
            manifest = json.loads((out / "artifact-manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["status"], "failed")
            self.assertIn("candidate scan", manifest["failure_reason"])

    def test_gc_valid_archive_can_purge(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            junk = root / "run" / "a.tmp"; junk.parent.mkdir(); junk.write_text("data", encoding="utf-8")
            archive = root / "_gc_archive" / "ok"
            plan = gc_run.build_plan(root, archive)
            gc_run.apply_plan(root, archive, plan)
            gc_run.verify_for_purge(root, archive)
            with patch("sys.argv", ["gc_run.py", "--root", str(root), "--purge", str(archive)]):
                rc = gc_run.main()
            self.assertEqual(rc, 0)
            self.assertFalse(archive.exists())

    def test_gc_rejects_tampered_archive(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            junk = root / "run" / "a.tmp"; junk.parent.mkdir(); junk.write_text("data", encoding="utf-8")
            archive = root / "_gc_archive" / "tampered"
            plan = gc_run.build_plan(root, archive)
            gc_run.apply_plan(root, archive, plan)
            archived = archive / "run" / "a.tmp"
            archived.write_text("changed", encoding="utf-8")
            with self.assertRaises(ValueError):
                gc_run.verify_for_purge(root, archive)

    def test_gc_rejects_directory_without_manifest(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            archive = root / "_gc_archive" / "fake"; archive.mkdir(parents=True)
            with self.assertRaises(ValueError):
                gc_run.verify_for_purge(root, archive)


if __name__ == "__main__":
    unittest.main()
