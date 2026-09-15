from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPTS = Path(__file__).resolve().parent
SKILL = SCRIPTS.parent


class DashboardReadabilityTest(unittest.TestCase):
    def test_generated_dashboard_exposes_shared_reader_model_and_accessible_views(self) -> None:
        graph = {
            "metadata": {"title": "测试书", "chapter_start": 1, "chapter_end": 10},
            "entities": [
                {"id": "char_main", "type": "character", "name": "主角", "first_chapter": 1, "evidence_ids": ["ev_shared"]},
                {"id": "char_owner", "type": "character", "name": "所有者", "first_chapter": 1},
                {"id": "char_holder", "type": "character", "name": "持有人", "first_chapter": 1},
                {"id": "char_user", "type": "character", "name": "使用者", "first_chapter": 1},
                {"id": "char_keeper", "type": "character", "name": "保管者", "first_chapter": 1},
                {"id": "item_relic", "type": "item", "name": "遗物", "first_chapter": 1},
                {"id": "org_family", "type": "organization", "name": "测试家族", "first_chapter": 1},
                {"id": "org_branch", "type": "organization", "name": "家族支脉", "first_chapter": 2},
                {"id": "loc_country", "type": "location", "name": "测试国", "first_chapter": 1},
                {"id": "skill_test", "type": "skill", "name": "测试技能", "first_chapter": 2},
                {"id": "axis_test", "type": "level_axis", "name": "测试等级", "first_chapter": 1, "attributes": {"档位": ["一级", "二级"]}},
            ],
            "relations": [
                {"id": "rel_friend", "source_id": "char_main", "target_id": "char_owner", "relation_type": "friend_of", "valid_from": 1, "valid_to": 10, "evidence_ids": ["ev_shared"]},
                {"id": "rel_skill", "source_id": "char_main", "target_id": "skill_test", "relation_type": "learned", "valid_from": 2, "evidence_ids": ["ev_shared"]},
                {"id": "rel_sibling", "source_id": "char_main", "target_id": "char_holder", "relation_type": "sibling_of", "valid_from": 1, "evidence_ids": ["ev_shared"]},
                {"id": "rel_family", "source_id": "char_main", "target_id": "org_family", "relation_type": "family_member_of", "valid_from": 1, "evidence_ids": ["ev_shared"]},
                {"id": "rel_subset", "source_id": "org_branch", "target_id": "org_family", "relation_type": "subgroup_of", "valid_from": 2, "evidence_ids": ["ev_shared"]},
            ],
            "state_changes": [
                {"id": "sc_identity", "entity_id": "char_main", "facet": "identity", "action": "revealed", "chapter": 2, "before": None, "after": "测试者", "reason": "身份公开", "confidence": "explicit", "evidence_ids": ["ev_shared"]},
                {"id": "sc_level", "entity_id": "char_main", "target_id": "axis_test", "facet": "level", "action": "upgraded", "chapter": 3, "before": None, "after": {"value": 1, "label": "一级"}, "reason": "完成晋级", "confidence": "explicit", "evidence_ids": ["ev_shared"]},
            ],
            "evidence": [{"id": "ev_shared", "chapter": 2, "quote": "同一条证据同时支持多个记录。"}],
            "item_roles": [
                {"id": "ir_owner", "item_id": "item_relic", "entity_id": "char_owner", "role": "owner", "valid_from": 1},
                {"id": "ir_holder", "item_id": "item_relic", "entity_id": "char_holder", "role": "holder", "valid_from": 1},
                {"id": "ir_user", "item_id": "item_relic", "entity_id": "char_user", "role": "user", "valid_from": 1},
                {"id": "ir_keeper", "item_id": "item_relic", "entity_id": "char_keeper", "role": "custodian", "valid_from": 1},
            ],
            "review_issues": [{"id": "issue_main", "category": "weak_evidence", "severity": "warning", "chapter": 2, "description": "待核", "related_ids": ["char_main"], "evidence_ids": ["ev_shared"]}],
            "story_arcs": [{"id": "arc_main", "title": "主剧情", "chapter_start": 1, "chapter_end": 10, "parent_arc_id": None, "status": "active", "phase": "development", "event_ids": [], "entity_ids": ["char_main", "item_relic"], "turning_point_ids": [], "evidence_ids": ["ev_shared"]}],
        }
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            graph_path = root / "graph.json"
            dashboard = root / "dashboard.html"
            dump = root / "panels"
            graph_path.write_text(json.dumps(graph, ensure_ascii=False), encoding="utf-8")
            (root / "dashboard-views.json").write_text(json.dumps({"collections": [{"id": "arc_members", "label": "主剧情成员", "expression": {"arc": "arc_main"}, "display": {"primary": True, "order": 1}}]}, ensure_ascii=False), encoding="utf-8")
            (root / "style-observations.json").write_text(json.dumps({"observations": [{"id": "sty_1", "scope": "work", "dimension": "narrative", "claim": "测试叙事观察。", "chapter_start": 1, "chapter_end": 10, "stability": "contextual", "evidence_ids": ["ev_shared"], "counterexamples": [], "confidence": "inferred"}]}, ensure_ascii=False), encoding="utf-8")
            subprocess.run(
                [sys.executable, str(SCRIPTS / "build_dashboard.py"), "--graph", str(graph_path), "--output", str(dashboard)],
                check=True,
                capture_output=True,
                text=True,
            )
            html = dashboard.read_text(encoding="utf-8")
            self.assertIn("function entityReaderStats", html)
            self.assertIn("function warehouseReaderMeta", html)
            self.assertIn('data-warehouse-view="compact"', html)
            self.assertIn('id="warehouseFilter"', html)
            self.assertIn("所有者", html)
            self.assertIn("当前持有人", html)
            self.assertIn("使用者", html)
            self.assertIn("保管者", html)
            self.assertIn("分类关系泳道", html)
            self.assertNotIn("登场热度", html)
            self.assertNotIn("有机关系布局", html)
            self.assertNotIn("char_liu_yi", html)
            self.assertNotIn("char_tang_san", html)
            self.assertIn('id="arcs"', html)
            self.assertIn('id="collections"', html)
            self.assertIn('id="style"', html)
            self.assertIn('id="warehousePager"', html)
            self.assertIn("warehousePageSize=24", html)
            self.assertIn("story_arcs", html)
            self.assertIn("_collection_views", html)
            if shutil.which("node"):
                subprocess.run(
                    [sys.executable, str(SCRIPTS / "smoke_dashboard.py"), "--dashboard", str(dashboard), "--entity", "char_main", "--entity", "item_relic", "--dump-dir", str(dump)],
                    check=True,
                    capture_output=True,
                    text=True,
                )
                person = (dump / "char_main.html").read_text(encoding="utf-8")
                self.assertIn("可追溯证据", person)
                self.assertIn("待核问题", person)
                self.assertIn("完整变化历史", person)
                self.assertIn("<b>1</b><span>可追溯证据</span>", person)
                self.assertIn("<b>1</b><span>待核问题</span>", person)
                self.assertNotIn("undefined", person)
                subprocess.run(
                    [sys.executable, str(SCRIPTS / "verify_chapter_views.py"), "--run-dir", str(root), "--snapshot", "1", "--snapshot", "10", "--entity", "char_main", "--entity", "item_relic"],
                    check=True,
                    capture_output=True,
                    text=True,
                )


if __name__ == "__main__":
    unittest.main()
