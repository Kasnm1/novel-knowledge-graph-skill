#!/usr/bin/env python3
"""Measure the first-pass cost of a chapter update, and test the obvious causes for it.

Round 19 found this effect while decomposing the difference between the two perf probes in
`accept_atlas.py`, and could not name its mechanism. The measurement is kept as a script so
the next attempt starts from an instrument rather than from six ad-hoc probes.

The effect, measured on `runs/book-9d37baf0822f/dashboard.html`:

    the first pass in a session that paints these chapters   js p50  99.7 / 118.6 / 125.7 ms
    every pass after that                                    js p50  70.1 / 71.7 / 74.4 /
                                                                     76.0 / 78.9 / 79.4 /
                                                                     81.4 / 82.7 ms

Three candidate causes were REFUTED by this instrument:

  * `buildSidebar()` — 0.1 ms, 1.4% of a frame (so it is not the omitted sidebar);
  * the projection cache — `CACHE.clear()` before every step makes the pass *faster*
    (78.9 against 116.0 ms), so it is not projection hits;
  * the markup cache — clearing `MARKUP_CACHE` does not bring the cost back
    (82.7 against 125.7 ms).

and the projection table's size axis disagreed between two probes, so it is not established
either. **The effect is real; the mechanism is open.** This script reports the effect and
runs the three cache manipulations; it does not claim a cause.

Reaching into `CACHE` / `MARKUP_CACHE` couples this probe to the renderer's internals: if
those names change, the corresponding flag reports `null` instead of silently measuring
nothing. Treat a `null` there as "this test did not run", never as "the cache is not it".

Usage:

    python probe_atlas_first_pass.py <atlas.html> <out.json> [--steps 10]

Nothing here asserts anything about the build; it produces a JSON record.
"""
from __future__ import annotations

import argparse
import ctypes
import json
import statistics
import sys
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

CHROME = r"C:\Users\Kasumi\AppData\Local\ms-playwright\chromium-1243\chrome-win64\chrome.exe"


class MEMORYSTATUSEX(ctypes.Structure):
    _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
                ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
                ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong),
                ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]


def machine() -> dict:
    """Contract 5.5: a pass without an environment fingerprint is not a guarantee."""
    m = MEMORYSTATUSEX()
    m.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
    ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(m))
    return {"when": time.strftime("%Y-%m-%d %H:%M:%S"), "mem_load_pct": m.dwMemoryLoad,
            "mem_total_gb": round(m.ullTotalPhys / 2 ** 30, 2),
            "mem_avail_gb": round(m.ullAvailPhys / 2 ** 30, 2)}


# The reset `accept_atlas.py` performs before its scrub: the earlier gates leave debris and
# none of it is what a chapter update looks like.
RESET = """() => {
  for (const row of document.querySelectorAll('#zone-legend .row.off')){
    const eye = row.querySelector('[data-eye]');
    if (eye) eye.click();
  }
  if (CM.open) closePalette();
  closeDrawer();
  window.scrollTo({ top: 0, behavior: 'instant' });
  FILTER.chapters = '';
  FILTER.things = { item: 'all', skill: 'all', concept: 'all',
                    item_sort: 'chapter', skill_sort: 'chapter', concept_sort: 'chapter' };
  PAGE.chapters = 1;
  setChapter(MAX_CH, true);
}"""

# One update per animation frame, stepping across the whole range, recording both spans and
# the two cache sizes. `%s` runs before each step (the cache manipulation under test).
STEPS = """([n, pre]) => new Promise(res => {
  const seq = [];
  for (let s = 0; s < n; s++) seq.push(Math.round(MIN_CH + (MAX_CH - MIN_CH) * (s / (n - 1))));
  const out = [];
  let i = 0, prev = null;
  const step = (ts) => {
    if (prev !== null) out[out.length - 1].interval = ts - prev;
    if (i >= seq.length) return res(out);
    const c = seq[i++];
    prev = ts;
    const pre_fn = { none: () => {}, cache: () => CACHE.clear(),
                     markup: () => MARKUP_CACHE.clear() }[pre];
    pre_fn();
    const t = performance.now();
    setChapter(c, true);
    out.push({ ch: c, js: performance.now() - t, interval: null,
               cache: CACHE.size, markup: MARKUP_CACHE.size });
    requestAnimationFrame(step);
  };
  requestAnimationFrame(step);
})"""

TAIL = """() => new Promise(res => {
  const seq = [];
  const lo = Math.max(MIN_CH, MAX_CH - 40);
  for (let c = MAX_CH - 5; c > lo; c--) seq.push(c);
  let i = 0;
  const step = () => {
    if (i >= seq.length) return res();
    setChapter(seq[i++], true);
    requestAnimationFrame(step);
  };
  requestAnimationFrame(step);
})"""

CONDITIONS = [("pass1_first_ever", "none"),
              ("pass2_repeat", "none"),
              ("pass3_after_cache_clear", "cache"),
              ("pass4_after_markup_clear", "markup"),
              ("pass5_repeat_after_that", "none")]


def stat(xs):
    xs = sorted(x for x in xs if x is not None)
    if not xs:
        return {"n": 0, "p50": None, "p95": None, "max": None}
    return {"n": len(xs), "p50": round(statistics.median(xs), 1),
            "p95": round(xs[int(len(xs) * 0.95) - 1], 1), "max": round(max(xs), 1)}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("atlas", type=Path)
    ap.add_argument("out", type=Path)
    ap.add_argument("--steps", type=int, default=10)
    ap.add_argument("--settle-ms", type=int, default=400)
    args = ap.parse_args()

    rep = {"atlas": str(args.atlas), "atlas_bytes": args.atlas.stat().st_size,
           "machine": machine(), "steps": args.steps}
    with sync_playwright() as p:
        b = p.chromium.launch(executable_path=CHROME, args=["--hide-scrollbars"])
        pg = b.new_page(viewport={"width": 1680, "height": 1050})
        pg.goto(args.atlas.as_uri(), wait_until="load")
        pg.wait_for_timeout(2500)
        rep["range"] = [pg.evaluate("MIN_CH"), pg.evaluate("MAX_CH")]
        # Is the probe even able to reach the caches it manipulates?
        rep["cache_reachable"] = pg.evaluate(
            "() => ({cache: typeof CACHE !== 'undefined', markup: typeof MARKUP_CACHE !== 'undefined',"
            " snap_limit: typeof SNAP_LIMIT === 'number' ? SNAP_LIMIT : null,"
            " markup_cap: 160})")
        pg.evaluate(RESET)
        pg.wait_for_timeout(500)
        # warm the page the way the gate does, so pass 1 is not a cold session
        for _ in range(2):
            pg.evaluate(TAIL)
            pg.wait_for_timeout(args.settle_ms)
        rep["markup_after_tail_warmup"] = pg.evaluate("MARKUP_CACHE.size")

        for label, pre in CONDITIONS:
            rows = pg.evaluate(STEPS, [args.steps, pre])
            rep[label] = {"pre": pre,
                          "js": stat([r["js"] for r in rows]),
                          "interval": stat([r["interval"] for r in rows]),
                          "cache_sizes": [r["cache"] for r in rows],
                          "markup_sizes": [r["markup"] for r in rows],
                          "per_step": [[r["ch"], round(r["js"], 1)] for r in rows]}
            pg.wait_for_timeout(args.settle_ms)
        b.close()

    args.out.write_text(json.dumps(rep, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"atlas {rep['atlas']}  range {rep['range']}  steps {rep['steps']}")
    print(f"caches reachable: {rep['cache_reachable']}")
    print(f"markup after tail warm-up: {rep['markup_after_tail_warmup']}")
    for label, _ in CONDITIONS:
        v = rep[label]
        print(f"{label:26s} js={json.dumps(v['js'], ensure_ascii=False)} "
              f"interval p50={v['interval']['p50']}")
        print(f"    cache {v['cache_sizes'][:2]}..{v['cache_sizes'][-1]}   "
              f"markup {v['markup_sizes'][:2]}..{v['markup_sizes'][-1]}")
    print("wrote", args.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
