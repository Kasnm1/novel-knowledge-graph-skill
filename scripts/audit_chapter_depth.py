#!/usr/bin/env python3
"""Measure how deeply each chapter was audited, and list the data defects that follow.

`validate_graph.py` answers "is this graph well-formed". It cannot answer "was
chapter 412 actually read closely", because a chapter that yielded one event and
a chapter that was skimmed look the same to a structural check. This report
answers the second question with deterministic proxies, so a backfill can be
aimed at the chapters that need it instead of re-reading the whole book:

- per-chapter record density (events, state changes, relation changes, traits);
- recall gaps: an entity named in the chapter summary — or, when prepared chapter
  text is supplied, named repeatedly in the chapter itself — that has no record
  of any kind in that chapter;
- audit-card completeness for protocol-2 chapters;
- run-wide defects: non-canonical vocabularies, level states recorded on an entity
  type their axis does not govern, near-duplicate level axes, mixed state value
  shapes, notes packed into labels, unclosed lifecycles, missing categories and
  hierarchy, core characters with no speech trait, missing story arcs.

Every number is an audit indicator, not a truth probability. Read-only.
"""
from __future__ import annotations

import argparse
import collections
import json
import re
import statistics
from pathlib import Path
from typing import Any

from chapter_audit import AUDIT_ITEMS, SENTENCE_END
from event_types import RECOMMENDED_EVENT_TYPES, canonical_event_type
from relation_types import RELATION_GROUPS, RELATION_TYPE_ALIASES, canonical_relation_type


def recs(graph: dict, key: str) -> list[dict]:
    value = graph.get(key)
    return [r for r in value if isinstance(r, dict)] if isinstance(value, list) else []


def chapter_texts(index_path: Path | None) -> dict[int, str]:
    if not index_path or not index_path.exists():
        return {}
    out: dict[int, str] = {}
    for line in index_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        path = Path(row.get("text_path") or "")
        if not path.is_absolute():
            path = index_path.parent / path
        if path.exists():
            out[int(row["chapter"])] = path.read_text(encoding="utf-8")
    return out


def touched_by_chapter(graph: dict) -> dict[int, set[str]]:
    """Entity IDs that carry any record in each chapter."""
    touched: dict[int, set[str]] = collections.defaultdict(set)
    for ev in recs(graph, "events"):
        touched[ev.get("chapter")].update(ev.get("participant_ids") or [])
        if ev.get("location_id"):
            touched[ev.get("chapter")].add(ev["location_id"])
    for sc in recs(graph, "state_changes"):
        touched[sc.get("chapter")].add(sc.get("entity_id"))
    for rel in recs(graph, "relations"):
        for ch in {rel.get("valid_from"), rel.get("valid_to"),
                   *(o.get("chapter") for o in rel.get("observations") or [] if isinstance(o, dict))}:
            if ch is not None:
                touched[ch].update({rel.get("source_id"), rel.get("target_id")})
    for tr in recs(graph, "character_traits"):
        touched[tr.get("chapter")].add(tr.get("entity_id"))
    for act in recs(graph, "intimate_acts"):
        touched[act.get("chapter")].update(
            (act.get("initiator_ids") or []) + (act.get("recipient_ids") or []) + (act.get("observer_ids") or []))
    for ir in recs(graph, "item_roles"):
        touched[ir.get("valid_from")].update({ir.get("item_id"), ir.get("entity_id")})
    for cs in recs(graph, "chapter_summaries"):
        for row in cs.get("presence") or []:
            if isinstance(row, dict):
                touched[cs.get("chapter")].add(row.get("entity_id"))
        touched[cs.get("chapter")].update(cs.get("notable_character_ids") or [])
    return touched


def name_forms(entity: dict) -> list[str]:
    forms = [entity.get("name") or ""] + list(entity.get("aliases") or [])
    return [f for f in forms if isinstance(f, str) and len(f) >= 2]


def per_chapter(graph: dict, texts: dict[int, str], min_text_hits: int) -> list[dict[str, Any]]:
    meta = graph.get("metadata") or {}
    chapters = meta.get("analyzed_chapters") or list(
        range(int(meta.get("chapter_start") or 1), int(meta.get("chapter_end") or 0) + 1))
    non_narrative = {i.get("chapter") for i in recs(graph, "review_issues")
                     if i.get("category") == "non_narrative_chapter"}
    counters = {
        "events": collections.Counter(e.get("chapter") for e in recs(graph, "events")),
        "state_changes": collections.Counter(s.get("chapter") for s in recs(graph, "state_changes")),
        "relation_changes": collections.Counter(
            ch for r in recs(graph, "relations") for ch in (r.get("valid_from"), r.get("valid_to")) if ch is not None),
        "evidence": collections.Counter(e.get("chapter") for e in recs(graph, "evidence")),
        "traits": collections.Counter(t.get("chapter") for t in recs(graph, "character_traits")),
        "intimate_acts": collections.Counter(a.get("chapter") for a in recs(graph, "intimate_acts")),
    }
    summaries = {c.get("chapter"): c for c in recs(graph, "chapter_summaries")}
    touched = touched_by_chapter(graph)
    characters = [e for e in recs(graph, "entities") if e.get("type") == "character"]
    rows = []
    for ch in chapters:
        cs = summaries.get(ch) or {}
        summary = str(cs.get("summary") or "")
        row: dict[str, Any] = {"chapter": ch, "non_narrative": ch in non_narrative}
        row.update({k: c.get(ch, 0) for k, c in counters.items()})
        row["summary_chars"] = len(summary)
        row["summary_sentences"] = len([s for s in SENTENCE_END.split(summary) if s.strip()])
        missing_summary = sorted({
            e["id"] for e in characters
            if e.get("first_chapter", 0) <= ch and any(f in summary for f in name_forms(e))
            and e["id"] not in touched.get(ch, set())
        })
        row["summary_named_without_record"] = missing_summary
        text = texts.get(ch)
        if text is not None:
            row["text_named_without_record"] = sorted({
                e["id"] for e in characters
                if sum(text.count(f) for f in name_forms(e)) >= min_text_hits
                and e["id"] not in touched.get(ch, set())
            })
        card_keys = set((cs.get("audit") or {}).keys())
        row["audit_card"] = bool(cs.get("audit"))
        row["audit_items_missing"] = sorted(set(AUDIT_ITEMS) - card_keys) if cs.get("audit") else None
        rows.append(row)
    return rows


def run_defects(graph: dict) -> dict[str, Any]:
    entities = {e.get("id"): e for e in recs(graph, "entities")}
    rels, events, changes = recs(graph, "relations"), recs(graph, "events"), recs(graph, "state_changes")
    out: dict[str, Any] = {}

    out["relation_types"] = {
        "distinct": len({r.get("relation_type") for r in rels}),
        "aliases_used": dict(collections.Counter(r.get("relation_type") for r in rels
                                                 if r.get("relation_type") in RELATION_TYPE_ALIASES)),
        "unknown": dict(collections.Counter(r.get("relation_type") for r in rels
                                            if canonical_relation_type(r.get("relation_type")) not in RELATION_GROUPS)),
    }
    out["event_types"] = {
        "distinct": len({e.get("type") for e in events}),
        "outside_recommended": dict(collections.Counter(
            e.get("type") for e in events if canonical_event_type(e.get("type")) not in RECOMMENDED_EVENT_TYPES)),
    }

    # a level axis governs whichever entity type carries most of its states; the rest are suspects
    by_axis: dict[str, collections.Counter] = collections.defaultdict(collections.Counter)
    level_rows = [s for s in changes if s.get("facet") == "level" and s.get("target_id")]
    for s in level_rows:
        by_axis[s["target_id"]][(entities.get(s.get("entity_id")) or {}).get("type")] += 1
    misattributed = []
    for s in level_rows:
        axis = entities.get(s["target_id"]) or {}
        applies = axis.get("applies_to")
        etype = (entities.get(s.get("entity_id")) or {}).get("type")
        major = by_axis[s["target_id"]].most_common(1)[0][0]
        if (isinstance(applies, list) and etype not in applies) or (not applies and etype != major):
            misattributed.append({"id": s.get("id"), "entity": s.get("entity_id"), "entity_type": etype,
                                  "axis": s["target_id"], "axis_major_type": major, "chapter": s.get("chapter")})
    out["level_misattribution_suspects"] = misattributed

    axes = [e for e in entities.values() if e.get("type") == "level_axis"]
    dup_axes = []
    for i, a in enumerate(axes):
        for b in axes[i + 1:]:
            na, nb = str(a.get("name")), str(b.get("name"))
            if sorted(na) == sorted(nb) or (len(na) >= 3 and (na in nb or nb in na)):
                dup_axes.append([a.get("id"), na, b.get("id"), nb])
    out["near_duplicate_level_axes"] = dup_axes

    shapes = collections.Counter(type(s.get("after")).__name__ for s in changes)
    note_labels = [s.get("id") for s in changes if isinstance(s.get("after"), dict)
                   and re.search(r"[（(].{6,}[)）]", str(s["after"].get("label") or ""))]
    out["state_value_shapes"] = dict(shapes)
    out["labels_with_embedded_notes"] = {"count": len(note_labels), "sample": note_labels[:10]}
    event_like = re.compile(r"(露出|摘下|打败|击杀|发现|得知|赶到|离开|召唤|首次|当众)")
    out["identity_facet_event_like"] = [
        {"id": s.get("id"), "entity": s.get("entity_id"), "after": s.get("after")}
        for s in changes if s.get("facet") in {"identity", "possession"}
        and event_like.search(str((s.get("after") or {}).get("label") if isinstance(s.get("after"), dict) else s.get("after")))
    ][:30]

    fs, cms = recs(graph, "foreshadowing"), recs(graph, "commitments")
    out["lifecycle"] = {
        "foreshadowing_total": len(fs),
        "foreshadowing_with_payoff": sum(1 for f in fs if f.get("payoff_chapter")),
        "commitments_total": len(cms),
        "commitments_resolved": sum(1 for c in cms if c.get("resolved_chapter") or c.get("status") in
                                    {"fulfilled", "broken", "partially_fulfilled", "expired", "waived"}),
        "relations_total": len(rels),
        "relations_closed": sum(1 for r in rels if r.get("valid_to")),
        "romance_routes": dict(collections.Counter(r.get("status") for r in recs(graph, "romance_routes"))),
    }
    items = [e for e in entities.values() if e.get("type") == "item"]
    skills = [e for e in entities.values() if e.get("type") == "skill"]
    places = [e for e in entities.values() if e.get("type") == "location"]
    placed = {r.get("source_id") for r in rels if canonical_relation_type(r.get("relation_type")) in {"located_in", "part_of"}}
    out["classification"] = {
        "items_with_categories": [sum(1 for e in items if e.get("categories")), len(items)],
        "skills_with_categories": [sum(1 for e in skills if e.get("categories")), len(skills)],
        "locations_in_hierarchy": [sum(1 for e in places if e.get("id") in placed), len(places)],
    }
    part = collections.Counter(p for e in events for p in e.get("participant_ids") or [])
    core = [i for i, e in entities.items() if e.get("type") == "character" and part[i] >= 20]
    speech = {t.get("entity_id") for t in recs(graph, "character_traits") if t.get("facet") == "speech"}
    out["core_characters"] = {"count": len(core), "with_speech_trait": sum(1 for i in core if i in speech),
                              "without_speech_trait": [entities[i].get("name") for i in core if i not in speech][:40]}
    degree = collections.Counter()
    for r in rels:
        degree.update([r.get("source_id"), r.get("target_id")])
    out["isolated_entities"] = sum(1 for i in entities if degree[i] == 0)
    out["story_arcs"] = len(recs(graph, "story_arcs"))
    out["facets_structured"] = {
        "combat": sum(1 for e in events if e.get("combat")),
        "mortality": sum(1 for e in events if e.get("mortality")),
        "transaction": sum(1 for e in events if e.get("transaction")),
        "information": sum(1 for e in events if e.get("information")),
    }
    out["duplicate_entity_issues_open"] = sum(
        1 for i in recs(graph, "review_issues") if i.get("category") == "duplicate_entity" and not i.get("resolution"))
    return out


def summarize(rows: list[dict]) -> dict[str, Any]:
    story = [r for r in rows if not r["non_narrative"]]

    def dist(key: str) -> dict[str, Any]:
        vals = [r[key] for r in story]
        return {"mean": round(statistics.mean(vals), 2) if vals else 0, "max": max(vals, default=0),
                "zero_chapters": sum(1 for v in vals if v == 0)}

    gaps = sum(len(r["summary_named_without_record"]) for r in story)
    text_gaps = [len(r["text_named_without_record"]) for r in story if "text_named_without_record" in r]
    thin = [r["chapter"] for r in story if r["events"] <= 1 and r["state_changes"] == 0]
    return {
        "chapters": len(rows), "narrative_chapters": len(story),
        "events": dist("events"), "state_changes": dist("state_changes"),
        "relation_changes": dist("relation_changes"), "evidence": dist("evidence"), "traits": dist("traits"),
        "summary_chars_mean": round(statistics.mean(r["summary_chars"] for r in story), 1) if story else 0,
        "summaries_under_three_sentences": sum(1 for r in story if r["summary_sentences"] < 3),
        "summary_named_without_record": gaps,
        "text_named_without_record": sum(text_gaps) if text_gaps else None,
        "thin_chapters": {"count": len(thin), "chapters": thin},
        "audit_cards": sum(1 for r in story if r["audit_card"]),
    }


def markdown(title: str, summary: dict, defects: dict, rows: list[dict]) -> str:
    L = [f"# 逐章深度审计：{title}", "", "由 `scripts/audit_chapter_depth.py` 生成；数字是审计指标，不是真值概率。", "",
         "## 逐章密度", "", "| 指标 | 平均 | 最多 | 为 0 的正文章 |", "|---|---|---|---|"]
    for key, label in [("events", "事件"), ("state_changes", "状态变化"), ("relation_changes", "关系开始/结束"),
                       ("evidence", "证据"), ("traits", "人物特征")]:
        d = summary[key]
        L.append(f"| {label} | {d['mean']} | {d['max']} | {d['zero_chapters']} / {summary['narrative_chapters']} |")
    L += ["", f"- 梗概平均 {summary['summary_chars_mean']} 字；不足三句的章：{summary['summaries_under_three_sentences']}",
          f"- 梗概点名、但该章没有任何记录的人物：{summary['summary_named_without_record']} 次"]
    if summary["text_named_without_record"] is not None:
        L.append(f"- 正文反复出现、但该章没有任何记录的人物：{summary['text_named_without_record']} 次")
    L += [f"- 薄章（事件 ≤ 1 且无状态变化）：{summary['thin_chapters']['count']} 章",
          f"- 带审计卡的正文章：{summary['audit_cards']} / {summary['narrative_chapters']}", "", "## 数据缺陷", ""]
    lc, cl, cc = defects["lifecycle"], defects["classification"], defects["core_characters"]
    L += [
        f"- 关系类型 {defects['relation_types']['distinct']} 种；使用别名 {sum(defects['relation_types']['aliases_used'].values())} 条；"
        f"不在规范集合的 {sum(defects['relation_types']['unknown'].values())} 条",
        f"- 事件类型 {defects['event_types']['distinct']} 种；推荐集合外 {sum(defects['event_types']['outside_recommended'].values())} 条",
        f"- 疑似记错对象的等级记录：{len(defects['level_misattribution_suspects'])} 条",
        f"- 疑似重复的等级轴：{len(defects['near_duplicate_level_axes'])} 对 "
        + "；".join(f"{a[1]} / {a[3]}" for a in defects["near_duplicate_level_axes"]),
        f"- 状态值形态：{defects['state_value_shapes']}；label 夹带括号说明：{defects['labels_with_embedded_notes']['count']} 条",
        f"- 身份/持有物 facet 写成事件的疑似记录：{len(defects['identity_facet_event_like'])} 条（抽样上限 30）",
        f"- 伏笔回收 {lc['foreshadowing_with_payoff']} / {lc['foreshadowing_total']}；承诺了结 {lc['commitments_resolved']} / {lc['commitments_total']}；"
        f"关系关闭 {lc['relations_closed']} / {lc['relations_total']}",
        f"- 感情线状态：{lc['romance_routes']}",
        f"- 物品有分类 {cl['items_with_categories'][0]} / {cl['items_with_categories'][1]}；技能有分类 "
        f"{cl['skills_with_categories'][0]} / {cl['skills_with_categories'][1]}；地点进入层级 "
        f"{cl['locations_in_hierarchy'][0]} / {cl['locations_in_hierarchy'][1]}",
        f"- 核心人物（参与 ≥ 20 事件）{cc['count']} 位，有说话特征 {cc['with_speech_trait']} 位",
        f"- 没有任何关系的实体：{defects['isolated_entities']}；故事弧：{defects['story_arcs']}",
        f"- 结构化事件面向：{defects['facets_structured']}；未处理的重复实体警告：{defects['duplicate_entity_issues_open']}",
        "", "## 最需要补审的章（按召回缺口排序，前 30）", "", "| 章 | 事件 | 状态变化 | 梗概点名却无记录 |", "|---|---|---|---|",
    ]
    worst = sorted((r for r in rows if not r["non_narrative"]),
                   key=lambda r: (-len(r["summary_named_without_record"]), r["events"]))[:30]
    for r in worst:
        L.append(f"| {r['chapter']} | {r['events']} | {r['state_changes']} | {len(r['summary_named_without_record'])} |")
    return "\n".join(L) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--graph", required=True, type=Path)
    ap.add_argument("--chapters-jsonl", type=Path, help="prepared chapter index; enables text recall checks")
    ap.add_argument("--min-text-hits", type=int, default=3, help="name occurrences that count as 'in the chapter'")
    ap.add_argument("--json", type=Path)
    ap.add_argument("--markdown", type=Path)
    args = ap.parse_args()

    data = json.loads(args.graph.read_text(encoding="utf-8"))
    graph = data.get("graph", data) if isinstance(data.get("graph"), dict) else data
    rows = per_chapter(graph, chapter_texts(args.chapters_jsonl), args.min_text_hits)
    summary, defects = summarize(rows), run_defects(graph)
    title = (graph.get("metadata") or {}).get("title") or args.graph.stem
    if args.json:
        args.json.write_text(json.dumps({"summary": summary, "defects": defects, "chapters": rows},
                                        ensure_ascii=False, indent=1), encoding="utf-8")
    report = markdown(title, summary, defects, rows)
    if args.markdown:
        args.markdown.write_text(report, encoding="utf-8")
    print(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
