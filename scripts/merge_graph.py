#!/usr/bin/env python3
"""Merge independently extracted novel-graph fragments deterministically."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path

from attribute_keys import canonicalize_attributes
from event_types import canonicalize_event_types
from intimacy_types import canonicalize_intimate_acts
from character_traits import canonical_facet, sort_traits
from level_conversions import canonicalize_level_conversions


ARRAYS = ("entities", "events", "relations", "state_changes", "romance_routes", "foreshadowing", "evidence", "review_issues", "intimate_acts", "level_conversions", "character_traits", "chapter_summaries", "item_roles", "story_arcs")
STRICT_KINDS = {"events", "state_changes", "evidence"}
SYMMETRIC_RELATION_TYPES = {
    "alter_ego_of", "close_friend_of", "companion_of", "dating", "enemy_of", "friend_of",
    "mission_partner_of", "partner_of", "rival_of", "romantic_partner_of",
    "sibling_of", "spouse_of", "sworn_sibling_of", "task_partner_of",
}


def canonicalize_character_traits(records: list) -> tuple[list, list]:
    """把中文／别名分面折回规范值，并按 (人物, 分面, 章节) 排序。

    排序不是美化：渲染要按 `chapter <= N` 取每个分面的最新一条，顺序错了就会
    显示成旧的那一版。所以排序发生在合并这一层，两个渲染器都受益。
    """
    notes: list[str] = []
    for record in records:
        raw = record.get("facet")
        canonical = canonical_facet(raw)
        if canonical != raw:
            record["facet"] = canonical
            notes.append(f"{record.get('id')}：分面 {raw} → {canonical}")
    return sort_traits(records), notes


def unique(values: list) -> list:
    result = []
    for value in values:
        if value not in result:
            result.append(value)
    return result


def merge_value(left, right, field: str):
    if left is None or left == "" or left == [] or left == {}:
        return deepcopy(right)
    if right is None or right == "" or right == [] or right == {}:
        return deepcopy(left)
    if isinstance(left, list) and isinstance(right, list):
        return unique(left + right)
    if isinstance(left, dict) and isinstance(right, dict):
        merged = deepcopy(left)
        for key, value in right.items():
            merged[key] = merge_value(merged.get(key), value, key)
        return merged
    if field in {"first_chapter", "valid_from", "planted_chapter", "first_meeting_chapter", "ambiguity_started_chapter", "confirmed_chapter", "first_sex_chapter"} and isinstance(left, int) and isinstance(right, int):
        return min(left, right)
    if field in {"last_chapter", "valid_to", "payoff_chapter"} and isinstance(left, int) and isinstance(right, int):
        return max(left, right)
    return deepcopy(right)


def merge_record(left: dict, right: dict) -> dict:
    merged = deepcopy(left)
    for field, value in right.items():
        merged[field] = merge_value(merged.get(field), value, field)
    return merged


def remap_ids(value, mapping: dict[str, str]):
    if isinstance(value, str):
        return mapping.get(value, value)
    if isinstance(value, list):
        return [remap_ids(item, mapping) for item in value]
    if isinstance(value, dict):
        return {key: remap_ids(item, mapping) for key, item in value.items()}
    return value


def relation_key(record: dict) -> tuple[str, str, str]:
    source, target = str(record.get("source_id", "")), str(record.get("target_id", ""))
    relation_type = str(record.get("relation_type", ""))
    if relation_type in SYMMETRIC_RELATION_TYPES and target < source:
        source, target = target, source
    return source, target, relation_type


def relation_pair_key(record: dict) -> str:
    """Stable, readable key for one canonical pair and semantic relation."""
    source, target, relation_type = relation_key(record)
    return f"{source}|{target}|{relation_type}"


def relation_observation(record: dict) -> dict:
    """Project one fragment declaration into append-only relationship history."""
    observation = {
        "chapter": record.get("chapter") if isinstance(record.get("chapter"), int) else record.get("valid_from"),
        "evidence_ids": unique(list(record.get("evidence_ids") or [])),
    }
    for field in ("description", "status", "valid_from", "valid_to", "close_reason"):
        value = record.get(field)
        if value not in (None, "", [], {}):
            observation[field] = deepcopy(value)
    return observation


def prepare_relation(record: dict) -> dict:
    prepared = deepcopy(record)
    prepared["pair_key"] = record.get("pair_key") or relation_pair_key(record)
    prepared["episode_id"] = record.get("episode_id") or f"{prepared['pair_key']}@{record.get('valid_from', '?')}"
    observations = [deepcopy(item) for item in (record.get("observations") or []) if isinstance(item, dict)]
    implicit = relation_observation(record)
    marker = json.dumps(implicit, ensure_ascii=False, sort_keys=True)
    if marker not in {json.dumps(item, ensure_ascii=False, sort_keys=True) for item in observations}:
        observations.append(implicit)
    prepared["observations"] = observations
    return prepared


def merge_relation_records(left: dict, right: dict) -> dict:
    """Merge one uninterrupted episode without losing scalar qualifications."""
    merged = merge_record(left, right)
    merged["id"] = left["id"]
    merged["source_id"] = left.get("source_id")
    merged["target_id"] = left.get("target_id")
    merged["pair_key"] = left.get("pair_key") or relation_pair_key(left)
    merged["episode_id"] = left.get("episode_id") or right.get("episode_id") or f"{merged['pair_key']}@{merged.get('valid_from', '?')}"
    merged["evidence_ids"] = unique(list(left.get("evidence_ids") or []) + list(right.get("evidence_ids") or []))
    if left.get("change_ids") or right.get("change_ids"):
        merged["change_ids"] = unique(list(left.get("change_ids") or []) + list(right.get("change_ids") or []))

    descriptions = []
    for value in (left.get("description"), right.get("description")):
        if isinstance(value, str) and value.strip() and value.strip() not in descriptions:
            descriptions.append(value.strip())
    if descriptions:
        merged["description"] = "；".join(descriptions)

    observations = []
    seen = set()
    for item in list(left.get("observations") or []) + list(right.get("observations") or []):
        if not isinstance(item, dict):
            continue
        marker = json.dumps(item, ensure_ascii=False, sort_keys=True)
        if marker not in seen:
            seen.add(marker)
            observations.append(deepcopy(item))
    observations.sort(key=lambda item: (item.get("chapter") if isinstance(item.get("chapter"), int) else 0, json.dumps(item, ensure_ascii=False, sort_keys=True)))
    merged["observations"] = observations
    return merged


def relation_intervals_overlap(left: dict, right: dict) -> bool:
    left_start, right_start = left.get("valid_from"), right.get("valid_from")
    if not isinstance(left_start, int) or not isinstance(right_start, int):
        return False
    left_end = left.get("valid_to") if isinstance(left.get("valid_to"), int) else float("inf")
    right_end = right.get("valid_to") if isinstance(right.get("valid_to"), int) else float("inf")
    return max(left_start, right_start) <= min(left_end, right_end)


def coalesce_relations(records: list[dict]) -> tuple[list[dict], dict[str, str]]:
    """Merge overlapping restatements of one relation while preserving true episodes."""
    result: list[dict] = []
    buckets: dict[tuple[str, str, str], list[int]] = {}
    canonicalization: dict[str, str] = {}
    # Python's stable sort retains fragment order for equal start chapters, so a
    # later fragment can close or refine an earlier open relationship episode.
    # valid_from 为显式 null 时 r.get(..., 0) 仍返回 None，与 int 比较会抛
    # TypeError。数据本身该被 validate 拦下，但合并不该因此整个崩掉。
    ordered = sorted(records, key=lambda r: (r.get("valid_from") if isinstance(r.get("valid_from"), int) else 0))
    for record in ordered:
        key = relation_key(record)
        match_index = next(
            (index for index in buckets.get(key, []) if relation_intervals_overlap(result[index], record)),
            None,
        )
        if match_index is None:
            buckets.setdefault(key, []).append(len(result))
            result.append(prepare_relation(record))
            continue
        prior = result[match_index]
        prior_id = prior["id"]
        duplicate_id = record["id"]
        merged = merge_relation_records(prior, prepare_relation(record))
        if record.get("status") == "active" and record.get("valid_to") in (None, ""):
            merged.pop("valid_to", None)
        result[match_index] = merged
        if duplicate_id != prior_id:
            canonicalization[duplicate_id] = prior_id
    return result, canonicalization


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", nargs="+", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--manifest", type=Path, help="Prepared source manifest used to lock provenance")
    parser.add_argument("--id-map", action="append", default=[], metavar="OLD=NEW", help="Canonicalize an entity or record ID before merging; repeat as needed")
    args = parser.parse_args()

    id_mapping: dict[str, str] = {}
    for item in args.id_map:
        if "=" not in item or not all(part.strip() for part in item.split("=", 1)):
            print(f"ERROR: invalid --id-map {item!r}; expected OLD=NEW", file=sys.stderr)
            return 2
        old, new = (part.strip() for part in item.split("=", 1))
        id_mapping[old] = new

    fragments = []
    for path in args.input:
        try:
            fragment = json.loads(path.resolve().read_text(encoding="utf-8"))
            fragments.append((path.resolve(), remap_ids(fragment, id_mapping)))
        except (OSError, json.JSONDecodeError) as exc:
            print(f"ERROR reading {path}: {exc}", file=sys.stderr)
            return 2

    merged = {"metadata": {}, **{name: [] for name in ARRAYS}}
    conflicts = []
    indexes = {name: {} for name in ARRAYS}
    metadata_notes: list = []
    # Coverage has to be read per fragment, before the metadata merge flattens
    # every fragment's chapter_range into one list. A fragment may declare the
    # exact chapters it read (analyzed_chapters) or only the span it covered
    # (chapter_range / chapter_start+chapter_end); both describe coverage, and
    # neither is the same thing as the manifest's prepared_chapters.
    analyzed: set[int] = set()

    def absorb_coverage(meta: dict) -> None:
        declared = meta.get("analyzed_chapters")
        if isinstance(declared, list) and declared:
            analyzed.update(c for c in declared if isinstance(c, int))
            return
        span = meta.get("chapter_range")
        if isinstance(span, list) and len(span) == 2 and all(isinstance(c, int) for c in span):
            analyzed.update(range(min(span), max(span) + 1))
            return
        start, end = meta.get("chapter_start"), meta.get("chapter_end")
        if isinstance(start, int) and isinstance(end, int):
            analyzed.update(range(min(start, end), max(start, end) + 1))

    for path, fragment in fragments:
        meta = fragment.get("metadata", {})
        if isinstance(meta, dict):
            absorb_coverage(meta)
        raw_notes = meta.get("notes") if isinstance(meta, dict) else None
        if isinstance(raw_notes, list):
            metadata_notes.extend(raw_notes)
        elif raw_notes not in (None, ""):
            metadata_notes.append(raw_notes)
        merged["metadata"] = merge_record(merged["metadata"], meta)
        for name in ARRAYS:
            for record in fragment.get(name, []):
                if not isinstance(record, dict) or not record.get("id"):
                    conflicts.append({"kind": name, "file": str(path), "issue": "record missing id"})
                    continue
                record_id = record["id"]
                existing = indexes[name].get(record_id)
                if existing is None:
                    indexes[name][record_id] = deepcopy(record)
                    continue
                if name in STRICT_KINDS and existing != record:
                    conflicts.append({"kind": name, "id": record_id, "file": str(path), "issue": "incompatible duplicate"})
                    continue
                indexes[name][record_id] = merge_record(existing, record)

    for name in ARRAYS:
        merged[name] = list(indexes[name].values())
    # Independent fragments spell the same attribute two ways ("性别" and
    # "gender"). Fold the alias spellings onto canonical keys here so the graph
    # itself carries one key per fact and no reader-facing view renders it twice.
    attribute_notes: list[str] = []
    for record in merged["entities"]:
        if "attributes" not in record:
            continue
        canonical, notes = canonicalize_attributes(record["attributes"])
        if canonical != record["attributes"]:
            record["attributes"] = canonical
        for note in notes:
            attribute_notes.append(f"{record.get('id')}：{note}")
    # One fragment names an entity "血皇（刘弈的猎人代号与伪装身份）" with alias "血皇",
    # a later fragment settles on the name "血皇". After the name merge the alias merely
    # repeats the name, and the dashboard renders the same label twice in the alias chips.
    # This is invisible to any per-fragment check, so it is normalized on the merged view.
    alias_notes: list[str] = []
    for record in merged["entities"]:
        aliases = record.get("aliases")
        if not isinstance(aliases, list):
            continue
        kept = unique([
            alias for alias in aliases
            if (alias.get("name") if isinstance(alias, dict) else alias) != record.get("name")
        ])
        if len(kept) != len(aliases):
            record["aliases"] = kept
            alias_notes.append(f"{record.get('id')}：删除与名称重复的别名")
    # A pass has no shared event-type vocabulary unless the spec fixes one, so the
    # same kind of event arrives as "reveal" from one fragment and
    # "information_reveal" from another. Fold the unambiguous synonyms here; a
    # label outside RECOMMENDED_EVENT_TYPES is reported by validate_graph.py
    # rather than rewritten, because it may be a legitimate book-specific kind.
    merged["events"], event_type_notes = canonicalize_event_types(merged["events"])
    merged["intimate_acts"], intimacy_notes = canonicalize_intimate_acts(merged["intimate_acts"])
    merged["level_conversions"], conversion_notes = canonicalize_level_conversions(merged["level_conversions"])
    merged["character_traits"], trait_notes = canonicalize_character_traits(merged.get("character_traits") or [])
    merged["relations"], relation_canonicalization = coalesce_relations(merged["relations"])
    if relation_canonicalization:
        for name in ARRAYS:
            if name != "relations":
                merged[name] = remap_ids(merged[name], relation_canonicalization)
    merged["metadata"]["analyzed_chapters"] = sorted(analyzed)
    if merged["metadata"].get("analyzed_chapters"):
        merged["metadata"]["chapter_start"] = min(merged["metadata"]["analyzed_chapters"])
        merged["metadata"]["chapter_end"] = max(merged["metadata"]["analyzed_chapters"])
    merged["metadata"]["generated_at"] = datetime.now(timezone.utc).isoformat()
    merged["metadata"]["fragment_sources"] = [str(path) for path, _ in fragments]
    # `fragment` is a per-fragment field, and a scalar merge keeps the *last*
    # input's copy — so the merged graph claimed to come from the final fragment
    # alone (`fragment-11-ch091-100` for a twelve-fragment book). The real source
    # list is `fragment_sources`, so the misleading single name is dropped.
    merged["metadata"].pop("fragment", None)
    # A fragment edited *after* this merge leaves graph.json stale while
    # validation still reports valid: true -- validation proves the graph is
    # self-consistent, never that it is current. Recording each input's digest
    # here is what lets validate_graph.py notice; paths alone cannot, because a
    # path is unchanged by an edit.
    merged["metadata"]["input_fingerprint"] = {
        "algorithm": "sha256",
        "fragments": {
            path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path, _ in fragments
        },
    }
    merged["metadata"]["merge_conflicts"] = conflicts
    # Record the currently installed Skill rather than copying/freeze-pinning it
    # into the run. The receipt is diagnostic; compatibility is decided by schema.
    try:
        from record_skill_version import aggregate_fingerprint, skill_files

        skill_root = Path(__file__).resolve().parent.parent
        merged["metadata"]["skill_fingerprint"] = {
            "algorithm": "sha256",
            "skill": aggregate_fingerprint(skill_root, skill_files(skill_root)),
        }
    except Exception as error:  # Fingerprinting never blocks a story-data merge.
        print(f"警告：未能记录 Skill 指纹（{error}）", file=sys.stderr)
    merged["metadata"]["id_canonicalization"] = id_mapping
    merged["metadata"]["relation_canonicalization"] = relation_canonicalization
    merged["metadata"]["attribute_canonicalization"] = attribute_notes
    merged["metadata"]["event_type_canonicalization"] = event_type_notes
    merged["metadata"]["intimacy_act_canonicalization"] = intimacy_notes
    merged["metadata"]["character_trait_canonicalization"] = trait_notes
    merged["metadata"]["level_conversion_canonicalization"] = conversion_notes
    merged["metadata"]["alias_canonicalization"] = alias_notes
    merged["metadata"]["notes"] = unique(metadata_notes)
    if args.manifest:
        try:
            manifest = json.loads(args.manifest.resolve().read_text(encoding="utf-8"))
            # The manifest describes the whole prepared novel, so it may only
            # supply provenance and the chapter title map -- never the analyzed
            # range. Unioning prepared_chapters in here used to inflate coverage
            # to every chapter that was split into a file, which made
            # validate_graph's chapter_outside_coverage check vacuous and let the
            # page advertise chapters nobody had read.
            for field in ("title", "source_file", "source_sha256"):
                if field in manifest:
                    merged["metadata"][field] = manifest[field]
            if not merged["metadata"].get("analyzed_chapters"):
                fallback = manifest.get("prepared_chapters") or manifest.get("analyzed_chapters") or []
                merged["metadata"]["analyzed_chapters"] = sorted(
                    c for c in fallback if isinstance(c, int)
                )
                if merged["metadata"]["analyzed_chapters"]:
                    merged["metadata"]["chapter_start"] = min(merged["metadata"]["analyzed_chapters"])
                    merged["metadata"]["chapter_end"] = max(merged["metadata"]["analyzed_chapters"])
        except (OSError, json.JSONDecodeError) as exc:
            print(f"ERROR reading manifest {args.manifest}: {exc}", file=sys.stderr)
            return 2

    # The metadata merge unions every fragment's chapter_range into one flat
    # list; collapse it to the single analyzed span so the metadata stays
    # readable and cannot be mistaken for a chapter-by-chapter coverage claim.
    if merged["metadata"].get("analyzed_chapters"):
        merged["metadata"]["chapter_range"] = [
            merged["metadata"]["chapter_start"],
            merged["metadata"]["chapter_end"],
        ]

    output = args.output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(merged, ensure_ascii=False, indent=2), encoding="utf-8")
    summary = {
        "output": str(output),
        "counts": {name: len(merged[name]) for name in ARRAYS},
        "relations_coalesced": len(relation_canonicalization),
        "attributes_canonicalized": attribute_notes,
        "aliases_canonicalized": alias_notes,
        "event_types_canonicalized": event_type_notes,
        "intimacy_acts_canonicalized": intimacy_notes,
        "character_traits_canonicalized": trait_notes,
        "level_conversions_canonicalized": conversion_notes,
        "conflicts": conflicts,
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 1 if conflicts else 0


if __name__ == "__main__":
    raise SystemExit(main())
