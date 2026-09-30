"""Per-chapter audit card: the checklist every analysed chapter must answer.

A fragment that records nothing for a chapter and a fragment that never looked
are indistinguishable from their records alone. Measured on a 999-chapter run:
1.16 events per chapter (never more than 4), no state change in 624 chapters,
and 912 of 4,061 character mentions in chapter summaries with no record of that
character in that chapter. The audit card closes that gap by making every
checklist item an explicit answer — "recorded N" or "none, because …" — that a
deterministic check can hold against the records the fragment actually carries.

The card lives on the chapter's `chapter_summaries` row (no new top-level fact
array):

- `scenes[]`      scene segmentation: place, time, participants, POV, purpose;
- `presence[]`    every named entity present or mentioned, with a state check;
- `continuity`    how the chapter picks up the previous one and what it sets up;
- `narrative`     narrative function, cliffhanger, pacing, notable lines;
- `audit`         one receipt per `AUDIT_ITEMS` key.

Fragments declaring `metadata.audit_protocol >= 2` must carry a complete card for
every analysed narrative chapter. Older fragments are checked only when they
choose to carry a card.
"""

from __future__ import annotations

import re
from typing import Any, Callable, Iterable

from controlled_vocab import CLIFFHANGER_TYPES
from event_types import RECOMMENDED_EVENT_TYPES, canonical_event_type
from relation_types import RELATION_GROUPS, RELATION_TYPE_ALIASES, canonical_relation_type
from nkg.core.records import records

AUDIT_PROTOCOL = 2

AUDIT_ITEMS: dict[str, str] = {
    "scenes": "场景切分",
    "presence": "出场名册",
    "events": "情节点",
    "state_check": "在场人物状态确认",
    "levels": "等级变化",
    "skills_items": "功法与物品得失",
    "relations": "关系变化",
    "knowledge": "信息与秘密",
    "combat": "战斗与伤亡",
    "transactions": "交易与财富",
    "romance_intimacy": "感情与亲密",
    "commitments": "承诺",
    "foreshadowing": "伏笔与悬念",
    "traits": "外貌、性格与说话方式",
    "narrative": "叙事功能与名句",
}

RECEIPT_STATUSES = frozenset({"recorded", "none"})
PRESENCE_MODES = frozenset({"present", "mentioned"})
STATE_CHECKS = frozenset({"changed", "confirmed_unchanged", "not_tracked"})
PACING = frozenset({"fast", "medium", "slow"})
NARRATIVE_FUNCTIONS: dict[str, str] = {
    "setup": "铺垫",
    "development": "推进",
    "payoff": "爽点兑现",
    "face_slap": "打脸",
    "twist": "反转",
    "revelation": "揭秘",
    "climax": "高潮",
    "breather": "日常缓冲",
    "romance": "感情戏",
    "worldbuilding": "世界观展开",
    "transition": "过渡",
}
FORESHADOWING_KINDS = frozenset({"foreshadowing", "question"})
SENTENCE_END = re.compile(r"[。！？!?…]+")

Report = Callable[[str], None]


def _records(frag: dict, key: str) -> list[dict]:
    return records(frag.get(key))


def _in_chapter(rec: dict, chapter: int, *fields: str) -> bool:
    return any(rec.get(f) == chapter for f in fields)


def item_counts(frag: dict, chapter: int, card: dict) -> dict[str, int]:
    """Count the records a fragment carries for each audit item in one chapter."""
    events = [e for e in _records(frag, "events") if e.get("chapter") == chapter]
    changes = [s for s in _records(frag, "state_changes") if s.get("chapter") == chapter]
    by_facet = lambda *facets: sum(1 for s in changes if s.get("facet") in facets)
    relations = [
        r for r in _records(frag, "relations")
        if _in_chapter(r, chapter, "valid_from", "valid_to")
        or any(isinstance(o, dict) and o.get("chapter") == chapter for o in r.get("observations") or [])
    ]
    routes = [
        r for r in _records(frag, "romance_routes")
        if _in_chapter(r, chapter, "first_meeting_chapter", "ambiguity_started_chapter",
                       "confirmed_chapter", "first_sex_chapter")
    ]
    foreshadowing = [
        f for f in _records(frag, "foreshadowing")
        if _in_chapter(f, chapter, "planted_chapter", "payoff_chapter")
        or any(isinstance(p, dict) and p.get("chapter") == chapter for p in f.get("progression") or [])
    ]
    narrative = card.get("narrative") if isinstance(card.get("narrative"), dict) else {}
    return {
        "scenes": len(card.get("scenes") or []),
        "presence": len(card.get("presence") or []),
        "events": len(events),
        "state_check": sum(1 for s in changes if s.get("facet") not in {"level", "skill", "possession", "knowledge"}),
        "levels": by_facet("level"),
        "skills_items": by_facet("skill", "possession")
        + sum(1 for r in _records(frag, "item_roles") if _in_chapter(r, chapter, "valid_from", "valid_to")),
        "relations": len(relations),
        "knowledge": by_facet("knowledge") + sum(1 for e in events if e.get("information")),
        "combat": sum(1 for e in events if e.get("combat") or e.get("mortality")),
        "transactions": sum(1 for e in events if e.get("transaction")),
        "romance_intimacy": len(routes)
        + sum(1 for a in _records(frag, "intimate_acts") if a.get("chapter") == chapter),
        "commitments": sum(1 for c in _records(frag, "commitments")
                           if _in_chapter(c, chapter, "created_chapter", "resolved_chapter")),
        "foreshadowing": len(foreshadowing),
        "traits": sum(1 for t in _records(frag, "character_traits") if t.get("chapter") == chapter),
        "narrative": len(narrative.get("functions") or []) + len(narrative.get("quote_evidence_ids") or []),
    }


def check_card(card: dict, frag: dict, entity_types: dict[str, str], evidence_ids: set[str],
               err: Report, warn: Report) -> None:
    """Check one chapter's audit card against the records the fragment carries."""
    rid = card.get("id", "<无 id>")
    chapter = card.get("chapter")
    if not isinstance(chapter, int):
        err(f"{rid}: 审计卡缺少整数 chapter")
        return
    tag = f"{rid}（第 {chapter} 章）"

    # ---- presence ----
    presence = card.get("presence")
    present: set[str] = set()
    listed: set[str] = set()
    if not isinstance(presence, list) or not presence:
        err(f"{tag}: presence 出场名册为必填，且不能为空")
        presence = []
    changed_here = {s.get("entity_id") for s in _records(frag, "state_changes") if s.get("chapter") == chapter}
    for row in presence:
        if not isinstance(row, dict):
            err(f"{tag}: presence 中存在非对象记录")
            continue
        eid, mode, check = row.get("entity_id"), row.get("mode"), row.get("state_check")
        if eid not in entity_types:
            err(f"{tag}: presence.entity_id {eid!r} 不是已知实体")
            continue
        listed.add(eid)
        if mode not in PRESENCE_MODES:
            err(f"{tag}: {eid} 的 presence.mode 必须是 present / mentioned")
        if mode == "present":
            present.add(eid)
        if not str(row.get("role") or "").strip():
            warn(f"{tag}: {eid} 缺少 role（本章在做什么），名册无法向读者解释他为何出场")
        if mode == "present" and entity_types.get(eid) == "character":
            if check not in STATE_CHECKS:
                err(f"{tag}: 在场人物 {eid} 必须给 state_check（changed / confirmed_unchanged / not_tracked）")
            elif check == "changed" and eid not in changed_here:
                err(f"{tag}: {eid} 标为 changed，但本片没有他在本章的状态变化记录")
            elif check == "confirmed_unchanged" and eid in changed_here:
                err(f"{tag}: {eid} 标为 confirmed_unchanged，但本章记录了他的状态变化")

    for ev in _records(frag, "events"):
        if ev.get("chapter") != chapter:
            continue
        missing = [p for p in ev.get("participant_ids") or [] if p not in listed]
        if missing:
            err(f"{tag}: 事件 {ev.get('id')} 的参与者 {missing} 不在出场名册里")
    for sid in sorted(changed_here - listed):
        if entity_types.get(sid) == "character":
            err(f"{tag}: 人物 {sid} 本章有状态变化，却不在出场名册里")

    # ---- scenes ----
    scenes = card.get("scenes")
    event_ids = {e.get("id") for e in _records(frag, "events") if e.get("chapter") == chapter}
    covered: set[str] = set()
    if not isinstance(scenes, list) or not scenes:
        err(f"{tag}: scenes 场景切分为必填，至少一个场景")
        scenes = []
    for i, sc in enumerate(scenes, 1):
        if not isinstance(sc, dict):
            err(f"{tag}: scenes[{i}] 不是对象")
            continue
        if not str(sc.get("purpose") or "").strip():
            err(f"{tag}: scenes[{i}] 缺少 purpose（这一场要完成什么）")
        if not (sc.get("location_id") or str(sc.get("location_label") or "").strip()):
            warn(f"{tag}: scenes[{i}] 没有地点（location_id 或 location_label）")
        loc = sc.get("location_id")
        if loc and loc not in entity_types:
            err(f"{tag}: scenes[{i}].location_id {loc!r} 不是已知实体")
        stray = [p for p in sc.get("participant_ids") or [] if p not in present]
        if stray:
            err(f"{tag}: scenes[{i}] 的参与者 {stray} 在名册中不是 present")
        pov = sc.get("pov_entity_id")
        if pov and pov not in listed:
            err(f"{tag}: scenes[{i}].pov_entity_id {pov!r} 不在出场名册里")
        for ref in sc.get("event_ids") or []:
            if ref not in event_ids:
                err(f"{tag}: scenes[{i}] 引用的事件 {ref} 不是本章事件")
            covered.add(ref)
    if scenes and event_ids - covered:
        warn(f"{tag}: 事件 {sorted(event_ids - covered)} 没有归入任何场景")

    # ---- continuity and summary shape ----
    cont = card.get("continuity") if isinstance(card.get("continuity"), dict) else {}
    if chapter > 1 and not str(cont.get("from_previous") or "").strip():
        err(f"{tag}: continuity.from_previous（承上）为必填")
    if not str(cont.get("sets_up") or "").strip():
        err(f"{tag}: continuity.sets_up（启下）为必填；真的什么都没铺垫就写明「本章收束，无新悬念」")
    summary = str(card.get("summary") or "")
    sentences = [s for s in SENTENCE_END.split(summary) if s.strip()]
    if len(sentences) < 3:
        err(f"{tag}: summary 只有 {len(sentences)} 句，逐章审计要求三到六句")

    # ---- narrative ----
    nar = card.get("narrative") if isinstance(card.get("narrative"), dict) else None
    if nar is None:
        err(f"{tag}: narrative 为必填")
    else:
        bad = [f for f in nar.get("functions") or [] if f not in NARRATIVE_FUNCTIONS]
        if not nar.get("functions"):
            err(f"{tag}: narrative.functions 至少一项")
        if bad:
            err(f"{tag}: narrative.functions 含未知值 {bad}")
        if nar.get("cliffhanger_type") not in CLIFFHANGER_TYPES:
            err(f"{tag}: narrative.cliffhanger_type 必须取自受控词表")
        if nar.get("pacing") not in PACING:
            err(f"{tag}: narrative.pacing 必须是 fast / medium / slow")
        for ref in nar.get("quote_evidence_ids") or []:
            if ref not in evidence_ids:
                err(f"{tag}: narrative.quote_evidence_ids 引用了不存在的证据 {ref}")

    # ---- receipts ----
    audit = card.get("audit")
    if not isinstance(audit, dict):
        err(f"{tag}: audit 审计收据为必填")
        return
    counts = item_counts(frag, chapter, card)
    for key, label in AUDIT_ITEMS.items():
        receipt = audit.get(key)
        if not isinstance(receipt, dict):
            err(f"{tag}: 审计项「{label}」({key}) 没有收据")
            continue
        status, reason = receipt.get("status"), str(receipt.get("reason") or "").strip()
        actual = counts[key]
        if status not in RECEIPT_STATUSES:
            err(f"{tag}: 「{label}」收据 status 必须是 recorded / none")
        elif status == "recorded":
            if receipt.get("count") != actual:
                err(f"{tag}: 「{label}」收据写 {receipt.get('count')} 条，本片实际 {actual} 条")
            if actual == 0:
                err(f"{tag}: 「{label}」标为 recorded，但本片没有对应记录")
        else:
            if actual:
                err(f"{tag}: 「{label}」标为 none，但本片有 {actual} 条对应记录")
            if len(reason) < 4:
                err(f"{tag}: 「{label}」标为 none 时必须写明理由（原文确实没有什么）")
    extra = set(audit) - set(AUDIT_ITEMS)
    if extra:
        warn(f"{tag}: audit 含未知审计项 {sorted(extra)}")


def check_protocol_records(frag: dict, entity_types: dict[str, str], err: Report, warn: Report) -> None:
    """Record-level rules that protocol-2 fragments must satisfy."""
    for rel in _records(frag, "relations"):
        raw = rel.get("relation_type")
        if raw in RELATION_TYPE_ALIASES:
            err(f"{rel.get('id')}: relation_type {raw!r} 请写规范类型 {RELATION_TYPE_ALIASES[raw]!r}")
        elif canonical_relation_type(raw) not in RELATION_GROUPS:
            err(f"{rel.get('id')}: relation_type {raw!r} 不在 relation_types.RELATION_GROUPS 里")
    for ev in _records(frag, "events"):
        raw = ev.get("type")
        if raw not in RECOMMENDED_EVENT_TYPES:
            hint = canonical_event_type(raw)
            err(f"{ev.get('id')}: 事件 type {raw!r} 不在推荐集合里"
                + (f"，请写 {hint!r}" if hint in RECOMMENDED_EVENT_TYPES and hint != raw else ""))
    for fs in _records(frag, "foreshadowing"):
        if fs.get("kind", "foreshadowing") not in FORESHADOWING_KINDS:
            err(f"{fs.get('id')}: foreshadowing.kind 必须是 foreshadowing / question")

    axes = {e.get("id"): e for e in _records(frag, "entities") if e.get("type") == "level_axis"}
    for aid, axis in axes.items():
        applies = axis.get("applies_to")
        if not isinstance(applies, list) or not applies:
            err(f"{aid}: 新等级轴必须声明 applies_to（适用的实体类型），例如 [\"character\"]")
    for sc in _records(frag, "state_changes"):
        sid = sc.get("id")
        for side in ("before", "after"):
            value = sc.get(side)
            if value is None:
                continue
            if not isinstance(value, dict) or "label" not in value:
                err(f"{sid}: {side} 必须是 null 或 {{value, label, note}} 对象")
                continue
            label = str(value.get("label") or "")
            if re.search(r"[（(].{6,}[)）]", label):
                warn(f"{sid}: {side}.label「{label}」夹带括号说明，请移到 note")
        if sc.get("facet") == "level":
            axis_id = sc.get("target_id")
            axis = axes.get(axis_id)
            applies = axis.get("applies_to") if axis else None
            etype = entity_types.get(sc.get("entity_id"))
            if isinstance(applies, list) and etype and etype not in applies:
                err(f"{sid}: 等级轴 {axis_id} 只适用于 {applies}，不能记在 {etype} 实体上")


def narrative_chapters(frag: dict, analyzed: Iterable[int]) -> list[int]:
    """Analysed chapters minus those declared non-narrative in review_issues."""
    skip = {
        i.get("chapter") for i in _records(frag, "review_issues")
        if i.get("category") == "non_narrative_chapter"
    }
    return [c for c in analyzed if c not in skip]


def check_fragment_audit(frag: dict, entity_types: dict[str, str], evidence_ids: set[str],
                         analyzed: Iterable[int], err: Report, warn: Report) -> None:
    """Entry point used by check_fragment.py."""
    meta = frag.get("metadata") if isinstance(frag.get("metadata"), dict) else {}
    protocol = meta.get("audit_protocol") or 1
    cards = {c.get("chapter"): c for c in _records(frag, "chapter_summaries")
             if any(k in c for k in ("audit", "presence", "scenes"))}
    if protocol >= AUDIT_PROTOCOL:
        if meta.get("supplementary"):
            pass
        else:
            summaries = {c.get("chapter"): c for c in _records(frag, "chapter_summaries")}
            for ch in narrative_chapters(frag, analyzed):
                if ch not in summaries:
                    err(f"第 {ch} 章：audit_protocol {protocol} 要求每个正文章都有审计卡，本片缺失")
                elif ch not in cards:
                    err(f"第 {ch} 章：梗概存在，但没有审计卡字段（scenes / presence / audit）")
        check_protocol_records(frag, entity_types, err, warn)
    for card in cards.values():
        check_card(card, frag, entity_types, evidence_ids, err, warn)


def blank_card(chapter: int) -> dict[str, Any]:
    """A skeleton authors can fill; every receipt starts unanswered on purpose."""
    return {
        "chapter": chapter,
        "summary": "",
        "continuity": {"from_previous": "", "sets_up": ""},
        "scenes": [],
        "presence": [],
        "narrative": {"functions": [], "cliffhanger_type": "none", "pacing": "medium", "quote_evidence_ids": []},
        "audit": {key: {"status": None, "count": 0, "reason": ""} for key in AUDIT_ITEMS},
    }
