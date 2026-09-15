"""Regression tests for canonical run identity and exclusive ownership."""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from resolve_run import (
    DuplicateRunError,
    RunLockedError,
    claim_run,
    release_run,
    resolve_run,
)


class ResolveRunTests(unittest.TestCase):
    def make_source(self, root: Path, name: str, text: str) -> Path:
        path = root / name
        path.write_text(text, encoding="utf-8")
        return path

    def write_manifest(self, run: Path, digest: str) -> None:
        run.mkdir(parents=True)
        (run / "source_manifest.json").write_text(
            json.dumps({"source_sha256": digest}), encoding="utf-8"
        )

    def test_prompt_title_and_range_do_not_change_run_identity(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            source = self.make_source(root, "novel.txt", "same immutable edition")
            runs = root / "runs"
            first, digest, reused = resolve_run(source, runs)
            self.assertEqual(first.name, f"book-{digest[:12]}")
            self.assertFalse(reused)
            claim_run(first, source, digest, "task-a", "Title from prompt A")
            release_run(first, "task-a")
            second, second_digest, reused = resolve_run(source, runs)
            self.assertEqual(second, first)
            self.assertEqual(second_digest, digest)
            self.assertTrue(reused)

    def test_existing_legacy_run_is_reused_by_source_hash(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            source = self.make_source(root, "novel.txt", "legacy edition")
            candidate, digest, _ = resolve_run(source, root / "empty")
            legacy = root / "runs" / "旧提示词-1-50"
            self.write_manifest(legacy, digest)
            resolved, _, reused = resolve_run(source, root / "runs")
            self.assertEqual(resolved, legacy.resolve())
            self.assertNotEqual(resolved, candidate)
            self.assertTrue(reused)

    def test_multiple_legacy_runs_fail_instead_of_creating_another(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            source = self.make_source(root, "novel.txt", "duplicate edition")
            _, digest, _ = resolve_run(source, root / "empty")
            self.write_manifest(root / "runs" / "book-a", digest)
            self.write_manifest(root / "runs" / "book-b", digest)
            with self.assertRaises(DuplicateRunError):
                resolve_run(source, root / "runs")

    def test_lock_is_exclusive_and_only_owner_can_release(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            source = self.make_source(root, "novel.txt", "locked edition")
            run, digest, _ = resolve_run(source, root / "runs")
            claim_run(run, source, digest, "task-a")
            with self.assertRaises(RunLockedError):
                claim_run(run, source, digest, "task-b")
            with self.assertRaises(RunLockedError):
                release_run(run, "task-b")
            release_run(run, "task-a")
            self.assertFalse((run / "RUN.lock").exists())

    def test_changed_source_bytes_get_a_different_run(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            first = self.make_source(root, "first.txt", "edition one")
            second = self.make_source(root, "second.txt", "edition two")
            first_run, first_hash, _ = resolve_run(first, root / "runs")
            second_run, second_hash, _ = resolve_run(second, root / "runs")
            self.assertNotEqual(first_hash, second_hash)
            self.assertNotEqual(first_run, second_run)

    def test_same_book_id_reuses_run_when_source_is_appended(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            source = self.make_source(root, "book.txt", "chapters 1-10")
            run, digest, _ = resolve_run(source, root / "runs", "book-demo", "web")
            claim_run(run, source, digest, "task-a", book_key="book-demo::web")
            release_run(run, "task-a")
            source.write_text("chapters 1-20", encoding="utf-8")
            same, next_digest, reused = resolve_run(source, root / "runs", "book-demo", "web")
            self.assertEqual(same, run)
            self.assertNotEqual(next_digest, digest)
            self.assertTrue(reused)
            claim_run(same, source, next_digest, "task-b", book_key="book-demo::web")
            release_run(same, "task-b")
            identity = json.loads((same / ".run-identity.json").read_text(encoding="utf-8"))
            self.assertEqual(identity["source_sha256"], next_digest)
            self.assertEqual(len(identity["source_snapshots"]), 2)


if __name__ == "__main__":
    unittest.main()
