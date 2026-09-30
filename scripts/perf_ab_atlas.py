"""A/B performance harness for the atlas: is a measured difference real, or is it the instrument?

Run this BEFORE calling any performance number a regression. A cross-version comparison needs
two things that a single measurement cannot give you:

  1. the within-artifact spread of this measurement (the noise floor). Measured on this project:
     the same artifact, same session, four consecutive rounds -> p50 spread 1.9 ms under the
     protocol below, but 10.8 ms when the protocol is sloppy (see 2 and 3). A 12.5 ms
     cross-version difference means nothing until you know which of those you are looking at.
  2. a discarded session warm-up. The session's first measurement describes V8 still compiling
     the artifact, not the artifact. Leaving it in produced a 136.8 ms p95 outlier and, in one
     revision, a 4.7 ms "effect" that vanished under a tighter protocol.
  3. alternating order (ABBA). If A is always measured first in a round, any within-round drift
     is charged to A by construction. That too produced a phantom effect.

Variant B is derived from A, never hand-made, and the derivation is asserted to be the *only*
edit: every `--replace OLD NEW` pair must apply exactly the expected number of times, and
re-applying the pairs to A must reproduce B byte for byte. Two traps are recorded here because
both were hit:

  * counting differing positions with `zip(a, b)` on two strings of DIFFERENT length is
    meaningless — every position past the first edit is misaligned and the count comes out in
    the millions (measured: 6,578,998). Use the arithmetic identity instead (the derivation
    assertion above).
  * a regex that rewrites only the first occurrence per declaration under-counts. Replacing a
    token inside `transition:background X,color X` needs a plain full `str.replace`, and the
    count must be asserted (measured: 33 found by regex, 46 actually present).

Usage:
  perf_ab_atlas.py <A.html> --replace "var(--t-fast) var(--ease)" ".12s" [--rounds 4]
  perf_ab_atlas.py <A.html> --b <B.html> [--rounds 4]

Pass a byte-identical copy as `--b` to turn this into a pure noise-floor measurement: |A-B| then
describes the instrument, not any code. Do that before trusting any budget that is asserted on a
single reading of one of these statistics — a budget is only meaningful if the statistic it is
asserted on moves less than the margin it leaves. The summary reports the spread for p50, p95 and
max separately, because they do not converge together: this project measured one build's drag p95
at 140.7 / 127.6 / 115.3 / 80.4 / 68.1 ms across five runs in one session while its p50 barely
moved, i.e. the tail converges last and a budget read off the tail is read off the slowest
converging quantity.

Prints, per round, drag p50/p95/max and jump p50/p95, plus the machine memory fingerprint, and
ends with |A-B| against the largest within-artifact spread. Exit code is 0 either way — this
harness measures, it does not judge; read the last lines.

Run standalone. No other browser instance may be open (see the acceptance protocol).
"""
import argparse
import ctypes
import pathlib
import statistics
import sys
import time

from playwright.sync_api import sync_playwright

DEFAULT_CHROME = r"C:\Users\Kasumi\AppData\Local\ms-playwright\chromium-1243\chrome-win64\chrome.exe"

# Reported separately and never averaged together: p50, p95 and max do not converge at the same
# rate, so a spread quoted for one of them says nothing about the others.
STATS = ("p50", "p95", "max")


class MEMSTATUS(ctypes.Structure):
    _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
                ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
                ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong),
                ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]


def machine():
    """The same fingerprint `accept_atlas.py` writes into `accept.json`.

    A baseline without it is not a baseline: this project's 2026-09-19 `accept.json` recorded
    `machine: null`, which is why a later 12.5 ms difference could not be attributed to a
    version at all.
    """
    m = MEMSTATUS()
    m.dwLength = ctypes.sizeof(MEMSTATUS)
    ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(m))
    return {"load_pct": m.dwMemoryLoad, "total_gb": round(m.ullTotalPhys / 2 ** 30, 1),
            "avail_gb": round(m.ullAvailPhys / 2 ** 30, 2)}


# The measurement sequence is copied from `accept_atlas.py` verbatim (reset -> two warm-up
# passes -> drag frames -> 10 isolated `setChapter` steps) so the numbers stay comparable with
# the gate's own.
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
WARM = """() => new Promise(res => {
  const seq = [];
  for (let c = MAX_CH - 5; c > MAX_CH - 40; c--) seq.push(c);
  let i = 0;
  const step = () => {
    if (i >= seq.length) return res();
    render(seq[i++]);
    requestAnimationFrame(step);
  };
  requestAnimationFrame(step);
})"""
DRAG = """() => new Promise(res => {
  const frames = [];
  const lo = Math.max(MIN_CH, MAX_CH - 40);
  const seq = [];
  for (let c = MAX_CH - 5; c > lo; c--) seq.push(c);
  let i = 0;
  const step = () => {
    if (i >= seq.length) return res(frames);
    const t = performance.now();
    render(seq[i++]);
    frames.push(performance.now() - t);
    requestAnimationFrame(step);
  };
  requestAnimationFrame(step);
})"""
JUMP = """(ch) => {
  const t = performance.now();
  setChapter(ch, true);
  return performance.now() - t;
}"""


def build_variant_b(a_path, b_path, pairs, work):
    """Derive B from A by full-string replacement, and assert the derivation is the only edit."""
    raw = a_path.read_bytes()
    a = work / "A.html"
    a.write_bytes(raw)
    text = raw.decode("utf-8")
    new = text
    for old, repl in pairs:
        n = new.count(old)
        assert n > 0, f"`--replace {old!r}` matched nothing in A"
        new = new.replace(old, repl)
        print(f"  derivation: {old!r} -> {repl!r} applied {n} time(s)")
    assert new != text, "the derivation changed nothing — A and B would be the same file"
    # The only edit is the declared one. Re-applying the pairs to A must reproduce B exactly;
    # do NOT try to prove it by diffing positions (see the module docstring).
    check = text
    for old, repl in pairs:
        check = check.replace(old, repl)
    assert check == new, "the derivation was not the only edit"
    b = work / "B.html"
    b.write_bytes(new.encode("utf-8"))
    print(f"variant B: {len(raw)} -> {len(new.encode('utf-8'))} bytes, derived from A by "
          f"{len(pairs)} declared replacement(s)")
    return a, b


def measure(pg, path, label):
    t0 = time.time()
    pg.goto(path.as_uri(), wait_until="load", timeout=180000)
    pg.wait_for_timeout(2500)
    ready = pg.evaluate("window.__atlasReady === true")
    pg.evaluate(RESET)
    pg.wait_for_timeout(500)
    for _ in range(2):
        pg.evaluate(WARM)
        pg.wait_for_timeout(400)
    frames = pg.evaluate(DRAG)
    warm = frames[1:] or frames
    stamps = []
    for step in range(10):
        ch = int(pg.evaluate("MIN_CH + (MAX_CH - MIN_CH) * " + str(step / 9.0)))
        stamps.append(pg.evaluate(JUMP, ch))
    return {
        "label": label, "ready": ready, "load_s": round(time.time() - t0, 1),
        "drag": {"n": len(warm), "p50": round(statistics.median(warm), 1),
                 "p95": round(sorted(warm)[min(len(warm) - 1, int(len(warm) * 0.95))], 1),
                 "max": round(max(warm), 1)},
        "jump": {"p50": round(statistics.median(stamps), 1),
                 "p95": round(sorted(stamps)[int(len(stamps) * 0.95) - 1], 1),
                 "max": round(max(stamps), 1)},
        "machine": machine(),
    }


def main():
    ap = argparse.ArgumentParser(description="A/B the atlas artifact against a derived variant.")
    ap.add_argument("a", help="the artifact as shipped (variant A)")
    ap.add_argument("--b", help="a pre-made variant B; omit to derive one with --replace")
    ap.add_argument("--replace", nargs=2, action="append", default=[], metavar=("OLD", "NEW"),
                    help="derivation step for variant B; repeatable")
    ap.add_argument("--rounds", type=int, default=4, help="ABBA rounds (default 4)")
    ap.add_argument("--work", help="scratch dir for A.html/B.html (default: <A dir>/_ab)")
    ap.add_argument("--chrome", default=DEFAULT_CHROME)
    args = ap.parse_args()

    a_src = pathlib.Path(args.a).resolve()
    assert a_src.is_file(), f"no such artifact: {a_src}"
    work = pathlib.Path(args.work).resolve() if args.work else a_src.parent / "_ab"
    work.mkdir(parents=True, exist_ok=True)

    if args.b:
        b_src = pathlib.Path(args.b).resolve()
        assert b_src.is_file(), f"no such variant: {b_src}"
        a, b = work / "A.html", work / "B.html"
        a.write_bytes(a_src.read_bytes())
        b.write_bytes(b_src.read_bytes())
        print(f"variant B: supplied ({b_src.name}), {len(b.read_bytes())} bytes")
    else:
        assert args.replace, "give --b, or --replace OLD NEW to derive variant B from A"
        a, b = build_variant_b(a_src, work / "B.html", args.replace, work)

    rows = []
    with sync_playwright() as p:
        br = p.chromium.launch(executable_path=args.chrome, args=["--hide-scrollbars"])
        pg = br.new_page(viewport={"width": 1680, "height": 1050})
        pg.set_default_timeout(120000)
        print("  session warm-up (discarded) ...")
        measure(pg, a, "warmup")
        for r in range(1, args.rounds + 1):
            order = ((a, "A"), (b, "B")) if r % 2 else ((b, "B"), (a, "A"))
            for path, label in order:
                got = measure(pg, path, label)
                got["round"] = r
                rows.append(got)
                print(f"  r{r} {label:<3} drag p50={got['drag']['p50']:>6} "
                      f"p95={got['drag']['p95']:>6} max={got['drag']['max']:>6} | "
                      f"jump p50={got['jump']['p50']:>6} p95={got['jump']['p95']:>6} | "
                      f"mem {got['machine']['load_pct']}% "
                      f"{got['machine']['avail_gb']}GB avail")
        br.close()

    print()
    stats = {}
    for label in ("A", "B"):
        sel = [r for r in rows if r["label"] == label]
        stats[label] = {}
        for key in ("drag", "jump"):
            stats[label][key] = {}
            for stat in STATS:
                vals = [r[key][stat] for r in sel]
                stats[label][key][stat] = (statistics.mean(vals), max(vals) - min(vals))
                print(f"{label} {key:<5} {stat:<4} per round = {vals}  "
                      f"spread={max(vals) - min(vals):.1f} ms  mean={statistics.mean(vals):.1f}")
    print()
    for key in ("drag", "jump"):
        for stat in STATS:
            ma, sa = stats["A"][key][stat]
            mb, sb = stats["B"][key][stat]
            delta = abs(ma - mb)
            worst = max(sa, sb)
            verdict = "inside the noise" if delta <= worst else "EXCEEDS the noise"
            print(f"{key} {stat}: |A-B| = {delta:.1f} ms ; largest within-artifact spread = "
                  f"{worst:.1f} ms -> delta is {verdict}")
    print("\nReport these numbers with the protocol, not instead of it: a bare p50 from a single "
          "uncontrolled run is not evidence about a version.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
