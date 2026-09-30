"""Coverage for backend modules that had no tests: reader_prose, prepare_novel,
plan_reconciliation, export_ai_context and the validate_graph rules."""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import prepare_novel
from reader_prose import strip_process_text, to_js
from testing_fixtures import FUTURE, fixture_graph
from validate_graph import validate

HERE = Path(__file__).resolve().parent


class ReaderProseTests(unittest.TestCase):
    def test_bookkeeping_is_removed_and_story_text_kept(self):
        cleaned = strip_process_text("秦朝击退了黄虎（rom_A01、rom_A02）。请主 Agent 裁决。")
        self.assertIn("秦朝击退了黄虎", cleaned)
        self.assertNotIn("主 Agent", cleaned)
        self.assertNotIn("rom_A01", cleaned)

    def test_text_that_is_almost_all_bookkeeping_is_handed_back_empty(self):
        text = "秦朝击退了黄虎。本条由主 Agent 从 3 条分片记录合并（rom_A01、rom_A02）。请主 Agent 裁决。"
        self.assertEqual(strip_process_text(text), "")

    def test_plain_story_text_is_untouched_and_js_port_exists(self):
        self.assertEqual(strip_process_text("她笑着点头。"), "她笑着点头。")
        self.assertIn("function", to_js())


class PrepareNovelTests(unittest.TestCase):
    def test_numerals_and_headings(self):
        self.assertEqual(prepare_novel.chinese_number("一百零五"), 105)
        self.assertEqual(prepare_novel.chinese_number("十二"), 12)
        with self.assertRaises(ValueError):
            prepare_novel.chinese_number("甲")
        self.assertEqual(prepare_novel.match_heading("第十二章 夜袭")[0], 12)
        self.assertIsNone(prepare_novel.match_heading("他说第十二章的内容很长很长很长很长很长很长很长很长很长很长很长很长。"))

    def test_splits_a_small_novel_into_chapters(self):
        body = "".join(f"第{n}章 标题{n}\n" + "　　正文段落，内容足够长，写满一整行文字用于测试章节切分。\n" * 5
                       for n in ("一", "二", "三"))
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "book.txt"
            source.write_text(body, encoding="utf-8")
            out = Path(tmp) / "run"
            run = subprocess.run([sys.executable, str(HERE / "prepare_novel.py"), "--input", str(source),
                                  "--output-dir", str(out), "--start", "1", "--end", "3"],
                                 capture_output=True, text=True)
            self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
            rows = [json.loads(l) for l in (out / "chapters.jsonl").read_text(encoding="utf-8").splitlines() if l]
            self.assertEqual([r["chapter"] for r in rows], [1, 2, 3])
            self.assertTrue(all(Path(r["text_path"]).is_file() or (out / r["text_path"]).is_file() for r in rows))


class PlanReconciliationTests(unittest.TestCase):
    def test_reports_one_id_declared_with_two_names(self):
        with tempfile.TemporaryDirectory() as tmp:
            run = Path(tmp)
            (run / "fragments").mkdir()
            (run / "chapters").mkdir()
            for n, name in ((1, "黄虎"), (2, "黄老虎")):
                (run / "fragments" / f"fragment-0{n}.json").write_text(json.dumps(
                    {"metadata": {"chapter_start": n, "chapter_end": n, "analyzed_chapters": [n]},
                     "entities": [{"id": "char_huanghu", "type": "character", "name": name,
                                   "first_chapter": n, "evidence_ids": []}]}, ensure_ascii=False), encoding="utf-8")
            report = run / "report.json"
            proc = subprocess.run([sys.executable, str(HERE / "plan_reconciliation.py"), "--run-dir", str(run),
                                   "--json", str(report)], capture_output=True, text=True)
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            data = json.loads(report.read_text(encoding="utf-8"))
            self.assertIn("char_huanghu", json.dumps(data["duplicate_entity_ids"], ensure_ascii=False))
            self.assertIn("char_huanghu", json.dumps(data["entity_first_chapter"], ensure_ascii=False))
            self.assertEqual(len(data["fragment_gate"]["suspect_fragments"]), 2)


class ExportAiContextTests(unittest.TestCase):
    def test_story_bible_respects_cutoff(self):
        import export_ai_context
        with tempfile.TemporaryDirectory() as tmp:
            graph = Path(tmp) / "graph.json"
            graph.write_text(json.dumps(fixture_graph(), ensure_ascii=False), encoding="utf-8")
            full, cut = Path(tmp) / "full.md", Path(tmp) / "cut.md"
            self.assertEqual(export_ai_context.main(["--graph", str(graph), "--output", str(full)]), 0)
            self.assertEqual(export_ai_context.main(["--graph", str(graph), "--output", str(cut), "--cutoff", "5"]), 0)
            self.assertIn(FUTURE, full.read_text(encoding="utf-8"))
            self.assertNotIn(FUTURE, cut.read_text(encoding="utf-8"))


class ValidateGraphRuleTests(unittest.TestCase):
    def test_rules_report_duplicates_bad_refs_and_coverage(self):
        graph = fixture_graph()
        graph["events"].append(dict(graph["events"][0]))                       # duplicate id
        graph["relations"][0]["evidence_ids"] = ["missing_ev"]                 # unknown evidence
        graph["evidence"].append({"id": "e99", "chapter": 99, "quote": "outside the analysed range",
                                  "source_line_start": 1, "source_line_end": 1})
        report = validate(graph)
        codes = {e["code"] for e in report["errors"]}
        self.assertIn("duplicate_id", codes)
        self.assertIn("bad_evidence_ref", codes)
        self.assertIn("chapter_outside_coverage", codes)
        self.assertFalse(report["valid"])
        self.assertEqual(report["record_counts"]["commitments"], 1)


if __name__ == "__main__":
    unittest.main()
