"""Shared record, chapter and text helpers.

Before this module the same five helpers existed in up to six private copies
(`_records`, `recs`, `records`, `chapter_of`, `_chapter`, `load_chapters`,
`norm`, `decode_source`) and had begun to drift — two Chinese-numeral tables no
longer agreed on which characters they accepted. Every script imports these
instead of defining its own.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Iterable, Mapping

ENCODINGS = ("utf-8-sig", "utf-8", "gb18030", "big5")

# Chinese numerals as they appear in chapter headings and level labels. The
# union of the two tables that used to live in prepare_novel.py and rollup_levels.py.
CN_DIGITS: dict[str, int] = {
    "零": 0, "〇": 0, "○": 0, "一": 1, "二": 2, "两": 2, "兩": 2, "三": 3, "四": 4,
    "五": 5, "六": 6, "七": 7, "八": 8, "九": 9,
}
CN_UNITS: dict[str, int] = {"十": 10, "拾": 10, "百": 100, "佰": 100, "千": 1000, "仟": 1000, "万": 10000, "萬": 10000}

# Reader-facing prose fields: every field whose text is printed in the dashboard or
# the AI story bible, and therefore subject to prose cleaning and as-of audits.
READER_PROSE_FIELDS: tuple[str, ...] = (
    "description", "reason", "observation", "interpretation", "summary", "resolution",
    "title", "label", "note", "notes", "detail", "conclusion", "statement",
)


def records(value: object) -> list[dict[str, Any]]:
    """Mapping records from an array field; anything else yields an empty list."""
    return [row for row in value if isinstance(row, dict)] if isinstance(value, list) else []


def chapter_value(value: object) -> int | None:
    """An integer chapter number, rejecting booleans and malformed values."""
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def chapter_of(record: Mapping[str, Any], *fields: str) -> int | None:
    """The first integer chapter among `fields`, in order."""
    for field in fields:
        value = chapter_value(record.get(field))
        if value is not None:
            return value
    return None


def first_chapter(record: Mapping[str, Any], fields: Iterable[str]) -> int | None:
    """The earliest integer chapter among `fields`."""
    present = [c for c in (chapter_value(record.get(f)) for f in fields) if c is not None]
    return min(present) if present else None


def interval_active(record: Mapping[str, Any], chapter: int, start_key: str = "valid_from",
                    end_key: str = "valid_to") -> bool:
    """Inclusive validity interval: active from `start` through `end`."""
    start = chapter_value(record.get(start_key))
    end = chapter_value(record.get(end_key))
    return (start is None or start <= chapter) and (end is None or chapter <= end)


def normalize_text(value: str | None) -> str:
    """Strip BOMs and all whitespace, for verbatim quote matching."""
    return re.sub(r"\s+", "", (value or "").replace("﻿", ""))


def decode_source(raw: bytes) -> tuple[str, str]:
    """Decode a source file, returning (text, encoding)."""
    for encoding in ENCODINGS:
        try:
            return raw.decode(encoding), encoding
        except UnicodeDecodeError:
            continue
    raise UnicodeError("Unable to decode source as UTF-8, GB18030, or Big5")


def chinese_number(text: str) -> int | None:
    """Parse a Chinese or Arabic numeral string (第一百二十三 → 123); None if not a number."""
    text = text.strip()
    if text.isdigit():
        return int(text)
    if not text or any(ch not in CN_DIGITS and ch not in CN_UNITS for ch in text):
        return None
    total, section, digit = 0, 0, None
    for ch in text:
        if ch in CN_DIGITS:
            digit = CN_DIGITS[ch]
            continue
        unit = CN_UNITS[ch]
        if unit == 10000:
            section = (section + (digit if digit is not None else (0 if section else 1))) * unit
            total += section
            section = 0
        else:
            section += (digit or 1) * unit
        digit = None
    return total + section + (digit or 0)


def read_chapter_index(path: Path, start: int | None = None, end: int | None = None,
                       *, with_text: bool = False, require_text: bool = False) -> list[dict[str, Any]]:
    """Rows of a prepared `chapters.jsonl`, sorted by chapter and optionally range-limited.

    `text_path` is resolved relative to the index when it is not absolute. With
    `with_text`, each row gains `text` (or keeps an inline `text`). With
    `require_text`, a row whose file is missing raises instead of being skipped.
    """
    rows: list[dict[str, Any]] = []
    missing: list[dict[str, Any]] = []
    for line_no, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not raw.strip():
            continue
        try:
            row = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ValueError(f"{path} line {line_no}: {exc}") from exc
        chapter = chapter_value(row.get("chapter"))
        if chapter is None:
            raise ValueError(f"{path} line {line_no}: chapter must be an integer")
        if (start is not None and chapter < start) or (end is not None and chapter > end):
            continue
        if with_text and not isinstance(row.get("text"), str):
            text_path = Path(row.get("text_path") or "")
            if not text_path.is_absolute():
                text_path = path.parent / text_path
            if text_path.is_file():
                row["text"] = text_path.read_text(encoding="utf-8")
            else:
                missing.append({"chapter": chapter, "text_path": str(text_path)})
                if require_text:
                    continue
        rows.append(row)
    if missing and require_text:
        raise FileNotFoundError("missing prepared chapter text: " + json.dumps(missing, ensure_ascii=False))
    rows.sort(key=lambda r: r["chapter"])
    return rows


def chapter_files(chapters_dir: Path) -> list[dict[str, Any]]:
    """`chapters/NNN.txt` files as index rows, for runs without a chapters.jsonl.

    The whole numeric stem is the chapter number: slicing the first three digits
    reads 1000.txt as chapter 100.
    """
    rows = []
    for text_path in chapters_dir.glob("*.txt"):
        if text_path.stem.isdigit():
            rows.append({"chapter": int(text_path.stem), "text_path": str(text_path)})
    return sorted(rows, key=lambda r: r["chapter"])
