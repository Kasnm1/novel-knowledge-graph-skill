#!/usr/bin/env python3
"""Decide which non-character entities deserve the character-style layout.

A talking, scheming spirit beast is not a `character` — retyping it would lose its
creature node shape, its colour, and its place under the creature filter. But it is
also not scenery: it negotiates, plans, warns, and drives events, so a flat
"creature" panel hides the most interesting entity in the book.

This module answers "which non-human entities act like people" from the graph alone,
so the answer is reproducible, auditable, and book-agnostic. It is the shared
definition used by both `build_dashboard.py` and `export_ai_context.py`; keeping one
implementation is what stops the page and the AI text from disagreeing.

Signals, in the order they matter:

- ``self_state`` — the graph records the entity changing its own identity, title,
  goal, emotion, knowledge, or affiliation. Scenery has no inner life; a health
  change alone (killed, injured) is deliberately *not* enough, because that is
  something done to an animal, not something an animal does.
- ``speaks`` — a source quotation attributes speech to the entity.
- ``social`` — a relationship whose other end is a character.
- ``events`` — participation in several events.
- ``foreshadow`` — named as the subject of several foreshadowing records.

The weights and threshold are tuned so that a creature with only combat or travel
participation scores zero, while a spirit beast with a recorded identity change
scores well clear. Run the module directly to print the full scoring table.

An explicit ``"is_agent": true`` in the data always wins (manual confirmation), and
``"is_agent": false`` is a veto for a false positive.

The type exclusion is a deliberate silence, not a judgement: ``excluded_candidates``
reports entities whose type keeps them out of this layout even though they speak and
change their own identity, so a person filed under the wrong type (a second
personality, an avatar, a disguised double) is caught instead of vanishing. Run the
module directly to see both lists.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path


# Types that are world objects rather than actors. Anything outside this set is a
# candidate, so a sentient sword or a bound spirit is considered without a code change.
NON_AGENT_TYPES = {"character", "level_axis", "location", "organization", "concept", "title"}

# Facets that describe an entity's own inner life or social standing. A change here is
# something the entity did or became, not something that happened to it.
SELF_FACETS = {"identity", "title", "goal", "emotion", "knowledge", "affiliation"}

SPEECH_VERBS = (
    "道", "说道", "说", "称", "问", "答道", "笑道", "喝道", "怒道", "冷声道",
    "提醒", "警告", "解释", "告诉", "表示", "承认", "介绍", "自述", "自称",
    "提议", "要求", "指出", "说明", "回答", "开口", "笑道", "声称", "宣称",
)
SPEECH_VERB_RE = "|".join(sorted(SPEECH_VERBS, key=len, reverse=True))
# The entity is the speaker, not the topic: the verb follows the name directly, or
# after a single comma (「天梦冰蚕，说道」).
#
# An earlier version allowed up to three arbitrary characters between the name and the
# verb. That matched the one-character verbs *inside ordinary words* — 阎王帖「何等霸道」,
# 「被称之为」, 「毫无疑问」, 「说(得)更贴切」 — and the Douluo run promoted twelve skills and
# items to the character layout on a phantom speech attribution (18 candidates, 12 of
# them false). A comma is the only thing that may sit between the name and the verb.
SPEAK_DIRECT_RE = re.compile(r"{name}(?:{verb})")
SPEAK_NEAR_RE = re.compile(r"{name}[，,]?(?:{verb})")
# A one-character verb is a speech verb only when the word around it says so. 「道：」
# 「道，」 「说「」 are attributions; 「霸道」 「味道」 「知道」 「称之为」 are not — and neither is
# 「说得更贴切」, where 得 marks 说 as a verb of construal rather than of speech.
SINGLE_CHAR_VERBS = frozenset(verb for verb in SPEECH_VERBS if len(verb) == 1)
NON_SPEECH_TAIL = frozenset("得")
SPEECH_VERBS_BY_LENGTH = tuple(sorted(SPEECH_VERBS, key=len, reverse=True))

WEIGHTS = {
    "speaks": 3,
    "self_state": 3,
    "social": 2,
    "events": 2,
    "foreshadow": 1,
}
# Agency must be *evidenced*, not merely plausible. Every skill and item in a book has a
# relation to whoever uses it, and several are the subject of foreshadowing, so those
# corroborating signals alone would promote half the equipment list. At least one core
# signal — the entity speaks, or the graph records it changing its own identity, title,
# goal, emotion, knowledge, or affiliation — is therefore required before the weighted
# score is even considered.
CORE_SIGNALS = {"speaks", "self_state"}
# Tuned on the Douluo run: the spirit beast scores 9, every scenery creature scores 0,
# and no skill or item clears the core gate at all.
THRESHOLD = 3

REASON_TEXT = {
    "speaks": "原文有对其发言的归属",
    "self_state": "有自主的身份／称号／目标／情绪／认知／隶属变化",
    "social": "与人物之间存在关系",
    "events": "参与多个事件",
    "foreshadow": "是多个伏笔的涉及对象",
}
EXPLICIT_REASON = "数据中显式标记为拟人主体"
VETO_REASON = "数据中显式排除"


def _names_of(entity: dict) -> list[str]:
    names = [str(entity.get("name") or "")]
    names.extend(str(alias) for alias in (entity.get("aliases") or []))
    # A one-character name would match half the corpus; require two characters.
    return sorted({name for name in names if len(name) >= 2}, key=len, reverse=True)


def _verb_of(match: re.Match[str]) -> str | None:
    """The speech verb that produced this match (longest-first, as the pattern is built)."""
    text = match.group(0)
    for verb in SPEECH_VERBS_BY_LENGTH:
        if text.endswith(verb):
            return verb
    return None


def _speech_match(pattern: str, quote: str) -> bool:
    """True when `pattern` matches somewhere that really introduces speech.

    A one-character verb followed by 得 is a verb of construal, not of speech
    (「模拟，说得更贴切一点就是…」 describes the skill; the skill does not speak).
    """
    for match in re.finditer(pattern, quote):
        verb = _verb_of(match)
        if verb in SINGLE_CHAR_VERBS and quote[match.end():match.end() + 1] in NON_SPEECH_TAIL:
            continue
        return True
    return False


def speech_hits(names: list[str], quotes: list[str]) -> int:
    """Count quotations in which one of these names is the speaker."""
    hits = 0
    for quote in quotes:
        if not any(name in quote for name in names):
            continue
        for name in names:
            escaped = re.escape(name)
            direct = SPEAK_DIRECT_RE.pattern.format(name=escaped, verb=SPEECH_VERB_RE)
            near = SPEAK_NEAR_RE.pattern.format(name=escaped, verb=SPEECH_VERB_RE)
            if _speech_match(direct, quote) or _speech_match(near, quote):
                hits += 1
                break
    return hits


def score_entity(entity: dict, graph: dict, quotes: list[str], entity_types: dict[str, str]) -> dict:
    """Return the signal breakdown for one candidate entity."""
    entity_id = entity["id"]
    signals: dict[str, int] = {}

    names = _names_of(entity)
    if names and speech_hits(names, quotes):
        signals["speaks"] = 1

    changes = [c for c in graph.get("state_changes", []) if c.get("entity_id") == entity_id]
    if any(c.get("facet") in SELF_FACETS for c in changes):
        signals["self_state"] = 1

    relations = [
        r for r in graph.get("relations", [])
        if entity_id in (r.get("source_id"), r.get("target_id"))
    ]
    social = 0
    for relation in relations:
        other = relation.get("target_id") if relation.get("source_id") == entity_id else relation.get("source_id")
        if entity_types.get(other) == "character":
            social += 1
    if social:
        signals["social"] = 1

    events = sum(1 for e in graph.get("events", []) if entity_id in (e.get("participant_ids") or []))
    if events >= 3:
        signals["events"] = 1

    foreshadow = sum(
        1 for f in graph.get("foreshadowing", [])
        if entity_id in (f.get("related_entity_ids") or [])
    )
    if foreshadow >= 2:
        signals["foreshadow"] = 1

    score = sum(WEIGHTS[key] for key in signals)
    return {
        "signals": signals,
        "score": score,
        "mentions": sum(1 for q in quotes if any(name in q for name in names)) if names else 0,
        "events": events,
        "foreshadow": foreshadow,
        "changes": len(changes),
        "relations": len(relations),
    }


def detect_agents(graph: dict) -> dict[str, dict]:
    """Return entity_id -> {"score", "reasons", "signals"} for every detected agent."""
    entities = [e for e in graph.get("entities", []) if isinstance(e, dict) and e.get("id")]
    entity_types = {e["id"]: e.get("type") for e in entities}
    quotes = [str(item.get("quote") or "") for item in graph.get("evidence", [])]

    detected: dict[str, dict] = {}
    for entity in entities:
        entity_id = entity["id"]
        explicit = entity.get("is_agent")
        if explicit is False:
            continue
        if explicit is True:
            detected[entity_id] = {"score": None, "signals": {}, "reasons": [EXPLICIT_REASON]}
            continue
        if entity.get("type") in NON_AGENT_TYPES:
            continue
        breakdown = score_entity(entity, graph, quotes, entity_types)
        if not (set(breakdown["signals"]) & CORE_SIGNALS):
            continue
        if breakdown["score"] >= THRESHOLD:
            reasons = [REASON_TEXT[key] for key in WEIGHTS if key in breakdown["signals"]]
            detected[entity_id] = {**breakdown, "reasons": reasons}
    return detected


def is_agent(entity: dict, detected: dict[str, dict] | None = None) -> bool:
    """True when an entity should get the character-style layout."""
    if entity.get("type") == "character":
        return True
    if entity.get("is_agent") is False:
        return False
    if entity.get("is_agent") is True:
        return True
    return bool(detected) and entity.get("id") in detected


def excluded_candidates(graph: dict) -> dict[str, dict]:
    """Non-agent-type entities that act like actors but are excluded by their type.

    Keeping `concept` and friends out of the agent layout is right — a quotation like
    「修仙，只能增强我们自己的体魄」 puts a speech verb next to 修仙 without 修仙 being
    a speaker. But the same exclusion is a trap for a *person* filed under the wrong
    type: a second personality, an avatar, or a disguised double typed as `concept` can
    never reach the character-style layout however much it speaks, decides, and takes
    over, and nothing in the pipeline says so. This report surfaces those cases so the
    decision (retype it, or confirm it is scenery) is made deliberately.

    Only entities with a ``self_state`` signal qualify: a bare speech-verb match is
    exactly the false positive the type list exists to suppress.
    """
    entities = [e for e in graph.get("entities", []) if isinstance(e, dict) and e.get("id")]
    entity_types = {e["id"]: e.get("type") for e in entities}
    quotes = [str(item.get("quote") or "") for item in graph.get("evidence", [])]

    excluded: dict[str, dict] = {}
    for entity in entities:
        if entity.get("is_agent") is not None:
            continue
        # `character` is in NON_AGENT_TYPES only because `detect_agents` must skip it
        # (it already gets the layout via `is_agent`); it is never "excluded".
        if entity.get("type") in {"character", "level_axis"}:
            continue
        if entity.get("type") not in NON_AGENT_TYPES:
            continue
        breakdown = score_entity(entity, graph, quotes, entity_types)
        if "self_state" not in breakdown["signals"]:
            continue
        if breakdown["score"] < THRESHOLD:
            continue
        excluded[entity["id"]] = breakdown
    return excluded


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--graph", required=True, type=Path)
    parser.add_argument("--output", type=Path, help="Optional path to write the detection report as JSON")
    args = parser.parse_args()

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    graph = json.loads(args.graph.resolve().read_text(encoding="utf-8"))
    detected = detect_agents(graph)

    names = {e["id"]: e.get("name", e["id"]) for e in graph.get("entities", []) if isinstance(e, dict)}
    print(f"detected {len(detected)} agent(s) among non-character entities:")
    for entity_id, info in detected.items():
        score = "explicit" if info["score"] is None else str(info["score"])
        print(f"  {names.get(entity_id, entity_id)}（{entity_id}） score={score}")
        for reason in info["reasons"]:
            print(f"      - {reason}")

    excluded = excluded_candidates(graph)
    if excluded:
        print()
        print(f"{len(excluded)} entity(ies) act like people but their type excludes them from this layout:")
        for entity_id, info in excluded.items():
            signals = "、".join(REASON_TEXT[key] for key in WEIGHTS if key in info["signals"])
            print(f"  {names.get(entity_id, entity_id)}（{entity_id}） score={info['score']}｜{signals}")
        print("  → 若其中某项其实是人物（第二人格／分身／伪装身份），请改类型或显式写 is_agent: true；")
        print("    若是抽象概念或场景，可显式写 is_agent: false 记录已核对。")
    if args.output:
        args.output.resolve().write_text(
            json.dumps(
                {
                    entity_id: {"name": names.get(entity_id, entity_id), **info}
                    for entity_id, info in detected.items()
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        print(f"\nwrote {args.output.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
