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
from relation_types import SYMMETRIC_RELATION_TYPES, canonical_relation_type
from io_utils import atomic_write_json
from required_fields import ARRAY_KINDS


# One canonical array registry. New top-level fact families must enter through
# required_fields.py so merge, validation, results facts and exports can audit
# the same set instead of maintaining divergent hand-written tuples.
ARRAYS = tuple(ARRAY_KINDS)
STRICT_KINDS = {"events", "state_changes", "evidence"}


def canonicalize_character_traits(records: list) -> tuple[list, list]:
    """把中文／别名分面折回规范值，并按 (人物, 分面, 章节) 排序。"""
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
    if field in {
        "first_chapter", "valid_from", "planted_chapter", "first_meeting_chapter",
        "ambiguity_started_chapter", "confirmed_chapter", "first_sex_chapter",
        "created_chapter",
    } and isinstance(left, int) and isinstance(right, int):
        return min(left, right)
    if field in {"last_chapter", "valid_to", "payoff_chapter", "resolved_chapter"} and isinstance(left, int) and isinstance(right, int):
        return max(left, right)
    return deepcopy(right)


# Entity prose that changes as the story goes on. Two fragments declaring the
# same entity with different text used to keep only the last one, silently; the
# earlier paragraph now survives as a dated history row that as-of views select.
PROSE_HISTORY_FIELDS = ("summary", "description")

# Romance status order when fragments disagree: the most advanced evidenced stage
# wins instead of whichever fragment happened to be merged last.
ROMANCE_STATUS_RANK = {
    "excluded_nonromantic": -1, "accidental_or_contextual": 0, "coerced_or_forced": 0, "ended": 1,
    "uncertain": 2, "provisional_intimate": 3, "one_sided": 3, "ambiguous": 3, "mutual_interest": 4,
    "betrothed": 5, "spouse": 6, "confirmed_relationship": 6,
}


def fragment_start(meta: dict) -> int | None:
    """The first chapter a fragment covers, or None for a supplementary fragment."""
    declared = meta.get("analyzed_chapters")
    if isinstance(declared, list) and any(isinstance(c, int) for c in declared):
        return min(c for c in declared if isinstance(c, int))
    span = meta.get("chapter_range")
    if isinstance(span, list) and len(span) == 2 and all(isinstance(c, int) for c in span):
        return min(span)
    start = meta.get("chapter_start")
    return start if isinstance(start, int) else None


def _blank(value) -> bool:
    return value is None or value == "" or value == [] or value == {}


def merge_entity_prose(existing: dict, incoming: dict, first_seen: int | None, start: int | None) -> dict:
    """Fold differing summaries/descriptions into `<field>_history` rows.

    Returns a copy of `incoming` whose prose fields no longer overwrite blindly:
    the current value becomes the one with the latest start chapter, and every
    distinct text is kept once with the chapter its fragment began at.
    """
    incoming = deepcopy(incoming)
    for field in PROSE_HISTORY_FIELDS:
        old, new = existing.get(field), incoming.get(field)
        if _blank(new) or _blank(old) or old == new or start is None:
            continue
        history_key = f"{field}_history"
        history = existing.get(history_key)
        if not isinstance(history, list) or not history:
            history = [{"valid_from": first_seen, field: old}] if first_seen is not None else []
        texts = {row.get(field) for row in history if isinstance(row, dict)}
        if new not in texts:
            history.append({"valid_from": start, field: new})
        history.sort(key=lambda row: (row.get("valid_from") is None, row.get("valid_from") or 0))
        existing[history_key] = history
        incoming.pop(history_key, None)
        dated = [row for row in history if isinstance(row.get("valid_from"), int)]
        incoming[field] = dated[-1][field] if dated else new
    return incoming


def scalar_overrides(existing: dict, incoming: dict) -> list[str]:
    """Top-level string fields a later fragment rewrites with different text."""
    return [
        field for field, value in incoming.items()
        if isinstance(value, str) and value and isinstance(existing.get(field), str)
        and existing[field] and existing[field] != value and field not in PROSE_HISTORY_FIELDS and field != "status"
    ]


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
    source, target, relation_type = relation_key(record)
    return f"{source}|{target}|{relation_type}"


def relation_observation(record: dict) -> dict:
    observation = {
        "chapter": record.get("chapter") if isinstance(record.get("chapter"), int) else record.get("valid_from"),
        "evidence_ids": unique(list(record.get("evidence_ids") or [])),
    }
    for field in ("description", "status", "stance", "valid_from", "valid_to", "close_reason"):
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
    observations.sort(key=lambda item: (
        item.get("chapter") if isinstance(item.get("chapter"), int) else 0,
        json.dumps(item, ensure_ascii=False, sort_keys=True),
    ))
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
    """Merge overlapping restatements while preserving a known close.

    A later overlapping record that merely says ``active`` with no ``valid_to``
    is weaker than an earlier evidence-backed close. True resumed relationships
    start after the old episode ends and therefore form a separate episode.
    """
    result: list[dict] = []
    buckets: dict[tuple[str, str, str], list[int]] = {}
    canonicalization: dict[str, str] = {}
    ordered = sorted(records, key=lambda row: row.get("valid_from") if isinstance(row.get("valid_from"), int) else 0)
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
        result[match_index] = merge_relation_records(prior, prepare_relation(record))
        if duplicate_id != prior_id:
            canonicalization[duplicate_id] = prior_id
    return result, canonicalization


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", nargs="+", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--manifest", type=Path, help="Prepared source manifest used to lock provenance")
    parser.add_argument("--id-map", action="append", default=[], metavar="OLD=NEW", help="Canonicalize an entity or record ID before merging; repeat as needed")
    args = parser.parse_args(argv)

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
    overrides: list[dict] = []
    first_seen: dict[str, int | None] = {}
    indexes = {name: {} for name in ARRAYS}
    metadata_notes: list = []
    analyzed: set[int] = set()

    def absorb_coverage(meta: dict) -> None:
        declared = meta.get("analyzed_chapters")
        if isinstance(declared, list) and declared:
            analyzed.update(chapter for chapter in declared if isinstance(chapter, int))
            return
        span = meta.get("chapter_range")
        if isinstance(span, list) and len(span) == 2 and all(isinstance(chapter, int) for chapter in span):
            analyzed.update(range(min(span), max(span) + 1))
            return
        start, end = meta.get("chapter_start"), meta.get("chapter_end")
        if isinstance(start, int) and isinstance(end, int):
            analyzed.update(range(min(start, end), max(start, end) + 1))

    for path, fragment in fragments:
        meta = fragment.get("metadata", {})
        start = fragment_start(meta) if isinstance(meta, dict) else None
        if isinstance(meta, dict):
            absorb_coverage(meta)
        raw_notes = meta.get("notes") if isinstance(meta, dict) else None
        if isinstance(raw_notes, list):
            metadata_notes.extend(raw_notes)
        elif raw_notes not in (None, ""):
            metadata_notes.append(raw_notes)
        merged["metadata"] = merge_record(merged["metadata"], meta)
        for name in ARRAYS:
            records = fragment.get(name, [])
            if records is None:
                continue
            if not isinstance(records, list):
                conflicts.append({"kind": name, "file": str(path), "issue": "array field is not a list"})
                continue
            for record in records:
                if not isinstance(record, dict) or not record.get("id"):
                    conflicts.append({"kind": name, "file": str(path), "issue": "record missing id"})
                    continue
                record_id = record["id"]
                existing = indexes[name].get(record_id)
                if existing is None:
                    indexes[name][record_id] = deepcopy(record)
                    if name == "entities":
                        first_seen[record_id] = start
                    continue
                if name in STRICT_KINDS and existing != record:
                    conflicts.append({"kind": name, "id": record_id, "file": str(path), "issue": "incompatible duplicate"})
                    continue
                incoming = record
                if name == "entities":
                    incoming = merge_entity_prose(existing, record, first_seen.get(record_id), start)
                if name == "romance_routes" and not _blank(existing.get("status")) and not _blank(record.get("status")):
                    if ROMANCE_STATUS_RANK.get(existing["status"], -2) > ROMANCE_STATUS_RANK.get(record["status"], -2):
                        incoming = {**incoming, "status": existing["status"]}
                if name == "relations":
                    # a restated relation keeps every observation (status, stance, wording) of both sides
                    indexes[name][record_id] = merge_relation_records(prepare_relation(existing), prepare_relation(incoming))
                    continue
                for field in scalar_overrides(existing, incoming):
                    overrides.append({"kind": name, "id": record_id, "field": field, "file": path.name})
                indexes[name][record_id] = merge_record(existing, incoming)

    for name in ARRAYS:
        merged[name] = list(indexes[name].values())

    attribute_notes: list[str] = []
    for record in merged["entities"]:
        if "attributes" not in record:
            continue
        canonical, notes = canonicalize_attributes(record["attributes"])
        if canonical != record["attributes"]:
            record["attributes"] = canonical
        for note in notes:
            attribute_notes.append(f"{record.get('id')}：{note}")

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

    merged["events"], event_type_notes = canonicalize_event_types(merged["events"])
    merged["intimate_acts"], intimacy_notes = canonicalize_intimate_acts(merged["intimate_acts"])
    merged["level_conversions"], conversion_notes = canonicalize_level_conversions(merged["level_conversions"])
    merged["character_traits"], trait_notes = canonicalize_character_traits(merged.get("character_traits") or [])
    relation_type_notes: list[str] = []
    for record in merged["relations"]:
        raw = record.get("relation_type")
        canonical = canonical_relation_type(raw)
        if canonical != raw:
            record["relation_type"] = canonical
            relation_type_notes.append(f"{record.get('id')}：关系类型 {raw} → {canonical}")
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
    merged["metadata"].pop("fragment", None)
    merged["metadata"]["input_fingerprint"] = {
        "algorithm": "sha256",
        "fragments": {path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path, _ in fragments},
    }
    merged["metadata"]["merge_conflicts"] = conflicts
    # Not conflicts — a later pass may legitimately reword a field — but never silent.
    merged["metadata"]["merge_overrides"] = {"count": len(overrides), "sample": overrides[:50]}
    try:
        from record_skill_version import aggregate_fingerprint, skill_files

        skill_root = Path(__file__).resolve().parent.parent
        merged["metadata"]["skill_fingerprint"] = {
            "algorithm": "sha256",
            "skill": aggregate_fingerprint(skill_root, skill_files(skill_root)),
        }
    except Exception as error:  # Diagnostic fingerprinting must never destroy an otherwise valid merge.
        print(f"警告：未能记录 Skill 指纹（{error}）", file=sys.stderr)
    merged["metadata"]["id_canonicalization"] = id_mapping
    merged["metadata"]["relation_canonicalization"] = relation_canonicalization
    merged["metadata"]["attribute_canonicalization"] = attribute_notes
    merged["metadata"]["event_type_canonicalization"] = event_type_notes
    merged["metadata"]["relation_type_canonicalization"] = relation_type_notes
    merged["metadata"]["intimacy_act_canonicalization"] = intimacy_notes
    merged["metadata"]["character_trait_canonicalization"] = trait_notes
    merged["metadata"]["level_conversion_canonicalization"] = conversion_notes
    merged["metadata"]["alias_canonicalization"] = alias_notes
    merged["metadata"]["notes"] = unique(metadata_notes)

    if args.manifest:
        try:
            manifest = json.loads(args.manifest.resolve().read_text(encoding="utf-8"))
            for field in ("title", "source_file", "source_sha256"):
                if field in manifest:
                    merged["metadata"][field] = manifest[field]
            if not merged["metadata"].get("analyzed_chapters"):
                fallback = manifest.get("prepared_chapters") or manifest.get("analyzed_chapters") or []
                merged["metadata"]["analyzed_chapters"] = sorted(chapter for chapter in fallback if isinstance(chapter, int))
                if merged["metadata"]["analyzed_chapters"]:
                    merged["metadata"]["chapter_start"] = min(merged["metadata"]["analyzed_chapters"])
                    merged["metadata"]["chapter_end"] = max(merged["metadata"]["analyzed_chapters"])
        except (OSError, json.JSONDecodeError) as exc:
            print(f"ERROR reading manifest {args.manifest}: {exc}", file=sys.stderr)
            return 2

    if merged["metadata"].get("analyzed_chapters"):
        merged["metadata"]["chapter_range"] = [merged["metadata"]["chapter_start"], merged["metadata"]["chapter_end"]]

    output = args.output.resolve()
    atomic_write_json(output, merged, trailing_newline=False)
    summary = {
        "output": str(output),
        "counts": {name: len(merged[name]) for name in ARRAYS},
        "relations_coalesced": len(relation_canonicalization),
        "attributes_canonicalized": attribute_notes,
        "aliases_canonicalized": alias_notes,
        "event_types_canonicalized": event_type_notes,
        "relation_types_canonicalized": relation_type_notes,
        "scalar_overrides": len(overrides),
        "intimacy_acts_canonicalized": intimacy_notes,
        "character_traits_canonicalized": trait_notes,
        "level_conversions_canonicalized": conversion_notes,
        "conflicts": conflicts,
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 1 if conflicts else 0


if __name__ == "__main__":
    raise SystemExit(main())
