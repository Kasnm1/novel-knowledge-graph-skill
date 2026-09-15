import json
import tempfile
import unittest
from pathlib import Path
import importlib.util

SCRIPT = Path(__file__).with_name("export_ai_bundle.py")
spec = importlib.util.spec_from_file_location("export_ai_bundle", SCRIPT)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


class ExportBundleTests(unittest.TestCase):
    def test_bundle_is_complete_deterministic_and_snapshot_safe(self):
        graph = {
            "metadata": {"title": "Demo", "chapter_start": 1, "chapter_end": 3},
            "entities": [{"id": "char_b", "type": "character", "name": "B"}, {"id": "char_a", "type": "character", "name": "A"}],
            "events": [{"id": "ev_future", "chapter": 3, "description": "future event 第 3 行"}],
            "evidence": [{"id": "evd1", "chapter": 3, "quote": "quote 第 9 行"}],
            "state_changes": [{"id": "sc_now", "entity_id": "char_a", "chapter": 1, "description": "current state"}, {"id": "sc_future", "entity_id": "char_a", "chapter": 3, "description": "future state"}],
            "foreshadowing": [{"id": "fs1", "label": "clue", "status": "open", "planted_chapter": 1, "observation": "watch", "interpretation": "later", "evidence_ids": ["evd1"]}],
            "chapter_summaries": [{"id": "cs3", "chapter": 3, "summary": "A future summary", "evidence_ids": ["evd1"]}],
            "story_arcs": [{"id": "arc1", "title": "Arc", "chapter_start": 1, "chapter_end": 3, "parent_arc_id": None, "status": "resolved", "phase": "resolution", "event_ids": ["ev_future"], "entity_ids": ["char_a"], "turning_point_ids": ["ev_future"], "evidence_ids": ["evd1"]}],
        }
        with tempfile.TemporaryDirectory() as td:
            root = Path(td); gp = root / "graph.json"; vp = root / "validation.json"; out = root / "out"
            gp.write_text(json.dumps(graph, ensure_ascii=False), encoding="utf-8"); vp.write_text(json.dumps({"record_counts": {}}), encoding="utf-8")
            (root / "style-observations.json").write_text(json.dumps({"observations": [{"id": "sty1", "scope": "character", "entity_id": "char_a", "dimension": "speech", "claim": "Uses short clauses.", "chapter_start": 1, "chapter_end": 3, "stability": "contextual", "confidence": "inferred", "evidence_ids": ["evd1"], "counterexamples": []}]}), encoding="utf-8")
            self.assertEqual(mod.main(["--graph", str(gp), "--validation", str(vp), "--output-dir", str(out), "--chapter", "1"]), 0)
            expected = {
                "manifest.json",
                "AI_CORE.md",
                "CONTINUE.md",
                "FORESHADOWING.md",
                "STORY_ARCS.md",
                "STYLE.md",
                "INDEX.json",
                "characters/char_a.md",
                "characters/char_b.md",
                "chapters/0001.md",
                "chapters/0002.md",
                "chapters/0003.md",
            }
            self.assertEqual({p.relative_to(out).as_posix() for p in out.rglob("*") if p.is_file()}, expected)
            self.assertIn("future event", (out / "chapters/0003.md").read_text(encoding="utf-8"))
            self.assertIn("A future summary", (out / "chapters/0003.md").read_text(encoding="utf-8"))
            all_text = "\n".join(p.read_text(encoding="utf-8") for p in out.rglob("*.md"))
            self.assertNotIn("第 9 行", all_text)
            self.assertIn("future state", (out / "characters/char_a.md").read_text(encoding="utf-8"))
            self.assertNotIn("future state", (out / "AI_CORE.md").read_text(encoding="utf-8"))
            first = (out / "INDEX.json").read_text(encoding="utf-8")
            mod.main(["--graph", str(gp), "--validation", str(vp), "--output-dir", str(out), "--chapter", "1"])
            self.assertEqual(first, (out / "INDEX.json").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
