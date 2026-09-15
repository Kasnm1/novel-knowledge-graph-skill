#!/usr/bin/env python3
"""Build a dual-axis narrative-chapter/story-time derived view."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from io_utils import atomic_write_json
from nkg.views.story_time import build_story_time_view


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--graph", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    graph = json.loads(args.graph.read_text(encoding="utf-8"))
    result = build_story_time_view(graph)
    atomic_write_json(args.output, result)
    coverage = result["story_time_coverage"]
    print(json.dumps({"output": str(args.output), "chapters": coverage["total"], "with_story_time": coverage["with_story_time"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
