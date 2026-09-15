#!/usr/bin/env python3
"""Deprecated compatibility alias for the canonical merge entry point.

Expansion semantics now live directly in ``merge_graph.py``: commitments share
the canonical array registry, closed relation intervals are preserved, and the
published graph is atomic. New workflows should invoke ``merge_graph.py``.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import merge_graph


def main(argv: list[str] | None = None) -> int:
    if argv is None:
        return merge_graph.main()
    # Programmatic compatibility for tests/older callers without mutating
    # process-global sys.argv. The subprocess executes the same canonical engine.
    script = Path(__file__).with_name("merge_graph.py")
    return subprocess.run([sys.executable, str(script), *argv], check=False).returncode


if __name__ == "__main__":
    raise SystemExit(main())
