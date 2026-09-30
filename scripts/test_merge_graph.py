"""Tests for the canonical merge engine (merge_graph.py)."""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from nkg.temporal.asof import filter_graph

SCRIPT = Path(__file__).resolve().parent / "merge_graph.py"


def fragment(start: int, end: int, **arrays) -> dict:
    return {"metadata": {"chapter_start": start, "chapter_end": end, "analyzed_chapters": list(range(start, end + 1))},
            **arrays}


def merge(*fragments: dict) -> dict:
    with tempfile.TemporaryDirectory() as tmp:
        paths = []
        for i, frag in enumerate(fragments, 1):
            path = Path(tmp) / f"fragment-{i:02d}.json"
            path.write_text(json.dumps(frag, ensure_ascii=False), encoding="utf-8")
            paths.append(str(path))
        out = Path(tmp) / "graph.json"
        run = subprocess.run([sys.executable, str(SCRIPT), "--input", *paths, "--output", str(out)],
                             capture_output=True, text=True)
        assert run.returncode == 0, run.stdout + run.stderr
        return json.loads(out.read_text(encoding="utf-8"))


def hero(summary: str) -> dict:
    return {"id": "char_hero", "type": "character", "name": "甲", "first_chapter": 1, "summary": summary,
            "evidence_ids": []}


class MergeGraphTests(unittest.TestCase):
    def test_differing_summaries_become_dated_history(self):
        graph = merge(fragment(1, 10, entities=[hero("落魄保安")]),
                      fragment(11, 20, entities=[hero("集团董事长")]))
        entity = graph["entities"][0]
        self.assertEqual(entity["summary"], "集团董事长")
        self.assertEqual(entity["summary_history"],
                         [{"valid_from": 1, "summary": "落魄保安"}, {"valid_from": 11, "summary": "集团董事长"}])
        early = next(e for e in filter_graph(graph, 5)["entities"] if e["id"] == "char_hero")
        self.assertEqual(early["summary"], "落魄保安")

    def test_identical_summary_adds_no_history(self):
        graph = merge(fragment(1, 10, entities=[hero("同一句")]), fragment(11, 20, entities=[hero("同一句")]))
        self.assertNotIn("summary_history", graph["entities"][0])

    def test_romance_status_keeps_the_most_advanced_stage(self):
        route = lambda status: {"id": "rr", "protagonist_id": "char_hero", "character_id": "char_b", "status": status}
        graph = merge(fragment(1, 10, romance_routes=[route("confirmed_relationship")]),
                      fragment(11, 20, romance_routes=[route("ambiguous")]))
        self.assertEqual(graph["romance_routes"][0]["status"], "confirmed_relationship")

    def test_relation_type_aliases_are_canonicalized(self):
        rel = {"id": "r1", "source_id": "a", "target_id": "b", "relation_type": "holds", "valid_from": 1,
               "status": "active", "evidence_ids": []}
        graph = merge(fragment(1, 10, relations=[rel]))
        self.assertEqual(graph["relations"][0]["relation_type"], "possesses")
        self.assertTrue(graph["metadata"]["relation_type_canonicalization"])

    def test_stance_shift_is_kept_as_an_observation(self):
        rel = lambda stance, frm: {"id": "r1", "source_id": "a", "target_id": "b", "relation_type": "sworn_sibling_of",
                                   "valid_from": frm, "status": "active", "stance": stance, "evidence_ids": []}
        graph = merge(fragment(1, 10, relations=[rel("warm", 1)]),
                      fragment(11, 20, relations=[{**rel("contempt", 1), "chapter": 12}]))
        stances = [o.get("stance") for o in graph["relations"][0]["observations"]]
        self.assertIn("warm", stances)
        self.assertIn("contempt", stances)

    def test_scalar_rewrite_is_reported_not_silent(self):
        graph = merge(fragment(1, 10, foreshadowing=[{"id": "fs1", "label": "旧标签"}]),
                      fragment(11, 20, foreshadowing=[{"id": "fs1", "label": "新标签"}]))
        self.assertEqual(graph["metadata"]["merge_overrides"]["count"], 1)
        self.assertEqual(graph["metadata"]["merge_overrides"]["sample"][0]["field"], "label")


if __name__ == "__main__":
    unittest.main()
