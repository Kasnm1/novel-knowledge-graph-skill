#!/usr/bin/env python3
"""Resolve one book/edition to one canonical run and optionally claim it.

Use an explicit stable ``book_id`` plus optional edition whenever possible.
Source SHA-256 identifies an immutable input snapshot, not the book: an appended
source file must reuse the same run. Legacy callers without ``book_id`` retain
hash-based resolution so existing runs remain discoverable.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping


IDENTITY_FILE = ".run-identity.json"
LOCK_FILE = "RUN.lock"
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class RunIdentityError(ValueError):
    """Base error for unsafe or ambiguous run identity."""


class DuplicateRunError(RunIdentityError):
    """More than one existing run claims the same source edition."""


class RunLockedError(RunIdentityError):
    """Another writer already owns this run."""


def source_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def read_object(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RunIdentityError(f"cannot read {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise RunIdentityError(f"{path} must contain a JSON object")
    return value


def normalized_hash(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    candidate = value.strip().lower()
    return candidate if SHA256_RE.fullmatch(candidate) else None


def recorded_hashes(run_dir: Path) -> set[str]:
    """Return every valid source hash declared by one immediate run directory."""

    hashes: set[str] = set()
    identity = run_dir / IDENTITY_FILE
    if identity.is_file():
        value = normalized_hash(read_object(identity).get("source_sha256"))
        if value:
            hashes.add(value)
    manifest = run_dir / "source_manifest.json"
    if manifest.is_file():
        value = normalized_hash(read_object(manifest).get("source_sha256"))
        if value:
            hashes.add(value)
    profile = run_dir / "book-profile.json"
    if profile.is_file():
        data = read_object(profile)
        source = data.get("source") if isinstance(data.get("source"), Mapping) else {}
        value = normalized_hash(source.get("sha256"))
        if value:
            hashes.add(value)
    if len(hashes) > 1:
        raise RunIdentityError(
            f"conflicting source hashes inside {run_dir}: {', '.join(sorted(hashes))}"
        )
    return hashes


def canonical_book_key(book_id: str, edition: str | None = None) -> str:
    book = book_id.strip()
    if not book:
        raise RunIdentityError("book_id must be non-empty")
    return f"{book}::{(edition or 'default').strip() or 'default'}"


def recorded_book_key(run_dir: Path) -> str | None:
    identity = run_dir / IDENTITY_FILE
    if identity.is_file():
        value = read_object(identity).get("book_key")
        if isinstance(value, str) and value.strip():
            return value.strip()
    profile = run_dir / "book-profile.json"
    if profile.is_file():
        data = read_object(profile)
        book_id = data.get("book_id")
        if isinstance(book_id, str) and book_id.strip():
            return canonical_book_key(book_id, data.get("edition") if isinstance(data.get("edition"), str) else None)
    return None


def discover_runs(runs_root: Path, digest: str) -> list[Path]:
    if not runs_root.is_dir():
        return []
    matches: list[Path] = []
    for candidate in sorted((path for path in runs_root.iterdir() if path.is_dir()), key=lambda path: path.name):
        if digest in recorded_hashes(candidate):
            matches.append(candidate.resolve())
    return matches


def resolve_run(source: Path, runs_root: Path, book_id: str | None = None, edition: str | None = None) -> tuple[Path, str, bool]:
    """Return ``(run_dir, source_hash, reused_existing)`` without writing."""

    source = source.resolve()
    if not source.is_file():
        raise RunIdentityError(f"source file does not exist: {source}")
    runs_root = runs_root.resolve()
    digest = source_sha256(source)
    book_key = canonical_book_key(book_id, edition) if book_id is not None else None
    matches = (
        [path.resolve() for path in sorted(runs_root.iterdir(), key=lambda p: p.name) if path.is_dir() and recorded_book_key(path) == book_key]
        if book_key and runs_root.is_dir()
        else discover_runs(runs_root, digest)
    )
    if len(matches) > 1:
        listing = "\n  - ".join(str(path) for path in matches)
        raise DuplicateRunError(
            "multiple runs already claim this source edition; choose and reconcile one before continuing:\n"
            f"  - {listing}"
        )
    if matches:
        return matches[0], digest, True

    identity_digest = hashlib.sha256(book_key.encode("utf-8")).hexdigest() if book_key else digest
    canonical = (runs_root / f"book-{identity_digest[:12]}").resolve()
    if canonical.exists():
        declared_key = recorded_book_key(canonical)
        declared = recorded_hashes(canonical)
        if (book_key and declared_key == book_key) or (not book_key and declared == {digest}):
            return canonical, digest, True
        if declared:
            raise RunIdentityError(
                f"canonical path collision: {canonical} declares {next(iter(declared))}, expected {digest}"
            )
        raise RunIdentityError(
            f"canonical path already exists without source identity: {canonical}"
        )
    return canonical, digest, False


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def write_identity(run_dir: Path, source: Path, digest: str, title: str | None, book_key: str | None = None) -> None:
    identity_path = run_dir / IDENTITY_FILE
    if identity_path.exists():
        existing = read_object(identity_path)
        declared_key = existing.get("book_key")
        declared = normalized_hash(existing.get("source_sha256"))
        if book_key and declared_key == book_key:
            snapshots = existing.get("source_snapshots") if isinstance(existing.get("source_snapshots"), list) else []
            snapshots = [row for row in snapshots if isinstance(row, dict)]
            if not any(row.get("sha256") == digest for row in snapshots):
                snapshots.append({"sha256": digest, "source_file": str(source.resolve()), "seen_at": utc_now()})
            existing.update({"source_sha256": digest, "source_file": str(source.resolve()), "source_snapshots": snapshots})
            temporary = identity_path.with_name(f"{identity_path.name}.tmp-{os.getpid()}")
            temporary.write_text(json.dumps(existing, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            temporary.replace(identity_path)
            return
        if declared != digest:
            raise RunIdentityError(
                f"{identity_path} declares {declared or 'no valid hash'}, expected {digest}"
            )
        return
    value = {
        "schema_version": "1.0",
        "source_sha256": digest,
        "source_file": str(source.resolve()),
        "title_hint": title,
        "identity_rule": "source_sha256",
        "created_at": utc_now(),
    }
    if book_key:
        value["book_key"] = book_key
        value["identity_rule"] = "book_id_and_edition"
        value["source_snapshots"] = [{"sha256": digest, "source_file": str(source.resolve()), "seen_at": value["created_at"]}]
    temporary = identity_path.with_name(f"{identity_path.name}.tmp-{os.getpid()}")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(identity_path)


def read_lock(run_dir: Path) -> dict[str, Any] | None:
    path = run_dir / LOCK_FILE
    return read_object(path) if path.is_file() else None


def claim_run(run_dir: Path, source: Path, digest: str, owner: str, title: str | None = None, book_key: str | None = None) -> dict[str, Any]:
    if not owner.strip():
        raise RunIdentityError("owner must be a non-empty task or session identifier")
    run_dir.mkdir(parents=True, exist_ok=True)
    lock_path = run_dir / LOCK_FILE
    record = {
        "schema_version": "1.0",
        "owner": owner,
        "source_sha256": digest,
        "pid": os.getpid(),
        "acquired_at": utc_now(),
    }
    try:
        descriptor = os.open(lock_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL)
    except FileExistsError as exc:
        current = read_lock(run_dir) or {}
        raise RunLockedError(
            f"run is already locked by {current.get('owner', 'unknown')} since "
            f"{current.get('acquired_at', 'unknown')}: {lock_path}"
        ) from exc
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="") as stream:
            json.dump(record, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
        write_identity(run_dir, source, digest, title, book_key)
    except Exception:
        lock_path.unlink(missing_ok=True)
        raise
    return record


def release_run(run_dir: Path, owner: str) -> dict[str, Any]:
    lock_path = run_dir / LOCK_FILE
    current = read_lock(run_dir)
    if current is None:
        raise RunIdentityError(f"run is not locked: {run_dir}")
    if current.get("owner") != owner:
        raise RunLockedError(
            f"lock belongs to {current.get('owner', 'unknown')}, not {owner}: {lock_path}"
        )
    lock_path.unlink()
    return current


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, type=Path, help="Immutable novel source file")
    parser.add_argument("--runs-root", required=True, type=Path, help="Directory whose immediate children are runs")
    parser.add_argument("--title", help="Metadata hint only; never affects the run path")
    parser.add_argument("--book-id", help="Stable book/work ID; recommended so appended sources reuse one run")
    parser.add_argument("--edition", help="Edition/translation ID; defaults to 'default' with --book-id")
    action = parser.add_mutually_exclusive_group()
    action.add_argument("--claim", action="store_true", help="Create/reuse the run and atomically acquire RUN.lock")
    action.add_argument("--release", action="store_true", help="Release RUN.lock owned by --owner")
    parser.add_argument("--owner", help="Task/session identifier; required for --claim and --release")
    args = parser.parse_args(argv)

    if (args.claim or args.release) and not args.owner:
        parser.error("--owner is required with --claim or --release")
    try:
        run_dir, digest, reused = resolve_run(args.source, args.runs_root, args.book_id, args.edition)
        book_key = canonical_book_key(args.book_id, args.edition) if args.book_id else None
        status = "resolved"
        lock: dict[str, Any] | None = read_lock(run_dir) if run_dir.is_dir() else None
        if args.claim:
            lock = claim_run(run_dir, args.source, digest, args.owner, args.title, book_key)
            status = "claimed"
        elif args.release:
            lock = release_run(run_dir, args.owner)
            status = "released"
        result = {
            "status": status,
            "run_dir": str(run_dir),
            "source_sha256": digest,
            "book_key": book_key,
            "reused_existing": reused,
            "lock": lock,
        }
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except DuplicateRunError as exc:
        print(f"DUPLICATE_RUN: {exc}", file=sys.stderr)
        return 3
    except RunLockedError as exc:
        print(f"RUN_LOCKED: {exc}", file=sys.stderr)
        return 4
    except RunIdentityError as exc:
        print(f"RUN_IDENTITY_ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
