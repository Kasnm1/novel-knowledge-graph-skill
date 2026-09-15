#!/usr/bin/env python3
"""Export a modular, deterministic AI bundle from a validated novel graph."""
from __future__ import annotations

import argparse
import hashlib
import importlib
import json
import re
from pathlib import Path
from typing import Any
from validate_style_observations import validate_style_observations

LINE_RE = re.compile(r"(?:(?:原文)?第\s*\d+\s*(?:[—–-]\s*\d+\s*)?行|\b(?:source[ _-]?)?lines?\s*\d+(?:\s*[-–—]\s*\d+)?)", re.IGNORECASE)
CHAPTER_RE = re.compile(r"第\s*(\d+)\s*章")
GROUPS = ("entities", "events", "relations", "state_changes", "foreshadowing", "evidence", "review_issues", "romance_routes", "intimate_acts", "level_conversions", "character_traits", "chapter_summaries", "item_roles", "story_arcs")


def clean(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: clean(v) for k, v in value.items() if k not in {"source_line_start", "source_line_end", "line_start", "line_end"}}
    if isinstance(value, list):
        return [clean(v) for v in value]
    if isinstance(value, str):
        return LINE_RE.sub("", value)
    return value


def stable_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def record_id(record: dict[str, Any]) -> str:
    return str(record.get("id", ""))


def chapter_of(record: dict[str, Any]) -> int | None:
    for key in ("chapter", "planted_chapter", "first_meeting_chapter"):
        value = record.get(key)
        if isinstance(value, int):
            return value
    return None


def sort_records(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(records, key=lambda r: (chapter_of(r) is None, chapter_of(r) or 0, record_id(r)))


def compact(record: dict[str, Any]) -> str:
    rid = record_id(record)
    body = record.get("summary") or record.get("description") or record.get("observation") or record.get("statement") or record.get("label") or record.get("title") or record.get("quote") or ""
    ch = chapter_of(record)
    prefix = f"[{rid}]"
    if ch is not None:
        prefix += f" 第{ch}章"
    return f"- {prefix} {clean(str(body)).strip()}".rstrip()


def write(path: Path, text: str) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text.rstrip() + "\n", encoding="utf-8")
    return hashlib.sha256(path.read_bytes()).hexdigest()


def dynamic_state(graph: dict[str, Any], chapter: int) -> list[dict[str, Any]]:
    """Use the shared snapshot kernel; preserve a conservative fallback."""
    try:
        snapshot = importlib.import_module("snapshot")
        helper = getattr(snapshot, "state_changes_at", None)
        if callable(helper):
            return [r for r in helper(graph, chapter) if isinstance(r, dict)]
    except (ImportError, AttributeError, TypeError, ValueError):
        pass
    return [
        r
        for r in graph.get("state_changes", [])
        if isinstance(r, dict)
        and (chapter_of(r) or 0) <= chapter
        and (not isinstance(r.get("end_chapter"), int) or chapter <= r["end_chapter"])
    ]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--graph", required=True, type=Path)
    parser.add_argument("--validation", required=True, type=Path)
    parser.add_argument("--vocabulary", type=Path)
    parser.add_argument("--output-dir", "--output", dest="output_dir", required=True, type=Path)
    parser.add_argument("--chapter", type=int)
    parser.add_argument("--style-observations", type=Path, help="Optional style-observations.json; auto-discovered beside graph")
    args = parser.parse_args(argv)

    graph = clean(json.loads(args.graph.read_text(encoding="utf-8")))
    style_path = args.style_observations or args.graph.resolve().parent / "style-observations.json"
    style_observations = validate_style_observations(json.loads(style_path.read_text(encoding="utf-8")), graph) if style_path.is_file() else []
    validation = json.loads(args.validation.read_text(encoding="utf-8"))
    vocabulary = json.loads(args.vocabulary.read_text(encoding="utf-8")) if args.vocabulary else {}
    metadata = graph.get("metadata") or {}
    start = int(metadata.get("chapter_start", 1))
    end = int(metadata.get("chapter_end", start))
    snapshot = end if args.chapter is None else args.chapter
    if not start <= snapshot <= end:
        raise ValueError(f"snapshot chapter {snapshot} outside {start}-{end}")

    out = args.output_dir
    out.mkdir(parents=True, exist_ok=True)
    entities = sort_records([r for r in graph.get("entities", []) if isinstance(r, dict)])
    chars = [r for r in entities if r.get("type") == "character"]
    chapters = sort_records([r for r in graph.get("chapter_summaries", []) if isinstance(r, dict)])
    static_groups = {g: sort_records([r for r in graph.get(g, []) if isinstance(r, dict)]) for g in GROUPS}
    files: dict[str, str] = {}

    current_changes = sort_records(dynamic_state(graph, snapshot))
    core = ["# AI Core", "", f"Book: {metadata.get('title', '')}", f"Coverage: chapters {start}-{end}", f"Snapshot state: chapter {snapshot}", "", "This bundle is modular: stable IDs and evidence links are authoritative. Static sections retain the full analyzed graph; only state claims are snapshot-aware.", "", f"Characters: {len(chars)}", f"Events: {len(static_groups['events'])}", f"Story arcs: {len(static_groups['story_arcs'])}", f"Foreshadowing: {len(static_groups['foreshadowing'])}", "", "## Dynamic state through snapshot"]
    core.extend(compact(r) for r in current_changes)
    core.extend(["", "## Entry Points", "- `CONTINUE.md` for incremental continuation", "- `FORESHADOWING.md` for the complete clue ledger", "- `INDEX.json` for machine navigation"])
    files["AI_CORE.md"] = write(out / "AI_CORE.md", "\n".join(core))

    cont = ["# Continue", "", "Use `graph.json` as the source of truth and continue extraction from the last covered chapter. Preserve every existing stable ID, evidence record, and historical state change; append only new chapter-supported records. Do not re-extract or rewrite prior chapters. The `--chapter` option changes the dynamic snapshot only and must not remove future static summaries, events, evidence, or foreshadowing.", "", f"Current analyzed boundary: chapters {start}-{end}."]
    files["CONTINUE.md"] = write(out / "CONTINUE.md", "\n".join(cont))

    fs_lines = ["# Foreshadowing", "", "Complete static foreshadowing ledger (future records remain visible regardless of snapshot)."]
    for r in static_groups["foreshadowing"]:
        fs_lines.extend([compact(r), "```json", json.dumps(r, ensure_ascii=False, indent=2, sort_keys=True), "```"])
    files["FORESHADOWING.md"] = write(out / "FORESHADOWING.md", "\n".join(fs_lines))

    if static_groups["story_arcs"]:
        arc_lines = ["# Story Arcs", "", "Overlapping, nested, and parallel intervals are preserved.", ""]
        for record in static_groups["story_arcs"]:
            arc_lines.extend([compact(record), "```json", json.dumps(record, ensure_ascii=False, indent=2, sort_keys=True), "```"])
        files["STORY_ARCS.md"] = write(out / "STORY_ARCS.md", "\n".join(arc_lines))
    if style_observations:
        style_lines = ["# Style Observations", "", "Evidence-backed analytical observations; not story facts.", ""]
        for record in style_observations:
            style_lines.extend([compact(record), "```json", json.dumps(clean(record), ensure_ascii=False, indent=2, sort_keys=True), "```"])
        files["STYLE.md"] = write(out / "STYLE.md", "\n".join(style_lines))

    char_index = []
    for entity in chars:
        eid = record_id(entity)
        related = []
        for group in ("state_changes", "relations", "events", "romance_routes", "character_traits", "item_roles", "story_arcs"):
            for r in static_groups[group]:
                if eid in {r.get("entity_id"), r.get("source_id"), r.get("target_id"), r.get("protagonist_id"), r.get("character_id")} or eid in (r.get("related_entity_ids") or []) or eid in (r.get("entity_ids") or []):
                    related.append(r)
        lines = [f"# {entity.get('name') or eid}", "", f"Stable ID: `{eid}`", f"Type: {entity.get('type', '')}", "", "## Static record", compact(entity), "", "## Related records"]
        lines.extend(compact(r) for r in sort_records(related))
        relpath = f"characters/{eid}.md"
        files[relpath] = write(out / relpath, "\n".join(lines))
        char_index.append({"id": eid, "path": relpath})

    chapter_index = []
    summaries_by_chapter = {int(r["chapter"]): r for r in chapters if isinstance(r.get("chapter"), int)}
    for ch in range(start, end + 1):
        r = summaries_by_chapter.get(ch, {})
        relpath = f"chapters/{ch:04d}.md"
        dynamic = ch <= snapshot
        events = [x for x in static_groups["events"] if chapter_of(x) == ch]
        arcs = [x for x in static_groups["story_arcs"] if (x.get("chapter_start") or 0) <= ch and (x.get("chapter_end") is None or ch <= x.get("chapter_end"))]
        evidence = [x for x in static_groups["evidence"] if chapter_of(x) == ch]
        lines = [f"# Chapter {ch}", "", f"Static summary: {clean(str(r.get('summary', '')))}", f"Dynamic state available at snapshot: {'yes' if dynamic else 'no'}", "", "## Static events (never snapshot-filtered)"]
        lines.extend(compact(x) for x in events)
        lines.extend(["", "## Active story arcs (overlap preserved)"])
        lines.extend(compact(x) for x in arcs)
        lines.extend(["", "## Static evidence (never snapshot-filtered)"])
        lines.extend(compact(x) for x in evidence)
        if dynamic:
            lines.extend(["", "## Dynamic changes through snapshot"])
            lines.extend(compact(x) for x in current_changes if chapter_of(x) == ch)
        files[relpath] = write(out / relpath, "\n".join(lines))
        chapter_index.append({"chapter": ch, "path": relpath, "dynamic_through_snapshot": dynamic})

    index = {"schema": "ai-bundle-index/v1", "snapshot_chapter": snapshot, "characters": char_index, "chapters": chapter_index, "modules": sorted(files)}
    files["INDEX.json"] = write(out / "INDEX.json", json.dumps(index, ensure_ascii=False, indent=2, sort_keys=True))
    def dependency(path: Path | None) -> dict[str, str] | None:
        return None if path is None else {"path": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
    manifest = {"schema": "ai-bundle-manifest/v1", "version": 1, "book": {k: metadata[k] for k in ("title", "author", "source_file") if k in metadata}, "profile": metadata.get("profile") or metadata.get("analysis_profile"), "chapter_boundary": {"start": start, "end": end}, "snapshot_chapter": snapshot, "module_hashes": files, "dependencies": {"graph": dependency(args.graph), "validation": dependency(args.validation), "vocabulary": dependency(args.vocabulary), "style_observations": dependency(style_path) if style_path.is_file() else None}, "size": sum((out / p).stat().st_size for p in files), "character_count": len(chars), "record_counts": validation.get("record_counts", {})}
    write(out / "manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
