#!/usr/bin/env python3
"""Build a polished self-contained Cytoscape.js novel knowledge dashboard."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

from agent_detection import detect_agents
from attribute_keys import ATTRIBUTE_LABELS
from event_types import EVENT_TYPE_LABELS
from character_traits import FACET_ALIASES, FACET_LABELS, FACET_ORDER
from level_conversions import CONVERSION_RELATIONS as CONVERSION_RELATION_LABELS
from reader_prose import to_js as reader_prose_js
from intimacy_types import EJACULATION_SITES, INTIMACY_TYPE_LABELS
from derive_collection_views import derive_collection_views
from validate_style_observations import validate_style_observations


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


LINE_REFERENCE_RE = re.compile(r"(?:原文)?第\s*\d+\s*(?:[—–\-~～至]\s*\d+\s*)?行")


def reader_safe_data(value: object) -> object:
    """Remove audit-only line locations from the self-contained reader artifact."""
    if isinstance(value, dict):
        return {
            key: reader_safe_data(item)
            for key, item in value.items()
            if key not in {"source_line_start", "source_line_end"}
        }
    if isinstance(value, list):
        return [reader_safe_data(item) for item in value]
    if isinstance(value, str):
        value = value.replace("以准备稿绝对行号为证", "以准备稿原文为证")
        return LINE_REFERENCE_RE.sub("", value)
    return value


HTML = r'''<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>小说知识图谱</title>
<link rel="icon" href="data:,">
<style>
:root{color-scheme:light;--bg:#f4f5f7;--surface:#fff;--surface2:#f8f9fb;--ink:#171a21;--muted:#687083;--line:#e2e5eb;--accent:#6157d8;--accent-soft:#eeecff;--good:#15845f;--warn:#b46a08;--danger:#b53c4b;--shadow:0 12px 40px rgba(26,30,44,.08)}
*{box-sizing:border-box}html{scroll-behavior:smooth}body{margin:0;background:var(--bg);color:var(--ink);font:14px/1.55 Inter,"Segoe UI","Microsoft YaHei",sans-serif;overflow-y:scroll;-webkit-font-smoothing:antialiased;-moz-osx-font-smoothing:grayscale;text-rendering:optimizeLegibility}button,input,select{font:inherit}button{cursor:pointer}.app{min-height:100vh}.app>header{height:72px}
header{position:sticky;top:0;display:flex;align-items:center;gap:18px;padding:0 22px;background:rgba(255,255,255,.92);border-bottom:1px solid var(--line);backdrop-filter:blur(14px);z-index:8}.brand{min-width:250px}.brand h1{font-size:17px;line-height:1.25;margin:0;font-weight:650}.brand p{margin:4px 0 0;color:var(--muted);font-size:12px}.metrics{display:flex;gap:22px;margin-left:auto}.metric b{display:block;font-size:16px;line-height:1.1}.metric span{color:var(--muted);font-size:11px}.verified{color:var(--good)}
.shell{--detail-width:370px;min-height:calc(100vh - 72px);display:grid;grid-template-columns:248px minmax(360px,1fr) var(--detail-width);align-items:start}.controls{position:sticky;top:72px;max-height:calc(100vh - 72px);padding:18px;background:var(--surface);border-right:1px solid var(--line);overflow-y:auto;scrollbar-gutter:stable;overscroll-behavior:contain}.controls h2{font-size:11px;letter-spacing:.12em;text-transform:uppercase;color:var(--muted);margin:22px 0 9px}.controls h2:first-child{margin-top:0}.field{display:grid;gap:6px}.field label,.chapter-head{font-size:12px;color:var(--muted)}input[type=search],select{width:100%;border:1px solid var(--line);border-radius:10px;background:var(--surface2);color:var(--ink);padding:9px 10px;outline:none}input:focus,select:focus{border-color:#9a93ed;box-shadow:0 0 0 3px var(--accent-soft)}input[type=range]{width:100%;accent-color:var(--accent)}.chapter-head{display:flex;justify-content:space-between}.chapter-head b{color:var(--accent);font-size:13px}.segmented{display:grid;grid-template-columns:repeat(3,1fr);gap:4px;background:var(--surface2);padding:4px;border-radius:11px}.segmented.two{grid-template-columns:repeat(2,1fr)}.segmented button,.type-button,.ghost{border:0;background:transparent;color:var(--muted);border-radius:8px;padding:7px}.segmented button.active,.type-button.active{background:var(--surface);color:var(--ink);box-shadow:0 1px 4px rgba(20,24,34,.08)}.type-mode-row{display:grid;grid-template-columns:1fr auto;gap:7px;align-items:center;margin-bottom:7px}.type-actions{display:flex;gap:4px}.type-actions button{border:1px solid var(--line);background:var(--surface);color:var(--muted);border-radius:8px;padding:6px 8px}.type-actions button:hover:not(:disabled){color:var(--accent);border-color:#bbb6f3}.type-actions button:disabled{opacity:.4;cursor:default}.type-list{display:grid;gap:4px}.type-button{display:flex;align-items:center;gap:8px;text-align:left}.select-mark{display:grid;place-items:center;width:16px;height:16px;border:1.5px solid #b8beca;border-radius:4px;color:white;font-size:11px;line-height:1;flex:none}.single-mode .select-mark{border-radius:50%}.type-button.active .select-mark{background:var(--accent);border-color:var(--accent)}.type-button.active .select-mark::after{content:'✓'}.single-mode .type-button.active .select-mark::after{content:'';width:6px;height:6px;border-radius:50%;background:white}.swatch{width:9px;height:9px;border-radius:50%;flex:none}.type-button small{margin-left:auto;color:var(--muted)}.hint{color:var(--muted);font-size:12px;margin-top:14px}.status{padding:10px 11px;background:#ecf8f3;color:var(--good);border-radius:10px;font-size:12px}
 .stage{min-width:0;position:sticky;top:72px;height:calc(100vh - 72px);background:radial-gradient(circle at 50% 40%,#fff 0,#f7f8fb 55%,#eff1f5 100%)}.stage-nav{position:absolute;top:14px;left:50%;transform:translateX(-50%);z-index:4;display:flex;gap:4px;max-width:calc(100% - 24px);overflow-x:auto;padding:4px;background:rgba(255,255,255,.94);border:1px solid var(--line);border-radius:12px;box-shadow:var(--shadow)}.stage-nav button{border:0;background:transparent;color:var(--muted);padding:8px 13px;border-radius:8px;white-space:nowrap}.stage-nav button.active{background:var(--accent-soft);color:var(--accent)}.graph-tools{position:absolute;left:16px;bottom:16px;z-index:4;display:flex;gap:6px}.ghost{background:rgba(255,255,255,.92);border:1px solid var(--line);padding:7px 10px;box-shadow:0 4px 16px rgba(30,34,48,.05)}.ghost:hover{color:var(--accent);border-color:#bbb6f3}#cy{width:100%;height:100%}.view{display:none;height:100%;overflow:auto;scrollbar-gutter:stable}.view.active{display:block}.list-view{padding:74px 28px 28px;max-width:980px;margin:auto}.list-view h2{font-size:22px;margin:0 0 6px}.list-view>p{margin:0 0 22px;color:var(--muted)}.feed{display:grid;gap:9px}.feed-item{display:grid;grid-template-columns:70px 1fr;gap:12px;padding:14px 0;border-bottom:1px solid var(--line);cursor:pointer}.feed-item:hover h3{color:var(--accent)}.feed-item time{color:var(--accent);font-weight:600}.feed-item h3{font-size:14px;margin:0 0 3px}.feed-item p{color:var(--muted);margin:0}.tag{display:inline-block;font-size:11px;color:var(--muted);margin-right:8px}.empty{padding:36px;color:var(--muted);text-align:center}
 .detail{position:relative;min-height:calc(100vh - 72px);background:var(--surface);border-left:1px solid var(--line);overflow:visible}.detail-resize{position:absolute;left:-6px;top:0;bottom:0;width:12px;z-index:7;cursor:col-resize;touch-action:none}.detail-resize::after{content:'';position:absolute;left:5px;top:0;bottom:0;width:2px;background:transparent;transition:background .15s}.detail-resize:hover::after,.detail-resize:focus::after,body.detail-resizing .detail-resize::after{background:var(--accent)}.detail-resize:focus{outline:none}.detail-inner{padding:21px}.detail .eyebrow{color:var(--accent);font-size:11px;font-weight:650;letter-spacing:.1em;text-transform:uppercase}.detail h2{font-size:23px;line-height:1.25;margin:5px 0 7px}.detail .summary{color:var(--muted);margin:0}.detail-back{display:block;width:100%;margin:0 0 14px;padding:9px 11px;border:1px solid #c9c5f4;border-radius:9px;background:var(--accent-soft);color:var(--accent);font-weight:600;text-align:left}.detail-back:hover{border-color:var(--accent)}.chips{display:flex;gap:5px;flex-wrap:wrap;margin:12px 0}.chip{padding:3px 8px;border-radius:999px;background:var(--surface2);color:var(--muted);font-size:11px}.section{border-top:1px solid var(--line);margin-top:18px;padding-top:16px}.section h3{font-size:12px;margin:0 0 10px;color:var(--muted);letter-spacing:.06em}.row{display:grid;grid-template-columns:92px 1fr;gap:9px;margin:7px 0}.row b{color:var(--muted);font-weight:500}.history{display:grid;gap:8px}.history-item{border-left:2px solid #c9c5f4;padding:7px 0 7px 11px;cursor:pointer}.history-item:hover{border-color:var(--accent)}.history-item b{font-size:12px}.history-item p{margin:3px 0;color:var(--muted);font-size:12px}.quote{margin:9px 0;padding:10px 11px;background:var(--surface2);border-radius:9px;color:#3f4657}.quote small{display:block;color:var(--muted);margin-top:5px}.confidence-explicit{color:var(--good)}.confidence-inferred{color:var(--warn)}.confidence-uncertain{color:var(--danger)}pre{white-space:pre-wrap;word-break:break-word;font:12px/1.5 ui-monospace,monospace;color:#3f4657;margin:0}.coverage-grid{display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-top:14px}.coverage-grid div{background:var(--surface2);padding:10px;border-radius:9px}.coverage-grid b{display:block;font-size:15px}.coverage-grid span{font-size:11px;color:var(--muted)}
.warehouse-toolbar{display:grid;grid-template-columns:minmax(180px,1fr) 170px 170px auto;gap:9px;align-items:center;margin:18px 0}.warehouse-tabs{grid-column:1/-1;display:grid;grid-template-columns:repeat(4,1fr);gap:5px;padding:4px;background:var(--surface);border:1px solid var(--line);border-radius:12px}.warehouse-tabs button{border:0;background:transparent;color:var(--muted);padding:8px 10px;border-radius:8px}.warehouse-tabs button.active{background:var(--accent-soft);color:var(--accent);font-weight:600}.warehouse-view-toggle{display:flex;gap:4px;padding:4px;background:var(--surface2);border-radius:10px}.warehouse-view-toggle button{border:0;background:transparent;color:var(--muted);padding:6px 9px;border-radius:7px}.warehouse-view-toggle button.active{background:var(--surface);color:var(--accent);box-shadow:0 1px 4px rgba(20,24,34,.08)}.warehouse-section{margin-top:22px}.warehouse-section:first-child{margin-top:10px}.warehouse-section-head{display:flex;align-items:center;gap:9px;margin:0 0 10px;padding-bottom:7px;border-bottom:1px solid var(--line)}.warehouse-section-head h3{margin:0;font-size:16px}.warehouse-section-head span{padding:2px 7px;border-radius:999px;background:var(--accent-soft);color:var(--accent);font-size:11px}.warehouse-section-note{margin-left:auto!important;background:transparent!important;color:var(--muted)!important;font-size:11px!important}.warehouse-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(235px,1fr));gap:11px}.warehouse-card{min-width:0;padding:15px;border:1px solid var(--line);border-radius:12px;background:rgba(255,255,255,.82);cursor:pointer;text-align:left}.warehouse-card:hover{border-color:#bbb6f3;box-shadow:0 7px 22px rgba(41,37,92,.08);transform:translateY(-1px)}.warehouse-card h3{margin:0 0 5px;font-size:15px}.warehouse-card p{margin:7px 0 0;color:var(--muted);font-size:12px;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}.warehouse-card-status{margin-top:8px;padding:7px 9px;border-radius:8px;background:var(--accent-soft);color:#433b9d;font-size:12px;font-weight:600}.warehouse-card-secondary{margin-top:5px;color:#4d566b;font-size:11px}.warehouse-card-stats{margin-top:9px;color:var(--muted);font-size:11px}.warehouse-card-meta{display:flex;justify-content:space-between;gap:8px;margin-top:11px;color:var(--muted);font-size:11px}.warehouse-card-alias{margin-top:8px;color:var(--accent);font-size:11px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.relation-tags{display:flex;gap:4px;flex-wrap:wrap;margin-top:8px}.relation-tags span{padding:2px 6px;border-radius:999px;background:var(--surface2);color:var(--muted);font-size:10px}.warehouse-table-wrap{overflow:auto;border:1px solid var(--line);border-radius:11px;background:var(--surface)}.warehouse-table{width:100%;border-collapse:collapse;min-width:650px}.warehouse-table th,.warehouse-table td{padding:9px 11px;border-bottom:1px solid var(--line);text-align:left;font-size:12px}.warehouse-table th{position:sticky;top:0;background:var(--surface2);color:var(--muted);font-weight:600}.warehouse-table tr:last-child td{border-bottom:0}.warehouse-table tbody tr{cursor:pointer}.warehouse-table tbody tr:hover,.warehouse-table tbody tr:focus{background:var(--accent-soft);outline:none}.warehouse-table-name b{display:block}.warehouse-table-name small{color:var(--muted)}.level-axis{margin-top:22px}.level-axis:first-child{margin-top:10px}.level-axis-head{display:flex;align-items:baseline;gap:9px;flex-wrap:wrap;margin:0 0 4px}.level-axis-head h3{margin:0;font-size:16px}.level-axis-head span{padding:2px 7px;border-radius:999px;background:var(--accent-soft);color:var(--accent);font-size:11px}.level-axis-note{margin:6px 0 10px;color:var(--muted);font-size:12px}.level-ladder{display:flex;flex-direction:column;gap:4px;margin:10px 0 4px}.level-rung{display:grid;grid-template-columns:minmax(72px,auto) 1fr auto;gap:9px;align-items:center;padding:6px 10px;border:1px solid var(--line);border-radius:9px;background:rgba(255,255,255,.6);font-size:12px}.level-rung.attested{border-color:#bbb6f3;background:var(--accent-soft)}.level-rung b{font-weight:600}.level-rung .rung-holders{color:#4d566b;font-size:11px;text-align:right}.level-rung .rung-range{color:var(--muted);font-size:11px}.conv-list{display:flex;flex-direction:column;gap:7px;margin-top:8px}.conv-row{display:grid;grid-template-columns:1fr auto 1fr;gap:9px;align-items:center;padding:9px 11px;border:1px solid var(--line);border-radius:10px;background:rgba(255,255,255,.72);font-size:12px}.conv-side{min-width:0}.conv-side em{font-style:normal;color:var(--muted);font-size:11px}.conv-side b{display:block;font-size:13px}.conv-rel{padding:3px 9px;border-radius:999px;background:var(--accent-soft);color:var(--accent);font-size:11px;white-space:nowrap}.conv-why{grid-column:1/-1;color:var(--muted);font-size:11px;margin-top:5px}.conv-derived{border-style:dashed}.conv-derived .conv-rel{background:var(--surface2);color:var(--muted)}.conv-tools{display:grid;grid-template-columns:minmax(140px,1fr) minmax(120px,1fr);gap:8px;margin:12px 0 4px}.conv-tools select,.conv-tools input{width:100%}.conv-out{margin-top:10px}
.person-time{margin:17px 0 4px;padding:13px;background:var(--surface2);border-radius:11px}.person-time-head{display:flex;justify-content:space-between;align-items:center;margin-bottom:8px}.person-time-head b{font-size:12px}.person-time-head span{color:var(--accent);font-weight:650}.person-time input{width:100%;accent-color:var(--accent)}.time-dots{height:15px;position:relative;margin:0 6px}.time-dot{position:absolute;top:2px;width:7px;height:7px;padding:0;border:0;border-radius:50%;background:#b9bfca;transform:translateX(-50%)}.time-dot.past{background:#8c84df}.time-dot.current{width:11px;height:11px;top:0;background:var(--accent);box-shadow:0 0 0 3px var(--accent-soft)}.time-nav{display:grid;grid-template-columns:1fr 1fr;gap:7px;margin-top:4px}.time-nav button{border:1px solid var(--line);background:var(--surface);color:var(--muted);border-radius:8px;padding:6px}.time-nav button:not(:disabled):hover{color:var(--accent);border-color:#bbb6f3}.time-nav button:disabled{opacity:.42;cursor:default}
 .category-list{display:grid;gap:8px;margin-top:17px}.category{border:1px solid var(--line);border-radius:11px;background:var(--surface)}.category>summary{display:flex;align-items:center;gap:8px;padding:11px 12px;cursor:pointer;font-weight:600;list-style:none}.category>summary::-webkit-details-marker{display:none}.category>summary::before{content:'›';color:var(--accent);font-size:18px;line-height:1;transition:transform .16s}.category[open]>summary::before{transform:rotate(90deg)}.category>summary small{margin-left:auto;color:var(--muted);font-weight:400}.category-body{border-top:1px solid var(--line);padding:10px 12px 12px}.category-subtitle{font-size:11px;color:var(--muted);margin:8px 0 5px}.category-subtitle:first-child{margin-top:0}.category-empty{color:var(--muted);font-size:12px}.state-line{display:grid;grid-template-columns:minmax(76px,auto) 1fr;gap:9px;padding:5px 0}.state-line b{color:var(--muted);font-weight:500}.change-line{padding:8px 0;border-top:1px solid var(--line);cursor:pointer}.change-line:first-of-type{border-top:0}.change-line b{font-size:12px}.change-line p{margin:3px 0 0;color:var(--muted);font-size:12px}.change-values{color:#3f4657}.empty-value{color:var(--muted)}.romance-card{padding:11px;border:1px solid #dedaf8;border-radius:10px;background:#faf9ff;cursor:pointer}.romance-card+.romance-card{margin-top:8px}.romance-card:hover{border-color:var(--accent)}.romance-card h3{margin:0 0 5px;font-size:14px}.romance-card p{margin:3px 0;color:var(--muted);font-size:12px}.milestone-grid{display:grid;gap:7px}.milestone{padding:9px 10px;border-radius:9px;background:var(--surface2)}.milestone b{display:block;font-size:12px}.milestone span{color:var(--muted);font-size:12px}
 .level-strip{display:flex;gap:8px;flex-wrap:wrap;margin:14px 0 2px}.level-card{flex:1 1 132px;min-width:132px;padding:9px 11px;border:1px solid #e4d6bd;border-radius:10px;background:#fdf9f1}.level-card .level-axis{display:block;font-size:11px;color:var(--muted);letter-spacing:.04em}.level-card b{display:block;font-size:17px;margin:2px 0 1px;color:#8a5f18}.level-card small{color:var(--muted);font-size:11px}.summary-withheld{font-style:italic;opacity:.82}
.agent-why{margin:6px 0 0;padding:7px 10px;border-left:2px solid var(--accent);background:var(--accent-soft);border-radius:0 8px 8px 0;color:#4d566b;font-size:11px}
.category>summary{flex-wrap:wrap;row-gap:3px}.category-title{font-weight:600}.category-preview{flex:0 0 100%;color:var(--muted);font-weight:400;font-size:11px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.entry-list{display:grid;gap:7px;margin-top:2px}
.entry{padding:9px 11px;border:1px solid var(--line);border-radius:10px;background:var(--surface2)}
.entry-name{display:flex;align-items:center;gap:7px;flex-wrap:wrap;margin:0;font-size:14.5px;font-weight:650;line-height:1.3;color:var(--ink)}
.entry-dot{width:8px;height:8px;border-radius:50%;flex:none}
.entry-kind{padding:2px 6px;border-radius:999px;background:rgba(255,255,255,.75);border:1px solid var(--line);color:var(--muted);font-size:10px;font-weight:400}
.entry-badge{padding:2px 8px;border-radius:999px;background:var(--accent-soft);color:var(--accent);font-size:11px;font-weight:600}
.entry-meta{margin:4px 0 0;color:var(--muted);font-size:11px}
.entry-lines{margin-top:6px;display:grid;gap:4px}
.entry-line{display:grid;grid-template-columns:minmax(84px,auto) 1fr;gap:9px;font-size:12px;color:#3f4657;cursor:pointer}
.entry-line:hover{color:var(--accent)}
.entry-line b{font-weight:600;color:var(--muted)}
.entry-reason{margin:5px 0 0;color:var(--muted);font-size:11px;line-height:1.5}
.entry-reasons{margin-top:8px;border-top:1px dashed var(--line);padding-top:6px}
.entry-reasons>summary{cursor:pointer;color:var(--muted);font-size:11px;list-style:none}
.entry-reasons>summary::-webkit-details-marker{display:none}
.entry-reasons>summary::before{content:'› ';color:var(--accent)}
.entry-reasons[open]>summary::before{content:'⌄ '}
.entity-summary-card{margin:14px 0 4px;padding:12px;border:1px solid #dcd8fb;border-radius:12px;background:linear-gradient(135deg,#faf9ff,#f4f2ff)}.entity-summary-scope{color:var(--accent);font-size:11px;font-weight:650}.entity-summary-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:7px;margin-top:9px}.entity-summary-grid div{padding:7px 8px;border-radius:8px;background:rgba(255,255,255,.78)}.entity-summary-grid b{display:block;font-size:15px}.entity-summary-grid span{color:var(--muted);font-size:10px}.entity-highlights{display:flex;gap:5px;flex-wrap:wrap;margin-top:9px}.entity-highlights span{padding:3px 7px;border-radius:999px;background:#fff;color:#4d566b;font-size:11px}.entity-latest{margin-top:8px;color:var(--muted);font-size:11px}.history-more{margin-top:7px;border-top:1px dashed var(--line);padding-top:6px}.history-more>summary{cursor:pointer;color:var(--accent);font-size:11px}.evidence-summary{color:var(--muted);font-size:11px;margin:0 0 7px}.quote-preview{display:grid;grid-template-columns:auto 1fr;gap:8px;margin:6px 0;padding:8px 9px;border-radius:8px;background:var(--surface2);font-size:11px}.quote-preview b{color:var(--accent);white-space:nowrap}.quote-preview span{min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.category-scope{padding:6px 8px;border-radius:8px;background:var(--surface2);color:var(--muted);font-size:11px}.category-scope.current{background:var(--accent-soft);color:#4d45aa}
@media(max-width:1050px){.shell{grid-template-columns:220px minmax(330px,1fr) var(--detail-width)}.metrics .metric:nth-child(-n+2){display:none}.warehouse-toolbar{grid-template-columns:1fr 160px}}@media(max-width:780px){.app{min-height:100vh}.app>header{height:auto;min-height:72px}.shell{grid-template-columns:1fr;min-height:0}.controls,.stage{position:static;top:auto;max-height:none}.controls{border-right:0;border-bottom:1px solid var(--line);overflow:visible}.stage{height:70vh}.detail{border-left:0;border-top:1px solid var(--line);min-height:420px}.detail-resize{display:none}.warehouse-toolbar{grid-template-columns:1fr}.warehouse-tabs{grid-template-columns:1fr}.warehouse-tabs,#warehouseSearch,#warehouseSort,#warehouseFilter,.warehouse-view-toggle{grid-column:1}.entity-summary-grid{grid-template-columns:repeat(2,1fr)}.metrics{display:none}.brand{min-width:0}}
.trait-history{margin:.3rem 0 0;color:var(--muted,#7b8494);font-size:12px;line-height:1.55}
.graph-visible-count{position:absolute;top:72px;left:16px;z-index:4;padding:6px 10px;border:1px solid var(--line);border-radius:9px;background:rgba(255,255,255,.92);color:var(--muted);font-size:11px;box-shadow:0 4px 16px rgba(30,34,48,.05)}
.scope-full{border-left:3px solid #d9d5ff;padding-left:12px}.scope-full h3::after{content:' · 不隐藏后续信息';font-weight:400;color:var(--accent)}
.warehouse-tabs{grid-template-columns:repeat(6,minmax(95px,1fr));overflow-x:auto}.page-controls{position:sticky;bottom:0;display:flex;align-items:center;justify-content:center;gap:8px;margin:16px 0 0;padding:10px;background:rgba(255,255,255,.94);border:1px solid var(--line);border-radius:11px;z-index:2}.page-controls button{border:1px solid var(--line);background:var(--surface);padding:6px 10px;border-radius:8px}.page-controls button:disabled{opacity:.4}.page-controls select{width:auto;padding:5px 8px}.arc-lanes{display:grid;gap:8px}.arc-lane{display:grid;grid-template-columns:160px minmax(220px,1fr);gap:10px;align-items:center}.arc-label{min-width:0}.arc-label b{display:block}.arc-label small{color:var(--muted)}.arc-track{position:relative;height:34px;border-radius:8px;background:var(--surface2);overflow:hidden}.arc-bar{position:absolute;top:5px;height:24px;min-width:8px;border:1px solid #8e86e5;border-radius:7px;background:var(--accent-soft);color:#433b9d;font-size:11px;padding:3px 7px;overflow:hidden;white-space:nowrap;text-overflow:ellipsis}.arc-lane.child .arc-label{padding-left:18px}.collection-grid,.style-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(240px,1fr));gap:10px}.collection-card,.style-card{padding:14px;border:1px solid var(--line);border-radius:12px;background:var(--surface)}.collection-card{color:inherit;text-align:left}.collection-card.active{border-color:var(--accent);background:var(--accent-soft)}.collection-card h3,.style-card h3{margin:0 0 6px}.collection-toolbar{display:flex;gap:8px;align-items:center;flex-wrap:wrap;margin:12px 0}.collection-toolbar select{width:auto}.membership-chip{display:inline-block;margin:2px 4px 2px 0;padding:2px 7px;border:0;border-radius:999px;background:var(--accent-soft);color:var(--accent);font-size:10px}.relation-lane-label{font-size:10px;color:var(--muted)}
</style>
<script>__CYTOSCAPE__</script>
</head>
<body>
<div class="app">
 <header><div class="brand"><h1 id="title">小说知识图谱</h1><p id="subtitle"></p></div><div class="metrics"><div class="metric"><b id="mCharacters">0</b><span>人物</span></div><div class="metric"><b id="mAbilities">0</b><span id="abilityMetricLabel">能力</span></div><div class="metric"><b id="mChanges">0</b><span>历史变化</span></div><div class="metric"><b id="mEvidence">0</b><span>原文证据</span></div><div class="metric"><b id="mVerified" class="verified">—</b><span>数据审计</span></div></div></header>
 <div class="shell">
  <aside class="controls">
   <h2>浏览范围</h2><div class="segmented" id="scope"><button data-scope="core" class="active">核心</button><button data-scope="characters">人物</button><button data-scope="all">全部</button></div>
   <h2>章节回放</h2><div class="chapter-head"><span>查看当时状态</span><b>第 <span id="chapterValue">50</span> 章</b></div><input id="chapter" type="range" min="1" max="50" value="50">
    <h2>查找</h2><div class="field"><input id="search" type="search" placeholder="人物、物品或别名"><select id="layout"><option value="lanes">分类关系泳道</option><option value="concentric">中心辐射布局</option><option value="breadthfirst">层级／子集布局</option></select></div>
   <h2>实体类型</h2><div class="type-mode-row"><div id="typeMode" class="segmented two"><button data-type-mode="single">单选</button><button data-type-mode="multi" class="active">多选</button></div><div class="type-actions"><button id="typeAll" title="选择全部类型">全选</button><button id="typeNone" title="清空类型选择">清空</button></div></div><div id="types" class="type-list" aria-label="实体类型筛选"></div>
    <h2>数据状态</h2><div id="status" class="status"></div><p class="hint">默认只显示焦点实体的一度关系，并按家族、朋友、师徒、敌对、感情、势力、物品与身份分区；搜索会聚焦匹配项及其邻居。</p>
  </aside>
  <main class="stage">
    <nav class="stage-nav"><button data-view="graph" class="active">关系图</button><button data-view="warehouse">资料仓库</button><button data-view="arcs">剧情线</button><button data-view="collections">集合</button><button data-view="timeline">时间线</button><button data-view="romance">感情线</button><button data-view="intimacy">亲密行为</button><button data-view="foreshadowing">伏笔</button><button data-view="style">风格</button><button data-view="issues">待核问题</button></nav>
   <section id="graph" class="view active"><div id="graphVisibleCount" class="graph-visible-count" aria-live="polite"></div><div id="cy" role="img" aria-label="可点击小说知识关系图"></div><div class="graph-tools"><button id="fit" class="ghost">适应画布</button><button id="focus" class="ghost">聚焦选中</button><button id="clear" class="ghost">清除选择</button></div></section><div id="diag" style="display:none;position:fixed;right:14px;bottom:14px;z-index:99;background:#171a21;color:#e8ebf2;padding:10px 12px;border-radius:10px;font:11px/1.6 ui-monospace,monospace;white-space:pre;pointer-events:none;box-shadow:0 8px 28px rgba(0,0,0,.28)"></div>
   <section id="warehouse" class="view"><div class="list-view"><h2>故事资料仓库</h2><p>完整资料始终可浏览；章节控件只回放当前有效的身份、关系、技能、物品角色与等级占用。每页只渲染有限记录，切换详情后仍保留筛选与页码。</p><div class="warehouse-toolbar"><div id="warehouseTabs" class="warehouse-tabs"><button data-warehouse="characters" class="active">人物库</button><button data-warehouse="organizations">势力／家族</button><button data-warehouse="locations">地点库</button><button data-warehouse="skills">技能库</button><button data-warehouse="items">装备／物品库</button><button data-warehouse="levels">等级库</button></div><input id="warehouseSearch" type="search" placeholder="在当前仓库中搜索"><select id="warehouseSort" aria-label="仓库排序"><option value="first">按初见章节</option><option value="name">按名称</option><option value="latest">按最近变化</option></select><select id="warehouseFilter" aria-label="结果筛选"><option value="all">全部结果</option><option value="protagonist">主角相关</option><option value="active">当前有效</option><option value="changed">有变化记录</option><option value="issues">有待核问题</option></select><div class="warehouse-view-toggle" aria-label="仓库视图"><button data-warehouse-view="cards" class="active" aria-pressed="true">卡片</button><button data-warehouse-view="compact" aria-pressed="false">紧凑</button></div></div><div id="warehouseCount" class="hint" aria-live="polite"></div><div id="warehouseGrid"></div><div id="warehousePager" class="page-controls"></div></div></section>
    <section id="arcs" class="view"><div class="list-view"><h2>交叉剧情时间线</h2><p>大剧情、子剧情与并行剧情保留各自泳道；章节可以同时属于多条剧情。</p><div id="arcFeed" class="arc-lanes"></div></div></section>
    <section id="collections" class="view"><div class="list-view"><h2>人物／物品集合</h2><p>集合是可审计查询；交集和并集按稳定实体 ID 去重，多重归属用标签展示。</p><div class="collection-toolbar"><select id="collectionOperator" aria-label="集合组合方式"><option value="and">同时满足（AND／交集）</option><option value="or">满足任一（OR／并集）</option><option value="not">排除所选（NOT／差集）</option></select><button id="clearCollections" class="ghost">清除筛选</button><span id="collectionCount" class="hint" aria-live="polite"></span></div><div id="collectionFeed" class="collection-grid"></div><h3>唯一实体结果</h3><div id="collectionResults" class="warehouse-grid"></div><div id="collectionResultsPager" class="page-controls"></div></div></section>
   <section id="timeline" class="view"><div class="list-view"><h2>事件与状态变化</h2><p>按章节排列的获得、失去、转移、升级、受伤与恢复。</p><div id="timelineFeed" class="feed"></div></div></section>
   <section id="romance" class="view"><div class="list-view"><h2>感情线／后宫档案</h2><p>有原文可证的亲密动作或明确亲密提议即可入列；意外、救援、能力影响和受胁迫会单独标明，入列不等于自愿或确认恋爱。</p><div id="romanceFeed" class="feed"></div></div></section>
   <section id="intimacy" class="view"><div class="list-view"><h2>亲密行为记录</h2><p>逐次记录发生过的亲密或性行为，区分主动方、承受方与旁观者。「暴力强迫」与「非自愿／受迫」刻意分开：前者是暴力或无力反抗，后者是胁迫、施压或权力不对等。</p><div id="intimacyFeed" class="feed"></div></div></section>
   <section id="foreshadowing" class="view"><div class="list-view"><h2>伏笔生命周期</h2><p>把原文观察、解释、推进与回收分开记录。</p><div id="foreshadowFeed" class="feed"></div></div></section>
    <section id="style" class="view"><div class="list-view"><h2>风格分析</h2><p>区分全文行文、叙事、人物刻画、关键人物语言与行为风格；每条结论保留范围、证据、置信度与反例。</p><div id="styleFeed" class="style-grid"></div></div></section>
    <section id="issues" class="view"><div class="list-view"><h2>待核问题</h2><p>系统没有擅自补齐的歧义、弱证据和覆盖边界。</p><div id="issueFeed" class="feed"></div></div></section>
  </main>
  <aside class="detail"><div id="detailResize" class="detail-resize" role="separator" aria-orientation="vertical" aria-label="拖动调整档案栏宽度" tabindex="0"></div><div id="detail" class="detail-inner"></div></aside>
 </div>
</div>
<script>
const graph=__GRAPH_DATA__;
// Hot-path indexes are built once. Chapter scrubbing must not repeatedly scan the
// whole graph for every visible card and entity panel.
function normalizedItemRoles(raw){if(Array.isArray(raw))return raw.filter(x=>x&&typeof x==='object');if(!raw||typeof raw!=='object')return [];const out=[];for(const [itemId,value] of Object.entries(raw)){const entries=Array.isArray(value)?value:[value];for(const [index,entry] of entries.entries()){if(typeof entry==='string')out.push({id:`item_role:${itemId}:${index}`,item_id:itemId,entity_id:entry,role:'owner'});else if(entry&&typeof entry==='object')out.push({item_id:itemId,...entry})}}return out}
const normalizedItemRoleRows=normalizedItemRoles(graph.item_roles);
const relationsByEntity=new Map(),changesByEntity=new Map(),changesByTarget=new Map(),relationsByType=new Map(),itemRolesByItem=new Map();
for(const relation of (graph.relations||[])){
  for(const id of [relation.source_id,relation.target_id]){if(!relationsByEntity.has(id))relationsByEntity.set(id,[]);relationsByEntity.get(id).push(relation)}
  if(!relationsByType.has(relation.relation_type))relationsByType.set(relation.relation_type,[]);relationsByType.get(relation.relation_type).push(relation)
}
for(const change of (graph.state_changes||[])){if(!changesByEntity.has(change.entity_id))changesByEntity.set(change.entity_id,[]);changesByEntity.get(change.entity_id).push(change);if(change.target_id){if(!changesByTarget.has(change.target_id))changesByTarget.set(change.target_id,[]);changesByTarget.get(change.target_id).push(change)}}
for(const changes of changesByEntity.values())changes.sort((a,b)=>(a.chapter??0)-(b.chapter??0)||String(a.id||'').localeCompare(String(b.id||'')));
for(const role of normalizedItemRoleRows){if(!itemRolesByItem.has(role.item_id))itemRolesByItem.set(role.item_id,[]);itemRolesByItem.get(role.item_id).push(role)}
const scheduleFrame=globalThis.requestAnimationFrame||((callback)=>setTimeout(callback,0));
let chapterRenderFrame=0;
const byId=new Map((graph.entities||[]).map(x=>[x.id,x]));
const evidenceById=new Map((graph.evidence||[]).map(x=>[x.id,x]));
const eventById=new Map((graph.events||[]).map(x=>[x.id,x]));
const relationById=new Map((graph.relations||[]).map(x=>[x.id,x]));
const changeById=new Map((graph.state_changes||[]).map(x=>[x.id,x]));
const romanceById=new Map((graph.romance_routes||[]).map(x=>[x.id,x]));
const foreshadowById=new Map((graph.foreshadowing||[]).map(x=>[x.id,x]));
const arcById=new Map((graph.story_arcs||[]).map(x=>[x.id,x]));
const collectionById=new Map((graph._collection_views?.collections||[]).map(x=>[x.id,x]));
const vocabulary=graph._display_vocabulary||{};
const term=(group,key)=>vocabulary[group]?.[key]||vocabulary.fallback||'未分类';
function relationDisplayLabel(r){const exact=vocabulary.relations?.[r?.relation_type];if(exact)return exact;const type=String(r?.relation_type||'');if(/gift|gave|donat/.test(type))return '赠予／馈赠';if(/rescu|protect|save|heal/.test(type))return '保护／救助';if(/harm|hurt|attack|enemy|hunt|kill|rival/.test(type))return '伤害／敌对';if(/parent|child|sibling|family|spouse|marri|betroth/.test(type))return '家族／婚姻／婚约';if(/teacher|mentor|student|instruct|teach/.test(type))return '师徒／教导';if(/friend|ally|companion|partner/.test(type))return '朋友／盟友';if(/romance|love|dating|intimat|crush/.test(type))return '感情／亲密';if(/member|affiliat|sect|school|citizen|leader/.test(type))return '势力／组织归属';if(/own|hold|use|transfer|possess/.test(type))return '物品持有／转交';if(/identity|alter|avatar|disguis|same_body/.test(type))return '身份／秘密';if(/part_of|subgroup|located/.test(type))return '层级／地点子集';if(/shared|participat/.test(type))return '共同经历事件';return '其他关系（待补显示词）'}
const attrKey=key=>vocabulary.attribute_keys?.[key]||key;
// 枚举值 -> 中文标签：摊平词汇表，交给 reader_prose 替换散文里的英文机器键。
const ENUM_LABELS=(()=>{const m={};for(const g of Object.values(vocabulary)){if(g&&typeof g==='object'&&!Array.isArray(g))for(const [k,v] of Object.entries(g))if(typeof v==='string')m[k]=v}return m})();
const TRAIT_FACETS={"appearance": "外貌", "personality": "性格", "speech": "语言语气", "habit": "习惯动作"};
const TRAIT_ALIASES={"外貌": "appearance", "长相": "appearance", "外形": "appearance", "外观": "appearance", "体貌": "appearance", "外表": "appearance", "容貌": "appearance", "穿着": "appearance", "装扮": "appearance", "性格": "personality", "性情": "personality", "秉性": "personality", "个性": "personality", "语气": "speech", "语言": "speech", "说话": "speech", "口头禅": "speech", "言辞": "speech", "语言语气": "speech", "说话方式": "speech", "称谓": "speech", "称呼": "speech", "习惯": "habit", "习惯动作": "habit", "癖好": "habit", "小动作": "habit", "嗜好": "habit"};
const TRAIT_ORDER=["appearance", "personality", "speech", "habit"];
const PROSE_WITHHELD_HTML='<span class="summary-withheld">注记已略去：该条只含整理过程记录，没有读者可见的内容。</span>';
__READER_PROSE_JS__
const typeColors={character:'#675bd8',skill:'#25896a',martial_soul:'#d0517c',item:'#c17822',organization:'#4c77b7',location:'#3e8b9e',creature:'#79943e',title:'#9a5b37',concept:'#758097',level_axis:'#a8752b'};
const typeMeta=type=>[term('entity_types',type),typeColors[type]||'#758097'];
const agentInfo=id=>(graph._agents||{})[id];
const isAgent=e=>!!e&&(e.type==='character'||e.is_agent===true||(e.is_agent!==false&&!!agentInfo(e.id)));
const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
// A record reference is not always an entity. A review issue about six foreshadowings
// names the six foreshadowings, and a state change is named by whose facet it changed.
// Falling straight through to the raw ID printed `fs_f31_long_blood_tracking` in the
// panel -- an internal key reaching the reader. Resolve every record kind to something
// readable; the raw ID stays as the last resort, never the first.
function labelOfRecord(id){
  const entity=byId.get(id);if(entity)return visibleNameOf(entity);
  const clue=foreshadowById.get(id);
  if(clue)return clue.label||id;
  const event=eventById.get(id);
  if(event)return event.title||id;
  const change=changeById.get(id);
  if(change)return `${byId.get(change.entity_id)?.name||change.entity_id}·${term('facets',change.facet)}`;
  const relation=relationById.get(id);
  if(relation)return `${byId.get(relation.source_id)?.name||relation.source_id}–${byId.get(relation.target_id)?.name||relation.target_id}`;
  const arc=arcById.get(id);if(arc)return arc.title||id;
  const collection=collectionById.get(id);if(collection)return collection.label||id;
  return id;
}
const nameOf=id=>labelOfRecord(id);
// Resolving a *field* is not enough: prose is hand-written and refers to records by
// ID inside its own sentences -- "因此未把它与 location_huihuang_feichang 合并".
// 26 review-issue descriptions carried 46 bare `char_*` / `sc_*` tokens like that
// when this was written, and the panel printed them verbatim. Replace known IDs
// with their labels across every
// prose field. `quote` is deliberately NOT in the list: source text is verbatim
// evidence and must never be rewritten. An unknown token is left alone, so a
// genuinely dangling reference stays visible instead of being papered over.
// `rom_` / `rr_` 前缀与大写后缀都曾漏过：rom_A01、fs_A01、ri_E06 被原样印给读者。
// 前缀表与 reader_prose.ID_PREFIXES 保持一份定义。
const ID_TOKEN=/\b(?:char|concept|item|skill|location|org|creature|event|rel|sc|fs|ri|ev|axis|rom|rr|lcv|ia|level)_[A-Za-z0-9_]{2,}\b/g;
const scrubText=value=>typeof value!=='string'?value:value.replace(ID_TOKEN,token=>{const label=labelOfRecord(token);return label===token?token:label;});
const PROSE_FIELDS=['description','reason','observation','interpretation','summary','resolution','title','label','note'];
for(const key of ['entities','events','relations','state_changes','foreshadowing','review_issues','romance_routes']){
  for(const record of graph[key]||[]){
    if(!record||typeof record!=='object')continue;
    for(const field of PROSE_FIELDS){
      if(typeof record[field]==='string')record[field]=scrubText(record[field]);
    }
    if(record.attributes&&typeof record.attributes==='object'){
      for(const [attrName,attrText] of Object.entries(record.attributes)){
        if(typeof attrText==='string')record.attributes[attrName]=scrubText(attrText);
      }
    }
  }
}
const allTypes=[...new Set((graph.entities||[]).map(x=>x.type))];
const counts=Object.fromEntries(allTypes.map(t=>[t,(graph.entities||[]).filter(x=>x.type===t).length]));
let chapter=graph.metadata?.chapter_end||50,scope='core',layoutName='lanes',selectedId=null,activeTypes=new Set(allTypes),typeSelectionMode='multi',search='',warehouseKind='characters',warehouseSearch='',warehouseSort='first',warehouseFilter='all',warehouseView='cards',warehousePage=1,warehousePageSize=24,detailRoute={kind:'coverage',id:null,returnPersonId:null};
let collectionOperator='and',selectedCollections=new Set(),collectionMemberPage=1,collectionMemberPageSize=24;
const configuredProtagonists=arr(graph.metadata?.protagonist_ids||graph.metadata?.profile?.protagonist_ids);
const protagonistId=configuredProtagonists.find(id=>byId.has(id))
  ||(graph.romance_routes||[]).map(r=>r.protagonist_id).find(id=>byId.has(id))
  ||(graph.entities||[]).find(e=>arr(e.tags).includes('protagonist'))?.id
  ||null;

let activeView='graph';
document.querySelector('#title').textContent=graph.metadata?.title||'小说知识图谱';
document.querySelector('#subtitle').textContent=`第 ${graph.metadata?.chapter_start??1}–${graph.metadata?.chapter_end||chapter} 章 · 动态设定数据库`;
document.querySelector('#mCharacters').textContent=counts.character||0;
document.querySelector('#mAbilities').textContent=(counts.skill||0)+(counts.martial_soul||0);
document.querySelector('#abilityMetricLabel').textContent=[counts.skill?typeMeta('skill')[0]:'',counts.martial_soul?typeMeta('martial_soul')[0]:''].filter(Boolean).join(' / ')||'能力';
document.querySelector('#search').placeholder=`人物、物品、${typeMeta('skill')[0]}或别名`;
document.querySelector('#mChanges').textContent=(graph.state_changes||[]).length;
document.querySelector('#mEvidence').textContent=(graph.evidence||[]).length;
document.querySelector('#mVerified').textContent=graph._validation?.valid?'通过':'待检查';
document.querySelector('#chapter').min=graph.metadata?.chapter_start??1;document.querySelector('#chapter').max=graph.metadata?.chapter_end||chapter;document.querySelector('#chapter').value=chapter;document.querySelector('#chapterValue').textContent=chapter;
document.querySelector('#status').innerHTML=graph._validation?.valid?`已核对 <b>${graph._validation.source_audit?.evidence_audited||0}</b> 条原文证据，0 错误`:`验证报告未通过或未提供`;
document.querySelector('#types').innerHTML=allTypes.map(t=>{const [label,color]=typeMeta(t);return `<button class="type-button active" data-type="${esc(t)}" aria-pressed="true"><span class="select-mark" aria-hidden="true"></span><span class="swatch" style="background:${color}"></span>${esc(label)}<small>${counts[t]}</small></button>`}).join('');

function syncTypeControls(){const list=document.querySelector('#types');list.classList.toggle('single-mode',typeSelectionMode==='single');document.querySelectorAll('[data-type-mode]').forEach(b=>{const on=b.dataset.typeMode===typeSelectionMode;b.classList.toggle('active',on);b.setAttribute('aria-pressed',String(on))});document.querySelectorAll('[data-type]').forEach(b=>{const on=activeTypes.has(b.dataset.type);b.classList.toggle('active',on);b.setAttribute('aria-pressed',String(on))});document.querySelector('#typeAll').disabled=typeSelectionMode==='single';document.querySelector('#typeNone').disabled=typeSelectionMode==='single'}
syncTypeControls();

const shell=document.querySelector('.shell'),detailResize=document.querySelector('#detailResize');
function detailWidthLimit(){return Math.max(300,Math.min(760,window.innerWidth-(window.innerWidth<=1050?220:248)-330))}
function setDetailWidth(width,persist=true){if(window.innerWidth<=780)return;const next=Math.max(300,Math.min(detailWidthLimit(),Math.round(width)));shell.style.setProperty('--detail-width',`${next}px`);detailResize.setAttribute('aria-valuenow',String(next));if(persist)try{localStorage.setItem('novel-dashboard-detail-width',String(next))}catch{};setTimeout(()=>{cy.resize()},0)}
try{const saved=Number(localStorage.getItem('novel-dashboard-detail-width'));if(Number.isFinite(saved)&&saved>=300)setDetailWidth(saved,false)}catch{}
detailResize.addEventListener('pointerdown',event=>{if(window.innerWidth<=780)return;event.preventDefault();const startX=event.clientX,startWidth=document.querySelector('.detail').getBoundingClientRect().width;detailResize.setPointerCapture(event.pointerId);document.body.classList.add('detail-resizing');const move=e=>setDetailWidth(startWidth+startX-e.clientX);const stop=()=>{document.body.classList.remove('detail-resizing');detailResize.removeEventListener('pointermove',move);detailResize.removeEventListener('pointerup',stop);detailResize.removeEventListener('pointercancel',stop)};detailResize.addEventListener('pointermove',move);detailResize.addEventListener('pointerup',stop);detailResize.addEventListener('pointercancel',stop)});
detailResize.addEventListener('keydown',event=>{if(!['ArrowLeft','ArrowRight','Home'].includes(event.key))return;event.preventDefault();const current=document.querySelector('.detail').getBoundingClientRect().width;setDetailWidth(event.key==='Home'?370:current+(event.key==='ArrowLeft'?24:-24))});
function applyPixelRatio(){const d=dprValue();try{const r=cy.renderer&&cy.renderer();if(r)r.forcedPixelRatio=d}catch(e){}cy.resize()}let lastDpr=dprValue();window.addEventListener('resize',()=>{if(window.innerWidth>780)setDetailWidth(document.querySelector('.detail').getBoundingClientRect().width,false);const d=dprValue();if(Math.abs(d-lastDpr)>.01){lastDpr=d;applyPixelRatio()}});setTimeout(()=>{applyPixelRatio()},0);const diagBox=document.querySelector('#diag');function renderDiag(){if(!diagBox||diagBox.style.display==="none")return;const host=document.querySelector('#cy'),cv=host.querySelector('canvas');const bw=Math.round(host.clientWidth),bh=Math.round(host.clientHeight);const cw=cv?cv.width:0,ch=cv?cv.height:0;const dpr=window.devicePixelRatio||1;const eff=bw?(cw/bw):0;const ok=eff>=dpr-0.02;diagBox.textContent='devicePixelRatio  '+dpr.toFixed(2)+"\n"+'有效渲染倍率      '+eff.toFixed(2)+(ok?'  匹配':'  低于 DPR(会模糊)')+"\n"+'容器 CSS 尺寸     '+bw+' x '+bh+"\n"+'canvas 实际像素   '+cw+' x '+ch+"\n"+'当前缩放 zoom     '+cy.zoom().toFixed(2)+"\n"+'按 D 键关闭'}window.addEventListener('keydown',e=>{const t=e.target;if(t&&/^(INPUT|SELECT|TEXTAREA)$/.test(t.tagName))return;if(e.key==='d'||e.key==='D'){diagBox.style.display=diagBox.style.display==="none"?'block':'none';renderDiag()}});setTimeout(()=>{try{cy.on('render zoom pan resize',renderDiag)}catch(e){}setInterval(renderDiag,600)},0);

const degree=new Map((graph.entities||[]).map(x=>[x.id,0]));
for(const r of graph.relations||[]){degree.set(r.source_id,(degree.get(r.source_id)||0)+1);degree.set(r.target_id,(degree.get(r.target_id)||0)+1)}
const elements=[
 ...(graph.entities||[]).map(e=>({group:'nodes',data:{id:e.id,label:nameOf(e.id),type:e.type,first:e.first_chapter??1,last:e.last_chapter||chapter,degree:degree.get(e.id)||0}})),
 ...(graph.relations||[]).filter(r=>byId.has(r.source_id)&&byId.has(r.target_id)).map(r=>({group:'edges',data:{id:r.id,source:r.source_id,target:r.target_id,label:relationDisplayLabel(r),validFrom:r.valid_from??1,validTo:r.valid_to||99999,strength:Number.isFinite(Number(r.strength))?Number(r.strength):1}}))
];
function dprValue(){return Math.max(1,Math.min(3,window.devicePixelRatio||1))}
const cy=cytoscape({container:document.querySelector('#cy'),elements,boxSelectionEnabled:false,autounselectify:false,minZoom:.22,maxZoom:4,pixelRatio:dprValue(),motionBlur:false,textureOnViewport:false,hideEdgesOnViewport:false,style:[
 {selector:'node',style:{'background-color':e=>typeMeta(e.data('type'))[1],'width':e=>e.data('type')==='character'?34:25,'height':e=>e.data('type')==='character'?34:25,'label':'data(label)','font-family':'Inter, Segoe UI, Microsoft YaHei, sans-serif','font-size':12,'font-weight':500,'color':'#2b3040','text-background-color':'#ffffff','text-background-opacity':.9,'text-background-padding':3,'text-background-shape':'roundrectangle','text-margin-y':8,'text-valign':'bottom','border-width':2,'border-color':'#ffffff','overlay-opacity':0,'transition-property':'opacity, border-width, width, height','transition-duration':'140ms'}},
 {selector:'node[type="skill"]',style:{'shape':'round-rectangle'}},{selector:'node[type="item"]',style:{'shape':'diamond'}},{selector:'node[type="martial_soul"]',style:{'shape':'hexagon'}},{selector:'node[type="organization"]',style:{'shape':'rectangle'}},{selector:'node[type="location"]',style:{'shape':'tag'}},{selector:'node[type="creature"]',style:{'shape':'ellipse'}},
 {selector:'edge',style:{'width':e=>Math.max(1,Math.min(3,e.data('strength'))),'line-color':'#b9bfca','target-arrow-color':'#b9bfca','target-arrow-shape':'triangle','arrow-scale':.7,'curve-style':'bezier','opacity':.55,'label':'','overlay-opacity':0,'transition-property':'opacity, line-color, width','transition-duration':'140ms'}},
 {selector:'edge:selected',style:{'line-color':'#6157d8','target-arrow-color':'#6157d8','width':3,'opacity':1,'label':'data(label)','font-size':11,'color':'#5148bd','text-background-color':'#fff','text-background-opacity':1,'text-background-padding':3,'z-index':99}},
 {selector:'node:selected',style:{'border-color':'#262143','border-width':4,'width':42,'height':42,'z-index':99}},
 {selector:'.faded',style:{'opacity':.09,'text-opacity':0}},{selector:'.hidden',style:{'display':'none'}},{selector:'.spotlight',style:{'border-color':'#252039','border-width':4,'z-index':100}}
]});

function coreIds(base){
 const root=selectedId&&base.has(selectedId)?selectedId:(protagonistId&&base.has(protagonistId)?protagonistId:[...base].sort((a,b)=>(degree.get(b)||0)-(degree.get(a)||0))[0]),ids=new Set(root?[root]:[]);
 for(const r of graph.relations||[]){if(!activeRelation(r,base))continue;if(r.source_id===root)ids.add(r.target_id);else if(r.target_id===root)ids.add(r.source_id)}
 return ids;
}
function baseVisible(){return new Set((graph.entities||[]).filter(e=>entityVisibleAt(e)&&activeTypes.has(e.type)).map(e=>e.id))}
function filteredIds(){let ids=baseVisible();if(scope==='characters')ids=new Set([...ids].filter(id=>isAgent(byId.get(id))));if(scope==='core')ids=new Set([...coreIds(ids)].filter(id=>ids.has(id)));if(search){const q=search.toLowerCase(),hits=[...baseVisible()].filter(id=>{const e=byId.get(id);return [e.name,...visibleAliases(e)].join(' ').toLowerCase().includes(q)}),expanded=new Set(hits);for(const r of graph.relations||[])if(hits.includes(r.source_id))expanded.add(r.target_id);else if(hits.includes(r.target_id))expanded.add(r.source_id);ids=new Set([...expanded].filter(id=>baseVisible().has(id)))}if(ids.size>400)ids=new Set([...ids].sort((a,b)=>(a===protagonistId?-1:b===protagonistId?1:(degree.get(b)||0)-(degree.get(a)||0)||a.localeCompare(b))).slice(0,400));return ids}
function activeRelation(r,ids){return ids.has(r.source_id)&&ids.has(r.target_id)&&(r.valid_from??1)<=chapter&&(!r.valid_to||r.valid_to>=chapter)}
function relSpan(r){return `第 ${r.valid_from} 章起${r.valid_to?'，至第 '+r.valid_to+' 章':''}`}
function relSpanTight(r){return `第 ${r.valid_from} 章${r.valid_to?'—'+r.valid_to+'章':'起'}`}
function applyGraphFilters(relayout=true){const eligible=baseVisible().size,ids=filteredIds();let visibleEdges=0;const lanes=new Map();cy.batch(()=>{cy.nodes().forEach(n=>n.toggleClass('hidden',!ids.has(n.id())));cy.edges().forEach(e=>{const relation=relationById.get(e.id()),visible=activeRelation(relation,ids);e.toggleClass('hidden',!visible);if(visible){visibleEdges++;const lane=relationLane(relation);lanes.set(lane,(lanes.get(lane)||0)+1)}})});const laneText=[...lanes.entries()].sort((a,b)=>b[1]-a[1]).slice(0,6).map(([lane,count])=>`${relationLaneLabels[lane]||lane} ${count}`).join(' · '),counter=document.querySelector('#graphVisibleCount');if(counter)counter.textContent=`当前显示 ${ids.size}/${eligible} 个符合条件的实体，${visibleEdges}/${(graph.relations||[]).length} 条关系${laneText?' · 分区：'+laneText:''}${eligible>400&&scope!=='core'?' · 画布上限 400，请继续筛选':''}`;if(relayout)runLayout();refreshDetailForChapter()}

function levelShape(v){return typeof v==='object'&&v!==null&&!Array.isArray(v)&&Object.keys(v).every(k=>k==='value'||k==='label')&&('value' in v||'label' in v)}
function levelText(v){if(v===null||v===undefined||v==='')return '';if(typeof v==='number')return String(v);if(levelShape(v)){const label=v.label===null||v.label===undefined||v.label===''?'':String(v.label),num=v.value===null||v.value===undefined||v.value===''?'':String(v.value);if(label&&num&&label!==num)return `${label}（${num}）`;return label||num||''}return String(v)}
function attrText(v){if(v===null||v===undefined||v==='')return '无';if(typeof v==='boolean')return v?'是':'否';if(Array.isArray(v))return v.map(attrText).join('、');if(typeof v==='object'){const label=v.label!==undefined?v.label:v['名称'];if(label!==undefined&&label!==null&&label!==''){const range=v.range!==undefined?v.range:v['区间'];return Array.isArray(range)&&range.length===2?`${label}（${range[0]}—${range[1]}）`:String(label)}return Object.entries(v).map(([k,x])=>`${attrKey(k)}：${attrText(x)}`).join('；')}return String(v)}
function value(v){if(v===null||v===undefined||v==='')return '<span class="empty-value">无</span>';if(typeof v==='boolean')return v?'是':'否';if(levelShape(v)){const t=levelText(v);return t?asOf(t):'<span class="empty-value">无</span>'}if(typeof v==='object')return asOf(attrText(v));return asOf(v)}
function section(title,body){return body?`<section class="section"><h3>${esc(title)}</h3>${body}</section>`:''}
function romanceRoutesFor(id){return (graph.romance_routes||[]).filter(r=>r.protagonist_id===id||r.character_id===id)}
function routeOther(r,id){return r.protagonist_id===id?r.character_id:r.protagonist_id}
function isRomancePair(a,b){return (graph.romance_routes||[]).some(r=>(r.protagonist_id===a&&r.character_id===b)||(r.protagonist_id===b&&r.character_id===a))}
const romanceRelationTypes=new Set(['romantic_partner_of','spouse_of','dating','secret_lover_of','one_sided_crush_on','pursues','interested_in']);
function isRomanceRelation(r){return romanceRelationTypes.has(r.relation_type)&&isRomancePair(r.source_id,r.target_id)}
function levelAxes(e,allChanges){const axes=new Map();for(const x of allChanges.filter(c=>c.facet==='level'&&c.chapter<=chapter).sort((a,b)=>a.chapter-b.chapter)){const id=x.target_id||'facet:level';if(!axes.has(id))axes.set(id,{id,axis:nameOf(id),value:x.before,chapter:null});const rec=axes.get(id);rec.value=x.after;rec.chapter=x.chapter}return [...axes.values()]}
function levelStrip(e,allChanges){const axes=levelAxes(e,allChanges).filter(a=>a.value!==null&&a.value!==undefined&&a.value!=='');if(!axes.length)return '';return `<div class="level-strip">${axes.map(a=>`<div class="level-card" data-level-axis="${esc(a.id)}"><span class="level-axis">${esc(a.axis)}</span><b>${value(a.value)}</b><small>第 ${a.chapter} 章</small></div>`).join('')}</div>`}
function personFacetForChange(x){return x.facet==='relationship'&&x.target_id&&isRomancePair(x.entity_id,x.target_id)?'romance':x.facet}
function personFacets(e,allChanges,relations){
 const facets=new Map();
 const slot=(facet,key,label)=>{if(!facets.has(facet))facets.set(facet,new Map());const m=facets.get(facet);if(!m.has(key))m.set(key,{key,label,value:null,valueChapter:null,first:null,last:null,changes:[],relations:[]});const it=m.get(key);if(label)it.label=label;return it};
 const mark=(it,ch)=>{if(!ch)return;it.first=it.first===null?ch:Math.min(it.first,ch);it.last=it.last===null?ch:Math.max(it.last,ch)};
 for(const x of allChanges.slice().sort((a,b)=>a.chapter-b.chapter)){const facet=personFacetForChange(x),key=x.target_id||`facet:${facet}`,it=slot(facet,key,x.target_id?nameOf(x.target_id):term('facets',facet));it.changes.push(x);if(x.chapter<=chapter&&(!Number.isInteger(x.end_chapter)||chapter<=x.end_chapter)){it.value=x.after;it.valueChapter=x.chapter}mark(it,x.chapter)}
 for(const r of relations){const other=r.source_id===e.id?r.target_id:r.source_id,it=slot(relationFacet(r,e.id),other,nameOf(other));it.relations.push(r);mark(it,r.valid_from)}
 for(const [key,val] of Object.entries(e.attributes||{})){const label=attrKey(key),it=slot('attribute',`attribute:${label}`,label);const empty=v=>v===null||v===undefined||v==='';if(empty(it.value)||(!empty(val)&&String(val).length>String(it.value).length))it.value=val}
 return facets;
}
function namedEntry(it){return !it.key.startsWith('facet:')&&!it.key.startsWith('attribute:')}
function personEntryCard(it,personId){
 const entity=byId.get(it.key),kind=entity?typeMeta(entity.type)[0]:'';
 const changes=it.changes.slice().sort((a,b)=>b.chapter-a.chapter);
 const rels=it.relations.slice().sort((a,b)=>(b.valid_from??1)-(a.valid_from??1));
 const current=it.value!==null&&it.value!==undefined&&it.value!==''&&it.value!==false?value(it.value):'';
 const recordCount=changes.length+rels.length;
 // The individual lines already carry their own chapters, so a per-card summary line
 // only earns its space when there is more than one record to summarize.
 const meta=recordCount>1?[changes.length?`${changes.length} 次变化`:'',rels.length?`${rels.length} 条关系`:''].filter(Boolean).join(' · '):'';
 const lines=[
  ...rels.map(r=>`<div class="entry-line" data-relation="${esc(r.id)}" data-return-person="${esc(personId)}"><b>${esc(relationDisplayLabel(r))}</b><span>${relSpan(r)}</span></div>`),
  ...changes.map(x=>`<div class="entry-line" data-change="${esc(x.id)}" data-return-person="${esc(personId)}"><b>第 ${x.chapter} 章 · ${esc(term('actions',x.action))}</b><span class="change-values">${value(x.before)} → ${value(x.after)}</span></div>`),
 ].sort((a,b)=>{const ca=Number((a.match(/第 (\d+) 章/)||[])[1]||0),cb=Number((b.match(/第 (\d+) 章/)||[])[1]||0);return cb-ca});
 const reasonItems=changes.filter(x=>x.reason);
 const reasons=reasonItems.length?`<details class="entry-reasons"><summary>${reasonItems.length} 条变化原因</summary>${reasonItems.map(x=>`<p class="entry-reason">第 ${x.chapter} 章：${asOf(x.reason)}</p>`).join('')}</details>`:'';
 // The dot reuses the graph legend colour so a reader can map a card straight back to the node colour.
 const dot=entity?`<i class="entry-dot" style="background:${typeColors[entity.type]||'#b8beca'}"></i>`:'';
 return `<article class="entry"${entity?` data-entity="${esc(it.key)}"`:''}><h4 class="entry-name">${dot}${esc(it.label)}${kind?`<span class="entry-kind">${esc(kind)}</span>`:''}${current?`<span class="entry-badge">${current}</span>`:''}</h4>${meta?`<p class="entry-meta">${esc(meta)}</p>`:''}${lines.length?`<div class="entry-lines">${collapsibleHistory(lines)}</div>`:''}${reasons}</article>`;
}
function personTimeline(e,allChanges){const chapters=[...new Set(allChanges.map(x=>x.chapter))].sort((a,b)=>a-b),min=e.first_chapter??graph.metadata?.chapter_start??1,max=graph.metadata?.chapter_end||chapter,previous=[...chapters].reverse().find(x=>x<chapter),next=chapters.find(x=>x>chapter),span=Math.max(1,max-min);const dots=chapters.filter(x=>x>=min&&x<=max).map(x=>`<button class="time-dot${x<chapter?' past':''}${x===chapter?' current':''}" style="left:${((x-min)/span)*100}%" data-jump-chapter="${x}" aria-label="跳到第 ${x} 章变化"></button>`).join('');return `<div class="person-time"><div class="person-time-head"><b>${esc(nameOf(e.id))}的变化时间轴</b><span>第 ${chapter} 章</span></div><input id="personChapter" type="range" min="${min}" max="${max}" value="${chapter}" aria-label="${esc(nameOf(e.id))}的章节"><div class="time-dots">${dots}</div><div class="time-nav"><button id="previousChange"${previous===undefined?' disabled':''}>上次变化${previous===undefined?'':' · 第 '+previous+'章'}</button><button id="nextChange"${next===undefined?' disabled':''}>下次变化${next===undefined?'':' · 第 '+next+'章'}</button></div></div>`}
function relationFacet(r,personId){const other=r.source_id===personId?r.target_id:r.source_id,type=byId.get(other)?.type;if(isRomanceRelation(r))return 'romance';if(type==='item')return 'possession';if(type==='martial_soul')return 'martial_soul';if(type==='skill')return 'skill';if(type==='organization')return 'affiliation';if(type==='location')return 'location';if(r.relation_type==='knows_about')return 'knowledge';return 'relationship'}
function romanceStatusAt(r){return term('romance_statuses',r.status)}
function foreshadowStatusAt(f){return f.status}
function foreshadowDatedSteps(f){return progressionSteps(f).sort((a,b)=>(a.chapter||0)-(b.chapter||0))}
function romanceCard(r,personId){const other=routeOther(r,personId),confirmation=r.confirmed_chapter?`第 ${r.confirmed_chapter} 章`:'尚未确认';return `<div class="romance-card" data-romance="${esc(r.id)}" data-return-person="${esc(personId)}"><h3>${esc(nameOf(other))} · ${esc(romanceStatusAt(r))}</h3><p>${esc(term('romance_inclusion_bases',r.inclusion_basis))} · ${esc(term('consent_contexts',r.consent_context))}</p><p>首次相遇：${esc(firstMeetingText(r))} · 首次亲密／暧昧：第 ${r.ambiguity_started_chapter} 章</p><p>关系确认：${esc(confirmation)} · 首次明确性关系：${esc(firstSexText(r))}</p></div>`}
function facetSummaryText(facet,entries,routes=[]){const changes=entries.flatMap(x=>x.changes),rels=entries.flatMap(x=>x.relations),current=entries.filter(x=>x.value!==null&&x.value!==undefined&&x.value!==''&&x.value!==false),latest=changes.length?Math.max(...changes.map(x=>x.chapter)):null;if(facet==='relationship'){const active=rels.filter(visibleRelation).length,ended=rels.filter(r=>Number.isInteger(r.valid_to)&&r.valid_to<chapter).length;return `当前有效 ${active} 条 · 已结束 ${ended} 条`};if(facet==='romance'){const active=routes.filter(r=>r.status!=='ended').length,ended=routes.filter(r=>r.status==='ended').length;return `当前路线 ${active} 条 · 已结束 ${ended} 条`};if(facet==='level'){const labels=current.slice(0,2).map(x=>levelText(x.value)).filter(Boolean);return `${labels.length?'当前 '+labels.join('、'):'当前未记录'} · ${changes.length} 次变化${latest?' · 最近第 '+latest+'章':''}`};if(['skill','martial_soul','possession'].includes(facet))return `当前 ${current.length} 项 · 历史 ${changes.length+rels.length} 条${latest?' · 最近第 '+latest+'章':''}`;return `当前 ${current.length} 项 · 共 ${changes.length} 次变化${latest?' · 最近第 '+latest+'章':''}`}
function personCategories(e,allChanges,relations){
 const facets=personFacets(e,allChanges,relations),routes=romanceRoutesFor(e.id);
 if(routes.length&&!facets.has('romance'))facets.set('romance',new Map());
 const order=['identity','title','level','attribute','skill','martial_soul','possession','romance','relationship','knowledge','goal','health','location','affiliation','emotion'];
 const sorted=[...facets.keys()].sort((a,b)=>{const ai=order.indexOf(a),bi=order.indexOf(b);return (ai<0?99:ai)-(bi<0?99:bi)});
 return `<div class="category-list">${sorted.map(facet=>{
  const entries=[...facets.get(facet).values()];
  const items=entries.filter(namedEntry).sort((a,b)=>(a.first||0)-(b.first||0)||a.label.localeCompare(b.label,'zh-CN'));
  const scalars=entries.filter(x=>!namedEntry(x));
  const routeCards=facet==='romance'?routes.map(r=>romanceCard(r,e.id)).join(''):'';
  const scalarState=scalars.filter(x=>x.value!==null&&x.value!==undefined&&x.value!==false&&x.value!=='').map(x=>`<div class="state-line"><b>${esc(x.label)}</b><span>${value(x.value)}</span></div>`).join('');
  const scalarHistory=scalars.flatMap(x=>x.changes).sort((a,b)=>b.chapter-a.chapter).map(x=>`<div class="change-line" data-change="${esc(x.id)}" data-return-person="${esc(e.id)}"><b>第 ${x.chapter} 章 · ${esc(term('actions',x.action))}</b><p class="change-values">${value(x.before)} → ${value(x.after)}</p><p>${asOf(x.reason)}</p></div>`);
  const categoryEvidence=uniqueEvidence([...entries.flatMap(x=>recordEvidence([...x.changes,...x.relations])),...(facet==='romance'?recordEvidence(routes):[])]);
  const semanticSummary=facetSummaryText(facet,entries,facet==='romance'?routes:[]);
  const preview=items.length?`<span class="category-preview">${items.slice(0,6).map(x=>esc(x.label)).join('、')}${items.length>6?' 等':''}</span>`:'';
  const stateBlock=(scalarState||routeCards)?`<div class="category-subtitle category-scope current">截至第 ${chapter} 章的动态状态</div>${routeCards}${scalarState}`:'<div class="category-subtitle category-scope current">截至第 '+chapter+' 章的动态状态</div><div class="category-empty">此时点没有有效状态。</div>';
  const itemBlock=items.length?`<div class="category-subtitle">全范围具名条目</div><div class="entry-list">${items.map(x=>personEntryCard(x,e.id)).join('')}</div>`:'';
  const changeBlock=`<div class="category-subtitle category-scope">完整变化历史</div>${collapsibleHistory(scalarHistory)}`;
  const evidenceBlock=`<div class="category-subtitle category-scope">原文证据</div>${compactEvidenceHtml(categoryEvidence)}`;
  return `<details class="category"><summary><span class="category-title">${esc(term('facets',facet))}</span><small>${esc(semanticSummary)}</small>${preview}</summary><div class="category-body">${stateBlock}${itemBlock}${changeBlock}${evidenceBlock}</div></details>`;
 }).join('')}</div>`;
}
function backButton(returnPersonId){return returnPersonId&&isAgent(byId.get(returnPersonId))?`<button class="detail-back" data-back-person="${esc(returnPersonId)}">← 返回${esc(nameOf(returnPersonId))}的人物总览</button>`:''}
function setDetail(html,route){if(route)detailRoute=route;document.querySelector('#detail').innerHTML=html}
function showCoverage(){const v=graph._validation,open=(graph.review_issues||[]).filter(x=>!x.resolution).length;setDetail(`<div class="eyebrow">数据概览</div><h2>可回放的故事世界</h2><p class="summary">不是最终状态清单，而是带原因和原文依据的变化账本。</p><div class="coverage-grid"><div><b>${graph.metadata.chapter_start}–${graph.metadata.chapter_end}</b><span>章节覆盖</span></div><div><b>${(graph.entities||[]).length}</b><span>实体</span></div><div><b>${v?.source_audit?.evidence_audited||0}</b><span>证据核对</span></div><div><b>${open}</b><span>保留疑点</span></div></div>${section('使用方法','<p class="summary">先从核心图查看主角周边；再切换人物图或全部图。拖动章节会回到当时有效的状态与关系。</p>')}`,{kind:'coverage',id:null,returnPersonId:null})}
function asOf(text){if(typeof text!=='string')return text;const clean=cleanReaderProse(text,ENUM_LABELS);if(text.trim()&&!clean)return PROSE_WITHHELD_HTML;return esc(clean)}
// 记录级数组字段的统一兜底。顶层 graph.* 数组由 validate_graph.py 保证是数组，
// 但分片写坏一个记录级字段（例如把列表写成一段字符串）同样会让整页白屏——
// 而且症状是「什么都没有」，不是「某个区块报错」，很难回溯。这里只做最小防护：
// 不猜内容，只保证调用方拿到一个数组。
function arr(v){return Array.isArray(v)?v:[]}

// 伏笔的推进记录。分片偶尔把整段说明写成字符串而不是步骤数组；整页不该因此死掉，
// 内容也不该被丢掉——当成一条「日期未定」的步骤显示（校验器会把它报成错误，
// 修数据是数据的事）。
function progressionSteps(f){
  const raw=f?f.progression:null;
  if(Array.isArray(raw))return raw;
  if(typeof raw==='string'&&raw.trim())return [{kind:'observation',chapter:null,description:raw,evidence_ids:[]}];
  return [];
}
// Full-range dossiers are intentionally spoiler-visible. Chapter replay affects
// dynamic state and relation validity, not names, summaries, evidence, or history.
function entityVisibleAt(_e){return true}
function visibleNameOf(e){return e?.name||'未命名实体'}
function identityText(v){return v&&typeof v==='object'?v.name:v}
function visibleAliases(e){return arr(e.aliases).map(identityText).filter(Boolean)}
function nameAtChapter(e){const matches=arr(e?.name_history).filter(x=>Number.isInteger(x.valid_from)&&x.valid_from<=chapter&&(!Number.isInteger(x.valid_to)||chapter<=x.valid_to)).sort((a,b)=>a.valid_from-b.valid_from);return matches.at(-1)?.name||visibleNameOf(e)}
function summaryHtml(e){return e.summary?`<section class="section scope-full"><h3>全范围资料</h3><p class="summary">${asOf(e.summary)}</p></section>`:''}
function evidenceHtml(ids){return (ids||[]).map(id=>{const e=evidenceById.get(id);return e?`<div class="quote">“${esc(e.quote)}”<small>第 ${e.chapter} 章</small></div>`:''}).join('')}
function effectiveState(e){const state={};for(const x of (changesByEntity.get(e.id)||[])){if((x.chapter??0)>chapter)break;if(Number.isInteger(x.end_chapter)&&chapter>x.end_chapter)continue;const facet=term('facets',x.facet),key=x.target_id?`${facet} · ${nameOf(x.target_id)}`:facet;state[key]=x.after}if(chapter>=(graph.metadata?.chapter_end??chapter)){const current=e.current_state;if(typeof current==='string'){if(current&&!('当前状态' in state))state['当前状态']=current}else for(const [key,val] of Object.entries(current||{}))if(!(key in state))state[key]=val}return state}
function uniqueEvidence(ids){return [...new Set(arr(ids).filter(id=>evidenceById.has(id)))]}
function recordEvidence(records){return uniqueEvidence(records.flatMap(x=>arr(x.evidence_ids)))}
function compactEvidenceHtml(ids,limit=3){const records=uniqueEvidence(ids).map(id=>evidenceById.get(id)).filter(Boolean).sort((a,b)=>(a.chapter??0)-(b.chapter??0));if(!records.length)return '<p class="category-empty">暂无可追溯原文证据。</p>';const chapters=records.map(x=>x.chapter).filter(Number.isFinite),range=chapters.length?(Math.min(...chapters)===Math.max(...chapters)?`第 ${chapters[0]} 章`:`第 ${Math.min(...chapters)}—${Math.max(...chapters)} 章`):'章节未定';return `<p class="evidence-summary">${records.length} 条可追溯证据 · ${range}</p>${records.slice(0,limit).map(x=>`<div class="quote-preview"><b>第 ${x.chapter} 章</b><span title="${esc(x.quote)}">“${esc(x.quote)}”</span></div>`).join('')}${records.length>limit?`<details class="history-more"><summary>展开其余 ${records.length-limit} 条证据</summary>${records.slice(limit).map(x=>`<div class="quote-preview"><b>第 ${x.chapter} 章</b><span title="${esc(x.quote)}">“${esc(x.quote)}”</span></div>`).join('')}</details>`:''}`}
function collapsibleHistory(lines,limit=3){if(!lines.length)return '<p class="category-empty">暂无变化记录。</p>';return lines.slice(0,limit).join('')+(lines.length>limit?`<details class="history-more"><summary>展开其余 ${lines.length-limit} 条历史</summary>${lines.slice(limit).join('')}</details>`:'')}
const readerMemo={chapter:null,entities:new Map()};
function refreshReaderMemo(){if(readerMemo.chapter===chapter)return;readerMemo.chapter=chapter;readerMemo.entities.clear()}
function entityChanges(id){const rows=[...(changesByEntity.get(id)||[]),...(changesByTarget.get(id)||[])];return [...new Map(rows.map(x=>[x.id,x])).values()]}
function entityReaderStats(e){refreshReaderMemo();if(readerMemo.entities.has(e.id))return readerMemo.entities.get(e.id);const changes=isAgent(e)?(changesByEntity.get(e.id)||[]):entityChanges(e.id),rels=relationsByEntity.get(e.id)||[],state=effectiveState(e),activeRelations=rels.filter(visibleRelation),endedRelations=rels.filter(r=>Number.isInteger(r.valid_to)&&r.valid_to<chapter),evidenceIds=uniqueEvidence([...arr(e.evidence_ids),...recordEvidence(changes),...recordEvidence(rels)]),issues=(graph.review_issues||[]).filter(x=>!x.resolution&&arr(x.related_ids).includes(e.id)),pastChanges=changes.filter(x=>(x.chapter??0)<=chapter),latestChangeChapter=pastChanges.length?Math.max(...pastChanges.map(x=>x.chapter)):null;const priority=['等级','身份','称号','所在地点','地点','所属势力','身体状态'],entries=Object.entries(state).filter(([,v])=>v!==null&&v!==undefined&&v!==''&&v!==false),highlights=[];for(const wanted of priority){const hit=entries.find(([k])=>k===wanted||k.startsWith(wanted+' ·'));if(hit&&!highlights.some(x=>x[0]===hit[0]))highlights.push(hit);if(highlights.length===3)break}for(const row of entries)if(highlights.length<3&&!highlights.some(x=>x[0]===row[0]))highlights.push(row);const result={state,currentStateCount:entries.length,currentHighlights:highlights,activeRelations,activeRelationCount:activeRelations.length,endedRelationCount:endedRelations.length,changeCount:changes.length,latestChangeChapter,evidenceIds,evidenceCount:evidenceIds.length,issueCount:issues.length};readerMemo.entities.set(e.id,result);return result}
function entitySummaryCard(e){const s=entityReaderStats(e),metrics=[[s.currentStateCount,'当前状态'],[s.activeRelationCount,'当前有效关系'],[s.changeCount,'历史变化'],[s.evidenceCount,'可追溯证据'],[s.issueCount,'待核问题']];return `<section class="entity-summary-card"><div class="entity-summary-scope">截至第 ${chapter} 章的动态状态</div><div class="entity-summary-grid">${metrics.map(([n,label])=>`<div><b>${n}</b><span>${label}</span></div>`).join('')}</div>${s.currentHighlights.length?`<div class="entity-highlights">${s.currentHighlights.map(([k,v])=>`<span>${esc(k)}：${value(v)}</span>`).join('')}</div>`:'<p class="entity-latest">此时点没有可推导的动态状态。</p>'}${s.latestChangeChapter?`<div class="entity-latest">最近一次已发生变化：第 ${s.latestChangeChapter} 章</div>`:''}</section>`}
const relationLaneGroups=[
 ['family',new Set(['parent_of','child_of','sibling_of','spouse_of','betrothed_to','family_member_of'])],
 ['romance',new Set(['romantic_partner_of','love_interest_of','dating'])],
 ['mentor',new Set(['teacher_of','mentor_of','student_of','instructed'])],
 ['friend',new Set(['friend_of','close_friend_of','ally_of','companion_of','sworn_sibling_of'])],
 ['enemy',new Set(['enemy_of','rival_of','targets','hunts','attacked','harmed','hurt'])],
 ['affiliation',new Set(['member_of','sect_member_of','school_member_of','citizen_of','affiliated_with','leader_of'])],
 ['item',new Set(['owns','holds','uses','gifted_to','gave_to','transferred_to','gifted_item_to'])],
 ['identity',new Set(['alter_ego_of','same_body_as','avatar_of','disguised_as'])],
 ['hierarchy',new Set(['part_of','subgroup_of','located_in','located_at'])],
];
function relationLane(r){for(const [lane,types] of relationLaneGroups)if(types.has(r?.relation_type))return lane;return 'other'}
function arcPhaseLabel(phase){return phase?term('story_arc_phases',phase):'阶段未定'}
function lanePositions(ids){const root=selectedId&&ids.has(selectedId)?selectedId:(protagonistId&&ids.has(protagonistId)?protagonistId:[...ids][0]),positions={};if(root)positions[root]={x:0,y:0};const grouped=new Map();for(const r of graph.relations||[]){if(!activeRelation(r,ids)||!root)continue;const other=r.source_id===root?r.target_id:r.target_id===root?r.source_id:null;if(!other)continue;const lane=relationLane(r);if(!grouped.has(lane))grouped.set(lane,[]);grouped.get(lane).push(other)}const order=[...relationLaneGroups.map(x=>x[0]),'other'];let laneIndex=0;for(const lane of order){const members=[...new Set(grouped.get(lane)||[])].sort();if(!members.length)continue;const y=(laneIndex-(Math.max(1,grouped.size)-1)/2)*150;members.forEach((id,index)=>positions[id]={x:220+(index%5)*145,y:y+Math.floor(index/5)*70});laneIndex++}const remaining=[...ids].filter(id=>!positions[id]);remaining.forEach((id,index)=>positions[id]={x:-220-(index%4)*130,y:(index%8-4)*85});return positions}
function runLayout(){const visible=cy.elements(':visible');if(!visible.length)return;let options;if(layoutName==='lanes'){const ids=new Set(visible.nodes().map(n=>n.id())),positions=lanePositions(ids);options={name:'preset',fit:true,padding:48,positions:n=>positions[n.id()]||{x:0,y:0}}}else if(layoutName==='concentric'){options={name:'concentric',animate:false,fit:true,padding:48,minNodeSpacing:52,levelWidth:()=>2,concentric:n=>n.data('degree')}}else{options={name:'breadthfirst',animate:false,fit:true,padding:48,spacingFactor:1.25,directed:true,roots:(selectedId||protagonistId)?`#${selectedId||protagonistId}`:undefined}}visible.layout(options).run()}
function axisHolders(axisId){const byEntity=new Map();for(const x of (graph.state_changes||[]).filter(c=>c.facet==='level'&&c.target_id===axisId).sort((a,b)=>a.chapter-b.chapter)){const rec=byEntity.get(x.entity_id)||{id:x.entity_id,name:nameOf(x.entity_id),value:x.before,chapter:null};if(x.chapter<=chapter){rec.value=x.after;rec.chapter=x.chapter}byEntity.set(x.entity_id,rec)}return [...byEntity.values()].filter(h=>h.chapter!==null&&h.value!==null&&h.value!==undefined&&h.value!=='')}
// ---------------------------------------------------------------------------
// 等级库：把各体系的档位阶梯排出来，并按原文陈述做跨体系换算。
//
// 三条纪律：
// ① 档位只能来自数据。优先 attributes.档位（带区间或位次），其次用 下限~上限 生成
//    步进，都没有时退回「原文实际出现过的档位」。绝不根据 分级依据 的散文去猜档位名。
// ② 换算分两层。原文陈述的（有证据、可回溯）与经共同轴一跳推算的。推算必须显式标
//    注——否则读者会把推算当成原书的说法。
// ③ 一切受 chapter 门控，散文段落走 asOf。
// ---------------------------------------------------------------------------

// 把等级端点或等级值归一成一个数字；取不到数字返回 null（命名档位就是这种）。
function levelNum(v){
  if(typeof v==='number')return v;
  if(levelShape(v)){const n=v.value;return typeof n==='number'?n:null}
  if(typeof v==='string'&&v.trim()!==''&&!isNaN(Number(v)))return Number(v);
  return null;
}

// 换算端点 -> 可用区间。点位是 [v,v]，档位是 [lo,hi]，只有文字则是 null。
function convSpan(ep){
  if(!ep||typeof ep!=='object')return null;
  const r=ep.range;
  if(Array.isArray(r)&&r.length===2&&typeof r[0]==='number'&&typeof r[1]==='number')return [r[0],r[1]];
  const n=levelNum(ep.value);
  return n===null?null:[n,n];
}

function convSpansOverlap(a,b){
  if(!a||!b)return false;
  return a[0]<=b[1]&&b[0]<=a[1];
}

// 该轴在原文里实际出现过的档位（按首次出现章排序）。这是 档位/上下限 都缺失时的兜底，
// 数据来源是 level 状态变化本身，因此天然是「原文说过」的。
function observedRungs(axisId){
  const seen=new Map();
  for(const x of (graph.state_changes||[]).filter(c=>c.facet==='level'&&c.target_id===axisId).sort((a,b)=>a.chapter-b.chapter)){
    for(const v of [x.before,x.after]){
      const text=levelText(v);
      if(!text)continue;
      if(!seen.has(text))seen.set(text,{label:text,value:levelNum(v),chapter:x.chapter});
    }
  }
  return [...seen.values()].sort((a,b)=>(a.value===null?Infinity:a.value)-(b.value===null?Infinity:b.value)||a.chapter-b.chapter);
}

// 档位阶梯。返回 [{label,lo,hi,ord,attested,holders}]
function axisRungs(axis){
  const a=axis.attributes||{};
  const out=[];
  const tiers=a['档位']!==undefined?a['档位']:a['tiers'];
  if(Array.isArray(tiers)&&tiers.length){
    for(const t of tiers){
      if(!t||typeof t!=='object')continue;
      const name=t['名称']!==undefined?t['名称']:(t['label']!==undefined?t['label']:t['name']);
      if(name===undefined||name===null||String(name).trim()==='')continue;
      const rng=t['区间']!==undefined?t['区间']:t['range'];
      const ord=t['位次']!==undefined?t['位次']:t['order'];
      if(Array.isArray(rng)&&rng.length===2)out.push({label:String(name),lo:rng[0],hi:rng[1],ord:null});
      else out.push({label:String(name),lo:null,hi:null,ord:typeof ord==='number'?ord:out.length+1});
    }
  }else{
    const lo=Number(a['下限']),hi=Number(a['上限']);
    if(Number.isFinite(lo)&&Number.isFinite(hi)&&hi>=lo&&hi-lo<=60){
      const unit=String(a['单位']||'').trim();
      for(let v=lo;v<=hi;v++)out.push({label:unit?v+' '+unit:String(v),lo:v,hi:v,ord:null});
    }
  }
  if(!out.length){
    for(const r of observedRungs(axis.id))out.push({label:r.label,lo:r.value,hi:r.value,ord:null});
  }
  // 标注该档位在当前快照下有没有人：点位落在区间内，或档位名与记录文字一致。
  const holders=axisHolders(axis.id);
  for(const rung of out){
    const span=(rung.lo===null&&rung.hi===null)?null:[rung.lo,rung.hi];
    rung.holders=holders.filter(h=>{
      const hs=convSpan({value:levelNum(h.value)});
      if(span&&hs&&convSpansOverlap(span,hs))return true;
      return levelText(h.value)===rung.label;
    });
    rung.attested=rung.holders.length>0;
  }
  return out;
}

// 当前快照下可见的换算记录。
function visibleConversions(){
  return (graph.level_conversions||[]).filter(r=>r&&typeof r==='object'&&typeof r.chapter==='number'&&r.chapter<=chapter);
}

function axisName(id){const e=(graph.entities||[]).find(x=>x.id===id);return e?e.name:String(id||'')}

function convEndpointHtml(ep){
  const span=convSpan(ep);
  const label=ep&&ep.label!==undefined&&ep.label!==null&&String(ep.label).trim()!==''?String(ep.label):'';
  const num=levelNum(ep?ep.value:null);
  const range=ep&&Array.isArray(ep.range)&&ep.range.length===2?ep.range:null;
  let shown=label;
  if(!shown)shown=range?(range[0]+'—'+range[1]):(num===null?'':String(num));
  else if(range)shown=shown+'（'+range[0]+'—'+range[1]+'）';
  else if(num!==null&&String(num)!==label)shown=shown+'（'+num+'）';
  return '<div class="conv-side"><em>'+esc(axisName(ep?ep.axis_id:''))+'</em><b>'+asOf(shown||'未指明')+'</b></div>';
}

function convRelationLabel(rel){return term('level_conversion_relations',rel)}

// 判定一条换算的某一端是否命中「该轴上的这个档位」。
// 优先用数值区间相交；一边没有数字时退回文字相等。
function convSideMatches(ep,rungLabel,num){
  if(!ep||typeof ep!=='object')return false;
  const span=convSpan(ep);
  if(num!==null&&span)return num>=span[0]&&num<=span[1];
  return ep.label!==undefined&&ep.label!==null&&String(ep.label)===String(rungLabel);
}

// 换算：返回 {direct:[], derived:[]}
// direct  = 原文直接陈述的换算
// derived = 经一条直接换算落到中间轴，再从中间轴落到第三个体系的推算结果
function levelConvert(axisId,label,num){
  const out={direct:[],derived:[]};
  const seenDerived=new Set();
  for(const rec of visibleConversions()){
    for(const [near,far] of [['from','to'],['to','from']]){
      const a=rec[near],b=rec[far];
      if(!a||a.axis_id!==axisId)continue;
      if(!convSideMatches(a,label,num))continue;
      out.direct.push({rec,other:b,relation:rec.relation,side:near});
      // 中转到第三个体系：中间端只要有位置就能继续——点位是退化区间，
      // 档位是真区间，用同一套判交叠的逻辑，而不是只认数字。
      const bSpan=convSpan(b);
      if(!bSpan)continue;
      for(const rec2 of visibleConversions()){
        if(rec2.id===rec.id)continue;
        for(const [n2,f2] of [['from','to'],['to','from']]){
          const c=rec2[n2],d=rec2[f2];
          if(!c||c.axis_id!==b.axis_id)continue;
          const cSpan=convSpan(c)||(c.label!==undefined&&c.label!==null?convSpan({value:levelNum(c.label)}):null);
          if(!cSpan||!convSpansOverlap(cSpan,bSpan))continue;
          if(d.axis_id===axisId)continue;
          const key=d.axis_id+'|'+(d.label!==undefined&&d.label!==null?d.label:'');
          if(seenDerived.has(key))continue;
          seenDerived.add(key);
          out.derived.push({via:b,other:d,relation1:rec.relation,relation2:rec2.relation,chapter1:rec.chapter,chapter2:rec2.chapter});
        }
      }
    }
  }
  return out;
}

function levelWarehouseHtml(axes){
  if(!axes.length)return '<div class="empty">截至第 '+chapter+' 章还没有等级体系记录</div>';
  const convs=visibleConversions();
  return axes.map(axis=>{
    const rungs=axisRungs(axis);
    const holders=axisHolders(axis.id),occupied=rungs.filter(r=>r.attested).length,changes=(changesByTarget.get(axis.id)||[]).filter(x=>x.facet==='level').length;
    const ladder=rungs.length?('<div class="level-ladder">'+rungs.map(r=>{
      const rangeText=(r.lo===null&&r.hi===null)?(r.ord===null?'':'第 '+r.ord+' 位'):(r.lo===r.hi?String(r.lo):r.lo+'—'+r.hi);
      const rungHolders=r.holders.map(h=>esc(h.name)+(h.chapter===null?'':'（第 '+h.chapter+' 章）')).join('、');
      return '<div class="level-rung'+(r.attested?' attested':'')+'"><b>'+esc(r.label)+'</b>'
        +'<span class="rung-range">'+esc(rangeText)+'</span>'
        +'<span class="rung-holders">'+(rungHolders||'截至第 '+chapter+' 章无人')+'</span></div>'
    }).join('')+'</div>'):'<p class="level-axis-note">该体系未附档位表，原文也没有出现具体档位记录。</p>';
    const own=convs.filter(c=>c.from&&c.to&&(c.from.axis_id===axis.id||c.to.axis_id===axis.id));
    return '<section class="level-axis"><div class="level-axis-head"><h3>'+esc(axis.name)+'</h3>'
      +'<span>'+esc(term('entity_types','level_axis'))+'</span>'
      +'<span>第 '+esc(axis.first_chapter===undefined?1:axis.first_chapter)+' 章起</span>'
      +'<span>当前占用 '+occupied+' 档／'+holders.length+' 人</span>'
      +'<span>历史变化 '+changes+' 次</span>'
      +'<span>换算 '+own.length+' 条</span></div>'
      +(axis.summary?'<p class="level-axis-note">'+asOf(axis.summary)+'</p>':'')
      +ladder+'</section>'
  }).join('')+levelConverterHtml(axes);
}

function levelConverterHtml(axes){
  const options=axes.map(a=>'<option value="'+esc(a.id)+'">'+esc(a.name)+'</option>').join('');
  const rows=visibleConversions().map(rec=>{
    const why=rec.description?'<div class="conv-why">'+asOf(rec.description)+'（第 '+rec.chapter+' 章）</div>':'';
    return '<div class="conv-row">'
      +convEndpointHtml(rec['from'])
      +'<span class="conv-rel">'+esc(convRelationLabel(rec.relation))+'</span>'
      +convEndpointHtml(rec['to'])
      +why+'</div>';
  }).join('');
  return '<section class="level-axis"><div class="level-axis-head"><h3>体系换算</h3>'
    +'<span>原文陈述 '+visibleConversions().length+' 条</span></div>'
    +'<p class="level-axis-note">选一个体系和一个档位，列出原文把其它体系对应到哪一档。'
    +'没有直接对应的会用一个中间轴推算一次——推算项是虚线框并标注「推算」，'
    +'它是本页算出来的，不是原书的说法。</p>'
    +'<div class="conv-tools"><select id="levelConvAxis">'+options+'</select>'
    +'<select id="levelConvValue"></select></div><div class="conv-out" id="levelConvOut"></div>'
    +'<h4 class="level-axis-note">原文陈述的换算</h4>'
    +'<div class="conv-list">'+(rows||'<div class="empty">截至第 '+chapter+' 章原文还没有把两个体系对上号</div>')+'</div></section>';
}

function fillLevelConverterValues(){
  const axisSel=document.querySelector('#levelConvAxis'),valSel=document.querySelector('#levelConvValue');
  if(!axisSel||!valSel)return;
  const axis=(graph.entities||[]).find(e=>e.id===axisSel.value);
  if(!axis)return;
  const rungs=axisRungs(axis);
  const known=rungs.slice();
  for(const h of axisHolders(axis.id)){
    const text=levelText(h.value);
    if(text&&!known.some(k=>k.label===text))known.push({label:text,lo:levelNum(h.value),hi:levelNum(h.value)});
  }
  valSel.innerHTML=known.length?known.map(r=>{
    const n=r.lo!==null&&r.lo!==undefined?r.lo:(r.hi!==null&&r.hi!==undefined?r.hi:'');
    return '<option value="'+esc(r.label)+'" data-num="'+esc(n)+'">'+esc(r.label)+'</option>';
  }).join(''):'<option value="">（该体系暂无档位）</option>';
  runLevelConvert();
}

function runLevelConvert(){
  const axisSel=document.querySelector('#levelConvAxis'),valSel=document.querySelector('#levelConvValue'),out=document.querySelector('#levelConvOut');
  if(!axisSel||!valSel||!out)return;
  const label=valSel.value;
  const opt=valSel.options[valSel.selectedIndex];
  const raw=opt&&opt.dataset?opt.dataset.num:'';
  const num=(raw===''||raw===undefined||raw===null)?levelNum(label):Number(raw);
  if(!label){out.innerHTML='';return}
  const res=levelConvert(axisSel.value,label,isNaN(num)?null:num);
  const head='<div class="conv-why">「'+esc(axisName(axisSel.value))+' · '+esc(label)+'」的对应</div>';
  const direct=res.direct.map(d=>'<div class="conv-row">'
    +convEndpointHtml({axis_id:axisSel.value,label:label})
    +'<span class="conv-rel">'+esc(convRelationLabel(d.relation))+'</span>'
    +convEndpointHtml(d.other)
    +'<div class="conv-why">原文第 '+d.rec.chapter+' 章陈述'
    +(d.side==='to'?'（原文以另一端为出发点，此处按等价关系反向读取）':'')
    +'</div></div>').join('');
  const derived=res.derived.map(d=>'<div class="conv-row conv-derived">'
    +convEndpointHtml({axis_id:axisSel.value,label:label})
    +'<span class="conv-rel">推算</span>'
    +convEndpointHtml(d.other)
    +'<div class="conv-why">推算：经「'+esc(axisName(d.via.axis_id))+' · '+esc(levelText(d.via.value))+'」中转'
    +'（第 '+d.chapter1+' 章、第 '+d.chapter2+' 章的陈述）。本页算出，非原文说法。</div></div>').join('');
  out.innerHTML=head+direct+derived+((!res.direct.length&&!res.derived.length)?'<div class="empty">原文没有把这个体系与其它体系对上号</div>':'');
}

function wireLevelConverter(){
  const axisSel=document.querySelector('#levelConvAxis');
  if(!axisSel)return;
  axisSel.onchange=fillLevelConverterValues;
  const valSel=document.querySelector('#levelConvValue');
  if(valSel)valSel.onchange=runLevelConvert;
  fillLevelConverterValues();
}

function axisPanel(e){if(e.type!=='level_axis')return '';const attrs=Object.entries(e.attributes||{}),rows=attrs.map(([k,v])=>`<div class="row"><b>${esc(attrKey(k))}</b><span>${asOf(attrText(v))}</span></div>`).join('');const holders=axisHolders(e.id);const list=holders.length?holders.map(h=>`<div class="history-item" data-entity="${esc(h.id)}"><b>${esc(h.name)}</b><p>${value(h.value)} · 第 ${h.chapter} 章</p></div>`).join(''):'<p class="summary">截至第 '+chapter+' 章尚无角色在该体系上有等级记录。</p>';return section('全范围分级说明',rows||'<p class="summary">该等级体系未附分级说明。</p>')+section('截至第 '+chapter+' 章的等级归属',list)}
const relationLaneLabels={family:'家族／亲属',romance:'感情／亲密',mentor:'师徒／教导',friend:'朋友／盟友',enemy:'敌对／伤害',affiliation:'势力／门派／学院／国家',item:'物品持有／转交',identity:'身份／分身／伪装',hierarchy:'层级／子集',other:'其他关系'};
function categoryEntries(e){return arr(e.categories).map(raw=>typeof raw==='string'?{id:raw,primary:false}:raw).filter(x=>x&&x.id)}
function categoryPanel(e){const cats=categoryEntries(e);if(!cats.length)return e.type==='item'?section('物品分类','<p class="category-empty">待分类：没有证据支持具体类别。</p>'):'';const ordered=cats.slice().sort((a,b)=>(b.primary===true)-(a.primary===true)||String(a.id).localeCompare(String(b.id)));return section(e.type==='item'?'物品分类':'类别归属',`<div class="chips">${ordered.map(c=>`<span class="chip">${c.primary?'主分类 · ':''}${esc(term('item_categories',c.id)||c.id)}${c.confidence?` · ${esc(term('confidences',c.confidence))}`:''}</span>`).join('')}</div>${compactEvidenceHtml(ordered.flatMap(c=>arr(c.evidence_ids)))}`)}
function collectionPanel(e){const membership=graph._collection_views?.memberships?.[e.id],ids=membership?.collection_ids||[];if(!ids.length)return '';return section('集合归属（派生视图）',`<div class="chips">${ids.slice(0,3).map(id=>`<span class="chip">${esc(collectionById.get(id)?.label||id)}</span>`).join('')}${ids.length>3?`<span class="chip">+${ids.length-3} 个归属</span>`:''}</div><details class="history-more"><summary>查看全部归属与匹配依据</summary>${ids.map(id=>`<div class="history-item"><b>${esc(collectionById.get(id)?.label||id)}</b><p>${esc(arr(membership.membership_reasons?.[id]).map(x=>x.operator).join(' ∩ ')||'派生查询')}</p></div>`).join('')}</details>`)}
function storyArcPanel(e){const arcs=(graph.story_arcs||[]).filter(a=>arr(a.entity_ids).includes(e.id)).sort((a,b)=>(a.chapter_start??0)-(b.chapter_start??0)||String(a.id).localeCompare(String(b.id)));if(!arcs.length)return '';return section('所属剧情（允许多重／交叉）',collapsibleHistory(arcs.map(a=>`<div class="history-item"><b>${esc(a.title)}</b><p>第 ${a.chapter_start} 章—${a.chapter_end??'未完'} · ${esc(term('story_arc_statuses',a.status))} · ${esc(arcPhaseLabel(a.phase))}${a.parent_arc_id?' · 子剧情于 '+esc(nameOf(a.parent_arc_id)):''}</p></div>`)))}
function hierarchyAncestors(id){const out=[],membershipTargets=(relationsByEntity.get(id)||[]).filter(r=>visibleRelation(r)&&r.source_id===id&&['family','affiliation'].includes(relationLane(r))).map(r=>r.target_id),seen=new Set([id,...membershipTargets]),queue=[id,...membershipTargets];while(queue.length){const child=queue.shift();for(const r of graph.relations||[]){if(!visibleRelation(r)||r.source_id!==child||relationLane(r)!=='hierarchy'||seen.has(r.target_id))continue;seen.add(r.target_id);out.push({id:r.target_id,relation:r});queue.push(r.target_id)}}return out}
function affiliationPanel(e){const relevant=(relationsByEntity.get(e.id)||[]).filter(r=>['family','affiliation','identity','hierarchy'].includes(relationLane(r))).sort((a,b)=>(a.valid_from??0)-(b.valid_from??0)||String(a.id).localeCompare(String(b.id)));if(!relevant.length)return '';const line=r=>{const other=r.source_id===e.id?r.target_id:r.source_id;return `<div class="history-item" data-relation="${esc(r.id)}"><b>${esc(relationLaneLabels[relationLane(r)])} · ${esc(relationDisplayLabel(r))} · ${esc(nameOf(other))}</b><p>${relSpanTight(r)} · ${visibleRelation(r)?'当前有效':'历史'}</p></div>`};const current=relevant.filter(visibleRelation),history=relevant.filter(r=>!visibleRelation(r)),directIds=new Set(current.map(r=>otherEntity(r,e.id))),ancestors=hierarchyAncestors(e.id).filter(x=>!directIds.has(x.id));return section('归属、家族与身份体系',`<div class="category-subtitle">当前有效</div>${current.map(line).join('')||'<p class="category-empty">无当前有效归属。</p>'}${ancestors.length?`<div class="category-subtitle">继承的上级集合</div>${ancestors.map(x=>`<div class="history-item"><b>${esc(nameOf(x.id))}</b><p>经 ${esc(relationDisplayLabel(x.relation))} 继承；非直接成员关系</p></div>`).join('')}`:''}<div class="category-subtitle">历史</div>${collapsibleHistory(history.map(line))}`)}
function traitFacet(v){const s=String(v==null?'':v).trim();return Object.prototype.hasOwnProperty.call(TRAIT_FACETS,s)?s:(TRAIT_ALIASES[s]||s)}
function traitPanel(e){
  const all=(graph.character_traits||[]).filter(t=>t.entity_id===e.id);
  if(!all.length)return '';
  const byFacet={};
  for(const t of all){const f=traitFacet(t.facet);(byFacet[f]=byFacet[f]||[]).push(t)}
  const rows=[];
  for(const f of TRAIT_ORDER){
    const list=(byFacet[f]||[]).slice().sort((a,b)=>(a.chapter??0)-(b.chapter??0));
    if(!list.length)continue;
    const active=list.filter(x=>(x.chapter??1)<=chapter),cur=active[active.length-1];
    const history=list.map(x=>`第 ${x.chapter} 章 ${asOf(x.statement)}`).join('；');
    rows.push(`<div class="history-item"><b>${esc(TRAIT_FACETS[f]||f)} · 截至第 ${chapter} 章</b><p>${cur?asOf(cur.statement):'尚无有效断言'}</p><p class="trait-history">完整变化历史：${history}</p></div>`);
  }
  return rows.length?section('人物特征',rows.join('')):'';
}
function showEntity(id){const e=byId.get(id);if(!e)return;selectedId=id;const allChanges=isAgent(e)?(changesByEntity.get(id)||[]):entityChanges(id),rels=relationsByEntity.get(id)||[],aliases=visibleAliases(e),route={kind:'entity',id,returnPersonId:null},why=e.type==='character'?[]:(agentInfo(e.id)?.reasons||[]),stats=entityReaderStats(e),identityMeta=[...arr(e.historical_names).map(x=>'旧名 · '+x),...arr(e.titles).map(x=>'称号 · '+x),...arr(e.name_history).map(x=>`${x.kind==='title'?'称号':x.kind==='alias'?'别名':'历史称呼'} · ${x.name} · 第 ${x.valid_from??'?'}—${x.valid_to??'现在'}章`)],historicalName=nameAtChapter(e);const identityChips=[...(historicalName!==e.name?[`截至第 ${chapter} 章称呼 · ${historicalName}`]:[]),...aliases.map(x=>'别名 · '+x),...identityMeta];const shared=`${summaryHtml(e)}${identityChips.length?`<div class="chips">${[...new Set(identityChips)].map(x=>`<span class="chip">${esc(x)}</span>`).join('')}</div>`:''}${categoryPanel(e)}${affiliationPanel(e)}${storyArcPanel(e)}${collectionPanel(e)}`;if(isAgent(e)){setDetail(`<div class="eyebrow">${esc(typeMeta(e.type)[0])}${e.type==='character'?'':'（拟人主体）'}</div><h2>${esc(e.name||nameOf(id))}</h2>${why.length?`<p class="agent-why">按拟人主体处理：${why.map(esc).join('；')}</p>`:''}${entitySummaryCard(e)}${shared}${personTimeline(e,allChanges)}${personCategories(e,allChanges,rels)}${traitPanel(e)}${section(e.type==='character'?'全范围人物证据':'全范围实体证据',compactEvidenceHtml(stats.evidenceIds))}`,route)}else{const state=stats.state,changes=allChanges.slice().sort((a,b)=>b.chapter-a.chapter),activeRels=stats.activeRelations,historyLines=changes.map(x=>`<div class="history-item" data-change="${esc(x.id)}"><b>第 ${x.chapter} 章 · ${esc(term('facets',x.facet))} / ${esc(term('actions',x.action))}</b><p>${asOf(x.reason)}</p></div>`);setDetail(`<div class="eyebrow">${esc(typeMeta(e.type)[0])}</div><h2>${esc(e.name||nameOf(id))}</h2>${entitySummaryCard(e)}${shared}${section(`截至第 ${chapter} 章的动态状态`,Object.entries(state).map(([k,v])=>`<div class="row"><b>${esc(k)}</b><span>${value(v)}</span></div>`).join('')||'<p class="summary">此时点没有可推导的动态状态。</p>')}${traitPanel(e)}${section('当前有效关系',activeRels.map(r=>{const other=r.source_id===id?r.target_id:r.source_id;return `<div class="history-item" data-relation="${esc(r.id)}"><b>${esc(relationDisplayLabel(r))} · ${esc(nameOf(other))}</b><p>${relSpan(r)}</p></div>`}).join('')||'<p class="summary">截至本章没有有效关系。</p>')}${section('完整变化历史',collapsibleHistory(historyLines))}${axisPanel(e)}${section('全范围实体证据',compactEvidenceHtml(stats.evidenceIds))}`,route)}bindDetailClicks()}
function showRelation(id,returnPersonId=null){const r=relationById.get(id);if(!r)return;const relationLabel=relationDisplayLabel(r),observations=(r.observations||[]).slice().sort((a,b)=>(a.chapter??a.valid_from??0)-(b.chapter??b.valid_from??0));setDetail(`${backButton(returnPersonId)}<div class="eyebrow">关系档案 · ${esc(relationLaneLabels[relationLane(r)]||'其他关系')} · 当前快照：第 ${chapter} 章</div><h2>${esc(nameOf(r.source_id))} → ${esc(nameOf(r.target_id))}</h2><p class="summary">${asOf(r.description||relationLabel)}</p><section class="section"><div class="row"><b>读者分类</b><span>${esc(relationLabel)}</span></div><div class="row"><b>原始谓词</b><span>${esc(r.relation_type)}</span></div><div class="row"><b>完整有效期</b><span>第 ${r.valid_from} 章${r.valid_to?`—第 ${r.valid_to} 章`:'起'}</span></div><div class="row"><b>截至本章是否有效</b><span>${(r.valid_from??1)<=chapter&&(!r.valid_to||r.valid_to>=chapter)?'是':'否'}</span></div></section>${section('关系观察与状态变化',observations.map(o=>`<div class="history-item"><b>第 ${o.chapter??o.valid_from??'?'} 章 · ${esc(term('relation_statuses',o.status)||o.status||'补充证据')}</b>${o.description?`<p>${asOf(o.description)}</p>`:''}${evidenceHtml(o.evidence_ids)}</div>`).join(''))}${section('全范围原文证据',evidenceHtml(r.evidence_ids))}`,{kind:'relation',id,returnPersonId});bindDetailClicks()}
function showChange(id,returnPersonId=null){const x=changeById.get(id);if(!x)return;setDetail(`${backButton(returnPersonId)}<div class="eyebrow">状态变化 · <span class="confidence-${esc(x.confidence)}">${esc(term('confidences',x.confidence))}</span></div><h2>${esc(nameOf(x.entity_id))} · ${esc(term('actions',x.action))}</h2><section class="section"><div class="row"><b>章节</b><span>第 ${x.chapter} 章</span></div><div class="row"><b>维度</b><span>${esc(term('facets',personFacetForChange(x)))}</span></div><div class="row"><b>此前</b><span>${value(x.before)}</span></div><div class="row"><b>此后</b><span>${value(x.after)}</span></div><div class="row"><b>原因</b><span>${asOf(x.reason)}</span></div></section>${x.cause_event_id?section('原因事件',`<div class="history-item" data-event="${esc(x.cause_event_id)}"${returnPersonId?` data-return-person="${esc(returnPersonId)}"`:''}><b>${asOf(eventById.get(x.cause_event_id)?.title||'对应事件')}</b></div>`):''}${section('原文证据',evidenceHtml(x.evidence_ids))}`,{kind:'change',id,returnPersonId});bindDetailClicks()}
function showEvent(id,returnPersonId=null){const e=eventById.get(id);if(!e)return;setDetail(`${backButton(returnPersonId)}<div class="eyebrow">事件 · 第 ${e.chapter} 章</div><h2>${asOf(e.title)}</h2><p class="summary">${asOf(e.description)}</p>${section('参与者',`<div class="chips">${arr(e.participant_ids).map(x=>`<span class="chip">${esc(nameOf(x))}</span>`).join('')}</div>`)}${section('原文证据',evidenceHtml(e.evidence_ids))}`,{kind:'event',id,returnPersonId});bindDetailClicks()}
function intimacyWho(a){const ids=[...arr(a.initiator_ids),...arr(a.recipient_ids),...arr(a.observer_ids)];return ids.map(nameOf).join('、')||'未记录'}
function showIntimacy(id,returnPersonId=null){const a=(graph.intimate_acts||[]).find(x=>x.id===id);if(!a)return;const site=a.ejaculation_site?term('ejaculation_sites',a.ejaculation_site):'';setDetail(`${backButton(returnPersonId)}<div class="eyebrow">亲密行为 · 第 ${a.chapter} 章</div><h2>${esc(term('intimacy_act_types',a.act_type))}</h2><p class="summary">${asOf(a.description)}</p><section class="section"><div class="row"><b>主动方</b><span>${esc(arr(a.initiator_ids).map(nameOf).join('、')||'—')}</span></div><div class="row"><b>承受方</b><span>${esc(arr(a.recipient_ids).map(nameOf).join('、')||'—')}</span></div>${(a.observer_ids||[]).length?`<div class="row"><b>旁观者</b><span>${esc(a.observer_ids.map(nameOf).join('、'))}</span></div>`:''}<div class="row"><b>互动性质</b><span>${esc(term('consent_contexts',a.consent)||'未记录')}</span></div>${a.nudity!==undefined?`<div class="row"><b>涉及裸体</b><span>${a.nudity?'是':'否'}${a.nudity_note?'（'+esc(a.nudity_note)+'）':''}</span></div>`:''}${site?`<div class="row"><b>结束方式</b><span>${esc(site)}</span></div>`:''}<div class="row"><b>可信度</b><span class="confidence-${esc(a.confidence)}">${esc(term('confidences',a.confidence))}</span></div></section>${section('原文证据',evidenceHtml(a.evidence_ids))}`,{kind:'intimacy',id,returnPersonId});bindDetailClicks()}
function showForeshadow(id){const f=(graph.foreshadowing||[]).find(x=>x.id===id);if(!f)return;const steps=foreshadowDatedSteps(f);setDetail(`<div class="eyebrow">伏笔 · ${esc(term('foreshadow_statuses',foreshadowStatusAt(f)))}</div><h2>${asOf(f.label)}</h2><p class="summary">${asOf(f.observation)}</p><section class="section"><div class="row"><b>埋设</b><span>第 ${f.planted_chapter} 章</span></div><div class="row"><b>解释</b><span>${asOf(f.interpretation)}</span></div><div class="row"><b>可信度</b><span class="confidence-${esc(f.confidence)}">${esc(term('confidences',f.confidence))}</span></div><div class="row"><b>涉及</b><span>${esc(arr(f.related_entity_ids).map(nameOf).join('、'))}</span></div></section>${section('推进记录',steps.map(p=>`<div class="history-item"><b>${p.chapter==null?'日期未定':'第 '+p.chapter+' 章'} · ${esc(term('progression_kinds',p.kind))}</b><p>${asOf(p.description)}</p>${evidenceHtml(p.evidence_ids)}</div>`).join('')||'<p class="summary">截至第 '+chapter+' 章尚无推进记录。</p>')}${section('原文证据',evidenceHtml(f.evidence_ids))}`,{kind:'foreshadow',id,returnPersonId:null})}
function showIssue(id){const x=(graph.review_issues||[]).find(v=>v.id===id);if(!x)return;setDetail(`<div class="eyebrow">待核问题 · ${esc(term('issue_severities',x.severity))}</div><h2>${esc(term('issue_categories',x.category))}</h2><p class="summary">${asOf(x.description)}</p><section class="section"><div class="row"><b>章节</b><span>第 ${x.chapter} 章</span></div><div class="row"><b>相关对象</b><span>${esc(arr(x.related_ids).map(nameOf).join('、')||'全局')}</span></div></section>${section('原文证据',evidenceHtml(x.evidence_ids))}`,{kind:'issue',id,returnPersonId:null})}
function firstSexText(r){return r.first_sex_chapter?`第 ${r.first_sex_chapter} 章`:'尚未记录'}
// 首次相遇可以无章号：一对人物在本图谱覆盖之前就已相识时，凭空给一个章号是编造，
// 写「尚未发生」又是谎话。原文没交代就照实说没定年。
function firstMeetingText(r){return r.first_meeting_chapter?`第 ${r.first_meeting_chapter} 章`:'未定年（原文未在本图谱覆盖范围内交代）'}
function milestoneBlock(label,milestoneChapter,evidenceIds,missing='尚未发生／未确认'){const shown=!!milestoneChapter;return `<div class="milestone"><b>${esc(label)}</b><span>${shown?'第 '+milestoneChapter+' 章':esc(missing)}</span>${shown?evidenceHtml(evidenceIds):''}</div>`}
function showRomance(id,returnPersonId=null){const r=romanceById.get(id);if(!r)return;const status=romanceStatusAt(r);setDetail(`${backButton(returnPersonId)}<div class="eyebrow">感情线／后宫 · ${esc(status)}</div><h2>${esc(nameOf(r.protagonist_id))} × ${esc(nameOf(r.character_id))}</h2><p class="summary">${asOf(r.notes||'只记录有原文依据的感情进展。')}</p><section class="section"><div class="row"><b>入选依据</b><span>${esc(term('romance_inclusion_bases',r.inclusion_basis))}</span></div><div class="row"><b>互动性质</b><span>${esc(term('consent_contexts',r.consent_context))}</span></div><div class="row"><b>当前阶段</b><span>${esc(status)}</span></div><div class="row"><b>可信度</b><span class="confidence-${esc(r.confidence)}">${esc(term('confidences',r.confidence))}</span></div></section>${section('里程碑',`<div class="milestone-grid">${milestoneBlock('首次相遇',r.first_meeting_chapter,r.first_meeting_evidence_ids,'未定年（原文未在本图谱覆盖范围内交代）')}${milestoneBlock('首次亲密／暧昧',r.ambiguity_started_chapter,r.ambiguity_evidence_ids)}${milestoneBlock('关系确认',r.confirmed_chapter,r.confirmed_evidence_ids)}${milestoneBlock('首次明确性关系',r.first_sex_chapter,r.first_sex_evidence_ids,'尚未记录')}</div>`)}`,{kind:'romance',id,returnPersonId});bindDetailClicks()}
function showArc(id){const a=arcById.get(id);if(!a)return;const children=(graph.story_arcs||[]).filter(x=>x.parent_arc_id===id),overlaps=(graph.story_arcs||[]).filter(x=>x.id!==id&&Math.max(a.chapter_start,x.chapter_start)<=Math.min(a.chapter_end??Infinity,x.chapter_end??Infinity));setDetail(`<div class="eyebrow">剧情弧 · ${esc(term('story_arc_statuses',a.status))}</div><h2>${esc(a.title)}</h2><p class="summary">第 ${a.chapter_start} 章—${a.chapter_end??'未完'} · ${esc(term('story_arc_phases',a.phase)||'阶段未定')}</p>${a.parent_arc_id?section('父剧情',`<div class="history-item" data-arc="${esc(a.parent_arc_id)}"><b>${esc(nameOf(a.parent_arc_id))}</b></div>`):''}${section('参与人物／地点／物品',`<div class="chips">${arr(a.entity_ids).map(x=>`<button class="chip" data-entity="${esc(x)}">${esc(nameOf(x))}</button>`).join('')}</div>`)}${section('关键事件与转折',arr(a.event_ids).map(x=>`<div class="history-item" data-event="${esc(x)}"><b>${esc(nameOf(x))}</b><p>${arr(a.turning_point_ids).includes(x)?'转折点':'剧情事件'}</p></div>`).join(''))}${section('子剧情',children.map(x=>`<div class="history-item" data-arc="${esc(x.id)}"><b>${esc(x.title)}</b></div>`).join(''))}${section('同期交叉剧情',overlaps.map(x=>`<div class="history-item" data-arc="${esc(x.id)}"><b>${esc(x.title)}</b><p>第 ${x.chapter_start}—${x.chapter_end??'未完'} 章</p></div>`).join(''))}${section('证据',evidenceHtml(a.evidence_ids))}`,{kind:'arc',id,returnPersonId:null});bindDetailClicks()}
function refreshDetailForChapter(){const route={...detailRoute};if(route.kind==='entity')showEntity(route.id);else if(route.kind==='relation')showRelation(route.id,route.returnPersonId);else if(route.kind==='change')showChange(route.id,route.returnPersonId);else if(route.kind==='event')showEvent(route.id,route.returnPersonId);else if(route.kind==='romance')showRomance(route.id,route.returnPersonId);else if(route.kind==='arc')showArc(route.id);else if(route.kind==='foreshadow')showForeshadow(route.id);else if(route.kind==='issue')showIssue(route.id);else showCoverage()}
function setChapter(nextChapter,relayout=false){chapter=Math.max(graph.metadata?.chapter_start??1,Math.min(graph.metadata?.chapter_end||chapter,+nextChapter));document.querySelector('#chapter').value=chapter;document.querySelector('#chapterValue').textContent=chapter;if(chapterRenderFrame)return;chapterRenderFrame=scheduleFrame(()=>{chapterRenderFrame=0;renderFeeds();applyGraphFilters(relayout)})}
function bindDetailClicks(){document.querySelectorAll('#detail [data-entity]').forEach(x=>x.onclick=()=>showEntity(x.dataset.entity));document.querySelectorAll('[data-relation]').forEach(x=>x.onclick=()=>showRelation(x.dataset.relation,x.dataset.returnPerson||null));document.querySelectorAll('[data-change]').forEach(x=>x.onclick=()=>showChange(x.dataset.change,x.dataset.returnPerson||null));document.querySelectorAll('[data-event]').forEach(x=>x.onclick=()=>showEvent(x.dataset.event,x.dataset.returnPerson||null));document.querySelectorAll('[data-romance]').forEach(x=>x.onclick=()=>showRomance(x.dataset.romance,x.dataset.returnPerson||null));document.querySelectorAll('[data-arc]').forEach(x=>x.onclick=()=>showArc(x.dataset.arc));document.querySelectorAll('[data-back-person]').forEach(x=>x.onclick=()=>showEntity(x.dataset.backPerson));document.querySelectorAll('[data-jump-chapter]').forEach(x=>x.onclick=()=>setChapter(+x.dataset.jumpChapter));const slider=document.querySelector('#personChapter');if(slider)slider.oninput=e=>setChapter(+e.target.value);const currentPerson=detailRoute.kind==='entity'?detailRoute.id:null,previous=document.querySelector('#previousChange'),next=document.querySelector('#nextChange');if(currentPerson&&previous&&!previous.disabled)previous.onclick=()=>{const points=[...new Set((graph.state_changes||[]).filter(x=>x.entity_id===currentPerson&&x.chapter<chapter).map(x=>x.chapter))];setChapter(Math.max(...points))};if(currentPerson&&next&&!next.disabled)next.onclick=()=>{const points=[...new Set((graph.state_changes||[]).filter(x=>x.entity_id===currentPerson&&x.chapter>chapter).map(x=>x.chapter))];setChapter(Math.min(...points))}}

cy.on('tap','node',e=>{cy.elements().removeClass('faded spotlight');const n=e.target;selectedId=n.id();if(scope==='core')applyGraphFilters(true);n.addClass('spotlight');n.closedNeighborhood().difference(n).addClass('spotlight');cy.elements().not(n.closedNeighborhood()).addClass('faded');showEntity(n.id())});
cy.on('tap','edge',e=>showRelation(e.target.id()));cy.on('tap',e=>{if(e.target===cy){cy.elements().removeClass('faded spotlight');selectedId=null;if(scope==='core')applyGraphFilters(true);showCoverage()}});
document.querySelector('#fit').onclick=()=>cy.fit(cy.elements(':visible'),45);document.querySelector('#focus').onclick=()=>{if(selectedId&&cy.getElementById(selectedId).visible())cy.animate({center:{eles:cy.getElementById(selectedId)},zoom:1.35},{duration:350})};document.querySelector('#clear').onclick=()=>{cy.elements().removeClass('faded spotlight');selectedId=null;if(scope==='core')applyGraphFilters(true);showCoverage()};
document.querySelector('#chapter').oninput=e=>setChapter(+e.target.value);
document.querySelector('#search').oninput=e=>{search=e.target.value.trim();applyGraphFilters(true)};document.querySelector('#layout').onchange=e=>{layoutName=e.target.value;runLayout()};
document.querySelectorAll('#scope button').forEach(b=>b.onclick=()=>{scope=b.dataset.scope;document.querySelectorAll('#scope button').forEach(x=>x.classList.toggle('active',x===b));applyGraphFilters(true)});
document.querySelectorAll('[data-type-mode]').forEach(b=>b.onclick=()=>{typeSelectionMode=b.dataset.typeMode;if(typeSelectionMode==='single'&&activeTypes.size!==1){const preferred=activeTypes.has('character')?'character':([...activeTypes][0]||allTypes[0]);activeTypes=new Set(preferred?[preferred]:[])}syncTypeControls();applyGraphFilters(true)});
document.querySelector('#typeAll').onclick=()=>{if(typeSelectionMode!=='multi')return;activeTypes=new Set(allTypes);syncTypeControls();applyGraphFilters(true)};
document.querySelector('#typeNone').onclick=()=>{if(typeSelectionMode!=='multi')return;activeTypes.clear();syncTypeControls();applyGraphFilters(true)};
document.querySelectorAll('[data-type]').forEach(b=>b.onclick=()=>{const t=b.dataset.type;if(typeSelectionMode==='single')activeTypes=new Set([t]);else if(activeTypes.has(t))activeTypes.delete(t);else activeTypes.add(t);syncTypeControls();applyGraphFilters(true)});
document.querySelectorAll('[data-view]').forEach(b=>b.onclick=()=>{activeView=b.dataset.view;document.querySelectorAll('[data-view]').forEach(x=>x.classList.toggle('active',x===b));document.querySelectorAll('.view').forEach(x=>x.classList.toggle('active',x.id===activeView));renderFeeds();if(activeView==='graph')setTimeout(()=>{cy.resize();cy.fit(cy.elements(':visible'),45)},0)});

const warehouseDefinitions={characters:{label:'人物库',match:e=>isAgent(e)},organizations:{label:'势力／家族库',match:e=>e.type==='organization'},locations:{label:'地点库',match:e=>e.type==='location'},skills:{label:'技能库',match:e=>e.type==='skill'||e.type==='martial_soul'},items:{label:'装备／物品库',match:e=>e.type==='item'},levels:{label:'等级库',match:e=>e.type==='level_axis'}};
const friendRelationTypes=new Set(['friend_of','close_friend_of','ally_of','companion_of','sworn_sibling_of']);
const enemyRelationTypes=new Set(['enemy_of','rival_of','targets','hunts','hired_to_kill','attacked','harmed','hurt']);
const siblingRelationTypes=new Set(['sibling_of','sworn_sibling_of']);
const familyRelationTypes=new Set(['parent_of','child_of','grandparent_of','family_member_of','spouse_of','betrothed_to']);
const mentorRelationTypes=new Set(['teacher_of','mentor_of','student_of','instructed']);
const affiliationRelationTypes=new Set(['member_of','sect_member_of','school_member_of','citizen_of','affiliated_with','leader_of']);
// A second personality, avatar, or possessed double shares the protagonist's body and
// acts on its own, so it belongs in its own shelf rather than under 朋友／敌人／其它人物.
// A mere cover identity (伪装身份) is deliberately *not* here: the same person wears it
// without a second agent behind it, so it stays an ordinary alias or concept.
const alterEgoRelationTypes=new Set(['alter_ego_of','same_body_as','avatar_of']);
// `owns` is accepted only when an explicit relation records a holder; names never imply ownership.
const skillOwnerRelationTypes=new Set(['learned','uses','teaches','owns','created']);
const itemOwnerRelationTypes=new Set(['owns','possesses','uses','uses_as_weapon']);
function visibleRelation(r){return (r.valid_from??1)<=chapter&&(!r.valid_to||r.valid_to>=chapter)}
function otherEntity(r,id){return r.source_id===id?r.target_id:r.source_id}
function protagonistRelations(id){return protagonistId?(graph.relations||[]).filter(r=>visibleRelation(r)&&((r.source_id===protagonistId&&r.target_id===id)||(r.target_id===protagonistId&&r.source_id===id))):[]}
function latestEntityChapter(e){const stats=entityReaderStats(e),relationChapters=stats.activeRelations.map(r=>r.valid_from??1);return Math.max(e.first_chapter??1,stats.latestChangeChapter??0,...relationChapters)}
function sortWarehouseEntities(items){return [...items].sort((a,b)=>warehouseSort==='name'?a.name.localeCompare(b.name,'zh-CN'):warehouseSort==='latest'?latestEntityChapter(b)-latestEntityChapter(a)||a.name.localeCompare(b.name,'zh-CN'):(a.first_chapter??1)-(b.first_chapter??1)||a.name.localeCompare(b.name,'zh-CN'))}
function characterGroup(e){if(e.type!=='character')return 'agents';if(e.id===protagonistId)return 'protagonist';const relations=protagonistRelations(e.id),types=new Set(relations.map(r=>r.relation_type));if(relations.some(r=>alterEgoRelationTypes.has(r.relation_type)))return 'alter';if((graph.romance_routes||[]).some(r=>(r.ambiguity_started_chapter??r.first_meeting_chapter??1)<=chapter&&(r.protagonist_id===e.id||r.character_id===e.id)))return 'harem';if([...types].some(t=>siblingRelationTypes.has(t)))return 'siblings';if([...types].some(t=>familyRelationTypes.has(t)))return 'family';if([...types].some(t=>mentorRelationTypes.has(t)))return 'mentors';if([...types].some(t=>enemyRelationTypes.has(t)))return 'enemies';if([...types].some(t=>friendRelationTypes.has(t)))return 'friends';if([...types].some(t=>affiliationRelationTypes.has(t)))return 'organizations';return 'others'}
function visibleTerm(group,key){const label=term(group,key);return label&&label!=='未分类'&&label!==vocabulary.fallback?label:null}
function characterTags(e){if(e.id===protagonistId)return ['主角'];const tags=protagonistRelations(e.id).map(r=>visibleTerm('relations',r.relation_type)).filter(Boolean);const route=(graph.romance_routes||[]).find(r=>r.ambiguity_started_chapter<=chapter&&(r.protagonist_id===e.id||r.character_id===e.id));if(route)tags.unshift(romanceStatusAt(route));return [...new Set(tags)].slice(0,4)}
const itemRoleLabels={owner:'所有者',holder:'当前持有人',user:'使用者',custodian:'保管者'};
function itemRoleSummary(own){const grouped=new Map();for(const rec of own.roles.values()){if(!grouped.has(rec.role))grouped.set(rec.role,[]);grouped.get(rec.role).push(rec.id)}return ['owner','holder','user','custodian'].filter(role=>grouped.has(role)).map(role=>`${itemRoleLabels[role]}：${[...new Set(grouped.get(role))].map(nameOf).join('、')}`).join(' · ')}
function skillHistoryTags(e){const rows=(changesByTarget.get(e.id)||[]).filter(x=>(x.chapter??0)<=chapter).slice().sort((a,b)=>b.chapter-a.chapter),tags=[];for(const x of rows){const text=`${x.reason||''} ${attrText(x.after)}`;let label={lost:'已失去',forgotten:'已遗忘',sealed:'已封印',unsealed:'已解封',learned:'已学会',gained:'已获得',transferred:'临时借用'}[x.action];if(/无法修炼|不能修炼|不可修炼/.test(text))label='被传授但无法修炼';else if(Number.isInteger(x.end_chapter)&&x.end_chapter<chapter)label='临时借用已结束';if(label)tags.push(label)}return [...new Set(tags)].slice(0,4)}
function warehouseReaderMeta(e,kind=warehouseKind){const stats=entityReaderStats(e),base={primaryStatusText:'当前状态暂无记录',secondaryStatusText:'',tags:[],isCurrentActive:stats.currentStateCount>0||stats.activeRelationCount>0,...stats};if(kind==='characters'){const highlights=stats.currentHighlights.map(([k,v])=>`${k}：${attrText(v)}`);base.primaryStatusText=highlights.slice(0,2).join(' · ')||'当前身份／等级暂无记录';base.secondaryStatusText=highlights.slice(2).join(' · ')||characterTags(e).join(' · ');base.tags=[...characterTags(e),...(stats.issueCount?['有待核问题']:[])];return base}if(kind==='skills'){const owners=skillOwners(e),rows=[...owners.entries()].map(([id,status])=>`${nameOf(id)}（${status}）`),history=skillHistoryTags(e);base.primaryStatusText=rows.length?`当前：${rows.join('、')}`:'当前无人掌握或使用';base.secondaryStatusText=history.length?`历史状态：${history.join('、')}`:'暂无可关联到此技能实体的变化记录';base.tags=[...new Set([...owners.values(),...history,...(stats.issueCount?['有待核问题']:[])])];base.isCurrentActive=owners.size>0;return base}if(kind==='items'){const own=itemOwnership(e),roles=itemRoleSummary(own);base.primaryStatusText=roles||'当前所有者／持有人／使用者／保管者未明';base.secondaryStatusText=own.history.length?`历史涉及：${own.history.map(nameOf).join('、')}`:'尚无人物角色记录';base.tags=[...new Set([...own.roles.values()].map(x=>itemRoleLabels[x.role]||x.role)),...(stats.issueCount?['有待核问题']:[])];base.currentCount=own.roles.size;base.isCurrentActive=own.roles.size>0;return base}if(kind==='levels'){const holders=axisHolders(e.id),rungs=axisRungs(e),occupied=rungs.filter(x=>x.attested).length;base.primaryStatusText=holders.length?`当前占用 ${occupied} 个档位 · ${holders.length} 个主体`:'当前无人占用已记录档位';base.secondaryStatusText=`档位 ${rungs.length} 个 · 换算 ${visibleConversions().filter(c=>c.from&&c.to&&(c.from.axis_id===e.id||c.to.axis_id===e.id)).length} 条`;base.tags=[holders.length?'当前有效':'尚无占用',...(stats.issueCount?['有待核问题']:[])];base.isCurrentActive=holders.length>0;return base}return base}
function warehouseCard(e,meta){const al=visibleAliases(e),latest=meta.latestChangeChapter?`最近第 ${meta.latestChangeChapter} 章`:'尚无变化',categoryTags=categoryEntries(e).map(c=>term('item_categories',c.id)||c.id),membership=graph._collection_views?.memberships?.[e.id],membershipTags=arr(membership?.collection_ids).map(id=>collectionById.get(id)?.label||id),tags=[...new Set([...meta.tags,...categoryTags,...membershipTags])];return `<article class="warehouse-card" data-entity="${esc(e.id)}" tabindex="0"><h3>${esc(nameOf(e.id))} <span class="entry-kind">${esc(typeMeta(e.type)[0])}</span></h3><div class="warehouse-card-status">${esc(meta.primaryStatusText)}</div>${meta.secondaryStatusText?`<div class="warehouse-card-secondary">${esc(meta.secondaryStatusText)}</div>`:''}<p>${asOf(e.summary||'暂无一句话摘要，可点击查看完整状态、关系与原文证据。')}</p><div class="warehouse-card-stats">变化 ${meta.changeCount} 次 · 证据 ${meta.evidenceCount} 条 · ${latest}</div>${tags.length?`<div class="relation-tags">${tags.slice(0,3).map(x=>`<span>${esc(x)}</span>`).join('')}${tags.length>3?`<span>+${tags.length-3} 个归属</span>`:''}</div>`:''}${al.length?`<div class="warehouse-card-alias">别名：${esc(al.join('、'))}</div>`:''}<div class="warehouse-card-meta"><span>初见 · 第 ${e.first_chapter??1} 章</span><span>${meta.issueCount?meta.issueCount+' 个待核问题':'无待核问题'}</span></div></article>`}
function warehouseCompactRow(e,meta){return `<tr data-entity="${esc(e.id)}" tabindex="0"><td class="warehouse-table-name"><b>${esc(nameOf(e.id))}</b><small>${esc(typeMeta(e.type)[0])}</small></td><td>${esc(meta.primaryStatusText)}</td><td>${meta.changeCount}</td><td>${meta.evidenceCount}</td><td>${meta.latestChangeChapter?'第 '+meta.latestChangeChapter+'章':'—'}</td></tr>`}
function warehouseSection(label,items,metaMap,note=''){if(!items.length)return '';const sorted=sortWarehouseEntities(items),body=warehouseView==='compact'?`<div class="warehouse-table-wrap"><table class="warehouse-table"><thead><tr><th>名称</th><th>当前状态／归属</th><th>变化</th><th>证据</th><th>最近章节</th></tr></thead><tbody>${sorted.map(e=>warehouseCompactRow(e,metaMap.get(e.id))).join('')}</tbody></table></div>`:`<div class="warehouse-grid">${sorted.map(e=>warehouseCard(e,metaMap.get(e.id))).join('')}</div>`;return `<section class="warehouse-section"><div class="warehouse-section-head"><h3>${esc(label)}</h3><span>${items.length}</span>${note?`<span class="warehouse-section-note">${esc(note)}</span>`:''}</div>${body}</section>`}
function warehouseFilterMatch(e,meta){if(warehouseFilter==='all')return true;if(warehouseFilter==='changed')return meta.changeCount>0;if(warehouseFilter==='issues')return meta.issueCount>0;if(warehouseFilter==='active')return meta.isCurrentActive;if(warehouseFilter==='protagonist'){if(e.id===protagonistId||meta.activeRelations.some(r=>r.source_id===protagonistId||r.target_id===protagonistId))return true;if(warehouseKind==='skills')return skillOwners(e).has(protagonistId);if(warehouseKind==='items')return itemOwnership(e).current.includes(protagonistId);if(warehouseKind==='levels')return axisHolders(e.id).some(x=>x.id===protagonistId)}return false}
function renderWarehouse(){
 const definition=warehouseDefinitions[warehouseKind],query=warehouseSearch.toLocaleLowerCase('zh-CN');
 const all=(graph.entities||[]).filter(e=>definition.match(e)&&entityVisibleAt(e)).filter(e=>!query||[e.name,...visibleAliases(e),e.summary||''].join(' ').toLocaleLowerCase('zh-CN').includes(query));
 const metaMap=new Map(all.map(e=>[e.id,warehouseReaderMeta(e)])),matched=sortWarehouseEntities(all.filter(e=>warehouseFilterMatch(e,metaMap.get(e.id))));
 const pageCount=Math.max(1,Math.ceil(matched.length/warehousePageSize));warehousePage=Math.min(Math.max(1,warehousePage),pageCount);
 const from=(warehousePage-1)*warehousePageSize,to=Math.min(matched.length,from+warehousePageSize),entities=matched.slice(from,to);let html='';
 if(warehouseKind==='characters'){
  const groups={protagonist:[],alter:[],agents:[],siblings:[],family:[],mentors:[],friends:[],harem:[],enemies:[],organizations:[],others:[]};for(const e of entities)groups[characterGroup(e)].push(e);
  html=warehouseSection('主角',groups.protagonist,metaMap)+warehouseSection('同一人的另一面',groups.alter,metaMap,'第二人格／分身／化身')+warehouseSection('拟人主体',groups.agents,metaMap,'魂兽／异类等按人物式档案展示')+warehouseSection('兄弟姐妹／结义',groups.siblings,metaMap)+warehouseSection('家族／婚姻',groups.family,metaMap)+warehouseSection('师徒／教导',groups.mentors,metaMap)+warehouseSection('朋友／盟友',groups.friends,metaMap)+warehouseSection('亲密关系／感情线候选',groups.harem,metaMap,'候选不等于双方自愿或恋爱确认')+warehouseSection('敌对／伤害',groups.enemies,metaMap)+warehouseSection('势力／门派关联',groups.organizations,metaMap)+warehouseSection('其它人物',groups.others,metaMap,'当前没有可证的主角侧分类');
 }else if(warehouseKind==='skills'){
  const groups={protagonist:[],others:[],unknown:[]};for(const e of entities){const owners=skillOwners(e);if(protagonistId&&owners.has(protagonistId))groups.protagonist.push(e);else if(owners.size)groups.others.push(e);else groups.unknown.push(e)}html=warehouseSection(`${nameOf(protagonistId)}当前已学会／能使用`,groups.protagonist,metaMap)+warehouseSection('其他人物当前技能',groups.others,metaMap)+warehouseSection('当前无人掌握／使用',groups.unknown,metaMap);
 }else if(warehouseKind==='levels'){
  html=warehouseView==='compact'?warehouseSection('等级体系',entities,metaMap,'新档位并入兼容旧轴；跨体系只采用明示换算'):levelWarehouseHtml(entities);
 }else if(warehouseKind==='items'){
  const groups=new Map();for(const e of entities){const cats=categoryEntries(e),primary=cats.find(c=>c.primary)||cats[0]||{id:'unresolved'},label=term('item_categories',primary.id)||primary.id;if(!groups.has(label))groups.set(label,[]);groups.get(label).push(e)}html=[...groups.entries()].sort((a,b)=>a[0].localeCompare(b[0],'zh-CN')).map(([label,items])=>warehouseSection(label,items,metaMap,'每件物品只显示一次，其他类别保留为标签')).join('');
 }else{
  const groups={root:[],subset:[]};for(const e of entities)(hierarchyAncestors(e.id).length?groups.subset:groups.root).push(e);html=warehouseSection('顶层集合',groups.root,metaMap,'没有当前有效上级')+warehouseSection('子集／下属',groups.subset,metaMap,'详情中区分直接归属与继承上级');
 }
 document.querySelectorAll('[data-warehouse]').forEach(b=>b.classList.toggle('active',b.dataset.warehouse===warehouseKind));document.querySelectorAll('[data-warehouse-view]').forEach(b=>{const on=b.dataset.warehouseView===warehouseView;b.classList.toggle('active',on);b.setAttribute('aria-pressed',String(on))});
 document.querySelector('#warehouseCount').textContent=`${definition.label} · 匹配 ${matched.length}/${all.length} 项 · 当前 ${matched.length?from+1:0}—${to} · 第 ${warehousePage}/${pageCount} 页 · 截至第 ${chapter} 章`;
 document.querySelector('#warehouseGrid').innerHTML=html||'<div class="empty">当前搜索与筛选条件下暂无条目</div>';
 const pager=document.querySelector('#warehousePager');pager.innerHTML=`<button id="warehousePrev"${warehousePage<=1?' disabled':''}>上一页</button><span aria-live="polite">第 ${warehousePage}/${pageCount} 页</span><button id="warehouseNext"${warehousePage>=pageCount?' disabled':''}>下一页</button><select id="warehousePageSize" aria-label="每页条数">${[12,24,48,96].map(n=>`<option value="${n}"${warehousePageSize===n?' selected':''}>每页 ${n}</option>`).join('')}</select>`;
 document.querySelector('#warehousePrev').onclick=()=>{warehousePage--;renderWarehouse()};document.querySelector('#warehouseNext').onclick=()=>{warehousePage++;renderWarehouse()};document.querySelector('#warehousePageSize').onchange=e=>{warehousePageSize=+e.target.value;warehousePage=1;renderWarehouse()};
 document.querySelectorAll('#warehouseGrid [data-entity]').forEach(card=>{card.onclick=()=>showEntity(card.dataset.entity);card.onkeydown=e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();showEntity(card.dataset.entity)}}});if(warehouseKind==='levels'&&warehouseView==='cards')wireLevelConverter();
}
document.querySelectorAll('[data-warehouse]').forEach(b=>b.onclick=()=>{warehouseKind=b.dataset.warehouse;warehousePage=1;renderWarehouse()});
document.querySelector('#warehouseSearch').oninput=e=>{warehouseSearch=e.target.value.trim();warehousePage=1;renderWarehouse()};
document.querySelector('#warehouseSort').onchange=e=>{warehouseSort=e.target.value;warehousePage=1;renderWarehouse()};
document.querySelector('#warehouseFilter').onchange=e=>{warehouseFilter=e.target.value;warehousePage=1;renderWarehouse()};
document.querySelectorAll('[data-warehouse-view]').forEach(b=>b.onclick=()=>{warehouseView=b.dataset.warehouseView;renderWarehouse()});

const timeline=[...(graph.events||[]).map(x=>({...x,_kind:'event'})),...(graph.state_changes||[]).map(x=>({...x,_kind:'change'})),...(graph.chapter_summaries||[]).map(x=>({...x,_kind:'summary'}))].sort((a,b)=>a.chapter-b.chapter||String(a.id).localeCompare(String(b.id)));
const feedPage={arcs:1,collections:1,timeline:1,romance:1,intimacy:1,foreshadowing:1,style:1,issues:1},feedPageSize={arcs:24,collections:24,timeline:24,romance:24,intimacy:24,foreshadowing:24,style:24,issues:24};
function pageRows(view,rows){const size=feedPageSize[view]||24,pages=Math.max(1,Math.ceil(rows.length/size));feedPage[view]=Math.min(Math.max(1,feedPage[view]||1),pages);const start=(feedPage[view]-1)*size;return {rows:rows.slice(start,start+size),total:rows.length,pages,start,end:Math.min(rows.length,start+size)}}
function pagerHtml(view,page){return `<div class="page-controls" data-pager="${view}"><button data-page-prev${feedPage[view]<=1?' disabled':''}>上一页</button><span aria-live="polite">${page.total?`${page.start+1}—${page.end} / ${page.total}`:'0 条'} · 第 ${feedPage[view]}/${page.pages} 页</span><button data-page-next${feedPage[view]>=page.pages?' disabled':''}>下一页</button><select data-page-size aria-label="每页条数">${[12,24,48,96].map(n=>`<option value="${n}"${feedPageSize[view]===n?' selected':''}>每页 ${n}</option>`).join('')}</select></div>`}
function wirePager(view){const host=document.querySelector(`[data-pager="${view}"]`);if(!host)return;host.querySelector('[data-page-prev]').onclick=()=>{feedPage[view]--;renderFeeds()};host.querySelector('[data-page-next]').onclick=()=>{feedPage[view]++;renderFeeds()};host.querySelector('[data-page-size]').onchange=e=>{feedPageSize[view]=+e.target.value;feedPage[view]=1;renderFeeds()}}
function arcDepth(arc){let depth=0,cursor=arc,seen=new Set();while(cursor?.parent_arc_id&&!seen.has(cursor.parent_arc_id)){seen.add(cursor.parent_arc_id);cursor=arcById.get(cursor.parent_arc_id);if(cursor)depth++}return depth}
function renderArcRows(rows){const start=graph.metadata?.chapter_start??1,end=graph.metadata?.chapter_end??start,span=Math.max(1,end-start+1);return rows.map(a=>{const left=Math.max(0,((a.chapter_start-start)/span)*100),right=a.chapter_end??end,width=Math.max(1,((right-a.chapter_start+1)/span)*100);return `<article class="arc-lane${a.parent_arc_id?' child':''}" style="--arc-depth:${arcDepth(a)}"><div class="arc-label" style="padding-left:${arcDepth(a)*16}px"><b>${esc(a.title)}</b><small>第 ${a.chapter_start}—${a.chapter_end??'未完'} 章 · ${esc(term('story_arc_statuses',a.status))} · ${esc(arcPhaseLabel(a.phase))}</small></div><div class="arc-track"><button class="arc-bar" data-arc="${esc(a.id)}" style="left:${left}%;width:${Math.min(100-left,width)}%" title="${esc(a.title)}">${esc(a.title)}</button></div></article>`}).join('')}
function collectionExpressionLabel(expression){if(!expression||typeof expression!=='object')return '无表达式';const [operator,operand]=Object.entries(expression)[0]||[];if(operator==='collection')return collectionById.get(operand)?.label||operand;if(['and','or'].includes(operator))return `(${arr(operand).map(collectionExpressionLabel).join(operator==='and'?' ∩ ':' ∪ ')})`;if(operator==='not')return `排除 ${collectionExpressionLabel(operand)}`;if(operator==='type')return `类型：${arr(Array.isArray(operand)?operand:[operand]).map(x=>term('entity_types',x)).join('、')}`;if(operator==='relation')return `关系：${typeof operand==='string'?operand:(operand.relation_type||arr(operand.types).join('、'))}`;if(operator==='arc')return `剧情：${typeof operand==='string'?nameOf(operand):'指定剧情'}`;if(operator==='active_at')return `在第 ${typeof operand==='number'?operand:operand.chapter} 章有效`;if(operator==='explicit_members')return '人工确认成员';return operator||'未知表达式'}
function renderCombinedCollections(){const definitions=graph._collection_views?.collections||[],selected=definitions.filter(c=>selectedCollections.has(c.id)),sets=selected.map(c=>new Set(c.members.map(m=>m.entity_id)));let ids;if(!sets.length)ids=[];else if(collectionOperator==='and')ids=[...sets[0]].filter(id=>sets.every(set=>set.has(id)));else if(collectionOperator==='or')ids=[...new Set(sets.flatMap(set=>[...set]))];else{const excluded=new Set(sets.flatMap(set=>[...set]));ids=[...byId.keys()].filter(id=>!excluded.has(id))}ids=ids.sort((a,b)=>nameOf(a).localeCompare(nameOf(b),'zh-CN')||a.localeCompare(b));const pages=Math.max(1,Math.ceil(ids.length/collectionMemberPageSize));collectionMemberPage=Math.min(Math.max(1,collectionMemberPage),pages);const start=(collectionMemberPage-1)*collectionMemberPageSize,visible=ids.slice(start,start+collectionMemberPageSize),operatorLabel={and:'同时满足／交集',or:'满足任一／并集',not:'排除所选／差集'}[collectionOperator];document.querySelector('#collectionCount').textContent=selected.length?`${operatorLabel}：${selected.map(c=>c.label).join('、')} · ${ids.length} 个唯一实体`:'请选择一个或多个集合';document.querySelector('#collectionResults').innerHTML=visible.map(id=>warehouseCard(byId.get(id),warehouseReaderMeta(byId.get(id)))).join('')||'<div class="empty">当前组合没有实体</div>';const pager=document.querySelector('#collectionResultsPager');pager.innerHTML=`<button data-collection-prev${collectionMemberPage<=1?' disabled':''}>上一页</button><span>${ids.length?`${start+1}—${Math.min(ids.length,start+collectionMemberPageSize)} / ${ids.length}`:'0 条'} · 第 ${collectionMemberPage}/${pages} 页</span><button data-collection-next${collectionMemberPage>=pages?' disabled':''}>下一页</button><select data-collection-page-size aria-label="集合结果每页条数">${[12,24,48,96].map(n=>`<option value="${n}"${collectionMemberPageSize===n?' selected':''}>每页 ${n}</option>`).join('')}</select>`;pager.querySelector('[data-collection-prev]').onclick=()=>{collectionMemberPage--;renderCombinedCollections()};pager.querySelector('[data-collection-next]').onclick=()=>{collectionMemberPage++;renderCombinedCollections()};pager.querySelector('[data-collection-page-size]').onchange=e=>{collectionMemberPageSize=+e.target.value;collectionMemberPage=1;renderCombinedCollections()};document.querySelectorAll('#collectionResults [data-entity]').forEach(x=>x.onclick=()=>showEntity(x.dataset.entity))}
const warehouseMemo={chapter:null,skills:new Map(),items:new Map()};
function refreshWarehouseMemo(){if(warehouseMemo.chapter===chapter)return;warehouseMemo.chapter=chapter;warehouseMemo.skills.clear();warehouseMemo.items.clear()}
function skillOwners(e){refreshWarehouseMemo();if(warehouseMemo.skills.has(e.id))return warehouseMemo.skills.get(e.id);const owners=new Map(),labels={learned:'已学会',uses:'能使用',knows_about:'仅见过',teaches:'被传授',created:'创制',owns:'持有',borrowed:'临时借用',taught_but_unable:'被传授但无法修炼'};for(const r of (relationsByEntity.get(e.id)||[])){if((r.valid_from??1)>chapter||(r.valid_to&&r.valid_to<chapter)||!Object.prototype.hasOwnProperty.call(labels,r.relation_type))continue;const id=r.source_id===e.id?r.target_id:r.source_id;if(isAgent(byId.get(id)))owners.set(id,labels[r.relation_type])}for(const x of (changesByTarget.get(e.id)||[])){if((x.chapter??0)>chapter||!isAgent(byId.get(x.entity_id)))continue;if(['lost','forgotten','left','sealed'].includes(x.action)||Number.isInteger(x.end_chapter)&&x.end_chapter<chapter)owners.delete(x.entity_id);else if(['learned','gained','upgraded','revealed','unsealed'].includes(x.action)){const text=`${x.reason||''} ${attrText(x.after)}`;owners.set(x.entity_id,/无法修炼|不能修炼|不可修炼/.test(text)?'被传授但无法修炼':x.action==='learned'?'已学会':'能使用')}}warehouseMemo.skills.set(e.id,owners);return owners}
function normalItemRole(value,fallback='holder'){const aliases={owns:'owner',owner:'owner',owned_by:'owner',uses:'user',user:'user',used_by:'user',custodian:'custodian',custodian_of:'custodian',holder:'holder',holds:'holder'};const key=String(value||fallback).toLowerCase();return aliases[key]||key}
function itemRoleRefs(value,fallbackEntity=null){const out=[];if(typeof value==='string')return [[value,'holder']];if(Array.isArray(value)){for(const row of value)out.push(...itemRoleRefs(row,fallbackEntity));return out}if(value&&typeof value==='object'){for(const [key,role] of Object.entries({owner_id:'owner',user_id:'user',custodian_id:'custodian',holder_id:'holder'})){const ref=value[key];if(typeof ref==='string')out.push([ref,role]);else if(Array.isArray(ref))for(const id of ref)if(typeof id==='string')out.push([id,role])}const generic=[value.entity_id,value.character_id,value.possessor_id].find(x=>typeof x==='string');if(generic)out.push([generic,normalItemRole(value.role)]);return out}return fallbackEntity?[[fallbackEntity,'holder']]:[]}
function itemOwnership(e){refreshWarehouseMemo();if(warehouseMemo.items.has(e.id))return warehouseMemo.items.get(e.id);const events=[],history=new Set(),push=(at,priority,id,op,entity,role)=>{if(at<=chapter&&typeof entity==='string')events.push([at,priority,String(id||''),op,entity,normalItemRole(role)])};const relationRoles={owns:'owner',uses:'user',custodian_of:'custodian',holds:'holder'};for(const r of (relationsByEntity.get(e.id)||[])){const role=relationRoles[r.relation_type];if(!role||r.target_id!==e.id)continue;const start=Number.isInteger(r.valid_from)?r.valid_from:0;push(start,0,r.id,'add',r.source_id,role);if(Number.isInteger(r.valid_to))push(r.valid_to+1,0,r.id,'remove',r.source_id,role)}for(const x of (changesByTarget.get(e.id)||[])){if(x.facet!=='possession')continue;const start=Number.isInteger(x.chapter)?x.chapter:0,before=itemRoleRefs(x.before,x.entity_id),after=itemRoleRefs(x.after,x.entity_id),removal=['forgotten','left','lost','removed','relinquished'].includes(String(x.action||'').toLowerCase())||('after'in x&&x.after===null);if(removal){for(const [id,role] of (before.length?before:[[x.entity_id,'holder']]))push(start,1,x.id,'remove_entity',id,role)}else if(x.action==='transferred'){for(const [id,role] of (before.length?before:[[x.entity_id,'holder']]))push(start,1,x.id,'remove_entity',id,role);for(const [id,role] of after)push(start,1,x.id,'add',id,role)}else for(const [id,role] of (after.length?after:[[x.entity_id,'holder']]))push(start,1,x.id,'add',id,role);if(Number.isInteger(x.end_chapter)){for(const [id,role] of (after.length?after:[[x.entity_id,'holder']]))push(x.end_chapter+1,1,x.id,'remove',id,role);for(const [id,role] of before)push(x.end_chapter+1,1,x.id,'add',id,role)}}for(const row of (itemRolesByItem.get(e.id)||[])){const start=Number.isInteger(row.valid_from)?row.valid_from:(Number.isInteger(row.chapter)?row.chapter:0),refs=itemRoleRefs(row);for(const [id,inferred] of refs){const role=normalItemRole(row.role,inferred),inactive=['ended','inactive','lost'].includes(String(row.status||'active').toLowerCase());push(start,2,row.id,inactive?'remove':'add',id,role);const end=Number.isInteger(row.valid_to)?row.valid_to:row.end_chapter;if(Number.isInteger(end))push(end+1,2,row.id,'remove',id,role)}}events.sort((a,b)=>a[0]-b[0]||a[1]-b[1]||a[2].localeCompare(b[2])||((a[3].startsWith('remove')?0:1)-(b[3].startsWith('remove')?0:1)));const roles=new Map();for(const [, , ,op,id,role] of events){history.add(id);if(op==='remove_entity'){for(const key of [...roles.keys()])if(key.startsWith(id+'\u0000'))roles.delete(key)}else if(op==='remove')roles.delete(id+'\u0000'+role);else roles.set(id+'\u0000'+role,{id,role})}const current=[...new Set([...roles.values()].map(x=>x.id))].sort(),result={current,history:[...history].sort(),roles};warehouseMemo.items.set(e.id,result);return result}
function renderFeeds(){
 if(activeView==='graph')return;if(activeView==='warehouse'){renderWarehouse();return}
 if(activeView==='arcs'){const page=pageRows('arcs',(graph.story_arcs||[]).slice().sort((a,b)=>(a.parent_arc_id!==null)-(b.parent_arc_id!==null)||(a.chapter_start??0)-(b.chapter_start??0)||String(a.id).localeCompare(b.id)));document.querySelector('#arcFeed').innerHTML=(renderArcRows(page.rows)||'<div class="empty">暂无剧情弧记录</div>')+pagerHtml('arcs',page);wirePager('arcs');document.querySelectorAll('[data-arc]').forEach(x=>x.onclick=()=>showArc(x.dataset.arc));return}
 if(activeView==='collections'){const page=pageRows('collections',graph._collection_views?.collections||[]);document.querySelector('#collectionFeed').innerHTML=(page.rows.map(c=>`<button class="collection-card${selectedCollections.has(c.id)?' active':''}" data-collection="${esc(c.id)}" aria-pressed="${selectedCollections.has(c.id)}"><h3>${esc(c.label)}</h3><p>${c.member_count} 个唯一成员 · ${c.display?.primary?'主显示集合':'派生集合'}</p><p>查询：${esc(collectionExpressionLabel(c.expression))}</p><div>${c.members.slice(0,12).map(m=>`<span class="membership-chip">${esc(nameOf(m.entity_id))}</span>`).join('')}${c.member_count>12?`<span class="membership-chip">+${c.member_count-12}</span>`:''}</div></button>`).join('')||'<div class="empty">未提供 dashboard-views.json；集合功能可用但当前没有定义。</div>')+pagerHtml('collections',page);wirePager('collections');document.querySelectorAll('[data-collection]').forEach(x=>x.onclick=()=>{const id=x.dataset.collection;if(selectedCollections.has(id))selectedCollections.delete(id);else selectedCollections.add(id);collectionMemberPage=1;renderFeeds()});document.querySelector('#collectionOperator').value=collectionOperator;document.querySelector('#collectionOperator').onchange=e=>{collectionOperator=e.target.value;collectionMemberPage=1;renderCombinedCollections()};document.querySelector('#clearCollections').onclick=()=>{selectedCollections.clear();collectionMemberPage=1;renderFeeds()};renderCombinedCollections();return}
 if(activeView==='style'){const dimensions={prose:'全文行文',narrative:'叙事风格',characterization:'人物刻画',speech:'关键人物语言',behavior:'关键人物行为'},page=pageRows('style',arr(graph._style_observations).slice().sort((a,b)=>(a.chapter_start??0)-(b.chapter_start??0)||String(a.id).localeCompare(b.id)));document.querySelector('#styleFeed').innerHTML=(page.rows.map(s=>`<article class="style-card"><h3>${esc(dimensions[s.dimension]||s.dimension||'风格观察')}${s.entity_id?' · '+esc(nameOf(s.entity_id)):''}</h3><p>${asOf(s.claim)}</p><div class="relation-tags"><span>第 ${s.chapter_start}—${s.chapter_end??'未完'} 章</span><span>${esc(s.stability||'未标注稳定性')}</span><span>${esc(term('confidences',s.confidence))}</span><span>${arr(s.evidence_ids).length} 条证据</span><span>${arr(s.counterexamples).length} 个反例</span></div></article>`).join('')||'<div class="empty">未提供 style-observations.json；不会凭空生成风格结论。</div>')+pagerHtml('style',page);wirePager('style');return}
 const source=activeView==='timeline'?timeline:activeView==='romance'?(graph.romance_routes||[]).slice().sort((a,b)=>(a.ambiguity_started_chapter??0)-(b.ambiguity_started_chapter??0)):activeView==='intimacy'?(graph.intimate_acts||[]).slice().sort((a,b)=>(a.chapter??0)-(b.chapter??0)):activeView==='foreshadowing'?(graph.foreshadowing||[]).slice().sort((a,b)=>(a.planted_chapter??0)-(b.planted_chapter??0)):(graph.review_issues||[]);
 const page=pageRows(activeView,source),rows=page.rows;let body='';
 if(activeView==='timeline')body=rows.map(x=>x._kind==='event'?`<article class="feed-item" data-event="${esc(x.id)}"><time>第 ${x.chapter} 章</time><div><h3>${asOf(x.title)}</h3><p>${asOf(x.description)}</p><span class="tag">事件 · ${esc(term('event_types',x.type))}</span></div></article>`:x._kind==='summary'?`<article class="feed-item"><time>第 ${x.chapter} 章</time><div><h3>${asOf(x.title||'章节梗概')}</h3><p>${asOf(x.summary)}</p><span class="tag">${arr(x.arc_ids).map(nameOf).join(' · ')||'未归入剧情弧'}${x.dominant_arc_id?' · 主显示剧情（非排他）：'+esc(nameOf(x.dominant_arc_id)):''}</span></div></article>`:`<article class="feed-item" data-change="${esc(x.id)}"><time>第 ${x.chapter} 章</time><div><h3>${esc(nameOf(x.entity_id))} · ${esc(term('actions',x.action))}</h3><p>${asOf(x.reason)}</p><span class="tag">${esc(term('facets',personFacetForChange(x)))}</span></div></article>`).join('');
 else if(activeView==='romance')body=rows.map(r=>`<article class="feed-item" data-romance="${esc(r.id)}"><time>第 ${r.ambiguity_started_chapter??r.first_meeting_chapter??'?'} 章</time><div><h3>${esc(nameOf(r.protagonist_id))} × ${esc(nameOf(r.character_id))}</h3><p>${esc(term('romance_inclusion_bases',r.inclusion_basis))} · ${esc(term('consent_contexts',r.consent_context))}</p><span class="tag">${esc(term('romance_statuses',r.status))}</span></div></article>`).join('');
 else if(activeView==='intimacy')body=rows.map(a=>`<article class="feed-item" data-intimacy="${esc(a.id)}"><time>第 ${a.chapter} 章</time><div><h3>${esc(term('intimacy_act_types',a.act_type))} · ${esc(intimacyWho(a))}</h3><p>${asOf(a.description)}</p><span class="tag">${esc(term('consent_contexts',a.consent)||'性质未记录')}</span></div></article>`).join('');
 else if(activeView==='foreshadowing')body=rows.map(f=>`<article class="feed-item" data-foreshadow="${esc(f.id)}"><time>第 ${f.planted_chapter} 章</time><div><h3>${asOf(f.label)}</h3><p>${asOf(f.observation)}</p><span class="tag">${esc(term('foreshadow_statuses',f.status))}</span></div></article>`).join('');
 else body=rows.map(x=>`<article class="feed-item" data-issue="${esc(x.id)}"><time>第 ${x.chapter} 章</time><div><h3>${esc(term('issue_categories',x.category))}</h3><p>${asOf(x.description)}</p></div></article>`).join('');
 const container=document.querySelector(`#${activeView==='foreshadowing'?'foreshadow':activeView}Feed`);container.innerHTML=(body||'<div class="empty">暂无记录</div>')+pagerHtml(activeView,page);wirePager(activeView);bindDetailClicks();document.querySelectorAll('[data-intimacy]').forEach(x=>x.onclick=()=>showIntimacy(x.dataset.intimacy));document.querySelectorAll('[data-foreshadow]').forEach(x=>x.onclick=()=>showForeshadow(x.dataset.foreshadow));document.querySelectorAll('[data-issue]').forEach(x=>x.onclick=()=>showIssue(x.dataset.issue));
}
renderFeeds();showCoverage();applyGraphFilters(true);const initialEntity=new URLSearchParams(location.search).get('entity');if(initialEntity&&byId.has(initialEntity)){showEntity(initialEntity)}
</script>
</body></html>'''


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--graph", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--validation", type=Path, help="Optional validation.json to display")
    parser.add_argument("--vocabulary", type=Path, help="Optional book-specific display vocabulary JSON")
    parser.add_argument("--views", type=Path, help="Optional dashboard-views.json collection manifest")
    parser.add_argument("--style-observations", type=Path, help="Optional style-observations.json analytical view")
    args = parser.parse_args()
    graph = reader_safe_data(json.loads(args.graph.resolve().read_text(encoding="utf-8")))
    views_path = args.views or args.graph.resolve().parent / "dashboard-views.json"
    if views_path.is_file():
        views = json.loads(views_path.resolve().read_text(encoding="utf-8"))
        graph["_collection_views"] = derive_collection_views(graph, views)
    else:
        graph["_collection_views"] = {"collections": [], "memberships": {}}
    style_path = args.style_observations or args.graph.resolve().parent / "style-observations.json"
    if style_path.is_file():
        style_payload = json.loads(style_path.resolve().read_text(encoding="utf-8"))
        graph["_style_observations"] = reader_safe_data(validate_style_observations(style_payload, graph))
    else:
        graph["_style_observations"] = []
    if args.validation:
        graph["_validation"] = json.loads(args.validation.resolve().read_text(encoding="utf-8"))
    vocabulary = merge_vocabulary(DEFAULT_VOCABULARY, graph.get("metadata", {}).get("display_vocabulary", {}))
    if args.vocabulary:
        vocabulary = merge_vocabulary(vocabulary, json.loads(args.vocabulary.resolve().read_text(encoding="utf-8")))
    graph["_display_vocabulary"] = vocabulary
    # Non-human entities that act like people get the character-style layout. The
    # detection runs here, from the graph alone, so the page never depends on a
    # hand-written flag; `graph._agents` carries the per-entity reasons so the panel
    # can show why an entity was promoted.
    graph["_agents"] = detect_agents(graph)
    asset = Path(__file__).resolve().parent.parent / "assets" / "cytoscape-3.34.3.min.js"
    if not asset.is_file():
        raise FileNotFoundError(f"Bundled Cytoscape.js asset not found: {asset}")
    cytoscape_js = asset.read_text(encoding="utf-8").replace("</script>", "<\\/script>")
    payload = json.dumps(graph, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    output = args.output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(HTML.replace("__CYTOSCAPE__", cytoscape_js)
        .replace("__READER_PROSE_JS__", reader_prose_js())
        .replace("__GRAPH_DATA__", payload), encoding="utf-8")
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
