#!/usr/bin/env python3
"""Run the legacy validator plus the expansion contract validator.

Both reports are kept separate so structural validity and expansion coverage
cannot be conflated. A publish is valid only when both validators pass.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

from extension_contracts import validate_graph_extensions


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--graph", required=True, type=Path)
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--base-report", type=Path)
    parser.add_argument("--extension-report", type=Path)
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
    text = json.dumps(extension, ensure_ascii=False, indent=2)
    if args.extension_report:
        args.extension_report.parent.mkdir(parents=True, exist_ok=True)
        args.extension_report.write_text(text, encoding="utf-8")
    print("\n== expansion contract ==")
    print(text)
    return 0 if base.returncode == 0 and extension["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
