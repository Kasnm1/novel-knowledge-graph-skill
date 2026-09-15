#!/usr/bin/env python3
"""Plan contiguous chapter ranges for parallel fragment extraction.

Extraction parallelizes along chapter ranges, but the ranges must be
*contiguous* — a pass that reads chapters 51, 53, 55 cannot reason about
continuity, and a pass that owns chapters 51-60 while another owns 61-70 can be
given a clean boundary. Chapter length in a web novel varies several-fold, so
partition by character count, not by chapter count.

Non-narrative chapters (author notes, vote requests) still have to appear in
`metadata.analyzed_chapters` — coverage is validated against it — but must yield
no records. This script flags them so every pass is told which chapters in its
range are notes, instead of each pass deciding for itself.

Writes a plan JSON and prints a table. Feed the plan to the extraction passes.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Author notes in these books are a few hundred characters; a story chapter is
# several thousand. The threshold only needs to separate those two populations.
NOTE_CHAR_LIMIT = 1200
NOTE_KEYWORDS = ("求票", "推荐票", "月票", "加更", "感言", "订阅", "打赏", "书友", "更新", "上架")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--chapters-jsonl", required=True, type=Path)
    parser.add_argument("--start", required=True, type=int, help="First chapter to plan, inclusive")
    parser.add_argument("--end", required=True, type=int, help="Last chapter to plan, inclusive")
    parser.add_argument("--count", required=True, type=int, help="Number of fragments to produce")
    parser.add_argument("--first-fragment", type=int, default=1, help="Fragment number for the first range")
    parser.add_argument("--output", required=True, type=Path, help="Plan JSON path")
    return parser.parse_args()


def load_chapters(path: Path, start: int, end: int) -> list[dict]:
    rows = []
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            record = json.loads(line)
            if start <= record["chapter"] <= end:
                rows.append(record)
    rows.sort(key=lambda r: r["chapter"])
    return rows


def is_note(record: dict) -> bool:
    if record["char_count"] >= NOTE_CHAR_LIMIT:
        return False
    text = Path(record["text_path"]).read_text(encoding="utf-8") if record.get("text_path") else ""
    return any(keyword in text for keyword in NOTE_KEYWORDS)


def split_contiguous(sizes: list[int], count: int) -> list[int]:
    """Cut `sizes` into `count` contiguous groups minimising the largest group.

    Returns the end indices of each group. Dynamic programming over prefix sums;
    the chapter count here is small enough that O(n^2 * k) is instant.
    """
    n = len(sizes)
    if count > n:
        raise ValueError(f"cannot make {count} contiguous groups from {n} chapters")
    prefix = [0] * (n + 1)
    for index, size in enumerate(sizes):
        prefix[index + 1] = prefix[index] + size

    # best[i][k] = (largest group size, end indices) for sizes[i:] split into k groups
    best: list[list[tuple[int, list[int]] | None]] = [[None] * (count + 1) for _ in range(n + 1)]
    for index in range(n):
        best[index][1] = (prefix[n] - prefix[index], [n])
    for groups in range(2, count + 1):
        for index in range(n - groups + 1):
            winner: tuple[int, list[int]] | None = None
            for cut in range(index + 1, n - groups + 2):
                tail = best[cut][groups - 1]
                if tail is None:
                    continue
                candidate = max(prefix[cut] - prefix[index], tail[0])
                if winner is None or candidate < winner[0]:
                    winner = (candidate, [cut, *tail[1]])
            best[index][groups] = winner
    result = best[0][count]
    if result is None:
        raise ValueError("no contiguous split found")
    return result[1]


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    args = parse_args()
    rows = load_chapters(args.chapters_jsonl, args.start, args.end)
    if not rows:
        print("ERROR: no chapters in range", file=sys.stderr)
        return 2
    sizes = [r["char_count"] for r in rows]
    cuts = split_contiguous(sizes, args.count)

    plan = []
    previous = 0
    for offset, cut in enumerate(cuts):
        segment = rows[previous:cut]
        notes = [r["chapter"] for r in segment if is_note(r)]
        plan.append(
            {
                "fragment": f"fragment-{args.first_fragment + offset:02d}",
                "chapter_start": segment[0]["chapter"],
                "chapter_end": segment[-1]["chapter"],
                "chapters": [r["chapter"] for r in segment],
                "non_narrative_chapters": notes,
                "char_count": sum(r["char_count"] for r in segment),
            }
        )
        previous = cut

    for item in plan:
        print(
            "{fragment}  ch{start:03d}-{end:03d}  {count:2d}章 {chars:6d}字  非正文({notes_count}): {notes}".format(
                fragment=item["fragment"],
                start=item["chapter_start"],
                end=item["chapter_end"],
                count=len(item["chapters"]),
                chars=item["char_count"],
                notes_count=len(item["non_narrative_chapters"]),
                notes=item["non_narrative_chapters"],
            )
        )
    covered = sorted(c for item in plan for c in item["chapters"])
    assert covered == [r["chapter"] for r in rows], "partition must cover every chapter exactly once"
    largest = max(item["char_count"] for item in plan)
    print(f"共 {len(plan)} 片，最大片 {largest} 字，覆盖 {len(covered)} 章，无重叠无遗漏")

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"wrote {args.output.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
