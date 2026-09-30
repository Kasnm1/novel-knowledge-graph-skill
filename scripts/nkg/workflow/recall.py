"""Deterministic recall candidates for one audited chapter.

The verifier is only as good as what it is asked to look at. These candidates
point it at the places a chapter audit most often misses, measured on a
999-chapter run: named characters on stage with no record, and sentences that
announce a death, an injury, money, a breakthrough, an item changing hands, a
promise, a secret or an intimate act while the chapter carries no record of that
kind. A candidate is review work — the verifier answers each one `recorded`,
`not_applicable` or `missed` — never a fact.
"""

from __future__ import annotations

import re
from typing import Any, Iterable, Mapping

from nkg.core.records import records

SENTENCE = re.compile(r"[^。！？!?\n]+[。！？!?]?")

# kind -> (marker pattern, record kinds that would satisfy it)
KEYWORD_GROUPS: dict[str, tuple[re.Pattern[str], tuple[str, ...]]] = {
    "death": (re.compile(r"死了|身亡|毙命|丧命|断气|气绝|杀了|斩杀|击杀"), ("mortality", "health")),
    "injury": (re.compile(r"受伤|重伤|吐血|昏迷|骨折|中毒"), ("health",)),
    "money": (re.compile(r"\d+万|[一二三四五六七八九十百千]+万|[亿]|块钱|灵石|交易|买下|卖给|支付|赔偿"), ("transaction",)),
    "breakthrough": (re.compile(r"突破|晋级|晋升|提升到|踏入|境界|修为大增"), ("level",)),
    "item": (re.compile(r"得到|获得|夺走|抢走|送给|赠予|交给|丢失|取出"), ("item_role", "possession")),
    "promise": (re.compile(r"发誓|立誓|答应|承诺|约定|赌约|保证"), ("commitment",)),
    "secret": (re.compile(r"秘密|真相|原来是|竟然是|身份暴露|识破"), ("knowledge", "information")),
    "intimacy": (re.compile(r"吻|亲了|抱住|搂住|爱抚|脱下|上床"), ("intimate_act",)),
}


def chapter_record_kinds(graph: Mapping[str, Any], chapter: int) -> tuple[set[str], set[str]]:
    """(record kinds present in the chapter, entity IDs carrying any record in it)."""
    kinds: set[str] = set()
    touched: set[str] = set()
    for ev in records(graph.get("events")):
        if ev.get("chapter") != chapter:
            continue
        touched.update(ev.get("participant_ids") or [])
        for facet in ("combat", "mortality", "transaction", "information"):
            if ev.get(facet):
                kinds.add(facet)
    for sc in records(graph.get("state_changes")):
        if sc.get("chapter") == chapter:
            kinds.add(str(sc.get("facet")))
            touched.add(sc.get("entity_id"))
    for ir in records(graph.get("item_roles")):
        if chapter in (ir.get("valid_from"), ir.get("valid_to")):
            kinds.add("item_role")
            touched.update({ir.get("item_id"), ir.get("entity_id")})
    for c in records(graph.get("commitments")):
        if chapter in (c.get("created_chapter"), c.get("resolved_chapter")):
            kinds.add("commitment")
    for a in records(graph.get("intimate_acts")):
        if a.get("chapter") == chapter:
            kinds.add("intimate_act")
            touched.update((a.get("initiator_ids") or []) + (a.get("recipient_ids") or []) + (a.get("observer_ids") or []))
    for r in records(graph.get("relations")):
        if chapter in (r.get("valid_from"), r.get("valid_to")):
            touched.update({r.get("source_id"), r.get("target_id")})
    for t in records(graph.get("character_traits")):
        if t.get("chapter") == chapter:
            touched.add(t.get("entity_id"))
    for cs in records(graph.get("chapter_summaries")):
        if cs.get("chapter") == chapter:
            touched.update(p.get("entity_id") for p in cs.get("presence") or [] if isinstance(p, dict))
    return kinds, touched


def recall_candidates(graph: Mapping[str, Any], chapter: int, text: str, *, min_name_hits: int = 3,
                      max_per_kind: int = 5) -> list[dict[str, Any]]:
    kinds, touched = chapter_record_kinds(graph, chapter)
    out: list[dict[str, Any]] = []

    def add(kind: str, snippet: str, reason: str, entity_id: str | None = None) -> None:
        out.append({"id": f"rc_{chapter:04d}_{len(out) + 1:03d}", "chapter": chapter, "kind": kind,
                    "entity_id": entity_id, "snippet": snippet.strip()[:120], "reason": reason, "verdict": None})

    for entity in records(graph.get("entities")):
        if entity.get("type") != "character" or entity.get("id") in touched:
            continue
        forms = [f for f in [entity.get("name"), *(entity.get("aliases") or [])] if isinstance(f, str) and len(f) >= 2]
        hits = sum(text.count(f) for f in forms)
        if hits >= min_name_hits:
            where = next((m.group(0) for m in SENTENCE.finditer(text) if any(f in m.group(0) for f in forms)), "")
            add("presence", where, f"「{entity.get('name')}」在本章出现 {hits} 次，却没有任何记录", entity["id"])

    sentences = [m.group(0) for m in SENTENCE.finditer(text)]
    for kind, (pattern, satisfied_by) in KEYWORD_GROUPS.items():
        if kinds & set(satisfied_by):
            continue
        shown = 0
        for sentence in sentences:
            if pattern.search(sentence):
                add(kind, sentence, f"原文有「{pattern.search(sentence).group(0)}」，本章没有 {'/'.join(satisfied_by)} 记录")
                shown += 1
                if shown >= max_per_kind:
                    break

    summary = next((s.get("summary") for s in records(graph.get("chapter_summaries")) if s.get("chapter") == chapter), "")
    for entity in records(graph.get("entities")):
        name = entity.get("name")
        if (entity.get("type") == "character" and isinstance(name, str) and len(name) >= 2 and summary
                and name in summary and entity.get("id") not in touched
                and not any(c["entity_id"] == entity["id"] for c in out)):
            add("summary_named", summary, f"梗概点名「{name}」，本章却没有他的记录", entity["id"])
    return out


def apply_verdicts(candidates: Iterable[Mapping[str, Any]], verdicts: Mapping[str, str]) -> dict[str, int]:
    """Tally verifier answers; a candidate without an answer stays open."""
    tally = {"recorded": 0, "not_applicable": 0, "missed": 0, "open": 0}
    for candidate in candidates:
        verdict = verdicts.get(candidate["id"])
        tally[verdict if verdict in tally else "open"] += 1
    return tally
