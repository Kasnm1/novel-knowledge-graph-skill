"""Cross-chapter reconciliation: candidates by code, decisions by AI, corrections by code.

Chapter workers see a few chapters at a time, so beginnings are recorded and
endings are not: on the 999-chapter sample only 7 of 327 clues had a payoff and
41 of 823 relations ever closed. This module finds the places where an ending
probably exists, hands them to an AI reviewer by arc window, and turns the
reviewer's decisions into hash-guarded `corrections.jsonl` lines that
`apply_corrections.py` replays. Nothing here decides a story fact.

Candidate kinds:
  foreshadow_payoff   an open clue whose related entities act together later
  commitment_resolution  an open promise whose parties meet again later
  relation_close      an open relation whose endpoint later dies, or whose pair turns hostile
  romance_milestone   a route whose dated milestones disagree with its status or its intimate acts
  duplicate_entity    two entities of one type sharing a name or alias
  categorize          an item or skill without categories
  hierarchy           a place or organization with no parent
"""

from __future__ import annotations

import copy
import hashlib
import json
import re
from typing import Any, Iterable, Mapping

from nkg.core.records import chapter_value, records
from relation_types import relation_group

DEATH = re.compile(r"死|亡|陨落|毙|身故|丧命|断气")
DECISIONS = frozenset({"apply", "reject", "unresolved"})


def _bigrams(text: str) -> set[str]:
    text = re.sub(r"[^一-龥A-Za-z0-9]", "", text or "")
    return {text[i:i + 2] for i in range(len(text) - 1)}


def _similar(a: str, b: str) -> float:
    x, y = _bigrams(a), _bigrams(b)
    return len(x & y) / max(1, min(len(x), len(y))) if x and y else 0.0


def _label(value: Any) -> str:
    if isinstance(value, dict):
        return str(value.get("label") or value.get("value") or "")
    return str(value or "")


def reconcile_candidates(graph: Mapping[str, Any], *, window: int = 200, per_item: int = 3) -> list[dict[str, Any]]:
    events = sorted(records(graph.get("events")), key=lambda e: (e.get("chapter") or 0, str(e.get("id"))))
    entities = {e["id"]: e for e in records(graph.get("entities")) if isinstance(e.get("id"), str)}
    out: list[dict[str, Any]] = []

    def add(kind: str, target: tuple[str, str] | None, question: str, **payload: Any) -> None:
        out.append({"id": f"rcn_{kind}_{sum(1 for c in out if c['kind'] == kind) + 1:04d}", "kind": kind,
                    "target": {"collection": target[0], "id": target[1]} if target else None,
                    "question": question, **payload})

    for clue in records(graph.get("foreshadowing")):
        planted = chapter_value(clue.get("planted_chapter"))
        if planted is None or chapter_value(clue.get("payoff_chapter")) is not None:
            continue
        related = set(clue.get("related_entity_ids") or [])
        text = f"{clue.get('label', '')}{clue.get('observation', '')}{clue.get('interpretation', '')}"
        scored = []
        for ev in events:
            ch = ev.get("chapter") or 0
            if not planted < ch <= planted + window or not related & set(ev.get("participant_ids") or []):
                continue
            score = _similar(text, f"{ev.get('title', '')}{ev.get('description', '')}")
            if score >= 0.15:
                scored.append((score, ev))
        if scored:
            options = [{"event_id": ev["id"], "chapter": ev.get("chapter"), "title": ev.get("title"), "score": round(s, 2)}
                       for s, ev in sorted(scored, key=lambda x: -x[0])[:per_item]]
            add("foreshadow_payoff", ("foreshadowing", clue["id"]),
                f"伏笔「{clue.get('label')}」是否在以下事件中回收？回收则给 payoff_chapter / payoff_event_id。",
                options=options)

    for c in records(graph.get("commitments")):
        created = chapter_value(c.get("created_chapter"))
        if created is None or chapter_value(c.get("resolved_chapter")) is not None:
            continue
        parties = set(c.get("promisor_ids") or []) | set(c.get("counterparty_ids") or [])
        scored = []
        for ev in events:
            ch = ev.get("chapter") or 0
            present = parties & set(ev.get("participant_ids") or [])
            if created < ch <= created + window and len(present) >= min(2, len(parties)):
                score = _similar(str(c.get("terms", "")), f"{ev.get('title', '')}{ev.get('description', '')}")
                if score >= 0.15:
                    scored.append((score, ev))
        if scored:
            add("commitment_resolution", ("commitments", c["id"]),
                f"承诺「{str(c.get('terms', ''))[:40]}」是否在以下事件中履行或违背？",
                options=[{"event_id": ev["id"], "chapter": ev.get("chapter"), "title": ev.get("title"), "score": round(s, 2)}
                         for s, ev in sorted(scored, key=lambda x: -x[0])[:per_item]])

    deaths: dict[str, int] = {}
    for sc in sorted(records(graph.get("state_changes")), key=lambda s: s.get("chapter") or 0):
        if sc.get("facet") == "health" and DEATH.search(_label(sc.get("after"))):
            deaths.setdefault(sc.get("entity_id"), sc.get("chapter"))
    for ev in events:
        mortality = ev.get("mortality") if isinstance(ev.get("mortality"), dict) else None
        for victim in (mortality or {}).get("victim_ids") or []:
            deaths.setdefault(victim, ev.get("chapter"))
    last_seen: dict[str, int] = {}
    for ev in events:
        for pid in ev.get("participant_ids") or []:
            last_seen[pid] = max(last_seen.get(pid, 0), ev.get("chapter") or 0)
    # a "death" followed by further on-page action is a temporary state or a revival, not an ending
    deaths = {eid: ch for eid, ch in deaths.items() if last_seen.get(eid, 0) <= ch + 2}
    hostile_start: dict[frozenset, int] = {}
    for rel in records(graph.get("relations")):
        if relation_group(rel.get("relation_type")) == "hostile" and chapter_value(rel.get("valid_from")) is not None:
            key = frozenset((rel.get("source_id"), rel.get("target_id")))
            hostile_start[key] = min(hostile_start.get(key, 10 ** 9), rel["valid_from"])
    for rel in records(graph.get("relations")):
        if chapter_value(rel.get("valid_to")) is not None:
            continue
        start = chapter_value(rel.get("valid_from")) or 0
        for endpoint in (rel.get("source_id"), rel.get("target_id")):
            died = deaths.get(endpoint)
            if died is not None and died > start:
                add("relation_close", ("relations", rel["id"]),
                    f"{entities.get(endpoint, {}).get('name', endpoint)} 于第 {died} 章死亡；关系 {rel.get('relation_type')} 是否就此结束？",
                    suggested={"valid_to": died, "close_reason": "death"})
                break
        else:
            turned = hostile_start.get(frozenset((rel.get("source_id"), rel.get("target_id"))))
            if relation_group(rel.get("relation_type")) in {"ally", "mentorship", "romance"} and turned and turned > start:
                add("relation_close", ("relations", rel["id"]),
                    f"双方于第 {turned} 章转为敌对；关系 {rel.get('relation_type')} 是结束，还是只记一次态度变化（stance）？",
                    suggested={"valid_to": turned, "close_reason": "turned_hostile"})

    acts: dict[frozenset, list[dict]] = {}
    for act in records(graph.get("intimate_acts")):
        people = frozenset((act.get("initiator_ids") or []) + (act.get("recipient_ids") or []))
        acts.setdefault(people, []).append(act)
    for route in records(graph.get("romance_routes")):
        pair = frozenset((route.get("protagonist_id"), route.get("character_id")))
        status = route.get("status")
        if status in {"confirmed_relationship", "spouse", "betrothed"} and chapter_value(route.get("confirmed_chapter")) is None:
            add("romance_milestone", ("romance_routes", route["id"]),
                f"感情线状态为 {status}，但没有 confirmed_chapter；确认发生在哪一章？")
        sex = [a.get("chapter") for a in acts.get(pair, []) if a.get("act_type") in {"intercourse", "oral_sex", "anal_intercourse"}]
        if sex and (chapter_value(route.get("first_sex_chapter")) is None or min(sex) < route["first_sex_chapter"]):
            add("romance_milestone", ("romance_routes", route["id"]),
                f"亲密行为显示第 {min(sex)} 章已有性行为，而 first_sex_chapter 为 {route.get('first_sex_chapter')}；是否更正？",
                suggested={"first_sex_chapter": min(sex)})

    by_name: dict[tuple[str, str], set[str]] = {}
    for entity in entities.values():
        for name in [entity.get("name"), *(entity.get("aliases") or [])]:
            if isinstance(name, str) and len(name) >= 2:
                by_name.setdefault((entity.get("type"), name), set()).add(entity["id"])
    seen_pairs: set[frozenset] = set()
    for (etype, name), ids in sorted(by_name.items(), key=lambda kv: kv[0][1]):
        if len(ids) > 1 and frozenset(ids) not in seen_pairs:
            seen_pairs.add(frozenset(ids))
            add("duplicate_entity", None, f"「{name}」同时属于 {sorted(ids)}：是同一实体（合并）还是不同实体？",
                entity_ids=sorted(ids))

    for entity in entities.values():
        if entity.get("type") in {"item", "skill"} and not entity.get("categories"):
            add("categorize", ("entities", entity["id"]), f"「{entity.get('name')}」属于哪些分类？")
    has_parent = {r.get("source_id") for r in records(graph.get("relations"))
                  if r.get("relation_type") in {"located_in", "part_of", "subgroup_of"}}
    for entity in entities.values():
        if entity.get("type") in {"location", "organization"} and entity["id"] not in has_parent:
            add("hierarchy", ("entities", entity["id"]), f"「{entity.get('name')}」的上级地点或所属势力是什么？")
    return out


def _hash(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def decisions_to_corrections(graph: Mapping[str, Any], candidates: Iterable[Mapping[str, Any]],
                             decisions: Iterable[Mapping[str, Any]], *, reviewer: str = "") -> dict[str, Any]:
    """Turn `apply` decisions into guarded replace corrections; merges become --id-map lines."""
    by_id = {c["id"]: c for c in candidates}
    work = copy.deepcopy(dict(graph))
    corrections, id_map, skipped = [], [], []
    for decision in decisions:
        cid = decision.get("candidate_id")
        candidate = by_id.get(cid)
        if candidate is None or decision.get("decision") not in DECISIONS:
            skipped.append({"candidate_id": cid, "reason": "unknown candidate or decision"})
            continue
        if decision["decision"] != "apply":
            continue
        if candidate["kind"] == "duplicate_entity":
            keep, drop = decision.get("keep"), decision.get("merge")
            if keep in candidate["entity_ids"] and drop in candidate["entity_ids"] and keep != drop:
                id_map.append(f"{drop}={keep}")
            else:
                skipped.append({"candidate_id": cid, "reason": "merge needs keep and merge ids from the candidate"})
            continue
        target = candidate["target"]
        rows = work.get(target["collection"]) or []
        record = next((r for r in rows if isinstance(r, dict) and r.get("id") == target["id"]), None)
        changes = decision.get("set")
        if record is None or not isinstance(changes, Mapping) or not changes:
            skipped.append({"candidate_id": cid, "reason": "missing record or empty 'set'"})
            continue
        for n, (path, value) in enumerate(sorted(changes.items()), 1):
            before = _hash(record)
            created = path not in record
            record[path] = copy.deepcopy(value)
            corrections.append({
                "correction_id": f"{cid}-{n}", "operation": "replace",
                "collection": target["collection"], "record_id": target["id"], "path": path, "value": value,
                "before_hash": before, "after_hash": _hash(record), **({"allow_create": True} if created else {}),
                "reason": decision.get("reason", ""), "evidence_ids": decision.get("evidence_ids", []),
                "reviewer": reviewer,
            })
    return {"corrections": corrections, "id_map": id_map, "skipped": skipped}
