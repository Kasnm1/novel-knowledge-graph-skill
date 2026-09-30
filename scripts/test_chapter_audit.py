from __future__ import annotations

import copy
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from chapter_audit import AUDIT_ITEMS, blank_card, check_fragment_audit, item_counts

TYPES = {
    "char_a": "character", "char_b": "character", "char_c": "character",
    "loc_town": "location", "axis_qi": "level_axis", "item_sword": "item",
}


def fragment() -> dict:
    """A minimal protocol-2 fragment for chapter 2 whose card is complete and consistent."""
    frag = {
        "metadata": {"chapter_start": 2, "chapter_end": 2, "analyzed_chapters": [2], "audit_protocol": 2},
        "entities": [
            {"id": "char_a", "type": "character", "name": "甲", "first_chapter": 1, "evidence_ids": ["ev1"]},
            {"id": "char_b", "type": "character", "name": "乙", "first_chapter": 2, "evidence_ids": ["ev1"]},
            {"id": "char_c", "type": "character", "name": "丙", "first_chapter": 2, "evidence_ids": ["ev2"]},
            {"id": "loc_town", "type": "location", "name": "小镇", "first_chapter": 2, "evidence_ids": ["ev1"]},
            {"id": "axis_qi", "type": "level_axis", "name": "炼气", "first_chapter": 2, "evidence_ids": ["ev2"],
             "applies_to": ["character"]},
            {"id": "item_sword", "type": "item", "name": "铁剑", "first_chapter": 2, "evidence_ids": ["ev2"]},
        ],
        "evidence": [
            {"id": "ev1", "chapter": 2, "quote": "甲在镇口拦下乙。"},
            {"id": "ev2", "chapter": 2, "quote": "丙一剑破开第一层。"},
        ],
        "events": [
            {"id": "event_f1_001", "type": "conflict", "chapter": 2, "title": "镇口对峙", "description": "甲拦下乙。",
             "participant_ids": ["char_a", "char_b"], "evidence_ids": ["ev1"], "location_id": "loc_town"},
            {"id": "event_f1_002", "type": "breakthrough", "chapter": 2, "title": "丙突破", "description": "丙突破炼气一层。",
             "participant_ids": ["char_c"], "evidence_ids": ["ev2"]},
        ],
        "state_changes": [
            {"id": "sc_f1_001", "entity_id": "char_c", "facet": "level", "action": "gained", "chapter": 2,
             "before": None, "after": {"value": 1, "label": "炼气一层"}, "target_id": "axis_qi",
             "reason": "一剑破境", "evidence_ids": ["ev2"], "confidence": "explicit"},
            {"id": "sc_f1_002", "entity_id": "char_b", "facet": "location", "action": "changed", "chapter": 2,
             "before": {"value": None, "label": "野外"}, "after": {"value": None, "label": "小镇"},
             "reason": "被拦在镇口", "evidence_ids": ["ev1"], "confidence": "explicit"},
        ],
        "relations": [
            {"id": "rel_f1_001", "source_id": "char_a", "target_id": "char_b", "relation_type": "enemy_of",
             "valid_from": 2, "status": "active", "evidence_ids": ["ev1"]},
        ],
        "foreshadowing": [],
    }
    card = blank_card(2)
    card.update({
        "id": "cs_f1_002",
        "title": "第二章",
        "evidence_ids": ["ev1", "ev2"],
        "summary": "甲在镇口拦下乙，两人结怨。丙在一旁练剑。丙一剑破开炼气第一层。",
        "continuity": {"from_previous": "接第一章乙逃出山林。", "sets_up": "乙记恨甲，埋下报复。"},
        "scenes": [
            {"location_id": "loc_town", "participant_ids": ["char_a", "char_b"], "pov_entity_id": "char_a",
             "purpose": "立起甲乙的冲突", "event_ids": ["event_f1_001"]},
            {"location_label": "镇外竹林", "participant_ids": ["char_c"], "purpose": "丙突破",
             "event_ids": ["event_f1_002"]},
        ],
        "presence": [
            {"entity_id": "char_a", "mode": "present", "role": "拦路", "state_check": "confirmed_unchanged"},
            {"entity_id": "char_b", "mode": "present", "role": "被拦", "state_check": "changed"},
            {"entity_id": "char_c", "mode": "present", "role": "突破", "state_check": "changed"},
            {"entity_id": "loc_town", "mode": "present", "role": "主场景"},
        ],
        "narrative": {"functions": ["setup", "payoff"], "cliffhanger_type": "suspense", "pacing": "medium",
                      "quote_evidence_ids": ["ev2"]},
    })
    frag["chapter_summaries"] = [card]
    counts = item_counts(frag, 2, card)
    for key in AUDIT_ITEMS:
        card["audit"][key] = ({"status": "recorded", "count": counts[key]} if counts[key]
                              else {"status": "none", "count": 0, "reason": "原文本章没有此类内容"})
    return frag


def run(frag: dict) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    ev = {e["id"] for e in frag["evidence"]}
    check_fragment_audit(frag, TYPES, ev, frag["metadata"]["analyzed_chapters"], errors.append, warnings.append)
    return errors, warnings


class ChapterAuditTests(unittest.TestCase):
    def test_complete_card_passes(self) -> None:
        errors, _ = run(fragment())
        self.assertEqual(errors, [])

    def test_protocol_two_requires_a_card_for_every_narrative_chapter(self) -> None:
        frag = fragment()
        frag["chapter_summaries"] = []
        errors, _ = run(frag)
        self.assertTrue(any("审计卡" in e for e in errors))

    def test_non_narrative_chapter_is_exempt(self) -> None:
        frag = fragment()
        frag["chapter_summaries"] = []
        frag["review_issues"] = [{"id": "ri1", "severity": "info", "category": "non_narrative_chapter",
                                  "description": "作者感言", "related_ids": [], "chapter": 2}]
        errors, _ = run(frag)
        self.assertFalse(any("审计卡" in e for e in errors))

    def test_receipt_count_must_match_records(self) -> None:
        frag = fragment()
        frag["chapter_summaries"][0]["audit"]["events"]["count"] = 5
        errors, _ = run(frag)
        self.assertTrue(any("情节点" in e and "实际 2" in e for e in errors))

    def test_none_receipt_with_records_is_rejected(self) -> None:
        frag = fragment()
        frag["chapter_summaries"][0]["audit"]["relations"] = {"status": "none", "reason": "本章无关系变化"}
        errors, _ = run(frag)
        self.assertTrue(any("关系变化" in e and "标为 none" in e for e in errors))

    def test_none_receipt_needs_reason_and_missing_receipt_is_rejected(self) -> None:
        frag = fragment()
        audit = frag["chapter_summaries"][0]["audit"]
        audit["commitments"] = {"status": "none", "reason": ""}
        del audit["traits"]
        errors, _ = run(frag)
        self.assertTrue(any("承诺" in e and "理由" in e for e in errors))
        self.assertTrue(any("外貌" in e and "没有收据" in e for e in errors))

    def test_event_participant_must_be_on_roster(self) -> None:
        frag = fragment()
        frag["chapter_summaries"][0]["presence"] = [
            p for p in frag["chapter_summaries"][0]["presence"] if p["entity_id"] != "char_b"]
        frag["chapter_summaries"][0]["scenes"][0]["participant_ids"] = ["char_a"]
        errors, _ = run(frag)
        self.assertTrue(any("不在出场名册" in e for e in errors))

    def test_mentioned_character_cannot_take_part_unless_recalled(self) -> None:
        frag = fragment()
        card = frag["chapter_summaries"][0]
        card["presence"][1]["mode"] = "mentioned"          # char_b is only talked about
        card["presence"][1].pop("state_check")
        card["scenes"][0]["participant_ids"] = ["char_a"]
        frag["state_changes"] = [s for s in frag["state_changes"] if s["entity_id"] != "char_b"]
        counts = item_counts(frag, 2, card)
        for key in AUDIT_ITEMS:
            card["audit"][key] = ({"status": "recorded", "count": counts[key]} if counts[key]
                                  else {"status": "none", "count": 0, "reason": "原文本章没有此类内容"})
        errors, _ = run(frag)
        self.assertTrue(any("只是 mentioned" in e for e in errors))
        frag["events"][0]["tags"] = ["recalled"]
        errors, _ = run(frag)
        self.assertFalse(any("只是 mentioned" in e for e in errors))

    def test_state_check_must_agree_with_state_changes(self) -> None:
        frag = fragment()
        presence = frag["chapter_summaries"][0]["presence"]
        presence[0]["state_check"] = "changed"          # char_a has no change
        presence[1]["state_check"] = "confirmed_unchanged"  # char_b has one
        errors, _ = run(frag)
        self.assertTrue(any("char_a 标为 changed" in e for e in errors))
        self.assertTrue(any("char_b 标为 confirmed_unchanged" in e for e in errors))

    def test_summary_needs_three_sentences_and_continuity(self) -> None:
        frag = fragment()
        card = frag["chapter_summaries"][0]
        card["summary"] = "甲拦下乙。"
        card["continuity"] = {"from_previous": "", "sets_up": ""}
        errors, _ = run(frag)
        self.assertTrue(any("三到六句" in e for e in errors))
        self.assertTrue(any("承上" in e for e in errors))
        self.assertTrue(any("启下" in e for e in errors))

    def test_relation_alias_and_unknown_type_are_rejected(self) -> None:
        frag = fragment()
        frag["relations"][0]["relation_type"] = "holds"
        errors, _ = run(frag)
        self.assertTrue(any("possesses" in e for e in errors))
        frag["relations"][0]["relation_type"] = "frenemy_of"
        errors, _ = run(frag)
        self.assertTrue(any("frenemy_of" in e for e in errors))

    def test_unknown_stance_is_rejected(self) -> None:
        frag = fragment()
        frag["relations"][0]["observations"] = [{"chapter": 2, "stance": "frosty", "evidence_ids": ["ev1"]}]
        errors, _ = run(frag)
        self.assertTrue(any("stance" in e for e in errors))

    def test_level_axis_applicability_and_value_shape(self) -> None:
        frag = fragment()
        frag["state_changes"].append({
            "id": "sc_f1_003", "entity_id": "item_sword", "facet": "level", "action": "gained", "chapter": 2,
            "before": None, "after": "人器五品", "target_id": "axis_qi", "reason": "x",
            "evidence_ids": ["ev2"], "confidence": "explicit"})
        errors, _ = run(frag)
        self.assertTrue(any("只适用于" in e for e in errors))
        self.assertTrue(any("{value, label, note}" in e for e in errors))

    def test_legacy_fragment_without_card_is_not_checked(self) -> None:
        frag = fragment()
        frag["metadata"].pop("audit_protocol")
        for key in ("scenes", "presence", "audit"):
            frag["chapter_summaries"][0].pop(key)
        frag["relations"][0]["relation_type"] = "holds"
        errors, _ = run(frag)
        self.assertEqual(errors, [])

    def test_check_fragment_cli_runs_the_audit(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            good = Path(tmp) / "fragment-01.json"
            good.write_text(json.dumps(fragment(), ensure_ascii=False), encoding="utf-8")
            text = Path(tmp) / "002.txt"
            text.write_text("甲在镇口拦下乙。\n丙一剑破开第一层。\n", encoding="utf-8")
            index = Path(tmp) / "chapters.jsonl"
            # a relative text_path resolves against the index directory, wherever the gate runs
            index.write_text(json.dumps({"chapter": 2, "text_path": text.name}) + "\n", encoding="utf-8")
            script = Path(__file__).resolve().parent / "check_fragment.py"
            ok = subprocess.run([sys.executable, str(script), "--fragment", str(good), "--no-siblings",
                                 "--chapters-jsonl", str(index)],
                                capture_output=True, text=True)
            self.assertEqual(ok.returncode, 0, ok.stdout + ok.stderr)
            bad = copy.deepcopy(fragment())
            bad["chapter_summaries"][0]["audit"]["events"]["count"] = 9
            good.write_text(json.dumps(bad, ensure_ascii=False), encoding="utf-8")
            fail = subprocess.run([sys.executable, str(script), "--fragment", str(good), "--no-siblings",
                                 "--chapters-jsonl", str(index)],
                                  capture_output=True, text=True)
            self.assertEqual(fail.returncode, 1)
            self.assertIn("情节点", fail.stdout)


if __name__ == "__main__":
    unittest.main()
