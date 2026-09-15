#!/usr/bin/env python3
"""Audit that every place which must agree about record kinds actually agrees.

Why this exists
---------------
The same defect has now shipped twice, and both times it was "the template is
the gate" (known-gaps A12):

* `intimate_acts` — the fragment template had no slot for an intimate act, so no
  worker ever wrote one, and the book's first sexual relationship was missing
  from the graph until a reader noticed.
* `character_traits` — the template had no slot for a trait either, so the
  run shipped **0 traits across 734 entities** and nothing said so. The
  infrastructure was already complete (schema, per-fragment gate, dashboard
  panel, AI-context section); only the spec was missing.

Both times the fix was "add that one key", which is fixing the instance and not
the class. Adding a record kind means editing **six** places, and nothing was
comparing them:

    1. `required_fields.ARRAY_KINDS`      the authority
    2. `TASK-SPEC.md` template keys       what each extraction worker is handed
    3. `build_results_facts.ARRAYS`       which counts reach RESULTS.md
    4. `check_fragment.py`                the per-fragment gate
    5. `build_dashboard.py` / `export_ai_context.py`   the readers
    6. `audit_asof_prose.ARRAYS`          which arrays get as-of prose checking

This script turns "when a field is missing from the template, look for what else
is missing" from a mood into a diff. It is also the checklist: run it and it
names every place a new kind still has to be wired in.

Hard failures vs. reports
-------------------------
Checks 1–4 are structural — every record kind must be handled there, so a gap is
an error. Checks 5–6 are reported, not failed: not every array is a panel
(`evidence` has no panel), and not every array carries prose that can cite the
future. Those lists are printed so a human can see the coverage instead of
guessing.

The textual checks search for the array name as a quoted literal after dropping
comment-only lines. A mention inside a comment or a docstring therefore counts as
"present" — deliberately: this is a reminder for the common case, and the
structural checks above are the real gates.

Usage
-----
    python audit_schema_coverage.py --task-spec <run>/fragments/TASK-SPEC.md
    python audit_schema_coverage.py --run-dir <run>          # finds TASK-SPEC.md
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))

from required_fields import ARRAY_KINDS  # noqa: E402

# 模板里出现但不是记录数组的键（`metadata` 是片头信息）。
NON_ARRAY_TEMPLATE_KEYS = {"metadata"}

# 这些脚本按类型名取数据，用「带引号的字面量」做代理判断。
TEXTUAL_CONSUMERS = {
    "check_fragment.py": "分片门禁",
    "build_dashboard.py": "网页渲染器",
    "export_ai_context.py": "AI 文本资料库",
}

KEY_IN_TEMPLATE = re.compile(r'^  "([a-z_]+)":', re.MULTILINE)


def template_keys(task_spec: Path) -> list[str] | None:
    """TASK-SPEC 的模板块里声明的顶层键；找不到模板块返回 None。

    模板块是含 `"metadata":` 与 `"evidence":` 的那个围栏代码块——按内容找，
    不按行号，因为这份文档由 `refresh_task_spec.py` 局部重写、行号会漂。
    """
    if not task_spec.is_file():
        return None
    text = task_spec.read_text(encoding="utf-8")
    for block in re.findall(r"```[a-z]*\n(.*?)```", text, re.DOTALL):
        if '"metadata"' in block and '"evidence"' in block:
            return KEY_IN_TEMPLATE.findall(block)
    return None


def array_literal_in(path: Path) -> list[str]:
    """`path` 里引用过的数组名（忽略纯注释行）。

    两种写法都要认，否则会报假阴性：带引号的字面量（`frag.get("character_traits")`、
    `graph.get('x', [])`）与**点号访问**（`graph.character_traits`）。第一版只查带引号的，
    于是 `build_dashboard.py` 里明明有 `graph.character_traits||[]` 却被报成「未出现」——
    报告里的假阴性和没有报告是一回事，这正是本脚本要消灭的那类盲区。
    """
    if not path.is_file():
        return []
    lines = [
        line for line in path.read_text(encoding="utf-8").splitlines()
        if not line.lstrip().startswith("#")
    ]
    text = "\n".join(lines)
    found = []
    for name in ARRAY_KINDS:
        if f'"{name}"' in text or f"'{name}'" in text or re.search(rf"\.{name}\b", text):
            found.append(name)
    return found


def facts_arrays(path: Path) -> list[str] | None:
    """`build_results_facts.ARRAYS` 的内容。"""
    if not path.is_file():
        return None
    text = path.read_text(encoding="utf-8")
    match = re.search(r"^ARRAYS = \((.*?)^\)", text, re.DOTALL | re.MULTILINE)
    if not match:
        return None
    return re.findall(r'"([a-z_]+)"', match.group(1))


def asof_arrays(path: Path) -> list[str] | None:
    """`audit_asof_prose.ARRAYS` 的内容（它前面还有 PROSE_FIELDS，所以锚定到 ARRAYS）。"""
    if not path.is_file():
        return None
    text = path.read_text(encoding="utf-8")
    match = re.search(r"^ARRAYS = \((.*?)^\)", text, re.DOTALL | re.MULTILINE)
    if not match:
        return None
    return re.findall(r'"([a-z_]+)"', match.group(1))


def report(title: str, lines: list[str]) -> None:
    print(title)
    for line in lines:
        print(line)
    print()


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, help="用 <run>/fragments/TASK-SPEC.md")
    parser.add_argument("--task-spec", type=Path, help="直接指定 TASK-SPEC.md")
    args = parser.parse_args()

    task_spec = args.task_spec
    if task_spec is None:
        if args.run_dir is None:
            parser.error("要么 --run-dir，要么 --task-spec")
        task_spec = args.run_dir / "fragments" / "TASK-SPEC.md"

    authority = set(ARRAY_KINDS)
    print(f"权威清单 required_fields.ARRAY_KINDS：{len(authority)} 个数组")
    print(f"  {'、'.join(sorted(authority))}")
    print()

    failures: list[str] = []

    # ---- 2. TASK-SPEC 模板 ----
    keys = template_keys(task_spec)
    if keys is None:
        report(f"[2] TASK-SPEC 模板（{task_spec}）", ["  找不到模板块（含 \"metadata\" 与 \"evidence\" 的围栏代码块）"])
        failures.append("TASK-SPEC 模板块未找到")
    else:
        declared = set(keys) - NON_ARRAY_TEMPLATE_KEYS
        missing = sorted(authority - declared)
        extra = sorted(declared - authority)
        lines = [f"  模板声明 {len(declared)} 个数组：{'、'.join(sorted(declared))}"]
        if missing:
            lines.append(f"  ✗ 模板里缺 {len(missing)} 个：{'、'.join(missing)}")
            lines.append("    → 工人拿到的 schema 里没有槽位，这一类型一条都不会被写出来"
                         "（`character_traits` 就是这样 0/734 活了六轮）。")
            failures.append(f"TASK-SPEC 模板缺 {len(missing)} 个数组：{'、'.join(missing)}")
        if extra:
            lines.append(f"  注意：模板里有 {len(extra)} 个不在权威清单里：{'、'.join(extra)}"
                         "（若不是笔误，应加进 ARRAY_KINDS，否则它没有校验也没有数字）")
        if not missing:
            lines.append("  ✓ 覆盖权威清单全部数组")
        report(f"[2] TASK-SPEC 模板（{task_spec}）", lines)

    # ---- 3. FACTS 数字表 ----
    facts = facts_arrays(SCRIPTS / "build_results_facts.py")
    if facts is None:
        failures.append("读不到 build_results_facts.ARRAYS")
    else:
        declared = set(facts)
        missing = sorted(authority - declared)
        extra = sorted(declared - authority)
        lines = [f"  声明 {len(declared)} 个数组"]
        if missing:
            lines.append(f"  ✗ 缺 {len(missing)} 个：{'、'.join(missing)}"
                         " → 它们的「0 条」在 RESULTS.md 里无处显形")
            failures.append(f"build_results_facts.ARRAYS 缺 {len(missing)} 个：{'、'.join(missing)}")
        if extra:
            lines.append(f"  ✗ 多 {len(extra)} 个：{'、'.join(extra)}")
            failures.append(f"build_results_facts.ARRAYS 多 {len(extra)} 个：{'、'.join(extra)}")
        if not missing and not extra:
            lines.append("  ✓ 与权威清单逐项一致")
        report("[3] FACTS 数字表（build_results_facts.ARRAYS）", lines)

    # ---- 4. 分片门禁 ----
    seen = set(array_literal_in(SCRIPTS / "check_fragment.py"))
    missing = sorted(authority - seen)
    lines = [f"  认得 {len(seen)} 个数组"]
    if missing:
        lines.append(f"  ✗ 不认识 {len(missing)} 个：{'、'.join(missing)}"
                     " → 分片层静默放行，问题推到合并之后")
        failures.append(f"check_fragment.py 不认识 {len(missing)} 个：{'、'.join(missing)}")
    else:
        lines.append("  ✓ 覆盖权威清单全部数组")
    report("[4] 分片门禁（check_fragment.py）", lines)

    # ---- 5. 渲染器（报告，不失败）----
    lines = []
    for name, label in TEXTUAL_CONSUMERS.items():
        if name == "check_fragment.py":
            continue
        present = set(array_literal_in(SCRIPTS / name))
        absent = sorted(authority - present)
        lines.append(f"  {label}（{name}）：认得 {len(present)}/{len(authority)}"
                     + (f"，未出现：{'、'.join(absent)}" if absent else "，全部出现"))
    lines.append("  未出现不等于缺陷（不是每个数组都有面板，`evidence` 就没有），"
                 "但新增类型时值得看一眼是不是漏接了。")
    report("[5] 渲染器（报告项）", lines)

    # ---- 6. as-of 散文审计（报告，不失败）----
    asof = asof_arrays(SCRIPTS / "audit_asof_prose.py")
    if asof is None:
        report("[6] as-of 散文审计（audit_asof_prose.ARRAYS）", ["  读不到 ARRAYS"])
    else:
        covered = set(asof)
        absent = sorted(authority - covered)
        lines = [f"  扫描 {len(covered)} 个数组：{'、'.join(sorted(covered))}"]
        lines.append(f"  未扫描：{'、'.join(absent) if absent else '（无）'}")
        lines.append("  判据是「这个数组里有没有会点名未来的散文」。带 `description` /"
                     " `reason` / `statement` / `notes` 这类字段的类型应尽量覆盖——"
                     "`character_traits.statement` 就是 2026-09-14 补进去的。")
        report("[6] as-of 散文审计（报告项）", lines)

    if failures:
        print(f"FAIL：{len(failures)} 处不一致")
        for item in failures:
            print(f"  - {item}")
        return 1
    print("PASS：模板 / 数字表 / 分片门禁三处与权威清单一致。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
