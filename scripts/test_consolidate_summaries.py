from __future__ import annotations

import unittest

from consolidate_summaries import dedupe


class ConsolidateSummariesTests(unittest.TestCase):
    def test_identical_normalized_clauses_leave_one_copy(self) -> None:
        self.assertEqual(dedupe(["同一句。", "同一句。"]), ["同一句。"])
        self.assertEqual(dedupe(["同一句，", "同一句。"]), ["同一句，"])

    def test_duplicate_clause_does_not_erase_unique_clauses(self) -> None:
        self.assertEqual(dedupe(["甲；乙。", "甲；乙。", "丙。"]), ["甲；", "乙。", "丙。"])

    def test_strictly_longer_clause_subsumes_shorter_clause(self) -> None:
        self.assertEqual(dedupe(["住在城外。", "住在城外并守护村庄。"]), ["住在城外并守护村庄。"])


if __name__ == "__main__":
    unittest.main()
