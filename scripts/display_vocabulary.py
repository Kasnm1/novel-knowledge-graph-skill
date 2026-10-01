"""Reader-facing display vocabulary and the staleness rules for state facets.

One source for every renderer and export: Chinese labels for entity types,
facets, actions, relation types, statuses and enum values, merged with a book's
own `metadata.display_vocabulary`. `FACET_TTL` says how long a volatile state
(where someone is, how they feel, an injury) may be shown after it was last
changed or confirmed by an audit card; durable facets hold until they change.
A value past its TTL is hidden rather than shown stale.
"""

from __future__ import annotations

from attribute_keys import ATTRIBUTE_LABELS
from event_types import EVENT_TYPE_LABELS
from intimacy_types import EJACULATION_SITES, INTIMACY_TYPE_LABELS
from level_conversions import CONVERSION_RELATIONS as CONVERSION_RELATION_LABELS

DEFAULT_VOCABULARY = {
    "fallback": "未分类",
    "entity_types": {
        "character": "人物", "skill": "技能", "martial_soul": "特殊能力",
        "item": "物品", "organization": "组织", "location": "地点",
        "creature": "生物", "title": "称号", "concept": "概念",
        "level_axis": "等级体系",
    },
    "facets": {
        "attribute": "属性", "skill": "技能", "martial_soul": "武魂", "possession": "持有物",
        "identity": "身份", "title": "称号", "health": "身体状态",
        "location": "所在地点", "affiliation": "所属势力",
        "romance": "感情线／后宫", "relationship": "人物关系", "knowledge": "知情状态",
        "goal": "目标", "emotion": "情绪", "level": "等级",
    },
    "attribute_keys": {
        **ATTRIBUTE_LABELS,
    },
    "actions": {
        "gained": "获得", "lost": "失去", "changed": "改变",
        "transferred": "转移", "upgraded": "提升", "downgraded": "降低",
        "sealed": "封印", "unsealed": "解封", "damaged": "受损",
        "repaired": "恢复", "learned": "习得", "forgotten": "遗忘",
        "joined": "加入", "left": "离开", "revealed": "揭示",
        "concealed": "隐瞒",
    },
    "relations": {
        "parent_of": "父母关系", "teacher_of": "师生关系",
        "friend_of": "朋友关系", "rival_of": "对手关系",
        "member_of": "隶属于", "owns": "拥有", "uses": "使用",
        "learned": "习得", "knows_about": "知晓", "located_at": "位于",
        "commissions": "委托", "companion_of": "同伴关系",
        "familiar_with": "熟识", "grandparent_of": "祖孙关系",
        "healed": "治疗", "holds": "持有", "instructed": "指导",
        "leader_of": "领导", "romantic_partner_of": "恋爱关系",
        "sibling_of": "手足关系", "spouse_of": "夫妻关系",
        "sworn_sibling_of": "结义关系",
        "gifted_to": "赠予／馈赠", "gave_to": "赠予／馈赠",
        "protected_by": "保护／救助", "protects": "保护／救助", "rescuer_of": "保护／救助",
        "attacked": "伤害／攻击", "harmed": "伤害／攻击", "enemy_of": "敌对／追杀",
        "betrothed_to": "家族／婚约", "love_interest_of": "感情／亲密",
        "alter_ego_of": "身份／分身", "same_body_as": "身份／分身", "disguised_as": "身份／伪装",
        "transferred_to": "物品持有／转交", "gifted_item_to": "物品持有／转交",
        "close_friend_of": "挚友", "ally_of": "盟友", "mentor_of": "导师关系",
        "student_of": "师徒关系", "child_of": "子女关系", "family_member_of": "家族归属",
        "sect_member_of": "门派归属", "school_member_of": "学院归属", "citizen_of": "国家归属",
        "affiliated_with": "势力归属", "part_of": "属于上级", "subgroup_of": "下属组织",
        "located_in": "位于上级地点", "rescued": "保护／救助", "saved": "保护／救助",
        "hurt": "伤害／攻击", "attacked_by": "伤害／攻击", "shared_event_with": "共同经历事件",
        "lover_of": "恋人", "former_lover_of": "前恋人", "uncle_of": "叔伯／舅", "step_parent_of": "继父母",
        "relative_of": "亲戚", "colleague_of": "同事", "benefactor_of": "恩人", "savior_of": "救命恩人",
        "supports": "支持", "owes_favor_to": "欠人情", "subordinate_of": "下属", "servant_of": "仆从",
        "master_of": "主人", "serves": "效力于", "employs": "雇佣", "employed_by": "受雇于",
        "possesses": "拥有", "controls": "控制", "contains": "包含", "crafted_from": "炼制自",
        "derived_from": "源自", "controlled_by": "受控于",
    },
    "relation_statuses": {
        "active": "有效", "ambiguous": "关系未定", "ended": "已结束", "uncertain": "待确认",
    },
    "confidences": {
        "explicit": "原文明示", "inferred": "合理推断", "uncertain": "尚不确定",
    },
    "romance_statuses": {
        "ambiguous": "暧昧中", "mutual_interest": "相互有意",
        "confirmed_relationship": "关系已确认", "ended": "已经结束",
        "provisional_intimate": "亲密关系候选", "one_sided": "单方面亲密",
        "spouse": "夫妻关系", "betrothed": "婚约关系",
        "coerced_or_forced": "受迫／强迫语境", "accidental_or_contextual": "意外／情境接触",
        "excluded_nonromantic": "已排除为非恋爱", "uncertain": "尚不确定",
    },
    "romance_inclusion_bases": {
        "romantic_ambiguity": "感情暧昧", "intimate_contact": "发生亲密举动",
        "explicit_intimate_proposal": "明确亲密提议", "repeated_attachment": "反复依恋",
        "intimate_psychology": "亲密心理／张力", "marriage": "婚姻",
        "betrothal": "婚约", "spouse_relation": "夫妻关系",
    },
    "story_arc_statuses": {
        "open": "尚未收束", "active": "进行中", "paused": "暂缓",
        "resolved": "已收束", "uncertain": "待确认",
    },
    "story_arc_phases": {
        "setup": "铺垫", "development": "展开", "escalation": "升级",
        "turning_point": "转折", "climax": "高潮", "resolution": "收束",
        "aftermath": "余波", "interlude": "间章", "recurring": "长期推进", "uncertain": "待确认",
    },
    "item_categories": {
        "weapon": "武器", "armor": "防具／护具", "accessory": "饰品",
        "luxury_collectible": "奢侈品／珍藏", "consumable": "消耗品／药剂／丹药",
        "resource_material": "资源／材料", "book_manual_contract": "书卷／秘籍／契约",
        "vehicle_container_dwelling": "交通／容器／住所性物件", "token_credential": "信物／凭证",
        "ordinary": "普通物品", "unresolved": "待分类",
    },
    "consent_contexts": {
        "mutual": "双方自愿", "one_sided": "单方面主动", "accidental": "意外发生",
        "coerced": "非自愿／受迫", "forced": "暴力强迫", "ability_induced": "受能力影响",
        "altered_state": "异常状态", "uncertain": "性质待确认",
    },
    "foreshadow_statuses": {
        "suspected": "疑似伏笔", "open": "尚未回收", "progressed": "已有推进",
        "partially_resolved": "部分回收", "resolved": "已经回收",
        "false_lead": "已排除",
    },
    "progression_kinds": {
        "observation": "再次出现", "progression": "线索推进",
        "payoff": "伏笔回收", "concealment": "继续隐瞒",
        "identity_reveal": "身份揭示",
    },
    "event_types": {
        "ability_acquisition": "获得能力", "achievement": "达成成果",
        "advancement": "实力提升", "affiliation": "势力归属",
        "awakening": "能力觉醒", "breakthrough": "突破", "combat": "战斗",
        "combat_injury": "战斗受伤", "combat_result": "战斗结果",
        "conflict": "冲突", "countermeasure": "应对措施", "crafting": "制作",
        "demonstration": "展示", "departure": "离开", "discovery": "发现",
        "duel_result": "对决结果", "emergency_treatment": "紧急救治",
        "employment": "任职", "formation": "组建", "healing": "治疗",
        "injury": "受伤", "instruction": "传授", "journey": "行程",
        "leadership": "带领", "promotion": "晋升", "recovery": "恢复",
        "relationship": "关系变化", "resource_dispute": "资源争夺",
        "retrospective_advancement": "回溯性提升", "separation": "分别",
        "temporary_effect_end": "临时效果结束",
        "temporary_powerup": "临时强化", "training": "训练",
        "training_result": "训练成果", "transaction": "交易", "transfer": "转交",
    },
    "issue_severities": {"info": "说明", "warning": "需注意", "error": "错误"},
    "issue_categories": {
        "alias_conflict": "别名冲突", "contradiction": "信息矛盾",
        "coverage_gap": "覆盖缺口", "missing_cause": "原因缺失",
        "possible_foreshadowing": "疑似伏笔", "time_ambiguity": "时间不明确",
        "weak_evidence": "证据较弱",
        # 这两个必须分开：`non_narrative_chapter` 是「整章排除、零抽取」，
        # `author_note` 是「正文完整、章内另附作者语」。混用会让
        # 「正文章数 = analyzed_chapters − non_narrative_chapter」算少一章，
        # 而且读者会在待核问题里看到一章被标成「作者感言单章」却明明有剧情。
        "non_narrative_chapter": "作者感言单章",
        "author_note": "章内作者语",
    },
}

# The event-kind vocabulary is fixed in `event_types.py` so that merge, validation
# and both renderers cannot disagree about it. Fold it in here rather than
# duplicating the list, so a recommended type never renders as the fallback string.
DEFAULT_VOCABULARY["event_types"].update(EVENT_TYPE_LABELS)
DEFAULT_VOCABULARY.setdefault("intimacy_act_types", {}).update(INTIMACY_TYPE_LABELS)
DEFAULT_VOCABULARY.setdefault("level_conversion_relations", {}).update(CONVERSION_RELATION_LABELS)
DEFAULT_VOCABULARY.setdefault("ejaculation_sites", {}).update(EJACULATION_SITES)


def merge_vocabulary(base: dict, override: dict) -> dict:
    """Recursively merge a book-specific display vocabulary into Chinese defaults."""
    merged = {key: (value.copy() if isinstance(value, dict) else value) for key, value in base.items()}
    for key, value in (override or {}).items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key].update(value)
        else:
            merged[key] = value
    return merged

# Volatile facets: chapters a value stays visible after its last change or confirmation.
FACET_TTL: dict[str, int] = {
    "location": 5, "emotion": 3, "mind": 3, "attitude": 5, "state": 8, "status": 10,
    "health": 10, "affliction": 10, "appearance": 20, "goal": 40, "activity": 3,
}
# A health value naming death or a permanent loss is durable until a later change.
DURABLE_HEALTH_WORDS = ("死", "亡", "陨落", "身故", "残废", "失明", "断臂")
