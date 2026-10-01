"""The reader model shows only what is true at each chapter, and hides what went stale."""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import build_reader_model
from nkg.views.reader_model import build_reader_model as build
from testing_fixtures import FUTURE, fixture_graph


def ev(eid, ch, quote="原文"):
    return {"id": eid, "chapter": ch, "quote": quote, "source_line_start": 1, "source_line_end": 1}


def graph():
    return {
        "metadata": {"title": "测试书", "chapter_start": 1, "chapter_end": 40, "analyzed_chapters": list(range(1, 41)),
                     "protagonist_ids": ["char_a"]},
        "entities": [
            {"id": "char_a", "type": "character", "name": "阿甲", "first_chapter": 1, "aliases": ["甲哥"],
             "summary": "终局总结", "evidence_ids": ["e1"]},
            {"id": "char_b", "type": "character", "name": "云谷", "first_chapter": 2,
             "name_history": [{"name": "白衣老者", "valid_from": 2}, {"name": "云谷", "valid_from": 30}], "aliases": []},
        ],
        "events": [{"id": "event_1", "chapter": 3, "title": "相遇", "participant_ids": ["char_a", "char_b"], "evidence_ids": ["e3"]}],
        "state_changes": [
            {"id": "sc_loc", "entity_id": "char_a", "facet": "location", "chapter": 3, "action": "changed",
             "after": {"label": "山谷"}, "evidence_ids": ["e3"]},
            {"id": "sc_lv1", "entity_id": "char_a", "facet": "level", "target_id": "axis_x", "chapter": 3,
             "action": "gained", "after": {"value": 1, "label": "一级"}, "evidence_ids": ["e3"]},
            {"id": "sc_lv2", "entity_id": "char_a", "facet": "level", "target_id": "axis_x", "chapter": 20,
             "action": "upgraded", "after": {"value": 2, "label": "二级"}, "evidence_ids": ["e20"]},
            {"id": "sc_dead", "entity_id": "char_b", "facet": "health", "chapter": 25, "action": "changed",
             "after": {"label": "身亡"}, "evidence_ids": ["e25"]},
        ],
        "relations": [{"id": "rel_1", "source_id": "char_a", "target_id": "char_b", "relation_type": "mentor_of",
                       "valid_from": 3, "valid_to": 24, "evidence_ids": ["e3"],
                       "observations": [{"chapter": 3, "stance": "respectful"}, {"chapter": 10, "stance": "wary"}]}],
        "chapter_summaries": [{"id": "cs_8", "chapter": 8, "summary": "第八章", "presence": [
            {"entity_id": "char_a", "mode": "present", "state_check": "confirmed_unchanged"}]}],
        "romance_routes": [], "foreshadowing": [], "commitments": [], "intimate_acts": [],
        "evidence": [ev("e1", 1, "人称甲哥"), ev("e3", 3), ev("e20", 20), ev("e25", 25)],
    }


def interval(model, entity, facet, chapter):
    return [f["value"] for f in model["facts"] if f["e"] == entity and f["facet"] == facet
            and f["from"] <= chapter and (f.get("to") is None or chapter <= f["to"])]


class ReaderModelTests(unittest.TestCase):
    def setUp(self):
        self.model = build(graph())

    def test_volatile_state_expires_and_a_confirmation_extends_it(self):
        # location TTL is 5; the audit card confirmed it unchanged at chapter 8
        self.assertEqual(interval(self.model, "char_a", "location", 3), ["山谷"])
        self.assertEqual(interval(self.model, "char_a", "location", 13), ["山谷"])
        self.assertEqual(interval(self.model, "char_a", "location", 14), [])

    def test_durable_state_holds_until_the_next_change(self):
        self.assertEqual(interval(self.model, "char_a", "level", 19), ["一级"])
        self.assertEqual(interval(self.model, "char_a", "level", 20), ["二级"])
        self.assertEqual(interval(self.model, "char_b", "health", 40), ["身亡"])

    def test_late_name_and_untimed_prose_stay_hidden(self):
        b = self.model["entities"]["char_b"]
        self.assertEqual(b["names"], [[2, "白衣老者"], [30, "云谷"]])
        a = self.model["entities"]["char_a"]
        self.assertEqual(a["summary"], [[40, "终局总结"]])      # untimed: terminal chapter only
        self.assertEqual(a["aliases"], [[1, "甲哥"]])            # dated by a quotation about char_a

    def test_relation_interval_and_stance_timeline(self):
        rel = self.model["relations"][0]
        self.assertEqual((rel["from"], rel["to"], rel["group"]), (3, 24, "mentorship"))
        self.assertEqual(rel["stance"], [[3, "respectful"], [10, "wary"]])

    def test_chapter_rows_and_level_ladder(self):
        chapters = {c["n"]: c for c in self.model["chapters"]}
        self.assertEqual(chapters[8]["summary"], "第八章")
        self.assertEqual(chapters[3]["events"], ["event_1"])
        self.assertEqual([c["id"] for c in chapters[3]["cast"]], ["char_a", "char_b"])
        self.assertEqual([r["label"] for r in self.model["levels"]["axis_x"]["rungs"]], ["一级", "二级"])

    def test_only_cited_evidence_is_carried(self):
        # entity-level evidence is undated prose support, so it is not carried
        self.assertEqual(set(self.model["evidence"]), {"e3", "e20", "e25"})


class CutoffBuildTests(unittest.TestCase):
    def test_cutoff_model_has_no_future_content(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "graph.json"
            path.write_text(json.dumps(fixture_graph(), ensure_ascii=False), encoding="utf-8")
            out = Path(tmp) / "model.json"
            self.assertEqual(build_reader_model.main(["--graph", str(path), "--cutoff", "5", "--output", str(out)]), 0)
            text = out.read_text(encoding="utf-8")
            self.assertNotIn(FUTURE, text)
            self.assertEqual(json.loads(text)["meta"]["last"], 5)


if __name__ == "__main__":
    unittest.main()
