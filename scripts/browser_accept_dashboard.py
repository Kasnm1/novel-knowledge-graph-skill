#!/usr/bin/env python3
"""Full acceptance pass: every panel, entity detail, chapter scrubbing, perf."""
import json
import statistics
import sys
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

CHROME = r"C:\Users\Kasumi\AppData\Local\ms-playwright\chromium-1243\chrome-win64\chrome.exe"
PANELS = ["overview", "graph", "repo", "foreshadowing", "collections", "achievements",
          "combat", "resources", "skills", "commitments", "knowledge", "foreshadowing",
          "levels", "rhythm", "romance", "intimacy", "mortality", "economy", "rules",
          "narrative", "issues"]


def main():
    html = Path(sys.argv[1]).resolve()
    out = Path(sys.argv[2])
    out.mkdir(parents=True, exist_ok=True)
    report = {"panels": {}, "errors": [], "perf": {}}
    with sync_playwright() as p:
        b = p.chromium.launch(executable_path=CHROME, args=["--hide-scrollbars"])
        pg = b.new_page(viewport={"width": 1600, "height": 1000})
        pg.on("pageerror", lambda e: report["errors"].append(f"pageerror: {str(e)[:200]}"))
        pg.on("console", lambda m: report["errors"].append(f"[{m.type}] {m.text[:200]}") if m.type == "error" else None)
        pg.goto(html.as_uri(), wait_until="load", timeout=120000)
        pg.wait_for_timeout(3000)

        tabs = pg.evaluate("Array.from(document.querySelectorAll('#tabs button')).map(b=>b.dataset.panel)")
        report["tabs"] = tabs
        for name in tabs:
            pg.evaluate(f"document.querySelector('#tabs button[data-panel={name}]').click()")
            pg.wait_for_timeout(700)
            info = pg.evaluate("""() => {
              const m = document.getElementById('main');
              return {len: m.innerText.length, text: m.innerText.slice(0, 160)};
            }""")
            report["panels"][name] = {"len": info["len"], "head": info["text"].replace("\n", " | ")[:120]}
            if info["len"] < 20:
                report["errors"].append(f"EMPTY PANEL: {name}")

        # entity detail at three chapters
        pg.evaluate("document.querySelector('#tabs button[data-panel=overview]').click()")
        pg.evaluate("showEntity('char_qin_chao')")
        pg.wait_for_timeout(1000)
        for ch in [1, 500, 999]:
            pg.evaluate(f"() => {{ const s=document.getElementById('ch'); s.value={ch}; s.dispatchEvent(new Event('input')); }}")
            pg.wait_for_timeout(600)
            d = pg.evaluate("""() => {
              const a = document.querySelector('aside.detail');
              const txt = a ? a.innerText : '';
              return {open: !!a && a.classList.contains('on'), len: txt.length, head: txt.slice(0,120).replace(/\\n/g,' | ')};
            }""")
            report.setdefault("entity_asof", {})[str(ch)] = d
            pg.screenshot(path=str(out / f"entity_ch{ch}.png"))

        # perf: 40 sequential slider inputs
        pg.evaluate("document.querySelector('#tabs button[data-panel=overview]').click()")
        times = pg.evaluate("""async () => {
          const s = document.getElementById('ch');
          const out = [];
          for (let c = 1; c <= 200; c += 5) {
            const t0 = performance.now();
            s.value = c;
            s.dispatchEvent(new Event('input'));
            await new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r)));
            out.push(performance.now() - t0);
          }
          return out;
        }""")
        times = sorted(times)
        report["perf"] = {
            "samples": len(times),
            "p50": round(statistics.median(times), 1),
            "p95": round(times[int(len(times) * 0.95) - 1], 1),
            "max": round(max(times), 1),
        }
        b.close()
    report["errors"] = report["errors"][:25]
    print(json.dumps(report, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
