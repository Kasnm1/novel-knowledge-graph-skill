#!/usr/bin/env python3
"""Canonical intimacy act types, shared by merge, validation and the dashboard.

`events[].type` carries one value for every intimate moment: `intimacy`. That is
the right granularity for an event list — it answers "what kind of scene was
this" — and the wrong granularity for the question a reader actually asks about
a harem book: *what happened, between whom, and was it consensual*. A kiss, a
grope, oral sex, intercourse, and rape all collapse into the same label there,
and `romance_routes.first_sex_chapter` records only the date of one act, never
its nature.

`intimate_acts` is the separate array that answers it. This module fixes its
vocabulary in one place, exactly as `event_types.py` does for event kinds:

- `INTIMACY_TYPES` is the set a pass should choose from: the *physical act*,
  named as specifically as the text supports.
- `INTIMACY_TYPE_ALIASES` folds labels that unambiguously mean the same act onto
  the canonical spelling, so a merge cannot keep both `boob_grope` and
  `groping_breast` for the same touch.
- `INTIMACY_GROUPS` is a display axis only. The group is never stored on the
  record; it is derived so the panel and the AI text can cluster the 20-odd acts
  into five readable bins.

Naming rules:
- Name the act, not the judgement. `rape` is an act; `victim` and `assaulted`
  are roles and verdicts and belong in `consent` / `participant` fields.
- Witnessing is an act. Seeing someone naked, walking in on a couple, or
  spying through a window is recorded with the *observer* as the participant —
  otherwise the scene simply vanishes from the graph.
- An attempt is its own act. `attempted_rape` is not `rape` with a qualifier;
  it is a different event with different consequences.
"""

from __future__ import annotations

# Canonical act -> reader-facing label. Keys are the machine values stored in
# `intimate_acts[].act_type`; labels are what the page and the AI text show.
INTIMACY_TYPES: dict[str, str] = {
    # 观看与暴露
    "witness_nudity": "目睹裸体",
    "witness_intimacy": "目睹他人亲密",
    "voyeurism": "偷窥",
    "exposure": "暴露身体",
    "peeping_attempt": "偷窥未遂",
    # 触碰
    "embrace": "拥抱",
    "kiss": "亲吻",
    "groping_breast": "摸胸",
    "groping_buttock": "摸臀",
    "groping_genital": "摸生殖器",
    "fondling": "爱抚",
    "stripping": "褪去衣物",
    # 性行为
    "manual_stimulation": "手交",
    "oral_sex": "口交",
    "intercourse": "性交",
    "anal_intercourse": "肛交",
    "masturbation": "自慰",
    "ejaculation": "射精",
    # 强迫与侵害
    "sexual_harassment": "性骚扰",
    "molestation": "猥亵",
    "attempted_rape": "强奸未遂",
    "rape": "强奸",
    # 其他
    "sexual_proposition": "性暗示或性要求",
    "other_intimate": "其他亲密行为",
}

# Display grouping only — derived, never stored on the record.
INTIMACY_GROUPS: dict[str, list[str]] = {
    "观看与暴露": [
        "witness_nudity", "witness_intimacy", "voyeurism", "exposure", "peeping_attempt",
    ],
    "触碰": [
        "embrace", "kiss", "groping_breast", "groping_buttock",
        "groping_genital", "fondling", "stripping",
    ],
    "性行为": [
        "manual_stimulation", "oral_sex", "intercourse",
        "anal_intercourse", "masturbation", "ejaculation",
    ],
    "强迫与侵害": [
        "sexual_harassment", "molestation", "attempted_rape", "rape",
    ],
    "其他": [
        "sexual_proposition", "other_intimate",
    ],
}

# Every label that must fold onto a canonical act. Each entry is a claim that
# the two labels name one act in every context — keep the list short.
INTIMACY_TYPE_ALIASES: dict[str, str] = {
    # 观看
    "see_naked": "witness_nudity",
    "saw_nudity": "witness_nudity",
    "nudity_seen": "witness_nudity",
    "peeping": "voyeurism",
    "peep": "voyeurism",
    "witness_sex": "witness_intimacy",
    # 触碰
    "hug": "embrace",
    "breast_grope": "groping_breast",
    "boob_grope": "groping_breast",
    "touch_breast": "groping_breast",
    "butt_grope": "groping_buttock",
    "ass_grope": "groping_buttock",
    "touch_genital": "groping_genital",
    "genital_grope": "groping_genital",
    "caress": "fondling",
    "undress": "stripping",
    # 性行为
    "handjob": "manual_stimulation",
    "footjob": "manual_stimulation",
    "oral": "oral_sex",
    "fellatio": "oral_sex",
    "cunnilingus": "oral_sex",
    "sex": "intercourse",
    "vaginal_intercourse": "intercourse",
    "anal": "anal_intercourse",
    "sodomy": "anal_intercourse",
    "cumshot": "ejaculation",
    # 强迫
    "harassment": "sexual_harassment",
    "indecent_assault": "molestation",
    "assault": "molestation",
    "rape_attempt": "attempted_rape",
    "sexual_assault": "rape",
    # 其他
    "proposition": "sexual_proposition",
}

# alias -> reader-facing label, for the display vocabulary.
INTIMACY_TYPE_LABELS: dict[str, str] = {
    **INTIMACY_TYPES,
    **{alias: INTIMACY_TYPES[canonical] for alias, canonical in INTIMACY_TYPE_ALIASES.items()},
}

# Consent / coercion. `forced` is the violent end of the scale and is
# deliberately separate from `coerced` (pressure, threat, or unequal power):
# a reader filtering for non-consensual acts needs both, and collapsing them
# hides the difference between "she was talked into it" and "she was held down".
# Single source of truth: validate_graph imports this set for romance_routes too,
# so one act and one route can never disagree about what `coerced` means.
# `uncertain` (not `unknown`) is the historical spelling and is kept for that
# reason — it is already written into existing graphs.
CONSENT_CONTEXTS: set[str] = {
    "mutual",            # 双方自愿
    "one_sided",         # 单方面主动，对方未表态
    "accidental",        # 意外发生
    "coerced",           # 受胁迫、受压力、权力不对等
    "forced",            # 暴力强迫、无法反抗
    "ability_induced",   # 受能力或术法影响
    "altered_state",     # 意识不清、醉酒、药物、变身状态
    "uncertain",         # 原文未交代
}

# Where the act ended, when the text supports it. Optional and only meaningful
# for acts that can conclude this way; leave the field off otherwise.
EJACULATION_SITES: dict[str, str] = {
    "internal": "体内",
    "oral": "口中",
    "external": "体外",
    "on_body": "身体上",
    "none": "未射",
    "unknown": "未交代",
}

# Participant roles. `observer_ids` is what makes a witnessed scene exist at all.
PARTICIPANT_ROLES: tuple[str, ...] = ("initiator_ids", "recipient_ids", "observer_ids")


def canonical_intimacy_type(value: object) -> str:
    """Return the canonical spelling of an intimacy act type."""
    text = str(value).strip()
    return INTIMACY_TYPE_ALIASES.get(text, text)


def group_of(act_type: object) -> str:
    """Return the display group for an act type, or 其他 when unknown."""
    text = canonical_intimacy_type(act_type)
    for group, members in INTIMACY_GROUPS.items():
        if text in members:
            return group
    return "其他"


def canonicalize_intimate_acts(acts: list[dict]) -> tuple[list[dict], list[str]]:
    """Fold alias act types onto canonical ones, in place.

    Returns the rewritten list plus one note per folded record, so the merge can
    report what it changed instead of rewriting authored data silently.
    """
    notes: list[str] = []
    for record in acts:
        if not isinstance(record, dict):
            continue
        raw = record.get("act_type")
        if raw is None:
            continue
        canonical = canonical_intimacy_type(raw)
        if canonical != raw:
            record["act_type"] = canonical
            notes.append(f"{record.get('id')}：{raw} → {canonical}")
    return acts, notes


def unknown_intimacy_types(acts: list[dict]) -> dict[str, int]:
    """Act types actually used that are outside the canonical set, with counts.

    Reported rather than rewritten — a book may have an act the set does not
    name, and the decision to keep it belongs to review, not to a merge.
    """
    counts: dict[str, int] = {}
    for record in acts:
        if not isinstance(record, dict):
            continue
        value = record.get("act_type")
        if value is None:
            continue
        # 先折叠：`boob_grope` 是 `groping_breast` 的别名，合并后会归一，
        # 不能在报告里把它当成规范集外的类型。
        text = canonical_intimacy_type(value)
        if text not in INTIMACY_TYPES:
            counts[text] = counts.get(text, 0) + 1
    return counts


def has_participant(record: dict) -> bool:
    """True when at least one participant role names somebody.

    An act with nobody in it cannot be placed on a timeline or a relationship.
    """
    return any(bool(record.get(role)) for role in PARTICIPANT_ROLES)
