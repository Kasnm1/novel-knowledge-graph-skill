#!/usr/bin/env python3
"""Accuracy regression gate for retrieval/token optimizations."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from io_utils import atomic_write_json
from nkg.validation.accuracy import compare_outputs


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--baseline", required=True, type=Path)
    p.add_argument("--optimized", required=True, type=Path)
    p.add_argument("--report", type=Path)
    args = p.parse_args()
    baseline = json.loads(args.baseline.read_text(encoding="utf-8"))
    optimized = json.loads(args.optimized.read_text(encoding="utf-8"))
    report = compare_outputs(baseline, optimized)
    if args.report:
        atomic_write_json(args.report, report)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
