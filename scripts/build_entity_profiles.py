#!/usr/bin/env python3
"""Build derived entity display profiles with optional AI-authored hints."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from filter_graph_asof import filter_graph
from io_utils import atomic_write_json
from nkg.views.entity_profiles import build_entity_profiles


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--graph", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--hints", type=Path, help="Optional AI-authored display-hints JSON")
    parser.add_argument("--cutoff", type=int)
    args = parser.parse_args()

    graph = json.loads(args.graph.read_text(encoding="utf-8"))
    if args.cutoff is not None:
        graph = filter_graph(graph, args.cutoff, strict=True)
    hints = json.loads(args.hints.read_text(encoding="utf-8")) if args.hints else None
    result = build_entity_profiles(graph, hints)
    atomic_write_json(args.output, result)
    print(json.dumps({
        "output": str(args.output),
        "profiles": len(result["profiles"]),
        "ai_profiles": result["ai_profile_count"],
        "issues": len(result["issues"]),
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
