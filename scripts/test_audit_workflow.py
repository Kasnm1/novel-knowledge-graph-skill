"""Tests for the chapter-audit workflow tools (nkg/workflow, audit_workflow.py)."""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import audit_workflow
from chapter_audit import check_fragment_audit
from nkg.workflow.authoring import FragmentBuilder
from nkg.workflow.capsule import build_chapter_capsule
from nkg.workflow.planner import chapter_density, plan_audit
from nkg.workflow.quality import chapter_score
from nkg.workflow.recall import apply_verdicts, recall_candidates
from nkg.workflow.registry import AmbiguousName, IdRegistry, RegistryError
from nkg.workflow.survey import build_scaffold, seed_registry, validate_survey


def graph() -> dict:
    return {
        "metadata": {"chapter_start": 1, "chapter_end": 6, "analyzed_chapters": [1, 2, 3, 4, 5, 6]},
        "entities": [
            {"id": "char_hero", "type": "character", "name": "秦朝", "aliases": ["秦哥"], "first_chapter": 1,
             "tags": ["protagonist"]},
            {"id": "char_su", "type": "character", "name": "苏姬", "first_chapter": 1},
            {"id": "char_huang", "type": "character", "name": "黄虎", "first_chapter": 3},
            {"id": "loc_town", "type": "location", "name": "苏南", "first_chapter": 1},
        ],
        "events": [{"id": "e1", "type": "encounter", "chapter": 1, "title": "相遇", "participant_ids": ["char_hero", "char_su"]}],
        "state_changes": [
            {"id": "s1", "entity_id": "char_hero", "facet": "location", "chapter": 2,
             "after": {"value": None, "label": "苏南"}},
            {"id": "s5", "entity_id": "char_hero", "facet": "location", "chapter": 5,
             "after": {"value": None, "label": "东川"}},
        ],
        "relations": [{"id": "r1", "source_id": "char_hero", "target_id": "char_su", "relation_type": "lover_of",
                       "valid_from": 2, "status": "active"}],
        "foreshadowing": [{"id": "fs1", "label": "花瓶来历", "planted_chapter": 1, "related_entity_ids": ["char_hero"]}],
        "commitments": [{"id": "c1", "kind": "promise", "terms": "照顾苏姬", "created_chapter": 2,
                         "promisor_ids": ["char_hero"], "counterparty_ids": ["char_su"]}],
        "chapter_summaries": [{"chapter": 3, "summary": "秦朝与黄虎在车站对峙。"}],
        "evidence": [], "review_issues": [],
    }


class RegistryTests(unittest.TestCase):
    def test_claim_reuses_known_names_and_aliases(self):
        reg = IdRegistry()
        reg.seed_from_graph(graph())
        self.assertEqual(reg.claim("character", "秦哥", "qin_ge"), ("char_hero", False))
        self.assertEqual(reg.claim("character", "余倩", "yu_qian", aliases=["倩倩"]), ("char_yu_qian", True))
        self.assertEqual(reg.lookup("倩倩"), ["char_yu_qian"])

    def test_id_table_marks_names_the_text_does_not_use_yet(self):
        reg = IdRegistry()
        reg.claim("character", "云谷", "yun_gu", aliases=["师傅", "医圣"])
        table = reg.id_table(["char_yun_gu"], text="他的师傅一生悬壶济世。")
        self.assertIn("| 师傅 |", table)
        self.assertIn("云谷（后文才出现，本段勿写）", table)

    def test_bad_slug_duplicate_id_and_ambiguity_raise(self):
        reg = IdRegistry()
        reg.seed_from_graph(graph())
        with self.assertRaises(RegistryError):
            reg.claim("character", "某人", "Mou Ren")
        with self.assertRaises(RegistryError):
            reg.claim("character", "另一个苏姬", "su")
        with self.assertRaises(AmbiguousName):
            reg.claim("character", "秦朝", "x", aliases=["苏姬"])

    def test_fragment_numbers_are_issued_once_and_respect_disk(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "fragment-07.json").write_text("{}", encoding="utf-8")
            reg = IdRegistry()
            first = reg.issue_fragment("L01-U01", Path(tmp))
            self.assertEqual(first, {"fragment": "fragment-08", "marker": "f08"})
            self.assertEqual(reg.issue_fragment("L01-U01", Path(tmp)), first)
            self.assertEqual(reg.issue_fragment("L01-U02", Path(tmp))["fragment"], "fragment-09")


class PlannerTests(unittest.TestCase):
    def rows(self, n=30, size=3000):
        return [{"chapter": c, "char_count": size} for c in range(1, n + 1)]

    def test_plan_covers_every_chapter_with_bounded_units(self):
        plan = plan_audit(self.rows(), lane_chapters=10, target_chars=10_000, max_chapters=5)
        self.assertEqual([c for u in plan["units"] for c in u["chapters"]], list(range(1, 31)))
        self.assertEqual(len(plan["lanes"]), 3)
        self.assertTrue(all(len(u["chapters"]) <= 5 for u in plan["units"]))
        first_lane = plan["lanes"][0]["units"]
        self.assertIsNone(plan["units"][0]["depends_on"])
        self.assertEqual(plan["units"][1]["depends_on"], first_lane[0])
        self.assertEqual(plan["units"][0]["read_only_context"]["next_chapter_head"]["chapter"], 4)

    def test_arcs_become_lanes_and_gaps_are_filled(self):
        arcs = [{"id": "arc_a", "chapter_start": 5, "chapter_end": 18}, {"id": "arc_sub", "chapter_start": 6,
                "chapter_end": 8, "parent_arc_id": "arc_a"}]
        plan = plan_audit(self.rows(), arcs=arcs, lane_chapters=100)
        self.assertEqual([(l["chapter_start"], l["chapter_end"], l["arc_id"]) for l in plan["lanes"]],
                         [(1, 4, None), (5, 18, "arc_a"), (19, 30, None)])
        self.assertEqual(plan["lanes"][1]["checkpoint_chapter"], 4)

    def test_dense_chapters_get_smaller_units(self):
        quiet, dense = "日常" * 1500, "突破杀血吻" * 600
        rows = [{"chapter": c, "text": quiet if c <= 10 else dense} for c in range(1, 21)]
        self.assertGreater(chapter_density(dense), chapter_density(quiet))
        plan = plan_audit(rows, lane_chapters=100, target_chars=9_000, max_chapters=5)
        quiet_units = [len(u["chapters"]) for u in plan["units"] if u["chapter_end"] <= 10]
        dense_units = [len(u["chapters"]) for u in plan["units"] if u["chapter_start"] > 10]
        self.assertGreater(sum(quiet_units) / len(quiet_units), sum(dense_units) / len(dense_units))


class CapsuleAndRecallTests(unittest.TestCase):
    def test_capsule_holds_state_before_the_chapter_only(self):
        cap = build_chapter_capsule(graph(), 5, text="秦朝走进东川。苏姬也在。")
        hero = next(e for e in cap["entities"] if e["id"] == "char_hero")
        self.assertEqual(cap["state_as_of"], 4)
        self.assertEqual(hero["facets"]["location"], {"value": "苏南", "since": 2})
        self.assertEqual(hero["state_check"][:2], ["identity", "location"])
        self.assertIn({"other": "char_su", "type": "lover_of", "since": 2}, hero["relations"])
        self.assertEqual([c["id"] for c in cap["open_threads"]["commitments"]], ["c1"])
        self.assertEqual([f["id"] for f in cap["open_threads"]["foreshadowing"]], ["fs1"])

    def test_recall_flags_unrecorded_presence_and_uncovered_markers(self):
        text = "黄虎冷笑。黄虎说他要钱。黄虎拿出五十万现金交易。秦朝突破了。"
        candidates = recall_candidates(graph(), 3, text)
        kinds = {c["kind"] for c in candidates}
        self.assertIn("presence", kinds)
        self.assertIn("money", kinds)
        self.assertIn("breakthrough", kinds)
        g = graph()
        g["state_changes"].append({"id": "s3", "entity_id": "char_hero", "facet": "level", "chapter": 3})
        self.assertNotIn("breakthrough", {c["kind"] for c in recall_candidates(g, 3, text)})
        tally = apply_verdicts(candidates, {candidates[0]["id"]: "missed"})
        self.assertEqual(tally["missed"], 1)
        self.assertEqual(tally["open"], len(candidates) - 1)

    def test_unverified_chapter_never_scores_as_clean(self):
        unverified = chapter_score(card=True, recall_open=0, recall_missed=0, verifier=None)
        verified = chapter_score(card=True, recall_open=0, recall_missed=0, verifier={"missed": 0, "wrong": 0})
        self.assertEqual((unverified["score"], verified["score"]), (70, 100))
        self.assertEqual(unverified["grade"], "review")


class SurveyTests(unittest.TestCase):
    def test_scaffold_validate_and_seed(self):
        rows = [{"chapter": 1, "text": "秦朝说道：“走。”" * 5 + "筑基期" * 3},
                {"chapter": 2, "text": "求月票！作者请假一天。"}] + \
               [{"chapter": c, "text": "正文" * 400} for c in range(3, 8)]
        scaffold = build_scaffold(rows)
        self.assertEqual(scaffold["frequent_speakers"][0]["name"], "秦朝")
        self.assertTrue(next(c for c in scaffold["chapters"] if c["chapter"] == 2)["likely_non_narrative"])
        survey = {"cast": [{"type": "character", "name": "秦朝", "slug": "qin_chao", "tier": "protagonist",
                            "aliases": ["秦哥"], "first_chapter": 1}],
                  "level_systems": [{"name": "九重天", "slug": "jiuchongtian"}],
                  "arcs": [{"id": "arc1", "chapter_start": 1, "chapter_end": 7}]}
        self.assertEqual(validate_survey(survey, range(1, 8)), [])
        bad = {"cast": [{"type": "character", "name": "X", "slug": "X X", "tier": "hero"}], "arcs": []}
        self.assertEqual(len(validate_survey(bad, range(1, 8))), 2)
        reg = IdRegistry()
        issued = seed_registry(reg, survey)
        self.assertEqual([i["id"] for i in issued], ["char_qin_chao", "axis_jiuchongtian"])


class AuthoringTests(unittest.TestCase):
    def build(self, reasons):
        b = FragmentBuilder("fragment-01", "f01", [1])
        b.entity("char_hero", "character", "秦朝", 1, "秦朝走进大门。")
        b.entity("char_su", "character", "苏姬", 1, "苏姬抬起头。")
        e = b.event(1, "encounter", "相遇", "秦朝在门口遇见苏姬。", ["char_hero", "char_su"], "秦朝走进大门。")
        b.state("char_hero", "location", "changed", 1, "苏南", "走进苏南", "秦朝走进大门。", before="野外")
        b.card(1, summary="秦朝进城。他遇见苏姬。两人对视良久。", from_previous="开篇", sets_up="苏姬的来历",
               scenes=[{"location_label": "城门", "participant_ids": ["char_hero", "char_su"], "purpose": "相遇",
                        "event_ids": [e]}],
               presence=[{"entity_id": "char_hero", "mode": "present", "role": "进城", "state_check": "changed"},
                         {"entity_id": "char_su", "mode": "present", "role": "被遇见", "state_check": "confirmed_unchanged"}],
               functions=["setup"], cliffhanger="suspense", pacing="medium", summary_quotes="苏姬抬起头。",
               line_quotes="苏姬抬起头。", none_reasons=reasons)
        return b

    def test_receipts_are_computed_and_the_card_passes(self):
        reasons = {k: "原文本章没有此类内容" for k in ("levels", "skills_items", "relations", "knowledge", "combat",
                                                   "transactions", "romance_intimacy", "commitments",
                                                   "foreshadowing", "traits")}
        frag = self.build(reasons).build()
        self.assertEqual(frag["chapter_summaries"][0]["audit"]["events"], {"status": "recorded", "count": 1})
        self.assertEqual(len(frag["evidence"]), 2)
        self.assertEqual(frag["state_changes"][0]["before"], {"value": None, "label": "野外"})
        errors: list[str] = []
        types = {"char_hero": "character", "char_su": "character"}
        check_fragment_audit(frag, types, {e["id"] for e in frag["evidence"]}, [1], errors.append, lambda _: None)
        self.assertEqual(errors, [])

    def test_observe_relation_appends_or_restates(self):
        b = FragmentBuilder("fragment-02", "f02", [6])
        b.observe_relation("rel_f01_004", 6, "四长老转为鄙视萧烈", "四长老冷眼相看。", stance="contempt",
                           base={"source_id": "char_elder", "target_id": "char_xiao_lie",
                                 "relation_type": "sworn_sibling_of", "valid_from": 1, "status": "active"})
        rel = b.data["relations"][0]
        self.assertEqual(rel["id"], "rel_f01_004")
        self.assertEqual(rel["observations"][0]["stance"], "contempt")
        with self.assertRaises(ValueError):
            b.observe_relation("rel_missing", 6, "x", "四长老冷眼相看。", stance="cold")

    def test_build_refuses_items_without_records_or_reason(self):
        with self.assertRaises(ValueError) as ctx:
            self.build({}).build()
        self.assertIn("commitments", str(ctx.exception))


class CliTests(unittest.TestCase):
    def test_plan_and_ids_commands(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            index = root / "chapters.jsonl"
            index.write_text("".join(json.dumps({"chapter": c, "char_count": 4000}) + "\n" for c in range(1, 13)),
                             encoding="utf-8")
            self.assertEqual(audit_workflow.main(["plan", "--chapters-jsonl", str(index), "--lane-chapters", "6",
                                                  "--output", str(root / "plan.json")]), 0)
            plan = json.loads((root / "plan.json").read_text(encoding="utf-8"))
            self.assertEqual(plan["summary"]["lanes"], 2)
            graph_path = root / "graph.json"
            graph_path.write_text(json.dumps(graph(), ensure_ascii=False), encoding="utf-8")
            registry = root / "ids.json"
            self.assertEqual(audit_workflow.main(["ids", "--registry", str(registry), "--seed-graph", str(graph_path)]), 0)
            self.assertEqual(audit_workflow.main(["ids", "--registry", str(registry), "--claim", "character",
                                                  "苏姬", "su_ji_2"]), 0)
            data = json.loads(registry.read_text(encoding="utf-8"))
            self.assertNotIn("char_su_ji_2", data["entities"])


if __name__ == "__main__":
    unittest.main()
