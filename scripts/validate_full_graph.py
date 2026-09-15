#!/usr/bin/env python3
"""Run structural, expansion and semantic-invariant validators.

Reports stay separate so structural validity, expansion contract coverage and
story-world consistency are not conflated. Publication fails on hard errors in
any layer; invariant warnings remain review work rather than automatic facts.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

from extension_contracts import validate_graph_extensions
from io_utils import atomic_write_json
from nkg.validation.invariants import validate_invariants


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--graph", required=True, type=Path)
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--base-report", type=Path)
    parser.add_argument("--extension-report", type=Path)
    parser.add_argument("--invariant-report", type=Path)
    args = parser.parse_args()

    script_dir = Path(__file__).resolve().parent
    command = [sys.executable, str(script_dir / "validate_graph.py"), "--graph", str(args.graph)]
    if args.manifest:
        command += ["--manifest", str(args.manifest)]
    if args.base_report:
        command += ["--report", str(args.base_report)]
    base = subprocess.run(command, check=False)

    graph = json.loads(args.graph.read_text(encoding="utf-8"))
    extension = validate_graph_extensions(graph)
    invariants = validate_invariants(graph)
    if args.extension_report:
        atomic_write_json(args.extension_report, extension)
    if args.invariant_report:
        atomic_write_json(args.invariant_report, invariants)

    print("\n== expansion contract ==")
    print(json.dumps(extension, ensure_ascii=False, indent=2))
    print("\n== semantic invariants ==")
    print(json.dumps(invariants, ensure_ascii=False, indent=2))
    return 0 if base.returncode == 0 and extension["valid"] and invariants["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
