from __future__ import annotations

import hashlib
import json
import re
from typing import Any, Iterable, Mapping

from nkg.core.runtime import GraphRuntime, chapter_value

LEVEL_ORDER = {"R1": 1, "R2": 2, "R3": 3, "R4": 4}

GLOBAL_PATTERNS = re.compile(
    r"(?:第一次|首次|最后一次|唯一|从未|从不|所有|全部|整个|全书|始终|never|first|last|only|all|none|whole[- ]book)", re.IGNORECASE,
)
TEMPORAL_PATTERNS = re.compile(
    r"(?:再次|又一次|重新|仍然|依旧|终于|此前|之前|后来|恢复|失去|获得|突破|退步|again|still|finally|previously|restore|lost|gain)", re.IGNORECASE,
)
CROSS_CHAPTER_PATTERNS = re.compile(
    r"(?:真实身份|身份|伪装|化名|别名|秘密|真相|承诺|发誓|誓言|约定|恋爱|喜欢|爱上|亲密|伏笔|预言|回忆|前世|identity|alias|secret|promise|oath|romance|intimacy|foreshadow|prophecy)", re.IGNORECASE,
)

DOMAIN_PATTERNS: dict[str, re.Pattern[str]] = {
    "relations": re.compile(r"(?:朋友|敌人|师父|师傅|徒弟|父亲|母亲|兄弟|姐妹|关系|同伴|partner|friend|enemy|teacher|parent)", re.I),
    "item_roles": re.compile(r"(?:得到|获得|丢失|交给|转移|赠送|武器|法宝|物品|材料|item|weapon|give|transfer)", re.I),
    "commitments": re.compile(r"(?:承诺|发誓|誓言|约定|赌约|复仇|promise|oath|vow|wager)", re.I),
    "romance_routes": re.compile(r"(?:喜欢|爱上|恋人|夫妻|婚约|暧昧|亲吻|亲密|romance|lover|kiss|intimacy)", re.I),
    "intimate_acts": re.compile(r"(?:亲吻|接吻|性行为|性交|亲密行为|kiss|sex|intercourse|intimate)", re.I),
    "foreshadowing": re.compile(r"(?:伏笔|暗示|预言|线索|谜团|回收|foreshadow|clue|prophecy|payoff)", re.I),
    "combat": re.compile(r"(?:战斗|决斗|击败|杀死|逃脱|对战|battle|duel|defeat|victory|killed)", re.I),
    "knowledge": re.compile(r"(?:知道|得知|秘密|真相|情报|knowledge|secret|learned)", re.I),
    "mortality": re.compile(r"(?:死亡|死去|复活|重生|阵亡|death|died|revive|resurrect)", re.I),
    "economy": re.compile(r"(?:购买|出售|交易|价格|金币|灵石|金钱|财富|buy|sell|trade|price|money)", re.I),
}

BASE_SCHEMA = ["entities", "events", "state_changes", "evidence", "review_issues"]
DOMAIN_SCHEMA = {
    "relations": ["relations"], "item_roles": ["item_roles"], "commitments": ["commitments"],
    "romance_routes": ["romance_routes"], "intimate_acts": ["intimate_acts"], "foreshadowing": ["foreshadowing"],
    "combat": ["events.combat"], "knowledge": ["state_changes.knowledge", "events.information"],
    "mortality": ["events.mortality", "state_changes.health"], "economy": ["events.transaction", "state_changes.wealth"],
}


def _text(excerpts: Iterable[Mapping[str, Any]]) -> str:
    return "\n".join(str(row.get("text") or "") for row in excerpts)


def _candidate_kind(candidate: Mapping[str, Any]) -> str:
    return str(candidate.get("kind") or candidate.get("candidate_type") or candidate.get("category") or "").strip().lower()


def choose_retrieval_level(text: str, candidates: Iterable[Mapping[str, Any]] = ()) -> str:
    kinds = " ".join(_candidate_kind(row) for row in candidates)
    combined = f"{text}\n{kinds}"
    if GLOBAL_PATTERNS.search(combined): return "R4"
    if CROSS_CHAPTER_PATTERNS.search(combined): return "R3"
    if TEMPORAL_PATTERNS.search(combined): return "R2"
    return "R1"


def _entity_names(entity: Mapping[str, Any]) -> list[str]:
    values: list[str] = []
    raw_values: list[Any] = [entity.get("name")]
    for field in ("aliases", "historical_names", "titles"):
        raw = entity.get(field)
        if isinstance(raw, list): raw_values.extend(raw)
    for value in raw_values:
        if isinstance(value, dict): value = value.get("name") or value.get("value")
        if isinstance(value, str) and value.strip(): values.append(value.strip())
    for row in entity.get("name_history", []) if isinstance(entity.get("name_history"), list) else []:
        if isinstance(row, dict) and isinstance(row.get("name"), str) and row["name"].strip(): values.append(row["name"].strip())
    return list(dict.fromkeys(values))


def detect_entities(runtime: GraphRuntime, text: str) -> set[str]:
    # Over-recall is safer than dropping a one-character name. Entity linking is
    # only a context-retrieval signal; it never proves identity or creates facts.
    return {
        entity_id for entity_id, entity in runtime.entity_by_id.items()
        if any(name in text for name in _entity_names(entity))
    }


def candidate_entity_ids(candidates: Iterable[Mapping[str, Any]]) -> set[str]:
    result: set[str] = set()
    keys = ("entity_id", "source_id", "target_id", "item_id", "character_id", "protagonist_id", "location_id")
    list_keys = ("entity_ids", "participant_ids", "promisor_ids", "counterparty_ids", "related_entity_ids")
    for candidate in candidates:
        for key in keys:
            value = candidate.get(key)
            if isinstance(value, str): result.add(value)
        for key in list_keys:
            values = candidate.get(key)
            if isinstance(values, list): result.update(value for value in values if isinstance(value, str))
    return result


def schema_slice(text: str, candidates: Iterable[Mapping[str, Any]], entity_count: int) -> list[str]:
    selected = list(BASE_SCHEMA)
    if entity_count > 1: selected.append("relations")
    kinds = {_candidate_kind(row) for row in candidates}
    for domain, pattern in DOMAIN_PATTERNS.items():
        if pattern.search(text) or any(domain.rstrip("s") in kind or domain in kind for kind in kinds):
            selected.extend(DOMAIN_SCHEMA[domain])
    return list(dict.fromkeys(selected))


def _recursive_evidence_ids(value: Any, result: list[str]) -> None:
    if isinstance(value, Mapping):
        for key, item in value.items():
            if key.endswith("evidence_ids") and isinstance(item, list):
                result.extend(ref for ref in item if isinstance(ref, str))
            else:
                _recursive_evidence_ids(item, result)
    elif isinstance(value, list):
        for item in value: _recursive_evidence_ids(item, result)


def _relevant_commitments(runtime: GraphRuntime, entity_ids: set[str], chapter: int) -> list[dict[str, Any]]:
    rows = []
    for row in runtime.commitments:
        created = chapter_value(row.get("created_chapter"))
        if created is not None and created > chapter: continue
        parties = set(row.get("promisor_ids") or []) | set(row.get("counterparty_ids") or [])
        if entity_ids & parties: rows.append(row)
    return rows


def _relevant_foreshadowing(runtime: GraphRuntime, entity_ids: set[str], chapter: int) -> list[dict[str, Any]]:
    rows = []
    for row in runtime.foreshadowing:
        planted = chapter_value(row.get("planted_chapter"))
        if planted is not None and planted > chapter: continue
        if entity_ids & set(row.get("related_entity_ids") or []): rows.append(row)
    return rows


def _state_capsule(runtime: GraphRuntime, entity_ids: set[str], chapter: int, level: str) -> dict[str, Any]:
    # R3/R4 retain the complete relevant state history. A context budget may
    # require splitting the job, never truncating this history silently.
    depth = {"R1": 1, "R2": 2, "R3": 10**9, "R4": 10**9}[level]
    return runtime.state_capsule(sorted(entity_ids), chapter, history_depth=depth)


def _context_records(runtime: GraphRuntime, entity_ids: set[str], start: int, end: int, level: str) -> dict[str, Any]:
    relations: list[dict[str, Any]] = []
    seen_rel: set[str] = set()
    for entity_id in entity_ids:
        rel_rows = runtime.relations_for(entity_id, None if level in {"R3", "R4"} else end)
        for row in rel_rows:
            valid_from = chapter_value(row.get("valid_from"))
            if valid_from is not None and valid_from > end: continue
            rid = str(row.get("id") or "")
            if rid and rid not in seen_rel: seen_rel.add(rid); relations.append(row)
    events: list[dict[str, Any]] = []
    seen_event: set[str] = set()
    if level in {"R3", "R4"}:
        for entity_id in entity_ids:
            for row in runtime.events_for(entity_id, None, end):
                eid = str(row.get("id") or "")
                if eid and eid not in seen_event: seen_event.add(eid); events.append(row)
    else:
        for row in runtime.events_between(start, end):
            participants = set(row.get("participant_ids") or [])
            if entity_ids & participants or row.get("location_id") in entity_ids: events.append(row)
    return {"relations": relations, "events": events}


def _evidence_pointers(runtime: GraphRuntime, *values: Any) -> list[dict[str, Any]]:
    refs: list[str] = []
    for value in values: _recursive_evidence_ids(value, refs)
    pointers: list[dict[str, Any]] = []
    for ref in dict.fromkeys(refs):
        evidence = runtime.evidence_record(ref)
        if evidence:
            pointers.append({"id": ref, "chapter": evidence.get("chapter"), "source_line_start": evidence.get("source_line_start"), "source_line_end": evidence.get("source_line_end")})
        else:
            pointers.append({"id": ref, "missing": True})
    return pointers


def _telemetry(parts: Mapping[str, Any]) -> dict[str, Any]:
    chars = {key: len(json.dumps(value, ensure_ascii=False, separators=(",", ":"))) for key, value in parts.items()}
    total = sum(chars.values())
    return {"chars_by_part": chars, "total_chars": total, "approx_input_tokens": (total + 3) // 4, "approximation": "character_count_divided_by_4; use provider telemetry when available"}


def build_extraction_packet(
    graph: Mapping[str, Any], excerpts: Iterable[Mapping[str, Any]], *, chapter_start: int, chapter_end: int,
    candidates: Iterable[Mapping[str, Any]] = (), max_context_chars: int | None = None, requested_level: str | None = None,
) -> dict[str, Any]:
    """Build the smallest complete context packet while preserving accuracy gates."""
    start, end = sorted((int(chapter_start), int(chapter_end)))
    excerpt_rows = [dict(row) for row in excerpts if isinstance(row, Mapping)]
    candidate_rows = [dict(row) for row in candidates if isinstance(row, Mapping)]
    source_text = _text(excerpt_rows)
    runtime = GraphRuntime(graph)
    detected = (detect_entities(runtime, source_text) | candidate_entity_ids(candidate_rows)) & set(runtime.entity_by_id)
    level = choose_retrieval_level(source_text, candidate_rows)
    if requested_level in LEVEL_ORDER and LEVEL_ORDER[requested_level] > LEVEL_ORDER[level]: level = requested_level
    hops = {"R1": 0, "R2": 1, "R3": 1, "R4": 2}[level]
    closure_ids = runtime.connected_entities(detected, end, hops=hops) if detected else set()
    context = _context_records(runtime, closure_ids, start, end, level)
    commitments = _relevant_commitments(runtime, closure_ids, end)
    foreshadowing = _relevant_foreshadowing(runtime, closure_ids, end)
    state = _state_capsule(runtime, closure_ids, end, level)
    schemas = schema_slice(source_text, candidate_rows, len(closure_ids))
    entity_rows = [runtime.entity_by_id[eid] for eid in sorted(closure_ids) if eid in runtime.entity_by_id]
    evidence_pointers = _evidence_pointers(runtime, entity_rows, state, context, commitments, foreshadowing, candidate_rows)
    global_claim = bool(GLOBAL_PATTERNS.search(source_text))
    required_capabilities = {
        "R1": ["current_scene", "semantic_boundary_overlap", "direct_evidence"],
        "R2": ["canonical_entity", "aliases", "prior_state", "changes_through_target", "contradictions"],
        "R3": ["connected_entities", "event_history", "arc_links", "distant_evidence", "unresolved_candidates"],
        "R4": ["complete_relevant_coverage", "indexed_search", "opened_candidate_evidence", "coverage_receipt"],
    }[level]
    packet = {
        "packet_version": 2, "chapter_range": [start, end], "retrieval_level": level,
        "source_excerpts": excerpt_rows, "candidate_records": candidate_rows, "entity_ids": sorted(closure_ids), "entities": entity_rows,
        "state_capsule": state, "relations": context["relations"], "events": context["events"], "commitments": commitments,
        "foreshadowing": foreshadowing, "evidence_pointers": evidence_pointers, "schema_slice": schemas,
        "accuracy_contract": {
            "candidate_recall_must_not_drop": True, "evidence_must_resolve_before_confirmation": True,
            "required_capabilities": required_capabilities, "global_search_required": global_claim or level == "R4",
            "on_incomplete_context": "emit_unresolved_not_guess", "budget_policy": "never_drop_candidates_evidence_or_required_history",
        },
    }
    telemetry = _telemetry({key: packet[key] for key in ("source_excerpts", "candidate_records", "entities", "state_capsule", "relations", "events", "commitments", "foreshadowing", "evidence_pointers", "schema_slice")})
    telemetry.update({"max_context_chars": max_context_chars, "budget_exceeded": bool(max_context_chars and telemetry["total_chars"] > max_context_chars), "truncated_for_budget": False})
    packet["token_telemetry"] = telemetry
    fingerprint_payload = json.dumps({"range": [start, end], "source": excerpt_rows, "candidates": candidate_rows, "level": level}, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    packet["packet_fingerprint"] = hashlib.sha256(fingerprint_payload).hexdigest()
    return packet
