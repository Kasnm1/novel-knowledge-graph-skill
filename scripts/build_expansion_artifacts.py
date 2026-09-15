#!/usr/bin/env python3
"""Fail-closed one-command build for the final artifact set.

Every subprocess result is recorded. A build is successful only when every
required step returns zero and every declared artifact exists. Complete prior
builds may be reused only when all input, parameter, implementation and artifact
fingerprints still match. The manifest is always written atomically.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from io_utils import atomic_write_json
from nkg.core.cache import build_cache_key, verify_artifact_manifest


def digest(path: Path) -> dict[str, Any]:
    h = hashlib.sha256()
    size = 0
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            size += len(chunk)
            h.update(chunk)
    return {"path": str(path), "size": size, "sha256": h.hexdigest()}


def run_step(name: str, cmd: list[Any], manifest: dict[str, Any], timeout: float | None = None) -> int:
    started = time.perf_counter()
    command = [str(value) for value in cmd]
    try:
        proc = subprocess.run(
            command,
            capture_output=True,
            text=True,
            check=False,
            timeout=timeout if timeout and timeout > 0 else None,
        )
        code = proc.returncode
        stdout, stderr = proc.stdout, proc.stderr
        timed_out = False
    except subprocess.TimeoutExpired as exc:
        code = 124
        timed_out = True
        stdout = exc.stdout.decode(errors="replace") if isinstance(exc.stdout, bytes) else (exc.stdout or "")
        stderr = exc.stderr.decode(errors="replace") if isinstance(exc.stderr, bytes) else (exc.stderr or "")
        stderr = (stderr + f"\nstep timed out after {timeout:g}s").strip()
    manifest["steps"].append({
        "name": name,
        "command": command,
        "returncode": code,
        "timed_out": timed_out,
        "duration_ms": round((time.perf_counter() - started) * 1000, 3),
        "stdout": stdout[-6000:],
        "stderr": stderr[-6000:],
    })
    return code


def write_manifest(path: Path, manifest: dict[str, Any]) -> None:
    atomic_write_json(path, manifest)


def implementation_files(scripts: Path) -> list[Path]:
    names = (
        "build_expansion_artifacts.py", "validate_full_graph.py", "validate_graph.py",
        "extension_contracts.py", "filter_graph_asof.py", "derive_novel_views.py",
        "build_quality_report.py", "build_provenance_index.py", "build_entity_profiles.py",
        "build_story_time_view.py", "build_unified_dashboard.py", "enhance_unified_dashboard.py",
        "build_expansion_candidates.py", "build_reader_overlay.py", "build_snapshot_checkpoints.py",
    )
    files = [scripts / name for name in names]
    files.extend((scripts / "nkg").rglob("*.py"))
    return [path for path in files if path.is_file()]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--graph", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--chapters-jsonl", type=Path)
    parser.add_argument("--collection-manifest", type=Path)
    parser.add_argument("--display-hints", type=Path, help="Optional AI-authored derived display hints; never a canonical fact source")
    parser.add_argument("--cutoff", type=int)
    parser.add_argument("--protagonist-id", action="append", default=[])
    parser.add_argument("--checkpoint-interval", type=int, default=0, help="Prebuild strict snapshot checkpoints; 0 disables")
    parser.add_argument("--no-cache", action="store_true", help="Force a rebuild even if a fingerprint-identical complete build exists")
    parser.add_argument("--step-timeout", type=float, default=0, help="Optional per-subprocess timeout in seconds; 0 disables the timeout.")
    args = parser.parse_args()
    if args.step_timeout < 0:
        parser.error("--step-timeout must be >= 0")
    if args.checkpoint_interval < 0:
        parser.error("--checkpoint-interval must be >= 0")

    scripts = Path(__file__).resolve().parent
    out = args.output_dir.resolve()
    out.mkdir(parents=True, exist_ok=True)
    manifest_path = out / "artifact-manifest.json"
    timeout = args.step_timeout or None
    build_started = time.perf_counter()

    cache_key, cache_material = build_cache_key(
        input_files={
            "graph": args.graph.resolve(),
            "source_manifest": args.manifest.resolve() if args.manifest else None,
            "chapters_jsonl": args.chapters_jsonl.resolve() if args.chapters_jsonl else None,
            "collection_manifest": args.collection_manifest.resolve() if args.collection_manifest else None,
            "display_hints": args.display_hints.resolve() if args.display_hints else None,
        },
        parameters={
            "cutoff": args.cutoff,
            "protagonist_ids": sorted(args.protagonist_id),
            "checkpoint_interval": args.checkpoint_interval,
        },
        implementation_files=implementation_files(scripts),
    )

    if not args.no_cache and manifest_path.is_file():
        try:
            previous = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            previous = None
        if isinstance(previous, dict) and previous.get("build_cache_key") == cache_key:
            valid_cache, cache_errors = verify_artifact_manifest(previous)
            if valid_cache:
                previous["cache_reused_at"] = datetime.now(timezone.utc).isoformat()
                previous["last_invocation_duration_ms"] = round((time.perf_counter() - build_started) * 1000, 3)
                write_manifest(manifest_path, previous)
                print(json.dumps({"status": "reused", "manifest": str(manifest_path), "build_cache_key": cache_key}, ensure_ascii=False))
                return 0
            previous["cache_reuse_rejected"] = cache_errors

    manifest: dict[str, Any] = {
        "schema_version": 6,
        "status": "running",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "source_graph": str(args.graph.resolve()),
        "source_graph_sha256": digest(args.graph)["sha256"],
        "cutoff": args.cutoff,
        "checkpoint_interval": args.checkpoint_interval,
        "step_timeout_seconds": timeout,
        "display_hints": str(args.display_hints.resolve()) if args.display_hints else None,
        "build_cache_key": cache_key,
        "cache_material": cache_material,
        "steps": [],
        "required_artifacts": [],
        "artifacts": [],
    }
    write_manifest(manifest_path, manifest)

    def fail(reason: str) -> int:
        manifest["status"] = "failed"
        manifest["failure_reason"] = reason
        manifest["duration_ms"] = round((time.perf_counter() - build_started) * 1000, 3)
        manifest["finished_at"] = datetime.now(timezone.utc).isoformat()
        write_manifest(manifest_path, manifest)
        print(json.dumps({"status": "failed", "reason": reason, "manifest": str(manifest_path)}, ensure_ascii=False))
        return 1

    validate = [
        sys.executable, scripts / "validate_full_graph.py", "--graph", args.graph,
        "--base-report", out / "validation-base.json",
        "--extension-report", out / "validation-expansion.json",
        "--invariant-report", out / "validation-invariants.json",
    ]
    if args.manifest:
        validate += ["--manifest", args.manifest]
    if run_step("validate", validate, manifest, timeout):
        return fail("validation failed")

    graph = args.graph
    if args.cutoff is not None:
        graph = out / f"graph-asof-{args.cutoff}.json"
        if run_step("spoiler-closure", [sys.executable, scripts / "filter_graph_asof.py", "--graph", args.graph, "--chapter", args.cutoff, "--output", graph], manifest, timeout):
            return fail("spoiler closure failed")

    views = out / "novel-views.json"
    command = [sys.executable, scripts / "derive_novel_views.py", "--graph", graph, "--output", views]
    for protagonist_id in args.protagonist_id:
        command += ["--protagonist-id", protagonist_id]
    if run_step("derive-views", command, manifest, timeout):
        return fail("view derivation failed")

    story_time = out / "story-time-view.json"
    if run_step("story-time", [sys.executable, scripts / "build_story_time_view.py", "--graph", graph, "--output", story_time], manifest, timeout):
        return fail("story time view failed")

    quality = out / "quality-report.json"
    if run_step("quality", [sys.executable, scripts / "build_quality_report.py", "--graph", graph, "--output", quality], manifest, timeout):
        return fail("quality/invariant report failed")

    provenance = out / "provenance-index.json"
    if run_step("provenance", [sys.executable, scripts / "build_provenance_index.py", "--graph", graph, "--output", provenance], manifest, timeout):
        return fail("provenance index failed")

    profiles = out / "entity-profiles.json"
    profile_command = [sys.executable, scripts / "build_entity_profiles.py", "--graph", graph, "--output", profiles]
    if args.display_hints:
        profile_command += ["--hints", args.display_hints]
    if run_step("entity-profiles", profile_command, manifest, timeout):
        return fail("entity display profile build failed")

    candidate_command = [sys.executable, scripts / "build_expansion_candidates.py", "--graph", args.graph, "--output", out / "expansion-candidates.json"]
    if args.chapters_jsonl:
        candidate_command += ["--chapters-jsonl", args.chapters_jsonl]
    if args.cutoff is not None:
        candidate_command += ["--cutoff", args.cutoff]
    if run_step("candidates", candidate_command, manifest, timeout):
        return fail("candidate scan incomplete or failed")

    dashboard = [sys.executable, scripts / "build_unified_dashboard.py", "--graph", args.graph, "--output-dir", out]
    if args.cutoff is not None:
        dashboard += ["--cutoff", args.cutoff]
    if args.collection_manifest:
        dashboard += ["--collection-manifest", args.collection_manifest]
    for protagonist_id in args.protagonist_id:
        dashboard += ["--protagonist-id", protagonist_id]
    if run_step("dashboard", dashboard, manifest, timeout):
        return fail("dashboard build failed")
    if run_step("dashboard-intelligence", [
        sys.executable, scripts / "enhance_unified_dashboard.py",
        "--dashboard", out / "dashboard.html", "--profiles", profiles, "--quality", quality,
    ], manifest, timeout):
        return fail("dashboard intelligence enhancement failed")

    if args.chapters_jsonl:
        reader = [sys.executable, scripts / "build_reader_overlay.py", "--graph", args.graph, "--chapters-jsonl", args.chapters_jsonl, "--output", out / "reader.html"]
        if args.cutoff is not None:
            reader += ["--cutoff", args.cutoff]
        if run_step("reader", reader, manifest, timeout):
            return fail("reader build failed")

    checkpoint_manifest: Path | None = None
    if args.checkpoint_interval:
        checkpoint_dir = out / "checkpoints"
        checkpoint_command = [sys.executable, scripts / "build_snapshot_checkpoints.py", "--graph", graph, "--output-dir", checkpoint_dir, "--interval", args.checkpoint_interval]
        if run_step("checkpoints", checkpoint_command, manifest, timeout):
            return fail("snapshot checkpoint build failed")
        checkpoint_manifest = checkpoint_dir / "checkpoint-manifest.json"

    required = [
        out / "validation-base.json", out / "validation-expansion.json", out / "validation-invariants.json",
        views, story_time, quality, provenance, profiles, out / "dashboard.html", out / "expansion-candidates.json",
    ]
    if args.cutoff is not None:
        required.append(graph)
    if args.chapters_jsonl:
        required.append(out / "reader.html")
    if checkpoint_manifest is not None:
        required.append(checkpoint_manifest)
    manifest["required_artifacts"] = [str(path) for path in required]
    missing = [str(path) for path in required if not path.is_file()]
    if missing:
        return fail("missing required artifacts: " + ", ".join(missing))

    manifest["artifacts"] = [digest(path) for path in required]
    manifest["status"] = "complete"
    manifest["duration_ms"] = round((time.perf_counter() - build_started) * 1000, 3)
    manifest["finished_at"] = datetime.now(timezone.utc).isoformat()
    write_manifest(manifest_path, manifest)
    print(json.dumps({
        "status": "complete", "manifest": str(manifest_path), "dashboard": str(out / "dashboard.html"),
        "views": str(views), "story_time": str(story_time), "quality": str(quality), "provenance": str(provenance),
        "profiles": str(profiles), "build_cache_key": cache_key,
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
