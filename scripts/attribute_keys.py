#!/usr/bin/env python3
"""Canonical attribute keys, shared by merge, validation and both renderers.

Fragments are extracted independently, so the same fact can arrive under the
book's own wording ("性别") from one fragment and under the English schema
spelling ("gender") from another. Left alone, the merge keeps both and every
reader-facing surface renders the same attribute twice. This module is the
single place that decides which spelling is canonical, so merge, validation,
the page and the AI text cannot disagree about it.

The canonical spelling is the book's own wording, matching the project rule that
stored attribute content is displayed verbatim — nothing has to be translated on
the way out. English schema spellings are aliases that fold onto it.

Only add an alias when the two spellings mean the same thing for every entity in
the graph. A label that merely looks similar stays untouched.
"""

from __future__ import annotations

# Canonical spelling (book's language) -> the English schema spelling it replaces.
CANONICAL_ATTRIBUTE_KEYS: dict[str, str] = {
    "单位": "unit",
    "下限": "min",
    "上限": "max",
    "越高越强": "higher_is_more_advanced",
    "档位": "tiers",
    "区间": "range",
    "名称": "label",
    "分级依据": "definition",
    "备注": "note",
    "类型": "type",
    "属性": "attribute",
    "类别": "category",
    "性别": "gender",
    "武魂": "martial_soul",
    "物种": "species",
    "出身": "origin",
    "种族": "race",
    "数值": "value",
}

# Every spelling that must fold onto a canonical key.
ATTRIBUTE_KEY_ALIASES: dict[str, str] = {
    english: canonical for canonical, english in CANONICAL_ATTRIBUTE_KEYS.items()
}

# Chinese synonyms seen in the corpus. Same failure mode as an English spelling:
# one fragment writes 分类 for the species category while the canonical key is
# 类别, and the reader would see one fact under two labels. Only add an entry when
# the two words answer the same question for every entity that uses them.
ATTRIBUTE_KEY_ALIASES.update({
    "分类": "类别",
})

# key -> reader-facing label, for the display vocabulary. Canonical keys are
# already in the book's language, so they map to themselves; the alias entries
# only exist so a stray English key still renders in Chinese instead of leaking.
ATTRIBUTE_LABELS: dict[str, str] = {
    **{canonical: canonical for canonical in CANONICAL_ATTRIBUTE_KEYS},
    **ATTRIBUTE_KEY_ALIASES,
}


def canonical_key(key: object) -> str:
    """Return the canonical spelling of an attribute key."""
    text = str(key).strip()
    return ATTRIBUTE_KEY_ALIASES.get(text, text)


def _prefer(left: object, right: object) -> object:
    """Choose the more informative of two values recorded for one attribute."""
    if left in (None, "", [], {}):
        return right
    if right in (None, "", [], {}):
        return left
    if left == right:
        return left
    # Both spellings carry a value and they differ. The longer string is the one
    # that kept its qualifier ("本体武魂（疑似）" over "本体武魂"), so it wins.
    if isinstance(left, str) and isinstance(right, str):
        return right if len(right) > len(left) else left
    return left


def canonicalize_attributes(attributes: object) -> tuple[dict, list[str]]:
    """Fold alias spellings onto canonical keys.

    Returns the rewritten mapping plus a note per collapsed pair, so the merge
    can report what it folded instead of dropping the duplicate silently.
    """
    if not isinstance(attributes, dict):
        return {}, []
    result: dict = {}
    seen: dict[str, str] = {}
    notes: list[str] = []
    for raw_key, value in attributes.items():
        key = canonical_key(raw_key)
        spelling = str(raw_key)
        if key in result:
            chosen = _prefer(result[key], value)
            first = seen[key]
            where = f"{first}／{spelling}" if first != spelling else f"{key} 重复出现"
            notes.append(f"{where} 合并为 {key}，保留 {chosen!r}")
            result[key] = chosen
        else:
            result[key] = value
            seen[key] = spelling
    return result, notes
