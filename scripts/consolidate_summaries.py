#!/usr/bin/env python3
"""Fold every multiply-declared entity's `summary` into the fragment that declares it last.

`merge_value` keeps the **last** input for any non-list, non-dict field, so when
several passes each declare the same entity with a complementary `summary` the
merge silently keeps only the final pass's paragraph and reports **no conflict**.
In the 流氓老师 run that lost the origin paragraph of the protagonist to the
chapter-202 paragraph, and left two entities with no summary at all because every
declaration of them happened to carry `summary: null`.

This pass is the entity-side twin of `backfill_reader_prose.py`: it edits the
fragments, not the graph, because `graph.json` is rebuilt from `fragments/*.json`
on every merge — a hand-edited graph is wiped by the next round.

What it does, per entity declared in two or more fragments:

  1. collects each declaration's non-empty `summary`, in fragment order,
  2. cuts every summary into clauses and drops a clause already stated by an
     earlier declaration (so a pass that restated the whole story is not
     repeated verbatim),
  3. joins what is left with the book's own sentence punctuation,
  4. writes the result into the **last** fragment that declares that entity —
     the only place `merge_value` will read it from.

Dedupe works at **clause** level, not paragraph level. Paragraph level was too
coarse: two passes that state the same fact in different words both survived, so
the consolidated text repeated itself (on the 斗罗大陆II run `char_gongjue` said
"府邸位于星罗城西北五十里外……" twice and `skill_ziji_motong` restated its four
realms twice, 337 chars). Clause level removes the repetition while still
dropping no fact that no other declaration states.

Re-running is a no-op: after the first pass the last declaration already
contains every clause of every earlier text, so step 2 collapses the group to
one entry.

Two deliberate refusals:

  * an entity whose declarations are *all* empty is reported, not invented. A
    summary is content, and this pass only folds what a pass already wrote.
  * a consolidated text shorter than the longest single input is never written.

Usage:
    python consolidate_summaries.py --run-dir runs/<book-range>          # preview
    python consolidate_summaries.py --run-dir runs/<book-range> --write
    python consolidate_summaries.py --run-dir runs/<book-range> --json out.json
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

FRAGMENT_GLOB = "fragment-*.json"
# `fragment-07.json` -> 7; a supplementary `fragment-K.json` sorts last, after the
# numbered passes, which is where a consolidation fragment belongs.
NUMBERED = re.compile(r"fragment-(\d+)\.json$")

SENTENCE_END = "。！？；…"


def fragment_order(path: Path) -> tuple[int, str]:
    match = NUMBERED.search(path.name)
    if match:
        return (int(match.group(1)), path.name)
    return (10**6, path.name)


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


CLAUSE_SPLIT = re.compile(r"[^。！？；…]*[。！？；…]|[^。！？；…]+")


def split_clauses(text: str) -> list[str]:
    """Cut a summary into clauses, each keeping its own closing punctuation."""
    return [part.strip() for part in CLAUSE_SPLIT.findall(text) if part.strip()]


def join_summaries(texts: list[str]) -> str:
    """Join summaries with the book's punctuation instead of a space."""
    out = ""
    for text in texts:
        text = text.strip()
        if not text:
            continue
        if not out:
            out = text
            continue
        if out[-1] not in SENTENCE_END:
            out += "。"
        out += text
    return out


def dedupe(texts: list[str]) -> list[str]:
    """Drop a clause already stated by another declaration; keep fragment order otherwise.

    Clause level, and the containment test is done on a **punctuation-stripped**
    form. Both refinements matter on the 斗罗大陆II run: two passes often state the
    same fact with different punctuation, so a literal `in` test keeps both —

        A: 府邸位于星罗城西北五十里外；常年代表星罗帝国外出征战，……霍雨浩母子。
        B: 府邸位于星罗城西北五十里外，常年代表星罗帝国外出征战，……霍雨浩母子，是霍雨浩认定的敌人之一。

    Stripping punctuation makes A a prefix of B, so A is dropped and the superset
    survives. A clause subsumed by a longer one is dropped; a clause that states
    something no other clause states is always kept.
    """
    clauses = [clause for text in texts for clause in split_clauses(text)]
    norm = [re.sub(r"[\s。！？；…，、,.：:]+", "", clause) for clause in clauses]
    # Collapse exact normalized duplicates before containment pruning. Without
    # this pass, two equal clauses each see the other as a superset and both die.
    unique: list[tuple[str, str]] = []
    seen: set[str] = set()
    for clause, normalized in zip(clauses, norm):
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        unique.append((clause, normalized))

    kept: list[str] = []
    for index, (clause, normalized) in enumerate(unique):
        if any(index != other and normalized in other_norm
               for other, (_, other_norm) in enumerate(unique)):
            continue
        kept.append(clause)
    return kept


def scan(run_dir: Path) -> dict:
    frag_dir = run_dir / "fragments"
    paths = sorted(frag_dir.glob(FRAGMENT_GLOB), key=fragment_order)
    declarations: dict[str, list[tuple[Path, dict]]] = {}
    for path in paths:
        try:
            data = load(path)
        except (OSError, json.JSONDecodeError) as exc:
            print(f"  !! {path.name} 解析失败: {exc}")
            continue
        for entity in data.get("entities") or []:
            if isinstance(entity, dict) and entity.get("id"):
                declarations.setdefault(str(entity["id"]), []).append((path, entity))

    planned: list[dict] = []
    empty: list[dict] = []
    for entity_id, items in declarations.items():
        if len(items) < 2:
            continue
        texts = [str(e.get("summary") or "").strip() for _, e in items]
        non_empty = [t for t in texts if t]
        if not non_empty:
            empty.append({
                "entity": entity_id,
                "declared_in": len(items),
                "name": items[-1][1].get("name"),
            })
            continue
        distinct = dedupe(non_empty)
        if len(distinct) < 2:
            continue  # already consolidated (or only one pass wrote anything)
        consolidated = join_summaries(distinct)
        # 守卫用**原始段落**里最长的那条，而不是最长子句：子句级去重后
        # distinct 是一串子句，拿它比会把守卫放松掉。
        longest = max(len(t) for t in non_empty)
        if len(consolidated) < longest:
            continue  # never shrink a summary
        last_path, last_entity = items[-1]
        planned.append({
            "entity": entity_id,
            "name": last_entity.get("name"),
            "file": last_path.name,
            "parts": len(distinct),
            "before": len(str(last_entity.get("summary") or "")),
            "after": len(consolidated),
            "text": consolidated,
        })
    return {"run": run_dir.name, "fragments": len(paths), "planned": planned, "empty": empty}


def apply(run_dir: Path, planned: list[dict]) -> int:
    by_file: dict[str, dict[str, str]] = {}
    for item in planned:
        by_file.setdefault(item["file"], {})[item["entity"]] = item["text"]
    touched = 0
    for name, updates in by_file.items():
        path = run_dir / "fragments" / name
        data = load(path)
        changed = False
        for entity in data.get("entities") or []:
            if isinstance(entity, dict) and entity.get("id") in updates:
                if entity.get("summary") != updates[entity["id"]]:
                    entity["summary"] = updates[entity["id"]]
                    changed = True
        if changed:
            backup = path.with_suffix(path.suffix + ".pre-consolidate")
            if not backup.exists():
                backup.write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
            path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n",
                            encoding="utf-8")
            touched += 1
    return touched


def main() -> int:
    parser = argparse.ArgumentParser(description="把多分片实体的 summary 折进最后声明它的分片")
    parser.add_argument("--run-dir", required=True)
    parser.add_argument("--write", action="store_true", help="真正落盘（默认只预演）")
    parser.add_argument("--show", type=int, default=8, help="打印几条对照")
    parser.add_argument("--json", dest="json_path", help="把结果写成 JSON")
    args = parser.parse_args()

    run_dir = Path(args.run_dir)
    if not (run_dir / "fragments").is_dir():
        print(f"找不到分片目录：{run_dir / 'fragments'}", file=sys.stderr)
        return 2

    report = scan(run_dir)
    planned = report["planned"]
    print(f"  {report['run']:32s} 分片 {report['fragments']} 个 | "
          f"需要合并 summary 的实体 {len(planned)} 个 | 全空 {len(report['empty'])} 个"
          + ("" if args.write else "   [预演]"))
    for item in planned[:args.show]:
        print(f"    [{item['entity']}] {item['name']} @ {item['file']}  "
              f"{item['before']}→{item['after']} 字（折进 {item['parts']} 个子句）")
    if len(planned) > args.show:
        print(f"    … 另有 {len(planned) - args.show} 个")
    for item in report["empty"][:args.show]:
        print(f"    [全空] {item['entity']} {item['name']}：声明 {item['declared_in']} 次，"
              f"每次 summary 都为空——本脚本不代写内容，需人工补")

    if args.json_path:
        Path(args.json_path).write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    if args.write:
        touched = apply(run_dir, planned)
        print(f"已写入 {touched} 个分片（原文件备份为 *.pre-consolidate）；"
              f"下一步重跑 merge_graph.py 让图谱生效。")
    else:
        print("这是预演。加 --write 才会落盘。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
