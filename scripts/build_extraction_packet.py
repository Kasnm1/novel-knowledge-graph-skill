#!/usr/bin/env python3
"""Build an accuracy-preserving, token-efficient extraction packet."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from io_utils import atomic_write_json
from nkg.extraction.packet import build_extraction_packet


def _jsonl(path: Path) -> list[dict]:
    rows: list[dict] = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        raw = raw.strip()
        if raw:
            value = json.loads(raw)
            if isinstance(value, dict):
                rows.append(value)
    return rows


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--graph", required=True, type=Path)
    p.add_argument("--excerpts-jsonl", required=True, type=Path, help="JSONL rows with chapter and text")
    p.add_argument("--chapter-start", required=True, type=int)
    p.add_argument("--chapter-end", required=True, type=int)
    p.add_argument("--candidates", type=Path, help="JSON object with candidates[] or a JSON array")
    p.add_argument("--output", required=True, type=Path)
    p.add_argument("--max-context-chars", type=int)
    p.add_argument("--minimum-level", choices=("R1", "R2", "R3", "R4"))
    args = p.parse_args()

    graph = json.loads(args.graph.read_text(encoding="utf-8"))
    excerpts = _jsonl(args.excerpts_jsonl)
    candidates: list[dict] = []
    if args.candidates:
        raw = json.loads(args.candidates.read_text(encoding="utf-8"))
        if isinstance(raw, list):
            candidates = [row for row in raw if isinstance(row, dict)]
        elif isinstance(raw, dict):
            candidates = [row for row in raw.get("candidates", []) if isinstance(row, dict)]
    packet = build_extraction_packet(
        graph,
        excerpts,
        chapter_start=args.chapter_start,
        chapter_end=args.chapter_end,
        candidates=candidates,
        max_context_chars=args.max_context_chars,
        requested_level=args.minimum_level,
    )
    atomic_write_json(args.output, packet, trailing_newline=False)
    print(json.dumps({
        "output": str(args.output),
        "retrieval_level": packet["retrieval_level"],
        "entities": len(packet["entity_ids"]),
        "schema_fields": len(packet["schema_slice"]),
        "approx_input_tokens": packet["token_telemetry"]["approx_input_tokens"],
        "budget_exceeded": packet["token_telemetry"]["budget_exceeded"],
        "truncated_for_budget": packet["token_telemetry"]["truncated_for_budget"],
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
