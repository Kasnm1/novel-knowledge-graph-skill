#!/usr/bin/env python3
"""Consolidate romance routes that parallel extraction passes declared separately.

Ten passes each mint their own `romance_routes` entry for the same pair — the
我的美女老师 run had nine routes for 苏姬 alone — while the schema wants one route
per pair carrying dated milestones. Doing this with `--id-map` looks right and is
not: `merge_value` keeps the *last* fragment's scalar, so the final pass's
`status: ambiguous` overwrites an earlier pass's `confirmed_relationship` and its
`confirmed_chapter` becomes null. The merge is silent about it.

Instead this script:

  1. collects every route from the chapter fragments *and* from any canonical
     fragment already on disk (so a second run is a no-op rather than a wipe),
  2. merges each (protagonist, character) group into one canonical route, taking
     the earliest evidenced milestone, the most advanced status, and the consent
     wording of the earliest qualifying episode,
  3. empties `romance_routes` in the chapter fragments,
  4. writes the canonical routes to the output fragment, marked
     `metadata.supplementary: true` so `plan_reconciliation.py` does not read it
     as a pass that failed to extract.

A route restated with only `id` plus one field is resolved against whichever
fragment declares it in full; three such stubs would otherwise collapse into one
bogus ("", "") pair.

Usage:
    python consolidate_romance.py --run-dir runs/<book-range>
        [--letters A,B,C,D,E,F,G,H,I,J] [--output fragment-K.json]
"""

from __future__ import annotations

import argparse
import json
import sys
from copy import deepcopy
from pathlib import Path

STATUS_RANK = {
    "excluded_nonromantic": -1,
    "accidental_or_contextual": 0,
    "coerced_or_forced": 0,
    "ended": 1,
    "uncertain": 2,
    "provisional_intimate": 3,
    "one_sided": 3,
    "ambiguous": 3,
    "mutual_interest": 4,
    "betrothed": 5,
    "spouse": 6,
    "confirmed_relationship": 6,
}
CONFIDENCE_RANK = {"uncertain": 0, "inferred": 1, "explicit": 2}

MILESTONES = (
    ("first_meeting", "first_meeting_chapter", "first_meeting_evidence_ids"),
    ("ambiguity", "ambiguity_started_chapter", "ambiguity_evidence_ids"),
    ("confirmed", "confirmed_chapter", "confirmed_evidence_ids"),
    ("first_sex", "first_sex_chapter", "first_sex_evidence_ids"),
)


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def route_key_map(paths: list[Path]) -> dict[str, tuple[str, str]]:
    """id -> pair, from whichever declarations carry the full key."""
    keys: dict[str, tuple[str, str]] = {}
    for path in paths:
        if not path.exists():
            continue
        for route in load(path).get("romance_routes") or []:
            if route.get("id") and route.get("protagonist_id") and route.get("character_id"):
                keys[route["id"]] = (route["protagonist_id"], route["character_id"])
    return keys


def merge_group(group: list[dict], journal: list[dict] | None = None) -> dict:
    """Fold one pair's routes into a single canonical record."""
    group = sorted(group, key=lambda r: (r.get("first_meeting_chapter") or 999, r["id"]))
    # Already canonical: one full record for this pair. Return it untouched so a
    # second run is a no-op instead of rewriting its `notes` every time.
    if len(group) == 1 and group[0].get("protagonist_id") and group[0].get("character_id"):
        return deepcopy(group[0])
    base = group[0]
    merged: dict = {
        "id": f"rom_{base['character_id'].replace('char_', '')}",
        "protagonist_id": base["protagonist_id"],
        "character_id": base["character_id"],
    }

    for _, chapter_field, evidence_field in MILESTONES:
        dated = [r for r in group if isinstance(r.get(chapter_field), int)]
        if not dated:
            merged[chapter_field] = None
            merged[evidence_field] = []
            continue
        merged[chapter_field] = min(r[chapter_field] for r in dated)
        evidence: list[str] = []
        for route in group:
            for value in route.get(evidence_field) or []:
                if value not in evidence:
                    evidence.append(value)
        merged[evidence_field] = evidence

    # Status and consent wording follow the earliest qualifying episode; a later
    # fragment that only restates an earlier contact must not downgrade a
    # confirmation another fragment evidenced.
    qualifying = [r for r in group if isinstance(r.get("ambiguity_started_chapter"), int)]
    qualifying = sorted(qualifying, key=lambda r: r["ambiguity_started_chapter"]) or group
    if merged["confirmed_chapter"] is not None:
        merged["status"] = "confirmed_relationship"
    else:
        merged["status"] = max(
            group, key=lambda r: STATUS_RANK.get(r.get("status"), -1)
        ).get("status")

    merged["inclusion_basis"] = qualifying[0].get("inclusion_basis")
    contexts: list[str] = []
    for route in qualifying:
        context = route.get("consent_context")
        if context and context not in contexts:
            contexts.append(context)
    merged["consent_context"] = contexts[0] if contexts else "uncertain"
    merged["confidence"] = max(
        group, key=lambda r: CONFIDENCE_RANK.get(r.get("confidence"), -1)
    ).get("confidence")

    # `notes` is reader-facing prose: it is printed verbatim in the dashboard and in
    # the Markdown story bible. Only the passes' own content goes here — the
    # `[rom_A01 第7章]` markers, the "同意语境不同" ruling and the "本条由 N 条分片记录
    # 合并" banner are all bookkeeping about *how this record was assembled*, and they
    # belong in metadata where an operator can still read them. Writing them here put
    # 24 merge banners and 41 fragment tags in front of readers of one run alone.
    notes = []
    for route in group:
        text = (route.get("notes") or "").strip()
        if text:
            notes.append(text)
    merged["notes"] = " ".join(notes)

    if journal is not None:
        entry = {
            "id": merged["id"],
            "merged_from": [r["id"] for r in group],
            "consent_contexts_seen": contexts,
            "milestone_rule": "取最早有原文依据的章节",
        }
        if len(contexts) > 1:
            entry["consent_conflict"] = (
                "各分片判定的同意语境不同，取最早一节的判定："
                + "、".join(contexts)
            )
        journal.append(entry)
    return merged


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--run-dir", required=True, type=Path)
    parser.add_argument("--letters", default="A,B,C,D,E,F,G,H,I,J",
                        help="comma-separated fragment letters holding the chapter fragments")
    parser.add_argument("--output", default="fragment-K.json",
                        help="supplementary fragment that will hold the canonical routes")
    args = parser.parse_args()

    frag_dir = args.run_dir.resolve() / "fragments"
    letters = [part.strip() for part in args.letters.split(",") if part.strip()]
    chapter_fragments = [frag_dir / f"fragment-{letter}.json" for letter in letters]
    output = frag_dir / args.output
    inputs = chapter_fragments + [output]

    missing = [p for p in chapter_fragments if not p.exists()]
    if missing:
        for path in missing:
            print(f"ERROR 分片不存在：{path}", file=sys.stderr)
        return 2

    keys = route_key_map(inputs)
    groups: dict[tuple[str, str], list[dict]] = {}
    for path in inputs:
        if not path.exists():
            continue
        for route in load(path).get("romance_routes") or []:
            route_id = route.get("id")
            if not route_id:
                continue
            key = (route.get("protagonist_id") or "", route.get("character_id") or "")
            if not (key[0] and key[1]):
                key = keys.get(route_id, ("", ""))
                if not (key[0] and key[1]):
                    print(f"WARNING 跳过无法定配对的路线 {route_id}", file=sys.stderr)
                    continue
            groups.setdefault(key, []).append(route)

    journal: list[dict] = []
    canonical = [merge_group(group, journal) for group in groups.values()]
    canonical.sort(key=lambda r: (r.get("first_meeting_chapter") or 999, r["id"]))

    removed = 0
    for path in chapter_fragments:
        data = load(path)
        if data.get("romance_routes"):
            removed += len(data["romance_routes"])
            data["romance_routes"] = []
            path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    output.write_text(
        json.dumps(
            {
                "metadata": {
                    "title": load(chapter_fragments[0]).get("metadata", {}).get("title", ""),
                    "supplementary": True,
                    "notes": (
                        "感情线合并分片：由 consolidate_romance.py 从各章分片的重复记录整理而成，"
                        "不新增章节覆盖，也不携带自有证据（引文仍由各章分片声明）。"
                    ),
                    # 合并记账：哪条路线由哪些分片记录拼来、同意语境是否有分歧、里程碑怎么取。
                    # 放在这里而不是 romance_routes[].notes，因为 notes 会被原样印给读者。
                    "romance_consolidation": journal,
                },
                "entities": [], "events": [], "relations": [], "state_changes": [],
                "foreshadowing": [], "evidence": [], "review_issues": [],
                "romance_routes": canonical,
            },
            ensure_ascii=False, indent=2,
        ) + "\n",
        encoding="utf-8",
    )

    print(f"清理各分片中的临时 romance 记录 {removed} 条；规范路线 {len(canonical)} 条：")
    for route in canonical:
        print(
            f"  {route['id']:24s} status={route['status']:<22s} "
            f"初遇={route['first_meeting_chapter']} 暧昧={route['ambiguity_started_chapter']} "
            f"确认={route['confirmed_chapter']}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
