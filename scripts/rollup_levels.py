#!/usr/bin/env python3
"""Derive level ladders from a graph and audit them against the prepared source.

Two jobs, both read-only with respect to graph.json:

1. Rollup — for every (entity, level_axis) pair, replay the ``level`` state
   changes in chapter order and emit the ordered ladder plus the value in force
   as of the last analyzed chapter.
2. Audit — for every chapter, find level statements that name a tracked
   character and sort them into three buckets:
     * recorded     — this chapter already carries a level change for them
     * restatement  — the number mentioned was already established earlier
     * candidate    — the number was never recorded for them, so either the
                      graph is missing an upgrade or the line is a plan/estimate

   The candidate bucket is the actionable one: it is what catches "the
   protagonist levelled up and nobody wrote it down".

The script never writes graph.json. Merge output stays the single source of
truth; this only produces a review artifact.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path


DIGITS = {"零": 0, "一": 1, "二": 2, "两": 2, "三": 3, "四": 4, "五": 5,
          "六": 6, "七": 7, "八": 8, "九": 9}
UNITS = {"十": 10, "百": 100, "千": 1000, "万": 10000}

# 等级计数单位。刻意不含「层」：中文里「一层灰尘」「一层光芒」是量词，放进来
# 会把候选表淹没。「重」只通过「第 N 重」的专门模式识别，用于功法／境界类等级轴。
LEVEL_UNIT = r"(?:级|阶|品|星)"

CN_NUM = r"[零一二两三四五六七八九十百千万]+"
AR_NUM = r"\d+"

LEVEL_PATTERNS = [
    # 魂力十七级 / 魂力提升到了十七级 / 三十三级魂师
    re.compile(rf"(?P<label>[\u4e00-\u9fa5]{{0,6}}?)(?P<num>{AR_NUM}|{CN_NUM}){LEVEL_UNIT}"),
    # 一级魂导师 / 三级魂导师
    re.compile(rf"(?P<num>{AR_NUM}|{CN_NUM}){LEVEL_UNIT}(?P<label>[\u4e00-\u9fa5]{{1,6}})"),
    # 第二重 / 四重境界 —— 功法与境界类等级轴
    re.compile(rf"第(?P<num>{AR_NUM}|{CN_NUM})重"),
    re.compile(rf"(?P<num>{AR_NUM}|{CN_NUM})重境界"),
]

# 等级语境词：只有和「数字＋单位」同时出现，才视为等级候选句。
LEVEL_CUES = (
    "魂力", "修为", "等级", "魂师", "魂导师", "魂士", "大魂师", "魂尊",
    "魂宗", "魂王", "魂帝", "魂圣", "魂斗罗", "封号斗罗", "魂环", "武魂",
    "境界", "瓶颈", "突破", "晋级", "晋阶", "晋升", "提升", "达到", "级",
)

# 通用称谓别名：这些词在任何一句里都可能作为普通名词出现
# （「大师」会命中「大师兄」，「公爵」会命中「公爵府」），不能用来锁定人物。
GENERIC_LABELS = {
    "大师", "老师", "学长", "学姐", "师兄", "师姐", "师弟", "师妹",
    "院长", "主任", "公爵", "亲王", "殿下", "少爷", "小姐", "大人",
    "前辈", "老者", "少女", "少年", "小子", "同学", "班长", "首领",
}

# 规划／推测语气：命中这些词的候选句多半是「打算升级」而非「已经升级」，
# 单独标记出来，方便人工一眼跳过。
PLAN_CUES = (
    "有信心", "计划", "争取", "希望", "准备", "将要", "即将", "以后",
    "未来", "等到", "如果", "若是", "恐怕", "说不定", "至少也", "估计",
    "大概", "明天", "想要",
)

NAME_PROXIMITY = 14
NUMERAL_IN_TEXT = re.compile(rf"(?:{AR_NUM}|{CN_NUM})")


def cn_to_int(text: str) -> int | None:
    """Parse a Chinese numeral up to 万, e.g. 十七 -> 17, 二十 -> 20."""
    if not text:
        return None
    if text.isdigit():
        return int(text)
    total = 0
    section = 0
    number = 0
    for char in text:
        if char in DIGITS:
            number = DIGITS[char]
        elif char in UNITS:
            unit = UNITS[char]
            if unit == 10000:
                section = (section + (number or 1)) * unit
                total += section
                section = 0
            else:
                section += (number or 1) * unit
            number = 0
        else:
            return None
    return total + section + number


def as_list(value) -> list:
    """Treat a missing, null, or non-list field as an empty list instead of crashing."""
    return value if isinstance(value, list) else []


def as_int(value) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    if isinstance(value, dict):
        inner = value.get("value")
        if isinstance(inner, (int, float)) and not isinstance(inner, bool):
            return int(inner)
        return scrape_label_level(value.get("label"))
    if isinstance(value, str):
        parsed = cn_to_int(value.strip())
        if parsed is not None:
            return parsed
        return scrape_label_level(value)
    return None


# 标签里真正的等级数字必须紧跟等级单位。「两环大魂师」里的「两」是魂环个数、
# 「唯一魂帝」里的「一」是「唯一」、「千年魂环」里的「千」是年份——把它们读成
# 等级会凭空造出 2 / 1 / 1000 这种数值，在阶梯上表现为假回退。
LABEL_LEVEL_NUM = re.compile(rf"(?:{AR_NUM}|{CN_NUM})(?={LEVEL_UNIT})")


def scrape_label_level(label) -> int | None:
    """从标签措辞里取等级数字，仅接受「数字＋等级单位」的写法。

    「三十级以上（魂尊）」→ 30；「四环魂宗（两黄两紫）」→ None（只有环数）；
    「魂帝（唯一魂帝）」→ None；「吸收千年魂环后成为魂尊」→ None。
    """
    if not isinstance(label, str):
        return None
    found = LABEL_LEVEL_NUM.search(label)
    return cn_to_int(found.group(0)) if found else None


def level_label(value) -> str:
    if value is None or value == "":
        return "无"
    if isinstance(value, bool):
        return "是" if value else "否"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, dict):
        label = "" if value.get("label") in (None, "") else str(value["label"])
        number = "" if value.get("value") in (None, "") else str(value["value"])
        if label and number and label != number:
            return f"{label}（{number}）"
        return label or number or "无"
    return str(value)


def load_chapters(chapters_dir: Path, chapters_jsonl: Path | None) -> list[dict]:
    records: list[dict] = []
    if chapters_jsonl and chapters_jsonl.exists():
        for line in chapters_jsonl.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line:
                records.append(json.loads(line))
    if records:
        return records
    for path in sorted(chapters_dir.glob("*.txt")):
        match = re.search(r"(\d+)", path.stem)
        if match:
            records.append({"chapter": int(match.group(1)), "text_path": str(path)})
    return records


def chapter_text_path(record: dict, chapters_dir: Path | None) -> Path | None:
    path = Path(str(record.get("text_path", "")))
    if path.exists():
        return path
    if chapters_dir:
        fallback = chapters_dir / f"{int(record['chapter']):03d}.txt"
        if fallback.exists():
            return fallback
    return None


def scan_mentions(text: str, tracked: dict[str, str]) -> list[dict]:
    """Attribute each level token to the tracked character standing nearest to it.

    Attribution is token-centric rather than line-centric on purpose. A line like
    "周漪乃是六十级以上的魂帝……想要拒绝霍雨浩这十一级魂师" carries two level
    numbers for two different people; attributing the whole line to everyone it
    names would invent upgrades that never happened. Each number goes to its own
    nearest character, and only if that character is within NAME_PROXIMITY.
    """
    hits: list[dict] = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if not any(cue in stripped for cue in LEVEL_CUES):
            continue
        plan_like = any(cue in stripped for cue in PLAN_CUES)
        for pattern in LEVEL_PATTERNS:
            for match in pattern.finditer(stripped):
                number = cn_to_int(match.group("num"))
                if number is None:
                    continue
                start, end = match.span()
                best: tuple[int, int, str] | None = None
                for name, entity_id in tracked.items():
                    index = stripped.find(name)
                    while index >= 0:
                        distance = min(abs(index - start), abs(index + len(name) - end))
                        if distance <= NAME_PROXIMITY:
                            candidate = (distance, -len(name), entity_id)
                            if best is None or candidate < best:
                                best = candidate
                        index = stripped.find(name, index + 1)
                if best is None:
                    continue
                hits.append({
                    "line": stripped,
                    "entity_id": best[2],
                    "number": number,
                    "is_plan": plan_like,
                })
    return hits


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--graph", required=True, type=Path)
    parser.add_argument("--chapters", type=Path, help="Directory of prepared chapter .txt files")
    parser.add_argument("--chapters-jsonl", type=Path, help="Prepared chapters.jsonl")
    parser.add_argument("--output", type=Path, help="Where to write the rollup JSON report")
    parser.add_argument("--max-samples", type=int, default=3, help="Sample lines to keep per flagged entry")
    parser.add_argument("--strict", action="store_true",
                        help="Exit non-zero if any ladder self-check reports a hit")
    parser.add_argument("--max-chapter", type=int, default=None,
                        help="Highest chapter to audit. Defaults to metadata.chapter_end; "
                             "without a bound the audit scans every prepared chapter on disk, "
                             "including chapters this graph never analyzed.")
    parser.add_argument(
        "--acknowledged", type=Path, default=None,
        help="已人工判定的命中清单（JSON）。命中的项照旧列出，但不计入 --strict 失败；"
             "未列入清单的新命中仍然非零退出。见 references/known-gaps.md 的 A2："
             "「命中不是错误，是要人读一遍」——没有确认机制的门禁不可用，人会学会忽略它。",
    )
    args = parser.parse_args()

    graph = json.loads(args.graph.resolve().read_text(encoding="utf-8"))
    entities = {e.get("id"): e for e in graph.get("entities", []) if isinstance(e, dict)}
    axes = {i: e for i, e in entities.items() if e.get("type") == "level_axis"}

    # ---- 0. 确认清单 ------------------------------------------------------
    ack_doc: dict = {}
    ack_sha = None
    if args.acknowledged and args.acknowledged.exists():
        raw = args.acknowledged.read_bytes()
        ack_sha = hashlib.sha256(raw).hexdigest()
        try:
            ack_doc = json.loads(raw.decode("utf-8"))
        except json.JSONDecodeError as exc:
            print(f"警告：确认清单不是合法 JSON（{exc}），按空清单继续", file=sys.stderr)
            ack_doc = {}

    def ack_keys(section: str, check: str) -> dict[str, dict]:
        block = (ack_doc.get(section) or {}).get(check) or []
        out: dict[str, dict] = {}
        for item in block:
            if isinstance(item, dict) and isinstance(item.get("key"), str):
                out[item["key"]] = item
        return out

    # ---- 1. rollup --------------------------------------------------------
    ladders: dict[tuple[str, str], dict] = {}
    for change in graph.get("state_changes", []):
        if not isinstance(change, dict) or change.get("facet") != "level":
            continue
        entity_id, axis_id = change.get("entity_id"), change.get("target_id")
        key = (entity_id, axis_id or "facet:level")
        ladder = ladders.setdefault(key, {
            "entity_id": entity_id,
            "entity_name": (entities.get(entity_id) or {}).get("name", entity_id),
            "axis_id": axis_id,
            "axis_name": (axes.get(axis_id) or {}).get("name", axis_id or "等级"),
            "steps": [],
        })
        ladder["steps"].append({
            "chapter": change.get("chapter"),
            "action": change.get("action"),
            "before": level_label(change.get("before")),
            "after": level_label(change.get("after")),
            "before_value": as_int(change.get("before")),
            "after_value": as_int(change.get("after")),
            "confidence": change.get("confidence"),
            "reason": change.get("reason"),
            "evidence_ids": change.get("evidence_ids") or [],
            "id": change.get("id"),
        })

    rollup: list[dict] = []
    for ladder in ladders.values():
        ladder["steps"].sort(key=lambda s: (s["chapter"] or 0, s["id"] or ""))
        numbers = [s["after_value"] for s in ladder["steps"] if s["after_value"] is not None]
        ladder["current"] = ladder["steps"][-1]["after"] if ladder["steps"] else None
        ladder["current_value"] = numbers[-1] if numbers else None
        ladder["step_count"] = len(ladder["steps"])
        ladder["monotonic_nondecreasing"] = all(b <= a for b, a in zip(numbers, numbers[1:]))
        ladder["regressions"] = [
            {"chapter": s["chapter"], "before": s["before"], "after": s["after"]}
            for s in ladder["steps"]
            if s["before_value"] is not None and s["after_value"] is not None
            and s["after_value"] < s["before_value"]
        ]
        rollup.append(ladder)
    rollup.sort(key=lambda item: (item["entity_name"], item["axis_name"]))

    # ---- 1b. ladder self-checks -------------------------------------------
    # 每个等级轴的档位名称 -> 所属轴。用于「这个词其实是另一个轴的档位」的判定。
    tier_owner: dict[str, str] = {}
    for axis_id, axis in axes.items():
        for tier in as_list((axis.get("attributes") or {}).get("档位")):
            if isinstance(tier, dict) and tier.get("名称"):
                tier_owner.setdefault(str(tier["名称"]), axis_id)

    def raw_label(value) -> str:
        """标签原文；只取 label，不取 value——「5」不能拿来判定跨轴。"""
        if isinstance(value, dict):
            inner = value.get("label")
            return "" if inner in (None, "") else str(inner)
        return "" if value is None else str(value)

    chain_breaks: list[dict] = []
    for ladder in rollup:
        for prev, cur in zip(ladder["steps"], ladder["steps"][1:]):
            if prev["after_value"] is None or cur["before_value"] is None:
                continue
            if prev["after_value"] != cur["before_value"]:
                chain_breaks.append({
                    "key": f"{ladder['entity_id']}|{ladder['axis_id']}|{cur['id']}",
                    "entity_id": ladder["entity_id"],
                    "entity_name": ladder["entity_name"],
                    "axis_id": ladder["axis_id"],
                    "axis_name": ladder["axis_name"],
                    "previous": {"chapter": prev["chapter"], "after": prev["after"],
                                 "after_value": prev["after_value"], "id": prev["id"]},
                    "current": {"chapter": cur["chapter"], "before": cur["before"],
                                "before_value": cur["before_value"], "id": cur["id"]},
                    "gap": cur["before_value"] - prev["after_value"],
                })

    cross_axis_labels: list[dict] = []
    action_value_conflicts: list[dict] = []
    UP_ACTIONS = {"upgraded", "gained", "increased", "advanced"}
    DOWN_ACTIONS = {"lost", "decreased", "regressed", "dropped"}
    for change in graph.get("state_changes", []):
        if not isinstance(change, dict) or change.get("facet") != "level":
            continue
        axis_id = change.get("target_id")
        entity_id = change.get("entity_id")
        for side in ("before", "after"):
            text = raw_label(change.get(side))
            if not text:
                continue
            owner = tier_owner.get(text)
            if owner is not None and owner != axis_id:
                cross_axis_labels.append({
                    "key": f"{change.get('id')}|{side}",
                    "chapter": change.get("chapter"),
                    "entity_id": entity_id,
                    "entity_name": (entities.get(entity_id) or {}).get("name", entity_id),
                    "axis_id": axis_id,
                    "axis_name": (axes.get(axis_id) or {}).get("name", axis_id or "等级"),
                    "side": side,
                    "label": text,
                    "label_axis_id": owner,
                    "label_axis_name": (axes.get(owner) or {}).get("name", owner),
                    "record_id": change.get("id"),
                })
        before_value = as_int(change.get("before"))
        after_value = as_int(change.get("after"))
        action = change.get("action")
        if before_value is None or after_value is None or not isinstance(action, str):
            continue
        if action in UP_ACTIONS and after_value < before_value:
            direction = "声明为提升，数值却下降"
        elif action in DOWN_ACTIONS and after_value > before_value:
            direction = "声明为下降，数值却上升"
        else:
            continue
        action_value_conflicts.append({
            "key": str(change.get("id")),
            "chapter": change.get("chapter"),
            "entity_id": entity_id,
            "entity_name": (entities.get(entity_id) or {}).get("name", entity_id),
            "axis_name": (axes.get(axis_id) or {}).get("name", axis_id or "等级"),
            "action": action,
            "before": before_value,
            "after": after_value,
            "direction": direction,
            "record_id": change.get("id"),
        })

    # 每个实体已出现过的等级数值（用于区分「重复陈述」和「候选漏记」）
    seen_values: dict[str, set[int]] = {}
    changed_pairs: set[tuple[int, str]] = set()
    for ladder in rollup:
        for step in ladder["steps"]:
            for value in (step["before_value"], step["after_value"]):
                if value is not None:
                    seen_values.setdefault(ladder["entity_id"], set()).add(value)
            if step["chapter"] is not None:
                changed_pairs.add((step["chapter"], ladder["entity_id"]))

    # ---- 2. audit ---------------------------------------------------------
    chapter_records = load_chapters(args.chapters or Path("."), args.chapters_jsonl)

    # 审计窗口必须和图谱声明的分析范围对齐。run 目录里的 chapters/ 往往是「整本书」
    # 的预处理结果（真实案例：1319 章），而图谱只分析了其中一段（1—400 章）。不设
    # 边界时，candidate_gaps 会混进从未分析过的章节——真实案例里 13 条候选有 8 条
    # 落在 401—1319 章——而且报告内容会随「磁盘上恰好有多少章」而变：图谱一个字都
    # 没改，审计结论却变了。所以这里默认按 metadata.chapter_end 截断。
    declared_end = (graph.get("metadata") or {}).get("chapter_end")
    audit_end = args.max_chapter if args.max_chapter is not None else declared_end
    scanned, skipped_out_of_window = len(chapter_records), 0
    if isinstance(audit_end, int):
        kept = [
            record for record in chapter_records
            if isinstance(record.get("chapter"), int) and record["chapter"] <= audit_end
        ]
        skipped_out_of_window = len(chapter_records) - len(kept)
        chapter_records = kept
    audit_window = {
        "source": "metadata.chapter_end" if args.max_chapter is None else "--max-chapter",
        "chapter_start": (graph.get("metadata") or {}).get("chapter_start"),
        "chapter_end": audit_end,
        "chapters_on_disk": scanned,
        "chapters_scanned": len(chapter_records),
        "chapters_skipped_out_of_window": skipped_out_of_window,
    }
    if skipped_out_of_window:
        print(f"注：磁盘上有 {scanned} 章，按图谱范围（≤{audit_end}）只审计 {len(chapter_records)} 章，"
              f"跳过 {skipped_out_of_window} 章从未分析过的章节。", file=sys.stderr)

    tracked: dict[str, str] = {}
    for entity in graph.get("entities", []):
        if not isinstance(entity, dict) or entity.get("type") != "character":
            continue
        for raw in [entity.get("name"), *as_list(entity.get("aliases"))]:
            label = str(raw or "").strip()
            if len(label) >= 2 and label not in GENERIC_LABELS:
                tracked.setdefault(label, entity.get("id"))

    recorded: list[dict] = []
    restatements: list[dict] = []
    candidates: list[dict] = []
    for record in chapter_records:
        chapter = record.get("chapter")
        path = chapter_text_path(record, args.chapters)
        if path is None:
            continue
        hits = scan_mentions(path.read_text(encoding="utf-8"), tracked)
        if not hits:
            continue
        per_entity: dict[str, dict] = {}
        for hit in hits:
            entry = per_entity.setdefault(hit["entity_id"], {"lines": [], "numbers": set(), "plans": []})
            if hit["line"] not in entry["lines"]:
                entry["lines"].append(hit["line"])
            entry["numbers"].add(hit["number"])
            if hit["is_plan"] and hit["line"] not in entry["plans"]:
                entry["plans"].append(hit["line"])
        for entity_id, entry in per_entity.items():
            known = seen_values.get(entity_id, set())
            payload = {
                "chapter": chapter,
                "entity_id": entity_id,
                "entity_name": (entities.get(entity_id) or {}).get("name", entity_id),
                "numbers": sorted(entry["numbers"]),
                "unknown_numbers": sorted(number for number in entry["numbers"] if number not in known),
                "hit_count": len(entry["lines"]),
                "samples": entry["lines"][: args.max_samples],
            }
            if (chapter, entity_id) in changed_pairs:
                recorded.append(payload)
            elif payload["unknown_numbers"]:
                payload["plan_like"] = bool(entry["plans"])
                candidates.append(payload)
            else:
                restatements.append(payload)

    changed_only = sorted(
        {c for c, _ in changed_pairs if c is not None} - {r["chapter"] for r in recorded}
    )
    unbacked = [
        {"chapter": chapter,
         "entities": sorted({
             (entities.get(e) or {}).get("name", e)
             for c, e in changed_pairs if c == chapter
         })}
        for chapter in changed_only
    ]

    # ---- 3. 把已确认的命中从门禁里摘出来 --------------------------------
    def split(items: list[dict], check: str) -> tuple[list[dict], list[dict]]:
        acked = ack_keys("level_ladder_checks", check)
        known = [i for i in items if i.get("key") in acked]
        fresh = [i for i in items if i.get("key") not in acked]
        for item in known:
            entry = acked[item["key"]]
            item["acknowledged"] = True
            item["acknowledged_reason"] = entry.get("reason")
            item["acknowledged_review_issue"] = entry.get("review_issue")
        for item in fresh:
            item["acknowledged"] = False
        return known, fresh

    cb_known, cb_fresh = split(chain_breaks, "chain_breaks")
    ca_known, ca_fresh = split(cross_axis_labels, "cross_axis_labels")
    av_known, av_fresh = split(action_value_conflicts, "action_value_conflicts")

    report = {
        "axes": [
            {"id": i, "name": e.get("name"),
             # Level axes may carry reader-facing Chinese attribute keys; fall
             # back so the report is not blank when 单位 replaced unit.
             "unit": (e.get("attributes") or {}).get("unit")
                     or (e.get("attributes") or {}).get("单位"),
             "first_chapter": e.get("first_chapter")}
            for i, e in sorted(axes.items())
        ],
        "ladders": rollup,
        "ladder_checks": {
            "chain_breaks": chain_breaks,
            "cross_axis_labels": cross_axis_labels,
            "action_value_conflicts": action_value_conflicts,
            "unacknowledged": {
                "chain_breaks": cb_fresh,
                "cross_axis_labels": ca_fresh,
                "action_value_conflicts": av_fresh,
            },
            "acknowledged_source": (str(args.acknowledged) if args.acknowledged else None),
            "acknowledged_sha256": ack_sha,
        },
        "audit_window": audit_window,
        "recorded_mentions": recorded,
        "restatements": restatements,
        "candidate_gaps": candidates,
        "unbacked_level_chapters": unbacked,
        "summary": {
            "axes": len(axes),
            "ladders": len(rollup),
            "level_changes": sum(item["step_count"] for item in rollup),
            "recorded_mentions": len(recorded),
            "restatements": len(restatements),
            "candidate_gaps": len(candidates),
            "candidate_gaps_plan_like": sum(1 for item in candidates if item.get("plan_like")),
            "chapters_with_unbacked_changes": len(unbacked),
            "regressions": sum(len(item["regressions"]) for item in rollup),
            "chain_breaks": len(chain_breaks),
            "cross_axis_labels": len(cross_axis_labels),
            "action_value_conflicts": len(action_value_conflicts),
            "chain_breaks_acknowledged": len(cb_known),
            "cross_axis_labels_acknowledged": len(ca_known),
            "action_value_conflicts_acknowledged": len(av_known),
            "unacknowledged_hits": len(cb_fresh) + len(ca_fresh) + len(av_fresh),
        },
    }
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report["summary"], ensure_ascii=False, indent=2))
    for item in rollup:
        chain = " → ".join(f"{s['after']}(第{s['chapter']}章)" for s in item["steps"])
        print(f"  {item['entity_name']}／{item['axis_name']}：{chain or '无记录'}")
    if candidates:
        print("\n候选漏记（原文提到该角色等级，但图谱没有对应数值）：")
        for item in candidates:
            flag = "（规划／推测语气）" if item.get("plan_like") else ""
            print(f"  第{item['chapter']}章 · {item['entity_name']}"
                  f" 未记录数值 {item['unknown_numbers']}{flag}")
            for sample in item["samples"]:
                print(f"      {sample[:100]}")
    if cb_fresh:
        print("\n阶梯自检 · 链断裂（本条 before 与上一条 after 不一致，逐章抽取看不出来）：")
        for item in cb_fresh:
            prev, cur = item["previous"], item["current"]
            print(f"  {item['entity_name']}／{item['axis_name']}："
                  f"第{prev['chapter']}章 after=「{prev['after']}」({prev['after_value']})"
                  f" → 第{cur['chapter']}章 before=「{cur['before']}」({cur['before_value']})"
                  f"　差 {item['gap']:+d}")
            print(f"      {cur['id']}")
    if ca_fresh:
        print("\n阶梯自检 · 跨轴档位标签（这个词是另一个轴的档位名，须人工判定数值取哪个口径）：")
        for item in ca_fresh:
            print(f"  第{item['chapter']}章 · {item['entity_name']} · 挂在「{item['axis_name']}」上，"
                  f"{item['side']}=「{item['label']}」，而该词是「{item['label_axis_name']}」的档位")
            print(f"      {item['record_id']}")
    if av_fresh:
        print("\n阶梯自检 · 动作与数值矛盾：")
        for item in av_fresh:
            print(f"  第{item['chapter']}章 · {item['entity_name']}／{item['axis_name']}："
                  f"{item['action']} {item['before']}→{item['after']}（{item['direction']}）")
            print(f"      {item['record_id']}")
    if cb_fresh or ca_fresh or av_fresh:
        print("\n  提示：以上三类不一定是错，但都是「规则只写在文档里、机器查不出违反」的盲区，"
              "需要人工读一遍阶梯。修法是把更正写成补充分片，不要原地改已交付分片；"
              "判定完的项请写进确认清单（--acknowledged），否则每轮都要重读一遍。")
    known_total = len(cb_known) + len(ca_known) + len(av_known)
    if known_total:
        print(f"\n  已确认命中 {known_total} 项（链断裂 {len(cb_known)}／跨轴标签 {len(ca_known)}／"
              f"动作矛盾 {len(av_known)}），已从门禁摘出，逐条理由见确认清单：")
        for check, items in (("链断裂", cb_known), ("跨轴标签", ca_known), ("动作矛盾", av_known)):
            for item in items:
                print(f"      [{check}] {item['key']}　{item.get('acknowledged_reason') or ''}")
                if item.get("acknowledged_review_issue"):
                    print(f"          见 {item['acknowledged_review_issue']}")
    return 1 if args.strict and (cb_fresh or ca_fresh or av_fresh) else 0


if __name__ == "__main__":
    raise SystemExit(main())
