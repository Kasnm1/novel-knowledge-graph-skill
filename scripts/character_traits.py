#!/usr/bin/env python3
"""人物特征（外貌／性格／语言语气／习惯）的单一词汇来源。

为什么不是一个 `attributes.外貌` 字符串
------------------------------------
人物特征以前散在 `entities[].attributes` 里，有的写 `外貌`、有的写 `性格`、更多
干脆塞进 `备注`。三个问题：

1. **键不统一**，同一件事两个人写成两种标签，读者看到两份表述。
2. **`attributes` 是标量**，`merge_value` 只保留最后一个分片的写法，所以「第30章
   受伤后脸上留了疤」会覆盖掉前一版的描述，而不是并存。
3. **没有「什么时候变成这样」**。特征是要随时间走的：一个人第1章是及肩短发，
   第40章剪短，读者在 as-of 第 20 章时该看到短发、在 as-of 第 50 章时该看到更短的。

所以特征进 `character_traits`，一条一个断言：

    {"id": "trait_qin_chao_appearance_01", "entity_id": "char_qin_chao",
     "facet": "appearance", "statement": "身材精瘦，黑色短发，眉骨高。",
     "chapter": 1, "status": "current", "evidence_ids": ["ev_..."]}

**「不用每章都变」是靠 `chapter` 实现的，不是靠省略**：基线在人物首次出场章记一条，
之后只在真正改变的地方再记一条。渲染时按 (entity, facet) 取 `chapter <= N` 的最后
一条 —— 所以不用复述，读者看到的仍然是最新的那一版。

刻意**不依赖 `supersedes` 链**：并行抽取时每个分片只看到自己那几章，链会在分片之间
断掉；按 `chapter` 排序取最新是鲁棒的，也让「第 40 章那条写错了」可以直接删掉重写。
`status` 用于另一种情形 —— 某个特征**失效但没有新值**（「惯用右手」断臂之后）。
"""

from __future__ import annotations

# 四个分面。分得比这更细会让分片难以保持一致，更粗则「语言语气」会和「性格」混在一起。
FACETS: set[str] = {"appearance", "personality", "speech", "habit"}

FACET_LABELS: dict[str, str] = {
    "appearance": "外貌",
    "personality": "性格",
    "speech": "语言语气",
    "habit": "习惯动作",
}

# 抽取时容易写出的同义标签，merge 折叠回上面的规范值。
# 其中中文别名是主干 —— 分片大多用中文写 facet，英文只出现在早期或少见情况下。
FACET_ALIASES: dict[str, str] = {
    "外貌": "appearance", "长相": "appearance", "外形": "appearance", "外观": "appearance",
    "体貌": "appearance", "外表": "appearance", "容貌": "appearance",
    "穿着": "appearance", "装扮": "appearance",
    "性格": "personality", "性情": "personality", "秉性": "personality",
    "个性": "personality",
    "语气": "speech", "语言": "speech", "说话": "speech",
    "口头禅": "speech", "言辞": "speech", "语言语气": "speech",
    "说话方式": "speech", "称谓": "speech", "称呼": "speech",
    "习惯": "habit", "习惯动作": "habit", "癖好": "habit",
    "小动作": "habit", "嗜好": "habit",
}

# 展示顺序。`FACETS` 是集合（判成员用），渲染要按固定次序排 —— 同一个人每本书
# 都按「外貌→性格→语言语气→习惯」出现，读者才不用每次重新找。
FACET_ORDER: tuple[str, ...] = ("appearance", "personality", "speech", "habit")

STATUSES: set[str] = {"current", "superseded", "uncertain"}

STATUS_LABELS: dict[str, str] = {
    "current": "现行",
    "superseded": "已变化",
    "uncertain": "存疑",
}

REQUIRED_FIELDS = ("id", "entity_id", "facet", "statement", "chapter")


def canonical_facet(value: object) -> str:
    """把写出来的分面名折回规范值；认不出就原样返回（由校验器报出来）。"""
    if value is None:
        return ""
    text = str(value).strip()
    if text in FACETS:
        return text
    return FACET_ALIASES.get(text, text)


def facet_label(value: object) -> str:
    canonical = canonical_facet(value)
    return FACET_LABELS.get(canonical, str(value) if value is not None else "")


def canonical_status(value: object) -> str:
    if value is None:
        return "current"
    text = str(value).strip()
    if text in STATUSES:
        return text
    return {"现行": "current", "有效": "current", "已失效": "superseded",
            "已变化": "superseded", "存疑": "uncertain"}.get(text, text)


def statement_is_substantive(record: dict) -> bool:
    """`statement` 得是一句能独立读懂的话。

    太短的多半是标签而非描述（「漂亮」「善良」），对读者没有增量 —— 图谱里已有
    `summary` 承担一句话概括，特征值应该具体到可辨认（「及肩黑发，常用右手拨开
    额前碎发」）。这里只挡明显不合格的，不替抽取者做风格判断。
    """
    text = record.get("statement")
    if not isinstance(text, str):
        return False
    stripped = text.strip()
    if len(stripped) < 4:
        return False
    # 纯标签：没有任何标点、也不长，通常是「性格：高冷」被拆错了字段。
    if len(stripped) <= 6 and not any(ch in stripped for ch in "，。；、（） "):
        return False
    return True


def unknown_facets(records: list[dict]) -> list[tuple[str, str]]:
    """返回 (record_id, 原值) —— 不在规范集内、也不在任何别名里的分面。

    先折叠再判断：`外貌` 是 `appearance` 的别名，合并后会归一，不能把它当成
    规范集外的值报出来。
    """
    out: list[tuple[str, str]] = []
    for record in records:
        if not isinstance(record, dict):
            continue
        value = record.get("facet")
        if value is None:
            continue
        if canonical_facet(value) not in FACETS:
            out.append((str(record.get("id")), str(value)))
    return out


def sort_traits(records: list[dict]) -> list[dict]:
    """按 (人物, 分面, 章节) 排 —— 渲染取「最新一条」和人工核对都依赖这个顺序。"""
    return sorted(
        records,
        key=lambda r: (
            str(r.get("entity_id") or ""),
            canonical_facet(r.get("facet")),
            r.get("chapter") if isinstance(r.get("chapter"), int) else 10**9,
            str(r.get("id") or ""),
        ),
    )


def latest_traits(records: list[dict], as_of: int | None = None) -> dict[tuple[str, str], dict]:
    """每个 (人物, 分面) 在 `as_of` 章时的现行断言。

    `as_of=None` 表示不过滤（取全书的最终状态）。回放时传章号即可 —— 这正是
    「特征只在关键处变化」能成立的地方：没有新断言的章节自动沿用上一条。
    """
    current: dict[tuple[str, str], dict] = {}
    for record in sort_traits(records):
        chapter = record.get("chapter")
        if as_of is not None and isinstance(chapter, int) and chapter > as_of:
            continue
        # 不合法的断言由校验器报错；这里直接跳过，免得把「漂亮」这类纯标签
        # 当成一条外貌描述渲染出去。
        if not statement_is_substantive(record):
            continue
        key = (str(record.get("entity_id") or ""), canonical_facet(record.get("facet")))
        current[key] = record
    return current


def trait_history(records: list[dict], entity_id: str, facet: str) -> list[dict]:
    """某人在某个分面上的全部断言（按章节），用于「历史变化」折叠区。"""
    wanted = canonical_facet(facet)
    return [
        r for r in sort_traits(records)
        if str(r.get("entity_id")) == str(entity_id)
        and canonical_facet(r.get("facet")) == wanted
        and statement_is_substantive(r)
    ]
