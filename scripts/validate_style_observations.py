#!/usr/bin/env python3
"""Validate evidence-backed style-observations.json without changing graph facts."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Mapping


SCOPES = {"work", "arc", "character"}
DIMENSIONS = {"prose", "narrative", "characterization", "speech", "behavior"}
STABILITIES = {"stable", "evolving", "contextual"}
CONFIDENCES = {"explicit", "inferred", "uncertain"}


class StyleObservationError(ValueError):
    pass


def validate_style_observations(payload: Any, graph: Mapping[str, Any]) -> list[dict[str, Any]]:
    rows = payload.get("observations") if isinstance(payload, Mapping) else payload
    if rows is None:
        return []
    if not isinstance(rows, list) or any(not isinstance(row, Mapping) for row in rows):
        raise StyleObservationError("style observations must be an object array")
    evidence_ids = {row.get("id") for row in graph.get("evidence", []) if isinstance(row, Mapping)}
    entity_ids = {row.get("id") for row in graph.get("entities", []) if isinstance(row, Mapping)}
    arc_ids = {row.get("id") for row in graph.get("story_arcs", []) if isinstance(row, Mapping)}
    seen: set[str] = set()
    result: list[dict[str, Any]] = []
    for raw in rows:
        row = dict(raw)
        record_id = row.get("id")
        if not isinstance(record_id, str) or not record_id or record_id in seen:
            raise StyleObservationError(f"style observation has missing/duplicate id: {record_id}")
        seen.add(record_id)
        if row.get("scope") not in SCOPES or row.get("dimension") not in DIMENSIONS:
            raise StyleObservationError(f"{record_id}: unsupported scope/dimension")
        if not isinstance(row.get("claim"), str) or not row["claim"].strip():
            raise StyleObservationError(f"{record_id}: claim is required")
        start, end = row.get("chapter_start"), row.get("chapter_end")
        if not isinstance(start, int) or isinstance(start, bool) or start < 0:
            raise StyleObservationError(f"{record_id}: chapter_start must be a non-negative integer")
        if end is not None and (not isinstance(end, int) or isinstance(end, bool) or end < start):
            raise StyleObservationError(f"{record_id}: invalid chapter_end")
        if row.get("stability") not in STABILITIES or row.get("confidence") not in CONFIDENCES:
            raise StyleObservationError(f"{record_id}: unsupported stability/confidence")
        refs = row.get("evidence_ids")
        if not isinstance(refs, list) or not refs or any(ref not in evidence_ids for ref in refs):
            raise StyleObservationError(f"{record_id}: evidence_ids must resolve and be non-empty")
        if not isinstance(row.get("counterexamples", []), list):
            raise StyleObservationError(f"{record_id}: counterexamples must be an array")
        if row.get("scope") == "character" and row.get("entity_id") not in entity_ids:
            raise StyleObservationError(f"{record_id}: character scope requires a valid entity_id")
        if row.get("scope") == "arc" and row.get("arc_id") not in arc_ids:
            raise StyleObservationError(f"{record_id}: arc scope requires a valid arc_id")
        result.append(row)
    return sorted(result, key=lambda row: (row["chapter_start"], row["dimension"], row["id"]))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--graph", required=True, type=Path)
    parser.add_argument("--style-observations", required=True, type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    graph = json.loads(args.graph.resolve().read_text(encoding="utf-8"))
    payload = json.loads(args.style_observations.resolve().read_text(encoding="utf-8"))
    rows = validate_style_observations(payload, graph)
    rendered = json.dumps({"valid": True, "count": len(rows), "observations": rows}, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    else:
        print(rendered, end="")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except StyleObservationError as exc:
        raise SystemExit(f"style observations error: {exc}")
