from __future__ import annotations

import os
import shutil
import tempfile
import time
import unittest
from pathlib import Path

from build_reader_overlay import build as build_reader
from build_unified_dashboard import build_html, build_model
from enhance_unified_dashboard import enhance_html
from nkg.views.entity_profiles import build_entity_profiles
from nkg.views.quality import build_quality_summary

try:
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options
    from selenium.webdriver.common.by import By
except ImportError:
    webdriver = None


def detail_graph() -> dict:
    return {
        "metadata": {
            "title": "detail-fixture",
            "chapter_start": 1,
            "chapter_end": 6,
            "analyzed_chapters": [1, 2, 3, 4, 5, 6],
            "attribute_first_chapter": {"hero": {"职业": 2, "隐藏属性": 5}},
        },
        "entities": [
            {
                "id": "hero", "type": "character", "name": "主角", "first_chapter": 2,
                "attributes": {"职业": "剑士", "隐藏属性": "后期信息"}, "evidence_ids": ["e2", "e5"],
            },
            {"id": "ally", "type": "character", "name": "同伴", "first_chapter": 3, "attributes": {}, "evidence_ids": ["e3"]},
        ],
        "events": [
            {"id": "ev3", "type": "encounter", "chapter": 3, "title": "相遇", "description": "", "participant_ids": ["hero", "ally"], "evidence_ids": ["e3"]},
        ],
        "relations": [
            {"id": "r1", "source_id": "hero", "target_id": "ally", "relation_type": "friend_of", "valid_from": 3, "status": "active", "evidence_ids": ["e3"]},
        ],
        "state_changes": [
            {"id": "s4", "entity_id": "hero", "facet": "状态", "action": "changed", "chapter": 4, "before": "平静", "after": "警觉", "reason": "", "evidence_ids": ["e4"], "confidence": "explicit"},
        ],
        "evidence": [
            {"id": f"e{i}", "chapter": i, "quote": f"第{i}章证据文本足够长", "source_line_start": 1, "source_line_end": 1}
            for i in range(1, 7)
        ],
        "romance_routes": [], "intimate_acts": [], "level_conversions": [], "character_traits": [],
        "chapter_summaries": [], "item_roles": [], "story_arcs": [], "commitments": [],
        "foreshadowing": [], "review_issues": [],
    }


def display_hints() -> dict:
    return {
        "schema_version": 1,
        "profiles": {
            "hero": {
                "headlines": [{"text": "以剑术为主要行动方式", "valid_from": 2, "evidence_ids": ["e2"]}],
                "important_attributes": [
                    {"source_key": "职业", "label": "核心身份", "valid_from": 2},
                    {"source_key": "隐藏属性", "label": "后期重要属性", "valid_from": 5},
                ],
            }
        },
    }


class EntityProfileContractTests(unittest.TestCase):
    def test_ai_selects_importance_without_copying_fact_values(self):
        result = build_entity_profiles(detail_graph(), display_hints())
        profile = result["profiles"]["hero"]
        self.assertTrue(profile["ai_authored"])
        self.assertEqual(profile["first_chapter"], 2)
        self.assertEqual(profile["important_attributes"][0]["source_key"], "职业")
        self.assertNotIn("value", profile["important_attributes"][0])
        self.assertEqual(profile["important_attributes"][1]["valid_from"], 5)

    def test_unknown_display_evidence_is_auditable_not_a_story_fact(self):
        hints = display_hints()
        hints["profiles"]["hero"]["headlines"][0]["evidence_ids"] = ["missing"]
        result = build_entity_profiles(detail_graph(), hints)
        self.assertTrue(any(row["code"] == "unknown_display_evidence" for row in result["issues"]))
        self.assertTrue(result["derived_only"])

    def test_reader_contains_query_deep_link_support(self):
        source = build_reader({"chapters": [], "evidence": {}, "events": {}, "refs": {}}, "x")
        self.assertIn("URLSearchParams", source)
        self.assertIn("focused-evidence", source)
        self.assertIn("chapterForEvidence", source)

    def test_unified_dashboard_restores_light_reader_first_theme(self):
        source = build_html(build_model(detail_graph()))
        self.assertIn("color-scheme:light", source)
        self.assertIn("--accent:#6157d8", source)
        self.assertIn("感情 / 亲密", source)
        self.assertIn("entity-card", source)
        self.assertIn("radial-gradient", source)


class EntityDetailBrowserTests(unittest.TestCase):
    def setUp(self):
        required = os.environ.get("REQUIRE_BROWSER_TESTS") == "1"
        if webdriver is None:
            if required:
                self.fail("REQUIRE_BROWSER_TESTS=1 but selenium is not installed")
            self.skipTest("selenium not installed")
        chrome = os.environ.get("CHROME_BIN") or shutil.which("google-chrome") or shutil.which("google-chrome-stable") or shutil.which("chrome") or shutil.which("chromium")
        if not chrome:
            if required:
                self.fail("REQUIRE_BROWSER_TESTS=1 but Chrome/Chromium is not installed")
            self.skipTest("Chrome/Chromium not installed")
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        graph = detail_graph()
        profiles = build_entity_profiles(graph, display_hints())
        source = enhance_html(build_html(build_model(graph)), profiles, build_quality_summary(graph))
        page = root / "dashboard.html"
        page.write_text(source, encoding="utf-8")
        asset = Path(__file__).resolve().parent.parent / "assets" / "cytoscape-3.34.3.min.js"
        shutil.copy2(asset, root / asset.name)
        options = Options(); options.binary_location = chrome
        options.add_argument("--headless=new"); options.add_argument("--no-sandbox"); options.add_argument("--disable-dev-shm-usage"); options.add_argument("--window-size=1440,1000")
        self.driver = webdriver.Chrome(options=options)
        self.driver.get(page.as_uri())
        self.slider = self.driver.find_element(By.ID, "ch")

    def tearDown(self):
        if hasattr(self, "driver"): self.driver.quit()
        if hasattr(self, "tmp"): self.tmp.cleanup()

    def set_chapter(self, chapter: int) -> None:
        self.driver.execute_script("arguments[0].value=arguments[1]; arguments[0].dispatchEvent(new Event('input',{bubbles:true}));", self.slider, chapter)
        time.sleep(0.04)

    def open_tab(self, label: str) -> None:
        button = next(x for x in self.driver.find_elements(By.CSS_SELECTOR, "#tabs button") if x.text == label)
        button.click(); time.sleep(0.04)

    def open_first_entity(self) -> str:
        self.open_tab("仓库")
        self.driver.find_elements(By.CSS_SELECTOR, "#main [data-entity-id]")[0].click(); time.sleep(0.04)
        return self.driver.find_element(By.ID, "nkgEntityDrawer").text

    def test_entity_detail_makes_first_appearance_and_important_attributes_obvious(self):
        self.set_chapter(3)
        text = self.open_first_entity()
        self.assertIn("首次出现", text)
        self.assertIn("第 2 章", text)
        self.assertIn("重要属性", text)
        self.assertIn("核心身份", text)
        self.assertIn("剑士", text)
        self.assertNotIn("后期重要属性", text)
        self.assertNotIn("后期信息", text)

        self.driver.execute_script("nkgCloseEntity()")
        self.set_chapter(6)
        text = self.open_first_entity()
        self.assertIn("后期重要属性", text)
        self.assertIn("后期信息", text)

    def test_snapshot_diff_and_quality_are_in_same_dashboard(self):
        labels = [x.text for x in self.driver.find_elements(By.CSS_SELECTOR, "#tabs button")]
        self.assertIn("变化", labels)
        self.assertIn("感情 / 亲密", labels)
        self.open_tab("变化")
        self.assertIn("章节变化", self.driver.find_element(By.ID, "main").text)
        self.open_tab("审计")
        audit = self.driver.find_element(By.ID, "main").text
        self.assertIn("证据引用覆盖", audit)
        self.assertIn("时序来源缺口", audit)


if __name__ == "__main__":
    unittest.main()
