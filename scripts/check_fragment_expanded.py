#!/usr/bin/env python3
"""Deprecated alias: `check_fragment.py` now runs the expansion checks itself."""
from __future__ import annotations

from check_fragment import main
from fragment_extensions import validate_fragment_extensions  # noqa: F401  (re-exported)

if __name__ == "__main__":
    raise SystemExit(main())
