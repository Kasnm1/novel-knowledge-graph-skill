"""The reader app opens every entry without browser errors, follows the slider and honours the spoiler lock."""
from __future__ import annotations

import os
import shutil
import tempfile
import time
import unittest
from pathlib import Path

from build_reader_dashboard import APP, inject
from nkg.views.reader_model import build_reader_model
from testing_fixtures import FUTURE, fixture_graph

try:
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options
    from selenium.webdriver.common.by import By
except ImportError:  # local stdlib-only runs may skip; CI requires Selenium
    webdriver = None

ROUTES = ["chapter", "story", "people", "relations", "world/factions", "world/map", "world/levels", "threads"]


class ReaderAppBrowserTests(unittest.TestCase):
    def setUp(self):
        required = os.environ.get("REQUIRE_BROWSER_TESTS") == "1"
        chrome = os.environ.get("CHROME_BIN") or next(
            (p for p in map(shutil.which, ("google-chrome", "google-chrome-stable", "chrome", "chromium", "chromium-browser")) if p), None)
        if webdriver is None or not chrome:
            if required:
                self.fail("REQUIRE_BROWSER_TESTS=1 but selenium or Chrome is missing")
            self.skipTest("selenium or Chrome not installed")
        self.tmp = tempfile.TemporaryDirectory()
        self.page = Path(self.tmp.name) / "dashboard.html"
        self.model = build_reader_model(fixture_graph())
        self.page.write_text(inject(APP.read_text(encoding="utf-8"), self.model), encoding="utf-8")
        options = Options()
        options.binary_location = chrome
        for arg in ("--headless=new", "--no-sandbox", "--disable-dev-shm-usage", "--window-size=1440,1000"):
            options.add_argument(arg)
        options.set_capability("goog:loggingPrefs", {"browser": "ALL"})
        self.driver = webdriver.Chrome(options=options)

    def tearDown(self):
        if hasattr(self, "driver"):
            self.driver.quit()
        if hasattr(self, "tmp"):
            self.tmp.cleanup()

    def open(self, route: str, chapter: int) -> None:
        self.driver.get(f"{self.page.as_uri()}#/{route}?c={chapter}")
        time.sleep(0.6)

    def severe(self) -> list[str]:
        return [e["message"] for e in self.driver.get_log("browser") if e["level"] == "SEVERE"]

    def test_every_entry_renders_without_errors(self):
        last = self.model["meta"]["last"]
        for route in ROUTES:
            self.open(route, last)
            main = self.driver.find_element(By.CSS_SELECTOR, "main.main")
            self.assertTrue(main.text.strip(), route)
        self.assertEqual(self.severe(), [])

    def test_early_chapter_shows_no_future_content(self):
        first = self.model["meta"]["first"]
        for route in ("chapter", "people", "threads"):
            self.open(route, first)
            self.assertNotIn(FUTURE, self.driver.find_element(By.TAG_NAME, "body").text, route)

    def test_spoiler_lock_caps_the_slider(self):
        chapters = [c["n"] for c in self.model["chapters"]]
        self.open("chapter", chapters[0])
        self.driver.find_element(By.CSS_SELECTOR, ".lock-btn").click()
        self.driver.get(f"{self.page.as_uri()}#/chapter?c={chapters[-1]}")
        time.sleep(0.6)
        self.assertIn(f"c={chapters[0]}", self.driver.current_url + self.driver.execute_script("return location.hash"))
        self.assertNotIn(FUTURE, self.driver.find_element(By.TAG_NAME, "body").text)


if __name__ == "__main__":
    unittest.main()
