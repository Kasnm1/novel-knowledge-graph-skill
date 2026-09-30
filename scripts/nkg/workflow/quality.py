"""Per-chapter audit quality, recorded in coverage-ledger.json.

The score is an audit indicator for deciding which chapters need another pass,
not a probability that the chapter is right. It combines three signals:

- the audit card: present and every receipt answered (40 points);
- recall candidates the verifier has not cleared (30 points, minus 6 per open
  or missed candidate);
- the verifier's own verdict: missed and wrong records it reported (30 points,
  minus 10 per issue).

A chapter never verified keeps its card and recall points but scores the
verifier part as 0, so "not checked" can never read as "checked and clean".
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

from chapter_audit import AUDIT_ITEMS
from nkg.core.records import records


def card_complete(graph: Mapping[str, Any], chapter: int) -> bool:
    card = next((c for c in records(graph.get("chapter_summaries")) if c.get("chapter") == chapter), None)
    audit = (card or {}).get("audit")
    return isinstance(audit, dict) and all(
        isinstance(audit.get(k), dict) and audit[k].get("status") in {"recorded", "none"} for k in AUDIT_ITEMS
    )


def chapter_score(*, card: bool, recall_open: int, recall_missed: int,
                  verifier: Mapping[str, Any] | None) -> dict[str, Any]:
    score = 40 if card else 0
    score += max(0, 30 - 6 * (recall_open + recall_missed))
    if verifier:
        issues = int(verifier.get("missed") or 0) + int(verifier.get("wrong") or 0)
        score += max(0, 30 - 10 * issues)
    grade = "good" if score >= 85 else "review" if score >= 60 else "reaudit"
    return {"score": score, "grade": grade, "card_complete": card, "recall_open": recall_open,
            "recall_missed": recall_missed, "verified": bool(verifier),
            "verifier": dict(verifier) if verifier else None}


def update_ledger(ledger_path: Path, chapter: int, quality: Mapping[str, Any]) -> dict[str, Any]:
    """Write one chapter's quality into coverage-ledger.json, keeping other fields."""
    from io_utils import atomic_write_json
    ledger = json.loads(ledger_path.read_text(encoding="utf-8")) if ledger_path.exists() else {"chapters": []}
    rows = ledger.setdefault("chapters", [])
    row = next((r for r in rows if r.get("chapter") == chapter), None)
    if row is None:
        row = {"chapter": chapter, "status": "analyzed"}
        rows.append(row)
    row["quality"] = dict(quality)
    rows.sort(key=lambda r: r.get("chapter") or 0)
    atomic_write_json(ledger_path, ledger)
    return row
