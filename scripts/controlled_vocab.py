#!/usr/bin/env python3
"""Central controlled vocabularies for the novel knowledge-graph expansion.

Keep reusable semantic axes here instead of minting new top-level arrays or event
``type`` values.  Unknown values are data-contract failures for new work; legacy
runs can be audited before backfill.
"""
from __future__ import annotations

SKILL_CATEGORIES: dict[str, str] = {
    "movement": "身法",
    "cultivation": "心法/修炼功法",
    "attack": "攻击",
    "defense": "防御",
    "control": "控制",
    "support": "辅助",
    "healing": "治疗",
    "perception": "感知",
    "crafting": "炼制",
    "formation": "阵法",
    "passive": "被动",
    "transformation": "变身/状态",
    "summoning": "召唤",
    "utility": "通用",
    "unresolved": "待分类",
}

CONCEPT_CATEGORIES: dict[str, str] = {
    "secret": "秘密",
    "rule": "规则",
    "prohibition": "禁令",
    "curse": "诅咒",
    "currency": "货币",
    "recipe": "配方",
    "world_lore": "世界观",
    "unresolved": "待分类",
}

COMBAT_OUTCOMES: frozenset[str] = frozenset({
    "victory", "defeat", "draw", "escaped", "interrupted", "uncertain",
})
COMBAT_KINDS: frozenset[str] = frozenset({
    "duel", "group_battle", "ambush", "siege", "trial", "sparring", "uncertain",
})
COMBAT_RESOLUTIONS: frozenset[str] = frozenset({
    "decisive", "technical", "withdrawal", "interrupted", "uncertain",
})

COMMITMENT_KINDS: frozenset[str] = frozenset({
    "promise", "oath", "agreement", "wager", "revenge_vow",
})
COMMITMENT_STATUSES: frozenset[str] = frozenset({
    "active", "fulfilled", "partially_fulfilled", "broken", "expired", "waived", "uncertain",
})

CLIFFHANGER_TYPES: frozenset[str] = frozenset({
    "crisis", "suspense", "reversal", "revelation", "breakthrough", "romance", "none", "uncertain",
})
PAYOFF_KINDS: frozenset[str] = frozenset({
    "face_slap", "reversal", "revenge", "breakthrough", "status_gain",
    "wealth_gain", "romance", "revelation", "other",
})
INFORMATION_MODES: frozenset[str] = frozenset({
    "reveal", "leak", "overheard", "confession", "deception", "exposure", "discovery", "uncertain",
})

RESOURCE_RARITIES: frozenset[str] = frozenset({
    "common", "uncommon", "rare", "very_rare", "unique", "unresolved",
})
RESOURCE_SUPPLY: frozenset[str] = frozenset({
    "repeatable", "limited", "unique", "unresolved",
})

EVENT_TAGS: frozenset[str] = frozenset({
    "milestone", "wager", "contest", "transaction", "rule_enforcement",
    "rule_violation", "secret_leak", "identity_reveal", "payoff",
    "first_visit", "territory_change", "resource_gain", "resource_spend",
})

RELATION_EXTENSION_TYPES: frozenset[str] = frozenset({
    "owes_favor_to", "controlled_by", "crafted_from", "derived_from",
})

LEVEL_FACET_HINTS: frozenset[str] = frozenset({
    "level", "等级", "境界", "修为", "cultivation", "realm", "rank", "阶位", "层次",
})


def category_ids(value: object) -> list[str]:
    """Extract category IDs from current entity ``categories`` representations."""
    if not isinstance(value, list):
        return []
    result: list[str] = []
    for entry in value:
        if isinstance(entry, str):
            text = entry.strip()
        elif isinstance(entry, dict):
            raw = entry.get("id")
            text = raw.strip() if isinstance(raw, str) else ""
        else:
            text = ""
        if text and text not in result:
            result.append(text)
    return result


def resource_tag_parts(tags: object) -> tuple[str | None, str | None, list[str]]:
    """Return ``(rarity, supply, malformed)`` from item tags.

    Only tags under the reserved ``rarity/`` and ``supply/`` namespaces are
    interpreted; unrelated book-specific tags remain untouched.
    """
    rarity = None
    supply = None
    malformed: list[str] = []
    if not isinstance(tags, list):
        return rarity, supply, malformed
    for tag in tags:
        if not isinstance(tag, str):
            continue
        if tag.startswith("rarity/"):
            value = tag.split("/", 1)[1]
            if value not in RESOURCE_RARITIES:
                malformed.append(tag)
            elif rarity is not None and rarity != value:
                malformed.append(tag)
            else:
                rarity = value
        elif tag.startswith("supply/"):
            value = tag.split("/", 1)[1]
            if value not in RESOURCE_SUPPLY:
                malformed.append(tag)
            elif supply is not None and supply != value:
                malformed.append(tag)
            else:
                supply = value
    return rarity, supply, malformed
