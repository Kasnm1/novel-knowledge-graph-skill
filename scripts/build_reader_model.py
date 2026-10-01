#!/usr/bin/env python3
"""Build the reader model (`reader-model.json`) the dashboard renders.

Every chapter-dependent value is precomputed as an interval by
`nkg.views.reader_model`; the page only picks the interval that contains the
chapter on the slider. With `--cutoff N` the graph is first closed at chapter N
(`filter_graph`, strict), and the model then passes the late-name leak gate:
any name not yet introduced by chapter N fails the build.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from asof_names import leak_report
from nkg.temporal.asof import filter_graph
from nkg.views.reader_model import build_reader_model, model_text


def _load(path: Path | None) -> Any:
    return json.loads(path.read_text(encoding="utf-8")) if path and path.exists() else None


def build(args: argparse.Namespace) -> dict[str, Any]:
    graph = json.loads(args.graph.read_text(encoding="utf-8"))
    source = graph
    if args.cutoff is not None:
        graph = filter_graph(graph, args.cutoff, strict=True)
    model = build_reader_model(graph, hints=_load(args.display_hints), ledger=_load(args.ledger),
                               vocabulary=_load(args.vocabulary), protagonist_ids=args.protagonist_id or (),
                               cutoff=args.cutoff)
    if args.cutoff is not None:
        leaks = leak_report({"reader-model": model_text(model)}, source, args.cutoff)
        if leaks:
            raise SystemExit(f"leak gate: names after chapter {args.cutoff} reached the model: {leaks}")
    return model


def parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--graph", required=True, type=Path)
    ap.add_argument("--display-hints", type=Path, help="display-hints.json from the editorial layer")
    ap.add_argument("--ledger", type=Path, help="coverage-ledger.json with per-chapter quality")
    ap.add_argument("--vocabulary", type=Path, help="book-specific display vocabulary")
    ap.add_argument("--protagonist-id", action="append")
    ap.add_argument("--cutoff", type=int, help="close the model at this chapter (share builds)")
    ap.add_argument("--output", type=Path)
    return ap


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    model = build(args)
    text = json.dumps(model, ensure_ascii=False, separators=(",", ":"))
    if args.output:
        from io_utils import atomic_write_text
        atomic_write_text(args.output, text)
    else:
        sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
