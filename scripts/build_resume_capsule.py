#!/usr/bin/env python3
"""Build a compact continuation capsule for the next extraction batch."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from io_utils import atomic_write_json
from nkg.extraction.resume import build_resume_capsule


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--graph", required=True, type=Path)
    p.add_argument("--chapter", required=True, type=int)
    p.add_argument("--previous-chapter", type=int)
    p.add_argument("--candidates", type=Path)
    p.add_argument("--output", required=True, type=Path)
    args = p.parse_args()
    graph = json.loads(args.graph.read_text(encoding="utf-8"))
    candidates = []
    if args.candidates:
        value = json.loads(args.candidates.read_text(encoding="utf-8"))
        if isinstance(value, list):
            candidates = value
        elif isinstance(value, dict):
            candidates = value.get("candidates", [])
    capsule = build_resume_capsule(graph, chapter=args.chapter, previous_chapter=args.previous_chapter, candidates=candidates)
    atomic_write_json(args.output, capsule)
    print(json.dumps({"output": str(args.output), "chapter": args.chapter, "active_entities": len(capsule["active_entity_ids"]), "unresolved_candidates": len(capsule["unresolved_candidate_ids"])}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
