#!/usr/bin/env python3
"""Validate temporal novel graph references and evidence invariants."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

from attribute_keys import canonical_key
from character_traits import (
    FACETS as TRAIT_FACETS,
    canonical_facet,
    statement_is_substantive,
)
from event_types import canonical_event_type, unknown_event_types
from intimacy_types import (
    CONSENT_CONTEXTS,
    EJACULATION_SITES,
    INTIMACY_TYPES,
    PARTICIPANT_ROLES,
    canonical_intimacy_type,
    has_participant,
    unknown_intimacy_types,
)
from level_conversions import (
    CONVERSION_RELATIONS,
    canonical_relation,
    endpoint_has_position,
    range_is_sane,
    unknown_relations,
)
# 必填字段表与 check_fragment.py 共用一份，见 required_fields.py 的模块说明：
# 门禁比校验器弱，就等于把失败推迟到合并之后。
from required_fields import CONFIDENCE, REQUIRED, REQUIRED_KEYS


CORE_ARRAYS = ("entities", "events", "relations", "state_changes", "foreshadowing", "evidence", "review_issues")
OPTIONAL_ARRAYS = ("romance_routes", "intimate_acts", "level_conversions",
                   "character_traits", "chapter_summaries", "item_roles", "story_arcs")
ARRAYS = CORE_ARRAYS + OPTIONAL_ARRAYS
LOSS_ACTIONS = {"lost", "transferred", "sealed", "forgotten", "left", "destroyed", "removed", "broken"}
# CONFIDENCE 由 required_fields.py 提供：`check_fragment.py` 的合并前门禁要用同一份，
# 否则门禁只查这个字段「存在」、校验器查「取值」，坏值就被推迟到合并后才炸。
# 2026-09-14《逆天邪神》fragment-25 的 `confidence: "suspected"` 就是这么漏过去的。
ROMANCE_STATUSES = {
    "provisional_intimate", "ambiguous", "one_sided", "mutual_interest",
    "confirmed_relationship", "spouse", "betrothed", "coerced_or_forced",
    "accidental_or_contextual", "excluded_nonromantic", "ended", "uncertain",
}
ROMANCE_INCLUSION_BASES = {
    "romantic_ambiguity", "intimate_contact", "explicit_intimate_proposal",
    "repeated_attachment", "intimate_psychology", "marriage", "betrothal", "spouse_relation",
}
STORY_ARC_STATUSES = {"open", "active", "paused", "resolved", "uncertain"}
STORY_ARC_PHASES = {
    "setup", "development", "escalation", "turning_point", "climax",
    "resolution", "aftermath", "interlude", "recurring", "uncertain",
}
ITEM_CATEGORIES = {
    "weapon", "armor", "accessory", "luxury_collectible", "consumable",
    "resource_material", "book_manual_contract", "vehicle_container_dwelling",
    "token_credential", "ordinary", "unresolved",
}
# CONSENT_CONTEXTS 由 intimacy_types.py 提供：romance_routes 与 intimate_acts 共用一份定义
SYMMETRIC_RELATION_TYPES = {
    "alter_ego_of", "close_friend_of", "companion_of", "dating", "enemy_of", "friend_of",
    "mission_partner_of", "partner_of", "rival_of", "romantic_partner_of",
    "sibling_of", "spouse_of", "sworn_sibling_of", "task_partner_of",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--graph", required=True, type=Path)
    parser.add_argument("--report", type=Path)
    parser.add_argument("--manifest", type=Path, help="source_manifest.json for quote and chapter-line auditing")
    return parser.parse_args()


def decode_source(raw: bytes) -> str:
    for encoding in ("utf-8-sig", "utf-8", "gb18030", "big5"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise UnicodeError("Unable to decode source")


def normalized_text(value: str) -> str:
    return re.sub(r"\s+", "", value.replace("\ufeff", ""))


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    args = parse_args()
    graph_path = args.graph.resolve()
    try:
        graph = json.loads(graph_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    errors: list[dict] = []
    warnings: list[dict] = []
    # A third channel for facts that are worth reporting but are not defects: a
    # book-specific event kind outside the recommended set is a decision for
    # review, not a validation failure, and it must not inflate warning_count.
    observations: list[dict] = []

    def add(level: str, code: str, message: str, record_id: str | None = None) -> None:
        target = errors if level == "error" else warnings
        item = {"code": code, "message": message}
        if record_id:
            item["record_id"] = record_id
        target.append(item)

    def observe(code: str, message: str, record_id: str | None = None) -> None:
        item = {"code": code, "message": message}
        if record_id:
            item["record_id"] = record_id
        observations.append(item)

    def as_list(value) -> list:
        """Treat a missing, null, or non-list field as an empty list instead of crashing."""
        return value if isinstance(value, list) else []

    def level_value_ok(value) -> bool:
        """A level endpoint is a number, or an object carrying value and/or label."""
        if value is None:
            return True
        if isinstance(value, bool):
            return False
        if isinstance(value, (int, float)):
            return True
        if isinstance(value, dict):
            return "value" in value or "label" in value
        return False

    for name in CORE_ARRAYS:
        if not isinstance(graph.get(name), list):
            add("error", "missing_array", f"{name} must be an array")
            graph[name] = []
    for name in OPTIONAL_ARRAYS:
        if name not in graph:
            graph[name] = []
        elif not isinstance(graph.get(name), list):
            add("error", "bad_optional_array", f"{name} must be an array when present")
            graph[name] = []

    metadata = graph.get("metadata")
    if not isinstance(metadata, dict):
        add("error", "bad_metadata", "metadata must be an object")
        metadata = {}
    for field in ("title", "source_file", "source_sha256", "chapter_start", "chapter_end", "analyzed_chapters", "generated_at"):
        if field not in metadata or metadata[field] in (None, "", []):
            add("error", "missing_metadata", f"metadata.{field} is required")
    analyzed = metadata.get("analyzed_chapters", [])
    if not isinstance(analyzed, list) or not all(isinstance(ch, int) for ch in analyzed):
        add("error", "bad_analyzed_chapters", "metadata.analyzed_chapters must be an integer array")
        analyzed = []
    analyzed_set = set(analyzed)
    if analyzed and analyzed != sorted(set(analyzed)):
        add("warning", "chapter_order", "analyzed_chapters should be sorted and unique")
    if analyzed:
        if metadata.get("chapter_start") != min(analyzed) or metadata.get("chapter_end") != max(analyzed):
            add("error", "coverage_mismatch", "chapter_start/chapter_end must match analyzed_chapters bounds")
    if isinstance(metadata.get("source_sha256"), str) and not re.fullmatch(r"[0-9a-fA-F]{64}", metadata["source_sha256"]):
        add("error", "bad_source_hash", "metadata.source_sha256 must be a 64-character SHA-256 hex digest")

    # --- input freshness ---------------------------------------------------
    # The graph is a build product of the fragments, and nothing about the
    # graph's own consistency implies they have not changed since the merge. A
    # fragment edited afterwards silently drops whatever it added -- validation
    # then reports valid: true on a graph that is missing a record. Paths cannot
    # catch this (an edit leaves the path alone), so merge_graph.py records each
    # input's digest and we recompute it here.
    fingerprint = metadata.get("input_fingerprint")
    if not isinstance(fingerprint, dict) or not isinstance(fingerprint.get("fragments"), dict):
        observe(
            "input_fingerprint_missing",
            "图谱没有 metadata.input_fingerprint（由 merge_graph.py 写入），无法判断分片在合并后是否被改动过。"
            "重跑 merge_graph.py 即可补上这条可核查性。",
        )
    else:
        fragment_dir = graph_path.parent / "fragments"
        stale: list[str] = []
        missing: list[str] = []
        for name, digest in sorted(fingerprint["fragments"].items()):
            source = fragment_dir / name
            if not source.is_file():
                missing.append(name)
            elif hashlib.sha256(source.read_bytes()).hexdigest() != digest:
                stale.append(name)
        if stale:
            shown = "、".join(stale[:6]) + ("…" if len(stale) > 6 else "")
            add(
                "error",
                "stale_inputs",
                f"{len(stale)} 个分片在合并之后被改动，graph.json 已过期：{shown}。"
                "校验只能证明图谱自洽，不能证明它是最新的——必须重跑 "
                "merge_graph.py → validate_graph.py → rollup_levels.py → build_dashboard.py → export_ai_context.py。",
            )
        if missing:
            shown = "、".join(missing[:6]) + ("…" if len(missing) > 6 else "")
            add(
                "warning",
                "missing_inputs",
                f"{len(missing)} 个合并时用到的分片已不在 {fragment_dir}：{shown}。"
                "图谱本身仍可读，但输入无法复核（运行目录被移动时也会出现这条）。",
            )

    all_records = [record for name in ARRAYS for record in graph[name] if isinstance(record, dict)]
    ids = [record.get("id") for record in all_records if record.get("id")]
    for record_id, count in Counter(ids).items():
        if count > 1:
            add("error", "duplicate_id", f"ID appears {count} times", record_id)
    known_ids = set(ids)
    entity_ids = {r.get("id") for r in graph["entities"] if isinstance(r, dict)}
    entity_types = {r.get("id"): r.get("type") for r in graph["entities"] if isinstance(r, dict)}
    event_ids = {r.get("id") for r in graph["events"] if isinstance(r, dict)}
    evidence_ids = {r.get("id") for r in graph["evidence"] if isinstance(r, dict)}
    entity_names: dict[str, str] = {}

    def require(record: dict, fields: tuple[str, ...], kind: str) -> None:
        record_id = record.get("id", f"<{kind} without id>")
        for field in fields:
            value = record.get(field)
            if value is None or value == "" or value == []:
                add("error", "missing_field", f"{kind}.{field} is required", record_id)

    def check_evidence_refs(record: dict, kind: str) -> None:
        record_id = record.get("id", f"<{kind} without id>")
        refs = as_list(record.get("evidence_ids"))
        if not refs:
            add("error", "missing_evidence", f"{kind} has no evidence", record_id)
        for ref in refs:
            if ref not in evidence_ids:
                add("error", "bad_evidence_ref", f"Unknown evidence ID: {ref}", record_id)

    for record in graph["evidence"]:
        if not isinstance(record, dict):
            add("error", "bad_record", "evidence record must be an object")
            continue
        require(record, REQUIRED["evidence"], "evidence")
        if isinstance(record.get("quote"), str) and len(record["quote"].strip()) < 4:
            add("warning", "weak_quote", "Evidence quotation is very short", record.get("id"))
        start, end = record.get("source_line_start"), record.get("source_line_end")
        if isinstance(start, int) and isinstance(end, int) and start > end:
            add("error", "bad_line_range", "source_line_start exceeds source_line_end", record.get("id"))
        if analyzed_set and record.get("chapter") not in analyzed_set:
            add("error", "chapter_outside_coverage", f"Evidence chapter {record.get('chapter')} is not analyzed", record.get("id"))

    for record in graph["entities"]:
        if not isinstance(record, dict):
            add("error", "bad_record", "entity record must be an object")
            continue
        require(record, REQUIRED["entity"], "entity")
        check_evidence_refs(record, "entity")
        canonical_name = record.get("name")
        if (
            isinstance(canonical_name, str)
            and re.search(r"[（(][^）)]+[）)]", canonical_name)
            and record.get("stable_composite_name") is not True
        ):
            add(
                "error", "parenthetical_canonical_name",
                "Canonical name contains a parenthetical second name; keep the authoritative name in name and move old/nick/title identities to evidence-backed aliases unless the source treats the composite as stable (stable_composite_name: true)",
                record.get("id"),
            )
        # Two spellings of one attribute must never survive into the graph: the
        # panel would render the same label twice and the AI text would repeat it.
        attributes = record.get("attributes")
        if isinstance(attributes, dict):
            first_spelling: dict[str, str] = {}
            for raw_key in attributes:
                key = canonical_key(raw_key)
                spelling = str(raw_key)
                prior_spelling = first_spelling.setdefault(key, spelling)
                if prior_spelling != spelling:
                    add(
                        "error",
                        "alias_attribute_key",
                        f"attributes mixes {prior_spelling!r} and {spelling!r}; both mean {key!r}",
                        record.get("id"),
                    )
        identity_values = [record.get("name", "")]
        for field in ("aliases", "historical_names", "titles"):
            values = record.get(field, [])
            if not isinstance(values, list) or any(not isinstance(value, str) for value in values):
                add("error", "bad_identity_names", f"entities.{field} must be a string array", record.get("id"))
            else:
                identity_values.extend(values)
        name_history = record.get("name_history", [])
        if not isinstance(name_history, list) or any(not isinstance(value, dict) for value in name_history):
            add("error", "bad_name_history", "entities.name_history must be an object array", record.get("id"))
            name_history = []
        for entry in name_history:
            shown_name = str(entry.get("name") or "")
            if not shown_name.strip():
                add("error", "missing_identity_name", "name_history entries require a non-empty name", record.get("id"))
            refs = entry.get("evidence_ids")
            if not isinstance(refs, list) or not refs:
                add("error", "missing_identity_evidence", "name_history entries require evidence_ids", record.get("id"))
            else:
                for ref in refs:
                    if ref not in evidence_ids:
                        add("error", "bad_evidence_ref", f"Unknown name_history evidence ID: {ref}", record.get("id"))
            start, end = entry.get("valid_from"), entry.get("valid_to")
            if isinstance(start, int) and isinstance(end, int) and start > end:
                add("error", "bad_identity_validity", "name_history valid_from exceeds valid_to", record.get("id"))
            identity_values.append(shown_name)
        for shown_name in identity_values:
            normalized_name = normalized_text(shown_name).casefold()
            if not normalized_name:
                continue
            prior = entity_names.get(normalized_name)
            if prior and prior != record.get("id"):
                add("warning", "alias_collision", f"Name or alias {shown_name!r} also belongs to {prior}", record.get("id"))
            else:
                entity_names[normalized_name] = record.get("id")
        # An alias identical to the name is not a second way to call the entity; the
        # dashboard would list the same label twice. `merge_graph.py` drops these on the
        # merged view, so a hit here means the graph was not built through the pipeline.
        for raw_alias in as_list(record.get("aliases")):
            if raw_alias == str(record.get("name", "")):
                add("warning", "redundant_alias", f"Alias {raw_alias!r} repeats the entity name", record.get("id"))

        categories = record.get("categories", [])
        if not isinstance(categories, list):
            add("error", "bad_categories", "entities.categories must be an array", record.get("id"))
        else:
            primary_count = 0
            for category in categories:
                category_id = category.get("id") if isinstance(category, dict) else category
                if not isinstance(category_id, str) or not category_id:
                    add("error", "bad_category", "Category entries require a stable string id", record.get("id"))
                    continue
                if record.get("type") == "item" and category_id not in ITEM_CATEGORIES:
                    add("error", "bad_item_category", f"Unsupported item category: {category_id}", record.get("id"))
                if isinstance(category, dict):
                    primary_count += category.get("primary") is True
                    confidence = category.get("confidence")
                    if confidence is not None and confidence not in CONFIDENCE:
                        add("error", "bad_confidence", f"Unsupported category confidence: {confidence}", record.get("id"))
                    refs = category.get("evidence_ids")
                    if not isinstance(refs, list) or not refs:
                        add("error", "missing_category_evidence", "Category objects require evidence_ids", record.get("id"))
                    else:
                        for ref in refs:
                            if ref not in evidence_ids:
                                add("error", "bad_evidence_ref", f"Unknown category evidence ID: {ref}", record.get("id"))
            if primary_count > 1:
                add("error", "multiple_primary_categories", "An entity may have at most one display-primary category", record.get("id"))

    for record in graph["events"]:
        if not isinstance(record, dict):
            add("error", "bad_record", "event record must be an object")
            continue
        require(record, REQUIRED["event"], "event")
        check_evidence_refs(record, "event")
        for ref in as_list(record.get("participant_ids")):
            if ref not in entity_ids:
                add("error", "bad_participant_ref", f"Unknown participant ID: {ref}", record.get("id"))
        for ref in as_list(record.get("cause_event_ids")):
            if ref not in event_ids:
                add("error", "bad_cause_ref", f"Unknown cause event ID: {ref}", record.get("id"))
        for ref in as_list(record.get("consequence_event_ids")):
            if ref not in event_ids:
                add("error", "bad_consequence_ref", f"Unknown consequence event ID: {ref}", record.get("id"))
        location = record.get("location_id")
        if location and location not in entity_ids:
            add("error", "bad_location_ref", f"Unknown location ID: {location}", record.get("id"))
        if analyzed_set and record.get("chapter") not in analyzed_set:
            add("error", "chapter_outside_coverage", f"Event chapter {record.get('chapter')} is not analyzed", record.get("id"))

    relation_groups: dict[tuple[str, str, str], list[dict]] = defaultdict(list)

    def relation_semantic_key(record: dict) -> tuple[str, str, str]:
        source, target = str(record.get("source_id", "")), str(record.get("target_id", ""))
        relation_type = str(record.get("relation_type", ""))
        if relation_type in SYMMETRIC_RELATION_TYPES and target < source:
            source, target = target, source
        return source, target, relation_type

    def relation_intervals_overlap(left: dict, right: dict) -> bool:
        left_start, right_start = left.get("valid_from"), right.get("valid_from")
        if not isinstance(left_start, int) or not isinstance(right_start, int):
            return False
        left_end = left.get("valid_to") if isinstance(left.get("valid_to"), int) else float("inf")
        right_end = right.get("valid_to") if isinstance(right.get("valid_to"), int) else float("inf")
        return max(left_start, right_start) <= min(left_end, right_end)

    for record in graph["relations"]:
        if not isinstance(record, dict):
            add("error", "bad_record", "relation record must be an object")
            continue
        require(record, REQUIRED["relation"], "relation")
        check_evidence_refs(record, "relation")
        for field in ("source_id", "target_id"):
            if record.get(field) not in entity_ids:
                add("error", "bad_entity_ref", f"Unknown {field}: {record.get(field)}", record.get("id"))
        strength = record.get("strength")
        if strength is not None and (not isinstance(strength, int) or isinstance(strength, bool) or not 1 <= strength <= 3):
            add("error", "bad_relation_strength", "relation.strength must be an integer from 1 to 3", record.get("id"))
        if isinstance(record.get("valid_from"), int) and isinstance(record.get("valid_to"), int) and record["valid_from"] > record["valid_to"]:
            add("error", "bad_validity", "valid_from exceeds valid_to", record.get("id"))
        if analyzed_set and record.get("valid_from") not in analyzed_set:
            add("warning", "relation_starts_outside_coverage", f"valid_from {record.get('valid_from')} is not analyzed", record.get("id"))
        key = relation_semantic_key(record)
        for prior in relation_groups[key]:
            if relation_intervals_overlap(prior, record):
                add(
                    "error",
                    "duplicate_relation",
                    f"Overlapping unchanged relation duplicates {prior.get('id')}; merge evidence into one record",
                    record.get("id"),
                )
        relation_groups[key].append(record)

    hierarchy_types = {"part_of", "subgroup_of", "located_in"}
    hierarchy_parent: dict[str, set[str]] = defaultdict(set)
    for record in graph["relations"]:
        if isinstance(record, dict) and record.get("relation_type") in hierarchy_types:
            source, target = record.get("source_id"), record.get("target_id")
            if source in entity_ids and target in entity_ids:
                hierarchy_parent[source].add(target)
    for start in sorted(hierarchy_parent):
        stack: list[tuple[str, tuple[str, ...]]] = [(start, (start,))]
        while stack:
            node, path = stack.pop()
            for parent in hierarchy_parent.get(node, set()):
                if parent in path:
                    add("error", "cyclic_hierarchy", f"Hierarchy contains a cycle: {' -> '.join((*path, parent))}", start)
                    stack.clear()
                    break
                stack.append((parent, (*path, parent)))

    for record in graph["state_changes"]:
        if not isinstance(record, dict):
            add("error", "bad_record", "state_change record must be an object")
            continue
        require(record, REQUIRED["state_change"], "state_change")
        if "before" not in record or "after" not in record:
            add("error", "missing_state_endpoint", "state_change requires both before and after keys", record.get("id"))
        check_evidence_refs(record, "state_change")
        if record.get("entity_id") not in entity_ids:
            add("error", "bad_entity_ref", f"Unknown entity_id: {record.get('entity_id')}", record.get("id"))
        if record.get("target_id") and record["target_id"] not in entity_ids:
            add("error", "bad_target_ref", f"Unknown target_id: {record['target_id']}", record.get("id"))
        if record.get("cause_event_id") and record["cause_event_id"] not in event_ids:
            add("error", "bad_cause_ref", f"Unknown cause_event_id: {record['cause_event_id']}", record.get("id"))
        if record.get("before") == record.get("after"):
            add("error", "no_state_delta", "before and after must differ", record.get("id"))
        if record.get("confidence") not in CONFIDENCE:
            add("error", "bad_confidence", f"Unsupported confidence: {record.get('confidence')}", record.get("id"))
        if record.get("action") in LOSS_ACTIONS and not str(record.get("reason", "")).strip() and not record.get("cause_event_id"):
            add("error", "missing_loss_reason", "Loss-like change needs a reason or causal event", record.get("id"))
        if record.get("facet") == "level":
            axis_id = record.get("target_id")
            if not axis_id:
                add("error", "missing_level_axis", "A level change must set target_id to its level_axis entity", record.get("id"))
            elif axis_id not in entity_ids:
                add("error", "bad_level_axis_ref", f"Unknown level axis: {axis_id}", record.get("id"))
            elif entity_types.get(axis_id) != "level_axis":
                add("error", "bad_level_axis_ref", f"target_id must reference a level_axis entity, got {entity_types.get(axis_id)!r}: {axis_id}", record.get("id"))
            for field in ("before", "after"):
                if field in record and not level_value_ok(record.get(field)):
                    add("error", "bad_level_value", f"level {field} must be a number, null, or an object with value/label", record.get("id"))
        if analyzed_set and record.get("chapter") not in analyzed_set:
            add("error", "chapter_outside_coverage", f"State-change chapter {record.get('chapter')} is not analyzed", record.get("id"))

    referenced_axes = {
        record.get("target_id")
        for record in graph["state_changes"]
        if isinstance(record, dict) and record.get("facet") == "level"
    }
    # A `level_conversions` endpoint must name a `level_axis` entity, so an axis
    # that only ever carries cross-system equivalences (天玄榜名次、苍风玄府府级)
    # is legitimately in the graph with no `level_changes` on it. Without this the
    # warning fires on every conversion-only axis and trains the operator to
    # ignore it.
    for record in graph.get("level_conversions", []):
        if not isinstance(record, dict):
            continue
        for endpoint in (record.get("from"), record.get("to")):
            if isinstance(endpoint, dict) and endpoint.get("axis_id"):
                referenced_axes.add(endpoint["axis_id"])
    for record in graph["entities"]:
        if isinstance(record, dict) and record.get("type") == "level_axis" and record.get("id") not in referenced_axes:
            add("warning", "unused_level_axis", "level_axis entity has no level change referencing it", record.get("id"))
    axes_by_system: dict[str, list[str]] = defaultdict(list)
    for record in graph["entities"]:
        if not isinstance(record, dict) or record.get("type") != "level_axis":
            continue
        system_key = record.get("system_key")
        if isinstance(system_key, str) and system_key.strip():
            axes_by_system[system_key.strip().casefold()].append(record.get("id"))
        else:
            observe("level_axis_missing_system_key", "level_axis lacks system_key; future labels cannot be checked for compatible-axis reuse", record.get("id"))
    for system_key, axis_members in axes_by_system.items():
        if len(axis_members) > 1:
            for axis_id in axis_members:
                add("error", "duplicate_level_system", f"Compatible level system {system_key!r} is split across axes: {', '.join(axis_members)}; extend one existing axis", axis_id)

    for record in graph["romance_routes"]:
        if not isinstance(record, dict):
            add("error", "bad_record", "romance_route record must be an object")
            continue
        require(record, REQUIRED["romance_route"], "romance_route")
        record_id = record.get("id")
        for field in REQUIRED_KEYS["romance_route"]:
            if field not in record:
                add("error", "missing_field", f"romance_route.{field} key is required", record_id)
        protagonist_id, character_id = record.get("protagonist_id"), record.get("character_id")
        for field, ref in (("protagonist_id", protagonist_id), ("character_id", character_id)):
            if ref not in entity_ids:
                add("error", "bad_entity_ref", f"Unknown {field}: {ref}", record_id)
            elif entity_types.get(ref) != "character":
                # 感情线的另一端可以是一个「在原文里被当成人写」的非人存在：
                # 本书的犬女小米（creature_xiaomi，会说话、自称「小米」、叫刘弈
                # 「主人」、踮脚吻他）就是这样，她的路线用人物类型去装是错的。
                # 但这条放宽必须由记录**显式声明**，否则真正的拼写错误会被静默放过：
                # 只有当 character_id 指向的非人物类型恰好等于记录自己写的
                # character_type 时才降级为 warning，其余仍是 error。
                # 用户口径是「感情线一律保留，不做删除式清洗」，所以这里放宽而不是删记录。
                declared_type = record.get("character_type")
                if (
                    field == "character_id"
                    and isinstance(declared_type, str)
                    and declared_type == entity_types.get(ref)
                ):
                    observe(
                        "non_character_romance_partner",
                        f"character_id 指向 {entity_types.get(ref)} 实体 {ref}"
                        f"（已由 character_type 显式声明；感情线的另一端不是人物）",
                        record_id,
                    )
                else:
                    add("error", "bad_character_ref", f"{field} must reference a character: {ref}", record_id)
        if protagonist_id == character_id:
            add("error", "self_romance_route", "A romance route must reference two different characters", record_id)
        if record.get("status") not in ROMANCE_STATUSES:
            add("error", "bad_romance_status", f"Unsupported status: {record.get('status')}", record_id)
        if record.get("inclusion_basis") not in ROMANCE_INCLUSION_BASES:
            add("error", "bad_romance_inclusion_basis", f"Unsupported inclusion_basis: {record.get('inclusion_basis')}", record_id)
        if record.get("consent_context") not in CONSENT_CONTEXTS:
            add("error", "bad_consent_context", f"Unsupported consent_context: {record.get('consent_context')}", record_id)
        if record.get("confidence") not in CONFIDENCE:
            add("error", "bad_confidence", f"Unsupported confidence: {record.get('confidence')}", record_id)

        def check_milestone(chapter_field: str, evidence_field: str, required: bool = False) -> None:
            milestone_chapter = record.get(chapter_field)
            refs = record.get(evidence_field, [])
            if not isinstance(refs, list):
                add("error", "bad_evidence_list", f"romance_route.{evidence_field} must be an array", record_id)
                return
            if required and not isinstance(milestone_chapter, int):
                add("error", "missing_milestone", f"romance_route.{chapter_field} must be an integer", record_id)
            if milestone_chapter is not None and not isinstance(milestone_chapter, int):
                add("error", "bad_milestone_chapter", f"romance_route.{chapter_field} must be an integer or null", record_id)
            if milestone_chapter is None and refs:
                add("error", "evidence_without_milestone", f"{evidence_field} must be empty when {chapter_field} is null", record_id)
            if isinstance(milestone_chapter, int) and not refs:
                add("error", "missing_evidence", f"{chapter_field} needs supporting evidence", record_id)
            evidence_chapters: list[int] = []
            for ref in refs:
                if ref not in evidence_ids:
                    add("error", "bad_evidence_ref", f"Unknown {evidence_field} ID: {ref}", record_id)
                elif isinstance(milestone_chapter, int):
                    evidence_chapter = next((item.get("chapter") for item in graph["evidence"] if isinstance(item, dict) and item.get("id") == ref), None)
                    if isinstance(evidence_chapter, int):
                        evidence_chapters.append(evidence_chapter)
            if isinstance(milestone_chapter, int) and refs and milestone_chapter not in evidence_chapters:
                add("error", "milestone_evidence_chapter_mismatch", f"At least one {evidence_field} record must come from chapter {milestone_chapter}", record_id)
            if analyzed_set and isinstance(milestone_chapter, int) and milestone_chapter not in analyzed_set:
                add("error", "chapter_outside_coverage", f"{chapter_field} {milestone_chapter} is not analyzed", record_id)

        check_milestone("first_meeting_chapter", "first_meeting_evidence_ids", required=True)
        check_milestone("ambiguity_started_chapter", "ambiguity_evidence_ids", required=True)
        check_milestone("confirmed_chapter", "confirmed_evidence_ids")
        check_milestone("first_sex_chapter", "first_sex_evidence_ids")

        milestones = [
            ("first_meeting_chapter", record.get("first_meeting_chapter")),
            ("ambiguity_started_chapter", record.get("ambiguity_started_chapter")),
            ("confirmed_chapter", record.get("confirmed_chapter")),
            ("first_sex_chapter", record.get("first_sex_chapter")),
        ]
        prior_name, prior_chapter = None, None
        for field, milestone_chapter in milestones:
            if not isinstance(milestone_chapter, int):
                continue
            if prior_chapter is not None and milestone_chapter < prior_chapter:
                add("error", "bad_romance_chronology", f"{field} precedes {prior_name}", record_id)
            prior_name, prior_chapter = field, milestone_chapter

        if record.get("status") == "confirmed_relationship" and record.get("confirmed_chapter") is None:
            add("error", "missing_confirmation", "confirmed_relationship requires confirmed_chapter", record_id)

    # Several routes for one (protagonist, character) pair is usually not a story
    # fact but the residue of parallel passes each minting their own route ID: the
    # 流氓老师 run had four routes for 何桃 (`rom_f01_hetao` … `rom_f05_hetao`).
    # It is an observation rather than an error because a relationship that ended
    # and was later rebuilt is legitimately two routes — but validation is the one
    # gate everybody runs, and nothing else would say so after the merge.
    routes_by_pair: dict[tuple, list[str]] = {}
    for record in graph["romance_routes"]:
        if not isinstance(record, dict):
            continue
        key = (record.get("protagonist_id"), record.get("character_id"))
        routes_by_pair.setdefault(key, []).append(record.get("id"))
    for (protagonist_id, character_id), route_ids in routes_by_pair.items():
        if len(route_ids) > 1:
            observe(
                "duplicate_romance_pair",
                f"{len(route_ids)} routes for one pair ({protagonist_id}, {character_id}): "
                f"{', '.join(str(i) for i in route_ids)} — consolidate with "
                f"--id-map unless the relationship genuinely ended and was rebuilt",
            )

    # 亲密行为：每条都要说清发生了什么、涉及谁、是否自愿。只写「发生了亲密关系」
    # 的记录，正是这个数组要消灭的东西。
    for record in graph["intimate_acts"]:
        if not isinstance(record, dict):
            add("error", "bad_record", "intimate_acts entries must be objects")
            continue
        record_id = record.get("id", "<intimate_act without id>")
        require(record, REQUIRED["intimate_act"], "intimate_act")
        act_type = record.get("act_type")
        if isinstance(act_type, str) and act_type.strip():
            if canonical_intimacy_type(act_type) not in INTIMACY_TYPES:
                add("error", "bad_intimacy_act_type", f"Unsupported act_type: {act_type}", record_id)
        if not has_participant(record):
            add("error", "missing_intimacy_participant",
                "at least one of initiator_ids / recipient_ids / observer_ids is required", record_id)
        consent = record.get("consent")
        if consent is not None and consent not in CONSENT_CONTEXTS:
            add("error", "bad_consent_context", f"Unsupported consent: {consent}", record_id)
        site = record.get("ejaculation_site")
        if site is not None and site not in EJACULATION_SITES:
            add("error", "bad_ejaculation_site", f"Unsupported ejaculation_site: {site}", record_id)
        for role in PARTICIPANT_ROLES:
            for ref in as_list(record.get(role)):
                if ref not in entity_ids:
                    add("error", "bad_entity_ref", f"Unknown {role} ID: {ref}", record_id)
        check_evidence_refs(record, "intimate_act")
        if analyzed_set and isinstance(record.get("chapter"), int) and record.get("chapter") not in analyzed_set:
            add("error", "chapter_outside_coverage",
                f"Intimate act chapter {record.get('chapter')} is not analyzed", record_id)

    # ---- 主角侧广义亲密候选覆盖 ----
    # 这是召回门禁，不是恋爱确认器：候选可以用 excluded_nonromantic、
    # accidental_or_contextual 或 coerced_or_forced 明确排除／区分语境。
    raw_protagonists = metadata.get("protagonist_ids")
    if not isinstance(raw_protagonists, list):
        profile = metadata.get("profile") if isinstance(metadata.get("profile"), dict) else {}
        raw_protagonists = profile.get("protagonist_ids") if isinstance(profile.get("protagonist_ids"), list) else []
    protagonist_ids = {item for item in raw_protagonists if item in entity_ids}
    protagonist_ids.update(
        route.get("protagonist_id") for route in graph.get("romance_routes") or []
        if isinstance(route, dict) and route.get("protagonist_id") in entity_ids
    )
    route_pairs = {
        frozenset((route.get("protagonist_id"), route.get("character_id")))
        for route in graph.get("romance_routes") or []
        if isinstance(route, dict) and route.get("protagonist_id") and route.get("character_id")
    }
    missing_route_candidates: set[tuple[str, str, str]] = set()

    def require_route_candidate(source_id: str, participants: list[str]) -> None:
        people = {item for item in participants if item in entity_ids}
        for protagonist_id in people.intersection(protagonist_ids):
            for other_id in people.difference({protagonist_id}):
                if frozenset((protagonist_id, other_id)) not in route_pairs:
                    missing_route_candidates.add((source_id, protagonist_id, other_id))

    for act in graph.get("intimate_acts") or []:
        if isinstance(act, dict):
            require_route_candidate(
                str(act.get("id") or "<intimate_act>"),
                as_list(act.get("initiator_ids")) + as_list(act.get("recipient_ids")),
            )
    for event in graph.get("events") or []:
        if isinstance(event, dict) and canonical_event_type(event.get("type")) == "intimacy":
            require_route_candidate(str(event.get("id") or "<intimacy event>"), as_list(event.get("participant_ids")))
    candidate_relation_types = {
        "spouse_of", "betrothed_to", "romantic_partner_of", "love_interest_of",
        "dating", "one_sided_crush_on", "pursues",
    }
    for relation in graph.get("relations") or []:
        if isinstance(relation, dict) and relation.get("relation_type") in candidate_relation_types:
            require_route_candidate(
                str(relation.get("id") or "<romance relation>"),
                [relation.get("source_id"), relation.get("target_id")],
            )
    candidate_tags = {"romance_candidate", "repeated_attachment", "intimate_psychology", "explicit_intimate_proposal"}
    for change in graph.get("state_changes") or []:
        if not isinstance(change, dict) or not candidate_tags.intersection(as_list(change.get("tags"))):
            continue
        require_route_candidate(
            str(change.get("id") or "<romance state>"),
            [change.get("entity_id"), change.get("target_id")],
        )
    for source_id, protagonist_id, other_id in sorted(missing_route_candidates):
        add(
            "error", "missing_romance_route_candidate",
            f"{source_id} links protagonist {protagonist_id} with {other_id}; add a romance_route candidate or an evidence-backed excluded_nonromantic route",
            source_id,
        )
    if not protagonist_ids and any(canonical_event_type(e.get("type")) == "intimacy" for e in graph.get("events") or [] if isinstance(e, dict)):
        observe("protagonist_ids_missing", "存在亲密事件但 metadata/profile 未声明 protagonist_ids，无法执行主角侧路线候选覆盖门禁。")

    # 等级换算：原文把两个等级体系对上号的地方，例如「修罗王……十颗星的实力」。
    # 这类记录的全部价值在于「原文这么说」，所以三类错必须拦下：引用了不存在的轴、
    # 端点没钉住任何值（只剩 axis_id 的端点根本换算不出东西）、以及没有证据。
    axis_ids = {e.get("id") for e in graph["entities"] if isinstance(e, dict) and e.get("type") == "level_axis"}
    for record in graph["level_conversions"]:
        if not isinstance(record, dict):
            add("error", "bad_record", "level_conversions entries must be objects")
            continue
        record_id = record.get("id", "<level_conversion without id>")
        require(record, REQUIRED["level_conversion"], "level_conversion")
        relation = canonical_relation(record.get("relation"))
        if relation and relation not in CONVERSION_RELATIONS:
            add("error", "bad_conversion_relation",
                f"Unsupported relation: {record.get('relation')}", record_id)
        for side in ("from", "to"):
            endpoint = record.get(side)
            if not isinstance(endpoint, dict):
                add("error", "bad_conversion_endpoint", f"{side} must be an object", record_id)
                continue
            endpoint_axis = endpoint.get("axis_id")
            if endpoint_axis not in axis_ids:
                add("error", "bad_conversion_axis",
                    f"Unknown {side}.axis_id: {endpoint_axis} (must be a level_axis entity)", record_id)
            if not endpoint_has_position(endpoint):
                add("error", "empty_conversion_endpoint",
                    f"{side} pins nothing: it needs value, range, or label", record_id)
            value = endpoint.get("value")
            if value is not None and (isinstance(value, bool) or not isinstance(value, (int, float))):
                add("error", "bad_conversion_value", f"{side}.value must be a number or null", record_id)
            band = endpoint.get("range")
            if band is not None and not range_is_sane(band):
                add("error", "bad_conversion_range",
                    f"{side}.range must be two increasing numbers", record_id)
        check_evidence_refs(record, "level_conversion")
        if analyzed_set and isinstance(record.get("chapter"), int) and record.get("chapter") not in analyzed_set:
            add("error", "chapter_outside_coverage",
                f"Level conversion chapter {record.get('chapter')} is not analyzed", record_id)

    # 同轴换算（两端指向同一体系）是合法的——它记录的是单位或比例规则，
    # 例如「每三颗星璇开一层心法」在两端同一轴时表达的是步进。只作观察，提醒人工确认。
    same_axis = [
        r.get("id") for r in graph["level_conversions"]
        if isinstance(r, dict)
        and isinstance(r.get("from"), dict) and isinstance(r.get("to"), dict)
        and r["from"].get("axis_id") == r["to"].get("axis_id")
    ]
    if same_axis:
        observe(
            "conversion_within_one_axis",
            f"{len(same_axis)} 条换算的两端指向同一等级轴（{'、'.join(str(x) for x in same_axis[:6])}"
            + ("…" if len(same_axis) > 6 else "")
            + "）；若原文表达的是步进或比例规则则属正常，否则应检查是否把两个体系误写成了一端。",
        )

    stray_relations = unknown_relations(as_list(graph.get("level_conversions")))
    if stray_relations:
        listed = "、".join(f"{k}×{v}" for k, v in sorted(stray_relations.items(), key=lambda kv: (-kv[1], kv[0])))
        observe(
            "conversion_relation_outside_set",
            f"{len(stray_relations)} 个换算关系不在规范集内（{listed}）；"
            f"请归并到 scripts/level_conversions.py 的 CONVERSION_RELATIONS。",
        )

    # 一个角色对同一 act_type 反复出现的记录，通常是并行分片各自记了一条，
    # 而不是同一件事发生了两次。只作观察。
    stray_acts = unknown_intimacy_types(as_list(graph.get("intimate_acts")))
    if stray_acts:
        listed = "、".join(
            f"{name}×{count}" for name, count in sorted(stray_acts.items(), key=lambda kv: (-kv[1], kv[0]))
        )
        observe(
            "intimacy_act_type_outside_set",
            f"{len(stray_acts)} 个亲密行为类型不在规范集内（{listed}）；"
            f"建议归并到 scripts/intimacy_types.py，或确认其为本书专有的行为后保留。",
        )

    valid_fs_status = {"suspected", "open", "progressed", "partially_resolved", "resolved", "false_lead"}
    for record in graph["foreshadowing"]:
        if not isinstance(record, dict):
            add("error", "bad_record", "foreshadowing record must be an object")
            continue
        require(record, REQUIRED["foreshadowing"], "foreshadowing")
        check_evidence_refs(record, "foreshadowing")
        if record.get("status") not in valid_fs_status:
            add("error", "bad_foreshadowing_status", f"Unsupported status: {record.get('status')}", record.get("id"))
        # `confidence` 此前只在 state_changes 与 romance_routes 两处校验，伏笔这一路漏掉了。
        # 后果：2026-09-14 在斗罗实测 fragment-46 的 35 条（high/medium）与 fragment-37 的
        # 2 条（suspected）非法值完全静默，校验只报出另外 48 条，真实总数是 85 条。
        # 合法集合与另外两处一致，都是 CONFIDENCE。
        if record.get("confidence") not in CONFIDENCE:
            add("error", "bad_confidence", f"Unsupported confidence: {record.get('confidence')}", record.get("id"))
        for ref in as_list(record.get("related_entity_ids")):
            if ref not in entity_ids:
                add("error", "bad_entity_ref", f"Unknown related entity: {ref}", record.get("id"))
        if record.get("payoff_event_id") and record["payoff_event_id"] not in event_ids:
            add("error", "bad_payoff_ref", f"Unknown payoff event: {record['payoff_event_id']}", record.get("id"))
        progression = record.get("progression", [])
        if progression and not isinstance(progression, list):
            add("error", "bad_progression", "foreshadowing.progression must be an array of step objects", record.get("id"))
            progression = []
        for step in progression:
            if not isinstance(step, dict):
                add(
                    "error",
                    "bad_progression",
                    "foreshadowing.progression entries must be objects with chapter/kind/description/evidence_ids",
                    record.get("id"),
                )
                continue
            if analyzed_set and step.get("chapter") not in analyzed_set:
                add("error", "chapter_outside_coverage", f"Foreshadowing progression chapter {step.get('chapter')} is not analyzed", record.get("id"))
            for ref in as_list(step.get("evidence_ids")):
                if ref not in evidence_ids:
                    add("error", "bad_evidence_ref", f"Unknown progression evidence: {ref}", record.get("id"))
        if analyzed_set and record.get("planted_chapter") not in analyzed_set:
            add("error", "chapter_outside_coverage", f"Foreshadowing plant chapter {record.get('planted_chapter')} is not analyzed", record.get("id"))

    for record in graph["review_issues"]:
        if not isinstance(record, dict):
            add("error", "bad_record", "review_issue record must be an object")
            continue
        require(record, REQUIRED["review_issue"], "review_issue")
        if "related_ids" not in record or not isinstance(record.get("related_ids"), list):
            add("error", "missing_field", "review_issue.related_ids must be an array (empty is allowed for global issues)", record.get("id"))
        for ref in record.get("related_ids", []):
            if ref not in known_ids:
                add("warning", "bad_review_ref", f"Unknown related ID: {ref}", record.get("id"))
        for ref in record.get("evidence_ids", []):
            if ref not in evidence_ids:
                add("error", "bad_evidence_ref", f"Unknown review evidence: {ref}", record.get("id"))

    source_audit = {"performed": False}
    if args.manifest:
        try:
            manifest_path = args.manifest.resolve()
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            source_path = Path(manifest["source_file"]).resolve()
            claimed_source = Path(str(metadata.get("source_file", ""))).resolve()
            if os.path.normcase(str(claimed_source)) != os.path.normcase(str(source_path)):
                add("error", "source_file_mismatch", "Graph source_file does not match the audited manifest source_file")
            raw_source = source_path.read_bytes()
            source_text = decode_source(raw_source)
            source_lines = source_text.splitlines(keepends=True)
            actual_hash = hashlib.sha256(raw_source).hexdigest()
            expected_hash = metadata.get("source_sha256") or manifest.get("source_sha256")
            if expected_hash and actual_hash.lower() != str(expected_hash).lower():
                add("error", "source_hash_mismatch", "Current source hash does not match graph metadata")
            index_path = Path(manifest["chapter_index"])
            chapter_rows = [json.loads(line) for line in index_path.read_text(encoding="utf-8").splitlines() if line.strip()]
            chapter_map = {row["chapter"]: row for row in chapter_rows}
            audited = 0
            for record in graph["evidence"]:
                if not isinstance(record, dict):
                    continue
                start, end, chapter = record.get("source_line_start"), record.get("source_line_end"), record.get("chapter")
                if not isinstance(start, int) or not isinstance(end, int) or start < 1 or end > len(source_lines) or start > end:
                    add("error", "source_line_out_of_range", "Evidence line range is outside the source", record.get("id"))
                    continue
                row = chapter_map.get(chapter)
                if not row:
                    add("error", "missing_chapter_mapping", f"No prepared mapping for chapter {chapter}", record.get("id"))
                    continue
                if start < row["source_line_start"] or end > row["source_line_end"]:
                    add("error", "chapter_line_mismatch", "Evidence lines fall outside the claimed chapter", record.get("id"))
                segment = "".join(source_lines[start - 1:end])
                if normalized_text(str(record.get("quote", ""))) not in normalized_text(segment):
                    add("error", "quote_not_found", "Exact evidence quote was not found in the claimed source lines", record.get("id"))
                else:
                    audited += 1
            source_audit = {"performed": True, "source_file": str(source_path), "source_sha256": actual_hash, "evidence_audited": audited}
        except (OSError, KeyError, json.JSONDecodeError, UnicodeError) as exc:
            add("error", "source_audit_failed", str(exc))

    # Event `type` is free-form in the schema, so a run drifts into nearly one label
    # per event. Report the labels outside the recommended set in a single line: the
    # type facet cannot group anything if every group holds one event, but a
    # book-specific kind is a legitimate choice, so this is an observation.
    stray_types = unknown_event_types(as_list(graph.get("events")))
    if stray_types:
        listed = "、".join(
            f"{name}×{count}" for name, count in sorted(stray_types.items(), key=lambda kv: (-kv[1], kv[0]))
        )
        observe(
            "event_type_outside_recommended_set",
            f"{len(stray_types)} 个事件类型不在推荐集内（{listed}），涉及 {sum(stray_types.values())} 个事件；"
            f"建议归并到 scripts/event_types.py 的推荐集，或确认其为本书专有类型后保留。",
        )

    # Fidelity check: the global rule requires every act the text depicts to be
    # recorded plainly, and forbids disclaimers, elision, and moral framing in the
    # analyst prose. Nothing else in this validator can see that, because an elided
    # record is structurally valid - it simply says less than the chapter does.
    #
    # Only analyst-written fields are scanned. `quote` is deliberately excluded: it
    # is verbatim source text, and a published novel may legitimately contain
    # "不可描述" in the author's own voice. A hit is an observation, not an error:
    # a review_issues entry may quote the phrase while discussing it.
    elision_phrases = (
        "此处省略", "略去不表", "不便描述", "不可描述", "不予记录", "内容敏感",
        "兹不赘述", "为避免不适", "为保护读者", "不予展开", "不做描述", "点到为止",
        "disclaimer", "sensitive content", "omitted for", "redacted", "self-censor",
    )
    prose_fields = {
        "events": ("description", "cause", "consequence"),
        "state_changes": ("reason", "note"),
        "intimate_acts": ("description", "notes"),
        "level_conversions": ("description", "notes"),
        "relations": ("description", "notes"),
        "foreshadowing": ("observation", "interpretation", "notes"),
        "review_issues": ("summary", "detail"),
    }
    elided = []
    for array_name, fields in prose_fields.items():
        for record in as_list(graph.get(array_name)):
            record_id = record.get("id")
            for field in fields:
                value = record.get(field)
                if not isinstance(value, str) or not value.strip():
                    continue
                for phrase in elision_phrases:
                    if phrase in value:
                        elided.append((array_name, record_id, field, phrase))
                        break
    if elided:
        listed = "；".join(f"{arr}.{rid}.{field}（{phrase}）" for arr, rid, field, phrase in elided[:10])
        observe(
            "analyst_elision_or_disclaimer",
            f"{len(elided)} 处分析性文字含省略、弱化或免责措辞（{listed}"
            + ("…" if len(elided) > 10 else "")
            + "）；全局规则要求忠实记录，不得因题材敏感而省略、弱化或附加免责说明，"
            "请核对原文章节把内容补全。",
        )

    entity_ids_all = {e.get("id") for e in graph.get("entities") or []}
    entity_types_all = {e.get("id"): e.get("type") for e in graph.get("entities") or []}

    # ---- 物品角色 ----
    # This array is an explicit temporal authority, not renderer-only metadata.
    # Validate it with the same strength as the other graph record arrays.
    item_role_values = {"owner", "holder", "user", "custodian"}
    item_role_actions = {"gained", "lost", "transferred", "confirmed"}
    for record in graph.get("item_roles") or []:
        if not isinstance(record, dict):
            add("error", "bad_record", "item_roles entries must be objects")
            continue
        record_id = record.get("id", "<item_role without id>")
        require(record, REQUIRED["item_role"], "item_role")
        check_evidence_refs(record, "item_role")
        item_id, entity_id = record.get("item_id"), record.get("entity_id")
        if item_id not in entity_ids_all:
            add("error", "bad_item_ref", f"Unknown item_roles.item_id: {item_id}", record_id)
        elif entity_types_all.get(item_id) != "item":
            add("error", "item_role_target_not_item",
                f"item_roles.item_id must reference an item, got {entity_types_all.get(item_id)}",
                record_id)
        if entity_id not in entity_ids_all:
            add("error", "bad_entity_ref", f"Unknown item_roles.entity_id: {entity_id}", record_id)
        if record.get("role") not in item_role_values:
            add("error", "bad_item_role", f"Unsupported item role: {record.get('role')}", record_id)
        if record.get("action") not in item_role_actions:
            add("error", "bad_item_role_action",
                f"Unsupported item role action: {record.get('action')}", record_id)
        if record.get("confidence") not in CONFIDENCE:
            add("error", "bad_confidence", f"Unsupported confidence: {record.get('confidence')}", record_id)
        start, end = record.get("valid_from"), record.get("valid_to")
        if isinstance(start, int) and isinstance(end, int) and start > end:
            add("error", "bad_validity", "item_role.valid_from exceeds valid_to", record_id)

    # ---- 人物特征 ----
    # 校验的三件事都对应一类真实错误：分面写成了听不懂的词、断言指向了非人物实体、
    # 断言本身是标签而非描述（「漂亮」对读者没有增量，图谱里已有 summary 承担它）。
    trait_facet_misses: list[tuple[str, str]] = []
    seen_trait_anchor: dict[tuple[str, str, int], str] = {}
    for record in graph.get("character_traits") or []:
        if not isinstance(record, dict):
            add("error", "bad_record", "character_traits entries must be objects")
            continue
        record_id = record.get("id", "<character_trait without id>")
        require(record, REQUIRED["character_trait"], "character_trait")
        check_evidence_refs(record, "character_trait")

        facet = canonical_facet(record.get("facet"))
        if facet not in TRAIT_FACETS:
            trait_facet_misses.append((str(record_id), str(record.get("facet"))))

        entity_id = record.get("entity_id")
        if entity_id not in entity_ids_all:
            add("error", "bad_entity_ref",
                f"Unknown character_traits.entity_id: {entity_id}", record_id)
        elif entity_types_all.get(entity_id) != "character":
            add("warning", "trait_on_non_character",
                f"character_traits 指向的不是人物实体（{entity_types_all.get(entity_id)}）",
                record_id)

        if not statement_is_substantive(record):
            add("error", "thin_trait_statement",
                "character_traits.statement 必须是一句可读的描述：少于 5 字、"
                "或没有任何标点的 6 字以内标签都不合格", record_id)

        chapter = record.get("chapter")
        if isinstance(chapter, int) and facet:
            key = (str(entity_id), facet, chapter)
            if key in seen_trait_anchor:
                add("warning", "duplicate_trait_anchor",
                    f"同一人物／分面在第 {chapter} 章有两条断言（另一条：{seen_trait_anchor[key]}）；"
                    "同一时点只应保留一条，变化另起一个 chapter", record_id)
            else:
                seen_trait_anchor[key] = str(record_id)
    if trait_facet_misses:
        listed = "、".join(f"{rid}={value}" for rid, value in trait_facet_misses[:8])
        add("error", "unknown_trait_facet",
            f"{len(trait_facet_misses)} 条 character_traits.facet 不在规范集内：{listed}"
            "（规范值见 scripts/character_traits.py）")

    # ---- 章节梗概 ----
    summary_by_chapter: dict[int, str] = {}
    event_ids_all = {e.get("id") for e in graph.get("events") or []}
    for record in graph.get("chapter_summaries") or []:
        if not isinstance(record, dict):
            add("error", "bad_record", "chapter_summaries entries must be objects")
            continue
        record_id = record.get("id", "<chapter_summary without id>")
        require(record, REQUIRED["chapter_summary"], "chapter_summary")
        check_evidence_refs(record, "chapter_summary")

        chapter = record.get("chapter")
        if isinstance(chapter, int):
            if chapter in summary_by_chapter:
                add("error", "duplicate_chapter_summary",
                    f"第 {chapter} 章有两条梗概（另一条：{summary_by_chapter[chapter]}）",
                    record_id)
            else:
                summary_by_chapter[chapter] = str(record_id)

        summary = record.get("summary")
        if isinstance(summary, str) and len(summary.strip()) < 20:
            add("warning", "thin_chapter_summary",
                f"chapter_summaries.summary 只有 {len(summary.strip())} 字；"
                "三到六句才够读者扫读", record_id)

        for eid in as_list(record.get("key_event_ids")):
            if eid not in event_ids_all:
                add("error", "bad_evidence_ref",
                    f"Unknown chapter_summaries.key_event_ids: {eid}", record_id)

    # 章节梗概的覆盖缺口：哪些已分析章没有梗概。梗概是读者往前走的索引，缺一章
    # 就是一个断点，而这件事只有把两边的数字对起来才看得见。
    if summary_by_chapter:
        analysed = graph.get("metadata", {}).get("analyzed_chapters") or []
        gaps = sorted(c for c in analysed if isinstance(c, int) and c not in summary_by_chapter)
        if gaps:
            shown = "、".join(str(c) for c in gaps[:12])
            observe("chapters_without_summary",
                    f"{len(gaps)} 章已分析但没有章节梗概（{shown}"
                    + ("…" if len(gaps) > 12 else "") + "）")

    # ---- 交叉剧情弧 ----
    # 区间可以重叠或嵌套；这里只验证每一条弧自身和显式引用，不把重叠误判为冲突。
    arc_ids = {
        record.get("id") for record in graph.get("story_arcs") or []
        if isinstance(record, dict) and isinstance(record.get("id"), str)
    }
    arc_parent: dict[str, str] = {}
    for record in graph.get("story_arcs") or []:
        if not isinstance(record, dict):
            add("error", "bad_record", "story_arcs entries must be objects")
            continue
        record_id = record.get("id", "<story_arc without id>")
        require(record, REQUIRED["story_arc"], "story_arc")
        check_evidence_refs(record, "story_arc")
        for field in REQUIRED_KEYS.get("story_arc", ()):
            if field not in record:
                add("error", "missing_key", f"story_arc.{field} key is required (null/list allowed)", record_id)

        start, end = record.get("chapter_start"), record.get("chapter_end")
        if not isinstance(start, int) or isinstance(start, bool) or start < 0:
            add("error", "bad_chapter", "story_arc.chapter_start must be a non-negative integer", record_id)
        if end is not None and (not isinstance(end, int) or isinstance(end, bool) or end < 0):
            add("error", "bad_chapter", "story_arc.chapter_end must be null or a non-negative integer", record_id)
        elif isinstance(start, int) and isinstance(end, int) and start > end:
            add("error", "bad_arc_range", "story_arc.chapter_start exceeds chapter_end", record_id)
        if record.get("status") not in STORY_ARC_STATUSES:
            add("error", "bad_story_arc_status", f"Unsupported story_arc status: {record.get('status')}", record_id)
        phase = record.get("phase")
        if phase is not None and phase not in STORY_ARC_PHASES:
            add("error", "bad_story_arc_phase", f"Unsupported story_arc phase: {phase}", record_id)

        parent_id = record.get("parent_arc_id")
        if parent_id is not None:
            if parent_id == record_id:
                add("error", "self_parent_arc", "story_arc cannot be its own parent", record_id)
            elif parent_id not in arc_ids:
                add("error", "bad_parent_arc_ref", f"Unknown story_arc.parent_arc_id: {parent_id}", record_id)
            elif isinstance(record_id, str):
                arc_parent[record_id] = parent_id
        for field, valid_ids, code in (
            ("event_ids", event_ids_all, "bad_arc_event_ref"),
            ("turning_point_ids", event_ids_all, "bad_arc_turning_point_ref"),
            ("entity_ids", entity_ids_all, "bad_arc_entity_ref"),
        ):
            refs = record.get(field)
            if not isinstance(refs, list):
                add("error", "bad_arc_refs", f"story_arc.{field} must be an array", record_id)
                continue
            for ref in refs:
                if ref not in valid_ids:
                    add("error", code, f"Unknown story_arc.{field}: {ref}", record_id)

    for arc_id in sorted(arc_parent):
        seen: set[str] = set()
        cursor = arc_id
        while cursor in arc_parent:
            if cursor in seen:
                add("error", "cyclic_arc_parent", "story_arc parent chain contains a cycle", arc_id)
                break
            seen.add(cursor)
            cursor = arc_parent[cursor]

    # A chapter can belong to several arcs. dominant_arc_id is only a non-exclusive
    # display hint, but it still has to be one of that chapter's explicit arc_ids.
    for record in graph.get("chapter_summaries") or []:
        if not isinstance(record, dict):
            continue
        record_id = record.get("id", "<chapter_summary without id>")
        refs = record.get("arc_ids", [])
        if not isinstance(refs, list):
            add("error", "bad_summary_arc_refs", "chapter_summaries.arc_ids must be an array", record_id)
            refs = []
        for ref in refs:
            if ref not in arc_ids:
                add("error", "bad_summary_arc_ref", f"Unknown chapter_summaries.arc_ids: {ref}", record_id)
        dominant = record.get("dominant_arc_id")
        if dominant is not None and dominant not in refs:
            add("error", "bad_dominant_arc", "dominant_arc_id must also appear in arc_ids", record_id)

    report = {
        "graph": str(graph_path),
        "validated_at": datetime.now(timezone.utc).isoformat(),
        "valid": not errors,
        "error_count": len(errors),
        "warning_count": len(warnings),
        "record_counts": {name: len(graph[name]) for name in ARRAYS},
        "source_audit": source_audit,
        "errors": errors,
        "warnings": warnings,
        "observations": observations,
    }
    output = json.dumps(report, ensure_ascii=False, indent=2)
    if args.report:
        args.report.resolve().write_text(output, encoding="utf-8")
    print(output)
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())

