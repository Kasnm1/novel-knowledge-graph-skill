#!/usr/bin/env python3
"""Generate auditable legacy-backfill candidates without inventing facts.

The output is a review queue plus a scan receipt. A run is not considered fully
scanned merely because some candidates were emitted: the receipt records the
requested/declared range, actual readable chapters, missing inputs, per-kind hit
and truncation counts, spoiler cutoff and review progress.
"""
from __future__ import annotations

import argparse
import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from controlled_vocab import category_ids
from filter_graph_asof import filter_graph

PATTERNS = {
    "commitment": re.compile(r"(答应|承诺|发誓|立誓|约定|赌约|赌一把|三年之约|一定会|必将)"),
    "secret": re.compile(r"(秘密|真相|隐瞒|身份|不能告诉|别让.*知道|瞒着|泄露)"),
    "mortality": re.compile(r"(死了|死亡|身亡|陨落|被杀|杀死|复活|重生|还魂|死而复生)"),
}
REVIEW_STATUSES = {"unresolved", "confirmed", "excluded"}


def recs(value: Any) -> list[dict[str, Any]]:
    return [x for x in value if isinstance(x, dict)] if isinstance(value, list) else []


def candidate_key(row: dict[str, Any]) -> str:
    snippet = str(row.get("snippet") or "")[:160]
    return "|".join((str(row.get("candidate_kind") or ""), str(row.get("record_id") or ""), str(row.get("chapter") or ""), snippet))


def structural_candidates(graph: dict[str, Any], relation_gap_threshold: int = 3) -> list[dict[str, Any]]:
    entities = recs(graph.get("entities")); events = recs(graph.get("events")); relations = recs(graph.get("relations")); roles = recs(graph.get("item_roles"))
    ids_by_type: dict[str, set[str]] = defaultdict(set)
    for entity in entities:
        if isinstance(entity.get("id"), str): ids_by_type[str(entity.get("type"))].add(entity["id"])
    out: list[dict[str, Any]] = []

    def add(kind, record_id, reason, chapter=None, related_ids=None):
        out.append({"candidate_kind":kind,"record_id":record_id,"chapter":chapter,"related_ids":related_ids or [],"reason":reason,"status":"unresolved"})

    for entity in entities:
        if entity.get("type") == "skill" and not category_ids(entity.get("categories")):
            add("skill_category", entity.get("id"), "技能尚无受控分类", entity.get("first_chapter"), [entity.get("id")])

    children = {r.get("source_id") for r in relations if r.get("relation_type") in {"located_in","part_of"}}
    for entity_id in ids_by_type["location"]:
        if entity_id not in children:
            add("location_hierarchy", entity_id, "地点尚无 located_in/part_of 父级；顶层地点需人工明确", related_ids=[entity_id])

    for event in events:
        if event.get("type") == "battle" and not isinstance(event.get("combat"), dict):
            add("combat_structure", event.get("id"), "battle 事件尚未结构化胜负/阵营", event.get("chapter"), list(event.get("participant_ids") or []))
        if not event.get("location_id"):
            add("event_location", event.get("id"), "事件尚无 location_id", event.get("chapter"), list(event.get("participant_ids") or []))

    for role in roles:
        if not role.get("cause_event_id"):
            add("item_role_cause", role.get("id"), "物品获得/转移尚未连接 cause_event_id", role.get("valid_from"), [role.get("item_id"), role.get("entity_id")])

    characters = ids_by_type["character"]; counts: Counter[tuple[str,str]] = Counter(); pair_events: dict[tuple[str,str],list[str]] = defaultdict(list)
    for event in events:
        people = sorted(set(event.get("participant_ids") or []) & characters) if isinstance(event.get("participant_ids"), list) else []
        for i in range(len(people)):
            for j in range(i+1, len(people)):
                key=(people[i],people[j]); counts[key]+=1
                if isinstance(event.get("id"), str): pair_events[key].append(event["id"])
    related={tuple(sorted((r.get("source_id"),r.get("target_id")))) for r in relations if r.get("source_id") in characters and r.get("target_id") in characters}
    for pair,count in counts.items():
        if count >= relation_gap_threshold and pair not in related:
            add("side_relation", ":".join(pair), f"共同事件 {count} 次但无人物关系边", related_ids=list(pair)+pair_events[pair][:10])
    return out


def scan_text_candidates(index: Path, *, chapter_start: int | None, chapter_end: int | None, cutoff: int | None, max_hits: int) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    rows: list[dict[str, Any]]=[]; declared=[]; read=[]; missing=[]; malformed=[]
    stats={kind:{"total_hits":0,"emitted":0,"truncated":0} for kind in PATTERNS}
    for line_no,line in enumerate(index.read_text(encoding="utf-8").splitlines(),1):
        if not line.strip(): continue
        try: item=json.loads(line)
        except json.JSONDecodeError as exc:
            malformed.append({"line":line_no,"error":str(exc)}); continue
        chapter=item.get("chapter")
        if not isinstance(chapter,int):
            malformed.append({"line":line_no,"error":"chapter is not an integer"}); continue
        declared.append(chapter)
        if chapter_start is not None and chapter < chapter_start: continue
        if chapter_end is not None and chapter > chapter_end: continue
        if cutoff is not None and chapter > cutoff: continue
        path=Path(item.get("text_path", ""))
        if not path.exists():
            missing.append({"chapter":chapter,"text_path":str(path),"reason":"missing"}); continue
        try: text=path.read_text(encoding="utf-8",errors="strict")
        except (OSError,UnicodeError) as exc:
            missing.append({"chapter":chapter,"text_path":str(path),"reason":str(exc)}); continue
        read.append(chapter)
        for kind,pattern in PATTERNS.items():
            matches=list(pattern.finditer(text)); stats[kind]["total_hits"] += len(matches)
            selected=matches[:max_hits]; stats[kind]["emitted"] += len(selected); stats[kind]["truncated"] += max(0,len(matches)-len(selected))
            for match in selected:
                lo=max(0,match.start()-60); hi=min(len(text),match.end()+100)
                rows.append({"candidate_kind":kind,"chapter":chapter,"record_id":None,"related_ids":[],"reason":"source_keyword_candidate","snippet":text[lo:hi].replace("\n"," "),"status":"unresolved"})
    requested_declared=[c for c in declared if (chapter_start is None or c>=chapter_start) and (chapter_end is None or c<=chapter_end) and (cutoff is None or c<=cutoff)]
    audit={
        "index":str(index),
        "declared_chapter_range":[min(declared),max(declared)] if declared else None,
        "requested_chapter_range":[min(requested_declared),max(requested_declared)] if requested_declared else None,
        "actual_read_chapter_range":[min(read),max(read)] if read else None,
        "declared_chapters_in_scope":len(set(requested_declared)),
        "actual_read_chapters":len(set(read)),
        "missing_or_unreadable":missing,
        "malformed_index_rows":malformed,
        "cutoff":cutoff,
        "per_kind":stats,
        "max_hits_per_kind_per_chapter":max_hits,
    }
    return rows,audit


def carry_review_progress(rows: list[dict[str, Any]], previous: dict[str, Any] | None) -> None:
    if not previous: return
    old={candidate_key(r):r for r in recs(previous.get("candidates"))}
    for row in rows:
        prior=old.get(candidate_key(row))
        if not prior: continue
        status=prior.get("status")
        if status in REVIEW_STATUSES: row["status"]=status
        for field in ("review_note","reviewed_by","reviewed_at","resolution_ids"):
            if field in prior: row[field]=prior[field]


def build_output(graph: dict[str, Any], *, chapters_jsonl: Path | None = None, relation_gap_threshold: int = 3, chapter_start: int | None = None, chapter_end: int | None = None, cutoff: int | None = None, max_hits: int = 20, previous: dict[str, Any] | None = None) -> dict[str, Any]:
    scoped=filter_graph(graph, cutoff, strict=True) if cutoff is not None else graph
    rows=structural_candidates(scoped,max(1,relation_gap_threshold))
    text_audit={"cutoff":cutoff,"declared_chapters_in_scope":0,"actual_read_chapters":0,"missing_or_unreadable":[],"malformed_index_rows":[],"per_kind":{}}
    if chapters_jsonl is not None:
        if not chapters_jsonl.exists(): raise FileNotFoundError(chapters_jsonl)
        text_rows,text_audit=scan_text_candidates(chapters_jsonl,chapter_start=chapter_start,chapter_end=chapter_end,cutoff=cutoff,max_hits=max_hits)
        rows.extend(text_rows)
    carry_review_progress(rows, previous)
    counts=Counter(row["candidate_kind"] for row in rows); progress=Counter(row.get("status","unresolved") for row in rows)
    audit={
        "chapter_start":chapter_start,"chapter_end":chapter_end,"cutoff":cutoff,
        "structural_candidates":sum(1 for r in rows if r.get("reason")!="source_keyword_candidate"),
        "text_scan":text_audit,
        "candidate_counts":dict(counts),
        "review_progress":{"unresolved":progress["unresolved"],"confirmed":progress["confirmed"],"excluded":progress["excluded"],"total":len(rows)},
        "complete": not text_audit.get("missing_or_unreadable") and not text_audit.get("malformed_index_rows"),
    }
    return {"candidates":rows,"counts":dict(counts),"audit":audit}


def main() -> int:
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--graph",required=True,type=Path); p.add_argument("--output",required=True,type=Path); p.add_argument("--chapters-jsonl",type=Path)
    p.add_argument("--relation-gap-threshold",type=int,default=3); p.add_argument("--chapter-start",type=int); p.add_argument("--chapter-end",type=int); p.add_argument("--cutoff",type=int)
    p.add_argument("--max-text-hits-per-kind-per-chapter",type=int,default=20); p.add_argument("--previous",type=Path,help="Prior candidate file whose review status should be carried forward")
    args=p.parse_args(); graph=json.loads(args.graph.read_text(encoding="utf-8")); previous=json.loads(args.previous.read_text(encoding="utf-8")) if args.previous else None
    result=build_output(graph,chapters_jsonl=args.chapters_jsonl,relation_gap_threshold=args.relation_gap_threshold,chapter_start=args.chapter_start,chapter_end=args.chapter_end,cutoff=args.cutoff,max_hits=max(1,args.max_text_hits_per_kind_per_chapter),previous=previous)
    args.output.parent.mkdir(parents=True,exist_ok=True); args.output.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps({"output":str(args.output),"candidates":len(result["candidates"]),"audit_complete":result["audit"]["complete"],"review_progress":result["audit"]["review_progress"]},ensure_ascii=False))
    return 0 if result["audit"]["complete"] else 2

if __name__=="__main__": raise SystemExit(main())
