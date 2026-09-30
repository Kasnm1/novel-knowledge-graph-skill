"""Where the audit stands: unit states, handoffs and the token ledger.

`audit-state.json` sits next to `plan.json` and replaces the hand-written
`_progress.json`. Each unit moves pending → extracting → verifying → done (or
blocked), and records what it cost: gate runs, verifier rounds, tokens. A unit is
ready when it is pending and the unit it depends on is done, so lanes advance in
parallel while units inside a lane stay in order. A new session resumes from this
file alone.
"""

from __future__ import annotations

import json
import statistics
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

STATUSES = ("pending", "extracting", "verifying", "done", "blocked")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def init_state(plan: Mapping[str, Any], existing: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Unit rows for every planned unit, keeping progress already recorded."""
    old = dict((existing or {}).get("units") or {})
    units = {}
    for unit in plan["units"]:
        row = dict(old.get(unit["unit"]) or {})
        row.setdefault("status", "pending")
        row.update({"lane": unit["lane"], "chapters": unit["chapters"], "depends_on": unit["depends_on"]})
        units[unit["unit"]] = row
    return {"schema": "audit-state/v1", "units": units, "updated_at": _now()}


def ready_units(state: Mapping[str, Any], lane: str | None = None) -> list[str]:
    units = state["units"]
    ready = [
        uid for uid, row in units.items()
        if row["status"] == "pending" and (lane is None or row["lane"] == lane)
        and (row["depends_on"] is None or units.get(row["depends_on"], {}).get("status") == "done")
    ]
    return sorted(ready)


def update_unit(state: dict[str, Any], unit_id: str, **fields: Any) -> dict[str, Any]:
    row = state["units"][unit_id]
    status = fields.get("status")
    if status is not None and status not in STATUSES:
        raise ValueError(f"status must be one of {STATUSES}")
    for key in ("gate_runs", "verify_rounds", "tokens_extract", "tokens_verify"):
        if fields.get(key) is not None:
            row[key] = int(row.get(key) or 0) + int(fields.pop(key))
    row.update({k: v for k, v in fields.items() if v is not None})
    row["updated_at"] = _now()
    state["updated_at"] = row["updated_at"]
    return row


def summary(state: Mapping[str, Any]) -> dict[str, Any]:
    units = state["units"]
    by_status = {s: sum(1 for r in units.values() if r["status"] == s) for s in STATUSES}
    lanes: dict[str, dict[str, int]] = {}
    for row in units.values():
        lane = lanes.setdefault(row["lane"], {s: 0 for s in STATUSES})
        lane[row["status"]] += 1
    done = [r for r in units.values() if r["status"] == "done"]
    done_chapters = sum(len(r["chapters"]) for r in done)
    all_chapters = sum(len(r["chapters"]) for r in units.values())
    per_chapter = [(int(r.get("tokens_extract") or 0) + int(r.get("tokens_verify") or 0)) / len(r["chapters"])
                   for r in done if r.get("tokens_extract") or r.get("tokens_verify")]
    tokens_spent = sum(int(r.get("tokens_extract") or 0) + int(r.get("tokens_verify") or 0) for r in units.values())
    mean = statistics.mean(per_chapter) if per_chapter else None
    return {
        "units": by_status, "lanes": lanes,
        "chapters": {"done": done_chapters, "total": all_chapters},
        "tokens": {"spent": tokens_spent, "per_chapter_mean": round(mean) if mean else None,
                   "projected_remaining": round(mean * (all_chapters - done_chapters)) if mean else None},
        "gate_runs_mean": round(statistics.mean([r.get("gate_runs") or 0 for r in done]), 2) if done else None,
        "ready": ready_units(state),
    }


def load_state(path: Path) -> dict[str, Any] | None:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


def save_state(path: Path, state: Mapping[str, Any]) -> None:
    from io_utils import atomic_write_json
    atomic_write_json(path, state)
