#!/usr/bin/env python3
"""Deprecated alias for ``merge_graph.py``, kept for older callers.

It runs the canonical merge in-process and stamps ``metadata.merge_engine`` so a
graph built through the alias can still be recognised.
"""
from __future__ import annotations

import json
from pathlib import Path

import merge_graph
from io_utils import atomic_write_json


def _output(argv: list[str]) -> Path | None:
    try:
        return Path(argv[argv.index("--output") + 1])
    except (ValueError, IndexError):
        return None


def main(argv: list[str] | None = None) -> int:
    import sys
    args = list(sys.argv[1:] if argv is None else argv)
    code = merge_graph.main(args)
    output = _output(args)
    if code == 0 and output is not None and output.is_file():
        graph = json.loads(output.read_text(encoding="utf-8"))
        metadata = graph.setdefault("metadata", {})
        metadata["merge_engine"] = "compat-alias"
        metadata["canonical_merge_engine"] = "merge_graph.py/v2"
        atomic_write_json(output, graph, trailing_newline=False)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
