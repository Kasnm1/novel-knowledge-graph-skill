#!/usr/bin/env python3
"""Apply guarded JSONL corrections to a novel graph without mutating its base.

Corrections target records in top-level graph arrays by ``collection`` and
``record_id`` (or ``target: {collection, id}``).  Hash guards are SHA-256 of
canonical JSON for the selected record; a retract's post-state hashes JSON null.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def value_hash(value: Any) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def read_graph(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"cannot read graph {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError("graph must be a JSON object")
    return data


def read_corrections(path: Path) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise ValueError(f"cannot read corrections {path}: {exc}") from exc
    for line_number, line in enumerate(lines, 1):
        if not line.strip():
            continue
        try:
            item = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"invalid corrections JSONL line {line_number}: {exc}") from exc
        if not isinstance(item, dict):
            raise ValueError(f"corrections JSONL line {line_number} must be an object")
        item["_line"] = line_number
        items.append(item)
    return items


def selector(correction: Mapping[str, Any]) -> tuple[str, str | None]:
    target = correction.get("target") if isinstance(correction.get("target"), dict) else {}
    collection = correction.get("collection", correction.get("target_collection", target.get("collection")))
    record_id = correction.get("record_id", correction.get("target_id", target.get("id")))
    if not isinstance(collection, str) or not collection:
        raise ValueError("correction requires string collection")
    if record_id is not None and not isinstance(record_id, str):
        raise ValueError("record_id must be a string")
    return collection, record_id


def array_for(graph: dict[str, Any], collection: str) -> list[Any]:
    value = graph.get(collection)
    if not isinstance(value, list):
        raise ValueError(f"collection {collection!r} is not a top-level array")
    return value


def record_index(records: list[Any], record_id: str) -> int:
    matches = [index for index, record in enumerate(records) if isinstance(record, dict) and record.get("id") == record_id]
    if not matches:
        raise ValueError(f"record id {record_id!r} was not found")
    if len(matches) != 1:
        raise ValueError(f"record id {record_id!r} is not unique")
    return matches[0]


def parse_path(value: Any) -> list[str | int]:
    if isinstance(value, str):
        parts: list[str | int] = []
        for part in value.split("."):
            if not part:
                raise ValueError("path has an empty segment")
            parts.append(int(part) if part.isdecimal() else part)
        return parts
    if isinstance(value, list) and all(isinstance(item, (str, int)) and not isinstance(item, bool) for item in value):
        return list(value)
    raise ValueError("replace requires path as dot string or list")


def replace_path(record: dict[str, Any], path: list[str | int], value: Any) -> None:
    current: Any = record
    for segment in path[:-1]:
        if isinstance(current, dict) and segment in current:
            current = current[segment]
        elif isinstance(current, list) and isinstance(segment, int) and 0 <= segment < len(current):
            current = current[segment]
        else:
            raise ValueError(f"path segment {segment!r} does not exist")
    last = path[-1]
    if isinstance(current, dict) and isinstance(last, str) and last in current:
        current[last] = copy.deepcopy(value)
    elif isinstance(current, list) and isinstance(last, int) and 0 <= last < len(current):
        current[last] = copy.deepcopy(value)
    else:
        raise ValueError(f"path target {last!r} does not exist")


def replace_references(value: Any, old_id: str, new_id: str) -> int:
    """Replace all exact ID-string references throughout the graph."""

    changed = 0
    if isinstance(value, dict):
        for key, child in list(value.items()):
            if child == old_id:
                value[key] = new_id
                changed += 1
            else:
                changed += replace_references(child, old_id, new_id)
    elif isinstance(value, list):
        for index, child in enumerate(value):
            if child == old_id:
                value[index] = new_id
                changed += 1
            else:
                changed += replace_references(child, old_id, new_id)
    return changed


def metadata_ledger(graph: dict[str, Any]) -> list[dict[str, str]]:
    metadata = graph.setdefault("metadata", {})
    if not isinstance(metadata, dict):
        raise ValueError("graph metadata must be an object when corrections are applied")
    raw = metadata.setdefault("applied_corrections", [])
    if not isinstance(raw, list):
        raise ValueError("metadata.applied_corrections must be an array")
    for item in raw:
        if not isinstance(item, dict) or not isinstance(item.get("correction_id"), str) or not isinstance(item.get("sha256"), str):
            raise ValueError("metadata.applied_corrections contains an invalid ledger entry")
    # Return the graph-owned list, not a validation copy: successful staged
    # corrections must persist their IDs so replay can be idempotent.
    return raw


def require_hash(correction: Mapping[str, Any], key: str, actual: str) -> None:
    expected = correction.get(key)
    if expected is not None and expected != actual:
        raise ValueError(f"{key} conflict: expected {expected}, got {actual}")


def apply_corrections(base_graph: Mapping[str, Any], corrections: list[dict[str, Any]]) -> tuple[dict[str, Any], dict[str, Any]]:
    """Apply all corrections transactionally, returning staged graph and report."""

    graph = copy.deepcopy(dict(base_graph))
    ledger = metadata_ledger(graph)
    known = {item["correction_id"]: item["sha256"] for item in ledger}
    results: list[dict[str, Any]] = []
    base_hash = value_hash(base_graph)

    for correction in corrections:
        correction_id = correction.get("correction_id")
        if not isinstance(correction_id, str) or not correction_id:
            raise ValueError("correction requires non-empty correction_id")
        normalized = {key: value for key, value in correction.items() if key != "_line"}
        correction_hash = value_hash(normalized)
        prior = known.get(correction_id)
        if prior is not None:
            if prior != correction_hash:
                raise ValueError(f"correction_id {correction_id!r} was replayed with different content")
            results.append({"correction_id": correction_id, "line": correction.get("_line"), "status": "already_applied"})
            continue

        operation = correction.get("operation", correction.get("op"))
        if operation not in {"replace", "append", "retract", "rekey"}:
            raise ValueError(f"correction {correction_id!r} has unsupported operation {operation!r}")
        collection, selected_id = selector(correction)
        records = array_for(graph, collection)
        before: Any
        after: Any
        details: dict[str, Any] = {}

        if operation == "append":
            value = correction.get("value", correction.get("record"))
            if not isinstance(value, dict):
                raise ValueError("append requires object value")
            appended_id = value.get("id")
            if not isinstance(appended_id, str) or not appended_id:
                raise ValueError("append value requires non-empty id")
            if selected_id is not None and selected_id != appended_id:
                raise ValueError("append record_id must match value.id")
            before = records
            require_hash(correction, "before_hash", value_hash(before))
            existing = [item for item in records if isinstance(item, dict) and item.get("id") == appended_id]
            if existing:
                if len(existing) == 1 and value_hash(existing[0]) == value_hash(value):
                    results.append({"correction_id": correction_id, "line": correction.get("_line"), "status": "already_applied"})
                    known[correction_id] = correction_hash
                    continue
                raise ValueError(f"append id {appended_id!r} already exists")
            records.append(copy.deepcopy(value))
            after = value
            details["record_id"] = appended_id
        else:
            if selected_id is None:
                raise ValueError(f"{operation} requires record_id")
            index = record_index(records, selected_id)
            before = records[index]
            require_hash(correction, "before_hash", value_hash(before))
            if operation == "replace":
                replace_path(records[index], parse_path(correction.get("path")), correction.get("value"))
                after = records[index]
            elif operation == "retract":
                records.pop(index)
                after = None
            else:
                new_id = correction.get("new_id", correction.get("value"))
                if not isinstance(new_id, str) or not new_id:
                    raise ValueError("rekey requires non-empty new_id")
                for top in graph.values():
                    if isinstance(top, list) and any(isinstance(item, dict) and item.get("id") == new_id for item in top):
                        raise ValueError(f"new id {new_id!r} already exists")
                records[index]["id"] = new_id
                details["rekeyed_references"] = replace_references(graph, selected_id, new_id)
                after = records[index]
                details["new_id"] = new_id
        require_hash(correction, "after_hash", value_hash(after))
        known[correction_id] = correction_hash
        ledger.append({"correction_id": correction_id, "sha256": correction_hash})
        results.append({"correction_id": correction_id, "line": correction.get("_line"), "status": "applied", **details})

    report = {
        "schema_version": "1.0",
        "success": True,
        "base_graph_sha256": base_hash,
        "output_graph_sha256": value_hash(graph),
        "applied_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "corrections": results,
    }
    return graph, report


def write_json(path: Path, value: Mapping[str, Any]) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--graph", type=Path, required=True, help="Immutable base graph.json")
    parser.add_argument("--corrections", type=Path, required=True, help="JSONL correction stream")
    parser.add_argument("--write-output", type=Path, help="Destination graph; base graph is never overwritten")
    parser.add_argument("--dry-run", action="store_true", help="Validate and stage but do not write output")
    parser.add_argument("--report", type=Path, help="Optional application report destination (not written on dry-run)")
    args = parser.parse_args(argv)
    if not args.dry_run and args.write_output is None:
        parser.error("--write-output is required unless --dry-run is used")
    if args.write_output is not None and args.write_output.resolve() == args.graph.resolve():
        parser.error("--write-output must not overwrite the base graph")
    try:
        staged, report = apply_corrections(read_graph(args.graph), read_corrections(args.corrections))
        report["dry_run"] = args.dry_run
        if not args.dry_run:
            write_json(args.write_output, staged)
            if args.report:
                write_json(args.report, report)
    except ValueError as exc:
        print(json.dumps({"success": False, "error": str(exc)}, ensure_ascii=False, sort_keys=True), file=sys.stderr)
        return 2
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
