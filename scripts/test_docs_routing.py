"""The reference routing stays loadable and small, and the docs name only scripts that exist."""
from __future__ import annotations

import json
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REFS = ROOT / "references"
# Names in the docs that are not repository scripts: examples, a worker's own temp file.
NOT_SCRIPTS = {"_tmp_gen_fNN.py"}


def lines(path: Path) -> int:
    return len(path.read_text(encoding="utf-8").splitlines()) if path.suffix == ".md" else 0


class ReferenceRoutingTests(unittest.TestCase):
    def setUp(self):
        self.routing = json.loads((REFS / "reference-routing.json").read_text(encoding="utf-8"))

    def test_every_routed_file_exists_and_each_mode_stays_within_budget(self):
        always = sum(lines(REFS / f) for f in self.routing["always"])
        for mode, files in self.routing["modes"].items():
            for name in files:
                self.assertTrue((REFS / name).is_file(), f"{mode}: {name} missing")
            total = always + sum(lines(REFS / f) for f in files)
            self.assertLessEqual(total, self.routing["max_lines_per_mode"], mode)
        for name in self.routing["lookup"]:
            self.assertTrue((REFS / name).is_file(), f"lookup: {name} missing")

    def test_skill_md_stays_a_router(self):
        self.assertLessEqual(lines(ROOT / "SKILL.md"), 170)


class DocScriptReferenceTests(unittest.TestCase):
    def test_docs_name_only_existing_scripts(self):
        known = {p.name for p in (ROOT / "scripts").rglob("*.py")}
        docs = [ROOT / "SKILL.md", ROOT / "README.md", *REFS.glob("*.md")]
        missing = sorted({f"{doc.name}: {name}" for doc in docs
                          for name in re.findall(r"[A-Za-z_]+\.py", doc.read_text(encoding="utf-8"))
                          if name not in known and name not in NOT_SCRIPTS})
        self.assertEqual(missing, [])


if __name__ == "__main__":
    unittest.main()
