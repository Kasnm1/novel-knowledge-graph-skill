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
from typing import Any, Iterable

from derive_novel_views import build_views
from filter_graph_asof import filter_graph
from io_utils import atomic_write_json
from nkg.views.quality import build_quality_summary


def _collections(filtered: dict[str, Any], collection_manifest: dict[str, Any] | None, chapter: int) -> dict[str, Any] | None:
    """Collection memberships with their reasons, derived once from the closed graph."""
    if collection_manifest is None:
        return None
    from derive_collection_views import CollectionDeriver
    return CollectionDeriver(filtered, collection_manifest, chapter=chapter).derive()


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
    views["quality"] = build_quality_summary(filtered)
    views["collections"] = _collections(filtered, collection_manifest, chapter)
    views["metadata"]["snapshot_chapter"] = chapter
    views["metadata"]["spoiler_strict"] = strict
    views["metadata"]["temporal_provenance_gaps"] = list(filtered.get("metadata", {}).get("temporal_provenance_gaps", []))
    return {
        "chapter": chapter,
        "metadata": dict(filtered.get("metadata", {})),
        "graph": filtered,
        "views": views,
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
    atomic_write_json(args.output, snapshot, trailing_newline=False)
    print(json.dumps({
        "output": str(args.output),
        "chapter": args.chapter,
        "entities": len(snapshot["graph"].get("entities", [])),
        "events": len(snapshot["graph"].get("events", [])),
        "temporal_provenance_gaps": len(snapshot["metadata"].get("temporal_provenance_gaps", [])),
        "invariant_warnings": snapshot["views"]["quality"]["invariants"]["warning_count"],
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
