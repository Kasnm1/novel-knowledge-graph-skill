#!/usr/bin/env python3
"""Export a modular, deterministic AI bundle from a validated novel graph.

``--chapter`` preserves the historical meaning: it changes the dynamic state
snapshot while static analyzed facts remain available. ``--cutoff`` is a
separate, strict spoiler boundary; when supplied the graph is closed through the
shared temporal filter before any static module is built.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib
import json
import re
from copy import deepcopy
from pathlib import Path
from typing import Any

from filter_graph_asof import filter_graph
from io_utils import atomic_write_text
from required_fields import ARRAY_KINDS
from validate_style_observations import validate_style_observations

LINE_RE = re.compile(r"(?:(?:原文)?第\s*\d+\s*(?:[—–-]\s*\d+\s*)?行|\b(?:source[ _-]?)?lines?\s*\d+(?:\s*[-–—]\s*\d+)?)", re.IGNORECASE)
GROUPS = tuple(ARRAY_KINDS)


def clean(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: clean(item) for key, item in value.items() if key not in {"source_line_start", "source_line_end", "line_start", "line_end"}}
    if isinstance(value, list):
        return [clean(item) for item in value]
    if isinstance(value, str):
        return LINE_RE.sub("", value)
    return value


def stable_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def record_id(record: dict[str, Any]) -> str:
    return str(record.get("id", ""))


def chapter_of(record: dict[str, Any]) -> int | None:
    for key in ("chapter", "created_chapter", "planted_chapter", "first_meeting_chapter", "valid_from", "chapter_start"):
        value = record.get(key)
        if isinstance(value, int) and not isinstance(value, bool):
            return value
    return None


def sort_records(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(records, key=lambda row: (chapter_of(row) is None, chapter_of(row) or 0, record_id(row)))


def compact(record: dict[str, Any]) -> str:
    rid = record_id(record)
    body = (
        record.get("summary")
        or record.get("description")
        or record.get("observation")
        or record.get("statement")
        or record.get("terms")
        or record.get("label")
        or record.get("title")
        or record.get("quote")
        or ""
    )
    chapter = chapter_of(record)
    prefix = f"[{rid}]"
    if chapter is not None:
        prefix += f" 第{chapter}章"
    return f"- {prefix} {clean(str(body)).strip()}".rstrip()


def write(path: Path, text: str) -> str:
    atomic_write_text(path, text.rstrip() + "\n")
    return hashlib.sha256(path.read_bytes()).hexdigest()


def dynamic_state(graph: dict[str, Any], chapter: int) -> list[dict[str, Any]]:
    """Use the shared snapshot kernel; preserve a conservative fallback."""
    try:
        snapshot = importlib.import_module("snapshot")
        helper = getattr(snapshot, "state_changes_at", None)
        if callable(helper):
            return [row for row in helper(graph, chapter) if isinstance(row, dict)]
    except (ImportError, AttributeError, TypeError, ValueError):
        pass
    return [
        row
        for row in graph.get("state_changes", [])
        if isinstance(row, dict)
        and (chapter_of(row) or 0) <= chapter
        and (not isinstance(row.get("end_chapter"), int) or chapter <= row["end_chapter"])
    ]


def _style_asof(rows: list[dict[str, Any]], cutoff: int | None) -> list[dict[str, Any]]:
    if cutoff is None:
        return rows
    result: list[dict[str, Any]] = []
    for row in rows:
        start = chapter_of(row)
        if start is None or start > cutoff:
            continue
        copy = deepcopy(row)
        if isinstance(copy.get("chapter_end"), int) and copy["chapter_end"] > cutoff:
            copy["chapter_end"] = cutoff
        result.append(copy)
    return result


def _mentions_entity(record: dict[str, Any], entity_id: str) -> bool:
    scalar_fields = ("entity_id", "source_id", "target_id", "protagonist_id", "character_id", "item_id")
    if entity_id in {record.get(field) for field in scalar_fields}:
        return True
    for field in ("related_entity_ids", "entity_ids", "participant_ids", "promisor_ids", "counterparty_ids"):
        values = record.get(field)
        if isinstance(values, list) and entity_id in values:
            return True
    return False


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--graph", required=True, type=Path)
    parser.add_argument("--validation", required=True, type=Path)
    parser.add_argument("--vocabulary", type=Path)
    parser.add_argument("--output-dir", "--output", dest="output_dir", required=True, type=Path)
    parser.add_argument("--chapter", type=int, help="Dynamic state snapshot chapter")
    parser.add_argument("--cutoff", type=int, help="Strict spoiler boundary for every static and dynamic module")
    parser.add_argument("--style-observations", type=Path, help="Optional style-observations.json; auto-discovered beside graph")
    args = parser.parse_args(argv)

    raw_graph = json.loads(args.graph.read_text(encoding="utf-8"))
    raw_meta = raw_graph.get("metadata") if isinstance(raw_graph.get("metadata"), dict) else {}
    raw_start = int(raw_meta.get("chapter_start", 1))
    raw_end = int(raw_meta.get("chapter_end", raw_start))
    if args.cutoff is not None and not raw_start <= args.cutoff <= raw_end:
        raise ValueError(f"cutoff chapter {args.cutoff} outside {raw_start}-{raw_end}")
    if args.cutoff is not None:
        raw_graph = filter_graph(raw_graph, args.cutoff, strict=True)
    graph = clean(raw_graph)

    style_path = args.style_observations or args.graph.resolve().parent / "style-observations.json"
    style_observations = (
        validate_style_observations(json.loads(style_path.read_text(encoding="utf-8")), graph)
        if style_path.is_file()
        else []
    )
    style_observations = _style_asof(style_observations, args.cutoff)
    validation = json.loads(args.validation.read_text(encoding="utf-8"))
    vocabulary = json.loads(args.vocabulary.read_text(encoding="utf-8")) if args.vocabulary else {}
    metadata = graph.get("metadata") or {}
    start = int(metadata.get("chapter_start", raw_start))
    end = int(metadata.get("chapter_end", args.cutoff if args.cutoff is not None else raw_end))
    snapshot_chapter = end if args.chapter is None else args.chapter
    if not start <= snapshot_chapter <= end:
        raise ValueError(f"snapshot chapter {snapshot_chapter} outside {start}-{end}")

    out = args.output_dir
    out.mkdir(parents=True, exist_ok=True)
    entities = sort_records([row for row in graph.get("entities", []) if isinstance(row, dict)])
    characters = [row for row in entities if row.get("type") == "character"]
    chapter_summaries = sort_records([row for row in graph.get("chapter_summaries", []) if isinstance(row, dict)])
    static_groups = {group: sort_records([row for row in graph.get(group, []) if isinstance(row, dict)]) for group in GROUPS}
    files: dict[str, str] = {}

    current_changes = sort_records(dynamic_state(graph, snapshot_chapter))
    scope_text = f"Strict spoiler cutoff: chapter {args.cutoff}" if args.cutoff is not None else "Static scope: full analyzed graph"
    core = [
        "# AI Core",
        "",
        f"Book: {metadata.get('title', '')}",
        f"Coverage: chapters {start}-{end}",
        f"Snapshot state: chapter {snapshot_chapter}",
        scope_text,
        "",
        "Stable IDs and evidence links are authoritative. `--chapter` changes dynamic state only; `--cutoff` closes the entire exported fact set.",
        "",
        f"Characters: {len(characters)}",
        f"Events: {len(static_groups.get('events', []))}",
        f"Story arcs: {len(static_groups.get('story_arcs', []))}",
        f"Foreshadowing: {len(static_groups.get('foreshadowing', []))}",
        f"Commitments: {len(static_groups.get('commitments', []))}",
        "",
        "## Dynamic state through snapshot",
    ]
    core.extend(compact(row) for row in current_changes)
    core.extend(["", "## Entry Points", "- `CONTINUE.md` for incremental continuation", "- `FORESHADOWING.md` for the visible clue ledger", "- `INDEX.json` for machine navigation"])
    files["AI_CORE.md"] = write(out / "AI_CORE.md", "\n".join(core))

    cont = [
        "# Continue",
        "",
        "Use `graph.json` as the source of truth and preserve every visible stable ID, evidence record, and historical state change. Append only chapter-supported records; do not rewrite prior facts.",
        "",
        f"Export boundary: chapters {start}-{end}.",
    ]
    if args.cutoff is None:
        cont.append("`--chapter` is only a dynamic-state selector; static analyzed facts beyond that snapshot remain intentionally available.")
    else:
        cont.append(f"This bundle is strictly closed at chapter {args.cutoff}; do not infer or request later facts from this artifact.")
    files["CONTINUE.md"] = write(out / "CONTINUE.md", "\n".join(cont))

    fs_lines = ["# Foreshadowing", "", "Foreshadowing ledger visible within this export boundary.", ""]
    for row in static_groups.get("foreshadowing", []):
        fs_lines.extend([compact(row), "```json", json.dumps(row, ensure_ascii=False, indent=2, sort_keys=True), "```"])
    files["FORESHADOWING.md"] = write(out / "FORESHADOWING.md", "\n".join(fs_lines))

    if static_groups.get("story_arcs"):
        arc_lines = ["# Story Arcs", "", "Overlapping, nested, and parallel intervals are preserved.", ""]
        for row in static_groups["story_arcs"]:
            arc_lines.extend([compact(row), "```json", json.dumps(row, ensure_ascii=False, indent=2, sort_keys=True), "```"])
        files["STORY_ARCS.md"] = write(out / "STORY_ARCS.md", "\n".join(arc_lines))

    if static_groups.get("commitments"):
        commitment_lines = ["# Commitments", "", "Evidence-backed promises, oaths, agreements, wagers and vows visible within the export boundary.", ""]
        for row in static_groups["commitments"]:
            commitment_lines.extend([compact(row), "```json", json.dumps(row, ensure_ascii=False, indent=2, sort_keys=True), "```"])
        files["COMMITMENTS.md"] = write(out / "COMMITMENTS.md", "\n".join(commitment_lines))

    if style_observations:
        style_lines = ["# Style Observations", "", "Evidence-backed analytical observations; not story facts.", ""]
        for row in style_observations:
            style_lines.extend([compact(row), "```json", json.dumps(clean(row), ensure_ascii=False, indent=2, sort_keys=True), "```"])
        files["STYLE.md"] = write(out / "STYLE.md", "\n".join(style_lines))

    character_index = []
    related_groups = ("state_changes", "relations", "events", "romance_routes", "character_traits", "item_roles", "story_arcs", "commitments")
    for entity in characters:
        entity_id = record_id(entity)
        related = [row for group in related_groups for row in static_groups.get(group, []) if _mentions_entity(row, entity_id)]
        lines = [
            f"# {entity.get('name') or entity_id}",
            "",
            f"Stable ID: `{entity_id}`",
            f"Type: {entity.get('type', '')}",
            "",
            "## Static record",
            compact(entity),
            "",
            "## Related records",
        ]
        lines.extend(compact(row) for row in sort_records(related))
        relpath = f"characters/{entity_id}.md"
        files[relpath] = write(out / relpath, "\n".join(lines))
        character_index.append({"id": entity_id, "path": relpath})

    chapter_index = []
    summaries_by_chapter = {int(row["chapter"]): row for row in chapter_summaries if isinstance(row.get("chapter"), int)}
    for chapter in range(start, end + 1):
        summary = summaries_by_chapter.get(chapter, {})
        relpath = f"chapters/{chapter:04d}.md"
        dynamic = chapter <= snapshot_chapter
        events = [row for row in static_groups.get("events", []) if chapter_of(row) == chapter]
        arcs = [row for row in static_groups.get("story_arcs", []) if (row.get("chapter_start") or 0) <= chapter and (row.get("chapter_end") is None or chapter <= row.get("chapter_end"))]
        evidence = [row for row in static_groups.get("evidence", []) if chapter_of(row) == chapter]
        lines = [
            f"# Chapter {chapter}",
            "",
            f"Static summary: {clean(str(summary.get('summary', '')))}",
            f"Dynamic state available at snapshot: {'yes' if dynamic else 'no'}",
            "",
            "## Static events",
        ]
        lines.extend(compact(row) for row in events)
        lines.extend(["", "## Active story arcs"])
        lines.extend(compact(row) for row in arcs)
        lines.extend(["", "## Static evidence"])
        lines.extend(compact(row) for row in evidence)
        if dynamic:
            lines.extend(["", "## Dynamic changes through snapshot"])
            lines.extend(compact(row) for row in current_changes if chapter_of(row) == chapter)
        files[relpath] = write(out / relpath, "\n".join(lines))
        chapter_index.append({"chapter": chapter, "path": relpath, "dynamic_through_snapshot": dynamic})

    index = {
        "schema": "ai-bundle-index/v2",
        "snapshot_chapter": snapshot_chapter,
        "spoiler_cutoff_chapter": args.cutoff,
        "characters": character_index,
        "chapters": chapter_index,
        "modules": sorted(files),
    }
    files["INDEX.json"] = write(out / "INDEX.json", json.dumps(index, ensure_ascii=False, indent=2, sort_keys=True))

    def dependency(path: Path | None) -> dict[str, str] | None:
        return None if path is None else {"path": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}

    manifest = {
        "schema": "ai-bundle-manifest/v2",
        "version": 2,
        "book": {key: metadata[key] for key in ("title", "author", "source_file") if key in metadata},
        "profile": metadata.get("profile") or metadata.get("analysis_profile"),
        "chapter_boundary": {"start": start, "end": end},
        "snapshot_chapter": snapshot_chapter,
        "spoiler_cutoff_chapter": args.cutoff,
        "module_hashes": files,
        "dependencies": {
            "graph": dependency(args.graph),
            "validation": dependency(args.validation),
            "vocabulary": dependency(args.vocabulary),
            "style_observations": dependency(style_path) if style_path.is_file() else None,
        },
        "size": sum((out / path).stat().st_size for path in files),
        "character_count": len(characters),
        "record_counts": {group: len(rows) for group, rows in static_groups.items()},
        "source_validation_record_counts": validation.get("record_counts", {}),
    }
    write(out / "manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
