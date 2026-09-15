#!/usr/bin/env python3
"""Compact or expand the semantic-name-preserving fragment wire format."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from io_utils import atomic_write_json
from nkg.extraction.wire import compact_fragment, expand_fragment


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("mode", choices=("compact", "expand"))
    p.add_argument("--input", required=True, type=Path)
    p.add_argument("--output", required=True, type=Path)
    args = p.parse_args()
    value = json.loads(args.input.read_text(encoding="utf-8"))
    result = compact_fragment(value) if args.mode == "compact" else expand_fragment(value)
    atomic_write_json(args.output, result, trailing_newline=False)
    print(json.dumps({"mode": args.mode, "output": str(args.output)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
