"""The whole-book survey: a skeleton read before any chapter is audited.

Deep chapter audits used to discover the book as they went: a supporting
character got a second ID because the pass that met him did not know he existed,
two passes each created the same level ladder under different names, and nobody
ever wrote down the story arcs. The survey fixes that order. A cheap, fast model
reads the whole book once and fills `survey.json`:

- `cast`: named characters (and key organizations, places, items) with aliases,
  a proposed ID slug and a tier (protagonist / core / major / minor);
- `level_systems`: every ranked progression the book uses, with its tiers;
- `arcs`: volume / arc / sub-arc intervals — the audit's lanes;
- `outline`: one line per chapter;
- `non_narrative`: author notes, announcements, duplicate chapters.

`build_scaffold` gives that model deterministic hints to start from (chapter
sizes, likely non-narrative chapters, frequent speakers, level-like phrases);
`validate_survey` checks what it returns; `seed_registry` turns the cast into
issued IDs before the first chapter worker starts. The survey is a plan, not a
fact source: chapter audits confirm or correct it with evidence.
"""

from __future__ import annotations

import collections
import re
from typing import Any, Iterable, Mapping

from nkg.workflow.registry import SLUG, TYPE_PREFIXES, IdRegistry

TIERS = ("protagonist", "core", "major", "minor")
NOTE_MARKERS = re.compile(r"月票|推荐票|求票|请假|上架|感言|更新时间|加更|单章|作者的话|公告")
SPEAKER = re.compile(r"([一-龥]{2,3}?)(?:冷笑道|笑道|说道|问道|喝道|怒道|叹道|说|道|问)[：:，,]?[“「\"]")
LEVEL_PHRASE = re.compile(r"[一-龥]{1,4}(?:境|期|阶|级|品|重|星|层)(?:初期|中期|后期|巅峰|大圆满)?")


def build_scaffold(chapter_rows: Iterable[Mapping[str, Any]], *, top_speakers: int = 150,
                   top_levels: int = 60) -> dict[str, Any]:
    rows = sorted(chapter_rows, key=lambda r: r["chapter"])
    speakers: collections.Counter[str] = collections.Counter()
    first_seen: dict[str, int] = {}
    levels: collections.Counter[str] = collections.Counter()
    chapters = []
    sizes = [len(str(r.get("text") or "")) for r in rows]
    median = sorted(sizes)[len(sizes) // 2] if sizes else 0
    for row, size in zip(rows, sizes):
        text = str(row.get("text") or "")
        for name in SPEAKER.findall(text):
            speakers[name] += 1
            first_seen.setdefault(name, row["chapter"])
        levels.update(LEVEL_PHRASE.findall(text))
        chapters.append({
            "chapter": row["chapter"], "title": row.get("title"), "chars": size,
            "likely_non_narrative": bool(size < median * 0.35 and NOTE_MARKERS.search(text)),
        })
    return {
        "schema": "survey-scaffold/v1",
        "chapters": chapters,
        "frequent_speakers": [{"name": n, "speech_hits": c, "first_chapter": first_seen[n]}
                              for n, c in speakers.most_common(top_speakers)],
        "level_phrases": [{"phrase": p, "hits": c} for p, c in levels.most_common(top_levels)],
        "instructions": "Fill survey.json (schema survey/v1): cast with tiers and pinyin slugs, level_systems, "
                        "arcs (volume/arc/sub-arc with chapter ranges), one-line outline per chapter, non_narrative. "
                        "Speaker and level lists are hints with false positives; keep only what the text supports.",
    }


def validate_survey(survey: Mapping[str, Any], chapters: Iterable[int]) -> list[str]:
    errors: list[str] = []
    known = set(chapters)
    for i, row in enumerate(survey.get("cast") or []):
        tag = f"cast[{i}] {row.get('name')!r}"
        if row.get("type") not in TYPE_PREFIXES:
            errors.append(f"{tag}: type must be one of {sorted(TYPE_PREFIXES)}")
        if not SLUG.fullmatch(str(row.get("slug") or "")):
            errors.append(f"{tag}: slug must be lowercase pinyin words joined by underscores")
        if row.get("type") == "character" and row.get("tier") not in TIERS:
            errors.append(f"{tag}: tier must be one of {TIERS}")
        if row.get("first_chapter") is not None and row.get("first_chapter") not in known:
            errors.append(f"{tag}: first_chapter outside the book")
    ids = [a.get("id") for a in survey.get("arcs") or []]
    if len(ids) != len(set(ids)):
        errors.append("arcs: duplicate id")
    for arc in survey.get("arcs") or []:
        start, end = arc.get("chapter_start"), arc.get("chapter_end")
        if start not in known or (end is not None and (end not in known or end < start)):
            errors.append(f"arc {arc.get('id')!r}: chapter range invalid")
        if arc.get("parent_arc_id") and arc["parent_arc_id"] not in ids:
            errors.append(f"arc {arc.get('id')!r}: unknown parent_arc_id")
    for system in survey.get("level_systems") or []:
        if not system.get("name") or not SLUG.fullmatch(str(system.get("slug") or "")):
            errors.append(f"level system {system.get('name')!r}: name and pinyin slug required")
    return errors


def seed_registry(registry: IdRegistry, survey: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Claim IDs for the surveyed cast and level systems; returns what was issued or reused."""
    issued = []
    for row in survey.get("cast") or []:
        entity_id, created = registry.claim(row["type"], row["name"], row["slug"], aliases=row.get("aliases") or [],
                                            first_chapter=row.get("first_chapter"), claimed_by="survey")
        issued.append({"name": row["name"], "id": entity_id, "created": created, "tier": row.get("tier")})
    for system in survey.get("level_systems") or []:
        entity_id, created = registry.claim("level_axis", system["name"], system["slug"],
                                            aliases=system.get("aliases") or [], claimed_by="survey")
        issued.append({"name": system["name"], "id": entity_id, "created": created})
    return issued
