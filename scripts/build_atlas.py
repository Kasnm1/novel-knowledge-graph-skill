#!/usr/bin/env python3
"""Build the layered single-page atlas dashboard.

The graph is not a flat bag of records. It has three natural tiers, and the page
is organized the way the data actually nests:

  tier 1 — the whole book: chapter summaries, rhythm, coverage, rules, level axes
  tier 2 — the agents: every character / organization / creature, and *underneath*
           each one its traits, level track, relations, skills, possessions,
           commitments, foreshadowing and intimacy records
  tier 3 — the circulating things: items, skills and concepts, each with the
           custody / transfer / usage timeline that moves it between agents

So the page is one vertical stream ordered by that hierarchy rather than a row of
peer tabs. Scrolling is browsing; clicking drills into a side panel.

Everything reader-facing is Chinese: the display vocabulary is merged here, at
build time, and no ontology key is ever printed raw.
"""
from __future__ import annotations

import argparse
import html
import json
import math
import random
import shutil
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from build_dashboard import DEFAULT_VOCABULARY, merge_vocabulary
# `controlled_vocab.py` is the authority for these axes; it stores them as bare
# English sets because it is a validator. The Chinese labels come with them.
from controlled_vocab import CONCEPT_CATEGORIES, SKILL_CATEGORIES
from derive_novel_views import build_views
from io_utils import atomic_write_text

TIER_AGENT = ("character", "organization", "creature", "level_axis")
TIER_THING = ("item", "skill", "concept")

# Groups the page renders but DEFAULT_VOCABULARY does not yet carry Chinese labels
# for. `controlled_vocab.py` holds these as bare English sets (it is a validator, not
# a display table), so the labels live here rather than being invented inline in JS.
# A missing group would print `revenge_vow` / `holder` straight to the reader.
ATLAS_VOCABULARY: dict[str, dict[str, str]] = {
    "concept_categories": dict(CONCEPT_CATEGORIES),
    "skill_categories": dict(SKILL_CATEGORIES),
    "commitment_kinds": {
        "promise": "许诺", "oath": "誓约", "agreement": "约定",
        "wager": "赌约", "revenge_vow": "复仇之誓",
    },
    "item_roles": {
        "owner": "所有者", "holder": "持有者", "user": "使用者", "custodian": "保管者",
    },
    "nudity_states": {
        "true": "有裸露描写", "false": "无裸露描写",
        "fully": "全身裸露", "partial": "部分裸露", "underwear": "仅着内衣",
        "topless": "上身裸露", "bottomless": "下身裸露", "none": "无裸露",
    },
    # `DEFAULT_VOCABULARY` covers the family and core social ties but the extractor
    # emitted 22 more relation types this graph uses — 200+ edges that would print
    # their raw English. Same rule as below: a missing entry falls back to the raw key.
    "relations": {
        "benefactor_of": "恩主", "colleague_of": "同僚", "contains": "包含",
        "controls": "操控", "employee": "雇员", "employer": "雇主",
        "employs": "雇用", "father_of": "生父", "former_lover_of": "旧情人",
        "instance_of": "属于", "lover_of": "情人", "master_of": "主人",
        "mother_of": "生母", "owes_favor_to": "欠人情", "possesses": "持有",
        "savior_of": "救命恩人", "servant_of": "仆从", "serves": "效力",
        "stepmother_of": "继母", "subordinate_of": "下属", "supports": "支持",
        "uncle_of": "叔伯",
    },
    # `DEFAULT_VOCABULARY.event_types` covers the common cases but the extractor emitted
    # 25 further types this book actually uses — 270+ events that would have printed
    # their raw English type straight onto the page.
    "event_types": {
        "alliance": "结盟", "ambush": "伏击", "assassination": "刺杀",
        "cliffhanger": "悬念", "contest": "比试", "crisis": "危机",
        "death": "死亡", "disguise": "易容", "escape": "脱身",
        "gathering": "聚会", "negotiation": "交涉", "payoff": "回收",
        "perception": "察觉", "promise": "许诺", "pursuit": "追击",
        "recruitment": "招揽", "rescue": "援救", "resurrection": "复活",
        "revenge_vow": "立誓复仇", "ritual": "仪式", "romance": "情愫",
        "social": "社交", "strategy": "谋略", "temptation": "诱惑",
        "warning": "警告",
    },
    # `entity_tags` was the group nobody had, and the reason is instructive: the renderer
    # never read `e.tags` at all, so no leak was ever *visible*, so no one translated the
    # values. MEASURED on this graph, five pure-English tags sit on eleven subjects —
    # `protagonist` (秦朝), `antagonist` (罗如梦/耿鑫/夜无常), `minor` (铁牛/周江涛/天丹子),
    # `assassin` and a romanised `mokuui` (墨非烟/春九娘/罗如梦). Both leak scans in
    # `accept_atlas.py` walk right past them: `LEAK_KEYS` is a hand-written list that does
    # not contain "tags", and the snake_case regex requires an underscore, which none of
    # these five words has.
    #
    # Translating them here rather than only filtering them at the render site is the
    # point: a tag is *information* (「反派」 tells the reader something 「antagonist」 does
    # not), so the fix is to say it in the book's language, not to hide it.
    "entity_tags": {
        "protagonist": "主角", "antagonist": "反派", "minor": "配角",
        "assassin": "刺客", "mokuui": "墨门",
    },
}


def _layer_of(entity_type: str) -> str:
    if entity_type in TIER_AGENT:
        return "agent"
    if entity_type in TIER_THING:
        return "thing"
    return "world"


def build_layers(graph: dict[str, Any]) -> dict[str, Any]:
    """Pre-arrange the graph into the three render tiers.

    Doing this in Python keeps the client from re-walking 980 entities and 6168
    evidence rows on every chapter scrub, and makes the hierarchy explicit in one
    place instead of being re-derived by each panel.
    """
    entities = graph.get("entities") or []
    by_id = {e["id"]: e for e in entities if isinstance(e, dict) and e.get("id")}

    traits_by_entity: dict[str, list] = defaultdict(list)
    for row in graph.get("character_traits") or []:
        if isinstance(row, dict) and row.get("entity_id"):
            traits_by_entity[row["entity_id"]].append(row)
    for rows in traits_by_entity.values():
        rows.sort(key=lambda r: (r.get("chapter") or 0, str(r.get("id") or "")))

    changes_by_entity: dict[str, list] = defaultdict(list)
    changes_by_target: dict[str, list] = defaultdict(list)
    for row in graph.get("state_changes") or []:
        if not isinstance(row, dict):
            continue
        if row.get("entity_id"):
            changes_by_entity[row["entity_id"]].append(row)
        if row.get("target_id"):
            changes_by_target[row["target_id"]].append(row)
    for rows in changes_by_entity.values():
        rows.sort(key=lambda r: (r.get("chapter") or 0, str(r.get("id") or "")))

    relations_by_entity: dict[str, list] = defaultdict(list)
    for row in graph.get("relations") or []:
        if not isinstance(row, dict):
            continue
        for key in (row.get("source_id"), row.get("target_id")):
            if key:
                relations_by_entity[key].append(row)

    item_roles_by_item: dict[str, list] = defaultdict(list)
    for row in graph.get("item_roles") or []:
        if isinstance(row, dict) and row.get("item_id"):
            item_roles_by_item[row["item_id"]].append(row)
    for rows in item_roles_by_item.values():
        rows.sort(key=lambda r: (r.get("valid_from") or 0, str(r.get("id") or "")))

    return {
        "by_id": by_id,
        "traits_by_entity": {k: v for k, v in traits_by_entity.items()},
        "changes_by_entity": {k: v for k, v in changes_by_entity.items()},
        "changes_by_target": {k: v for k, v in changes_by_target.items()},
        "relations_by_entity": {k: v for k, v in relations_by_entity.items()},
        "item_roles_by_item": {k: v for k, v in item_roles_by_item.items()},
    }


def compute_zone_layout(graph: dict[str, Any], layers: dict[str, Any], protagonists: list[str]) -> dict[str, Any]:
    """Place every node on a fixed polar grid: one angular sector per entity type.

    A force layout over 980 nodes and 823 edges is what made the previous graph
    unreadable — unrelated clusters get pulled into each other and the labels overlap.
    A fixed layout fixes that, but two earlier attempts still collapsed, and the reasons
    are worth keeping:

    1. Coordinates were written into `data.x`/`data.y`. Cytoscape's `preset` layout reads
       `position` from the element, so every node sat at the origin.
    2. Bands were stacked radially, one type after another. Each type then only used the
       circumference of its own narrow ring, so the disc's area went to waste: the nine
       `level_axis` nodes were pushed out to r=0.9 while the middle of the disc held
       almost nothing. Compressing that back to fit shrank the pitch until neighbours
       were 0.016 apart — about 6px, which is the grey blob again.

    What works is giving each type a *sector* (a wedge from the centre to the rim) and
    letting it fill that wedge outward on its own. A wedge keeps the type visually
    grouped, gives it area proportional to its angular share, and lets a small type sit
    near the centre instead of being exiled to the rim. Sector width is proportional to
    the square root of headcount, because area grows with the square of radius: a type
    with 4x the nodes needs 2x the angle for the same depth.
    """
    entities = [e for e in (graph.get("entities") or []) if isinstance(e, dict)]
    hero = protagonists[0] if protagonists else None
    hero_anchored = bool(hero and hero in layers["by_id"])

    order = ["character", "organization", "creature", "location", "item", "skill", "concept", "level_axis"]
    counts = Counter(e.get("type") for e in entities)
    present = [t for t in order if counts.get(t)]

    # Spacing between neighbouring labels, in the unit disc. This is the number that
    # decides whether the graph reads or blobs, and it trades directly against how many
    # nodes fit.
    #
    # It cannot be a constant. The disc holds roughly pi/pitch^2 nodes, so demanding
    # 0.065 for 980 of them asks for more area than the circle has — the wedges then run
    # short and the overflow step squeezes neighbours down to a few pixels. Deriving the
    # pitch from the headcount keeps the layout honest: a smaller cast gets generous
    # spacing, a huge one gets what the geometry can actually provide, and no node ever
    # ends up on top of another because the ask outran the supply.
    USABLE_R = 0.97
    PITCH_MAX = 0.075   # ceiling: beyond this the disc is mostly empty air
    PITCH_MIN = 0.026   # floor: below this labels interleave and the map blobs anyway
    n_seats = sum(counts[t] for t in present) or 1
    PITCH = max(PITCH_MIN, min(PITCH_MAX, math.sqrt((math.pi * USABLE_R ** 2) / n_seats)))

    # Labels are wider than the dots they sit under — a two-character name is ~34px
    # against a 20px seat — so a layout that spaces *dots* by one pitch still overlaps
    # *names*. Measured on the built page: 63 named nodes produced 50 overlapping label
    # pairs, which is the reader's original complaint exactly.
    #
    # Two things follow, and they are deliberately separable:
    #
    #   1. The seat spacing keeps its own number. Widening it to the label width would
    #      ask for ~2.3x the area the disc has, and the layout would answer by squeezing
    #      the overflow into a blob — trading a legible overlap for an illegible one.
    #   2. The *label budget* is what actually has to fit. Only the nodes whose names can
    #      be placed without collision are named at rest; the rest keep their name one
    #      hover (or one zoom) away. That is a statement about how many names a disc can
    #      carry, not about how many subjects deserve naming.
    LABEL_W = 0.086     # ~40px in unit-disc terms: a short name plus its outline
    LABEL_BUDGET = max(8, int((math.pi * (USABLE_R * 0.92) ** 2) / (LABEL_W ** 2)))

    # Half a slot of clearance at each wedge edge, expressed in *slots* and converted to
    # an angle per wedge rather than as a fraction of the wedge. A fraction does not work:
    # the narrowest wedge here is a fraction of a degree, so a 6% guard is 0.02 degrees
    # and the last node of one type lands on the first node of the next. That produced
    # the five worst pairs in the whole graph (2.3px between `concept` and `level_axis`).
    EDGE_GUARD_SLOTS = 0.55

    def wedge_capacity(sweep_deg: float, r_in: float, r_out: float) -> int:
        """Nodes a wedge of this angle can hold between these two radii.

        A ring contributes nothing when its arc is shorter than the pitch. Forcing one
        seat per ring instead (the `max(1, ...)` that used to be here) is what stacked the
        narrow wedges onto a single ray: nine rings each holding exactly one node, all at
        the wedge's centre line, one pitch apart. The rows read as a dense column rather
        than a group, and the count it reported was wrong by the whole inner region.
        """
        total = 0
        r = max(r_in, PITCH * 0.5)
        while r <= r_out + PITCH * 0.5:
            arc_slots = int((2.0 * math.pi * r) * (sweep_deg / 360.0) / PITCH)
            if arc_slots >= 1:
                total += arc_slots
            r += PITCH
        return total

    def inner_radius_for(sweep_deg: float, r_in: float, r_out: float) -> float:
        """Smallest radius at which this wedge's arc is at least one pitch wide.

        A narrow wedge near the centre has no room for anything: at r=0.03 a 1-degree
        wedge is 0.0005 across. Starting there wastes the inner rings entirely, so the
        wedge begins where it can hold a node.

        Deliberately *one* node, not two. Requiring two looks like it helps (the inner
        tail of one-per-ring rings disappears) but it is the wrong lever: it buys
        horizontal room by spending radial room, and for a small type that trade is
        strictly bad — `level_axis` went from 15.9px to 10.6px when this asked for two,
        because nine nodes were left with four rings to fit into. Vertical room is what
        small types need, and that comes from `readable_sweep` below, not from here.
        """
        need = PITCH * 360.0 / (2.0 * math.pi * max(sweep_deg, 1e-6))
        return max(r_in, min(need, r_out * 0.92))

    # Angle has to be handed out so that every type can actually seat its members.
    #
    # Sharing by headcount does not do that: a wedge's capacity grows with radius, so a
    # narrow sector holds far fewer than its angle suggests. Solving each wedge by binary
    # search and *normalising the results* does not do it either, and that was the subtler
    # bug — the search returns an angle proportional to sqrt(headcount), and rescaling
    # those to 360 degrees hands every type a share of the circle proportional to its own
    # ask. The nine `level_axis` nodes asked for one degree and were granted 0.4 of one,
    # which is narrower than a single label.
    #
    # Allocate by angular *density* instead: each type claims a number of radial slots
    # (`headcount / slots-on-a-full-ring-at-its-own-radius`), then pays the mean density
    # to turn that into degrees. A type spread across many rings because it is narrow ends
    # up paying for the rings it actually uses, so the small types get a wedge they can be
    # read in while the large ones still dominate. When the total overshoots the circle,
    # the scale-down is uniform, so the relative claims survive.
    # Angle has to be handed out so that every type can actually seat its members.
    #
    # Sharing by headcount does not do that: a wedge's capacity grows with radius, so a
    # narrow sector holds far fewer than its angle suggests. Solving each wedge by binary
    # search and *normalising the results* does not do it either, and that was the subtler
    # bug — the search returns an angle proportional to sqrt(headcount), and rescaling
    # those to 360 degrees hands every type a share of the circle proportional to its own
    # ask. The nine `level_axis` nodes asked for one degree and were granted 0.4 of one,
    # which is narrower than a single label.
    #
    # Allocate in angular *density* terms instead. Each type claims `headcount` nodes, and
    # a wedge of `deg` degrees at this pitch has a known seating capacity; solve for the
    # angle whose capacity first covers the claim, then blend that "fitting" angle with a
    # pure headcount share. The blend keeps small types legible (they get the fit, which
    # for 9 nodes is a couple of degrees rather than a tenth of one) without letting the
    # large ones be starved by a wedge that is technically sufficient but unreadably thin.
    need = {t: max(0, counts[t] - (1 if (t == "character" and hero_anchored) else 0)) for t in present}

    def sweep_for(t: str) -> float:
        """Smallest angle whose seating capacity covers this type's claim."""
        want = max(need[t], 1)
        if wedge_capacity(360.0, 0.0, USABLE_R) < want:
            return 360.0  # cannot be seated even with the whole circle
        lo, hi = 0.05, 360.0
        for _ in range(48):
            mid = (lo + hi) / 2.0
            if wedge_capacity(mid, 0.0, USABLE_R) >= want:
                hi = mid
            else:
                lo = mid
        return hi

    claim = {t: max(need[t], 1) for t in present}
    total_claim = sum(claim.values()) or 1

    # A wedge has to be wide enough to read a label in, and that floor is nowhere near
    # as small as the geometry suggests. Nine nodes fit in a 5.9-degree wedge on paper —
    # one per ring, an exact pitch apart — but the rings are then separated *radially*
    # while the labels run *tangentially*, so nine labels in single file sit 8px apart
    # with 60px of overlap. The count is fine and the reading is not.
    #
    # The floor therefore has to grow as the type gets smaller, because a small type has
    # no radial room to hide in: 33 creatures spread over 14 rings is fine, 9 axes over
    # 4 rings is a pile. Asking for `ceil(n / 4)` abreast guarantees at least four rings
    # to work with whatever the headcount, which is the depth at which a wedge starts
    # reading as a group. It costs the large types about a degree each.
    MID_R = USABLE_R * 0.62
    MIN_RINGS = 4

    def readable_sweep(headcount: int) -> float:
        abreast = max(2.0, math.ceil(max(headcount, 1) / float(MIN_RINGS)))
        # Keep the request inside what a wedge can actually hold, or the floor would
        # demand more than 360 degrees for a big type and the normalisation would starve
        # everyone else to compensate.
        abreast = min(abreast, 8.0)
        return math.degrees(abreast * PITCH / max(MID_R, 1e-6))

    # Blend the geometric requirement with the headcount claim, then normalise. `fit` is
    # what it takes to seat the type at this pitch and is roughly proportional to the
    # headcount; `fair` splits the circle by headcount alone, which is too generous to the
    # crowd. `fit` leads because it measures the need directly.
    FIT_WEIGHT = 0.72
    raw = {}
    for t in present:
        fair = 360.0 * claim[t] / total_claim
        fit = max(sweep_for(t), readable_sweep(claim[t]))
        raw[t] = FIT_WEIGHT * fit + (1.0 - FIT_WEIGHT) * fair
    raw_total = sum(raw.values()) or 360.0
    sweeps = {t: raw[t] * 360.0 / raw_total for t in present}

    # A pure fit/fair blend is monotone in headcount, so the largest type keeps growing and
    # every other wedge is squeezed toward the degenerate line where labels overlap. With
    # 425 characters the blend gave one wedge 40% of the circle and left `level_axis` and
    # `creature` as unreadable slivers — the same complaint the reader made about the old
    # force-directed view, just expressed in sectors instead of a hairball.
    #
    # The cap makes the layout *sub-linear* in headcount: a type can be at most
    # `MAX_SWEEP` of the circle, so the crowd has to spend its extra members on radial
    # depth rather than angular width. The freed degrees are handed to whoever the cap
    # squeezed, in proportion to what they asked for. Three passes because taking degrees
    # from one type can push another over the cap.
    #
    # The cap value is solved against the actual allocator, not against a hand model of
    # it. Seating all eight types at the full pitch needs 377.1 degrees — 17.1 more than a
    # circle has — so someone must be compressed and the only question is who. Raising the
    # cap looks like it should help the mid-size types (a hand calculation says 138.5 lets
    # location/item/concept/skill keep full pitch) but it does the opposite here: the
    # degrees freed by the cap are redistributed in proportion to *requested* sweep, so
    # every wedge below the cap grows a little, the total overshoots again, and six types
    # end up compressed instead of four. Measured at 138.5: character 137 + six types at
    # 0.04339. Measured at 132.0: character 132 + four types at 0.04339. The lower cap is
    # the better layout, and the only trustworthy way to find that out was to build both
    # and read `pitch_used` out of the payload.
    #
    # `character` cannot reach full pitch at any cap that leaves the other seven room
    # (it needs 155.5 and they need 221.6). So the crowd compresses — which is the point
    # of the cap — and the constant is set where the fewest others pay for it.
    MAX_SWEEP = 132.0
    for _ in range(3):
        over = {t: sweeps[t] - MAX_SWEEP for t in sweeps if sweeps[t] > MAX_SWEEP}
        if not over:
            break
        freed = sum(over.values())
        for t in over:
            sweeps[t] = MAX_SWEEP
        hungry = {t: sweeps[t] for t in sweeps if sweeps[t] < MAX_SWEEP}
        h_total = sum(hungry.values()) or 1.0
        for t in hungry:
            sweeps[t] += freed * (hungry[t] / h_total)
        scale = 360.0 / (sum(sweeps.values()) or 360.0)
        for t in sweeps:
            sweeps[t] *= scale

    zones: dict[str, dict] = {}
    positions: dict[str, dict[str, float]] = {}
    cursor = -90.0  # start at the top

    for t in present:
        members = [e for e in entities if e.get("type") == t]
        others = [e for e in members if e["id"] != hero]
        anchored = t == "character" and hero_anchored
        if anchored:
            positions[hero] = {"x": 0.0, "y": 0.0, "zone": t}

        sweep = sweeps[t]
        z_start, z_end = cursor, cursor + sweep
        cursor = z_end

        # The protagonist occupies the very centre, so the character wedge has to start
        # outside his marker rather than under it.
        r_base = PITCH * 2.4 if anchored else 0.0
        r_out = 0.97
        n = len(others)

        if not n:
            zones[t] = {"start": z_start, "end": z_end, "count": counts[t],
                        "r_in": round(r_base, 3), "r_out": round(r_out, 3), "rings": 0}
            continue

        # A narrow wedge has no usable area near the centre, so it begins at the radius
        # where its arc is at least one pitch wide. Without this the inner rings are
        # empty and the type is pushed to the rim for nothing.
        r_in = inner_radius_for(sweep, r_base, r_out)

        # Clearance at each wedge edge, expressed in slots and converted to degrees. A
        # guard that is a *fraction* of the sweep vanishes on a narrow wedge: 6% of 0.4
        # degrees is 0.02, and the last node of one type landed on the first node of the
        # next. Slots do not have this problem because the arc a slot occupies is roughly
        # constant whatever the wedge's angle.
        #
        # This is computed *before* the ring table because the rings must be sized against
        # the same arc the placement loop will fill. Counting seats from the full sweep and
        # then insetting by the guard overstates capacity by exactly the inset: harmless on
        # a 38° wedge, but on a narrow wedge's inner rings the arc is barely one pitch to
        # begin with, so the discrepancy was the whole margin and 583 pairs ended up 0.0377
        # apart when the pitch said 0.0549.
        guard_deg = min((EDGE_GUARD_SLOTS * PITCH * 360.0) / (2.0 * math.pi * r_out), sweep / 6.0)
        span = max(sweep - 2.0 * guard_deg, 1e-6)

        # Seats are laid out ring by ring. A ring at radius `r` that spans
        # `avail_deg` of arc can hold `k` seats at one pitch of *chord* spacing, and `k`
        # is found by solving `2 r sin(step/2) >= PITCH` for the largest `k` with
        # `step = avail_deg / k`. The chord form matters: solving against the arc length
        # (`r * step >= PITCH`) asks for slightly more seats than the ring can space,
        # because a chord is always shorter than its arc. That discrepancy is invisible
        # on a wide ring and is *the entire margin* on a small one, which is how 580
        # same-ring pairs ended up 25% closer than the pitch while the code looked right.
        #
        # Rings grow outward from `r_in`. If the wedge fills before the members run out,
        # the remainder is placed by shrinking this wedge's own effective pitch — the
        # degradation is local to the type that needs it, and `pitch_used` reports what
        # each type actually got so the caller can see it rather than guess.
        def seats_on_ring(radius: float, avail_deg: float, pitch: float) -> int:
            if radius <= 0 or avail_deg <= 0:
                return 0
            k = int(radius * math.radians(avail_deg) / pitch)
            while k > 1 and 2.0 * radius * math.sin(math.radians(avail_deg / k) / 2.0) < pitch:
                k -= 1
            if k < 1:
                return 0
            if 2.0 * radius * math.sin(math.radians(avail_deg / k) / 2.0) < pitch:
                return 0
            return k

        def ring_table(pitch: float) -> list[tuple[float, int]]:
            """Every ring from `r_in` to `r_out`, and how many seats each will take."""
            out: list[tuple[float, int]] = []
            rr = r_in
            while rr <= r_out + 1e-9:
                k = seats_on_ring(rr, span, pitch)
                if k >= 1:
                    out.append((round(rr, 6), k))
                rr += pitch
            return out

        seats = ring_table(PITCH)
        pitch_used = PITCH
        # Halve the pitch until the wedge can hold everyone, or until further shrinking
        # stops helping. Bounded at eight halvings, which is a 256-fold density increase —
        # far past any real book, and it guarantees the loop terminates.
        for _ in range(8):
            if sum(k for _, k in seats) >= n:
                break
            pitch_used = pitch_used * 0.79
            seats = ring_table(pitch_used)
        if not seats:
            seats = [(r_in, n)]

        # If even the finest pitch in the budget cannot seat them, spread the surplus over
        # the widest rings. This is the only path that can violate the spacing contract and
        # it only triggers on a book whose single largest type is denser than a disc can
        # hold at this scale.
        cap = sum(k for _, k in seats)
        if cap < n:
            order = sorted(range(len(seats)), key=lambda i: -seats[i][1]) or [0]
            surplus = n - cap
            i = 0
            while surplus > 0:
                wi = order[i % len(order)]
                rw, kw = seats[wi]
                seats[wi] = (rw, kw + 1)
                surplus -= 1
                i += 1

        # Place. Rings alternate a half-step offset in absolute degrees; the offset is half
        # of the *largest* ring's step so that "odd rings sit between even rings' seats"
        # stays true where two neighbouring rings hold different counts.
        widest = max(k for _, k in seats) if seats else 1
        half_step = (span / widest) * 0.5
        idx = 0
        for ri, (rr, take) in enumerate(seats):
            if take <= 0:
                continue
            off_deg = half_step if (ri % 2) else 0.0
            for k in range(take):
                frac = (k + 0.5) / take
                ang = z_start + guard_deg + frac * span + off_deg
                # Keep every seat strictly inside the wedge. The guard exists so the first
                # node of one type cannot land on the last node of the previous one, and
                # squashing the result back into `[lo, hi]` preserves that without the
                # modulo arithmetic that would wrap a seat onto the far side of the disc.
                lo_a, hi_a = z_start + guard_deg, z_end - guard_deg
                if hi_a > lo_a:
                    ang = min(max(ang, lo_a), hi_a)
                positions[others[idx]["id"]] = {
                    "x": round(math.cos(math.radians(ang)) * rr, 5),
                    "y": round(math.sin(math.radians(ang)) * rr, 5),
                    "zone": t,
                }
                idx += 1
                if idx >= n:
                    break
            if idx >= n:
                break

        zones[t] = {"start": round(z_start, 1), "end": round(z_end, 1), "count": counts[t],
                    "r_in": round(r_in, 3), "r_out": round(r_out, 3), "rings": len(seats),
                    "pitch_used": round(pitch_used, 5)}

    return {"positions": positions, "zones": zones, "present": present,
            "pitch": round(PITCH, 5)}


def compute_circles(graph: dict[str, Any]) -> dict[str, Any]:
    """Group entities into the social circles the relations actually describe.

    Why this exists: the disc layout places a node by `(type, index-within-type)` and
    never looks at the edges. Measured on the 400-chapter build, that produces 174
    disconnected components inside one 640-node picture — the largest holding 440 nodes
    and the rest mostly 2-5 — plus 155 nodes with no edges at all. A family of three who
    relate only to each other ("苏姬 · 苏妃 · 苏耀") gets seated wherever their index falls
    inside the 132° character wedge, so the picture shows a uniform scatter of dots with
    no visible groupings. The reader asked for "集合效果" — collections you can see.
    Type is not the interesting grouping; who associates with whom is.

    Two levels, because they answer different questions:

      * weak connected components — the hard partition. Anything in one component can
        reach anything else in it, so it is safe to draw as one enclosure.
      * label propagation inside the giant component — the giant one is 440 of 640 nodes
        and enclosing it says nothing. Propagating labels splits it into the circles a
        reader recognises: the Su family, the Long family plus their corporation, the
        Japanese faction.

    Label propagation is run with a fixed seed and a shuffled sweep order so the output is
    reproducible; an unreproducible layout would make every screenshot and every gate
    result incomparable between two builds of the same input.

    Entities with no relations are *not* a circle. They are reported as one explicit
    `isolated` bucket so the view can put them somewhere deliberate instead of scattering
    them through the disc as litter.
    """
    entities = [e for e in (graph.get("entities") or []) if isinstance(e, dict) and e.get("id")]
    known = {e["id"] for e in entities}

    parent = {i: i for i in known}

    def find(x: str) -> str:
        root = x
        while parent[root] != root:
            root = parent[root]
        while parent[x] != root:
            parent[x], x = root, parent[x]
        return root

    def union(a: str, b: str) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb

    adj: dict[str, set[str]] = {i: set() for i in known}
    for r in (graph.get("relations") or []):
        if not isinstance(r, dict):
            continue
        s, t = r.get("source_id"), r.get("target_id")
        if s in known and t in known and s != t:
            union(s, t)
            adj[s].add(t)
            adj[t].add(s)

    linked = sorted(i for i in known if adj[i])
    isolated = sorted(i for i in known if not adj[i])

    comp: dict[str, list[str]] = {}
    for i in linked:
        comp.setdefault(find(i), []).append(i)
    components = sorted(comp.values(), key=len, reverse=True)

    degree = {i: len(adj[i]) for i in known}

    # Label propagation over every linked entity at once. Components are still honoured
    # because a node with no neighbours keeps its own label and can never adopt another's.
    rng = random.Random(20260918)
    label = {i: i for i in linked}
    for _ in range(32):
        order = linked[:]
        rng.shuffle(order)
        changed = 0
        for n in order:
            nb = adj[n]
            if not nb:
                continue
            counts: dict[str, int] = {}
            for m in nb:
                counts[label[m]] = counts.get(label[m], 0) + 1
            best = max(counts.items(), key=lambda kv: (kv[1], kv[0]))[0]
            if label[n] != best:
                label[n] = best
                changed += 1
        if not changed:
            break

    buckets: dict[str, list[str]] = {}
    for i in linked:
        buckets.setdefault(label[i], []).append(i)

    def describe(members: list[str]) -> str:
        """Name a circle by its most connected real members — never invent one."""
        top = sorted(members, key=lambda x: (-degree[x], x))[:3]
        by_id = {e["id"]: e for e in entities}
        names = [str(by_id[t].get("name") or t) for t in top if t in by_id]
        return " · ".join(names)

    circles: list[dict[str, Any]] = []
    # Largest first so the colour ramp runs from the big factions to the small cliques.
    for rank, members in enumerate(sorted(buckets.values(), key=len, reverse=True)):
        members = sorted(members, key=lambda x: (-degree[x], x))
        circles.append({
            "id": f"circle-{len(circles):02d}",
            "label": describe(members),
            "size": len(members),
            "members": members,
            # A component of one can only happen if it has an edge to a node outside
            # `known`; treat anything under 3 as a clique rather than a faction.
            "kind": "faction" if len(members) >= 8 else ("clique" if len(members) >= 3 else "pair"),
            # Whether this circle sits inside the one big connected web of the book or
            # stands outside it. Measured on this graph the 500 linked entities form 19
            # weak components and the largest holds 456 of them, so "is it in the giant"
            # is a real distinction the reader can act on, and a circle that stands alone
            # is a different kind of fact from a faction embedded in the main web.
            "giant": rank == 0,
        })

    return {
        "circles": circles,
        "isolated": {"label": "未连接", "size": len(isolated), "members": isolated},
        "degree": degree,
        # The hard partition underneath the circles: how many separate webs the relations
        # actually describe, and how big the biggest one is. Reported rather than only
        # implied so a check can tell a real regroup from a reshuffle.
        "components": len(components),
        "giant_size": len(components[0]) if components else 0,
        "linked": len(linked),
    }


def build_model(graph: dict[str, Any], protagonists: list[str], gap_threshold: int, cutoff: int | None,
                vocabulary: dict[str, Any] | None, style_payload: Any | None = None) -> dict[str, Any]:
    meta = graph.get("metadata") if isinstance(graph.get("metadata"), dict) else {}
    vocab = merge_vocabulary(
        DEFAULT_VOCABULARY,
        meta.get("display_vocabulary") if isinstance(meta.get("display_vocabulary"), dict) else {},
    )
    vocab = merge_vocabulary(vocab, ATLAS_VOCABULARY)
    if vocabulary:
        vocab = merge_vocabulary(vocab, vocabulary)

    layers = build_layers(graph)
    layout = compute_zone_layout(graph, layers, protagonists)
    views = build_views(graph, protagonists, max(1, gap_threshold))

    # Two extras are decided from the graph itself rather than hand-written flags.
    # `_agents` carries the anthropomorphism verdict (so a creature that speaks and
    # holds goals gets the character-style layout, while a mere mount scores 0), and
    # `_style_observations` carries the validated narrative-voice rows.
    from agent_detection import detect_agents
    agents = detect_agents(graph)
    style_rows: list[dict[str, Any]] = []
    if style_payload is not None:
        from validate_style_observations import validate_style_observations
        style_rows = validate_style_observations(style_payload, graph)

    entities = [e for e in (graph.get("entities") or []) if isinstance(e, dict)]
    tier_counts = Counter(_layer_of(e.get("type")) for e in entities)
    circles = compute_circles(graph)

    return {
        "graph": {
            "metadata": {
                "title": meta.get("title"),
                "chapter_start": meta.get("chapter_start"),
                "chapter_end": meta.get("chapter_end"),
                "analyzed_chapters": meta.get("analyzed_chapters") or [],
                "temporal_provenance_gaps": meta.get("temporal_provenance_gaps") or [],
            },
            "entities": entities,
            "relations": graph.get("relations") or [],
            "events": graph.get("events") or [],
            "state_changes": graph.get("state_changes") or [],
            "chapter_summaries": graph.get("chapter_summaries") or [],
            "character_traits": graph.get("character_traits") or [],
            "item_roles": graph.get("item_roles") or [],
            "commitments": graph.get("commitments") or [],
            "foreshadowing": graph.get("foreshadowing") or [],
            "intimate_acts": graph.get("intimate_acts") or [],
            "romance_routes": graph.get("romance_routes") or [],
            "level_conversions": graph.get("level_conversions") or [],
            "evidence": graph.get("evidence") or [],
            "review_issues": graph.get("review_issues") or [],
            "_display_vocabulary": vocab,
            "_agents": agents,
            "_style_observations": style_rows,
        },
        "layers": {
            "traits_by_entity": layers["traits_by_entity"],
            "changes_by_entity": layers["changes_by_entity"],
            "changes_by_target": layers["changes_by_target"],
            "relations_by_entity": layers["relations_by_entity"],
            "item_roles_by_item": layers["item_roles_by_item"],
        },
        # Every key `compute_circles` returns is carried through. Listing them by hand is how
        # `components`/`giant_size`/`linked` were silently dropped once already: the check that
        # wants to assert "the circles partition the linked entities" then read `linked: 0`
        # and passed without ever testing the claim.
        "layout": {**layout, **circles, "community_degree": circles["degree"]},
        "views": views,
        "counts": {
            "entities": len(entities),
            "tier_agent": tier_counts.get("agent", 0),
            "tier_thing": tier_counts.get("thing", 0),
            "tier_world": tier_counts.get("world", 0),
            "events": len(graph.get("events") or []),
            "relations": len(graph.get("relations") or []),
            "state_changes": len(graph.get("state_changes") or []),
            "traits": len(graph.get("character_traits") or []),
            "summaries": len(graph.get("chapter_summaries") or []),
            "evidence": len(graph.get("evidence") or []),
            "intimate": len(graph.get("intimate_acts") or []),
            "foreshadowing": len(graph.get("foreshadowing") or []),
            "commitments": len(graph.get("commitments") or []),
            "item_roles": len(graph.get("item_roles") or []),
            "issues": len(graph.get("review_issues") or []),
        },
        "metadata": {"cutoff": cutoff, "protagonists": protagonists},
    }


CSS = r"""
:root{
  color-scheme:light;
  /* ---- surface & ink ----
   * The palette was already restrained; what it lacked was a *ramp*. Every step now has
   * a stated job, so a new component picks a token instead of inventing a hex:
   *   bg      the page behind everything
   *   surface cards and panels
   *   surface2 raised strips inside a card (table headers, row stripes)
   *   surface3 recessed wells (inputs, code, empty states)
   * Ink runs ink → ink2 → muted → faint in decreasing prominence. `ink2` is the body
   * text of a secondary line; `muted` is a label; `faint` is a hint that should be
   * legible but never competes. */
  --bg:#f2f3f7; --surface:#fff; --surface2:#f8f9fc; --surface3:#eceef4;
  --ink:#141821; --ink2:#3a4250; --muted:#646c7e; --faint:#98a0b0;
  --line:#e3e6ed; --line2:#d0d4e0;
  /* ---- accent ---- */
  --accent:#5b51d6; --accent-soft:#eeecff; --accent-ink:#463dbe;
  --good:#12805c; --good-soft:#e4f4ee;
  --warn:#ac6306; --warn-soft:#fdf2e0;
  --danger:#b03a3a; --danger-soft:#fdeaea;
  /* ---- geometry ----
   * One radius scale and one shadow scale, both short. The previous two-value radius
   * (10/14) collapsed under nesting — a 14px card holding a 10px chip reads as a
   * mismatch once the card itself sits inside a padded section, so `sm` exists for
   * in-card controls and the sizes now nest visibly (8 inside 12 inside 16). */
  --r-sm:8px; --r-md:12px; --r-lg:16px; --r-pill:999px;
  --radius:var(--r-md); --radius-lg:var(--r-lg);
  /* A four-step spacing scale, and deliberately not six.
   *
   * The page had forty-four near-identical gaps — 4px, 6px, 7px, 8px, 9px — which is what a
   * layout looks like when each component picks its own number. They now resolve to two steps
   * (4px and 8px) plus two for panel padding (12px and 16px). Two larger steps were declared
   * here first and removed: nothing read them, and a token nobody reads is the same defect as a
   * vocabulary entry with no call site — the next author picks the plausible-looking name and
   * gets a value that was never tuned against anything. */
  --sp-1:4px; --sp-2:8px; --sp-3:12px; --sp-4:16px;
  /* Shadows are tinted with the ink hue rather than pure black, which is what keeps a
   * light UI from looking grey-smudged, and the spread is small: this is a document,
   * not a dashboard of floating panels. */
  --shadow:0 1px 2px rgba(20,24,33,.05),0 3px 10px rgba(20,24,33,.045);
  --shadow-md:0 2px 6px rgba(20,24,33,.06),0 10px 26px rgba(20,24,33,.07);
  --shadow-lg:0 4px 12px rgba(20,24,33,.08),0 18px 44px rgba(20,24,33,.10);
  /* ---- motion ----
   * One duration for state changes on a control. A second, slower duration was declared here
   * and removed: the drawer and the palette both appear by toggling `display`, which cannot be
   * transitioned, so there was no slower transition for it to govern. */
  --ease:cubic-bezier(.22,.61,.36,1);
  --t-fast:.13s;
  --type-character:#5b51d6; --type-organization:#0f7494; --type-location:#348551;
  --type-item:#ac6306; --type-skill:#9046a0; --type-creature:#0b8071;
  --type-concept:#646c7e; --type-level_axis:#b8430b;
  /* Per-type colours live here and nowhere else, so a type has ONE colour on this site:
   * the fan chart's wedge, the shape in the legend, the dot beside a sidebar row, the bar on
   * a card line and the chip on a page all resolve through `ZONE_COLOR` -> `var(--type-*)`.
   * A previous revision also declared three zone-level tints (agent/thing/world); they were
   * removed because nothing read them — every surface asks for a *type*, and a second,
   * coarser set of colours sitting unused beside the one that works is a trap for the next
   * component author, who would reasonably pick the token whose name matches the payload key. */
}
*{box-sizing:border-box}
html{scroll-behavior:smooth}
.ix-group{scroll-margin-top:70px}
/* The base size steps up to 14.5px and the line-height to 1.68. This is a page of
 * continuous Chinese prose — 97-character chapter summaries, paragraph-length relation
 * descriptions — and CJK at 14px/1.6 is the density of a settings dialog, not of
 * something written to be read. The Latin-first stack keeps digits and Latin words in
 * Inter while microsoft-yahei carries the Han; claiming a webfont is not an option in a
 * self-contained file, so this is the system stack done properly. */
body{
  margin:0;background:var(--bg);color:var(--ink);
  font:14.5px/1.68 "Inter","Segoe UI Variable Text","Segoe UI","Microsoft YaHei","PingFang SC",sans-serif;
  -webkit-font-smoothing:antialiased;
  text-rendering:optimizeLegibility;
}
/* Headings get tighter letter-spacing as they grow, which is the one typographic rule
 * that most separates a styled page from a defaulted one: 17px bold Chinese with default
 * tracking looks loose next to 14.5px body. */
h1,h2,h3{letter-spacing:-.012em}
a{color:var(--accent-ink);text-decoration:none}
button{font:inherit;cursor:pointer}
/* Numerals in tables and stat strips line up in columns instead of shifting width. */
.stat-v,.attr .v,.ev-ch,.when,.side-kinds b{font-variant-numeric:tabular-nums}

/* ---------- top bar ---------- */
header.top{
  position:sticky;top:0;z-index:40;background:rgba(244,245,247,.88);
  backdrop-filter:blur(12px);border-bottom:1px solid var(--line);
}
.top-inner{padding:11px 26px;margin-left:calc(var(--side-w) + var(--side-gap) + 18px);display:flex;align-items:center;gap:18px;flex-wrap:wrap}
@media (max-width:1560px){.top-inner{margin-left:0}}
.brand{display:flex;align-items:baseline;gap:var(--sp-2);min-width:0}
.brand h1{margin:0;font-size:17px;font-weight:650;letter-spacing:-.01em;white-space:nowrap}
.brand .sub{color:var(--muted);font-size:12px;white-space:nowrap}
.scrub{display:flex;align-items:center;gap:11px;margin-left:auto;flex:1;min-width:320px;max-width:560px}
.scrub label{font-size:12px;color:var(--muted);white-space:nowrap}
.scrub input[type=range]{flex:1;accent-color:var(--accent);height:20px}
.chapter-badge{
  font:600 12px/1 ui-monospace,SFMono-Regular,Menlo,monospace;
  background:var(--accent-soft);color:var(--accent-ink);
  padding:6px 9px;border-radius:7px;white-space:nowrap;
}
.snap-note{font-size:11.5px;color:var(--faint);white-space:nowrap}

/* ---------- shell ---------- */
/* The sidebar is fixed, so the shell and the top bar both reserve the same gutter. The
 * two reserves read the same variable the sidebar's own width uses, so a width change in
 * one place cannot leave the other overlapping the labels. */
/* The shell is flush to the sidebar rather than centred in a max-width box. Centring with
 * a left padding that reserves the sidebar's width double-counts it: the padding pushes
 * the content right while `margin: auto` re-centres the padded box, so the content ends up
 * narrower than the viewport by the sidebar's width and the right edge sits empty. */
.shell{padding:22px 26px 40px 26px;
  margin-left:calc(var(--side-w) + var(--side-gap) + 18px);
  display:grid;grid-template-columns:minmax(0,1fr);gap:22px;align-items:start}
body.drawer-open .shell{grid-template-columns:minmax(0,1fr) 460px}
/* Below the sidebar's breakpoint it stops being a column, so the offset goes away. */
@media (max-width:1560px){.shell{margin-left:0;padding-left:22px}}

/* ---------- sidebar ----------
 * Fixed to the left edge, a full column tall, and never dismissed. The earlier version
 * was a floating card centred in the gutter: it covered whatever was behind it and had to
 * be pushed aside on narrow screens. A reader who is looking things up wants the index
 * to stay put, so it occupies its own column and the content simply starts after it.
 *
 * It holds the three ways a reader arrives somewhere: searching (always visible, not
 * hidden behind a key), browsing by kind (the tree), and jumping within the current page
 * (the block rail). */
:root{--side-w:232px;--side-gap:16px;--rail-w:186px}
#side{position:fixed;left:0;top:0;bottom:0;z-index:38;
  width:calc(var(--side-w) + var(--side-gap) + 18px);
  padding:12px 0 12px 14px;
  display:flex;flex-direction:column;gap:10px;
  background:linear-gradient(180deg,#fbfbfd 0%,#f7f8fa 100%);
  border-right:1px solid var(--line)}
.side-search{position:relative;padding-right:14px}
.side-search input{width:100%;border:1px solid var(--line2);background:var(--surface);
  border-radius:9px;padding:8px 30px 8px 11px;font-size:12.5px;color:var(--ink);
  transition:border-color var(--t-fast) var(--ease),box-shadow var(--t-fast) var(--ease)}
.side-search input::placeholder{color:var(--faint)}
.side-search input:focus{outline:none;border-color:var(--accent);
  box-shadow:0 0 0 3px var(--accent-soft)}
.side-kbd{position:absolute;right:22px;top:50%;transform:translateY(-50%);
  font:600 10px/1 ui-monospace,monospace;color:var(--faint);
  border:1px solid var(--line2);border-radius:4px;padding:2px 5px;pointer-events:none;
  background:var(--surface)}
.side-scroll{flex:1;min-height:0;overflow:auto;padding-right:8px;
  display:flex;flex-direction:column;gap:14px}
.side-scroll::-webkit-scrollbar{width:7px}
.side-scroll::-webkit-scrollbar-thumb{background:var(--line2);border-radius:4px}
.side-scroll::-webkit-scrollbar-thumb:hover{background:var(--faint)}

/* A section heading is a control, so it is a real button with the affordances of one:
 * a disclosure caret that turns, a hover state, and a cursor. It reads as the same
 * heading it always was, but it now answers a click instead of merely looking clickable. */
#side .side-h{font:600 9.5px/1.4 ui-monospace,monospace;color:var(--faint);
  letter-spacing:.07em;padding:6px 4px 6px 2px;margin:0;width:100%;background:none;
  border:0;border-radius:6px;text-align:left;cursor:pointer;
  display:flex;align-items:center;gap:var(--sp-2);transition:background var(--t-fast) var(--ease),color var(--t-fast) var(--ease)}
#side .side-h:hover{background:var(--surface3);color:var(--ink2)}
#side .side-h .n{font:600 9.5px/1 ui-monospace,monospace;color:var(--accent-ink);
  background:var(--accent-soft);padding:2px 5px;border-radius:4px;letter-spacing:0}
#side .side-h .tail{margin-left:auto;font:600 9.5px/1 ui-monospace,monospace;
  color:var(--faint);letter-spacing:0}
#side .side-h .tw{width:0;height:0;flex:none;border-left:4px solid currentColor;
  border-top:3.5px solid transparent;border-bottom:3.5px solid transparent;
  transform:rotate(90deg);transform-origin:38% 50%;transition:transform var(--t-fast) var(--ease) ease}
#side .side-h.shut .tw{transform:rotate(0deg)}
.side-crumb{font-size:11.5px;color:var(--muted);padding:2px 2px 0;line-height:1.7;
  display:flex;flex-wrap:wrap;align-items:baseline;gap:1px}
.side-crumb a{color:var(--muted);border-bottom:1px solid transparent}
.side-crumb a:hover{color:var(--accent-ink);border-bottom-color:var(--accent)}
.side-crumb b{color:var(--ink);font-weight:600}
.side-crumb .sep{color:var(--faint);padding:0 3px}
.side-acts{display:flex;gap:var(--sp-2);margin:2px 0 2px}
.side-acts .sbtn{flex:1;font-size:11.5px;color:var(--muted);padding:6px 8px;
  border-radius:7px;background:var(--surface);border:1px solid var(--line);
  cursor:pointer;text-align:center;transition:var(--t-fast) var(--ease);font-family:inherit}
.side-acts .sbtn:hover{color:var(--accent-ink);border-color:var(--accent);
  background:var(--accent-soft)}
/* The rail's group headings are disclosure controls too. */
#rail .rt{cursor:pointer;border:0;background:none;width:100%;text-align:left;
  display:flex;align-items:center;gap:5px;border-radius:6px;transition:background var(--t-fast) var(--ease)}
#rail .rt:hover{background:var(--surface3)}
#rail .rt .cnt{margin-left:auto}
#rail .rt .tw{width:0;height:0;flex:none;border-left:4px solid currentColor;
  border-top:3.5px solid transparent;border-bottom:3.5px solid transparent;
  transform:rotate(90deg);transform-origin:38% 50%;transition:transform var(--t-fast) var(--ease) ease}
#rail .rt.shut .tw{transform:rotate(0deg)}

/* kinds — a branch per type, each with the live count so an empty kind cannot show */
.side-kinds{display:flex;flex-direction:column;gap:1px;padding-right:2px}
.side-kinds a{display:flex;align-items:center;gap:var(--sp-2);font-size:12.5px;color:var(--ink2);
  padding:6px 9px;border-radius:7px;transition:background var(--t-fast) var(--ease),color var(--t-fast) var(--ease)}
.side-kinds a i{width:7px;height:7px;border-radius:2px;flex:none}
.side-kinds a i.ev{background:var(--faint)}
.side-kinds a span{flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.side-kinds a b{font:600 10px/1 ui-monospace,monospace;color:var(--faint);
  font-variant-numeric:tabular-nums}
.side-kinds a:hover{background:var(--surface3);color:var(--ink)}
.side-kinds a.on{background:var(--accent-soft);color:var(--accent-ink);font-weight:620}
.side-kinds a.on b{color:var(--accent-ink)}

/* chapter grid — the one genuinely numeric list, so it is a grid, not a branch */
.side-ch{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:var(--sp-1);padding-right:2px}
.side-ch button{border:1px solid var(--line);background:var(--surface);color:var(--ink2);
  font:600 11px/1 ui-monospace,monospace;padding:7px 0;border-radius:6px;
  transition:var(--t-fast) var(--ease);font-variant-numeric:tabular-nums}
.side-ch button:hover{border-color:var(--accent);color:var(--accent-ink);background:var(--accent-soft)}
.side-ch .mini{grid-column:1/-1;font-size:10.5px;color:var(--faint);padding-top:3px}

/* search hits */
#side-hits{padding-bottom:2px}
.side-hit{display:flex;flex-direction:column;gap:2px;width:100%;text-align:left;
  border:none;background:none;padding:7px 9px;border-radius:7px;transition:background var(--t-fast) var(--ease)}
.side-hit:hover{background:var(--accent-soft)}
.side-hit .nm{font-size:12.5px;font-weight:560;color:var(--ink)}
.side-hit:hover .nm{color:var(--accent-ink)}
.side-hit .sb{font-size:10.5px;color:var(--faint);font-family:ui-monospace,monospace;
  overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.side-none{font-size:11.5px;color:var(--faint);padding:4px 2px;line-height:1.6}

/* the block rail lives inside the sidebar now, so it is a static list, not a card */
#rail{display:flex;flex-direction:column;gap:1px}
#rail .rt{font:600 9.5px/1.4 ui-monospace,monospace;color:var(--faint);
  letter-spacing:.07em;padding:0 2px 7px;margin-top:4px}
#rail .rt:first-child{margin-top:0}
#rail button{display:flex;align-items:center;gap:var(--sp-2);border:none;background:none;
  color:var(--ink2);font-size:12.5px;padding:6px 9px;border-radius:7px;text-align:left;
  white-space:nowrap;transition:background var(--t-fast) var(--ease),color var(--t-fast) var(--ease)}
#rail button i{width:5px;height:5px;border-radius:50%;background:var(--line2);flex:none;transition:var(--t-fast) var(--ease)}
#rail button:hover{background:var(--surface3);color:var(--ink)}
#rail button.on{background:var(--accent-soft);color:var(--accent-ink);font-weight:620}
#rail button.on i{background:var(--accent)}
#rail button .cnt{margin-left:auto;font:600 9.5px/1 ui-monospace,monospace;color:var(--faint)}
#rail button.on .cnt{color:var(--accent-ink)}

/* Narrow enough that a permanent column would starve the content: the sidebar collapses
 * to a horizontal strip pinned under the top bar, which keeps search and the kind tree
 * reachable without stealing the full column. */
@media (max-width:1560px){
  #side{position:sticky;top:0;left:auto;bottom:auto;width:auto;flex-direction:row;
    align-items:center;gap:14px;padding:9px 14px;border-right:0;
    border-bottom:1px solid var(--line);overflow-x:auto}
  .side-scroll{flex-direction:row;align-items:center;gap:14px;overflow:visible;padding-right:0}
  #side .side-h{padding:0 6px 0 0}
  .side-kinds{flex-direction:row;gap:2px}
  .side-ch{grid-template-columns:repeat(8,minmax(0,1fr))}
  #rail,#side-hits{display:none}
}

/* ---------- tier headers ---------- */
.tier{
  display:flex;align-items:center;gap:12px;margin:34px 0 14px;
  padding-bottom:9px;border-bottom:2px solid var(--line2);
}
.tier:first-of-type{margin-top:6px}
.tier .tag{
  font:600 11px/1 ui-monospace,monospace;background:var(--ink);color:#fff;
  padding:5px 8px;border-radius:6px;letter-spacing:.04em;
}
.tier h2{margin:0;font-size:19px;font-weight:650;letter-spacing:-.01em}
.tier .hint{color:var(--muted);font-size:12.5px;margin-left:auto;text-align:right}

/* ---------- cards / sections ---------- */
.block{background:var(--surface);border:1px solid var(--line);border-radius:var(--r-lg);box-shadow:var(--shadow);margin-bottom:var(--sp-4);overflow:hidden}
.block-head{display:flex;align-items:center;gap:10px;padding:var(--sp-3) var(--sp-4);border-bottom:1px solid var(--line);background:var(--surface2)}
.block-head h3{margin:0;font-size:14.5px;font-weight:620}
.block-head .n{font:600 11px/1 ui-monospace,monospace;color:var(--muted);background:var(--surface3);padding:4px 7px;border-radius:5px}
.block-head .right{margin-left:auto;display:flex;gap:var(--sp-2);align-items:center}
.block-body{padding:15px 16px}
.block-body.tight{padding:11px 12px}

/* ---------- stat strip ---------- */
/* The column count arrives as `--cols` because it depends on how many counters the
 * data produced; a fixed `auto-fit` track fitted nine of ten and stranded the last.
 * The narrow-width overrides re-declare `--cols` rather than re-using `min()` inside
 * `repeat()`, which not every engine resolves. */
.stat-strip{display:grid;grid-template-columns:repeat(var(--cols,5),minmax(0,1fr));gap:11px;margin-bottom:16px}
@media (max-width:1180px){.stat-strip{--cols:4}}
@media (max-width:900px){.stat-strip{--cols:3}}
@media (max-width:640px){.stat-strip{--cols:2}}
.stat{background:var(--surface);border:1px solid var(--line);border-radius:var(--radius-lg);padding:13px 15px;box-shadow:var(--shadow);cursor:pointer;transition:var(--t-fast) var(--ease)}
.stat:hover{border-color:var(--accent);transform:translateY(-1px);box-shadow:var(--shadow-lg)}
.stat .v{font-size:23px;font-weight:670;letter-spacing:-.02em;line-height:1.15}
.stat .l{color:var(--muted);font-size:12px;margin-top:3px}
.stat .src{color:var(--faint);font-size:10.5px;margin-top:5px;font-family:ui-monospace,monospace}

/* ---------- entity grid ---------- */
.e-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(232px,1fr));gap:11px}
.e-card{
  background:var(--surface);border:1px solid var(--line);border-radius:var(--r-lg);
  padding:var(--sp-3) var(--sp-3) calc(var(--sp-3) + 1px);box-shadow:var(--shadow);
  cursor:pointer;position:relative;overflow:hidden;
  transition:border-color var(--t-fast) var(--ease),box-shadow var(--t-fast) var(--ease),
             transform var(--t-fast) var(--ease);
}
/* `--shadow-md` rather than `--shadow-lg` on hover: a card that lifts 2px should not gain the
 * same depth as the drawer, which actually floats over the page. Two surfaces at the same
 * elevation is what made the earlier build read as a dashboard of panels instead of a
 * document with one movable layer. */
.e-card:hover{border-color:var(--accent);box-shadow:var(--shadow-md);transform:translateY(-2px)}
.e-card .bar{position:absolute;left:0;top:0;bottom:0;width:3px}
.e-card .nm{font-size:14px;font-weight:620;margin:0 0 3px;display:flex;align-items:center;gap:var(--sp-2)}
.e-card .ty{font-size:10.5px;color:var(--muted);background:var(--surface3);padding:2px 6px;border-radius:4px;font-weight:500}
.e-card .sm{color:var(--muted);font-size:11.5px;line-height:1.5;margin:5px 0 0;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}
.e-card .meta{display:flex;gap:var(--sp-2);flex-wrap:wrap;margin-top:8px;font-size:10.5px;color:var(--faint)}
.e-card .meta b{color:var(--ink2);font-weight:600}

/* ---------- chips ---------- */
.chips{display:flex;gap:var(--sp-2);flex-wrap:wrap;margin-top:7px}
.chip{font-size:10.5px;background:var(--surface3);color:var(--ink2);padding:3px 7px;border-radius:5px}
.chip.alias{background:var(--accent-soft);color:var(--accent-ink)}

/* ---------- level strip ---------- */
.level-strip{display:flex;gap:var(--sp-2);flex-wrap:wrap;margin:9px 0}
.level-card{background:var(--surface2);border:1px solid var(--line);border-radius:9px;padding:8px 11px;min-width:120px}
.level-card .ax{font-size:10.5px;color:var(--muted);display:block;margin-bottom:2px}
.level-card b{font-size:13.5px;font-weight:640;color:var(--accent-ink)}
.level-card small{display:block;color:var(--faint);font-size:10.5px;margin-top:2px}

/* ---------- timeline ---------- */
.tl{position:relative;padding:16px 0 6px;margin:8px 0}
.tl-track{position:relative;height:3px;background:var(--line2);border-radius:2px}
.tl-dot{position:absolute;top:-4px;width:11px;height:11px;border-radius:50%;background:var(--surface);border:2px solid var(--line2);transform:translateX(-50%);cursor:pointer;transition:var(--t-fast) var(--ease);padding:0}
.tl-dot:hover{transform:translateX(-50%) scale(1.45);border-color:var(--accent)}
.tl-dot.past{border-color:var(--accent);background:var(--accent-soft)}
.tl-dot.cur{border-color:var(--warn);background:var(--warn);width:13px;height:13px;top:-5px}
.tl-ends{display:flex;justify-content:space-between;font-size:10.5px;color:var(--faint);margin-top:9px;font-family:ui-monospace,monospace}

/* ---------- state table ---------- */
table.st{width:100%;border-collapse:collapse;font-size:12.5px}
table.st th{text-align:left;font-weight:600;color:var(--muted);font-size:11px;padding:7px 9px;border-bottom:1px solid var(--line2);background:var(--surface2);position:sticky;top:0}
table.st td{padding:7px 9px;border-bottom:1px solid var(--line);vertical-align:top}
table.st tr:last-child td{border-bottom:0}
table.st td.k{color:var(--muted);white-space:nowrap;width:1%}
table.st td.ch{font-family:ui-monospace,monospace;color:var(--faint);white-space:nowrap;width:1%;font-size:11px}

/* ---------- quotes / evidence ---------- */
.quote{border-left:2px solid var(--line2);padding:7px 0 7px 11px;margin:7px 0;font-size:12.5px;color:var(--ink2);line-height:1.65}
.quote small{display:block;color:var(--faint);font-size:10.5px;margin-top:3px;font-family:ui-monospace,monospace}
.ev-more{margin-top:8px}
.ev-more>summary{cursor:pointer;color:var(--accent-ink);font-size:11.5px;list-style:none}
.ev-more>summary::-webkit-details-marker{display:none}
.ev-more>summary:before{content:"▸ ";color:var(--faint)}
.ev-more[open]>summary:before{content:"▾ "}

/* ---------- trait / facet groups ---------- */
.facets{display:grid;grid-template-columns:repeat(auto-fit,minmax(268px,1fr));gap:12px}
.facet-g{background:var(--surface2);border:1px solid var(--line);border-radius:var(--radius);padding:11px 12px}
.facet-g h4{margin:0 0 8px;font-size:12.5px;font-weight:620;color:var(--ink2);display:flex;align-items:center;gap:var(--sp-2)}
.facet-g h4 .n{font:600 10.5px/1 ui-monospace,monospace;color:var(--faint);margin-left:auto}
.facet-item{padding:7px 0;border-bottom:1px dashed var(--line);font-size:12.5px;line-height:1.62}
.facet-item:last-child{border-bottom:0;padding-bottom:0}
.facet-item .st{color:var(--ink)}
.facet-item .when{color:var(--faint);font-size:10.5px;font-family:ui-monospace,monospace;margin-left:6px}

/* ---------- graph ---------- */
.graph-wrap{position:relative;height:min(86vh,940px);background:radial-gradient(circle at 50% 45%,#fff 0,#f7f8fb 58%,#eff1f5 100%);border-radius:var(--radius);overflow:hidden}
#cy{width:100%;height:100%}
/* Sector backdrop. Painting the eight wedges as filled arcs behind the nodes is what
 * turns "a disc of dots" into "eight distinguishable regions" at a glance — the boundary
 * between two sectors is otherwise invisible until you trace the colour change. Drawn in
 * an overlay SVG rather than by cytoscape so it never participates in hit-testing or
 * zooming: it is scenery, and the nodes stay the only click targets. */
#radar{position:absolute;inset:0;width:100%;height:100%;pointer-events:none;z-index:0}
/* Circle captions ride above the canvas in their own layer and are transformed to follow
 * the pan/zoom. They must not take pointer events — the node under a caption still has to
 * be clickable, and a caption that swallows the click is worse than no caption. */
.cy-overlay{position:absolute;left:0;top:0;width:100%;height:100%;pointer-events:none;z-index:2}
.cy-overlay .cc{position:absolute;display:flex;align-items:center;gap:var(--sp-2);
  padding:2px 8px;border-radius:999px;background:rgba(255,255,255,.92);
  border:1px solid var(--line);box-shadow:0 1px 2px rgba(20,28,44,.05);
  transform:translate(0,-14px);white-space:nowrap;max-width:220px}
.cy-overlay .cc-name{font-size:10.5px;font-weight:600;color:var(--ink2);overflow:hidden;
  text-overflow:ellipsis}
.cy-overlay .cc-n{font:600 9.5px/1 ui-monospace,monospace;color:var(--faint);
  background:var(--surface3);border-radius:999px;padding:2px 5px}
.cy-overlay .cc-iso{border-style:dashed;background:rgba(255,255,255,.7)}
.cy-overlay .cc-iso .cc-name{color:var(--faint)}
.cy-rings{position:absolute;left:0;top:0;width:100%;height:100%;pointer-events:none;z-index:1}
.cy-rings i{position:absolute;border-radius:50%;border:1px solid;opacity:.22}
/* A circle outside the main web is drawn with a softer ring so the giant component reads
 * as the centre of gravity and the satellites read as satellites. */
.cy-rings i.rg-sat{border-style:dotted;opacity:.16}
.cy-rings i.rg-iso{border-style:dashed;opacity:.18;border-radius:14px}
.zone-legend{position:absolute;top:14px;left:14px;z-index:3;display:flex;flex-direction:column;gap:2px;
  background:rgba(255,255,255,.9);backdrop-filter:blur(6px);border:1px solid var(--line);
  border-radius:var(--radius);padding:9px 11px;box-shadow:var(--shadow);min-width:132px}
.zone-legend .row{display:flex;align-items:center;gap:var(--sp-2);font-size:12px;color:var(--ink2);
  cursor:pointer;padding:3px 5px;border-radius:6px;transition:var(--t-fast) var(--ease)}
.zone-legend .row:hover,.zone-legend .row.lit{background:var(--surface3);color:var(--ink)}
.zone-legend .row.lit{box-shadow:inset 0 0 0 1px var(--accent-soft)}
.zone-legend .sw{width:11px;height:11px;flex:none;display:flex;align-items:center}
.zone-legend .sw svg{display:block}
.zone-legend .row b{font-variant-numeric:tabular-nums;color:var(--ink);font-weight:600}
.graph-tools{position:absolute;right:12px;top:12px;display:flex;gap:var(--sp-2);flex-direction:column}
.graph-tools button{background:rgba(255,255,255,.95);border:1px solid var(--line);border-radius:8px;padding:6px 10px;font-size:11.5px;box-shadow:var(--shadow);color:var(--ink2)}
.graph-tools button:hover{border-color:var(--accent);color:var(--accent-ink)}
/* Sector rows double as visibility switches. Hovering already lit a wedge, but there was
 * no way to *remove* the seven sectors the reader is not looking at, so a 640-node disc
 * always drew 640 nodes. The eye-off state is carried by the row itself, not by a
 * separate control, so the legend stays the only place that manages sectors. */
.zone-legend .row.off{opacity:.42}
.zone-legend .row.off .sw path,.zone-legend .row.off .sw circle{
  fill:transparent!important;stroke:var(--muted);stroke-width:1.2}
.zone-legend .eye{width:14px;text-align:center;font-size:9.5px;color:var(--faint);flex:none}
.zone-legend .row.off .eye{color:var(--muted)}
.zone-legend .row:focus-visible{outline:2px solid var(--accent);outline-offset:1px}

/* ---------- command palette ---------- */
#cmdk{position:fixed;inset:0;z-index:80;display:none;background:rgba(28,32,42,.34);
  backdrop-filter:blur(2px);padding-top:12vh}
body.cm-open #cmdk{display:block}
.cm-box{width:min(660px,92vw);margin:0 auto;background:var(--surface);border:1px solid var(--line);
  border-radius:var(--r-lg);box-shadow:0 24px 70px rgba(24,28,38,.28);overflow:hidden;
  display:flex;flex-direction:column;max-height:70vh;animation:cmpop var(--t-fast) var(--ease)}
@keyframes cmpop{from{transform:translateY(-7px);opacity:0}to{transform:none;opacity:1}}
.cm-head{display:flex;align-items:center;gap:10px;padding:13px 15px;border-bottom:1px solid var(--line)}
.cm-input{flex:1;border:none;outline:none;background:none;font:inherit;font-size:15px;color:var(--ink)}
.cm-input::placeholder{color:var(--faint)}
.cm-list{overflow:auto;padding:5px}
.cm-row{display:flex;align-items:baseline;gap:var(--sp-2);width:100%;text-align:left;border:none;background:none;
  font:inherit;padding:8px 10px;border-radius:8px;cursor:pointer;color:var(--ink2)}
.cm-row:hover{background:var(--surface3)}
.cm-row.on{background:var(--accent-soft);color:var(--accent-ink)}
.cm-ic{font-size:10px;color:var(--faint);flex:none;width:12px}
.cm-row.on .cm-ic{color:var(--accent)}
.cm-name{font-size:13.5px;font-weight:600;color:var(--ink);flex:none;max-width:52%;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.cm-row.on .cm-name{color:var(--accent-ink)}
.cm-sub{font-size:11px;color:var(--muted);background:var(--surface3);padding:2px 6px;border-radius:5px;flex:none}
.cm-meta{font-size:11px;color:var(--faint);overflow:hidden;text-overflow:ellipsis;white-space:nowrap;margin-left:auto}
.cm-empty{padding:26px 14px;text-align:center;font-size:12.5px;color:var(--muted);line-height:1.7}
.cm-foot{display:flex;align-items:center;gap:var(--sp-2);padding:9px 15px;border-top:1px solid var(--line);
  font-size:11px;color:var(--faint)}
kbd{font:inherit;font-size:10.5px;background:var(--surface3);border:1px solid var(--line);
  border-bottom-width:2px;border-radius:4px;padding:1px 5px;color:var(--ink2)}
/* Keyboard users had no idea where they were: buttons, chips, rows and cards were all
 * reachable by Tab and all drew nothing. One rule at the end of the sheet gives every
 * focusable control the same ring, without 20 selectors repeating it. */
:focus-visible{outline:2px solid var(--accent);outline-offset:2px;border-radius:5px}
button:focus-visible,[tabindex]:focus-visible,.cm-row:focus-visible{outline-offset:1px}
#cm-btn{position:fixed;left:14px;bottom:16px;z-index:36;display:inline-flex;align-items:center;gap:var(--sp-2);
  background:rgba(255,255,255,.95);backdrop-filter:blur(10px);border:1px solid var(--line);
  border-radius:10px;padding:7px 11px;font:inherit;font-size:12px;color:var(--ink2);
  box-shadow:var(--shadow-lg);cursor:pointer;transition:var(--t-fast) var(--ease)}
#cm-btn:hover{border-color:var(--accent);color:var(--accent-ink)}
#cm-btn b{font-weight:620;color:var(--ink)}
@media (max-width:1500px){#cm-btn{left:auto;right:16px}}

/* ---------- bars (rhythm) ---------- */
.bars{display:flex;flex-direction:column;gap:2px;max-height:340px;overflow:auto}
.bar-row{display:grid;grid-template-columns:88px minmax(0,1fr) 46px;gap:var(--sp-2);align-items:center;font-size:10.5px;font-family:ui-monospace,monospace;color:var(--muted)}
.bar-track{height:11px;background:var(--surface3);border-radius:3px;overflow:hidden}
.bar-fill{height:100%;background:linear-gradient(90deg,var(--accent),#8b83e8);border-radius:3px}
.bar-row.cov{grid-template-columns:112px minmax(0,1fr) 42px 62px}
.bar-row.cov>span:first-child{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.cov-fill{height:100%;border-radius:3px;display:block}
.cov-fill.ok{background:linear-gradient(90deg,#15845f,#3aa87e)}
.cov-fill.warn{background:linear-gradient(90deg,#b46a08,#d99a3a)}
.cov-fill.bad{background:linear-gradient(90deg,#b53c3c,#d46a6a)}
.cov-tally{color:var(--faint);text-align:right}

/* ---------- chapter summaries ---------- */
.cs-list{display:flex;flex-direction:column;gap:0}
.cs{padding:11px 0;border-bottom:1px solid var(--line);display:grid;grid-template-columns:66px minmax(0,1fr);gap:13px}
.cs:last-child{border-bottom:0}
.cs .cn{font:600 11px/1.5 ui-monospace,monospace;color:var(--accent-ink);background:var(--accent-soft);padding:3px 7px;border-radius:5px;text-align:center;height:fit-content}
.cs h4{margin:0 0 4px;font-size:13px;font-weight:620}
.cs p{margin:0;font-size:12.5px;color:var(--ink2);line-height:1.68}
.cs .meta{margin-top:6px;display:flex;gap:var(--sp-2);flex-wrap:wrap}

/* ---------- romance routes ---------- */
.romance-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(292px,1fr));gap:11px}
.romance-card{background:var(--surface);border:1px solid var(--line);border-radius:var(--radius-lg);padding:12px 13px;box-shadow:var(--shadow);cursor:pointer;transition:var(--t-fast) var(--ease)}
.romance-card:hover{border-color:var(--accent);box-shadow:var(--shadow-lg)}
.romance-card .nm{font-size:13.5px;font-weight:620;margin:0 0 4px;display:flex;align-items:center;gap:var(--sp-2);flex-wrap:wrap}
.romance-card .meta{color:var(--muted);font-size:11.5px}
.romance-card .ms{display:flex;flex-wrap:wrap;gap:5px;margin-top:7px}
.romance-card .ms-i{background:var(--surface3);border-radius:6px;padding:3px 7px;font-size:11px;color:var(--ink2)}
.romance-card .ms-i b{color:var(--accent-ink);font-weight:600;margin-right:4px}

/* ---------- drawer ---------- */
aside.drawer{
  position:sticky;top:74px;max-height:calc(100vh - 96px);overflow:auto;
  background:var(--surface);border:1px solid var(--line);border-radius:var(--radius-lg);
  box-shadow:var(--shadow-lg);display:none;
}
body.drawer-open aside.drawer{display:block}
.drawer-head{padding:14px 16px;border-bottom:1px solid var(--line);background:var(--surface2);position:sticky;top:0;z-index:2;border-radius:var(--radius-lg) var(--radius-lg) 0 0}
.drawer-head .row1{display:flex;align-items:flex-start;gap:10px}
.drawer-head h2{margin:0;font-size:17px;font-weight:660;letter-spacing:-.01em}
.drawer-head .kind{font-size:11px;color:var(--muted);background:var(--surface3);padding:2.5px 7px;border-radius:5px;font-weight:500;white-space:nowrap}
.drawer-head .first{font-size:11.5px;color:var(--faint);margin-top:4px;font-family:ui-monospace,monospace}
.drawer-close{margin-left:auto;background:none;border:0;color:var(--muted);font-size:19px;line-height:1;padding:0 3px}
.drawer-body{padding:15px 16px}

/* ---------- subject pages ----------
 * A page is a destination, not a peek: it replaces the stream, gets its own scroll
 * position and a real URL, and every name inside it is a link to that name's page. The
 * blocks below are the same card vocabulary the stream uses, re-declared at page scale so
 * a page reads as one document rather than a pile of unrelated panels. */
body.paged #stream{display:none}
#page{display:none}
body.paged #page{display:block}

.pg-head{margin:0 0 18px}
.pg-crumb{font-size:12px;color:var(--muted);margin-bottom:9px;display:flex;
  align-items:center;gap:var(--sp-2)}
.pg-crumb a{color:var(--muted)}
.pg-crumb a:hover{color:var(--accent-ink)}
.pg-crumb span.sep{color:var(--faint)}
.pg-title{display:flex;align-items:baseline;gap:12px;flex-wrap:wrap;
  padding-bottom:12px;border-bottom:2px solid var(--line2)}
.pg-title h1{margin:0;font-size:27px;font-weight:680;letter-spacing:-.022em;line-height:1.25}
.pg-title .n{font:600 11.5px/1 ui-monospace,monospace;color:var(--muted);
  background:var(--surface3);padding:5px 8px;border-radius:6px}
.pg-tags{display:flex;gap:var(--sp-2);flex-wrap:wrap;align-items:center}
.pg-kind{font-size:10.5px;font-weight:600;padding:3px 9px;border-radius:5px;
  color:#fff;white-space:nowrap}
.pg-sub{margin:11px 0 0;color:var(--ink2);font-size:14px;line-height:1.72;max-width:88ch}

.pg-body{display:flex;flex-direction:column;gap:16px}
.pblock{background:var(--surface);border:1px solid var(--line);
  border-radius:var(--r-lg);box-shadow:var(--shadow);overflow:hidden}
.pblock>h2{margin:0;font-size:14.5px;font-weight:640;padding:var(--sp-3) var(--sp-4);
  border-bottom:1px solid var(--line);background:var(--surface2);
  display:flex;align-items:center;gap:var(--sp-2)}
.pblock>h2 .n{font:600 11px/1 ui-monospace,monospace;color:var(--muted);
  background:var(--surface3);padding:4px 7px;border-radius:var(--r-sm)}
.pblock>h2 .hint{margin-left:auto;font-size:11.5px;color:var(--faint);font-weight:400}
.pblock>.pcards,.pblock>.ev-list,.pblock>.quotes,.pblock>.attr-grid{
  padding:var(--sp-3) var(--sp-4);display:block}
.pblock>.ev-list{padding:0}
.pblock>.pcards{padding:0}
.pblock>.pg-prose{margin:0;padding:15px 16px}
.pblock>.pg-empty{margin:0;padding:16px}
.pg-prose{color:var(--ink2);font-size:13.5px;line-height:1.78;max-width:92ch}

/* cards — a card is one grouping key (one facet, one relation type, one role slot) */
.pcards{display:grid;grid-template-columns:repeat(auto-fit,minmax(296px,1fr));gap:0}
.pcard{border-right:1px solid var(--line);border-bottom:1px solid var(--line);
  padding:13px 16px}
.pcard:last-child{border-right:0}
.pcard h3{margin:0 0 9px;font-size:12.5px;font-weight:640;color:var(--ink);
  display:flex;align-items:center;gap:var(--sp-2)}
.pcard h3 .n{font:600 10px/1 ui-monospace,monospace;color:var(--faint);
  background:var(--surface3);padding:3px 6px;border-radius:4px}
.pcard .pg-empty{padding:2px 0}

/* rows — when / who / what / detail, one line per record */
.prow{display:grid;grid-template-columns:auto minmax(0,1fr);gap:3px 10px;
  padding:6px 0;border-bottom:1px dashed var(--line);font-size:12.5px;
  line-height:1.55;align-items:baseline}
.prow:last-child{border-bottom:0}
.prow .when{font:600 10.5px/1.7 ui-monospace,monospace;color:var(--faint);
  white-space:nowrap;font-variant-numeric:tabular-nums}
.prow .what{color:var(--ink2);min-width:0;overflow-wrap:anywhere}
.prow .what b{color:var(--ink);font-weight:600}
.prow .det{grid-column:2;color:var(--muted);font-size:11.5px;line-height:1.6}
.prow .why{grid-column:2;color:var(--muted);font-size:11.5px;line-height:1.65}
.prow .why b{color:var(--ink);font-weight:600}
.prow[data-hidden="1"]{opacity:.42}
/* A chapter number that is clickable is a button, not a link: it has no text of its own
 * to underline, so it gets the chip treatment instead. */
button.chx{border:1px solid var(--line);background:var(--surface2);color:var(--muted);
  font:600 10.5px/1 ui-monospace,monospace;padding:4px 7px;border-radius:5px;
  transition:var(--t-fast) var(--ease);font-variant-numeric:tabular-nums}
button.chx:hover{border-color:var(--accent);color:var(--accent-ink);background:var(--accent-soft)}

/* links to other subjects — a name in a page is always a way to get to that subject */
.lref{color:var(--accent-ink);border-bottom:1px solid transparent;transition:var(--t-fast) var(--ease)}
.lref:hover{border-bottom-color:var(--accent)}
.lref[data-hidden="1"]{color:var(--faint);border-bottom:none}
/* A wall of names needs to wrap as a run of chips, not as a column of rows. */
.lrefs{display:flex;flex-wrap:wrap;gap:var(--sp-2) 10px;padding:4px 16px 14px}
.lrefs .lref{font-size:12.5px;padding:3px 0}

/* event rows — the same row shape, but each row is itself a link to the event page */
.ev-list{display:flex;flex-direction:column}
a.ev-row{display:grid;grid-template-columns:auto minmax(0,1fr) auto auto;gap:12px;
  align-items:baseline;padding:9px 16px;border-bottom:1px solid var(--line);
  color:var(--ink);transition:background var(--t-fast) var(--ease)}
a.ev-row:last-child{border-bottom:0}
a.ev-row:hover{background:var(--accent-soft)}
.ev-ch{font:600 10.5px/1.6 ui-monospace,monospace;color:var(--muted);
  white-space:nowrap;font-variant-numeric:tabular-nums}
.ev-t{font-size:13px;font-weight:560;min-width:0;overflow:hidden;
  text-overflow:ellipsis;white-space:nowrap}
a.ev-row:hover .ev-t{color:var(--accent-ink)}
.ev-k{font-size:10.5px;color:var(--muted);background:var(--surface3);
  padding:3px 7px;border-radius:5px;white-space:nowrap}
.ev-n{font-size:10.5px;color:var(--faint);white-space:nowrap;
  text-align:right}
/* A mention row carries names instead of a count. The names are chips, not links — the
   whole row already navigates to the event page, and a nested <a> inside an <a> is
   invalid HTML that browsers reparent unpredictably. The click handler routes them. */
.ev-mention{grid-template-columns:auto minmax(0,1fr) auto minmax(0,auto)}
.ev-who{display:flex;flex-wrap:wrap;gap:var(--sp-1);justify-content:flex-end;max-width:260px}
.ev-w{font-style:normal;font-size:10.5px;padding:1px 6px;border-radius:999px;
  background:var(--surface3);color:var(--ink2);white-space:nowrap;cursor:pointer;
  border:1px solid transparent;transition:border-color var(--t-fast) var(--ease),background var(--t-fast) var(--ease)}
.ev-w:hover{border-color:var(--accent);background:var(--accent-soft);color:var(--accent-ink)}
.ev-w-more{font-style:normal;font-size:10.5px;color:var(--faint);white-space:nowrap;
  align-self:center}
/* The literal name a mention matched on. Deliberately muted: it is provenance, not a
   headline. A shared name gets a warning tint because the same string may belong to a
   different subject entirely. */
.ev-via{font-style:normal;font-size:10px;color:var(--faint);margin-left:5px;
  padding:0 5px;border-radius:999px;background:var(--surface2);
  border:1px solid var(--line);white-space:nowrap}
.ev-via.shared{color:#9a6b00;border-color:#e6cf9a;background:#fdf6e3}
  font-variant-numeric:tabular-nums}
.ev-more{border-top:1px solid var(--line);padding:9px 16px;background:var(--surface2)}
.ev-more summary{font-size:12px;color:var(--muted);cursor:pointer}

/* quotes — one quoted span of source text, always with its chapter (never a line number) */
.quotes{display:flex;flex-direction:column;gap:var(--sp-2)}
.quotes blockquote,.quote{margin:0;padding:9px 12px;background:var(--surface2);
  border-left:3px solid var(--accent);border-radius:0 7px 7px 0;
  font-size:12.5px;line-height:1.75;color:var(--ink2)}
.quote .q-src{display:block;margin-top:5px;font:600 10.5px/1.5 ui-monospace,monospace;
  color:var(--faint)}

/* fixed attributes — genuinely time-invariant facts only, so a plain key/value grid */
.attr-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(232px,1fr));gap:0}
.attr-grid .ar{display:flex;gap:10px;align-items:baseline;padding:7px 14px;
  border-right:1px solid var(--line);border-bottom:1px solid var(--line);font-size:12.5px}
.attr-grid .ar .k{color:var(--muted);white-space:nowrap;flex:none}
.attr-grid .ar .v{color:var(--ink);font-weight:520;min-width:0;overflow-wrap:anywhere}

/* subject tags — a soft chip row, deliberately quieter than an attribute: an attribute
 * is a fact about the subject, a tag is a pointer to a theme, and giving them the same
 * weight would tell the reader they are the same kind of claim. The left dot carries the
 * accent so the row reads as a set at a glance. */
.tag-row{display:flex;flex-wrap:wrap;gap:var(--sp-2);padding:2px 0}
.tag-chip{display:inline-flex;align-items:center;gap:var(--sp-2);
  padding:5px 11px 5px 9px;border-radius:var(--r-pill);
  background:var(--surface2);border:1px solid var(--line);
  font-size:12.5px;font-weight:520;color:var(--ink2);
  transition:background var(--t-fast) var(--ease),border-color var(--t-fast) var(--ease)}
.tag-chip::before{content:"";width:6px;height:6px;border-radius:50%;
  background:var(--accent);opacity:.55;flex:none}
.tag-chip:hover{background:var(--accent-soft);border-color:var(--accent);color:var(--accent-ink)}
.tag-chip:hover::before{opacity:1}

/* index pages — grouped by kind, because a flat grid of 113 places is a wall, not
 * an index. Each group is a row of cards under its own heading. */
.ix-wrap{display:grid;grid-template-columns:minmax(0,1fr) 186px;gap:22px;align-items:start}
@media (max-width:1180px){.ix-wrap{grid-template-columns:minmax(0,1fr)}
  .ix-jump{display:none}}
.ix-group{margin:0 0 24px}
.ix-group:last-child{margin-bottom:0}
.ix-gh{display:flex;align-items:baseline;gap:var(--sp-2);margin:0 0 9px;
  padding:7px 0 6px;border-bottom:1px solid var(--line);
  position:sticky;top:0;z-index:2;background:var(--bg);
  box-shadow:0 1px 0 0 var(--line)}
.ix-gh h2{margin:0;font-size:14px;font-weight:660;letter-spacing:-.01em;color:var(--ink)}
.ix-gh .n{font:600 10.5px/1 ui-monospace,monospace;color:var(--muted);
  background:var(--surface3);padding:3px 6px;border-radius:5px}
.ix-gh .why{margin-left:auto;font-size:11px;color:var(--faint)}
.ix-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(238px,1fr));gap:var(--sp-2)}
.ix-card{display:block;background:var(--surface);border:1px solid var(--line);
  border-radius:var(--radius);padding:10px 12px;box-shadow:var(--shadow);
  transition:var(--t-fast) var(--ease);border-left-width:3px}
.ix-card:hover{transform:translateY(-1px);box-shadow:var(--shadow-lg);
  border-color:var(--accent)}
.ix-card .nm{font-size:13px;font-weight:620;color:var(--ink);display:block;
  overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.ix-card .sb{font-size:11.5px;color:var(--muted);margin-top:3px;display:block;
  overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.ix-card .sm{font-size:11.5px;color:var(--muted);margin-top:4px;line-height:1.5;
  display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}
.ix-card .mt{font:600 10.5px/1.5 ui-monospace,monospace;color:var(--faint);
  margin-top:5px;display:flex;gap:var(--sp-2);font-variant-numeric:tabular-nums}
/* Chapters and events are far too numerous for one card each — 999 and 1159 rows carrying
   one number and one title. A line is the right shape: the reader already knows which
   chapter they want, so the list has to be scannable by number, not browsable by box. */
.ix-lines{display:flex;flex-direction:column;gap:1px}
.ix-line{display:flex;align-items:baseline;gap:10px;padding:5px 9px;border-radius:6px;
  border:1px solid transparent;font-size:12.5px;color:var(--ink2);text-decoration:none}
.ix-line:hover{background:var(--surface3);border-color:var(--line);color:var(--ink)}
.ix-line .ln{flex:none;min-width:70px;font:600 11px/1.5 ui-monospace,monospace;
  color:var(--accent-ink);font-variant-numeric:tabular-nums}
.ix-line .lt{flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.ix-line .lm{flex:none;font:600 10.5px/1.5 ui-monospace,monospace;color:var(--faint)}
.ix-note{font-size:12px;color:var(--muted);line-height:1.6;margin:0 0 14px;
  padding:9px 12px;background:var(--surface2);border:1px solid var(--line);border-radius:8px}
/* Feedback for a rail row. A rail row asks the window to scroll to the block it names, and
   a page shorter than the viewport cannot scroll at all — `#/chapter/251` measures
   `scrollHeight === innerHeight`, so all three of its rows were physically unable to move
   anything and read as dead. Flashing the block is the honest answer: it says the click
   landed, and on a long page it also marks where the viewport came to rest. */
.rail-flash{animation:railflash 1.2s ease-out}
@keyframes railflash{
  0%{box-shadow:0 0 0 3px var(--accent);background:var(--accent-soft)}
  60%{box-shadow:0 0 0 6px rgba(97,87,216,0);background:var(--accent-soft)}
  100%{box-shadow:0 0 0 0 rgba(97,87,216,0);background:transparent}
}
/* Chapter navigation. Reading a book is a walk, so the walk needs a next step inside the page:
   the sidebar's 20-cell chapter grid gets the reader to a neighbourhood, not to the chapter
   after this one. */
.ch-nav{display:flex;gap:var(--sp-2);align-items:center;flex-wrap:wrap}
/* `.sbtn` is styled under `.side-acts` only, so the chapter nav has to carry its own copy —
   borrowing the class without the rules would have produced three unstyled words. */
.ch-nav .sbtn{display:inline-block;font-size:11.5px;font-weight:600;line-height:1.5;
  color:var(--muted);padding:6px 10px;border-radius:7px;background:var(--surface);
  border:1px solid var(--line);cursor:pointer;text-align:center;transition:var(--t-fast) var(--ease);
  font-family:inherit;white-space:nowrap;text-decoration:none}
.ch-nav .sbtn:hover{color:var(--accent-ink);border-color:var(--accent);background:var(--accent-soft)}
/* the jump list — the sidebar of the index page. 8 groups is too many to scroll
   past when you came for one of them. */
.ix-jump{position:sticky;top:70px;font-size:12px}
.ix-jump .jh{font:600 9.5px/1.4 ui-monospace,monospace;color:var(--faint);
  letter-spacing:.08em;text-transform:uppercase;margin:0 0 7px}
.ix-jump a{display:flex;align-items:baseline;gap:var(--sp-2);padding:4px 7px;border-radius:6px;
  color:var(--muted);text-decoration:none}
.ix-jump a:hover{background:var(--accent-soft);color:var(--accent-ink)}
.ix-jump a b{margin-left:auto;font:600 10px/1 ui-monospace,monospace;color:var(--faint);
  font-variant-numeric:tabular-nums}

/* embedded full record — the drawer body reused inline, so the two cannot disagree */
.embed{padding:15px 16px}
.embed>:first-child{margin-top:0}

/* the subject's own mind map, on its page */
.pg-graph{padding:0;border-bottom:1px solid var(--line)}
.pg-graph #pg-cy{height:min(72vh,620px);width:100%}
.pg-graph .mini{padding:9px 16px;border-top:1px solid var(--line);background:var(--surface2)}

/* page footer navigation */
.pg-nav{display:flex;gap:var(--sp-2);flex-wrap:wrap;padding-top:2px}
.pg-nav .pnav{font-size:12.5px;padding:8px 14px;border-radius:8px;
  background:var(--surface);border:1px solid var(--line);color:var(--ink2);
  transition:var(--t-fast) var(--ease);box-shadow:var(--shadow)}
.pg-nav .pnav:hover{border-color:var(--accent);color:var(--accent-ink);
  background:var(--accent-soft)}
.pg-empty{color:var(--faint);font-size:12.5px;line-height:1.75}
.pg-missing{background:var(--surface);border:1px solid var(--line);
  border-radius:var(--radius-lg);padding:26px;text-align:center;color:var(--muted);
  box-shadow:var(--shadow)}
.pg-missing code{font-size:11.5px;background:var(--surface3);padding:2px 6px;
  border-radius:5px;font-family:ui-monospace,monospace;color:var(--ink2)}

/* ---------- graph view switch ----------
 * Four layouts answer four different questions about the same edges: sector = what kinds
 * of things exist and how the kinds connect, mind = what is near this subject, flow = in
 * what order things moved or advanced, tree = who belongs to whom. The switch sits in the
 * block header next to the other graph actions. */
.gmodes{display:inline-flex;background:var(--surface3);border-radius:8px;padding:2px;gap:2px}
button.gmode{border:none;background:none;font-size:11.5px;color:var(--muted);
  padding:5px 11px;border-radius:6px;transition:var(--t-fast) var(--ease);white-space:nowrap}
button.gmode:hover{color:var(--ink);background:rgba(255,255,255,.7)}
button.gmode[aria-pressed="true"]{background:var(--surface);color:var(--accent-ink);
  font-weight:620;box-shadow:var(--shadow)}

/* tier tree — an indented outline rather than drawn boxes: 195 `member_of` edges cannot
 * be laid out as nested rectangles at any readable scale, but they read fine as an
 * outline, and an outline stays searchable and selectable. */
.tree{display:flex;flex-direction:column}
.trow{display:flex;align-items:baseline;gap:var(--sp-2);padding:4px 16px 4px calc(16px + var(--d,0)*19px);
  font-size:12.5px;border-bottom:1px solid var(--surface3)}
.trow:hover{background:var(--surface2)}
.trow .tw{font:600 10px/1.6 ui-monospace,monospace;color:var(--faint);flex:none;
  white-space:nowrap;font-variant-numeric:tabular-nums}
.trow .tnode{min-width:0}
.trow .tty{font-size:10px;color:var(--faint);background:var(--surface3);
  padding:2px 6px;border-radius:4px;white-space:nowrap;flex:none}
.trow .trel{font-size:10.5px;color:var(--muted);white-space:nowrap;flex:none}
.trow .tn{font:600 10px/1 ui-monospace,monospace;color:var(--faint);flex:none;
  margin-left:auto;font-variant-numeric:tabular-nums}
.trow.miss .tnode{color:var(--faint)}
.trow .tk{font-size:10.5px;color:var(--muted);background:var(--surface3);
  padding:2px 6px;border-radius:4px;white-space:nowrap;margin-left:auto;flex:none}

/* ---------- misc ---------- */
.empty{color:var(--faint);font-size:12.5px;padding:15px;text-align:center;background:var(--surface2);border-radius:var(--radius);line-height:1.75}
.empty b{display:block;color:var(--ink2);margin-bottom:3px;font-weight:600}
.empty code{font-size:11px;background:var(--surface3);padding:1px 5px;border-radius:4px;font-family:ui-monospace,monospace;color:var(--ink2)}
.tag{font-size:10.5px;padding:2.5px 7px;border-radius:5px;background:var(--surface3);color:var(--ink2);white-space:nowrap}
.tag.ok{background:var(--good-soft);color:var(--good)}
.tag.warn{background:var(--warn-soft);color:var(--warn)}
.tag.bad{background:var(--danger-soft);color:var(--danger)}
.tag.acc{background:var(--accent-soft);color:var(--accent-ink)}
.cols2{display:grid;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));gap:16px}
.mini{font-size:11.5px;color:var(--muted);line-height:1.6}

/* ---- folded lists ----------------------------------------------------------------
 * A fold is the difference between "there are 1043 of these and you get 40" and "there
 * are 1043 of these, here are 40, the rest are one click away". The button is styled as
 * a small control rather than a link so it does not read like another row of data. */
.fold-ctl{margin:8px 0 2px}
.fold-btn{font:500 11.5px/1 inherit;color:var(--accent-ink);background:var(--accent-soft);
  border:1px solid transparent;border-radius:7px;padding:7px 11px;cursor:pointer;
  transition:var(--t-fast) var(--ease);font-family:inherit}
.fold-btn:hover{background:var(--surface);border-color:var(--accent)}
.fold-btn::before{content:"▾";display:inline-block;margin-right:5px;font-size:9px;
  transition:transform var(--t-fast) var(--ease) ease}
.fold-btn[aria-expanded="true"]::before{transform:rotate(180deg)}
.fold-rest{margin-top:6px}

/* ---- page table of contents ------------------------------------------------------
 * The protagonist's page is ~97k characters. Anchors let a reader jump to the part they
 * came for instead of scrolling through everything they did not. Sticky so it stays
 * reachable on a page this long. */
.page-toc{position:sticky;top:8px;z-index:5;display:flex;flex-wrap:wrap;gap:var(--sp-1);
  padding:9px 11px;margin:0 0 14px;background:var(--surface);
  border:1px solid var(--line);border-radius:10px;
  box-shadow:0 1px 2px rgba(20,28,44,.04)}
.page-toc a{font-size:11.5px;color:var(--muted);padding:5px 9px;border-radius:6px;
  border:1px solid transparent;transition:var(--t-fast) var(--ease);white-space:nowrap}
.page-toc a:hover{color:var(--accent-ink);background:var(--accent-soft);border-color:var(--accent)}
.page-toc a b{font:600 9.5px/1 ui-monospace,monospace;margin-left:5px;color:var(--faint);
  font-variant-numeric:tabular-nums}
.page-toc a:hover b{color:var(--accent-ink)}
.page-toc a.on{background:var(--accent-soft);border-color:var(--accent);color:var(--accent-ink)}
h3.sub{font-size:13px;font-weight:620;margin:16px 0 8px;color:var(--ink2)}
h3.sub:first-child{margin-top:0}
.rel-line{display:flex;align-items:baseline;gap:var(--sp-2);padding:6px 0;border-bottom:1px dashed var(--line);font-size:12.5px;flex-wrap:wrap}
.rel-line:last-child{border-bottom:0}
.rel-line .rt{color:var(--ink2);font-weight:560}
.rel-line .span{color:var(--faint);font-size:10.5px;font-family:ui-monospace,monospace;margin-left:auto}
.milestone-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(132px,1fr));gap:var(--sp-2);margin-top:9px}
.milestone{background:var(--surface2);border:1px solid var(--line);border-radius:8px;padding:8px 10px}
.milestone .k{font-size:10.5px;color:var(--muted);display:block}
.milestone .v{font-size:12.5px;font-weight:600;color:var(--accent-ink);margin-top:2px}

/* ---------- utility spacing (no inline styles in generated markup) ---------- */
.mt4{margin-top:4px}.mt6{margin-top:6px}.mt8{margin-top:8px}
.fb100{flex-basis:100%}
#stream>.sec{display:block}
#stream>.sec:empty{display:none}
.more-row{display:flex;justify-content:center;padding:12px 0 2px}
.more-row .chip{border:1px solid var(--line2);background:var(--surface);padding:6px 14px;font-size:12px}
.more-row .chip:hover{border-color:var(--accent);color:var(--accent-ink)}
.find{border:1px solid var(--line);border-radius:7px;padding:5px 9px;font-size:12px;width:200px;margin-left:auto}
.e-card.sel{border-color:var(--accent);box-shadow:0 0 0 2px var(--accent-soft),var(--shadow-lg)}
.chip.on{background:var(--accent-soft);color:var(--accent-ink);font-weight:600}

/* ---------- filter chips + pager ----------
 * Every long list on the page is now: filter row, one page of rows, pager. The three share
 * one visual grammar so that a reader who has learned it in one block reads every other
 * block for free. Chips carry their own count so the cost of a filter is visible before
 * it is applied. */
.fchips{display:flex;gap:var(--sp-2);flex-wrap:wrap;align-items:center}
.fbrow{display:flex;gap:var(--sp-2);align-items:center;padding:11px 16px 2px;flex-wrap:wrap}
.fbrow .fchips{margin-right:auto}
.fchip{display:inline-flex;align-items:baseline;gap:5px;font-size:11.5px;line-height:1;
  border:1px solid var(--line);background:var(--surface);color:var(--ink2);
  padding:5px 9px;border-radius:999px;cursor:pointer;transition:background var(--t-fast) var(--ease),border-color var(--t-fast) var(--ease),color var(--t-fast) var(--ease)}
.fchip:hover{border-color:var(--accent);color:var(--accent-ink)}
.fchip.on{background:var(--accent-soft);border-color:var(--accent-soft);color:var(--accent-ink);font-weight:620}
.fchip i{font-style:normal;font-size:9.5px;font-weight:600;color:var(--muted);
  background:var(--surface3);padding:2px 4px;border-radius:4px;min-width:12px;text-align:center}
.fchip.on i{background:rgba(255,255,255,.72);color:var(--accent-ink)}

.pager{display:flex;align-items:center;gap:12px;flex-wrap:wrap;
  padding:12px 16px 14px;border-top:1px solid var(--line);margin-top:12px}
.pg-info{font-size:11.5px;color:var(--muted);font-variant-numeric:tabular-nums;margin-right:auto}
.pg-btns{display:flex;gap:var(--sp-1);align-items:center}
.pg{min-width:28px;height:28px;padding:0 8px;border:1px solid var(--line);background:var(--surface);
  color:var(--ink2);font-size:11.5px;border-radius:6px;cursor:pointer;
  font-variant-numeric:tabular-nums;transition:background var(--t-fast) var(--ease),border-color var(--t-fast) var(--ease),color var(--t-fast) var(--ease)}
.pg:hover:not(:disabled){border-color:var(--accent);color:var(--accent-ink);background:var(--surface2)}
.pg.on{background:var(--accent);border-color:var(--accent);color:#fff;font-weight:620}
.pg:disabled{opacity:.38;cursor:default}
.pg-jump{width:62px;border:1px solid var(--line);border-radius:6px;padding:5px 8px;
  font-size:11.5px;text-align:center;color:var(--ink2)}
.pg-jump:focus{outline:none;border-color:var(--accent);box-shadow:0 0 0 2px var(--accent-soft)}

/* ---------- in-drawer navigation ----------
 * The drawer is a reading surface with a history, so it shows a back affordance and the
 * name of where you came from. Without the trail, a reader three hops into a relation
 * chain has no idea the first panel is still behind them. */
.dnav{display:flex;align-items:center;gap:var(--sp-2);padding:0 0 10px;margin-bottom:10px;
  border-bottom:1px dashed var(--line)}
.dback{border:1px solid var(--line);background:var(--surface);color:var(--ink2);
  font-size:11.5px;padding:4px 10px;border-radius:6px;cursor:pointer;transition:var(--t-fast) var(--ease)}
.dback:hover{border-color:var(--accent);color:var(--accent-ink);background:var(--accent-soft)}
.dtrail{font-size:11.5px;color:var(--muted)}
.dtrail b{color:var(--ink2);font-weight:620}
/* an inline cross-reference: looks like a link, behaves like a push */
.xlink{border:none;background:none;padding:0;font:inherit;color:var(--accent-ink);
  border-bottom:1px solid var(--accent-soft);cursor:pointer;transition:var(--t-fast) var(--ease)}
.xlink:hover{border-bottom-color:var(--accent-ink)}
"""


def esc(value: Any) -> str:
    return html.escape("" if value is None else str(value))


# ---------------------------------------------------------------------------
# HTML shell
#
# Structure, top to bottom:
#   header  — title + the one chapter scrub that every block reads
#   tier 1  — the book (stat strip, chapter stream, rhythm, coverage)
#   tier 2  — the agents (zone map, character library, per-entity drill-down)
#   tier 3  — the things (items / skills / concepts with custody timelines)
#   drawer  — the single detail surface, opened by any click
# ---------------------------------------------------------------------------
TEMPLATE = r"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>__TITLE__ · 知识图谱图鉴</title>
<link rel="icon" href="data:,">
<style>__CSS__</style>
</head>
<body>
<header class="top">
  <div class="top-inner">
    <div class="brand">
      <h1>__TITLE__</h1>
      <span class="sub">第 <span id="c-start"></span>–<span id="c-end"></span> 章 · 分层知识图谱</span>
    </div>
    <div class="scrub">
      <label for="ch">回放到第</label>
      <input type="range" id="ch" min="__C_START__" max="__C_END__" value="__C_END__" step="1">
      <span class="chapter-badge" id="ch-badge">第 __C_END__ 章</span>
      <span class="snap-note" id="ch-note"></span>
    </div>
  </div>
</header>

<div class="shell">
<aside id="side" aria-label="浏览">
  <div class="side-search">
    <input type="search" id="side-q" placeholder="搜人物 / 地点 / 物品 / 剧情…" autocomplete="off"
           aria-label="全库检索">
    <span class="side-kbd">/</span>
  </div>
  <div class="side-scroll">
    <div id="side-tree"></div>
    <nav id="rail" aria-label="区块导航"></nav>
  </div>
</aside>
<main id="main">
  <div id="page"></div>
  <div id="stream"></div>
</main>
<aside class="drawer" id="drawer" aria-live="polite"></aside>
</div>

<button id="cm-btn" aria-label="打开全局检索"><b>检索</b><kbd>/</kbd></button>
<div id="cmdk"></div>

<script>__READER_PROSE_JS__</script>
<script>__CYTOSCAPE__</script>
<script>
__APP__
</script>
</body>
</html>
"""


def build_html(model: dict[str, Any]) -> str:
    """Inline the model, the reader-prose sanitiser and Cytoscape into one file."""
    from reader_prose import to_js as reader_prose_js_source

    asset = Path(__file__).resolve().parent.parent / "assets" / "cytoscape-3.34.3.min.js"
    if not asset.is_file():
        raise FileNotFoundError(f"bundled Cytoscape.js asset not found: {asset}")
    cytoscape_js = asset.read_text(encoding="utf-8").replace("</script>", "<\\/script>")

    meta = model["graph"]["metadata"]
    payload = json.dumps(model, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    app = APP_JS.replace("__PAYLOAD__", payload)

    return (
        TEMPLATE.replace("__CSS__", CSS)
        .replace("__TITLE__", esc(meta.get("title") or "小说知识图谱"))
        .replace("__C_START__", str(meta.get("chapter_start") or 1))
        .replace("__C_END__", str(meta.get("chapter_end") or 1))
        .replace("__READER_PROSE_JS__", reader_prose_js_source())
        .replace("__CYTOSCAPE__", cytoscape_js)
        .replace("__APP__", app)
    )


APP_JS = r"""
"use strict";
/* ------------------------------------------------------------------ *
 * model
 * ------------------------------------------------------------------ */
const M = __PAYLOAD__;
const G = M.graph;
/* Handles for the acceptance harness. A classic script's top-level `const` is a script
 * binding, not a `window` property, so a probe that reads `window.G` gets `undefined` and
 * a check built on it silently measures nothing. Exposing them here is the difference
 * between a check that can fail and one that can only look like it passed. */
window.G = G;
window.ENT = null;   /* filled in once the entity index is built */
const V = M.views || {};
const L = M.layout || {positions:{},zones:{},present:[]};
const LAY = M.layers || {};
const C = M.counts || {};
/* Same reason as `window.G`: a probe needs a handle to the layout, and in particular to
 * the circles, or a check on the circle view can only ever measure `undefined`. */
window.L = L;
window.M = M;

const MIN_CH = G.metadata.chapter_start || 1;
const MAX_CH = G.metadata.chapter_end || 1;
const PRO = new Set((M.metadata && M.metadata.protagonists) || []);
const TODAY = Math.max(G.metadata.chapter_end || 1, MIN_CH);

const A = x => Array.isArray(x) ? x : (x == null ? [] : [x]);
const N = x => (typeof x === "number" && isFinite(x) ? x : null);
const clamp = c => Math.max(MIN_CH, Math.min(MAX_CH, c|0));
const esc = s => String(s == null ? "" : s).replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
/* Analyst-facing prose carries merge bookkeeping ("请主 Agent 合并", "本分片…") and
 * bare record IDs. The sanitiser is generated from reader_prose.py so the page and
 * AI_CONTEXT.md cannot disagree about what is safe to print.
 *
 * reader_prose deliberately keeps *resolvable* IDs (`char_yang_li`) because a
 * renderer can turn them into real names — only fragment-local ones are deleted.
 * This page must therefore do that resolution itself, or the raw ID reaches the
 * reader. `prose()` is the single entry point: resolve IDs to names, then sanitise. */
const ID_RE = /\b(?:char|concept|item|skill|location|org|creature|event|rel|sc|fs|ri|ev|axis|rom|rr|lcv|ia|level)_[a-z0-9]+(?:_[a-z0-9]+)*\b/g;
function resolveIds(text){
  return String(text == null ? "" : text).replace(ID_RE, (m) => {
    const e = ENT.get(m);
    return e && e.name ? e.name : m;
  });
}
const prose = s => {
  const t = resolveIds(s);
  return typeof cleanReaderProse === "function" ? cleanReaderProse(t) : t;
};
/* An issue's `description` cites the ids it reconciled against — 「旧表记方雯（char_fang_wen）
 * 首见第 11 章…」. `resolveIds()` substitutes an id it knows and leaves one it does not, which is
 * right for prose but wrong here: MEASURED, five of the ids cited in `review_issues` no longer
 * exist in the graph at all (`item_xiewang_jian`, `item_huazhuang_he`, `char_ding_lei`,
 * `item_chuangguo_yuoxi`, `org_jinxing_baoan`) — they are precisely the ids the audit could not
 * place, which is *why* the issue was filed. So the reader got `（char_ding_lei）` printed into a
 * Chinese sentence. This workspace's rule is that no internal structure key reaches the reader.
 *
 * The order matters: resolve first, so a citation whose entity still exists collapses into the
 * name already sitting in front of it (「方雯（char_fang_wen）」 -> 「方雯」) instead of becoming
 * 「方雯（方雯）」. Only then are the dead ones dropped. An id is a fact about the extraction, not
 * about the story — dropping the citation keeps the sentence. */
function issueText(s){
  /* The id pattern, and a list of them. One issue cites 「金刚经（item_jingang_jing/
   * skill_jingang_jing/axis_jingangjing）」 — three ids for one name — so a rule that expects a
   * single id before the closing bracket leaves `（//）` behind. */
  const ID = "[a-z][a-z0-9]*(?:_[a-z0-9]+)+";
  const LIST = ID + "(?:\\s*[/、,，]\\s*" + ID + ")*";
  const t = String(s == null ? "" : s)
    .replace(new RegExp("([^\\s（()）]{1,24})\\s*[（(]\\s*" + LIST + "\\s*[)）]", "g"), "$1")
    .replace(new RegExp("\\s*[（(]\\s*" + LIST + "\\s*[)）]", "g"), "")
    .replace(new RegExp("\\b" + ID + "\\b", "g"), "")
    .replace(/\s{2,}/g, " ")
    .replace(/\s+([，。、；：！？）])/g, "$1")
    .trim();
  return typeof cleanReaderProse === "function" ? cleanReaderProse(t) : t;
}

function term(group, key, fallback){
  const g = (G._display_vocabulary || {})[group];
  if (g && typeof g === "object" && key != null && g[key] != null) return g[key];
  if (key == null || key === "") return (G._display_vocabulary && G._display_vocabulary.fallback) || fallback || "未分类";
  return fallback || String(key);
}
const ETYPE  = t => term("entity_types", t, t);
const RELT   = t => term("relations", t, t);
const FACET  = f => term("facets", f, f);
const ACT    = a => term("actions", a, a);
const CONF   = c => term("confidences", c, c);
const ESTAT  = s => term("relation_statuses", s, s);
const RS     = s => term("romance_statuses", s, s);
const RIB    = s => term("romance_inclusion_bases", s, s);
const CC     = s => term("consent_contexts", s, s);
const FSSTAT = s => term("foreshadow_statuses", s, s);
const EVT    = t => term("event_types", t, t);
const IAT    = t => term("intimacy_act_types", t, t);
const CITEM  = k => term("issue_categories", k, k);
const ISEV   = k => term("issue_severities", k, k);
const AK     = k => term("attribute_keys", k, k);
/* `e.tags` is free-ish text: the extractor mixes Chinese subject tags (「黑龙会」「反派」)
 * with English enums (`protagonist`, `minor`) and, in one case, a romanisation of a name
 * (`mokuui` for 墨非烟). Reader-facing means translated-and-shown, not hidden, so this
 * returns the vocabulary entry when there is one and the raw tag otherwise — the same
 * contract every other `term()` call site uses.
 *
 * The fallback matters here more than elsewhere: tags are the one entity field with no
 * controlled vocabulary upstream, so an unknown tag is normal, not a bug. Printing it
 * verbatim is the honest behaviour; the vocabulary is what keeps the known English ones
 * from reaching the reader as English. */
const TAGV   = t => term("entity_tags", t, t);

/* ------------------------------------------------------------------ *
 * indexes (built once; the chapter scrub only re-projects them)
 * ------------------------------------------------------------------ */
const ENT = new Map();
const TRAITS = new Map(), CHANGES = new Map(), BY_TARGET = new Map();
const RELS = new Map(), ROLES = new Map(), EVENTS = new Map();
const EVID = new Map(), FSH = new Map(), COMM = new Map(), IACTS = new Map();
/* entity_id -> [event, ...] for events whose TEXT names the entity without listing it as a
 * participant. Kept apart from EVENTS on purpose — see `eventsMentioning()`. */
const MENTIONS = new Map();
/* Parallel to MENTIONS: how each mention matched — the literal name, whether that name is
 * shared by several entities, and whether it is the entity's primary name. The page needs
 * this to say「以别名 X 匹配」而不是当成确定事实。 */
const MENTION_HOW = new Map();
/* Bare titles are not names. MEASURED: 姬媛媛 carried 「长老」 as an alias, so all 15
 * events containing the word 长老 credited her — including 长老龙子羽, which is someone
 * else. A title has no referent on its own, and matching on one manufactures evidence.
 * The span rule cannot catch it: 长老龙子羽 IS claimed by the longer name 龙子羽, but a
 * standalone 长老 is unclaimed and matches anyway. */
const TITLE_WORDS = new Set([
  "长老", "掌门", "大师", "前辈", "大人", "子爵", "侯爵", "伯爵", "先生", "女士",
  "小姐", "夫人", "老板", "主任", "队长", "组长", "师父", "师叔", "师尊", "师祖",
  "门主", "族长", "家主", "陛下", "殿下", "阁下", "属下", "弟子", "师兄", "师姐",
  "师弟", "师妹", "老太爷", "老爷子", "老头", "少女", "青年", "男爵", "公爵",
]);
const SUMMARY = new Map(), ROUTE = new Map();
const CHILD_OF = new Map();   /* child -> parent, for the collapsible library */
/* Relation degree per entity, module scope so the graph ranking, the library sort and
 * the palette's tie-break all read the same number. It was a local inside
 * `graphElements()`, which meant the two features added later reached for a name that
 * did not exist outside that function — `DEG is not defined` aborted the palette before
 * it could paint. */
const DEG = new Map();

function push(m, k, v){ if(!m.has(k)) m.set(k, []); m.get(k).push(v); }

(function buildIndexes(){
  for (const e of A(G.entities)){ if (e && e.id) ENT.set(e.id, e); }
  window.ENT = ENT;
  for (const t of A(G.character_traits)) if (t && t.entity_id) push(TRAITS, t.entity_id, t);
  for (const s of A(G.state_changes)){
    if (!s) continue;
    if (s.entity_id) push(CHANGES, s.entity_id, s);
    if (s.target_id) push(BY_TARGET, s.target_id, s);
  }
  for (const r of A(G.relations)){ if(!r) continue; if (r.source_id) push(RELS, r.source_id, r); if (r.target_id) push(RELS, r.target_id, r); }
  /* Degree counts every relation the graph records, not only the ones live at the
   * current chapter — it is a property of the entity, and a hub that has not debuted yet
   * still deserves a high tie-break when its name is searched. */
  for (const r of A(G.relations)){
    if (!r) continue;
    if (r.source_id) DEG.set(r.source_id, (DEG.get(r.source_id) || 0) + 1);
    if (r.target_id) DEG.set(r.target_id, (DEG.get(r.target_id) || 0) + 1);
  }
  for (const r of A(G.item_roles)) if (r && r.item_id) push(ROLES, r.item_id, r);
  for (const e of A(G.events)){ if(!e) continue; push(EVENTS, "ch" + e.chapter, e); }
  for (const e of A(G.evidence)) if (e && e.id) EVID.set(e.id, e);
  for (const f of A(G.foreshadowing)){ if(!f) continue; for (const id of A(f.related_entity_ids)) push(FSH, id, f); }
  for (const c of A(G.commitments)){ if(!c) continue; for (const id of A(c.promisor_ids).concat(A(c.counterparty_ids))) push(COMM, id, c); }
  for (const a of A(G.intimate_acts)){ if(!a) continue; for (const id of A(a.initiator_ids).concat(A(a.recipient_ids))) push(IACTS, id, a); }
  for (const s of A(G.chapter_summaries)) if (s && N(s.chapter) != null) SUMMARY.set(s.chapter, s);
  for (const r of A(G.romance_routes)) if (r && r.id) ROUTE.set(r.id, r);

  /* Body-mention index: per-occurrence span claiming.
   *
   * The first version sorted the name list longest-first and then did `txt.includes(nm)`
   * for each name independently. The sort was decorative — it changed the checking ORDER
   * but each name still staked its claim alone, so 秦朝 was recorded as a mention on every
   * event that merely contained 秦朝家 or 秦朝的母亲, two names owned by other entities.
   * MEASURED on a 30-match hand-read sample: 25 correct, 3 plainly wrong, and the
   * wrongness was invisible because a substring hit and a real hit print identically.
   *
   * Now a name only counts an occurrence no LONGER name has already claimed. 秦朝家 eats
   * the span inside 秦朝家; a standalone 秦朝 still counts. The ambiguity is positional,
   * not global — an earlier attempt banned every name that is a substring of another and
   * cost 秦朝 all 33 of its matches to fix 3 bad ones.
   *
   * Names below two characters are skipped: a single character is a substring of too much
   * ordinary prose to be evidence of anything. */
  {
    const nameIndex = [];
    const nameOwners = new Map();      /* name -> Set(entity_id) */
    const nameIsMain = new Map();      /* name -> Set(entity_id that has it as `name`) */
    for (const e of A(G.entities)){
      if (!e || !e.id) continue;
      for (const raw of [e.name].concat(A(e.aliases))){
        if (typeof raw !== "string") continue;
        const s = raw.trim();
        if (s.length < 2) continue;
        if (TITLE_WORDS.has(s)) continue;
        if (!nameOwners.has(s)) nameOwners.set(s, new Set());
        nameOwners.get(s).add(e.id);
        if (s === (e.name || "").trim()){
          if (!nameIsMain.has(s)) nameIsMain.set(s, new Set());
          nameIsMain.get(s).add(e.id);
        }
        nameIndex.push(s);
      }
    }
    const uniq = [...new Set(nameIndex)].sort((a, b) => b.length - a.length);
    window.__nameOwners = nameOwners;
    window.__nameIsMain = nameIsMain;

    for (const ev of A(G.events)){
      if (!ev || !ev.id) continue;
      const txt = String(ev.title || "") + " " + String(ev.description || "");
      if (!txt.trim()) continue;
      const party = new Set(A(ev.participant_ids));
      const claimed = [];              /* [start, end] spans already taken */
      const hit = new Map();           /* entity_id -> name that matched it */
      for (const nm of uniq){
        let from = 0;
        for (;;){
          const k = txt.indexOf(nm, from);
          if (k < 0) break;
          const end = k + nm.length;
          /* inside an already-claimed span? then this occurrence belongs to the longer name */
          const covered = claimed.some(([s2, e2]) => k >= s2 && end <= e2);
          if (!covered){
            claimed.push([k, end]);
            for (const id of nameOwners.get(nm)){
              /* Prefer the entity that carries the name as its PRIMARY name. A hit via an
               * alias is kept only when no primary holder exists, because a title-alias
               * like 「长老」 attached to 姬媛媛 was matching prose about 长老龙子羽. */
              const prev = hit.get(id);
              const better = prev == null || (nameIsMain.has(nm) && !nameIsMain.has(prev));
              if (!prev || better) hit.set(id, nm);
            }
          }
          from = k + 1;
        }
      }
      for (const [id, nm] of hit){
        if (party.has(id)) continue;
        push(MENTIONS, id, ev);
        /* Record WHICH name matched and whether that name is shared, so the page can say
         * so. The text genuinely names the string; the defect was presenting a
         * possibly-shared string as a settled per-entity fact. */
        push(MENTION_HOW, id, { ev: ev.id, name: nm, shared: (nameOwners.get(nm) || new Set()).size > 1,
                                primary: nameIsMain.has(nm) });
      }
    }
  }
  /* the book nests: an organization owns characters, a character owns skills and
   * items. Derive that parent link once so the library can be collapsed. */
  for (const r of A(G.relations)){
    if (!r || r.status === "ended") continue;
    const p = r.source_id, c = r.target_id;
    if (!ENT.has(p) || !ENT.has(c)) continue;
    const pt = (ENT.get(p) || {}).type, ct = (ENT.get(c) || {}).type;
    if (["member_of","subsidiary_of","owns","leader_of","parent_of"].includes(r.relation_type) && (pt === "organization" || ct === "organization")){
      const org = pt === "organization" ? p : c, kid = pt === "organization" ? c : p;
      if (!CHILD_OF.has(kid)) CHILD_OF.set(kid, org);
    }
  }
})();

/* ------------------------------------------------------------------ *
 * as-of projection
 * ------------------------------------------------------------------ */
const S = { chapter: MAX_CH, sel: null, selKind: null, zone: null, graphStrict: true };

const appears = (e, c) => N(e && e.first_chapter) == null || e.first_chapter <= c;
function anySpan(span, c, fromKey, toKey){
  const from = N(span[fromKey]), to = N(span[toKey == null ? "valid_to" : toKey]);
  if (from == null) return false;
  return from <= c && (to == null || c <= to);
}
/* A relation's lifetime is not one span, and it is not written under one key.
 *
 * Two independent mistakes lived here. First, the end was read from `valid_to` only, so a
 * relation whose end extraction recorded as `end_chapter` was drawn as live for the whole
 * book — `rel_f01_016` (罗德 possesses 秦朝) carried `end_chapter: 1` and was shown active at
 * chapter 400. Second, even after reading `end_chapter`, collapsing the relation to a single
 * [start, end] span was wrong: that same record has two `observations[]`, an episode from
 * chapter 1 that `ended`, and a *separate* episode from chapter 322 that is `active` with no
 * end. The top-level `end_chapter: 1` summarises the first episode, not the relation, so
 * applying it globally hides the second episode for the last 80 chapters of the book.
 *
 * So the lifetime is a set of intervals. When `observations[]` exist they *are* the
 * intervals and the top-level scalars are only a summary of the first one; when there are
 * none, the single top-level span is the only thing there is. `valid_to: 0` is the declared
 * "open-ended" sentinel and always wins over any other end.
 *
 * A field being absent never means the fact is absent — enumerate every field that can carry
 * it first. And a single scalar override must never be applied across an episode boundary. */
function relIntervals(r){
  if (!r) return [];
  const eps = [];
  for (const o of A(r.observations)){
    if (!o) continue;
    const from = N(o.valid_from) != null ? N(o.valid_from) : N(o.chapter);
    if (from == null) continue;
    let to = N(o.valid_to != null ? o.valid_to : o.end_chapter);
    if (to === 0) to = null;                       /* open-ended sentinel */
    eps.push({ from, to, active: o.status === "active" });
  }
  if (eps.length){
    eps.sort((a, b) => a.from - b.from);
    /* An episode marked `ended` that carries no explicit end is closed by the start of the
     * next episode — that boundary is the only end the record has. `rel_f01_016` states it
     * exactly this way: episode 1 is `ended` with no `valid_to`, and episode 2 opens at 322.
     * Leaving episode 1 open makes it swallow the rest of the book and the second episode
     * never gets a window of its own. Only the *last* episode may stay open. */
    return eps.map((e, i) => {
      const next = eps[i + 1];
      /* Only the last episode may run to the end of the book; every earlier one is closed
       * by the next episode's start when it has no explicit end of its own. */
      const to = (e.to == null && next) ? next.from : e.to;
      return { from: e.from, to };
    });
  }
  const from = N(r.valid_from);
  let to = N(r.valid_to);
  if (to === 0) to = null;
  if (to == null){ const e = N(r.end_chapter); if (e === 0) to = null; else if (e != null) to = e; }
  return [{ from: from == null ? 0 : from, to }];
}
function relLiveAt(r, c){
  for (const iv of relIntervals(r)){
    if (iv.from <= c && (iv.to == null || c <= iv.to)) return true;
  }
  return false;
}
/* Kept for the caption code, which shows one representative span. Reports the *last*
 * interval end so a still-running episode reads as "第 N 章起" rather than as a closed one. */
function relEnd(r){
  const iv = relIntervals(r);
  if (!iv.length) return null;
  const last = iv[iv.length - 1];
  return last.to == null ? 0 : last.to;
}
const relActive = (r, c) => appears(ENT.get(r.source_id), c) && appears(ENT.get(r.target_id), c)
  && (N(r.valid_from) == null || r.valid_from <= c)
  && relLiveAt(r, c);
const changeSeen = (s, c) => N(s.chapter) != null && s.chapter <= c;

const CACHE = new Map();
/* `snap(c)` projects the whole graph for one chapter and the result is deliberately
 * kept, because a scrub frame revisits the chapters either side of the cursor. But the
 * sliders and the cross-links together can walk the entire 999-chapter range, and every
 * miss stores another full copy of `ent` / `rels` / `events` / `sums`. Left unbounded
 * that turns into a measurable slowdown: measured on this build, 36 cached chapters
 * gave p95 86.8 ms per scrub frame and 174 gave 104.7 ms, with the same visible work
 * — the frame was paying for the table, not the DOM.
 *
 * So the map is capped and evicts least-recently-used. 48 is above the working set of
 * any single gesture (a 34-step scrub touches 34 chapters, a jump touches two) and low
 * enough that the table stays small. `get` re-inserts to refresh recency, which is what
 * makes the eviction actually LRU rather than insertion-ordered. */
const SNAP_LIMIT = 48;
function snap(c){
  if (CACHE.has(c)){
    const hit = CACHE.get(c);
    CACHE.delete(c); CACHE.set(c, hit);
    return hit;
  }
  const ent = A(G.entities).filter(e => appears(e, c));
  const live = new Set(ent.map(e => e.id));
  const rels = A(G.relations).filter(r => relActive(r, c));
  const changes = A(G.state_changes).filter(s => changeSeen(s, c) && live.has(s.entity_id));
  const traits = A(G.character_traits).filter(t => changeSeen(t, c) && live.has(t.entity_id));
  const events = A(G.events).filter(e => N(e.chapter) != null && e.chapter <= c);
  const fsh = A(G.foreshadowing).filter(f => N(f.planted_chapter) == null || f.planted_chapter <= c);
  const comm = A(G.commitments).filter(x => N(x.created_chapter) == null || x.created_chapter <= c);
  const iac = A(G.intimate_acts).filter(x => changeSeen(x, c));
  const roles = A(G.item_roles).filter(r => N(r.valid_from) == null || r.valid_from <= c);
  const sums = A(G.chapter_summaries).filter(s => changeSeen(s, c));
  const st = { c, ent, live, rels, changes, traits, events, fsh, comm, iac, roles, sums };
  CACHE.set(c, st);
  if (CACHE.size > SNAP_LIMIT){
    /* `Map` iterates in insertion order and every access above re-inserted its key, so
     * the first key is the least recently used. */
    CACHE.delete(CACHE.keys().next().value);
  }
  return st;
}

/* The latest state change at or before `c` for one entity + facet. */
function stateAt(entityId, facets, c){
  const wanted = A(facets);
  let best = null;
  for (const s of CHANGES.get(entityId) || []){
    if (s.chapter > c) continue;
    if (!wanted.includes(s.facet)) continue;
    if (!best || s.chapter > best.chapter || (s.chapter === best.chapter && String(s.id) > String(best.id))) best = s;
  }
  return best;
}
function levelAt(entityId, c){ return stateAt(entityId, ["level"], c); }

function lvText(v){
  if (v == null) return "";
  if (typeof v === "string" || typeof v === "number") return String(v);
  const label = v.label ?? v.名称 ?? v.name ?? v.value;
  return label == null ? "" : String(label);
}
function tierText(t){
  if (t == null) return "";
  if (typeof t === "string" || typeof t === "number") return String(t);
  const name = t.名称 ?? t.name ?? t.label ?? "";
  const range = A(t.区间).length ? `（${t.区间[0]}—${t.区间[1]}）` : (t.说明 ?? t.note ? `（${t.说明 ?? t.note}）` : "");
  return String(name) + range;
}

function evLine(ids, limit){
  const rows = A(ids).map(id => EVID.get(id)).filter(Boolean);
  if (!rows.length) return "";
  const shown = rows.slice(0, limit || 2);
  const rest = rows.slice(limit || 2);
  const one = e => `<div class="quote">${esc(prose(e.quote))}<small>第 ${esc(e.chapter)} 章</small></div>`;
  return shown.map(one).join("")
    + (rest.length ? `<details class="ev-more"><summary>另有 ${rest.length} 条引文</summary>${rest.map(one).join("")}</details>` : "");
}
function evCount(ids){ return A(ids).filter(id => EVID.has(id)).length; }

/* ------------------------------------------------------------------ *
 * small builders
 * ------------------------------------------------------------------ */
function chip(text, cls){ return `<span class="chip${cls ? " " + cls : ""}">${esc(text)}</span>`; }
function tag(text, cls){ return `<span class="tag${cls ? " " + cls : ""}">${esc(text)}</span>`; }
function block(title, count, body, right){
  return `<section class="block"><div class="block-head"><h3>${esc(title)}</h3>`
    + (count == null ? "" : `<span class="n">${esc(count)}</span>`)
    + (right ? `<div class="right">${right}</div>` : "")
    + `</div><div class="block-body">${body}</div></section>`;
}
function empty(title, hint){
  return `<div class="empty"><b>${esc(title)}</b>${hint ? esc(hint) : ""}</div>`;
}
function link(id, label){
  const e = ENT.get(id);
  const text = label || (e ? e.name : id);
  if (!e) return `<span class="chip">${esc(text)}</span>`;
  const kind = ROUTE_TYPE[e.type] || "thing";
  /* Inside the drawer a reference is a *cross-reference*: the reader is already reading one
   * subject and wants to compare or follow a thread, so it swaps the panel's contents and
   * leaves the back trail. On a page the same chip is a doorway to another page, and the
   * handler routes it by kind. `data-drawer-link` marks the intent so one delegated handler
   * can serve both without guessing from the DOM. */
  const inDrawer = DRAWER_DEPTH > 0;
  return `<a class="chip alias" href="${esc(entityHref(id) || "#/")}" `
    + `data-entity="${esc(id)}" data-kind="${esc(kind)}"`
    + (inDrawer ? ` data-drawer-link="1"` : "") + `>${esc(text)}</a>`;
}
/* A chapter number inside the drawer is a place you can go. Rendering it as a button
 * that re-scrubs the whole page lets a reader jump from "第 412 章 结丹" to what the book
 * looked like at that moment without hunting the slider. */
function chLink(n, label){
  const v = N(n);
  if (v == null) return esc(label == null ? n : label);
  return `<button class="xlink chx" data-goto-chapter="${v}">${esc(label == null ? ("第 " + v + " 章") : label)}</button>`;
}
function firstAppearance(ids){ return A(ids).map(i => N(i)).filter(v => v != null).sort((a,b) => a-b)[0] ?? null; }
function spanText(from, to, c){
  const f = N(from);
  const t = N(to);
  if (f == null && t == null) return "";
  if (t == null || t === 0 || t > c) return `第 ${f ?? "?"} 章起`;
  return `第 ${f ?? "?"}–${t} 章`;
}


/* ------------------------------------------------------------------ *
 * entity card
 * ------------------------------------------------------------------ */
function isAgentEntity(e){
  if (!e) return false;
  if (e.type === "character" || e.type === "level_axis") return true;
  const agents = G._agents || {};
  return Object.prototype.hasOwnProperty.call(agents, e.id);
}
function latestLevelText(id, c){
  const s = levelAt(id, c);
  if (!s) return "";
  return lvText(s.after) || lvText(s.before) || "";
}
function cardStats(e, c){
  const rels = (RELS.get(e.id) || []).filter(r => relActive(r, c));
  const ch = (CHANGES.get(e.id) || []).filter(s => s.chapter <= c);
  const tr = (TRAITS.get(e.id) || []).filter(s => s.chapter <= c);
  const out = [];
  if (rels.length) out.push(`<span><b>${rels.length}</b> 关系</span>`);
  if (ch.length) out.push(`<span><b>${ch.length}</b> 变化</span>`);
  if (tr.length) out.push(`<span><b>${tr.length}</b> 特征</span>`);
  const lv = latestLevelText(e.id, c);
  if (lv) out.push(`<span><b>${esc(lv)}</b></span>`);
  return out.join("");
}
function entityCard(e, c){
  const color = `var(--type-${e.type})`;
  return `<article class="e-card" data-entity="${esc(e.id)}">
    <span class="bar" style="background:${color}"></span>
    <h4 class="nm">${esc(e.name)}${PRO.has(e.id) ? tag("主角", "acc") : ""}<span class="ty">${esc(ETYPE(e.type))}</span></h4>
    <p class="sm">${esc(prose(e.summary))}</p>
    <div class="meta">${cardStats(e, c)}<span>第 <b>${esc(e.first_chapter ?? "?")}</b> 章登场</span></div>
  </article>`;
}

/* ------------------------------------------------------------------ *
 * router — every subject gets its own page
 *
 * The first three revisions put everything on one stream with a sliding drawer. That
 * answers "what is 苏姬 like right now" but not "show me 苏姬" — a drawer is a look at a
 * record, not a place you can be, link to, bookmark or go Back from. So each subject now
 * has a real page at a real URL fragment:
 *
 *   #/                 the stream (chapter replay, the four graphs, all libraries)
 *   #/char/<id>        a person        #/loc/<id>    a place
 *   #/org/<id>         a faction       #/creature/<id> a beast
 *   #/axis/<id>        a level system  #/item/<id>   an object
 *   #/skill/<id>       a technique     #/concept/<id> a setting
 *   #/event/<id>       one story beat  #/chapter/<n> one chapter
 *   #/index/<type>     the index of a type
 *
 * The page *type* comes from the entity's own `type`, so links never need to know the
 * mapping. Routing is hash-based on purpose: the build is one self-contained file meant
 * to be opened from disk, where `history.pushState` paths do not exist. Hash changes
 * also give Back/Forward for free, which is what makes browsing 980 subjects feel like
 * a wiki instead of a slideshow.
 *
 * The drawer stays for the "peek without leaving" case — clicking a name inside a page
 * opens it without disturbing the route. Pages are for arriving somewhere.
 * ------------------------------------------------------------------ */
const ROUTE_TYPE = {
  character: "char", location: "loc", organization: "org", creature: "creature",
  level_axis: "axis", item: "item", skill: "skill", concept: "concept",
};
const ROUTE_ENTITY = {};
for (const k in ROUTE_TYPE) ROUTE_ENTITY[ROUTE_TYPE[k]] = k;

/* One page per kind, so the shell can say "人物" / "地点" rather than "实体". */
const PAGE_NOUN = {
  char: "人物", loc: "地点", org: "势力", creature: "生灵", axis: "等级体系",
  item: "物品", skill: "技能", concept: "设定", event: "剧情", chapter: "章节",
};
const PAGE_TIER = { char: 2, org: 2, creature: 2, axis: 2, item: 3, skill: 3, concept: 3, loc: 3 };

/* `RT` rather than `ROUTE` — the latter is already the romance-route index (line 1156). */
let RT = { view: "home", kind: null, id: null, n: null };

/* A visit stack, so "返回" can mean "the page I was just on" rather than "the overview".
 *
 * The reader's complaint was literal: on a character page reached from a chapter page, the only
 * way back was 回到总览, which throws away the chapter they came from. Measured: the page carried
 * zero back controls — `.side-acts` had 回到总览 and 顶部 and nothing else — while the browser's own
 * history already recorded the path (`back1=chapter/300`, `back2=entity/char_qin_chao`). The
 * information existed; nothing surfaced it.
 *
 * The stack mirrors history rather than replacing it, so the browser's Back button and this
 * control agree. `NAV_IDX` is where in the stack the current page sits; a hashchange that lands
 * on the previous entry is a pop, anything else is a push that truncates the forward tail. That
 * is the standard model and it keeps the two navigation surfaces consistent — a hand-rolled
 * stack that ignored `history` would drift from the browser buttons the first time one was used.
 */
let NAV_STACK = [];
let NAV_IDX = -1;
function navPush(hash){
  /* Same page, no move: re-applying a route must not grow the stack. */
  if (NAV_IDX >= 0 && NAV_STACK[NAV_IDX] === hash) return;
  /* Landing on the entry immediately before the current one is a back, not a new visit. */
  if (NAV_IDX > 0 && NAV_STACK[NAV_IDX - 1] === hash){
    NAV_IDX -= 1;
    return;
  }
  NAV_STACK = NAV_STACK.slice(0, NAV_IDX + 1);
  NAV_STACK.push(hash);
  NAV_IDX = NAV_STACK.length - 1;
  /* The stack is per-tab browsing state, not content, but an unbounded array would grow for
   * the life of the tab. 120 entries is far past any real reading session and keeps the
   * "back through what I just did" promise intact. */
  if (NAV_STACK.length > 120){
    NAV_STACK = NAV_STACK.slice(-120);
    NAV_IDX = NAV_STACK.length - 1;
  }
}
function navCanBack(){ return NAV_IDX > 0; }
function navBack(){
  if (!navCanBack()) return false;
  /* Delegate to the browser so the two navigation surfaces cannot disagree. */
  history.back();
  return true;
}
/* Exposed for the acceptance harness, which has to assert on the router's own idea of "where
 * did I come from" rather than on a rendered label. */
window.__atlasNav = { canBack: navCanBack, back: navBack,
                      depth: () => NAV_IDX, stack: () => NAV_STACK.slice() };

function hrefFor(kind, id){ return "#/" + kind + "/" + encodeURIComponent(id); }
function entityHref(id){
  const e = ENT.get(id);
  return e ? hrefFor(ROUTE_TYPE[e.type] || "thing", id) : null;
}
/* Name-plus-link for an entity id, shared by every page that lists records. A record citing
 * an id the graph no longer holds falls back to the raw id rather than to nothing: dropping
 * the row would hide the fact that a record exists, which is worse than showing that its
 * subject is unresolved. `entLinks` drops unknown ids instead, because in a list a dead id
 * is noise — and a list is where the 「同源记录」-style joins end up. */
function entLink(id){
  const e = ENT.get(id);
  return e ? `<a class="lref" href="${esc(entityHref(id) || "#/")}">${esc(e.name)}</a>`
           : esc(id || "—");
}
function entLinks(ids){
  return A(ids).filter(id => ENT.has(id)).map(entLink).join("、");
}
/* Non-zero while `entityBody()` is being built for the drawer. `link()` asks this to decide
 * whether a reference should swap the open panel (inside) or open a page (outside) — the
 * body builder is shared by both surfaces, so the distinction cannot be made by looking at
 * the finished markup, only by knowing which surface asked for it. */
let DRAWER_DEPTH = 0;
/* Navigate to a subject's own page from anywhere in the document. The href carries the
 * kind, so an entity whose type has no route of its own still lands on the overview rather
 * than on a dead hash. */
function openEntityRoute(id, kind){
  const e = ENT.get(id);
  const k = kind || (e && ROUTE_TYPE[e.type]) || "thing";
  location.hash = hrefFor(k, id) || "#/";
}
/* Where the reader currently is, as `[label, href]` pairs. The last pair has a null href
 * because it is the page itself. The sidebar renders this as a breadcrumb; each earlier
 * segment is the "back to the level above" control the tree itself does not provide,
 * since the tree only ever offers sibling links. */
function currentCrumb(){
  if (RT.view === "index"){
    const row = SIDE_KINDS.find(k => k[0] === RT.kind);
    return [["分类索引", null], [row ? row[1] : (PAGE_NOUN[RT.kind] || RT.kind), null]];
  }
  /* A crumb segment with a `href` is a link back up the tree; one without is a control that
   * scrolls to the top of what it names. Both are clickable, which is the point — but the
   * *parent* of a chapter page is the chapter index, and it was rendered as a scroll-to-top
   * button even though `#/index/chapter` exists. The reader saw "按章回放" styled as a step
   * they could take and it never took them anywhere. */
  if (RT.view === "chapter") return [["按章回放", "#/index/chapter"], [`第 ${RT.n} 章`, null]];
  if (RT.view === "event"){
    const ev = (A(G.events).find(x => x && x.id === RT.id)) || {};
    return [["剧情", "#/index/event"], [prose(ev.title || RT.id), null]];
  }
  if (RT.view === "entity"){
    const e = ENT.get(RT.id);
    /* Both segments come from `SIDE_KINDS`, which already carries the reader-facing label
     * for each kind — the same table the sidebar tree is built from, so the breadcrumb
     * and the tree can never disagree about what a kind is called. */
    const pair = SIDE_KINDS.find(k => k[0] === RT.kind);
    const out = [];
    if (pair) out.push([pair[1], `#/index/${pair[0]}`]);
    out.push([e ? (e.name || RT.id) : RT.id, null]);
    return out;
  }
  return [];
}
function parseHash(){
  const raw = (location.hash || "").replace(/^#\/?/, "");
  if (!raw) return { view: "home" };
  const seg = raw.split("/").map(decodeURIComponent);
  if (seg[0] === "chapter" && seg[1]) return { view: "chapter", n: Number(seg[1]) };
  if (seg[0] === "event" && seg[1]) return { view: "event", id: seg[1] };
  if (seg[0] === "index" && seg[1]) return { view: "index", kind: seg[1] };
  if (ROUTE_ENTITY[seg[0]] && seg[1]) return { view: "entity", kind: seg[0], id: seg[1] };
  return { view: "home" };
}
function go(route){
  const h = route === "home" ? "#/" : route;
  if (location.hash === h){ applyRoute(); return; }
  location.hash = h;
}
function applyRoute(){
  const next = parseHash();
  RT = next;
  /* The visit stack is updated here and only here, because this is the single place that
   * observes every route change — the reader's own clicks, the back control, and the browser's
   * Back button all arrive through `hashchange` -> `applyRoute`. */
  navPush(location.hash || "#/");
  /* Exposed for the acceptance harness. The router lives in a closed script scope, so
   * there is no other way to ask "which route is active" from outside without reading it
   * back off the DOM, which would test the renderer instead of the router. */
  window.__atlasRoute = next;
  document.body.dataset.view = next.view;
  document.body.dataset.kind = next.kind || "";
  if (next.view === "home"){
    document.getElementById("page").innerHTML = "";
    document.body.classList.remove("paged");
    paintStream();
  } else {
    document.body.classList.add("paged");
    paintPage(next);
  }
  buildSidebar();
  window.scrollTo({ top: 0, behavior: "instant" });
}
window.addEventListener("hashchange", applyRoute);

/* ------------------------------------------------------------------ *
 * drawer — one detail surface for every kind of record
 *
 * Navigation inside the drawer is a real stack, not a replacement. Opening a related
 * entity *pushes*, the back arrow *pops*, and the browser's own back button is bound to
 * the same stack. Without this, clicking "钟离" inside "夏侯兰"'s panel destroyed the
 * panel you were reading and there was no way back to it.
 * ------------------------------------------------------------------ */
let DNAV = [];
function openDrawer(html, opts){
  const o = opts || {};
  const d = document.getElementById("drawer");
  if (o.push){
    const cur = d.firstElementChild;
    if (cur) DNAV.push({ html: d.innerHTML, scroll: d.scrollTop, sel: S.sel, selKind: S.selKind });
  }
  d.innerHTML = html;
  document.body.classList.add("drawer-open");
  d.scrollTop = 0;
  paintNav();
  /* The rail mirrors whichever drawer is open, so it has to be rebuilt whenever the panel
   * turns over — not only when the route changes. */
  buildRail();
}
function closeDrawer(){
  DNAV = [];
  document.body.classList.remove("drawer-open");
  document.getElementById("drawer").innerHTML = "";
  buildRail();
  /* Forgetting this made the drawer reappear on the next slider move: `render()` ends
   * with "if something is selected, re-project it as-of the new chapter", so a closed
   * drawer would spring back open as soon as the user scrubbed. */
  S.sel = null; S.selKind = null;
}
function drawerBack(){
  if (!DNAV.length) return;
  const prev = DNAV.pop();
  const d = document.getElementById("drawer");
  d.innerHTML = prev.html;
  d.scrollTop = prev.scroll || 0;
  S.sel = prev.sel; S.selKind = prev.selKind;
  paintNav();
  buildRail();
}
function paintNav(){
  const d = document.getElementById("drawer");
  const bar = d.querySelector(".drawer-head");
  if (!bar) return;
  let nav = d.querySelector(".dnav");
  if (!DNAV.length){
    if (nav) nav.remove();
    return;
  }
  if (!nav){
    nav = document.createElement("div");
    nav.className = "dnav";
    bar.insertBefore(nav, bar.firstChild);
  }
  const top = DNAV[DNAV.length - 1];
  const who = top.html.replace(/[\s\S]*?<h2>([^<]*)<\/h2>[\s\S]*/, "$1");
  nav.innerHTML = `<button class="dback" data-dback="1">← 返回</button>
    <span class="dtrail">来自 <b>${esc(who)}</b>${DNAV.length > 1 ? ` · 第 ${DNAV.length} 层` : ""}</span>`;
}
/* A link that re-points the drawer at another record without losing the current one. */
function xlink(id, label){
  const e = ENT.get(id);
  if (!e) return esc(label || id);
  return `<button class="xlink" data-goto="${esc(id)}">${esc(label || e.name)}</button>`;
}

function openDrawerLink(id){
  const e = ENT.get(id);
  if (!e) return;
  const c = S.chapter;
  S.sel = id; S.selKind = "entity";
  openDrawer(drawerShell(e, c, entityBodyInDrawer(e, c)), { push: true });
  document.getElementById("drawer").querySelectorAll(".tab").forEach((b, i) => {
    if (i === 0) b.classList.add("on");
  });
}
function openChapterDrawer(ch){
  const n = Math.max(1, Math.min(MAX_CH, ch | 0));
  setChapter(n, true);
  const s = snap(n).sums.find(x => x.chapter === n);
  const body = s
    ? `<p class="mini">${esc(s.summary || "")}</p>
       <div class="mini mt8">本页面已回放到第 ${n} 章。</div>`
    : `<p class="mini">第 ${n} 章没有梗概记录。</p>`;
  openDrawer(`<div class="drawer-head"><div class="row1">
      <h2>第 ${n} 章</h2><span class="kind">章节</span>
      <button class="drawer-close" data-close="1" title="关闭">&times;</button></div>
      <div class="first">${esc(s && s.title ? s.title : "章节记录")}</div></div>
    <div class="drawer-body">${body}</div>`);
}

/* Attribute values are not all scalars. `level_axis.attributes.档位` is an array of
 * `{名称, 区间}` objects and `分级` is a long ladder string; joining an array of
 * objects with the default separator prints `[object Object], [object Object]` into
 * the reader's face. Every shape the schema actually uses gets a reader-facing form. */
function attrText(v){
  if (v == null) return "";
  if (Array.isArray(v)) return v.map(attrText).filter(Boolean).join("、");
  if (typeof v === "object"){
    const o = v;
    const name = o.名称 ?? o.name ?? o.label ?? o.档位;
    const detail = o.说明 ?? o.描述 ?? o.description;
    const range = o.区间;
    if (name != null){
      let tail = "";
      if (range != null) tail = Array.isArray(range) ? `${attrText(range[0])}–${attrText(range[1])}` : attrText(range);
      else if (detail != null) tail = attrText(detail);
      return tail ? `${attrText(name)}（${tail}）` : attrText(name);
    }
    /* an unrecognised object must not be dumped raw */
    return Object.keys(o).map(k => {
      const inner = attrText(o[k]);
      return inner ? `${k} ${inner}` : "";
    }).filter(Boolean).join("；");
  }
  if (typeof v === "boolean") return v ? "是" : "否";
  return String(v);
}

function drawerShell(e, c, body){
  const aliases = A(e.aliases);
  const attrs = e.attributes && typeof e.attributes === "object" ? e.attributes : {};
  const keys = Object.keys(attrs).filter(k => attrText(attrs[k]) !== "");
  const attrRows = keys.map(k =>
    `<tr><td class="k">${esc(AK(k))}</td><td>${esc(attrText(attrs[k]))}</td></tr>`).join("");
  return `<div class="drawer-head">
      <div class="row1">
        <h2>${esc(e.name)}</h2>
        <span class="kind">${esc(ETYPE(e.type))}</span>
        <button class="drawer-close" data-close="1" title="关闭">&times;</button>
      </div>
      <div class="first">第 ${esc(e.first_chapter ?? "?")} 章登场 · 截至第 ${esc(c)} 章${aliases.length ? " · 又称 " + esc(aliases.join("、")) : ""}</div>
    </div>
    <div class="drawer-body">
      ${e.summary ? `<p class="mini">${esc(prose(e.summary))}</p>` : ""}
      ${keys.length ? `<h3 class="sub" data-secsection="固定属性">固定属性</h3><table class="st">${attrRows}</table>` : ""}
      ${body}
    </div>`;
}
function valArrow(s){
  const from = lvText(s.before), to = lvText(s.after);
  if (from && to && from !== to) return `${esc(from)} → <b>${esc(to)}</b>`;
  return esc(to || from || "");
}

/* the things that hang underneath an agent, in the order a reader asks for them */
function entityBodyInDrawer(e, c){
  DRAWER_DEPTH += 1;
  try { return entityBody(e, c); } finally { DRAWER_DEPTH -= 1; }
}
function axisBodyInDrawer(e, c){
  DRAWER_DEPTH += 1;
  try { return axisBody(e, c); } finally { DRAWER_DEPTH -= 1; }
}
function entityBody(e, c){
  const id = e.id;
  const out = [];

  /* 1 — level ladder as of now */
  const lvChanges = (CHANGES.get(id) || []).filter(s => s.facet === "level" && s.chapter <= c);
  if (lvChanges.length){
    const axes = new Map();
    for (const s of lvChanges){
      const axis = s.target_id ? ENT.get(s.target_id) : null;
      const key = axis ? axis.id : FACET(s.facet);
      if (!axes.has(key)) axes.set(key, { axis, rows: [] });
      axes.get(key).rows.push(s);
    }
    const cards = [...axes.values()].map(pair => {
      const rowsDesc = pair.rows.slice().sort((a, b) => b.chapter - a.chapter);
      const now = rowsDesc.find(s => lvText(s.after)) || rowsDesc[0];
      const val = lvText(now.after) || lvText(now.before) || "—";
      /* `hist` is already markup: `chLink()` returns a `<button>`. Escaping it here —
       * as this line did — printed the button as literal text, so the reader saw
       * `→金仙期（<button class="xlink chx" data-goto-chapter="939">第 939 章</button>）`
       * instead of a clickable chapter. The distinction is per-piece: the level names
       * come from the graph and must be escaped, the link is ours and must not be. */
      const hist = rowsDesc.filter(s => s.chapter !== now.chapter).slice(0, 3)
        .map(s => `${esc(lvText(s.before) || "?")}→${esc(lvText(s.after) || "?")}（${chLink(s.chapter)}）`).join("｜");
      return `<div class="milestone"><span class="k">${esc(pair.axis ? pair.axis.name : "境界")}</span>
        <span class="v">${esc(val)}</span>
        ${hist ? `<span class="k mt4">${hist}</span>` : ""}</div>`;
    }).join("");
    out.push(`<h3 class="sub" data-secsection="境界">境界 · 截至第 ${c} 章</h3><div class="milestone-grid">${cards}</div>`);
    const last = lvChanges.slice().sort((a, b) => a.chapter - b.chapter).slice(-1)[0];
    if (last) out.push(evLine(last.evidence_ids, 1));
  }

  /* 2 — traits, grouped by facet, newest first */
  const traits = (TRAITS.get(id) || []).filter(t => t.chapter <= c).slice().sort((a, b) => b.chapter - a.chapter);
  if (traits.length){
    const groups = new Map();
    for (const t of traits){ if (!groups.has(t.facet)) groups.set(t.facet, []); groups.get(t.facet).push(t); }
    const cards = [...groups.entries()].map(entry => `<div class="facet-g">
        <h4>${esc(FACET(entry[0]))}<span class="n">${entry[1].length}</span></h4>
        ${entry[1].slice(0, 6).map(t => `<div class="facet-item"><span class="st">${esc(prose(t.statement))}</span><span class="when">${chLink(t.chapter, "第 " + t.chapter + " 章")}</span></div>`).join("")}
        ${entry[1].length > 6 ? `<div class="mini mt6">另有 ${entry[1].length - 6} 条</div>` : ""}
      </div>`).join("");
    out.push(`<h3 class="sub" data-secsection="人物特征">人物特征</h3><div class="facets">${cards}</div>`);
  }

  /* 3 — state changes that are not the level track */
  const others = (CHANGES.get(id) || []).filter(s => s.chapter <= c && s.facet !== "level");
  if (others.length){
    const rows = others.slice().sort((a, b) => b.chapter - a.chapter).slice(0, 16).map(s => {
      let cause = s.reason ? prose(s.reason) : "";
      if (!cause && s.cause_event_id){
        const ev = A(G.events).find(x => x.id === s.cause_event_id);
        if (ev) cause = "因「" + prose(ev.title) + "」";
      }
      return `<tr><td class="ch">${chLink(s.chapter)}</td><td class="k">${esc(FACET(s.facet))}</td>
        <td>${esc(ACT(s.action))}${valArrow(s) ? " · " + valArrow(s) : ""}
        ${cause ? `<div class="mini">${esc(cause)}</div>` : ""}</td></tr>`;
    }).join("");
    const more = others.length > 16 ? `<div class="mini mt6">另有 ${others.length - 16} 条变化未列出</div>` : "";
    out.push(`<h3 class="sub" data-secsection="状态变化">状态变化</h3><table class="st">${rows}</table>${more}`);
  }

  /* 4 — relations, live at this chapter */
  const rels = (RELS.get(id) || []).filter(r => relActive(r, c));
  if (rels.length){
    const seen = new Set();
    const rows = rels
      .slice().sort((a, b) => (a.valid_from || 0) - (b.valid_from || 0))
      .filter(r => { const k = r.pair_key || r.id; if (seen.has(k)) return false; seen.add(k); return true; })
      .map(r => {
        const otherId = r.source_id === id ? r.target_id : r.source_id;
        const other = ENT.get(otherId);
        const dir = r.source_id === id ? "→" : "←";
        return `<div class="rel-line"><span class="rt">${esc(RELT(r.relation_type))}</span>
          <span>${esc(dir)}</span>${link(otherId, other ? other.name : otherId)}
          <span class="span">${esc(spanText(r.valid_from, relEnd(r), c))}</span>
          ${r.description ? `<div class="mini fb100">${esc(prose(r.description))}</div>` : ""}</div>`;
      }).join("");
    out.push(`<h3 class="sub" data-secsection="关系">关系 · 截至第 ${c} 章</h3>${rows}`);
  }

  /* 5 — what this agent holds / uses / keeps */
  const held = A(G.item_roles).filter(r => r.entity_id === id && (N(r.valid_from) == null || r.valid_from <= c));
  if (held.length){
    const rows = held.map(r => {
      const item = ENT.get(r.item_id);
      return `<div class="rel-line"><span class="rt">${esc(term("item_roles", r.role, r.role))}</span>
        ${link(r.item_id, item ? item.name : r.item_id)}
        <span class="span">第 ${esc(r.valid_from ?? "?")} 章起</span>
        ${r.description ? `<div class="mini fb100">${esc(prose(r.description))}</div>` : ""}</div>`;
    }).join("");
    out.push(`<h3 class="sub" data-secsection="持有 · 使用 · 保管">持有 · 使用 · 保管</h3>${rows}`);
  }

  /* 6 — agreements */
  const comms = (COMM.get(id) || []).filter(x => N(x.created_chapter) == null || x.created_chapter <= c);
  if (comms.length){
    const rows = comms.map(x => {
      const done = x.resolved_chapter != null && x.resolved_chapter <= c;
      const who = A(x.promisor_ids).concat(A(x.counterparty_ids)).filter(a => a !== id);
      const dl = N(x.deadline_chapter) != null ? "第 " + x.deadline_chapter + " 章前" : "";
      return `<div class="rel-line"><span class="rt">${esc(term("commitment_kinds", x.kind, x.kind))}</span>
        ${who.map(w => link(w, (ENT.get(w) || {}).name)).join("")}
        ${done ? tag("已了结", "ok") : tag(ESTAT(x.status))}
        ${dl ? tag(dl, "warn") : ""}
        <span class="span">第 ${esc(x.created_chapter ?? "?")} 章立</span>
        <div class="mini fb100">${esc(prose(x.terms))}</div>
        ${done && x.resolution ? `<div class="mini fb100">结局：${esc(prose(x.resolution))}（第 ${x.resolved_chapter} 章）</div>` : ""}</div>`;
    }).join("");
    out.push(`<h3 class="sub" data-secsection="承诺与约定">承诺与约定</h3>${rows}`);
  }

  /* 7 — foreshadowing this agent is implicated in */
  const fsh = (FSH.get(id) || []).filter(f => N(f.planted_chapter) == null || f.planted_chapter <= c);
  if (fsh.length){
    const rows = fsh.map(f => {
      const done = f.status === "paid_off" || f.status === "resolved";
      return `<div class="rel-line"><span class="rt">${esc(f.label || f.id)}</span>${tag(FSSTAT(f.status), done ? "ok" : "warn")}
        <span class="span">第 ${esc(f.planted_chapter ?? "?")} 章埋</span>
        ${f.observation ? `<div class="mini fb100">原文：${esc(prose(f.observation))}</div>` : ""}
        ${f.interpretation ? `<div class="mini fb100">判读：${esc(prose(f.interpretation))}</div>` : ""}</div>`;
    }).join("");
    out.push(`<h3 class="sub" data-secsection="相关伏笔">相关伏笔</h3>${rows}`);
  }

  /* 8 — intimacy, only for agents that carry such records */
  const acts = (IACTS.get(id) || []).filter(x => x.chapter <= c);
  if (acts.length){
    const rows = acts.slice().sort((a, b) => b.chapter - a.chapter).map(x => {
      const who = A(x.initiator_ids).concat(A(x.recipient_ids)).filter(a => a !== id);
      /* `nudity` is a boolean on this data face, not a list of states. */
      const nudity = x.nudity === true ? " · 有裸露描写" : "";
      const site = x.ejaculation_site ? " · " + term("ejaculation_sites", x.ejaculation_site, x.ejaculation_site) : "";
      return `<div class="rel-line"><span class="rt">${esc(IAT(x.act_type))}</span>${who.map(w => link(w, (ENT.get(w) || {}).name)).join("")}
        ${tag(CC(x.consent), x.consent === "mutual" ? "ok" : "")}
        <span class="span">第 ${esc(x.chapter)} 章</span>
        <div class="mini fb100">${esc(prose(x.description))}${esc(nudity)}${esc(site)}</div></div>`;
    }).join("");
    out.push(`<h3 class="sub" data-secsection="亲密记录">亲密记录</h3>${rows}`);
  }

  /* 9 — romance route, if this agent stands on one */
  const route = A(G.romance_routes).find(r => r.character_id === id || r.protagonist_id === id);
  if (route && appears(ENT.get(route.character_id), c)){
    const other = route.character_id === id ? route.protagonist_id : route.character_id;
    out.push(`<h3 class="sub" data-secsection="感情线">感情线</h3>
      <div class="milestone-grid">
        <div class="milestone"><span class="k">对象</span><span class="v">${esc((ENT.get(other) || {}).name || other)}</span></div>
        <div class="milestone"><span class="k">状态</span><span class="v">${esc(RS(route.status))}</span></div>
        <div class="milestone"><span class="k">入选依据</span><span class="v">${esc(RIB(route.inclusion_basis))}</span></div>
        <div class="milestone"><span class="k">互动性质</span><span class="v">${esc(CC(route.consent_context))}</span></div>
      </div>
      <div class="chips">
        ${tag("初次相遇 第 " + (route.first_meeting_chapter ?? "?") + " 章")}
        ${N(route.ambiguity_started_chapter) != null ? tag("开始暧昧 第 " + route.ambiguity_started_chapter + " 章") : ""}
        ${N(route.confirmed_chapter) != null ? tag("确认关系 第 " + route.confirmed_chapter + " 章", "ok") : ""}
        ${N(route.first_sex_chapter) != null ? tag("首次亲密 第 " + route.first_sex_chapter + " 章") : ""}
      </div>
      ${route.notes ? `<div class="mini mt8">${esc(prose(route.notes))}</div>` : ""}
      ${evLine(A(route.confirmed_evidence_ids).slice(0, 1), 1)}`);
  }

  if (!out.length){
    return drawerShell(e, c, empty("截至第 " + c + " 章尚无下挂记录",
      "该主体在此章节前没有特征、变化、关系或持有记录。"));
  }
  return drawerShell(e, c, out.join(""));
}

/* level_axis entities render their ladder rather than an agent body */
function axisBody(e, c){
  const attrs = e.attributes || {};
  const tiers = A(attrs.档位);
  const out = [];
  if (attrs.分级) out.push(`<h3 class="sub" data-secsection="分级">分级</h3><p class="mini">${esc(String(attrs.分级))}</p>`);
  if (tiers.length){
    out.push(`<h3 class="sub" data-secsection="档位说明">档位说明</h3><div class="facets">${tiers.map(t => {
      const name = t.名称 ?? t.name ?? "";
      const note = t.说明 ?? t.note ?? (A(t.区间).length ? `${t.区间[0]}—${t.区间[1]}` : "");
      return `<div class="facet-g"><h4>${esc(name)}</h4><div class="facet-item">${esc(note)}</div></div>`;
    }).join("")}</div>`);
  }
  const affected = (BY_TARGET.get(e.id) || []).filter(s => s.chapter <= c);
  if (affected.length){
    const rows = affected.slice().sort((a, b) => b.chapter - a.chapter).slice(0, 24).map(s => {
      const who = ENT.get(s.entity_id);
      return `<tr><td class="ch">第 ${s.chapter} 章</td><td>${link(s.entity_id, who ? who.name : s.entity_id)}</td>
        <td>${esc(lvText(s.before) || "—")} → <b>${esc(lvText(s.after) || "—")}</b></td></tr>`;
    }).join("");
    out.push(`<h3 class="sub" data-secsection="在该体系上的进阶记录">在该体系上的进阶记录 · 截至第 ${c} 章</h3><table class="st">${rows}</table>`);
  }
  const conv = A(G.level_conversions).filter(x => {
    if (N(x.chapter) > c) return false;
    return (x.from && x.from.axis_id === e.id) || (x.to && x.to.axis_id === e.id);
  });
  if (conv.length){
    out.push(`<h3 class="sub" data-secsection="体系换算">体系换算</h3>${conv.map(x => {
      const rel = term("level_conversion_relations", x.relation, x.relation);
      return `<div class="rel-line"><span class="rt">${esc(lvText(x.from))} ${esc(rel)} ${esc(lvText(x.to))}</span>
        <span class="span">第 ${esc(x.chapter)} 章</span>
        <div class="mini fb100">${esc(prose(x.description))}</div></div>`;
    }).join("")}`);
  }
  if (!out.length) out.push(empty("该体系没有分档说明或进阶记录", ""));
  return drawerShell(e, c, out.join(""));
}

function showEntity(id){
  const e = ENT.get(id);
  if (!e) return;
  /* Clicking a relation chip while a panel is already open *pushes*: the previous panel
   * stays reachable through the back arrow. Replacing it in place is what made the old
   * panel feel like a one-way door. */
  const push = document.body.classList.contains("drawer-open");
  S.sel = id; S.selKind = "entity";
  const c = S.chapter;
  openDrawer(e.type === "level_axis" ? axisBodyInDrawer(e, c) : entityBodyInDrawer(e, c), { push });
  for (const el of document.querySelectorAll(".e-card.sel")) el.classList.remove("sel");
  const card = document.querySelector('.e-card[data-entity="' + id + '"]');
  if (card) card.classList.add("sel");
}

/* ------------------------------------------------------------------ *
 * zone graph
 *
 * A force layout over 980 nodes pulls unrelated clusters into each other and
 * buries the labels. Here every entity type owns a fixed angular sector and a
 * radial band, so the categories cannot invade one another and the same node
 * keeps the same seat on every chapter scrub. Positions come from the build step.
 * ------------------------------------------------------------------ */
let CY = null;
/* The at-rest name budget is placed while the node array is being built, before any
 * Cytoscape instance exists, so its collision box has to be a constant. It is sized from
 * what the built page actually renders: a six-character name wrapped to two lines at the
 * label font size, plus the outline stroke.
 *
 * The hover pass runs with a live graph and uses the *measured* label box instead, since
 * a constant around the node centre gets the hang-below-the-node offset and the wrapping
 * wrong. Both passes exist; only the measurement source differs. */
const LABEL_BOX_W = 68, LABEL_BOX_H = 34;
/* Every name drawn on the disc has to fit in the room the disc has, and "fit" is a
 * per-node question: two nodes can be one pitch apart and still have names that touch,
 * because a name is wider than the marker under it. So both places that reveal names —
 * the at-rest budget and the sector hover — run the same greedy pass and accept a name
 * only if its box clears every name already accepted.
 *
 * The box is the *measured* label box, not a constant around the node centre. Two earlier
 * versions got this wrong in different ways and both left overlaps on screen:
 *   - a fixed 46x26 box around the centre ignored that the label hangs 3px below the
 *     node and wraps to two lines, so names two rows apart still touched;
 *   - widening that box to 68x34 fixed the at-rest case but was then applied to nodes
 *     whose labels had not been measured at all, so the hover case still overlapped.
 * Cytoscape will report `renderedBoundingBox({includeLabels: true})` once labels are on,
 * but a node whose label is currently "" reports only its marker. So the pass works in
 * two steps: turn every candidate's label on, measure, then remove the ones that did not
 * fit. That is a real layout pass over a few hundred nodes and costs a few milliseconds,
 * which is affordable on hover and on zoom but not on every frame — it is called from
 * exactly those two places. */
function labelFittingSet(){
  if (!CY) return new Set();
  const cand = CY.nodes(".zoned").sort((a, b) =>
    (b.data("deg") || 0) - (a.data("deg") || 0));
  if (!cand.length) return new Set();
  /* Measure with labels forced on, so the boxes include the text rather than just the
   * marker. The class is a scratch state that the caller's `toggleClass` overwrites. */
  cand.addClass("loud");
  const out = new Set();
  const chairs = [];
  cand.forEach(n => {
    const bb = n.renderedBoundingBox({ includeLabels: true, includeOverlays: false });
    const box = { x1: bb.x1 - 2, y1: bb.y1 - 2, x2: bb.x2 + 2, y2: bb.y2 + 2 };
    const clash = chairs.some(q => Math.min(q.x2, box.x2) > Math.max(q.x1, box.x1)
      && Math.min(q.y2, box.y2) > Math.max(q.y1, box.y1));
    if (clash){ n.removeClass("loud"); return; }
    chairs.push(box);
    out.add(n.id());
  });
  return out;
}
function applyLoud(){
  if (!CY) return;
  const on = CY.zoom() >= 1.35;
  if (!on){ CY.nodes(".zoned").removeClass("loud"); return; }
  labelFittingSet();
}
/* Exposed deliberately. `let` at the top level of a classic script creates a binding in
 * the script scope, not a property of `window`, so `window.CY` is undefined no matter how
 * long you wait. Anything outside this file — the acceptance harness, a console session —
 * needs a real handle to check whether the graph actually built, and a check that can
 * never be true is worse than no check: it reported "never drew" while the canvas was
 * sitting there fully drawn. */
Object.defineProperty(window, "CY", {
  get(){ return CY; }, set(v){ CY = v; }, configurable: true,
});
let graphObserver = null;
let graphChapter = null;

/* Two colour accessors, because two consumers want different things from the same token.
 *
 * `ZONE_COLOR` returns the CSS custom-property reference, which is right wherever a
 * browser resolves the value for us: inline `style="background:..."`, an SVG `fill=`
 * attribute, a `<i>` swatch in the sidebar. One declaration in `:root` then drives every
 * one of those sites.
 *
 * `ZONE_RGB` returns a concrete colour, and it exists because **Cytoscape does not
 * resolve CSS custom properties**. Handing it `"var(--type-character)"` makes it fail to
 * parse the value and silently fall back to its default `rgb(153,153,153)` — MEASURED:
 * all 640 nodes rendered that one grey while the legend swatches beside them were
 * correctly coloured. The legend and the canvas disagreed, which is worse than having no
 * legend at all, and no gate caught it because every check asked for the *shape* and the
 * *style string*, never for the resolved colour.
 *
 * The custom property stays the single source of truth — this reads it once and caches.
 * Reading it per node would put a `getComputedStyle` call inside the element-building
 * loop, which is the hot path the frame budget is measured on. */
const RGB_CACHE = new Map();
function ZONE_RGB(t){
  if (RGB_CACHE.has(t)) return RGB_CACHE.get(t);
  const v = getComputedStyle(document.documentElement)
    .getPropertyValue(`--type-${t}`).trim().replace(/^['"]|['"]$/g, "");
  /* A custom property that is missing or unparseable must not become grey by accident:
   * that is exactly the silent fallback this function exists to prevent. `#6b7280` is
   * the neutral the palette already uses for 设定, so a new type that forgot its token
   * is visibly grey-on-purpose rather than grey-by-accident. */
  const out = /^#([0-9a-f]{3}|[0-9a-f]{6})$|^(rgb|hsl)a?\(/i.test(v) ? v : "#6b7280";
  RGB_CACHE.set(t, out);
  return out;
}
const ZONE_COLOR = t => `var(--type-${t})`;

/* Shape carries the entity kind, so a node's type is readable without consulting the
 * legend or the colour. Colour alone fails the two readers who need it most: the one
 * with a colour-vision deficiency, and the one who printed the page.
 *
 * The assignment is not arbitrary — each shape is a small diagram of what the type is:
 *   character    ellipse   a person is a dot: the neutral default
 *   location     round-rect  a place is a bounded area
 *   organization hexagon   a body with members: the six-sided cell
 *   creature     diamond   not human, and pointed
 *   item         tag       a physical object with a hang-tag
 *   skill        pentagon  a learned technique, categorised
 *   concept      rectangle a written rule / abstraction
 *   level_axis   barrel    a graded ladder, stacked
 *
 * Shapes are fixed per type and never vary by chapter: a reader who learned "hexagon
 * means 势力" at chapter 100 must still be right at chapter 900. Only position and
 * emphasis change over time. */
const TYPE_SHAPE = {
  character: "ellipse", location: "round-rectangle", organization: "hexagon",
  creature: "diamond", item: "tag", skill: "pentagon",
  concept: "rectangle", level_axis: "barrel",
  /* `title` and `martial_soul` are in the schema but carry no entities in this run;
   * listing them anyway means a future run that does use them gets a shape instead
   * of silently falling through to the default. */
  title: "round-tag", martial_soul: "star",
};
const shapeOf = t => TYPE_SHAPE[t] || "ellipse";

/* Legend swatch. The legend is the only place the reader is told what the shapes mean,
 * so it has to draw the actual shape rather than a generic dot — a legend that shows a
 * circle for 势力 while the graph draws a hexagon is worse than no legend. Each shape is
 * an inline SVG in the type's colour, sized to the same 11px box the dots occupied. */
const SWATCH_PATH = {
  ellipse:          { d: null, r: 4.5 },
  "round-rectangle": { d: "M1.2 2.4h8.6a1.2 1.2 0 0 1 1.2 1.2v4.8a1.2 1.2 0 0 1-1.2 1.2H1.2A1.2 1.2 0 0 1 0 8.4V3.6a1.2 1.2 0 0 1 1.2-1.2Z" },
  hexagon:          { d: "M5.5 0.4 10.2 3.1v5.4L5.5 11.2 0.8 8.5V3.1Z" },
  diamond:          { d: "M5.5 0.3 10.7 5.5 5.5 10.7 0.3 5.5Z" },
  tag:              { d: "M0.6 1.4h6.2l3.6 4.1-3.6 4.1H0.6Z" },
  pentagon:         { d: "M5.5 0.3 10.7 4.1 8.7 10.3H2.3L0.3 4.1Z" },
  rectangle:        { d: "M0.6 1.6h9.8v7.8H0.6Z" },
  barrel:           { d: "M2.2 0.9h6.6c-.7 1.2-.7 2.4 0 3.6v2c-.7 1.2-.7 2.4 0 3.6H2.2c.7-1.2.7-2.4 0-3.6v-2c.7-1.2.7-2.4 0-3.6Z" },
  "round-tag":      { d: "M3.4 0.9h4.8l2.3 4.6-2.3 4.6H3.4L1.1 5.5Z" },
  star:             { d: "M5.5 0.4 6.9 3.9 10.6 4.2 7.8 6.6 8.7 10.3 5.5 8.3 2.3 10.3 3.2 6.6 0.4 4.2 4.1 3.9Z" },
};
function shapeSwatch(t){
  const sp = SWATCH_PATH[shapeOf(t)] || SWATCH_PATH.ellipse;
  const fill = ZONE_COLOR(t);
  const inner = sp.d
    ? `<path d="${sp.d}" fill="${fill}"/>`
    : `<circle cx="5.5" cy="5.5" r="${sp.r}" fill="${fill}"/>`;
  return `<span class="sw"><svg viewBox="0 0 11 11" width="11" height="11" aria-hidden="true">${inner}</svg></span>`;
}
/* Nodes drawn at once. The layout's pitch is set so this many seats exist without any
 * two labels touching; beyond it the ring filler has to overlap them. The rest of the
 * cast stays reachable through search and through each entity's own relations panel. */
const GRAPH_CAP = 640;
function graphElements(c){
  const st = snap(c);
  const wrap = document.getElementById("cy");
  /* The layout is a unit disc; cytoscape wants pixels. Derive the scale from the
   * container so the graph fills it at any window size instead of assuming 1300px. */
  const box = wrap ? wrap.getBoundingClientRect() : { width: 0, height: 0 };
  const SCALE = Math.max(320, Math.min(box.width || 1200, box.height || 720)) / 2 - 34;
  /* Rank by connectedness so the cap keeps the structurally important nodes rather
   * than an arbitrary slice, and always keep the protagonist. `DEG` was filled once at
   * index time; re-counting here would double every entity's degree on each repaint. */
  const degree = DEG;
  const ranked = st.ent.slice().sort((a, b) =>
    (PRO.has(b.id) ? 1 : 0) - (PRO.has(a.id) ? 1 : 0)
    || (degree.get(b.id) || 0) - (degree.get(a.id) || 0)
    || String(a.name).localeCompare(String(b.name), "zh"));
  const picked = ranked.slice(0, GRAPH_CAP);
  /* The named core: enough edges to be worth finding by name. The threshold scales with
   * the book rather than being a constant, because a 200-node graph and a 900-node one
   * have very different ideas of "well connected". Protagonists and level axes are always
   * named — there are 9 axes and they carry the whole progression structure. */
  const degs = picked.map(e => degree.get(e.id) || 0).sort((a, b) => b - a);
  /* Which nodes keep their name at the default zoom. A fixed percentile of degree does
   * not work: 22% of 640 is 141 names, and a legible name needs ~52px of clear width, so
   * 141 of them need ~7300px of room on a disc whose label ring is ~2400px around. The
   * wedge becomes a wall of text and the two-tier scheme has bought nothing.
   *
   * The bar is therefore derived from *space*. Measured on the rendered page, roughly 45
   * names fit legibly around this disc at the default zoom, so the top 45 by degree keep
   * theirs; everyone else is named on sector hover, or on zoom past 1.35x where the
   * viewport opens up more room. The flat cap is deliberately a literal, with the
   * measurement recorded here, rather than a formula whose terms are guesses.
   */
  const NAME_BUDGET = 45;
  const cutIdx = Math.min(degs.length - 1, NAME_BUDGET);
  const solidCut = Math.max(3, degs[cutIdx] || 3);
  const degMax = Math.max(1, degs[0] || 1);
  /* The degree cut alone does not decide whether the names *fit*. It ranks the whole cast
   * by importance and hands the top 45 their labels, but it never looks at where those 45
   * sit — and the top 45 are overwhelmingly `character`, which means they all land inside
   * one 132° wedge. Measured on the built page: 63 named nodes, 50 overlapping pairs, the
   * worst ("苏姬"/"罗德") overlapping by 15x22px. Ranking by importance and placing by
   * geometry are two different problems and the cut only solved the first.
   *
   * So there is a second pass. It walks the candidates in importance order and accepts a
   * name only if its box clears every already-accepted box. The result is that importance
   * decides *who is asked first* and geometry decides *who is answered*, which is what
   * "the names do not overlap" has to mean if it is to hold at any zoom.
   *
   * The box has to be a constant here rather than a measurement: this pass runs while the
   * node array is being built, before any Cytoscape instance exists to measure against.
   * 68x34 covers a six-character name wrapped to two lines plus the outline stroke, which
   * is what the built page actually renders. The hover pass, which runs with a live graph,
   * uses the measured box instead — see `labelFittingSet`. */
  const chairs = [];
  const fits = (x, y) => chairs.every(q => Math.abs(q.x - x) > LABEL_BOX_W
    || Math.abs(q.y - y) > LABEL_BOX_H);
  const rank = [...picked].sort((a, b) => (degree.get(b.id) || 0) - (degree.get(a.id) || 0)
    || (PRO.has(b.id) ? 1 : 0) - (PRO.has(a.id) ? 1 : 0)
    || (b.type === "level_axis" ? 1 : 0) - (a.type === "level_axis" ? 1 : 0)
    || String(a.id).localeCompare(String(b.id)));
  const named = new Set();
  for (const e of rank){
    const p = L.positions[e.id];
    if (!p) continue;
    /* Protagonists and the level axes are always named — they are the anchor of the whole
     * picture and the reader navigates by them. They take their seat first so the greedy
     * pass places everyone else *around* them rather than pushing them out. */
    const must = PRO.has(e.id) || e.type === "level_axis";
    if (!must && named.size >= NAME_BUDGET) break;
    const px = p.x * SCALE, py = p.y * SCALE;
    if (!must && !fits(px, py)) continue;
    named.add(e.id);
    chairs.push({ x: px, y: py });
  }
  const nodes = [];
  for (const e of picked){
    const p = L.positions[e.id];
    if (!p) continue;
    const lv = latestLevelText(e.id, c);
    const dg = degree.get(e.id) || 0;
    const solid = named.has(e.id);
    /* `preset` reads `position` from the element itself, not from `data`. Parking the
     * coordinates under `data.x`/`data.y` left every node at the origin, which is what
     * collapsed the whole cast into one grey blob on top of the protagonist.
     *
     * The layout is authored in a unit disc (radius 1) so the geometry stays readable
     * in Python, but cytoscape positions are *pixels*. Passing the raw unit values put
     * all 420 nodes inside a 2x2 patch; `fit: true` then zoomed that patch to the
     * viewport, and because node sizes are fixed pixels the markers scaled right along
     * with the coordinates and the blob survived the zoom. Multiplying by GRAPH_SCALE
     * spreads the disc to ~1300px, which is the size the container actually is. */
    nodes.push({
      data: {
        id: e.id, label: e.name, type: e.type, zone: p.zone, kind: p.zone,
        lv, protagonist: PRO.has(e.id) ? 1 : 0, deg: dg, solid: solid ? 1 : 0,
        /* Marker size follows connectedness. At a uniform 7px a 425-node wedge reads as
         * one flat field of dots — the reader cannot tell the sect leader from a walk-on
         * who was named once. Sizing by degree gives the mass a visible top, which is
         * exactly the hierarchy the flat render was hiding.
         *
         * The band moved from [5.5, 11] to [11, 16] because the old floor made the shape
         * channel useless. MEASURED on the built page: every non-protagonist node rendered
         * at 5.5–8.3px, and at 7px a hexagon, a diamond, a tag, a pentagon and a rectangle
         * are the same seven pixels. `accept_atlas.py` gate 30 passed the whole time,
         * because it asked `CY.nodes()[].style("shape")` — that reads the *configuration*,
         * not what the reader can see. A gate on a style string is not a gate on legibility.
         *
         * 11–16px is not a guess. The seat pitch on this graph is 0.0549 unit-disc units,
         * and the container is ~686px, so neighbouring seats sit 37.7px apart. A 16px
         * marker therefore keeps a 2.3x clearance to its neighbour — the old 5.5px floor
         * was using under a fifth of the room the layout had already reserved. The upper
         * bound still exists for the reason it always did: a hub must not swallow the seat
         * next to it. Widening it further would, and 2.3x is the margin that says where. */
        r: Math.round((11 + Math.min(1, Math.log1p(dg) / Math.log1p(degMax)) * 5) * 10) / 10,
      },
      position: { x: p.x * SCALE, y: p.y * SCALE },
    });
  }
  const ids = new Set(nodes.map(n => n.data.id));
  const edges = [];
  const seenPair = new Set();
  for (const r of st.rels){
    if (!ids.has(r.source_id) || !ids.has(r.target_id)) continue;
    if (r.source_id === r.target_id) continue;
    const key = (r.pair_key || (r.source_id + "|" + r.target_id + "|" + r.relation_type));
    if (seenPair.has(key)) continue;
    seenPair.add(key);
    edges.push({ data: { id: r.id, source: r.source_id, target: r.target_id, type: r.relation_type, label: RELT(r.relation_type) }});
  }
  return { elements: nodes.concat(edges), drawn: nodes.length, total: st.ent.length };
}
function paintRadar(){
  /* Eight filled wedges behind the nodes, so the sectors read as regions rather than as
   * gradients of dot colour. Uses the exact same geometry the Python layout computed
   * (zone start/end angles), so the backdrop cannot drift away from where the nodes
   * actually are. Coordinates are flipped into SVG space (y down) to match cytoscape. */
  const svg = document.getElementById("radar");
  if (!svg) return;
  const wrap = document.getElementById("cy");
  const box = wrap ? wrap.getBoundingClientRect() : null;
  if (!box || !box.width) return;
  const W = box.width, H = box.height;
  svg.setAttribute("viewBox", `0 0 ${W} ${H}`);
  const cx = W / 2, cyc = H / 2;
  const R = Math.min(W, H) / 2 - 20;
  const zones = L.zones || {};
  const parts = [];
  for (const t of (L.present || [])){
    const z = zones[t];
    if (!z) continue;
    const a0 = (z.start) * Math.PI / 180, a1 = (z.end) * Math.PI / 180;
    /* Angles are authored with 0 at +x and increase counter-clockwise, but SVG's y axis
     * points down, so the sweep has to be negated or every wedge lands mirrored. */
    const x0 = cx + Math.cos(a0) * R, y0 = cyc + Math.sin(a0) * R;
    const x1 = cx + Math.cos(a1) * R, y1 = cyc + Math.sin(a1) * R;
    const large = (z.end - z.start) > 180 ? 1 : 0;
    parts.push(`<path d="M ${cx} ${cyc} L ${x0.toFixed(1)} ${y0.toFixed(1)} `
      + `A ${R.toFixed(1)} ${R.toFixed(1)} 0 ${large} 1 ${x1.toFixed(1)} ${y1.toFixed(1)} Z" `
      + `fill="${ZONE_COLOR(t)}" fill-opacity="0.055" stroke="${ZONE_COLOR(t)}" `
      + `stroke-opacity="0.20" stroke-width="1" data-zone="${esc(t)}"></path>`);
  }
  svg.innerHTML = parts.join("");
}
/* The cytoscape style sheet, shared by the whole-book graph and every subject graph.
 * Both draw the same data, so a rule that describes "what a node looks like" must live in
 * one place or the two views will drift apart on the next edit. */
function graphStyle(){
  return [
      { selector: "node", style: {
          /* Resolved, not `var(...)` — see `ZONE_RGB`. This line previously passed the
           * custom-property reference straight to Cytoscape and every node drew grey. */
          "background-color": ele => ZONE_RGB(ele.data("zone")),
          /* Shape is the type. See `TYPE_SHAPE` for why each type got the shape it did;
           * the short version is that colour alone cannot carry type for a reader who
           * is colour-blind or printing the page in black and white. */
          "shape": ele => shapeOf(ele.data("zone")),
          /* Size carries connectedness, not name length. The previous rule scaled the
           * marker by `sqrt(label.length)`, which drew a talkative walk-on larger than a
           * hub with a two-character name — the visual weight pointed at the wrong nodes.
           * `data.r` is computed from degree in `graphElements()`. */
          "width": ele => (ele.data("protagonist") ? 22 : ele.data("r") || 7),
          "height": ele => (ele.data("protagonist") ? 22 : ele.data("r") || 7),
          "border-width": ele => (ele.data("protagonist") ? 2.5 : 1),
          "border-color": "#ffffff",
          /* No label by default. 640 names on a 1000px disc cannot be read at once —
           * drawing them all is the same complaint as the old force layout's overlap,
           * just with better geometry behind it. Labels are revealed in tiers below:
           * the cast that carries the graph keeps its name, hovering a sector names that
           * sector's members, and hovering a node names its neighbourhood.
           *
           * This default has to be the empty string, and `.solid` below is what turns names
           * on. Writing `"label": "data(label)"` here — as this line did — names all 640
           * nodes and makes the two selectors beneath it no-ops, because cytoscape resolves
           * later rules as overrides and both of them say the same thing the base already
           * said. The rule and the comment above it disagreed for a whole build cycle. */
          "label": "",
          "font-size": 10,
          "color": "#2b313d",
          /* Names sit below the marker. On a dense disc the space above a node is as
           * occupied as the space beside it, and below is the one direction where a
           * stack of names reads as a list rather than as a smear. */
          "text-valign": "bottom", "text-halign": "center", "text-margin-y": 3,
          "text-outline-width": 2.4, "text-outline-color": "#ffffff",
          "text-wrap": "wrap", "text-max-width": "84px",
          "z-index": ele => (ele.data("protagonist") ? 20 : 1),
      }},
      /* Tier 1 — the named core. Nodes with enough edges to be worth finding by name,
       * plus every protagonist and every level axis (the nine of them are the backbone
       * of the whole graph and there are few enough to always afford). */
      { selector: "node.solid", style: {
          "label": "data(label)", "font-size": 11, "font-weight": 600,
          "text-outline-width": 2.8, "z-index": 6,
      }},
      /* Sector hover: the whole wedge brightens and its members get names. This is what
       * makes the keyed sectors in the legend worth having — pointing at "组织" turns
       * that wedge into a readable list instead of hunting node by node.
       *
       * Names are held back while the view is zoomed out. 354 characters in one wedge sit
       * 20px apart, which clears the markers but not the labels, so naming all of them at
       * once is legible-looking soup. Past 1.35x the wedge has spread enough for a name
       * per node to be readable, and the reader who wants them can zoom. */
      { selector: "node.zoned", style: {
          "label": "", "font-size": 10.5, "z-index": 14,
          "border-width": 1.8, "border-color": "#6157d8",
      }},
      { selector: "node.zoned.loud", style: {
          "label": "data(label)",
      }},
      { selector: "edge", style: {
          "width": 0.6, "line-color": "#c8cdd8",
          "curve-style": "haystack", "haystack-radius": 0.35,
          "opacity": 0.42, "z-index": 0,
      }},
      { selector: "node.hot", style: { "border-width": 3, "border-color": "#6157d8", "z-index": 30, "font-size": 11.5 }},
      { selector: "node.faded", style: { "opacity": 0.16 }},
      { selector: "edge.hot", style: { "line-color": "#6157d8", "width": 1.6, "opacity": 0.9, "z-index": 5 }},
      /* Sector visibility. The class carries the state and this rule honours it, so
       * removing the class restores the element — an inline `style("display", ...)` would
       * stick past the un-toggle and keep the node out of the render for good. */
      { selector: ".hidden", style: { "display": "none" } },
      /* Subject pages draw a hub-and-spoke map where every node is worth naming — there
       * are a few dozen, not 640 — so that view opts in by class instead of inheriting
       * the whole-book label budget. */
      { selector: "node.slabel", style: {
          "label": "data(label)", "font-size": 11.5, "font-weight": 600,
          "text-outline-width": 3, "text-outline-color": "#ffffff", "z-index": 12,
      }},
      { selector: "node.center", style: {
          "label": "data(label)", "font-size": 13.5, "font-weight": 700,
          "border-width": 3, "border-color": "#6157d8", "z-index": 40,
          "text-outline-width": 3.4,
      }},
      { selector: "edge.flow", style: {
          "curve-style": "bezier", "line-color": "#aeb5c4", "width": 1.2,
          "opacity": 0.75, "target-arrow-shape": "triangle",
          "target-arrow-color": "#aeb5c4", "arrow-scale": 0.8, "z-index": 3,
      }},
      { selector: "node.ring0", style: { "border-width": 3, "border-color": "#6157d8" } },
  ];
}

/* ------------------------------------------------------------------ *
 * subject graph — one hub, its neighbours, and their neighbours
 *
 * The whole-book disc answers "how is everything arranged". It cannot answer "who is
 * around this person", because at 640 nodes a single node's neighbourhood is fifteen
 * pixels wide. This draws that neighbourhood at a readable scale instead: the subject at
 * the centre, its direct relations on the first ring, their further relations on the
 * second, arranged so that the nearer a node is the more it says about the subject.
 *
 * Placement is polar and deterministic — ring by graph distance, angle spread evenly —
 * so the same subject always draws the same picture and a reader can learn where to look.
 * A force layout would give a marginally prettier scatter and a different one every time.
 * ------------------------------------------------------------------ */
function subjectElements(e, c){
  const seen = new Map([[e.id, 0]]);
  const adj = new Map();
  for (const r of A(G.relations)){
    if (!relActive(r, c)) continue;
    push(adj, r.source_id, r); push(adj, r.target_id, r);
  }
  /* Breadth-first to depth 2. Depth 3 was tried and draws a hairball: with 42 relation
   * kinds the second ring is already the horizon of what the eye can attribute to the
   * centre, and everything past it reads as noise rather than as structure. */
  let frontier = [e.id];
  for (let depth = 1; depth <= 2; depth++){
    const next = [];
    for (const id of frontier){
      for (const r of adj.get(id) || []){
        const other = r.source_id === id ? r.target_id : r.source_id;
        if (!other || seen.has(other)) continue;
        if (!appears(ENT.get(other), c)) continue;
        seen.set(other, depth);
        next.push(other);
      }
    }
    frontier = next;
    if (!next.length) break;
  }
  const rings = new Map();
  for (const [id, d] of seen){ if (!rings.has(d)) rings.set(d, []); rings.get(d).push(id); }
  const nodes = new Map();
  /* The protagonist has 261 neighbours; a map that draws all of them is a starburst, not
   * a relationship map — nothing on the outer ring can be attributed to the centre, and
   * at any zoom that shows the whole thing the markers are a texture. So each ring is
   * capped at what can be *read*: the highest-degree neighbours make the ring, and the
   * rest are recorded in the "关系" block below, which lists all of them with evidence.
   *
   * Capping rather than compressing is the point. An earlier version derived the radius
   * from the full headcount so nothing was dropped, which pushed the ring out to 3500px
   * and made `fit` shrink the drawing until the nodes were sub-pixel. There is no radius
   * at which 261 labelled neighbours are readable on one ring; the honest answer is to
   * draw the readable ones and say the rest are below. */
  const RING_CAP = [0, 26, 40];
  const RING_R = [0, 190, 340];
  const namedSet = new Set([e.id]);
  const shownSet = new Set([e.id]);
  const ringMembers = [];
  for (const d of [...rings.keys()].sort((a, b) => a - b)){
    const full = rings.get(d).sort((a, b) => (DEG.get(b) || 0) - (DEG.get(a) || 0)
      || String((ENT.get(a) || {}).name).localeCompare(String((ENT.get(b) || {}).name), "zh"));
    const list = d === 0 ? full : full.slice(0, RING_CAP[Math.min(d, RING_CAP.length - 1)]);
    ringMembers.push([d, full.length, list.length]);
    const r = RING_R[Math.min(d, RING_R.length - 1)];
    list.forEach((id, i) => {
      /* The inner ring starts at -90° so the first neighbour sits at the top, which is
       * where the eye lands; later rings are offset by half a step so their nodes do not
       * line up radially with the first ring and hide its edges. */
      const step = (Math.PI * 2) / Math.max(1, list.length);
      const a = -Math.PI / 2 + i * step + (d > 1 ? step / 2 : 0);
      const ent = ENT.get(id) || {};
      shownSet.add(id);
      if (d < 2) namedSet.add(id);
      nodes.set(id, {
        data: {
          id, label: ent.name || id,
          zone: ent.type || "concept",
          r: id === e.id ? 15 : Math.max(6, Math.min(11, 5.5 + (DEG.get(id) || 0) * 0.35)),
          protagonist: !!ent.is_protagonist,
        },
        position: { x: 420 + r * Math.cos(a), y: 330 + r * Math.sin(a) },
        classes: id === e.id ? "center" : (d < 2 ? "slabel ring0" : "slabel"),
      });
    });
  }
  const edges = [];
  const drawn = new Set();
  for (const r of A(G.relations)){
    if (!relActive(r, c)) continue;
    if (!nodes.has(r.source_id) || !nodes.has(r.target_id)) continue;
    const key = [r.source_id, r.target_id, r.relation_type].join("|");
    if (drawn.has(key)) continue;
    drawn.add(key);
    edges.push({ data: { id: "e_" + key, source: r.source_id, target: r.target_id,
                         label: RELT(r.relation_type) }, classes: "flow" });
  }
  return { elements: [...nodes.values(), ...edges], count: nodes.size,
           depth2: (rings.get(2) || []).length, rings: ringMembers,
           hidden: seen.size - shownSet.size };
}

let PG_CY = null;
function buildSubjectGraph(e, c){
  const wrap = document.getElementById("pg-cy");
  if (!wrap) return;
  if (typeof cytoscape !== "function"){
    wrap.innerHTML = empty("本页未内嵌关系图引擎", "关系列表见下方「关系」一节。");
    return;
  }
  const built = subjectElements(e, c);
  if (PG_CY){ PG_CY.destroy(); PG_CY = null; }
  PG_CY = cytoscape({
    container: wrap,
    elements: built.elements,
    boxSelectionEnabled: false,
    minZoom: 0.3, maxZoom: 3,
    wheelSensitivity: 0.2,
    style: graphStyle().concat([
      /* Relation names on the edges. A subject page draws tens of edges, not the whole
       * graph's hundreds, so it can afford labels — but not all at once. With 261 edges
       * radiating from one hub, "labelling every edge" paints 261 rotated strings over
       * each other and the map becomes unreadable, which is the same failure the node
       * labels were just fixed for. The name is worth having when you are looking at one
       * edge, so it appears on hover and stays quiet otherwise. */
      { selector: "edge.flow", style: {
          "label": "", "font-size": 9, "color": "#7b8494",
          "text-outline-width": 2.4, "text-outline-color": "#ffffff",
          "text-rotation": "autorotate", "z-index": 2,
      }},
      { selector: "edge.flow.showlabel", style: {
          "label": "data(label)", "z-index": 20,
      }},
    ]),
    layout: { name: "preset", fit: false, padding: 0 },
  });
  PG_CY.ready(() => {
    if (!PG_CY) return;
    PG_CY.fit(undefined, 44);
    /* Some subjects have a two-node neighbourhood; a one-node component cannot be fitted
     * without dividing by zero, and `fit` silently leaves the zoom at 1 there, which puts
     * the lone centre in a corner. Centre it instead. */
    if (built.count <= 1) PG_CY.center();
  });
  /* Tapping a node navigates to *that* subject's page, not a drawer. The reader asked for
   * one page per subject; a drawer here would be a second, weaker navigation model. */
  PG_CY.on("tap", "node", ev => {
    const id = ev.target.id();
    if (id && id !== e.id) go(hrefFor(ROUTE_TYPE[(ENT.get(id) || {}).type] || "char", id));
  });
  PG_CY.on("tap", "edge", ev => {
    const d = ev.target.data();
    const other = d.source === e.id ? d.target : d.source;
    const oe = ENT.get(other);
    if (oe) openDrawerLink(other);
  });
  /* One relation name at a time, on the edge the pointer is over. */
  PG_CY.on("mouseover", "edge", ev => {
    ev.target.addClass("showlabel");
  });
  PG_CY.on("mouseout", "edge", ev => {
    ev.target.removeClass("showlabel");
  });
  PG_CY.on("mouseover", "node", ev => {
    const hood = PG_CY.getElementById(ev.target.id()).closedNeighborhood();
    PG_CY.elements().not(hood).addClass("faded");
    hood.addClass("hot");
  });
  PG_CY.on("mouseout", () => PG_CY.elements().removeClass("faded").removeClass("hot"));

  const hex = document.getElementById("pg-legend");
  if (hex){
    const zones = new Map();
    for (const el of built.elements){
      if (!el.data || !el.data.zone) continue;
      zones.set(el.data.zone, (zones.get(el.data.zone) || 0) + 1);
    }
    hex.innerHTML = [...zones.entries()].sort((a, b) => b[1] - a[1]).map(([t, n]) =>
      `<div class="row">${shapeSwatch(t)}
       <span>${esc(ETYPE(t))}</span><b style="margin-left:auto">${n}</b></div>`).join("");
  }
}

/* ------------------------------------------------------------------ *
 * graph views
 *
 * One disc, four readings. The sectors answer "how is the cast distributed"; the mind map
 * answers "who is around this person"; the flow answers "how did this get here, step by
 * step"; the tree answers "what contains what". They share the same nodes and the same
 * relation records — only the placement and the filtering differ — so switching views can
 * never show a fact the others deny.
 *
 * Every one of them places labels *below* the node and budgets them: a view that needs
 * 640 names is a view that needs fewer nodes, so the flow and tree views cap what they
 * draw instead of shrinking the type until it is unreadable. That is the fix for the
 * original complaint ("人员网络互相挤压、覆盖") at the level of each view rather than only
 * for the disc.
 * ------------------------------------------------------------------ */
const GRAPH_MODES = [
  ["sector", "扇区图"],
  ["circle", "势力圈"],
  ["mind", "思维导图"],
  ["flow", "思维链"],
  ["tree", "层级树"],
];
let GMODE = "sector";

/* Focus for the mind map: the subject the reader last opened, or the protagonist. */
let GFOCUS = null;
function graphFocus(){
  if (GFOCUS && ENT.has(GFOCUS) && appears(ENT.get(GFOCUS), S.chapter)) return GFOCUS;
  const hero = A(G.metadata && G.metadata.protagonists)[0]
    || (typeof PROTAGONISTS !== "undefined" && A(PROTAGONISTS)[0]);
  if (hero && ENT.has(hero)) return hero;
  const top = snap(S.chapter).ent.slice().sort((a, b) => (DEG.get(b.id) || 0) - (DEG.get(a.id) || 0))[0];
  return top ? top.id : null;
}
const GRAPH_MODE_HINT = {
  sector: "按类型分区固定布局：同一节点在每一章都坐在同一个位置，类型之间互不侵占。名字默认可读的只有骨干成员；<b>悬停左侧分区</b>可点亮整个类型并显示全部名字，悬停节点高亮邻域，<b>点击节点进入它的专属页面</b>。",
  circle: "按关系把主体聚成一个个势力圈：同一圈就是关系上真的连在一起的一伙人。<b>圆的面积正比于人数</b>，所以一眼就能比出一个势力有多大；圈内的人是按「在本圈里和多少人有关联」从中心往外排的，越靠中间越是这一伙的核心。圈外用轮廓框出、写上圈子名，虚线轮廓的是主网之外的独立小圈子，带「未连接」的那一块是全书没有任何关系记录的主体。点任意节点进入它的页面，点圈名只看这一圈。",
  mind: "以一个人为中心按关系距离分层放射：中心是第一层，直接关系在第二环，再往外一圈是他们的关系。点任意节点进入它的页面；点连线上的关系名可查看那段关系的来龙去脉。",
  flow: "按时间排出的流转链：同一条链上的节点是依次发生的。适合看物品怎么转手、境界怎么进阶、剧情怎么一步步推进。",
  tree: "层级树：势力上下级、地点包含、技能归属逐层展开。缩进即从属关系，同级按关系数排序。",
};

/* ---- view 2: mind map — a hub, its neighbours, their neighbours ---------------- */
function mindElements(c){
  const id = graphFocus();
  const e = id ? ENT.get(id) : null;
  if (!e) return { elements: [], count: 0 };
  const built = subjectElements(e, c);
  return { elements: built.elements, count: built.count };
}

/* ---- view 3: flow — chronological chains --------------------------------------
 *
 * A chain is a sequence of events sharing a participant or an item, ordered by chapter.
 * Two chain families are built because they answer the two questions this data is best
 * at: an item passing between hands (`item_roles` with `gained` / `transferred`), and a
 * level track going up one step at a time (`state_changes` with facet `level`). Chains
 * shorter than three links are dropped — a two-step "chain" is just a relation and would
 * fill the view with noise.
 *
 * Placement is left-to-right by index, one row per chain, so reading order *is* time
 * order and the eye never has to consult an axis to know which way is forward.
 * ------------------------------------------------------------------ */
function flowChains(c){
  const chains = [];

  /* Item handovers, oldest first, grouped by item. */
  const byItem = new Map();
  for (const r of A(G.item_roles)){
    if (N(r.valid_from) == null || r.valid_from > c) continue;
    if (!ENT.has(r.item_id) || !ENT.has(r.entity_id)) continue;
    push(byItem, r.item_id, r);
  }
  for (const [itemId, rows] of byItem){
    if (rows.length < 3) continue;
    const seq = rows.slice().sort((a, b) => a.valid_from - b.valid_from);
    chains.push({ kind: "item", title: (ENT.get(itemId) || {}).name, steps: seq.map(r => ({
      id: r.entity_id, chapter: r.valid_from, label: (ENT.get(r.entity_id) || {}).name,
      role: r.role, note: r.description || "",
    })) });
  }

  /* Level tracks, grouped by entity + axis. */
  const byTrack = new Map();
  for (const s of A(G.state_changes)){
    if (s.facet !== "level" || s.chapter > c) continue;
    if (!lvText(s.after)) continue;
    push(byTrack, s.entity_id + "|" + (s.target_id || ""), s);
  }
  for (const [key, rows] of byTrack){
    if (rows.length < 3) continue;
    const [eid, axisId] = key.split("|");
    const seq = rows.slice().sort((a, b) => a.chapter - b.chapter);
    const steps = [{ id: eid, chapter: seq[0].chapter, label: lvText(seq[0].before) || "起点", note: "" }];
    for (const s of seq) steps.push({ id: eid, chapter: s.chapter, label: lvText(s.after), note: s.reason || "" });
    chains.push({ kind: "level", title: `${(ENT.get(eid) || {}).name} · ${axisId ? (ENT.get(axisId) || {}).name : "境界"}`, steps });
  }

  /* Longest first would put a 206-step handover chain at the top, and a single chain that
   * long is 36000px wide when laid out in a row — `fit` then has to shrink the whole
   * drawing to make that one row visible, and the other eleven chains collapse into a
   * single line of pixels. Chains are therefore capped and drawn in reading order: the
   * head of the chain (its first steps) is what carries the story, and the tail of a
   * 200-step chain is a list, which the "流转与使用" block below already presents. */
  const CHAIN_MAX = 14;
  const trimmed = chains.map(ch => ch.steps.length > CHAIN_MAX
    ? { ...ch, steps: ch.steps.slice(0, CHAIN_MAX), truncated: ch.steps.length - CHAIN_MAX }
    : ch);
  return trimmed
    .sort((a, b) => b.steps.length - a.steps.length
      || String(a.title).localeCompare(String(b.title), "zh"))
    .slice(0, 12);
}

function flowElements(c){
  const chains = flowChains(c);
  const elements = [];
  const seen = new Map();
  const ROW = 92, COL = 178;
  const maxSteps = Math.max(1, ...chains.map(ch => ch.steps.length));
  chains.forEach((ch, ri) => {
    ch.steps.forEach((s, si) => {
      /* The same person appears in many chains. Cytoscape needs unique ids, so a repeat
       * gets a per-chain copy — the graph is a diagram here, not the entity index. */
      const nid = "f" + ri + "_" + si;
      seen.set(nid, true);
      elements.push({
        data: { id: nid, label: s.label || "?", zone: (ENT.get(s.id) || {}).type || "concept",
                r: 9, entity: s.id },
        position: { x: 90 + si * COL, y: 70 + ri * ROW },
        classes: "slabel" + (si === 0 ? " ring0" : ""),
      });
      if (si > 0){
        const prev = "f" + ri + "_" + (si - 1);
        elements.push({ data: { id: "fe" + ri + "_" + si, source: prev, target: nid,
                                label: ch.steps[si].chapter ? "第 " + ch.steps[si].chapter + " 章" : "" },
                        classes: "flow" });
      }
    });
  });
  return { elements, count: elements.length, chains: chains.length };
}

/* ---- view 4: tree — containment -------------------------------------------------
 *
 * Which relations are containment? `member_of` / `subordinate_of` / `part_of` /
 * `contains` / `located_at` / `parent_of` are the ones that form a hierarchy in this data;
 * the rest are lateral and would make the tree cycle. Everything is laid out as an
 * indented outline rather than a drawn tree, because the data has 195 `member_of` edges
 * — far more than can be drawn as boxes — and an outline scales where a diagram does not.
 * ------------------------------------------------------------------ */
const TREE_RELS = ["member_of", "subordinate_of", "part_of", "contains", "located_at", "leader_of"];
function treeMarkup(c){
  const live = new Set(snap(c).ent.map(e => e.id));
  const kids = new Map();
  for (const r of A(G.relations)){
    if (!relActive(r, c)) continue;
    if (TREE_RELS.indexOf(r.relation_type) < 0) continue;
    if (!live.has(r.source_id) || !live.has(r.target_id)) continue;
    push(kids, r.target_id, { id: r.source_id, rel: r.relation_type });
  }
  const roots = A(G.entities).filter(e => live.has(e.id)
    && (e.type === "organization" || e.type === "location")
    && !A(G.relations).some(r => r.source_id === e.id && r.relation_type === "member_of" && live.has(r.target_id)))
    .sort((a, b) => (DEG.get(b.id) || 0) - (DEG.get(a.id) || 0)).slice(0, 14);
  const rows = [];
  const seen = new Set();
  const walk = (id, depth, rel) => {
    if (depth > 3 || seen.has(id)) return;
    seen.add(id);
    const e = ENT.get(id);
    if (!e) return;
    const list = (kids.get(id) || []).filter(k => !seen.has(k.id))
      .sort((a, b) => (DEG.get(b.id) || 0) - (DEG.get(a.id) || 0));
    rows.push(`<div class="trow" style="--d:${depth}">
        <a class="lref" href="${esc(entityHref(id) || "#/")}">${esc(e.name)}</a>
        <span class="tty">${esc(PAGE_NOUN[ROUTE_TYPE[e.type]] || ETYPE(e.type))}</span>
        ${rel ? `<span class="trel">${esc(RELT(rel))}</span>` : ""}
        ${list.length ? `<span class="tn">${list.length}</span>` : ""}</div>`);
    for (const k of list.slice(0, 22)) walk(k.id, depth + 1, k.rel);
  };
  for (const r of roots) walk(r.id, 0, null);
  return rows.join("") || `<p class="pg-empty">当前章节没有可展开的层级关系。</p>`;
}

/* ---- view: 势力圈 (circles) ------------------------------------------------------
 *
 * The sector view answers "what kinds of things are in this book". This one answers the
 * question a reader actually asks about a cast of 980: "who belongs with whom". The
 * grouping is computed in Python (`compute_circles`) from the relations themselves, so
 * a circle is a real statement about the data, not a hand-drawn decoration.
 *
 * Two placements, because a faction and a pair have nothing in common except being
 * connected:
 *
 *   * Each circle gets a disc of area proportional to its size, packed outward from the
 *     centre largest-first. Inside its disc the members form a small ring — a clique of
 *     three and a faction of twenty-eight are both legible as a unit, and no layout
 *     iteration is needed, so the picture is identical on every run.
 *   * Isolated entities get one dedicated region rather than being sprinkled through the
 *     picture. They are 480 of 980 — the single largest group — and scattering them is
 *     what made the old view read as noise.
 *
 * Positions are computed once and handed to a `preset` layout. A force simulation would
 * look more organic and would also move every time the chapter slider moves, which breaks
 * the one promise the disc view makes: that a node keeps its place.
 */
const CIRCLE_COLORS = [
  "#4d5fd0", "#0f8f86", "#c2571f", "#8b3fa8", "#1d7f3c",
  "#b8860b", "#2f6fb5", "#b03a52", "#5d7a20", "#7a5aa8",
  "#0d7a99", "#a8600d",
];
function circleColor(i){ return CIRCLE_COLORS[i % CIRCLE_COLORS.length]; }

function circleLayout(c){
  const st = snap(c);
  const live = new Set(st.ent.map(e => e.id));
  const wrap = document.getElementById("cy");
  const box = wrap ? wrap.getBoundingClientRect() : { width: 1200, height: 720 };
  const W = Math.max(560, box.width || 1200);
  const H = Math.max(420, box.height || 720);

  const circles = A(L.circles).map((cir, i) => ({
    ...cir,
    color: circleColor(i),
    members: A(cir.members).filter(id => live.has(id) && ENT.has(id)),
  })).filter(cir => cir.members.length > 0);

  const isoMembers = A(L.isolated && L.isolated.members)
    .filter(id => live.has(id) && ENT.has(id));

  /* Inside a circle, a member is drawn closer to the middle the more of its relations
   * stay at home. The hub — the person the rest of the circle is actually related to —
   * then lands in the middle, and the members who only connect through the hub sit on
   * the rim. What the eye follows outward is the real structure of the circle rather
   * than an alphabetical ring. */
  const linkCounts = new Map();
  for (const r of A(G.relations)){
    if (!r || r.source_id === r.target_id) continue;
    linkCounts.set(r.source_id, (linkCounts.get(r.source_id) || 0) + 1);
    linkCounts.set(r.target_id, (linkCounts.get(r.target_id) || 0) + 1);
  }
  const spokeCount = new Map();
  for (const cir of circles){
    const inside = new Set(cir.members);
    const counts = new Map(cir.members.map(id => [id, 0]));
    for (const r of A(G.relations)){
      if (!r || !inside.has(r.source_id) || !inside.has(r.target_id)) continue;
      if (r.source_id === r.target_id) continue;
      counts.set(r.source_id, counts.get(r.source_id) + 1);
      counts.set(r.target_id, counts.get(r.target_id) + 1);
    }
    cir.members.forEach((id, k) => { spokeCount.set(id, counts.get(id) * 10000 + (cir.size - k)); });
  }
  const byWeight = list => list.slice().sort((a, b) =>
    (spokeCount.get(b) || 0) - (spokeCount.get(a) || 0) || linkCounts.get(b) - linkCounts.get(a));

  /* Spiral the members out from the centre, densest first. Rings sized from the allotted
   * area keep the packing tight, and the spiral never leaves a hole in the middle the
   * way concentric rings do at low counts.
   *
   * The disc radius is *packing* rather than drawing area, so it can be compressed. What
   * the reader reads as size is the span between the outermost members, so that span is
   * normalised separately: the square root still carries the membership ratio, but a
   * 2-member pair is pulled out to a visible blob instead of the 12px speck that raw
   * area proportionality gives it. */
  const SPAN_MIN = 23, SPAN_MAX = 96, SPAN_K = 27;
  const spanOf = n => Math.min(SPAN_MAX, Math.max(SPAN_MIN, Math.sqrt(n) * SPAN_K));
  const GAP_ALLOWANCE = 2600;
  const spiralJob = (list, cx, cy, span, seed) => {
    const n = list.length;
    if (n === 1) return [{ id: list[0], x: cx, y: cy }];
    const rMax = span / 2;
    const growth = rMax / Math.sqrt(n);
    const out = [];
    list.forEach((id, k) => {
      if (k === 0){ out.push({ id, x: cx, y: cy }); return; }
      const rr = Math.min(rMax, growth * Math.sqrt(k));
      const a = k * 2.39996323 + seed;
      out.push({ id, x: cx + Math.cos(a) * rr, y: cy + Math.sin(a) * rr });
    });
    return out;
  };

  /* Circles are placed largest first so the big factions stay in the top-left where a
   * reader starts. The nominal width is deliberately much wider than the stage: every
   * disc is packed at its true size, and `fit()` shrinks the whole picture to the stage
   * once. Compressing the packing to fit instead would either overlap discs or — as
   * measured on the first build — push the largest circle off the left edge, which is
   * what made the big factions invisible.
   *
   * The nominal width is sized from the total disc area to land on a stage-shaped rather
   * than a ribbon-shaped picture. A fixed width is not enough: the aspect ratio of the
   * packed result is what `fit()` scales by, and a 2600x700 ribbon fitted to a 1336x904
   * stage leaves most of the stage empty while shrinking the discs to 40% of the size
   * they could have been.
   *
   * There is no "lone circle" case to handle. Label propagation assigns every linked
   * entity a label that some neighbour already holds, so a bucket of one is structurally
   * impossible; measured on this graph the 500 linked entities land in 19 components and
   * none of them is a singleton. What *is* worth separating is the giant component — 456
   * of the 500 — from the satellites that hang outside it. */
  const placed = [];
  const PAD = 18;
  let spanSum = 0, spanMax = 0;
  for (const cir of circles){
    const span = spanOf(cir.members.length);
    spanSum += span; spanMax = Math.max(spanMax, span);
  }
  const aspect = Math.max(1.05, (H / Math.max(1, W)) * 1.16);
  const NOMINAL = Math.max(spanMax + PAD * 2,
    Math.min(5200, Math.sqrt(aspect * (spanSum + GAP_ALLOWANCE) * (spanMax + PAD * 2))));

  let cursorX = 0, cursorY = 0, rowH = 0;
  for (const cir of circles){
    const span = spanOf(cir.members.length);
    const w = span + PAD * 2;
    if (cursorX + w > NOMINAL && cursorX > 0){ cursorX = 0; cursorY += rowH; rowH = 0; }
    const cx = cursorX + span / 2 + PAD;
    const cy = cursorY + span / 2 + PAD;
    placed.push({ circle: cir, cx, cy, radius: span / 2,
                  pts: spiralJob(byWeight(cir.members), cx, cy, span, 0) });
    cursorX += w;
    rowH = Math.max(rowH, span + PAD * 2);
  }

  const nodes = [];
  for (const p of placed){
    for (const q of p.pts){
      const e = ENT.get(q.id);
      if (!e) continue;
      nodes.push({ data: {
        id: q.id, entity: q.id, label: e.name || q.id, zone: e.type,
        circle: p.circle.id, circleLabel: p.circle.label, circleColor: p.circle.color,
      }, position: { x: q.x, y: q.y }, classes: "cnode" });
    }
  }
  /* One densely packed block for everything unconnected, labelled as such. Packing them
   * tightly is the point: as litter they cost 480 nodes of visual noise, as one block
   * they cost one glance and a count. */
  if (isoMembers.length){
    const isoTop = cursorY + Math.max(rowH, 30) + 44;
    const cols = Math.max(1, Math.floor((NOMINAL - 40) / 15));
    const pts = [];
    isoMembers.forEach((id, k) => {
      pts.push({ id, x: 20 + (k % cols) * 15, y: isoTop + 26 + Math.floor(k / cols) * 15 });
    });
    for (const q of pts){
      const e = ENT.get(q.id);
      if (!e) continue;
      nodes.push({ data: {
        id: q.id, entity: q.id, label: e.name || q.id, zone: e.type,
        circle: "circle-iso", circleLabel: "未连接", circleColor: "#b9c0cc",
      }, position: { x: q.x, y: q.y }, classes: "cn-iso" });
    }
    const isoRows = Math.ceil(isoMembers.length / cols);
    const isoBottom = isoTop + 26 + isoRows * 15;
    placed.push({ circle: { id: "circle-iso", label: "未连接", size: isoMembers.length,
                            color: "#b9c0cc", kind: "isolated" },
                  cx: NOMINAL / 2, cy: (isoTop + isoBottom) / 2,
                  radius: (isoBottom - isoTop) / 2, pts: pts, hull: true });
    cursorY = isoBottom;
    rowH = 0;
  }

  /* Only the edges whose *both* ends survived the chapter filter, so the picture never
   * claims a relationship to someone who has not appeared yet.
   *
   * Edges are split by whether they stay inside one circle. Measured on the first build,
   * drawing all 823 identically produced long chords across the whole canvas that buried
   * the very grouping the view exists to show. An intra-circle edge is evidence *for* the
   * circle, so it is drawn solid and dark; a cross-circle edge is a bridge between
   * collections, so it is drawn faint and is what the hover state reveals. */
  const circleOf = new Map();
  for (const p of placed) for (const q of p.pts) circleOf.set(q.id, p.circle.id);
  const edges = [];
  for (const r of A(G.relations)){
    if (!r || !live.has(r.source_id) || !live.has(r.target_id)) continue;
    if (!ENT.has(r.source_id) || !ENT.has(r.target_id)) continue;
    const inner = circleOf.get(r.source_id) === circleOf.get(r.target_id);
    edges.push({ data: { id: "e-" + r.id, source: r.source_id, target: r.target_id,
                         label: RELT(r.relation_type), rel: r.id, inner: inner ? 1 : 0 },
                 classes: inner ? "e-inner" : "e-bridge" });
  }
  return { nodes, edges, placed, isoCount: isoMembers.length,
           components: L.components || 0, giantSize: L.giant_size || 0,
           height: cursorY + rowH };
}

function renderCircles(c){
  const wrap = document.getElementById("cy");
  if (!wrap) return;
  const legend = document.getElementById("zone-legend");
  const radar = document.getElementById("radar");
  if (radar) radar.innerHTML = "";
  if (typeof cytoscape !== "function"){
    wrap.innerHTML = empty("本页未内嵌关系图引擎", "关系列表仍可在各主体的详情中查看。");
    return;
  }
  const built = circleLayout(c);
  if (CY){ CY.destroy(); CY = null; }
  wrap.innerHTML = "";
  const outer = document.getElementById("cy-outer");
  CY = cytoscape({
    container: wrap,
    elements: built.nodes.concat(built.edges),
    boxSelectionEnabled: false,
    minZoom: 0.12, maxZoom: 4,
    wheelSensitivity: 0.22,
    style: graphStyle().concat([
      { selector: "node.cnode", style: { "width": 14, "height": 14 } },
      { selector: "node.cn-iso", style: { "width": 9, "height": 9, "opacity": 0.62 } },
      /* Intra-circle edges carry the grouping, so they are the visible ones. Cross-circle
       * bridges are drawn nearly invisible: they are real and the reader can bring them
       * out by hovering, but at rest they were 400 long chords that destroyed the very
       * structure this view is for. */
      { selector: "edge.e-inner", style: { "width": 1.25, "opacity": 0.42,
          "line-color": "#8f9aad", "curve-style": "bezier" } },
      { selector: "edge.e-bridge", style: { "width": 0.7, "opacity": 0.07,
          "line-color": "#b6bfcd", "curve-style": "bezier" } },
      { selector: "edge.hot", style: { "opacity": 0.9, "width": 1.8,
          "line-color": "#5b6473", "z-index": 4 } },
    ]),
    layout: { name: "preset", fit: false, padding: 0 },
  });
  CY.ready(() => { if (CY) CY.fit(undefined, 34); });

  /* Circle captions are drawn as HTML over the canvas rather than as cytoscape nodes:
   * a label node would be grabbable, would be counted as an entity by every degree
   * calculation, and would travel with the graph when the reader pans. An absolutely
   * positioned overlay pans with a transform instead. */
  const overlay = document.createElement("div");
  overlay.className = "cy-overlay";
  /* A circle earns a caption and an outline when it is a grouping the reader can act on.
   * The single "unconnected" block gets a dashed one instead, because it is a leftover
   * bucket rather than a group with a name. */
  overlay.innerHTML = built.placed.map(p => {
    const cls = p.circle.kind === "isolated" ? "cc-iso" : "cc";
    const w = Math.max(72, p.radius * 2);
    return `<div class="${cls}" style="left:${(p.cx - w / 2).toFixed(1)}px;top:${
      (p.cy - p.radius).toFixed(1)}px;width:${w.toFixed(1)}px;border-color:${p.circle.color}">
      <span class="cc-name">${esc(p.circle.label)}</span>
      <span class="cc-n">${p.circle.size}</span></div>`;
  }).join("");
  /* A faint ring behind each group is the other half of the "集合" reading: the caption
   * names the collection, the ring shows how much of the canvas it occupies. Drawn in the
   * overlay rather than as a cytoscape node so it is not grabbable and never counts
   * toward a degree. */
  const rings = document.createElement("div");
  rings.className = "cy-rings";
  rings.innerHTML = built.placed.map(p => {
    const d = p.radius * 2 + 16;
    const cls = p.circle.kind === "isolated" ? "rg-iso" : (p.circle.giant ? "rg" : "rg-sat");
    return `<i style="left:${(p.cx - d / 2).toFixed(1)}px;top:${(p.cy - d / 2).toFixed(1)}px;
      width:${d.toFixed(1)}px;height:${d.toFixed(1)}px;border-color:${p.circle.color}"
      class="${cls}"></i>`;
  }).join("");
  wrap.appendChild(rings);
  wrap.appendChild(overlay);
  const syncOverlay = () => {
    if (!CY) return;
    const z = CY.zoom(), pan = CY.pan();
    for (const el of [overlay, rings]){
      el.style.transform = `translate(${pan.x}px,${pan.y}px) scale(${z})`;
      el.style.transformOrigin = "0 0";
    }
  };
  syncOverlay();
  CY.on("zoom pan", syncOverlay);

  CY.on("tap", "node", ev => {
    const eid = ev.target.data("entity");
    if (eid && ENT.has(eid)) go(entityHref(eid));
  });
  CY.on("mouseover", "node", ev => {
    const hood = CY.getElementById(ev.target.id()).closedNeighborhood();
    CY.elements().not(hood).addClass("faded");
    hood.addClass("hot");
  });
  CY.on("mouseout", () => CY.elements().removeClass("faded").removeClass("hot"));

  if (legend){
    const top = built.placed.filter(p => p.circle.kind !== "isolated")
      .sort((a, b) => b.circle.size - a.circle.size).slice(0, 10);
    legend.innerHTML = top.map(p => `<div class="row" data-circle="${esc(p.circle.id)}" tabindex="0"
        role="button" aria-label="只看这一圈"><span class="sw"><svg viewBox="0 0 11 11"
        width="11" height="11" aria-hidden="true"><circle cx="5.5" cy="5.5" r="4.5"
        fill="${p.circle.color}"/></svg></span><span>${esc(p.circle.label)}</span>
        <b style="margin-left:auto">${p.circle.size}</b></div>`).join("")
      + `<div class="row"><span class="sw"><svg viewBox="0 0 11 11"
        width="11" height="11" aria-hidden="true"><circle cx="5.5" cy="5.5" r="4"
        fill="#b9c0cc"/></svg></span><span>未连接（无关系记录）</span>
        <b style="margin-left:auto">${built.isoCount}</b></div>`;
    for (const row of legend.querySelectorAll("[data-circle]")){
      row.addEventListener("click", () => {
        focusCircle(row.dataset.circle);
      });
    }
  }
}

/* Dim everything outside one circle. Cheaper and steadier than re-laying out: the
 * picture stays, the emphasis moves. */
function focusCircle(cid){
  if (!CY) return;
  CY.elements().removeClass("faded").removeClass("hot");
  if (FOCUS_CIRCLE === cid){ FOCUS_CIRCLE = null; return; }
  FOCUS_CIRCLE = cid;
  CY.nodes().forEach(n => {
    if (n.data("circle") !== cid) n.addClass("faded"); else n.addClass("hot");
  });
  CY.edges().forEach(e => {
    if (e.source().data("circle") !== cid || e.target().data("circle") !== cid) e.addClass("faded");
  });
  const ids = CY.nodes().filter(n => n.data("circle") === cid).map(n => n.id());
  if (ids.length) CY.fit(CY.collection(ids.map(i => CY.getElementById(i))), 70);
}
let FOCUS_CIRCLE = null;

function renderFlowOrTree(mode, c){
  const wrap = document.getElementById("cy");
  if (!wrap) return;
  const legend = document.getElementById("zone-legend");
  /* The sector layout draws its wedge backgrounds and ring guides into a separate SVG
   * layer that sits behind the cytoscape canvas. It is not a cytoscape element, so
   * destroying `CY` does not remove it — switching to the chain or tree view left the
   * eight coloured wedges painted over the new content, which read as the view switch
   * having failed. Clear the layer here, with the canvas. */
  const radar = document.getElementById("radar");
  if (radar) radar.innerHTML = "";
  if (mode === "tree"){
    if (CY){ CY.destroy(); CY = null; }
    wrap.innerHTML = `<div class="tree">${treeMarkup(c)}</div>`;
    if (legend) legend.innerHTML = "";
    return;
  }
  if (typeof cytoscape !== "function"){ wrap.innerHTML = ""; return; }
  const built = flowElements(c);
  if (CY){ CY.destroy(); CY = null; }
  wrap.innerHTML = "";
  CY = cytoscape({
    container: wrap,
    elements: built.elements,
    boxSelectionEnabled: false,
    minZoom: 0.2, maxZoom: 3,
    wheelSensitivity: 0.2,
    style: graphStyle().concat([
      { selector: "edge.flow", style: {
          "label": "data(label)", "font-size": 9.5, "color": "#7b8494",
          "text-outline-width": 2.4, "text-outline-color": "#ffffff",
          "text-rotation": "autorotate", "z-index": 2,
      }},
    ]),
    layout: { name: "preset", fit: false, padding: 0 },
  });
  CY.ready(() => { if (CY) CY.fit(undefined, 30); });
  CY.on("tap", "node", ev => {
    const eid = ev.target.data("entity");
    if (eid && ENT.has(eid)) go(entityHref(eid));
  });
  CY.on("mouseover", "node", ev => {
    const hood = CY.getElementById(ev.target.id()).closedNeighborhood();
    CY.elements().not(hood).addClass("faded");
    hood.addClass("hot");
  });
  CY.on("mouseout", () => CY.elements().removeClass("faded").removeClass("hot"));
  /* This row is a caption, not a type key, so it draws an accent-coloured ellipse
   * rather than a per-type shape. */
  if (legend) legend.innerHTML = `<div class="row">
    <span class="sw"><svg viewBox="0 0 11 11" width="11" height="11" aria-hidden="true">
      <circle cx="5.5" cy="5.5" r="4.5" fill="#6157d8"/></svg></span>
    <span>${built.chains} 条链 · ${built.count} 步</span></div>`;
}

function buildGraph(c){
  const wrap = document.getElementById("cy");
  if (!wrap) return;
  graphChapter = c;

  /* Every mode has to start from a clean container. Three separate things can be sitting
   * in it or behind it — the cytoscape canvas, the `#radar` SVG the sector layout paints
   * its wedges into, and the plain-DOM tree outline — and only one of them belongs to any
   * given mode. Clearing all three here means each mode's builder does not have to know
   * what the previous one left, which is what let the wedges survive into the chain view. */
  const radar = document.getElementById("radar");
  if (radar) radar.innerHTML = "";
  wrap.innerHTML = "";

  /* Non-disc views replace the canvas entirely. The hint line is repainted for all four
   * so the reader always knows what the current picture is showing. */
  const hint = document.getElementById("g-hint");
  if (hint) hint.innerHTML = GRAPH_MODE_HINT[GMODE] || "";
  if (GMODE === "flow" || GMODE === "tree"){ renderFlowOrTree(GMODE, c); return; }
  if (GMODE === "circle"){ renderCircles(c); return; }
  if (GMODE === "mind"){
    if (typeof cytoscape !== "function"){
      wrap.innerHTML = empty("本页未内嵌关系图引擎", "关系列表仍可在各主体的详情中查看。");
      return;
    }
    const built = mindElements(c);
    const legendHost = document.getElementById("zone-legend");
    if (CY){ CY.destroy(); CY = null; }
    wrap.innerHTML = "";
    CY = cytoscape({
      container: wrap,
      elements: built.elements,
      boxSelectionEnabled: false,
      minZoom: 0.25, maxZoom: 4,
      wheelSensitivity: 0.22,
      style: graphStyle().concat([
        { selector: "edge.flow", style: {
            "label": "data(label)", "font-size": 9.5, "color": "#7b8494",
            "text-outline-width": 2.4, "text-outline-color": "#ffffff",
            "text-rotation": "autorotate", "z-index": 2,
        }},
      ]),
      layout: { name: "preset", fit: false, padding: 0 },
    });
    CY.ready(() => { if (CY) CY.fit(undefined, 46); });
    CY.on("tap", "node", ev => {
      const id = ev.target.id();
      if (!id) return;
      /* Clicking the hub itself opens its page; clicking a neighbour also opens *its*
       * page. Neither opens a drawer — the reader asked for pages. */
      go(entityHref(id) || "#/");
    });
    CY.on("mouseover", "node", ev => {
      const hood = CY.getElementById(ev.target.id()).closedNeighborhood();
      CY.elements().not(hood).addClass("faded");
      hood.addClass("hot");
    });
    CY.on("mouseout", () => CY.elements().removeClass("faded").removeClass("hot"));
    if (legendHost){
      const zones = new Map();
      for (const el of built.elements){
        if (!el.data || !el.data.zone) continue;
        zones.set(el.data.zone, (zones.get(el.data.zone) || 0) + 1);
      }
      const focus = ENT.get(graphFocus());
      legendHost.innerHTML = `<div class="row">${shapeSwatch(focus ? focus.type : "character")}
          <span>中心：${esc(focus ? focus.name : "—")}</span><b style="margin-left:auto">${built.count}</b></div>`
        + [...zones.entries()].sort((a, b) => b[1] - a[1]).slice(0, 6).map(([t, n]) =>
          `<div class="row">${shapeSwatch(t)}
           <span>${esc(ETYPE(t))}</span><b style="margin-left:auto">${n}</b></div>`).join("");
    }
    return;
  }

  const zones = L.present || [];
  const legend = zones.map(t => {
    const z = L.zones[t];
    return `<div class="row" data-zone="${esc(t)}" tabindex="0" role="button"
      aria-label="聚焦或隐藏该类型">${shapeSwatch(t)}
      <span>${esc(ETYPE(t))}</span><b style="margin-left:auto">${z ? z.count : 0}</b>
      <span class="eye" data-eye="${esc(t)}" title="显示／隐藏该类型">◉</span></div>`;
  }).join("");

  const packed = graphElements(c);
  if (CY){ CY.destroy(); CY = null; }
  /* The tree view renders an indented outline into this same container rather than into a
   * cytoscape canvas, and that outline is plain DOM — destroying `CY` leaves it in place,
   * so returning to the disc would paint the graph behind a list of rows. */
  wrap.innerHTML = "";
  if (typeof cytoscape !== "function"){
    wrap.innerHTML = empty("本页未内嵌关系图引擎", "关系列表仍可在各主体的详情中查看。");
    return;
  }
  CY = cytoscape({
    container: wrap,
    elements: packed.elements,
    boxSelectionEnabled: false,
    minZoom: 0.25, maxZoom: 4,
    motionBlur: false,
    wheelSensitivity: 0.22,
    style: graphStyle(),
    /* `fit: true` cannot be used here. The layout is computed so that adjacent nodes
     * clear each other at the pixel scale above; `fit` would rescale the whole drawing
     * to the container and drag node sizes nowhere (they are fixed px), so any zoom
     * past 1 re-introduces the overlap the layout just removed. The positions already
     * fill the container, so the view is placed once and left alone. */
    layout: { name: "preset", fit: false, padding: 0 },
  });
  CY.ready(() => {
    if (!CY) return;
    CY.center();
    /* Promote the named core once the graph exists. Doing it through classes rather
     * than at construction keeps the style block the single place that decides what a
     * named node looks like. */
    CY.nodes().filter(n => n.data("solid")).addClass("solid");
    /* Names revealed by a sector hover have to be re-fitted when the reader zooms: the
     * threshold says there is *room* past 1.35x, but only the fitting pass can say which
     * names actually clear each other at the new scale. Bound here, where `CY` exists. */
    CY.on("zoom", () => applyLoud());
  });
  /* Navigate, do not peek. A drawer would leave the reader on the disc; the whole point
   * of giving each subject a page is that clicking a name goes somewhere you can link to
   * and come Back from. `openDrawerLink` stays available from inside pages, where a peek
   * genuinely is the right gesture. */
  CY.on("tap", "node", ev => {
    const id = ev.target.id();
    if (id) go(entityHref(id) || "#/");
  });
  CY.on("mouseover", "node", ev => {
    const id = ev.target.id();
    const hood = CY.getElementById(id).closedNeighborhood();
    CY.elements().not(hood).addClass("faded");
    hood.addClass("hot");
  });
  CY.on("mouseout", "node", () => {
    CY.elements().removeClass("faded").removeClass("hot");
  });

  const hex = document.getElementById("zone-legend");
  if (hex) hex.innerHTML = legend;
  /* Whether the sector's names are worth drawing depends on how far in the reader is, so
   * the class is re-applied whenever the zoom changes rather than only on hover.
   *
   * Zooming in spreads the *positions* but not the *type*: at 1.35x a two-character name
   * still occupies about the same screen width while its neighbours have moved apart only
   * by the zoom factor, so a wedge of 354 characters still cannot name all of them. The
   * same greedy pass the at-rest names use runs here, in screen space, so what gets named
   * is always a set that actually fits at the current zoom. */
  const loud = () => applyLoud();
  /* The sector rows in the legend are the answer to "I cannot tell which dot is which".
   * Hovering one names that whole wedge, dims the rest, and lifts the top names; clicking
   * still zooms to it. Hover is the cheap gesture (no viewport change, no lost place) and
   * click is the one that moves the camera, so the two do different jobs. */
  for (const row of document.querySelectorAll("#zone-legend .row")){
    const zone = row.dataset.zone;
    const apply = on => {
      if (!CY) return;
      const hit = CY.nodes().filter(n => n.data("zone") === zone);
      if (on){
        CY.elements().not(hit).addClass("faded");
        hit.removeClass("faded").addClass("hot").addClass("zoned");
        row.classList.add("lit");
        loud();
      } else {
        CY.elements().removeClass("faded").removeClass("hot");
        CY.nodes().removeClass("zoned").removeClass("loud");
        row.classList.remove("lit");
      }
    };
    row.addEventListener("mouseenter", () => apply(true));
    row.addEventListener("mouseleave", () => apply(false));
    /* Hover lights a sector, but lighting seven at a time is not the same as being able
     * to put five of them away. The eye marks the sector hidden and the class hides its
     * members; because the layout is fixed, unhiding restores exactly the same picture
     * rather than triggering a re-layout. */
    const eye = row.querySelector("[data-eye]");
    if (eye){
      eye.addEventListener("click", ev => {
        ev.stopPropagation();
        if (!CY) return;
        const nowOff = !row.classList.contains("off");
        row.classList.toggle("off", nowOff);
        eye.textContent = nowOff ? "◌" : "◉";
        /* Hiding is done with the `hidden` class and a style rule, not by writing
         * `display` on each element. `.style()` writes an inline value that survives the
         * class being removed, so the first version put the node back but left it
         * invisible — and it defeated the stylesheet's own display rules, which is what
         * made the next chapter's scrub pay a per-element style recalculation. */
        const eles = CY.elements().filter(e => e.data("zone") === zone);
        eles.toggleClass("hidden", nowOff);
        apply(false);
      });
    }
    /* Keyboard parity: a sector row is reachable by Tab and toggles with Space, so the
     * legend is not a mouse-only control. */
    row.addEventListener("keydown", ev => {
      if (ev.key === "Enter" || ev.key === " "){
        ev.preventDefault();
        const hit = eye || row;
        hit.click();
      }
    });
    row.addEventListener("click", () => {
      if (!CY) return;
      const hit = CY.nodes().filter(n => n.data("zone") === zone);
      if (!hit.length) return;
      CY.animate({ fit: { eles: hit, padding: 60 }, duration: 320 });
    });
  }
}

/* ------------------------------------------------------------------ *
 * tier 1 — the book
 * ------------------------------------------------------------------ */
function statStrip(c){
  const st = snap(c);
  /* The jump target is an internal block id; the reader must not see it. Keep the
   * two separate: `data-jump` for behaviour, `it[2]` never printed. */
  const items = [
    ["章节", st.sums.length, "chapter_summaries"],
    ["主体", st.ent.length, "entities"],
    ["事件", st.events.length, "events"],
    ["关系", st.rels.length, "entities"],
    ["状态变化", st.changes.length, "entities"],
    ["人物特征", st.traits.length, "entities"],
    ["亲密记录", st.iac.length, "intimacy"],
    ["承诺约定", st.comm.length, "commitments"],
    ["伏笔", st.fsh.length, "foreshadowing"],
    ["引文", evCount(A(G.evidence).filter(e => e.chapter <= c).map(e => e.id)), "entities"],
  ];
  /* Column count is set from the item count so the strip always fills whole rows.
   * With `auto-fit` the wide container fitted nine and stranded the tenth. */
  const cols = items.length >= 10 ? 5 : items.length >= 8 ? 4 : items.length >= 6 ? 3 : 2;
  return `<div class="stat-strip" style="--cols:${cols}">${items.map(it =>
    `<div class="stat" data-jump="${esc(it[2])}"><div class="v">${it[1]}</div><div class="l">${esc(it[0])}</div></div>`
  ).join("")}</div>`;
}
/* Pagination. Every long list shares one control, and the state lives in PAGE rather
 * than in twelve booleans.
 *
 * What this replaces: a single "展开其余 N 条" button that dumped the whole remainder
 * into the DOM at once. On the 327-row foreshadowing list that turned a tidy block into
 * a many-thousand-pixel column with no way back, and the reader lost their place
 * entirely. Paging is the honest version of the same idea — the list is long, so show a
 * slice and let the reader walk it.
 *
 * `key` is the block the control belongs to, `total` the row count, and `per` the page
 * size. Keeping `per` per-block means the chapter stream can show 20 while the item
 * library shows 48 without either knowing about the other. */
const PAGE = { cards: 1, chapters: 1, romance: 1, items: 1, skills: 1, concepts: 1,
               foreshadow: 1, commitments: 1, intimacy: 1, issues: 1, milestones: 1 };
const PER = { cards: 48, chapters: 20, romance: 12, items: 36, skills: 36, concepts: 36,
              foreshadow: 20, commitments: 20, intimacy: 20, issues: 20, milestones: 20 };
/* Filters live here too, so re-rendering a block from a fresh chapter does not silently
 * drop the reader's筛选. */
const FILTER = { cards: { q: "", kind: "all", sort: "degree" },
                 things: { item: "all", skill: "all", concept: "all" },
                 chapters: "", romance: "all", foreshadow: "all", issues: "all",
                 milestones: "all", sort: "chapter" };

function pageSlice(key, rows){
  const per = PER[key] || 20;
  const pages = Math.max(1, Math.ceil(rows.length / per));
  const cur = Math.min(Math.max(1, PAGE[key] | 0), pages);
  PAGE[key] = cur;
  const from = (cur - 1) * per;
  return { slice: rows.slice(from, from + per), page: cur, pages, per,
           from, total: rows.length };
}
/* The control prints 第 X–Y 条 / 共 Z 条 plus a window of page numbers. A window rather
 * than every page: 386 issues is 20 pages, and printing 20 numbers dwarfs the block.
 * First and last are always reachable; the middle walks with the reader. */
function pager(key, st){
  if (st.total <= st.per) return "";
  const win = [];
  const lo = Math.max(1, st.page - 2), hi = Math.min(st.pages, lo + 4);
  for (let p = Math.max(1, hi - 4); p <= hi; p++) win.push(p);
  const btn = (p, label, dis) =>
    `<button class="pg${p === st.page ? " on" : ""}" data-page="${esc(key)}" data-to="${p}"`
    + `${dis ? " disabled" : ""}>${esc(label)}</button>`;
  return `<div class="pager">
    <span class="pg-info">第 ${st.from + 1}–${st.from + st.slice.length} 条 / 共 ${st.total} 条</span>
    <span class="pg-btns">
      ${btn(1, "«", st.page === 1)}
      ${btn(st.page - 1, "‹", st.page === 1)}
      ${win.map(p => btn(p, String(p))).join("")}
      ${btn(st.page + 1, "›", st.page === st.pages)}
      ${btn(st.pages, "»", st.page === st.pages)}
    </span>
    <input class="pg-jump" data-page-jump="${esc(key)}" placeholder="跳页"
           inputmode="numeric" aria-label="跳转到指定页">
  </div>`;
}
/* A filter bar the reader can actually use: each option is a chip with its live count,
 * so "设定与概念 · 105" reads the same whether it is selected or not. */
function filterChips(key, opts, current, axis){
  return `<span class="fchips">${opts.map(o =>
    `<button class="fchip${o[0] === current ? " on" : ""}" data-filter="${esc(key)}"`
    + (axis ? ` data-axis="${esc(axis)}"` : "")
    + ` data-value="${esc(o[0])}">${esc(o[1])}<i>${o[2]}</i></button>`).join("")}</span>`;
}
/* A `<select>` rather than three more chips: the filter chips already carry counts and
 * the sort options do not, so mixing them into one row made the sort look like a fourth
 * category. `axis` is the sub-key the repaint handler writes to, which is how one select
 * per library coexists with one filter per library. */
function sortSelect(key, axis, current, opts){
  return `<select class="sel" data-sort="${esc(key)}" data-axis="${esc(axis)}" aria-label="排序">`
    + opts.map(o => `<option value="${esc(o[0])}"${o[0] === current ? " selected" : ""}>`
        + `${esc(o[1])}</option>`).join("") + `</select>`;
}

/* ------------------------------------------------------------------ *
 * command palette
 *
 * The rail answers "take me to a section", the libraries answer "show me everything of
 * this kind". Neither answers "where is 苏姬" without first knowing she is a character
 * rather than an organization, and with 980 entities spread over three libraries that
 * guess is the whole cost of looking something up. The palette searches all of them at
 * once plus every section, so the reader types a name and lands on it.
 *
 * Ranking is deliberately simple: prefix beats substring, hubs beat walk-ons, and a
 * section never outranks an entity of the same name. That is enough to put the person
 * ahead of the place that shares their name without a query language.
 * ------------------------------------------------------------------ */
let CM = { open: false, q: "", sel: 0, rows: [] };
/* One glyph per result kind, so a mixed result list is scannable. The kinds are the record
 * types the index now covers; a kind with no glyph falls back to the generic block mark. */
const CM_ICON = { entity: "◆", chapter: "§", section: "▤",
                  event: "✦", summary: "¶", thread: "◇", commit: "✧" };

function paletteIndex(){
  const out = [];
  for (const e of snap(S.chapter).ent){
    const aliases = A(e.aliases);
    out.push({
      kind: "entity", id: e.id, name: e.name,
      /* Aliases are searchable but never shown as the title — the reader should find a
       * person by the nickname they remember and still see the canonical name. */
      keys: [String(e.name).toLowerCase()].concat(aliases.map(a => String(a).toLowerCase())),
      sub: ETYPE(e.type),
      meta: e.role || e.species || "",
      dg: (DEG && DEG[e.id]) || 0,
    });
  }
  for (const [tid, label, keys] of RAIL_GROUPS){
    for (const k of keys){
      if (!document.getElementById(k)) continue;
      out.push({ kind: "section", id: k, name: RAIL_LABEL[k] || k,
                 keys: [String(RAIL_LABEL[k] || k).toLowerCase(), k.toLowerCase()],
                 sub: label, meta: "", dg: 0 });
    }
  }
  /* Chapters are offered by number as well as by name: "第 640 章" is the one query the
   * reader already knows verbatim. The range comes from the analysed span rather than
   * from 1..MAX_CH, because the run may not start at chapter 1. */
  for (let ch = MIN_CH; ch <= MAX_CH; ch++){
    out.push({ kind: "chapter", id: String(ch), name: "第 " + ch + " 章",
               keys: [String(ch)], sub: "章节", meta: "", dg: 0 });
  }
  /* Events, chapter summaries, foreshadowing and commitments are searchable too.
   *
   * MEASURED before this was added: six realistic queries all returned zero hits —
   * 「花瓶中魔神入体」(an event title that exists verbatim), 「盒饭」(a chapter summary title
   * that exists verbatim), 「罗德向臭道士复仇」(a foreshadowing label that exists verbatim),
   * 「秦朝将亲自出手审判方华」(a commitment's own wording) and 「秦朝 苏姬」(two characters).
   * The index covered entity names, section names and chapter numbers, so the prose the reader
   * actually remembers — "the scene where the vase..." — was the one thing it could not find.
   * A search that only knows the labels the UI invented is not a search of the book.
   *
   * `goto` carries the destination for rows that are not entities, chapters or in-page
   * sections, so `cmRun` can route them without a per-kind branch.
   */
  for (const ev of A(G.events)){
    if (!ev || !ev.id) continue;
    const title = String(ev.title || "").trim();
    const desc = String(ev.description || "").trim();
    if (!title && !desc) continue;
    out.push({
      kind: "event", id: ev.id, goto: "#/event/" + encodeURIComponent(ev.id),
      name: title || desc.slice(0, 24),
      /* The description is searchable but shown only as a subtitle excerpt: it is the sentence
       * the reader half-remembers, and matching it is the whole point. */
      keys: [title.toLowerCase(), desc.toLowerCase()],
      sub: "第 " + N(ev.chapter) + " 章 · 剧情",
      meta: desc.slice(0, 40), dg: 0,
    });
  }
  for (const s of A(G.chapter_summaries)){
    const ch = N(s && s.chapter);
    if (ch == null) continue;
    const title = String((s && s.title) || "").trim();
    const body = String((s && s.summary) || "").trim();
    if (!title && !body) continue;
    out.push({
      kind: "summary", id: "ch-" + ch, goto: "#/chapter/" + ch,
      name: title || ("第 " + ch + " 章"),
      keys: [title.toLowerCase(), body.toLowerCase(), String(ch)],
      sub: "第 " + ch + " 章 · 梗概",
      meta: body.slice(0, 40), dg: 0,
    });
  }
  for (const f of A(G.foreshadowing)){
    const label = String((f && f.label) || "").trim();
    if (!label) continue;
    const ch = N(f.planted_chapter);
    out.push({
      kind: "thread", id: "fs-" + (f.id || label), goto: ch != null ? "#/chapter/" + ch : "#/",
      name: label,
      keys: [label.toLowerCase(), String(f.observation || "").toLowerCase(),
             String(f.interpretation || "").toLowerCase()],
      sub: "伏笔 · " + (FSSTAT ? FSSTAT(f.status) : String(f.status || "")),
      meta: ch != null ? ("埋于第 " + ch + " 章") : "", dg: 0,
    });
  }
  for (const x of A(G.commitments)){
    const terms = String((x && x.terms) || "").trim();
    if (!terms) continue;
    const ch = N(x.created_chapter);
    out.push({
      kind: "commit", id: "cr-" + (x.id || terms),
      goto: ch != null ? "#/chapter/" + ch : "#/",
      name: terms.slice(0, 28),
      keys: [terms.toLowerCase(), String(x.resolution || "").toLowerCase()],
      sub: "承诺 · " + (ESTAT ? ESTAT(x.status) : String(x.status || "")),
      meta: ch != null ? ("立于第 " + ch + " 章") : "", dg: 0,
    });
  }
  return out;
}
let CM_INDEX = null;

function cmScore(row, q){
  let best = -1;
  for (const k of row.keys){
    const i = k.indexOf(q);
    if (i < 0) continue;
    /* A hit at position 0 is worth far more than one at position 40 — otherwise a
     * substring in a long alias can outrank an exact short name. */
    const s = (i === 0 ? 100 : 60 - Math.min(40, i));
    if (s > best) best = s;
  }
  return best;
}
/* A multi-word query means "all of these words", which is what a reader types when they
 * remember two things about one scene.
 *
 * MEASURED before this existed: 「秦朝 苏姬」 returned nothing, while both names are in the
 * index and the two appear together throughout the book. The search compared the whole query
 * as one substring, so any query with a space was guaranteed to fail — the reader had to
 * already know the exact wording to find anything. Terms are ANDed and may match different
 * keys of the same record, which is the useful reading: an event whose title holds one name and
 * whose description holds the other is exactly the scene being looked for.
 */
function cmScoreAll(row, terms){
  let total = 0;
  for (const t of terms){
    const s = cmScore(row, t);
    if (s < 0) return -1;
    total += s;
  }
  return total;
}
function cmSearch(q){
  if (!CM_INDEX) CM_INDEX = paletteIndex();
  const needle = String(q || "").trim().toLowerCase();
  if (!needle) return CM_INDEX.filter(r => r.kind === "section").slice(0, 12);
  const terms = needle.split(/\s+/).filter(Boolean);
  const out = [];
  for (const r of CM_INDEX){
    const s = cmScoreAll(r, terms);
    if (s >= 0) out.push([s * 1000 + Math.min(999, r.dg || 0), r]);
  }
  out.sort((a, b) => b[0] - a[0]);
  /* Score order alone lets one kind fill the list. MEASURED reason this matters: entity names
   * match at position 0 and so score 100000, while an event's description can only match at
   * position 20+ and scores under 60000 — so a query naming a character returns forty people
   * and hides the scenes they are in, which is exactly the thing that could not be found at
   * all before this round. Each kind is therefore capped, and the leftover slots are filled by
   * score so a query with only one kind of match still shows everything it has. */
  const CAP = 8, LIMIT = 40;
  const picked = [], overflow = [], seenKind = {};
  for (const [s, r] of out){
    const k = r.kind;
    if ((seenKind[k] || 0) < CAP){ seenKind[k] = (seenKind[k] || 0) + 1; picked.push(r); }
    else overflow.push(r);
    if (picked.length >= LIMIT) break;
  }
  for (const r of overflow){
    if (picked.length >= LIMIT) break;
    picked.push(r);
  }
  return picked.slice(0, LIMIT);
}
function cmBody(){
  if (!CM.rows.length){
    return `<div class="cm-empty">没有匹配的条目。试试人物名、势力名、章节号，或「伏笔」这类区块名。</div>`;
  }
  return CM.rows.map((r, i) =>
    `<button class="cm-row${i === CM.sel ? " on" : ""}" data-cm-row="${i}">
      <span class="cm-ic">${esc(CM_ICON[r.kind] || "▤")}</span>
      <span class="cm-name">${esc(r.name)}</span>
      <span class="cm-sub">${esc(r.sub)}</span>
      ${r.meta ? `<span class="cm-meta">${esc(r.meta)}</span>` : ""}
    </button>`).join("");
}
function openPalette(seed){
  const p = document.getElementById("cmdk");
  if (!p) return;
  CM.open = true; CM.q = seed || ""; CM.sel = 0;
  CM.rows = cmSearch(CM.q);
  p.innerHTML = `<div class="cm-box" role="dialog" aria-label="全局检索">
    <div class="cm-head"><input class="cm-input" id="cm-input" placeholder="搜索人物 · 剧情 · 章节梗概 · 伏笔 · 承诺"
      value="${esc(CM.q)}" autocomplete="off">
      <kbd>Esc</kbd></div>
    <div class="cm-list" id="cm-list">${cmBody()}</div>
    <div class="cm-foot"><kbd>↑</kbd><kbd>↓</kbd> 选择 <kbd>↵</kbd> 打开 <kbd>/</kbd> 唤起</div></div>`;
  document.body.classList.add("cm-open");
  const inp = document.getElementById("cm-input");
  if (inp){
    inp.focus();
    try { inp.setSelectionRange(inp.value.length, inp.value.length); } catch (e) {}
  }
}
function closePalette(){
  const p = document.getElementById("cmdk");
  if (!p) return;
  CM.open = false;
  p.innerHTML = "";
  document.body.classList.remove("cm-open");
}
function cmMove(d){
  if (!CM.rows.length) return;
  CM.sel = (CM.sel + d + CM.rows.length) % CM.rows.length;
  const list = document.getElementById("cm-list");
  if (list){
    list.innerHTML = cmBody();
    const on = list.querySelector(".cm-row.on");
    if (on && on.scrollIntoView) on.scrollIntoView({ block: "nearest" });
  }
}
function cmRun(idx){
  const r = CM.rows[idx == null ? CM.sel : idx];
  if (!r) return;
  closePalette();
  if (r.kind === "entity"){ showEntity(r.id); return; }
  if (r.kind === "chapter"){ openChapterDrawer(Number(r.id)); return; }
  /* Events, summaries, threads and commitments each name a page that is not a section of the
   * current one, so they carry their destination rather than an element id. Routing through
   * `location.hash` keeps them consistent with every other link in the page — including the
   * browser history, which is what makes 返回 work after arriving from a search. */
  if (r.goto){ location.hash = r.goto; return; }
  const node = document.getElementById(r.id);
  if (!node) return;
  const top = node.getBoundingClientRect().top + window.scrollY - 74;
  window.scrollTo({ top: Math.max(0, top), behavior: "smooth" });
}

function chapterStream(c){
  const all0 = snap(c).sums.slice().sort((a, b) => b.chapter - a.chapter);
  /* The filter narrows the whole set, not the visible page of 20. Filtering only the
   * rendered rows meant looking for chapter 700 found nothing unless you had already
   * paged to it. */
  const q = (FILTER.chapters || "").toLowerCase();
  const all = !q ? all0 : all0.filter(s =>
    String(s.chapter).includes(q)
    || String(s.title || "").toLowerCase().includes(q)
    || String(s.summary || "").toLowerCase().includes(q));
  const pg = pageSlice("chapters", all);
  const rows = pg.slice;
  const head = `<div class="block-head"><h3>章节梗概</h3><span class="n">${all.length}${q ? " / " + all0.length : ""}</span>
    <div class="right"><input class="find" id="cs-find" data-textfilter="chapters" placeholder="按章号或关键词筛选" value="${esc(FILTER.chapters || "")}">
    <button class="chip" id="cs-jump" title="跳到指定章">跳到第 N 章</button></div></div>`;
  const body = rows.length ? `<div class="cs-list">${rows.map(s => {
    const evs = (EVENTS.get("ch" + s.chapter) || []).slice(0, 4);
    return `<article class="cs" data-ch="${s.chapter}">
      <span class="cn">第 ${s.chapter} 章</span>
      <div>
        ${s.title ? `<h4>${esc(prose(s.title))}</h4>` : ""}
        <p>${esc(prose(s.summary))}</p>
        <div class="meta">${evs.map(e => tag(EVT(e.type))).join("")}</div>
      </div></article>`;
  }).join("")}</div>${pager("chapters", pg)}`
    : empty(q ? `没有匹配「${FILTER.chapters}」的章节` : "第 " + c + " 章之前没有章节梗概",
            q ? "清空筛选框可恢复全部章节。" : "章节梗概来自 chapter_summaries 数据面。");
  return `<section class="block" id="block-chapter_summaries">${head}<div class="block-body tight">${body}</div></section>`;
}
function rhythmBlock(c){
  const chap = A(V.chapter_rhythm && V.chapter_rhythm.chapters).filter(r => r.chapter <= c);
  if (!chap.length) return "";
  const max = Math.max(1, ...chap.map(r => r.event_total || 0));
  const rows = chap.slice().sort((a, b) => b.event_total - a.event_total).slice(0, 40).map(r =>
    `<div class="bar-row"><span>第 ${r.chapter} 章</span>
      <span class="bar-track"><span class="bar-fill" style="width:${Math.round(100 * (r.event_total || 0) / max)}%"></span></span>
      <span>${r.event_total || 0}</span></div>`).join("");
  return block("节奏 · 事件密度最高的章节", chap.length, `<div class="bars">${rows}</div>`);
}
function rulesBlock(c){
  /* `derive_novel_views.derive_rules` returns `{concepts, enforcement_events}`, not
   * `{rules}` — reading the wrong key silently produced an empty block here. */
  const R = V.rules || {};
  const concepts = A(R.concepts).filter(x => N(x.first_chapter) == null || x.first_chapter <= c);
  const enforcement = A(R.enforcement_events).filter(x => N(x.chapter) == null || x.chapter <= c);
  if (!concepts.length && !enforcement.length) return "";
  const conceptRows = concepts.slice(0, 20).map(x =>
    `<div class="rel-line"><span class="rt">${esc(x.name || x.id)}</span>
      ${A(x.categories).map(cat => tag(term("concept_categories", cat, "")).trim() || "").join("")}
      ${N(x.first_chapter) != null ? `<span class="span">第 ${x.first_chapter} 章</span>` : ""}
      <div class="mini fb100">${esc(prose(x.summary))}</div></div>`).join("");
  const enfRows = enforcement.slice(0, 12).map(x =>
    `<div class="rel-line"><span class="rt">${esc(prose(x.title || x.description || x.id))}</span>
      ${N(x.chapter) != null ? `<span class="span">第 ${x.chapter} 章</span>` : ""}</div>`).join("");
  return block("世界观规则与设定", concepts.length + enforcement.length,
    (conceptRows ? `<h3 class="sub" data-secsection="设定条目">设定条目</h3>${conceptRows}` : "")
    + (enfRows ? `<h3 class="sub" data-secsection="规则的动用">规则的动用</h3>${enfRows}` : ""));
}
function coverageBlock(c){
  /* `contract["coverage"]` is `{axis_name: {covered, total, ratio}}` — an object of
   * per-axis tallies, not an array of chapter rows. It is the graph's own audit of how
   * complete each data face is, so render it as a ratio bar per axis. */
  const cov = (V.coverage && !Array.isArray(V.coverage)) ? V.coverage : {};
  const axes = Object.keys(cov).map(k => ({ key: k, ...cov[k] })).filter(x => typeof x.ratio === "number");
  axes.sort((a, b) => a.ratio - b.ratio);
  const label = k => term("coverage_axes", k, HUMANISE(k));
  const bars = axes.map(x => {
    const pct = Math.round(x.ratio * 100);
    const cls = pct >= 80 ? "ok" : (pct >= 50 ? "warn" : "bad");
    return `<div class="bar-row cov"><span title="${esc(x.key)}">${esc(label(x.key))}</span>
      <span class="bar-track"><span class="cov-fill ${cls}" style="width:${Math.max(2, pct)}%"></span></span>
      <span>${pct}%</span>
      <span class="cov-tally">${x.covered}/${x.total}</span></div>`;
  }).join("");
  const analyzed = A(G.metadata.analyzed_chapters).filter(x => x <= c);
  const body = `<div class="milestone-grid">
      <div class="milestone"><span class="k">已分析章</span><span class="v">${analyzed.length}</span></div>
      <div class="milestone"><span class="k">范围内章</span><span class="v">${c - MIN_CH + 1}</span></div>
      <div class="milestone"><span class="k">待核事项</span><span class="v">${A(G.review_issues).filter(i => N(i.chapter) == null || i.chapter <= c).length}</span></div>
    </div>
    ${axes.length ? `<h3 class="sub">各数据面覆盖度 · 越低表示越需要补</h3><div class="bars">${bars}</div>` : ""}`;
  return block("覆盖台账", axes.length || null, body);
}

/* `coverage_axes` keys are internal slugs (`side_character_relations`). Show a readable
 * fallback rather than the raw key when the vocabulary has no entry. */
function HUMANISE(key){
  const KNOWN = {
    battle_combat: "战斗记录", skill_categories: "技能分类", location_hierarchy: "地点层级",
    event_location: "事件地点", item_role_cause: "物品流转原因", chapter_summaries: "章节梗概",
    resource_tags: "资源标签", side_character_relations: "次要人物关系", secret_knowledge: "秘密知情",
    commitment_lifecycle: "承诺生命周期",
  };
  return KNOWN[key] || "其他数据面";
}

/* ------------------------------------------------------------------ *
 * tier 2 — the agents
 * ------------------------------------------------------------------ */
function agentLibrary(c){
  const st = snap(c);
  const kinds = ["character", "organization", "creature"];
  const all = st.ent.filter(e => kinds.includes(e.type));

  /* The grid, its filter and its pager are all painted by `paintLib()` in `wire()`. That
   * function owns the query and the type filter, and it must range over *every* agent
   * that is live at this chapter rather than over the rendered slice — otherwise typing
   * the name of someone who debuts in chapter 700 matches nothing, because the card was
   * never in the DOM to be filtered. Rendering a first slice here as well would double
   * the work and reintroduce exactly that bug. */
  const counts = { all: all.length };
  for (const k of kinds) counts[k] = all.filter(e => e.type === k).length;
  const sel = `<div class="chips" id="lib-filter">
    ${[["all", "全部"], ["character", ETYPE("character")],
       ["organization", ETYPE("organization")], ["creature", ETYPE("creature")]].map(o =>
      `<button class="chip" data-lib="${o[0]}">${esc(o[1])}<i>${counts[o[0]] || 0}</i></button>`).join("")}
    <select class="sel" id="lib-sort" aria-label="排序">
      <option value="degree">按关系数</option>
      <option value="chapter">按登场章</option>
      <option value="name">按名称</option>
    </select>
    <input class="find" id="lib-find" placeholder="搜索姓名、别名、简介">
  </div>`;

  return `<section class="block" id="block-entities">
    <div class="block-head"><h3>人物 · 势力 · 生灵</h3>
      <span class="n" id="lib-tally">${all.length}</span></div>
    <div class="block-body">${sel}<div class="e-grid" id="lib-grid"></div>
    <div id="lib-pager"></div></div></section>`;
}
function levelBlock(c){
  const axes = A(G.entities).filter(e => e.type === "level_axis" && appears(e, c));
  if (!axes.length) return "";
  const cards = axes.map(ax => {
    const changes = (BY_TARGET.get(ax.id) || []).filter(s => s.chapter <= c);
    const holders = new Map();
    for (const s of changes){
      const w = ENT.get(s.entity_id);
      if (!w) continue;
      const v = lvText(s.after);
      if (v) holders.set(s.entity_id, { name: w.name, v, ch: s.chapter });
    }
    const top = [...holders.values()].sort((a, b) => b.ch - a.ch).slice(0, 6);
    const attrs = ax.attributes || {};
    return `<article class="e-card" data-entity="${esc(ax.id)}">
      <span class="bar" style="background:${ZONE_COLOR("level_axis")}"></span>
      <h4 class="nm">${esc(ax.name)}<span class="ty">${esc(ETYPE("level_axis"))}</span></h4>
      <p class="sm">${esc(String(attrs.分级 || attrs.单位 || prose(ax.summary)))}</p>
      <div class="chips">${top.map(h => `<span class="chip">${esc(h.name)} · ${esc(h.v)}</span>`).join("")}</div>
      <div class="meta"><span><b>${changes.length}</b> 次进阶</span></div>
    </article>`;
  }).join("");
  return `<section class="block" id="block-level_axis"><div class="block-head"><h3>境界与等级体系</h3>
    <span class="n">${axes.length}</span></div><div class="block-body"><div class="e-grid">${cards}</div></div></section>`;
}
function milestoneBlock(c){
  const st = snap(c);
  const all = st.events.slice().sort((a, b) => b.chapter - a.chapter);
  /* Type filter over the whole event set. The old block hard-capped at "最近 40 条" with
   * no way to see anything else, which hid 1119 of 1159 events from the reader. */
  const counts = {};
  for (const e of all) counts[e.type || "?"] = (counts[e.type || "?"] || 0) + 1;
  const opts = [["all", "全部", all.length]]
    .concat(Object.keys(counts).sort((a, b) => counts[b] - counts[a])
      .map(k => [k, EVT(k) || "其他", counts[k]]));
  const want = FILTER.milestones || "all";
  const kept = want === "all" ? all : all.filter(e => (e.type || "?") === want);
  const pg = pageSlice("milestones", kept);
  const body = pg.slice.map(e => {
    const who = A(e.participant_ids).map(id => link(id, (ENT.get(id) || {}).name)).join("");
    return `<div class="rel-line"><span class="rt">${esc(prose(e.title))}</span>${tag(EVT(e.type))}
      <span class="span">第 ${esc(e.chapter)} 章</span>
      <div class="mini fb100">${esc(prose(e.description))}</div>
      ${who ? `<div class="chips fb100">${who}</div>` : ""}</div>`;
  }).join("");
  if (!all.length) return block("关键事件", 0, empty("第 " + c + " 章之前没有事件记录", ""));
  return block("关键事件", all.length,
    `<div class="fbrow">${filterChips("milestones", opts, want)}</div>` + body + pager("milestones", pg));
}

/* ------------------------------------------------------------------ *
 * tier 3 — the things that circulate
 * ------------------------------------------------------------------ */
/* Building a block's markup costs far more than deciding whether it changed. The
 * chapter slider fires continuously, and a one-step move usually leaves most blocks
 * untouched — but only the *DOM write* was being skipped, never the string build. So
 * the 96-card grids were re-serialised on every frame for nothing. These caches hold
 * the produced markup and are keyed on a cheap fingerprint of exactly the inputs the
 * block reads, so a key hit is equivalent to a rebuild. */
const MARKUP_CACHE = new Map();
function cachedMarkup(key, produce){
  const hit = MARKUP_CACHE.get(key);
  if (hit !== undefined) return hit;
  const val = produce();
  /* The slider visits a bounded window of chapters; unbounded growth would leak the
   * whole book's markup. */
  if (MARKUP_CACHE.size > 160) MARKUP_CACHE.clear();
  MARKUP_CACHE.set(key, val);
  return val;
}
function fingerprint(parts){
  let h = 2166136261;
  const s = parts.join("\u0001");
  for (let i = 0; i < s.length; i++){
    h ^= s.charCodeAt(i);
    h = Math.imul(h, 16777619);
  }
  return (h >>> 0).toString(36) + ":" + s.length;
}

function thingBlock(c, type){
  const st = snap(c);
  /* Skills, items and concepts all carry a real `first_chapter`, so the appearance
   * filter from `snap()` is already the right gate — the 1st-chapter view shows only
   * what has actually been introduced by then. Do not add a relation-based filter on
   * top: only 40 of the 103 skills have a `learned`/`uses` edge, and requiring one
   * would silently hide the other 63 from the whole page. */
  const rows = st.ent.filter(e => e.type === type);
  if (!rows.length) return "";
  /* Category filter. The controlled vocabulary already assigns every item, skill and
   * concept a category and nothing was reading it, so a 111-item library arrived as one
   * undifferentiated grid. Categories are ranked by size so the chips lead with the ones
   * the reader is most likely to want. */
  /* Three skill rows carry the controlled vocabulary's *rendered repr* rather than a
   * label: `attributes["类别"]` is the string `"['attack', 'summoning']"`, because the
   * extractor stored the Python list without flattening it. Printing that raw is how the
   * reader got `['attack', 'summoning']` sitting next to 外家拳 and 防御术 in the same
   * chip row — mixed Chinese and bare English enum inside one filter.
   *
   * So a category is normalised in two steps: peel the list repr into its members, then
   * translate each member through the `skill_categories` vocabulary. Anything already in
   * Chinese (the other eleven skills, all items, all concepts) passes through untouched,
   * and a member the vocabulary does not know keeps its own text rather than vanishing. */
  const catOf = e => {
    if (!e.attributes) return null;
    let v = e.attributes["类别"] || e.attributes.category;
    if (v == null || v === "") return null;
    /* A real array is the common shape (three skills carry `["attack","summoning"]`);
     * the stringified list repr `"['attack', 'summoning']"` shows up in hand-written
     * fragments. Both have to reduce to the same member list before translation — an
     * earlier revision joined the array to `"attack,summoning"` and returned it
     * untranslated, which is exactly the string the reader was seeing. */
    let parts;
    if (Array.isArray(v)){
      parts = v.map(x => String(x).trim()).filter(Boolean);
    } else {
      const s = String(v).trim();
      const inner = /^\[(.*)\]$/.exec(s);
      parts = inner
        ? inner[1].split(",").map(x => x.trim().replace(/^['"]|['"]$/g, "")).filter(Boolean)
        : [s];
    }
    const group = (G._display_vocabulary || {})[type + "_categories"];
    /* Only translate members the vocabulary actually knows. A member that is already
     * Chinese — 外家拳, 九幽法决 — has no entry and must be kept verbatim; dropping it
     * would empty the chip of the eleven skills that were always fine. */
    const mapped = parts.map(p => (group && group[p]) || p).filter(Boolean);
    return mapped.length ? mapped.join(" · ") : null;
  };
  const catCount = {};
  for (const e of rows){ const k = catOf(e) || "未分类"; catCount[k] = (catCount[k] || 0) + 1; }
  const catOpts = [["all", "全部", rows.length]]
    .concat(Object.keys(catCount).sort((a, b) => catCount[b] - catCount[a] || a.localeCompare(b, "zh"))
      .map(k => [k, k, catCount[k]]));
  const want = (FILTER.things && FILTER.things[type]) || "all";
  const kept = want === "all" ? rows : rows.filter(e => (catOf(e) || "未分类") === want);
  /* Sort. Alphabetical was the only order, which is the right default for looking up a
   * name and the wrong one for browsing — sorted by name a 111-item library opens on a
   * wall of unrelated objects. Chapter order reads as "what has shown up lately", and
   * relation count reads as "what matters to the story", so all three are offered. */
  const sortMode = (FILTER.things && FILTER.things[type + "_sort"]) || "chapter";
  const sorted = kept.slice().sort((a, b) => {
    if (sortMode === "name") return String(a.name).localeCompare(String(b.name), "zh");
    if (sortMode === "degree") return (DEG[b.id] || 0) - (DEG[a.id] || 0)
      || String(a.name).localeCompare(String(b.name), "zh");
    return (b.first_chapter || 0) - (a.first_chapter || 0)
      || String(a.name).localeCompare(String(b.name), "zh");
  });
  /* Only the membership of the row set and each row's own as-of inputs matter. Roles
   * and `learned` edges are filtered by chapter, so their counts have to join the key
   * — otherwise a transfer that happens at chapter N would not repaint. */
  const key = "thing|" + type + "|" + c + "|" + want + "|" + sortMode + "|" + (PAGE[type] | 0) + "|" + fingerprint(sorted.map(e => {
    const roles = (ROLES.get(e.id) || []).filter(r => N(r.valid_from) == null || r.valid_from <= c);
    const learned = type === "skill"
      ? (RELS.get(e.id) || []).filter(r => relActive(r, c) && r.relation_type === "learned").length : 0;
    return e.id + ":" + roles.length + ":" + learned;
  }));
  return cachedMarkup(key, () => {
  const pg = pageSlice(type, sorted);
  const cards = pg.slice.map(e => {
    const roles = (ROLES.get(e.id) || []).filter(r => N(r.valid_from) == null || r.valid_from <= c);
    const owners = roles.filter(r => r.role === "owner" || r.role === "holder")
      .map(r => (ENT.get(r.entity_id) || {}).name).filter(Boolean);
    const skills = type === "skill" ? (RELS.get(e.id) || []).filter(r => relActive(r, c) && r.relation_type === "learned") : [];
    const extra = skills.length ? `<div class="chips">${skills.slice(0, 5).map(r => {
      const who = r.source_id === e.id ? r.target_id : r.source_id;
      return `<span class="chip">${esc((ENT.get(who) || {}).name || who)} 已习得</span>`;
    }).join("")}</div>` : "";
    return `<article class="e-card" data-entity="${esc(e.id)}">
      <span class="bar" style="background:${ZONE_COLOR(type)}"></span>
      <h4 class="nm">${esc(e.name)}<span class="ty">${esc(ETYPE(type))}</span></h4>
      <p class="sm">${esc(prose(e.summary))}</p>
      ${owners.length ? `<div class="chips">${owners.slice(0, 4).map(o => chip(o)).join("")}</div>` : ""}
      ${extra}
      <div class="meta"><span>第 <b>${esc(e.first_chapter ?? "?")}</b> 章出现</span>${roles.length ? `<span><b>${roles.length}</b> 次流转</span>` : ""}</div>
    </article>`;
  }).join("");
  const labels = { item: "法器物品", skill: "法术与技能", concept: "设定与概念" };
  /* The section id matches the stream key (`items`, not `item`) so `repaint("items")` and
   * the rail's `#items` lookup both land on the same node. Carrying a different id here
   * was what let a repaint silently rebuild the wrong element. */
  const key3 = type + "s";
  return `<section class="block" id="block-${esc(key3)}"><div class="block-head"><h3>${esc(labels[type] || ETYPE(type))}</h3>
    <span class="n">${kept.length}${want === "all" ? "" : " / " + rows.length}</span></div><div class="block-body">
    <div class="fbrow">${filterChips("things", catOpts, want, type)}
      ${sortSelect("things", type + "_sort", sortMode,
        [["chapter", "按登场章"], ["degree", "按关系数"], ["name", "按名称"]])}</div>
    <div class="e-grid">${cards}</div>${pager(type, pg)}</div></section>`;
  });
}
function foreshadowBlock(c){
  const st = snap(c);
  if (!st.fsh.length) return "";
  const openCount = st.fsh.filter(f => f.status === "open" || f.status === "suspected").length;
  const counts = {};
  for (const f of st.fsh) counts[f.status || "?"] = (counts[f.status || "?"] || 0) + 1;
  const opts = [["all", "全部", st.fsh.length]]
    .concat(Object.keys(counts).sort((a, b) => counts[b] - counts[a])
      .map(k => [k, FSSTAT(k) || "未标注", counts[k]]));
  const want = FILTER.foreshadow || "all";
  const kept = want === "all" ? st.fsh : st.fsh.filter(f => (f.status || "?") === want);
  const ordered = kept.slice().sort((a, b) => (b.planted_chapter || 0) - (a.planted_chapter || 0));
  const pg = pageSlice("foreshadow", ordered);
  const body = pg.slice.map(f => {
    const done = f.status === "paid_off" || f.status === "resolved";
    return `<div class="rel-line"><span class="rt">${esc(f.label || f.id)}</span>${tag(FSSTAT(f.status), done ? "ok" : "warn")}
      <span class="span">第 ${esc(f.planted_chapter ?? "?")} 章埋</span>
      <div class="mini fb100">原文线索：${esc(prose(f.observation))}</div>
      ${f.interpretation ? `<div class="mini fb100">图谱判读：${esc(prose(f.interpretation))}</div>` : ""}
      </div>`;
  }).join("");
  return block("伏笔 · 尚未回收 " + openCount + " 条", st.fsh.length,
    `<div class="fbrow">${filterChips("foreshadow", opts, want)}</div>` + body + pager("foreshadow", pg));
}
function commitmentBlock(c){
  const st = snap(c);
  if (!st.comm.length) return "";
  const ordered = st.comm.slice().sort((a, b) => (b.created_chapter || 0) - (a.created_chapter || 0));
  const pg = pageSlice("commitments", ordered);
  const rows = pg.slice.map(x => {
    const done = x.resolved_chapter != null && x.resolved_chapter <= c;
    const who = A(x.promisor_ids).concat(A(x.counterparty_ids)).map(id => link(id, (ENT.get(id) || {}).name)).join("");
    return `<div class="rel-line"><span class="rt">${esc(term("commitment_kinds", x.kind, x.kind))}</span>${who}
      ${done ? tag("已了结", "ok") : tag(ESTAT(x.status))}
      ${N(x.deadline_chapter) != null ? tag("期限 第 " + x.deadline_chapter + " 章", "warn") : ""}
      <span class="span">第 ${esc(x.created_chapter ?? "?")} 章立</span>
      <div class="mini fb100">${esc(prose(x.terms))}</div>
      ${done && x.resolution ? `<div class="mini fb100">结局：${esc(prose(x.resolution))}</div>` : ""}</div>`;
  }).join("");
  return block("承诺与约定", st.comm.length, rows + pager("commitments", pg));
}
/* Romance is the one surface the reader asked for by name, and it has two halves that
 * belong together: the routed milestones (first meeting → first flirtation → confirmed
 * → first sex) and the log of individual intimate acts. The earlier version showed only
 * a per-couple act count, which says how much happened but nothing about the shape of
 * the relationship. */
function romanceBlock(c){
  const routes = A(G.romance_routes).filter(r => {
    const seen = N(r.first_meeting_chapter) ?? N(r.ambiguity_started_chapter)
      ?? N(r.confirmed_chapter) ?? N(r.first_sex_chapter);
    return seen == null || seen <= c;
  });
  const st = snap(c);
  const actsOf = (route) => {
    const ids = new Set(A(route.initiator_ids).concat(A(route.recipient_ids),
      [route.character_id, route.protagonist_id]).filter(Boolean));
    if (!ids.size) return [];
    return st.iac.filter(a => {
      const who = A(a.initiator_ids).concat(A(a.recipient_ids));
      return who.some(x => ids.has(x)) && (N(a.chapter) == null || a.chapter <= c);
    });
  };
  const card = (r) => {
    const other = ENT.get(r.character_id === (M.metadata.protagonists || [])[0] ? r.protagonist_id : r.character_id)
      || ENT.get(r.character_id) || ENT.get(r.protagonist_id);
    const acts = actsOf(r);
    const marks = [
      ["首次相遇", r.first_meeting_chapter],
      ["首次亲密／暧昧", r.ambiguity_started_chapter],
      ["关系确认", r.confirmed_chapter],
      ["首次明确性关系", r.first_sex_chapter],
    ];
    /* Only the milestones that have actually happened by this chapter: a "截至第 N 章"
     * panel that shows a later chapter's milestone would leak the future. */
    const shown = marks.filter(x => N(x[1]) != null && x[1] <= c);
    const pending = marks.filter(x => N(x[1]) == null || x[1] > c).map(x => x[0]);
    return `<div class="romance-card" data-entity="${esc((other || {}).id || r.character_id || "")}">
      <h4 class="nm">${esc((other || {}).name || "未命名")}${tag(RS(r.status), r.status === "confirmed" ? "ok" : "warn")}</h4>
      <div class="meta">${esc(RIB(r.inclusion_basis) || "")}
        ${r.consent_context ? " · " + esc(CC(r.consent_context)) : ""}</div>
      <div class="ms">${shown.map(x => `<span class="ms-i"><b>第 ${esc(x[1])} 章</b>${esc(x[0])}</span>`).join("")}</div>
      ${acts.length ? `<div class="chips mt6">${acts.slice(0, 4).map(a =>
          `<span class="chip">第 ${esc(a.chapter)} 章 · ${esc(IAT(a.act_type))}</span>`).join("")}
        ${acts.length > 4 ? `<span class="chip">另有 ${acts.length - 4} 次</span>` : ""}</div>` : ""}
      ${pending.length ? `<div class="mini fb100">尚未发生：${esc(pending.join("、"))}</div>` : ""}
    </div>`;
  };
  const rows = routes.slice().sort((a, b) =>
    (N(b.confirmed_chapter) ?? 0) - (N(a.confirmed_chapter) ?? 0)
    || (N(b.ambiguity_started_chapter) ?? 0) - (N(a.ambiguity_started_chapter) ?? 0));
  if (!rows.length && !st.iac.length) return "";
  /* Status filter, because "which of these are actually confirmed" is the first question
   * a 71-route list raises and the answer is not visible from the cards alone. */
  const counts = {};
  for (const r of rows) counts[r.status || "?"] = (counts[r.status || "?"] || 0) + 1;
  const opts = [["all", "全部", rows.length]]
    .concat(Object.keys(counts).sort().map(k => [k, RS(k) || "未标注", counts[k]]));
  const want = FILTER.romance;
  const kept = want === "all" ? rows : rows.filter(r => (r.status || "?") === want);
  const pg = pageSlice("romance", kept);
  return block("感情线 · 截至第 " + c + " 章", rows.length,
    `<div class="fbrow">${filterChips("romance", opts, want)}</div>`
    + `<div class="romance-grid">${pg.slice.map(card).join("")}</div>` + pager("romance", pg));
}
function intimacyBlock(c){
  const st = snap(c);
  if (!st.iac.length) return "";
  const byRoute = new Map();
  for (const a of st.iac){
    const who = A(a.initiator_ids).concat(A(a.recipient_ids));
    const key = who.slice().sort().join("＋") || "其他";
    if (!byRoute.has(key)) byRoute.set(key, []);
    byRoute.get(key).push(a);
  }
  /* Paginated over pairs, not over individual acts. The block answers "who is involved
   * with whom and how often", so a pair is one row; 116 acts collapse to ~30 pairs and
   * paging 30 rows is manageable where paging 116 undifferentiated acts is not. */
  const pairs = [...byRoute.entries()].sort((a, b) => b[1].length - a[1].length);
  const pg = pageSlice("intimacy", pairs);
  const cards = pg.slice.map(entry => {
      const names = entry[1][0] ? A(entry[1][0].initiator_ids).concat(A(entry[1][0].recipient_ids))
        .filter(id => ENT.has(id)).map(id => ENT.get(id).name).join("、") : entry[0];
      const last = entry[1].slice().sort((a, b) => b.chapter - a.chapter)[0];
      return `<div class="milestone"><span class="k">${esc(names)}</span>
        <span class="v">${entry[1].length} 次记录</span>
        <span class="k mt4">最近：第 ${last.chapter} 章 · ${esc(IAT(last.act_type))}</span></div>`;
    }).join("");
  return block("亲密记录 · 截至第 " + c + " 章", st.iac.length,
    `<div class="milestone-grid">${cards}</div>` + pager("intimacy", pg));
}
function issueBlock(c){
  const rows = A(G.review_issues).filter(i => N(i.chapter) == null || i.chapter <= c);
  if (!rows.length) return "";
  const sev = { warning: "warn", info: "", low: "", uncertain: "warn" };
  /* Filter by severity. The block is the honest account of what the graph still doubts,
   * so the reader needs to be able to isolate the warnings — 386 rows sorted by chapter
   * buries the twelve that actually matter. */
  const sevCount = {};
  for (const i of rows){ const k = i.severity || "?"; sevCount[k] = (sevCount[k] || 0) + 1; }
  const opts = [["all", "全部", rows.length]]
    .concat(Object.keys(sevCount).sort((a, b) => sevCount[b] - sevCount[a])
      .map(k => [k, ISEV(k) || "未分级", sevCount[k]]));
  const want = FILTER.issues || "all";
  const kept = want === "all" ? rows : rows.filter(i => (i.severity || "?") === want);
  const ordered = kept.slice().sort((a, b) => (b.chapter || 0) - (a.chapter || 0));
  const pg = pageSlice("issues", ordered);
  const body = pg.slice.map(i => {
    const related = A(i.related_ids).filter(id => ENT.has(id)).slice(0, 4)
      .map(id => link(id, ENT.get(id).name)).join("");
    /* `category` is a free-text field with ~190 distinct values across fragments;
     * the vocabulary covers only the nine recommended ones. Anything unmapped is an
     * internal slug and must not reach the reader, so fall back to "待核" rather than
     * printing the machine key. */
    const cat = ((G._display_vocabulary || {}).issue_categories || {})[i.category];
    return `<div class="rel-line">${tag(ISEV(i.severity), sev[i.severity] || "")}
      <span class="rt">${esc(cat || "待核")}</span>
      ${N(i.chapter) != null ? `<span class="span">第 ${i.chapter} 章</span>` : ""}
      <div class="mini fb100">${esc(issueText(i.description))}</div>
      ${related ? `<div class="chips fb100">${related}</div>` : ""}</div>`;
  }).join("");
  return block("待人工核对事项", rows.length,
    `<div class="fbrow">${filterChips("issues", opts, want)}</div>` + body + pager("issues", pg));
}

/* ------------------------------------------------------------------ *
 * page assembly — one vertical stream in the order the data nests
 * ------------------------------------------------------------------ */
function tierHead(tag, title, hint){
  return `<div class="tier"><span class="tag">${esc(tag)}</span><h2>${esc(title)}</h2><span class="hint">${esc(hint)}</span></div>`;
}
function render(c){
  S.chapter = c;
  const st = snap(c);
  const host = document.getElementById("stream");

  /* Sectioned update instead of one innerHTML swap. Replacing 55 000 characters of
   * DOM on every slider tick costs ~300 ms, and almost none of it changes: the level
   * axes, the item/skill/concept libraries and the static prose barely move between
   * chapters. Each block is rebuilt only when its own markup string changes. */
  const sections = streamSections(st, c);

  const graphHost = document.getElementById("graph");
  const graphWasLive = graphHost && graphHost.contains(document.getElementById("cy"));

  for (let i = 0; i < sections.length; i++){
    const key = sections[i][0];
    const markup = sections[i][1] || "";
    let node = document.getElementById(key);
    if (!node){
      node = document.createElement("div");
      node.id = key;
      node.className = "sec";
      host.appendChild(node);
      node.dataset.sig = "\u0000";
    }
    /* Position matters: the stream is ordered, so a section that appeared later must
     * be moved after its predecessor. */
    const prev = i > 0 ? document.getElementById(sections[i - 1][0]) : null;
    if (prev && prev.nextSibling !== node) host.insertBefore(node, prev.nextSibling);
    /* An empty result must still clear the node. Skipping it left the previous
     * chapter's markup in place — a 1st-chapter view showed all 103 skills because
     * `thingBlock` returned "" and the earlier content was never removed. */
    if (node.dataset.sig === markup) continue;
    node.dataset.sig = markup;
    node.innerHTML = markup;
  }

  wire(c);
  buildRail();
  /* Rebuilding 420 nodes on every slider tick costs ~130 ms and the reader cannot
   * see the graph while scrubbing past it anyway. Defer the rebuild to the moment
   * the graph actually enters the viewport. */
  scheduleGraph(c, graphWasLive);
  if (S.sel && ENT.has(S.sel)) showEntity(S.sel);
}

/* The stream's blocks, in page order. Split out of `render()` so the router can repaint
 * the same stream when it returns home without duplicating the list. */
function streamSections(st, c){
  return [
    ["T1", tierHead("T1", "全书", "章节 · 节奏 · 规则 · 覆盖")],
    ["stat", statStrip(c)],
    ["chapters", chapterStream(c)],
    ["rhythm", rhythmBlock(c)],
    ["coverage", coverageBlock(c)],
    ["rules", rulesBlock(c)],
    ["T2", tierHead("T2", "主体", "人物 · 势力 · 生灵 · 境界体系，各自下挂自己的记录")],
    ["graph", graphBlockMarkup(st, c)],
    ["levels", levelBlock(c)],
    ["agents", agentLibrary(c)],
    ["milestones", milestoneBlock(c)],
    ["T3", tierHead("T3", "流转物", "法器 · 法术 · 设定，以及它们在主体之间转移的时间线")],
    ["items", thingBlock(c, "item")],
    ["skills", thingBlock(c, "skill")],
    ["concepts", thingBlock(c, "concept")],
    ["TAIL", tierHead("附", "未决与校验", "图谱自认还需要人判断的地方")],
    ["romance", romanceBlock(c)],
    ["foreshadow", foreshadowBlock(c)],
    ["commitments", commitmentBlock(c)],
    ["intimacy", intimacyBlock(c)],
    ["issues", issueBlock(c)],
  ];
}
function graphBlockMarkup(st, c){
  const modes = GRAPH_MODES.map(m => `<button class="gmode" data-gmode="${esc(m[0])}"`
    + `${m[0] === GMODE ? ' aria-pressed="true"' : ""}>${esc(m[1])}</button>`).join("");
  return `<section class="block" id="block-graph"><div class="block-head"><h3>关系图谱</h3><span class="n">${st.rels.length}</span>
    <div class="right"><span class="gmodes">${modes}</span>
    <button class="chip" id="g-fit">全图</button>
    <button class="chip" id="g-hero">只看主角</button></div></div>
    <div class="block-body tight"><div class="graph-wrap">
      <svg id="radar" aria-hidden="true"></svg>
      <div id="cy"></div>
      <div class="zone-legend" id="zone-legend"></div></div>
      <div class="mini mt8" id="g-hint"></div>
    </div></section>`;
}

/* Repaint the home stream after a route change. `paintStream` is the counterpart to
 * `paintPage`: the router swaps between the two, and both must leave the DOM consistent
 * because the reader can come back at any time. */
function paintStream(){
  const host = document.getElementById("stream");
  if (host) host.innerHTML = "";
  render(S.chapter);
}

/* ------------------------------------------------------------------ *
 * subject pages
 *
 * Each page answers the same question in a different shape: *what has this thing been
 * involved in, and when*. The stream is a chapter-ordered view of the whole book; a page
 * is a subject-ordered view of the same evidence. Both read the same indexes, so they can
 * never disagree about a fact — only about its arrangement.
 *
 * Every row that names another subject is a link to that subject's page. That is what
 * turns 980 records into something walkable: land on 秦朝, follow 阴阳铃 to the object's
 * own page, follow its 持有者 to 罗德, follow his 势力 to 罗刹门, and the browser's Back
 * button retraces the whole path because each step is a real route.
 * ------------------------------------------------------------------ */
function pageShell(kind, title, sub, chipsHtml, bodyHtml, rightHtml){
  const tier = PAGE_TIER[kind];
  const tierName = tier === 2 ? "主体" : tier === 3 ? "流转物" : "记录";
  return `<div class="pg-head">
      <div class="pg-crumb"><a href="#/">总览</a>
        <span>/</span><a href="#/index/${esc(kind)}">${esc(PAGE_NOUN[kind] || kind)}索引</a>
        <span>/</span><b>${esc(title)}</b></div>
      <div class="pg-title">
        <h1>${esc(title)}</h1>
        <div class="pg-tags">${chipsHtml || ""}</div>
        ${rightHtml || ""}
      </div>
      ${sub ? `<p class="pg-sub">${sub}</p>` : ""}
    </div>
    <div class="pg-body">${bodyHtml}</div>`;
}

/* Chapter range a subject appears in, for the header line. */
function activeSpan(ids, c){
  const chs = A(ids).map(i => N(i)).filter(v => v != null && v <= c).sort((a, b) => a - b);
  if (!chs.length) return null;
  return [chs[0], chs[chs.length - 1]];
}

function relatedRows(ids, c, limit){
  return A(ids).slice(0, limit).map(id => {
    const e = ENT.get(id);
    if (!e) return esc(id);
    const live = appears(e, c);
    return `<a class="lref" href="${esc(entityHref(id) || "#/")}"${live ? "" : ' data-hidden="1"'}>${esc(e.name)}</a>`;
  }).join("");
}

/* Events a subject took part in, newest first. `participant_ids` is on every one of the
 * 1159 events, which is what makes this list complete rather than best-effort. */
function eventsFor(id, c){
  return A(G.events).filter(e => N(e.chapter) != null && e.chapter <= c
    && A(e.participant_ids).includes(id)).sort((a, b) => b.chapter - a.chapter);
}
/* Events whose TEXT names the subject, minus the ones it already participates in.
 *
 * This exists because `eventsFor()` reads one field and the page reported the emptiness
 * of that field as emptiness of the record. MEASURED: `location` entities appear in
 * `participant_ids` 0 times across 1159 events, yet 323 event bodies name a location;
 * `skill` is 0 and 658. 764 of 1159 events mention a sparse-type entity that is not in
 * `participant_ids`.
 *
 * Deduplicated against participation so the two sections never show the same event twice,
 * and deliberately NOT merged into one list: "was there" and "was named in the account of
 * it" are different claims, and this workspace's rule is that a reader must be able to
 * tell them apart. */
function eventsMentioning(id, c, exclude){
  const skip = exclude || new Set();
  return A(MENTIONS.get(id)).filter(e => N(e.chapter) != null && e.chapter <= c && !skip.has(e.id))
    .sort((a, b) => b.chapter - a.chapter);
}
/* A mention row carries the people who WERE at the event, as links. The event page is
 * reachable either way, but a sparse entity page that only lists titles is a dead end:
 * the reader has to open each one to find out who it was about. Doing it here keeps the
 * subject page answering "what happened around this thing" in one screen. */
function mentionRow(e, c, subjectId){
  const names = A(e.participant_ids)
    .filter(id => id !== subjectId)
    .map(id => ENT.get(id)).filter(Boolean).slice(0, 4);
  const extra = A(e.participant_ids).filter(id => id !== subjectId).length - names.length;
  /* How did this row match? `MENTION_HOW` was filled by the span-claiming pass. Showing
   * the literal name is not decoration: this whole section is an INFERENCE from a string
   * match, and an inference presented with the same weight as a recorded fact is exactly
   * the failure mode this round is about. A shared name is flagged because 「残心剑阵」
   * belongs to both a skill and an item, so both pages would otherwise claim the event. */
  const how = A(MENTION_HOW.get(subjectId)).find(x => x && x.ev === e.id);
  const via = how ? `<i class="ev-via${how.shared ? " shared" : ""}"${
    how.shared ? ` title="「${esc(how.name)}」同时也是其他主体的名称"` : ""}>${
    how.primary ? "" : "别名 "}${esc(how.name)}${how.shared ? " ⚠共有名" : ""}</i>` : "";
  return `<a class="ev-row ev-mention" href="#/event/${encodeURIComponent(e.id)}">
      <span class="ev-ch">第 ${esc(e.chapter)} 章</span>
      <span class="ev-t">${esc(e.title || e.description || e.id)}</span>
      <span class="ev-k">${esc(term("event_types", e.type, e.type))}${via}</span>
      <span class="ev-who">${names.map(n =>
        `<i class="ev-w" data-goto="${esc(n.id)}">${esc(n.name)}</i>`).join("")}${
        extra > 0 ? `<i class="ev-w-more">等 ${esc(A(e.participant_ids).length)} 人</i>` : ""}</span></a>`;
}
function eventRow(e, c){
  const others = A(e.participant_ids).length;
  return `<a class="ev-row" href="#/event/${encodeURIComponent(e.id)}">
      <span class="ev-ch">第 ${esc(e.chapter)} 章</span>
      <span class="ev-t">${esc(e.title || e.description || e.id)}</span>
      <span class="ev-k">${esc(term("event_types", e.type, e.type))}</span>
      <span class="ev-n">${others} 人参与</span></a>`;
}
/* Hard truncation used to be the end of the road: `共 1043 条，另有 1003 条未列出。` and
 * no way to see the other 1003. On the protagonist's page that sentence stood for 96% of
 * the section. Truncation is still right as the *default* — 1043 rows would make the page
 * unusable — but it has to be a fold, not a wall. The first slice is whatever the caller
 * already decided to render as the visible sample; this wraps it with the rest kept in the
 * DOM and toggled, so expanding costs no re-render and the count stays honest. */
let FOLD_ID = 0;
function foldable(headHtml, restHtml, total, shown, what){
  if (!restHtml) return headHtml;
  const id = "fold-" + (FOLD_ID++);
  const more = total - shown;
  return headHtml
    + `<div class="fold-rest" id="${id}" hidden>${restHtml}</div>`
    + `<div class="fold-ctl"><button type="button" class="fold-btn" data-fold="${id}"
        data-open="展开其余 ${more} ${esc(what || "条")}"
        data-shut="收起这 ${more} ${esc(what || "条")}"
        aria-expanded="false" aria-controls="${id}">展开其余 ${more} ${
        esc(what || "条")}</button></div>`;
}
/* The catch-all has no honest count — it is every record the sections above did not claim —
 * so it gets fixed labels instead of the counted ones. */
function foldBlock(innerHtml, id, openLabel, shutLabel){
  return `<div class="fold-rest" id="${id}" hidden>${innerHtml}</div>`
    + `<div class="fold-ctl"><button type="button" class="fold-btn" data-fold="${id}"
        data-open="${esc(openLabel)}" data-shut="${esc(shutLabel)}"
        aria-expanded="false" aria-controls="${id}">${esc(openLabel)}</button></div>`;
}
function eventList(rows, c, limit, emptyHint){
  if (!rows.length) return `<p class="pg-empty">${esc(emptyHint || "图谱中没有记录到相关剧情。")}</p>`;
  const show = limit ? rows.slice(0, limit) : rows;
  const head = `<div class="ev-list">${show.map(e => eventRow(e, c)).join("")}</div>`;
  if (!limit || rows.length <= limit) return head;
  const rest = rows.slice(limit).map(e => eventRow(e, c)).join("");
  return foldable(head, rest, rows.length, show.length, "条");
}

/* A table of contents built from the sections the page actually emitted, rather than from
 * a hand-written list. A hand-written one drifts: it would keep offering 「关系」 on a page
 * whose subject has none, and it would miss any section added later. Reading the headings
 * back means the contents are wrong only if the page itself is. */
function pageToc(sections){
  const found = [];
  for (const html of sections){
    const m = /<section class="pblock" id="([^"]+)"><h2>([^<]+)(?:<span class="n">(\d+)<\/span>)?/.exec(html);
    if (m) found.push([m[1], m[2].trim(), m[3] || ""]);
  }
  if (found.length < 3) return "";
  return `<nav class="page-toc" aria-label="本页目录">`
    + found.map(([id, label, n]) =>
        `<a href="#${esc(id)}" data-toc="${esc(id)}">${esc(label)}${
          n ? `<b>${esc(n)}</b>` : ""}</a>`).join("")
    + `</nav>`;
}

/* Item roles involving an entity, as-of `c`. The four roles are kept apart because
 * "owns", "holds", "uses" and "keeps" are different facts and merging them would lose
 * exactly the distinction the workflow asks for. */
function rolesFor(id, c){
  return A(G.item_roles).filter(r => (r.entity_id === id || r.item_id === id)
    && (N(r.valid_from) == null || r.valid_from <= c));
}

/* Relations touching a subject, grouped by type so a page reads as a map of that
 * subject's world rather than an undifferentiated edge dump. */
function relationsFor(id, c){
  return A(G.relations).filter(r => (r.source_id === id || r.target_id === id) && relActive(r, c));
}

function pageEntity(route){
  const e = ENT.get(route.id);
  if (!e) return pageMissing("找不到这个主体", route.id);
  const c = S.chapter;
  const isAgent = isAgentEntity(e);
  const span = activeSpan([e.first_chapter], c);
  const chips = [
    tag(PAGE_NOUN[route.kind] || ETYPE(e.type)),
    e.first_chapter != null ? tag(`第 ${e.first_chapter} 章登场`) : "",
    A(e.aliases).length ? tag(`${A(e.aliases).length} 个称呼`) : "",
    (DEG.get(e.id) || 0) ? tag(`${DEG.get(e.id)} 条关系`) : "",
  ].filter(Boolean).join("");

  const events = eventsFor(e.id, c);
  const rels = relationsFor(e.id, c);
  const roles = rolesFor(e.id, c);

  const header = pageShell(route.kind, e.name, esc(prose(e.summary)), chips, "", "");
  const body = [];

  /* 1 — the relation map, drawn for this subject alone. */
  if (rels.length){
    body.push(`<section class="pblock" id="sec-net"><h2>关系网络<span class="n">${rels.length}</span></h2>
      <div class="pg-graph"><div id="pg-cy"></div>
      <div class="zone-legend" id="pg-legend"></div></div>
      <div class="mini mt8">以 ${esc(e.name)} 为中心分层展开，层级即关系距离。点任意节点进入它的页面。</div>
      </section>`);
  }

  /* 2 — the four role tracks, only when the subject is a thing or handles one. */
  if (roles.length){
    const LABEL = { owner: "所有者", holder: "持有者", user: "使用者", custodian: "保管者" };
    const groups = new Map();
    for (const r of roles){
      const other = r.entity_id === e.id ? r.item_id : r.entity_id;
      const role = r.entity_id === e.id ? r.role : "被" + (LABEL[r.role] || r.role);
      const k = role;
      if (!groups.has(k)) groups.set(k, []);
      groups.get(k).push({ r, other });
    }
    const cards = [...groups.entries()].map(([k, list]) => `<div class="pcard">
        <h3>${esc(k)}<span class="n">${list.length}</span></h3>
        ${list.slice(0, 12).map(({ r, other }) => {
          const oe = ENT.get(other);
          const nm = oe ? `<a class="lref" href="${esc(entityHref(other) || "#/")}">${esc(oe.name)}</a>` : esc(other);
          return `<div class="prow"><span class="when">${r.valid_from != null ? chLink(r.valid_from) : "—"}</span>
            <span class="what">${nm}</span>
            <span class="why">${esc(prose(r.description || ""))}</span></div>`;
        }).join("")}
      </div>`).join("");
    body.push(`<section class="pblock" id="sec-roles"><h2>流转与使用</h2><div class="pcards">${cards}</div></section>`);
  }

  /* 3 — the level ladder and every other recorded change, as-of now. */
  const changes = (CHANGES.get(e.id) || []).filter(s => s.chapter <= c);
  if (changes.length){
    const byFacet = new Map();
    for (const s of changes){
      const k = s.facet === "level" && s.target_id && ENT.get(s.target_id)
        ? ENT.get(s.target_id).name : FACET(s.facet);
      if (!byFacet.has(k)) byFacet.set(k, []);
      byFacet.get(k).push(s);
    }
    const cards = [...byFacet.entries()].map(([k, list]) => {
      const rows = list.slice().sort((a, b) => b.chapter - a.chapter);
      const isLv = list[0].facet === "level";
      const row = s => {
        const val = isLv ? `${esc(lvText(s.before) || "?")} → <b>${esc(lvText(s.after) || "?")}</b>`
          : `${esc(attrText(s.before) || "—")} → <b>${esc(attrText(s.after) || "—")}</b>`;
        return `<div class="prow"><span class="when">${chLink(s.chapter)}</span>
          <span class="what">${val}</span>
          <span class="why">${esc(prose(s.reason || ""))}</span></div>`;
      };
      const head = rows.slice(0, 10).map(row).join("");
      const rest = rows.slice(10).map(row).join("");
      return `<div class="pcard"><h3>${esc(k)}<span class="n">${list.length}</span></h3>`
        + head + foldable("", rest, rows.length, 10, "条变化") + `</div>`;
    }).join("");
    body.push(`<section class="pblock" id="sec-changes"><h2>状态变化<span class="n">${changes.length}</span>
      <span class="hint">截至第 ${c} 章</span></h2><div class="pcards">${cards}</div></section>`);
  }

  /* 4 — traits, grouped the same way the drawer groups them. */
  const traits = (TRAITS.get(e.id) || []).filter(t => t.chapter <= c)
    .slice().sort((a, b) => b.chapter - a.chapter);
  if (traits.length){
    const groups = new Map();
    for (const t of traits){ if (!groups.has(t.facet)) groups.set(t.facet, []); groups.get(t.facet).push(t); }
    const cards = [...groups.entries()].map(([k, list]) => `<div class="pcard">
        <h3>${esc(FACET(k))}<span class="n">${list.length}</span></h3>
        ${list.slice(0, 8).map(t => `<div class="prow"><span class="when">${chLink(t.chapter)}</span>
          <span class="why">${esc(prose(t.statement))}</span></div>`).join("")}
      </div>`).join("");
    body.push(`<section class="pblock" id="sec-traits"><h2>人物特征<span class="n">${traits.length}</span></h2>
      <div class="pcards">${cards}</div></section>`);
  }

  /* 5 — relations grouped by kind, each row naming the other side as a link. */
  if (rels.length){
    const groups = new Map();
    for (const r of rels){
      if (!groups.has(r.relation_type)) groups.set(r.relation_type, []);
      groups.get(r.relation_type).push(r);
    }
    const cards = [...groups.entries()].sort((a, b) => b[1].length - a[1].length)
      .map(([k, list]) => {
        const row = r => {
          const oid = r.source_id === e.id ? r.target_id : r.source_id;
          const oe = ENT.get(oid);
          const span2 = (() => { const t = relEnd(r);
            return (t != null && t !== 0) ? `第 ${r.valid_from}–${t} 章` : `第 ${r.valid_from} 章起`; })();
          return `<div class="prow"><span class="when">${esc(span2)}</span>
            <span class="what">${oe ? `<a class="lref" href="${esc(entityHref(oid) || "#/")}">${esc(oe.name)}</a>` : esc(oid)}</span>
            <span class="why">${esc(prose(r.description || ""))}</span></div>`;
        };
        const head = list.slice(0, 10).map(row).join("");
        const rest = list.slice(10).map(row).join("");
        return `<div class="pcard"><h3>${esc(RELT(k))}<span class="n">${list.length}</span></h3>`
          + head + foldable("", rest, list.length, 10, "条") + `</div>`;
      }).join("");
    body.push(`<section class="pblock" id="sec-rel"><h2>关系<span class="n">${rels.length}</span></h2>
      <div class="pcards">${cards}</div></section>`);
  }

  /* 6 — the events, which is the question a page exists to answer. */
  body.push(`<section class="pblock" id="sec-events"><h2>参与剧情<span class="n">${events.length}</span>
    <span class="hint">截至第 ${c} 章</span></h2>${eventList(events, c, 40)}</section>`);

  /* 6b — the events whose text names the subject but which do not list it as a
   * participant. Same defect class as the grey nodes and the 7px shapes: the renderer
   * trusted one field and read its emptiness as the absence of a fact. Only shown when
   * it carries more than participation does, so a protagonist page stays readable. */
  const partIds = new Set(events.map(x => x.id));
  const mentioned = eventsMentioning(e.id, c, partIds);
  if (mentioned.length > events.length){
    const mHead = mentioned.slice(0, 30).map(x => mentionRow(x, c, e.id)).join("");
    const mRest = mentioned.slice(30).map(x => mentionRow(x, c, e.id)).join("");
    body.push(`<section class="pblock" id="sec-mention"><h2>正文提及<span class="n">${mentioned.length}</span>
      <span class="hint">剧情正文写到 ${esc(e.name)}，但未把它列为参与主体</span></h2>
      <div class="ev-list">${mHead}</div>${foldable("", mRest, mentioned.length, 30, "条")}
      <div class="mini mt8">这一类与「参与剧情」不是同一件事：参与是抽取时登记的主体，
      正文提及只是名字出现在这场剧情的记述里。</div></section>`);
  }

  /* 7 — attributes, because they are the least time-bound, then the raw dump. */
  const attrs = Object.entries(e.attributes || {}).filter(([, v]) => v != null && v !== "");
  if (attrs.length){
    body.push(`<section class="pblock" id="sec-attr"><h2>固定属性<span class="n">${attrs.length}</span></h2>
      <div class="attr-grid">${attrs.map(([k, v]) =>
        `<div class="attr"><span class="k">${esc(k)}</span><span class="v">${esc(attrText(v))}</span></div>`)
        .join("")}</div></section>`);
  }
  /* 7b — subject tags. MEASURED: this field was never rendered, so its five English
   * values were never translated either — the leak and the omission were the same
   * omission. Rendering it is what makes the vocabulary entry load-bearing rather than
   * decorative: a `entity_tags` entry with no call site is a table that cannot fail.
   *
   * `data-tag` carries the *raw* tag so the acceptance gate can assert the translation
   * actually happened, instead of asserting that a Chinese string is present somewhere
   * on a Chinese page — which is true whether or not the mapping ran. */
  const tags = A(e.tags).filter(t => t != null && String(t).trim() !== "");
  if (tags.length){
    body.push(`<section class="pblock" id="sec-tags"><h2>主题标签<span class="n">${tags.length}</span></h2>
      <div class="tag-row">${tags.map(t =>
        `<span class="tag-chip" data-tag="${esc(String(t))}">${esc(TAGV(String(t)))}</span>`).join("")}</div>
      <div class="mini mt8">标签是抽取时按主体归拢的关联主题，与上面的「固定属性」不同：
      属性写的是它本身是什么，标签写的是它跟哪些线索有关。</div></section>`);
  }
  /* The catch-all used to be one unlabelled 80,000-character block — 83% of this page —
   * with no way to find anything inside it and nothing to say what it contained. It is
   * still the catch-all, because it is what guarantees nothing is dropped, but it is
   * folded by default and labelled with what it holds, so the sections above are the
   * page and this is the appendix. */
  if (isAgent){
    const inner = entityBody(e, c);
    body.push(`<section class="pblock" id="sec-full"><h2>完整档案
      <span class="hint">下面各节的原始汇总，含未单独成节的记录</span></h2>`
      + foldBlock(`<div class="embed">${inner}</div>`, "fold-full",
                  "展开全部记录", "收起全部记录") + `</section>`);
  }

  return header.replace("</div>\n    <div class=\"pg-body\">", "</div><div class=\"pg-body\">")
    + pageToc(body) + body.join("");
}

function pageEvent(route){
  const ev = A(G.events).find(x => x.id === route.id);
  if (!ev) return pageMissing("找不到这段剧情", route.id);
  const c = S.chapter;
  const parts = A(ev.participant_ids).map(id => ENT.get(id)).filter(Boolean);
  const rels = A(G.relations).filter(r => A(r.evidence_ids).some(e => A(ev.evidence_ids).includes(e)));
  const chips = [
    tag(term("event_types", ev.type, ev.type)),
    ev.chapter != null ? tag(`第 ${ev.chapter} 章`) : "",
    parts.length ? tag(`${parts.length} 位参与者`) : "",
  ].filter(Boolean).join("");
  const body = [];

  /* Who, where, with what — the "全要素清单" the reader asked for, and the reason a
   * single event needs a page: four different record kinds meet here. */
  /* `ev.location_id` is a gap of its own: MEASURED 496 of 1,159 events (42.8%) record where
   * they happened, and this builder never read the field — it derived a location from each
   * participant's state instead, which yields nothing for a scene whose actors have no
   * location on record. The recorded field leads; the derived rows follow. */
  const evLoc = ev.location_id ? ENT.get(ev.location_id) : null;
  const places = parts.map(p => ({ p, loc: stateAt(p.id, ["location"], ev.chapter || c) }))
    .filter(x => x.loc && (x.loc.after || x.loc.before));
  const uses = [];
  for (const r of A(G.item_roles)){
    if (ev.chapter == null || N(r.valid_from) == null || r.valid_from > ev.chapter) continue;
    if (A(ev.participant_ids).includes(r.entity_id)) uses.push(r);
  }
  const facts = `<div class="pcards">
    <div class="pcard"><h3>参与者<span class="n">${parts.length}</span></h3>
      ${parts.map(p => `<div class="prow"><span class="what"><a class="lref" href="${esc(entityHref(p.id) || "#/")}">${esc(p.name)}</a></span>
        <span class="why">${esc(PAGE_NOUN[ROUTE_TYPE[p.type]] || ETYPE(p.type))}${p.role ? " · " + esc(p.role) : ""}</span></div>`).join("")
        || '<p class="pg-empty">无</p>'}</div>
    ${(evLoc || places.length) ? `<div class="pcard"><h3>发生地点<span class="n">${(evLoc ? 1 : 0) + places.length}</span></h3>
      ${evLoc ? `<div class="prow"><span class="what">${entLink(ev.location_id)}</span>
        <span class="why">这场剧情的记录地点</span></div>` : ""}
      ${places.map(({ p, loc }) => {
        const lid = loc.after && loc.after.entity_id ? loc.after.entity_id : (loc.after && loc.after.value);
        const le = lid && ENT.get(lid);
        return `<div class="prow"><span class="what">${le ? `<a class="lref" href="${esc(entityHref(lid) || "#/")}">${esc(le.name)}</a>` : esc(attrText(loc.after || loc.before))}</span>
          <span class="why">${esc(p.name)} 当时所在</span></div>`;
      }).join("")}</div>` : ""}
    ${uses.length ? `<div class="pcard"><h3>涉及物品与技能<span class="n">${uses.length}</span></h3>
      ${uses.slice(0, 14).map(r => {
        const oe = ENT.get(r.item_id);
        return `<div class="prow"><span class="what">${oe ? `<a class="lref" href="${esc(entityHref(r.item_id) || "#/")}">${esc(oe.name)}</a>` : esc(r.item_id)}</span>
          <span class="why">${esc({owner: "所有者", holder: "持有者", user: "使用者", custodian: "保管者"}[r.role] || r.role)}：${esc((ENT.get(r.entity_id) || {}).name || r.entity_id)}</span></div>`;
      }).join("")}</div>` : ""}
    ${rels.length ? `<div class="pcard"><h3>同源记录<span class="n">${rels.length}</span></h3>
      ${rels.slice(0, 10).map(r => {
        const a = ENT.get(r.source_id), b = ENT.get(r.target_id);
        return `<div class="prow"><span class="what">${a ? `<a class="lref" href="${esc(entityHref(r.source_id) || "#/")}">${esc(a.name)}</a>` : esc(r.source_id)}
         → ${b ? `<a class="lref" href="${esc(entityHref(r.target_id) || "#/")}">${esc(b.name)}</a>` : esc(r.target_id)}</span>
          <span class="why">${esc(RELT(r.relation_type))}</span></div>`;
      }).join("")}</div>` : ""}
  </div>`;
  body.push(`<section class="pblock" id="ev-facts"><h2>全要素清单</h2>${facts}</section>`);

  const desc = prose(ev.description || "");
  if (desc) body.push(`<section class="pblock" id="ev-story"><h2>经过</h2><p class="pg-prose">${esc(desc)}</p></section>`);

  /* The evidence, so the claim is checkable from the page itself. */
  const quotes = evLine(ev.evidence_ids, 8);
  if (quotes) body.push(`<section class="pblock" id="ev-evidence"><h2>原文证据<span class="n">${evCount(ev.evidence_ids)}</span></h2>
    <div class="quotes">${quotes}</div></section>`);

  /* Cause and effect by chapter proximity plus explicit `cause_event_id`, which is the
   * only link the graph records between two events. */
  const causes = A(G.state_changes).filter(s => s.cause_event_id === ev.id);
  if (causes.length){
    body.push(`<section class="pblock" id="ev-changes"><h2>这场剧情造成的改变<span class="n">${causes.length}</span></h2>
      <div class="pcards"><div class="pcard">
      ${causes.slice(0, 12).map(s => {
        const who = ENT.get(s.entity_id);
        return `<div class="prow"><span class="what">${who ? `<a class="lref" href="${esc(entityHref(s.entity_id) || "#/")}">${esc(who.name)}</a>` : esc(s.entity_id)}</span>
          <span class="why">${esc(FACET(s.facet))}：${esc(attrText(s.before) || "—")} → <b>${esc(attrText(s.after) || "—")}</b></span></div>`;
      }).join("")}</div></div></section>`);
  }
  /* The chapter page got its dropped channels in the twelfth round; the event page had the
   * same shape of gap, joined the way 「同源记录」 already joins relations — by evidence-id
   * intersection, i.e. "the same line of the text supports both records".
   *
   * MEASURED across all 1,159 events before any of it was rendered:
   *   character traits 36.8% · state changes 34.3% · foreshadowing 26.2% ·
   *   intimacy 17.3% · commitments 15.4% · item roles 11.8%
   * Union: 805 events (69.5%) gain at least one row, 1.31 rows per event; 354 events (30.5%)
   * gain nothing, and a section is emitted only when it has rows, so they are unaffected.
   *
   * The join is deliberately tight — an event with one evidence id joins only records citing
   * that id. A looser join (same chapter, or same participants) would attribute a character's
   * trait to every scene they appear in, and that is not what the record says. */
  const evIds = new Set(A(ev.evidence_ids));
  const byEvidence = rows => A(rows).filter(r => A(r.evidence_ids).some(x => evIds.has(x)));
  const eTraits = byEvidence(G.character_traits);
  if (eTraits.length) body.push(`<section class="pblock" id="ev-traits"><h2>人物特征<span class="n">${eTraits.length}</span></h2>
    <div class="pcards"><div class="pcard">${eTraits.map(t => `<div class="prow">
      <span class="what">${entLink(t.entity_id)}</span>
      <span class="why">${esc(FACET(t.facet))}：${esc(prose(t.statement || ""))}</span></div>`).join("")}</div></div></section>`);
  const eThreads = [];
  for (const f of byEvidence(G.foreshadowing)) eThreads.push(`<div class="prow"><span class="when">埋下伏笔</span>
    <span class="what">${esc(prose(f.label || ""))}</span>
    <span class="why">${esc(prose(f.observation || f.interpretation || ""))}
      <span class="tag">${esc(FSSTAT(f.status))}</span></span></div>`);
  for (const x of byEvidence(G.commitments)) eThreads.push(`<div class="prow"><span class="when">立下承诺</span>
    <span class="what">${esc(prose(x.terms || ""))}</span>
    <span class="why">${entLinks(x.promisor_ids)} → ${entLinks(x.counterparty_ids) || "—"}
      <span class="tag">${esc(term("commitment_kinds", x.kind, x.kind))}</span></span></div>`);
  if (eThreads.length) body.push(`<section class="pblock" id="ev-threads"><h2>伏笔与承诺<span class="n">${eThreads.length}</span></h2>
    <div class="pcards"><div class="pcard">${eThreads.join("")}</div></div></section>`);
  const eIntimate = byEvidence(G.intimate_acts);
  if (eIntimate.length) body.push(`<section class="pblock" id="ev-intimate"><h2>亲密记录<span class="n">${eIntimate.length}</span></h2>
    <div class="pcards"><div class="pcard">${eIntimate.map(a => `<div class="prow">
      <span class="when">${esc(IAT(a.act_type))}</span>
      <span class="what">${entLinks(a.initiator_ids)}${A(a.recipient_ids).length ? " → " + entLinks(a.recipient_ids) : ""}</span>
      <span class="why">${esc(prose(a.description || ""))}
        <span class="tag warn">${esc(CC(a.consent))}</span>${a.nudity ? ` <span class="tag">有裸露</span>` : ""}</span></div>`).join("")}</div></div></section>`);
  const eItems = byEvidence(G.item_roles);
  if (eItems.length) body.push(`<section class="pblock" id="ev-items"><h2>物品归属<span class="n">${eItems.length}</span></h2>
    <div class="pcards"><div class="pcard">${eItems.map(r => `<div class="prow">
      <span class="when">${esc(term("item_roles", r.role, r.role))}</span>
      <span class="what">${entLink(r.entity_id)} · ${entLink(r.item_id)}</span>
      <span class="why">${esc(ACT(r.action))}</span></div>`).join("")}</div></div></section>`);

  const siblings = A(G.events).filter(x => x.id !== ev.id && x.chapter != null && ev.chapter != null
    && Math.abs(x.chapter - ev.chapter) <= 1).slice(0, 12);
  if (siblings.length){
    body.push(`<section class="pblock" id="ev-siblings"><h2>前后章节的其他剧情</h2>${eventList(siblings, c, 12)}</section>`);
  }

  /* Reading is a walk, so the walk needs a next step — the same reasoning as the chapter
   * page, and the same failure mode if a button is used instead of an anchor. Events are
   * ordered by (chapter, id): MEASURED, sorting the 1,159 events by id alone leaves only 2
   * adjacent chapter inversions, so the id carries book order almost exactly — but chapter
   * is still the primary key, because those 2 exist. */
  const evOrder = A(G.events).slice().sort((a, b) =>
    ((a.chapter || 0) - (b.chapter || 0)) || String(a.id).localeCompare(String(b.id)));
  const at = evOrder.findIndex(x => x.id === ev.id);
  const prevEv = at > 0 ? evOrder[at - 1] : null;
  const nextEv = at >= 0 && at < evOrder.length - 1 ? evOrder[at + 1] : null;
  const cut = (s, n) => { const t = String(s || ""); return t.length > n ? t.slice(0, n) + "…" : t; };
  const evNav = `<div class="ch-nav">`
    + (prevEv ? `<a class="sbtn" href="#/event/${esc(prevEv.id)}" title="${esc(prevEv.title || prevEv.id)}">← ${esc(cut(prevEv.title || prevEv.id, 12))}</a>` : "")
    + `<a class="sbtn" href="#/index/event">剧情索引</a>`
    + (nextEv ? `<a class="sbtn" href="#/event/${esc(nextEv.id)}" title="${esc(nextEv.title || nextEv.id)}">${esc(cut(nextEv.title || nextEv.id, 12))} →</a>` : "")
    + `</div>`;
  const nav = `<div class="pg-nav">
      ${ev.chapter != null ? `<a class="pnav" href="#/chapter/${esc(ev.chapter)}">看第 ${esc(ev.chapter)} 章梗概</a>` : ""}
      <a class="pnav" href="#/">回到总览</a></div>`;
  return pageShell("event", ev.title || ev.id, esc(prose(ev.description || "")).slice(0, 220), chips,
    evNav + body.join("") + nav, "");
}

function pageChapter(route){
  const n = route.n;
  const c = S.chapter;
  const sum = A(G.chapter_summaries).find(s => s.chapter === n);
  const events = A(G.events).filter(e => e.chapter === n);
  const changed = A(G.state_changes).filter(s => s.chapter === n);
  /* The twelfth round. This page used to answer "what happened here" with three sections and
   * MEASURED 1,604 characters on `#/chapter/251` — shorter than the viewport, so its rail rows
   * had nothing to scroll to and the chapter read as a stub. The graph was already carrying
   * eight more per-chapter channels that this builder dropped on the floor.
   *
   * Coverage was measured across all 999 chapters before any of it was rendered, because the
   * rule for a *grouping axis* (reject anything under ~50%) does not transfer to a *section*:
   *   new relation episodes 46.8% · character traits 44.1% · state changes 37.5% ·
   *   open issues 32.8% · planted foreshadowing 28.6% · intimacy 26.7% ·
   *   commitments 18.3% · item roles 14.2%
   * That is 3.03 new rows per chapter on average, only 12 chapters (1.2%) gain nothing, and a
   * section is emitted only when it has rows — so a sparse channel costs a chapter nothing.
   * An index axis covered by 14% would bury the other 86%; a section covered by 14% is simply
   * absent from 86% of pages, which is the truth about those chapters. */
  const traits   = A(G.character_traits).filter(t => t.chapter === n);
  const intimate = A(G.intimate_acts).filter(a => a.chapter === n);
  const items    = A(G.item_roles).filter(r => N(r.valid_from) === n);
  const planted  = A(G.foreshadowing).filter(f => N(f.planted_chapter) === n);
  const made     = A(G.commitments).filter(x => N(x.created_chapter) === n);
  const kept     = A(G.commitments).filter(x => N(x.resolved_chapter) === n);
  const issues   = A(G.review_issues).filter(r => N(r.chapter) === n);
  /* Relation movement reads the *intervals*, never the top-level `valid_from`: since the tenth
   * round a relation's lifetime is a set of episodes and the scalar only summarises the first
   * one, so the chapter where a relationship actually began can be anywhere in that set.
   * `rel_f01_016` is the record that forced this — its second episode starts at 322 while the
   * top-level scalar says 1. */
  const relMoves = [];
  for (const r of A(G.relations)){
    const ivs = A(relIntervals(r));
    if (!ivs.length) continue;
    if (ivs.some(iv => iv.from === n)) relMoves.push({ r, kind: "start" });
    else if (ivs.some(iv => iv.to === n)) relMoves.push({ r, kind: "end" });
  }
  const people = new Set();
  for (const e of events) for (const p of A(e.participant_ids)) people.add(p);
  for (const t of traits) if (t.entity_id) people.add(t.entity_id);
  for (const s of changed) if (s.entity_id) people.add(s.entity_id);
  for (const m of relMoves){ people.add(m.r.source_id); people.add(m.r.target_id); }
  for (const a of intimate) for (const id of A(a.initiator_ids).concat(A(a.recipient_ids))) people.add(id);
  for (const id of [...people]) if (!ENT.has(id)) people.delete(id);
  const nm = entLink, nmList = entLinks;
  const chips = [
    tag(`第 ${n} 章`),
    events.length ? tag(`${events.length} 段剧情`) : "",
    changed.length ? tag(`${changed.length} 处变化`) : "",
    people.size ? tag(`${people.size} 人登场`) : "",
  ].filter(Boolean).join("");
  /* Reading a chapter is a walk, so the walk needs a next step. The chapter grid in the
   * sidebar gets you to a neighbourhood; these get you to the next page.
   *
   * These are anchors, not `data-goto-chapter` buttons. That attribute is handled by
   * `openChapterDrawer()`, which re-scrubs the page and opens a drawer *without touching the
   * route* — on a chapter page it re-paints from `RT.n`, which is still the chapter the reader
   * is already on. MEASURED: clicking 「第 252 章 →」 left the hash at `#/chapter/251` and the
   * page unchanged. Changing the hash is what actually navigates here, and an anchor is also
   * the honest element for "go somewhere else". */
  const nav = `<div class="ch-nav">`
    + (n > MIN_CH ? `<a class="sbtn" href="#/chapter/${n - 1}">← 第 ${n - 1} 章</a>` : "")
    + `<a class="sbtn" href="#/index/chapter">章节索引</a>`
    + (n < MAX_CH ? `<a class="sbtn" href="#/chapter/${n + 1}">第 ${n + 1} 章 →</a>` : "")
    + `</div>`;
  /* The nav leads the body rather than sitting in `.pg-title`: that row is `align-items:
   * baseline` for the h1 and the tags, and a row of buttons set on a text baseline looks
   * broken. It is a bare `div`, not a `section.pblock`, so the rail does not list it. */
  const body = [nav];
  /* Every block carries an id, because the rail's job is to list *this page's* sections and
   * it derives them from the DOM. A chapter page used to emit bare `<section class="pblock">`
   * with no id, so `#page section.pblock[id]` matched nothing: `buildRail()` found no
   * sections, took its "the page has not painted yet" exit, and left whatever the previous
   * route had put in the rail. On 999 chapter pages the rail was simply empty — the reader
   * saw no table of contents and nothing to click. */
  if (sum && sum.title) body.push(`<section class="pblock" id="ch-summary"><h2>${esc(sum.title)}</h2>
    <p class="pg-prose">${esc(prose(sum.summary || ""))}</p>${evLine(sum.evidence_ids, 2) ? `<div class="quotes">${evLine(sum.evidence_ids, 2)}</div>` : ""}</section>`);
  else if (sum) body.push(`<section class="pblock" id="ch-summary"><h2>梗概</h2><p class="pg-prose">${esc(prose(sum.summary || ""))}</p></section>`);
  if (events.length) body.push(`<section class="pblock" id="ch-events"><h2>本章剧情<span class="n">${events.length}</span></h2>${eventList(events, c)}</section>`);
  if (changed.length) body.push(`<section class="pblock" id="ch-changes"><h2>本章变化<span class="n">${changed.length}</span></h2>
    <div class="pcards"><div class="pcard">${changed.map(s => {
      const who = ENT.get(s.entity_id);
      return `<div class="prow"><span class="what">${who ? `<a class="lref" href="${esc(entityHref(s.entity_id) || "#/")}">${esc(who.name)}</a>` : esc(s.entity_id)}</span>
        <span class="why">${esc(FACET(s.facet))}：${esc(attrText(s.before) || "—")} → <b>${esc(attrText(s.after) || "—")}</b></span></div>`;
    }).join("")}</div></div></section>`);
  if (relMoves.length) body.push(`<section class="pblock" id="ch-rel"><h2>关系变动<span class="n">${relMoves.length}</span></h2>
    <div class="pcards"><div class="pcard">${relMoves.map(m => `<div class="prow">
      <span class="when">${m.kind === "start" ? "开始" : "结束"}</span>
      <span class="what">${nm(m.r.source_id)} — ${esc(RELT(m.r.relation_type))} — ${nm(m.r.target_id)}</span>
      <span class="why">${esc(prose(m.r.description || ""))}</span></div>`).join("")}</div></div></section>`);
  if (traits.length) body.push(`<section class="pblock" id="ch-traits"><h2>人物特征<span class="n">${traits.length}</span></h2>
    <div class="pcards"><div class="pcard">${traits.map(t => `<div class="prow">
      <span class="what">${nm(t.entity_id)}</span>
      <span class="why">${esc(FACET(t.facet))}：${esc(prose(t.statement || ""))}</span></div>`).join("")}</div></div></section>`);
  const threads = [];
  for (const f of planted) threads.push(`<div class="prow"><span class="when">埋下伏笔</span>
    <span class="what">${esc(prose(f.label || ""))}</span>
    <span class="why">${esc(prose(f.observation || f.interpretation || ""))}
      <span class="tag">${esc(FSSTAT(f.status))}</span></span></div>`);
  for (const x of made) threads.push(`<div class="prow"><span class="when">立下承诺</span>
    <span class="what">${esc(prose(x.terms || ""))}</span>
    <span class="why">${nmList(x.promisor_ids)} → ${nmList(x.counterparty_ids) || "—"}
      <span class="tag">${esc(term("commitment_kinds", x.kind, x.kind))}</span></span></div>`);
  for (const x of kept) threads.push(`<div class="prow"><span class="when">兑现承诺</span>
    <span class="what">${esc(prose(x.resolution || x.terms || ""))}</span>
    <span class="why">第 ${esc(x.created_chapter)} 章立下 · ${nmList(x.promisor_ids)}</span></div>`);
  if (threads.length) body.push(`<section class="pblock" id="ch-threads"><h2>伏笔与承诺<span class="n">${threads.length}</span></h2>
    <div class="pcards"><div class="pcard">${threads.join("")}</div></div></section>`);
  /* Consent is not a footnote. This workspace's rule is that inclusion in the intimacy log
   * never implies willingness, so 「单方面」「受迫」 are tagged at the same weight as the act
   * itself rather than tucked into small grey type. */
  if (intimate.length) body.push(`<section class="pblock" id="ch-intimate"><h2>亲密记录<span class="n">${intimate.length}</span></h2>
    <div class="pcards"><div class="pcard">${intimate.map(a => `<div class="prow">
      <span class="when">${esc(IAT(a.act_type))}</span>
      <span class="what">${nmList(a.initiator_ids)}${A(a.recipient_ids).length ? " → " + nmList(a.recipient_ids) : ""}</span>
      <span class="why">${esc(prose(a.description || ""))}
        <span class="tag warn">${esc(CC(a.consent))}</span>${a.nudity ? ` <span class="tag">有裸露</span>` : ""}</span></div>`).join("")}</div></div></section>`);
  if (items.length) body.push(`<section class="pblock" id="ch-items"><h2>物品归属<span class="n">${items.length}</span></h2>
    <div class="pcards"><div class="pcard">${items.map(r => `<div class="prow">
      <span class="when">${esc(term("item_roles", r.role, r.role))}</span>
      <span class="what">${nm(r.entity_id)} · ${nm(r.item_id)}</span>
      <span class="why">${esc(ACT(r.action))}：${esc(prose(r.description || ""))}</span></div>`).join("")}</div></div></section>`);
  if (people.size) body.push(`<section class="pblock" id="ch-people"><h2>登场人物<span class="n">${people.size}</span></h2>
    <div class="lrefs">${relatedRows([...people], c, 60)}</div></section>`);
  /* Last on purpose. It is audit material, not story: a reader came for the chapter, and this
   * says only that some of what is above is uncertain. Placing it here keeps it available
   * without letting it lead. */
  if (issues.length) body.push(`<section class="pblock" id="ch-review"><h2>待人工核对<span class="n">${issues.length}</span></h2>
    <div class="pcards"><div class="pcard">${issues.map(r => `<div class="prow">
      <span class="when">${esc(ISEV(r.severity))}</span>
      <span class="why">${esc(issueText(r.description))}</span></div>`).join("")}</div></div></section>`);
  return pageShell("chapter", `第 ${n} 章`, "", chips, body.join(""), "");
}

/* ------------------------------------------------------------------ *
 * index page grouping
 *
 * A flat grid of 113 places is a wall, not an index. Every kind already has a
 * natural second axis in the data — a place is in a city, an item has a grade, a
 * skill has a category — so the index page groups by that axis instead of printing
 * one undifferentiated list.
 *
 * The axis has to be CHOSEN per kind, and chosen by what the data actually covers,
 * not by what would be tidy. Every candidate axis was measured against the real
 * graph before being adopted, and most of them lost:
 *
 *   location  by 所在地/位置 ....... 58% covered (41 groups) -> kept, city is the axis
 *   item      by 品级/性质 ........ 25% covered (25 groups) -> REJECTED
 *   skill     by 类别/类型 ........ 13% covered (13 groups) -> REJECTED
 *   org       by 性质/类型 ........ 30% covered (23 groups) -> REJECTED
 *   creature  by 物种/种类 ........ 64% covered (20 groups) -> kept
 *   concept   by tags ............. 22% covered (12 groups) -> REJECTED
 *   any kind  by story position ... 8 bands, 6-26 rows each -> kept as the default
 *
 * A rejected axis is not decoded wrong, it is simply too sparse: grouping 111 items
 * by a key that 83 of them lack produces one 83-row 其他 bucket and 24 singletons,
 * which is worse than the flat grid it replaced. The chronological axis is boring
 * but it is the one axis every single entity has (`first_chapter` is on 980/980), and
 * "what appeared in this stretch of the story" is a real way readers navigate.
 *
 * Group order is deterministic: size descending, then label. A reader coming back
 * twice must find 苏南市 in the same place.
 * ------------------------------------------------------------------ */
const IX_AXIS = {
  /* People get the one axis the reader navigates by: how central they are. Relation
   * count is a fact, not a judgement — it is the same number the card already prints. */
  char:     { label: "按戏份", why: "关系越多，在故事里越中心",
              of: e => charTier(e) },
};
/* Every other kind groups by where in the story it turns up, and that is not a
 * fallback — it is the measured winner.
 *
 * Three axes were built and then rejected against the real graph:
 *
 *   location by city ....... only 20 of 113 rows mention a city at all, and the
 *      summaries are prose ("秦朝毕业后落脚的北方城市，故事主要发生地"). Reading the
 *      city out of the first 24 characters yields 5 groups and leaves 100 rows
 *      uncategorised. Also tried attribute-first (42 groups, 32 of them singletons)
 *      and name-then-judge (5 groups, 105 uncategorised). The data does not have this
 *      axis; forcing it just renamed the flat list.
 *   item by 品级 .......... 25% coverage, 25 distinct values
 *   skill by 类别 ......... 13% coverage
 *   org by 性质 ........... 30% coverage
 *   creature by 物种 ...... 64% coverage but 19 of 20 groups are singletons: those are
 *      individual names ("九幽魔犬"), not a taxonomy
 *
 * Meanwhile `first_chapter` is on 980/980 entities and splits every kind into eight
 * bands of 6–26 rows. "What turned up in this stretch of the story" is a real way
 * readers navigate a 999-chapter book, and unlike the axes above it is actually
 * supported by the data.
 *
 * The lesson, recorded because it cost three rebuilds: an index axis must be chosen
 * by MEASURED COVERAGE, not by which field sounds most like a category. A tidy-looking
 * axis with 15% coverage produces one 90-row bucket plus 20 one-card headings, which is
 * the flat grid again with extra railings. */
const IX_ORDER = { label: "按登场顺序", why: "同一段故事里出现的放在一起" };

/* Story position, in eight bands rather than one list or 999 groups. 111 items in
 * eight bands of 12-18 is scannable; 111 in one column is the wall we are replacing. */
/* Per-type mean relation count, as a measurement rather than a hand-written disclaimer.
 *
 * This reads the *projected* graph (`snap(c)`), not a top-level field. The first version
 * of this helper iterated `S.rels` and `S.ent` -- and `S` holds only
 * {chapter, sel, selKind, zone, graphStrict}. Both fell through their `|| []` defaults,
 * so the map was all zeros and *every* index page, characters included, would have
 * claimed its type has no relations. Nothing would have failed: `|| []` turns a typo into
 * an empty iteration and an empty iteration into a confident wrong answer.
 *
 * Depends on the current chapter, because the projection does -- a kind that is thin at
 * chapter 999 may be thinner still at chapter 100, and the warning should track what the
 * reader is actually looking at. */
function kindRelAvg(kind){
  const st = snap(S.chapter);
  const sums = new Map(), nums = new Map();
  for (const r of st.rels){
    for (const end of [r.source_id, r.target_id]){
      const e = ENT.get(end);
      if (!e) continue;
      sums.set(e.type, (sums.get(e.type) || 0) + 1);
    }
  }
  for (const e of st.ent) nums.set(e.type, (nums.get(e.type) || 0) + 1);
  return nums.size && nums.has(ROUTE_ENTITY[kind])
    ? (sums.get(ROUTE_ENTITY[kind]) || 0) / nums.get(ROUTE_ENTITY[kind])
    : null;
}

const IX_BANDS = 8;
function chapterBand(ch){
  const w = Math.ceil(MAX_CH / IX_BANDS);
  const lo = Math.floor(((ch || 1) - 1) / w) * w + 1;
  return `第 ${lo}–${Math.min(MAX_CH, lo + w - 1)} 章`;
}

function attr(e, key){
  const v = e && e.attributes ? e.attributes[key] : null;
  if (v == null) return null;
  const s = attrText(v).trim();
  return s || null;
}

/* Three bands, not a continuous rank: a reader looking for "who matters here" and a
 * reader looking for "who was that walk-on" are asking different questions, and a
 * 425-row list sorted by degree answers neither. Thresholds are on the degree the
 * graph already computed, so the same character cannot change band between views. */
function charTier(e){
  const d = DEG.get(e.id) || 0;
  if (PRO.has(e.id) || d >= 6) return "主要人物";
  if (d >= 2) return "次要人物";
  return "过场人物";
}
/* Rank for the three cast bands. Sorting them by size would put 过场人物 (207) first
 * and make the reader scroll past everyone who does not matter to reach the 44 who
 * do. The bands are the axis here, so their order is the axis's order. */
const CHAR_TIER_ORDER = ["主要人物", "次要人物", "过场人物"];

/* ------------------------------------------------------------------ *
 * index pages for the two kinds that are not entities
 *
 * `#/index/chapter` and `#/index/event` used to fall through to
 * `pageMissing("找不到这个索引")` — "identifier chapter is not in this graph". That message is
 * a lie: chapters and events are in the graph, they are just not *entities*, and the index
 * page was written against `snap(c).ent` only. The cost was not a corner case:
 *
 *   - every chapter page's breadcrumb links to `#/index/chapter`, so all 999 of them ended
 *     at "找不到这个索引";
 *   - the sidebar's 剧情 row was pointed at `#/` to dodge the same dead page, which means
 *     clicking "剧情 1159" silently threw the reader back to the overview.
 *
 * Both kinds have a real axis — the same one the entity indexes fall back to, because it is
 * the axis every record has: where in the story it happens. A chapter is *at* a chapter, so
 * chapters band by their own number; events band by theirs.
 * ------------------------------------------------------------------ */
function indexGroups(items, bandOf, orderOf){
  const buckets = new Map();
  for (const it of items){
    const k = bandOf(it);
    if (!buckets.has(k)) buckets.set(k, []);
    buckets.get(k).push(it);
  }
  return [...buckets.entries()].sort((a, b) =>
    String(a[0]).localeCompare(String(b[0]), "zh", { numeric: true }));
}

/* A compact row, not a card. The entity indexes use cards because a card carries a name, a
 * summary and two facts and the reader is browsing subjects. There are 999 chapters and 1159
 * events, and a reader looking at this list knows the number they want — a card per chapter
 * would be 999 boxes to carry one number each. */
function ixLine(href, num, title, meta){
  return `<a class="ix-line" href="${esc(href)}">
    <b class="ln">${esc(num)}</b>
    <span class="lt">${esc(title || "—")}</span>
    ${meta ? `<span class="lm">${esc(meta)}</span>` : ""}</a>`;
}

function pageIndexChapters(route){
  const c = S.chapter;
  const sumOf = new Map();
  for (const s of A(G.chapter_summaries)){
    if (s && s.chapter != null) sumOf.set(s.chapter, s);
  }
  const evCount = new Map();
  for (const e of A(G.events)){
    if (e && e.chapter != null) evCount.set(e.chapter, (evCount.get(e.chapter) || 0) + 1);
  }
  const nums = [];
  for (let n = MIN_CH; n <= MAX_CH; n++) nums.push(n);
  const groups = indexGroups(nums, n => chapterBand(n));
  const body = `<div class="ix-wrap"><div class="ix-groups">${
    groups.map(([k, list]) => `<section class="ix-group" id="ixg-${esc(slug(k))}">
      <div class="ix-gh"><h2>${esc(k)}</h2><span class="n">${list.length}</span></div>
      <div class="ix-lines">${list.map(n => {
        const s = sumOf.get(n);
        const ne = evCount.get(n) || 0;
        return ixLine(`#/chapter/${n}`, `第 ${n} 章`, (s && s.title) || "",
          ne ? `${ne} 段剧情` : "");
      }).join("")}</div></section>`).join("")
  }</div><nav class="ix-jump"><div class="jh">按章节</div>${
    groups.map(([k, list]) => `<a href="#ixg-${esc(slug(k))}" data-toc="ixg-${esc(slug(k))}"><span>${esc(k)}</span>
      <b>${list.length}</b></a>`).join("")}</nav></div>`;
  const note = `全书共 ${MAX_CH - MIN_CH + 1} 章，按每 ${Math.ceil(MAX_CH / IX_BANDS)} 章一段分组。`
    + `点章号进入该章页面，可以看到梗概、本章剧情、本章变化与登场人物。`;
  return pageShell("chapter", "章节索引", "", "", body, "") 
    .replace('<div class="pg-body">', `<div class="pg-body"><p class="ix-note">${esc(note)}</p>`);
}

function pageIndexEvents(route){
  const c = S.chapter;
  const evs = A(G.events).filter(e => e && e.chapter != null && e.chapter <= c);
  if (!evs.length) return pageMissing("还没有记录到剧情", "event");
  const groups = indexGroups(evs, e => chapterBand(e.chapter));
  const body = `<div class="ix-wrap"><div class="ix-groups">${
    groups.map(([k, list]) => `<section class="ix-group" id="ixg-${esc(slug(k))}">
      <div class="ix-gh"><h2>${esc(k)}</h2><span class="n">${list.length}</span></div>
      <div class="ix-lines">${list
        .sort((a, b) => (a.chapter || 0) - (b.chapter || 0))
        .map(e => ixLine(`#/event/${encodeURIComponent(e.id)}`, `第 ${e.chapter} 章`,
          e.title || e.id, term("event_types", e.type, e.type))).join("")}</div></section>`).join("")
  }</div><nav class="ix-jump"><div class="jh">按章节</div>${
    groups.map(([k, list]) => `<a href="#ixg-${esc(slug(k))}" data-toc="ixg-${esc(slug(k))}"><span>${esc(k)}</span>
      <b>${list.length}</b></a>`).join("")}</nav></div>`;
  const note = `截至第 ${c} 章共记录 ${evs.length} 段剧情。每段剧情都是一页，`
    + `里面有参与者、发生地点、涉及的物品与技能、原文证据，以及这场剧情造成的改变。`;
  return pageShell("event", "剧情索引", "", "", body, "")
    .replace('<div class="pg-body">', `<div class="pg-body"><p class="ix-note">${esc(note)}</p>`);
}

function pageIndex(route){
  const kind = route.kind;
  /* Two kinds have index pages that are not entity indexes; they are dispatched here so the
   * router stays a single call site. */
  if (kind === "chapter") return pageIndexChapters(route);
  if (kind === "event") return pageIndexEvents(route);
  const etype = ROUTE_ENTITY[kind];
  if (!etype) return pageMissing("找不到这个索引", kind);
  const c = S.chapter;
  const rows = snap(c).ent.filter(e => e.type === etype)
    .sort((a, b) => (DEG.get(b.id) || 0) - (DEG.get(a.id) || 0)
      || (a.first_chapter || 0) - (b.first_chapter || 0)
      || String(a.name).localeCompare(String(b.name), "zh"));
  const axis = IX_AXIS[kind] || IX_ORDER;
  const byChapter = axis === IX_ORDER;
  /* `其他` is a real bucket, not a failure: some places have no city anywhere in
   * their record, and hiding them would silently drop them from their own index
   * page. It sorts last so the reader meets the named groups first. */
  const buckets = new Map();
  for (const e of rows){
    const k = (axis.of && axis.of(e)) || (byChapter ? chapterBand(e.first_chapter) : "其他");
    if (!buckets.has(k)) buckets.set(k, []);
    buckets.get(k).push(e);
  }
  /* A group of one is a heading with a single card under it — that is a table of
   * contents pretending to be a classification. Any name only one row uses is folded
   * back into 其他, so the group count reflects how many *categories* the data really
   * supports rather than how many distinct strings it happens to contain. */
  const MIN_GROUP = 2;
  if (!byChapter){
    for (const [k, list] of [...buckets]){
      if (k === "其他" || list.length >= MIN_GROUP) continue;
      buckets.delete(k);
      if (!buckets.has("其他")) buckets.set("其他", []);
      buckets.get("其他").push(...list);
    }
  }
  const ordered = [...buckets.entries()].sort((a, b) => {
    /* Chapter bands and cast tiers sort by their own semantics, not by size — "第 497
     * 章" before "第 249 章" is nonsense when the axis IS the chronology, and 过场人物
     * before 主要人物 buries the 44 characters the reader came for. */
    if (byChapter) return String(a[0]).localeCompare(String(b[0]), "zh", { numeric: true });
    if (kind === "char"){
      const ia = CHAR_TIER_ORDER.indexOf(a[0]), ib = CHAR_TIER_ORDER.indexOf(b[0]);
      if (ia !== ib) return (ia < 0 ? 99 : ia) - (ib < 0 ? 99 : ib);
    }
    return b[1].length - a[1].length
      || String(a[0]).localeCompare(String(b[0]), "zh");
  });
  /* What a card says about its subject.
   *
   * The second line used to be "N 条关系", and MEASURED it is the same string on almost
   * every card: 0 edges for 94% of locations, 89% of skills, 85% of concepts, 64% of
   * items, 58% of creatures, 100% of level axes. 823 relations in the whole graph and
   * nearly all of them connect characters, so a relation count answers a question nobody
   * asked and answers it identically 113 times. A line that is constant across a page is
   * not information; it is decoration that costs a row.
   *
   * `summary` is the field that is both universal and specific -- every entity has one and
   * no two read alike ("秦朝毕业后落脚的北方城市" vs "广元学院商学系七层高教学楼"). So the
   * summary takes the line, and the relation count is kept *only when it is non-zero*,
   * where it genuinely distinguishes (a 276-degree character is not the same subject as a
   * walk-on).
   *
   * The summary is clamped to two lines rather than one: a one-line clamp cut most
   * summaries mid-clause ("秦朝毕业后落脚的北方城"), and a truncated sentence is worse
   * than no sentence -- it reads as though the data itself is broken. Two lines fit the
   * common case whole and still bound the card height. */
  /* A card line has to come from somewhere for every row, and "every row carries it in
   * `summary`" is not true: MEASURED, 2 of the 9 level axes have an empty summary
   * (金刚经四层, 忍者等级).
   *
   * Those two are not missing information. They carry the same content in `attributes`
   * instead -- 金刚经四层 has 第一层..第四层 and 忍者等级 has 下忍/中忍/上忍 -- because
   * the fragments that produced them recorded the ladder as keyed levels rather than as
   * prose. So this is not the renderer inventing anything; it is the renderer reading a
   * second field the extraction actually filled, instead of printing a blank row and
   * letting the reader conclude the entry is empty.
   *
   * Order matters: summary first (it is prose and reads best), then the ladder keys, then
   * 备注. Nothing is synthesised -- every word here is already stored on the entity. */
  const cardLine = e => {
    const sum = String(e.summary || "").trim();
    if (sum) return sum;
    const at = (e && e.attributes) || {};
    const ladder = Object.keys(at).filter(k => /^第[一二三四五六七八九十\d]+[层阶档级重]$/.test(k)
      || /^(下|中|上|初|高|顶)[忍阶等级层]$/.test(k));
    if (ladder.length){
      const vals = ladder
        .sort((a, b) => ladder.indexOf(a) - ladder.indexOf(b))
        .map(k => String(at[k]).trim()).filter(Boolean);
      if (vals.length) return vals.join(" / ");
    }
    return String(at["备注"] || "").trim();
  };
  const card = e => {
    const deg = DEG.get(e.id) || 0;
    const sum = cardLine(e);
    return `<a class="ix-card" href="${esc(entityHref(e.id) || "#/")}">
      <b class="nm">${esc(e.name)}</b>
      ${A(e.aliases).length ? `<span class="sb">${esc(A(e.aliases).slice(0, 3).join("、"))}</span>` : ""}
      ${sum ? `<span class="sm">${esc(sum)}</span>` : ""}
      <span class="mt"><span>第 ${esc(e.first_chapter ?? "?")} 章</span>${
        deg ? `<span>${deg} 条关系</span>` : ""}</span></a>`;
  };
  const body = `<div class="ix-wrap"><div class="ix-groups">${
    ordered.map(([k, list]) => `<section class="ix-group" id="ixg-${esc(slug(k))}">
      <div class="ix-gh"><h2>${esc(k)}</h2><span class="n">${list.length}</span></div>
      <div class="ix-grid">${list.map(card).join("")}</div></section>`).join("")
  }</div>${
    ordered.length > 3 ? `<nav class="ix-jump"><div class="jh">${esc(axis.label)}</div>${
      ordered.map(([k, list]) => `<a href="#ixg-${esc(slug(k))}" data-toc="ixg-${esc(slug(k))}"><span>${esc(k)}</span>
        <b>${list.length}</b></a>`).join("")}</nav>` : ""
  }</div>`;
  /* Say what the page does NOT contain, before the reader infers it from blanks.
   *
   * MEASURED on this graph: of 823 relations, 697 have a character at one end, and the
   * per-entity averages run 2.97 for characters, 3.28 for organizations -- but 0.07 for
   * locations, 0.14 for skills, 0.21 for concepts. A reader who opens the location index
   * and sees 113 subjects with almost no edges will conclude the panel is broken. It is
   * not broken; the extraction simply recorded those subjects through `summary` and
   * `item_roles` rather than through `relations`, and the honest thing is to say so.
   *
   * This is the same rule the rest of the run follows: an unresolved state is registered
   * as unresolved rather than left to look like a settled fact. Here it is the difference
   * between "this place has no connections" (false) and "this panel does not draw
   * connections for this kind" (true). */
  const avg = kindRelAvg(kind);
  const sparse = (avg != null && avg < 1.0)
    ? `本页类型的关系边较少（该类型人均 ${avg.toFixed(2)} 条）：图谱主要在`
      + `人物与势力之间记录关系，地点／法术／设定多以简介与物品归属的形式登记。`
      + `卡片下未显示「关系」字样的，就是没有关系边记录，不代表它与其他内容无关。`
    : "";
  return pageShell(kind, `${PAGE_NOUN[kind]}索引`,
    `共 ${rows.length} 项，分 ${ordered.length} 组。${esc(axis.why)}。点任意一项进入它的专属页面。`
    + (sparse ? ` ${sparse}` : ""),
    tag(`${rows.length} 项`) + tag(`${ordered.length} 组`), body, "");
}

/* Anchor ids have to survive Chinese group names and spaces. */
function slug(s){
  return String(s).replace(/[^\w\u4e00-\u9fa5]+/g, "-").replace(/^-|-$/g, "") || "x";
}

function pageMissing(title, what){
  return `<div class="pg-head"><div class="pg-crumb"><a href="#/">总览</a></div>
    <div class="pg-title"><h1>${esc(title)}</h1></div></div>
    <div class="pg-body"><p class="pg-empty">标识 <code>${esc(String(what))}</code> 不在本图谱中。
    它可能来自另一个 run，或已被更名合并。<a href="#/">回到总览</a>。</p></div>`;
}

function paintPage(route){
  const host = document.getElementById("page");
  let html;
  if (route.view === "event") html = pageEvent(route);
  else if (route.view === "chapter") html = pageChapter(route);
  else if (route.view === "index") html = pageIndex(route);
  else html = pageEntity(route);
  host.innerHTML = html;
  /* The per-subject graph is built after the markup lands, the same way the stream's
   * graph is, because cytoscape needs a container that is already in the document. */
  if (route.view === "entity"){
    const e = ENT.get(route.id);
    if (e) buildSubjectGraph(e, S.chapter);
  }
  /* The rail has to be rebuilt after the page's own markup lands, and only `paintStream`
   * used to call it. The result was that a reader who navigated to a subject page kept the
   * rail built for the home stream: it still listed 「章节梗概」「节奏」 and clicking one
   * scrolled to an element the visitor could not see. Rebuilding here is what makes the rail
   * describe the page it is attached to. */
  buildRail();
}

/* ------------------------------------------------------------------ *
 * navigation sidebar
 *
 * The rail is rebuilt from the live DOM rather than from a hand-written list, so a
 * block that stops rendering (empty result, filtered out) disappears from the rail in
 * the same frame and cannot leave a dead link behind. Counts come from the block's own
 * `.n` badge, which is the same number the header shows.
 * ------------------------------------------------------------------ */
const RAIL_GROUPS = [
  ["T1", "全书", ["stat", "chapters", "rhythm", "coverage", "rules"]],
  ["T2", "主体", ["graph", "levels", "agents", "milestones"]],
  ["T3", "流转物", ["items", "skills", "concepts"]],
  ["TAIL", "未决", ["romance", "foreshadow", "commitments", "intimacy", "issues"]],
];
const RAIL_LABEL = {
  stat: "总览", chapters: "章节梗概", rhythm: "节奏", coverage: "覆盖台账", rules: "世界观规则",
  graph: "关系总谱", levels: "境界阶梯", agents: "人物与主体库", milestones: "关键事件",
  items: "法器与物品", skills: "法术与技能", concepts: "设定与概念",
  romance: "感情线", foreshadow: "伏笔", commitments: "承诺与约定",
  intimacy: "亲密记录", issues: "待核对",
};

/* ------------------------------------------------------------------ *
 * the sidebar
 *
 * Fixed to the left edge rather than floating over the content. A floating panel covers
 * the thing you are reading; a fixed one costs the same width on every screen and never
 * has to be dismissed. It holds the three ways a reader arrives somewhere: searching
 * (always visible, not hidden behind a key), browsing by kind (the tree), and jumping
 * within the current page (the block rail).
 *
 * The tree lists kinds, and the *counts come from the graph*, so a type that has no
 * entries cannot appear as an empty branch. Each branch opens that kind's index page
 * rather than expanding 425 rows inline — a sidebar is for choosing, not for scrolling.
 * ------------------------------------------------------------------ */
const SIDE_KINDS = [
  ["char", "人物", "character"], ["loc", "地点", "location"], ["org", "势力", "organization"],
  ["creature", "生灵", "creature"], ["axis", "等级体系", "level_axis"],
  ["item", "物品", "item"], ["skill", "技能", "skill"], ["concept", "设定", "concept"],
];
/* Which sidebar sections the reader has folded away. Kept outside the DOM because
 * `buildSidebar()` rewrites the whole tree on every chapter change. */
const SIDE_SHUT = new Set();
function sideHead(id, label, count, extra){
  const open = !SIDE_SHUT.has(id);
  return `<button class="side-h${open ? "" : " shut"}" data-side-head="${esc(id)}"
    aria-expanded="${open ? "true" : "false"}"
    title="${open ? "收起" : "展开"}「${esc(label)}」"><i class="tw"></i>${esc(label)}${
    count != null ? `<span class="n">${esc(count)}</span>` : ""}${
    extra ? `<span class="tail">${esc(extra)}</span>` : ""}</button>`;
}
function buildSidebar(){
  const host = document.getElementById("side-tree");
  if (!host) return;
  const c = S.chapter;
  const live = snap(c).ent;
  const byType = new Map();
  for (const e of live) byType.set(e.type, (byType.get(e.type) || 0) + 1);
  const events = A(G.events).filter(e => e.chapter != null && e.chapter <= c).length;
  let html = "";
  /* A one-line breadcrumb, not just a single link: knowing where you are is what makes
   * the "back" control usable at all, and the tree above it changes shape per page. */
  if (RT.view !== "home"){
    const here = (typeof currentCrumb === "function") ? currentCrumb() : [];
    /* Every segment is a control, including the last one. The current page cannot link to
     * itself — that would push a hash the router already has — so it scrolls to the top of
     * what it names instead. A `<b>` there read as one more clickable step and did nothing,
     * which is the same complaint as the heading rows. */
    html += `<nav class="side-crumb"><a href="#/" title="回到总览">总览</a>`
      + here.map(([label, href]) => href
          ? ` <span class="sep">›</span> <a href="${esc(href)}">${esc(label)}</a>`
          : ` <span class="sep">›</span> <button class="sbtn"
              data-scroll-top title="回到「${esc(label)}」的开头">${esc(label)}</button>`).join("")
      + `</nav>`;
    html += `<div class="side-acts">`
      /* 返回 is first because it is the control a reader wants most often, and it is the one
       * that was missing: 回到总览 discards the page they came from. It is a real `<button>`
       * rather than a link because its destination is the previous entry in the visit stack,
       * which is not expressible as a hash — the router owns that, not the markup. */
      + (navCanBack()
          ? `<button class="sbtn" data-nav-back title="回到上一页">← 返回</button>`
          : "")
      + `<a class="sbtn" href="#/">← 回到总览</a>`
      + `<button class="sbtn" data-scroll-top title="回到页面顶部">↑ 顶部</button></div>`;
  }
  const typeRows = SIDE_KINDS
    .map(([kind, label, etype]) => [kind, label, etype, byType.get(etype) || 0])
    .filter(x => x[3]);
  html += sideHead("kinds", "按类型浏览", typeRows.length);
  if (!SIDE_SHUT.has("kinds")){
    html += `<div class="side-kinds">`;
    for (const [kind, label, etype, n] of typeRows){
      const on = RT.view === "index" && RT.kind === kind ? ' class="on"' : "";
      html += `<a${on} href="#/index/${esc(kind)}"><i style="background:${ZONE_COLOR(etype)}"></i>
        <span>${esc(label)}</span><b>${n}</b></a>`;
    }
    /* 剧情 is a kind with an index page like any other. It used to link to `#/` because
     * `#/index/event` rendered "找不到这个索引" — clicking a row that says 剧情 1159 and
     * landing on the overview is the same dead-end as the empty rail, one level up. */
    html += `<a href="#/index/event"><i class="ev"></i><span>剧情</span><b>${events}</b></a></div>`;
  }
  /* The chapter index is the one list that is genuinely numeric, so it is a compact grid
   * rather than a branch. It leads to the chapter pages, which is how a reader who knows
   * "it was around chapter 300" gets anywhere. */
  html += sideHead("chapters", "章节", null, `第 ${MIN_CH}–${MAX_CH} 章`);
  if (!SIDE_SHUT.has("chapters")) html += `<div class="side-ch" id="side-ch"></div>`;
  if (host.dataset.sig === html) return;
  host.dataset.sig = html;
  host.innerHTML = html;
  for (const b of host.querySelectorAll("[data-side-head]")){
    b.addEventListener("click", () => {
      const id = b.dataset.sideHead;
      if (SIDE_SHUT.has(id)) SIDE_SHUT.delete(id); else SIDE_SHUT.add(id);
      buildSidebar();
    });
  }
  const top = host.querySelector("[data-scroll-top]");
  if (top) top.addEventListener("click", () =>
    window.scrollTo({ top: 0, behavior: "smooth" }));
  /* The back control delegates to the router's stack via `history.back()`, so the browser's
   * own Back button and this one can never disagree about where "previous" is. */
  const back = host.querySelector("[data-nav-back]");
  if (back) back.addEventListener("click", () => navBack());
  paintChapterGrid();
}
function paintChapterGrid(){
  const host = document.getElementById("side-ch");
  if (!host) return;
  const c = S.chapter;
  /* Chapters are offered in blocks of fifty — 999 links would be a wall, and the reader
   * is looking for a neighbourhood, not an exact number. */
  const blocks = [];
  for (let s = MIN_CH; s <= MAX_CH; s += 50){
    const to = Math.min(MAX_CH, s + 49);
    blocks.push([s, to]);
  }
  host.innerHTML = blocks.map(([s, to]) =>
    `<button data-ch-block="${s}" title="第 ${s}–${to} 章"
      aria-label="跳到第 ${s} 章"><span>${Math.floor(s / 50) + 1}</span></button>`).join("")
    + `<span class="mini">每格 50 章 · 点格子跳到该段开头</span>`;
  for (const b of host.querySelectorAll("[data-ch-block]")){
    b.addEventListener("click", () => {
      const s = Number(b.dataset.chBlock);
      const pick = Math.min(MAX_CH, s + 24);
      setChapter(pick, true);
      /* Route to the block's own first chapter, not the middle of the band: the reader
       * clicked "第 501–550 章" and asking for chapter 525 silently answered a question
       * they did not ask. */
      go("#/chapter/" + Math.min(MAX_CH, s));
    });
  }
}
let railObserver = null;
/* The rail's click listener is bound once, to the container itself. */
let railBound = false;
/* Collapsed groups live here rather than in `dataset`, because `buildRail()` rewrites the
 * rail's innerHTML whenever the visible section set changes and any state stored on the
 * replaced nodes would be lost with them. */
const RAIL_COLLAPSED = new Set();
/* Everything the rail holds up to, but not including, the mirrored half. */
function trimMirror(markup){
  const MARK = ' data-rail-group="SUBJ"';
  const cut = markup.indexOf(MARK);
  if (cut < 0) return markup;
  const open = markup.lastIndexOf("<button", cut);
  return open >= 0 ? markup.slice(0, open) : markup.slice(0, cut);
}
function buildRail(){
  const rail = document.getElementById("rail");
  if (!rail) return;
  /* Binding lives here, not in a separate `wireRail()` call at each construction site.
   * It used to be a second function that every caller had to remember to invoke, and the
   * moment one call site was rewritten without it the whole rail went silently inert —
   * the heading still looked like a control, still carried the pointer cursor, and
   * answered a click with nothing. The listener is delegated and attached once, so
   * rebuilding the markup can never detach it. */
  wireRail();
  let html = "";
  const live = [];
  /* The rail lists the sections of the *page* the reader is on, not the sections of the
   * home stream.
   *
   * It used to test `getElementById(key).innerHTML !== ""`, which is true on every route for
   * the home stream's own nodes — they stay in the document behind the paged view. So on an
   * entity page the rail advertised 「章节梗概」「节奏」「覆盖台账」, and clicking one scrolled to
   * whatever element happened to own that id. Two of them resolved to the page top, so the
   * row looked inert; the rest scrolled to the wrong place. That is the same complaint as
   * the unclickable headings, one level deeper: the row answered the click and still took
   * the reader nowhere.
   *
   * On a paged route the sections are the `[id^="sec-"]` blocks the page renderer emitted, so
   * the rail is derived from the DOM the reader is actually looking at. On the home stream it
   * keeps the curated groups, because there the stream really is those blocks. */
  /* The route decides which half exists, not whether a node happened to be found. Falling
   * through to the home groups when `#page` was momentarily unpainted is how a subject page
   * ended up advertising 「章节梗概」「节奏」 again.
   *
   * A chapter page is paged too. Excluding it sent the rail down the home branch, where the
   * home stream's blocks are `display:none` and therefore measure 0x0 — so the branch found
   * nothing, `html` stayed empty, and the rail was written blank. On all 999 chapter pages
   * the reader had no table of contents at all. The exclusion was there because the chapter
   * page's own blocks carried no id (see `pageChapter`); now that they do, the route belongs
   * on this side of the branch. */
  const paged = RT.view !== "home";
  if (paged){
    /* Two section shapes carry an id on a paged route: the subject page's blocks
     * (`section.pblock`) and an index page's groups (`section.ix-group`). Both are
     * navigable regions the reader is looking at, so both belong in the rail; matching
     * only the first meant an index page advertised nothing and the branch fell through to
     * the home stream's groups. */
    const secs = [...document.querySelectorAll(
      "#page section.pblock[id], #page section.ix-group[id]")];
    if (secs.length){
      const rows = secs.map(sec => {
        const h = sec.querySelector("h2");
        const n = sec.querySelector(".n");
        const label = h ? (h.textContent || "").replace(/\d+$/, "").trim() : sec.id;
        return { id: sec.id, label: label || sec.id,
                 cnt: n ? n.textContent.trim() : "" };
      });
      /* The disclosure flag is part of the markup, not a loop guard. An earlier revision
       * wrote `aria-expanded="true"` unconditionally and only used `RAIL_COLLAPSED` to skip
       * the rows, so collapsing the group hid the rows but left the control claiming it was
       * still open: no `shut` class, no `aria-expanded="false"`, no way for a reader (or a
       * screen reader) to tell which way the next click goes. The home-stream branch below
       * always did this correctly; this branch was written later and did not. */
      const pOpen = !RAIL_COLLAPSED.has("PAGE");
      html += `<button class="rt${pOpen ? "" : " shut"}" data-rail-group="PAGE"
        aria-expanded="${pOpen ? "true" : "false"}"
        title="${pOpen ? "收起" : "展开"}本页目录"><i class="tw"></i>本页目录<span class="cnt">${
        rows.length}</span></button>`;
      if (pOpen){
        for (const r of rows){
          live.push(r.id);
          html += `<button data-rail="${esc(r.id)}"><i></i>${esc(r.label)}`
            + (r.cnt ? `<span class="cnt">${esc(r.cnt)}</span>` : "") + `</button>`;
        }
      }
      /* The rail's markup is written in exactly one place — `mirrorDrawer()` — so the two
       * halves cannot drift apart. The signature covers the page half only; the mirrored
       * half contributes its own part inside. */
      const sig0 = html + "|" + [...RAIL_COLLAPSED].sort().join(",");
      observeRail(live);
      /* `html` is the page half *just derived from this page's own sections*. Passing the
       * rail's current markup instead, as an earlier revision did, handed over whatever the
       * previous route had left there — so navigating from the home stream to a subject
       * wrote the home stream's rows back under a signature that claimed they were the
       * subject's, and every later pass then agreed the rail was already correct. */
      mirrorDrawer(html, sig0, live);
      return;
    }
    /* A paged route with no identified sections. The old comment here said "leave the rail
     * alone, the page has not painted yet" — but "not painted yet" and "painted, and this
     * page has nothing to list" are indistinguishable from inside this function, and the
     * second case is real: it is every page built by `pageMissing` and every route whose
     * builder emitted no id. Leaving the rail alone then showed the reader the *previous*
     * route's contents. On a `#/event/<id>` page that meant the home stream's seventeen
     * rows — every one of which points at a `display:none` block, so every click did
     * nothing. Clearing is the honest answer: an empty rail says "nothing to list here",
     * a stale one says "here is the table of contents" and lies. */
    mirrorDrawer("", "", []);
    return;
  }
  for (const [tid, label, keys] of RAIL_GROUPS){
    const present = keys.filter(k => {
      const n = document.getElementById(k);
      if (!n) return false;
      /* A block counts only when it is actually laid out. The home stream's blocks stay in
       * the DOM behind a paged route, and an unlaid-out node is not a destination. */
      const r = n.getBoundingClientRect();
      return n.innerHTML.trim() !== "" && (r.width > 0 || r.height > 0);
    });
    if (!present.length) continue;
    /* The group heading used to be a plain div: it looked like a control and did
     * nothing. It is now the disclosure switch for its own group — the one affordance a
     * reader already expects from a heading with children under it. */
    const open = !RAIL_COLLAPSED.has(tid);
    html += `<button class="rt${open ? "" : " shut"}" data-rail-group="${esc(tid)}"
      aria-expanded="${open ? "true" : "false"}"
      title="${open ? "收起" : "展开"}「${esc(label)}」"><i class="tw"></i>${esc(label)}
      <span class="cnt">${present.length}</span></button>`;
    for (const k of present){
      if (!open) continue;
      const node = document.getElementById(k);
      const badge = node.querySelector(".block-head .n");
      const cnt = badge ? badge.textContent.trim() : "";
      live.push(k);
      html += `<button data-rail="${esc(k)}"><i></i>${esc(RAIL_LABEL[k] || k)}`
        + (cnt ? `<span class="cnt">${esc(cnt)}</span>` : "") + `</button>`;
    }
  }
  const sig = html + "|" + [...RAIL_COLLAPSED].sort().join(",");
  observeRail(live);
  mirrorDrawer(html, sig, live);
}
/* Append the open drawer's own contents list, if it has one. `html`/`sig` come from the
 * caller rather than from the rail, because the rail is only rewritten when its own
 * signature changes and the drawer can turn over independently of it. */
/* Re-append the open drawer's contents list to the rail.
 *
 * The rail has two halves: the page's own sections, and the sections of whatever subject is
 * open in the right-hand drawer. They are written together, from one place, because they
 * share a single `rail.dataset.sig` and a write from either half has to account for the
 * other — the earlier arrangement, in which `buildRail()` owned the rail and this function
 * appended to it, lost the page half whenever the page half happened to be unchanged.
 *
 * `baseHtml` is the rail's current markup, so a second call trims the previous mirrored
 * half before re-deriving it and the result is idempotent. */
/* Re-append the open drawer's contents list to the rail.
 *
 * The rail has two halves: the page's own sections, and the sections of whatever subject is
 * open in the right-hand drawer. Both are written here, from one place, because they share
 * a single `rail.dataset.sig` and a write from either half has to account for the other.
 *
 * The signature is computed from the markup that is about to be written, never from a
 * caller-supplied string: an earlier version compared a caller's idea of the page half
 * against the signature the last write happened to leave, and when the two disagreed the
 * guard skipped a write that had not actually happened — the rail kept the previous route's
 * contents while its signature claimed the new ones, and even re-running the builder could
 * not recover, because the stale signature said "already correct". Comparing against what
 * is on screen, and writing whenever they differ, cannot get into that state. */
function mirrorDrawer(pageHtml, pageSig, live){
  const rail = document.getElementById("rail");
  if (!rail) return;
  const host = document.getElementById("drawer");
  const heads = (host && host.innerHTML.trim())
    ? [...host.querySelectorAll("h3.sub[data-secsection]")] : [];
  let markup = pageHtml;
  let sig = pageSig + "|n";
  if (heads.length){
    const subOpen = !RAIL_COLLAPSED.has("SUBJ");
    let extra = `<button class="rt${subOpen ? "" : " shut"}" data-rail-group="SUBJ"
      aria-expanded="${subOpen ? "true" : "false"}"
      title="${subOpen ? "收起" : "展开"}「当前主体」"><i class="tw"></i>当前主体
      <span class="cnt">${heads.length}</span></button>`;
    if (subOpen){
      for (const h of heads){
        const label = h.dataset.secsection;
        extra += `<button data-rail="${esc(label)}" data-railsub="${esc(label)}"
          data-drawer-sec="1"><i></i>${esc(label)}</button>`;
      }
    }
    markup = pageHtml + extra;
    sig = pageSig + "|d" + extra;
  }
  /* The signature describes `markup`, so a match really does mean the DOM already holds it.
   * The `innerHTML` comparison is the belt to that braces: it catches the case where the
   * sig says one thing and the document says another, which is exactly the state a stale
   * caller-supplied signature used to create. */
  if (rail.dataset.sig === sig && rail.innerHTML === markup) return;
  rail.dataset.sig = sig;
  rail.innerHTML = markup;
  if (heads.length) observeRail(live);
}
function wireRail(){
  /* Delegation, once. `buildRail()` replaces `#rail`'s markup whenever the signature
   * changes, and `wireRail()` used to hand a fresh listener to every row it had just
   * written. The two call sites that raced — a `hashchange` firing while the previous
   * route's rebuild was still pending — could therefore double-bind a row, so a single
   * click on a group heading toggled it twice and looked like it did nothing. The fix is
   * that binding belongs to the container, and lives with the container's markup. */
  if (railBound) return;
  const rail = document.getElementById("rail");
  if (!rail) return;
  railBound = true;
  rail.addEventListener("click", (ev) => {
    const g = ev.target.closest("#rail [data-rail-group]");
    if (g){
      const tid = g.dataset.railGroup;
      if (RAIL_COLLAPSED.has(tid)) RAIL_COLLAPSED.delete(tid); else RAIL_COLLAPSED.add(tid);
      /* On a paged route `buildRail()` rebuilds the page half, which this toggle does not
       * affect, so it can early-return on an unchanged signature — and the mirrored half
       * would keep showing the old state. Re-derive it from the markup already there. */
      if (tid === "SUBJ"){
        const railEl = document.getElementById("rail");
        /* Only the disclosure flag changed, so the page half is reused verbatim and the
         * mirrored half is re-derived from the open drawer. `trimMirror` drops whatever
         * mirrored rows are already on screen first, so the toggle is idempotent. */
        mirrorDrawer(trimMirror(railEl.innerHTML),
                     "subj:" + [...RAIL_COLLAPSED].sort().join(","), []);
        return;
      }
      buildRail();
      return;
    }
    const b = ev.target.closest("#rail [data-rail]");
    if (!b) return;
    /* Two kinds of row share `data-rail`. A page block scrolls to the section it names;
     * a per-subject drawer row carries `data-railsub` and belongs to whatever drawer the
     * rail is currently describing, so it opens that drawer and its section instead. */
    if (b.dataset.railsub){
      /* A mirrored row belongs to the drawer, which is its own scroll container — the
       * window does not move when it scrolls, and `scrollIntoView` would walk up and move
       * the page instead. Scrolling the box by hand leaves the page where the reader left
       * it while the panel jumps to the section. */
      const node = subjectSection(b.dataset.railsub);
      if (!node) return;
      const box = document.getElementById("drawer");
      if (!box) return;
      const top = node.getBoundingClientRect().top - box.getBoundingClientRect().top
        + box.scrollTop - 8;
      box.scrollTo({ top: Math.max(0, top), behavior: "smooth" });
      return;
    }
    const node = document.getElementById(b.dataset.rail);
    if (!node) return;
    const top = node.getBoundingClientRect().top + window.scrollY - 74;
    window.scrollTo({ top: Math.max(0, top), behavior: "smooth" });
    flashBlock(node);
  });
}
/* A rail row names a block, and a block that is already on screen cannot be scrolled to. On
 * the 999 chapter pages — most of them shorter than the viewport — that made every row look
 * dead: the reader clicked 本章剧情 and nothing anywhere on screen changed. The flash is the
 * missing half of the feedback, and it is honest on a long page too, where it marks the block
 * the viewport actually came to rest on. */
let FLASH_T = 0;
function flashBlock(node){
  if (!node) return;
  node.classList.remove("rail-flash");
  void node.offsetWidth;             // restart the animation if one is already running
  node.classList.add("rail-flash");
  clearTimeout(FLASH_T);
  FLASH_T = setTimeout(() => node.classList.remove("rail-flash"), 1300);
}
/* The rail mirrors the drawer's own contents list. The drawer's headings repeat across
 * entities — `人物特征` is on all of them and several pages share `sec-param`/`sec-ref` as
 * block ids — so the identity of a mirrored row is its *label*, resolved against whichever
 * drawer is open right now. Asking the DOM beats keeping a second copy of "current
 * subject" that could drift from `RT`. */
function subjectSection(label){
  const host = document.getElementById("drawer");
  if (!host || !label) return null;
  const heads = [...host.querySelectorAll("h3.sub")];
  return heads.find(h => (h.textContent || "").trim() === label) || null;
}
function observeRail(keys){
  if (railObserver){ railObserver.disconnect(); railObserver = null; }
  if (typeof IntersectionObserver !== "function") return;
  railObserver = new IntersectionObserver((entries) => {
    for (const en of entries){
      if (!en.isIntersecting) continue;
      const id = en.target.id;
      for (const b of document.querySelectorAll("#rail [data-rail]")){
        b.classList.toggle("on", b.dataset.rail === id);
      }
    }
  }, { rootMargin: "-74px 0px -70% 0px", threshold: 0 });
  for (const k of keys){
    const n = document.getElementById(k);
    if (n) railObserver.observe(n);
  }
}

function scheduleGraph(c, wasLive){
  const host = document.getElementById("cy");
  if (!host) return;
  /* Whether the graph is current is decided by asking the DOM, not by a cached chapter
   * number. Re-rendering the graph section replaces `#cy` with a fresh empty div while
   * `CY` and `graphChapter` both still describe the *old* node, so the "already drawn"
   * shortcut used to fire and leave the new container blank — the legend and the canvas
   * stayed empty until the reader happened to force another repaint. Comparing the node
   * the instance was built on catches that, because a rebuilt section always gives a new
   * one. */
  if (CY && CY.container() === host && !wasLive && graphChapter === c) return;
  if (graphObserver){ graphObserver.disconnect(); graphObserver = null; }
  const visible = () => {
    const r = host.getBoundingClientRect();
    return r.bottom > 0 && r.top < (window.innerHeight || 800);
  };
  const draw = () => { graphObserver = null; graphChapter = c; paintRadar(); buildGraph(c); };
  if (visible() || typeof IntersectionObserver !== "function"){
    draw();
    return;
  }
  graphObserver = new IntersectionObserver((entries) => {
    for (const en of entries){
      if (en.isIntersecting){ graphObserver.disconnect(); draw(); break; }
    }
  }, { rootMargin: "200px" });
  graphObserver.observe(host);
}
function wire(c){
  for (const el of document.querySelectorAll("[data-entity]")){
    /* A card on a *page* opens that subject's page; only the drawer's own
     * cross-references swap the panel. Binding everything to `showEntity()` was why a
     * subject page's cards re-pointed the side panel instead of navigating, and why the
     * chip fix above had nothing to do — the direct listener runs before delegation. */
    el.addEventListener("click", ev => {
      ev.preventDefault();
      if (el.dataset.drawerLink) showEntity(el.dataset.entity);
      else openEntityRoute(el.dataset.entity, el.dataset.kind);
    });
  }
  for (const el of document.querySelectorAll("[data-close]")) el.addEventListener("click", closeDrawer);

  /* Graph view switching. The mode is global state rather than per-block state, because
   * the reader chose "思维导图" for the subject they are studying, not for this one
   * section of the page — coming back from a page should not silently revert to sectors. */
  for (const el of document.querySelectorAll("[data-gmode]:not([data-wired])")){
    el.dataset.wired = "1";
    el.addEventListener("click", () => {
      GMODE = el.dataset.gmode;
      /* Focus the mind map on whoever the reader was just looking at, when there is one.
       * Following the reader's attention is the difference between "a mind map" and "the
       * mind map I wanted". */
      if (GMODE === "mind" && S.sel && ENT.has(S.sel)) GFOCUS = S.sel;
      for (const b of document.querySelectorAll("[data-gmode]"))
        b.setAttribute("aria-pressed", b === el ? "true" : "false");
      buildGraph(c);
    });
  }

  const gf = document.getElementById("g-fit");
  if (gf) gf.addEventListener("click", () => {
    if (CY) CY.animate({ fit: { padding: 34 }, duration: 320 });
    else { const w = document.getElementById("cy"); if (w) w.scrollTop = 0; }
  });
  const gh = document.getElementById("g-hero");
  if (gh) gh.addEventListener("click", () => {
    /* In the mind map "只看主角" means "make the protagonist the hub", which is the same
     * intent expressed in that view's own vocabulary. */
    if (GMODE === "mind"){
      const hero = A(G.metadata && G.metadata.protagonists)[0];
      if (hero && ENT.has(hero)){ GFOCUS = hero; buildGraph(c); }
      return;
    }
    if (!CY) return;
    const hero = CY.nodes().filter(n => n.data("protagonist") || PRO.has(n.id()));
    if (hero.length) CY.animate({ fit: { eles: hero.closedNeighborhood(), padding: 70 }, duration: 320 });
  });
  /* Zoom changes whether a hovered sector's names are legible, so the class that shows
   * them has to follow the viewport, not just the pointer.
   *
   * This has to re-run the same fitting pass the hover used. The earlier version simply
   * switched every `.zoned` node to loud once the zoom passed the threshold, which named
   * 354 characters at once and re-created the overlap the rest of this file works to
   * avoid — the threshold answers "is there room?" in aggregate, and the pass answers it
   * per node, which is the question that decides whether two names actually touch.
   *
   * It is bound inside `buildGraph` rather than here: this function runs once at startup,
   * when `CY` is still null because the graph is built lazily when its block scrolls into
   * view. Registering here silently bound nothing at all, and the handler it was supposed
   * to install — the one that re-fits names on zoom — never existed. */
  /* The library renders a budgeted slice of the agents, but the filter must range
   * over *every* agent that is live at this chapter. Typing the name of someone who
   * debuts in chapter 700 and only gets an "expand" button would otherwise match
   * nothing — the card is not in the DOM to be filtered. So the query is resolved
   * against the full as-of set and the grid is re-rendered from that result. */
  /* Sort lives in FILTER so a chapter scrub does not reset the reader's choice. */
  function libRows(c){
    const kinds = ["character", "organization", "creature"];
    const all = snap(c).ent.filter(e => kinds.includes(e.type));
    const q = FILTER.cards.q.toLowerCase();
    const rows = all.filter(e => {
      if (FILTER.cards.kind !== "all" && e.type !== FILTER.cards.kind) return false;
      if (!q) return true;
      return [e.name, e.summary, A(e.aliases).join(" "), e.id].join(" ").toLowerCase().includes(q);
    });
    const mode = FILTER.cards.sort || "degree";
    if (mode === "name") rows.sort((a, b) => String(a.name).localeCompare(String(b.name), "zh"));
    else if (mode === "chapter") rows.sort((a, b) =>
      (N(a.first_chapter) ?? 1e9) - (N(b.first_chapter) ?? 1e9)
      || String(a.name).localeCompare(String(b.name), "zh"));
    else rows.sort((a, b) => (b.type === "character") - (a.type === "character")
      || (RELS.get(b.id) || []).length - (RELS.get(a.id) || []).length
      || String(a.name).localeCompare(String(b.name), "zh"));
    return rows;
  }
  function paintLib(){
    const grid = document.getElementById("lib-grid");
    if (!grid) return;
    const all = libRows(S.chapter);
    const pg = pageSlice("cards", all);
    /* Re-painting an identical grid on every `render()` would undo the sectioned
     * caching, since `render()` walks the whole page on each slider step. The page number
     * and sort are part of the signature or the controls would appear to do nothing. */
    const sig = [S.chapter, FILTER.cards.q, FILTER.cards.kind, FILTER.cards.sort,
                 pg.page, all.length].join("|");
    const tally = document.getElementById("lib-tally");
    if (tally) tally.textContent = `${all.length}`;
    const host = document.getElementById("lib-pager");
    /* Quantise the caption: "第 97–144 条 / 共 279 条" flips on every page turn, which is
     * the point, but the sig above only has the page number — the caption has to be
     * rebuilt whenever either changes, so it rides with the grid. */
    if (grid.dataset.sig === sig){ return; }
    grid.dataset.sig = sig;
    grid.innerHTML = pg.slice.map(e => entityCard(e, S.chapter)).join("");
    if (host) host.innerHTML = pager("cards", pg);
    for (const el of grid.querySelectorAll("[data-entity]")){
      el.addEventListener("click", ev => {
        ev.preventDefault();
        if (el.dataset.drawerLink) showEntity(el.dataset.entity);
        else openEntityRoute(el.dataset.entity, el.dataset.kind);
      });
    }
    /* Page turns must not silently strand the reader at the bottom of the grid. */
    for (const el of host ? host.querySelectorAll("[data-page]") : []){
      el.addEventListener("click", () => {
        PAGE.cards = +el.dataset.to;
        paintLib();
        const b = document.getElementById("block-entities");
        if (b) b.scrollIntoView({ behavior: "smooth", block: "start" });
      });
    }
  }
  const find = document.getElementById("lib-find");
  if (find) find.addEventListener("input", () => {
    FILTER.cards.q = find.value.trim();
    PAGE.cards = 1;          /* a new query starts at page one, not page seven */
    paintLib();
  });
  const sortSel = document.getElementById("lib-sort");
  if (sortSel) sortSel.addEventListener("change", () => {
    FILTER.cards.sort = sortSel.value; PAGE.cards = 1; paintLib();
  });
  for (const btn of document.querySelectorAll("[data-lib]")){
    btn.addEventListener("click", () => {
      for (const b of document.querySelectorAll("[data-lib]")) b.classList.remove("on");
      btn.classList.add("on");
      FILTER.cards.kind = btn.dataset.lib;
      PAGE.cards = 1;
      paintLib();
    });
  }
  if (document.getElementById("lib-grid")) paintLib();
  /* `repaint()` has to be able to drive the library too, and `paintLib` is closed over
   * `wire`'s scope. Handing it out through one named hook is clearer than promoting four
   * nested helpers to module scope and threading the filter state through each. */
  LIB_PAINT = paintLib;
  /* `#cs-find` is deliberately *not* bound here: paging the chapter list replaces the
   * block's innerHTML and with it the input node, so the listener has to be re-attached
   * on every repaint. `wireListHandlers()` owns that job. */
  const csJump = document.getElementById("cs-jump");
  if (csJump) csJump.addEventListener("click", () => {
    const raw = prompt("跳到第几章？（" + MIN_CH + "–" + MAX_CH + "）");
    if (raw == null) return;
    const n = parseInt(String(raw).replace(/[^0-9]/g, ""), 10);
    if (!isFinite(n)) return;
    setChapter(clamp(n), true);
    const blk = document.getElementById("block-chapter_summaries");
    if (blk) blk.scrollIntoView({ behavior: "smooth", block: "start" });
  });
  wireListHandlers();
}
/* Assigned by `wire()`. Null before the first render, which is why callers guard. */
let LIB_PAINT = null;
function paintLibNow(){ if (LIB_PAINT) LIB_PAINT(); }
/* The list controls (pager, jump box, filter chips) are rebuilt whenever a list block is
 * re-rendered — including by the pager itself — so they are wired by a function rather
 * than once at `wire()` time. The `data-wired` marker guards against double-binding a
 * node that survived a partial repaint. */
function wireListHandlers(){
  for (const el of document.querySelectorAll("[data-page]:not([data-wired])")){
    el.dataset.wired = "1";
    el.addEventListener("click", () => {
      const k = el.dataset.page;
      PAGE[k] = +el.dataset.to;
      repaint(k);
    });
  }
  for (const el of document.querySelectorAll("[data-page-jump]:not([data-wired])")){
    el.dataset.wired = "1";
    const jump = () => {
      if (el.value === "") return;
      const k = el.dataset.pageJump;
      const n = parseInt(String(el.value).replace(/[^0-9]/g, ""), 10);
      el.value = "";
      if (!isFinite(n)) return;
      PAGE[k] = n;
      repaint(k);
    };
    el.addEventListener("keydown", ev => { if (ev.key === "Enter") jump(); });
    el.addEventListener("blur", go);
  }
  for (const el of document.querySelectorAll("[data-filter]:not([data-wired])")){
    el.dataset.wired = "1";
    el.addEventListener("click", () => {
      const k = el.dataset.filter;
      if (k === "things"){
        FILTER.things[el.dataset.axis] = el.dataset.value;
        PAGE[el.dataset.axis] = 1;
        repaint(el.dataset.axis);
      } else {
        FILTER[k] = el.dataset.value;
        PAGE[k] = 1;
        repaint(k);
      }
    });
  }
  /* Sort selects, same rebuild problem as the text filter: replacing a block's innerHTML
   * takes the `<select>` with it, so the change listener is re-attached here. The chosen
   * value survives because it lives in FILTER, not in the DOM. */
  for (const el of document.querySelectorAll("[data-sort]:not([data-wired])")){
    el.dataset.wired = "1";
    el.addEventListener("change", () => {
      const k = el.dataset.sort;
      const axis = el.dataset.axis;
      if (k === "things"){
        FILTER.things[axis] = el.value;
        /* `axis` is `item_sort` but the stream slot is `items` — repainting the singular
         * name found nothing in the map and returned without a word, so the reader
         * changed the order and the grid stayed put. */
        const type = axis.replace(/_sort$/, "") + "s";
        PAGE[type] = 1;
        repaint(type);
      } else {
        FILTER[k] = FILTER[k] && typeof FILTER[k] === "object" ? FILTER[k] : {};
        FILTER[k].sort = el.value;
        PAGE[k] = 1;
        repaint(k);
      }
    });
  }
  /* The chapter filter is a text box rather than a chip, so it needs its own arm here.
   * Binding it once in `wire()` was not enough: paging the chapter list calls `repaint`,
   * which replaces the block's innerHTML and therefore the input node itself. The fresh
   * input had no listener, so the filter worked until you turned a page and then quietly
   * stopped narrowing anything. */
  for (const el of document.querySelectorAll("[data-textfilter]:not([data-wired])")){
    el.dataset.wired = "1";
    el.addEventListener("input", () => {
      const k = el.dataset.textfilter;
      FILTER[k] = el.value.trim();
      PAGE[k] = 1;
      repaint(k);
      /* Keep the caret in the box the reader is typing into: `repaint` swapped the node
       * out from under them, which would otherwise drop focus after the first keystroke. */
      const fresh = document.querySelector(`[data-textfilter="${k}"]`);
      if (fresh && fresh !== document.activeElement){
        fresh.focus();
        try { fresh.setSelectionRange(fresh.value.length, fresh.value.length); } catch (e) {}
      }
    });
  }
  for (const el of document.querySelectorAll("[data-jump]:not([data-wired])")){
    el.dataset.wired = "1";
    el.addEventListener("click", () => {
      const target = document.getElementById("block-" + el.dataset.jump);
      if (target) target.scrollIntoView({ behavior: "smooth", block: "start" });
    });
  }
}
/* Repaint one block by key without walking the whole stream. `render()` diffs 18 section
 * signatures on every call, which is right for a chapter scrub but wasteful when only one
 * list changed — and it would fight the pager by rebuilding the very node the click came
 * from. Naming the block keeps the interaction self-contained. */
function repaint(key){
  /* Each block builder returns a complete `<section>`. The stream mounts it *inside* a
   * `.sec` wrapper whose id is the block key, so a repaint has to replace the wrapper's
   * contents rather than the wrapper itself — writing the markup over `#items` used to
   * nest a second `<section id="block-item">` inside the first one, and every repaint
   * added another. The wrappers keep their ids, the sections keep theirs, and the two
   * are addressed separately: `#items` is the slot, `#block-item` is the card. */
  const map = {
    chapters: () => ["chapters", chapterStream(S.chapter)],
    romance: () => ["romance", romanceBlock(S.chapter)],
    foreshadow: () => ["foreshadow", foreshadowBlock(S.chapter)],
    commitments: () => ["commitments", commitmentBlock(S.chapter)],
    intimacy: () => ["intimacy", intimacyBlock(S.chapter)],
    issues: () => ["issues", issueBlock(S.chapter)],
    milestones: () => ["milestones", milestoneBlock(S.chapter)],
    items: () => ["items", thingBlock(S.chapter, "item")],
    skills: () => ["skills", thingBlock(S.chapter, "skill")],
    concepts: () => ["concepts", thingBlock(S.chapter, "concept")],
  };
  if (key === "cards"){ paintLibNow(); return; }
  const fn = map[key];
  if (!fn) return;
  const [id, markup] = fn();
  const node = document.getElementById(id);
  if (!node) return;
  node.innerHTML = markup || "";
  node.dataset.sig = markup || "";
  wireListHandlers();
}

/* ------------------------------------------------------------------ *
 * boot
 * ------------------------------------------------------------------ */
const slider = document.getElementById("ch");
const badge = document.getElementById("ch-badge");
let raf = null;

function setChapter(c, immediate){
  const v = clamp(c);
  S.chapter = v;
  badge.textContent = "第 " + v + " 章";
  document.getElementById("ch-note").textContent = (v >= MAX_CH ? "全书视图" : "截至此处");
  /* On a subject page the chapter control still means something — every page is projected
   * as-of a chapter — but the stream behind it is not visible, so rebuilding fifty thousand
   * characters of hidden DOM would be pure cost. The page is repainted instead, which is
   * the surface the reader is actually looking at. */
  /* The route is the authority on which surface is visible. Reading `body.paged` instead
   * made this depend on whether `applyRoute()` had already run, which is a different
   * question from "is the reader looking at a page". */
  const paged = RT.view !== "home";
  if (raf) cancelAnimationFrame(raf);
  const paint = () => {
    if (paged) paintPage(RT);
    else render(v);
    buildSidebar();
  };
  if (immediate){ paint(); return; }
  /* One frame of coalescing: a slider drag fires many `input` events per frame and
   * the page rebuilds a hundred-odd cards each time. Waiting one frame keeps the
   * scrub smooth without ever showing a stale chapter. */
  raf = requestAnimationFrame(() => { raf = null; paint(); });
}

document.addEventListener("keydown", ev => {
  if (CM.open){
    if (ev.key === "ArrowDown"){ ev.preventDefault(); cmMove(1); return; }
    if (ev.key === "ArrowUp"){ ev.preventDefault(); cmMove(-1); return; }
    if (ev.key === "Enter"){ ev.preventDefault(); cmRun(); return; }
    if (ev.key === "Escape"){ ev.preventDefault(); closePalette(); return; }
    return;
  }
  if (ev.key === "Escape"){
    /* Escape unwinds one layer at a time, outermost first: the palette, then the drawer,
     * then the route. A subject page is a place, so Escape leaves it — the same way it
     * leaves any page. */
    if (DNAV.length) drawerBack();
    else if (document.body.classList.contains("drawer-open")) closeDrawer();
    else if (RT.view !== "home") go("home");
  }
});
/* One delegated listener for the whole document: the drawer's inner HTML is replaced on
 * every push/pop, so per-node binding would have to run again each time and would leak
 * listeners on the discarded nodes. */
document.addEventListener("click", ev => {
  const t = ev.target;
  if (!t || !t.closest) return;
  if (t.closest("#cm-btn")){ openPalette(""); return; }
  const cmr = t.closest("[data-cm-row]");
  if (cmr){ cmRun(Number(cmr.dataset.cmRow)); return; }
  /* Clicking the scrim closes the palette; clicking inside the box must not. */
  if (t.id === "cmdk"){ closePalette(); return; }
  if (t.closest("[data-close]")){ closeDrawer(); return; }
  if (t.closest("[data-dback]")){ drawerBack(); return; }
  const ent = t.closest("[data-entity]");
  if (ent){
    /* `data-entity` appears on two surfaces with two different meanings. `data-drawer-link`
     * marks the drawer's cross-references: the reader is already reading one subject and
     * wants to follow a thread, so the panel swaps contents and the previous one stays
     * reachable through the back trail. Everything else — an alias chip, a card — is a
     * page-level doorway and opens that subject's own page.
     *
     * Both cases need `preventDefault`: the chips are anchors, and letting the default run
     * pushes whatever sits in `href` onto the hash. These used to be `href="#"`, so a click
     * set the hash to "" and the router read that as "no route" — the reader was thrown
     * back to the overview instead of the subject they had just clicked. */
    ev.preventDefault();
    if (ent.dataset.drawerLink) showEntity(ent.dataset.entity);
    else openEntityRoute(ent.dataset.entity, ent.dataset.kind);
    return;
  }
  const gotoEl = t.closest("[data-goto]");
  if (gotoEl){ openDrawerLink(gotoEl.dataset.goto); return; }
  const ch = t.closest("[data-goto-chapter]");
  if (ch){ openChapterDrawer(+ch.dataset.gotoChapter); return; }
  /* Expanding a folded list swaps one line of text rather than re-rendering the page, so
   * the reader keeps their scroll position — which is the whole point of folding instead
   * of truncating. `hidden` is toggled on the sibling container the button controls. */
  const fold = t.closest("[data-fold]");
  if (fold){
    const box = document.getElementById(fold.dataset.fold);
    if (box){
      const open = box.hasAttribute("hidden");
      if (open) box.removeAttribute("hidden"); else box.setAttribute("hidden", "");
      fold.setAttribute("aria-expanded", open ? "true" : "false");
      fold.textContent = open ? (fold.dataset.shut || "收起")
                              : (fold.dataset.open || "展开");
    }
    return;
  }
  /* TOC links scroll rather than navigate: an in-page anchor would also push a hash that
   * the router would then try to read as a route. */
  const toc = t.closest("[data-toc]");
  if (toc){
    ev.preventDefault();
    const node = document.getElementById(toc.dataset.toc);
    if (node){
      const top = node.getBoundingClientRect().top + window.scrollY - 66;
      window.scrollTo({ top: Math.max(0, top), behavior: "smooth" });
    }
    return;
  }
});
/* The palette input owns its own keystrokes: the copy is swapped on every render, so the
 * listener is bound on the document and filtered by id rather than on the node. */
document.addEventListener("input", ev => {
  const t = ev.target;
  if (!t || t.id !== "cm-input") return;
  CM.q = t.value;
  CM.sel = 0;
  CM.rows = cmSearch(CM.q);
  const list = document.getElementById("cm-list");
  if (list) list.innerHTML = cmBody();
});
/* The browser back button drives the same stack. Pushing one sentinel state per drawer
 * level means the reader's muscle memory works here as it does everywhere else.
 *
 * It now has to share the gesture with the router. Precedence: a palette over a drawer over
 * a route, because that is the order in which the overlays stack visually — undoing the
 * topmost layer is what Back means. A route change also fires `hashchange`, so this handler
 * must not clear a drawer when the reader merely navigated between pages. */
window.addEventListener("popstate", () => {
  if (CM.open){ closePalette(); return; }
  if (DNAV.length){ drawerBack(); return; }
  applyRoute();
});

/* The always-visible search box in the sidebar. It routes through the same matcher as the
 * palette rather than a second implementation — two searchers over one index is how the
 * two would come to disagree about what "苏" matches. Typing shows results inline under the
 * box; Enter opens the top hit; Escape clears. */
const sideQ = document.getElementById("side-q");
if (sideQ){
  const openTop = () => {
    const rows = cmSearch(sideQ.value);
    const hit = rows[0];
    if (!hit) return;
    sideQ.value = "";
    sideGo(hit);
  };
  sideQ.addEventListener("input", () => { paintSideHits(sideQ.value); });
  sideQ.addEventListener("keydown", ev => {
    if (ev.key === "Enter"){ ev.preventDefault(); openTop(); }
    else if (ev.key === "Escape"){ sideQ.value = ""; paintSideHits(""); sideQ.blur(); }
  });
  sideQ.addEventListener("blur", () => setTimeout(() => paintSideHits(""), 160));
  /* `/` focuses this box instead of opening the overlay palette: the sidebar is always on
   * screen, so a floating duplicate of it would be the second-best way to do the same job.
   * The palette is still reachable from its own button. */
  document.addEventListener("keydown", ev => {
    const typing = ev.target && /^(INPUT|TEXTAREA|SELECT)$/.test(ev.target.tagName || "");
    if (ev.key === "/" && !typing && !CM.open && !sideQ.disabled){
      ev.preventDefault(); sideQ.focus(); sideQ.select();
    }
  });
}
function sideGo(row){
  if (!row) return;
  if (row.kind === "entity"){
    const e = ENT.get(row.id);
    if (e) go(entityHref(row.id));
  } else if (row.kind === "chapter"){
    setChapter(Number(row.id), true);
    go("#/chapter/" + row.id);
  } else if (row.goto){
    /* The sidebar box searches the same index as the palette, so it can return the same
     * events, summaries, threads and commitments. They navigate by route rather than by
     * scrolling to an element, and they must do it here too or a sidebar hit on an event
     * would silently do nothing. */
    go(row.goto);
  } else {
    if (RT.view !== "home") go("#/");
    setTimeout(() => {
      const n = document.getElementById(row.id);
      if (n) window.scrollTo({ top: Math.max(0, n.getBoundingClientRect().top + window.scrollY - 90), behavior: "smooth" });
    }, 60);
  }
}
function paintSideHits(q){
  let host = document.getElementById("side-hits");
  if (!host){
    host = document.createElement("div");
    host.id = "side-hits";
    const tree = document.getElementById("side-tree");
    if (tree) tree.parentNode.insertBefore(host, tree);
  }
  const needle = String(q || "").trim();
  if (!needle){ host.innerHTML = ""; return; }
  const rows = cmSearch(needle).slice(0, 9);
  host.innerHTML = rows.length
    ? `<div class="side-h">检索结果<span class="n">${rows.length}</span></div>`
      + rows.map((r, i) => `<button class="side-hit" data-side-hit="${i}">
          <span class="nm">${esc(r.name)}</span><span class="sb">${esc(r.sub)}</span></button>`).join("")
    : `<div class="side-h">无匹配</div><div class="side-none">换个说法试试：人物名、物品名，或章号。</div>`;
  for (const b of host.querySelectorAll("[data-side-hit]")){
    b.addEventListener("mousedown", ev => {
      ev.preventDefault();
      sideGo(rows[Number(b.dataset.sideHit)]);
      sideQ.value = ""; paintSideHits("");
    });
  }
}

slider.value = String(MAX_CH);
document.getElementById("c-start").textContent = String(MIN_CH);
document.getElementById("c-end").textContent = String(MAX_CH);
slider.addEventListener("input", () => setChapter(N(slider.value)));
/* A deep link has to win on first paint: the page renders the routed view, not the stream,
 * and only then arms the ready flag the acceptance harness waits on.
 *
 * The order matters and is not interchangeable. `applyRoute()` is what sets `body.paged`,
 * and `setChapter()` decides between repainting the page and repainting the stream by
 * asking for that class. Calling `setChapter()` first therefore always took the stream
 * branch: on a deep link to a subject the page was rendered correctly but the rail was
 * built from the home stream's blocks, and nothing later rebuilt it, because the rail's
 * signature already claimed to describe the routed page. */
applyRoute();
setChapter(MAX_CH, true);
window.__atlasReady = true;
"""


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--graph", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path, help="Run directory; dashboard.html is written here")
    parser.add_argument("--protagonist-id", action="append", default=[])
    parser.add_argument("--relation-gap-threshold", type=int, default=3)
    parser.add_argument("--cutoff", type=int, default=None)
    parser.add_argument("--vocabulary", type=Path, default=None)
    parser.add_argument("--style", type=Path, default=None, help="style-observations.json")
    parser.add_argument("--name", default="dashboard.html")
    args = parser.parse_args()

    graph = json.loads(args.graph.resolve().read_text(encoding="utf-8"))
    style_payload = None
    if args.style and args.style.is_file():
        style_payload = json.loads(args.style.resolve().read_text(encoding="utf-8"))
    vocabulary = None
    if args.vocabulary and args.vocabulary.is_file():
        vocabulary = json.loads(args.vocabulary.resolve().read_text(encoding="utf-8"))

    # Line numbers are an audit artefact: AGENTS.md keeps them out of the reader
    # artifact, so strip them here rather than trusting every renderer to remember.
    from build_dashboard import reader_safe_data
    graph = reader_safe_data(graph)

    protagonists = list(args.protagonist_id)
    if not protagonists:
        protagonists = [e["id"] for e in (graph.get("entities") or [])
                        if isinstance(e, dict) and "protagonist" in (e.get("tags") or [])]

    model = build_model(graph, protagonists, args.relation_gap_threshold, args.cutoff, vocabulary, style_payload)
    html_text = build_html(model)
    out_dir = args.out.resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    target = out_dir / args.name
    atomic_write_text(target, html_text)

    entity_count = model["counts"]["entities"]
    size_mb = len(html_text.encode("utf-8")) / 1024 / 1024
    print(json.dumps({
        "output": str(target),
        "size_mb": round(size_mb, 2),
        "entities": entity_count,
        "tiers": {"agent": model["counts"]["tier_agent"],
                  "thing": model["counts"]["tier_thing"],
                  "world": model["counts"]["tier_world"]},
        "protagonists": protagonists,
        "chapters": [model["graph"]["metadata"].get("chapter_start"), model["graph"]["metadata"].get("chapter_end")],
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
