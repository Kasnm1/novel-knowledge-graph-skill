#!/usr/bin/env python3
"""Build a record-to-evidence provenance index for audit and reader drill-down."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from io_utils import atomic_write_json
from nkg.core.provenance import build_provenance_index


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--graph", required=True, type=Path)
    p.add_argument("--output", required=True, type=Path)
    args = p.parse_args()
    graph = json.loads(args.graph.read_text(encoding="utf-8"))
    result = build_provenance_index(graph)
    atomic_write_json(args.output, result)
    print(json.dumps({"output": str(args.output), "facts": result["fact_count"], "missing_evidence": len(result["missing_evidence_ids"])}, ensure_ascii=False))
    return 0 if not result["missing_evidence_ids"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
