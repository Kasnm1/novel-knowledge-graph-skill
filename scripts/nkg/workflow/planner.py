"""Plan the audit: lanes that run in parallel, units that run in order inside a lane.

Ten-chapter slices handed to parallel workers were the root of stale state: the
worker on chapters 301-310 could not know how chapter 300 ended, so `before`
values were guessed, relations were never closed and present characters were
never re-checked. The plan therefore has two levels:

- a **lane** is a contiguous stretch (a story arc when the survey provides one,
  otherwise a fixed window). Lanes are independent and run in parallel, each
  starting from the checkpoint at the chapter before it;
- a **unit** is 3-5 chapters inside a lane, sized by characters weighted by
  plot density, so a battle-heavy stretch gets smaller units than a quiet one.
  Units in a lane run strictly in order; each hands its state capsule to the next.

Every unit names read-only context (the tail of the chapter before, the head of
the chapter after) so a scene crossing a chapter boundary is read whole, but
facts are recorded only inside the unit's own chapters.
"""

from __future__ import annotations

import re
import statistics
from typing import Any, Iterable, Mapping

DENSITY_MARKERS = re.compile(
    r"死|杀|伤|血|突破|境界|晋级|得到|获得|夺|赠|吻|抱|表白|发誓|答应|约定|秘密|真相|原来|钱|万|亿|交易"
)


def chapter_density(text: str) -> float:
    """Plot-marker hits per thousand characters: a cheap, deterministic density proxy."""
    return len(DENSITY_MARKERS.findall(text)) * 1000 / max(len(text), 1)


def density_weights(values: Mapping[int, float]) -> dict[int, float]:
    """Normalise densities around the median into weights clipped to [0.7, 1.6]."""
    if not values:
        return {}
    median = statistics.median(values.values()) or 1.0
    return {ch: max(0.7, min(1.6, (v / median) ** 0.5)) for ch, v in values.items()}


def _lane_bounds(chapters: list[int], arcs: Iterable[Mapping[str, Any]] | None, lane_chapters: int) -> list[tuple[int, int, str | None]]:
    first, last = chapters[0], chapters[-1]
    tops = sorted(
        (a for a in (arcs or []) if not a.get("parent_arc_id") and isinstance(a.get("chapter_start"), int)),
        key=lambda a: a["chapter_start"],
    )
    bounds: list[tuple[int, int, str | None]] = []
    cursor = first
    for arc in tops:
        start = max(arc["chapter_start"], cursor)
        end = arc.get("chapter_end") if isinstance(arc.get("chapter_end"), int) else last
        end = min(end, last)
        if end < start:
            continue
        if start > cursor:
            bounds.append((cursor, start - 1, None))
        bounds.append((start, end, arc.get("id")))
        cursor = end + 1
    while cursor <= last:
        end = min(last, cursor + lane_chapters - 1)
        bounds.append((cursor, end, None))
        cursor = end + 1
    return bounds


def plan_audit(chapter_rows: Iterable[Mapping[str, Any]], *, arcs: Iterable[Mapping[str, Any]] | None = None,
               lane_chapters: int = 100, target_chars: int = 10_000, max_chapters: int = 5,
               densities: Mapping[int, float] | None = None, context_chars: int = 600) -> dict[str, Any]:
    rows = sorted((dict(r) for r in chapter_rows), key=lambda r: r["chapter"])
    if not rows:
        raise ValueError("no chapters to plan")
    size = {r["chapter"]: int(r.get("char_count") or len(str(r.get("text") or ""))) for r in rows}
    if densities is None and all("text" in r for r in rows):
        densities = {r["chapter"]: chapter_density(str(r["text"])) for r in rows}
    weight = density_weights(dict(densities or {}))
    notes = {r["chapter"] for r in rows if r.get("non_narrative")}
    order = [r["chapter"] for r in rows]

    lanes, units_out = [], []
    for lane_no, (start, end, arc_id) in enumerate(_lane_bounds(order, arcs, lane_chapters), 1):
        lane_chapters_list = [c for c in order if start <= c <= end]
        if not lane_chapters_list:
            continue
        lane_id = f"L{lane_no:02d}"
        units: list[list[int]] = [[]]
        load = 0.0
        for chapter in lane_chapters_list:
            cost = size[chapter] * weight.get(chapter, 1.0)
            if units[-1] and (load + cost > target_chars or len(units[-1]) >= max_chapters):
                units.append([])
                load = 0.0
            units[-1].append(chapter)
            load += cost
        previous = None
        unit_ids = []
        for n, chs in enumerate(units, 1):
            unit_id = f"{lane_id}-U{n:02d}"
            idx_first, idx_last = order.index(chs[0]), order.index(chs[-1])
            units_out.append({
                "unit": unit_id, "lane": lane_id, "chapters": chs,
                "chapter_start": chs[0], "chapter_end": chs[-1],
                "char_count": sum(size[c] for c in chs),
                "weighted_chars": round(sum(size[c] * weight.get(c, 1.0) for c in chs)),
                "non_narrative_chapters": [c for c in chs if c in notes],
                # one chapter larger than the budget stays whole; the worker splits it by scene
                "oversize_single_chapter": len(chs) == 1 and size[chs[0]] * weight.get(chs[0], 1.0) > target_chars,
                "depends_on": previous,
                "read_only_context": {
                    "previous_chapter_tail": {"chapter": order[idx_first - 1], "chars": context_chars} if idx_first > 0 else None,
                    "next_chapter_head": {"chapter": order[idx_last + 1], "chars": context_chars} if idx_last + 1 < len(order) else None,
                },
            })
            previous = unit_id
            unit_ids.append(unit_id)
        lanes.append({"lane": lane_id, "arc_id": arc_id, "chapter_start": lane_chapters_list[0],
                      "chapter_end": lane_chapters_list[-1], "checkpoint_chapter": lane_chapters_list[0] - 1,
                      "units": unit_ids})

    covered = [c for u in units_out for c in u["chapters"]]
    if covered != order:
        raise AssertionError("plan must cover every chapter exactly once, in order")
    sizes = [len(u["chapters"]) for u in units_out]
    return {
        "schema": "audit-plan/v1",
        "parameters": {"lane_chapters": lane_chapters, "target_chars": target_chars,
                       "max_chapters": max_chapters, "context_chars": context_chars, "arc_lanes": bool(arcs)},
        "lanes": lanes,
        "units": units_out,
        "summary": {"chapters": len(order), "lanes": len(lanes), "units": len(units_out),
                    "chapters_per_unit": {"min": min(sizes), "max": max(sizes),
                                          "mean": round(statistics.mean(sizes), 2)}},
    }


def split_balanced(sizes: list[int], count: int) -> list[int]:
    """Cut `sizes` into `count` contiguous groups minimising the largest group (end indices)."""
    n = len(sizes)
    if count > n:
        raise ValueError(f"cannot make {count} contiguous groups from {n} chapters")
    prefix = [0]
    for s in sizes:
        prefix.append(prefix[-1] + s)
    best: list[list[tuple[int, list[int]] | None]] = [[None] * (count + 1) for _ in range(n + 1)]
    for i in range(n):
        best[i][1] = (prefix[n] - prefix[i], [n])
    for groups in range(2, count + 1):
        for i in range(n - groups + 1):
            winner = None
            for cut in range(i + 1, n - groups + 2):
                tail = best[cut][groups - 1]
                if tail is None:
                    continue
                candidate = max(prefix[cut] - prefix[i], tail[0])
                if winner is None or candidate < winner[0]:
                    winner = (candidate, [cut, *tail[1]])
            best[i][groups] = winner
    result = best[0][count]
    if result is None:
        raise ValueError("no contiguous split found")
    return result[1]
