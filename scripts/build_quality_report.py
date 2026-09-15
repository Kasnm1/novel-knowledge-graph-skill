#!/usr/bin/env python3
"""Build deterministic data-quality/provenance audit metrics."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from io_utils import atomic_write_json
from nkg.views.quality import build_quality_summary


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--graph", required=True, type=Path)
    p.add_argument("--output", required=True, type=Path)
    args = p.parse_args()
    graph = json.loads(args.graph.read_text(encoding="utf-8"))
    report = build_quality_summary(graph)
    atomic_write_json(args.output, report)
    print(json.dumps({
        "output": str(args.output),
        "evidence_ratio": report["evidence"]["ratio"],
        "temporal_gaps": report["temporal_provenance"]["gap_count"],
        "unresolved": report["review"]["unresolved_count"],
        "invariant_warnings": report["invariants"]["warning_count"],
    }, ensure_ascii=False))
    return 0 if report["invariants"]["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
