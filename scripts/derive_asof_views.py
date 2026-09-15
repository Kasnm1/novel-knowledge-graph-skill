#!/usr/bin/env python3
"""Derive one authoritative chapter snapshot for every dashboard surface.

All consumer panels should read the object returned by ``derive_asof_views``.
The function first closes the canonical graph to chapter N, then derives every
view from that filtered graph. This prevents final-state fields from leaking into
an earlier chapter and gives graph/repository/story-arc/collection panels the
same temporal boundary as growth/world/narrative panels.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Iterable, Mapping

from derive_novel_views import build_views
from filter_graph_asof import filter_graph


def _records(value: Any) -> list[dict[str, Any]]:
    return [dict(row) for row in value if isinstance(row, Mapping)] if isinstance(value, list) else []


def _legacy_view(filtered: dict[str, Any], collection_manifest: dict[str, Any] | None, chapter: int) -> dict[str, Any]:
    collections: dict[str, Any] | None = None
    if collection_manifest is not None:
        from derive_collection_views import CollectionDeriver
        collections = CollectionDeriver(filtered, collection_manifest, chapter=chapter).derive()
    entities = _records(filtered.get("entities"))
    by_type: dict[str, list[dict[str, Any]]] = {}
    for entity in entities:
        by_type.setdefault(str(entity.get("type") or "unknown"), []).append(entity)
    for rows in by_type.values():
        rows.sort(key=lambda row: (str(row.get("name") or ""), str(row.get("id") or "")))
    return {
        "graph": {
            "entities": entities,
            "relations": _records(filtered.get("relations")),
            "events": _records(filtered.get("events")),
        },
        "repository": {"by_type": by_type, "counts": {kind: len(rows) for kind, rows in by_type.items()}},
        "story_arcs": _records(filtered.get("story_arcs")),
        "collections": collections,
    }


def derive_asof_views(
    graph: dict[str, Any],
    chapter: int,
    explicit_protagonists: Iterable[str] = (),
    gap_threshold: int = 3,
    collection_manifest: dict[str, Any] | None = None,
    *,
    strict: bool = True,
) -> dict[str, Any]:
    filtered = filter_graph(graph, chapter, strict=strict)
    views = build_views(filtered, explicit_protagonists, max(1, gap_threshold))
    legacy = _legacy_view(filtered, collection_manifest, chapter)
    views["metadata"]["snapshot_chapter"] = chapter
    views["metadata"]["spoiler_strict"] = strict
    views["metadata"]["temporal_provenance_gaps"] = list(filtered.get("metadata", {}).get("temporal_provenance_gaps", []))
    return {
        "chapter": chapter,
        "metadata": dict(filtered.get("metadata", {})),
        "graph": filtered,
        "views": views,
        "legacy": legacy,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--graph", required=True, type=Path)
    parser.add_argument("--chapter", required=True, type=int)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--collection-manifest", type=Path)
    parser.add_argument("--protagonist-id", action="append", default=[])
    parser.add_argument("--relation-gap-threshold", type=int, default=3)
    parser.add_argument("--compat", action="store_true")
    args = parser.parse_args()
    graph = json.loads(args.graph.read_text(encoding="utf-8"))
    collection_manifest = json.loads(args.collection_manifest.read_text(encoding="utf-8")) if args.collection_manifest else None
    snapshot = derive_asof_views(
        graph,
        args.chapter,
        args.protagonist_id,
        args.relation_gap_threshold,
        collection_manifest,
        strict=not args.compat,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({
        "output": str(args.output),
        "chapter": args.chapter,
        "entities": len(snapshot["graph"].get("entities", [])),
        "events": len(snapshot["graph"].get("events", [])),
        "temporal_provenance_gaps": len(snapshot["metadata"].get("temporal_provenance_gaps", [])),
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
