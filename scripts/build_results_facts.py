#!/usr/bin/env python3
"""Derive every headline number in RESULTS.md from the run's own artifacts.

Why this exists
---------------
Two consecutive closeout rounds shipped wrong numbers in `RESULTS.md`: the
entity/state-change/evidence/review totals were left over from an earlier
fragment batch, `RENAMES` was quoted as 103 when it held 38 entries, and the
"33 组同名" figure did not match the 38-old-IDs-to-26-survivors reality. Every
one of those numbers was *typed by hand* from a report someone had read once.
Nothing in the pipeline could tell that the document had drifted from the data,
because the document is prose and no check reads it.

The fix is not "be more careful". It is to make the numbers a build artifact:
this script recomputes each figure from `graph.json`, `validation.json`, the
fragment files and the audit scripts, writes them into `RESULTS.md` between two
markers, and can re-derive and compare them later.

    # write the generated block into RESULTS.md
    python scripts/build_results_facts.py --run-dir runs/<book-range> --write

    # verify the block still matches the artifacts (exit 1 on drift)
    python scripts/build_results_facts.py --run-dir runs/<book-range> --check

    # just print the facts as JSON
    python scripts/build_results_facts.py --run-dir runs/<book-range>

Numbers that appear *outside* the generated block are still hand-written; the
block is the spine, not a proof of the whole document. The finalization
checklist must say plainly: every number in RESULTS.md comes from here.

The level-audit figures are produced by invoking the shared `rollup_levels.py`
and `audit_asof_prose.py` rather than re-implementing them, so there is exactly
one definition of each number.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import tempfile
from collections import Counter
from pathlib import Path


SCRIPTS = Path(__file__).resolve().parent
BEGIN = "<!-- FACTS:BEGIN -->"
END = "<!-- FACTS:END -->"

# The arrays whose counts RESULTS.md quotes. Kept in one place so a new array
# cannot be silently omitted from the table.
#
# **这份清单必须与 `required_fields.ARRAY_KINDS` 逐项对齐**。此前少了
# `character_traits` / `chapter_summaries` / `level_conversions` 三项，后果是
# 「0 条」在这张表里无处显形——`character_traits` 因此以 0/734 的状态活了六轮。
# `scripts/audit_schema_coverage.py` 会对这份清单与 `ARRAY_KINDS` 做差集，漏一项就报错。
ARRAYS = (
    "entities", "events", "relations", "state_changes", "evidence",
    "foreshadowing", "review_issues", "romance_routes", "intimate_acts",
    "character_traits", "chapter_summaries", "level_conversions", "item_roles", "story_arcs",
)


def run_json(script: str, args: list[str], cwd: Path) -> dict | None:
    """Run a sibling script and read the JSON it wrote.

    Sibling scripts print human-facing text, so the machine-readable copy comes
    from an ``--output``/``--json`` file, not from stdout.
    """
    # 临时目录**必须建在系统临时区，不能建在 run 目录里**（原先写的是
    # `dir=cwd`）。本机的删除守卫按「单次工具调用内的删除数」计数，阈值 50；
    # 建在 run 目录里，清理时删的就是工作区内的文件，于是第 13 步在整条流水线的
    # 末尾被拦下（实测 2026-09-14：`[safe-delete][SAFE_DELETE_BULK_CONFIRM_REQUIRED]`，
    # 整个 rebuild.sh 退出 1），而且每次中止都在 run 目录里留下一个 `_facts_tmp_*` 残骸。
    # smoke_dashboard.py 与 verify_chapter_views.py 的临时目录本来就在系统临时区，
    # 所以它们从来没撞上过这条——这里跟它们保持一致。
    with tempfile.TemporaryDirectory(prefix="nkg-facts-") as tmp:
        out = Path(tmp) / "report.json"
        cmd = [sys.executable, str(SCRIPTS / script), *args, "--output", str(out)]
        if script == "audit_asof_prose.py":
            cmd = [sys.executable, str(SCRIPTS / script), *args, "--json", str(out)]
        proc = subprocess.run(cmd, cwd=str(cwd), capture_output=True, text=True, encoding="utf-8")
        if not out.is_file():
            print(f"警告：{script} 没有产出报告（退出码 {proc.returncode}）", file=sys.stderr)
            if proc.stderr.strip():
                print(proc.stderr.strip()[:500], file=sys.stderr)
            return None
        return json.loads(out.read_text(encoding="utf-8"))


def intimacy_coverage(graph: dict) -> dict:
    """亲密行为的覆盖度：事件 vs 记录 vs 说明。

    为什么这一项必须进 FACTS 块
    ---------------------------
    校验器只要求「一条 intimate_acts 记录的字段合法」，从不与原文比对，所以
    「有 62 条 intimacy 事件、却只有 9 个章节有行为记录」这种缺口可以一直
    报绿——本 run 就是这样漏掉了全书第一次性关系（第 334 章，用户指出前 500 章
    回填不彻底才发现）。所以把三个数并列打进 RESULTS.md：事件数、记录覆盖的章数、
    以及**既没有记录也没有待核问题说明的事件数**。

    最后一项是门禁口径：一条规范化后为 `intimacy` 的事件，要么该章有行为记录，
    要么有一条 `review_issue` 的 `related_ids` 点名这条事件（说明为什么它不是亲密
    行为）。两者都没有 = 有人读漏了。它必须为 0。
    """
    events = [e for e in (graph.get("events") or []) if isinstance(e, dict)]
    # Current merged graphs use the canonical spelling. Canonicalize here too,
    # so a legacy or not-yet-merged alias cannot bypass the coverage gate.
    from event_types import canonical_event_type
    intimate = [e for e in events if canonical_event_type(e.get("type")) == "intimacy"]
    act_chapters = {
        a.get("chapter") for a in (graph.get("intimate_acts") or [])
        if isinstance(a, dict) and isinstance(a.get("chapter"), int)
    }
    explained_events: set[str] = set()
    for issue in graph.get("review_issues") or []:
        if not isinstance(issue, dict):
            continue
        for ref in issue.get("related_ids") or []:
            explained_events.add(ref)

    unsilenced = [
        e for e in intimate
        if e.get("chapter") not in act_chapters and e.get("id") not in explained_events
    ]
    return {
        "intimate_contact_events": len(intimate),
        "intimate_contact_event_chapters": len({e.get("chapter") for e in intimate}),
        "intimate_act_chapters": len(act_chapters),
        "intimate_contact_events_unsilenced": len(unsilenced),
        "intimate_contact_events_unsilenced_ids": [e.get("id") for e in unsilenced],
    }


def skill_fingerprints(run_dir: Path) -> tuple[str, str]:
    """Return the current Skill fingerprint and the run's lightweight receipt.

    Runs execute the currently installed Skill and never copy a private toolchain.
    The receipt is informational: a mismatch identifies which derived products may
    need rebuilding, but does not make an otherwise compatible graph invalid.
    """
    from record_skill_version import aggregate_fingerprint, skill_files

    skill_root = SCRIPTS.parent
    current = aggregate_fingerprint(skill_root, skill_files(skill_root))[:12]
    receipt_path = run_dir / ".skill-version.json"
    receipt = ""
    if receipt_path.is_file():
        try:
            receipt = str(json.loads(receipt_path.read_text(encoding="utf-8")).get("skill_fingerprint") or "")[:12]
        except (OSError, json.JSONDecodeError):
            receipt = ""
    return current, receipt


def count_fragments(fragment_dir: Path) -> tuple[int, int]:
    """Total fragment files, and how many declare chapter coverage."""
    total = with_coverage = 0
    for path in sorted(fragment_dir.glob("fragment-*.json")):
        total += 1
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        chapters = (payload.get("metadata") or {}).get("analyzed_chapters")
        if isinstance(chapters, list) and chapters:
            with_coverage += 1
    return total, with_coverage


def expected_non_empty(run_dir: Path) -> tuple[list[str], dict]:
    """本 run 声明为「期望非空」的数组类型，以及覆盖文件的内容。

    默认取 `required_fields.EXPECTED_NON_EMPTY`（对任何一本书都不该为空的类型）。
    run 可以用 `<run>/expected_kinds.json` 覆盖：`{"character_traits": false}` 表示
    「本书确实没有人物特征」，`{"chapter_summaries": true}` 表示「本 run 做了逐章
    梗概，为空就是漏了」。

    覆盖必须是**显式文件**。静默豁免和没有门禁是一回事——`character_traits` 的 0
    之所以活了六轮，就是因为没有任何地方要求有人对它表态。
    """
    from required_fields import EXPECTED_NON_EMPTY

    path = run_dir / "expected_kinds.json"
    overrides: dict = {}
    if path.is_file():
        try:
            loaded = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                overrides = loaded
        except (json.JSONDecodeError, OSError) as error:
            print(f"警告：{path} 读不出来（{error}），按默认声明处理", file=sys.stderr)
    declared = [name for name in EXPECTED_NON_EMPTY if overrides.get(name, True) is not False]
    declared += [
        name for name, value in overrides.items()
        if value is True and name not in declared
    ]
    return declared, overrides


def collect(run_dir: Path) -> dict:
    graph_path = run_dir / "graph.json"
    graph_bytes = graph_path.read_bytes()
    graph = json.loads(graph_bytes.decode("utf-8"))

    counts = Counter()
    for array in ARRAYS:
        records = graph.get(array)
        counts[array] = len(records) if isinstance(records, list) else 0

    entity_types = Counter(
        str(e.get("type")) for e in (graph.get("entities") or []) if isinstance(e, dict)
    )
    level_changes = [
        c for c in (graph.get("state_changes") or [])
        if isinstance(c, dict) and c.get("facet") == "level"
    ]

    validation = {}
    validation_path = run_dir / "validation.json"
    if validation_path.is_file():
        validation = json.loads(validation_path.read_text(encoding="utf-8"))

    fragments_total, fragments_with_coverage = count_fragments(run_dir / "fragments")
    fingerprint = (graph.get("metadata") or {}).get("input_fingerprint") or {}
    fingerprints = len(fingerprint.get("fragments") or {})

    rollup = run_json("rollup_levels.py", [
        "--graph", str(graph_path),
        "--chapters", str(run_dir / "chapters"),
        "--chapters-jsonl", str(run_dir / "chapters.jsonl"),
    ], cwd=run_dir)
    rollup_summary = (rollup or {}).get("summary") or {}
    ladder_checks = (rollup or {}).get("ladder_checks") or {}
    audit_window = (rollup or {}).get("audit_window") or {}

    asof = run_json("audit_asof_prose.py", ["--graph", str(graph_path)], cwd=run_dir)

    facts: dict[str, tuple[str, object]] = {}
    def add(key: str, label: str, value) -> None:
        facts[key] = (label, value)

    add("graph_sha256", "图谱 SHA-256（前 12 位）", hashlib.sha256(graph_bytes).hexdigest()[:12])
    add("chapter_range", "分析章节范围", f"{graph.get('metadata', {}).get('chapter_start')}—{graph.get('metadata', {}).get('chapter_end')}")

    add("entities_total", "实体", counts["entities"])
    add("entities_characters", "　其中人物", entity_types.get("character", 0))
    add("state_changes_total", "状态变化", counts["state_changes"])
    add("state_changes_level", "　其中等级变化", len(level_changes))
    add("evidence_total", "证据", counts["evidence"])
    add("events_total", "事件", counts["events"])
    add("relations_total", "关系", counts["relations"])
    add("foreshadowing_total", "伏笔", counts["foreshadowing"])
    add("review_issues_total", "待核问题", counts["review_issues"])
    add("romance_routes_total", "感情线", counts["romance_routes"])
    add("intimate_acts_total", "亲密行为", counts["intimate_acts"])
    # 这三项此前不在表里（见 ARRAYS 的注释），于是「0 条」无处显形。
    add("character_traits_total", "人物特征", counts["character_traits"])
    add("chapter_summaries_total", "章节梗概", counts["chapter_summaries"])
    add("story_arcs_total", "剧情弧", counts["story_arcs"])
    add("level_conversions_total", "跨体系换算", counts["level_conversions"])
    add("item_roles_total", "物品角色记录", counts["item_roles"])
    # 期望非空却为空的类型：**必须 0**，且 `--check` 会非零退出。
    # 这不是「显示一个 0」——显示正是失败过的那一半（character_traits 的 0 在
    # AI_CONTEXT 里挂了几轮没人管）。见 required_fields.EXPECTED_NON_EMPTY。
    declared, overrides = expected_non_empty(run_dir)
    empty_expected = [a for a in declared if counts[a] == 0]
    add("expected_kinds_declared", "　声明为期望非空的类型", "、".join(declared) or "—")
    add("expected_kinds_empty", "　其中为空的（必须 0）", len(empty_expected))
    if empty_expected:
        print(f"门禁失败：这些类型被声明为期望非空，实际是 0 条：{'、'.join(empty_expected)}。"
              f"要么补数据，要么在 {run_dir}/expected_kinds.json 里显式声明"
              f"「本书确实没有」（形如 {{\"{empty_expected[0]}\": false}}）。",
              file=sys.stderr)

    # 覆盖度而不是存在性：见 intimacy_coverage() 的 docstring。
    coverage = intimacy_coverage(graph)
    add("intimate_contact_events", "亲密互动事件（intimacy）", coverage["intimate_contact_events"])
    add("intimate_contact_event_chapters", "　涉及章数", coverage["intimate_contact_event_chapters"])
    add("intimate_act_chapters", "有亲密行为记录的章数", coverage["intimate_act_chapters"])
    add("intimate_contact_events_unsilenced", "　既无记录又无待核说明的事件（必须 0）",
        coverage["intimate_contact_events_unsilenced"])
    if coverage["intimate_contact_events_unsilenced"]:
        print("警告：以下 intimacy 事件既没有亲密行为记录、也没有待核问题说明："
              + "、".join(coverage["intimate_contact_events_unsilenced_ids"]), file=sys.stderr)

    add("level_axes", "等级轴", rollup_summary.get("axes"))
    add("level_ladders", "阶梯（实体×轴）", rollup_summary.get("ladders"))
    add("level_changes_total", "等级变化（回放口径）", rollup_summary.get("level_changes"))
    add("level_regressions", "回退", rollup_summary.get("regressions"))
    add("level_chain_breaks", "自检·链断裂", rollup_summary.get("chain_breaks"))
    add("level_cross_axis_labels", "自检·跨轴档位标签", rollup_summary.get("cross_axis_labels"))
    add("level_action_value_conflicts", "自检·动作与数值矛盾", rollup_summary.get("action_value_conflicts"))
    add("level_candidate_gaps", "候选漏记（窗口内）", rollup_summary.get("candidate_gaps"))
    add("level_candidate_gaps_plan_like", "　其中规划／推测语气", rollup_summary.get("candidate_gaps_plan_like"))
    add("level_restatements", "重述", rollup_summary.get("restatements"))
    add("level_unbacked_chapters", "有变化却未被原文证实的章数", rollup_summary.get("chapters_with_unbacked_changes"))
    add("audit_chapters_scanned", "审计覆盖章数", audit_window.get("chapters_scanned"))
    add("audit_chapters_skipped", "　窗口外跳过章数", audit_window.get("chapters_skipped_out_of_window"))

    add("fragments_total", "分片", fragments_total)
    add("fragments_with_coverage", "　其中声明覆盖度", fragments_with_coverage)
    add("input_fingerprints", "合并时记录的分片指纹", fingerprints)
    current_hash, receipt_hash = skill_fingerprints(run_dir)
    add("skill_current_sha256", "当前 Skill 指纹", current_hash)
    add("skill_receipt_sha256", "本 run 最近登记的 Skill 指纹", receipt_hash or "—")
    add("skill_receipt_matches", "登记指纹与当前版本一致", "是" if receipt_hash == current_hash else "否／未登记")

    add("asof_prose_hits", "正文引用未来章节（渲染层义务）", (asof or {}).get("total"))
    add("asof_prose_groups", "　涉及字段组", (asof or {}).get("group_count"))
    # 名称侧与章号侧是两条独立义务：一条注记可以不含任何「第 X 章」却点名一个
    # 还没出现的称呼（第 148 章的伏笔标题写着「林彤的师父」）。此前只统计章号侧，
    # 名称侧的 62 处 / 10 组是**空转了很久才第一次有数**的——因为别名定年表为空时
    # 它恒报 0（见 references/known-gaps.md A8）。所以把「表有多大」也放进块里：
    # 它是「这一步真的跑过了」的凭据，0 条就说明核查在空转，而不是「没问题」。
    add("asof_name_hits", "正文引用尚未出现的名称（渲染层义务）", (asof or {}).get("name_total"))
    add("asof_name_groups", "　涉及字段组", (asof or {}).get("name_group_count"))
    add("alias_first_chapter_size", "别名定年表条目（0 = 别名核查空转）",
        (asof or {}).get("alias_first_chapter_size"))

    add("validation_valid", "校验 valid", validation.get("valid"))
    add("validation_errors", "校验 errors", validation.get("error_count"))
    add("validation_warnings", "校验 warnings", validation.get("warning_count"))

    return facts


def render(facts: dict) -> str:
    lines = [
        BEGIN,
        "",
        "> 本表由 `python scripts/build_results_facts.py --run-dir <run-dir> --write` 生成，"
        "**不要手改**。改动任何分片后重跑 `--check`；与产物不一致会退出非零。",
        "",
        "| 键 | 指标 | 值 |",
        "|---|---|---|",
    ]
    for key, (label, value) in facts.items():
        shown = "—" if value is None else value
        lines.append(f"| `{key}` | {label} | {shown} |")
    lines += ["", END]
    return "\n".join(lines)


def parse_block(text: str) -> dict[str, str]:
    """Read `| key | label | value |` rows out of the generated block."""
    if BEGIN not in text or END not in text:
        return {}
    body = text.split(BEGIN, 1)[1].split(END, 1)[0]
    found: dict[str, str] = {}
    for line in body.splitlines():
        stripped = line.strip()
        if not stripped.startswith("|"):
            continue
        cells = [c.strip() for c in stripped.strip("|").split("|")]
        if len(cells) < 3 or not cells[0].startswith("`"):
            continue
        found[cells[0].strip("`")] = cells[-1]
    return found


def splice(text: str, block: str) -> str:
    if BEGIN in text and END in text:
        head, rest = text.split(BEGIN, 1)
        _, tail = rest.split(END, 1)
        return f"{head}{block}{tail}"
    lines = text.splitlines(keepends=True)
    for index, line in enumerate(lines):
        if line.startswith("# "):
            return "".join(lines[: index + 1]) + "\n" + block + "\n" + "".join(lines[index + 1 :])
    return block + "\n\n" + text


def fact_gate_failures(facts: dict) -> list[str]:
    """Return hard coverage failures represented by the generated facts."""
    failures: list[str] = []
    empty_expected = facts.get("expected_kinds_empty", (None, 0))[1] or 0
    if empty_expected:
        failures.append(
            f"{empty_expected} 个类型被声明为期望非空，实际是 0 条；"
            "补数据或在 expected_kinds.json 中显式声明本书例外"
        )
    unsilenced = facts.get("intimate_contact_events_unsilenced", (None, 0))[1] or 0
    if unsilenced:
        failures.append(
            f"{unsilenced} 条 intimacy 事件既没有亲密行为记录，也没有待核问题说明"
        )
    return failures


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", required=True, type=Path)
    parser.add_argument("--results", type=Path, help="RESULTS.md path (default <run-dir>/RESULTS.md)")
    parser.add_argument("--write", action="store_true", help="Write/replace the generated block")
    parser.add_argument("--check", action="store_true", help="Verify the block matches the artifacts")
    parser.add_argument("--json", type=Path, help="Also dump the raw facts as JSON")
    args = parser.parse_args()

    run_dir = args.run_dir.resolve()
    if not (run_dir / "graph.json").is_file():
        print(f"找不到 {run_dir / 'graph.json'}", file=sys.stderr)
        return 2
    results_path = args.results or (run_dir / "RESULTS.md")

    facts = collect(run_dir)
    rendered = render(facts)

    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(
            json.dumps({k: v for k, (_, v) in facts.items()}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    if args.write:
        text = results_path.read_text(encoding="utf-8") if results_path.is_file() else ""
        if text.count(BEGIN) > 1 or text.count(END) > 1:
            print(f"FAIL：{results_path} 里有不止一个生成块"
                  f"（BEGIN×{text.count(BEGIN)} / END×{text.count(END)}）。"
                  f"splice 只会替换第一个，剩下的会变成第二份互相矛盾的表格。"
                  f"手工删到只剩一对标记再跑 --write。")
            return 1
        results_path.write_text(splice(text, rendered), encoding="utf-8")
        print(f"已写入 {results_path}（{len(facts)} 项）")
        return 0

    if args.check:
        if not results_path.is_file():
            print(f"找不到 {results_path}", file=sys.stderr)
            return 2
        text = results_path.read_text(encoding="utf-8")
        # 标记必须唯一：正文里若出现字面量（例如解释脚本用法时），第一个 BEGIN
        # 仍能解析成功，但下一次 --write 会只替换第一块而留下第二块。这种漂移
        # 靠比对数字看不出来，所以在这里挡掉。
        if text.count(BEGIN) != 1 or text.count(END) != 1:
            print(f"FAIL：{results_path} 的标记不是恰好一对"
                  f"（BEGIN×{text.count(BEGIN)} / END×{text.count(END)}）。"
                  f"正文里不要写标记字面量，改成「FACTS 标记块」这样的说法。")
            return 1
        embedded = parse_block(text)
        if not embedded:
            print(f"FAIL：{results_path} 里没有生成块（{BEGIN} … {END}）。"
                  f"先跑 --write。")
            return 1
        mismatches: list[str] = []
        for key, (label, value) in facts.items():
            shown = "—" if value is None else str(value)
            if key not in embedded:
                mismatches.append(f"  缺行  {key}（应为 {shown}）")
            elif embedded[key] != shown:
                mismatches.append(f"  不一致 {key}：文档 {embedded[key]} ≠ 产物 {shown}")
        for key in embedded:
            if key not in facts:
                mismatches.append(f"  多余行 {key}（产物已无此项）")
        if mismatches:
            print(f"FAIL：{results_path} 的生成块与产物不一致（{len(mismatches)} 处）：")
            print("\n".join(mismatches))
            print("\n跑 --write 重新生成，并检查正文里手写的数字是否也要跟着改。")
            return 1
        # 声明为「期望非空」却为空 → 非零退出。这一条**必须**在这里失败，不能只印一个 0：
        # 一个计数没人拿去跟任何东西比，就是 `character_traits` 活了六轮的原因。
        # `--write` 刻意不在这里失败（它要先落盘，好让 RESULTS.md 里能看到这些数字），
        # 所以流水线是在紧随其后的 `--check` 上停下。
        gate_failures = fact_gate_failures(facts)
        if gate_failures:
            print("FAIL：事实门禁未通过：")
            print("\n".join(f"  - {message}" for message in gate_failures))
            return 1
        print(f"PASS：{results_path} 的生成块与产物一致（{len(facts)} 项）。")
        return 0

    print(json.dumps({k: v for k, (_, v) in facts.items()}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
