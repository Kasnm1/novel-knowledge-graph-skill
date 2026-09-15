from __future__ import annotations

import unittest
import json
import subprocess
import sys
import tempfile
from pathlib import Path

from audit_schema_coverage import template_keys
from check_fragment import Checker, check_item_roles, check_required_fields
from required_fields import ARRAY_KINDS, REQUIRED


class ItemRolesContractTests(unittest.TestCase):
    def test_item_roles_are_first_class_and_present_in_worker_template(self) -> None:
        self.assertEqual(ARRAY_KINDS["item_roles"], "item_role")
        self.assertEqual(
            set(REQUIRED["item_role"]),
            {"id", "item_id", "entity_id", "role", "valid_from", "action", "evidence_ids", "confidence"},
        )
        template = Path(__file__).resolve().parent.parent / "references" / "TASK-SPEC.template.md"
        self.assertIn("item_roles", template_keys(template) or [])

    def test_fragment_gate_rejects_bad_role_and_missing_required_field(self) -> None:
        fragment = {
            "item_roles": [{
                "id": "ir1", "item_id": "item_ring", "entity_id": "char_a",
                "role": "possessor", "valid_from": 8, "valid_to": 7,
                "action": "gained", "evidence_ids": ["ev1"],
            }]
        }
        checker = Checker()
        check_required_fields(fragment, checker, set())
        check_item_roles(fragment, checker, {"ev1"})
        self.assertTrue(any("confidence" in error for error in checker.errors))
        self.assertTrue(any("role 非法" in error for error in checker.errors))
        self.assertTrue(any("valid_from" in error for error in checker.errors))

    def test_merged_graph_validator_checks_item_role_semantics(self) -> None:
        graph = {
            "metadata": {
                "title": "测试", "source_file": "book.txt", "source_sha256": "0" * 64,
                "chapter_start": 1, "chapter_end": 1, "analyzed_chapters": [1],
                "generated_at": "2026-01-01T00:00:00Z",
            },
            "entities": [
                {"id": "item_ring", "type": "item", "name": "戒指", "first_chapter": 1, "evidence_ids": ["ev1"]},
                {"id": "char_a", "type": "character", "name": "甲", "first_chapter": 1, "evidence_ids": ["ev1"]},
            ],
            "events": [], "relations": [], "state_changes": [], "foreshadowing": [],
            "review_issues": [],
            "evidence": [{"id": "ev1", "chapter": 1, "quote": "甲持有这枚戒指。", "source_line_start": 1, "source_line_end": 1}],
            "item_roles": [{
                "id": "ir1", "item_id": "item_ring", "entity_id": "char_a",
                "role": "possessor", "valid_from": 1, "action": "gained",
                "evidence_ids": ["ev1"], "confidence": "explicit",
            }],
        }
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            graph_path, report_path = root / "graph.json", root / "validation.json"
            graph_path.write_text(json.dumps(graph, ensure_ascii=False), encoding="utf-8")
            proc = subprocess.run(
                [sys.executable, str(Path(__file__).resolve().parent / "validate_graph.py"),
                 "--graph", str(graph_path), "--report", str(report_path)],
                capture_output=True, text=True, encoding="utf-8",
            )
            self.assertEqual(proc.returncode, 1)
            report = json.loads(report_path.read_text(encoding="utf-8"))
            self.assertTrue(any(row.get("code") == "bad_item_role" for row in report["errors"]))


if __name__ == "__main__":
    unittest.main()
