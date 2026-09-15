#!/usr/bin/env python3
"""Compare two strict chapter snapshots of one canonical graph."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from filter_graph_asof import filter_graph
from io_utils import atomic_write_json
from nkg.views.snapshot_diff import diff_snapshots


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--graph", required=True, type=Path)
    p.add_argument("--from-chapter", required=True, type=int)
    p.add_argument("--to-chapter", required=True, type=int)
    p.add_argument("--output", required=True, type=Path)
    args = p.parse_args()
    graph = json.loads(args.graph.read_text(encoding="utf-8"))
    before = filter_graph(graph, args.from_chapter, strict=True)
    after = filter_graph(graph, args.to_chapter, strict=True)
    report = diff_snapshots(before, after)
    atomic_write_json(args.output, report)
    print(json.dumps({"output": str(args.output), **report["summary"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
