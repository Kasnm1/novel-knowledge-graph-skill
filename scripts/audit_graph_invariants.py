#!/usr/bin/env python3
"""Run deterministic story-world invariants in addition to schema validation."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from io_utils import atomic_write_json
from nkg.validation.invariants import validate_invariants


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--graph", required=True, type=Path)
    p.add_argument("--report", type=Path)
    p.add_argument("--warnings-as-errors", action="store_true")
    args = p.parse_args()
    graph = json.loads(args.graph.read_text(encoding="utf-8"))
    report = validate_invariants(graph)
    if args.report:
        atomic_write_json(args.report, report)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if not report["valid"]:
        return 1
    return 1 if args.warnings_as_errors and report["warning_count"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
