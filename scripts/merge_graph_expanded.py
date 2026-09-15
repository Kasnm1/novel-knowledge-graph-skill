#!/usr/bin/env python3
"""Deprecated compatibility alias for the canonical merge entry point.

Expansion semantics live directly in ``merge_graph.py``. This wrapper exists
only for older callers/tests and records that the compatibility entry point was
used; the actual canonical engine is still ``merge_graph.py``.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import merge_graph
from io_utils import atomic_write_json


def _mark_compat(argv: list[str]) -> None:
    try:
        index = argv.index("--output")
        output = Path(argv[index + 1])
    except (ValueError, IndexError):
        return
    if not output.is_file():
        return
    graph = json.loads(output.read_text(encoding="utf-8"))
    metadata = graph.setdefault("metadata", {})
    # Preserve the historical diagnostic key for consumers that still inspect
    # it, while explicitly naming the real engine introduced by the v2 merge.
    metadata["merge_engine"] = "expanded-subprocess-v2"
    metadata["canonical_merge_engine"] = "merge_graph.py/v2"
    atomic_write_json(output, graph, trailing_newline=False)


def main(argv: list[str] | None = None) -> int:
    if argv is None:
        return merge_graph.main()
    script = Path(__file__).with_name("merge_graph.py")
    code = subprocess.run([sys.executable, str(script), *argv], check=False).returncode
    if code == 0:
        _mark_compat(argv)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
