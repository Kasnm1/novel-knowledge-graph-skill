"""A fragment builder for chapter-audit workers.

Most gate failures in the model comparison were mechanical, not judgment: a
receipt count that did not match the records, an ID without the fragment marker,
an evidence ID typed twice, a state value written as a bare string. One worker
needed fifteen gate runs. The builder removes that class of error:

- record IDs are numbered per kind with the fragment marker (`ev_f01_001`);
- evidence is passed as quotes and deduplicated per chapter; IDs come back;
- state values are normalised to `{value, label, note}`;
- audit-card receipts are **computed from the records** at `build()`; the worker
  only supplies a reason for each item that has no records, and `build()` refuses
  to finish while any such reason is missing.

Judgment stays with the worker: what happened, who was present, which facet
changed, what counts as a clue.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable, Mapping

from chapter_audit import AUDIT_ITEMS, AUDIT_PROTOCOL, item_counts

PREFIX = {
    "evidence": "ev", "events": "event", "state_changes": "sc", "relations": "rel",
    "character_traits": "tr", "item_roles": "ir", "commitments": "cm", "foreshadowing": "fs",
    "romance_routes": "rom", "intimate_acts": "ia", "review_issues": "ri", "level_conversions": "lc",
}
Quotes = str | Iterable[str] | None


def state_value(value: Any, note: str | None = None) -> Any:
    """Normalise a state endpoint to null or {value, label, note}."""
    if value is None:
        return None
    if isinstance(value, Mapping):
        out = dict(value)
        out.setdefault("value", None)
    elif isinstance(value, (int, float)) and not isinstance(value, bool):
        out = {"value": value, "label": str(value)}
    else:
        out = {"value": None, "label": str(value)}
    if note:
        out["note"] = note
    return out


class FragmentBuilder:
    def __init__(self, fragment: str, marker: str, chapters: Iterable[int], *, supplementary: bool = False):
        self.marker = marker
        self.chapters = sorted(chapters)
        self.data: dict[str, Any] = {
            "metadata": {"fragment": fragment, "chapter_start": self.chapters[0], "chapter_end": self.chapters[-1],
                         "analyzed_chapters": self.chapters, "audit_protocol": AUDIT_PROTOCOL,
                         **({"supplementary": True} if supplementary else {})},
            "entities": [], "evidence": [], "chapter_summaries": [],
            **{kind: [] for kind in PREFIX if kind != "evidence"},
        }
        self._counters: dict[str, int] = {}
        self._quotes: dict[tuple[int, str], str] = {}
        self._none_reasons: dict[int, dict[str, str]] = {}

    # ---- ids and evidence ----
    def _next(self, kind: str) -> str:
        self._counters[kind] = self._counters.get(kind, 0) + 1
        return f"{PREFIX[kind]}_{self.marker}_{self._counters[kind]:03d}"

    def quote(self, chapter: int, text: str) -> str:
        """Register a verbatim single-line quote; returns its evidence ID (deduplicated)."""
        text = text.strip()
        key = (chapter, text)
        if key not in self._quotes:
            evidence_id = self._next("evidence")
            self._quotes[key] = evidence_id
            self.data["evidence"].append({"id": evidence_id, "chapter": chapter, "quote": text})
        return self._quotes[key]

    def evidence(self, chapter: int, quotes: Quotes) -> list[str]:
        if quotes is None:
            return []
        items = [quotes] if isinstance(quotes, str) else list(quotes)
        return [q if q.startswith("ev_") else self.quote(chapter, q) for q in items]

    def _add(self, kind: str, record: dict[str, Any]) -> str:
        record.setdefault("id", self._next(kind))
        self.data[kind].append(record)
        return record["id"]

    # ---- records ----
    def entity(self, entity_id: str, entity_type: str, name: str, first_chapter: int, quotes: Quotes, **fields) -> str:
        self.data["entities"].append({"id": entity_id, "type": entity_type, "name": name,
                                      "first_chapter": first_chapter,
                                      "evidence_ids": self.evidence(first_chapter, quotes), **fields})
        return entity_id

    def event(self, chapter: int, event_type: str, title: str, description: str, participants: Iterable[str],
              quotes: Quotes, **fields) -> str:
        return self._add("events", {"type": event_type, "chapter": chapter, "title": title, "description": description,
                                    "participant_ids": list(participants), "evidence_ids": self.evidence(chapter, quotes),
                                    **fields})

    def state(self, entity_id: str, facet: str, action: str, chapter: int, after: Any, reason: str, quotes: Quotes,
              *, before: Any = None, note: str | None = None, confidence: str = "explicit", **fields) -> str:
        return self._add("state_changes", {"entity_id": entity_id, "facet": facet, "action": action, "chapter": chapter,
                                           "before": state_value(before), "after": state_value(after, note),
                                           "reason": reason, "evidence_ids": self.evidence(chapter, quotes),
                                           "confidence": confidence, **fields})

    def relation(self, source: str, target: str, relation_type: str, valid_from: int, quotes: Quotes, *,
                 status: str = "active", **fields) -> str:
        return self._add("relations", {"source_id": source, "target_id": target, "relation_type": relation_type,
                                       "valid_from": valid_from, "status": status,
                                       "evidence_ids": self.evidence(valid_from, quotes), **fields})

    def observe_relation(self, relation_id: str, chapter: int, description: str, quotes: Quotes, *,
                         stance: str | None = None, status: str | None = None, valid_to: int | None = None,
                         base: Mapping[str, Any] | None = None) -> str:
        """A later development inside an existing relation: an attitude shift, a status change, an ending.

        When the relation was declared in this fragment the observation is appended to it; otherwise
        `base` (source_id, target_id, relation_type, valid_from, status) restates the relation under the
        same ID and the merge folds the observation into the canonical episode.
        """
        observation = {"chapter": chapter, "description": description, "evidence_ids": self.evidence(chapter, quotes)}
        for key, value in (("stance", stance), ("status", status), ("valid_to", valid_to)):
            if value is not None:
                observation[key] = value
        record = next((r for r in self.data["relations"] if r["id"] == relation_id), None)
        if record is None:
            if base is None:
                raise ValueError(f"{relation_id} is not in this fragment; pass base= to restate it")
            record = {"id": relation_id, **dict(base), "evidence_ids": list(observation["evidence_ids"]), "observations": []}
            self.data["relations"].append(record)
        record.setdefault("observations", []).append(observation)
        if valid_to is not None:
            record["valid_to"] = valid_to
        return relation_id

    def trait(self, entity_id: str, facet: str, statement: str, chapter: int, quotes: Quotes,
              confidence: str = "explicit") -> str:
        return self._add("character_traits", {"entity_id": entity_id, "facet": facet, "statement": statement,
                                              "chapter": chapter, "evidence_ids": self.evidence(chapter, quotes),
                                              "confidence": confidence})

    def item_role(self, item_id: str, entity_id: str, role: str, valid_from: int, action: str, quotes: Quotes,
                  confidence: str = "explicit", **fields) -> str:
        return self._add("item_roles", {"item_id": item_id, "entity_id": entity_id, "role": role,
                                        "valid_from": valid_from, "action": action,
                                        "evidence_ids": self.evidence(valid_from, quotes), "confidence": confidence,
                                        **fields})

    def commitment(self, kind: str, promisors: Iterable[str], counterparties: Iterable[str], terms: str,
                   created_chapter: int, quotes: Quotes, *, status: str = "active", confidence: str = "explicit",
                   **fields) -> str:
        record = {"kind": kind, "promisor_ids": list(promisors), "counterparty_ids": list(counterparties),
                  "terms": terms, "created_chapter": created_chapter, "status": status,
                  "evidence_ids": self.evidence(created_chapter, quotes), "confidence": confidence,
                  "deadline_chapter": None, "deadline_story_time": None, "stake_ids": [],
                  "resolved_chapter": None, "resolution": None, "observations": []}
        record.update(fields)
        return self._add("commitments", record)

    def foreshadow(self, label: str, planted_chapter: int, observation: str, interpretation: str,
                   related: Iterable[str], quotes: Quotes, *, status: str = "open", confidence: str = "inferred",
                   kind: str = "foreshadowing", **fields) -> str:
        return self._add("foreshadowing", {"label": label, "kind": kind, "status": status,
                                           "planted_chapter": planted_chapter, "observation": observation,
                                           "interpretation": interpretation, "related_entity_ids": list(related),
                                           "evidence_ids": self.evidence(planted_chapter, quotes),
                                           "confidence": confidence, **fields})

    def intimate(self, chapter: int, act_type: str, description: str, quotes: Quotes, *,
                 initiators: Iterable[str] = (), recipients: Iterable[str] = (), observers: Iterable[str] = (),
                 consent: str = "uncertain", confidence: str = "explicit", **fields) -> str:
        return self._add("intimate_acts", {"chapter": chapter, "act_type": act_type, "description": description,
                                           "initiator_ids": list(initiators), "recipient_ids": list(recipients),
                                           "observer_ids": list(observers), "consent": consent,
                                           "confidence": confidence, "evidence_ids": self.evidence(chapter, quotes),
                                           **fields})

    def issue(self, severity: str, category: str, description: str, chapter: int, related: Iterable[str] = ()) -> str:
        return self._add("review_issues", {"severity": severity, "category": category, "description": description,
                                           "chapter": chapter, "related_ids": list(related)})

    def add(self, kind: str, record: Mapping[str, Any]) -> str:
        """Any other record kind (romance routes, level conversions …); gets a marked ID."""
        return self._add(kind, dict(record))

    # ---- audit card ----
    def card(self, chapter: int, *, summary: str, from_previous: str, sets_up: str,
             scenes: list[Mapping[str, Any]], presence: list[Mapping[str, Any]], functions: list[str],
             cliffhanger: str, pacing: str, summary_quotes: Quotes = None, line_quotes: Quotes = None,
             none_reasons: Mapping[str, str] | None = None, title: str | None = None) -> str:
        """The chapter's audit card; receipts are computed in build()."""
        card_id = f"cs_{self.marker}_{chapter:03d}"
        self.data["chapter_summaries"].append({
            "id": card_id, "chapter": chapter, **({"title": title} if title else {}),
            "summary": summary, "evidence_ids": self.evidence(chapter, summary_quotes),
            "continuity": {"from_previous": from_previous, "sets_up": sets_up},
            "scenes": [dict(s) for s in scenes], "presence": [dict(p) for p in presence],
            "narrative": {"functions": list(functions), "cliffhanger_type": cliffhanger, "pacing": pacing,
                          "quote_evidence_ids": self.evidence(chapter, line_quotes)},
        })
        self._none_reasons[chapter] = dict(none_reasons or {})
        return card_id

    def build(self) -> dict[str, Any]:
        missing: list[str] = []
        for card in self.data["chapter_summaries"]:
            chapter = card["chapter"]
            counts = item_counts(self.data, chapter, card)
            reasons = self._none_reasons.get(chapter, {})
            audit = {}
            for key, label in AUDIT_ITEMS.items():
                if counts[key]:
                    audit[key] = {"status": "recorded", "count": counts[key]}
                elif reasons.get(key, "").strip():
                    audit[key] = {"status": "none", "count": 0, "reason": reasons[key].strip()}
                else:
                    missing.append(f"第 {chapter} 章「{label}」({key})")
            card["audit"] = audit
        if missing:
            raise ValueError("these checklist items have no records and no none-reason: " + "；".join(missing))
        return self.data

    def write(self, path: Path) -> Path:
        from io_utils import atomic_write_text
        atomic_write_text(path, json.dumps(self.build(), ensure_ascii=False, indent=2) + "\n")
        return path
