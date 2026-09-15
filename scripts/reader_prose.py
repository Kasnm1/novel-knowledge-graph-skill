#!/usr/bin/env python3
"""Reader-facing prose cleanup, shared by both renderers.

Two defects reach the reader through the same fields. Both were measured across all
runs in this project before this module existed:

**1. Process text.** `notes` and other prose fields accumulated the merge's own
bookkeeping — `本分片` 400+ times, `请主 Agent …` 42 times,
`本条由主 Agent 从 N 条分片记录合并（…）` 24 times, `[rom_su_ji 第1章]` fragment tags 41
times, plus internal field names (`first_sex_chapter`, `consent_context`, `evidence`)
and English enum values (`altered_state`, `one_sided`) inside Chinese sentences.

**2. Unresolvable record IDs.** The original ID scrub matched
`(char|concept|…|axis)_[a-z0-9_]+`: no `rom_` / `rr_` prefix, no uppercase tail. So
`rom_A01`, `fs_A01`, `sc_D01`, `ri_E06`, `rr_huo_yuhao_*` all passed through.

Three rules keep this from being a content shredder, and each was added because a
first attempt violated it:

* **Work at sentence level, never inside one.** A clause-level rule that ate a comma
  merged two clauses and deleted the real content sentence in front of it
  (`首次登场在第1章（依据固定实体表说明），本分片无第1章证据…` lost 「首次登场在第1章」).
  Sentences are dropped whole or kept whole; only neutral replacements happen inside.
* **Delete only what cannot resolve.** `（char_huo_muqin / char_gongjue）` names three
  entities the renderer can turn into real names, so the stripper must leave it alone.
  Only fragment-local IDs — `rom_A01`, `rom_f03_hetao`, `fs_A01` — are unrecoverable,
  because the merge consolidated them away and no resolver can label them.
* **Replace when a neutral word will do.** `本分片` becomes 「本图谱范围」 rather than
  taking its clause with it; `本分片仅以书信现身：自居虎妖"小弟"` is content and survives.

After every deletion the separator litter is collapsed, because a removed ID list
otherwise leaves `新建、，`.
"""

from __future__ import annotations

import json
import re

# ---------------------------------------------------------------------------
# 1. Fragment-local record IDs — the only ones that cannot be resolved.
#
# They carry a per-fragment marker: `_f38_` or a two-digit uppercase tag `_A01`.
# ---------------------------------------------------------------------------
# 公开名（不带下划线）：export_ai_context.py 与 build_dashboard.py 都按
# `reader_prose.ID_PREFIXES` 引用它，两份注释也写着「保持一份定义」。
# 曾有一次重构把它改成 `_ID_PREFIXES` 而没同步导入方，导出脚本直接 ImportError。
ID_PREFIXES = (
    "char", "concept", "item", "skill", "location", "org", "creature", "event",
    "rel", "sc", "fs", "ri", "ev", "axis", "rom", "rr", "lcv", "ia", "level",
)
_PREFIX_ALT = "|".join(ID_PREFIXES)
FRAGMENT_LOCAL_ID = re.compile(
    r"\b(?:" + _PREFIX_ALT + r")_(?:[A-Z]\d{2}|f\d{2})(?:_[A-Za-z0-9_]+)?\b"
)
# A run of them, separated — removed as a unit so the separators go too.
FRAGMENT_LOCAL_RUN = re.compile(
    r"\b(?:" + _PREFIX_ALT + r")_(?:[A-Z]\d{2}|f\d{2})(?:_[A-Za-z0-9_]+)?"
    r"(?:\s*[、,，/]\s*(?:" + _PREFIX_ALT + r")_(?:[A-Z]\d{2}|f\d{2})(?:_[A-Za-z0-9_]+)?)+"
)
# `与 rom_f03_hetao / rom_f04_hetao 合并前` -> `合并前`
LEADING_ID_CLAUSE = re.compile(
    r"[^，。；]{0,20}(?:与|和|见)\s*[^，。；]{0,60}(?:合并前|合并时)[，,]?"
)
# `（依据固定实体表说明）` — the parenthetical only, never the following comma: the
# comma is what bounds the "留空" clause rule, and eating it merges two clauses.
FIXED_TABLE_NOTE = re.compile(r"（依据?固定(?:实体)?表(?:说明)?）|依据固定(?:实体)?表说明")

# `[rom_su_ji 第1章]` / `[rom_A01 第1章]` — the tag a fragment worker prefixed its findings
# with. It carries nothing the graph does not hold elsewhere, and 41 of them reached the
# reader-facing romance archive.
FRAGMENT_TAG = re.compile(r"\[[A-Za-z][A-Za-z0-9_]*\s*第\s*\d+\s*章\]\s*")

# ---------------------------------------------------------------------------
# 2. Sentence-level process detection.
#
# A matching sentence is dropped whole. Anything else is kept whole and only edited
# by the neutral replacements below — never cut.
# ---------------------------------------------------------------------------
PROCESS_SENTENCES: tuple[re.Pattern[str], ...] = (
    # merge journal / hand-off to the operator
    re.compile(r"本条由主\s*Agent[^。]*。?"),
    re.compile(r"合并前各分片[^。]*。?"),
    re.compile(r"请主\s*Agent[^，。；）)]*[，。；）)]?"),
    re.compile(r"交由主\s*Agent[^。]*。?"),
    re.compile(r"请由更早分片"),
    re.compile(r"若更早分片"),
    re.compile(r"请沿用其"),
    re.compile(r"建议主代理[^。]*。?"),
    re.compile(r"合并时(?:请|需|建议)[^。]*。?"),
    # `merge 时请与 rom_x / rom_y 按 character_id 合并` —— 只删「merge 时」两个词会
    # 把后半句交接语留在正文里，所以按从句整段删（句末「。」仍由残句规则决定去留）。
    re.compile(r"[，,]?\s*merge\s*时[^。]*"),
    re.compile(r"[，,]?\s*请(?:按|与|和|把|用)[^。]{0,80}?合并[^。]*"),
    re.compile(r"合并阶段需要[^。]*。?"),
    re.compile(r"需人工确认是否重复[^。]*。?"),
    re.compile(r"请人工"),
    # field bookkeeping: why a field is empty / how it was counted
    # 不要写成裸 `为空`：它会命中「扭曲为空**间**召唤」。要求字段话术把话说全。
    re.compile(r"[A-Za-z_]{4,}\s*(?:留空|未填|为空|为\s*null|=\s*null)"),
    re.compile(r"(?:该|此|本)(?:字段|项|记录|条)\s*(?:留空|未填|为空|一律\s*null)"),
    # 只认上面的纯字段陈述。中文里的「原文未记层数」「故首次见面里程碑留空」
    # 要么在陈述原文的沉默、要么在解释字段为什么空，都携带信息，属于内容；
    # 早先的 `未记(?!录)` 和裸 `留空` 会把它们整句删掉。

    re.compile(r"无本分片引文"),
    re.compile(r"属分片[A-Z](?!片)"),
    re.compile(r"本分片不(?:提供|含)"),
    # fragment bookkeeping about IDs and coverage
    re.compile(r"本分片(?:按|把|只|仅|未|无)[^，。；）)]{0,12}(?:编号|ID|evidence|证据|声明|登记|收录|记录|建成|取用)"),
    # 把「按内部键合并」当指令写进正文的交接句。从句级删除，句末的「。」不吞：
    # 吞了就会让这一句和下一句粘成「…里程碑第19章何桃…」。整句都是交接时残句为空，
    # 由 _strip_process_fragments 整句丢弃。
    re.compile(r"[，,]?\s*请按\s*[A-Za-z_]{3,}\s*合并[^。]*"),
    re.compile(r"若前序分片[^。]*"),
    re.compile(r"各分片均未为[^，。；）]*[，。；）]?"),
    # 「before 接第170章 sc_f18_002 的 after」——纯链条记账，句内删净。
    re.compile(r"(?:before|after)\s*接[^。]*"),
    # 「沿用更早分片已建的 id，只补新增字段」「首次相遇引文沿用 … 那条引文」——
    # 一句里除了这条声明没有别的信息，删掉从句后残句会被整句丢弃。
    re.compile(r"沿用[^。]{0,40}?(?:已建的|那条引文)[^。]*"),
    re.compile(r"本轮在同一批分片内[^。]*"),
    # 「合并后这条会由 coalesce 合并」——把 coalesce 换成中文会变成「由合并合并」，
    # 整句只是给整理者看的合并说明，按从句删净。
    re.compile(r"[，,；]?\s*合并后[^。]*?(?:coalesce|合并处理|会由合并)[^。]*"),
    re.compile(r"[（(][^（()）]*(?:原写作|合并期|--id-map)[^（()）]*[）)]"),
    # 上一条合并句被删后留下的孤儿尾巴，例如「取最早一节的判定。」
    re.compile(r"取\s*最\s*早\s*一节[^。]*。?"),
)

# ---------------------------------------------------------------------------
# 3. Neutral replacements applied inside surviving sentences.
# ---------------------------------------------------------------------------
NEUTRALISE: tuple[tuple[re.Pattern[str], str], ...] = (
    # 分片文件名（`fragment-08`）是内部路径，先于「分片」一词处理，否则会被拆成两半。
    # 带「分片」前缀的整句要排在裸文件名之前：`分片 fragment-02 已记录` 若先命中
    # `fragment-\d+`，就只剩「分片更早的图谱范围已记录」这种半截话。
    (re.compile(r"分片\s*fragment-\d+\s*已记录"), "更早的图谱范围已记录"),
    (re.compile(r"分片\s*fragment-\d+\s*范围内"), "更早的图谱范围内"),
    (re.compile(r"分片\s*fragment-\d+"), "更早的图谱范围"),
    (re.compile(r"在\s*fragment-\d+\s*范围内"), "在本图谱范围内"),
    (re.compile(r"(?:已)?由\s*fragment-\d+\s*的\s*"), "由更早的图谱范围"),
    (re.compile(r"(?:与|和)\s*fragment-\d+\s*的\s*"), "与更早的图谱范围"),
    (re.compile(r"(?:已)?由\s*fragment-\d+\s*"), "由更早的图谱范围"),
    (re.compile(r"fragment-\d+\s*范围"), "本图谱范围"),
    (re.compile(r"fragment-\d+"), "更早的图谱范围"),
    # 脚本文件名（`agent_detection.py`、`merge_graph.py`）是内部机件，正文里绝不会
    # 出现。审计的 INTERNAL_LATIN 把它算作内部标识，但渲染器原先不清，于是
    # 「渲染器已在输出时清洗」这句话对它不成立，脚本名会原样递给读者
    # （2026-09-14 在 `我的美女老师-1-100` 的 item_qiu_hun_suo.notes 上发现）。
    # 用通用规则而不是列举脚本名：脚本会增删，名单会腐烂。
    (re.compile(r"[A-Za-z][A-Za-z0-9_]*\.py"), ""),
    # 「本分片」按四种写法给四种结果，不能一条正则打天下：`本分片(?:范围)?内?`
    # 一律换成「本图谱范围内」，于是「早于本分片范围」成了「早于本图谱范围内」，
    # 「发生在本分片之前」成了「发生在本图谱范围内之前」——都是语病，而且是
    # 交付物里的语病。范围／内／引／裸用各留各的字。
    (re.compile(r"本分片范围"), "本图谱范围"),
    (re.compile(r"本分片内"), "本图谱范围内"),
    # 「本分片之前／之外」里的「本分片」后接方位词，换成「本图谱范围内」会成
    # 「本图谱范围内之前」。带方位词时只补到「本图谱范围」，让方位词自己接上。
    (re.compile(r"本分片(?=[之以])"), "本图谱范围"),
    (re.compile(r"本分片引"), "本图谱范围引"),
    (re.compile(r"本分片"), "本图谱范围内"),
    (re.compile(r"该分片"), "该图谱范围"),
    (re.compile(r"分片范围内"), "图谱范围内"),
    (re.compile(r"各分片"), "各图谱范围"),
    (re.compile(r"前序分片"), "更早的图谱范围"),
    # 裸「本片」也要收：留在正文里读者一样看不懂，且它是整理者视角的说法。
    # 但它必须与上面「本分片」同构地按四种写法分开处理。原先只有一条
    # `本片 -> 本图谱范围`，于是后接「范围」时被替换成「本图谱范围」再拼上原有的
    # 「范围」，成了「本图谱范围范围之外」——2026-09-14 在斗罗大陆 II 的 1-450 run
    # 上实测 13 条记录命中（sc_ch311_wang_qiuer_level.notes、ri_ch321_langyuan_hungu_shijian
    # 等）。范围／内／方位词／裸用各留各的字。
    (re.compile(r"本片范围"), "本图谱范围"),
    (re.compile(r"本片内"), "本图谱范围内"),
    (re.compile(r"本片(?=[之以])"), "本图谱范围"),
    (re.compile(r"本片"), "本图谱范围"),
    # 「范围范围」只可能是笔误：上游换词时把「本片」→「本图谱范围」之后又接了一个
    # 原有的「范围」，或分片作者直接写重。它不是内容，属本模块「折叠残留垃圾」的
    # 同一类（见模块 docstring 末段）。2026-09-14 在斗罗大陆 II 的 1-450 run 上实测
    # 3 条记录命中，且**已在源文本里**，清洗器不改就原样递给读者：
    # sc_ch311_wang_qiuer_level.notes「本图谱范围范围开始前锚点」、
    # sc_ch391_beibei_health.notes「发生在本图谱范围范围之前」、
    # fs_ch379_beibei_zhuangbing.interpretation「本图谱范围范围内未交代」。
    (re.compile(r"范围范围"), "范围"),
    # 交叉引用被摘掉 id 后剩「见 的伏笔回收」；空格是 id 的残留，用它当边界，
    # 免得把「撞见的」这类正常词也改掉。
    (re.compile(r"见\s+的"), "该"),
    (re.compile(r"的\s+(?=[，。；、）])"), ""),
    (re.compile(r"--id-map"), ""),
    (re.compile(r"主\s*Agent"), "整理者"),
)

# ---------------------------------------------------------------------------
# 4. Internal field names and English enum values.
# ---------------------------------------------------------------------------
FIELD_LABELS: dict[str, str] = {
    "consent_context": "互动性质",
    "inclusion_basis": "入选依据",
    "first_meeting_chapter": "首次相遇",
    "first_sex_chapter": "首次明确性关系",
    "first_sex_evidence_ids": "性关系证据",
    "ambiguity_started_chapter": "首次亲密／暧昧",
    "ambiguity_evidence_ids": "暧昧证据",
    "confirmed_chapter": "关系确认",
    "evidence_ids": "证据",
    "evidence": "证据",
    "progression": "推进记录",
    "relation_type": "关系类型",
    "romance_routes": "感情线",
    "review_issues": "待核问题",
    "state_change": "状态变化",
    "state_changes": "状态变化",
    "value": "数值",
    "label": "名称",
    "status": "状态",
    "notes": "说明",
    "quote": "原文",
    # 下面这些在分片注记里被当字段名用（`first_meeting 留空`、`不挂 target_id`），
    # 缺一条就在交付物里露出一个英文词。
    "first_meeting": "首次相遇",
    "first_chapter": "首次出现",
    "first_sex": "首次明确性关系",
    "confirmed": "关系确认",
    "participant_ids": "出场人物",
    "related_ids": "关联记录",
    "valid_from": "有效起始章",
    "valid_to": "有效终止章",
    "target_id": "目标实体",
    "character_id": "角色",
    "source_id": "来源记录",
    "confidence": "置信度",
    "facet": "维度",
    "route": "路线",
    "coalesce": "合并",
    "merge": "合并",
    "before": "变化前",
    "after": "变化后",
}

FALLBACK_ENUM_LABELS: dict[str, str] = {
    "mutual": "双方自愿",
    "one_sided": "单方面",
    "accidental": "意外",
    "coerced": "受迫",
    "forced": "暴力强迫",
    "ability_induced": "受能力影响",
    "altered_state": "意识不清",
    "uncertain": "待确认",
    "explicit": "原文明示",
    "inferred": "合理推断",
    "ambiguous": "暧昧中",
    "confirmed_relationship": "已确认关系",
    "mutual_interest": "相互有意",
    "romantic_ambiguity": "情感暧昧",
    "intimate_contact": "亲密接触",
    "explicit_intimate_proposal": "明确亲密提议",
    "repeated_attachment": "反复依恋",
    "intimate_psychology": "亲密心理／张力",
    "marriage": "婚姻",
    "betrothal": "婚约",
    "spouse_relation": "夫妻关系",
    "not_recorded": "尚未记录",
    "open": "未解",
    "resolved": "已回收",
    "partially_resolved": "部分回收",
    "false_lead": "误导线",
    "progressed": "已推进",
    "observed": "已观测",
    "suspected": "存疑",
}

# ---------------------------------------------------------------------------
# 5. Tidying — collapse what the deletions left behind.
# ---------------------------------------------------------------------------
TIDY: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"[ \t]{2,}"), " "),
    (re.compile(r"。{2,}"), "。"),
    (re.compile(r"，{2,}"), "，"),
    (re.compile(r"、{2,}"), "、"),
    (re.compile(r"[、,，]{1,}，"), "，"),
    (re.compile(r"，[、,，]+"), "，"),
    (re.compile(r"、\s*，"), "，"),
    (re.compile(r"（\s*）|\(\s*\)"), ""),
    # ID 列表被摘掉后括号里只剩连接词，整个括号连同「如…等」一起收掉
    (re.compile(r"（\s*(?:如|例如|含|包括)?\s*(?:等|等等)?\s*）"), ""),
    (re.compile(r"（\s*如\s*）"), ""),
    (re.compile(r"（\s*[，、]"), "（"),
    # 「见 ri_B06」里的 id 被摘掉后只剩一个孤零零的「见」。它现在指向空，连同
    # 前面的连接符一起收掉；用固定替换，避免反向引用在 JS 侧被当字面量输出。
    # 「（见 fs_f17_003）」这种括号里只剩「见」的，整个括号一起收。
    (re.compile(r"（\s*见\s*）|\(\s*见\s*\)"), ""),
    (re.compile(r"[，、,]\s*见\s*）"), "）"),
    (re.compile(r"[，、,]\s*见\s*\)"), ")"),
    (re.compile(r"[，、,]\s*见\s*）。"), "。）"),
    (re.compile(r"[，、,]\s*见\s*\)。"), ")。"),
    (re.compile(r"[，、,]\s*见\s*。"), "。"),
    (re.compile(r"[，、,]\s*见\s*；"), "；"),
    (re.compile(r"[，、,]\s*见\s*，"), "，"),
    # 交叉引用的 id 被摘掉后剩「另见。」「详见。」「实际状态见。」——「见」后面
    # 没有宾语，整句收尾就断了。只认这几个固定说法，避免命中「撞见。」这类正文。
    (re.compile(r"(?:另见|详见|参见|实际状态见|相关证据另见|证据另见)\s*([。；])"), r"\1"),
    (re.compile(r"，\s*。"), "。"),
    (re.compile(r"；\s*。"), "。"),
    (re.compile(r"。\s*，"), "。"),
    # 字段话术被摘掉后，句尾常剩下一个没有宾语的连接词：「…未给级数，故 value 为
    # null。」→「…未给级数，故。」；「…故 after 的 value 为 null。」→「…故 after 的。」。
    # 这类残句只能整段收掉——它已经不含任何实义内容。判据是连接词到句末之间**只剩
    # ASCII 字母数字下划线和空格**（可能还带一个「的」）：只要夹了一个汉字就说明它
    # 还带着内容（「，因此他败了。」），一律不动。
    (re.compile(r"[，、；]\s*(?:故|因此|所以|从而|于是)\s*[A-Za-z_0-9\s]{0,24}的?\s*(?=[。；])"), ""),
    (re.compile(r"^\s*[，、；。]+"), ""),
    (re.compile(r"\s+([，。；、）])"), r"\1"),
    (re.compile(r"([（])\s+"), r"\1"),
    (re.compile(r"\bnull\b"), "无"),
    (re.compile(r"\s{2,}"), " "),
    # 内部键被换成中文标签后，原来的英文词两侧的空格就留在汉字之间了
    # （`故 after 的 value 记 null` -> `故 变化后 的 数值 记 无`）。中文字之间的
    # 空格在交付物里是纯粹的噪声，两侧各收一次即可；放在 `null`→`无` 之后，
    # 否则「记 null」换完还剩一个空格。
    (re.compile(r"(?<=[\u4e00-\u9fff])[ \t]+"), ""),
    (re.compile(r"[ \t]+(?=[\u4e00-\u9fff])"), ""),
)

SENTENCE_SPLIT = re.compile(r"(?<=[。；！？])\s*")


def _is_process_sentence(sentence: str) -> bool:
    return any(p.search(sentence) for p in PROCESS_SENTENCES)


# 剥掉记账片段后，残句剩下的实义字符少于这个数就算整句都是记账。
# 取 8 是照中文实义片段的下限量：少于 8 字的基本只剩「见 ri_B06」这类残渣。
RESIDUE_MIN = 8

NON_WORD = re.compile(r"[^\w\u4e00-\u9fff]")


def _strip_process_fragments(sentence: str) -> str:
    """只删句子里的记账片段，返回剩下的实心内容。

    句子含记账不等于整句都是记账。逐条 `sub` 掉命中的片段后，残句若还有实义
    内容就保留下来 —— 否则一句「…属分片A，本分片仅按追述登记，见 ri_B06」会
    连带它前面的整段剧情追述一起消失。
    """
    trimmed = sentence
    for pattern in PROCESS_SENTENCES:
        trimmed = pattern.sub("", trimmed)
    trimmed = _sub_all(trimmed, TIDY)
    trimmed = trimmed.strip()
    # 句末标点必须留住：这一句后面还接着下一句，`strip("，、；")` 把「；」吃掉，
    # 两句就会粘成「…未出现对应周天数此为对已到层次的追述…」。
    tail = ""
    while trimmed and trimmed[-1] in "。；！？":
        tail = trimmed[-1] + tail
        trimmed = trimmed[:-1]
    trimmed = trimmed.strip().strip("，、；").strip()
    if len(NON_WORD.sub("", trimmed)) < RESIDUE_MIN:
        return ""
    return trimmed + tail


def _sub_all(text: str, pairs) -> str:
    for pattern, replacement in pairs:
        text = pattern.sub(replacement, text)
    return text


def strip_process_text(text: object, enum_labels: dict[str, str] | None = None) -> str:
    """Return the reader-facing form of one prose field.

    `enum_labels` maps raw enum values to the book's display wording; both renderers
    already build that map from the display vocabulary. Passing it turns
    `（altered_state，非其清醒意志）` into `（意识不清，非其清醒意志）` instead of leaving an
    English machine key mid-sentence.
    """
    if not isinstance(text, str) or not text.strip():
        return text if isinstance(text, str) else ""

    labels = dict(FALLBACK_ENUM_LABELS)
    if enum_labels:
        labels.update(enum_labels)
    whole_words = sorted(
        list(FIELD_LABELS.items()) + list(labels.items()), key=lambda kv: -len(kv[0])
    )

    original_length = len(text)
    text = FRAGMENT_TAG.sub("", text)

    kept: list[str] = []
    for raw_sentence in SENTENCE_SPLIT.split(text):
        if not raw_sentence or not raw_sentence.strip():
            continue
        sentence = FIXED_TABLE_NOTE.sub("", raw_sentence)
        if _is_process_sentence(sentence):
            # 只删记账片段，别把同句的内容一起带走；整句都是记账才丢。
            sentence = _strip_process_fragments(sentence)
            if not sentence:
                continue
        # Inside a surviving sentence: only neutral edits, never a cut.
        sentence = LEADING_ID_CLAUSE.sub("合并前", sentence)
        sentence = FRAGMENT_LOCAL_RUN.sub("", sentence)
        sentence = FRAGMENT_LOCAL_ID.sub("", sentence)
        for raw, label in whole_words:
            sentence = re.sub(rf"(?<![A-Za-z0-9_]){re.escape(raw)}(?![A-Za-z0-9_])", label, sentence)
        sentence = _sub_all(sentence, NEUTRALISE)
        kept.append(sentence)

    out = "".join(kept)
    out = _sub_all(out, TIDY)
    out = out.strip().strip("，、；").strip()
    # 整段几乎都是流程文字时，剩下的往往是一句断掉的残句（「何桃的感情线由…建立（，…」）。
    # 与其把残句递给读者，不如交还给调用方，用它自己的中性兜底文字。
    if out and original_length >= 60 and len(out) < original_length * 0.25:
        return ""
    return out if out else ""


def to_js() -> str:  # pragma: no cover - source emitter
    """Emit the same rule set as JavaScript for the dashboard's inline script.

    Generated from the definitions above so the page and the AI text cannot drift —
    two renderers disagreeing is the failure this project keeps hitting.
    """
    def js_re(source: str) -> str:
        return "/" + source.replace("/", r"\/") + "/g"

    def js_re_nog(source: str) -> str:
        # 只用于 `.test()` 的判断：带 `g` 的 RegExp 有状态，lastIndex 会在多次调用间
        # 推进，同一个正则第二次起就不再匹配。
        return "/" + source.replace("/", r"\/") + "/"

    def js_rep(replacement: str) -> str:
        # Python 用 \1，JS 用 $1；原样输出会把字面量 \1 写进正文。
        import re as _re
        return json.dumps(_re.sub(r"\\(\d+)", r"$\1", replacement), ensure_ascii=False)

    def js_pairs(pairs) -> str:
        return ", ".join(f"[{js_re(p.pattern)}, {js_rep(r)}]" for p, r in pairs)

    segments = ", ".join(js_re_nog(p.pattern) for p in PROCESS_SENTENCES)
    fields = json.dumps(FIELD_LABELS, ensure_ascii=False)
    fallback = json.dumps(FALLBACK_ENUM_LABELS, ensure_ascii=False)
    split = json.dumps(SENTENCE_SPLIT.pattern)

    return "\n".join([
        "// ---- 由 scripts/reader_prose.py 生成，勿手改 ----",
        f"const RP_PROCESS = [{segments}];",
        f"const RP_NEUTRALISE = [{js_pairs(NEUTRALISE)}];",
        f"const RP_TIDY = [{js_pairs(TIDY)}];",
        f"const RP_FIELDS = {fields};",
        f"const RP_ENUMS = {fallback};",
        f"const RP_SPLIT = {split};",
        f"const RP_FIXED_TABLE = {js_re(FIXED_TABLE_NOTE.pattern)};",
        f"const RP_FRAGMENT_TAG = {js_re(FRAGMENT_TAG.pattern)};",
        f"const RP_LEADING_ID = {js_re(LEADING_ID_CLAUSE.pattern)};",
        f"const RP_LOCAL_RUN = {js_re(FRAGMENT_LOCAL_RUN.pattern)};",
        f"const RP_LOCAL_ID = {js_re(FRAGMENT_LOCAL_ID.pattern)};",
        r"const RP_ESCAPE = /[.*+?^${}()|[\]\\]/g;",
        "function cleanReaderProse(text, enumLabels){",
        "  if(typeof text!=='string'||!text.trim())return typeof text==='string'?text:'';",
        "  const labels=Object.assign({},RP_ENUMS,enumLabels||{});",
        "  const pairs=Object.keys(RP_FIELDS).map(k=>[k,RP_FIELDS[k]])",
        "    .concat(Object.keys(labels).map(k=>[k,labels[k]]))",
        "    .sort((a,b)=>b[0].length-a[0].length);",
        "  const originalLength=text.length;",
        "  text=String(text).replace(RP_FRAGMENT_TAG,'');",
        "  const kept=[];",
        "  for(const raw of text.split(new RegExp(RP_SPLIT))){",
        "    if(!raw||!raw.trim())continue;",
        "    let s=raw.replace(RP_FIXED_TABLE,'');",
        "    if(RP_PROCESS.some(p=>p.test(s))){",
        "      // 与 Python 侧 _strip_process_fragments 同一条规则：只删记账片段，",
        "      // 别把同句的内容一起带走。整句都是记账时残句为空，才会被丢掉。",
        "      let t=s;",
        "      for(const p of RP_PROCESS)t=t.replace(p,'');",
        "      for(const [p,r] of RP_TIDY)t=t.replace(p,r);",
        "      // 与 Python 侧同一条规则：句末标点留住，否则这一句会和下一句粘在一起。",
        "      let tail='';",
        "      t=t.trim();",
        "      while(t&&'。；！？'.indexOf(t[t.length-1])>=0){tail=t[t.length-1]+tail;t=t.slice(0,-1);}",
        "      t=t.trim().replace(/^[，、；]+|[，、；]+$/g,'').trim();",
        f"      if(t.replace(/[^\\w\\u4e00-\\u9fff]/g,'').length>={RESIDUE_MIN})s=t+tail;",
        "      else continue;",
        "    }",
        "    s=s.replace(RP_LEADING_ID,'合并前');",
        "    s=s.replace(RP_LOCAL_RUN,'');",
        "    s=s.replace(RP_LOCAL_ID,'');",
        "    for(const [k,v] of pairs){",
        "      s=s.replace(new RegExp('(^|[^A-Za-z0-9_])'+k.replace(RP_ESCAPE,'\\\\$&')+'([^A-Za-z0-9_]|$)','g'),",
        "                   (m,a,b)=>a+v+b);",
        "    }",
        "    for(const [p,r] of RP_NEUTRALISE)s=s.replace(p,r);",
        "    kept.push(s);",
        "  }",
        "  let out=kept.join('');",
        "  // 与 Python 侧同一条规则：整段几乎都是流程文字时，剩下的往往是一句断掉的",
        "  // 残句，宁可返回空串，让调用方用它自己的中性兜底文字。",
        "  if(out&&originalLength>=60&&out.length<originalLength*0.25)return '';",
        "  for(const [p,r] of RP_TIDY)out=out.replace(p,r);",
        "  return out.trim().replace(/^[，、；]+|[，、；]+$/g,'').trim();",
        "}",
        "// ---- 生成结束 ----",
    ])


if __name__ == "__main__":  # pragma: no cover
    import sys

    if "--js" in sys.argv:
        print(to_js())
    else:
        for sample in (
            "[rom_su_ji 第1章] [rom_A01 第1章] 苏姬主动贴上来。本分片无第1章证据故 evidence 留空。请主 Agent 裁决。",
            "第31章苏姬主动躺进秦朝怀里（altered_state，非其清醒意志）；本条由主 Agent 从 1 条分片记录合并（rom_luo_qian），里程碑取最早有原文依据的章节。",
            "首次登场在第1章（依据固定实体表说明），本分片无第1章证据故 evidence 留空。",
            "本分片仅以书信现身：自居虎妖“小弟”，不与他妖往来。",
            "本分片按本 run 的既有写法新建 rom_f03_hetao / rom_f03_yanjie，只带本分片的新里程碑。",
            "只能用描述性命名的实体 ID（char_huo_muqin / char_gongjue / char_gongjue_furen）。",
        ):
            print("前:", sample)
            print("后:", strip_process_text(sample))
            print()
