"""The reader model: everything the dashboard shows, precomputed per chapter.

The browser never decides what is true at chapter N. This module turns the
canonical graph into intervals and per-chapter rows, using the same temporal
rules as `nkg.temporal.asof`, and the page only picks the interval that contains
the chapter on the slider.

Rules that decide what a reader may see:

- an entity exists from its first chapter; its name follows `name_history`, its
  aliases their first chapters. An alias with no timing is dated by the first
  source quotation that contains it. A name, alias, summary or attribute that
  still has no timing is the analysed end state, shown only at the terminal chapter;
- a state value starts at the chapter of the change that set it and ends where
  the next change on the same facet (and target) starts. Volatile facets
  (location, emotion, injury …) also end `FACET_TTL` chapters after the last
  change or audit-card confirmation: a stale value is hidden, never shown;
- a relation holds over its inclusive validity interval; its status and stance
  follow its dated observations;
- a romance route's status at each chapter is `romance_status_asof`;
- clue, promise and route statuses change only at dated chapters.

Prose shown to readers passes through `reader_prose.strip_process_text`.
"""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from typing import Any, Iterable, Mapping

from chapter_audit import AUDIT_ITEMS, NARRATIVE_FUNCTIONS
from display_vocabulary import DEFAULT_VOCABULARY, DURABLE_HEALTH_WORDS, FACET_TTL, merge_vocabulary
from nkg.core.records import chapter_value, records
from nkg.temporal.asof import first_visible_chapter, romance_status_asof
from reader_prose import strip_process_text
from relation_types import GROUP_LABELS, STANCES, canonical_relation_type, relation_group

SCHEMA = "nkg-reader/1"
STATE_CHECK_LABELS = {"changed": "本章变化", "confirmed_unchanged": "确认未变", "not_tracked": "无追踪状态"}
CLIFFHANGER_LABELS = {"crisis": "危机悬念", "suspense": "悬念", "reversal": "反转", "revelation": "揭示",
                      "breakthrough": "突破", "romance": "感情钩子", "none": "无", "uncertain": "待定"}
COMMITMENT_STATUS_LABELS = {"active": "未了结", "fulfilled": "已履行", "partially_fulfilled": "部分履行",
                            "broken": "已违背", "expired": "已过期", "waived": "已豁免", "uncertain": "待定"}
TIER_LABELS = {"protagonist": "主角", "core": "核心", "major": "主要", "minor": "次要", "background": "背景"}
TARGETED_FACETS = frozenset({"level", "possession", "skill", "knowledge", "ability", "item", "ownership",
                             "relationship", "qualification", "title"})
HIERARCHY_TYPES = frozenset({"located_in", "part_of", "subgroup_of"})
MEMBERSHIP_GROUPS = frozenset({"affiliation"})


def _prose(value: Any, labels: Mapping[str, str]) -> str:
    return strip_process_text(value, labels) if isinstance(value, str) else ""


def _label(value: Any) -> str | None:
    """Display text of a state value: `{value,label,note}`, a plain string, or a number."""
    if value is None:
        return None
    if isinstance(value, Mapping):
        label = value.get("label")
        if label in (None, "") and value.get("value") is not None:
            label = value.get("value")
        if label in (None, ""):
            return None
        note = value.get("note")
        return f"{label}（{note}）" if isinstance(note, str) and note and note not in str(label) else str(label)
    if isinstance(value, (list, tuple)):
        return "、".join(str(v) for v in value if v not in (None, "")) or None
    text = str(value).strip()
    return text or None


def _sort_value(value: Any) -> float | None:
    if isinstance(value, Mapping) and isinstance(value.get("value"), (int, float)):
        return float(value["value"])
    return None


def _drop_empty(row: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in row.items() if v not in (None, "", [], {})}


class _Builder:
    def __init__(self, graph: Mapping[str, Any], *, hints: Mapping[str, Any] | None,
                 ledger: Mapping[str, Any] | None, vocabulary: Mapping[str, Any] | None,
                 protagonist_ids: Iterable[str]):
        self.graph = graph
        meta = graph.get("metadata") if isinstance(graph.get("metadata"), Mapping) else {}
        self.meta = meta
        self.vocab = merge_vocabulary(DEFAULT_VOCABULARY, meta.get("display_vocabulary") or {})
        if vocabulary:
            self.vocab = merge_vocabulary(self.vocab, vocabulary)
        self.enum_labels = {k: v for group in self.vocab.values() if isinstance(group, dict)
                            for k, v in group.items() if isinstance(v, str)}
        analyzed = sorted({c for c in (meta.get("analyzed_chapters") or []) if isinstance(c, int)})
        if not analyzed:
            analyzed = sorted({c for c in (chapter_value(r.get("chapter")) for r in records(graph.get("evidence")))
                               if c is not None})
        self.analyzed = analyzed
        self.first = analyzed[0] if analyzed else 0
        self.terminal = chapter_value(meta.get("chapter_end"))
        if self.terminal is None:
            self.terminal = analyzed[-1] if analyzed else 0
        self.entities = {e["id"]: e for e in records(graph.get("entities")) if isinstance(e.get("id"), str)}
        self.hints = hints or {}
        self.ledger = ledger or {}
        self.protagonists = list(protagonist_ids)
        self.evidence = {e["id"]: e for e in records(graph.get("evidence")) if isinstance(e.get("id"), str)}
        self.used_evidence: set[str] = set()
        self.alias_meta = meta.get("alias_first_chapter") if isinstance(meta.get("alias_first_chapter"), Mapping) else {}

    # -- helpers -------------------------------------------------------------
    def ev(self, ids: Any) -> list[str]:
        out = [i for i in (ids or []) if isinstance(i, str) and i in self.evidence]
        self.used_evidence.update(out)
        return out

    def untimed(self) -> int:
        return self.terminal

    # -- entities ------------------------------------------------------------
    def entity_rows(self) -> dict[str, Any]:
        participation = Counter(p for ev in records(self.graph.get("events")) for p in ev.get("participant_ids") or [])
        tiers = self._tiers(participation)
        profiles = self.hints.get("profiles") if isinstance(self.hints.get("profiles"), Mapping) else {}
        out: dict[str, Any] = {}
        for eid, e in self.entities.items():
            first = chapter_value(e.get("first_chapter"))
            if first is None:
                first = first_visible_chapter(e)
            if first is None:
                first = self.untimed()
            names = self._timeline(e.get("name_history"), ("name", "value"))
            if not names or names[0][0] > first:
                # the canonical name is the end state; before a recorded rename it is only safe
                # when there is no history at all (the entity was introduced under that name)
                if not names:
                    names = [[first, str(e.get("name") or eid)]]
                else:
                    names.insert(0, [first, f"〔未具名{self.vocab['entity_types'].get(e.get('type'), '')}〕"])
            aliases = []
            for field in ("aliases", "historical_names", "titles"):
                for alias in e.get(field) or []:
                    if isinstance(alias, Mapping):
                        text = alias.get("name") or alias.get("value") or alias.get("label")
                        start = first_visible_chapter(alias)
                    else:
                        text = alias
                        nested = self.alias_meta.get(eid)
                        start = chapter_value(nested.get(alias)) if isinstance(nested, Mapping) else chapter_value(self.alias_meta.get(alias))
                    if isinstance(text, str) and text:
                        if start is None:
                            start = self._quoted_from(eid, text, first)
                        aliases.append([start if start is not None else self.untimed(), text])
            summary = self._timeline(e.get("summary_history"), ("summary", "value", "text"))
            if not summary and isinstance(e.get("summary"), str):
                summary = [[self.untimed(), e["summary"]]]
            prof = profiles.get(eid) if isinstance(profiles.get(eid), Mapping) else {}
            headlines = [[chapter_value(h.get("valid_from")) or self.untimed(), chapter_value(h.get("valid_to")),
                          _prose(h.get("text"), self.enum_labels)]
                         for h in prof.get("headlines") or [] if isinstance(h, Mapping) and h.get("text")]
            out[eid] = _drop_empty({
                "type": e.get("type"),
                "first": first,
                "names": names,
                "aliases": sorted(aliases),
                "summary": [[c, _prose(t, self.enum_labels)] for c, t in summary],
                "tier": prof.get("tier") or tiers.get(eid, "background"),
                "tierSource": "editorial" if prof.get("tier") else "derived",
                "categories": [c if isinstance(c, str) else c.get("id") for c in e.get("categories") or []
                               if isinstance(c, (str, Mapping))],
                "headlines": headlines,
                "bios": {k: _prose(v, self.enum_labels) for k, v in (prof.get("arc_bios") or {}).items()},
                "toProtagonist": prof.get("relation_to_protagonist"),
                "primary": prof.get("primary_membership") if prof.get("primary_membership") in self.entities else None,
                "attrs": self._attributes(e),
                "events": participation.get(eid, 0),
            })
        return out

    def _quoted_from(self, entity_id: str, text: str, first: int) -> int | None:
        """First chapter whose quotation, cited by a record about this entity, contains `text`.

        Only quotations tied to the entity count: a bare substring search across the
        book dates 「秦受」 by an unrelated 「秦受伤」.
        """
        if not hasattr(self, "_entity_quotes"):
            cited: dict[str, set[str]] = defaultdict(set)
            for kind, fields in (("entities", ("id",)), ("events", ("participant_ids",)),
                                 ("state_changes", ("entity_id",)), ("relations", ("source_id", "target_id")),
                                 ("chapter_summaries", ("notable_character_ids",))):
                for row in records(self.graph.get(kind)):
                    owners = [v for f in fields for v in (row.get(f) if isinstance(row.get(f), list) else [row.get(f)])]
                    for owner in owners:
                        if isinstance(owner, str):
                            cited[owner].update(i for i in row.get("evidence_ids") or [] if isinstance(i, str))
            self._entity_quotes = {
                owner: sorted((chapter_value(self.evidence[i].get("chapter")), self.evidence[i].get("quote") or "")
                              for i in ids if i in self.evidence and chapter_value(self.evidence[i].get("chapter")) is not None)
                for owner, ids in cited.items()}
        return next((ch for ch, quote in self._entity_quotes.get(entity_id, []) if ch >= first and text in quote), None)

    def _timeline(self, history: Any, keys: tuple[str, ...]) -> list[list[Any]]:
        rows = []
        for row in records(history):
            start = chapter_value(row.get("valid_from"))
            if start is None:
                start = chapter_value(row.get("chapter"))
            value = next((row[k] for k in keys if isinstance(row.get(k), str) and row[k]), None)
            if start is not None and value:
                rows.append([start, value])
        return sorted(rows)

    def _attributes(self, entity: Mapping[str, Any]) -> list[list[Any]]:
        """[from, key, value] for each attribute; untimed values appear at the terminal chapter."""
        out = []
        for row in records(entity.get("attribute_history")) + records(entity.get("attributes_history")):
            start = chapter_value(row.get("chapter"))
            if start is None:
                start = chapter_value(row.get("valid_from"))
            key = row.get("key") or row.get("attribute")
            if start is not None and isinstance(key, str):
                out.append([start, self.vocab["attribute_keys"].get(key, key), _label(row.get("value"))])
        timed = {k for _, k, _ in out}
        first_map = (self.meta.get("attribute_first_chapter") or {}).get(entity.get("id")) or {}
        for key, value in (entity.get("attributes") or {}).items() if isinstance(entity.get("attributes"), Mapping) else []:
            label = self.vocab["attribute_keys"].get(key, key)
            if label in timed or _label(value) is None:
                continue
            start = chapter_value(first_map.get(key)) if isinstance(first_map, Mapping) else None
            out.append([start if start is not None else self.untimed(), label, _label(value)])
        return sorted(out, key=lambda r: (r[0], r[1]))

    def _tiers(self, participation: Counter) -> dict[str, str]:
        """Fallback importance when no editorial tier exists: protagonist, then by on-page events."""
        tiers = {pid: "protagonist" for pid in self.protagonists}
        ranked = [eid for eid, _ in participation.most_common() if eid in self.entities and eid not in tiers
                  and self.entities[eid].get("type") == "character"]
        for index, eid in enumerate(ranked):
            count = participation[eid]
            tiers[eid] = "core" if index < 8 else "major" if index < 30 else "minor" if count >= 3 else "background"
        return tiers

    # -- states --------------------------------------------------------------
    def fact_rows(self, confirmations: Mapping[str, list[int]]) -> list[dict[str, Any]]:
        by_key: dict[tuple[str, str, str | None], list[dict]] = defaultdict(list)
        for sc in records(self.graph.get("state_changes")):
            ch = chapter_value(sc.get("chapter"))
            eid, facet = sc.get("entity_id"), sc.get("facet")
            if ch is None or eid not in self.entities or not isinstance(facet, str):
                continue
            target = sc.get("target_id") if facet in TARGETED_FACETS and isinstance(sc.get("target_id"), str) else None
            by_key[(eid, facet, target)].append(sc)
        rows = []
        for (eid, facet, target), changes in by_key.items():
            changes.sort(key=lambda s: (s["chapter"], str(s.get("id") or "")))
            for index, sc in enumerate(changes):
                start = sc["chapter"]
                nxt = changes[index + 1]["chapter"] - 1 if index + 1 < len(changes) else None
                explicit_end = chapter_value(sc.get("end_chapter"))
                end = min(x for x in (nxt, explicit_end) if x is not None) if (nxt is not None or explicit_end is not None) else None
                value = sc.get("after")
                text = _label(value)
                if text is None and sc.get("action") in {"lost", "transferred", "forgotten", "left"}:
                    continue  # the value ends here; nothing to show
                if text is None and target:
                    text = self.vocab["actions"].get(sc.get("action"), sc.get("action") or "")
                if not text:
                    continue
                ttl = FACET_TTL.get(facet)
                volatile = ttl is not None and not (facet == "health" and any(w in text for w in DURABLE_HEALTH_WORDS))
                stale = None
                if volatile:
                    last = start
                    for c in confirmations.get(eid, []):
                        if start <= c and (end is None or c <= end):
                            last = max(last, c)
                    stale = last + ttl
                    end = stale if end is None else min(end, stale)
                if end is not None and end < start:
                    end = start
                rows.append(_drop_empty({
                    "e": eid, "facet": facet, "target": target, "from": start, "to": end,
                    "value": _prose(text, self.enum_labels) or text, "sort": _sort_value(value),
                    "action": sc.get("action"), "reason": _prose(sc.get("reason"), self.enum_labels),
                    "ev": self.ev(sc.get("evidence_ids")), "volatile": volatile or None,
                    "id": sc.get("id"), "place": self._place(text) if facet == "location" else None,
                }))
        rows.sort(key=lambda r: (r["e"], r["facet"], r.get("target") or "", r["from"]))
        return rows

    def _place(self, text: str) -> str | None:
        """The location entity a location state names exactly (name or alias); no fuzzy match."""
        if not hasattr(self, "_places"):
            index: dict[str, set[str]] = defaultdict(set)
            for eid, e in self.entities.items():
                if e.get("type") == "location":
                    for label in [e.get("name"), *(a for a in e.get("aliases") or [] if isinstance(a, str))]:
                        if isinstance(label, str) and label:
                            index[label].add(eid)
            self._places = {k: next(iter(v)) for k, v in index.items() if len(v) == 1}
        return self._places.get(text.strip())

    # -- relations -----------------------------------------------------------
    def relation_rows(self) -> list[dict[str, Any]]:
        rows = []
        for rel in records(self.graph.get("relations")):
            s, t = rel.get("source_id"), rel.get("target_id")
            start = chapter_value(rel.get("valid_from"))
            if start is None:
                start = first_visible_chapter(rel)
            if s not in self.entities or t not in self.entities or start is None:
                continue
            rtype = canonical_relation_type(rel.get("relation_type"))
            obs = sorted(records(rel.get("observations")), key=lambda o: chapter_value(o.get("chapter")) or 0)
            status = [[chapter_value(o.get("chapter")), o["status"]] for o in obs
                      if chapter_value(o.get("chapter")) is not None and isinstance(o.get("status"), str)]
            stance = [[chapter_value(o.get("chapter")), o["stance"]] for o in obs
                      if chapter_value(o.get("chapter")) is not None and o.get("stance") in STANCES]
            if rel.get("stance") in STANCES and not stance:
                stance = [[start, rel["stance"]]]
            notes = [[chapter_value(o.get("chapter")), _prose(o.get("description"), self.enum_labels)] for o in obs
                     if chapter_value(o.get("chapter")) is not None and o.get("description")]
            if not notes and rel.get("description"):
                notes = [[start, _prose(rel.get("description"), self.enum_labels)]] if not obs else []
            rows.append(_drop_empty({
                "id": rel.get("id"), "s": s, "t": t, "type": rtype, "group": relation_group(rtype),
                "from": start, "to": chapter_value(rel.get("valid_to")),
                "status": status, "stance": stance, "notes": notes, "ev": self.ev(rel.get("evidence_ids")),
            }))
        return rows

    # -- chapters ------------------------------------------------------------
    def chapter_rows(self, events_by_chapter: Mapping[int, list[str]], arcs: list[dict]) -> tuple[list[dict], dict[str, list[int]]]:
        summaries = {chapter_value(s.get("chapter")): s for s in records(self.graph.get("chapter_summaries"))}
        quality = {r.get("chapter"): r.get("quality") for r in records(self.ledger.get("chapters")) if r.get("quality")}
        changes_by_chapter = Counter(chapter_value(s.get("chapter")) for s in records(self.graph.get("state_changes")))
        confirmations: dict[str, list[int]] = defaultdict(list)
        rows = []
        for n in self.analyzed:
            s = summaries.get(n) or {}
            cast = []
            for p in s.get("presence") or []:
                if isinstance(p, Mapping) and p.get("entity_id") in self.entities:
                    cast.append(_drop_empty({"id": p["entity_id"], "mode": p.get("mode"),
                                             "role": _prose(p.get("role"), self.enum_labels), "check": p.get("state_check")}))
                    if p.get("mode") == "present" and p.get("state_check") in {"confirmed_unchanged", "changed"}:
                        confirmations[p["entity_id"]].append(n)
            if not cast:
                seen = list(dict.fromkeys([*(s.get("notable_character_ids") or []),
                                           *(pid for ev in events_by_chapter.get(n, []) for pid in self._participants(ev))]))
                cast = [{"id": eid, "mode": "derived"} for eid in seen if eid in self.entities]
            continuity = s.get("continuity") if isinstance(s.get("continuity"), Mapping) else {}
            narrative = s.get("narrative") if isinstance(s.get("narrative"), Mapping) else {}
            audit = s.get("audit") if isinstance(s.get("audit"), Mapping) else {}
            rows.append(_drop_empty({
                "n": n,
                "title": s.get("title"),
                "summary": _prose(s.get("summary"), self.enum_labels),
                "arcs": [a["id"] for a in arcs if a["from"] <= n and (a.get("to") is None or n <= a["to"])],
                "events": events_by_chapter.get(n, []),
                "cast": cast,
                "scenes": [_drop_empty({"purpose": _prose(sc.get("purpose"), self.enum_labels),
                                        "who": [p for p in sc.get("participant_ids") or [] if p in self.entities],
                                        "where": sc.get("location_label"), "when": sc.get("time_label"),
                                        "pov": sc.get("pov_entity_id"), "events": sc.get("event_ids")})
                           for sc in s.get("scenes") or [] if isinstance(sc, Mapping)],
                "prev": _prose(continuity.get("from_previous"), self.enum_labels),
                "next": _prose(continuity.get("sets_up"), self.enum_labels),
                "functions": narrative.get("functions"),
                "cliffhanger": narrative.get("cliffhanger_type") or s.get("cliffhanger_type"),
                "audit": {k: _drop_empty({"s": v.get("status"), "c": v.get("count"), "r": v.get("reason")})
                          for k, v in audit.items() if isinstance(v, Mapping)},
                "density": len(events_by_chapter.get(n, [])) + changes_by_chapter.get(n, 0),
                "quality": quality.get(n),
                "ev": self.ev(s.get("evidence_ids")),
            }))
        return rows, confirmations

    def _participants(self, event_id: str) -> list[str]:
        return self._event_index.get(event_id, {}).get("participant_ids") or []

    # -- events, arcs, threads ------------------------------------------------
    def event_rows(self) -> tuple[dict[str, Any], dict[int, list[str]]]:
        self._event_index = {e["id"]: e for e in records(self.graph.get("events")) if isinstance(e.get("id"), str)}
        out, by_chapter = {}, defaultdict(list)
        for eid, ev in sorted(self._event_index.items(), key=lambda kv: (chapter_value(kv[1].get("chapter")) or 0, kv[0])):
            ch = chapter_value(ev.get("chapter"))
            if ch is None:
                continue
            by_chapter[ch].append(eid)
            out[eid] = _drop_empty({
                "ch": ch, "type": ev.get("type"), "title": _prose(ev.get("title"), self.enum_labels),
                "desc": _prose(ev.get("description"), self.enum_labels),
                "who": [p for p in ev.get("participant_ids") or [] if p in self.entities],
                "where": ev.get("location_id") if ev.get("location_id") in self.entities else None,
                "tags": ev.get("tags"), "ev": self.ev(ev.get("evidence_ids")),
                "combat": bool(ev.get("combat")) or None,
                "death": bool((ev.get("mortality") or {}).get("victim_ids")) if isinstance(ev.get("mortality"), Mapping) else None,
            })
        return out, by_chapter

    def arc_rows(self) -> list[dict[str, Any]]:
        out = []
        recaps = self.hints.get("arc_recaps") if isinstance(self.hints.get("arc_recaps"), Mapping) else {}
        for arc in records(self.graph.get("story_arcs")):
            start = chapter_value(arc.get("chapter_start"))
            if start is None:
                continue
            recap = recaps.get(arc.get("id")) if isinstance(recaps.get(arc.get("id")), Mapping) else {}
            out.append(_drop_empty({
                "id": arc.get("id"), "title": arc.get("title"), "from": start, "to": chapter_value(arc.get("chapter_end")),
                "parent": arc.get("parent_arc_id"), "phase": arc.get("phase"), "status": arc.get("status"),
                "summary": _prose(arc.get("summary") or arc.get("description"), self.enum_labels),
                "recap": _prose(recap.get("text") or recap.get("recap"), self.enum_labels),
                "cast": [e for e in arc.get("entity_ids") or [] if e in self.entities],
                "turns": arc.get("turning_point_ids"),
            }))
        return sorted(out, key=lambda a: (a["from"], -(a.get("to") or 10 ** 9)))

    def thread_rows(self) -> dict[str, list[dict[str, Any]]]:
        clues = []
        for fs in records(self.graph.get("foreshadowing")):
            planted = chapter_value(fs.get("planted_chapter"))
            if planted is None:
                continue
            status = [[planted, "open"]]
            for p in sorted(records(fs.get("progression")), key=lambda p: chapter_value(p.get("chapter")) or 0):
                ch = chapter_value(p.get("chapter"))
                if ch is not None:
                    status.append([ch, "resolved" if p.get("kind") == "payoff" else "progressed"])
            payoff = chapter_value(fs.get("payoff_chapter"))
            if payoff is not None:
                status.append([payoff, "resolved"])
            elif fs.get("status") in {"false_lead", "resolved", "partially_resolved"} and len(status) == 1:
                status.append([self.untimed(), fs["status"]])
            clues.append(_drop_empty({
                "id": fs.get("id"), "label": _prose(fs.get("label"), self.enum_labels), "from": planted,
                "obs": _prose(fs.get("observation"), self.enum_labels),
                "steps": [[chapter_value(p.get("chapter")), p.get("kind"), _prose(p.get("description"), self.enum_labels)]
                          for p in records(fs.get("progression")) if chapter_value(p.get("chapter")) is not None],
                "payoffAt": payoff, "who": [e for e in fs.get("related_entity_ids") or [] if e in self.entities],
                "status": _dedupe_steps(status), "ev": self.ev(fs.get("evidence_ids")),
            }))
        promises = []
        for c in records(self.graph.get("commitments")):
            created = chapter_value(c.get("created_chapter"))
            if created is None:
                continue
            status = [[created, "active"]]
            for o in sorted(records(c.get("observations")), key=lambda o: chapter_value(o.get("chapter")) or 0):
                if chapter_value(o.get("chapter")) is not None and isinstance(o.get("status"), str):
                    status.append([o["chapter"], o["status"]])
            resolved = chapter_value(c.get("resolved_chapter"))
            if resolved is not None:
                status.append([resolved, c.get("status") if c.get("status") not in {None, "active"} else "fulfilled"])
            promises.append(_drop_empty({
                "id": c.get("id"), "kind": c.get("kind"), "terms": _prose(c.get("terms"), self.enum_labels),
                "from": created, "by": [e for e in c.get("promisor_ids") or [] if e in self.entities],
                "to": [e for e in c.get("counterparty_ids") or [] if e in self.entities],
                "deadline": chapter_value(c.get("deadline_chapter")), "status": _dedupe_steps(status),
                "resolution": _prose(c.get("resolution"), self.enum_labels) if resolved is not None else None,
                "resolvedAt": resolved, "ev": self.ev(c.get("evidence_ids")),
            }))
        routes = []
        for r in records(self.graph.get("romance_routes")):
            if r.get("character_id") not in self.entities:
                continue
            start = first_visible_chapter(r)
            if start is None:
                start = chapter_value((self.entities[r["character_id"]]).get("first_chapter")) or self.untimed()
            points = sorted({start, self.terminal, *(c for c in (chapter_value(r.get(k)) for k in (
                "ambiguity_started_chapter", "first_sex_chapter", "confirmed_chapter")) if c is not None)})
            status = _dedupe_steps([[p, romance_status_asof(r, r, p, self.terminal)] for p in points if p >= start])
            routes.append(_drop_empty({
                "id": r.get("id"), "who": r["character_id"], "pro": r.get("protagonist_id"), "from": start,
                "status": status, "met": chapter_value(r.get("first_meeting_chapter")),
                "ambiguous": chapter_value(r.get("ambiguity_started_chapter")),
                "confirmed": chapter_value(r.get("confirmed_chapter")), "firstSex": chapter_value(r.get("first_sex_chapter")),
                "basis": r.get("inclusion_basis"), "consent": r.get("consent_context"),
                "steps": [[chapter_value(p.get("chapter")), p.get("kind"), _prose(p.get("description"), self.enum_labels)]
                          for p in records(r.get("progression")) if chapter_value(p.get("chapter")) is not None],
            }))
        acts = []
        for a in records(self.graph.get("intimate_acts")):
            ch = chapter_value(a.get("chapter"))
            if ch is None:
                continue
            acts.append(_drop_empty({
                "id": a.get("id"), "ch": ch, "type": a.get("act_type"),
                "by": [e for e in a.get("initiator_ids") or [] if e in self.entities],
                "to": [e for e in a.get("recipient_ids") or [] if e in self.entities],
                "consent": a.get("consent"), "desc": _prose(a.get("description"), self.enum_labels),
                "ev": self.ev(a.get("evidence_ids")),
            }))
        return {"clues": clues, "promises": promises, "routes": routes, "acts": sorted(acts, key=lambda a: a["ch"])}

    def level_ladders(self, facts: list[dict]) -> dict[str, Any]:
        ladders: dict[str, dict[str, Any]] = {}
        for f in facts:
            if f["facet"] != "level" or not f.get("target"):
                continue
            ladder = ladders.setdefault(f["target"], {"rungs": {}})
            rung = ladder["rungs"].setdefault(f["value"], {"label": f["value"], "sort": f.get("sort"), "from": f["from"]})
            rung["from"] = min(rung["from"], f["from"])
        for axis, ladder in ladders.items():
            rungs = sorted(ladder["rungs"].values(), key=lambda r: (r["sort"] if r["sort"] is not None else 1e9, r["from"]))
            ladder["rungs"] = [_drop_empty(r) for r in rungs]
        return ladders


def _dedupe_steps(steps: list[list[Any]]) -> list[list[Any]]:
    out: list[list[Any]] = []
    for ch, value in sorted(steps, key=lambda s: s[0]):
        if out and out[-1][0] == ch:
            out[-1][1] = value
        elif not out or out[-1][1] != value:
            out.append([ch, value])
    return out


def _milestones(model: Mapping[str, Any], protagonists: list[str]) -> list[dict[str, Any]]:
    """Landmarks for the chapter axis: deaths, protagonist breakthroughs, confirmed romances, clue payoffs."""
    names = {eid: (e.get("names") or [[0, eid]])[-1][1] for eid, e in model["entities"].items()}
    tiers = {eid: e.get("tier") for eid, e in model["entities"].items()}
    out: list[dict[str, Any]] = []
    for eid, ev in model["events"].items():
        if ev.get("death"):
            out.append({"ch": ev["ch"], "kind": "death", "label": ev.get("title") or "死亡", "event": eid})
    for f in model["facts"]:
        if f["facet"] == "health" and not f.get("volatile") and any(w in f["value"] for w in DURABLE_HEALTH_WORDS) \
                and tiers.get(f["e"]) in {"protagonist", "core", "major"}:
            out.append({"ch": f["from"], "kind": "death", "label": f"{names.get(f['e'], f['e'])}：{f['value']}", "who": f["e"]})
        if f["facet"] == "level" and f["e"] in protagonists and f.get("action") in {"gained", "upgraded", "changed"}:
            out.append({"ch": f["from"], "kind": "breakthrough", "label": f"{names.get(f['e'], f['e'])} → {f['value']}", "who": f["e"]})
    for r in model["threads"]["routes"]:
        if r.get("confirmed") is not None:
            out.append({"ch": r["confirmed"], "kind": "romance", "label": f"与{names.get(r['who'], r['who'])}确认关系", "who": r["who"]})
    for c in model["threads"]["clues"]:
        if c.get("payoffAt") is not None:
            out.append({"ch": c["payoffAt"], "kind": "payoff", "label": f"伏笔回收：{c['label']}"})
    seen, unique = set(), []
    for m in sorted(out, key=lambda m: (m["ch"], m["kind"], m["label"])):
        key = (m["ch"], m["kind"], m.get("who") or m["label"])
        if key not in seen:
            seen.add(key)
            unique.append(m)
    return unique


def build_reader_model(graph: Mapping[str, Any], *, hints: Mapping[str, Any] | None = None,
                       ledger: Mapping[str, Any] | None = None, vocabulary: Mapping[str, Any] | None = None,
                       protagonist_ids: Iterable[str] = (), cutoff: int | None = None) -> dict[str, Any]:
    """The full reader model. Apply `filter_graph` before calling when `cutoff` is set."""
    from derive_novel_views import protagonist_ids as find_protagonists

    b = _Builder(graph, hints=hints, ledger=ledger, vocabulary=vocabulary,
                 protagonist_ids=find_protagonists(dict(graph), protagonist_ids))
    if cutoff is not None:
        b.terminal = min(b.terminal, cutoff)
        b.analyzed = [c for c in b.analyzed if c <= cutoff]
    events, by_chapter = b.event_rows()
    arcs = b.arc_rows()
    chapters, confirmations = b.chapter_rows(by_chapter, arcs)
    facts = b.fact_rows(confirmations)
    model = {
        "schema": SCHEMA,
        "meta": _drop_empty({
            "title": b.meta.get("title") or b.meta.get("book"), "first": b.first, "last": b.terminal,
            "cutoff": cutoff, "protagonists": b.protagonists,
            "audited": sum(1 for c in chapters if c.get("audit")), "chapters": len(chapters),
        }),
        "vocab": {key: b.vocab.get(key, {}) for key in (
            "entity_types", "facets", "actions", "relations", "relation_statuses", "romance_statuses",
            "romance_inclusion_bases", "consent_contexts", "foreshadow_statuses", "progression_kinds",
            "event_types", "intimacy_act_types", "story_arc_phases", "story_arc_statuses", "item_categories")}
                 | {"relation_groups": GROUP_LABELS, "stances": STANCES, "audit_items": AUDIT_ITEMS,
                    "narrative_functions": NARRATIVE_FUNCTIONS, "state_checks": STATE_CHECK_LABELS,
                    "tiers": TIER_LABELS, "cliffhangers": CLIFFHANGER_LABELS,
                    "commitment_statuses": COMMITMENT_STATUS_LABELS},
        "arcs": arcs,
        "chapters": chapters,
        "entities": b.entity_rows(),
        "facts": facts,
        "relations": b.relation_rows(),
        "events": events,
        "threads": b.thread_rows(),
        "levels": b.level_ladders(facts),
    }
    model["milestones"] = _milestones(model, b.protagonists)
    model["evidence"] = {i: [chapter_value(b.evidence[i].get("chapter")), b.evidence[i].get("quote") or ""]
                         for i in sorted(b.used_evidence)}
    return model


def model_text(model: Mapping[str, Any]) -> str:
    """Every reader-visible string in the model, for the leak gate."""
    parts: list[str] = []

    def walk(value: Any) -> None:
        if isinstance(value, str):
            if not re.fullmatch(r"[a-z_0-9@]+", value):
                parts.append(value)
        elif isinstance(value, Mapping):
            for k, v in value.items():
                if k != "vocab":
                    walk(v)
        elif isinstance(value, list):
            for v in value:
                walk(v)

    walk({k: v for k, v in model.items() if k != "vocab"})
    return "\n".join(parts)
