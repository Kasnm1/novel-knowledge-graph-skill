#!/usr/bin/env python3
"""Plan source-budgeted whole-chapter extraction chunks with context-only overlap."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from io_utils import atomic_write_json
from nkg.extraction.chunking import plan_dynamic_chunks


def load_chapters(index: Path, start: int | None, end: int | None) -> list[dict]:
    rows: list[dict] = []
    for line_no, raw in enumerate(index.read_text(encoding="utf-8").splitlines(), 1):
        if not raw.strip():
            continue
        row = json.loads(raw)
        chapter = row.get("chapter")
        if not isinstance(chapter, int):
            raise ValueError(f"line {line_no}: chapter must be integer")
        if start is not None and chapter < start:
            continue
        if end is not None and chapter > end:
            continue
        if isinstance(row.get("text"), str):
            text = row["text"]
        else:
            path = Path(str(row.get("text_path") or ""))
            if not path.is_file():
                raise FileNotFoundError(f"chapter {chapter}: missing {path}")
            text = path.read_text(encoding="utf-8")
        rows.append({"chapter": chapter, "text": text})
    return rows


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--chapters-jsonl", required=True, type=Path)
    p.add_argument("--output", required=True, type=Path)
    p.add_argument("--chapter-start", type=int)
    p.add_argument("--chapter-end", type=int)
    p.add_argument("--target-chars", type=int, default=36000)
    p.add_argument("--max-chapters", type=int, default=20)
    p.add_argument("--overlap-chars", type=int, default=800)
    args = p.parse_args()
    chapters = load_chapters(args.chapters_jsonl, args.chapter_start, args.chapter_end)
    chunks = plan_dynamic_chunks(chapters, target_chars=args.target_chars, max_chapters=args.max_chapters, overlap_chars=args.overlap_chars)
    result = {
        "schema_version": 1,
        "source_chapter_count": len(chapters),
        "target_chars": args.target_chars,
        "max_chapters": args.max_chapters,
        "overlap_chars": args.overlap_chars,
        "context_overlap_is_non_emitting": True,
        "chunks": chunks,
    }
    atomic_write_json(args.output, result)
    print(json.dumps({"output": str(args.output), "chapters": len(chapters), "chunks": len(chunks), "oversize": sum(bool(c["oversize_single_chapter"]) for c in chunks)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
