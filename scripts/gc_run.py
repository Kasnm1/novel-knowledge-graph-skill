#!/usr/bin/env python3
"""Transactional garbage collection for run workspaces.

Dry-run is the default. ``--apply`` writes an operation manifest before moving
anything, moves only outermost candidates, and rolls back on failure.
``--restore`` verifies an applied archive before moving it back. ``--purge``
permanently removes only a fully applied archive whose exact file set and
SHA-256 fingerprints still match the manifest.

Symlinks are deliberately excluded: GC must never follow a workspace symlink
outside the run root and hash, move, restore, or purge external content.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from io_utils import atomic_write_json

PATTERNS = ("_toolchain-*", "_archive", "_superseded", "__pycache__", "*.tmp", "*.chk", "_tmp*", ".tmp*")
SCHEMA_VERSION = 3


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _relative(path: Path, root: Path) -> Path:
    """Return a lexical relative path without following symlinks."""
    try:
        return path.absolute().relative_to(root.absolute())
    except ValueError as exc:
        raise ValueError(f"path escapes GC root: {path}") from exc


def _walk_files(directory: Path) -> Iterable[Path]:
    for current, dirs, files in os.walk(directory, topdown=True, followlinks=False):
        base = Path(current)
        symlink_dirs = [name for name in dirs if (base / name).is_symlink()]
        if symlink_dirs:
            raise ValueError(f"GC candidate contains symlink directories: {base}: {symlink_dirs}")
        for name in files:
            path = base / name
            if path.is_symlink():
                raise ValueError(f"GC candidate contains symlink file: {path}")
            if path.is_file():
                yield path


def describe(path: Path, root: Path) -> dict[str, Any]:
    if path.is_symlink():
        raise ValueError(f"refusing symlink GC candidate: {path}")
    rel = _relative(path, root)
    if path.is_file():
        return {"path": str(rel), "kind": "file", "size": path.stat().st_size, "sha256": sha256(path)}
    if not path.is_dir():
        raise ValueError(f"GC candidate is neither file nor directory: {path}")
    files: list[dict[str, Any]] = []
    total = 0
    for file in sorted(_walk_files(path)):
        size = file.stat().st_size
        total += size
        files.append({"path": str(_relative(file, root)), "size": size, "sha256": sha256(file)})
    return {"path": str(rel), "kind": "directory", "size": total, "files": files}


def _raw_candidates(root: Path) -> list[Path]:
    found: set[Path] = set()
    bases = [root]
    for child in root.iterdir():
        if child.name == "_gc_archive" or child.is_symlink():
            continue
        if child.is_dir():
            bases.append(child)
    for base in bases:
        for pattern in PATTERNS:
            for candidate in base.glob(pattern):
                if "_gc_archive" in candidate.parts or candidate.is_symlink():
                    continue
                _relative(candidate, root)
                found.add(candidate.absolute())
    return sorted(found, key=lambda path: (len(path.parts), str(path)))


def candidates(root: Path) -> list[Path]:
    """Return only outermost safe candidates so parent moves never duplicate children."""
    root = root.absolute()
    selected: list[Path] = []
    for path in _raw_candidates(root):
        if any(parent == path or parent in path.parents for parent in selected):
            continue
        # Describe during planning so nested symlinks fail before any move.
        describe(path, root)
        selected.append(path)
    return sorted(selected, key=str)


def build_plan(root: Path, archive: Path) -> dict[str, Any]:
    rows = [describe(path, root) for path in candidates(root)]
    operations = [
        {
            "source": row["path"],
            "destination": str((archive / row["path"]).relative_to(root)),
            "fingerprint": row,
            "status": "planned",
        }
        for row in rows
    ]
    return {
        "schema_version": SCHEMA_VERSION,
        "root": str(root),
        "archive": str(archive),
        "status": "planned",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "bytes": sum(row["size"] for row in rows),
        "operations": operations,
    }


def _write_manifest(archive: Path, manifest: dict[str, Any]) -> None:
    archive.mkdir(parents=True, exist_ok=True)
    atomic_write_json(archive / "manifest.json", manifest)


def _file_map(path: Path) -> dict[str, tuple[int, str]]:
    if path.is_symlink():
        raise ValueError(f"archive contains symlink: {path}")
    if path.is_file():
        return {".": (path.stat().st_size, sha256(path))}
    if not path.is_dir():
        return {}
    result: dict[str, tuple[int, str]] = {}
    for file in _walk_files(path):
        rel = str(file.relative_to(path))
        result[rel] = (file.stat().st_size, sha256(file))
    return result


def _expected_file_map(record: dict[str, Any]) -> dict[str, tuple[int, str]]:
    if record.get("kind") == "file":
        return {".": (int(record.get("size", -1)), str(record.get("sha256") or ""))}
    prefix = Path(str(record.get("path") or ""))
    result: dict[str, tuple[int, str]] = {}
    for item in record.get("files", []):
        if not isinstance(item, dict):
            raise ValueError("invalid directory fingerprint entry")
        rel = Path(str(item.get("path") or ""))
        try:
            local = rel.relative_to(prefix)
        except ValueError as exc:
            raise ValueError(f"fingerprint path escapes candidate: {rel}") from exc
        result[str(local)] = (int(item.get("size", -1)), str(item.get("sha256") or ""))
    return result


def _same_fingerprint(path: Path, record: dict[str, Any]) -> bool:
    if not path.exists() or path.is_symlink():
        return False
    try:
        return _file_map(path) == _expected_file_map(record)
    except (OSError, ValueError):
        return False


def apply_plan(root: Path, archive: Path, manifest: dict[str, Any]) -> dict[str, Any]:
    _write_manifest(archive, manifest)
    moved: list[dict[str, Any]] = []
    try:
        for op in manifest["operations"]:
            src = root / op["source"]
            dst = root / op["destination"]
            if not src.exists() or src.is_symlink():
                raise FileNotFoundError(f"planned source disappeared or became a symlink: {src}")
            if not _same_fingerprint(src, op["fingerprint"]):
                raise ValueError(f"planned source changed after scan: {src}")
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(src), str(dst))
            op["status"] = "moved"
            moved.append(op)
            _write_manifest(archive, manifest)
        manifest["status"] = "applied"
        manifest["applied_at"] = datetime.now(timezone.utc).isoformat()
        _write_manifest(archive, manifest)
        return manifest
    except Exception as exc:
        rollback_errors: list[str] = []
        for op in reversed(moved):
            src = root / op["source"]
            dst = root / op["destination"]
            try:
                src.parent.mkdir(parents=True, exist_ok=True)
                if dst.exists():
                    if src.exists():
                        raise FileExistsError(f"rollback destination already exists: {src}")
                    shutil.move(str(dst), str(src))
                op["status"] = "rolled_back"
            except Exception as rollback_exc:  # Preserve both primary and rollback failures in the manifest.
                rollback_errors.append(str(rollback_exc))
                op["status"] = "rollback_failed"
        manifest["status"] = "rollback_failed" if rollback_errors else "rolled_back"
        manifest["error"] = str(exc)
        manifest["rollback_errors"] = rollback_errors
        _write_manifest(archive, manifest)
        raise


def load_manifest(archive: Path, root: Path) -> dict[str, Any]:
    manifest_path = archive / "manifest.json"
    if not manifest_path.is_file() or manifest_path.is_symlink():
        raise ValueError("GC archive has no safe manifest.json")
    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    if data.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("unsupported GC manifest schema")
    if Path(str(data.get("root", ""))).absolute() != root.absolute():
        raise ValueError("manifest root does not match --root")
    if Path(str(data.get("archive", ""))).absolute() != archive.absolute():
        raise ValueError("manifest archive path mismatch")
    if not isinstance(data.get("operations"), list):
        raise ValueError("invalid GC manifest operations")
    return data


def _verify_archive(root: Path, manifest: dict[str, Any]) -> None:
    for op in manifest["operations"]:
        archived = root / op["destination"]
        if not _same_fingerprint(archived, op["fingerprint"]):
            raise ValueError(f"archive fingerprint mismatch: {archived}")


def restore(root: Path, archive: Path) -> dict[str, Any]:
    manifest = load_manifest(archive, root)
    if manifest.get("status") not in {"applied", "rollback_failed"}:
        raise ValueError(f"archive status {manifest.get('status')} is not restorable")
    if manifest.get("status") == "applied":
        _verify_archive(root, manifest)
    restored: list[str] = []
    for op in reversed(manifest["operations"]):
        src = root / op["destination"]
        dst = root / op["source"]
        if not src.exists():
            continue
        if src.is_symlink():
            raise ValueError(f"refusing to restore symlink from archive: {src}")
        if dst.exists():
            raise FileExistsError(f"restore destination already exists: {dst}")
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(src), str(dst))
        op["status"] = "restored"
        restored.append(op["source"])
        _write_manifest(archive, manifest)
    manifest["status"] = "restored"
    manifest["restored_at"] = datetime.now(timezone.utc).isoformat()
    manifest["restored"] = restored
    _write_manifest(archive, manifest)
    return manifest


def verify_for_purge(root: Path, archive: Path) -> dict[str, Any]:
    manifest = load_manifest(archive, root)
    if manifest.get("status") != "applied":
        raise ValueError("only a fully applied GC archive may be purged")
    _verify_archive(root, manifest)
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--restore", type=Path)
    parser.add_argument("--purge", type=Path)
    args = parser.parse_args()
    root = args.root.absolute()
    if not root.is_dir() or root.is_symlink():
        raise SystemExit("--root must be a real directory, not a symlink")
    if sum(bool(value) for value in (args.apply, args.restore, args.purge)) > 1:
        raise SystemExit("choose only one of --apply/--restore/--purge")
    if args.restore:
        result = restore(root, args.restore.absolute())
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    if args.purge:
        target = args.purge.absolute()
        try:
            target.relative_to(root / "_gc_archive")
        except ValueError as exc:
            raise SystemExit("--purge target must be under <root>/_gc_archive") from exc
        verify_for_purge(root, target)
        shutil.rmtree(target)
        print(json.dumps({"purged": str(target), "verified_manifest": True}, ensure_ascii=False))
        return 0
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    archive = root / "_gc_archive" / stamp
    plan = build_plan(root, archive)
    if not args.apply:
        print(json.dumps({**plan, "dry_run": True, "candidate_count": len(plan["operations"])}, ensure_ascii=False, indent=2))
        return 0
    result = apply_plan(root, archive, plan)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
