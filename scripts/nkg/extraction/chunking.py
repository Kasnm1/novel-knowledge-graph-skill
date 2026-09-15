from __future__ import annotations

from typing import Any, Iterable, Mapping


def plan_dynamic_chunks(
    chapters: Iterable[Mapping[str, Any]],
    *,
    target_chars: int = 36_000,
    max_chapters: int = 20,
    overlap_chars: int = 800,
) -> list[dict[str, Any]]:
    """Group whole chapters by source budget without cutting semantic units.

    A chapter larger than the target remains intact and is marked oversize; the
    caller should use a scene-aware splitter if available rather than slicing it
    blindly. Boundary overlap is context-only and must never emit duplicate facts.
    """
    if target_chars <= 0 or max_chapters <= 0 or overlap_chars < 0:
        raise ValueError("target_chars/max_chapters must be positive and overlap_chars >= 0")
    rows = [dict(row) for row in chapters if isinstance(row, Mapping)]
    rows.sort(key=lambda row: int(row.get("chapter") or 0))
    chunks: list[dict[str, Any]] = []
    current: list[dict[str, Any]] = []
    current_chars = 0

    def flush() -> None:
        nonlocal current, current_chars
        if not current:
            return
        text = "\n".join(str(row.get("text") or "") for row in current)
        previous_tail = ""
        if chunks and overlap_chars:
            previous_tail = str(chunks[-1].get("source_text") or "")[-overlap_chars:]
        chunks.append({
            "chunk_id": f"ch{current[0]['chapter']}-{current[-1]['chapter']}",
            "chapter_start": current[0]["chapter"],
            "chapter_end": current[-1]["chapter"],
            "chapters": [row["chapter"] for row in current],
            "source_text": text,
            "source_chars": len(text),
            "context_only_overlap": previous_tail,
            "overlap_chars": len(previous_tail),
            "oversize_single_chapter": len(current) == 1 and len(text) > target_chars,
        })
        current, current_chars = [], 0

    for row in rows:
        chapter = row.get("chapter")
        if not isinstance(chapter, int):
            raise ValueError("every chapter row must have integer chapter")
        size = len(str(row.get("text") or ""))
        separator = 1 if current else 0
        if current and (len(current) >= max_chapters or current_chars + separator + size > target_chars):
            flush()
        current.append(row)
        current_chars += separator + size
        if size > target_chars:
            flush()
    flush()
    for index, chunk in enumerate(chunks, 1):
        chunk["index"] = index
        chunk.pop("source_text", None)
    return chunks
