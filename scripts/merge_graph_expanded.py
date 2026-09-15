#!/usr/bin/env python3
"""Compatibility merge entry point for commitments and safe relation intervals.

This wrapper no longer monkey-patches the imported ``merge_graph`` module. It
runs the historical merge in an isolated subprocess, then deterministically
rebuilds the two expansion-sensitive surfaces from the original fragments:
relations (preserving known ``valid_to`` values) and ``commitments``. The final
canonical graph is atomically published only after both passes succeed.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from copy import deepcopy
from pathlib import Path
from typing import Any

import merge_graph
from io_utils import atomic_write_json


def _blank(value: Any) -> bool:
    return value is None or value == "" or value == [] or value == {}


def _unique(values: list[Any]) -> list[Any]:
    result: list[Any] = []
    for value in values:
        if value not in result:
            result.append(value)
    return result


def _merge_value(left: Any, right: Any, field: str) -> Any:
    if _blank(left):
        return deepcopy(right)
    if _blank(right):
        return deepcopy(left)
    if isinstance(left, list) and isinstance(right, list):
        return _unique(deepcopy(left) + deepcopy(right))
    if isinstance(left, dict) and isinstance(right, dict):
        merged = deepcopy(left)
        for key, value in right.items():
            merged[key] = _merge_value(merged.get(key), value, key)
        return merged
    if field == "created_chapter" and isinstance(left, int) and isinstance(right, int):
        return min(left, right)
    if field == "resolved_chapter" and isinstance(left, int) and isinstance(right, int):
        return max(left, right)
    return deepcopy(right)


def _merge_record(left: dict[str, Any], right: dict[str, Any]) -> dict[str, Any]:
    merged = deepcopy(left)
    for field, value in right.items():
        merged[field] = _merge_value(merged.get(field), value, field)
    return merged


def safe_coalesce_relations(records: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, str]]:
    """Merge restatements without reopening a known closed interval."""
    result: list[dict[str, Any]] = []
    buckets: dict[tuple[str, str, str], list[int]] = {}
    canonicalization: dict[str, str] = {}
    ordered = sorted(records, key=lambda row: row.get("valid_from") if isinstance(row.get("valid_from"), int) else 0)
    for record in ordered:
        key = merge_graph.relation_key(record)
        match_index = next(
            (index for index in buckets.get(key, []) if merge_graph.relation_intervals_overlap(result[index], record)),
            None,
        )
        if match_index is None:
            buckets.setdefault(key, []).append(len(result))
            result.append(merge_graph.prepare_relation(record))
            continue
        prior = result[match_index]
        prior_id = prior["id"]
        duplicate_id = record["id"]
        # merge_relation_records already keeps explicit interval fields from the
        # merged records. Crucially, unlike the legacy coalescer, we do not pop a
        # previously known valid_to merely because a later overlapping fragment
        # restates the relation as active/open.
        result[match_index] = merge_graph.merge_relation_records(prior, merge_graph.prepare_relation(record))
        if duplicate_id != prior_id:
            canonicalization[duplicate_id] = prior_id
    return result, canonicalization


def _parse_id_map(values: list[str]) -> dict[str, str]:
    mapping: dict[str, str] = {}
    for item in values:
        if "=" not in item or not all(part.strip() for part in item.split("=", 1)):
            raise ValueError(f"invalid --id-map {item!r}; expected OLD=NEW")
        old, new = (part.strip() for part in item.split("=", 1))
        mapping[old] = new
    return mapping


def _load_fragments(paths: list[Path], id_mapping: dict[str, str]) -> list[dict[str, Any]]:
    fragments: list[dict[str, Any]] = []
    for path in paths:
        value = json.loads(path.resolve().read_text(encoding="utf-8"))
        if not isinstance(value, dict):
            raise ValueError(f"fragment must be a JSON object: {path}")
        fragments.append(merge_graph.remap_ids(value, id_mapping))
    return fragments


def _merge_commitments(fragments: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_id: dict[str, dict[str, Any]] = {}
    for fragment in fragments:
        raw = fragment.get("commitments")
        if raw is None:
            continue
        if not isinstance(raw, list):
            raise ValueError("commitments must be an array when present")
        for record in raw:
            if not isinstance(record, dict) or not isinstance(record.get("id"), str) or not record["id"]:
                raise ValueError("commitment record missing stable id")
            rid = record["id"]
            by_id[rid] = deepcopy(record) if rid not in by_id else _merge_record(by_id[rid], record)
    return list(by_id.values())


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", nargs="+", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--id-map", action="append", default=[], metavar="OLD=NEW")
    args = parser.parse_args(argv)
    try:
        id_mapping = _parse_id_map(args.id_map)
        fragments = _load_fragments(args.input, id_mapping)
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    script = Path(__file__).with_name("merge_graph.py")
    with tempfile.TemporaryDirectory(prefix="nkg-merge-") as temp_dir:
        base_output = Path(temp_dir) / "graph-base.json"
        command = [sys.executable, script, "--input", *args.input, "--output", base_output]
        if args.manifest:
            command += ["--manifest", args.manifest]
        for value in args.id_map:
            command += ["--id-map", value]
        process = subprocess.run([str(value) for value in command], capture_output=True, text=True, check=False)
        if process.stdout:
            print(process.stdout, end="" if process.stdout.endswith("\n") else "\n")
        if process.stderr:
            print(process.stderr, end="" if process.stderr.endswith("\n") else "\n", file=sys.stderr)
        if process.returncode != 0:
            return process.returncode
        try:
            graph = json.loads(base_output.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            print(f"ERROR reading base merge output: {exc}", file=sys.stderr)
            return 2

    raw_relations = [
        deepcopy(record)
        for fragment in fragments
        for record in fragment.get("relations", [])
        if isinstance(record, dict) and isinstance(record.get("id"), str)
    ]
    safe_relations, canonicalization = safe_coalesce_relations(raw_relations)
    if canonicalization:
        # The legacy merge uses the same matching/canonical-ID rule; remapping
        # again is idempotent and protects future changes from leaving stale refs.
        for key, value in list(graph.items()):
            if key not in {"metadata", "relations"} and isinstance(value, (list, dict)):
                graph[key] = merge_graph.remap_ids(value, canonicalization)
    graph["relations"] = safe_relations
    try:
        graph["commitments"] = _merge_commitments(fragments)
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    metadata = graph.setdefault("metadata", {})
    if isinstance(metadata, dict):
        metadata["relation_canonicalization"] = canonicalization
        metadata["merge_engine"] = "expanded-subprocess-v2"

    atomic_write_json(args.output.resolve(), graph, trailing_newline=False)
    print(json.dumps({
        "output": str(args.output.resolve()),
        "commitments": len(graph.get("commitments", [])),
        "relations": len(graph.get("relations", [])),
        "relations_coalesced": len(canonicalization),
        "merge_engine": "expanded-subprocess-v2",
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
