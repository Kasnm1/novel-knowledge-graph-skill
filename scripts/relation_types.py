"""Canonical relation types and their reader-facing groups.

`relation_type` used to be free-form, and a 999-chapter run ended with 42 spellings,
several of them the same relationship (`holds` / `possesses`, `mentor_of` /
`teacher_of`, `located_at` / `located_in`). A reader filter over 42 labels filters
nothing, and a renderer cannot group what it cannot recognise.

This module is the single definition, in the same shape as `event_types.py`:

- `RELATION_GROUPS` maps every recommended type to one reader-facing group. The group
  is what the dashboard filters and colours by; the type keeps the precise meaning.
- `RELATION_TYPE_ALIASES` folds spellings that mean the same relationship in every
  context onto the canonical type. Direction is preserved: an alias is only listed
  when source and target keep their roles.

Protocol-2 fragments must use a recommended type; legacy graphs are reported, not
rewritten.
"""

from __future__ import annotations

RELATION_GROUPS: dict[str, str] = {
    # 感情
    "lover_of": "romance", "spouse_of": "romance", "former_lover_of": "romance",
    "betrothed_to": "romance", "love_interest_of": "romance",
    # 亲属
    "parent_of": "family", "child_of": "family", "sibling_of": "family",
    "grandparent_of": "family", "uncle_of": "family", "step_parent_of": "family",
    "relative_of": "family", "sworn_sibling_of": "family",
    # 师徒
    "teacher_of": "mentorship", "student_of": "mentorship",
    # 盟友与恩情
    "friend_of": "ally", "close_friend_of": "ally", "ally_of": "ally",
    "companion_of": "ally", "colleague_of": "ally", "familiar_with": "ally",
    "benefactor_of": "ally", "savior_of": "ally", "protects": "ally",
    "supports": "ally", "owes_favor_to": "ally",
    # 敌对
    "enemy_of": "hostile", "rival_of": "hostile", "harmed": "hostile",
    # 势力与从属
    "member_of": "affiliation", "leader_of": "affiliation", "subordinate_of": "affiliation",
    "servant_of": "affiliation", "master_of": "affiliation", "serves": "affiliation",
    "employs": "affiliation", "employed_by": "affiliation", "affiliated_with": "affiliation",
    # 身份
    "alter_ego_of": "identity", "same_body_as": "identity", "disguised_as": "identity",
    # 物品、能力与知识
    "owns": "possession", "possesses": "possession", "uses": "possession",
    "learned": "possession", "knows_about": "possession", "controls": "possession",
    "contains": "possession", "crafted_from": "possession", "derived_from": "possession",
    # 地理与层级
    "located_in": "place", "part_of": "place", "subgroup_of": "place", "controlled_by": "place",
}

GROUP_LABELS: dict[str, str] = {
    "romance": "感情",
    "family": "亲属",
    "mentorship": "师徒",
    "ally": "盟友",
    "hostile": "敌对",
    "affiliation": "势力",
    "identity": "身份",
    "possession": "物品能力",
    "place": "地理层级",
    "other": "其他",
}

# Reversing source and target does not make a distinct relation for these types.
# Legacy spellings stay listed so graphs written before the canonical vocabulary
# still coalesce the same way.
SYMMETRIC_RELATION_TYPES: frozenset[str] = frozenset({
    "alter_ego_of", "same_body_as", "close_friend_of", "friend_of", "ally_of", "companion_of",
    "colleague_of", "familiar_with", "enemy_of", "rival_of", "sibling_of", "sworn_sibling_of",
    "relative_of", "spouse_of", "lover_of", "former_lover_of",
    # legacy spellings
    "dating", "mission_partner_of", "partner_of", "romantic_partner_of", "task_partner_of",
})

RELATION_TYPE_ALIASES: dict[str, str] = {
    "romantic_partner_of": "lover_of",
    "father_of": "parent_of",
    "mother_of": "parent_of",
    "stepmother_of": "step_parent_of",
    "stepfather_of": "step_parent_of",
    "mentor_of": "teacher_of",
    "instructed": "teacher_of",
    "holds": "possesses",
    "located_at": "located_in",
    "employer": "employs",
    "employee": "employed_by",
    "attacked": "harmed",
    "hurt": "harmed",
    "rescuer_of": "savior_of",
    "rescued": "savior_of",
    "saved": "savior_of",
}


def canonical_relation_type(value: object) -> str:
    text = str(value or "").strip()
    return RELATION_TYPE_ALIASES.get(text, text)


def relation_group(value: object) -> str:
    return RELATION_GROUPS.get(canonical_relation_type(value), "other")


def unknown_relation_types(relations: list[dict]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for rel in relations:
        raw = rel.get("relation_type") if isinstance(rel, dict) else None
        if canonical_relation_type(raw) not in RELATION_GROUPS:
            key = str(raw)
            counts[key] = counts.get(key, 0) + 1
    return counts
