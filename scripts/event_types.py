#!/usr/bin/env python3
"""Canonical event types, shared by merge, validation and the dashboard.

Event `type` is a free-form string in the schema, and that is how a run ends up
with 55 types for 112 events — 35 of them used once. Two extraction passes have
no way to converge on the same label, and a type facet whose groups hold one
event each cannot filter anything.

This module fixes the vocabulary in one place, exactly as `attribute_keys.py`
does for attribute keys:

- `RECOMMENDED_EVENT_TYPES` is the set a pass should choose from. It is the
  *kind* of thing that happened. Narrative role ("climax", "turning point",
  "cliffhanger", "plot") is a different axis and belongs in `tags`, not here.
- `EVENT_TYPE_ALIASES` folds labels that unambiguously mean the same kind onto
  the canonical spelling, so a merge cannot keep both `reveal` and
  `information_reveal` for the same kind of event.

Only add an alias when the two labels name the same kind of event in every
context. A label that merely looks related stays untouched, and a type outside
the recommended set is reported rather than rewritten.
"""

from __future__ import annotations

# Canonical event kind -> reader-facing label. The keys are the machine values
# stored in `events[].type`; the labels are what the page and the AI text show.
RECOMMENDED_EVENT_TYPES: dict[str, str] = {
    "revelation": "真相揭示",
    "conflict": "冲突对峙",
    "battle": "战斗",
    "killing": "杀伐",
    "conspiracy": "阴谋算计",
    "revenge": "复仇",
    "investigation": "调查探查",
    "accusation": "指控问罪",
    "punishment": "惩处责罚",
    "expulsion": "驱逐逐出",
    "agreement": "约定结盟",
    "aid": "救助支援",
    "request": "请求委托",
    "gift": "赠予馈赠",
    "transfer": "转移移交",
    "ceremony": "仪式典礼",
    "announcement": "宣布公告",
    "dialogue": "对话交谈",
    "encounter": "相遇遭遇",
    "supernatural_encounter": "异象遭遇",
    "departure": "离别出行",
    "training": "修习历练",
    "breakthrough": "突破进阶",
    "transformation": "形态异变",
    "affliction": "中毒疾患",
    "survival": "求生脱险",
    "intimacy": "亲密互动",
    "relationship_event": "关系变化",
    "identity": "身份暴露",
    "decision": "抉择决断",
    "preparation": "筹谋准备",
    "backstory": "背景交代",
    "other": "其他",
}

# Every label that must fold onto a canonical type. Keep this list short and
# obvious: each entry is a claim that the two labels name one kind of event.
EVENT_TYPE_ALIASES: dict[str, str] = {
    # 「同一件事变得可知」的各种写法
    "reveal": "revelation",
    "information_reveal": "revelation",
    "secret_overheard": "revelation",
    "discovery": "revelation",
    # 打斗
    "combat": "battle",
    # 对峙类
    "confrontation": "conflict",
    "incident": "conflict",
    # 算计类
    "scheme": "conspiracy",
    "political_event": "conspiracy",
    # 伤病类
    "medical_event": "affliction",
    "injury": "affliction",
    # 亲密与关系
    "intimate_moment": "intimacy",
    "intimate_contact": "intimacy",
    "relationship": "relationship_event",
    # 相遇
    "meeting": "encounter",
    "arrival": "encounter",
    # 修习
    "cultivation": "training",
}

# alias -> reader-facing label, for the display vocabulary.
EVENT_TYPE_LABELS: dict[str, str] = {
    **RECOMMENDED_EVENT_TYPES,
    **{alias: RECOMMENDED_EVENT_TYPES[canonical] for alias, canonical in EVENT_TYPE_ALIASES.items()},
}


def canonical_event_type(value: object) -> str:
    """Return the canonical spelling of an event type."""
    text = str(value).strip()
    return EVENT_TYPE_ALIASES.get(text, text)


def canonicalize_event_types(events: list[dict]) -> tuple[list[dict], list[str]]:
    """Fold alias event types onto canonical ones, in place.

    Returns the rewritten list plus one note per folded record, so the merge can
    report what it changed instead of rewriting authored data silently.
    """
    notes: list[str] = []
    for record in events:
        if not isinstance(record, dict):
            continue
        raw = record.get("type")
        if raw is None:
            continue
        canonical = canonical_event_type(raw)
        if canonical != raw:
            record["type"] = canonical
            notes.append(f"{record.get('id')}：{raw} → {canonical}")
    return events, notes


def unknown_event_types(events: list[dict]) -> dict[str, int]:
    """Types actually used that are outside the recommended set, with counts.

    Reported rather than rewritten: a label outside the set may be a legitimate
    book-specific kind, and the decision to keep or rename it belongs to review.
    """
    counts: dict[str, int] = {}
    for record in events:
        if not isinstance(record, dict):
            continue
        value = record.get("type")
        if value is None:
            continue
        text = str(value).strip()
        if text not in RECOMMENDED_EVENT_TYPES:
            counts[text] = counts.get(text, 0) + 1
    return counts
