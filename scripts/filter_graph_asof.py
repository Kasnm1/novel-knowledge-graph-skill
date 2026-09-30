#!/usr/bin/env python3
"""CLI for the strict spoiler-safe snapshot; the implementation is nkg.temporal.asof."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from io_utils import atomic_write_json
from nkg.temporal.asof import filter_graph, relation_active  # noqa: F401  (re-exported)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--graph", required=True, type=Path)
    parser.add_argument("--chapter", required=True, type=int)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--compat", action="store_true", help="Retain untimed legacy prose/aliases instead of strict spoiler closure")
    args = parser.parse_args()
    graph = json.loads(args.graph.read_text(encoding="utf-8"))
    filtered = filter_graph(graph, args.chapter, strict=not args.compat)
    atomic_write_json(args.output, filtered, trailing_newline=False)
    print(json.dumps({
        "output": str(args.output),
        "chapter": args.chapter,
        "entities": len(filtered.get("entities", [])),
        "events": len(filtered.get("events", [])),
        "temporal_provenance_gaps": len(filtered.get("metadata", {}).get("temporal_provenance_gaps", [])),
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
