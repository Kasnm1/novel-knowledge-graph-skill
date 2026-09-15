#!/usr/bin/env python3
"""Smoke-test a generated dashboard by executing its real renderer in Node.

The dashboard is a single self-contained HTML file whose logic lives in an inline
script. That makes "does the entity panel actually render correctly" hard to check
without a browser. This script extracts the real script, runs it under a minimal DOM
and Cytoscape stub, calls the real `showEntity()` for the entities you name, and
asserts on the produced HTML.

It catches the two failure modes that static grepping misses:

- a JS helper that was declared but silently lost during editing, so `value()`
  falls through to a raw `<pre>{...JSON...}</pre>` dump;
- an internal English structure key or attribute key reaching the rendered panel.

Usage:

    python scripts/smoke_dashboard.py --dashboard <run-dir>/dashboard.html \
        --entity creature_tianmeng_bingcan --entity axis_hunli_level

Requires `node` on PATH. Exits 0 when every check passes, 1 otherwise.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


APP_SCRIPT_RE = re.compile(r"<script(?![^>]*\bsrc=)[^>]*>(.*?)</script>", re.S)

# JSON-key form, so an HTML attribute such as type="range" is not a false positive.
LEAK_PATTERNS = {
    "raw JSON dump": re.compile(r"<pre>"),
    "level attribute key": re.compile(r"higher_is_more_advanced"),
    "attribute key": re.compile(r'"(?:unit|min|max|tiers|range|label|value|definition|note|gender|martial_soul|attribute|type|category|species|origin|race|tier)"\s*:'),
}

EXPORT_LINE = """
globalThis.__report = (function () {
  const out = { entities: {}, errors: [] };
  const probes = PROBE_IDS;
  for (const id of probes) {
    try {
      showEntity(id);
      out.entities[id] = { html: document.__captured, chapter: chapter };
    } catch (err) {
      out.entities[id] = { error: String(err) };
    }
  }
  out.helpers = {
    isAgent: typeof isAgent,
    levelShape: typeof levelShape,
    levelText: typeof levelText,
    attrText: typeof attrText,
    axisPanel: typeof axisPanel,
  };
  return out;
})();
"""

HARNESS_TEMPLATE = """const fs = require('fs');
global.document = (() => {
  let captured = '';
  const stub = () => ({
    innerHTML: '', textContent: '', value: '', disabled: false, dataset: {}, style: {},
    classList: { toggle() {}, add() {}, remove() {}, contains() { return false; } },
    setAttribute() {}, getAttribute() { return null; },
    addEventListener() {}, removeEventListener() {}, setPointerCapture() {},
    getBoundingClientRect: () => ({ width: 380, height: 600, top: 0, left: 0 }),
    querySelectorAll: () => [], querySelector: () => stub(), appendChild() {},
  });
  return {
    get __captured() { return captured; },
    body: stub(),
    querySelector: (sel) => (sel === '#detail'
      ? { set innerHTML(v) { captured = v; }, get innerHTML() { return captured; } }
      : stub()),
    querySelectorAll: () => [],
    createElement: () => stub(),
    addEventListener() {},
  };
})();
global.window = { devicePixelRatio: 1, innerWidth: 1280, addEventListener() {} };
global.location = { search: '' };
function cyProxy() {
  const fn = function () { return cyProxy(); };
  return new Proxy(fn, {
    get(target, prop) {
      if (prop === 'length') return 0;
      if (prop === 'forEach') return () => {};
      if (prop === 'layout') return () => ({ run() {} });
      if (prop === 'getElementById') return () => cyProxy();
      if (prop === 'visible') return () => false;
      if (prop === 'data') return () => '';
      if (prop === 'toString' || prop === Symbol.toPrimitive) return () => '';
      return cyProxy();
    },
    apply() { return cyProxy(); },
  });
}
global.cytoscape = function () { return cyProxy(); };
global.cytoscape.use = () => {};
const PROBE_IDS = __PROBES__;
eval(fs.readFileSync('app.js', 'utf8'));
fs.writeFileSync('report.json', JSON.stringify(globalThis.__report), 'utf8');
process.exit(0);
"""


def extract_app_script(html: str) -> str:
    scripts = APP_SCRIPT_RE.findall(html)
    for script in reversed(scripts):
        if "const graph=" in script:
            return script
    raise SystemExit("no inline dashboard script found (expected one containing 'const graph=')")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dashboard", required=True, type=Path)
    parser.add_argument("--entity", action="append", default=[], help="Entity ID to open and inspect; repeat as needed")
    parser.add_argument("--json", type=Path, help="Optional path to write the machine-readable report")
    parser.add_argument("--dump-dir", type=Path, help="Optional directory to write each entity's rendered HTML into, for review")
    args = parser.parse_args()

    if shutil.which("node") is None:
        raise SystemExit("node is required for the dashboard smoke test but was not found on PATH")

    html = args.dashboard.resolve().read_text(encoding="utf-8")
    app = extract_app_script(html)
    probes = args.entity or []
    if not probes:
        raise SystemExit("pass at least one --entity to inspect")

    with tempfile.TemporaryDirectory() as tmp:
        work = Path(tmp)
        (work / "app.js").write_text(app + EXPORT_LINE, encoding="utf-8")
        (work / "harness.js").write_text(
            HARNESS_TEMPLATE.replace("__PROBES__", json.dumps(probes)), encoding="utf-8"
        )
        proc = subprocess.run(
            ["node", "harness.js"], cwd=work, capture_output=True, text=True, encoding="utf-8"
        )
        if proc.returncode != 0:
            print(proc.stdout or "", file=sys.stderr)
            print(proc.stderr or "", file=sys.stderr)
            raise SystemExit(f"harness exited {proc.returncode}")
        report = json.loads((work / "report.json").read_text(encoding="utf-8"))

    problems: list[str] = []
    print(f"# dashboard smoke test: {args.dashboard}")
    print(f"helpers: {report['helpers']}")
    for name, kind in report["helpers"].items():
        if kind != "function":
            problems.append(f"helper {name} is {kind}, expected function (a lost edit renders raw JSON)")
    print()

    for entity_id, result in report["entities"].items():
        if "error" in result:
            problems.append(f"{entity_id}: renderer threw {result['error']}")
            print(f"- {entity_id}: THREW {result['error']}")
            continue
        body = result["html"]
        found = [label for label, pattern in LEAK_PATTERNS.items() if pattern.search(body)]
        if found:
            problems.append(f"{entity_id}: leaked {', '.join(found)}")
        print(f"- {entity_id}: {len(body)} chars at chapter {result['chapter']} | leaks: {found or 'none'}")
    print()

    if problems:
        print("FAIL")
        for item in problems:
            print(f"  - {item}")
    else:
        print("PASS")
    if args.json:
        args.json.resolve().write_text(
            json.dumps({"problems": problems, "report": report}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    if args.dump_dir:
        dump = args.dump_dir.resolve()
        dump.mkdir(parents=True, exist_ok=True)
        for entity_id, result in report["entities"].items():
            if "html" in result:
                (dump / f"{entity_id}.html").write_text(result["html"], encoding="utf-8")
        print(f"\ndumped {len(report['entities'])} panel(s) to {dump}")
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
