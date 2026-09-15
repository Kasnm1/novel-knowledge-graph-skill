#!/usr/bin/env python3
"""Cross-axis level conversion vocabulary, shared by merge, validation and both renderers.

A book rarely uses one ranked system. It uses several at once, and the text itself
states how they line up: 「修罗王……十颗星的实力，明显一个真正突破了人阶，走入地阶」,
「A 级猎人相当于修仙者中的地阶」, 「每修炼到三颗星璇即打开一层心法」. Those statements
are the only thing that lets a reader convert between systems, and left in prose they
are invisible to any tool — a level warehouse can list the ladders but cannot answer
"what is a 修罗将军 in 星".

This module is the single definition of the relation vocabulary, exactly as
`intimacy_types.py` is for acts and `event_types.py` is for event labels. Merge folds
synonyms onto it and both renderers take their labels from it, so the page and the AI
text cannot disagree about what a relation means.

Two things this module deliberately does **not** do:

* It never invents an equivalence. A conversion record is an analyst's reading of a
  sentence, so it carries `evidence_ids` and a `confidence` like any other record, and
  a pair the text does not state must be presented as derived, not attested.
* It never orders axes. Two axes may agree that higher is stronger and still not be
  comparable at all; the relation says how they compare, and the endpoints carry the
  actual values.
"""

from __future__ import annotations

# Canonical relation -> reader-facing label. The canonical spelling stays English
# because it is a machine key that is never printed raw; labels are what a reader sees.
CONVERSION_RELATIONS: dict[str, str] = {
    # The two axes measure the same thing on the same scale.
    # 「妖、魔、鬼、灵兽……其战力以「星」直接折算，与修仙者的星级同尺」
    "equals": "等同",
    # The text hedges: 大约 / 大体 / 差不多 / 相当于.
    # 「修罗将军……大概有九颗星的实力，准地阶」
    "approximately_equals": "约等于",
    # A floor, not an equivalence: the `from` endpoint needs at least the `to` value.
    # 「第三掌山岚按常理须四星方可修炼」
    "at_least": "至少／门槛",
    # The two sides only line up at the granularity of a band, because one axis is
    # named tiers with no numbers. 「A 级猎人相当于修仙者中的地阶」
    "band_equivalent": "档位对应",
    # A stated ratio rather than a value. 「每修炼到三颗星璇即打开一层心法」 — the rule
    # converts, but no single pair of numbers is the equivalence.
    "scales_with": "按比例推进",
}

# Which side a value has to be read from when the relation is directional.
# `at_least` is the only asymmetric relation: `from` requires `to`, never the reverse.
ASYMMETRIC_RELATIONS: frozenset[str] = frozenset({"at_least"})

# Synonyms seen in fragments and in earlier conventions. Folded onto the canonical set
# by `canonical_relation` so one meaning cannot render under two labels.
CONVERSION_RELATION_ALIASES: dict[str, str] = {
    "same": "equals",
    "same_as": "equals",
    "equal": "equals",
    "equivalent": "equals",
    "is": "equals",
    "approx": "approximately_equals",
    "about": "approximately_equals",
    "roughly": "approximately_equals",
    "roughly_equals": "approximately_equals",
    "approximately": "approximately_equals",
    "requires": "at_least",
    "require": "at_least",
    "minimum": "at_least",
    "floor": "at_least",
    "prerequisite": "at_least",
    "band": "band_equivalent",
    "tier_equivalent": "band_equivalent",
    "band_maps": "band_equivalent",
    "proportional": "scales_with",
    "proportional_to": "scales_with",
    "ratio": "scales_with",
    "rate": "scales_with",
}

# Endpoint fields. An endpoint always names its axis; it then carries a point
# (`value`), a band (`range`), a wording (`label`), or some combination.
ENDPOINT_KEYS: tuple[str, ...] = ("axis_id", "value", "label", "range")

# Required on every record.
REQUIRED_KEYS: tuple[str, ...] = ("id", "chapter", "from", "to", "relation", "description", "evidence_ids")


def canonical_relation(value: object) -> str:
    """Fold a relation spelling onto the canonical set, leaving unknown values alone."""
    if value is None:
        return ""
    text = str(value).strip()
    if text in CONVERSION_RELATIONS:
        return text
    return CONVERSION_RELATION_ALIASES.get(text.lower().replace(" ", "_"), text)


def canonicalize_level_conversions(records: list[dict]) -> tuple[list[dict], list[str]]:
    """Normalize relation spellings, reporting each fold so the merge is auditable."""
    notes: list[str] = []
    for record in records:
        if not isinstance(record, dict):
            continue
        original = record.get("relation")
        folded = canonical_relation(original)
        if folded and folded != str(original).strip():
            record["relation"] = folded
            notes.append(f"{record.get('id')}: relation {original} -> {folded}")
    return records, notes


def unknown_relations(records: list[dict]) -> dict[str, int]:
    """Relation values outside the canonical set, counted for a single-line report."""
    counts: dict[str, int] = {}
    for record in records:
        if not isinstance(record, dict):
            continue
        value = canonical_relation(record.get("relation"))
        if value and value not in CONVERSION_RELATIONS:
            counts[value] = counts.get(value, 0) + 1
    return counts


def endpoint_has_position(endpoint: object) -> bool:
    """True when an endpoint pins something: a number, a band, or at least a wording.

    An endpoint like `{"axis_id": "axis_star_rank"}` alone says nothing and cannot be
    converted with, so validation rejects it.
    """
    if not isinstance(endpoint, dict):
        return False
    if endpoint.get("value") is not None:
        return True
    if isinstance(endpoint.get("range"), list) and endpoint["range"]:
        return True
    label = endpoint.get("label")
    return isinstance(label, str) and bool(label.strip())


def range_is_sane(value: object) -> bool:
    """A band is two numbers, low first. Acceptor must match validate_graph's wording."""
    if not isinstance(value, list) or len(value) != 2:
        return False
    low, high = value
    for item in (low, high):
        if isinstance(item, bool) or not isinstance(item, (int, float)):
            return False
    return low <= high
