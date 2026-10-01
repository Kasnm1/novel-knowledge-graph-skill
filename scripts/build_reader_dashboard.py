#!/usr/bin/env python3
"""Build the reader dashboard: one self-contained `dashboard.html`.

The page itself is the prebuilt single-file app in `assets/reader-app.html`
(source in `web/`, rebuilt with `npm run build`; Skill users need no Node). This
script builds the reader model (`build_reader_model.py`) and injects it into the
page's `<script id="nkg-model" type="application/json">` slot. With `--cutoff N`
the model is closed at chapter N and must pass the late-name leak gate.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import build_reader_model

APP = Path(__file__).resolve().parent.parent / "assets" / "reader-app.html"
SLOT = "__NKG_MODEL__"


def inject(app_html: str, model: dict) -> str:
    if app_html.count(SLOT) != 1:
        raise SystemExit(f"{APP.name}: expected exactly one {SLOT} slot; rebuild web/ with npm run build")
    # `</` cannot appear inside a script element; JSON stays valid with the slash escaped.
    payload = json.dumps(model, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    title = model.get("meta", {}).get("title")
    html = app_html.replace(SLOT, payload)
    if isinstance(title, str) and title:
        html = html.replace("<title>小说知识图谱</title>", f"<title>{title} · 小说知识图谱</title>", 1)
    return html


def main(argv: list[str] | None = None) -> int:
    ap = build_reader_model.parser()
    ap.description = __doc__
    ap.add_argument("--app", type=Path, default=APP, help="prebuilt single-file app")
    ap.add_argument("--model-output", type=Path, help="also write reader-model.json here")
    args = ap.parse_args(argv)
    if not args.output:
        ap.error("--output is required (the dashboard.html path)")
    model = build_reader_model.build(args)
    from io_utils import atomic_write_text
    atomic_write_text(args.output, inject(args.app.read_text(encoding="utf-8"), model))
    if args.model_output:
        atomic_write_text(args.model_output, json.dumps(model, ensure_ascii=False, separators=(",", ":")))
    print(f"wrote {args.output} ({args.output.stat().st_size // 1024} KB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
