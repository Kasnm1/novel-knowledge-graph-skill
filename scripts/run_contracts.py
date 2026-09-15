#!/usr/bin/env python3
"""Build deterministic, derived contracts for one novel-graph run.

The graph and source manifest remain source artifacts.  This command only
writes three derived contracts in the run directory and deliberately retains
unknown fields already present in those contracts for human annotations.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping


DERIVED_PROFILE_KEYS = {
    "schema_version", "title", "source", "chapter_range", "validation",
    "vocabulary_sha256", "approval", "derived_at",
}
DERIVED_COVERAGE_KEYS = {"schema_version", "chapters", "summary", "derived_at"}
DERIVED_SNAPSHOT_KEYS = {
    "schema_version", "artifacts", "validation", "approval", "warnings",
    "created_at",
}


def canonical_bytes(value: Any) -> bytes:
    """Return the one JSON representation used for every contract hash."""

    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def sha256_value(value: Any) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_object(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"cannot read JSON object {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def write_json(path: Path, value: Mapping[str, Any]) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def int_set(value: Any) -> set[int]:
    return {item for item in value if isinstance(item, int) and not isinstance(item, bool)} if isinstance(value, list) else set()


def chapter_end_from_directory(name: str) -> int | None:
    """Infer an explicitly-labelled chapter range endpoint from a run name.

    An unlabelled number is intentionally ignored: dates and version numbers in
    run names must not become coverage facts.
    """

    match = re.search(
        r"(?i)(?:^|[_\-\s])ch(?:apter)?s?[_\-\s]*(\d+)(?:[_\-\s]*(?:to|[-–—])[_\-\s]*(\d+))?(?:$|[_\-\s])",
        name,
    )
    if not match:
        return None
    return int(match.group(2) or match.group(1))


def _chapter_values(*values: Any) -> set[int]:
    answer: set[int] = set()
    for value in values:
        answer.update(int_set(value))
    return answer


def build_coverage(manifest: Mapping[str, Any], graph: Mapping[str, Any], validation: Mapping[str, Any]) -> dict[str, Any]:
    """Build per-chapter state without promoting preparation into analysis."""

    metadata = graph.get("metadata") if isinstance(graph.get("metadata"), dict) else {}
    prepared = int_set(manifest.get("prepared_chapters"))
    analyzed = int_set(metadata.get("analyzed_chapters"))
    # A graph-wide successful validation validates the graph's analyzed claims;
    # it says nothing about merely prepared source chapters.
    validated = analyzed if validation.get("valid") is True else set()
    rendered = _chapter_values(metadata.get("rendered_chapters"), manifest.get("rendered_chapters"))
    excluded = _chapter_values(
        manifest.get("excluded_chapters"), manifest.get("missing_chapters"),
        manifest.get("missing_chapters_source_gap"), manifest.get("missing_chapters_unresolved"),
    )
    all_chapters = prepared | analyzed | validated | rendered | excluded
    rows = [
        {
            "chapter": chapter,
            "prepared": chapter in prepared,
            "analyzed": chapter in analyzed,
            "validated": chapter in validated,
            "rendered": chapter in rendered,
            "excluded": chapter in excluded,
        }
        for chapter in sorted(all_chapters)
    ]
    return {
        "schema_version": "1.0",
        "chapters": rows,
        "summary": {
            "prepared": len(prepared),
            "analyzed": len(analyzed),
            "validated": len(validated),
            "rendered": len(rendered),
            "excluded": len(excluded),
        },
        "derived_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }


def preserve_and_replace(existing: Mapping[str, Any], replacement: Mapping[str, Any], derived_keys: set[str]) -> dict[str, Any]:
    """Keep human/unknown fields while replacing only documented derived keys."""

    output = dict(existing)
    for key in derived_keys:
        output.pop(key, None)
    output.update(replacement)
    return output


def toolchain_hash(script_directory: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(script_directory.iterdir(), key=lambda item: item.name):
        if path.is_file() and path.suffix in {".py", ".js"}:
            digest.update(path.name.encode("utf-8"))
            digest.update(path.read_bytes())
    return digest.hexdigest()


def build_contracts(
    run_dir: Path,
    book_profile_path: Path | None = None,
    approval_status: str | None = None,
    approved_by: str | None = None,
) -> dict[str, Any]:
    """Create the three contracts and return their JSON objects for callers/tests."""

    run_dir = run_dir.resolve()
    graph_path = run_dir / "graph.json"
    validation_path = run_dir / "validation.json"
    source_path = run_dir / "source_manifest.json"
    vocabulary_path = run_dir / "display-vocabulary.json"
    graph, validation = read_object(graph_path), read_object(validation_path)
    source, vocabulary = read_object(source_path), read_object(vocabulary_path)

    profile_path = (book_profile_path or run_dir / "book-profile.json").resolve()
    coverage_path = run_dir / "coverage-ledger.json"
    snapshot_path = run_dir / "snapshot-manifest.json"
    existing_profile = read_object(profile_path) if profile_path.exists() else {}
    existing_coverage = read_object(coverage_path) if coverage_path.exists() else {}
    existing_snapshot = read_object(snapshot_path) if snapshot_path.exists() else {}
    metadata = graph.get("metadata") if isinstance(graph.get("metadata"), dict) else {}

    old_approval = existing_profile.get("approval") if isinstance(existing_profile.get("approval"), dict) else {}
    status = approval_status if approval_status is not None else old_approval.get("status", "draft")
    if not isinstance(status, str) or not status.strip():
        raise ValueError("approval status must be a non-empty string")
    approval: dict[str, Any] = {"status": status}
    chosen_approver = approved_by if approved_by is not None else old_approval.get("approved_by")
    if chosen_approver is not None:
        approval["approved_by"] = chosen_approver

    profile = preserve_and_replace(existing_profile, {
        "schema_version": "1.0",
        "title": metadata.get("title") or source.get("title"),
        "source": {"file": source.get("source_file"), "sha256": source.get("source_sha256")},
        "chapter_range": {"start": metadata.get("chapter_start", source.get("chapter_start")), "end": metadata.get("chapter_end", source.get("chapter_end"))},
        "validation": {"valid": validation.get("valid") is True, "sha256": sha256_file(validation_path)},
        "vocabulary_sha256": sha256_file(vocabulary_path),
        "approval": approval,
        "derived_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }, DERIVED_PROFILE_KEYS)
    coverage = preserve_and_replace(existing_coverage, build_coverage(source, graph, validation), DERIVED_COVERAGE_KEYS)
    write_json(profile_path, profile)
    write_json(coverage_path, coverage)

    warnings: list[str] = []
    named_end = chapter_end_from_directory(run_dir.name)
    graph_end = metadata.get("chapter_end")
    if named_end is not None and isinstance(graph_end, int) and named_end != graph_end:
        warnings.append(
            f"run directory chapter end {named_end} disagrees with graph metadata.chapter_end {graph_end}"
        )
    valid = validation.get("valid") is True
    snapshot = preserve_and_replace(existing_snapshot, {
        "schema_version": "1.0",
        "artifacts": {
            "source": source.get("source_sha256") or sha256_file(source_path),
            "graph": sha256_file(graph_path),
            "validation": sha256_file(validation_path),
            "toolchain": toolchain_hash(Path(__file__).resolve().parent),
            "profile": sha256_file(profile_path),
            "coverage": sha256_file(coverage_path),
        },
        "validation": {"valid": valid},
        # Approval is a separate human decision.  A valid graph remains draft
        # unless it was explicitly approved.
        "approval": {"status": status, "approved": valid and status == "approved", "approved_by": chosen_approver},
        "warnings": warnings,
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }, DERIVED_SNAPSHOT_KEYS)
    if chosen_approver is None:
        snapshot["approval"].pop("approved_by", None)
    write_json(snapshot_path, snapshot)
    return {"book_profile": profile, "coverage": coverage, "snapshot": snapshot}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--book-profile", type=Path, help="Profile path; defaults to <run-dir>/book-profile.json")
    parser.add_argument("--approval-status", help="Human approval state; defaults to existing status or draft")
    parser.add_argument("--approved-by", help="Human approver recorded only when supplied")
    args = parser.parse_args(argv)
    try:
        contracts = build_contracts(args.run_dir, args.book_profile, args.approval_status, args.approved_by)
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(contracts["snapshot"], ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
