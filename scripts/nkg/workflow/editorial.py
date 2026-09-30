"""The editorial layer: story arcs as facts, reader-facing judgments as display hints.

After reconciliation an AI editor reads the chapter summaries arc by arc and
writes `editorial.json`:

- `arcs`: the final volume / arc / sub-arc intervals (`story_arcs` records,
  starting from the survey's draft), each with its turning points and cast;
- `chapter_arcs`: which arcs each chapter belongs to (`chapter_summaries.arc_ids`);
- `profiles`: per entity a tier, one dated headline per arc ("who this person is
  at this point"), arc bios and the label of their relation to the protagonist;
- `arc_recaps`: one recap paragraph per arc with its key events.

`validate_editorial` checks identity, time and evidence; `editorial_outputs`
splits the result: arcs and chapter membership become a supplementary fragment
(facts, merged like any fragment), everything else becomes `display-hints.json`
(derived, read by `build_entity_profiles.py`). No reader-facing judgment is
written into the canonical graph.
"""

from __future__ import annotations

from typing import Any, Mapping

from chapter_audit import AUDIT_PROTOCOL
from nkg.core.records import chapter_value, records
from nkg.views.entity_profiles import TIERS

ARC_STATUSES = frozenset({"open", "active", "paused", "resolved", "uncertain"})
ARC_PHASES = frozenset({"setup", "development", "escalation", "turning_point", "climax", "resolution",
                        "aftermath", "interlude", "recurring", "uncertain"})


def validate_editorial(editorial: Mapping[str, Any], graph: Mapping[str, Any]) -> list[str]:
    errors: list[str] = []
    entities = {e["id"]: e for e in records(graph.get("entities")) if isinstance(e.get("id"), str)}
    events = {e["id"] for e in records(graph.get("events")) if isinstance(e.get("id"), str)}
    evidence = {e["id"] for e in records(graph.get("evidence")) if isinstance(e.get("id"), str)}
    analyzed = set((graph.get("metadata") or {}).get("analyzed_chapters") or [])
    arcs = records(editorial.get("arcs"))
    arc_ids = [a.get("id") for a in arcs]
    if len(arc_ids) != len(set(arc_ids)):
        errors.append("arcs: duplicate id")
    parents = {}
    for arc in arcs:
        tag = f"arc {arc.get('id')!r}"
        start, end = chapter_value(arc.get("chapter_start")), chapter_value(arc.get("chapter_end"))
        if not arc.get("title") or start is None or (analyzed and start not in analyzed):
            errors.append(f"{tag}: title and an analysed chapter_start are required")
        if end is not None and (end < (start or 0) or (analyzed and end not in analyzed)):
            errors.append(f"{tag}: chapter_end invalid")
        if arc.get("status") not in ARC_STATUSES:
            errors.append(f"{tag}: status must be one of {sorted(ARC_STATUSES)}")
        if arc.get("phase") is not None and arc.get("phase") not in ARC_PHASES:
            errors.append(f"{tag}: phase must be one of {sorted(ARC_PHASES)}")
        for field, known in (("event_ids", events), ("turning_point_ids", events), ("entity_ids", entities),
                             ("evidence_ids", evidence)):
            unknown = [x for x in arc.get(field) or [] if x not in known]
            if unknown:
                errors.append(f"{tag}: unknown {field} {unknown[:5]}")
        if not arc.get("evidence_ids"):
            errors.append(f"{tag}: evidence_ids required")
        parents[arc.get("id")] = arc.get("parent_arc_id")
    for arc_id, parent in parents.items():
        seen, cursor = set(), parent
        while cursor:
            if cursor not in parents:
                errors.append(f"arc {arc_id!r}: unknown parent_arc_id {cursor!r}")
                break
            if cursor in seen or cursor == arc_id:
                errors.append(f"arc {arc_id!r}: parent chain has a cycle")
                break
            seen.add(cursor)
            cursor = parents[cursor]
    for chapter, ids in (editorial.get("chapter_arcs") or {}).items():
        unknown = [x for x in ids if x not in parents]
        if unknown:
            errors.append(f"chapter {chapter}: unknown arc ids {unknown}")
    for entity_id, profile in (editorial.get("profiles") or {}).items():
        entity = entities.get(entity_id)
        if entity is None:
            errors.append(f"profile {entity_id!r}: unknown entity")
            continue
        if profile.get("tier") is not None and profile["tier"] not in TIERS:
            errors.append(f"profile {entity_id!r}: tier must be one of {TIERS}")
        first = chapter_value(entity.get("first_chapter")) or 0
        for headline in profile.get("headlines") or []:
            start = chapter_value(headline.get("valid_from"))
            if start is None or start < first:
                errors.append(f"profile {entity_id!r}: headline valid_from must be ≥ first_chapter {first}")
            if not headline.get("evidence_ids") or any(x not in evidence for x in headline.get("evidence_ids") or []):
                errors.append(f"profile {entity_id!r}: every headline needs known evidence_ids")
        for arc_id in (profile.get("arc_bios") or {}):
            if arc_id not in parents:
                errors.append(f"profile {entity_id!r}: arc_bios names unknown arc {arc_id!r}")
    for arc_id, recap in (editorial.get("arc_recaps") or {}).items():
        if arc_id not in parents:
            errors.append(f"recap for unknown arc {arc_id!r}")
        unknown = [x for x in (recap or {}).get("key_event_ids") or [] if x not in events]
        if unknown:
            errors.append(f"recap {arc_id!r}: unknown key_event_ids {unknown[:5]}")
    return errors


def editorial_outputs(editorial: Mapping[str, Any], graph: Mapping[str, Any], *, fragment: str,
                      marker: str) -> tuple[dict[str, Any], dict[str, Any]]:
    """(supplementary fragment with arcs and chapter membership, display hints)."""
    summaries = {s.get("chapter"): s for s in records(graph.get("chapter_summaries"))}
    restated = []
    for chapter, arc_ids in sorted((editorial.get("chapter_arcs") or {}).items(), key=lambda kv: int(kv[0])):
        row = summaries.get(int(chapter))
        if row and row.get("id"):
            restated.append({"id": row["id"], "chapter": int(chapter), "arc_ids": list(arc_ids)})
    arcs = []
    for arc in records(editorial.get("arcs")):
        record = {"chapter_end": None, "parent_arc_id": None, "phase": None, "event_ids": [], "entity_ids": [],
                  "turning_point_ids": [], **dict(arc)}
        arcs.append(record)
    frag = {"metadata": {"fragment": fragment, "supplementary": True, "audit_protocol": AUDIT_PROTOCOL,
                         "notes": f"editorial layer ({marker}): story arcs and chapter membership"},
            "story_arcs": arcs, "chapter_summaries": restated}
    hints = {"schema_version": 1, "profiles": dict(editorial.get("profiles") or {}),
             "arc_recaps": dict(editorial.get("arc_recaps") or {})}
    return frag, hints
