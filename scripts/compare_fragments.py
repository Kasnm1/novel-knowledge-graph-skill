#!/usr/bin/env python3
"""Align two independent extractions of the same chapters and measure agreement.

Used for blind re-audits (a second worker audits a sample from scratch) and for
gold chapters (one side is the human-checked answer). Records are matched on
structure, not wording:

- events: same chapter and participant sets overlapping by at least half;
- state changes: same chapter, entity and facet (and axis for levels);
- relations: same endpoints (either direction for symmetric types) and group;
- traits: same entity and facet;
- intimate acts: same chapter and overlapping participants;
- commitments: same created chapter and overlapping promisors;
- foreshadowing: same planted chapter and overlapping related entities.

For each kind the report gives matched / only-A / only-B counts and an agreement
score (2·matched / (A + B)). When B is a gold answer, matched / B is A's recall
and matched / A its precision for that kind. Read-only.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Callable, Iterable

from nkg.core.records import records
from relation_types import SYMMETRIC_RELATION_TYPES, canonical_relation_type, relation_group


def _people(record: dict, *fields: str) -> set[str]:
    return {p for f in fields for p in (record.get(f) or []) if isinstance(p, str)}


def _overlap(a: set, b: set) -> bool:
    return bool(a and b) and len(a & b) * 2 >= min(len(a), len(b))


MATCHERS: dict[str, tuple[Callable[[dict], Any], Callable[[dict, dict], bool] | None]] = {
    "events": (lambda r: r.get("chapter"),
               lambda a, b: _overlap(_people(a, "participant_ids"), _people(b, "participant_ids"))),
    "state_changes": (lambda r: (r.get("chapter"), r.get("entity_id"), r.get("facet"),
                                 r.get("target_id") if r.get("facet") == "level" else None), None),
    "relations": (lambda r: (tuple(sorted((r.get("source_id"), r.get("target_id"))))
                             if canonical_relation_type(r.get("relation_type")) in SYMMETRIC_RELATION_TYPES
                             else (r.get("source_id"), r.get("target_id")),
                             relation_group(r.get("relation_type"))), None),
    "character_traits": (lambda r: (r.get("entity_id"), r.get("facet")), None),
    "intimate_acts": (lambda r: r.get("chapter"),
                      lambda a, b: _overlap(_people(a, "initiator_ids", "recipient_ids", "observer_ids"),
                                            _people(b, "initiator_ids", "recipient_ids", "observer_ids"))),
    "commitments": (lambda r: r.get("created_chapter"),
                    lambda a, b: _overlap(_people(a, "promisor_ids"), _people(b, "promisor_ids"))),
    "foreshadowing": (lambda r: r.get("planted_chapter"),
                      lambda a, b: _overlap(_people(a, "related_entity_ids"), _people(b, "related_entity_ids"))),
}


def _within(rows: Iterable[dict], chapters: set[int] | None, kind: str) -> list[dict]:
    field = {"relations": "valid_from", "commitments": "created_chapter", "foreshadowing": "planted_chapter",
             "character_traits": "chapter"}.get(kind, "chapter")
    return [r for r in rows if chapters is None or r.get(field) in chapters]


def match_kind(kind: str, a_rows: list[dict], b_rows: list[dict]) -> dict[str, Any]:
    key, pair = MATCHERS[kind]
    unmatched_b = list(b_rows)
    matched, only_a = [], []
    for a in a_rows:
        hit = next((b for b in unmatched_b if key(a) == key(b) and (pair is None or pair(a, b))), None)
        if hit is None:
            only_a.append(a.get("id"))
        else:
            unmatched_b.remove(hit)
            matched.append((a.get("id"), hit.get("id")))
    total = len(a_rows) + len(b_rows)
    return {"a": len(a_rows), "b": len(b_rows), "matched": len(matched),
            "agreement": round(2 * len(matched) / total, 3) if total else None,
            "only_a": only_a, "only_b": [b.get("id") for b in unmatched_b]}


def compare(a: dict, b: dict, chapters: set[int] | None = None) -> dict[str, Any]:
    kinds = {kind: match_kind(kind, _within(records(a.get(kind)), chapters, kind),
                              _within(records(b.get(kind)), chapters, kind)) for kind in MATCHERS}
    matched = sum(k["matched"] for k in kinds.values())
    total = sum(k["a"] + k["b"] for k in kinds.values())
    return {"kinds": kinds, "overall_agreement": round(2 * matched / total, 3) if total else None}


def gold_gate(report: dict[str, Any], *, min_recall: float, previous: dict[str, Any] | None = None,
              tolerance: float = 0.02) -> list[str]:
    """Failures when B is the gold answer: a kind below `min_recall`, or recall worse than `previous`."""
    failures = []
    for kind, row in report["kinds"].items():
        if not row["b"]:
            continue
        recall = row["matched"] / row["b"]
        row["recall_vs_gold"] = round(recall, 3)
        row["precision_vs_gold"] = round(row["matched"] / row["a"], 3) if row["a"] else None
        if recall < min_recall:
            failures.append(f"{kind}: recall {recall:.2f} < {min_recall:.2f}")
        before = ((previous or {}).get("kinds", {}).get(kind) or {}).get("recall_vs_gold")
        if before is not None and recall < before - tolerance:
            failures.append(f"{kind}: recall dropped {before:.2f} → {recall:.2f}")
    return failures


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--a", required=True, type=Path)
    ap.add_argument("--b", required=True, type=Path, help="the other extraction, or the gold answer")
    ap.add_argument("--chapters", help="limit to START-END")
    ap.add_argument("--output", type=Path)
    ap.add_argument("--gold", action="store_true", help="B is the gold answer: report recall/precision and gate")
    ap.add_argument("--min-recall", type=float, default=0.8)
    ap.add_argument("--previous", type=Path, help="an earlier gold report; recall may not drop below it")
    args = ap.parse_args(argv)
    chapters = None
    if args.chapters:
        start, end = (int(x) for x in args.chapters.split("-"))
        chapters = set(range(start, end + 1))
    report = compare(json.loads(args.a.read_text(encoding="utf-8")), json.loads(args.b.read_text(encoding="utf-8")),
                     chapters)
    failures: list[str] = []
    if args.gold:
        previous = json.loads(args.previous.read_text(encoding="utf-8")) if args.previous else None
        failures = gold_gate(report, min_recall=args.min_recall, previous=previous)
        report["gold_failures"] = failures
    text = json.dumps(report, ensure_ascii=False, indent=2)
    if args.output:
        from io_utils import atomic_write_text
        atomic_write_text(args.output, text + "\n")
    print(json.dumps({k: {x: v[x] for x in ("a", "b", "matched", "agreement")} for k, v in report["kinds"].items()},
                     ensure_ascii=False, indent=1))
    print("overall agreement:", report["overall_agreement"])
    for failure in failures:
        print("GOLD FAIL:", failure)
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
