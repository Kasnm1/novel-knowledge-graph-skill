#!/usr/bin/env python3
"""Verify dynamic chapter replay through the dashboard's real renderer.

Same technique as `smoke_dashboard.py`: extract the dashboard's inline script, run the
*real* renderer under a minimal DOM / Cytoscape stub in Node, call the real
`setChapter(N)` and `showEntity(id)`, then scan the produced panel HTML.

For every requested snapshot it compares the renderer's derived current state,
active relation IDs, and item-role holders with `snapshot.py`. Full-range names,
summaries, histories, evidence, and foreshadowing are intentionally allowed.
It also rejects raw JSON dumps and reader-visible source-line fields.

The probe is appended to the app source *before* `eval`, so it shares the app's scope and
can see `let chapter` / `setChapter`. A probe run from outside the eval cannot.

Usage:

    python scripts/verify_chapter_views.py --run-dir runs/<book-range> \
        --snapshot 0 --snapshot 10 --snapshot 50

With no `--snapshot`, the script checks the first chapter, the quarter points, and the last
analyzed chapter. With no `--entity`, it probes the protagonist plus a spread of other entities.

Requires `node` on PATH. Exits 0 when clean, 1 otherwise.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from snapshot import active_relations, dynamic_state_for_entity, ownership_at


APP_SCRIPT_RE = re.compile(r"<script(?![^>]*\bsrc=)[^>]*>(.*?)</script>", re.S)
# `node` 起不来时的退出码（0xC0000142 STATUS_DLL_INIT_FAILED）。它是**系统级**资源
# 耗尽——同一台机器上跑着的其他会话也在开 node，双方互相拖死——所以它不是本脚本的
# 错误，重试有意义，但必须给系统足够时间回收（见 `run_snapshot`）。
DLL_INIT_FAILED = 3221225794

# 重试次数与**快照之间**的间隔。间隔是这里最有效的杠杆：实测「一个快照一个进程、
# 之间 sleep 5」能一次跑完 11 个快照（约 5.5 分钟），而把快照挤在一起时第 9 个左右
# 必挂。代价是慢，换来的是不再把环境问题报成内容问题。
RETRY_ATTEMPTS = 6
SNAPSHOT_GAP_SECONDS = 5.0

STUB = r"""const fs = require('fs');
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
"""

# Appended to the app source so it shares the app's eval scope; only then are
# `let chapter` and `setChapter` visible.
PROBE = r"""
;(function () {
  const out = { snapshot: __N__, applied: null, entities: {}, errors: [] };
  try { setChapter(__N__); out.applied = chapter; } catch (e) { out.errors.push('setChapter: ' + e); }
  for (const id of __PROBES__) {
    try {
      showEntity(id);
      const entity = byId.get(id);
      const relations = (relationsByEntity.get(id)||[])
        .filter(r => (r.valid_from??0) <= chapter && (!r.valid_to || r.valid_to >= chapter))
        .map(r => r.id).sort();
      const ownership = entity?.type === 'item' ? itemOwnership(entity).current.slice().sort() : [];
      out.entities[id] = { html: document.__captured, state: effectiveState(entity), relations, ownership };
    }
    catch (e) { out.entities[id] = { html: '', state: {}, relations: [], ownership: [] }; out.errors.push(id + ': ' + e); }
  }
  fs.writeFileSync('report.json', JSON.stringify(out), 'utf8');
  process.exit(0);
})();
"""

def extract_app_script(html: str) -> str:
    for script in reversed(APP_SCRIPT_RE.findall(html)):
        if "const graph=" in script:
            return script
    raise SystemExit("no inline dashboard script found (expected one containing 'const graph=')")


def default_snapshots(start: int, end: int) -> list[int]:
    """Range-proportional probe points.

    Fixed points (chapter 10 and the last chapter) collapse on a short run — a
    20-chapter book would be checked twice at the same place — so take quarters
    of the actual span instead, and always include the first chapter so a
    prologue at chapter 0 is exercised.
    """
    span = end - start
    points = {start, end}
    for fraction in (0.25, 0.5, 0.75):
        points.add(start + round(span * fraction))
    return sorted(n for n in points if start <= n <= end)


def default_probes(graph: dict) -> list[str]:
    """Protagonist first, then a spread across types so every panel branch is exercised."""
    entities = graph.get("entities") or []
    by_id = {e["id"]: e for e in entities}
    chosen: list[str] = []

    protagonist = graph.get("metadata", {}).get("protagonist_id")
    if protagonist in by_id:
        chosen.append(protagonist)
    for route in graph.get("romance_routes") or []:
        pid = route.get("protagonist_id")
        if pid in by_id and pid not in chosen:
            chosen.append(pid)
            break

    for wanted in ("character", "item", "skill", "creature", "level_axis", "organization", "location"):
        for e in entities:
            if e.get("type") == wanted and e["id"] not in chosen:
                chosen.append(e["id"])
                break
    return chosen[:8]


def run_snapshot(app: str, snapshot: int, probes: list[str]) -> dict:
    """Run one snapshot in Node, retrying once.

    The harness fails intermittently: the same artifact passes on a re-run, and
    `stderr` is empty, so the only evidence is the exit code. A bare
    "harness failed" with no diagnostic reads like a content problem when it is
    not (2026-09-14: once at N=200 in `谁让他修仙的-1-100` and once at N=413 in
    `我的狐仙老婆-full`; both PASSed on re-run). Retry once, and put the exit
    code in the message so a genuine failure is distinguishable from a flake.
    """
    last: subprocess.CompletedProcess | None = None
    for attempt in range(1, RETRY_ATTEMPTS + 1):
        if attempt > 1:
            # 「立刻重试一次」不够用：失败是**累积**的资源耗尽，不是单次抖动。
            # 2026-09-14 在斗罗实测，同一进程里连开 6 个 node 后必挂在 N=200，
            # returncode=3221225794（0xC0000142 STATUS_DLL_INIT_FAILED，stderr 空）；
            # 把快照拆成 3 个一批分别调用，11 个快照全部 PASS。所以重试必须**退避**，
            # 给系统时间回收进程资源，否则第 2 次照样立刻失败。
            #
            # 而这个码是**系统级**的，不只影响本进程：同一台机器上的其他会话也在开
            # node，双方互相拖死。1.5s 的退避在这种情形下等于没退避——实测 4 次重试
            # 全落在同一秒内、全部失败（2026-09-14 我的狐仙老婆-full 第 12 步 N=500）。
            # 对这个码改用 5s 起步的长退避，给系统时间回收句柄与桌面堆。
            backoff = 1.5 * (attempt - 1)
            if last is not None and last.returncode == DLL_INIT_FAILED:
                backoff = 5.0 * (attempt - 1)
            time.sleep(backoff)
        with tempfile.TemporaryDirectory() as tmp:
            work = Path(tmp)
            (work / "app_probe.js").write_text(
                app
                + PROBE.replace("__N__", str(snapshot)).replace("__PROBES__", json.dumps(probes)),
                encoding="utf-8",
            )
            (work / "run.js").write_text(
                STUB + "\neval(fs.readFileSync('app_probe.js', 'utf8'));\n", encoding="utf-8"
            )
            proc = subprocess.run(
                ["node", "run.js"], cwd=work, capture_output=True, text=True, encoding="utf-8"
            )
            if proc.returncode == 0:
                if attempt > 1:
                    print(
                        f"  ! N={snapshot}: 第 1 次 harness 退出码非 0（stderr 空），重试后通过",
                        file=sys.stderr,
                    )
                return json.loads((work / "report.json").read_text(encoding="utf-8"))
            last = proc
    raise SystemExit(
        f"harness failed at N={snapshot}: returncode={last.returncode} stderr={last.stderr!r}"
    )


def value_tokens(value: object) -> set[str]:
    """Flatten targeted snapshot values into stable comparison tokens."""

    if value is None or value == "" or value is False:
        return set()
    if isinstance(value, (list, tuple, set)) and not value:
        return set()
    if isinstance(value, dict) and "targets" in value:
        return value_tokens(value.get("value")) | value_tokens(value.get("targets"))
    if isinstance(value, dict) and not set(value).issubset({"value", "label"}):
        answer: set[str] = set()
        for item in value.values():
            answer.update(value_tokens(item))
        return answer
    if isinstance(value, dict) and not value:
        return set()
    return {json.dumps(value, ensure_ascii=False, sort_keys=True)}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", required=True, type=Path, help="Run directory holding dashboard.html and graph.json")
    parser.add_argument("--dashboard", type=Path, help="Defaults to <run-dir>/dashboard.html")
    parser.add_argument("--graph", type=Path, help="Defaults to <run-dir>/graph.json")
    parser.add_argument("--snapshot", action="append", type=int, default=[], help="Chapter to freeze at; repeat as needed")
    parser.add_argument("--entity", action="append", default=[], help="Entity ID to open; repeat as needed")
    parser.add_argument(
        "--vocabulary",
        type=Path,
        help="Display vocabulary (default <run-dir>/display-vocabulary.json). Its labels are "
             "excluded from the name-leak test: a label is UI chrome, not narrative content.",
    )
    args = parser.parse_args()

    if shutil.which("node") is None:
        raise SystemExit("node is required for this check but was not found on PATH")

    run = args.run_dir.resolve()
    dashboard = (args.dashboard or run / "dashboard.html").resolve()
    graph_path = (args.graph or run / "graph.json").resolve()
    html = dashboard.read_text(encoding="utf-8")
    graph = json.loads(graph_path.read_text(encoding="utf-8"))
    app = extract_app_script(html)

    analyzed = graph.get("metadata", {}).get("analyzed_chapters") or []
    end = max(analyzed) if analyzed else graph["metadata"]["chapter_end"]
    start = graph.get("metadata", {}).get("chapter_start") or 0
    snapshots = args.snapshot or default_snapshots(start, end)
    probes = args.entity or default_probes(graph)

    entity_index = {
        entity["id"]: entity for entity in graph.get("entities") or [] if entity.get("id")
    }
    failures: list[str] = []
    print(f"# 章节快照核查：{run.name}")
    print(f"范围 {start}–{end} 章 · 探测实体 {len(probes)} 个 · 快照 {snapshots}")
    for index, snapshot in enumerate(snapshots):
        # 快照之间留间隔：这是唯一被实测证明有效的杠杆（见 SNAPSHOT_GAP_SECONDS）。
        # 放在循环开头而不是结尾，是为了让「上一次失败后」也吃到这段间隔。
        if index:
            time.sleep(SNAPSHOT_GAP_SECONDS)
        reachable = [eid for eid in probes if eid in entity_index]
        report = run_snapshot(app, snapshot, reachable)
        if report["errors"]:
            failures.append(f"N={snapshot} 渲染报错：{report['errors'][:3]}")
        if report["applied"] != snapshot:
            failures.append(
                f"N={snapshot}: setChapter 实际停在第 {report['applied']} 章（章节区间不可达）"
            )
        checked_states = checked_relations = checked_ownership = 0
        for eid, rendered in report["entities"].items():
            body = rendered["html"]
            if "<pre>" in body:
                failures.append(f"N={snapshot}: {eid} 出现原始 JSON 转储")
            expected = dynamic_state_for_entity(graph, eid, snapshot)
            expected_values = value_tokens(expected.get("facets")) | value_tokens(expected.get("levels"))
            actual_values = value_tokens(rendered.get("state"))
            missing_values = expected_values - actual_values
            if missing_values:
                failures.append(f"N={snapshot}: {eid} 当前状态不符，缺少 {sorted(missing_values)[:3]}")
            checked_states += len(expected_values)
            expected_relations = sorted(r["id"] for r in active_relations(graph, eid, snapshot))
            if expected_relations != rendered.get("relations"):
                failures.append(
                    f"N={snapshot}: {eid} 有效关系不符，期望 {expected_relations[:5]}，实际 {rendered.get('relations', [])[:5]}"
                )
            checked_relations += len(expected_relations)
            if entity_index[eid].get("type") == "item":
                expected_owners = sorted({row["entity_id"] for row in ownership_at(graph, eid, snapshot)})
                if expected_owners != rendered.get("ownership"):
                    failures.append(
                        f"N={snapshot}: {eid} 物品角色不符，期望 {expected_owners}，实际 {rendered.get('ownership', [])}"
                    )
                checked_ownership += len(expected_owners)
        print(
            f"  N={snapshot}: 实际 chapter={report['applied']}，检查 {len(report['entities'])} 个面板"
            f"，当前状态值 {checked_states} 项，有效关系 {checked_relations} 条，物品角色 {checked_ownership} 项"
        )

    for name in ("dashboard.html", "AI_CONTEXT.md"):
        p = run / name
        if p.is_file() and re.search(r"source_line", p.read_text(encoding="utf-8")):
            failures.append(f"{name}: 出现 source_line 行号字段")

    if failures:
        print("FAIL")
        seen: set[str] = set()
        for item in failures:
            key = re.sub(r"「第 \d+ 章」", "", item)
            if key in seen:
                continue
            seen.add(key)
            print("  -", item)
        return 1
    print("PASS：动态状态、有效关系与物品角色回放一致；无原始 JSON 转储或读者可见行号。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
