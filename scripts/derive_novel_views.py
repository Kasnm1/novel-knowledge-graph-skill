#!/usr/bin/env python3
"""Derive deterministic growth/world/narrative view models from ``graph.json``.

The canonical graph remains the only story-fact source.  Everything emitted by
this module is disposable and may be rebuilt at any time.  The views are meant
for dashboards, audits, cross-book comparison and AI context selection; they
must never be merged back into the canonical graph.
"""
from __future__ import annotations

import argparse
import itertools
import json
from collections import Counter, defaultdict
from copy import deepcopy
from pathlib import Path
from typing import Any, Iterable

from controlled_vocab import LEVEL_FACET_HINTS, category_ids, resource_tag_parts
from extension_contracts import validate_graph_extensions


def records(value: object) -> list[dict[str, Any]]:
    return [item for item in value if isinstance(item, dict)] if isinstance(value, list) else []


def chapter_of(record: dict[str, Any], *fields: str) -> int | None:
    for field in fields:
        value = record.get(field)
        if isinstance(value, int) and not isinstance(value, bool):
            return value
    return None


def entity_maps(graph: dict[str, Any]) -> tuple[dict[str, dict[str, Any]], dict[str, str]]:
    entities = {e["id"]: e for e in records(graph.get("entities")) if isinstance(e.get("id"), str)}
    return entities, {eid: str(e.get("name") or eid) for eid, e in entities.items()}


def protagonist_ids(graph: dict[str, Any], explicit: Iterable[str] = ()) -> list[str]:
    result: list[str] = []

    def add(value: object) -> None:
        if isinstance(value, str) and value and value not in result:
            result.append(value)

    for value in explicit:
        add(value)
    meta = graph.get("metadata") if isinstance(graph.get("metadata"), dict) else {}
    for value in meta.get("protagonist_ids", []) if isinstance(meta.get("protagonist_ids"), list) else []:
        add(value)
    for route in records(graph.get("romance_routes")):
        add(route.get("protagonist_id"))
    for entity in records(graph.get("entities")):
        tags = entity.get("tags")
        if isinstance(tags, list) and "protagonist" in tags:
            add(entity.get("id"))
    return result


def _facet_looks_like_level(facet: object) -> bool:
    text = str(facet or "").strip().lower()
    if not text:
        return False
    return text in LEVEL_FACET_HINTS or any(hint.lower() in text for hint in LEVEL_FACET_HINTS if len(hint) >= 2)


def level_snapshot(graph: dict[str, Any], entity_id: str, chapter: int) -> dict[str, Any]:
    matching = [
        change for change in records(graph.get("state_changes"))
        if change.get("entity_id") == entity_id
        and isinstance(change.get("chapter"), int)
        and change["chapter"] <= chapter
        and _facet_looks_like_level(change.get("facet"))
    ]
    matching.sort(key=lambda c: (c.get("chapter", 0), str(c.get("id") or "")))
    latest: dict[str, Any] = {}
    for change in matching:
        end = change.get("end_chapter")
        if isinstance(end, int) and chapter > end:
            continue
        facet = str(change.get("facet"))
        latest[facet] = deepcopy(change.get("after") if "after" in change else change.get("target_id"))
    return latest


def derive_combat_records(graph: dict[str, Any], protagonists: set[str], names: dict[str, str]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for event in records(graph.get("events")):
        combat = event.get("combat")
        if not isinstance(combat, dict):
            continue
        chapter = chapter_of(event, "chapter")
        if chapter is None:
            continue
        participants = [p for p in combat.get("participants", []) if isinstance(p, dict)] if isinstance(combat.get("participants"), list) else []
        for participant in participants:
            subject = participant.get("entity_id")
            if not isinstance(subject, str) or (protagonists and subject not in protagonists):
                continue
            opponents = [
                p.get("entity_id") for p in participants
                if isinstance(p.get("entity_id"), str)
                and p.get("entity_id") != subject
                and (participant.get("side") is None or p.get("side") is None or p.get("side") != participant.get("side"))
            ]
            rows.append({
                "event_id": event.get("id"),
                "chapter": chapter,
                "protagonist_id": subject,
                "protagonist": names.get(subject, subject),
                "opponent_ids": opponents,
                "opponents": [names.get(value, value) for value in opponents],
                "result": participant.get("outcome", "uncertain"),
                "protagonist_level": level_snapshot(graph, subject, chapter),
                "opponent_levels": {value: level_snapshot(graph, value, chapter) for value in opponents},
                "location_id": event.get("location_id"),
                "location": names.get(event.get("location_id"), event.get("location_id")) if event.get("location_id") else None,
                "kind": combat.get("kind"),
                "resolution": combat.get("resolution"),
                "stake_ids": list(combat.get("stake_ids") or []) if isinstance(combat.get("stake_ids"), list) else [],
                "killed_ids": list(combat.get("killed_ids") or []) if isinstance(combat.get("killed_ids"), list) else [],
                "evidence_ids": list(event.get("evidence_ids") or []),
            })
    return sorted(rows, key=lambda r: (r["chapter"], str(r.get("event_id") or ""), r["protagonist_id"]))


def derive_resources(graph: dict[str, Any], names: dict[str, str]) -> dict[str, Any]:
    entities = {e["id"]: e for e in records(graph.get("entities")) if isinstance(e.get("id"), str)}
    events = {e["id"]: e for e in records(graph.get("events")) if isinstance(e.get("id"), str)}
    by_item: dict[str, dict[str, Any]] = {}
    for item in (e for e in entities.values() if e.get("type") == "item"):
        rarity, supply, malformed = resource_tag_parts(item.get("tags"))
        by_item[item["id"]] = {
            "item_id": item["id"], "name": names.get(item["id"], item["id"]),
            "categories": category_ids(item.get("categories")), "rarity": rarity, "supply": supply,
            "resource_tag_issues": malformed, "role_history": [], "quantity_history": [],
        }
    for role in records(graph.get("item_roles")):
        item_id = role.get("item_id")
        if item_id not in by_item:
            continue
        cause = events.get(role.get("cause_event_id"))
        location_id = cause.get("location_id") if cause else None
        by_item[item_id]["role_history"].append({
            "record_id": role.get("id"), "entity_id": role.get("entity_id"),
            "entity": names.get(role.get("entity_id"), role.get("entity_id")), "role": role.get("role"),
            "action": role.get("action"), "chapter": role.get("valid_from"), "valid_to": role.get("valid_to"),
            "cause_event_id": role.get("cause_event_id"), "location_id": location_id,
            "location": names.get(location_id, location_id) if location_id else None,
            "evidence_ids": list(role.get("evidence_ids") or []),
        })
    quantity_facets = {"inventory_quantity", "resource_quantity", "数量", "库存数量", "持有数量"}
    for change in records(graph.get("state_changes")):
        target = change.get("target_id")
        if target not in by_item or str(change.get("facet")) not in quantity_facets:
            continue
        by_item[target]["quantity_history"].append({
            "record_id": change.get("id"), "entity_id": change.get("entity_id"),
            "entity": names.get(change.get("entity_id"), change.get("entity_id")), "chapter": change.get("chapter"),
            "before": change.get("before"), "after": change.get("after"), "action": change.get("action"),
            "cause_event_id": change.get("cause_event_id"), "evidence_ids": list(change.get("evidence_ids") or []),
        })
    for item in by_item.values():
        item["role_history"].sort(key=lambda r: ((r.get("chapter") or 0), str(r.get("record_id") or "")))
        item["quantity_history"].sort(key=lambda r: ((r.get("chapter") or 0), str(r.get("record_id") or "")))
        gained = [r for r in item["role_history"] if r.get("action") == "gained"]
        item["acquisition_count"] = len(gained)
        chapters = [r.get("chapter") for r in gained if isinstance(r.get("chapter"), int)]
        item["first_acquired_chapter"] = min(chapters) if chapters else None
        item["latest_acquired_chapter"] = max(chapters) if chapters else None
        latest_by_entity: dict[str, Any] = {}
        for row in item["quantity_history"]:
            if isinstance(row.get("entity_id"), str):
                latest_by_entity[row["entity_id"]] = deepcopy(row.get("after"))
        item["current_quantities"] = latest_by_entity
    return {"items": sorted(by_item.values(), key=lambda r: (r["name"], r["item_id"]))}


def derive_world(graph: dict[str, Any], protagonists: set[str], names: dict[str, str]) -> dict[str, Any]:
    entities = records(graph.get("entities"))
    location_ids = {e.get("id") for e in entities if e.get("type") == "location" and isinstance(e.get("id"), str)}
    organization_ids = {e.get("id") for e in entities if e.get("type") == "organization" and isinstance(e.get("id"), str)}
    hierarchy: list[dict[str, Any]] = []
    controls: list[dict[str, Any]] = []
    for relation in records(graph.get("relations")):
        rtype, source, target = relation.get("relation_type"), relation.get("source_id"), relation.get("target_id")
        if rtype in {"located_in", "part_of"} and source in location_ids and target in location_ids:
            hierarchy.append({"relation_id": relation.get("id"), "child_id": source, "parent_id": target,
                              "valid_from": relation.get("valid_from"), "valid_to": relation.get("valid_to")})
        elif rtype == "controlled_by" and source in location_ids and target in organization_ids:
            controls.append({"relation_id": relation.get("id"), "location_id": source,
                             "location": names.get(source, source), "organization_id": target,
                             "organization_name": names.get(target, target), "valid_from": relation.get("valid_from"),
                             "valid_to": relation.get("valid_to"), "observations": relation.get("observations", [])})
    activity: Counter[str] = Counter()
    travel: dict[str, list[dict[str, Any]]] = {pid: [] for pid in protagonists}
    for event in records(graph.get("events")):
        location = event.get("location_id")
        if location not in location_ids:
            continue
        activity[location] += 1
        participants = set(event.get("participant_ids") or []) if isinstance(event.get("participant_ids"), list) else set()
        for pid in protagonists & participants:
            travel.setdefault(pid, []).append({"chapter": event.get("chapter"), "location_id": location,
                                               "location": names.get(location, location), "event_id": event.get("id")})
    for path in travel.values():
        path.sort(key=lambda r: ((r.get("chapter") or 0), str(r.get("event_id") or "")))
        compact: list[dict[str, Any]] = []
        previous = None
        for stop in path:
            if stop["location_id"] != previous:
                compact.append(stop)
                previous = stop["location_id"]
        path[:] = compact
    return {
        "locations": [{"id": eid, "name": names.get(eid, eid),
                       "first_chapter": next((e.get("first_chapter") for e in entities if e.get("id") == eid), None),
                       "event_count": activity[eid]} for eid in sorted(location_ids, key=lambda value: names.get(value, value))],
        "hierarchy": hierarchy, "controls": controls, "travel": travel,
        "map_mode": "topology", "coordinates_are_story_facts": False,
    }


def derive_cooccurrence(graph: dict[str, Any], protagonists: set[str], names: dict[str, str], threshold: int) -> dict[str, Any]:
    character_ids = {e.get("id") for e in records(graph.get("entities")) if e.get("type") == "character" and isinstance(e.get("id"), str)}
    counts: Counter[tuple[str, str]] = Counter()
    shared_events: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for event in records(graph.get("events")):
        participants = sorted(set(event.get("participant_ids") or []) & character_ids) if isinstance(event.get("participant_ids"), list) else []
        for left, right in itertools.combinations(participants, 2):
            key = (left, right); counts[key] += 1
            shared_events[key].append({"event_id": event.get("id"), "chapter": event.get("chapter"), "type": event.get("type")})
    related_pairs: set[tuple[str, str]] = set()
    for relation in records(graph.get("relations")):
        left, right = relation.get("source_id"), relation.get("target_id")
        if left in character_ids and right in character_ids and left != right:
            related_pairs.add(tuple(sorted((left, right))))
    pairs, gaps = [], []
    for key, count in counts.most_common():
        row = {"character_ids": list(key), "characters": [names.get(x, x) for x in key], "count": count,
               "shared_events": shared_events[key], "has_relation": key in related_pairs,
               "contains_protagonist": bool(protagonists & set(key))}
        pairs.append(row)
        if count >= threshold and key not in related_pairs and not (protagonists & set(key)):
            gaps.append(row)
    return {"pairs": pairs, "relation_gap_candidates": gaps, "threshold": threshold}


def derive_relation_timeline(graph: dict[str, Any], names: dict[str, str]) -> dict[str, Any]:
    rows = []
    for relation in records(graph.get("relations")):
        rows.append({
            "relation_id": relation.get("id"), "source_id": relation.get("source_id"),
            "source": names.get(relation.get("source_id"), relation.get("source_id")),
            "target_id": relation.get("target_id"), "target": names.get(relation.get("target_id"), relation.get("target_id")),
            "relation_type": relation.get("relation_type"), "valid_from": relation.get("valid_from"),
            "valid_to": relation.get("valid_to"), "status": relation.get("status"), "strength": relation.get("strength"),
            "observations": deepcopy(relation.get("observations") or []),
        })
    rows.sort(key=lambda r: ((r.get("valid_from") or 0), str(r.get("source") or ""), str(r.get("target") or "")))
    return {"relations": rows}


def derive_skills(graph: dict[str, Any], names: dict[str, str]) -> list[dict[str, Any]]:
    skills = {e["id"]: e for e in records(graph.get("entities")) if e.get("type") == "skill" and isinstance(e.get("id"), str)}
    user_relations: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for relation in records(graph.get("relations")):
        source, target = relation.get("source_id"), relation.get("target_id")
        if target in skills:
            user_relations[target].append({"entity_id": source, "entity": names.get(source, source),
                                           "relation_type": relation.get("relation_type"), "valid_from": relation.get("valid_from"),
                                           "valid_to": relation.get("valid_to"), "status": relation.get("status")})
        elif source in skills:
            user_relations[source].append({"entity_id": target, "entity": names.get(target, target),
                                           "relation_type": relation.get("relation_type"), "valid_from": relation.get("valid_from"),
                                           "valid_to": relation.get("valid_to"), "status": relation.get("status")})
    return [{"skill_id": sid, "name": names.get(sid, sid), "categories": category_ids(skill.get("categories")),
             "holders": sorted(user_relations[sid], key=lambda r: (str(r.get("entity") or ""), str(r.get("relation_type") or "")))}
            for sid, skill in sorted(skills.items(), key=lambda pair: names.get(pair[0], pair[0]))]


def derive_commitments(graph: dict[str, Any], names: dict[str, str]) -> list[dict[str, Any]]:
    rows = []
    for commitment in records(graph.get("commitments")):
        row = deepcopy(commitment)
        row["promisors"] = [names.get(v, v) for v in commitment.get("promisor_ids", []) if isinstance(v, str)]
        row["counterparties"] = [names.get(v, v) for v in commitment.get("counterparty_ids", []) if isinstance(v, str)]
        row["observations"] = sorted([deepcopy(o) for o in commitment.get("observations", []) if isinstance(o, dict)],
                                     key=lambda o: ((o.get("chapter") or 0), str(o.get("status") or "")))
        rows.append(row)
    return sorted(rows, key=lambda r: ((r.get("created_chapter") or 0), str(r.get("id") or "")))


def derive_favor_ledger(graph: dict[str, Any], names: dict[str, str]) -> list[dict[str, Any]]:
    rows = []
    for relation in records(graph.get("relations")):
        if relation.get("relation_type") != "owes_favor_to":
            continue
        rows.append({"relation_id": relation.get("id"), "debtor_id": relation.get("source_id"),
                     "debtor": names.get(relation.get("source_id"), relation.get("source_id")),
                     "creditor_id": relation.get("target_id"), "creditor": names.get(relation.get("target_id"), relation.get("target_id")),
                     "strength": relation.get("strength"), "valid_from": relation.get("valid_from"), "valid_to": relation.get("valid_to"),
                     "status": relation.get("status"), "observations": deepcopy(relation.get("observations") or [])})
    return sorted(rows, key=lambda r: ((r.get("valid_from") or 0), str(r.get("debtor") or "")))


def derive_knowledge(graph: dict[str, Any], names: dict[str, str]) -> dict[str, Any]:
    histories: dict[str, dict[str, list[dict[str, Any]]]] = defaultdict(lambda: defaultdict(list))
    for change in records(graph.get("state_changes")):
        facet = str(change.get("facet") or "").strip().lower()
        if facet not in {"knowledge", "知情", "秘密知情", "知道"}:
            continue
        entity_id, target_id = change.get("entity_id"), change.get("target_id")
        if isinstance(entity_id, str) and isinstance(target_id, str):
            histories[target_id][entity_id].append({"record_id": change.get("id"), "chapter": change.get("chapter"),
                                                    "action": change.get("action"), "before": change.get("before"), "after": change.get("after"),
                                                    "cause_event_id": change.get("cause_event_id"), "evidence_ids": list(change.get("evidence_ids") or [])})
    secrets = []
    for target_id, people in histories.items():
        rows = []
        for entity_id, history in people.items():
            history.sort(key=lambda r: ((r.get("chapter") or 0), str(r.get("record_id") or "")))
            rows.append({"entity_id": entity_id, "entity": names.get(entity_id, entity_id), "history": history})
        secrets.append({"secret_id": target_id, "secret": names.get(target_id, target_id), "people": rows})
    propagation = []
    for event in records(graph.get("events")):
        info = event.get("information")
        if not isinstance(info, dict):
            continue
        revealer = info.get("revealer_id")
        audiences = info.get("audience_ids") if isinstance(info.get("audience_ids"), list) else []
        secrets_ids = info.get("secret_ids") if isinstance(info.get("secret_ids"), list) else []
        for sid in secrets_ids:
            for audience in audiences:
                propagation.append({"event_id": event.get("id"), "chapter": event.get("chapter"), "secret_id": sid,
                                    "secret": names.get(sid, sid), "from_id": revealer, "from": names.get(revealer, revealer) if revealer else None,
                                    "to_id": audience, "to": names.get(audience, audience), "mode": info.get("mode")})
    return {"secrets": sorted(secrets, key=lambda r: str(r["secret"])),
            "propagation": sorted(propagation, key=lambda r: ((r.get("chapter") or 0), str(r.get("secret") or "")))}


def derive_foreshadowing(graph: dict[str, Any]) -> dict[str, Any]:
    rows = []
    for fs in records(graph.get("foreshadowing")):
        planted = fs.get("planted_chapter")
        payoff = fs.get("payoff_chapter")
        span = payoff - planted if isinstance(planted, int) and isinstance(payoff, int) else None
        rows.append({"id": fs.get("id"), "label": fs.get("label"), "status": fs.get("status"), "planted_chapter": planted,
                     "payoff_chapter": payoff, "span": span, "related_entity_ids": deepcopy(fs.get("related_entity_ids") or []),
                     "progression": deepcopy(fs.get("progression") or [])})
    return {"rows": sorted(rows, key=lambda r: ((r.get("planted_chapter") or 0), str(r.get("id") or ""))),
            "unresolved": [r for r in rows if not isinstance(r.get("payoff_chapter"), int) and r.get("status") not in {"resolved", "paid_off"}]}


def derive_levels(graph: dict[str, Any], names: dict[str, str]) -> dict[str, Any]:
    series: dict[str, dict[str, list[dict[str, Any]]]] = defaultdict(lambda: defaultdict(list))
    for change in records(graph.get("state_changes")):
        if not _facet_looks_like_level(change.get("facet")) or not isinstance(change.get("entity_id"), str):
            continue
        series[change["entity_id"]][str(change.get("facet"))].append({"chapter": change.get("chapter"), "after": deepcopy(change.get("after")),
                                                                       "before": deepcopy(change.get("before")), "action": change.get("action"),
                                                                       "record_id": change.get("id")})
    rows = []
    for entity_id, facets in series.items():
        for values in facets.values():
            values.sort(key=lambda r: ((r.get("chapter") or 0), str(r.get("record_id") or "")))
        rows.append({"entity_id": entity_id, "entity": names.get(entity_id, entity_id), "facets": facets})
    return {"series": sorted(rows, key=lambda r: str(r.get("entity") or ""))}


def derive_chapter_rhythm(graph: dict[str, Any], names: dict[str, str]) -> dict[str, Any]:
    event_counts: dict[int, Counter[str]] = defaultdict(Counter)
    for event in records(graph.get("events")):
        chapter = event.get("chapter")
        if isinstance(chapter, int):
            event_counts[chapter][str(event.get("type") or "other")] += 1
    summary_map = {s.get("chapter"): s for s in records(graph.get("chapter_summaries")) if isinstance(s.get("chapter"), int)}
    analyzed = graph.get("metadata", {}).get("analyzed_chapters", []) if isinstance(graph.get("metadata"), dict) else []
    chapters = sorted(set([c for c in analyzed if isinstance(c, int)] + list(event_counts) + list(summary_map)))
    rows = []
    for chapter in chapters:
        summary = summary_map.get(chapter, {})
        rows.append({"chapter": chapter, "events": dict(event_counts[chapter]), "event_total": sum(event_counts[chapter].values()),
                     "story_time": deepcopy(summary.get("story_time")),
                     "pov_entity_ids": deepcopy(summary.get("pov_entity_ids") or []),
                     "pov": [names.get(eid, eid) for eid in summary.get("pov_entity_ids", []) if isinstance(eid, str)],
                     "scene_count": summary.get("scene_count"), "cliffhanger_type": summary.get("cliffhanger_type"),
                     "summary": summary.get("summary")})
    return {"chapters": rows}


def derive_romance_milestones(graph: dict[str, Any], names: dict[str, str]) -> dict[str, Any]:
    routes = []
    for route in records(graph.get("romance_routes")):
        milestones = []
        for field, kind in (("first_meeting_chapter", "first_meeting"), ("ambiguity_started_chapter", "ambiguity"),
                            ("confirmed_chapter", "confirmed"), ("first_sex_chapter", "intimacy")):
            if isinstance(route.get(field), int):
                milestones.append({"chapter": route[field], "kind": kind})
        cid = route.get("character_id")
        routes.append({"route_id": route.get("id"), "protagonist_id": route.get("protagonist_id"), "character_id": cid,
                       "character": names.get(cid, cid), "status": route.get("status"), "milestones": milestones})
    return {"routes": sorted(routes, key=lambda r: ((r["milestones"][0]["chapter"] if r["milestones"] else 10**9), str(r.get("character") or "")))}


def derive_snapshot_changes(graph: dict[str, Any], names: dict[str, str]) -> dict[str, Any]:
    by_chapter: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for change in records(graph.get("state_changes")):
        chapter = change.get("chapter")
        if not isinstance(chapter, int):
            continue
        eid = change.get("entity_id")
        by_chapter[chapter].append({"record_id": change.get("id"), "entity_id": eid, "entity": names.get(eid, eid),
                                    "facet": change.get("facet"), "action": change.get("action"), "before": deepcopy(change.get("before")),
                                    "after": deepcopy(change.get("after")), "target_id": change.get("target_id")})
    return {"by_chapter": [{"chapter": chapter, "changes": rows} for chapter, rows in sorted(by_chapter.items())]}


def derive_mortality(graph: dict[str, Any], names: dict[str, str]) -> dict[str, Any]:
    entries = []
    for event in records(graph.get("events")):
        facet = event.get("mortality")
        if not isinstance(facet, dict):
            continue
        for deceased in facet.get("deceased_ids", []) if isinstance(facet.get("deceased_ids"), list) else []:
            entries.append({"event_id": event.get("id"), "chapter": event.get("chapter"), "entity_id": deceased, "entity": names.get(deceased, deceased),
                            "killer_ids": deepcopy(facet.get("killer_ids") or []), "killers": [names.get(x, x) for x in facet.get("killer_ids", []) if isinstance(x, str)],
                            "cause": facet.get("cause"), "witness_ids": deepcopy(facet.get("witness_ids") or []),
                            "revival_mechanism": facet.get("revival_mechanism"), "cost": facet.get("cost")})
    health_changes = [c for c in records(graph.get("state_changes")) if str(c.get("facet") or "").lower() in {"health", "生命", "生死", "存活状态"}]
    return {"events": sorted(entries, key=lambda r: ((r.get("chapter") or 0), str(r.get("entity") or ""))), "health_changes": health_changes}


def derive_inheritance(graph: dict[str, Any], names: dict[str, str]) -> dict[str, Any]:
    types = {"parent_of", "teacher_of", "learned", "inherited_from", "crafted_from", "derived_from"}
    rows = []
    for relation in records(graph.get("relations")):
        if relation.get("relation_type") not in types:
            continue
        rows.append({"relation_id": relation.get("id"), "source_id": relation.get("source_id"), "source": names.get(relation.get("source_id"), relation.get("source_id")),
                     "target_id": relation.get("target_id"), "target": names.get(relation.get("target_id"), relation.get("target_id")),
                     "relation_type": relation.get("relation_type"), "valid_from": relation.get("valid_from"), "valid_to": relation.get("valid_to")})
    return {"relations": rows}


def derive_economy(graph: dict[str, Any], names: dict[str, str]) -> dict[str, Any]:
    transactions = []
    for event in records(graph.get("events")):
        facet = event.get("transaction")
        if not isinstance(facet, dict):
            continue
        currency = facet.get("currency_id")
        transactions.append({"event_id": event.get("id"), "chapter": event.get("chapter"),
                             "buyers": [names.get(x, x) for x in facet.get("buyer_ids", []) if isinstance(x, str)],
                             "sellers": [names.get(x, x) for x in facet.get("seller_ids", []) if isinstance(x, str)],
                             "items": [names.get(x, x) for x in facet.get("item_ids", []) if isinstance(x, str)],
                             "currency_id": currency, "currency": names.get(currency, currency) if currency else None,
                             "amount": deepcopy(facet.get("amount")), "unit": facet.get("unit"), "location_id": event.get("location_id")})
    wealth_changes = [deepcopy(c) for c in records(graph.get("state_changes")) if str(c.get("facet") or "").lower() in {"wealth", "财富", "资产", "money", "currency_balance"}]
    return {"transactions": sorted(transactions, key=lambda r: ((r.get("chapter") or 0), str(r.get("event_id") or ""))), "wealth_changes": wealth_changes}


def derive_rules(graph: dict[str, Any], names: dict[str, str]) -> dict[str, Any]:
    concepts = []
    for entity in records(graph.get("entities")):
        if entity.get("type") != "concept":
            continue
        cats = category_ids(entity.get("categories"))
        if not set(cats) & {"rule", "prohibition", "curse", "currency", "recipe", "world_lore"}:
            continue
        concepts.append({"id": entity.get("id"), "name": names.get(entity.get("id"), entity.get("id")), "categories": cats,
                         "summary": entity.get("summary"), "first_chapter": entity.get("first_chapter")})
    enforcement = [deepcopy(e) for e in records(graph.get("events")) if isinstance(e.get("tags"), list) and set(e.get("tags")) & {"rule_enforcement", "rule_violation"}]
    return {"concepts": concepts, "enforcement_events": enforcement}


def derive_payoffs(graph: dict[str, Any]) -> dict[str, Any]:
    event_chapter = {e.get("id"): e.get("chapter") for e in records(graph.get("events"))}
    fs_chapter = {f.get("id"): f.get("planted_chapter") for f in records(graph.get("foreshadowing"))}
    rows = []
    for event in records(graph.get("events")):
        payoff = event.get("payoff")
        if not isinstance(payoff, dict):
            continue
        chapter = event.get("chapter")
        setups = []
        for setup_id in payoff.get("setup_ids", []) if isinstance(payoff.get("setup_ids"), list) else []:
            setup_ch = event_chapter.get(setup_id, fs_chapter.get(setup_id))
            setups.append({"id": setup_id, "chapter": setup_ch, "span": chapter - setup_ch if isinstance(chapter, int) and isinstance(setup_ch, int) else None})
        rows.append({"event_id": event.get("id"), "chapter": chapter, "kind": payoff.get("kind"), "title": event.get("title"), "setups": setups})
    return {"rows": rows}


def derive_voice_and_narrative(graph: dict[str, Any], names: dict[str, str]) -> dict[str, Any]:
    observations = records(graph.get("style_observations"))
    voices: dict[str, list[dict[str, Any]]] = defaultdict(list)
    author = []
    for obs in observations:
        entity_id = obs.get("entity_id") or obs.get("character_id")
        if isinstance(entity_id, str):
            row = deepcopy(obs); row["entity"] = names.get(entity_id, entity_id); voices[entity_id].append(row)
        else:
            author.append(deepcopy(obs))
    return {"character_voice": [{"entity_id": eid, "entity": names.get(eid, eid), "observations": rows} for eid, rows in voices.items()],
            "author_style": author}


def derive_achievements(graph: dict[str, Any], protagonists: set[str], names: dict[str, str], combat_records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    achievements: list[dict[str, Any]] = []
    def add(chapter: int | None, category: str, title: str, source_ids: list[str], entity_ids: list[str], importance: int = 2) -> None:
        if isinstance(chapter, int):
            achievements.append({"chapter": chapter, "category": category, "title": title, "source_ids": source_ids,
                                 "entity_ids": entity_ids, "importance": importance})
    for row in combat_records:
        if row.get("result") == "victory":
            add(row["chapter"], "combat", f"战胜 {'、'.join(row.get('opponents') or []) or '对手'}", [str(row.get("event_id"))], row.get("opponent_ids", []), 3)
    for role in records(graph.get("item_roles")):
        if role.get("entity_id") in protagonists and role.get("action") == "gained":
            item = role.get("item_id"); add(role.get("valid_from"), "item", f"获得 {names.get(item, item)}", [str(role.get("id"))], [item] if isinstance(item, str) else [], 2)
    visited: set[tuple[str, str]] = set()
    for event in sorted(records(graph.get("events")), key=lambda e: ((e.get("chapter") or 0), str(e.get("id") or ""))):
        participants = set(event.get("participant_ids") or []) if isinstance(event.get("participant_ids"), list) else set()
        for pid in protagonists & participants:
            location = event.get("location_id")
            if isinstance(location, str) and (pid, location) not in visited:
                visited.add((pid, location)); add(event.get("chapter"), "location", f"首次到达 {names.get(location, location)}", [str(event.get("id"))], [location], 1)
        if event.get("type") == "breakthrough" and protagonists & participants:
            add(event.get("chapter"), "breakthrough", str(event.get("title") or "完成突破"), [str(event.get("id"))], list(protagonists & participants), 3)
        tags = event.get("tags") if isinstance(event.get("tags"), list) else []
        if "milestone" in tags and protagonists & participants:
            add(event.get("chapter"), "milestone", str(event.get("title") or "重要里程碑"), [str(event.get("id"))], list(protagonists & participants), 3)
        if isinstance(event.get("payoff"), dict) and protagonists & participants:
            add(event.get("chapter"), "payoff", str(event.get("title") or "重要兑现"), [str(event.get("id"))], list(protagonists & participants), 3)
    for route in records(graph.get("romance_routes")):
        pid, cid = route.get("protagonist_id"), route.get("character_id")
        if pid not in protagonists or not isinstance(cid, str): continue
        name = names.get(cid, cid)
        for field, label, importance in (("first_meeting_chapter", "初遇", 1), ("ambiguity_started_chapter", "感情推进", 2), ("confirmed_chapter", "确认关系", 3), ("first_sex_chapter", "亲密关系里程碑", 3)):
            add(route.get(field), "romance", f"{label}：{name}", [str(route.get("id"))], [cid], importance)
    for commitment in records(graph.get("commitments")):
        if not (protagonists & set(commitment.get("promisor_ids") or [])): continue
        if commitment.get("status") in {"fulfilled", "broken", "expired", "waived"}:
            label = {"fulfilled": "兑现承诺", "broken": "背弃承诺", "expired": "承诺过期", "waived": "承诺解除"}.get(commitment.get("status"), "承诺变化")
            add(commitment.get("resolved_chapter"), "commitment", f"{label}：{commitment.get('terms', '')}", [str(commitment.get("id"))], list(commitment.get("counterparty_ids") or []), 3)
    seen, result = set(), []
    for row in sorted(achievements, key=lambda r: (r["chapter"], -r["importance"], r["category"], r["title"])):
        marker = (row["chapter"], row["category"], tuple(row["source_ids"]), tuple(row["entity_ids"]))
        if marker in seen: continue
        seen.add(marker); row["achievement_id"] = f"achv_{row['chapter']}_{len(result)+1:04d}"; result.append(row)
    return result


def build_views(graph: dict[str, Any], explicit_protagonists: Iterable[str] = (), gap_threshold: int = 3) -> dict[str, Any]:
    _entities, names = entity_maps(graph)
    protagonists = set(protagonist_ids(graph, explicit_protagonists))
    combat = derive_combat_records(graph, protagonists, names)
    contract = validate_graph_extensions(graph)
    views = {
        "metadata": {"source_title": graph.get("metadata", {}).get("title") if isinstance(graph.get("metadata"), dict) else None,
                     "chapter_start": graph.get("metadata", {}).get("chapter_start") if isinstance(graph.get("metadata"), dict) else None,
                     "chapter_end": graph.get("metadata", {}).get("chapter_end") if isinstance(graph.get("metadata"), dict) else None,
                     "protagonist_ids": sorted(protagonists), "derived_only": True},
        "combat_records": combat,
        "resources": derive_resources(graph, names),
        "world": derive_world(graph, protagonists, names),
        "cooccurrence": derive_cooccurrence(graph, protagonists, names, gap_threshold),
        "relation_timeline": derive_relation_timeline(graph, names),
        "skills": derive_skills(graph, names),
        "commitments": derive_commitments(graph, names),
        "favor_ledger": derive_favor_ledger(graph, names),
        "knowledge": derive_knowledge(graph, names),
        "foreshadowing": derive_foreshadowing(graph),
        "levels": derive_levels(graph, names),
        "chapter_rhythm": derive_chapter_rhythm(graph, names),
        "romance": derive_romance_milestones(graph, names),
        "snapshot_changes": derive_snapshot_changes(graph, names),
        "mortality": derive_mortality(graph, names),
        "inheritance": derive_inheritance(graph, names),
        "economy": derive_economy(graph, names),
        "rules": derive_rules(graph, names),
        "payoffs": derive_payoffs(graph),
        "narrative": derive_voice_and_narrative(graph, names),
        "coverage": contract.get("coverage", {}),
        "contract_summary": {"valid": contract.get("valid"), "error_count": contract.get("error_count"), "warning_count": contract.get("warning_count"), "observations": contract.get("observations", [])},
    }
    views["achievements"] = derive_achievements(graph, protagonists, names, combat)
    return views


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--graph", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--protagonist-id", action="append", default=[])
    parser.add_argument("--relation-gap-threshold", type=int, default=3)
    args = parser.parse_args()
    graph = json.loads(args.graph.read_text(encoding="utf-8"))
    views = build_views(graph, args.protagonist_id, max(1, args.relation_gap_threshold))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(views, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"output": str(args.output), "achievements": len(views["achievements"]),
                      "combat_records": len(views["combat_records"]), "resources": len(views["resources"]["items"]),
                      "locations": len(views["world"]["locations"]), "relation_gap_candidates": len(views["cooccurrence"]["relation_gap_candidates"]),
                      "commitments": len(views["commitments"]), "secrets": len(views["knowledge"]["secrets"])}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
