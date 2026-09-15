#!/usr/bin/env python3
"""Prebuild strict chapter checkpoints for long-run snapshot reuse."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from filter_graph_asof import filter_graph
from io_utils import atomic_write_json
from nkg.temporal.checkpoints import checkpoint_chapters, graph_fingerprint


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--graph", required=True, type=Path)
    p.add_argument("--output-dir", required=True, type=Path)
    p.add_argument("--interval", type=int, default=50)
    p.add_argument("--chapter-start", type=int)
    p.add_argument("--chapter-end", type=int)
    args = p.parse_args()
    if args.interval <= 0:
        p.error("--interval must be > 0")
    graph = json.loads(args.graph.read_text(encoding="utf-8"))
    metadata = graph.get("metadata") if isinstance(graph.get("metadata"), dict) else {}
    start = args.chapter_start if args.chapter_start is not None else int(metadata.get("chapter_start") or 0)
    end = args.chapter_end if args.chapter_end is not None else int(metadata.get("chapter_end") or start)
    fingerprint = graph_fingerprint(graph)
    root = args.output_dir
    root.mkdir(parents=True, exist_ok=True)
    rows = []
    for chapter in checkpoint_chapters(start, end, args.interval):
        snapshot = filter_graph(graph, chapter, strict=True)
        path = root / f"snapshot-{chapter:06d}.json"
        atomic_write_json(path, snapshot, trailing_newline=False)
        rows.append({"chapter": chapter, "path": path.name, "entities": len(snapshot.get("entities", [])), "events": len(snapshot.get("events", []))})
    manifest = {
        "schema_version": 1,
        "graph_fingerprint": fingerprint,
        "interval": args.interval,
        "chapter_start": start,
        "chapter_end": end,
        "checkpoints": rows,
    }
    atomic_write_json(root / "checkpoint-manifest.json", manifest)
    print(json.dumps({"output_dir": str(root), "checkpoints": len(rows), "graph_fingerprint": fingerprint}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
