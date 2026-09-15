from __future__ import annotations

import os
import shutil
import tempfile
import time
import unittest
from pathlib import Path

from build_unified_dashboard import build_html, build_model
from test_final_delivery import FUTURE, fixture_graph

try:
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options
    from selenium.webdriver.common.by import By
except ImportError:  # Local stdlib-only runs may skip; CI requires Selenium.
    webdriver = None


class BrowserAcceptanceTests(unittest.TestCase):
    def setUp(self):
        required = os.environ.get("REQUIRE_BROWSER_TESTS") == "1"
        if webdriver is None:
            if required:
                self.fail("REQUIRE_BROWSER_TESTS=1 but selenium is not installed")
            self.skipTest("selenium not installed")
        chrome = (
            os.environ.get("CHROME_BIN")
            or shutil.which("google-chrome")
            or shutil.which("google-chrome-stable")
            or shutil.which("chrome")
            or shutil.which("chromium")
            or shutil.which("chromium-browser")
        )
        if not chrome:
            if required:
                self.fail("REQUIRE_BROWSER_TESTS=1 but Chrome/Chromium is not installed")
            self.skipTest("Chrome/Chromium not installed")
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        model = build_model(fixture_graph(), gap_threshold=2)
        page = root / "dashboard.html"
        page.write_text(build_html(model), encoding="utf-8")
        asset = Path(__file__).resolve().parent.parent / "assets" / "cytoscape-3.34.3.min.js"
        shutil.copy2(asset, root / asset.name)
        options = Options()
        options.binary_location = chrome
        options.add_argument("--headless=new")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--window-size=1440,1000")
        options.set_capability("goog:loggingPrefs", {"browser": "ALL"})
        self.driver = webdriver.Chrome(options=options)
        self.driver.get(page.as_uri())
        self.slider = self.driver.find_element(By.ID, "ch")

    def tearDown(self):
        if hasattr(self, "driver"):
            self.driver.quit()
        if hasattr(self, "tmp"):
            self.tmp.cleanup()

    def set_chapter(self, chapter: int) -> None:
        self.driver.execute_script(
            "arguments[0].value=arguments[1]; arguments[0].dispatchEvent(new Event('input',{bubbles:true}));",
            self.slider,
            chapter,
        )
        time.sleep(0.03)
        self.assertEqual(self.driver.find_element(By.ID, "cl").text, str(chapter))

    def open_tab(self, label: str) -> str:
        buttons = self.driver.find_elements(By.CSS_SELECTOR, "#tabs button")
        target = next((button for button in buttons if button.text == label), None)
        self.assertIsNotNone(target, f"missing tab {label}")
        target.click()
        time.sleep(0.02)
        return self.driver.find_element(By.ID, "main").text

    def test_shared_slider_keeps_all_panels_on_same_snapshot(self):
        # Exercise non-monotonic slider movement; stale cached final state must not survive.
        for chapter in (1, 2, 8, 4, 7, 3, 5):
            self.set_chapter(chapter)
            self.assertIn("统一快照", self.driver.find_element(By.ID, "state").text)
            for tab in ("总览", "仓库", "剧情线", "集合", "承诺", "资源", "技能", "写法"):
                self.open_tab(tab)
            self.assertEqual(self.driver.find_element(By.ID, "cl").text, str(chapter))

        self.set_chapter(5)
        commitments = self.open_tab("承诺")
        self.assertIn("active", commitments)
        self.assertNotIn("fulfilled", commitments)
        resources = self.open_tab("资源")
        self.assertIn("1", resources)
        self.assertNotIn("99", resources)
        skills = self.open_tab("技能")
        self.assertNotIn("早期名", skills)  # holder relation begins at chapter 8
        narrative = self.open_tab("写法")
        self.assertNotIn(FUTURE, narrative)
        repository = self.open_tab("仓库")
        self.assertNotIn(FUTURE, repository)
        self.assertNotIn("最终正式名", repository)

        self.set_chapter(8)
        self.assertIn("fulfilled", self.open_tab("承诺"))
        self.assertIn("99", self.open_tab("资源"))
        self.assertIn("最终正式名", self.open_tab("技能"))
        self.assertIn(FUTURE, self.open_tab("写法"))
        self.assertIn("最终正式名", self.open_tab("仓库"))

        severe = [row for row in self.driver.get_log("browser") if row.get("level") == "SEVERE"]
        self.assertEqual(severe, [], severe)

    def test_cutoff_dashboard_source_has_no_future_marker(self):
        model = build_model(fixture_graph(), gap_threshold=2, cutoff=5)
        source = build_html(model)
        self.assertNotIn(FUTURE, source)
        self.assertNotIn("最终正式名", source)


if __name__ == "__main__":
    unittest.main()
