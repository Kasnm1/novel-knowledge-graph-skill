from __future__ import annotations

import unittest

from audit_chapter_depth import per_chapter, run_defects, summarize
from relation_types import canonical_relation_type, relation_group, unknown_relation_types


def graph() -> dict:
    return {
        "metadata": {"title": "t", "chapter_start": 1, "chapter_end": 3, "analyzed_chapters": [1, 2, 3]},
        "entities": [
            {"id": "char_a", "type": "character", "name": "张三", "first_chapter": 1},
            {"id": "char_b", "type": "character", "name": "李四", "first_chapter": 1},
            {"id": "item_x", "type": "item", "name": "铁剑", "first_chapter": 1},
            {"id": "axis_realm", "type": "level_axis", "name": "境界", "first_chapter": 1},
            {"id": "axis_realm2", "type": "level_axis", "name": "界境", "first_chapter": 2},
        ],
        "events": [{"id": "e1", "type": "battle", "chapter": 1, "participant_ids": ["char_a", "char_b"]}],
        "state_changes": [
            {"id": "s1", "entity_id": "char_a", "facet": "level", "chapter": 1, "target_id": "axis_realm",
             "after": {"value": 1, "label": "一重（入门时由师父点拨方才突破）"}},
            {"id": "s2", "entity_id": "char_b", "facet": "level", "chapter": 2, "target_id": "axis_realm",
             "after": {"value": 1, "label": "一重"}},
            {"id": "s3", "entity_id": "item_x", "facet": "level", "chapter": 2, "target_id": "axis_realm",
             "after": "人器五品"},
        ],
        "relations": [{"id": "r1", "source_id": "char_a", "target_id": "char_b", "relation_type": "holds",
                       "valid_from": 1}],
        "chapter_summaries": [
            {"chapter": 1, "summary": "张三击败李四。"},
            {"chapter": 3, "summary": "张三与李四在城门重逢。两人谈起旧事。约定再战。"},
        ],
        "review_issues": [],
    }


class ChapterDepthTests(unittest.TestCase):
    def test_per_chapter_density_and_recall_gap(self) -> None:
        rows = {r["chapter"]: r for r in per_chapter(graph(), {3: "张三张三张三 李四"}, 3)}
        self.assertEqual(rows[1]["events"], 1)
        self.assertEqual(rows[1]["summary_named_without_record"], [])
        self.assertEqual(rows[3]["summary_named_without_record"], ["char_a", "char_b"])
        self.assertEqual(rows[3]["text_named_without_record"], ["char_a"])
        summary = summarize(list(rows.values()))
        self.assertEqual(summary["summaries_under_three_sentences"], 2)
        self.assertEqual(summary["thin_chapters"]["chapters"], [3])

    def test_run_defects(self) -> None:
        d = run_defects(graph())
        self.assertEqual(d["relation_types"]["aliases_used"], {"holds": 1})
        self.assertEqual([s["id"] for s in d["level_misattribution_suspects"]], ["s3"])
        self.assertEqual(len(d["near_duplicate_level_axes"]), 1)
        self.assertEqual(d["labels_with_embedded_notes"]["count"], 1)
        self.assertEqual(d["state_value_shapes"], {"dict": 2, "str": 1})

    def test_relation_type_folding(self) -> None:
        self.assertEqual(canonical_relation_type("located_at"), "located_in")
        self.assertEqual(relation_group("mother_of"), "family")
        self.assertEqual(relation_group("frenemy_of"), "other")
        self.assertEqual(unknown_relation_types([{"relation_type": "frenemy_of"}, {"relation_type": "holds"}]),
                         {"frenemy_of": 1})


if __name__ == "__main__":
    unittest.main()
