from __future__ import annotations

import unittest

from verify_chapter_views import value_tokens


class ValueTokensTests(unittest.TestCase):
    def test_empty_containers_create_no_phantom_tokens(self) -> None:
        self.assertEqual(value_tokens({}), set())
        self.assertEqual(value_tokens([]), set())
        self.assertEqual(value_tokens({"属性": {}, "等级": []}), set())

    def test_real_scalar_and_level_values_remain_comparable(self) -> None:
        self.assertEqual(value_tokens("存在"), {'"存在"'})
        self.assertEqual(
            value_tokens({"value": 2, "label": "二级"}),
            {'{"label": "二级", "value": 2}'},
        )


if __name__ == "__main__":
    unittest.main()
