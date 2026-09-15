#!/usr/bin/env python3
"""as-of 视图里「名称」的判定：哪些名字算泄露，哪些只是更长可见名的一部分。

`metadata.alias_first_chapter`（由 `annotate_alias_chapters.py` 生成）给每个别名定了
首次出现的章。第 N 章的快照不该出现首见于 N 之后的名字——改名、新称号、新魂灵名都会
从注记里漏进早期快照，而且这些字符串**不带任何章节号**，`第 X 章` 正则是抓不到的。

但「字符串包含」是不够的判据。别名往往是实体正式名的一部分：

  · 别名「鲸胶」 ⊂ 正式名「万年鲸胶」
  · 别名「噬灵」 ⊂ 正式名「噬灵刻刀」
  · 别名「斗魂大赛」 ⊂ 正式名「全大陆高级魂师学院斗魂大赛」

第 60 章的面板里出现「万年鲸胶」是完全正确的——那是读者该看到的正式名——但朴素的
`"鲸胶" in body` 会把它报成未来名称泄露。第一次跑 `verify_chapter_views.py` 的别名
探针时，12 条报告**全部**是这一类误报。

更糟的是，同样的朴素判据如果用在渲染层，会把**正确的内容隐去**。实测（本 run，
`graph.json` 合并后）按「朴素命中字段数 / 边界感知命中字段数」：

  N=20  → 935 / 762（多隐 173）      N=200 → 233 / 192（多隐 41）
  N=100 → 512 / 423（多隐 89）       N=290 →  21 /   4（多隐 17）

即第 290 章快照里 21 条被隐去的注记，只有 4 条是真的。隐去正确内容不会泄露未来，
但它是**信息损失**：读者拿到的图谱少了一批评注。所以判定必须精确。

判据：某个晚期别名的一次出现，只有在**不落在任何更长可见名之内**时才算泄露。
「可见名」= 所有实体正式名 + 首见章不晚于 as_of 的别名。实现上先为每个晚期别名
预计算「包含它的可见名及其偏移」，再把文本里的每次出现按偏移对齐检查一次即可，
不必逐名字扫描全文。

第三类误报：**界面标签**（`label_strings`）
------------------------------------------------
词表里的标签是固定构件，每个快照都原样显示，与剧情时间线无关，所以它不可能是泄露：

    <div class="eyebrow">修仙设定 · 第 1 章状态</div>

`concept` 的类型标签是「修仙设定」，而本书有一个实体正式名就叫「修仙」（首见第 4 章）。
第 1 章快照里「修仙」是晚期名，`"修仙" in body` 命中，于是核查报出
「concept_honglingxia 面板出现未来别名「修仙」」——**面板里根本没有这个名字**，
命中来自类型标签。`relation_types` / `facets` / `actions` / `issue_categories` 等标签同理。

处理方式与导航条一致：把「渲染器会用到的整套标签」当作恒可见的长名，交给同一套
包含关系检查。标签集必须与渲染器**完全同源**（`DEFAULT_VOCABULARY` 合并本书词表，
即 `build_dashboard.merge_vocabulary`），否则漏一个标签就会漏一条误报。
"""
from __future__ import annotations

import re

# 数字／ASCII 符号型别名不能参与子串匹配。小三的对讲机代号「02」是原文里真实存在的称呼，
# 但它会在「第202章」「2002年」里命中，报出一个并不存在的未来名称泄露。这类别名仍然记录在
# 实体上（summary / attributes），只是不进入定年表、也不参与 as-of 名称判定。
# 判据：别名里至少有一个「非 ASCII 字符」或「ASCII 字母」。
_NAME_LIKE_RE = re.compile(r"[^\W\d_]", re.UNICODE)


def is_name_like(alias: str) -> bool:
    """这个别名能不能当成「名字」做子串搜索。"""
    text = str(alias)
    if not text:
        return False
    return bool(_NAME_LIKE_RE.search(text)) or not text.isascii()


def visible_names(
    entities: list[dict], alias_first_chapter: dict[str, int], as_of: int
) -> list[str]:
    """截至 `as_of` 章合法出现在界面上的名字，长的在前（对齐检查用）。

    正式名也要过定年表，不能无条件加入：一个先以「一个女孩」出场、第 275 章才被
    点名的人物，第 274 章的注记里出现「黄凌」就是泄露。把未到章的名字放进可见名表，
    还会让 `alias_is_inside_visible_name` 把它的每次出现都当成「某个更长可见名的一部分」
    而放过——那是把泄露洗成正常。
    """
    names: set[str] = set()
    for entity in entities or []:
        if not isinstance(entity, dict):
            continue
        for label in [entity.get("name"), *(entity.get("aliases") or [])]:
            if not label or not is_name_like(label):
                continue
            first = (alias_first_chapter or {}).get(label)
            if not first or first <= as_of:
                names.add(str(label))
    return sorted(names, key=len, reverse=True)


def label_strings(vocabulary: object) -> list[str]:
    """把词表里所有字符串叶子收集出来（类型名、关系名、阶段名……）。

    这些是渲染器会原样印出的界面标签，与时间线无关，所以恒为「可见」。
    只收长度 ≥ 2 的字符串：单字标签（「是」「否」）没有区分度，放进可见名表
    反而会把单字实体名的每次出现都洗成「某个标签的一部分」。
    """
    found: set[str] = set()

    def walk(node: object) -> None:
        if isinstance(node, dict):
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for value in node:
                walk(value)
        elif isinstance(node, str) and len(node) >= 2:
            found.add(node)

    walk(vocabulary)
    return sorted(found, key=len, reverse=True)


def late_alias_containers(
    late_aliases: set[str], names: list[str]
) -> dict[str, list[tuple[str, list[int]]]]:
    """每个晚期别名 → 包含它的可见名及其中所有偏移。"""
    containers: dict[str, list[tuple[str, list[int]]]] = {}
    for alias in late_aliases:
        found: list[tuple[str, list[int]]] = []
        for name in names:
            if len(name) <= len(alias) or alias not in name:
                continue
            offsets = [i for i in range(len(name) - len(alias) + 1) if name.startswith(alias, i)]
            if offsets:
                found.append((name, offsets))
        containers[alias] = found
    return containers


def alias_is_inside_visible_name(
    text: str, position: int, alias: str, containers: list[tuple[str, list[int]]]
) -> bool:
    """`text[position:...]` 处的这个别名，是某个更长可见名的一部分。"""
    for name, offsets in containers:
        for offset in offsets:
            start = position - offset
            if start >= 0 and text.startswith(name, start):
                return True
    return False


def leaked_late_names(
    text: str, late_aliases: set[str], containers: dict[str, list[tuple[str, list[int]]]]
) -> list[str]:
    """文本里**独立出现**（不属于更长可见名）的晚期别名。"""
    hits: list[str] = []
    for alias in sorted(late_aliases):
        position = text.find(alias)
        while position != -1:
            if not alias_is_inside_visible_name(text, position, alias, containers.get(alias, [])):
                hits.append(alias)
                break
            position = text.find(alias, position + 1)
    return hits


class LateNameIndex:
    """一次快照一份，供渲染器与审计脚本共用。

    渲染器每渲染一条注记都要问一次「这句话点名了未来的名字吗」，所以把可见名表与
    包含关系预先算好，避免每条注记重算。
    """

    def __init__(
        self,
        entities: list[dict],
        alias_first_chapter: dict[str, int] | None,
        as_of: int,
        extra_visible: list[str] | tuple[str, ...] = (),
    ) -> None:
        self.as_of = as_of
        self.mapping = alias_first_chapter or {}
        self.late: set[str] = {
            a for a, c in self.mapping.items() if c > as_of and is_name_like(a)
        }
        # `extra_visible` 是界面标签（见模块 docstring 第三类误报）。它们必须参与
        # 包含关系检查，否则「修仙设定」会被当成独立的「修仙」报出来。
        names = visible_names(entities, self.mapping, as_of)
        extras = [n for n in dict.fromkeys(extra_visible) if n and is_name_like(n)]
        self.names = sorted(set(names) | set(extras), key=len, reverse=True)
        self.containers = late_alias_containers(self.late, self.names)

    def hits(self, text: object) -> list[str]:
        if not isinstance(text, str) or not self.late:
            return []
        return leaked_late_names(text, self.late, self.containers)

    def in_text(self, text: object) -> bool:
        return bool(self.hits(text))
