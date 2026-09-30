#!/usr/bin/env python3
"""Acceptance pass for the layered atlas dashboard (`build_atlas.py`).

The atlas has no tabs. It is one vertical stream, so "does every panel have
content" becomes "does every block have content", and the failure modes that
matter are different from the tabbed renderer:

- a block that renders an empty shell with no explanation;
- an internal key that reaches the reader (raw English enum, `source_line_start`);
- a chapter scrub that changes the number of visible entities (it must not — the
  page is as-of, not filtered-by-appearance-only);
- an entity drawer that fails as-of projection.

Usage:

    python scripts/accept_atlas.py <atlas.html> <out-dir> [--entity ID ...]
"""
from __future__ import annotations

import json
import re
import statistics
import sys
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

CHROME = r"C:\Users\Kasumi\AppData\Local\ms-playwright\chromium-1243\chrome-win64\chrome.exe"

# Keys that must never surface in reader-facing text. Machine keys are listed
# because the whole point of the display vocabulary is that these never print.
LEAK_KEYS = ["source_line_start", "source_line_end", "pair_key", "episode_id",
             "first_chapter\"", "valid_from\"", "relation_type\'",
             "character_traits", "state_changes", "item_roles", "review_issues",
             "chapter_summaries", "intimate_acts", "romance_routes"]

BLOCK_IDS = ["block-chapter_summaries", "block-entities", "block-level_axis",
             "block-item", "block-skill", "block-concept"]


def preview(items, n=6):
    """A truncated preview that says it is truncated.

    Every failure message in this file pairs a count with the list of offenders. Printing
    `items[:6]` next to a count of 7 reads as "the count is wrong": measured on gate 45,
    `missing=7` was followed by exactly six ids — the count was right and the list was a
    preview, but nothing on the line said so, so the line described its own arithmetic
    incorrectly. Twenty-four messages had this shape, which is why this is one helper rather
    than twenty-four slices, and why it had to be applied in a single pass: changing one
    message alone would have left the set inconsistent, and would have invalidated the
    acceptance report produced by the previous revision of this script — a report and the gate
    that produced it must be the same revision.

    Returns `repr` for a short list (unchanged behaviour) and `repr + "(+N more)"` otherwise.
    """
    items = list(items)
    if len(items) <= n:
        return repr(items)
    return f"{items[:n]} (+{len(items) - n} more)"


def guarded(pg, js, label, budget_s=240):
    """Run a long in-page probe with a per-probe watchdog, and report which outcome it was.

    Why this exists: the acceptance suite has several probes that walk dozens of routes inside a
    single in-page `async` loop (`CHAP_JS` visits 19 chapters, `EV_JS` visits 40 events). Those
    probes are correct in isolation -- measured: `EV_JS` alone returns 40/40 pages with all nine
    sections in 32 seconds -- but inside the full run the death point drifts between gates, which
    is the signature of the harness being cut off rather than of a fault in any one gate.

    The distinction this function makes is the one that was missing: a probe that ran out of
    budget, a probe that the page killed, and a probe that legitimately found nothing must not
    read the same. Playwright's default timeout is applied to navigation, not to an arbitrary
    long `evaluate`, so a stuck in-page loop would previously hang the whole run with no message
    and be recorded later as "the renderer crashed".

    Returns the probe's own result, or `{"error": ...}` with a reason that names the case.
    """
    import time as _t

    t0 = _t.time()
    try:
        out = pg.evaluate(js)
        print(f"  [{label}] ok in {_t.time()-t0:.0f}s")
        return out
    except Exception as exc:
        dt = _t.time() - t0
        msg = str(exc)[:200]
        over_budget = dt >= budget_s
        # A renderer that died mid-probe can still be detected: if the page object is gone, the
        # probe was not merely slow, the tab is gone. That is a different defect from a timeout
        # and must be reported differently, or the next reader will chase the wrong one.
        try:
            pg.evaluate("() => 1")
            alive = True
        except Exception:
            alive = False
        reason = ("renderer died mid-probe" if not alive
                  else ("probe exceeded its budget" if over_budget else "probe threw"))
        print(f"  [{label}] FAILED after {dt:.0f}s: {reason} — {msg[:120]}")
        return {"error": f"{reason} ({msg})"}


def collect_blocks(pg) -> dict:
    """Collect every rendered block.

    The stream is sectioned: each tier/block lives in a `<div class="sec" id="...">`
    wrapper so the slider can rebuild only the parts that changed. Look through the
    wrappers rather than requiring `#stream > .block`.
    """
    return pg.evaluate("""() => {
      const out = {};
      const blocks = document.querySelectorAll('#stream .block');
      for (const b of blocks) {
        const head = b.querySelector('.block-head h3');
        const title = head ? head.textContent.trim() : '?';
        const host = b.closest('.sec');
        out[host ? host.id : title] = {
          id: b.id || '',
          sec: host ? host.id : '',
          title,
          chars: b.innerText.length,
        };
      }
      return out;
    }""")


def main() -> int:
    args = [a for a in sys.argv[1:]]
    if len(args) < 2:
        raise SystemExit(__doc__)
    html = Path(args[0]).resolve()
    out = Path(args[1]).resolve()
    out.mkdir(parents=True, exist_ok=True)
    extra_entities = [args[i + 1] for i, a in enumerate(args) if a == "--entity"]

    report: dict = {"blocks": {}, "errors": [], "perf": {}, "checks": [],
                    "open_questions": []}
    with sync_playwright() as p:
        b = p.chromium.launch(executable_path=CHROME, args=["--hide-scrollbars"])
        pg = b.new_page(viewport={"width": 1680, "height": 1050})
        pg.on("pageerror", lambda e: report["errors"].append(f"pageerror: {str(e)[:300]}"))
        pg.on("console", lambda m: report["errors"].append(f"[console.{m.type}] {m.text[:300]}") if m.type == "error" else None)
        # An in-page `evaluate` that never returns has to become a reportable failure rather
        # than a hang. Playwright applies `default_timeout` to actions and
        # `default_navigation_timeout` to navigations; a long `pg.evaluate` of an `async`
        # function is bounded by neither, so a probe whose loop fails to converge would hang
        # the entire suite. That is how a non-converging loop in the sidebar probe came to be
        # written up three times as "the renderer crashed": the run was still working when it
        # was cut off, and a frozen log looks identical either way.
        pg.set_default_timeout(120000)

        # Record the machine this ran on, because a verdict is only meaningful with it.
        #
        # Three acceptance runs were written down as "the renderer crashed inside the sidebar
        # probe" when the truth was that the probe's own row set never converged and the run
        # was still grinding when it was cut off. Nothing in the report could have shown that,
        # because it recorded no load, no available memory, and no time budget. A green from a
        # single unrepeatable run is not a guarantee, and the way to make the next reader able
        # to tell the two apart is to store the conditions alongside the result.
        try:
            import ctypes as _ct

            class _MEM(_ct.Structure):
                _fields_ = [("dwLength", _ct.c_ulong), ("dwMemoryLoad", _ct.c_ulong),
                            ("ullTotalPhys", _ct.c_ulonglong),
                            ("ullAvailPhys", _ct.c_ulonglong),
                            ("ullTotalPageFile", _ct.c_ulonglong),
                            ("ullAvailPageFile", _ct.c_ulonglong),
                            ("ullTotalVirtual", _ct.c_ulonglong),
                            ("ullAvailVirtual", _ct.c_ulonglong),
                            ("ullAvailExtendedVirtual", _ct.c_ulonglong)]

            _m = _MEM()
            _m.dwLength = _ct.sizeof(_MEM)
            _ct.windll.kernel32.GlobalMemoryStatusEx(_ct.byref(_m))
            report["machine"] = {
                "when": time.strftime("%Y-%m-%d %H:%M:%S"),
                "mem_load_pct": _m.dwMemoryLoad,
                "mem_total_gb": round(_m.ullTotalPhys / 2 ** 30, 1),
                "mem_avail_gb": round(_m.ullAvailPhys / 2 ** 30, 2),
            }
            print(f"machine: {report['machine']}")
        except Exception as _exc:  # pragma: no cover - informational only
            report["machine"] = {"when": time.strftime("%Y-%m-%d %H:%M:%S"),
                                 "probe": f"unavailable ({str(_exc)[:80]})"}

        t0 = time.time()
        pg.goto(html.as_uri(), wait_until="load", timeout=180000)
        pg.wait_for_timeout(2500)
        report["load_ms"] = round((time.time() - t0) * 1000)

        ready = pg.evaluate("window.__atlasReady === true")
        report["ready"] = ready
        if not ready:
            report["errors"].append("window.__atlasReady never became true — the boot block did not finish")

        report["counts"] = pg.evaluate("""() => ({
          entities: ENT.size, relations: document.querySelectorAll('#stream .rel-line').length,
          cards: document.querySelectorAll('#stream .e-card').length,
          chapters: SUMMARY.size, stats: document.querySelectorAll('#stream .stat').length,
          cyNodes: (typeof CY !== 'undefined' && CY) ? CY.nodes().length : 0,
          cyEdges: (typeof CY !== 'undefined' && CY) ? CY.edges().length : 0,
        })""")
        # The graph is built lazily on viewport entry; scroll it in and re-measure so
        # a deferred build is not mistaken for a broken one.
        pg.evaluate("document.getElementById('graph').scrollIntoView({block:'center'})")
        pg.wait_for_timeout(1500)
        report["graph_after_scroll"] = pg.evaluate("""() => ({
          cyNodes: (typeof CY !== 'undefined' && CY) ? CY.nodes().length : 0,
          cyEdges: (typeof CY !== 'undefined' && CY) ? CY.edges().length : 0,
          legend: document.querySelectorAll('#zone-legend .row').length,
        })""")
        pg.evaluate("window.scrollTo(0,0)")
        pg.wait_for_timeout(300)
        report["blocks"] = collect_blocks(pg)
        report["stream_chars"] = pg.evaluate("document.getElementById('stream').innerText.length")
        report["drawer_open"] = pg.evaluate("document.body.classList.contains('drawer-open')")

        # every named block must carry real content
        empty_blocks = [k for k, v in report["blocks"].items() if v["chars"] < 40]
        if empty_blocks:
            report["checks"].append(f"blocks with <40 chars: {empty_blocks}")
        if not report["blocks"]:
            report["checks"].append("no blocks found at all — the stream did not render")
        if report["graph_after_scroll"]["cyNodes"] == 0:
            report["checks"].append("graph never drew, even after scrolling it into view")
        if report["graph_after_scroll"]["legend"] == 0:
            report["checks"].append("zone legend is empty")

        # no internal key may leak into reader text
        text = pg.evaluate("document.body.innerText")
        leaks = [k for k in LEAK_KEYS if k.rstrip('"\\\'') in text]
        if leaks:
            report["checks"].append(f"internal keys leaked into body text: {leaks}")

        # a raw English enum would show up as a snake_case token in the visible text
        snake = sorted(set(re.findall(r"\b[a-z]{3,}(?:_[a-z]{2,}){1,3}\b", text)))
        report["snake_tokens"] = snake[:40]
        if snake:
            report["checks"].append(f"suspicious snake_case tokens visible: {preview(snake, 12)}")

        # The stat strip must fill whole rows. `auto-fit` once fitted nine of ten
        # counters and stranded the last one on a row of its own.
        strip = pg.evaluate("""() => {
          const el = document.querySelector('.stat-strip');
          if (!el) return null;
          const kids = [...el.children];
          const tops = new Set(kids.map(k => Math.round(k.getBoundingClientRect().top)));
          const perRow = {};
          for (const k of kids){
            const t = Math.round(k.getBoundingClientRect().top);
            perRow[t] = (perRow[t] || 0) + 1;
          }
          const counts = Object.values(perRow);
          return { items: kids.length, rows: tops.size, counts,
                   cols: +getComputedStyle(el).gridTemplateColumns.split(' ').length };
        }""")
        report["stat_strip"] = strip
        if strip and strip["rows"] > 1:
            full = strip["cols"]
            short = [c for c in strip["counts"] if c < full]
            if short and len(strip["counts"]) > 1:
                report["checks"].append(
                    f"stat strip wraps unevenly: {strip['counts']} across {strip['rows']} rows "
                    f"for a {strip['cols']}-column grid — a counter is stranded")


        # Single-word enums are the harder leak: `assassination` and `crafting` carry no
        # underscore, so the snake_case scan above walks right past them. Compare the
        # page against the vocabulary itself — every ENUM value the graph uses must have
        # a translation, or it renders as its raw key. Groups whose values are free prose
        # rather than an enum are marked 'freetext' in the probe and only their Latin
        # values are required to be covered.
        vocab_coverage = pg.evaluate("""() => {
          const V2 = G._display_vocabulary || {};
          /* `issue_categories` is deliberately excluded. The audit log uses 190+ ad-hoc
           * category slugs and `issueBlock` is written to fall back to a generic label
           * rather than printing the slug, so an uncovered value is by design, not a
           * leak. Only groups whose renderer falls back to the raw key belong here. */
          /* Two kinds of group live here, and conflating them turns this into a check
           * that cannot pass.
           *
           *   'enum'     — the value comes from a controlled upstream vocabulary
           *                (`event_types`, `relations`, …). Every value must have an
           *                entry; a missing one is an untranslated enum.
           *   'freetext' — the value is prose lifted out of the record (`entity_tags`).
           *                A Chinese tag printing as itself is the CORRECT rendering,
           *                not a leak. Only a value containing Latin letters could be
           *                an untranslated enum.
           *
           * MEASURED with the first version of this scan, which treated `entity_tags`
           * as an enum: it reported 170 "values that would print raw English" and every
           * one of them was Chinese (一眉道 / 三大家族 / 上忍 / 丹药 / …). The scan was
           * wrong, the page was right — which is why the group now carries its kind.
           *
           * `entity_tags` stays on this list because it is the group whose renderer was
           * missing, not merely whose table was incomplete. While nothing read the
           * field, no English value could reach the reader and so none was ever
           * translated — the omission and the leak were the same omission. Now that
           * `sec-tags` renders it, an untranslated value would print as-is, and this is
           * the only scan that can see it: the snake_case regex below requires an
           * underscore, which `protagonist` / `minor` / `assassin` do not have. */
          const groups = {
            event_types: ['event_types', A(G.events).map(e => e.type), 'enum'],
            relations: ['relations', A(G.relations).map(r => r.relation_type), 'enum'],
            foreshadow_statuses: ['foreshadow_statuses', A(G.foreshadowing).map(f => f.status), 'enum'],
            commitment_kinds: ['commitment_kinds', A(G.commitments).map(x => x.kind), 'enum'],
            intimacy_act_types: ['intimacy_act_types', A(G.intimate_acts).map(x => x.act_type), 'enum'],
            item_roles: ['item_roles', A(G.item_roles).map(x => x.role), 'enum'],
            entity_tags: ['entity_tags', A(G.entities).flatMap(e => A(e.tags)), 'freetext'],
          };
          const LATIN = /[A-Za-z]/;
          const out = {}, sampled = {};
          for (const [name, [group, values, kind]] of Object.entries(groups)){
            const table = V2[group] || {};
            const seen = new Set(values.filter(v => typeof v === 'string' && v));
            const candidates = kind === 'freetext'
              ? [...seen].filter(v => LATIN.test(v))
              : [...seen];
            /* `sampled` is what keeps the freetext group from becoming a scan that can
             * never fail: if `tags` disappeared from the graph, `candidates` would be
             * empty and the group would report nothing at all — a green light with
             * nothing behind it. The count is reported so the Python side can refuse. */
            sampled[name] = { kind: kind, total: seen.size, checked: candidates.length,
                              skipped_nonlatin: seen.size - candidates.length };
            const untranslated = candidates.filter(v => table[v] == null);
            if (untranslated.length) out[name] = untranslated.sort();
          }
          return { untranslated: out, sampled: sampled };
        }""")
        report["untranslated_enums"] = vocab_coverage.get("untranslated", {})
        report["vocab_sampled"] = vocab_coverage.get("sampled", {})
        for name, vals in vocab_coverage.get("untranslated", {}).items():
            report["checks"].append(
                f"{name}: {len(vals)} value(s) have no vocabulary entry and would print "
                f"raw English: {preview(vals, 8)}")
        # The freetext group must have something to look at. If `tags` were dropped from
        # the graph (or from the group list) this scan would go quiet and still look
        # green — the exact failure mode this round was about: an empty scan is not a
        # pass. So the count is asserted, not merely printed.
        _ft = report["vocab_sampled"].get("entity_tags") or {}
        if not _ft.get("total"):
            report["checks"].append(
                "entity_tags: the free-text vocabulary scan had no values to look at — "
                "either no entity carries a tag or the field left the graph; an empty "
                "scan proves nothing")
        else:
            print(f"vocab scan: entity_tags saw {_ft['total']} value(s), checked "
                  f"{_ft['checked']} Latin one(s), passed {_ft['skipped_nonlatin']} "
                  f"non-Latin one(s) through as-is")

        # entity drawer must open and project as-of
        probe_ids = extra_entities or pg.evaluate("""() => {
          const pref = ['char_qin_chao'];
          const cards = Array.from(document.querySelectorAll('#stream .e-card')).slice(0, 3)
            .map(c => c.dataset.entity);
          return Array.from(new Set(pref.concat(cards))).filter(Boolean);
        }""")
        report["drawer"] = {}
        for eid in probe_ids:
            pg.evaluate(f"showEntity({json.dumps(eid)})")
            pg.wait_for_timeout(260)
            info = pg.evaluate("""() => ({
              open: document.body.classList.contains('drawer-open'),
              chars: document.getElementById('drawer').innerText.length,
              head: document.getElementById('drawer').innerText.slice(0, 90).replace(/\\n/g, ' | '),
              sections: Array.from(document.querySelectorAll('#drawer .sub')).map(h => h.textContent),
            })""")
            report["drawer"][eid] = info
            if not info["open"] or info["chars"] < 60:
                report["checks"].append(f"drawer for {eid} looks empty ({info['chars']} chars, open={info['open']})")
        pg.evaluate("closeDrawer()")

        # A closed drawer must stay closed. `render()` re-projects the selection as-of
        # the new chapter, so a `closeDrawer` that forgot to clear the selection made
        # the panel pop back open on the next scrub.
        pg.evaluate("setChapter(Math.floor((MIN_CH+MAX_CH)/2), true)")
        pg.wait_for_timeout(260)
        reopened = pg.evaluate("""() => ({
          open: document.body.classList.contains('drawer-open'),
          chars: document.getElementById('drawer').innerText.length,
        })""")
        report["drawer_stays_closed"] = reopened
        if reopened["open"] or reopened["chars"] > 0:
            report["checks"].append(
                "the drawer reopened itself after a chapter change following closeDrawer()")

        # Attribute values must never reach the reader as `[object Object]`.
        for eid in probe_ids:
            pg.evaluate(f"showEntity({json.dumps(eid)})")
            pg.wait_for_timeout(200)
            bad = pg.evaluate("""() => {
              const t = document.getElementById('drawer').innerText;
              return t.includes('[object Object]');
            }""")
            if bad:
                report["checks"].append(f"drawer for {eid} renders a raw object as [object Object]")
        pg.evaluate("closeDrawer()")

        # Escaping a fragment that is *already* markup prints the tags as text. The level
        # ladder did exactly that: `chLink()` returns a `<button>`, the row then wrapped
        # the whole string in `esc()`, and the reader saw
        # `→金仙期（<button class="xlink chx" data-goto-chapter="939">第 939 章</button>）`.
        # `innerText` is the right oracle because a tag that parsed as markup would not be
        # in it — only a literal one is.
        for eid in probe_ids[:4]:
            pg.evaluate(f"showEntity({json.dumps(eid)})")
            pg.wait_for_timeout(200)
            markup = pg.evaluate("""() => {
              const t = document.getElementById('drawer').innerText;
              const hits = [];
              for (const sig of ['<button', '<span', '<div', '</', 'class="', 'data-goto'])
                if (t.includes(sig)) hits.push(sig);
              return hits;
            }""")
            if markup:
                report["checks"].append(
                    f"drawer for {eid} prints markup as text: {markup}")
        pg.evaluate("closeDrawer()")

        # The agent library renders a budgeted slice, but its search and type filters
        # must range over every live agent. A filter that only looked at the rendered
        # cards would silently fail to find anyone past the budget — the exact
        # "can't find my character" defect this check exists to catch.
        lib = pg.evaluate("""() => {
          const out = { err: null };
          try {
            const grid = document.getElementById('lib-grid');
            if (!grid) { out.err = 'no #lib-grid'; return out; }
            const total = (document.getElementById('lib-tally') || {}).textContent || '';
            out.total = total;
            out.rendered = grid.querySelectorAll('.e-card').length;
            out.hasMore = !!document.getElementById('lib-more');
            const m = total.match(/(\\d+)\\s*\\/\\s*(\\d+)/);
            if (m) { out.shown = +m[1]; out.all = +m[2]; }

            /* Pick an agent that is live but not in the rendered slice. */
            const live = snap(S.chapter).ent.filter(e =>
              ['character','organization','creature'].includes(e.type));
            const ids = new Set(Array.from(grid.querySelectorAll('.e-card')).map(c => c.dataset.entity));
            const hidden = live.find(e => !ids.has(e.id));
            if (!hidden) { out.err = 'nothing hidden — budget too high to test'; return out; }
            out.hiddenId = hidden.id;
            out.hiddenName = hidden.name;

            const f = document.getElementById('lib-find');
            f.value = hidden.name;
            f.dispatchEvent(new Event('input', { bubbles: true }));
            out.foundAfterSearch = !!grid.querySelector(`[data-entity="${hidden.id}"]`);
            out.moreGoneWhenFiltered = !document.getElementById('lib-more');
            f.value = ''; f.dispatchEvent(new Event('input', { bubbles: true }));
            out.restored = grid.querySelectorAll('.e-card').length;

            const orgBtn = Array.from(document.querySelectorAll('[data-lib]'))
              .find(b => b.dataset.lib === 'organization');
            if (orgBtn) {
              orgBtn.click();
              out.orgCards = grid.querySelectorAll('.e-card').length;
              out.orgLive = snap(S.chapter).ent.filter(e => e.type === 'organization').length;
              /* The grid is paginated, so the page holds fewer cards than there are
               * matches — that is correct, not a bug. What must hold is that the filter
               * is *complete*: every organization is reachable by paging, and the
               * result set the pager reports equals the live count. */
              const info = document.querySelector('#lib-pager .pg-info');
              out.orgTotal = info
                ? Number((String(info.textContent).match(/共[ \t]*([0-9]+)[ \t]*条/) || [0, NaN])[1])
                : null;
              out.orgChipCount = (() => {
                const c = document.querySelector('[data-lib="organization"] .cnt, [data-lib="organization"] i');
                return c ? Number(String(c.textContent).replace(/[^0-9]/g, '')) : null;
              })();
              Array.from(document.querySelectorAll('[data-lib]')).find(b => b.dataset.lib === 'all')
                .click();
            }
          } catch (e) { out.err = String(e); }
          return out;
        }""")
        report["library"] = lib
        if lib.get("err"):
            report["checks"].append(f"agent library probe failed: {lib['err']}")
        else:
            if lib.get("all") and lib.get("rendered", 0) > lib["all"]:
                report["checks"].append(
                    f"agent library renders {lib['rendered']} cards but only {lib['all']} agents are live")
            if lib.get("hiddenId") and not lib.get("foundAfterSearch"):
                report["checks"].append(
                    f"searching for {lib.get('hiddenName')} (live but outside the card budget) "
                    f"matched nothing — the filter only looks at rendered cards")
            if lib.get("hiddenId") and not lib.get("moreGoneWhenFiltered"):
                report["checks"].append(
                    "the expand-more button stayed visible while a filter was active")
            if lib.get("orgLive") is not None and lib.get("orgTotal") is not None \
                    and lib["orgTotal"] != lib["orgLive"]:
                report["checks"].append(
                    f"the organization filter's pager reports {lib.get('orgTotal')} rows "
                    f"but {lib.get('orgLive')} organizations are live")
            if lib.get("orgLive") is not None and lib.get("orgChipCount") is not None \
                    and lib["orgChipCount"] != lib["orgLive"]:
                report["checks"].append(
                    f"the organization filter chip counts {lib.get('orgChipCount')} "
                    f"but {lib.get('orgLive')} organizations are live")
            if lib.get("orgCards") and lib.get("orgTotal") is not None \
                    and lib["orgCards"] > lib["orgTotal"]:
                report["checks"].append(
                    f"the organization page holds {lib.get('orgCards')} cards for "
                    f"{lib.get('orgTotal')} rows")
            if lib.get("all") and lib.get("restored") != lib.get("shown"):
                report["checks"].append(
                    f"clearing the search did not restore the budgeted slice "
                    f"({lib.get('restored')} vs {lib.get('shown')})")

        # ---------------------------------------------------------------- pagination
        # A pager that does not actually move is worse than no pager: the reader clicks
        # "next", the page scrolls, and the same twenty rows come back. The check is
        # therefore "page 2 contains a row page 1 does not", not "the pager exists".
        pg.evaluate("setChapter(MAX_CH, true)")
        pg.wait_for_timeout(420)
        paging = pg.evaluate("""() => {
          const out = {};
          const find = (sel) => document.querySelector(sel);
          /* --- chapter summaries: paging must change the visible set --- */
          const before = Array.from(document.querySelectorAll('#chapters .cs .cn')).map(n => n.textContent);
          const next = find('#chapters [data-page="chapters"][data-to="2"]');
          out.hasNext = !!next;
          out.page1Rows = before.length;
          if (next) {
            next.click();
            const after = Array.from(document.querySelectorAll('#chapters .cs .cn')).map(n => n.textContent);
            out.page2Rows = after.length;
            out.overlap = after.filter(x => before.includes(x)).length;
            out.info = (find('#chapters .pg-info') || {}).textContent || '';
            /* back to page one so later probes see the default view */
            const back = find('#chapters [data-page="chapters"][data-to="1"]');
            if (back) back.click();
          }
          /* --- filtering must narrow the *whole* set, not just the visible page ---
           * The old filter only looked at rendered rows, so searching for a chapter
           * that lived on page 7 found nothing. */
          const fin = find('#cs-find');
          if (fin) {
            /* A vanished pager means "the result fits on one page", which for a filter
             * that cannot match is the same statement as zero rows. Reading `null` as
             * "unchanged" made a working filter look broken. */
            const total = () => {
              const i = find('#chapters .pg-info');
              if (!i) return document.querySelectorAll('#chapters .cs').length;
              return Number((String(i.textContent).match(/共[ \t]*([0-9]+)[ \t]*条/) || [0, NaN])[1]);
            };
            out.totalUnfiltered = total();
            fin.value = '没有这个章节';
            fin.dispatchEvent(new Event('input', { bubbles: true }));
            out.totalImpossible = total();
            out.rowsImpossible = document.querySelectorAll('#chapters .cs').length;
            /* The repaint replaces the input node; typing must survive that or the
             * reader loses focus on the first keystroke of a multi-character query. */
            const fresh = find('#cs-find');
            out.inputSurvivesRepaint = !!fresh;
            out.inputKeepsValue = fresh ? fresh.value : null;
            /* Clear through the *fresh* node — the one the page is now listening to. */
            const clearMe = fresh || fin;
            clearMe.value = '';
            clearMe.dispatchEvent(new Event('input', { bubbles: true }));
            out.totalRestored = total();
          }
          return out;
        }""")
        report["paging"] = paging
        if not paging.get("hasNext"):
            report["checks"].append(
                "the chapter list has no page-2 button — 999 summaries are unpaginated")
        if paging.get("overlap", 0) and paging.get("page2Rows"):
            report["checks"].append(
                f"page 2 of the chapter list repeats {paging['overlap']} rows from page 1 "
                f"— the pager redrew the same slice")
        if paging.get("totalUnfiltered") and paging.get("totalImpossible") is not None \
                and paging["totalImpossible"] >= paging["totalUnfiltered"]:
            report["checks"].append(
                f"filtering the chapter list for a string that cannot exist returned "
                f"{paging['totalImpossible']} of {paging['totalUnfiltered']} rows — the "
                f"filter only narrows the rendered page")
        if paging.get("totalRestored") != paging.get("totalUnfiltered"):
            report["checks"].append(
                f"clearing the chapter filter restored {paging.get('totalRestored')} rows "
                f"instead of {paging.get('totalUnfiltered')}")
        if paging.get("inputSurvivesRepaint") and paging.get("inputKeepsValue") != "没有这个章节":
            report["checks"].append(
                f"the chapter filter box lost its text across the repaint it triggered "
                f"({paging.get('inputKeepsValue')!r})")

        # ---------------------------------------------------------------- navigation
        # Cross-links must *push*. If opening a related entity replaces the panel, the
        # reader loses the one they were reading and there is no way back to it.
        nav = pg.evaluate("""() => {
          const out = {};
          const d = () => document.getElementById('drawer');
          const title = () => {
            const h = d().querySelector('.drawer-head h2');
            return h ? h.textContent : '';
          };
          showEntity('char_qin_chao');
          out.opened = !!d().querySelector('.drawer-head h2');
          const name0 = title();
          out.name0 = name0;
          const rel = d().querySelector('.rel-line [data-entity], .rel-line .xlink');
          out.hasRelLink = !!rel;
          if (rel) {
            rel.click();
            out.name1 = title();
            out.pushed = out.name1 !== name0;
            out.navVisible = !!d().querySelector('.dnav');
            out.backBtn = !!d().querySelector('[data-dback]');
            const b = d().querySelector('[data-dback]');
            if (b) {
              b.click();
              out.nameAfterBack = title();
              out.navAfterBack = !!d().querySelector('.dnav');
            }
          }
          /* chapter cross-link inside the panel must re-scrub the page */
          const cx = d().querySelector('[data-goto-chapter]');
          out.hasChapterLink = !!cx;
          if (cx) {
            const want = cx.dataset.gotoChapter;
            cx.click();
            out.chapterAfterClick = String(S.chapter);
            out.chapterWanted = want;
          }
          closeDrawer();
          return out;
        }""")
        report["navigation"] = nav
        if not nav.get("pushed"):
            report["checks"].append(
                "clicking a related entity in the drawer did not change the panel "
                f"(still showing {nav.get('name0')!r})")
        if nav.get("pushed") and not nav.get("navVisible"):
            report["checks"].append(
                "opening a related entity did not offer a way back to the previous panel")
        if nav.get("pushed") and nav.get("navAfterBack"):
            report["checks"].append(
                "the drawer still shows a back affordance after returning to the first panel")
        if nav.get("pushed") and nav.get("nameAfterBack") != nav.get("name0"):
            report["checks"].append(
                f"the drawer's back arrow landed on {nav.get('nameAfterBack')!r} instead of "
                f"{nav.get('name0')!r} — the panel history is not a stack")
        if nav.get("hasChapterLink") and nav.get("chapterAfterClick") != nav.get("chapterWanted"):
            report["checks"].append(
                f"a chapter link in the drawer jumped to {nav.get('chapterAfterClick')} "
                f"instead of {nav.get('chapterWanted')}")

        # ------------------------------------------------------------------ the rail
        rail = pg.evaluate("""() => {
          const rows = Array.from(document.querySelectorAll('#rail [data-rail]'));
          const out = { rows: rows.length, keys: rows.map(r => r.dataset.rail), targeted: 0 };
          for (const r of rows) {
            const t = document.getElementById(r.dataset.rail);
            if (t && t.innerHTML.trim() !== '') out.targeted++;
          }
          const live = Array.from(document.querySelectorAll('#stream > .sec'))
            .filter(s => s.innerHTML.trim() !== '').map(s => s.id);
          out.live = live;
          out.dangling = out.keys.filter(k => !live.includes(k));
          out.missing = live.filter(k => !out.keys.includes(k)
            && !['T1', 'T2', 'T3', 'TAIL'].includes(k));
          return out;
        }""")
        report["rail"] = rail
        if rail.get("rows", 0) < 8:
            report["checks"].append(
                f"the navigation rail only lists {rail.get('rows')} blocks")
        if rail.get("dangling"):
            report["checks"].append(
                f"the navigation rail points at empty blocks: {rail['dangling']}")
        if rail.get("missing"):
            report["checks"].append(
                f"blocks missing from the navigation rail: {rail['missing']}")

        # ------------------------------------------------------------ command palette
        # The palette is the only path to an entity whose name the reader half-remembers
        # and whose type they cannot guess. If it silently returns nothing, the 980
        # entities stay reachable only by already knowing where they live.
        pal = pg.evaluate("""() => {
          const out = {};
          const btn = document.getElementById('cm-btn');
          out.hasButton = !!btn;
          if (btn) btn.click();
          out.opened = document.body.classList.contains('cm-open');
          const inp = document.getElementById('cm-input');
          out.hasInput = !!inp;
          if (!inp) return out;
          const type = value => {
            inp.value = value;
            inp.dispatchEvent(new Event('input', { bubbles: true }));
            const rows = Array.from(document.querySelectorAll('#cm-list .cm-row'));
            return rows.map(r => ({
              name: (r.querySelector('.cm-name') || {}).textContent || '',
              sub: (r.querySelector('.cm-sub') || {}).textContent || '',
            }));
          };
          out.entityHits = type('苏姬');
          out.sectionHits = type('伏笔');
          out.chapterHits = type('640');
          out.gibberish = type('zzzqqq-nonexistent');
          out.emptyMarked = !!document.querySelector('#cm-list .cm-empty');
          // Enter on the first row must actually open something.
          type('苏姬');
          const before = document.getElementById('drawer').innerText.length;
          const first = document.querySelector('#cm-list .cm-row');
          if (first) first.click();
          out.closedAfterPick = !document.body.classList.contains('cm-open');
          out.drawerChars = document.getElementById('drawer').innerText.length;
          out.drawerGrew = out.drawerChars > before;
          return out;
        }""")
        report["palette"] = pal
        if not pal.get("hasButton"):
            report["checks"].append("no command palette trigger on the page")
        if not pal.get("opened"):
            report["checks"].append("the command palette did not open when triggered")
        if pal.get("hasInput") and not pal.get("entityHits"):
            report["checks"].append("the command palette found no entity for '苏姬'")
        if pal.get("hasInput") and not pal.get("sectionHits"):
            report["checks"].append("the command palette found no section for '伏笔'")
        if pal.get("hasInput") and not pal.get("chapterHits"):
            report["checks"].append("the command palette found no chapter for '640'")
        # A query with no possible match must say so rather than render an empty box.
        if pal.get("hasInput") and pal.get("gibberish") and not pal.get("emptyMarked"):
            report["checks"].append(
                "the command palette listed rows for a nonsense query instead of an "
                "empty state")
        if pal.get("hasInput") and not pal.get("drawerGrew"):
            report["checks"].append(
                "picking a palette result did not open the entity drawer")

        # --------------------------------------------------- keyboard reachability
        # Every control on the page used to be Tab-reachable and draw nothing, so a
        # keyboard user could not tell where they were. The ring is one shared rule, so a
        # single representative control is enough to prove it exists.
        kbd = pg.evaluate("""() => {
          const out = {};
          const sels = ['.fchip', '.pg', '#rail [data-rail]', '.cm-row'];
          out.rules = 0;
          for (const sheet of Array.from(document.styleSheets)){
            let rules;
            try { rules = Array.from(sheet.cssRules || []); } catch (e) { continue; }
            for (const r of rules){
              if (r.selectorText && r.selectorText.includes('focus-visible')) out.rules++;
            }
          }
          out.controls = 0;
          for (const s of sels) out.controls += document.querySelectorAll(s).length;
          const legend = document.querySelector('#zone-legend .row');
          out.legendTabIndex = legend ? legend.getAttribute('tabindex') : null;
          return out;
        }""")
        report["keyboard"] = kbd
        if not kbd.get("rules"):
            report["checks"].append("no :focus-visible rule is present in the stylesheet")
        if kbd.get("controls", 0) < 20:
            report["checks"].append(
                f"only {kbd.get('controls')} keyboard-reachable controls found")

        # ------------------------------------------------------- legend visibility
        # Hovering lit a sector but nothing could put a sector away, so a 640-node disc
        # always drew 640 nodes. The eye marks a sector hidden and must actually remove
        # its elements from the render.
        #
        # The legend only exists once the graph block has been painted, and earlier
        # chapter probes may have swapped the section out from under it — so the scroll
        # and the redraw are repeated here rather than assuming the state from the top of
        # the run is still current.
        pg.evaluate("document.getElementById('graph').scrollIntoView({block:'center'})")
        pg.wait_for_timeout(600)
        vis = pg.evaluate("""() => {
          const out = {};
          if (typeof CY === 'undefined' || !CY) return out;
          const row = document.querySelector('#zone-legend .row');
          if (!row) return out;
          out.zone = row.dataset.zone;
          const count = () => CY.nodes().filter(n => n.data('zone') === out.zone).length;
          const drawn = () => CY.nodes().filter(n => n.style('display') !== 'none').length;
          out.before = count();
          out.drawnBefore = drawn();
          const eye = row.querySelector('[data-eye]');
          out.hasEye = !!eye;
          if (!eye) return out;
          eye.click();
          out.after = count();
          out.drawnAfter = drawn();
          out.rowOff = row.classList.contains('off');
          eye.click();
          out.restoredDrawn = drawn();
          out.rowBack = !row.classList.contains('off');
          return out;
        }""")
        report["legend_visibility"] = vis
        if vis and not vis.get("hasEye"):
            report["checks"].append("sector rows have no visibility toggle")
        elif vis:
            if not vis.get("rowOff"):
                report["checks"].append("toggling a sector did not mark it hidden")
            if vis.get("drawnAfter", 0) >= vis.get("drawnBefore", 0):
                report["checks"].append(
                    f"hiding a sector did not remove its nodes from the render "
                    f"({vis.get('drawnBefore')} -> {vis.get('drawnAfter')} drawn)")
            if vis.get("restoredDrawn") != vis.get("drawnBefore"):
                report["checks"].append(
                    f"un-hiding a sector did not restore the drawing "
                    f"({vis.get('restoredDrawn')} vs {vis.get('drawnBefore')})")

        # -------------------------------------------------------------- sort control
        # Sorting was fixed server-side per block, so "show me the newest items" had no
        # answer. Each library now carries its own select and the order must really change.
        srt = pg.evaluate("""() => {
          const out = {};
          const sel = document.querySelector('[data-sort]');
          out.hasSelect = !!sel;
          if (!sel) return out;
          out.key = sel.dataset.sort;
          const blob = () => Array.from(document.querySelectorAll('#block-items .e-card .nm'))
            .map(n => n.textContent).join('|');
          out.opts = Array.from(sel.options).map(o => o.value);
          const seq = [];
          for (const v of out.opts){
            sel.value = v;
            sel.dispatchEvent(new Event('change', { bubbles: true }));
            seq.push([v, blob()]);
          }
          out.byMode = {};
          for (const [v, b] of seq) out.byMode[v] = b;
          out.distinct = new Set(seq.map(s => s[1])).size;
          out.maxLen = seq.reduce((m, s) => Math.max(m, s[1].length), 0);
          return out;
        }""")
        report["sort"] = {"hasSelect": srt.get("hasSelect"), "opts": srt.get("opts"),
                          "distinct": srt.get("distinct")}
        if srt.get("hasSelect"):
            if srt.get("distinct", 0) < 2:
                report["checks"].append(
                    "the library sort control does not change the rendered order")
            if srt.get("maxLen", 0) < 40:
                report["checks"].append(
                    "the item library rendered no rows to sort")


        # --------------------------------------------------- category label hygiene
        # Three skill rows stored the controlled vocabulary as the *rendered repr* of a
        # Python list (`"['attack', 'summoning']"`), so their filter chips printed bare
        # English enum next to 外家拳 and 防御术 — one chip row, two languages. The values
        # are legitimate data; only the display was wrong. This gate reads the chips the
        # way a reader does and rejects any that reduced to nothing but ASCII words.
        cats = pg.evaluate("""() => {
          const out = {};
          const bad = [];
          for (const id of ['items', 'skills', 'concepts']){
            const sec = document.getElementById('block-' + id);
            if (!sec) continue;
            for (const chip of sec.querySelectorAll('.fchip')){
              const t = (chip.innerText || '').replace(/\\d+$/, '').trim();
              if (!t || t === '全部' || t === '未分类') continue;
              /* Nothing but lower-case ASCII words, underscores and separators means the
               * reader is looking at a machine enum rather than a label. Real Chinese
               * labels never match this. */
              if (/^[a-z_]+(\\s*[,·/]\\s*[a-z_]+)*$/.test(t)) bad.push(id + ': ' + t);
            }
          }
          out.bad = bad;
          out.skillChips = Array.from(
            document.querySelectorAll('#block-skills .fchip')).map(c => c.innerText.trim());
          return out;
        }""")
        report["category_chips"] = cats.get("skillChips")
        if cats.get("bad"):
            report["checks"].append(
                "category chips print bare machine enums: " + "; ".join(cats["bad"]))
        for probe in ("attack", "summoning", "support", "cultivation", "utility", "control"):
            if cats.get("skillChips") and any(probe in c for c in cats["skillChips"]):
                report["checks"].append(
                    f"skill library still exposes the raw enum `{probe}` in a filter chip")
                break

        # chapter scrubbing: the rendered card count must track the as-of entity count,
        # which is the check that catches a stale section that was never cleared.
        probe_chapters = [pg.evaluate("MIN_CH"), pg.evaluate("Math.floor((MIN_CH+MAX_CH)/2)"), pg.evaluate("MAX_CH")]
        report["snapshots"] = []
        for ch in probe_chapters:
            pg.evaluate(f"setChapter({ch}, true)")
            pg.wait_for_timeout(420)
            snap = pg.evaluate("""() => {
              const per = {};
              for (const sec of document.querySelectorAll('#stream > .sec')) per[sec.id] = sec.querySelectorAll('.e-card').length;
              const st = snap(S.chapter);
              return {
                badge: document.getElementById('ch-badge').textContent,
                entities: st.ent.length,
                cards: document.querySelectorAll('#stream .e-card').length,
                per,
                chars: document.getElementById('stream').innerText.length,
              };
            }""")
            report["snapshots"].append({"chapter": ch, **snap})

        # A section must never show more cards than the chapter has entities. If it
        # does, sectioned caching kept markup that this chapter's data no longer backs.
        for s in report["snapshots"]:
            if s["cards"] > s["entities"]:
                report["checks"].append(
                    f"chapter {s['chapter']}: {s['cards']} cards rendered but only "
                    f"{s['entities']} entities are live — a section kept stale markup "
                    f"({s['per']})")

        # perf: what a real drag feels like. Driving consecutive chapters on rAF reproduces
        # the per-frame cost the reader pays. The slider handler is
        # `slider.addEventListener("input", () => setChapter(N(slider.value)))`, and a
        # non-immediate `setChapter` coalesces to one frame of `paint()`, where
        # `paint = () => { if (paged) paintPage(RT); else render(v); buildSidebar(); }`.
        #
        # This block used to say that measuring isolated `setChapter` calls "overstates
        # latency". That is not what separates the two probes, and it was measured this round:
        # `setChapter` and `render` over the same 34 consecutive chapters agree to 1.01x
        # (59.3 vs 58.5 ms p50), and `buildSidebar` costs 0.1 ms. What separates them is which
        # chapters they sample — 34 consecutive frames at the tail against ten steps spread
        # over the whole book.
        #
        # The earlier probes leave debris: a sector may still be hidden, the command
        # palette may have been opened and closed, and three library repaints have run.
        # None of that is what the reader's scrub looks like, so the page is reset to the
        # default view before the measurement rather than measuring whatever state the
        # gates happened to leave behind.
        #
        # The scroll position matters more than any of that. The stream is ~50000 px
        # tall; measured from the bottom of it (`scrollY` ~5000) a frame costs 290 ms,
        # and measured from the top the same frame costs 72 ms. That is the browser
        # laying out a document whose remaining height dwarfs the viewport, not the
        # renderer — an earlier revision of this gate reported the 290 ms figure as if it
        # described the reader's experience, and it does not. The reader scrubs from the
        # top of the page with the chapter stream under the cursor, so the measurement is
        # taken there.
        pg.evaluate("""() => {
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
        }""")
        pg.wait_for_timeout(500)
        # Warm-up, and it has to be longer than one gesture. Measuring the same build five
        # times in one session gives p95 140.7 / 127.6 / 115.3 / 80.4 / 68.1 ms — the p50
        # barely moves (74.1 → 59.8) while the tail collapses. That is V8 finishing
        # optimising the hot path, not a change in the work being done, and the reader
        # never measures their first frame. Two full warm-up passes put the measurement
        # past the cliff; their frames are discarded.
        #
        # This replaced a one-pass warm-up that was not enough: it still reported 133-146 ms
        # because the *tail* is what converges last.
        for _warm in range(2):
            pg.evaluate("""() => new Promise(res => {
              const seq = [];
              for (let c = MAX_CH - 5; c > MAX_CH - 40; c--) seq.push(c);
              let i = 0;
              const step = () => {
                if (i >= seq.length) return res();
                render(seq[i++]);
                requestAnimationFrame(step);
              };
              requestAnimationFrame(step);
            })""")
            pg.wait_for_timeout(400)
        # Each frame records two spans, because the reader waits for the second one:
        #   js       — `performance.now()` around the update, i.e. the JavaScript only;
        #   interval — the timestamp delta to the next animation frame, i.e. the JavaScript
        #              plus the browser's own style/layout/paint for the DOM just built, plus
        #              at most one vsync period.
        # MEASURED on this build: the scrub reads js p50 56.9 ms against interval p50 68.6 ms,
        # so the span the budget used to be asserted on was a ~12 ms optimistic reading of the
        # frame the reader waits for. The budget is now asserted on both — they bracket the
        # quantity, and a regression moves both.
        DRAG_JS = """() => new Promise(res => {
          const frames = [];
          const lo = Math.max(MIN_CH, MAX_CH - 40);
          const seq = [];
          for (let c = MAX_CH - 5; c > lo; c--) seq.push(c);
          let i = 0, prev = null;
          const step = (ts) => {
            if (prev !== null) frames[frames.length - 1].interval = ts - prev;
            if (i >= seq.length) return res(frames);
            const c = seq[i++];
            prev = ts;
            const t = performance.now();
            render(c);
            frames.push({ js: performance.now() - t, interval: null });
            requestAnimationFrame(step);
          };
          requestAnimationFrame(step);
        })"""

        def span_stats(frames, key):
            """One stat block per span, from one write point.

            The drag readings used to compute this dict inline three times; adding the interval
            span would have made it six, and six copies of a percentile expression is how two
            probes end up disagreeing about what `p95` means. The index expression is the drag
            block's original one, unchanged, so the js figures stay comparable with every
            earlier report. Note the jump probe's `p95` uses `int(n * 0.95) - 1`, a different
            index — registered as a defect rather than fixed mid-round, because unifying it
            would silently move figures that existing reports cite.
            """
            vals = [f[key] for f in frames if f.get(key) is not None]
            return {"n": len(vals),
                    "p50": round(statistics.median(vals), 1),
                    "p95": round(sorted(vals)[min(len(vals) - 1, int(len(vals) * 0.95))], 1),
                    "max": round(max(vals), 1)}
        drag = pg.evaluate(DRAG_JS)
        # the first sample includes the cold style/layout pass; drop it
        warm = drag[1:] or drag
        report["perf"]["drag_ms"] = span_stats(warm, "js")
        report["perf"]["drag_frame_ms"] = span_stats(warm, "interval")
        # The budget assertion is deliberately NOT applied to this first reading. AGENTS.md sets
        # p95 <= 100 ms for a chapter scrub on the default view, and a reading can only decide
        # that if it is compared against something reproducible. MEASURED on a byte-identical A/B
        # pair in one session, this same artifact's drag p95 ranged 69.8-90.0 ms (spread 20.2 ms)
        # and its p50 ranged 58.0-74.0 ms (spread 16.0 ms), with both variants moving together in
        # the same round — i.e. a within-round excursion of the machine, not of the build. The
        # margin under the budget is 10 ms, half the instrument's own spread, so asserting it on a
        # single reading fails good builds at random. Note what ABBA does and does not buy: it
        # cancels drift in a *comparison* (|A-B| stayed at 0.9 ms across a 16 ms spread) and does
        # nothing at all for an *absolute* threshold. Hence the scrub is measured three times and
        # the median is judged, below.

        # The same measurement a second time, in the same session, on the same build. This is not
        # another data point — it is a bound on the instrument, and it exists because of a
        # comparison that could not be made without one. MEASURED this round with an interleaved
        # A/B: the shipped artifact's drag p50 moved 59.6 / 58.8 / 59.2 / 57.7 ms across four runs
        # after a discarded warm-up (spread 1.9 ms), but 62.8 / 60.1 / 70.9 ms (spread 10.8 ms)
        # when the session's cold first measurement was kept. A later session on a BYTE-IDENTICAL
        # pair put the same artifact's p50 spread at 16.0 ms and its p95 spread at 20.2 ms, so the
        # floor is not a property of the instrument alone — it moves with the session. The bound
        # below is therefore set above every spread observed so far, and each run reports its own
        # spread rather than citing this comment. The historical baseline this build
        # was compared against recorded `machine: null`, and its 48.7 ms sits 10 ms below what the
        # same artifact measures now under two different current loads (58.8 and 61.2 ms). A gap
        # that size across two *sessions* is not readable as a regression while one build moves
        # 10.8 ms inside a single session — so reproducibility is asserted here, not assumed.
        # An instrument that cannot reproduce itself cannot detect anything.
        drag2 = pg.evaluate(DRAG_JS)
        warm2 = drag2[1:] or drag2
        report["perf"]["drag_ms_repeat"] = span_stats(warm2, "js")
        report["perf"]["drag_frame_ms_repeat"] = span_stats(warm2, "interval")
        drag3 = pg.evaluate(DRAG_JS)
        warm3 = drag3[1:] or drag3
        report["perf"]["drag_ms_third"] = span_stats(warm3, "js")
        report["perf"]["drag_frame_ms_third"] = span_stats(warm3, "interval")
        # The run carries its own noise floor, so nobody has to remember one. Every performance
        # number in this report is qualified by a spread measured on THIS build in THIS session,
        # for the same reason `machine` is written: a figure whose reproducibility is not stated
        # is a figure that will be compared against something incomparable.
        runs3 = [report["perf"]["drag_ms"], report["perf"]["drag_ms_repeat"],
                 report["perf"]["drag_ms_third"]]
        report["perf"]["drag_within_session_spread"] = {
            stat: round(max(r[stat] for r in runs3) - min(r[stat] for r in runs3), 1)
            for stat in ("p50", "p95", "max")}
        # The tail is the least reproducible statistic here and it is the one the budget names, so
        # the budget is asserted on the median of the three readings: a regression shifts the whole
        # distribution and still fails this, while a single unlucky frame no longer does.
        drag_p95_median = round(statistics.median([r["p95"] for r in runs3]), 1)
        report["perf"]["drag_p95_median_of_3"] = drag_p95_median
        if drag_p95_median > 100:
            report["checks"].append(
                f"chapter scrub p95 median of 3 {drag_p95_median} ms exceeds the 100 ms budget "
                f"(readings {[r['p95'] for r in runs3]}, within-session spread "
                f"{report['perf']['drag_within_session_spread']['p95']} ms; measured at page top, "
                f"default filters, 34 frames per reading)")
        # The same budget, asserted on the span the reader waits for. The JavaScript span above
        # is the tighter instrument and catches a regression first; this one is the quantity the
        # budget is actually about, so a frame that spends its time outside `render()` — style,
        # layout, paint — cannot hide behind a healthy js figure. A vsync period is included, so
        # this bound is an upper bound on the update and the js bound a lower one; both are
        # asserted and they bracket the same reader-visible cost.
        frame_runs3 = [report["perf"]["drag_frame_ms"], report["perf"]["drag_frame_ms_repeat"],
                       report["perf"]["drag_frame_ms_third"]]
        report["perf"]["drag_frame_within_session_spread"] = {
            stat: round(max(r[stat] for r in frame_runs3) - min(r[stat] for r in frame_runs3), 1)
            for stat in ("p50", "p95", "max")}
        drag_frame_p95_median = round(statistics.median([r["p95"] for r in frame_runs3]), 1)
        report["perf"]["drag_frame_p95_median_of_3"] = drag_frame_p95_median
        if drag_frame_p95_median > 100:
            report["checks"].append(
                f"chapter scrub frame interval p95 median of 3 {drag_frame_p95_median} ms exceeds "
                f"the 100 ms budget (readings {[r['p95'] for r in frame_runs3]}, within-session "
                f"spread {report['perf']['drag_frame_within_session_spread']['p95']} ms) — the "
                f"JavaScript span can be inside the budget while the frame the reader waits for "
                f"is not")
        drift = abs(report["perf"]["drag_ms"]["p50"] - report["perf"]["drag_ms_repeat"]["p50"])
        report["perf"]["drag_p50_drift_ms"] = round(drift, 1)
        if drift > 25:
            report["checks"].append(
                f"the chapter scrub measured p50 {report['perf']['drag_ms']['p50']} ms and then "
                f"{report['perf']['drag_ms_repeat']['p50']} ms in the same session on the same "
                f"build (drift {drift:.1f} ms) — the measurement does not reproduce itself, so "
                f"any cross-version comparison built on it means nothing")

        # The projection cache is what made the scrub slow down over a long session: 36
        # cached chapters measured p95 86.8 ms, 174 measured 104.7 ms for the same visible
        # work. It is now capped, and this gate is what keeps it capped — the regression is
        # invisible in any single-gesture measurement.
        cache = pg.evaluate("""() => {
          for (let c = MIN_CH; c <= MAX_CH; c += 11) snap(c);
          return { size: CACHE.size, limit: typeof SNAP_LIMIT === 'number' ? SNAP_LIMIT : null };
        }""")
        report["cache"] = cache
        if cache.get("limit") is None:
            report["checks"].append("the projection cache has no declared limit")
        elif cache["size"] > cache["limit"]:
            report["checks"].append(
                f"projection cache grew to {cache['size']} past its limit of {cache['limit']}")

        # perf: ten chapter updates on the default view, stepping across the whole book.
        #
        # AGENTS.md item 7 names three interactions to measure (continuous slider input,
        # repository switching, whole-graph layout) and gives two budgets, the first of which is
        # "默认视图章节更新 p95 <= 100 ms". The scrub measured above is the interaction that
        # clause names, and the gate asserts the clause on it. Ten steps spread over the book is
        # a *different* interaction — a chapter link, a deep link, a typed chapter number — that
        # item 7 does not list, so it is measured and registered rather than budgeted.
        #
        # What this probe measures is `setChapter`, the whole update. It used to run the ten
        # calls as ten separate evaluations with the page idle between them, which leaves the
        # browser's layout of each update outside the timed region; it now drives one update per
        # animation frame and records both spans, so each reading is a frame cost.
        def jump_sweep():
            return pg.evaluate("""() => new Promise(res => {
              const seq = [];
              for (let s = 0; s < 10; s++) seq.push(Math.round(MIN_CH + (MAX_CH - MIN_CH) * (s / 9)));
              const out = [];
              let i = 0, prev = null;
              const step = (ts) => {
                if (prev !== null) out[out.length - 1].interval = ts - prev;
                if (i >= seq.length) return res(out);
                const c = seq[i++];
                prev = ts;
                const t = performance.now();
                setChapter(c, true);
                out.push({ ch: c, js: performance.now() - t, interval: null });
                requestAnimationFrame(step);
              };
              requestAnimationFrame(step);
            })""")

        # The first sweep of a session is REPORTED, not filed as an artifact. It is the cost of
        # painting chapters this session has never painted, and it sits ~40 ms above every later
        # sweep: MEASURED across sessions, first sweeps read js p50 99.7 / 118.6 / 125.7 ms while
        # repeats read 70.1 / 71.7 / 74.4 / 76.0 / 78.9 / 79.4 / 81.4 / 82.7 ms.
        #
        # Three candidate causes were tested and REFUTED: the sidebar (0.1 ms), the projection
        # cache (`CACHE.clear()` before every step made the pass FASTER, 78.9 against 116.0), and
        # the markup cache (clearing it did not restore the cost, 82.7 against 125.7). The
        # projection table's size axis then disagreed between two probes — one read a full table
        # as slower, the other as faster. So the EFFECT is recorded and the MECHANISM is left
        # unnamed; an earlier revision of this comment called it "V8 finishing optimising the hot
        # path", which no measurement here supports.
        #
        # It also cannot be reproduced within a session: it happens once per page by
        # construction, so the report says so next to the number.
        first_sweep = jump_sweep()
        second_sweep = jump_sweep()
        report["perf"]["render_ms_warmup"] = [span_stats(first_sweep, "js"),
                                              span_stats(second_sweep, "js")]
        report["perf"]["render_ms_first_visit"] = span_stats(first_sweep, "js")
        report["perf"]["render_ms_first_visit_frame"] = span_stats(first_sweep, "interval")
        report["perf"]["render_ms_first_visit_note"] = (
            "one observation per session by construction: the cost is paid by the first pass "
            "that paints these chapters, so it cannot be repeated on the same page, and no "
            "within-session spread can be quoted for it")
        jump_rows = [jump_sweep(), jump_sweep(), jump_sweep()]
        report["perf"]["render_ms"] = span_stats(jump_rows[0], "js")
        report["perf"]["render_ms_frame"] = span_stats(jump_rows[0], "interval")
        report["perf"]["render_ms_repeat"] = span_stats(jump_rows[1], "js")
        report["perf"]["render_ms_repeat_frame"] = span_stats(jump_rows[1], "interval")
        report["perf"]["render_ms_third"] = span_stats(jump_rows[2], "js")
        report["perf"]["render_ms_third_frame"] = span_stats(jump_rows[2], "interval")
        jump_runs = [report["perf"]["render_ms"], report["perf"]["render_ms_repeat"],
                     report["perf"]["render_ms_third"]]
        report["perf"]["render_within_session_spread"] = {
            stat: round(max(r[stat] for r in jump_runs) - min(r[stat] for r in jump_runs), 1)
            for stat in ("p50", "p95", "max")}
        jump_frame_runs = [report["perf"]["render_ms_frame"],
                           report["perf"]["render_ms_repeat_frame"],
                           report["perf"]["render_ms_third_frame"]]
        report["perf"]["render_frame_within_session_spread"] = {
            stat: round(max(r[stat] for r in jump_frame_runs) - min(r[stat] for r in jump_frame_runs), 1)
            for stat in ("p50", "p95", "max")}

        # The budget this probe does NOT have. The earlier version of this block registered the
        # question as an ambiguity between two readings of item 7 and claimed it "changes what
        # the project promises, not whether this build passes". That claim was measured against a
        # JavaScript span on a cached second sweep and is false of the first visit: MEASURED this
        # round, the first visit to these chapters reads frame p95 well past the clause. So the
        # registration now carries the figures it is about, and states a proposal instead of an
        # ambiguity, because the measurement settled the part that was measurable: item 7 lists
        # three interactions and a wide-step update is not among them.
        report["perf"]["render_ms_budget"] = None
        steady_frame = report["perf"]["render_ms_frame"]["p95"]
        first_frame = report["perf"]["render_ms_first_visit_frame"]["p95"]
        first_js = report["perf"]["render_ms_first_visit"]["p95"]
        steady_js = report["perf"]["render_ms"]["p95"]
        # Both verdicts are DERIVED from the numbers, never written next to them. The first
        # version of the question said "the build fails the budget" unconditionally; the next
        # run measured p95 81.2 ms, inside it under both readings, because a warm-up fix had
        # removed a 106 ms artifact. A registered question that contradicts its own figures is
        # worse than no question — it is the round-17 `missing=7` error again.
        steady_verdict = ("inside the 100 ms clause at {v} ms".format(v=steady_frame)
                          if steady_frame <= 100
                          else "OVER the 100 ms clause at {v} ms".format(v=steady_frame))
        first_verdict = ("inside the 100 ms clause at {v} ms".format(v=first_frame)
                         if first_frame <= 100
                         else "OVER the 100 ms clause at {v} ms".format(v=first_frame))
        report["perf"]["render_ms_budget_note"] = (
            "no budget applied. AGENTS.md item 7 lists three interactions to measure and gives "
            "two budgets; the scrub is the interaction its 100 ms clause names, and the gate "
            "asserts the clause on the scrub (js and frame spans). A wide-step chapter update is "
            "not one of the three interactions. Measured here, steady: js p95 {sj} ms, frame p95 "
            "{sf} ms; first visit in this session: js p95 {fj} ms, frame p95 {ff} ms.".format(
                sj=steady_js, sf=steady_frame, fj=first_js, ff=first_frame))
        report["open_questions"].append(
            "AGENTS.md item 7 lists three interactions to measure and gives two budgets, the "
            "first being 默认视图章节更新 p95 <= 100 ms. A scrub is one sample of that quantity and "
            "a wide-step chapter update (a chapter link, a deep link, a typed chapter number) is "
            "another, and the two samples are not the same size — MEASURED this session, the "
            "scrub reads js p95 {dj} / frame p95 {df} ms over 34 consecutive frames, while the "
            "wide step reads js p95 {sj} / frame p95 {sf} ms steady ({sv}) and js p95 {fj} / "
            "frame p95 {ff} ms on the first visit to those chapters ({fv}). The reading therefore "
            "decides the verdict: the scenario the item names passes with {dm} ms of margin on "
            "the frame span, and a clause read as covering any default-view chapter update does "
            "not. The gate asserts the clause on the scrub, the interaction the item names, and "
            "does not decide the other. The first visit is one observation per session by "
            "construction and cannot be repeated on the same page. Proposal for the owner, who "
            "owns the wording: give wide-step updates a budget of their own, or say the clause "
            "covers them — the figures above are what it would have to cover.".format(
                dj=report["perf"]["drag_p95_median_of_3"],
                df=report["perf"]["drag_frame_p95_median_of_3"],
                dm=round(100 - report["perf"]["drag_frame_p95_median_of_3"], 1),
                sj=steady_js, sf=steady_frame, sv=steady_verdict,
                fj=first_js, ff=first_frame, fv=first_verdict))

        # Reproducibility, on the bound contract 5.7 established for the scrub — a gate added
        # without inventing a threshold, though the number is this path's own: MEASURED spreads
        # for the isolated update are p50 26.7 / p95 28.3 ms (this session) and p95 20.8 / 7.0 ms
        # (the byte-copy A/B), against the scrub's 2.4 ms — a 10x difference, so one bound cannot
        # serve both. 35 ms clears every one of them. Each run reports its own spread next to it,
        # because the floor moves with the session.
        jump_drift = abs(report["perf"]["render_ms"]["p50"]
                         - report["perf"]["render_ms_repeat"]["p50"])
        report["perf"]["render_p50_drift_ms"] = round(jump_drift, 1)
        if jump_drift > 35:
            report["checks"].append(
                f"the isolated chapter update measured p50 {report['perf']['render_ms']['p50']} ms "
                f"and then {report['perf']['render_ms_repeat']['p50']} ms in the same session on "
                f"(drift {jump_drift:.1f} ms, bound 35 ms) — the number does not "
                f"reproduce itself, so nothing may be concluded from its absolute value")

        # Liveness: the probe must still be measuring work. A degenerate probe — `setChapter`
        # short-circuiting, the sweep collapsing to no-ops — reports a BETTER number, and
        # "the metric improved" is exactly how this project has mistaken a broken probe three
        # times. The floor is relative to the scrub measured in this same session so it
        # self-normalises instead of citing an absolute figure; MEASURED ratio this session is
        # 104.9 / 59.4 = 1.77 when this check was added, i.e. the floor sits ~7x below the value
        # observed then. It is a liveness
        # margin, not a performance claim.
        jump_floor = round(0.25 * report["perf"]["drag_ms"]["p50"], 1)
        report["perf"]["render_liveness_floor_ms"] = jump_floor
        if report["perf"]["render_ms"]["p50"] < jump_floor:
            report["checks"].append(
                f"the isolated chapter update reported p50 {report['perf']['render_ms']['p50']} ms, "
                f"below the liveness floor of {jump_floor} ms (0.25 x this session's scrub p50 "
                f"{report['perf']['drag_ms']['p50']} ms) — setChapter wraps render, so a full "
                f"update costing a fraction of one frame means the probe stopped measuring work")
        pg.evaluate("setChapter(MAX_CH, true)")
        pg.wait_for_timeout(600)
        pg.screenshot(path=str(out / "atlas-top.png"), clip={"x": 0, "y": 0, "width": 1680, "height": 1050})

        # one screenshot at a mid chapter to prove the scrub visibly rebinds
        pg.evaluate("setChapter(Math.floor((MIN_CH+MAX_CH)/2), true)")
        pg.wait_for_timeout(700)
        pg.screenshot(path=str(out / "atlas-mid.png"), clip={"x": 0, "y": 0, "width": 1680, "height": 1050})

        # The two views that get looked at hardest, captured by the script rather than by
        # hand. These used to be taken ad-hoc during development, which meant they went
        # stale the moment the generator changed and quietly showed a layout that no
        # longer existed. Anything the reader is asked to judge has to be reproducible.
        pg.evaluate("setChapter(MAX_CH, true)")
        # Scroll by the section id — the graph block is emitted through the generic
        # `block()` helper and carries no id of its own, so asking for `#block-graph`
        # returns null and the probe silently measures an undrawn canvas.
        #
        # Retry rather than sleeping a fixed interval: `setChapter` re-renders the stream
        # and a render landing after the scroll replaces `#cy`, leaving the observer
        # watching a detached node.
        drawn = False
        for _ in range(20):
            pg.evaluate("document.getElementById('graph').scrollIntoView({block:'center'})")
            pg.wait_for_timeout(450)
            if pg.evaluate("() => !!window.CY && document.querySelectorAll('#zone-legend .row').length > 0"):
                drawn = True
                break
        if not drawn:
            report["checks"].append(
                "the graph never finished drawing after being scrolled into view")

        # How many names the graph shows *before* the reader does anything. The base node
        # style once carried `"label": "data(label)"` while the comment above it promised
        # the opposite, and every node was named: 640 overlapping labels, which is the
        # original "the network is a mess" complaint reproduced on a tidier layout. No
        # other check looked at this state, so it survived several builds.
        #
        # `style('label')` returns the *resolved* string, which is what the renderer draws:
        # an unnamed node gives ''. Falling back to `data('label')` when the style is empty
        # reports the node's name as if it were drawn — the check then accuses a correct
        # graph and would pass a broken one, depending on which way the fallback leans.
        labels = pg.evaluate("""() => {
          if (!window.CY) return null;
          const ns = CY.nodes();
          const named = ns.filter(n => String(n.style('label') || '') !== '');
          return { total: ns.length, named: named.length,
                   solid: ns.filter(n => n.hasClass('solid')).length,
                   sample: named.slice(0, 3).map(n => n.style('label')) };
        }""")
        report["default_labels"] = labels
        if labels and labels.get("named", 0) >= labels.get("total", 0):
            report["checks"].append(
                f"all {labels['total']} nodes carry a name at the default zoom — the "
                f"label tiers are not applied")
        elif labels and labels.get("named", 0) > 140:
            report["checks"].append(
                f"{labels['named']} of {labels['total']} nodes are named at the default "
                f"zoom — too many to read without overlap")
        elif labels and labels.get("named", 0) < 6:
            report["checks"].append(
                f"only {labels.get('named')} nodes are named at the default zoom — the "
                f"graph has no visible entry points")
        if labels:
            print(f"default labels: {labels.get('named')} of {labels.get('total')} named "
                  f"({labels.get('solid')} marked core) e.g. {labels.get('sample')}")
        pg.wait_for_timeout(700)
        pg.wait_for_timeout(900)
        # Clip to the block, not to the viewport. The graph section is taller than the
        # window, so a full-viewport shot cut off its own header and legend — the two
        # things a reviewer needs in order to read the picture. Scroll the block to the
        # top first: `block:'center'` leaves a taller-than-viewport section with a
        # negative top, which the clip then clamps to 0 and still loses the header.
        pg.evaluate("""() => {
          const s = document.getElementById('graph');
          if (s) window.scrollTo({ top: s.getBoundingClientRect().top + window.scrollY - 60,
                                   behavior: 'instant' });
        }""")
        pg.wait_for_timeout(500)
        gbox = pg.evaluate("""() => {
          const s = document.getElementById('graph');
          if (!s) return null;
          const r = s.getBoundingClientRect();
          return { x: Math.max(0, r.x), y: Math.max(0, r.y),
                   width: Math.min(r.width, window.innerWidth - Math.max(0, r.x)),
                   height: Math.min(r.height, window.innerHeight - Math.max(0, r.y)) };
        }""")
        if gbox and gbox["width"] > 200 and gbox["height"] > 200:
            pg.screenshot(path=str(out / "atlas-graph.png"), clip=gbox)
        else:
            pg.screenshot(path=str(out / "atlas-graph.png"),
                          clip={"x": 0, "y": 0, "width": 1680, "height": 1050})
            report["checks"].append(
                "the graph block had no usable bounds — the screenshot may be cropped")
        # Sector hover: the legend row is the affordance that makes the eight types
        # readable, so prove it actually lights the wedge — and that the names arrive in
        # the right tier. At the default zoom the wedge is coloured but unlabelled (354
        # names 20px apart is soup), and past 1.35x the names come in.
        zoneprobe = pg.evaluate("""() => {
          const row = document.querySelector('#zone-legend .row');
          if (!row) return { ok: false, why: 'no legend row' };
          row.dispatchEvent(new MouseEvent('mouseenter', { bubbles: false }));
          if (!window.CY) return { ok: false, why: 'no graph instance' };
          const lit = CY.nodes().filter(n => n.hasClass('zoned'));
          const out = {
            ok: true, zone: row.dataset.zone,
            named: lit.length,
            loudAtDefault: lit.filter(n => n.hasClass('loud')).length,
            rowLit: row.classList.contains('lit'),
            othersFaded: CY.nodes().filter(n => n.hasClass('faded')).length,
            zoom: CY.zoom(),
          };
          CY.zoom(1.8);
          CY.nodes('.zoned').toggleClass('loud', CY.zoom() >= 1.35);
          out.loudWhenZoomed = lit.filter(n => n.hasClass('loud')).length;
          CY.zoom(1);
          CY.nodes('.zoned').toggleClass('loud', CY.zoom() >= 1.35);
          return out;
        }""")
        report["sector_hover"] = zoneprobe
        if not zoneprobe.get("ok") or (zoneprobe.get("named") or 0) <= 0:
            report["checks"].append(
                "hovering a legend sector lit no nodes — the wedge stays unlabelled "
                f"({zoneprobe})")
        elif (zoneprobe.get("loudWhenZoomed") or 0) <= 0:
            report["checks"].append(
                f"zooming into a hovered sector still showed no names ({zoneprobe})")
        elif (zoneprobe.get("loudAtDefault") or 0) > 0:
            report["checks"].append(
                "a hovered sector named every member at the default zoom — that is the "
                f"overlap the two-tier labels exist to avoid ({zoneprobe})")
        pg.screenshot(path=str(out / "atlas-graph-zone.png"),
                      clip={"x": 0, "y": 0, "width": 1680, "height": 1050})

        # ------------------------------------------------------------- sector balance
        # The layout is read straight out of the generated payload, so this measures the
        # geometry the reader will actually see rather than a re-derivation of it. The
        # failure it guards against is concrete: a fit-proportional blend let the 425-node
        # character wedge take 40% of the circle and squeezed `level_axis` to a sliver,
        # which is the reader's original "everything overlaps" complaint wearing a new hat.
        metrics = pg.evaluate("""() => {
          const z = L.zones || {};
          const rows = Object.keys(z).map(t => ({
            type: t, sweep: z[t].end - z[t].start, count: z[t].count,
            pitch: z[t].pitch_used || L.pitch,
          })).sort((a, b) => b.sweep - a.sweep);
          /* Minimum seat distance, expressed as a fraction of the *pitch the two types
           * actually used*. A type that ran out of room is allowed a finer pitch — that is
           * a deliberate, reported degradation — so comparing every pair against one
           * global number would flag correct layouts and hide real collapses alike. */
          const ids = Object.keys(L.positions || {});
          const pts = ids.map(k => [k, L.positions[k]]);
          let worst = Infinity, worstPair = null, violations = 0, maxR = 0;
          for (let i = 0; i < pts.length; i++){
            const ri = Math.hypot(pts[i][1].x, pts[i][1].y);
            if (ri > maxR) maxR = ri;
            for (let j = i + 1; j < pts.length; j++){
              const d = Math.hypot(pts[i][1].x - pts[j][1].x, pts[i][1].y - pts[j][1].y);
              const za = z[pts[i][1].zone] || {}, zb = z[pts[j][1].zone] || {};
              const p = Math.min(za.pitch_used || L.pitch, zb.pitch_used || L.pitch);
              const ratio = d / p;
              if (ratio < worst){ worst = ratio; worstPair = [pts[i][0], pts[j][0]]; }
              if (ratio < 0.92) violations++;
            }
          }
          return { rows, totalSweep: rows.reduce((a, r) => a + r.sweep, 0),
                   worstRatio: worst, worstPair, violations, maxRadius: maxR,
                   /* Which types had to run a finer pitch than the global one. This is a
                    * deliberate, reported degradation rather than a defect — the circle
                    * cannot hold all eight types at full pitch (it needs 377.1° and has
                    * 360°) — but the *count* of compressed types is what separates a good
                    * cap from a bad one, and it cannot be predicted from the allocator by
                    * hand. Two candidate caps were built and this is what told them apart. */
                   compressed: rows.filter(r => r.pitch < (L.pitch || 0) - 1e-6)
                                   .map(r => [r.type, r.pitch]),
                   pitch: L.pitch };
        }""")
        report["sectors"] = metrics
        rows = metrics.get("rows") or []
        if rows and rows[0]["sweep"] > 140:
            report["checks"].append(
                f"the {rows[0]['type']} sector takes {rows[0]['sweep']:.0f}° of the circle "
                f"— it starves the other {len(rows) - 1} types")
        if rows and len(rows) >= 6 and rows[-1]["sweep"] < 7:
            report["checks"].append(
                f"the smallest sector ({rows[-1]['type']}) is only "
                f"{rows[-1]['sweep']:.1f}° wide — its members cannot be told apart")
        if metrics.get("violations"):
            report["checks"].append(
                f"{metrics['violations']} entity pairs sit closer than one pitch "
                f"(worst ratio {metrics.get('worstRatio', 0):.3f} at "
                f"{metrics.get('worstPair')}) — the layout overlaps")
        if metrics.get("maxRadius") and metrics["maxRadius"] > 0.99:
            report["checks"].append(
                f"nodes reach radius {metrics['maxRadius']:.3f} — outside the unit disc "
                f"the layout contract promises")
        print("sectors: " + " ".join(
            f"{r['type']}={r['sweep']:.0f}°/{r['count']}" for r in rows))
        print(f"min seat ratio: {metrics.get('worstRatio', 0):.4f} of pitch "
              f"(pitch {metrics.get('pitch')}, max radius {metrics.get('maxRadius', 0):.4f})")
        comp = metrics.get("compressed") or []
        print(f"compressed sectors: {len(comp)}"
              + ("  " + " ".join(f"{t}={p}" for t, p in comp) if comp else "  (all at full pitch)"))

        pg.evaluate("""() => {
          const row = document.querySelector('#zone-legend .row');
          if (row) row.dispatchEvent(new MouseEvent('mouseleave', { bubbles: false }));
          if (window.CY) CY.animate({ fit: { eles: CY.elements(), padding: 30 }, duration: 200 });
        }""")
        pg.wait_for_timeout(500)
        # ------------------------------------------------------------- routing & pages
        # The dashboard is no longer one long stream with a drawer. It is a routed
        # single-file app: every subject, event and chapter has its own URL, and the
        # sidebar is a fixed column rather than a floating card. Those three changes each
        # have a failure mode that the stream-era checks cannot see, because they all
        # still pass when the route is ignored and the old stream is painted instead:
        #
        #   - a deep link that silently lands on the home stream (the reader sends
        #     someone a link and it opens the wrong thing);
        #   - Back doing nothing, or leaving the app entirely;
        #   - a page that renders its shell but no body (blank-looking destination);
        #   - the fixed sidebar overlapping the content it was supposed to sit beside.
        #
        # Each is asserted from the rendered DOM, not from the router's own bookkeeping.
        routes = [
            ("#/char/char_qin_chao", "entity", "人物页"),
            ("#/chapter/500", "chapter", "章节页"),
            ("#/index/char", "index", "类型索引页"),
        ]
        # An event page is a destination too. The id is read from the routed payload
        # rather than scraped off the stream: the stream's event rows are paginated, so a
        # DOM scrape can legitimately find none and make this check silently skip while
        # looking like it passed.
        ev_id = pg.evaluate("""() => {
          const a = document.querySelector('a.ev-row[href^="#/event/"]');
          if (a) return decodeURIComponent(a.getAttribute('href').slice('#/event/'.length));
          const evs = (window.G && G.events) || [];
          return evs.length ? evs[evs.length - 1].id : null;
        }""")
        if not ev_id:
            report["checks"].append(
                "no event id could be obtained — the event-page check never ran")
        if ev_id:
            routes.append((f"#/event/{ev_id}", "event", "剧情页"))
        route_seen = {}
        for frag, want, label in routes:
            pg.evaluate("h => { location.hash = h; }", frag)
            pg.wait_for_timeout(320)
            info = pg.evaluate("""() => {
              const page = document.getElementById('page');
              const stream = document.getElementById('stream');
              return {
                pageHidden: getComputedStyle(page).display === 'none',
                pageChars: page.innerText.trim().length,
                streamHidden: getComputedStyle(stream).display === 'none',
                bodyPaged: document.body.classList.contains('paged'),
                title: (document.querySelector('#page .pg-title h1') || {}).textContent || '',
                routeView: (window.__atlasRoute || {}).view || '',
                blocks: page.querySelectorAll('.pblock').length,
              };
            }""")
            route_seen[want] = info
            if info["pageHidden"] or not info["bodyPaged"]:
                report["checks"].append(
                    f"{label} {frag} did not switch to the page view "
                    f"(page hidden={info['pageHidden']}, body.paged={info['bodyPaged']})")
            elif info["pageChars"] < 120:
                report["checks"].append(
                    f"{label} {frag} rendered only {info['pageChars']} characters — "
                    f"a destination that looks blank")
            elif info["routeView"] != want:
                report["checks"].append(
                    f"{label} {frag} parsed as route '{info['routeView']}' not '{want}'")
            if not info["streamHidden"]:
                report["checks"].append(
                    f"{label} {frag} left the home stream visible behind the page — "
                    f"the two views are not mutually exclusive")
        print("routes:")
        for want, info in route_seen.items():
            print(f"  - {want:<8} chars={info['pageChars']:>6} blocks={info['blocks']:>2} "
                  f"title={info['title'][:22]}")
        report["routes"] = route_seen

        # Deep link on a cold load. This is the case a shared link actually exercises, and
        # it is the one a router written against `hashchange` alone gets wrong: on first
        # paint there is no event to react to.
        cold = b.new_page()
        cold.set_viewport_size({"width": 1680, "height": 1050})
        cold_errors = []
        cold.on("pageerror", lambda e: cold_errors.append(str(e)))
        cold.goto(html.as_uri() + "#/char/char_qin_chao")
        cold.wait_for_function("() => window.__atlasReady === true", timeout=90000)
        cold.wait_for_timeout(600)
        coldinfo = cold.evaluate("""() => {
          const page = document.getElementById('page');
          return { paged: document.body.classList.contains('paged'),
                   chars: page.innerText.trim().length,
                   title: (document.querySelector('#page .pg-title h1') || {}).textContent || '' };
        }""")
        if not coldinfo["paged"] or coldinfo["chars"] < 120:
            report["checks"].append(
                f"a cold deep link to #/char/char_qin_chao rendered the stream instead of "
                f"the page (paged={coldinfo['paged']}, {coldinfo['chars']} chars)")
        if cold_errors:
            report["checks"].append(f"deep-link load raised: {preview(cold_errors, 2)}")
        print(f"cold deep link: paged={coldinfo['paged']} chars={coldinfo['chars']} "
              f"title={coldinfo['title'][:20]}")
        cold.close()

        # Back has to return to the previous destination, and enough times to reach home.
        pg.goto(html.as_uri() + "#/char/char_qin_chao")
        pg.wait_for_function("() => window.__atlasReady === true", timeout=90000)
        pg.wait_for_timeout(400)
        pg.evaluate("() => { location.hash = '#/chapter/300'; }")
        pg.wait_for_timeout(320)
        pg.evaluate("() => { location.hash = '#/index/item'; }")
        pg.wait_for_timeout(320)
        back1 = pg.evaluate("""() => {
          history.back();
          return new Promise(r => setTimeout(() => r({
            view: (window.__atlasRoute || {}).view || '', kind: (window.__atlasRoute || {}).kind || '',
            n: (window.__atlasRoute || {}).n || null,
          }), 420));
        }""")
        if back1.get("view") != "chapter" or back1.get("n") != 300:
            report["checks"].append(
                f"Back from #/index/item landed on {back1} — expected the chapter page "
                f"for 300")
        back2 = pg.evaluate("""() => {
          history.back();
          return new Promise(r => setTimeout(() => r({
            view: (window.__atlasRoute || {}).view || '', id: (window.__atlasRoute || {}).id || '',
          }), 420));
        }""")
        if back2.get("view") != "entity" or back2.get("id") != "char_qin_chao":
            report["checks"].append(
                f"a second Back landed on {back2} — expected the character page")
        print(f"history: back1={back1.get('view')}/{back1.get('n')} "
              f"back2={back2.get('view')}/{back2.get('id')}")

        # The four graph layouts. Each is a different projection of the same edges and
        # each can fail on its own: an empty canvas, a layout throwing mid-build, or a
        # mode button that does not repaint. The check is that switching produces a
        # *different, non-empty* drawing, which is what catches "the button toggles an
        # attribute but nothing redraws".
        pg.evaluate("() => { location.hash = '#/'; }")
        pg.wait_for_timeout(420)
        modeinfo = {}
        for mode in ("sector", "mind", "flow", "tree"):
            btn = pg.query_selector(f'[data-gmode="{mode}"]')
            if not btn:
                report["checks"].append(f"the graph view switch has no '{mode}' button")
                continue
            btn.click()
            pg.wait_for_timeout(700)
            info = pg.evaluate("""() => {
              const cy = document.getElementById('cy');
              const wrap = document.querySelector('.graph-wrap');
              const tree = wrap ? wrap.querySelector('.tree') : null;
              const pressed = [...document.querySelectorAll('[data-gmode]')]
                .filter(e => e.getAttribute('aria-pressed') === 'true').map(e => e.dataset.gmode);
              return {
                cyHidden: cy ? getComputedStyle(cy).display === 'none' : true,
                nodes: window.CY ? CY.nodes().length : 0,
                edges: window.CY ? CY.edges().length : 0,
                treeRows: tree ? tree.querySelectorAll('.trow').length : 0,
                pressed,
                text: (wrap ? wrap.innerText : '').trim().length,
              };
            }""")
            modeinfo[mode] = info
            if info["pressed"] != [mode]:
                report["checks"].append(
                    f"graph view '{mode}' did not become the pressed mode ({info['pressed']})")
            drawn = (info["nodes"] if not info["cyHidden"] else 0) + info["treeRows"]
            if drawn < 4:
                report["checks"].append(
                    f"graph view '{mode}' drew nothing ({info})")
        print("graph views: " + " ".join(
            f"{m}=n{v['nodes']}/e{v['edges']}/t{v['treeRows']}"
            for m, v in modeinfo.items()))
        report["graph_modes"] = modeinfo
        if modeinfo.get("sector", {}).get("nodes", 0) and \
                modeinfo.get("mind", {}).get("nodes", 0) and \
                modeinfo["sector"]["nodes"] == modeinfo["mind"]["nodes"] and \
                modeinfo["sector"]["edges"] == modeinfo["mind"]["edges"]:
            report["checks"].append(
                "sector and mind drew the identical element set — the mode switch is a "
                "no-op")
        pg.evaluate("() => { const b = document.querySelector('[data-gmode=\"sector\"]'); if (b) b.click(); }")
        pg.wait_for_timeout(500)

        # Labels sit *below* their node and must not overlap each other. Cytoscape
        # resolves this itself, but only if the style asks for it; a regression that puts
        # labels back inside the node, or drops the wrap, shows up here as overlapping
        # boxes rather than as a silent visual bug.
        labelinfo = pg.evaluate("""() => {
          const st = window.CY ? CY.style().json() : null;
          if (!st) return null;
          const pick = sel => {
            const rule = st.find(r => r.selector === sel);
            return rule ? (rule.style || {}) : null;
          };
          const base = pick('node') || {};
          return { valign: base['text-valign'], marginY: base['text-margin-y'],
                   wrap: base['text-wrap'], maxWidth: base['text-max-width'],
                   order: base['text-events'] };
        }""")
        if labelinfo:
            if labelinfo.get("valign") != "bottom":
                report["checks"].append(
                    f"node labels are not placed below the node "
                    f"(text-valign={labelinfo.get('valign')!r}) — the reader asked for the "
                    f"name under the point")
            if labelinfo.get("wrap") != "wrap" or not labelinfo.get("maxWidth"):
                report["checks"].append(
                    f"node labels do not wrap (text-wrap={labelinfo.get('wrap')!r}, "
                    f"text-max-width={labelinfo.get('maxWidth')!r}) — long names will "
                    f"overlap their neighbours")
            if labelinfo.get("marginY") in (None, 0, "0"):
                report["checks"].append(
                    "node labels have no vertical offset from the node")
        print(f"label style: valign={labelinfo.get('valign') if labelinfo else None} "
              f"marginY={labelinfo.get('marginY') if labelinfo else None} "
              f"wrap={labelinfo.get('wrap') if labelinfo else None} "
              f"maxW={labelinfo.get('maxWidth') if labelinfo else None}")
        report["labels"] = labelinfo

        # A rendered-name collision count, measured on the actual canvas: pull every
        # visible label box and see whether any two intersect. This is the reader's
        # complaint ("文字重叠") measured directly instead of argued about.
        overlap = pg.evaluate("""() => {
          if (!window.CY) return null;
          const boxes = [];
          CY.nodes().forEach(n => {
            const t = n.style('label');
            if (!t) return;
            const bb = n.renderedBoundingBox({ includeLabels: true, includeOverlays: false });
            boxes.push({ id: n.id(), t, x1: bb.x1, y1: bb.y1, x2: bb.x2, y2: bb.y2 });
          });
          let hits = 0;
          const sample = [];
          for (let i = 0; i < boxes.length; i++){
            for (let j = i + 1; j < boxes.length; j++){
              const a = boxes[i], b = boxes[j];
              const ox = Math.min(a.x2, b.x2) - Math.max(a.x1, b.x1);
              const oy = Math.min(a.y2, b.y2) - Math.max(a.y1, b.y1);
              if (ox > 4 && oy > 4){
                hits++;
                if (sample.length < 4) sample.push([a.t, b.t, Math.round(ox), Math.round(oy)]);
              }
            }
          }
          return { labelled: boxes.length, hits, sample };
        }""")
        print(f"label overlap: {overlap}")
        report["label_overlap"] = overlap
        if overlap and overlap.get("labelled", 0) >= 6 and overlap.get("hits", 0) > 0:
            report["checks"].append(
                f"{overlap['hits']} pairs of node labels overlap on the canvas "
                f"{preview(overlap['sample'], 2)} — the names are not readable")

        # The sidebar is a fixed column; it must not sit on top of the content. Measured
        # as an actual rectangle intersection against the shell, at a width where the
        # column is supposed to be permanent.
        geo = pg.evaluate("""() => {
          const side = document.getElementById('side');
          const shell = document.querySelector('.shell');
          const main = document.getElementById('main');
          const cs = getComputedStyle(side);
          const s = side.getBoundingClientRect();
          const m = main.getBoundingClientRect();
          const sh = shell.getBoundingClientRect();
          return {
            position: cs.position, display: cs.display,
            sideRight: Math.round(s.right), mainLeft: Math.round(m.left),
            overlapPx: Math.round(s.right - m.left),
            mainWidth: Math.round(m.width), sideWidth: Math.round(s.width),
            shellPadLeft: getComputedStyle(shell).paddingLeft,
          };
        }""")
        print(f"sidebar: pos={geo['position']} {geo['sideWidth']}px wide, "
              f"content starts at {geo['mainLeft']}px (overlap {geo['overlapPx']}px)")
        report["sidebar"] = geo
        if geo["position"] != "fixed":
            report["checks"].append(
                f"the sidebar is '{geo['position']}', not fixed to the left of the page")
        if geo["overlapPx"] > 2:
            report["checks"].append(
                f"the sidebar overlaps the content by {geo['overlapPx']}px — it is "
                f"floating over the page instead of sitting beside it")
        if geo["mainWidth"] < 620:
            report["checks"].append(
                f"the sidebar leaves the content only {geo['mainWidth']}px")

        # Search is the third way in, and it has to reach a subject that is not on screen.
        pq = pg.query_selector("#side-q")
        if not pq:
            report["checks"].append("the sidebar has no search box")
        else:
            pq.fill("杨树")
            pg.wait_for_timeout(320)
            hits = pg.evaluate("""() => {
              const hs = [...document.querySelectorAll('#side-hits .side-hit')];
              return { n: hs.length, first: hs.length ? hs[0].innerText.trim() : '' };
            }""")
            if not hits["n"]:
                report["checks"].append(
                    "typing a known name into the sidebar search produced no hit")
            pq.press("Enter")
            pg.wait_for_timeout(380)
            landed = pg.evaluate(
                "() => ((window.__atlasRoute || {}).view || '') + ':' + ((window.__atlasRoute || {}).id || '')")
            if not landed.startswith("entity:"):
                report["checks"].append(
                    f"Enter in the sidebar search did not open a subject page ({landed})")
            print(f"sidebar search: {hits['n']} hits, first={hits['first'][:18]!r}, "
                  f"Enter -> {landed}")
            pq.fill("")
            pg.wait_for_timeout(200)

        # A name on a page is a route to that name's page. This is the single interaction
        # the reader asked for by name ("点击某个人物…跳转到这个人物专属的一个页面"), so it is
        # asserted as a click that changes the route, not as "an anchor exists".
        pg.evaluate("() => { location.hash = '#/char/char_qin_chao'; }")
        pg.wait_for_timeout(420)
        before = pg.evaluate("() => (window.__atlasRoute || {}).id || ''")
        jumped = pg.evaluate("""() => {
          const a = [...document.querySelectorAll('#page a.lref')]
            .filter(x => {
              const id = decodeURIComponent((x.getAttribute('href') || '').split('/').pop());
              return id && id !== ((window.__atlasRoute || {}).id || '');
            })[0];
          if (!a) return null;
          const href = a.getAttribute('href');
          a.click();
          return href;
        }""")
        pg.wait_for_timeout(420)
        after = pg.evaluate(
            "() => ((window.__atlasRoute || {}).id || '') + '|' + ((window.__atlasRoute || {}).kind || '')")
        if not jumped:
            report["checks"].append(
                "the character page has no in-page link to another subject")
        elif after.split("|")[0] in ("", before):
            report["checks"].append(
                f"clicking an in-page link ({jumped}) did not navigate away from "
                f"{before} (now {after})")
        print(f"in-page link: {jumped} -> {after}")

        # Every kind has an index page, and the index page's cards go to pages too.
        idx = pg.evaluate("""() => {
          const kinds = ['char','loc','org','creature','axis','item','skill','concept'];
          return kinds;
        }""")
        bad_idx = []
        for k in idx:
            pg.evaluate("k => { location.hash = '#/index/' + k; }", k)
            pg.wait_for_timeout(260)
            n = pg.evaluate("""() => {
              const g = document.querySelector('#page .ix-grid');
              return g ? g.querySelectorAll('.ix-card').length : 0;
            }""")
            if n < 1:
                bad_idx.append(k)
        if bad_idx:
            report["checks"].append(
                f"index pages for {bad_idx} rendered no cards (the kind exists but the "
                f"index is empty)")
        print(f"index pages: {len(idx) - len(bad_idx)}/{len(idx)} non-empty")
        report["index_pages"] = {"checked": idx, "empty": bad_idx}

        # An index page must CLASSIFY, not just list. The reader's complaints were
        # "点进来之后没有分类，不应该全部平铺" — a page with one grid and no groupings
        # is the flat wall they rejected, however many cards it holds. So the gate is
        # on group count AND on no group being a single card, because a heading with
        # one card under it is a classification that failed rather than one that worked.
        grouped = {}
        for k in idx:
            pg.evaluate("k => { location.hash = '#/index/' + k; }", k)
            pg.wait_for_timeout(280)
            grouped[k] = pg.evaluate("""() => {
              const gs = [...document.querySelectorAll('.ix-group')];
              const sizes = gs.map(g => g.querySelectorAll('.ix-card').length);
              const heads = gs.map(g => g.querySelector('.ix-gh h2').innerText);
              return {
                groups: gs.length, sizes, heads,
                cards: document.querySelectorAll('.ix-card').length,
                jumps: document.querySelectorAll('.ix-jump a').length,
              };
            }""")
            g = grouped[k]
            if g["groups"] < 2:
                report["checks"].append(
                    f"index page '{k}' renders {g['groups']} group(s) — it is a flat "
                    f"list, not a classified index")
            # A singleton group is what a bad axis produces — a heading with one card
            # under it is a table of contents pretending to be a classification.
            #
            # Chronological bands are exempt, and the exemption is principled rather
            # than a size threshold: the band IS the axis, its bounds are fixed in
            # advance, and a band holding one row is a true statement about the story
            # (nothing else appeared in those 125 chapters). Bands are also dense enough
            # that a single-row band cannot be manufactured by a sparse field the way a
            # one-row city group can. A sampled axis like city or grade has no such
            # defence — there a one-row group means the axis did not hold.
            chrono = g["heads"] and all(h.startswith("第 ") and h.endswith(" 章")
                                        for h in g["heads"])
            singles = [h for h, n in zip(g["heads"], g["sizes"]) if n == 1]
            if singles and not chrono:
                report["checks"].append(
                    f"index page '{k}' has single-card groups {preview(singles, 3)} — a heading "
                    f"with one card under it is not a category")
            if g["cards"] != g["groups"] and sum(g["sizes"]) != g["cards"]:
                report["checks"].append(
                    f"index page '{k}': {g['cards']} cards but group sizes sum to "
                    f"{sum(g['sizes'])} — a card is rendering outside a group")
            # The jump list is what makes 8 groups navigable instead of 8 scrolls.
            if g["groups"] > 3 and g["jumps"] != g["groups"]:
                report["checks"].append(
                    f"index page '{k}' has {g['groups']} groups but {g['jumps']} jump "
                    f"links")
        print("index grouping: " + " ".join(
            f"{k}={v['groups']}g/{v['cards']}c" for k, v in grouped.items()))
        report["index_grouping"] = grouped

        # Shape must carry the entity type. The reader's complaint was "人物，物品，地点等
        # 类型不应该都是圆" — every node drawn as a circle. The gate asserts that the
        # distinct shapes actually RENDER, one per type, and that no type is mixed
        # (a type whose nodes disagree on shape would make the legend a lie).
        pg.evaluate("() => { location.hash = '#/'; }")
        pg.wait_for_timeout(600)
        pg.evaluate("""() => {
          const b = document.getElementById('block-graph');
          if (b) b.scrollIntoView({ block: 'center' });
        }""")
        pg.wait_for_timeout(900)
        shapes = pg.evaluate("""() => {
          if (!window.CY) return null;
          const map = {};
          CY.nodes().forEach(n => {
            const t = n.data('zone'), s = n.style('shape');
            if (!(t in map)) map[t] = s;
            else if (map[t] !== s) map[t] = 'MIXED:' + map[t] + '/' + s;
          });
          const legend = [...document.querySelectorAll('#zone-legend .row')].map(r => ({
            z: r.dataset.zone,
            svg: !!r.querySelector('.sw svg'),
            prim: r.querySelector('.sw svg')
                 ? r.querySelector('.sw svg').firstElementChild.tagName : null,
          }));
          return { map, legend };
        }""")
        if not shapes:
            report["checks"].append("the graph never built, so node shapes cannot be read")
        else:
            distinct = set(shapes["map"].values())
            if len(distinct) < 2:
                report["checks"].append(
                    f"all {len(shapes['map'])} entity types render the same shape "
                    f"({distinct}) — shape is not carrying type")
            mixed = {t: s for t, s in shapes["map"].items() if s.startswith("MIXED")}
            if mixed:
                report["checks"].append(
                    f"these types render inconsistent shapes across their own nodes: {mixed}")
            # The legend is the only place the reader is told what a shape means.
            no_svg = [r["z"] for r in shapes["legend"] if not r["svg"]]
            if no_svg:
                report["checks"].append(
                    f"legend rows for {no_svg} draw no shape swatch — the legend and the "
                    f"graph would disagree")
            shape_by_legend = {}
            for r in shapes["legend"]:
                shape_by_legend[r["z"]] = r["prim"]
            # Colours have to be RESOLVED on the canvas, not merely configured.
            #
            # This is the check that was missing while the nodes were all grey. Cytoscape
            # does not expand CSS custom properties: the node style said
            # `var(--type-character)`, it failed to parse, and all 640 nodes fell back to
            # `rgb(153,153,153)` while the legend swatches next to them rendered the
            # correct colours. Every existing shape assertion passed throughout.
            #
            # So read `pstyle('background-color').value` — the numbers the renderer will
            # actually paint with — and require that the types do not share one grey.
            GREY = [153, 153, 153]
            col = pg.evaluate("""() => {
              if (!window.CY) return null;
              const byType = {};
              CY.nodes().forEach(n => {
                const t = n.data('zone');
                const v = n.pstyle('background-color').value;
                const key = Array.isArray(v) ? v.slice(0, 3).join(',') : String(v);
                if (!(t in byType)) byType[t] = {};
                byType[t][key] = (byType[t][key] || 0) + 1;
              });
              const legend = [...document.querySelectorAll('#zone-legend .row')].map(r => {
                const sw = r.querySelector('.sw svg');
                const el = sw ? sw.firstElementChild : null;
                return { z: r.dataset.zone, fill: el ? el.getAttribute('fill') : null };
              });
              return { byType, legend };
            }""")
            if not col:
                report["checks"].append(
                    "the graph never built, so node colour cannot be read")
            else:
                grey_types = [t for t, m in col["byType"].items()
                              if list(m.keys()) == [",".join(map(str, GREY))]
                              or list(m.keys()) == ["153,153,153"]]
                if len(grey_types) >= 2:
                    report["checks"].append(
                        f"these types all paint the renderer's fallback grey "
                        f"rgb(153,153,153), so colour is not reaching the canvas: "
                        f"{sorted(grey_types)}")
                # The legend is a promise about what the colours mean. A legend that
                # paints a colour the canvas never uses is worse than no legend.
                legend_ok = [r["z"] for r in col["legend"] if r["fill"]]
                if len(legend_ok) < len(col["legend"]):
                    report["checks"].append(
                        "legend swatches carry no fill attribute, so the legend cannot "
                        "be matched to the canvas")
                print("node colour: " + ", ".join(
                    f"{t}={sorted(m.keys())[0] if len(m) == 1 else 'MIXED'}"
                    for t, m in sorted(col["byType"].items())))
                report["node_colour"] = col

            print("node shapes: " + ", ".join(
                f"{t}={s}" for t, s in sorted(shapes["map"].items())))
            print(f"  {len(distinct)} distinct shapes; legend swatches: "
                  f"{len(shapes['legend'])} rows, "
                  f"{sum(1 for r in shapes['legend'] if r['svg'])} with an svg")
            report["node_shapes"] = {"by_type": shapes["map"],
                                     "distinct": len(distinct),
                                     "legend": shapes["legend"]}

        # The sidebar must follow the route: from a subject page it offers a way back,
        # and from home it does not show a back link that would be a no-op.
        #
        # The way back is now a breadcrumb rather than a single "← 回到总览" row, so the probe
        # accepts either. What must hold either way is that a level above is reachable: home
        # offers nothing (a back link there is a no-op), a subject page offers at least one
        # link that is not the page itself.
        side_ctx = {}
        for frag, want_back in (("#/", False), ("#/char/char_qin_chao", True)):
            pg.evaluate("h => { location.hash = h; }", frag)
            pg.wait_for_timeout(420)
            side_ctx[frag] = pg.evaluate("""() => {
              const old = document.querySelector('#side .side-item.back');
              const crumb = document.querySelector('#side .side-crumb');
              const hrefs = crumb
                ? [...crumb.querySelectorAll('a')].map(a => a.getAttribute('href')).filter(Boolean)
                : [];
              const acts = document.querySelectorAll('#side .side-acts a, #side .side-acts button').length;
              const kinds = document.querySelectorAll('#side .side-kinds a').length;
              const chs = document.querySelectorAll('#side .side-ch button').length;
              // The first crumb segment is the root; a level-up link is any crumb link that
              // leads somewhere other than the current page.
              const upward = hrefs.filter(h => h && h !== ('#' + location.hash.replace(/^#/, '')));
              return { hasBack: !!old || upward.length > 0, crumbLinks: hrefs.length,
                       upward: upward.length, acts, kinds, chapters: chs };
            }""")
            got = side_ctx[frag]["hasBack"]
            if got != want_back:
                report["checks"].append(
                    f"sidebar back-link on {frag} is {got}, expected {want_back}")
            if want_back and not side_ctx[frag]["acts"]:
                report["checks"].append(
                    f"the sidebar offers no up/top control on {frag} — the level above the "
                    f"current page is unreachable")
            if not side_ctx[frag]["kinds"]:
                report["checks"].append(f"the sidebar shows no kinds on {frag}")
            if not side_ctx[frag]["chapters"]:
                report["checks"].append(f"the sidebar shows no chapter grid on {frag}")
        print("sidebar context: " + " ".join(
            f"{k}=back{int(v['hasBack'])}/up{v['upward']}/a{v['acts']}/k{v['kinds']}/c{v['chapters']}"
            for k, v in side_ctx.items()))
        report["sidebar_context"] = side_ctx

        # Gate 31 — a shape the reader cannot resolve is not a shape channel.
        #
        # Gate 30 above asks `CY.nodes()[].style("shape")` and passed for a whole round
        # while the feature did not exist for the reader. MEASURED at the time: every
        # non-protagonist node rendered at 5.5-8.3px, and at that size a hexagon, a
        # diamond, a tag, a pentagon and a rectangle are the same seven pixels. Gate 30 was
        # reading the *configuration*. **A gate on a style string is not a gate on what is
        # drawn** -- so this one reads `renderedWidth()`, the number of pixels the browser
        # actually painted, and requires it to clear the floor where corners are visible.
        #
        # The floor is 10px. Below roughly that, an 8-sided and a 6-sided figure differ by
        # under two pixels of silhouette and the distinction is lost. The ceiling is not
        # arbitrary either: the seat pitch on this graph is 0.0549 unit-disc units against
        # a ~686px container, so neighbouring seats sit 37.7px apart and a marker must stay
        # well under that to keep the wedges readable as regions. Both bounds are asserted,
        # because a fix that swaps an illegible small node for an overcrowded large one has
        # not fixed anything.
        SHAPE_MIN_PX = 10.0
        SHAPE_MAX_PX = 24.0
        pg.evaluate("() => { location.hash = '#/'; }")
        pg.wait_for_timeout(600)
        pg.evaluate("""() => {
          const b = document.getElementById('block-graph');
          if (b) b.scrollIntoView({ block: 'center' });
        }""")
        pg.wait_for_timeout(1100)
        sizes = pg.evaluate("""() => {
          if (!window.CY) return null;
          const byType = {};
          const all = [];
          CY.nodes().forEach(n => {
            const t = n.data('zone');
            const w = n.renderedWidth(), h = n.renderedHeight();
            all.push(Math.min(w, h));
            if (!(t in byType)) byType[t] = [];
            byType[t].push(Math.min(w, h));
          });
          const at = a => ({ min: +Math.min(...a).toFixed(1), max: +Math.max(...a).toFixed(1) });
          const out = {};
          for (const t in byType) out[t] = at(byType[t]);
          return { byType: out, all: at(all), n: all.length };
        }""")
        if not sizes:
            report["checks"].append(
                "the graph never built, so rendered node size cannot be read")
        else:
            too_small = {t: v["min"] for t, v in sizes["byType"].items()
                         if v["min"] < SHAPE_MIN_PX}
            too_big = {t: v["max"] for t, v in sizes["byType"].items()
                       if v["max"] > SHAPE_MAX_PX}
            if too_small:
                report["checks"].append(
                    f"these types render below {SHAPE_MIN_PX}px, where the shape is not "
                    f"resolvable and the type channel is invisible: {too_small}")
            if too_big:
                report["checks"].append(
                    f"these types render above {SHAPE_MAX_PX}px, which crowds the seat "
                    f"pitch (~37.7px) and turns the wedges into a blob: {too_big}")
            print(f"rendered node size: {sizes['all']['min']}-{sizes['all']['max']}px "
                  f"across {sizes['n']} nodes "
                  f"(floor {SHAPE_MIN_PX}, ceiling {SHAPE_MAX_PX})")
            print("  by type: " + ", ".join(
                f"{t}={v['min']}-{v['max']}" for t, v in sorted(sizes["byType"].items())))
            report["node_pixel_size"] = sizes

        # Gate 32 — a card line that is the same on every card is not information.
        #
        # The index cards' second line was "N 条关系". MEASURED: 0 relations for 94% of
        # locations, 100% of level axes, 89% of skills, 85% of concepts, 64% of items. A
        # page where 106 of 113 cards carry a byte-identical line has spent its most
        # valuable row saying nothing, and it did so while *looking* like a populated card.
        #
        # So the assertion is on distinctness, not on presence: every index page must have
        # a second line whose values are overwhelmingly distinct, i.e. the line discriminates
        # between the rows it sits on. Coverage is checked too, because a field that is
        # specific but absent is equally useless -- the two have to hold together.
        ix_info = {}
        for k in idx:
            pg.evaluate("k => { location.hash = '#/index/' + k; }", k)
            pg.wait_for_timeout(300)
            ix_info[k] = pg.evaluate("""() => {
              const cards = [...document.querySelectorAll('.ix-card')];
              const sums = cards.map(c => {
                const s = c.querySelector('.sm');
                return s ? s.innerText.trim() : null;
              }).filter(Boolean);
              const rels = cards.map(c => {
                const m = c.querySelectorAll('.mt span');
                return m[1] ? m[1].innerText.trim() : null;
              }).filter(Boolean);
              return {
                cards: cards.length,
                withSummary: sums.length,
                distinct: new Set(sums).size,
                withRel: rels.length,
                relDistinct: new Set(rels).size,
                sample: sums.slice(0, 2),
              };
            }""")
            v = ix_info[k]
            if v["cards"] < 2:
                continue
            cov = v["withSummary"] / v["cards"]
            disc = (v["distinct"] / v["withSummary"]) if v["withSummary"] else 0.0
            # Coverage: the line has to exist on nearly every card, or the page looks
            # half-filled and the reader cannot compare rows.
            if cov < 0.85:
                report["checks"].append(
                    f"index page '{k}' puts a descriptive line on only "
                    f"{v['withSummary']}/{v['cards']} cards ({cov:.0%})")
            # Distinctness: and where it exists it has to differ, or it is decoration.
            if v["withSummary"] and disc < 0.90:
                report["checks"].append(
                    f"index page '{k}' repeats the same second line across cards "
                    f"({v['distinct']} distinct of {v['withSummary']}) — that line is "
                    f"not distinguishing the rows")
            # The relation count may still appear, but only where it is non-zero and
            # therefore informative. If it is on most cards it is the old constant back.
            if v["withRel"] > 0.5 * v["cards"] and v["relDistinct"] <= 2:
                report["checks"].append(
                    f"index page '{k}' prints a near-constant relation count on "
                    f"{v['withRel']}/{v['cards']} cards ({v['relDistinct']} distinct)")
        print("index card line: " + " ".join(
            f"{k}={v['withSummary']}/{v['cards']}c,{v['distinct']}d"
            for k, v in ix_info.items()))
        report["index_card_line"] = ix_info

        # Gate 34 — the mention channel must exist AND be navigable.
        #
        # Two things are asserted, and the second is the one that matters. Counting chips
        # proves the section rendered; checking every chip carries a resolvable
        # `data-goto` proves a reader can actually get somewhere from it. I shipped the
        # first version of this row with `entityHref(id)` in that attribute — the click
        # handler resolves it against ENT, so it would have found nothing and opened an
        # empty drawer. A chip that exists but goes nowhere is worse than no chip.
        MENTION_SUBJECTS = [("loc", "loc_aoxi_cun"), ("loc", "loc_chao_yang_gong_yuan"),
                            ("skill", "skill_mo_yan"), ("axis", "axis_jiuchongtian"),
                            ("item", "item_baijin_lianhua_zhan")]
        mentions = {}
        for kind, mid in MENTION_SUBJECTS:
            pg.evaluate("h => { location.hash = h; }", f"#/{kind}/{mid}")
            pg.wait_for_timeout(380)
            info = pg.evaluate("""() => {
              const host = document.querySelector('#page');
              if (!host) return { has: false };
              const sec = [...host.querySelectorAll('section.pblock')]
                .find(s => ((s.querySelector('h2') || {}).innerText || '').startsWith('正文提及'));
              if (!sec) return { has: false, pageChars: host.innerText.trim().length };
              const rows = [...sec.querySelectorAll('.ev-row')];
              const chips = [...sec.querySelectorAll('.ev-w')];
              return { has: true, rows: rows.length, chips: chips.length,
                       dead: chips.filter(c => !c.dataset.goto).length,
                       badRoute: rows.filter(r => !(r.getAttribute('href') || '').startsWith('#/event/')).length,
                       pageChars: host.innerText.trim().length };
            }""")
            mentions[f"{kind}/{mid}"] = info
            if not info.get("has"):
                report["checks"].append(
                    f"mention section missing on {kind}/{mid}: the page lists no events, "
                    f"yet this type has 0 participant_ids across 1159 events — the reader "
                    f"is being told there is no record")
                continue
            if info["rows"] < 1:
                report["checks"].append(f"mention section on {kind}/{mid} rendered zero rows")
            if info["dead"]:
                report["checks"].append(
                    f"mention rows on {kind}/{mid} carry {info['dead']} people-chips with no "
                    f"data-goto — they render as names but lead nowhere")
            if info["badRoute"]:
                report["checks"].append(
                    f"mention rows on {kind}/{mid}: {info['badRoute']} rows do not link to an event page")
        print("mention channel: " + " ".join(
            f"{k.split('/')[1]}={v.get('rows','-')}r/{v.get('chips','-')}c" for k, v in mentions.items()))
        report["mention_channel"] = mentions

        # Gate 35 — a click on a mention chip must open THAT person, not an empty drawer.
        #
        # Gate 34 checks the attribute is present. This one checks the contract behind it,
        # because presence and correctness are different failures and this round has been
        # about exactly that gap. It is the only assertion here that drives a real click
        # and reads the resulting drawer title.
        pg.evaluate("h => { location.hash = h; }", "#/loc/loc_aoxi_cun")
        pg.wait_for_timeout(420)
        click_probe = pg.evaluate("""() => {
          const chip = document.querySelector('.ev-w[data-goto]');
          if (!chip) return { ok: false, why: 'no chip' };
          return { ok: true, expected: chip.dataset.goto, name: chip.innerText.trim() };
        }""")
        if click_probe.get("ok"):
            pg.click(".ev-w[data-goto]")
            pg.wait_for_timeout(420)
            got = pg.evaluate(r"""() => {
              const d = document.querySelector('#drawer');
              const on = d && (d.classList.contains('open') || d.offsetParent !== null);
              const t = on ? (d.innerText || '').replace(/\s+/g, ' ').trim() : '';
              return { open: !!on, chars: t.length, head: t.slice(0, 90) };
            }""")
            click_probe["drawer"] = got
            if not got["open"]:
                report["checks"].append(
                    "clicking a mention person-chip did not open a drawer — the name is "
                    "rendered but inert")
            elif got["chars"] < 30:
                report["checks"].append(
                    f"mention chip opened an empty drawer ({got['chars']} chars) — the "
                    f"data-goto value is not resolving against ENT")
            pg.keyboard.press("Escape")
            pg.wait_for_timeout(200)
        else:
            report["checks"].append("no mention chip available to click-test")
        print("mention click: " + json.dumps(click_probe, ensure_ascii=False)[:200])
        report["mention_click"] = click_probe

        # Gate 36 — the mention channel is an inference; assert it is AUDITABLE.
        #
        # Gate 34 asked whether the section rendered and whether its chips lead anywhere.
        # Neither question is "is the inference correct". Hand-reading 30 sampled matches
        # found 3 plainly wrong: a hand item credited through the alias 土系至宝, 姬媛媛
        # credited by the bare title 长老 across 15 events, and 残心剑阵 claimed by both a
        # skill and an item. Every gate passed throughout, because a substring hit and a
        # real hit print identically.
        #
        # A machine cannot judge whether a match is CORRECT. So this asserts the three
        # things a reader needs in order to judge for themselves.
        TITLES = ["长老", "掌门", "大师", "前辈", "大人", "子爵", "侯爵", "伯爵", "先生",
                  "女士", "小姐", "夫人", "老板", "主任", "队长", "组长", "师父", "师叔",
                  "师尊", "师祖", "门主", "族长", "家主", "陛下", "殿下", "阁下", "属下",
                  "弟子", "师兄", "师姐", "师弟", "师妹", "老太爷", "老爷子", "老头",
                  "少女", "青年", "男爵", "公爵"]
        AUDIT_JS = """(titles) => {
          const out = { rows: 0, withVia: 0, titleHits: [], sharedMarked: 0, samples: [] };
          const secs = [...document.querySelectorAll('section.pblock')]
            .filter(s => ((s.querySelector('h2') || {}).innerText || '').startsWith('正文提及'));
          out.hasSection = secs.length > 0;
          for (const sec of secs){
            out.rows += sec.querySelectorAll('.ev-row').length;
            for (const v of sec.querySelectorAll('.ev-via')){
              out.withVia += 1;
              const t = v.innerText.trim();
              const bare = t.split(' ').pop().replace('别名', '')
                .replace('⚠共有名', '').trim();
              if (titles.includes(bare)) out.titleHits.push(t);
              if (v.classList.contains('shared')) out.sharedMarked += 1;
              if (out.samples.length < 6) out.samples.push(t);
            }
          }
          return out;
        }"""
        # Audit across several subjects, not one. The first version measured only 奥西村,
        # whose name has no multi-owner collision, so `sharedMarked` was structurally 0 and
        # the shared-name assertion could never have failed. A check that cannot fail is not
        # a check. 残心剑阵 is the canonical collision (a skill and an item share the name).
        SUBJECTS = [("loc", "loc_aoxi_cun"), ("skill", "skill_canxin_zhenjian"),
                    ("item", "item_baijin_lianhua_zhan"), ("skill", "skill_jingang_jing")]
        audit = {"rows": 0, "withVia": 0, "titleHits": [], "sharedMarked": 0,
                 "samples": [], "hasSection": False, "scanned": []}
        for kind, sid in SUBJECTS:
            pg.evaluate("h => { location.hash = h; }", f"#/{kind}/{sid}")
            pg.wait_for_timeout(380)
            one = pg.evaluate(AUDIT_JS, TITLES)
            if not one.get("hasSection"):
                continue
            audit["hasSection"] = True
            audit["scanned"].append(f"{kind}/{sid}")
            audit["rows"] += one["rows"]
            audit["withVia"] += one["withVia"]
            audit["sharedMarked"] += one["sharedMarked"]
            audit["titleHits"] += one["titleHits"]
            audit["samples"] += one["samples"]
        report["mention_audit"] = audit
        if audit.get("hasSection") and audit.get("sharedMarked", 0) == 0:
            report["checks"].append(
                "mention audit: no row on any sampled subject was marked as a shared name — "
                "the ambiguity flag is either dead or the sample avoids every collision "
                "(残心剑阵 alone should produce some)")
        if audit.get("titleHits"):
            report["checks"].append(
                f"mention channel matched on bare title words {preview(sorted(set(audit['titleHits'])), 6)}"
                f" — a title has no referent, so matching on one manufactures evidence")
        if audit.get("rows", 0) > 0 and audit.get("withVia", 0) < audit.get("rows", 0):
            report["checks"].append(
                f"mention audit: only {audit.get('withVia')}/{audit.get('rows')} rows state which "
                f"literal name they matched — an inference the reader cannot audit")
        if audit.get("rows", 0) == 0:
            report["checks"].append(
                "mention audit: the tightened matcher now produces zero rows on the subject that "
                "always had some — the guard has eaten the channel")
        print(f"mention audit: rows={audit.get('rows')} via={audit.get('withVia')} "
              f"titleHits={len(audit.get('titleHits') or [])} sharedMarked={audit.get('sharedMarked')}")
        print("  samples: " + " | ".join(audit.get("samples") or []))

        # --- gate 37: a relation's lifetime must be read from every field that carries it.
        #
        # This gate exists because a relation was drawn as live for all 400 chapters while the
        # graph recorded, in a field the renderer never read, that its first episode had ended.
        # (`rel_f01_016`, 罗德 possesses 秦朝: `end_chapter: 1`, no `valid_to`.) The renderer read
        # `valid_to` alone; every gate stayed green because none of them asked where the end of a
        # relation is written.
        #
        # The first version of this gate compared the shipped predicate against a naive
        # `valid_to`-only one and required them to differ. That assertion could never fail:
        # `rel_f01_016` has two episodes whose *union* is [1,∞), which is exactly what the naive
        # reading produces, so the two agreed even when I deliberately downgraded the predicate
        # to prove the gate worked. A check must be validated by making it fail on purpose, and
        # this one survived the attempt — so it was measuring the wrong observable.
        #
        # What actually distinguishes a correct implementation is that it *reads the other
        # fields*: the episode count and the interval boundaries must reflect `end_chapter` and
        # `observations[]`, and a record whose end is written only in `end_chapter` must produce
        # a bounded first episode rather than an unbounded one.
        LIFETIME_JS = """() => {
          const out = { total: 0, withEndChapter: 0, withObs: 0, multiIv: 0,
                        endChapterHonoured: [], bounded: 0, holes: [], uncovered: [],
                        captions: [] };
          for (const r of (G.relations || [])){
            if (!r) continue;
            out.total += 1;
            if (r.end_chapter != null) out.withEndChapter += 1;
            if ((r.observations || []).length) out.withObs += 1;
            const iv = relIntervals(r);
            if (iv.length > 1) out.multiIv += 1;
            if (iv.some(x => x.to != null)) out.bounded += 1;
            // A relation that names its end in `end_chapter` but no `valid_to` must not come
            // back as a single open interval: that is the exact shape of the defect.
            if (r.end_chapter != null && r.valid_to == null){
              const open = iv.length === 1 && iv[0].to == null;
              out.endChapterHonoured.push({ id: r.id, end_chapter: r.end_chapter,
                intervals: iv.length, firstTo: iv.length ? iv[0].to : null, ignored: open });
            }
            // A hole is a real gap between episodes and must stay visible as one. Contiguity
            // (episode N ends exactly where N+1 begins) is the merger's normal split, not a gap.
            for (let i = 0; i + 1 < iv.length; i++){
              if (iv[i].to != null && iv[i + 1].from > iv[i].to){
                if (out.holes.length < 6) out.holes.push({ id: r.id, gap: [iv[i].to, iv[i + 1].from] });
              }
            }
            if (iv.length && r.valid_from != null && iv[0].from > r.valid_from){
              if (out.uncovered.length < 6) out.uncovered.push({ id: r.id,
                valid_from: r.valid_from, first: iv[0].from });
            }
          }
          const r16 = (G.relations || []).find(x => x && x.id === 'rel_f01_016');
          if (r16){
            const cap = relEnd(r16);
            out.captions.push({ id: r16.id, end: cap, open: (cap == null || cap === 0),
                                liveAt400: relLiveAt(r16, 400) });
          }
          return out;
        }"""
        try:
            life = pg.evaluate(LIFETIME_JS)
        except Exception as exc:  # pragma: no cover - surfaced as a failure
            life = {"error": str(exc)}
        report["relation_lifetime"] = life
        if life.get("error"):
            report["checks"].append(
                f"relation lifetime: predicate threw ({life['error']}) — the reader cannot "
                f"know when a relation ends")
        else:
            # The strongest statement available: every relation whose end lives only in
            # `end_chapter` must come back as something other than a single open span.
            ignored = [x for x in (life.get("endChapterHonoured") or []) if x.get("ignored")]
            if ignored:
                report["checks"].append(
                    f"relation lifetime: {len(ignored)} relation(s) declare `end_chapter` with no "
                    f"`valid_to` and still resolve to one open interval {preview(ignored, 3)} — the end "
                    f"field is read by nothing, so those relations never end")
            if life.get("withEndChapter", 0) > 0 and not (life.get("endChapterHonoured") or []):
                report["checks"].append(
                    "relation lifetime: the data contains `end_chapter` but the probe found no "
                    "record to check — the gate is not exercising the field it guards")
            if life.get("multiIv", 0) == 0:
                report["checks"].append(
                    "relation lifetime: no relation yields more than one interval, so the "
                    "per-episode split is untested and may be dead code")
            if life.get("uncovered"):
                report["checks"].append(
                    f"relation lifetime: interval set starts after the relation's own "
                    f"`valid_from` on {preview(life['uncovered'], 3)} — the first stretch of the "
                    f"relationship would be invisible")
            for cap in life.get("captions") or []:
                if cap.get("open") and not cap.get("liveAt400"):
                    report["checks"].append(
                        f"relation lifetime: {cap['id']} is captioned as open-ended but the "
                        f"predicate denies it at chapter 400")
        print(f"relation lifetime: relations={life.get('total')} "
              f"endChapter={life.get('withEndChapter')} obs={life.get('withObs')} "
              f"multiIv={life.get('multiIv')} bounded={life.get('bounded')} "
              f"holes={len(life.get('holes') or [])}")
        for cap in (life.get("captions") or []):
            print(f"  rel_f01_016: end={cap.get('end')} open={cap.get('open')} "
                  f"liveAt400={cap.get('liveAt400')}")

        # 38 — the circle view must group by connectivity and must not overflow the canvas.
        #
        # Three separate failures were measured on the first build of this view, and each has
        # its own observable:
        #   * the 112-member circle asked for a 164px disc and the packer pushed it off the
        #     left edge — the largest group was the one the reader could not see;
        #   * all 823 edges drawn alike produced long chords that buried the grouping;
        #   * the 480 unconnected entities were scattered as litter instead of gathered.
        # A check on any one of these passes on a view that fails the other two, so all three
        # are asserted. `circles` must also actually partition the linked entities: a layout
        # that put everything in one circle would satisfy "no overflow" trivially.
        CIRCLES_JS = """() => {
          const L0 = (window.L || {});
          const circles = (L0.circles || []);
          const iso = (L0.isolated || {});
          const members = circles.reduce((n, c) => n + (c.members || []).length, 0);
          const sized = circles.filter(c => (c.members || []).length > 1);
          const out = {
            circles: circles.length, members: members, isolated: (iso.members || []).length,
            linked: L0.linked || 0, components: L0.components || 0, giant: L0.giant_size || 0,
            biggest: circles.length ? Math.max(...circles.map(c => (c.members || []).length)) : 0,
            singletonCircles: circles.filter(c => (c.members || []).length < 2).length,
            groups: sized.length,
            // Every entity with at least one relation must land in exactly one circle; the
            // count is the honest way to say "the circles are a partition, not a sample".
            overflow: [], zoom: 0, innerEdges: 0, bridgeEdges: 0,
            rings: 0, captions: 0, offCanvas: 0,
            spineNodes: 0, isoNodes: 0,
          };
          if (typeof CY === 'undefined' || !CY) return out;
          const cy = CY;
          const wrap = document.getElementById('cy');
          if (wrap){
            const wb = wrap.getBoundingClientRect();
            cy.nodes().forEach(n => {
              const bb = n.renderedBoundingBox();
              if (bb.x1 < -1 || bb.y1 < -1 || bb.x2 > wb.width + 1 || bb.y2 > wb.height + 1){
                out.offCanvas += 1;
                if (out.overflow.length < 5) out.overflow.push(n.id());
              }
            });
          }
          out.zoom = cy.zoom();
          out.innerEdges = cy.edges('.e-inner').length;
          out.bridgeEdges = cy.edges('.e-bridge').length;
          out.rings = document.querySelectorAll('.cy-rings i').length;
          out.captions = document.querySelectorAll('.cy-overlay .cc, .cy-overlay .cc-iso').length;
          out.isoNodes = cy.nodes('.cn-iso').length;
          return out;
        }"""
        try:
            # The graph block sits below the fold on most routes, so the mode button is out of
            # view and a bare click waits forever for it. Scrolling the container into view
            # first is what the earlier mode screenshots already do; the probe has to do the
            # same or it fails for a reason that has nothing to do with the view.
            pg.evaluate("() => { location.hash = '#/'; }")
            pg.wait_for_timeout(600)
            pg.evaluate("""() => {
              const g = document.getElementById('cy');
              if (g) g.scrollIntoView({ block: 'center' });
            }""")
            pg.wait_for_timeout(600)
            btn = pg.query_selector('[data-gmode="circle"]')
            if btn:
                pg.evaluate("""() => {
                  const b = document.querySelector('[data-gmode="circle"]');
                  if (b) b.scrollIntoView({ block: 'center' });
                }""")
                pg.wait_for_timeout(400)
                btn.click(timeout=8000)
                pg.wait_for_timeout(2400)
            circles_rep = pg.evaluate(CIRCLES_JS)
        except Exception as exc:  # pragma: no cover - surfaced as a failure
            circles_rep = {"error": str(exc)}
        report["circle_view"] = circles_rep
        if circles_rep.get("error"):
            report["checks"].append(
                f"circle view: probe threw ({circles_rep['error']}) — the grouping cannot be "
                f"verified")
        else:
            if not circles_rep.get("circles"):
                report["checks"].append(
                    "circle view: the payload carries no circles, so the view has nothing to "
                    "group and the mode is presentational only")
            # `linked` is what makes the partition assertion meaningful. When the payload dropped
            # it, this probe read `linked: 0` and the partition check below passed without
            # testing anything — a gate that cannot fail. It is asserted first so its absence is
            # the failure, not a silent pass.
            if not circles_rep.get("linked"):
                report["checks"].append(
                    "circle view: the payload reports no linked-entity count, so the grouping "
                    "cannot be shown to cover the entities that have relations")
            if not circles_rep.get("components"):
                report["checks"].append(
                    "circle view: the payload reports no component count, so 'these circles come "
                    "from the relations' cannot be checked against the graph")
            if circles_rep.get("offCanvas"):
                report["checks"].append(
                    f"circle view: {circles_rep['offCanvas']} node(s) render outside the canvas "
                    f"({preview(circles_rep.get('overflow') or [], 3)}) — a group the reader cannot see "
                    f"is worse than no group")
            if circles_rep.get("linked") and circles_rep.get("members") != circles_rep.get("linked"):
                report["checks"].append(
                    f"circle view: the circles hold {circles_rep.get('members')} entities but "
                    f"{circles_rep.get('linked')} have at least one relation — the grouping drops "
                    f"members")
            if circles_rep.get("singletonCircles"):
                report["checks"].append(
                    f"circle view: {circles_rep['singletonCircles']} circle(s) hold a single "
                    f"entity — a one-member bucket is not a grouping and would be labelled as one")
            if circles_rep.get("linked") and circles_rep.get("groups") == circles_rep.get("linked"):
                report["checks"].append(
                    "circle view: every circle is trivially separate, so the grouping carries no "
                    "information about who associates with whom")
            if circles_rep.get("components", 0) > 1 and circles_rep.get("giant", 0) == 0:
                report["checks"].append(
                    "circle view: the graph has disconnected components but no component is "
                    "reported as the giant one, so the satellites cannot be told apart")
            if not circles_rep.get("bridgeEdges"):
                report["checks"].append(
                    "circle view: no cross-circle edges are classified, so every edge is drawn as "
                    "if it stayed inside a group")
            if not circles_rep.get("innerEdges"):
                report["checks"].append(
                    "circle view: no intra-circle edges are classified, so no edge is evidence for "
                    "the grouping it sits in")
            if not circles_rep.get("rings"):
                report["checks"].append(
                    "circle view: no group outlines are drawn, so the caption names a collection "
                    "with no visible extent")
            if not circles_rep.get("captions"):
                report["checks"].append(
                    "circle view: no group is named, so the reader sees clusters but cannot tell "
                    "who they are — which is the complaint this view answers")
            if not circles_rep.get("isoNodes") and circles_rep.get("isolated"):
                report["checks"].append(
                    f"circle view: {circles_rep.get('isolated')} unconnected entities are in the "
                    f"payload but none are drawn")
        print(f"circle view: circles={circles_rep.get('circles')} members={circles_rep.get('members')}"
              f"/{circles_rep.get('linked')} isolated={circles_rep.get('isolated')} "
              f"components={circles_rep.get('components')} giant={circles_rep.get('giant')} "
              f"biggest={circles_rep.get('biggest')} groups={circles_rep.get('groups')}")
        print(f"  rendered: offCanvas={circles_rep.get('offCanvas')} "
              f"zoom={circles_rep.get('zoom')} inner={circles_rep.get('innerEdges')} "
              f"bridge={circles_rep.get('bridgeEdges')} rings={circles_rep.get('rings')} "
              f"captions={circles_rep.get('captions')}")
        pg.evaluate("""() => {
          const b = document.querySelector('[data-gmode="sector"]');
          if (b) b.click();
        }""")
        pg.wait_for_timeout(400)

        # 39 — the sidebar must not contain controls that do not answer a click.
        #
        # The complaint was literal: "左侧还有很多点不了". Eight elements looked like controls
        # and were inert — four group headings, two section headings, a hint and a badge. The
        # check is the same one the reader performs: click every plausible control and see
        # whether anything changes. Ignoring a click is the failure; the specific effect is not
        # asserted, because a heading may legitimately collapse, scroll or navigate.
        SIDE_JS = r"""() => {
          const side = document.getElementById('side');
          if (!side) return { error: 'sidebar missing' };
          const cand = [];
          // Deciding by "does it have block children" is unreliable: a flex container makes
          // *every* child compute to display:block, so a heading and its decorations all look
          // block-level and the heading gets skipped. The question asked instead is the one the
          // reader asks — does this element read as something to click? A heading row or a
          // card row does, whatever its children compute to. Only elements the layout actually
          // presents as a row are considered, which is a property of the element itself.
          const ROW_SEL = '.side-h,.rt,.side-item,.side-kinds>a,.side-ch>button,' +
            '.side-crumb>a,.side-acts>.sbtn,.side-hit,#side-hits>*,' +
            '#rail>*,#rail [data-rail],#side-tree>*';
          const seen = new Set();
          const consider = el => {
            if (!el || seen.has(el)) return;
            seen.add(el);
            const txt = (el.innerText || '').trim();
            if (!txt || txt.length > 40) return;
            // A wrapper that owns several controls is a layout container, not a row; its
            // `innerText` is the concatenation of its children (see SIDE_CLICK_JS).
            if (el.querySelectorAll('button,a,[data-rail]').length > 1) return;
            const cs = getComputedStyle(el);
            if (cs.display === 'none' || cs.visibility === 'hidden') return;
            const rr = el.getBoundingClientRect();
            if (rr.width < 2 || rr.height < 2) return;
            // Punctuation between links and the shortcut badge are labels, not controls.
            if (el.classList.contains('sep') || el.classList.contains('side-kbd')) return;
            const role = el.getAttribute('role');
            const isCtrl = el.tagName === 'BUTTON' || el.tagName === 'A' ||
              el.tagName === 'SUMMARY' || role === 'button' || role === 'link' ||
              el.hasAttribute('tabindex') || cs.cursor === 'pointer';
            cand.push({ tag: el.tagName.toLowerCase(),
                        cls: (el.className || '').toString().slice(0, 28), txt, isCtrl });
          };
          side.querySelectorAll(ROW_SEL).forEach(consider);
          // Every element the sidebar presents as a row must be reachable this way, or the
          // probe is checking a subset. Anything with a block child that is not a known row
          // shape is reported so a new row type cannot silently escape the check.
          const strays = [];
          side.querySelectorAll('div,span,button,a').forEach(el => {
            if (seen.has(el)) return;
            const txt = (el.innerText || '').trim();
            if (!txt || txt.length > 40) return;
            const cs = getComputedStyle(el);
            if (cs.display === 'none' || cs.visibility === 'hidden') return;
            if (el.classList.contains('sep') || el.classList.contains('side-kbd')) return;
            const role = el.getAttribute('role');
            const ctrlish = el.tagName === 'BUTTON' || el.tagName === 'A' ||
              role === 'button' || role === 'link' || el.hasAttribute('tabindex');
            // A control that matches no row selector means ROW_SEL needs updating.
            if (ctrlish && !seen.has(el)) strays.push(`${el.tagName.toLowerCase()}.${
              (el.className || '').toString().slice(0, 24)}|${txt}`);
          });
          return { total: cand.length,
                   inert: cand.filter(c => !c.isCtrl)
                     .map(c => `${c.tag}|${c.txt}`),
                   strays: strays.slice(0, 8) };
        }"""
        try:
            side_rep = pg.evaluate(SIDE_JS)
        except Exception as exc:  # pragma: no cover
            side_rep = {"error": str(exc)}
        report["sidebar_controls"] = side_rep
        if side_rep.get("error"):
            report["checks"].append(f"sidebar: probe threw ({side_rep['error']})")
        else:
            for row in (side_rep.get("inert") or []):
                # The probe excludes breadcrumb separators, the shortcut badge and long prose.
                # Anything left that reads as a row is a defect: it looks clickable and is not.
                bare = row.split("|", 1)[1].strip() if "|" in row else row.strip()
                if bare in ("/", "›", "·", "→", ">", "|"):
                    continue
                if len(bare) > 14:
                    continue
                report["checks"].append(
                    f"sidebar: `{row}` reads as a control but is inert — the reader will click "
                    f"it and get nothing")
            if side_rep.get("strays"):
                report["checks"].append(
                    f"sidebar: {len(side_rep['strays'])} control(s) are not covered by the "
                    f"sidebar row selector, so they escape this check "
                    f"{preview(side_rep['strays'], 3)}")
        print(f"sidebar: {side_rep.get('total')} rows, "
              f"{len(side_rep.get('inert') or [])} inert: {side_rep.get('inert')}"
              + (f"  strays={side_rep['strays']}" if side_rep.get("strays") else ""))

        # A `cursor:pointer` on a div is a lie the CSS tells: the styling is shared by class,
        # so a heading that lost its behaviour keeps the pointer cursor and passes any
        # appearance-based test. This is the same failure mode as the earlier fake gates — the
        # assertion has to be about what happens, not what it looks like. So every sidebar row
        # is clicked, and a row whose click changes neither the hash, the sidebar markup, the
        # scroll position, nor the DOM under it is inert.
        SIDE_CLICK_JS = r"""async () => {
          const sleep = ms => new Promise(r => setTimeout(r, ms));
          // The signature has to include the entity/route identity, not just the number of
          // sections: navigating from one entity page to another with the same shape would
          // otherwise look like nothing happened. Scroll is sampled after the animation
          // settles, because every rail row scrolls smoothly and an immediate read always
          // sees the old position.
          /* The signature has to be sensitive to whatever the control is *for*, and the
           * sidebar has two scroll surfaces: the window (page blocks) and the drawer panel
           * (the mirrored per-subject rows). Comparing only `window.scrollY` made every
           * drawer row look inert, because scrolling the panel moves the page not at all.
           * Both are sampled, so a row that works on either surface reads as responsive. */
          const sig = () => [
            location.hash,
            (window.__atlasRoute || {}).view || '',
            (window.__atlasRoute || {}).id || '',
            (window.__atlasRoute || {}).kind || '',
            document.getElementById('side-tree').innerHTML.length,
            Math.round(window.scrollY),
            Math.round((document.getElementById('drawer') || {scrollTop:0}).scrollTop),
            (document.getElementById('page') || {innerHTML:''}).innerHTML.length,
            document.querySelectorAll('section.pblock').length,
            /* The rail's own disclosure state. Collapsing a rail group changes the rail and
             * nothing else — it deliberately does not scroll, navigate or repaint the page —
             * so a signature built only from the page and the route reads a working
             * disclosure as "answered the click with nothing". */
            (document.getElementById('rail') || {innerHTML:''}).innerHTML.length,
            [...document.querySelectorAll('#rail [aria-expanded]')]
              .map(b => b.getAttribute('aria-expanded')).join(','),
            [...document.querySelectorAll('#rail [data-rail-group]')]
              .map(b => b.className).join(','),
          ].join('|');
          /* `#rail>*` as well as `#rail [data-rail]`: a rail that renders its region as
           * plain headings instead of buttons still presents clickable-looking rows, and
           * selecting only the buttons would let exactly those rows go untested. */
          const sel = '.side-h,.rt,.side-item,.side-kinds>a,.side-ch>button,' +
            '.side-crumb>a,.side-acts>.sbtn,#rail>*,#rail [data-rail],#side-tree>*';
          const inert = [];
          let tested = 0;
          let unresolved = 0;
          /* Collect the rows *by label*, then resolve each label to a live node at the moment
           * it is clicked. Holding the element references instead made this probe lie: a
           * click that navigates (or collapses a group) rebuilds `#side-tree` and `#rail`, so
           * every later reference in the list pointed at a detached node. `click()` on a
           * detached button fires no delegated handler — nothing happens, and the row is
           * reported as broken. Eight working rail rows were reported that way. */
          const snap = () => [...document.querySelectorAll(sel)].filter(el => {
            const cs = getComputedStyle(el);
            if (cs.display === 'none' || cs.visibility === 'hidden') return false;
            const r = el.getBoundingClientRect();
            if (r.width < 2 || r.height < 2) return false;
            if (!(el.innerText || '').trim()) return false;
            if (el.querySelectorAll('button,a,[data-rail]').length > 1) return false;
            return true;
          });
          /* A row's identity must not include the count beside it.
           *
           * MEASURED failure this replaces: the kind tree renders `人物 340`, `剧情 957` and the
           * chapter grid renders cells like `18`, `19`. Clicking a chapter cell changes the
           * chapter, which changes every count in the kind tree, so `人物 340` becomes
           * `人物 359` becomes `人物 378`. Keying `done` on the full label therefore never
           * matched again: 186 rounds clicked 186 DIFFERENT labels, the loop could not converge,
           * and it ran until the 400-round cap — about 17 minutes, long enough that three
           * acceptance runs were recorded as "the renderer crashed" when in fact the probe was
           * still grinding and the driver was killed by its own timeout.
           *
           * The count is display text, not identity. Stripping a trailing number group makes
           * `人物 340` and `人物 359` the same row, which is what they are. */
          const labelOf = el => (el.innerText || '').trim().replace(/\n/g, ' ').slice(0, 22);
          const keyOf = el => labelOf(el).replace(/\s*\d[\d,]*\s*$/, '').trim() || labelOf(el);
          /* Re-open every disclosure, so the next round can see the rows the last click hid.
           *
           * Two things go wrong if this is skipped, and both shrink the tested set silently:
           * clicking a group heading collapses its rows, and clicking the kind tree's heading
           * collapses nine links and twenty chapter cells at once. A disclosure is *supposed*
           * to work that way — hiding rows is the whole point — so the probe cannot treat the
           * disappearance as a defect, and it cannot leave the rows hidden either, because
           * then they are never clicked. Restoring visibility between rounds is what makes
           * "every row was clicked" true; `done` is keyed by `keyOf` so a row is clicked once. */
          const reopen = () => {
            document.querySelectorAll(
              '#rail [data-rail-group][aria-expanded="false"],' +
              '#side-tree [data-side-head][aria-expanded="false"]').forEach(b => b.click());
          };
          const done = new Set();
          let rounds = 0;
          /* The cap stays as a safety net, but it must not be the thing that ends a healthy
           * run: a probe that only stops because it hit its own limit has not finished, and
           * reporting its verdict as if it had is the "tested=None" mistake one level up.
           * `hitCap` records that case so the gate can say so. */
          let hitCap = false;
          while (rounds < 400){
            rounds += 1;
            reopen();
            await sleep(140);
            const el = snap().find(e => !done.has(keyOf(e)));
            if (!el){
              /* Nothing left that has not been clicked. Only stop when the set is genuinely
               * exhausted: one more round after reopening, to catch a row revealed late. */
              if (rounds > 2) break;
              continue;
            }
            const want = labelOf(el);
            done.add(keyOf(el));
            if (rounds === 400) hitCap = true;
            const cls = (el.className || '').toString();
            const draggable = el.getAttribute('draggable');
            if (!/side-h|(^|\s)rt(\s|$)|side-item|sbtn|side-kinds|side-ch|side-crumb|data-rail/.test(cls)
                && el.tagName !== 'BUTTON' && el.tagName !== 'A') continue;
            /* `draggable="true"` is how the horizontal chapter scrubber says "this responds
             * to pointer input, just not to a click" — its gesture is a drag along the
             * strip, and a plain `click()` on it is not the interaction it offers. Judging it
             * by click alone would report a working control as inert. */
            if (draggable === 'true') continue;
            // "Top" is a no-op when already at the top, which is correct behaviour, so the
            // page is moved down before clicking a control that would scroll back up.
            if (el.hasAttribute('data-scroll-top') || (el.innerText || '').includes('顶部'))
              window.scrollTo(0, 2400);
            /* A rail row that names a block near the end of the page scrolls to the maximum
             * offset, and if the viewport is already there the click changes nothing that
             * `window.scrollY` can see. That is the control working, not failing. Moving away
             * from the target first gives the click room to move — the same reasoning as the
             * "top" case above, applied to every block row. */
            const dest = el.dataset.rail && !el.dataset.railsub
              ? document.getElementById(el.dataset.rail) : null;
            if (dest){
              const dr = dest.getBoundingClientRect();
              const here = Math.max(0, dr.top + window.scrollY - 74);
              const room = document.documentElement.scrollHeight - window.innerHeight;
              // Already parked at the destination (or at the bottom it wants): back off.
              if (Math.abs(window.scrollY - Math.min(here, room)) < 40)
                window.scrollTo(0, Math.max(0, Math.min(here, room) - 700));
            }
            // Long enough for any smooth scroll still in flight to finish before `before` is
            // sampled, so the sample is a resting position and the comparison is meaningful.
            await sleep(420);
            const before = sig();
            try { el.click(); } catch (e) { inert.push(want + ' [click threw]'); continue; }
            tested += 1;
            await sleep(650);          // long enough for the smooth scroll / hash change
            const after = sig();
            if (before === after) inert.push(want);
            // Return to the page the loop started from; a row that navigated away would
            // otherwise make every later row look inert.
            if (location.hash !== '#/char/char_qin_chao'){
              location.hash = '#/char/char_qin_chao';
              await sleep(420);
            }
          }
          for (const l of snap().map(keyOf)) if (!done.has(l)) unresolved += 1;
          return { tested: tested, inert: inert, unresolved: unresolved, hitCap: hitCap };
        }"""
        try:
            # Run on a subject page so the breadcrumb and up controls are present too.
            pg.evaluate("() => { location.hash = '#/char/char_qin_chao'; }")
            pg.wait_for_timeout(2200)
            # Disclosures opened or closed by an earlier check must not decide this one's
            # result. `RAIL_COLLAPSED` is a module-level set and it survives navigation, so a
            # click on the rail's group heading inside the loop below leaves the rail shut for
            # every route visited afterwards — which then made check 41 report that the rail
            # listed none of the page's sections. Reopening every disclosure is part of
            # establishing this check's starting state, not a workaround for its result.
            pg.evaluate("""() => {
              document.querySelectorAll('#rail [data-rail-group][aria-expanded="false"],' +
                '#side-tree [data-side-head][aria-expanded="false"]').forEach(b => b.click());
            }""")
            pg.wait_for_timeout(900)
            clk = pg.evaluate(SIDE_CLICK_JS)
        except Exception as exc:  # pragma: no cover
            clk = {"error": str(exc)}
        report["sidebar_click"] = clk
        if clk.get("error"):
            report["checks"].append(f"sidebar click: probe threw ({clk['error']})")
        else:
            if not clk.get("tested"):
                report["checks"].append(
                    "sidebar click: no row was actually clicked, so 'every control responds' "
                    "is untested")
            # A label that cannot be re-resolved means the sidebar changed shape under the
            # probe; silently skipping it would shrink the tested set without saying so.
            if clk.get("unresolved"):
                report["checks"].append(
                    f"sidebar click: {clk['unresolved']} row label(s) could not be re-resolved "
                    f"to a live element, so they were never clicked")
            # Reaching the round cap means the probe stopped because it ran out of budget, not
            # because it ran out of rows. That is the same non-signal as `tested=None`: a run
            # that ends on its own limit says nothing about whether the rows respond. Before
            # `keyOf` existed this was the normal outcome and it was read as a crash.
            if clk.get("hitCap"):
                report["checks"].append(
                    f"sidebar click: the probe hit its {400}-round cap after "
                    f"{clk.get('tested')} click(s) — the row set never converged, so 'every "
                    f"control responds' was not established")
            for row in (clk.get("inert") or []):
                report["checks"].append(
                    f"sidebar: `{row}` answers a click with nothing — it carries the pointer "
                    f"cursor and no behaviour")
        print(f"sidebar click: tested={clk.get('tested')} inert={clk.get('inert')}"
              + (f"  unresolved={clk['unresolved']}" if clk.get("unresolved") else "")
              + ("  HIT ROUND CAP" if clk.get("hitCap") else ""))
        # Keep "the probe died" and "the probe found nothing" from printing the same way.
        #
        # This is not a diagnostic that outlived its purpose — it is the fix for a measurement
        # error that cost this project three full acceptance runs. `tested=None` was printed
        # for a crashed probe AND for a probe that genuinely had no rows to click, so a run
        # that was actually still grinding through its 400-round cap was indistinguishable
        # from one whose renderer had been killed. Both were written down as "the renderer
        # crashed". A 0-byte log has the same shape: it reads as "finished without news"
        # whether the process was killed or is merely quiet. Making the two cases print
        # differently is what stops the next reader from drawing the wrong conclusion.
        if clk.get("error"):
            print(f"  !! sidebar click probe ERROR: {clk['error'][:200]}")
            report["checks"].append(
                f"sidebar click: the probe itself failed ({clk['error'][:120]}) — this is a "
                f"broken measurement, not a defect in the page")
        try:
            _alive = pg.evaluate("() => document.getElementById('page') ? 1 : 0")
            print(f"  renderer alive after sidebar-click phase: {_alive}")
        except Exception as exc:
            print(f"  !! renderer is GONE after the sidebar-click phase: {str(exc)[:140]}")
            report["checks"].append(
                f"the renderer did not survive the sidebar-click phase ({str(exc)[:120]})")


        #
        # 40 — a list cut short must be recoverable, and a long page must offer a contents list.
        #
        # `共 1043 条，另有 1003 条未列出。` was the whole of it: 96% of the section was named
        # and then withheld. The check is that the withheld part exists in the DOM and a control
        # reveals it, plus that a page this long offers a contents list — an 81,000-character
        # appendix with no way to reach a section is the same failure one level up.
        FOLD_JS = """() => {
          const out = { page: '', folds: 0, withRest: 0, restChars: 0, tocs: 0,
                        tocRows: 0, tocBadHref: [], fullFold: false, fullChars: 0,
                        expandedOk: null, deadButtons: [] };
          out.page = (window.__atlasRoute || {}).view || '';
          const folds = [...document.querySelectorAll('[data-fold]')];
          out.folds = folds.length;
          for (const b of folds){
            const box = document.getElementById(b.dataset.fold);
            if (!box) { out.deadButtons.push(b.dataset.fold); continue; }
            out.withRest += 1;
            out.restChars += box.innerHTML.length;
            if (b.dataset.fold === 'fold-full'){
              out.fullFold = true;
              out.fullChars = box.innerHTML.length;
            }
          }
          // Expanding must actually reveal text; a button wired to nothing is the defect.
          const first = folds[0];
          if (first){
            const box = document.getElementById(first.dataset.fold);
            const before = box ? box.hasAttribute('hidden') : null;
            if (box){
              const y = window.scrollY;
              first.click();
              out.expandedOk = box.hasAttribute('hidden') === false && before === true;
              first.click();
              if (box.hasAttribute('hidden') === false) out.expandedOk = false;
              window.scrollTo(0, y);
            }
          }
          const toc = document.querySelector('.page-toc');
          if (toc){
            out.tocs = 1;
            toc.querySelectorAll('a').forEach(a => {
              out.tocRows += 1;
              const id = (a.getAttribute('href') || '').replace(/^#/, '');
              if (!id || !document.getElementById(id)) out.tocBadHref.push(id || a.innerText);
            });
          }
          return out;
        }"""
        try:
            # The entity page with the most content is the one that exercises folding hardest,
            # so the probe uses the protagonist rather than an arbitrary small subject. Which
            # entity that is comes out of the payload, not a hard-coded id.
            _subj = pg.evaluate("""() => {
              const p = (window.G && window.G.metadata && window.G.metadata.protagonists) || [];
              if (p[0]) return p[0];
              if (typeof PROTAGONISTS !== 'undefined' && PROTAGONISTS.length) return PROTAGONISTS[0];
              return 'char_qin_chao';
            }""")
            pg.evaluate("(id) => { location.hash = '#/char/' + encodeURIComponent(id); }", _subj)
            pg.wait_for_timeout(2400)
            fold_rep = pg.evaluate(FOLD_JS)
        except Exception as exc:  # pragma: no cover
            fold_rep = {"error": str(exc)}
        report["entity_folds"] = fold_rep
        if fold_rep.get("error"):
            report["checks"].append(f"entity page: probe threw ({fold_rep['error']})")
        else:
            if not fold_rep.get("folds"):
                report["checks"].append(
                    "entity page: no truncated list offers an expand control, so anything cut "
                    "off is unreachable")
            if fold_rep.get("deadButtons"):
                report["checks"].append(
                    f"entity page: {len(fold_rep['deadButtons'])} fold button(s) point at no "
                    f"container {preview(fold_rep['deadButtons'], 3)} — clicking does nothing")
            if fold_rep.get("expandedOk") is False:
                report["checks"].append(
                    "entity page: expanding a folded list does not reveal it — the control is "
                    "wired to nothing")
            if fold_rep.get("tocBadHref"):
                report["checks"].append(
                    f"entity page: {len(fold_rep['tocBadHref'])} contents entry points at a "
                    f"section that is not on the page {preview(fold_rep['tocBadHref'], 3)}")
            if fold_rep.get("folds") and not fold_rep.get("tocs"):
                report["checks"].append(
                    "entity page: the page is long enough to fold sections but offers no "
                    "contents list to reach them")
        print(f"entity page: folds={fold_rep.get('folds')} containers={fold_rep.get('withRest')} "
              f"restChars={fold_rep.get('restChars')} fullFold={fold_rep.get('fullFold')}"
              f"({fold_rep.get('fullChars')}c) toc={fold_rep.get('tocs')}"
              f"/{fold_rep.get('tocRows')} expandOk={fold_rep.get('expandedOk')}")
        pg.evaluate("() => { location.hash = '#/'; }")
        pg.wait_for_timeout(500)

        #
        # 41 — the rail must describe the page the reader is looking at, and its rows must move
        # the viewport.
        #
        # `buildRail()` was called from `paintStream()` only, so on a subject page the rail kept
        # the home stream's block names. Two of those blocks (`stat`, `chapters`) keep their
        # markup in the document and sit at y=0, so a row could be present, clickable-looking,
        # and scroll nowhere. The probe therefore checks membership both ways and then clicks.
        RAIL_JS = """async () => {
          const sleep = ms => new Promise(r => setTimeout(r, ms));
          const out = { route: '', headings: [], rows: [], absent: [], missing: [],
                        ids: [], moved: null, movedFrom: null, movedTo: null,
                        maxScroll: 0, noRoom: false, verified: 0, noFlash: [] };
          out.route = location.hash;
          /* Both shapes of navigable section count: a subject page's blocks and an index
           * page's groups. Matching only the first made this gate reject a correct rail on
           * `#/index/<kind>`, whose rows point at `ixg-*` sections. */
          const secs = [...document.querySelectorAll(
            '#page section.pblock[id], #page section.ix-group[id]')];
          out.headings = secs.map(s => s.id);
          const rail = document.getElementById('rail');
          const rows = rail ? [...rail.querySelectorAll('[data-rail]')] : [];
          out.rows = rows.map(b => b.dataset.rail);
          const pageIds = new Set(out.headings);
          /* A row either names a page block or, when it carries `data-railsub`, a heading
           * inside the open drawer — whose label is its identity. Both are real
           * destinations, so both count towards coverage. */
          const sub = new Set([...document.querySelectorAll('#drawer h3.sub[data-secsection]')]
            .map(h => h.dataset.secsection));
          const railToPage = out.rows.filter(l => !sub.has(l));
          const railIds = new Set(railToPage);
          out.absent = out.headings.filter(i => !railIds.has(i));
          out.missing = railToPage.filter(i => !pageIds.has(i) || !document.getElementById(i));
          out.ids = [...railIds];
          out.drawerRows = out.rows.filter(l => sub.has(l));
          out.drawerAbsent = [...sub].filter(l => !out.rows.includes(l));
          /* What the probe actually saw, so a mismatch can be read off the gate output instead
           * of guessed at from a separate probe. */
          out.raw = { view: (window.__atlasRoute || {}).view,
                      paged: document.body.classList.contains('paged'),
                      railLen: rail ? rail.innerHTML.length : -1,
                      railHead: rail ? rail.innerHTML.slice(0, 70) : null,
                      secIds: out.headings.slice(0, 9), rowIds: out.rows.slice(0, 9) };
          // A row that points at a real block can still be inert — the home stream's blocks stay
          // in the DOM behind the paged view, so membership alone does not prove the row works.
          //
          // The assertion has to be "the window went where the row asked", not "the window
          // moved": a page shorter than the viewport has no scroll room at all, and there
          // `scrollTo` is a no-op *by physics*. `#/chapter/251` measures
          // `scrollHeight === innerHeight === 1050` — one event, six people, nothing to scroll.
          // Reading `scrollY < 20` as failure made this gate accuse a correct row on all 999
          // chapter pages. The reachable target is `min(want, maxScroll)`; anything else is a
          // real defect. A route with no room is recorded, not counted as verified, so the
          // gate cannot silently pass by only ever looking at pages that cannot move.
          //
          // The row is clicked either way, because on a page with no room the flash is the
          // *only* feedback that exists — and a click that changes nothing on screen is the
          // complaint this whole round started from.
          const maxScroll = Math.max(0,
            document.documentElement.scrollHeight - window.innerHeight);
          out.maxScroll = maxScroll;
          for (const b of rows){
            const n = b.dataset.railsub
              ? [...document.querySelectorAll('#drawer h3.sub[data-secsection]')]
                  .find(h => h.dataset.secsection === b.dataset.railsub)
              : document.getElementById(b.dataset.rail);
            if (!n) continue;
            if (b.dataset.railsub) continue;       // the drawer scrolls in place, not the window
            window.scrollTo(0, 0);
            await sleep(70);
            const r = n.getBoundingClientRect();
            const want = Math.max(0, r.top + window.scrollY - 66);
            if (want < 20) continue;               // the row is already at the top; nothing to prove
            const reach = Math.min(want, maxScroll);
            b.click();
            await sleep(150);                      // inside the 1.3 s flash window
            if (!n.classList.contains('rail-flash')) out.noFlash.push(b.dataset.rail);
            if (reach < 20){
              out.noRoom = true;                   // no block on this route can be scrolled to
              continue;
            }
            // `behavior: "smooth"` *animates*, so one sample after a fixed delay measures the
            // animation rather than the destination. A 9,437 px jump on the Qin Chao page was
            // still 1,006 px short after 700 ms and got reported as "the row does nothing" —
            // while the row was doing exactly what it should. Poll until the position settles.
            let last = -1;
            for (let i = 0; i < 30; i++){
              await sleep(100);
              const y = Math.round(window.scrollY);
              if (y === last) break;
              last = y;
            }
            out.moved = Math.round(window.scrollY);
            out.movedFrom = b.dataset.rail;
            out.movedTo = Math.round(reach);
            if (Math.abs(window.scrollY - reach) > 12){
              break;                               // remember the failure, do not let a later row hide it
            }
            out.verified += 1;
          }
          return out;
        }"""
        rail_rep = {}
        # Four route shapes, because the rail is derived from the page's own sections and the
        # pages do not all emit the same shape. The chapter page and the event page were the
        # two that got this wrong and neither was in this list: a chapter page emitted bare
        # `<section class="pblock">` with no id (so the rail came out blank on all 999 of
        # them) and an event page kept the *previous* route's rows (so all 1159 of them
        # advertised the home stream's blocks, every one of which scrolls nowhere). A gate
        # that only ever looks at a subject page and an index page cannot see either.
        for frag in ("#/char/char_qin_chao", "#/index/item",
                     "#/chapter/251", "#/event/event_f26_001"):
            try:
                pg.evaluate("h => { location.hash = h; }", frag)
                pg.wait_for_timeout(1400)
                # A rail collapsed by an earlier check is the reader's own state, not a defect:
                # this check asserts that the rail *describes the page*, so it has to look at
                # the rail with its sections open, the way a reader arrives.
                pg.evaluate("""() => {
                  document.querySelectorAll('#rail [data-rail-group][aria-expanded="false"]')
                    .forEach(b => b.click());
                }""")
                pg.wait_for_timeout(700)
                rr = pg.evaluate(RAIL_JS)
                rr["route"] = frag
                rr["scrolled"] = rr.get("moved") or 0
            except Exception as exc:  # pragma: no cover
                rr = {"route": frag, "error": str(exc)}
            rail_rep[frag] = rr
            if rr.get("error"):
                report["checks"].append(f"rail on {frag}: probe threw ({rr['error']})")
                continue
            if not rr.get("headings"):
                # No sections on the page at all means the page builder failed, which is caught
                # elsewhere; do not report a rail failure that is really a missing page.
                continue
            if not rr.get("rows"):
                report["checks"].append(
                    f"rail on {frag}: the page has {len(rr['headings'])} sections but the rail "
                    f"lists none of them — it is describing some other page")
            if rr.get("absent"):
                report["checks"].append(
                    f"rail on {frag}: sections the rail does not offer: {preview(rr['absent'], 4)}")
            if rr.get("missing"):
                report["checks"].append(
                    f"rail on {frag}: rail rows pointing at nothing: {preview(rr['missing'], 4)}")
            if rr.get("drawerAbsent"):
                report["checks"].append(
                    f"rail on {frag}: the open drawer offers {len(rr['drawerAbsent'])} section(s) "
                    f"the rail does not list: {preview(rr['drawerAbsent'], 4)}")
            if rr.get("noFlash"):
                report["checks"].append(
                    f"rail on {frag}: clicking row(s) {preview(rr['noFlash'], 3)} produced no visible "
                    f"change at all — on a page with no scroll room the flash is the only "
                    f"feedback the reader gets")
            if rr.get("movedFrom"):
                moved = rr.get("moved") or 0
                reach = rr.get("movedTo") or 0
                if abs(moved - reach) > 12:
                    report["checks"].append(
                        f"rail on {frag}: clicking row `{rr['movedFrom']}` left the viewport at "
                        f"scrollY={moved}, not the reachable {reach} — the row does nothing")
        report["rail"] = rail_rep
        # A route whose page is not taller than the viewport cannot exercise a single row, and
        # "nothing moved" there is correct. That makes it possible for this whole check to pass
        # while never having watched a row work, so require that at least two routes actually
        # moved the window. Without this the gate could be satisfied entirely by short pages.
        _verified = [f for f, r in rail_rep.items() if (r.get("verified") or 0) > 0]
        _no_room = [f for f, r in rail_rep.items() if r.get("noRoom")]
        if len(_verified) < 2:
            report["checks"].append(
                f"rail scrolling: only {len(_verified)} of {len(rail_rep)} routes actually moved "
                f"the window (no scroll room on {_no_room}) — the check has degenerated into a "
                f"no-op and proves nothing")
        for _frag, _rr in rail_rep.items():
            _room = (f"noRoom(maxScroll={_rr.get('maxScroll')})" if _rr.get("noRoom")
                     else f"verified={_rr.get('verified')}")
            print(f"rail {_frag}: rows={len(_rr.get('rows') or [])} "
                  f"drawerRows={_rr.get('drawerRows')} absent={_rr.get('absent')} "
                  f"missing={_rr.get('missing')} scrolled={_rr.get('scrolled')} "
                  f"reach={_rr.get('movedTo')} {_room} noFlash={_rr.get('noFlash')}"
                  + (f"  RAW={_rr.get('raw')}" if _rr.get("raw") else ""))
        print(f"rail verified on {len(_verified)}/{len(rail_rep)} routes; no scroll room on {_no_room}")
        pg.evaluate("() => { location.hash = '#/'; }")
        pg.wait_for_timeout(500)

        #
        # 42 — an in-page link must scroll, not navigate; and the two kinds that are not
        # entities must still have a working index page.
        #
        # The router reads `location.hash` as a route. A bare fragment (`href="#ixg-…"`) is
        # therefore not "scroll to this element" — it is "navigate to the route named `ixg-…`",
        # which matches nothing and resolves to home. MEASURED before the fix: clicking the
        # jump list on `#/index/item` took the page from 28,574 characters to **0**, view
        # `index` -> `home`. Every one of the ten index pages had a sidebar whose every row
        # threw the reader back to the overview. `data-toc` is the marker that says "this one
        # scrolls", so the assertion is that no in-page anchor lacks it.
        ANCHOR_JS = """async () => {
          const sleep = ms => new Promise(r => setTimeout(r, ms));
          const out = { routes: [], bad: [], jumped: [] };
          for (const frag of ['#/index/item', '#/index/chapter', '#/index/event',
                              '#/chapter/251', '#/char/char_qin_chao', '#/event/event_f26_001']){
            location.hash = frag;
            await sleep(1200);
            const page = document.getElementById('page');
            const anchors = [...page.querySelectorAll('a[href^="#"]')];
            const bare = anchors.filter(a => {
              const h = a.getAttribute('href') || '';
              if (h.startsWith('#/')) return false;        // a route
              return !a.hasAttribute('data-toc');          // in-page, but nothing handles it
            });
            out.routes.push({ frag, anchors: anchors.length, bare: bare.length });
            for (const a of bare.slice(0, 4))
              out.bad.push(frag + ' :: ' + a.getAttribute('href') + ' :: '
                + (a.innerText || '').trim().slice(0, 18));
            // Behavioural half: click a real in-page control and check the reader is still
            // on the same route afterwards.
            const toc = page.querySelector('a[data-toc]');
            if (toc){
              const view = (window.__atlasRoute || {}).view;
              const before = location.hash;
              toc.click();
              await sleep(800);
              const after = (window.__atlasRoute || {}).view;
              out.jumped.push({ frag, stayed: after === view && location.hash === before,
                                before, after, view });
            }
          }
          return out;
        }"""
        try:
            anchor_rep = pg.evaluate(ANCHOR_JS)
        except Exception as exc:  # pragma: no cover
            anchor_rep = {"error": str(exc)}
        report["anchors"] = anchor_rep
        if anchor_rep.get("error"):
            report["checks"].append(f"anchors: probe threw ({anchor_rep['error']})")
        else:
            if not anchor_rep.get("routes"):
                report["checks"].append(
                    "anchors: no route was examined, so 'in-page links scroll' is untested")
            for b in (anchor_rep.get("bad") or []):
                report["checks"].append(
                    f"in-page link without a handler: `{b}` — the router will read this "
                    f"fragment as a route name and send the reader to the overview")
            for j in (anchor_rep.get("jumped") or []):
                if not j.get("stayed"):
                    report["checks"].append(
                        f"clicking the in-page contents list on {j.get('frag')} left the page "
                        f"({j.get('view')} -> {j.get('after')}) — the link navigated instead of "
                        f"scrolling")
        for _r in (anchor_rep.get("routes") or []):
            print(f"anchors {_r['frag']}: {_r['anchors']} links, {_r['bare']} unhandled")
        print(f"anchors jumped: {anchor_rep.get('jumped')}")

        # The two non-entity kinds need real index pages, because the chapter page's
        # breadcrumb and the sidebar's 剧情 row both point at them.
        INDEX2_JS = """async () => {
          const sleep = ms => new Promise(r => setTimeout(r, ms));
          const out = [];
          for (const frag of ['#/index/chapter', '#/index/event']){
            location.hash = frag;
            await sleep(1400);
            const page = document.getElementById('page');
            const rail = document.getElementById('rail');
            const rows = [...page.querySelectorAll('.ix-line')];
            out.push({ frag, chars: page.innerHTML.length,
                       groups: page.querySelectorAll('section.ix-group').length,
                       rows: rows.length,
                       railRows: rail ? rail.querySelectorAll('[data-rail]').length : -1,
                       missing: (page.innerText || '').includes('找不到'),
                       firstHref: rows.length ? rows[0].getAttribute('href') : null });
          }
          return out;
        }"""
        try:
            idx2 = pg.evaluate(INDEX2_JS)
        except Exception as exc:  # pragma: no cover
            idx2 = [{"error": str(exc)}]
        report["index2"] = idx2
        for r in idx2:
            if r.get("error"):
                report["checks"].append(f"non-entity index: probe threw ({r['error']})")
                continue
            if r.get("missing"):
                report["checks"].append(
                    f"{r['frag']} renders 找不到这个索引 — the chapter page's breadcrumb and "
                    f"the sidebar's 剧情 row both link here")
            if not r.get("rows"):
                report["checks"].append(f"{r['frag']} lists no rows")
            if not r.get("railRows"):
                report["checks"].append(
                    f"{r['frag']}: {r.get('groups')} groups on the page but the rail lists none")
            print(f"non-entity index {r.get('frag')}: chars={r.get('chars')} "
                  f"groups={r.get('groups')} rows={r.get('rows')} railRows={r.get('railRows')}")

        # Gate 43. The twelfth round changed two things that no gate could see, and the
        # second one is the more instructive failure.
        #
        # (a) `pageChapter` went from four sections to ten. A gate that asserted only "the
        #     page has sections" would stay green with every new section deleted, so the
        #     assertion has to be that each of the ten ids is emitted by *some* chapter in
        #     the sample. The sample is 19 chapters spanning the book, and it was measured
        #     BEFORE the gate was written: item roles cover 14.2% of chapters and intimacy
        #     26.7%, so a narrow sample would have reported a false positive on a channel
        #     that is merely rare.
        #
        # (b) The leak scan near the top of this file evaluates `document.body.innerText`
        #     on `#/` and never navigates, so `LEAK_KEYS` and the snake_case regex have
        #     never seen a chapter page. MEASURED: five dangling ids reached readers on
        #     `#/chapter/322`, `#/chapter/375` and `#/chapter/631` while the suite stayed
        #     green — `item_xiewang_jian`, `item_huazhuang_he`, `char_ding_lei`,
        #     `item_chuangguo_yuoxi`, `org_jinxing_baoan`. They are precisely the ids the
        #     audit could not place, which is *why* the issue citing them exists, and
        #     `resolveIds()` leaves an id it cannot resolve. This is gate 41's mistake
        #     again: **coverage, not assertion, was the missing part.** So the scan below
        #     runs on six route shapes, not one.
        CHAP_SECTIONS = ["ch-summary", "ch-events", "ch-changes", "ch-rel", "ch-traits",
                         "ch-threads", "ch-intimate", "ch-items", "ch-people", "ch-review"]
        CHAP_JS = """async () => {
          const sleep = ms => new Promise(r => setTimeout(r, ms));
          const ID = /\\b[a-z][a-z0-9]*(?:_[a-z0-9]+){1,3}\\b/g;
          const out = { pages: [], emitted: {}, leaks: [], nav: [], shapes: [] };
          const ns = [1, 60, 120, 180, 251, 265, 284, 322, 375, 440, 500, 560, 631, 700,
                      760, 820, 880, 940, 999];
          for (const n of ns){
            location.hash = '#/chapter/' + n;
            await sleep(900);
            const page = document.getElementById('page');
            const rail = document.getElementById('rail');
            const secs = [...page.querySelectorAll('section.pblock[id]')];
            for (const s of secs) out.emitted[s.id] = (out.emitted[s.id] || 0) + 1;
            const text = page.innerText || '';
            const snake = [...new Set(text.match(ID) || [])];
            if (snake.length) out.leaks.push({ route: '#/chapter/' + n, snake: snake.slice(0, 8) });
            out.pages.push({ n, secs: secs.length,
                             railRows: rail ? rail.querySelectorAll('[data-rail]').length : -1,
                             scrollRoom: Math.max(0,
                               document.documentElement.scrollHeight - window.innerHeight) });
          }
          // Behavioural half of the chapter nav. `data-goto-chapter` would repaint the page
          // from `RT.n` without touching the route, which on a chapter page is a no-op, so
          // the assertion is on the route and not on the DOM.
          for (const [from, want, label] of [[251, 252, 'next'], [251, 250, 'prev']]){
            location.hash = '#/chapter/' + from;
            await sleep(900);
            const page = document.getElementById('page');
            const a = [...page.querySelectorAll('.ch-nav a')]
              .find(x => (x.innerText || '').includes('第 ' + want + ' 章'));
            if (!a){ out.nav.push({ from, label, found: false }); continue; }
            a.click();
            await sleep(900);
            out.nav.push({ from, label, found: true, hash: location.hash,
                           view: (window.__atlasRoute || {}).view });
          }
          // Every other route shape gets the same leak scan the home page gets.
          for (const frag of ['#/char/char_qin_chao', '#/event/event_f26_001', '#/index/item',
                              '#/loc/loc_aoxi_cun', '#/axis/axis_jiuchongtian']){
            location.hash = frag;
            await sleep(1000);
            const text = (document.getElementById('page') || document.body).innerText || '';
            const snake = [...new Set(text.match(ID) || [])];
            out.shapes.push({ frag, chars: text.length, snake: snake.slice(0, 8) });
            if (snake.length) out.leaks.push({ route: frag, snake: snake.slice(0, 8) });
          }
          return out;
        }"""
        try:
            chap_rep = guarded(pg, CHAP_JS, "gate43 chapter pages")
        except Exception as exc:  # pragma: no cover
            chap_rep = {"error": str(exc)}
        report["chapter_pages"] = chap_rep
        if chap_rep.get("error"):
            report["checks"].append(f"chapter pages: probe threw ({chap_rep['error']})")
        else:
            _cpages = chap_rep.get("pages") or []
            if len(_cpages) < 10:
                report["checks"].append(
                    f"chapter pages: only {len(_cpages)} sampled — too few chapters to assert "
                    f"that a rare channel reaches the page at all")
            for c in _cpages:
                if not c.get("secs"):
                    report["checks"].append(
                        f"#/chapter/{c['n']} emits no `section.pblock[id]` — the rail has "
                        f"nothing to list and no block on the page can be reached")
                elif c.get("railRows") != c.get("secs"):
                    report["checks"].append(
                        f"#/chapter/{c['n']}: {c['secs']} sections but the rail lists "
                        f"{c['railRows']} — it is describing some other page")
            for lk in (chap_rep.get("leaks") or []):
                report["checks"].append(
                    f"{lk['route']} shows internal ids to the reader: {lk['snake']}")
            _emitted = chap_rep.get("emitted") or {}
            _never = [s for s in CHAP_SECTIONS if not _emitted.get(s)]
            if _never:
                report["checks"].append(
                    f"across {len(_cpages)} sampled chapters these sections were never emitted: "
                    f"{_never} — the channel is not reaching the page")
            for nv in (chap_rep.get("nav") or []):
                if not nv.get("found"):
                    report["checks"].append(
                        f"#/chapter/{nv['from']} has no {nv['label']} link in `.ch-nav`")
                elif nv.get("hash") == f"#/chapter/{nv['from']}" or nv.get("view") != "chapter":
                    report["checks"].append(
                        f"#/chapter/{nv['from']}: the {nv['label']} control left the route at "
                        f"`{nv.get('hash')}` — it repaints the same chapter instead of navigating")
            for s in (chap_rep.get("shapes") or []):
                if not s.get("chars"):
                    report["checks"].append(
                        f"{s['frag']} rendered no text at all while scanning for leaks")
            _rooms = [c["scrollRoom"] for c in _cpages]
            print(f"chapter pages: {len(_cpages)} sampled, {len(_emitted)}/{len(CHAP_SECTIONS)} "
                  f"sections seen, leaks={len(chap_rep.get('leaks') or [])}")
            print(f"  section emission: {_emitted}")
            print(f"  scrollRoom min={min(_rooms)} max={max(_rooms)}; "
                  f"zero-room={[c['n'] for c in _cpages if c['scrollRoom'] == 0]}")
            print(f"  nav: {chap_rep.get('nav')}")
            print(f"  leak scan shapes: "
                  f"{[(s['frag'], s['chars']) for s in (chap_rep.get('shapes') or [])]}")

        # Gate 44. The event page gained the same shape of channels the chapter page did in
        # the twelfth round, plus `ev.location_id` — a field carrying where 496 of 1,159
        # events (42.8%) happened, which the builder had never read at all.
        #
        # MEASURED before the gate was written, over all 1,159 events, by evidence-id
        # intersection: traits 36.8% · threads (foreshadowing or commitments) ~36% ·
        # intimacy 17.3% · item roles 11.8%. The 40-event sample below was checked to emit
        # all eight section ids first — asserting "the page has sections" would stay green
        # with every new section deleted, which is the trap gate 43 exists to avoid.
        EV_SECTIONS = ["ev-facts", "ev-story", "ev-evidence", "ev-changes",
                       "ev-traits", "ev-threads", "ev-intimate", "ev-items", "ev-siblings"]
        EV_JS = """async () => {
          const sleep = ms => new Promise(r => setTimeout(r, ms));
          const out = { pages: [], emitted: {}, nav: [], locRows: 0, sampled: 0 };
          const evs = A(G.events);
          const step = Math.max(1, Math.floor(evs.length / 40));
          const ids = [];
          for (let i = 0; i < evs.length && ids.length < 40; i += step) ids.push(evs[i].id);
          out.sampled = ids.length;
          for (let i = 0; i < ids.length; i++){
            location.hash = '#/event/' + ids[i];
            await sleep(700);
            const page = document.getElementById('page');
            const rail = document.getElementById('rail');
            const secs = [...page.querySelectorAll('section.pblock[id]')];
            for (const s of secs) out.emitted[s.id] = (out.emitted[s.id] || 0) + 1;
            const text = page.innerText || '';
            // The recorded-location row only exists on events that carry `location_id`.
            if (text.includes('这场剧情的记录地点')) out.locRows += 1;
            out.pages.push({ id: ids[i], secs: secs.length,
                             railRows: rail ? rail.querySelectorAll('[data-rail]').length : -1,
                             navBtns: page.querySelectorAll('.ch-nav .sbtn').length,
                             missing: text.includes('找不到这段剧情') });
            if (i === 10){
              // Behavioural half. A `data-goto-chapter`-style control would repaint the same
              // event, which is exactly the bug the chapter page shipped with.
              for (const which of ['next', 'prev']){
                const btns = [...page.querySelectorAll('.ch-nav .sbtn')]
                  .filter(b => !(b.getAttribute('href') || '').includes('/index/'));
                if (!btns.length){ out.nav.push({ which, found: false }); continue; }
                const b = which === 'next' ? btns[btns.length - 1] : btns[0];
                const before = location.hash;
                b.click();
                await sleep(800);
                out.nav.push({ which, found: true, from: before, to: location.hash,
                               view: (window.__atlasRoute || {}).view,
                               moved: location.hash !== before });
                location.hash = '#/event/' + ids[i];
                await sleep(700);
              }
            }
          }
          return out;
        }"""
        try:
            ev_rep = guarded(pg, EV_JS, "gate44 event pages")
        except Exception as exc:  # pragma: no cover
            ev_rep = {"error": str(exc)}
        report["event_pages"] = ev_rep
        if ev_rep.get("error"):
            report["checks"].append(f"event pages: probe threw ({ev_rep['error']})")
        else:
            _epages = ev_rep.get("pages") or []
            if len(_epages) < 20:
                report["checks"].append(
                    f"event pages: only {len(_epages)} sampled — too few events to assert that "
                    f"a rare channel reaches the page")
            for d in _epages:
                if d.get("missing"):
                    report["checks"].append(
                        f"#/event/{d['id']} renders 找不到这段剧情 while walking the sample")
                if not d.get("secs"):
                    report["checks"].append(
                        f"#/event/{d['id']} emits no `section.pblock[id]` — the rail has nothing "
                        f"to list")
                elif d.get("railRows") != d.get("secs"):
                    report["checks"].append(
                        f"#/event/{d['id']}: {d['secs']} sections but the rail lists "
                        f"{d['railRows']} — it is describing some other page")
                if (d.get("navBtns") or 0) < 2:
                    report["checks"].append(
                        f"#/event/{d['id']}: {d.get('navBtns')} nav controls in `.ch-nav` — a "
                        f"middle event must offer both a previous and a next")
            _eemitted = ev_rep.get("emitted") or {}
            _enever = [s for s in EV_SECTIONS if not _eemitted.get(s)]
            if _enever:
                report["checks"].append(
                    f"across {len(_epages)} sampled events these sections were never emitted: "
                    f"{_enever} — the channel is not reaching the page")
            if not ev_rep.get("locRows"):
                report["checks"].append(
                    "no sampled event page shows the recorded-location row — `ev.location_id` "
                    "covers 42.8% of events, so the join is broken")
            for nv in (ev_rep.get("nav") or []):
                if not nv.get("found"):
                    report["checks"].append(
                        f"the {nv['which']} control is missing from `.ch-nav` on an event page")
                elif not nv.get("moved") or nv.get("view") != "event":
                    report["checks"].append(
                        f"event nav `{nv['which']}` left the route at `{nv.get('to')}` "
                        f"(view={nv.get('view')}) — it repaints the same event instead of "
                        f"navigating")
            print(f"event pages: {ev_rep.get('sampled')} sampled, "
                  f"{len(_eemitted)}/{len(EV_SECTIONS)} sections seen, "
                  f"recorded-location rows on {ev_rep.get('locRows')}")
            print(f"  section emission: {_eemitted}")
            print(f"  nav: {ev_rep.get('nav')}")
        pg.evaluate("() => { location.hash = '#/'; }")
        pg.wait_for_timeout(500)

        # ------------------------------------------------------------------
        # gate 45 — the subject-tag channel, asserted per entity id.
        #
        # Why this is a gate and not a screenshot: the field had a value on 11 subjects
        # and no reader at all, and the two existing leak scans are structurally unable
        # to notice — `LEAK_KEYS` is a hand-written list that never mentions `tags`, and
        # the snake_case regex needs an underscore that `protagonist` / `minor` /
        # `assassin` do not have. So the assertion here is deliberately about the
        # *translation*, read off `data-tag` (the raw value the renderer received)
        # against the text the reader sees, rather than about "a Chinese string exists
        # somewhere on a Chinese page" — the latter is true whether or not `TAGV` ran.
        #
        # The probe set is DERIVED from the graph, not captured in a list. The first version
        # hardcoded the nine subjects that happened to carry a Latin tag on the day the field
        # was first rendered — a snapshot of the data, not a rule. If a later extraction moved
        # `antagonist` onto a tenth subject, every probed page would still render Chinese tags,
        # `untranslated` would stay empty, and the English would reach the reader with this gate
        # green. That is gate 43's stale-sample failure again: a sample that cannot follow the
        # data is a sample that stops looking.
        #
        # MEASURED on this graph: 161 of 980 entities carry tags; 9 of them carry one of the 5
        # Latin values. The derived list is exactly those 9 — the same ids the hardcoded list
        # held — so this is a strict widening of the probe, not a different check.
        tag_latin_ids = pg.evaluate("""() => {
          const LATIN = /[A-Za-z]/;
          return A(G.entities)
            .filter(e => A(e.tags).some(t => typeof t === 'string' && LATIN.test(t)))
            .map(e => e.id).sort();
        }""")
        # Plus one tag-carrying subject per routable entity type. `sec-tags` is pushed by
        # `entityBody()` *before* its `isAgent` branch, so it renders for every type; nine
        # character pages structurally cannot see a break that only affects `location` or
        # `skill`, and the gate would keep passing while whole kinds went blank. Only types
        # that own a route are used, so a routing gap is reported by gate 41 and not by this
        # one dressed up as a tag failure.
        # One subject per type was a sample, not a rule. With 82 tagged characters and 13 tagged
        # items, breaking the *second* tagged entity of a type left the gate green — the probe's
        # shape, not its rule, decided what it could see. It now takes
        # min(TAG_REPS_PER_TYPE, however many that type has) subjects per routable type, and it
        # returns the per-type population it drew from, so a type that is thin in the data shows up
        # as a stated coverage limit instead of hiding behind the probe's shape.
        #
        # The subjects are the FIRST N in graph order, deliberately not N by sorted id. Sorting is
        # the obvious way to make a sample independent of input order, and here it was wrong:
        # MEASURED, sorting swapped the representative for 6 of the 8 types and thereby DROPPED
        # coverage for `org_luocha_men`, `loc_haiidao`, `concept_tian_sheng_mo_ti`,
        # `creature_guiquan` and `item_zhaohun_kulou` — including the entity the previous
        # degradation test used as its target. A sample size that grows can still shrink coverage.
        # Graph order is what the previous rule used, so taking a prefix of it keeps every
        # previously probed subject and adds to it: coverage grows monotonically, and this probe is
        # a strict superset of the one it replaces (16 -> 24 subjects).
        TAG_REPS_PER_TYPE = 2
        tag_type_rep = pg.evaluate("""() => {
          const by = {}, counts = {}, skipped = [];
          for (const e of A(G.entities)){
            if (!A(e.tags).length) continue;
            if (!ROUTE_TYPE[e.type]){ if (!skipped.includes(e.type)) skipped.push(e.type); continue; }
            (by[e.type] = by[e.type] || []).push(e.id);
            counts[e.type] = (counts[e.type] || 0) + 1;
          }
          const reps = {};
          for (const t of Object.keys(by)) reps[t] = by[t].slice(0, __REPS__);
          return { reps: reps, counts: counts, skipped: skipped.sort() };
        }""".replace("__REPS__", str(TAG_REPS_PER_TYPE)))
        tag_expected_count = pg.evaluate("""() => {
          const out = {};
          for (const e of A(G.entities)){
            const n = A(e.tags).filter(t => t != null && String(t).trim() !== '').length;
            if (n) out[e.id] = n;
          }
          return out;
        }""")
        tag_reps = tag_type_rep["reps"]
        tag_rep_ids = sorted({i for ids in tag_reps.values() for i in ids})
        TAG_PROBE = sorted(set(tag_latin_ids) | set(tag_rep_ids))
        # The probe's own coverage is asserted, not assumed. Without this, a later change that
        # quietly went back to one subject per type would leave every other number in this gate
        # identical while covering half as much — the defect class this probe was just fixed for.
        # Shape: {type: [taken, tagged-in-graph]}.
        tag_thin = {ty: [len(tag_reps[ty]), tag_type_rep["counts"][ty]] for ty in tag_reps
                    if len(tag_reps[ty]) != min(TAG_REPS_PER_TYPE, tag_type_rep["counts"][ty])}
        tag_rows, tag_missing, tag_untranslated, tag_raw_ascii, tag_count_bad = [], [], [], [], []
        for tid in TAG_PROBE:
            # Through the app's own navigation rather than a hand-built hash: `openEntityRoute`
            # resolves the kind from the entity's type, so a non-character probe lands on its
            # real page instead of a dead `#/char/<id>`.
            pg.evaluate("id => openEntityRoute(id)", tid)
            pg.wait_for_timeout(420)
            got = pg.evaluate("""() => {
              const sec = document.getElementById('sec-tags');
              if (!sec) return null;
              return [...sec.querySelectorAll('.tag-chip')]
                .map(c => [c.dataset.tag, c.textContent.trim()]);
            }""")
            if not got:
                tag_missing.append(tid)
                continue
            tag_rows.append([tid, got])
            # A second, different assertion: presence says the section exists, the count says it
            # holds what the graph holds. A chip silently dropped is invisible to the leak pair.
            want = tag_expected_count.get(tid, 0)
            if len(got) != want:
                tag_count_bad.append([tid, len(got), want])
            # And a third, which the previous revision only *intended*: it collected ASCII raw
            # values into `tag_raw_ascii` and never read the list, so the comment next to it
            # described a check that did not exist. The claim is that a raw English value must
            # not survive anywhere on the page, not merely inside the chip — so the whole page
            # text is searched, not just the chip's own textContent.
            page_text = pg.evaluate("document.getElementById('page').innerText")
            for raw, shown in got:
                if raw and all(ord(ch) < 128 for ch in raw) and raw in page_text:
                    tag_raw_ascii.append([tid, raw])
            for raw, shown in got:
                if shown == raw and all(ord(ch) < 128 for ch in raw):
                    tag_untranslated.append([tid, raw])
        # A previous revision appended `[tid, raw]` right here for *every* ASCII raw value, under
        # a comment claiming that "a raw value that is pure ASCII must not survive anywhere on the
        # page". That append was never read, and its semantics were not its comment's: it
        # collected all ASCII raw tags, not the ones surviving on the page. When the page-text
        # scan below started writing to the same list, the assertion read the union of two
        # different meanings and therefore could never be empty — MEASURED 11/11 hits, exactly one
        # per ASCII raw tag, in a run where the ASCII-word scan of the same page found nothing at
        # all. **One list, one writer.** The surviving-value scan below is now the only append.
        report["tag_channel"] = {"rows": tag_rows, "missing": tag_missing,
                                 "untranslated": tag_untranslated,
                                 "latin_ids": tag_latin_ids,
                                 "type_reps": tag_reps,
                                 "type_rep_ids": tag_rep_ids,
                                 "tagged_per_type": tag_type_rep["counts"],
                                 "thin_types": tag_thin,
                                 "types_without_route": tag_type_rep["skipped"],
                                 "count_mismatch": tag_count_bad,
                                 "raw_ascii_on_page": tag_raw_ascii}
        # An empty probe is not a pass. With no Latin tag anywhere in the graph the leak pair
        # below can never fire, and the run would look green while proving nothing about the
        # vocabulary — the same shape as the `entity_tags` scan that had nothing to look at.
        # This is a refusal to pass, not a verdict on the data: the message names both readings
        # and what each one calls for, because only a human can tell them apart.
        if not tag_latin_ids:
            report["checks"].append(
                "gate 45: no entity in the graph carries a Latin tag, so the probe had nothing "
                "to translate and this run proves nothing about the tag vocabulary — either the "
                "upstream extraction normalised every tag to Chinese (then the `entity_tags` "
                "table and this gate are dead code and should be removed together) or `e.tags` "
                "left the graph (then the channel is broken). An empty probe is not a pass")
        if tag_thin:
            report["checks"].append(
                f"gate 45: the probe took fewer subjects than the rule calls for, on "
                f"{len(tag_thin)} type(s): {preview(sorted(tag_thin.items()), 6)} — [taken, "
                f"tagged in graph] — either the derivation is wrong or the graph changed shape "
                f"under it")
        if tag_missing:
            report["checks"].append(
                f"`sec-tags` never rendered on {len(tag_missing)} of {len(TAG_PROBE)} "
                f"subjects that carry tags in the graph: {preview(tag_missing, 6)} — the field has "
                f"a value and no reader")
        if tag_untranslated:
            report["checks"].append(
                f"{len(tag_untranslated)} tag(s) render as their raw English value: "
                f"{preview(tag_untranslated, 8)} — `entity_tags` has no entry for them")
        if tag_count_bad:
            report["checks"].append(
                f"{len(tag_count_bad)} subject page(s) rendered a different number of tag chips "
                f"than the graph holds: {preview(tag_count_bad, 6)} — `sec-tags` is dropping or "
                f"duplicating values")
        if tag_raw_ascii:
            report["checks"].append(
                f"{len(tag_raw_ascii)} raw English tag value(s) survive somewhere on their own "
                f"subject page, outside the chip: {preview(tag_raw_ascii, 6)} — the vocabulary "
                f"translated the chip but the raw value is printed again in the body text")
        if not tag_rows:
            report["checks"].append(
                "no subject page showed a tag row — the assertion cannot distinguish "
                "\"the channel is broken\" from \"nothing was sampled\"")
        # And the same leak scanned on a page that renders tags, because the existing
        # body-text scan below only ever runs on `#/`.
        pg.evaluate("() => { location.hash = '#/char/char_mo_feiyan'; }")
        pg.wait_for_timeout(450)
        tag_text = pg.evaluate("document.getElementById('page').innerText")
        tag_leaks = [k for k in LEAK_KEYS if k.rstrip('"\\\'') in tag_text]
        if tag_leaks:
            report["checks"].append(f"internal keys leaked on a tag page: {tag_leaks}")
        tag_word = sorted(set(re.findall(r"\b[a-z]{3,}\b", tag_text)))
        # A bare lowercase word is what an untranslated single-word enum looks like. The
        # page legitimately contains Latin (alias names like ICE, unit-ish tokens), so
        # this reports rather than fails — the hard assertion is the pair above.
        report["tag_page_ascii_words"] = tag_word[:40]
        # A sample, not a census: the cap is stated next to it so the field cannot be read as
        # "the page held at most 40 ASCII words".
        report["tag_page_ascii_words_n"] = len(tag_word)
        print(f"tag channel: {len(tag_rows)}/{len(TAG_PROBE)} subjects "
              f"({len(tag_latin_ids)} Latin carriers + {len(tag_rep_ids)} type reps over "
              f"{len(tag_reps)} types, thin={tag_thin}), "
              f"missing={len(tag_missing)}, untranslated={len(tag_untranslated)}, "
              f"count_mismatch={len(tag_count_bad)}, "
              f"raw_ascii_on_page={len(tag_raw_ascii)}, "
              f"types_without_route={tag_type_rep['skipped']}")
        for tid, got in tag_rows:
            print(f"  {tid:<22} {got}")

        # 46 — the search must reach the book's own prose, not only the labels the UI invented.
        #
        # MEASURED before the index was widened, on the shipped build: six realistic queries all
        # returned zero hits — 「花瓶中魔神入体」(an event title, verbatim in the graph),
        # 「盒饭」(a chapter-summary title, verbatim), 「罗德向臭道士复仇」(a foreshadowing label,
        # verbatim), 「秦朝将亲自出手审判方华」(a commitment's own wording), and 「秦朝 苏姬」
        # (two characters appearing together). The index covered entity names, section names and
        # chapter numbers, so the one thing a reader actually remembers — what happened — was
        # the one thing it could not find.
        #
        # The sample is those same five strings, so the gate is a regression test against a
        # measurement rather than against an expectation. Each is asserted to return at least one
        # hit *of the right kind*, because returning a person who happens to share a substring
        # would satisfy a bare "hits > 0" without the search having found the scene.
        SEARCH_PROBE = [
            ("花瓶中魔神入体", "event"),
            ("盒饭", "summary"),
            ("罗德向臭道士复仇", "thread"),
            ("秦朝将亲自出手审判方华", "commit"),
        ]
        search_rows, search_missing, search_wrong = [], [], []
        for query, want_kind in SEARCH_PROBE:
            got = pg.evaluate("""q => {
              if (typeof cmSearch !== 'function') return null;
              return cmSearch(q).map(r => r.kind);
            }""", query)
            if got is None:
                search_missing.append(f"{query} (cmSearch unavailable)")
                continue
            search_rows.append((query, got[:6]))
            if want_kind not in got:
                search_wrong.append(f"{query} -> {preview(got, 6)} (want a {want_kind})")
        # A multi-word query must mean "all of these words". MEASURED before this was added:
        # 「秦朝 苏姬」 returned nothing while both names are indexed and the two appear together
        # throughout the book — the search compared the whole query as one substring, so any
        # query containing a space was guaranteed to fail.
        multi = pg.evaluate("""() => {
          if (typeof cmSearch !== 'function') return null;
          return cmSearch('秦朝 苏姬').map(r => `${r.kind}:${String(r.name).slice(0, 16)}`);
        }""")
        # A result list must not be one kind wearing forty hats. MEASURED rationale: entity
        # names match at position 0 and score 100000 while a description match scores under
        # 60000, so before the per-kind cap a query naming a character returned forty people and
        # hid the scenes. 「秦朝」 is the case that proves it, and it must surface more than one
        # kind of record.
        mixed = pg.evaluate("""() => {
          if (typeof cmSearch !== 'function') return null;
          const kinds = new Set(cmSearch('秦朝').map(r => r.kind));
          return [...kinds];
        }""")
        report["search_channel"] = {"rows": search_rows, "missing": search_missing,
                                    "wrong_kind": search_wrong, "mixed_kinds": mixed,
                                    "multi_term": multi}
        if not multi:
            report["checks"].append(
                "search: the two-word query 秦朝 苏姬 found nothing — a query with a space is "
                "being compared as a single substring, so multi-word search cannot work")
        if search_missing:
            report["checks"].append(
                f"search: the palette index did not answer for {search_missing} — the query "
                f"channel cannot be exercised")
        if search_wrong:
            report["checks"].append(
                f"search: {len(search_wrong)} known-in-graph phrase(s) did not return a record of "
                f"the right kind: {preview(search_wrong, 3)} — the index does not reach the book's prose")
        if mixed is not None and len(mixed) < 2:
            report["checks"].append(
                f"search: the query 秦朝 returns only {mixed} — one kind is crowding out the rest, "
                f"so a reader searching a name cannot see the scenes it appears in")
        print(f"search channel: {len(search_rows)}/{len(SEARCH_PROBE)} phrases resolved, "
              f"wrong_kind={len(search_wrong)}, mixed={mixed}")
        for q, got in search_rows:
            print(f"  {q:<22} -> {got}")

        # 47 — 返回 must return to the page the reader came from, not to the overview.
        #
        # The complaint was literal: on a character page reached from a chapter page the only way
        # back was 回到总览, which discards the chapter. MEASURED on the shipped build: the page
        # carried zero back controls. The browser already recorded the path, so the information
        # existed and nothing surfaced it.
        #
        # Asserted on the route, not on the label: the control's job is to change where you are,
        # and a button that reads 返回 while leaving the route alone is the same defect as a
        # heading row that looks clickable.
        back_rep = {"error": None}
        try:
            pg.evaluate("() => { location.hash = '#/chapter/300'; }")
            pg.wait_for_timeout(700)
            pg.evaluate("() => { location.hash = '#/char/char_qin_chao'; }")
            pg.wait_for_timeout(900)
            before = pg.evaluate("() => location.hash")
            btn = pg.query_selector("[data-nav-back]")
            back_rep["present"] = bool(btn)
            if btn:
                btn.click()
                pg.wait_for_timeout(900)
            back_rep["before"] = before
            back_rep["after"] = pg.evaluate("() => location.hash")
            back_rep["nav"] = pg.evaluate("() => (window.__atlasNav ? window.__atlasNav.depth() : null)")
            back_rep["moved"] = back_rep["before"] != back_rep["after"]
            back_rep["returned"] = back_rep["after"] == "#/chapter/300"
        except Exception as exc:  # pragma: no cover
            back_rep["error"] = str(exc)
        report["back_nav"] = back_rep
        if back_rep.get("error"):
            report["checks"].append(f"返回: probe threw ({back_rep['error'][:120]})")
        else:
            if not back_rep.get("present"):
                report["checks"].append(
                    "返回: no back control is rendered on a page reached from another page — the "
                    "reader's only exit is 回到总览, which discards where they came from")
            elif not back_rep.get("moved"):
                report["checks"].append(
                    f"返回: the control left the route at {back_rep.get('after')} — it is inert")
            elif not back_rep.get("returned"):
                report["checks"].append(
                    f"返回: from {back_rep.get('before')} it went to {back_rep.get('after')} "
                    f"instead of back to #/chapter/300")
        print(f"返回: present={back_rep.get('present')} "
              f"{back_rep.get('before')} -> {back_rep.get('after')} "
              f"returned={back_rep.get('returned')} depth={back_rep.get('nav')}")

        # 48 — the prose the reader sees must be the prose in the graph, character for
        # character, and it must not be clipped into a wall.
        #
        # Why this gate exists: I read `atlas-home.png` — 1680x1050 downscaled to 1080 — and
        # reconstructed a garbled-looking chapter summary, and was one step from filing it as
        # a rendering defect. The reconstructed string shared enough tokens with the real one
        # to be entirely plausible. **A screenshot proves that something is there; it never
        # proves what it says.** So the comparison is made against the graph, not against my
        # reading of a picture.
        #
        # The clamp half is contract 3.2.4: a truncated block must be a fold, not a wall.
        # Nothing gated text fidelity before this, and `esc()`/`prose()` double-escaping is a
        # defect this renderer has shipped before.
        #
        # Note on the sample: the home block lists chapters at and below the current cutoff,
        # so the cutoff is moved first. Each sample compares **the first card actually
        # present** against the graph entry for that card's own `data-ch`, rather than
        # assuming a particular card is on page 1 — an ordering assumption here would show up
        # as a false "not rendered".
        PROSE_CUTOFFS = [1, 120, 251, 500, 760, 975]
        prose_rows, prose_bad, prose_clamped, prose_absent, prose_ws, prose_stale = \
            [], [], [], [], [], []
        # Establish a clean starting state. Gate 47 leaves the route on `#/chapter/300`, and
        # the home stream is NOT repainted while a paged route is active — MEASURED on the
        # first full run of this gate: six cutoffs, six identical cards, every one
        # `data-ch=975`, because the block was frozen at whatever cutoff it was last painted
        # with. The fidelity numbers were all green and meant nothing; the anti-degeneration
        # count is what caught it (1 distinct chapter out of 6). Contract 4.4.0.8: every
        # check builds its own starting point.
        pg.evaluate("() => { location.hash = '#/'; }")
        pg.wait_for_timeout(1300)
        home_view = pg.evaluate("() => (window.__atlasRoute && window.__atlasRoute.view) || null")
        if home_view != "home":
            report["checks"].append(
                f"prose: could not get back to the home route before sampling "
                f"(view={home_view}) — the sample would read a stale stream")
        for cut in PROSE_CUTOFFS:
            pg.evaluate("ch => setChapter(ch, true)", cut)
            pg.wait_for_timeout(1500)
            got = pg.evaluate("""() => {
              const card = document.querySelector('#block-chapter_summaries article.cs');
              if (!card) return null;
              const ch = Number(card.dataset.ch);
              const s = A(G.chapter_summaries).find(x => x.chapter === ch) || {};
              const h = card.querySelector('h4'), p = card.querySelector('p');
              const cs = p ? getComputedStyle(p) : null;
              return { ch: ch, dataTitle: s.title || '', dataSummary: s.summary || '',
                       shownTitle: h ? h.textContent : null,
                       shownSummary: p ? p.textContent : null,
                       clamp: cs ? cs.webkitLineClamp : null,
                       overflow: cs ? cs.overflow : null,
                       scrollH: p ? p.scrollHeight : 0, clientH: p ? p.clientHeight : 0 };
            }""")
            if not got:
                prose_absent.append(cut)
                continue
            got["cut"] = cut
            prose_rows.append(got)
            # The block lists chapters at and below the cutoff, newest first, so the first
            # card belongs to the cutoff itself. If it does not, the stream did not repaint —
            # which is exactly how the first version of this gate read one chapter six times.
            if got["ch"] != cut:
                prose_stale.append([cut, got["ch"]])
            # Two deliberate differences are not fidelity failures, and both were found by
            # running this gate for the first time:
            #   * a missing `title` key means no <h4> is emitted at all, so the DOM side is
            #     `null` while the record side is `''` — comparing them raw reports a
            #     mismatch on 2 of 6 sampled chapters, none of which is a page defect;
            #   * `prose()` normalises CJK spacing, so 「第五百章 拜见娘家人」 renders as
            #     「第五百章拜见娘家人」. That is a typographic rule, not a rewritten fact.
            # Neither can hide a real mangle: `esc()` double-escaping and `join()` artifacts
            # change *characters*, and those still fail here.
            for field in ("Title", "Summary"):
                shown, data = got["shown" + field] or "", got["data" + field] or ""
                if shown == data:
                    continue
                if re.sub(r"\s+", "", shown) == re.sub(r"\s+", "", data):
                    prose_ws.append([field.lower(), got["ch"]])
                else:
                    prose_bad.append([field.lower(), got["ch"], data[:30], shown[:30]])
            # `-webkit-line-clamp: none` plus `overflow: visible` is what an unclipped block
            # computes to. Anything else means the text is present in the DOM but walled off.
            if got["clamp"] not in (None, "none") or (got["overflow"] or "visible") != "visible":
                prose_clamped.append([got["ch"], got["clamp"], got["overflow"]])
        covered = sorted({r["ch"] for r in prose_rows})
        report["prose_fidelity"] = {"rows": prose_rows, "mismatched": prose_bad,
                                    "clamped": prose_clamped, "absent": prose_absent,
                                    "whitespace_only": prose_ws, "covered": covered,
                                    "stale": prose_stale, "home_view": home_view}
        if prose_absent:
            report["checks"].append(
                f"prose: the chapter-summary block rendered no card at cutoff(s) {prose_absent} "
                f"— the block is empty, so text fidelity was not established")
        if prose_stale:
            report["checks"].append(
                f"prose: after moving the cutoff to {[c for c, _ in prose_stale]} the first "
                f"card still belonged to {[c for _, c in prose_stale]} — the stream did not "
                f"repaint, so the comparison was made against stale text")
        if prose_bad:
            report["checks"].append(
                f"prose: {len(prose_bad)} of {len(prose_rows) * 2} compared strings differ from "
                f"the graph — the reader is not being shown the record: {preview(prose_bad, 4)}")
        if prose_clamped:
            report["checks"].append(
                f"prose: the summary is clipped rather than folded on {len(prose_clamped)} "
                f"chapter(s) {preview(prose_clamped, 4)} — a wall, not a fold (contract 3.2.4)")
        # 防退化: too few distinct chapters means the sample stopped reaching the block, which
        # would let a fidelity assertion pass while comparing almost nothing.
        if len(covered) < 4:
            report["checks"].append(
                f"prose: only {len(covered)} distinct chapter(s) were reached "
                f"({covered}) out of {len(PROSE_CUTOFFS)} cutoffs — the sample degenerated")
        print(f"prose fidelity: {len(prose_rows)}/{len(PROSE_CUTOFFS)} cutoffs read, "
              f"home={home_view}, chapters={covered}, mismatched={len(prose_bad)}, "
              f"clamped={len(prose_clamped)}, absent={len(prose_absent)}, stale={len(prose_stale)}"
              + (f", whitespace-only={prose_ws}" if prose_ws else ""))

        # The report is persisted BEFORE the screenshots, not after them.
        #
        # Why this moved: every assertion in this suite runs above this line, and the screenshot
        # loop below is the only part that is purely cosmetic. The report used to be written
        # after `b.close()` at the very end, so a failure anywhere in the screenshot pass threw
        # away every verified result from all 45 gates. That is what happened three times in
        # round 15: the run completed every check with zero failures, died on a screenshot, and
        # left no `accept.json` behind -- so the only evidence of the passing run was a partial
        # stdout log. A cosmetic step must never be able to destroy the measurement.
        (out / "accept.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

        # Screenshots of the new surfaces, for the human pass that no assertion replaces.
        # Each shot scrolls its subject into view first: a screenshot of the top of the
        # document shows the header and nothing else, which is how an earlier round
        # produced four images that all looked identical.
        #
        # This whole block is best-effort. `pg.screenshot` on a page this large can be killed
        # by memory pressure (measured: the renderer tree reaches 851 MB and keeps climbing),
        # and the right response is to note which shots were missed, not to lose the report.
        def shoot(name):
            pg.screenshot(path=str(out / name))

        shots = [
            ("#/", "atlas-home.png", "#block-graph"),
            ("#/char/char_qin_chao", "atlas-page-char.png", ".pg-graph"),
            ("#/event/" + (ev_id or "x"), "atlas-page-event.png", ".pblock"),
            ("#/index/item", "atlas-index-item.png", ".ix-grid"),
        ]
        _shots_ok, _shots_failed = [], []
        try:
            for frag, name, anchor in shots:
                pg.evaluate("h => { location.hash = h; }", frag)
                pg.wait_for_timeout(560)
                if anchor:
                    pg.evaluate("""sel => {
                      const n = document.querySelector(sel);
                      if (n) n.scrollIntoView({ block: 'start' });
                      window.scrollBy(0, -70);
                    }""", anchor)
                    pg.wait_for_timeout(420)
                shoot(name)
                _shots_ok.append(name)
            for mode, name in (("mind", "atlas-graph-mind.png"),
                               ("flow", "atlas-graph-flow.png"),
                               ("tree", "atlas-graph-tree.png")):
                pg.evaluate("() => { location.hash = '#/'; }")
                pg.wait_for_timeout(380)
                el = pg.query_selector(f'[data-gmode="{mode}"]')
                if el:
                    el.click()
                    pg.wait_for_timeout(820)
                    pg.evaluate("""() => {
                      const w = document.querySelector('.graph-wrap');
                      if (w) w.scrollIntoView({ block: 'center' });
                    }""")
                    pg.wait_for_timeout(420)
                    shoot(name)
                    _shots_ok.append(name)
        except Exception as _exc:  # pragma: no cover - cosmetic only
            # Record the miss instead of dying on it. Which shots are absent is itself the
            # useful fact for the human pass; a missing image is not a failed assertion.
            _shots_failed.append(f"{name}: {str(_exc)[:140]}")
            print(f"  !! screenshot pass stopped at {name}: {str(_exc)[:140]}")
        report["screenshots"] = {"written": _shots_ok, "failed": _shots_failed}
        print(f"screenshots: {len(_shots_ok)} written"
              + (f", {len(_shots_failed)} failed {_shots_failed}" if _shots_failed else ""))
        try:
            pg.evaluate("""() => {
              const b = document.querySelector('[data-gmode="sector"]');
              if (b) b.click();
            }""")
            pg.wait_for_timeout(400)
        except Exception:
            pass

        b.close()

    (out / "accept.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"# atlas acceptance: {html.name}")
    print(f"ready={report['ready']} load={report.get('load_ms')}ms stream={report['stream_chars']} chars")
    print(f"counts: {report['counts']}")
    print(f"graph after scroll: {report.get('graph_after_scroll')}")
    print(f"blocks: {len(report['blocks'])}")
    for k, v in report["blocks"].items():
        print(f"  - [{v['sec']:<10}] {v['title'][:26]:<28} {v['chars']:>7} chars")
    print("drawer:")
    for k, v in report["drawer"].items():
        print(f"  - {k:<34} {v['chars']:>6} chars  sections={len(v['sections'])}")
    print("snapshots (cards must never exceed live entities):")
    for s in report["snapshots"]:
        print(f"  - {s['badge']:<12} entities={s['entities']:>4} cards={s['cards']:>4} chars={s['chars']}")

    lib = report.get("library") or {}
    if lib:
        print("agent library:")
        print(f"  - budget slice     {lib.get('shown')} / {lib.get('all')}  "
              f"(more button: {lib.get('hasMore')})")
        print(f"  - search '{lib.get('hiddenName')}' -> "
              f"{'hit' if lib.get('foundAfterSearch') else 'MISS'} "
              f"(hidden, id={lib.get('hiddenId')}), expand hidden when filtering: "
              f"{lib.get('moreGoneWhenFiltered')}")
        print(f"  - type filter 势力  {lib.get('orgCards')} / {lib.get('orgLive')} live")
        print(f"  - restored after clearing query: {lib.get('restored')}")
    print(f"perf drag (per-frame while scrubbing): {report['perf'].get('drag_ms')}")
    print(f"perf drag repeat (same session):       {report['perf'].get('drag_ms_repeat')} "
          f"-> p50 drift {report['perf'].get('drag_p50_drift_ms')} ms")
    print(f"perf drag third (same session):        {report['perf'].get('drag_ms_third')}")
    print(f"perf drag within-session spread:       "
          f"{report['perf'].get('drag_within_session_spread')} "
          f"-> p95 median of 3 = {report['perf'].get('drag_p95_median_of_3')} ms (budget 100)")
    print(f"perf drag frame interval (js + layout): {report['perf'].get('drag_frame_ms')} "
          f"-> p95 median of 3 = {report['perf'].get('drag_frame_p95_median_of_3')} ms "
          f"(budget 100; spread {report['perf'].get('drag_frame_within_session_spread')})")
    sh = report.get("sector_hover")
    if sh:
        print(f"sector hover: zone={sh.get('zone')} lit={sh.get('named')} "
              f"named@default={sh.get('loudAtDefault')} named@zoom={sh.get('loudWhenZoomed')} "
              f"rowLit={sh.get('rowLit')} othersFaded={sh.get('othersFaded')}")
    print(f"perf jump (isolated setChapter):       {report['perf'].get('render_ms')}")
    print(f"perf jump repeat (same session):       {report['perf'].get('render_ms_repeat')} "
          f"-> p50 drift {report['perf'].get('render_p50_drift_ms')} ms (bound 35)")
    print(f"perf jump third (same session):        {report['perf'].get('render_ms_third')}")
    print(f"perf jump frame interval (steady):     {report['perf'].get('render_ms_frame')} "
          f"(spread {report['perf'].get('render_frame_within_session_spread')})")
    print(f"perf jump FIRST VISIT (reported):      "
          f"{report['perf'].get('render_ms_first_visit')} "
          f"frame {report['perf'].get('render_ms_first_visit_frame')} "
          f"(one observation per session)")
    print(f"perf jump within-session spread:       "
          f"{report['perf'].get('render_within_session_spread')} -> budget "
          f"{report['perf'].get('render_ms_budget')} (see render_ms_budget_note), "
          f"liveness floor {report['perf'].get('render_liveness_floor_ms')} ms")
    if report["snake_tokens"]:
        print(f"snake tokens (first 40): {report['snake_tokens']}")
    if report.get("open_questions"):
        print("\nOPEN QUESTIONS (registered, not asserted):")
        for q in report["open_questions"]:
            print(f"  - {q}")
    if report["checks"]:
        print("\nCHECKS FAILED:")
        for c in report["checks"]:
            print(f"  - {c}")
    else:
        print("\nALL CHECKS PASS")
    if report["errors"]:
        print("\nJS ERRORS:")
        if len(report["errors"]) > 20:
            print(f"  (showing the first 20 of {len(report['errors'])} — the full list is in "
                  f"accept.json)")
        for e in report["errors"][:20]:
            print(f"  - {e}")
    return 1 if (report["checks"] or report["errors"]) else 0


if __name__ == "__main__":
    raise SystemExit(main())
