#!/usr/bin/env python3
"""One-command build for the complete expansion artifact set."""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path


def run(cmd) -> int:
    print("+", " ".join(map(str, cmd)))
    return subprocess.run([str(x) for x in cmd], check=False).returncode


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--graph", required=True, type=Path)
    p.add_argument("--output-dir", required=True, type=Path)
    p.add_argument("--manifest", type=Path)
    p.add_argument("--chapters-jsonl", type=Path)
    p.add_argument("--cutoff", type=int)
    p.add_argument("--protagonist-id", action="append", default=[])
    a = p.parse_args()
    d = Path(__file__).resolve().parent
    out = a.output_dir
    out.mkdir(parents=True, exist_ok=True)

    validate = [
        sys.executable, d / "validate_full_graph.py", "--graph", a.graph,
        "--base-report", out / "validation-base.json",
        "--extension-report", out / "validation-expansion.json",
    ]
    if a.manifest:
        validate += ["--manifest", a.manifest]
    if run(validate):
        return 1

    graph = a.graph
    if a.cutoff is not None:
        graph = out / f"graph-asof-{a.cutoff}.json"
        if run([sys.executable, d / "filter_graph_asof.py", "--graph", a.graph, "--chapter", a.cutoff, "--output", graph]):
            return 1

    views = out / "novel-views.json"
    command = [sys.executable, d / "derive_novel_views.py", "--graph", graph, "--output", views]
    for value in a.protagonist_id:
        command += ["--protagonist-id", value]
    if run(command):
        return 1
    if run([sys.executable, d / "build_expansion_dashboard.py", "--views", views, "--output-dir", out]):
        return 1

    candidates = [sys.executable, d / "build_expansion_candidates.py", "--graph", graph, "--output", out / "expansion-candidates.json"]
    if a.chapters_jsonl:
        candidates += ["--chapters-jsonl", a.chapters_jsonl]
    run(candidates)

    if a.chapters_jsonl:
        reader = [sys.executable, d / "build_reader_overlay.py", "--graph", a.graph, "--chapters-jsonl", a.chapters_jsonl, "--output", out / "reader.html"]
        if a.cutoff is not None:
            reader += ["--cutoff", a.cutoff]
        run(reader)

    print(json.dumps({
        "output_dir": str(out), "graph": str(graph), "views": str(views),
        "dashboard": str(out / "expansion-dashboard.html"),
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
