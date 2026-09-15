#!/usr/bin/env python3
"""Record the active Skill version without copying or freezing its files."""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path


INCLUDED_SUFFIXES = {".md", ".json", ".py", ".js"}
EXCLUDED_PARTS = {"__pycache__", ".git", "assets"}


def file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def skill_files(root: Path) -> list[Path]:
    return sorted(
        path
        for path in root.rglob("*")
        if path.is_file()
        and path.suffix.lower() in INCLUDED_SUFFIXES
        and not EXCLUDED_PARTS.intersection(path.relative_to(root).parts)
    )


def aggregate_fingerprint(root: Path, files: list[Path]) -> str:
    digest = hashlib.sha256()
    for path in files:
        relative = path.relative_to(root).as_posix()
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(bytes.fromhex(file_hash(path)))
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--skill-root", required=True, type=Path)
    parser.add_argument("--run-dir", required=True, type=Path)
    parser.add_argument("--schema-version", default="current")
    parser.add_argument("--write-output", action="store_true")
    args = parser.parse_args()

    root = args.skill_root.resolve()
    run_dir = args.run_dir.resolve()
    skill_path = root / "SKILL.md"
    task_spec = root / "references" / "TASK-SPEC.template.md"
    if not skill_path.is_file() or not task_spec.is_file():
        parser.error("skill root must contain SKILL.md and references/TASK-SPEC.template.md")

    files = skill_files(root)
    receipt = {
        "schema_version": 1,
        "skill_name": "novel-knowledge-graph",
        "skill_root": str(root),
        "skill_fingerprint": aggregate_fingerprint(root, files),
        "story_schema_version": args.schema_version,
        "task_spec_fingerprint": file_hash(task_spec),
        "applied_at": datetime.now(timezone.utc).isoformat(),
        "file_count": len(files),
        "policy": "reference-current-skill-no-freeze",
    }

    rendered = json.dumps(receipt, ensure_ascii=False, indent=2) + "\n"
    if args.write_output:
        run_dir.mkdir(parents=True, exist_ok=True)
        target = run_dir / ".skill-version.json"
        temporary = target.with_suffix(".json.tmp")
        temporary.write_text(rendered, encoding="utf-8")
        temporary.replace(target)
        print(target)
    else:
        print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
