#!/usr/bin/env python3
"""Pre-merge reconciliation report for parallel fragment extraction.

Runs between "every pass has written its fragment" and `merge_graph.py`. It is
read-only: it reports the divergence that parallel passes produce and prints the
exact `--id-map` arguments to fix the mechanical part, so the main agent decides
rather than discovering the problem after the merge.

Checks, in the order the merged graph would suffer from them:

0. `fragment_gate`          — first, that the passes actually produced files:
                              the fragment count, any file with an empty or
                              near-empty `evidence` array, and any prepared
                              chapter that no fragment claims. A pass that
                              narrated its result instead of writing it leaves no
                              file at all, and `--input fragments/fragment-*.json`
                              globs around the gap, so the lost range merges as
                              "nothing happened here" and only surfaces later as
                              a pile of `bad_participant_ref` errors that reads
                              like a modelling mistake. Fragments declaring
                              `metadata.supplementary: true` are exempt from the
                              empty-evidence test and listed separately, since a
                              supplementary fragment restates records the chapter
                              fragments already evidenced.
1. `duplicate_entity_ids`   — one id declared twice with a different name or type.
2. `entity_first_chapter`   — one id declared with different `first_chapter`
                              values (a fragment boundary is the usual cause).
3. `romance_pair_duplicates`— several routes for one (protagonist, character)
                              pair, with a ready-to-paste `--id-map` line. A
                              route restated with only `id` plus one field is
                              resolved against the fragment that declares it in
                              full, so a supplementary stub does not collapse
                              unrelated routes into one ("", "") group;
                              `romance_routes_without_pair` names the ones that
                              resolve nowhere.
4. `dangling_evidence`      — an `ev_*` id referenced by a record but never
                              declared by any fragment.
5. `record_id_collisions`   — the same record id in two fragments for a
                              non-strict kind (strict kinds are merge errors).
6. `duplicate_quotes`       — a quotation that occurs more than once inside its
                              own chapter, so line resolution is ambiguous.
7. `undeclared_cast`        — a name the chapters use repeatedly that no
                              fragment turned into an entity (the cast that falls
                              through the fragment boundary because it looks like
                              scenery in one pass and a supporting role in the
                              next). Ranked, not decided: it also surfaces
                              non-names in a corpus full of 「XX地」「XX的」
                              phrasing, so read the list rather than acting on it.

Exit code is 0 by design: every finding is a question, not an error. Findings 0
(a lost pass), 1 and 4 will fail validation if left alone; the rest are
judgement calls.

Usage:
    python plan_reconciliation.py --run-dir runs/<book> [--fragments GLOB]
    python plan_reconciliation.py --run-dir runs/<book> --json plan.json
"""

from __future__ import annotations

import argparse
import collections
import json
import re
import sys
from pathlib import Path

ENTITY_PREFIXES = (
    "char_", "skill_", "item_", "org_", "loc_", "creature_", "concept_",
    "title_", "axis_", "martial_soul_", "event_", "rel_", "sc_", "fs_", "ri_",
    "rom_", "ev_",
)
NON_STRICT = ("entities", "relations", "romance_routes", "foreshadowing", "review_issues")
ID_IN_STRING = re.compile(r"\b(?:%s)[a-z0-9_]+\b" % "|".join(ENTITY_PREFIXES))
SPEECH = "说道问喊叫答骂笑想"
# Characters that never occur inside a Chinese personal name. A candidate
# containing any of them is a phrase fragment, not a name: 「明大声地说」 yields
# 「明大声地」+说, 「何桃关心地说」 yields 「关心地」+说.
NAME_STOP_CHARS = frozenset(
    "的地得着了过是不没有就也还都很太又再只才已在和与而但却则因所被把让给对"
    "虽然当这样么呢吧啊呀哦嗯"
    "我你他她它咱谁这那哪什怎"
    "好意思心气声"
    "说问道喊叫答骂笑想"
    "个们些里外上下前后中间"
)
# Words that survive the character filter but are ordinary vocabulary.
NOT_NAMES = {
    "高兴", "明白", "明日", "白天", "东西", "地方", "时间", "石头", "金子",
    "厉害", "英雄", "王者", "王国", "马路", "江水", "金身", "白天鹅",
    "美人", "美女", "男人", "女人", "少女", "少年", "老人", "青年", "中年",
    "家伙", "庄家", "客人", "顾客", "主人", "对方", "众人", "旁人",
    # Adverb / conjunction debris and truncated descriptions that still pass the
    # adjacency test because the book writes 「其实说起来」 or 「漂亮女孩说道」.
    # Curated from the false positives item 7 actually reported on this book.
    "其实", "早知", "听听", "天开", "边用", "边淫", "忙高兴", "忙高",
    "漂亮", "漂亮女", "清秀", "清秀女", "瘦小", "羞涩", "柜台",
    "美女护", "胖男人", "姐丰满",
    # 「与蔡东风说起玩笑。」 yields 「起玩」+「笑」: 笑 is a speech verb, but
    # 「玩笑」 is a noun, so the token is debris rather than a speaker.
    "起玩",
}
# Kinship and occupational address forms: legitimate recurring roles, but not
# personal names. Kept in the report under `kind: "role"` so the reader is not
# asked to decide whether 「妈妈」 is a name.
ROLE_WORDS = {
    "妈妈", "爸爸", "爷爷", "奶奶", "姥姥", "外公", "外婆", "姐姐", "哥哥",
    "弟弟", "妹妹", "叔叔", "阿姨", "婶婶", "大婶", "大叔", "大嫂", "大爷",
    "大哥", "大姐", "小弟", "小妹", "先生", "小姐", "太太", "夫人", "大夫",
    "老师", "同学", "朋友", "孩子", "姑娘", "老头", "老婆", "老公", "媳妇",
    "儿子", "女儿", "护士", "医生", "警察", "保安", "司机", "老板", "师父",
    "女医生", "男医生", "售货员", "服务员", "经理", "院长", "校长", "局长",
}
# Chinese web novels rarely write `陈天明说道`; they write `陈天明高兴地说道`
# or `旁边的冯豪急了，说道`. So a name is not the token adjacent to the speech
# verb — it is the token at the *front* of a short speech-attribution window.
CAST_CONTEXT_GAP = 6
# A name spends a large share of its occurrences inside speech attribution
# windows; a common word does not (自己 appears 700 times and speaks 17).
CAST_CONTEXT_RATIO = 0.25


def load_fragments(paths: list[Path]) -> list[tuple[Path, dict]]:
    out = []
    for path in paths:
        out.append((path, json.loads(path.read_text(encoding="utf-8"))))
    return out


def plausible(name: str) -> bool:
    """A candidate is a name only if none of its characters is a function word."""
    if len(name) < 2 or name in NOT_NAMES:
        return False
    return not (set(name) & NAME_STOP_CHARS)


def scan_undeclared_cast(
    run_dir: Path, declared: set[str], threshold: int, ratio: float, top: int,
    analyzed: set[int] | None = None,
) -> list[dict]:
    """Names the chapters use repeatedly that no fragment declared as an entity.

    The signal is attributed speech. For every speech verb the code looks at the
    short window in front of it and, for the closing quote, at what follows it;
    the token at the front of such a window is a speaker candidate. Because
    「陈天明说道」 and 「陈天明看着」 share the prefix 「陈天明」, candidates are
    taken as 2- and 3-character *prefixes* of the window rather than as the whole
    window, and a prefix is dropped when a shorter prefix of it is attributed at
    least as often (that is what separates 「陈天明」 from 「陈天明一」).

    A name must also be concentrated in speech context: 小宁 speaks in 19 of its
    46 occurrences, while 自己 speaks in 17 of 705. A third requirement kills the
    adverb debris the window inevitably swallows (其实/听听/边用/忙高兴): the token
    must attach to a speech verb with **no gap at all** at least once, i.e. the
    text really contains 「陈天明说道」. 「忙高兴地说道」 has a gap of 1 and is
    dropped; so is 「清秀女」 from 「清秀女孩说道」. Tokens that never speak in the
    extracted range are not detected here — this check exists to catch the
    supporting cast that falls through a fragment boundary because it looks like
    scenery in one pass and a speaking role in the next.

    `chapters/` usually holds the *whole* book while the graph covers one stretch
    of it. Scanning every chapter file would flag the cast of chapters that were
    never extracted as "missing", so the scan is bounded by the union of the
    fragments' `analyzed_chapters` when that is available. A name first seen
    outside that window is not a fragment-boundary problem and is not reported;
    the window that was actually scanned is printed in the summary.
    """
    chapters = sorted((run_dir / "chapters").glob("*.txt"))
    if not chapters:
        return []
    context: collections.Counter = collections.Counter()
    direct: collections.Counter = collections.Counter()
    chapters_seen: dict[str, set] = collections.defaultdict(set)
    first_chapter: dict[str, int] = {}
    texts: dict[int, str] = {}
    before = re.compile("([\u4e00-\u9fa5]{2,4})[^\u201d]{0,%d}?([%s])" % (CAST_CONTEXT_GAP, SPEECH))
    after = re.compile("\u201d([\u4e00-\u9fa5]{2,4})")
    adjacent = re.compile("([\u4e00-\u9fa5]{2,4})([%s])" % SPEECH)
    for path in chapters:
        try:
            number = int(path.stem)
        except ValueError:
            continue
        if analyzed is not None and number not in analyzed:
            continue
        text = re.sub(r"\s+", "", path.read_text(encoding="utf-8"))
        texts[number] = text
        for pattern in (before, after):
            for match in pattern.finditer(text):
                token = match.group(1)
                for length in (2, 3):
                    prefix = token[:length]
                    if not plausible(prefix):
                        continue
                    context[prefix] += 1
                    chapters_seen[prefix].add(number)
                    first_chapter.setdefault(prefix, number)
        for match in adjacent.finditer(text):
            token = match.group(1)
            for length in (2, 3):
                prefix = token[:length]
                if plausible(prefix):
                    direct[prefix] += 1

    total = {
        name: sum(text.count(name) for text in texts.values()) for name in context
    }
    # 「女医」and「女医生」are generated from the same occurrences and get the same
    # raw count. When a token never occurs outside its longer extension, the
    # extension is the real name and the shorter form is an artefact.
    longest_extension = {
        name: max(
            (other for other in context if other.startswith(name) and len(other) > len(name)),
            key=len, default=None,
        )
        for name in context
    }

    def covered(name: str) -> bool:
        return any(name in entity or entity in name for entity in declared)

    candidates = []
    for name, count in context.most_common():
        if count < 2 or total[name] < threshold or covered(name):
            continue
        if count / total[name] < ratio:
            continue
        # Must attach to a speech verb with no gap at least once: this is what
        # separates a speaker from adverb debris the window happens to swallow.
        if not direct.get(name):
            continue
        if any(context.get(name[:length], 0) > count for length in range(2, len(name))):
            continue
        extension = longest_extension.get(name)
        if extension and context.get(extension, 0) >= count:
            continue
        candidates.append({
            "name": name,
            "kind": "role" if name in ROLE_WORDS else "person",
            "context_mentions": count,
            "raw_mentions": total[name],
            "context_ratio": round(count / total[name], 2),
            "first_chapter": first_chapter.get(name),
            "chapters": sorted(chapters_seen[name]),
            "why": "在发言归属语境中反复出现但没有任何实体覆盖该称呼",
        })
    candidates.sort(key=lambda item: (item["kind"] != "person", -item["context_mentions"]))
    return candidates[:top]


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--run-dir", required=True, type=Path)
    parser.add_argument("--fragments", default="fragments/fragment-*.json", help="glob relative to --run-dir")
    parser.add_argument("--json", type=Path, help="write the full report as JSON")
    parser.add_argument("--cast-threshold", type=int, default=8, help="raw mentions needed to flag an undeclared name")
    parser.add_argument("--cast-ratio", type=float, default=CAST_CONTEXT_RATIO,
                        help="minimum share of a token's occurrences that must sit in speech context")
    parser.add_argument("--cast-top", type=int, default=25)
    args = parser.parse_args()

    run_dir = args.run_dir.resolve()
    paths = sorted(run_dir.glob(args.fragments))
    if not paths:
        print(f"ERROR: no fragments matched {args.fragments} under {run_dir}", file=sys.stderr)
        return 2
    fragments = load_fragments(paths)

    report: dict = {"fragments": [p.name for p in paths]}

    # 0. The gate, before any semantic check. A pass that narrated its result
    # instead of writing it leaves no file at all, and `--input
    # fragments/fragment-*.json` globs around the gap: the missing range merges
    # as "nothing happened here" and only surfaces later as a pile of
    # `bad_participant_ref` errors that reads like a modelling mistake. Count the
    # files, check each one carries evidence, and confirm the union of the
    # declared ranges covers the prepared range.
    gate: dict = {"suspect_fragments": [], "no_coverage_declared": [], "supplementary_fragments": []}
    claimed: dict[int, list[str]] = collections.defaultdict(list)
    for path, fragment in fragments:
        meta = fragment.get("metadata") if isinstance(fragment.get("metadata"), dict) else {}
        chapters = meta.get("analyzed_chapters")
        declared_range = isinstance(chapters, list) and bool(chapters)
        if not declared_range:
            span = meta.get("chapter_range")
            if isinstance(span, list) and len(span) == 2:
                chapters = list(range(min(span), max(span) + 1))
            elif isinstance(meta.get("chapter_start"), int) and isinstance(meta.get("chapter_end"), int):
                chapters = list(range(meta["chapter_start"], meta["chapter_end"] + 1))
            else:
                chapters = []
        for chapter in chapters or []:
            if isinstance(chapter, int):
                claimed[chapter].append(path.name)
        counts = {kind: len(fragment.get(kind) or []) for kind in
                  ("entities", "events", "relations", "state_changes", "foreshadowing", "evidence")}
        # A supplementary fragment is allowed to carry no evidence of its own: it
        # restates records the chapter fragments already evidenced. It declares
        # that with `metadata.supplementary: true`, so the gate does not report it
        # as a lost pass.
        supplementary = bool(meta.get("supplementary"))
        problems = []
        if not supplementary:
            if counts["evidence"] == 0:
                problems.append("evidence 为空——这一片很可能没有真正抽取")
            elif counts["evidence"] < 5:
                problems.append("evidence 少于 5 条，与十章的体量不符")
        if problems:
            gate["suspect_fragments"].append({"fragment": path.name, "counts": counts, "problems": problems})
        elif supplementary:
            gate["supplementary_fragments"].append(path.name)
        elif not declared_range and not chapters:
            # A fragment that declares neither coverage nor `supplementary` is
            # ambiguous: list it so the reader confirms which one it is.
            gate["no_coverage_declared"].append(path.name)
    manifest_path = run_dir / "source_manifest.json"
    if manifest_path.is_file():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        start, end = manifest.get("chapter_start"), manifest.get("chapter_end")
        if isinstance(start, int) and isinstance(end, int):
            gate["unclaimed_chapters"] = [n for n in range(start, end + 1) if n not in claimed]
    gate.setdefault("unclaimed_chapters", [])
    gate["shared_chapters"] = sorted(n for n, names in claimed.items() if len(names) > 1)
    gate["fragment_count"] = len(fragments)
    report["fragment_gate"] = gate

    # 1 + 2. entity identity and first_chapter across fragments
    declared: dict[str, list[tuple[str, str, str, int | None]]] = collections.defaultdict(list)
    for path, fragment in fragments:
        for entity in fragment.get("entities", []):
            declared[entity.get("id", "")].append(
                (path.name, entity.get("name"), entity.get("type"), entity.get("first_chapter"))
            )
    dup_identity, dup_first = [], []
    for entity_id, rows in declared.items():
        shapes = {(name, type_) for _, name, type_, _ in rows if name and type_}
        if len(shapes) > 1:
            dup_identity.append({"id": entity_id, "declarations": rows})
        chapters = {chapter for *_, chapter in rows if isinstance(chapter, int)}
        if len(chapters) > 1:
            dup_first.append({"id": entity_id, "first_chapter_values": sorted(chapters), "declarations": rows})
    report["duplicate_entity_ids"] = dup_identity
    report["entity_first_chapter"] = dup_first

    # 3. several routes for one pair.
    # A supplementary fragment may restate only the fields it adds, so a route
    # can reach this point as `{"id": ..., "first_meeting_chapter": ...}` with no
    # key at all. Grouping on the raw fields then collapses every such restatement
    # into one bogus ("", "") pair and reports unrelated routes as "the same
    # woman". Resolve a missing key from whichever fragment declares the route in
    # full, and park the ones that resolve nowhere.
    route_keys: dict[str, tuple[str, str]] = {}
    for _path, _fragment in fragments:
        for route in _fragment.get("romance_routes", []):
            if route.get("id") and route.get("protagonist_id") and route.get("character_id"):
                route_keys[route["id"]] = (route["protagonist_id"], route["character_id"])
    pairs: dict[tuple[str, str], list[str]] = collections.defaultdict(list)
    unresolvable: list[str] = []
    for path, fragment in fragments:
        for route in fragment.get("romance_routes", []):
            route_id = route.get("id")
            if not route_id:
                continue
            key = (route.get("protagonist_id") or "", route.get("character_id") or "")
            if not (key[0] and key[1]):
                resolved = route_keys.get(route_id)
                if resolved is None:
                    if route_id not in unresolvable:
                        unresolvable.append(route_id)
                    continue
                key = resolved
            if route_id not in pairs[key]:
                pairs[key].append(route_id)
    pair_dupes = [
        {"protagonist_id": key[0], "character_id": key[1], "route_ids": ids}
        for key, ids in pairs.items() if len(ids) > 1 and key[0] and key[1]
    ]
    report["romance_pair_duplicates"] = pair_dupes
    report["romance_routes_without_pair"] = sorted(unresolvable)
    suggested = []
    for item in pair_dupes:
        canonical = item["route_ids"][0]
        for other in item["route_ids"][1:]:
            suggested.append(f"--id-map {other}={canonical}")
    report["suggested_id_map"] = suggested

    # 4. evidence referenced but never declared
    declared_evidence = set()
    referenced: dict[str, set] = collections.defaultdict(set)
    for path, fragment in fragments:
        for record in fragment.get("evidence", []):
            declared_evidence.add(record.get("id"))
        for kind in ("entities", "events", "relations", "state_changes", "foreshadowing", "romance_routes", "review_issues"):
            for record in fragment.get(kind, []):
                for found in ID_IN_STRING.findall(json.dumps(record, ensure_ascii=False)):
                    if found.startswith("ev_"):
                        referenced[found].add(f"{path.name}:{record.get('id')}")
    dangling = [
        {"evidence_id": ev, "referenced_by": sorted(where)}
        for ev, where in sorted(referenced.items()) if ev not in declared_evidence
    ]
    report["dangling_evidence"] = dangling

    # 5. record id collisions on non-strict kinds
    collisions = []
    for kind in NON_STRICT:
        seen: dict[str, list[str]] = collections.defaultdict(list)
        for path, fragment in fragments:
            for record in fragment.get(kind, []):
                seen[record.get("id", "")].append(path.name)
        for record_id, files in seen.items():
            if len(files) > 1:
                collisions.append({"kind": kind, "id": record_id, "files": files})
    report["record_id_collisions"] = collisions

    # 6. quotations repeated inside their own chapter
    duplicates = []
    chapter_cache: dict[int, str] = {}
    for path, fragment in fragments:
        for record in fragment.get("evidence", []):
            chapter, quote = record.get("chapter"), record.get("quote") or ""
            if not isinstance(chapter, int) or not quote:
                continue
            if chapter not in chapter_cache:
                file = run_dir / "chapters" / f"{chapter:03d}.txt"
                chapter_cache[chapter] = file.read_text(encoding="utf-8") if file.is_file() else ""
            count = chapter_cache[chapter].count(quote)
            if count > 1:
                duplicates.append({
                    "evidence_id": record.get("id"), "chapter": chapter,
                    "occurrences": count, "file": path.name, "quote": quote[:60],
                })
    report["duplicate_quotes"] = duplicates

    # 7. cast that no fragment declared
    declared_names = {
        name for rows in declared.values() for _, name, _, _ in rows if name
    }
    # `chapters/` may be the whole book; the graph only covers the fragments'
    # chapters. Bound the cast scan to the extracted window, or every name that
    # first speaks in a later, never-extracted chapter is reported as missing.
    audit_window: set[int] | None = set()
    for _path, _fragment in fragments:
        _meta = _fragment.get("metadata") or {}
        _owned = _meta.get("analyzed_chapters") or []
        if not _owned and _meta.get("chapter_start") and _meta.get("chapter_end"):
            _owned = list(range(_meta["chapter_start"], _meta["chapter_end"] + 1))
        if isinstance(_owned, list):
            audit_window.update(n for n in _owned if isinstance(n, int))
    if not audit_window:
        audit_window = None
    for path, fragment in fragments:
        for entity in fragment.get("entities", []):
            for alias in entity.get("aliases") or []:
                if isinstance(alias, str):
                    declared_names.add(alias)
    cast = scan_undeclared_cast(
        run_dir, declared_names, args.cast_threshold, args.cast_ratio, args.cast_top,
        analyzed=audit_window,
    )
    # Which pass owned the chapter the name first appears in? That pass is the
    # one that should have declared it; the boundary is the usual culprit.
    owners: list[tuple[str, set]] = []
    for path, fragment in fragments:
        meta = fragment.get("metadata") or {}
        owned = meta.get("analyzed_chapters") or []
        if not owned and meta.get("chapter_start") and meta.get("chapter_end"):
            owned = list(range(meta["chapter_start"], meta["chapter_end"] + 1))
        if isinstance(owned, list) and owned:
            owners.append((path.name, set(owned)))
    for item in cast:
        item["owning_fragment"] = [
            name for name, owned in owners if item.get("first_chapter") in owned
        ]
    report["undeclared_cast"] = cast
    report["audit_window"] = sorted(audit_window) if audit_window is not None else None

    if args.json:
        args.json.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    # ---- human summary ----
    print(f"# 合并前对账：{len(fragments)} 个分片，{run_dir.name}")
    print()
    print(f"0. 分片门禁：{gate['fragment_count']} 个文件，可疑 {len(gate['suspect_fragments'])}")
    for item in gate["suspect_fragments"]:
        print(f"   {item['fragment']}: {'；'.join(item['problems'])}")
        print(f"      记录数 {item['counts']}")
    if gate["unclaimed_chapters"]:
        shown = gate["unclaimed_chapters"][:40]
        print(f"   未覆盖章节 {len(gate['unclaimed_chapters'])} 章：{shown}"
              + (" …" if len(gate["unclaimed_chapters"]) > 40 else ""))
        print("   → 先确认有没有分片根本没落盘：glob 会静默跳过缺失文件，那一整段会被当成『这里没有内容』")
    if gate["no_coverage_declared"]:
        print(f"   未声明章节覆盖、也未标 supplementary（正常只应出现补充分片）：{gate['no_coverage_declared']}")
    if gate["supplementary_fragments"]:
        print(f"   补充分片（metadata.supplementary，无自有证据）：{gate['supplementary_fragments']}")
    if gate["shared_chapters"]:
        print(f"   被两个以上分片声明覆盖的章节 {len(gate['shared_chapters'])} 章（续拆重叠时正常）")
    print(f"1. 同 ID 不同名称/类型：{len(dup_identity)}")
    if dup_identity:
        print("   （列出的是各分片的原始写法。若某个 id 已在补充分片里给出完整 name、并把其余写法收进")
        print("     aliases，合并结果就是统一的——补充分片自己也会出现在这里，属正常。）")
    for item in dup_identity:
        print(f"   {item['id']}: {item['declarations']}")
    print(f"2. first_chapter 跨分片不一致：{len(dup_first)}")
    for item in dup_first:
        print(f"   {item['id']} → {item['first_chapter_values']}（合并取最小）")
    print(f"3. 同一女主多条感情线：{len(pair_dupes)}")
    for item in pair_dupes:
        print(f"   {item['character_id']}: {item['route_ids']}")
    if suggested:
        print("   建议合并参数：")
        for flag in suggested:
            print(f"     {flag}")
    if report["romance_routes_without_pair"]:
        print(f"   无法定配对（分片只声明了 id，未声明双方；正常见补充分片）：{report['romance_routes_without_pair']}")
    print(f"4. 引用了但无人声明的证据：{len(dangling)}")
    for item in dangling:
        print(f"   {item['evidence_id']} ← {item['referenced_by']}")
    print(f"5. 非严格类型记录 ID 跨分片重复：{len(collisions)}")
    for item in collisions:
        print(f"   {item['kind']} {item['id']} in {item['files']}")
    print(f"6. 引文在章内重复出现（行号有歧义）：{len(duplicates)}")
    for item in duplicates:
        print(f"   {item['evidence_id']} 第{item['chapter']}章 ×{item['occurrences']}｜{item['quote']}")
    print(f"7. 疑似漏建实体的人物称呼（{len(report['undeclared_cast'])} 项，需人工确认）：")
    if report["audit_window"]:
        print(f"   核查窗口：第 {report['audit_window'][0]}–{report['audit_window'][-1]} 章"
              f"（共 {len(report['audit_window'])} 章，取自各分片 analyzed_chapters 的并集）")
    else:
        print("   核查窗口：未限定（各分片都没有声明 analyzed_chapters，按全部章节扫描）")
    for item in report["undeclared_cast"]:
        owner = "、".join(item.get("owning_fragment") or []) or "无分片声明覆盖"
        mark = "称呼" if item["kind"] == "role" else "人名"
        print(f"   [{mark}] {item['name']}｜发言语境 {item['context_mentions']}｜总提及 {item['raw_mentions']}"
              f"｜占比 {item['context_ratio']}｜首见第{item['first_chapter']}章｜归属分片 {owner}"
              f"｜章 {item['chapters']}")
    print()
    print("结论：1、4 若不处理会在 validate_graph 阶段报错；其余为需人工判断的疑点。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
