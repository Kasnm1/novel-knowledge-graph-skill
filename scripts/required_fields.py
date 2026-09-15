#!/usr/bin/env python3
"""各记录类型的必填字段：`validate_graph.py` 与 `check_fragment.py` 共用这一份。

为什么要抽出来：分片门禁和合并后校验对「必填字段」的判断必须完全一致，否则门禁
只是把失败推迟到合并之后。第 201-300 章续拆时出过这个问题——`fragment-25` 有 22 条、
`fragment-30` 有 8 条 state_change 只写了 `cause_event_id` 而没写 `reason`。门禁当时
只对「无 reason **且** 无 cause_event_id **且** 无 notes」发警告，这 30 条因为带着
cause_event_id 而全数放行；一路合进 `graph.json` 才被 `validate_graph.py` 以 30 条
error 拦下，而那时要定位是哪一片写的、再回改分片，成本已经高得多。

两张表的语义差别是**故意**的：

- `REQUIRED`：值不得为 `None` / `""` / `[]`，与 `validate_graph.py` 里 `require()`
  的判断完全同语义（含空列表也算缺）。
- `REQUIRED_KEYS`：键必须存在，但值**允许**为 `null`。`first_sex_chapter` 就是例子：
  分析范围内主角群未成年时，正确写法是 `null` 且证据为空，而不是省略这个键。

`ARRAY_KINDS` 把分片／图谱里的数组名映射到记录类型名，两个脚本都用它遍历，
避免各写一份「数组名 → 类型名」的对照表而慢慢漂移。
"""
from __future__ import annotations

REQUIRED: dict[str, tuple[str, ...]] = {
    "evidence": ("id", "chapter", "quote", "source_line_start", "source_line_end"),
    "entity": ("id", "type", "name", "first_chapter", "evidence_ids"),
    "event": (
        "id", "type", "chapter", "title", "description", "participant_ids", "evidence_ids",
    ),
    "relation": (
        "id", "source_id", "target_id", "relation_type", "valid_from", "status", "evidence_ids",
    ),
    "state_change": (
        "id", "entity_id", "facet", "action", "chapter", "reason", "evidence_ids", "confidence",
    ),
    "romance_route": (
        "id", "protagonist_id", "character_id", "status", "inclusion_basis", "consent_context",
        "first_meeting_chapter", "first_meeting_evidence_ids",
        "ambiguity_started_chapter", "ambiguity_evidence_ids",
        "confidence",
    ),
    "intimate_act": ("id", "chapter", "act_type", "description", "confidence"),
    "level_conversion": ("id", "chapter", "from", "to", "relation", "description"),
    # 人物特征：一条一个断言，`chapter` 是它开始成立的章节。`status` 可选，默认 current。
    "character_trait": (
        "id", "entity_id", "facet", "statement", "chapter", "evidence_ids", "confidence",
    ),
    # 章节梗概：一章一条。`title` 可选（原文有章节标题时照抄，不要自己起名）。
    "chapter_summary": ("id", "chapter", "summary", "evidence_ids"),
    "story_arc": ("id", "title", "chapter_start", "status", "evidence_ids"),
    "item_role": (
        "id", "item_id", "entity_id", "role", "valid_from", "action",
        "evidence_ids", "confidence",
    ),
    "foreshadowing": (
        "id", "label", "status", "planted_chapter", "observation",
        "interpretation", "related_entity_ids", "evidence_ids", "confidence",
    ),
    "review_issue": ("id", "severity", "category", "description", "chapter"),
}

REQUIRED_KEYS: dict[str, tuple[str, ...]] = {
    "romance_route": (
        "confirmed_chapter", "confirmed_evidence_ids", "first_sex_chapter",
        "first_sex_evidence_ids", "notes",
    ),
    # `related_ids` 必须是数组（可为空数组，表示全局性问题）。`validate_graph.py`
    # 一直按这个口径校验，但分片门禁原先没管它——2026-09-14 在 fragment-66 的
    # 9 条 review_issue 上漏到合并后才炸。键必须在、值可为空，所以放 REQUIRED_KEYS。
    "review_issue": ("related_ids",),
    "story_arc": ("chapter_end", "parent_arc_id", "phase", "event_ids", "entity_ids", "turning_point_ids"),
}

ARRAY_KINDS: dict[str, str] = {
    "entities": "entity",
    "events": "event",
    "relations": "relation",
    "state_changes": "state_change",
    "romance_routes": "romance_route",
    "intimate_acts": "intimate_act",
    "level_conversions": "level_conversion",
    "character_traits": "character_trait",
    "chapter_summaries": "chapter_summary",
    "story_arcs": "story_arc",
    "item_roles": "item_role",
    "foreshadowing": "foreshadowing",
    "evidence": "evidence",
    "review_issues": "review_issue",
}

# 期望**非空**的数组类型。这是**声明**，不是猜测——因为判据必须能区分
# 「本书就没有这种东西」和「我们根本没抽」。
#
# 为什么需要它：`character_traits` 曾经是 0 条 / 734 个实体，活了六轮没人发现。
# 不是看不见——`AI_CONTEXT.md` 的「数据概况」每一版都写着「人物特征：0」。是**一个
# 计数没人拿去跟任何东西比**。所以「显示」和「门禁」是两件事：前者是打印一个 0，
# 后者是让流水线失败。`build_results_facts.py` 对本表里为 0 的类型**非零退出**。
#
# 只列「对任何一本书都不该为空」的类型：
#   * `character_traits` —— 有名字角色的书必须有人物特征，为空即「没抽」。
#   * `chapter_summaries` / `level_conversions` 是可选能力（本 run 就不做逐章梗概），
#     为空是合法的，不列。
# run 可以用 `<run>/expected_kinds.json` 覆盖，形如 `{"character_traits": false}`，
# 用来声明「本书确实没有」。覆盖文件是显式的、可审的，不是无声豁免。
EXPECTED_NON_EMPTY: tuple[str, ...] = ("character_traits",)

# `confidence` 的合法取值，`validate_graph.py` 与 `check_fragment.py` 共用这一份。
#
# 抽出来的理由与上面的必填字段表一样：门禁比校验器弱，失败就被推迟到合并之后。
# 2026-09-14 在《逆天邪神》的 `fragment-25` 上实测到一次——`fs_ch235_xue_gongzhu`
# 的 `confidence` 写了 `suspected`，`check_fragment.py` 只检查这个字段**存在**、
# 不检查取值，所以该片自检 0 error 全绿；一路合进 `graph.json` 才被
# `validate_graph.py` 以 `bad_confidence` 拦下，整条 rebuild 在第 5 步中止，
# 而那时要回改分片、重跑全链，成本高得多。
#
# 注意 `suspected` 是 `foreshadowing.status` 的合法取值，**不是** `confidence` 的
# 取值（见 references/schema.md：写进 `confidence` 会渲染成「未分类」）。两个词表
# 故意不重叠，正是为了让这类误填被当场发现而不是悄悄渲染。
CONFIDENCE: frozenset[str] = frozenset({"explicit", "inferred", "uncertain"})

# 由脚本算出来、不需要分片作者手写的字段。分片阶段只写 `quote`，
# `resolve_quotes.py` 在合并前按 quote 反查并回填行号（见 rebuild.sh 的 1b/9）。
# 所以分片门禁不能要求它们：门禁跑在 resolve_quotes **之前**，新写的证据
# 一定还没有行号。合并后的 `validate_graph.py` 照旧要求，那时已经回填完毕。
DERIVED: dict[str, tuple[str, ...]] = {
    "evidence": ("source_line_start", "source_line_end"),
}


def is_blank(value: object) -> bool:
    """与 `validate_graph.py` 的 `require()` 同语义：None / 空串 / 空列表都算缺。"""
    return value is None or value == "" or value == []
