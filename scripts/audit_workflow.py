#!/usr/bin/env python3
"""One entry point for the chapter-audit workflow (see references/ai-workflow.md).

  survey-scaffold  deterministic hints for the whole-book survey
  survey-check     validate survey.json and seed the ID registry from it
  ids              look up, claim or list entity IDs; issue fragment numbers
  plan             lanes and units for the audit
  capsule          state before a chapter, for the worker auditing it
  recall           recall candidates for the verifier
  score            per-chapter quality into coverage-ledger.json
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from io_utils import atomic_write_json, atomic_write_text
from nkg.core.records import read_chapter_index
from nkg.workflow.capsule import build_chapter_capsule
from nkg.workflow.planner import plan_audit
from nkg.workflow.quality import card_complete, chapter_score, update_ledger
from nkg.workflow.recall import apply_verdicts, recall_candidates
from nkg.workflow.registry import AmbiguousName, IdRegistry, RegistryError
from nkg.workflow.survey import build_scaffold, seed_registry, validate_survey


def _json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _emit(value, output: Path | None) -> None:
    text = json.dumps(value, ensure_ascii=False, indent=2)
    if output:
        atomic_write_text(output, text + "\n")
    print(text if len(text) < 4000 else text[:4000] + "\n…")


def cmd_survey_scaffold(a) -> int:
    rows = read_chapter_index(a.chapters_jsonl, with_text=True, require_text=True)
    _emit(build_scaffold(rows), a.output)
    return 0


def cmd_survey_check(a) -> int:
    survey = _json(a.survey)
    chapters = [r["chapter"] for r in read_chapter_index(a.chapters_jsonl)]
    errors = validate_survey(survey, chapters)
    if errors:
        _emit({"valid": False, "errors": errors}, None)
        return 1
    registry = IdRegistry.load(a.registry)
    try:
        issued = seed_registry(registry, survey)
    except (AmbiguousName, RegistryError) as exc:
        _emit({"valid": False, "errors": [str(exc)]}, None)
        return 1
    registry.save(a.registry)
    _emit({"valid": True, "issued": issued, "warnings": registry.warnings}, None)
    return 0


def cmd_ids(a) -> int:
    registry = IdRegistry.load(a.registry)
    if a.seed_graph:
        added = registry.seed_from_graph(_json(a.seed_graph))
        registry.save(a.registry)
        _emit({"seeded": added, "warnings": registry.warnings[-20:]}, None)
    elif a.lookup:
        _emit({"name": a.lookup, "ids": registry.lookup(a.lookup)}, None)
    elif a.claim:
        entity_type, name, slug = a.claim
        try:
            entity_id, created = registry.claim(entity_type, name, slug, aliases=a.alias,
                                                first_chapter=a.first_chapter, claimed_by=a.by)
        except (AmbiguousName, RegistryError) as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            return 1
        registry.save(a.registry)
        _emit({"id": entity_id, "created": created}, None)
    elif a.issue_fragment:
        issued = registry.issue_fragment(a.issue_fragment, a.fragments_dir)
        registry.save(a.registry)
        _emit(issued, None)
    else:
        ids, text = None, None
        if a.chapters_jsonl:
            text = "\n".join(r["text"] for r in read_chapter_index(a.chapters_jsonl, a.start, a.end, with_text=True))
            ids = [entity_id for entity_id in registry.entities
                   if any(n and len(n) >= 2 and n in text for n in
                          [registry.entities[entity_id].get("name"), *(registry.entities[entity_id].get("aliases") or [])])]
        table = registry.id_table(ids, text)
        if a.output:
            atomic_write_text(a.output, table + "\n")
        print(table)
    return 0


def cmd_plan(a) -> int:
    rows = read_chapter_index(a.chapters_jsonl, a.start, a.end, with_text=a.density)
    arcs = _json(a.survey).get("arcs") if a.survey else None
    plan = plan_audit(rows, arcs=arcs, lane_chapters=a.lane_chapters, target_chars=a.target_chars,
                      max_chapters=a.max_chapters)
    _emit(plan if a.output else plan["summary"], None)
    if a.output:
        atomic_write_json(a.output, plan)
    return 0


def cmd_capsule(a) -> int:
    graph = _json(a.graph)
    text = None
    if a.chapters_jsonl:
        row = next((r for r in read_chapter_index(a.chapters_jsonl, a.chapter, a.chapter, with_text=True)), None)
        text = row.get("text") if row else None
    capsule = build_chapter_capsule(graph, a.chapter, text=text, candidate_ids=a.entity)
    _emit(capsule, a.output)
    return 0


def cmd_recall(a) -> int:
    graph = _json(a.graph)
    row = next((r for r in read_chapter_index(a.chapters_jsonl, a.chapter, a.chapter, with_text=True,
                                             require_text=True)), None)
    if row is None:
        print(f"ERROR: chapter {a.chapter} not in {a.chapters_jsonl}", file=sys.stderr)
        return 2
    _emit({"chapter": a.chapter, "candidates": recall_candidates(graph, a.chapter, row["text"])}, a.output)
    return 0


def cmd_score(a) -> int:
    graph = _json(a.graph)
    candidates = _json(a.recall)["candidates"] if a.recall else []
    verdict = _json(a.verifier) if a.verifier else None
    tally = apply_verdicts(candidates, (verdict or {}).get("candidates", {}))
    quality = chapter_score(card=card_complete(graph, a.chapter), recall_open=tally["open"],
                            recall_missed=tally["missed"],
                            verifier={"missed": verdict.get("missed", 0), "wrong": verdict.get("wrong", 0),
                                      "rounds": verdict.get("rounds", 1)} if verdict else None)
    row = update_ledger(a.ledger, a.chapter, quality) if a.ledger else {"chapter": a.chapter, "quality": quality}
    _emit(row, None)
    return 0


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="command", required=True)

    p = sub.add_parser("survey-scaffold")
    p.add_argument("--chapters-jsonl", required=True, type=Path)
    p.add_argument("--output", type=Path)
    p.set_defaults(func=cmd_survey_scaffold)

    p = sub.add_parser("survey-check")
    p.add_argument("--survey", required=True, type=Path)
    p.add_argument("--chapters-jsonl", required=True, type=Path)
    p.add_argument("--registry", required=True, type=Path)
    p.set_defaults(func=cmd_survey_check)

    p = sub.add_parser("ids")
    p.add_argument("--registry", required=True, type=Path)
    p.add_argument("--seed-graph", type=Path, help="register every entity of a merged graph")
    p.add_argument("--lookup", metavar="NAME")
    p.add_argument("--claim", nargs=3, metavar=("TYPE", "NAME", "SLUG"))
    p.add_argument("--alias", action="append", default=[])
    p.add_argument("--first-chapter", type=int)
    p.add_argument("--by", default="", help="who claims (unit or worker id)")
    p.add_argument("--issue-fragment", metavar="UNIT")
    p.add_argument("--fragments-dir", type=Path)
    p.add_argument("--output", type=Path, help="write the ID table (default action)")
    p.add_argument("--chapters-jsonl", type=Path, help="limit the table to entities these chapters name, "
                                                         "showing the names the text uses there")
    p.add_argument("--start", type=int)
    p.add_argument("--end", type=int)
    p.set_defaults(func=cmd_ids)

    p = sub.add_parser("plan")
    p.add_argument("--chapters-jsonl", required=True, type=Path)
    p.add_argument("--survey", type=Path, help="survey.json whose top-level arcs become lanes")
    p.add_argument("--start", type=int)
    p.add_argument("--end", type=int)
    p.add_argument("--lane-chapters", type=int, default=100)
    p.add_argument("--target-chars", type=int, default=10_000)
    p.add_argument("--max-chapters", type=int, default=5)
    p.add_argument("--density", action="store_true", help="read chapter text and weight units by plot density")
    p.add_argument("--output", type=Path)
    p.set_defaults(func=cmd_plan)

    p = sub.add_parser("capsule")
    p.add_argument("--graph", required=True, type=Path)
    p.add_argument("--chapter", required=True, type=int)
    p.add_argument("--chapters-jsonl", type=Path, help="to detect who the chapter mentions")
    p.add_argument("--entity", action="append", default=[], help="force-include an entity ID")
    p.add_argument("--output", type=Path)
    p.set_defaults(func=cmd_capsule)

    p = sub.add_parser("recall")
    p.add_argument("--graph", required=True, type=Path, help="graph or fragment holding the chapter's records")
    p.add_argument("--chapter", required=True, type=int)
    p.add_argument("--chapters-jsonl", required=True, type=Path)
    p.add_argument("--output", type=Path)
    p.set_defaults(func=cmd_recall)

    p = sub.add_parser("score")
    p.add_argument("--graph", required=True, type=Path)
    p.add_argument("--chapter", required=True, type=int)
    p.add_argument("--recall", type=Path, help="recall candidates JSON")
    p.add_argument("--verifier", type=Path, help="verifier verdict JSON (see references/verifier-prompt.md)")
    p.add_argument("--ledger", type=Path, help="coverage-ledger.json to update")
    p.set_defaults(func=cmd_score)

    args = ap.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
