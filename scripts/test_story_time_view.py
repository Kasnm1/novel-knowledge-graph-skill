from __future__ import annotations

import unittest

from nkg.views.story_time import build_story_time_view


class StoryTimeViewTests(unittest.TestCase):
    def test_narrative_and_story_time_remain_separate_without_guessing_semantics(self):
        graph = {
            "chapter_summaries": [
                {"id": "c10", "chapter": 10, "story_time": "十年前的冬天", "summary": "回忆", "evidence_ids": ["e10"]},
                {"id": "c11", "chapter": 11, "story_time": "当日傍晚", "story_time_sort_key": 200, "story_time_label": "傍晚", "evidence_ids": ["e11"]},
            ]
        }
        view = build_story_time_view(graph)
        self.assertEqual([row["narrative_chapter"] for row in view["chapters"]], [10, 11])
        self.assertEqual(view["chapters"][0]["story_time"], "十年前的冬天")
        self.assertNotIn("flashback", view["chapters"][0])
        self.assertEqual(view["chapters"][1]["story_time_sort_key"], 200)
        self.assertEqual(view["story_time_coverage"]["with_story_time"], 2)
        self.assertTrue(view["derived_only"])

    def test_missing_story_time_is_reported_as_missing_not_inferred(self):
        graph = {"chapter_summaries": [{"id": "c1", "chapter": 1, "summary": "x", "evidence_ids": []}]}
        view = build_story_time_view(graph)
        self.assertIsNone(view["chapters"][0]["story_time"])
        self.assertEqual(view["story_time_coverage"], {"with_story_time": 0, "total": 1})


if __name__ == "__main__":
    unittest.main()
