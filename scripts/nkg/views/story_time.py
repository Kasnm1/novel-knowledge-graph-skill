from __future__ import annotations

from copy import deepcopy
from typing import Any, Mapping

from nkg.core.runtime import records


def build_story_time_view(graph: Mapping[str, Any]) -> dict[str, Any]:
    """Expose narrative chapter and source-faithful story time as separate axes.

    The code deliberately does not infer flashback/flashforward semantics from
    free-form prose. If the source/extractor supplies a structured sort key or
    label it is preserved; interpretation remains an AI/domain task.
    """
    rows: list[dict[str, Any]] = []
    for summary in records(graph.get("chapter_summaries")):
        chapter = summary.get("chapter")
        if not isinstance(chapter, int) or isinstance(chapter, bool):
            continue
        rows.append({
            "narrative_chapter": chapter,
            "story_time": deepcopy(summary.get("story_time")),
            "story_time_sort_key": deepcopy(summary.get("story_time_sort_key")),
            "story_time_label": deepcopy(summary.get("story_time_label")),
            "pov_entity_ids": deepcopy(summary.get("pov_entity_ids") or []),
            "scene_count": summary.get("scene_count"),
            "summary_id": summary.get("id"),
            "evidence_ids": deepcopy(summary.get("evidence_ids") or []),
        })
    rows.sort(key=lambda row: row["narrative_chapter"])
    return {
        "schema_version": 1,
        "derived_only": True,
        "axes": {
            "narrative": "chapter order in which the reader receives information",
            "story_time": "source-faithful in-world time when represented",
        },
        "chapters": rows,
        "story_time_coverage": {
            "with_story_time": sum(row["story_time"] not in (None, "", []) for row in rows),
            "total": len(rows),
        },
        "interpretation_policy": "Do not infer chronology class from free-form story_time in deterministic code.",
    }
