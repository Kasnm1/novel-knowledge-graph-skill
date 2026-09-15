from __future__ import annotations

import hashlib
import json
from typing import Any, Mapping


def graph_fingerprint(graph: Mapping[str, Any]) -> str:
    """Stable content fingerprint excluding volatile generation timestamps."""
    payload = dict(graph)
    metadata = dict(payload.get("metadata") or {}) if isinstance(payload.get("metadata"), dict) else {}
    for key in ("generated_at", "finished_at", "updated_at"):
        metadata.pop(key, None)
    payload["metadata"] = metadata
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def checkpoint_chapters(start: int, end: int, interval: int = 50) -> list[int]:
    if interval <= 0:
        raise ValueError("interval must be > 0")
    lo, hi = sorted((int(start), int(end)))
    values = [lo]
    cursor = ((lo // interval) + 1) * interval
    while cursor < hi:
        values.append(cursor)
        cursor += interval
    if hi not in values:
        values.append(hi)
    return sorted(set(values))


def nearest_checkpoint(chapter: int, available: list[int]) -> int | None:
    eligible = [value for value in available if value <= chapter]
    return max(eligible) if eligible else None
