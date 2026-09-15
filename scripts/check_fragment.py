#!/usr/bin/env python3
"""合并前对单个 fragment 做机械自检。

`validate_graph.py` 只在合并后发现问题，那时已经很难定位是哪一片写坏的；
`resolve_quotes.py` 只查引文能不能定位。这个脚本在两者之间补一道门禁，
把「必填字段齐全 / 引文单行逐字可查 / evidence_ids 不悬空 / 实体引用真实存在 /
before≠after / 失去类动作有 reason / 不引用未来章号 / 覆盖度等于范围 /
非正文单章都开了 review_issues / 亲密行为字段完整」一次查完，
让分片作者当场拿到可修的错误清单，而不是等合并后才炸。

必填字段表与 `validate_graph.py` 共用 `scripts/required_fields.py` 一份：门禁比
校验器弱，等于把失败推迟到合并之后（第 201-300 章那轮 30 条缺 `reason` 的
state_change 就是这么漏过去的）。

用法：
    python check_fragment.py --fragment <fragment.json> [--graph graph.json]
                             [--chapters-jsonl chapters.jsonl] [--json out.json]
退出码：0 全部通过；1 有 error。
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

LOSS_ACTIONS = {
    "lost", "transferred", "sealed", "forgotten", "left",
    "destroyed", "removed", "broken",
}

# 会进入渲染文本、可能引用章号的字段
PROSE_FIELDS = {
    "description", "notes", "interpretation", "observation", "summary",
    "reason", "resolution", "label",
}

ID_FIELDS = (
    "participant_ids", "related_entity_ids", "cause_event_ids",
    "consequence_event_ids", "change_ids",
)
SINGLE_ID_FIELDS = (
    "source_id", "target_id", "entity_id", "location_id",
    "cause_event_id", "payoff_event_id", "protagonist_id", "character_id", "item_id",
)

CHAPTER_TOKEN = re.compile(r"第\s*(\d+)\s*章")


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--fragment", required=True, type=Path)
    p.add_argument("--graph", type=Path, help="已合并图谱，用于校验跨片实体引用")
    p.add_argument("--chapters-jsonl", type=Path)
    p.add_argument(
        "--future-ceiling", type=int,
        help="散文可引用到的最大章号（分析上界）。缺省取图谱 chapter_end 与本片上界的较大者。",
    )
    p.add_argument(
        "--no-siblings", action="store_true",
        help="不扫同目录其他分片。合并后用（图谱已含全部分片），可显著加速。",
    )
    p.add_argument(
        "--strict-evidence-range", action="store_true",
        help=(
            "把「证据章号落在本片声明范围之外」升回 error。缺省只报警告：分区卫生是"
            "建议，真正的不变量是「证据落在分析覆盖范围内」，由 validate_graph.py 管。"
        ),
    )
    p.add_argument("--json", type=Path, help="把结果写成 JSON")
    return p.parse_args()


def norm(s: str) -> str:
    return re.sub(r"\s+", "", s.replace("\ufeff", ""))


class Checker:
    def __init__(self) -> None:
        self.errors: list[str] = []
        self.warnings: list[str] = []

    # `hint` 是可选的补充说明。加这个参数是因为文件里本来就有调用点写
    # `ck.err(msg, hint=...)`，而签名只收 `msg`——那是一颗定时炸弹：平时不报错，
    # 一旦真的命中该错误就抛 TypeError，把「一条清晰的错误」变成「一段 traceback」。
    def err(self, msg: str, hint: str | None = None) -> None:
        self.errors.append(f"{msg}（{hint}）" if hint else msg)

    def warn(self, msg: str, hint: str | None = None) -> None:
        self.warnings.append(f"{msg}（{hint}）" if hint else msg)


def collect_ids(frag: dict) -> dict[str, str]:
    """所有记录 id -> 所属类别，用于查重。"""
    seen: dict[str, str] = {}
    for key, value in frag.items():
        if not isinstance(value, list):
            continue
        for rec in value:
            if isinstance(rec, dict) and isinstance(rec.get("id"), str):
                if rec["id"] in seen:
                    seen[rec["id"]] = f"{seen[rec['id']]}+{key}"
                else:
                    seen[rec["id"]] = key
    return seen


def check_metadata(frag: dict, ck: Checker) -> tuple[int, int, list[int]]:
    meta = frag.get("metadata")
    if not isinstance(meta, dict):
        ck.err("缺少 metadata")
        return 0, 0, []
    start, end = meta.get("chapter_start"), meta.get("chapter_end")
    if not isinstance(start, int) or not isinstance(end, int):
        # 分片说明书（TASK-SPEC）要求的是 chapter_range: [起, 止]，不是
        # chapter_start/chapter_end；两者都认，否则正文分片会被误判成补充分片，
        # 连带把 range 检查与散文章号天花板一起跳掉（天花板会退回图谱的
        # chapter_end，于是本轮分片引用自己范围内的章号反而被报越界）。
        rng = meta.get("chapter_range")
        if isinstance(rng, list) and len(rng) == 2 and all(isinstance(c, int) for c in rng):
            start, end = rng[0], rng[1]
    analyzed = meta.get("analyzed_chapters")
    if not isinstance(start, int) or not isinstance(end, int):
        # 补充分片（等级回填、拟人判定等）不声明范围，只补记录，不承担覆盖度。
        ck.warn("补充分片：未声明 chapter_start / chapter_end / chapter_range，跳过覆盖度与范围检查")
        return 0, 0, []
    if analyzed is None:
        # merge_graph.py 把 analyzed_chapters 与 chapter_range 视为等价的覆盖声明
        # （见 merge_graph 的 analyzed 推导：两者取其一即可）。早期分片只写了
        # chapter_range，覆盖度照样成立；这里跟着推导，不要比管道契约更严，否则
        # 一批合法分片会被门禁误杀。
        analyzed = list(range(start, end + 1))
    if not isinstance(analyzed, list) or not all(isinstance(c, int) for c in analyzed):
        ck.err("metadata.analyzed_chapters 必须是整数数组")
        return start, end, []
    want = list(range(start, end + 1))
    if sorted(analyzed) != want:
        missing = sorted(set(want) - set(analyzed))
        extra = sorted(set(analyzed) - set(want))
        ck.err(
            f"analyzed_chapters 不等于范围 [{start}..{end}]"
            f"（缺 {missing[:12]}{'…' if len(missing) > 12 else ''}，"
            f"多 {extra[:12]}{'…' if len(extra) > 12 else ''}）"
        )
    if len(analyzed) != len(set(analyzed)):
        ck.err("analyzed_chapters 有重复章号")
    return start, end, analyzed


def check_evidence(
    frag: dict, ck: Checker, lines_of, start: int, end: int,
    owner_of=None, strict_range: bool = False,
) -> set[str]:
    scoped = end > 0
    ids: set[str] = set()
    for e in frag.get("evidence", []):
        if not isinstance(e, dict):
            ck.err("evidence 元素不是对象")
            continue
        eid = e.get("id")
        if not eid:
            ck.err("存在没有 id 的证据")
            continue
        if eid in ids:
            ck.err(f"证据 id 重复：{eid}")
        ids.add(eid)
        ch, quote = e.get("chapter"), e.get("quote")
        if not isinstance(ch, int):
            ck.err(f"{eid}: chapter 不是整数")
            continue
        if scoped and (ch < start or ch > end):
            # 分区卫生**不是**不变量：一片可以引用一段跨过自己边界的戏（对白落在
            # 下一章开头是常态），记录照样逐字正确。真正的不变量是「证据落在分析
            # 覆盖范围内」，那由 validate_graph.py 的 chapter_outside_coverage 管。
            # 把它当硬错误会把最早期三片（01—16 时代写的）11 条正确记录判死——
            # 门禁比管道契约更严，与 known-gaps A4 是同一类错。故缺省只告警，
            # 并在命中时点名该章属于哪一片，让新分片作者仍看得见分区信号。
            who = owner_of(ch) if owner_of else None
            if who:
                extra = f"；第 {ch} 章属 {who} 的范围，注意不要与它重复抽取"
            else:
                extra = "；该章不在任何分片的声明范围内"
            msg = f"{eid}: chapter={ch} 超出本片范围 {start}-{end}{extra}"
            if strict_range:
                ck.err(msg)
            else:
                ck.warn(msg)
        if not isinstance(quote, str) or not quote.strip():
            ck.err(f"{eid}: 缺少 quote")
            continue
        if not (15 <= len(quote) <= 60):
            ck.warn(f"{eid}: quote 长度 {len(quote)}，规范建议 15-60 字")
        lines = lines_of(ch)
        if lines is None:
            ck.err(f"{eid}: 找不到第 {ch} 章文本")
            continue
        nq = norm(quote)
        if not any(nq and nq in norm(ln) for ln in lines):
            ck.err(f"{eid}: 第{ch}章单行内找不到引文「{quote[:36]}」")
    return ids


def collect_sibling_evidence(path: Path) -> set[str]:
    """同目录其他分片已声明的证据 ID。

    补充分片（等级回填、拟人判定）按设计会引用别的分片声明的证据，
    所以「evidence_ids 必须指向本文件内证据」这条规则要放宽到兄弟分片。
    """
    ids: set[str] = set()
    for sibling in sorted(path.parent.glob("fragment-*.json")):
        if sibling.resolve() == path.resolve():
            continue
        try:
            data = json.loads(sibling.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        ids |= {e.get("id") for e in data.get("evidence", []) if isinstance(e, dict)}
    return ids


def collect_sibling_ranges(path: Path) -> dict[int, str]:
    """同目录其他分片声明的章节 → 分片名，用于给越界证据点名归属者。

    只读 metadata，不读记录，所以比 `collect_sibling_evidence()` 便宜。
    """
    owner: dict[int, str] = {}
    for sibling in sorted(path.parent.glob("fragment-*.json")):
        if sibling.resolve() == path.resolve():
            continue
        try:
            data = json.loads(sibling.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        meta = data.get("metadata") or {}
        rng = meta.get("chapter_range")
        lo, hi = meta.get("chapter_start"), meta.get("chapter_end")
        if isinstance(rng, list) and len(rng) == 2:
            lo, hi = rng[0], rng[1]
        if isinstance(lo, int) and isinstance(hi, int):
            for c in range(lo, hi + 1):
                owner.setdefault(c, sibling.name)
    return owner


def check_refs(frag: dict, ck: Checker, evidence_ids: set[str], known: set[str],
               state_ids: set[str] | None = None) -> None:
    # `change_ids`（schema.md 的 Relations 可选字段）指向的是**状态变化记录**，
    # 不是实体也不是事件。原先它和 participant_ids / related_entity_ids 共用同一个
    # `known`，而 `known` 只由 entities + events 构成，于是任何合法的 change_ids
    # 都必然报「引用未知实体」——2026-09-14 在《逆天邪神》的 fragment-04 上实测到
    # （rel_ch031_yulong_enemy_yunche 的 change_ids = ["sc_ch034_xiao_yulong_level_lost"]），
    # 每轮门禁都稳定复现 1 条 error，只能靠人记住它是伪报。
    # 现在按字段分流：change_ids 查 state_ids，其余 ID_FIELDS 仍查 known，
    # 所以这次修正不会顺带放宽 participant_ids 之类的校验。
    state_ids = state_ids if state_ids is not None else set()

    def walk(node, where: str) -> None:
        if isinstance(node, dict):
            for key, value in node.items():
                if key == "evidence_ids" and isinstance(value, list):
                    for ref in value:
                        if ref not in evidence_ids:
                            ck.err(f"{where}: evidence_id 悬空 {ref}")
                elif key == "change_ids" and isinstance(value, list):
                    for ref in value:
                        if isinstance(ref, str) and ref not in state_ids:
                            ck.err(f"{where}: change_ids 引用未知状态变化 {ref}")
                elif key in ID_FIELDS and isinstance(value, list):
                    for ref in value:
                        if isinstance(ref, str) and ref not in known:
                            ck.err(f"{where}: {key} 引用未知实体 {ref}")
                elif key in SINGLE_ID_FIELDS and isinstance(value, str):
                    if value not in known and key != "cause_event_id":
                        ck.err(f"{where}: {key} 引用未知对象 {value}")
                elif key == "cause_event_id" and isinstance(value, str):
                    pass  # 事件 id 在合并后校验
                elif isinstance(value, (dict, list)):
                    walk(value, where)
        elif isinstance(node, list):
            for item in node:
                walk(item, where)

    for key, value in frag.items():
        if not isinstance(value, list):
            continue
        for rec in value:
            if isinstance(rec, dict):
                walk(rec, rec.get("id") or key)


def record_ids(data: dict) -> set[str]:
    """一个分片／图谱文件里所有记录的 id（只取 ARRAY_KINDS 里的数组）。"""
    from required_fields import ARRAY_KINDS

    ids: set[str] = set()
    for array in ARRAY_KINDS:
        for record in data.get(array) or []:
            if isinstance(record, dict) and isinstance(record.get("id"), str):
                ids.add(record["id"])
    return ids


def check_required_fields(frag: dict, ck: Checker, elsewhere: set[str]) -> None:
    """必填字段：与 `validate_graph.py` 读同一张表（`scripts/required_fields.py`）。

    只在**本片是唯一声明者**时要求字段齐全（`elsewhere` 是「别的分片也声明了它」
    的 id 集合）。这条限制不是放水，而是分片协作的本来写法：一条记录由多个分片
    接力声明，`merge_value` 对列表取并集、对标量右覆盖，后一片专门补前一片没写的
    字段。本轮就有现成例子——

      · `rr_huo_yuhao_ju_zi`：fragment-26 只写 first_meeting_*，fragment-27 写
        status / inclusion_basis / notes 等；单看任何一片都「缺字段」。
      · `fs_ch097_yilaikexi_disanwuhun`：被 7 个分片接力补写。
      · `char_mingdetang_zhu`：fragment-27 只补名称与首次出现章。

    真正的缺陷是「全图谱只有这一片声明它，而它缺必填字段」——合并后没人再补。
    第 201-300 章那 30 条缺 `reason` 的 state_change 全部属于这一种，本检查因此
    能在合并前把它们拦下（当时门禁只查「无 reason 且无 cause_event_id 且无 notes」，
    它们带着 cause_event_id，于是静默放行，一路合进 graph.json 才炸）。

    两个刻意的差别，避免把正确写法误判成错误：

    - `first_sex_chapter: null` 是**正确**写法（分析范围内未成年时不作性化延伸），
      所以它只要求键存在，不要求有值——即 `REQUIRED_KEYS`。
    - `evidence.source_line_start` / `source_line_end` 由 `resolve_quotes.py` 从
      `quote` 反查回填，门禁跑在它之前，新写的证据必然还没有行号——即 `DERIVED`。
    - 空串与空列表按缺字段处理，与校验器的 `require()` 同语义；分片作者写
      `"reason": ""` 与不写这个键，在合并后是同一个错误，门禁里也应当是同一个。
    """
    from required_fields import (
        ARRAY_KINDS, CONFIDENCE, DERIVED, REQUIRED, REQUIRED_KEYS, is_blank,
    )

    for array, kind in ARRAY_KINDS.items():
        derived = set(DERIVED.get(kind, ()))
        for record in frag.get(array) or []:
            if not isinstance(record, dict):
                continue
            rid = record.get("id")
            if not isinstance(rid, str) or rid in elsewhere:
                continue
            if kind == "foreshadowing" and record.get("progression"):
                # 「给既有伏笔追加一条 progression」是本 skill 指定的推进写法
                # （见 references/analysis-protocol.md）：补充分片只写
                # `{id, progression:[...]}`，label / planted_chapter / observation /
                # interpretation / confidence 全由最初声明它的那一片提供。
                # 这种记录**按设计**就不带基础字段，不是「唯一声明者缺字段」。
                # 误报场景：`--no-siblings` 在合并**之前**跑（门禁第 0 步），
                # 而基础声明与 progression 都出自本轮新增分片，图谱里还没有它们，
                # 于是 `elsewhere` 看不到基础声明者 —— 2026-09-14 在
                # fragment-63/65/66 上就是这样被误判成 error 的。
                # 真的没人声明基础字段时，合并后 validate_graph.py 会用同一张
                # required_fields 表把它挡下，安全网仍在。
                #
                # 2026-09-14 收窄：原判据只看 `record.get("progression")` 是否存在，
                # 于是**同时**写齐基础字段与 progression 的记录也被警告——第 401-450 章
                # 的 fragment-44 有 5 条（维娜的『其他使命』、日月山脉活路、晨安假话、
                # 玉天龙三年侍卫、国师与穆恩的渊源）就是这样被误报的。它们自己就是
                # 声明者，`progression` 只是附带的推进记录。现在只有**缺基础字段**才警告，
                # 并把缺的字段名列进消息里；齐备的记录照常走下面的必填校验。
                missing = [f for f in REQUIRED.get(kind, ())
                           if f not in derived and is_blank(record.get(f))]
                if missing:
                    ck.warn(f"{rid}: 只带 progression 的伏笔补充推进（缺 {', '.join(missing)}），"
                            f"基础字段交给声明它的分片"
                            f"（若本轮无人声明该 id 的基础字段，合并后 validate_graph 会报错）")
                    continue
            for field in REQUIRED.get(kind, ()):
                if field in derived:
                    continue
                if is_blank(record.get(field)):
                    ck.err(f"{rid}: {kind}.{field} 为必填（本片是唯一声明者，合并后无人补）")
            for field in REQUIRED_KEYS.get(kind, ()):
                if field not in record:
                    ck.err(f"{rid}: {kind}.{field} 键缺失（值可为 null；本片是唯一声明者）")
            # `confidence` 的**取值**校验。原先门禁只把 confidence 当必填字段
            # （见 REQUIRED），从不检查取值，于是 `confidence: "suspected"`
            # ——那是 `foreshadowing.status` 的词，不是 confidence 的词——
            # 在每片自检里 0 error 全绿，一路合进 graph.json 才被
            # validate_graph.py 以 bad_confidence 拦下。2026-09-14《逆天邪神》
            # 的 fragment-25（fs_ch235_xue_gongzhu）实测踩到，整条 rebuild
            # 在第 5 步中止。合法集合与校验器共用 required_fields.CONFIDENCE 一份。
            confidence = record.get("confidence")
            if confidence is not None and confidence not in CONFIDENCE:
                ck.err(f"{rid}: {kind}.confidence「{confidence}」不在规范集内"
                       f"（只能是 {'/'.join(sorted(CONFIDENCE))}；"
                       f"若想表达「疑似」，那是 foreshadowing.status 的取值）")


def check_state_changes(frag: dict, ck: Checker) -> None:
    for sc in frag.get("state_changes", []):
        if not isinstance(sc, dict):
            continue
        sid = sc.get("id", "<无 id>")
        if "before" not in sc or "after" not in sc:
            ck.err(f"{sid}: state_change 必须同时有 before 与 after")
            continue
        if sc["before"] == sc["after"]:
            ck.err(f"{sid}: before 与 after 相同（{sc['before']!r}）")
        if sc.get("action") in LOSS_ACTIONS:
            if not sc.get("reason") and not sc.get("cause_event_id"):
                ck.err(f"{sid}: 失去类动作 {sc.get('action')} 缺 reason / cause_event_id")
        if not sc.get("reason") and not sc.get("cause_event_id") and not sc.get("notes"):
            ck.warn(f"{sid}: 无 reason / cause_event_id / notes")


def check_future_chapters(frag: dict, ck: Checker, ceiling: int) -> None:
    """散文里的章号引用，天花板是**分析上界**而不是本片上界。

    一条记录引用了本片之后、但仍在整本分析范围内的章号（例如一片 161-170 的
    review_issue 写着「第 171 章开战」），不是缺陷：那是回收信息，as-of 渲染层
    会按快照把它隐去，而数据层保留它是**要**的。真正的缺陷是引用分析范围之外的
    章号——那是还没被抽取、无从证实的未来。
    """
    if ceiling <= 0:
        return
    def walk(node, where: str) -> None:
        if isinstance(node, dict):
            for key, value in node.items():
                if isinstance(value, str) and key in PROSE_FIELDS:
                    for m in CHAPTER_TOKEN.finditer(value):
                        if int(m.group(1)) > ceiling:
                            ck.err(
                                f"{where}.{key}: 引用了分析范围之外的章号 第{m.group(1)}章"
                                f"（上界 {ceiling}）"
                            )
                elif isinstance(value, (dict, list)):
                    walk(value, where)
        elif isinstance(node, list):
            for item in node:
                walk(item, where)

    for key, value in frag.items():
        if isinstance(value, list):
            for rec in value:
                if isinstance(rec, dict):
                    walk(rec, rec.get("id") or key)


def check_romance(frag: dict, ck: Checker, ceiling: int, evidence_ids: set[str]) -> None:
    """感情线里程碑只做结构检查，不预设任何年龄或尺度门槛。

    这里曾有一条「分析范围内主角群未成年，first_sex_chapter 必须为 null」的规则，
    与 validate_graph 的同类限制一起移除。里程碑的取值由原文决定。

    `evidence_ids` 是**宽集合**（本片 + 兄弟分片 + 已合并图谱），不是本片自己的证据表：
    一条感情线会在多个分片里被反复声明，里程碑的章号与证据往往由最早看见它的那一片
    写定，后面的分片只做重申。要求证据必须落在重申者自己的文件里，会把这种正常写法
    判成错误（第 78-88 片的 rr_huo_yuhao_ma_xiaotao 引用第 17 章证据即是一例）。
    """
    for rr in frag.get("romance_routes", []):
        if not isinstance(rr, dict):
            continue
        rid = rr.get("id", "<无 id>")
        for chapter_field, evidence_field in (
            ("first_meeting_chapter", "first_meeting_evidence_ids"),
            ("ambiguity_started_chapter", "ambiguity_evidence_ids"),
            ("confirmed_chapter", "confirmed_evidence_ids"),
            ("first_sex_chapter", "first_sex_evidence_ids"),
        ):
            value = rr.get(chapter_field)
            refs = rr.get(evidence_field) or []
            if value is None and refs:
                ck.err(f"{rid}: {chapter_field} 为 null 时 {evidence_field} 必须为空")
            if isinstance(value, int) and not refs:
                ck.err(f"{rid}: {chapter_field} 有值时需要 {evidence_field}")
            for ref in refs:
                if ref not in evidence_ids:
                    ck.err(f"{rid}: {evidence_field} 引用了未知证据 {ref}")


def check_intimacy(frag: dict, ck: Checker, evidence_ids: set[str]) -> None:
    """亲密行为自检：字段、行为类型、参与者、互动性质、证据。

    分片阶段就挡住坏记录，比等到合并后再回查便宜得多。
    """
    from intimacy_types import (
        CONSENT_CONTEXTS,
        EJACULATION_SITES,
        INTIMACY_TYPES,
        canonical_intimacy_type,
        has_participant,
    )

    ev_ids = evidence_ids
    for ia in frag.get("intimate_acts", []):
        if not isinstance(ia, dict):
            ck.err("intimate_acts 中存在非对象记录")
            continue
        rid = ia.get("id", "<无 id>")
        for field in ("id", "chapter", "act_type", "description", "confidence"):
            if ia.get(field) in (None, "", []):
                ck.err(f"{rid}: intimate_acts.{field} 为必填")
        act_type = ia.get("act_type")
        if isinstance(act_type, str) and act_type.strip():
            if canonical_intimacy_type(act_type) not in INTIMACY_TYPES:
                ck.err(f"{rid}: act_type「{act_type}」不在规范集内（见 scripts/intimacy_types.py）")
        if not has_participant(ia):
            ck.err(f"{rid}: 至少要有一个 initiator_ids / recipient_ids / observer_ids")
        consent = ia.get("consent")
        if consent is not None and consent not in CONSENT_CONTEXTS:
            ck.err(f"{rid}: consent「{consent}」不合法")
        site = ia.get("ejaculation_site")
        if site is not None and site not in EJACULATION_SITES:
            ck.err(f"{rid}: ejaculation_site「{site}」不合法")
        refs = ia.get("evidence_ids") or []
        if not refs:
            ck.err(f"{rid}: intimate_acts 需要自己的证据，不能借用相邻事件的证据")
        for ref in refs:
            if ref not in ev_ids:
                ck.err(f"{rid}: 证据 {ref} 不在本分片 evidence 中")


def check_level_conversions(frag: dict, ck: Checker, evidence_ids: set[str]) -> None:
    """等级换算自检：字段、关系枚举、两端必须钉住值、必须落在本分片章节内。

    换算的全部价值在于「原文这么说过」，所以这里先把结构化错误挡掉，
    至于「原文到底有没有这么说」只能靠证据引用与人工回看。
    """
    from level_conversions import (
        CONVERSION_RELATIONS,
        canonical_relation,
        endpoint_has_position,
        range_is_sane,
    )

    records = frag.get("level_conversions")
    if records in (None, [], {}):
        return
    if not isinstance(records, list):
        ck.err("level_conversions 必须是数组")
        return

    ev_ids = evidence_ids
    for rec in records:
        if not isinstance(rec, dict):
            ck.err("level_conversions 中存在非对象记录")
            continue
        rid = rec.get("id", "<无 id>")
        for field in ("id", "chapter", "from", "to", "relation", "description"):
            if rec.get(field) in (None, "", [], {}):
                ck.err(f"{rid}: level_conversions.{field} 为必填")
        relation = canonical_relation(rec.get("relation"))
        if relation and relation not in CONVERSION_RELATIONS:
            ck.err(f"{rid}: relation「{rec.get('relation')}」不在规范集内（见 scripts/level_conversions.py）")
        for side in ("from", "to"):
            endpoint = rec.get(side)
            if not isinstance(endpoint, dict):
                ck.err(f"{rid}: {side} 必须是对象，且含 axis_id")
                continue
            if endpoint.get("axis_id") in (None, ""):
                ck.err(f"{rid}: {side}.axis_id 为必填")
            if not endpoint_has_position(endpoint):
                ck.err(f"{rid}: {side} 没钉住任何值，至少要给 value、range 或 label")
            band = endpoint.get("range")
            if band is not None and not range_is_sane(band):
                ck.err(f"{rid}: {side}.range 必须是两个递增数字")
            number = endpoint.get("value")
            if number is not None and (isinstance(number, bool) or not isinstance(number, (int, float))):
                ck.err(f"{rid}: {side}.value 必须是数字或 null")
        refs = rec.get("evidence_ids") or []
        if not refs:
            ck.err(f"{rid}: 换算记录必须带证据——没有引文的换算就是推断")
        for ref in refs:
            if ref not in ev_ids:
                ck.err(f"{rid}: 引用了本分片不存在的证据 {ref}",
                       hint="跨分片的证据要写进本分片的 evidence 数组，或改用本分片内的引文")


def check_character_traits(frag: dict, ck: Checker, evidence_ids: set[str], ceiling: int) -> None:
    """人物特征自检：分面枚举、断言质量、指向人物、落在本片章节内。

    三条都对应会一路漏到读者眼前的问题：分面写成听不懂的词会让筛选失效；
    断言写成标签（「漂亮」）等于没写；证据引用错了则整条无法回看。
    """
    from character_traits import FACETS, canonical_facet, statement_is_substantive

    records = frag.get("character_traits")
    if records in (None, [], {}):
        return
    if not isinstance(records, list):
        ck.err("character_traits 必须是数组")
        return

    chars = {
        r.get("id") for r in frag.get("entities", [])
        if isinstance(r, dict) and r.get("type") == "character"
    }
    for rec in records:
        if not isinstance(rec, dict):
            ck.err("character_traits 中存在非对象记录")
            continue
        rid = rec.get("id", "<无 id>")
        for field in ("id", "entity_id", "facet", "statement", "chapter", "evidence_ids", "confidence"):
            if rec.get(field) in (None, "", [], {}):
                ck.err(f"{rid}: character_traits.{field} 为必填")

        facet = canonical_facet(rec.get("facet"))
        if facet not in FACETS:
            ck.err(f"{rid}: 分面 {rec.get('facet')!r} 不在规范集内（{sorted(FACETS)}）")

        # 「漂亮」「高冷」这类标签对读者没有增量 —— 图谱里已有 summary 承担概括，
        # 特征值要具体到能看见（「个子高，右眉有一道旧疤」）。
        if not statement_is_substantive(rec):
            ck.err(f"{rid}: statement 必须是一句可读的描述，不能是标签或过短的词")

        eid = rec.get("entity_id")
        # 人物实体可以由兄弟分片声明，这里只对「本片有实体表却没这个人」提醒。
        if eid and chars and eid not in chars:
            ck.warn(f"{rid}: entity_id {eid} 不在本片人物实体里（若由兄弟分片声明可忽略）")

        chapter = rec.get("chapter")
        if isinstance(chapter, int) and ceiling and chapter > ceiling:
            ck.err(f"{rid}: chapter {chapter} 超出本片章节范围（上限 {ceiling}）")

        for ref in rec.get("evidence_ids") or []:
            if ref not in evidence_ids:
                ck.err(f"{rid}: 证据 {ref} 不在本片 evidence 里")


def check_chapter_summaries(frag: dict, ck: Checker, evidence_ids: set[str], ceiling: int) -> None:
    """章节梗概自检：一章一条、落在本片章节内、summary 够长。

    「一章一条」是硬要求：同章两条会让读者看到两份摘要，而两份都带着证据，
    谁也判不了该信哪条。
    """
    records = frag.get("chapter_summaries")
    if records in (None, [], {}):
        return
    if not isinstance(records, list):
        ck.err("chapter_summaries 必须是数组")
        return

    seen: dict[int, str] = {}
    for rec in records:
        if not isinstance(rec, dict):
            ck.err("chapter_summaries 中存在非对象记录")
            continue
        rid = rec.get("id", "<无 id>")
        for field in ("id", "chapter", "summary", "evidence_ids"):
            if rec.get(field) in (None, "", [], {}):
                ck.err(f"{rid}: chapter_summaries.{field} 为必填")

        chapter = rec.get("chapter")
        if isinstance(chapter, int):
            if chapter in seen:
                ck.err(f"{rid}: 第 {chapter} 章已有梗概 {seen[chapter]}，一章只能一条")
            else:
                seen[chapter] = rid
            if ceiling and chapter > ceiling:
                ck.err(f"{rid}: chapter {chapter} 超出本片章节范围（上限 {ceiling}）")

        summary = rec.get("summary")
        if isinstance(summary, str) and len(summary.strip()) < 20:
            ck.warn(f"{rid}: summary 只有 {len(summary.strip())} 字，三到六句才够读者扫读")

        for ref in rec.get("evidence_ids") or []:
            if ref not in evidence_ids:
                ck.err(f"{rid}: 证据 {ref} 不在本片 evidence 里")


def check_item_roles(frag: dict, ck: Checker, evidence_ids: set[str]) -> None:
    """物品角色自检：角色、动作、有效期与证据均使用共享 schema 口径。"""
    records = frag.get("item_roles")
    if records in (None, [], {}):
        return
    if not isinstance(records, list):
        ck.err("item_roles 必须是数组")
        return
    roles = {"owner", "holder", "user", "custodian"}
    actions = {"gained", "lost", "transferred", "confirmed"}
    for rec in records:
        if not isinstance(rec, dict):
            ck.err("item_roles 中存在非对象记录")
            continue
        rid = rec.get("id", "<无 id>")
        if rec.get("role") not in roles:
            ck.err(f"{rid}: item_roles.role 非法：{rec.get('role')}")
        if rec.get("action") not in actions:
            ck.err(f"{rid}: item_roles.action 非法：{rec.get('action')}")
        start, end = rec.get("valid_from"), rec.get("valid_to")
        if isinstance(start, int) and isinstance(end, int) and start > end:
            ck.err(f"{rid}: item_roles.valid_from 大于 valid_to")
        for ref in rec.get("evidence_ids") or []:
            if ref not in evidence_ids:
                ck.err(f"{rid}: 证据 {ref} 不在本片 evidence 里")


def check_story_arcs(frag: dict, ck: Checker, evidence_ids: set[str], ceiling: int) -> None:
    """Validate overlapping story-arc records without forcing exclusivity."""
    statuses = {"open", "active", "paused", "resolved", "uncertain"}
    phases = {
        "setup", "development", "escalation", "turning_point", "climax",
        "resolution", "aftermath", "interlude", "recurring", "uncertain",
    }
    records = frag.get("story_arcs")
    if records in (None, [], {}):
        return
    if not isinstance(records, list):
        ck.err("story_arcs 必须是数组")
        return
    seen: set[str] = set()
    for rec in records:
        if not isinstance(rec, dict):
            ck.err("story_arcs 中存在非对象记录")
            continue
        rid = rec.get("id", "<无 id>")
        if rid in seen:
            ck.err(f"{rid}: story_arcs id 重复")
        seen.add(rid)
        for field in ("id", "title", "chapter_start", "status", "evidence_ids"):
            if rec.get(field) in (None, "", [], {}):
                ck.err(f"{rid}: story_arcs.{field} 为必填")
        start, end = rec.get("chapter_start"), rec.get("chapter_end")
        if isinstance(start, int) and isinstance(end, int) and start > end:
            ck.err(f"{rid}: chapter_start 大于 chapter_end")
        if ceiling and isinstance(start, int) and start > ceiling:
            ck.err(f"{rid}: chapter_start {start} 超出范围上限 {ceiling}")
        if ceiling and isinstance(end, int) and end > ceiling:
            ck.err(f"{rid}: chapter_end {end} 超出范围上限 {ceiling}")
        if rec.get("parent_arc_id") == rid:
            ck.err(f"{rid}: parent_arc_id 不能指向自身")
        if rec.get("status") not in statuses:
            ck.err(f"{rid}: story_arcs.status 非法：{rec.get('status')}")
        if rec.get("phase") is not None and rec.get("phase") not in phases:
            ck.err(f"{rid}: story_arcs.phase 非法：{rec.get('phase')}")
        for field in ("event_ids", "entity_ids", "turning_point_ids"):
            if rec.get(field) is not None and not isinstance(rec.get(field), list):
                ck.err(f"{rid}: story_arcs.{field} 必须是数组")
        for ref in rec.get("evidence_ids") or []:
            if ref not in evidence_ids:
                ck.err(f"{rid}: 证据 {ref} 不在本片 evidence 里")


def check_non_narrative(frag: dict, ck: Checker, notes: list[int], analyzed: list[int]) -> None:
    flagged = set()
    for ri in frag.get("review_issues", []):
        if isinstance(ri, dict) and ri.get("category") == "non_narrative_chapter":
            ch = ri.get("chapter")
            if isinstance(ch, int):
                flagged.add(ch)
    for ch in notes:
        if ch not in analyzed:
            ck.err(f"非正文单章 {ch} 未出现在 analyzed_chapters")
        if ch not in flagged:
            ck.err(f"非正文单章 {ch} 未开 non_narrative_chapter 的 review_issues")
        for key in ("entities", "events", "relations", "state_changes", "foreshadowing"):
            for rec in frag.get(key, []):
                if isinstance(rec, dict) and rec.get("chapter") == ch:
                    ck.err(f"非正文单章 {ch} 不应有 {key} 记录（{rec.get('id')}）")
        for e in frag.get("evidence", []):
            if isinstance(e, dict) and e.get("chapter") == ch:
                ck.err(f"非正文单章 {ch} 不应有证据（{e.get('id')}）")


def check_non_narrative_issues(frag: dict, ck: Checker, analyzed: list[int]) -> None:
    """反向检查：标了 `non_narrative_chapter` 的 issue，其章在本分片内必须是零记录。

    `check_non_narrative()` 只从「计划器说这章非正文」单向出发——它要求计划器点名的章
    必须有 issue 且零记录，但**没有**要求「一条 non_narrative_chapter 的 issue 必须对应
    零记录的章」。于是「正文章被误标成非正文」一路放行：2026-09-14 的
    `ri_ch296_author_note` 就是这样——第 296 章有 3 条 event、11 条 evidence、2 条
    relation，却挂着 `non_narrative_chapter`，而它自己的 description 还写着
    「故按剧情章处理，未按 non_narrative_chapter 排除」，字段与内容自相矛盾。

    代价不是少一个数字：`正文章 = analyzed_chapters − non_narrative_chapter` 会算少一章，
    而且该分类在读者界面渲染成「作者感言单章」，会在待核问题里与「本章有完整剧情」打架。
    正确写法是 `author_note`（正文完整、章内另附作者语）。

    只检查落在本分片 `analyzed_chapters` 里的章：章是连续切分的，一章只有一个拥有者，
    越界的章交给拥有它的那片报，避免跨分片误报。
    """
    owned = set(analyzed)
    for ri in frag.get("review_issues", []):
        if not isinstance(ri, dict) or ri.get("category") != "non_narrative_chapter":
            continue
        ch = ri.get("chapter")
        if not isinstance(ch, int) or ch not in owned:
            continue
        for key in ("entities", "events", "relations", "state_changes", "foreshadowing"):
            for rec in frag.get(key, []):
                if isinstance(rec, dict) and rec.get("chapter") == ch:
                    ck.err(
                        f"{ri.get('id')}: 第 {ch} 章标为 non_narrative_chapter，"
                        f"本片却有 {key} 记录（{rec.get('id')}）",
                        hint="正文章含作者语请用 category=author_note，"
                             "non_narrative_chapter 只用于整章排除、零抽取的章",
                    )
        for e in frag.get("evidence", []):
            if isinstance(e, dict) and e.get("chapter") == ch:
                ck.err(
                    f"{ri.get('id')}: 第 {ch} 章标为 non_narrative_chapter，"
                    f"本片却有证据（{e.get('id')}）",
                    hint="正文章含作者语请用 category=author_note",
                )


def main() -> int:
    args = parse_args()
    ck = Checker()
    try:
        frag = json.loads(args.fragment.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        print(f"JSON 解析失败：{exc}", file=sys.stderr)
        return 1

    known: set[str] = {r.get("id") for r in frag.get("entities", []) if isinstance(r, dict)}
    # cause_event_ids / consequence_event_ids / payoff_event_id 指向事件，
    # 事件可以在本文件、兄弟分片或已合并图谱里声明。
    known |= {r.get("id") for r in frag.get("events", []) if isinstance(r, dict)}
    # change_ids 指向状态变化记录，单独一套（见 check_refs 的说明）。
    state_ids: set[str] = {r.get("id") for r in frag.get("state_changes", [])
                           if isinstance(r, dict)}
    # 别的分片声明了哪些 id：用于判断「本片是不是这条记录的唯一声明者」。
    # 一条记录被多片接力声明（后一片补前一片没写的字段）是正常写法，
    # 只有唯一声明者才必须自己把必填字段写全——详见 check_required_fields()。
    elsewhere: set[str] = set()
    graph = None
    graph_end = 0
    sibling_end = 0
    if not args.no_siblings:
        for sibling in sorted(args.fragment.parent.glob("fragment-*.json")):
            if sibling.resolve() == args.fragment.resolve():
                continue
            try:
                data = json.loads(sibling.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                continue
            known |= {r.get("id") for r in data.get("entities", []) if isinstance(r, dict)}
            known |= {r.get("id") for r in data.get("events", []) if isinstance(r, dict)}
            state_ids |= {r.get("id") for r in data.get("state_changes", [])
                          if isinstance(r, dict)}
            elsewhere |= record_ids(data)
            sib_meta = data.get("metadata") or {}
            sib_range = sib_meta.get("chapter_range")
            sib_hi = sib_meta.get("chapter_end")
            if isinstance(sib_range, list) and len(sib_range) == 2 and isinstance(sib_range[1], int):
                sib_hi = sib_range[1]
            if isinstance(sib_hi, int):
                sibling_end = max(sibling_end, sib_hi)
    if args.graph and args.graph.exists():
        graph = json.loads(args.graph.read_text(encoding="utf-8"))
        known |= {r.get("id") for r in graph.get("entities", []) if isinstance(r, dict)}
        known |= {r.get("id") for r in graph.get("events", []) if isinstance(r, dict)}
        state_ids |= {r.get("id") for r in graph.get("state_changes", [])
                      if isinstance(r, dict)}
        graph_end = graph.get("metadata", {}).get("chapter_end") or 0
        if args.no_siblings:
            # 合并后跑（--no-siblings）时图谱已是全量真值，它就是「别处也声明了它」
            # 的依据；分片阶段则不能把图谱算进去——图谱本身就是被校验的合并结果，
            # 一旦算进去，所有记录都「已被别处声明」，这道检查等于关掉。
            elsewhere |= record_ids(graph)

    index: dict[int, dict] = {}
    if args.chapters_jsonl and args.chapters_jsonl.exists():
        for line in args.chapters_jsonl.read_text(encoding="utf-8").splitlines():
            if line.strip():
                r = json.loads(line)
                index[r["chapter"]] = r

    cache: dict[int, list[str] | None] = {}

    def lines_of(ch: int):
        if ch not in cache:
            rec = index.get(ch)
            if not rec:
                cache[ch] = None
            else:
                p = Path(rec["text_path"])
                cache[ch] = p.read_text(encoding="utf-8").splitlines() if p.exists() else None
        return cache[ch]

    start, end, analyzed = check_metadata(frag, ck)
    ids = collect_ids(frag)
    for rid, kinds in ids.items():
        if "+" in kinds:
            ck.err(f"id 跨类别重复：{rid}（{kinds}）")
    ev_ids = check_evidence(
        frag, ck, lines_of, start, end,
        owner_of=(collect_sibling_ranges(args.fragment) if not args.no_siblings else {}).get,
        strict_range=args.strict_evidence_range,
    )
    ev_ids |= collect_sibling_evidence(args.fragment)
    if graph is not None:
        ev_ids |= {e.get("id") for e in graph.get("evidence", []) if isinstance(e, dict)}
    check_refs(frag, ck, ev_ids, known, state_ids)
    check_required_fields(frag, ck, elsewhere)
    check_state_changes(frag, ck)
    # 散文章号的天花板是**整本已抽取范围**的上界，不是本片上界：一片
    # 461-470 写「第十掌琉璃要到第494章才写明」是回收信息，不是泄露未来。
    # 默认取本片、兄弟分片、已合并图谱三者上界的最大值；--future-ceiling 可覆盖。
    ceiling = args.future_ceiling or max(end, graph_end, sibling_end)
    check_future_chapters(frag, ck, ceiling)
    check_romance(frag, ck, ceiling, ev_ids)
    check_intimacy(frag, ck, ev_ids)
    check_level_conversions(frag, ck, ev_ids)
    check_character_traits(frag, ck, ev_ids, ceiling)
    check_chapter_summaries(frag, ck, ev_ids, ceiling)
    check_item_roles(frag, ck, ev_ids)
    check_story_arcs(frag, ck, ev_ids, ceiling)

    # 计划文件按章段自动匹配，**不要写死文件名**。此前这里硬编码
    # `plan-201-300.json`，于是覆盖 301-400 的分片一个都匹配不上，
    # `check_non_narrative()` 被静默跳过——闸门看起来在跑，其实少了一道。
    # 一个 run 可以同时留着多份 plan（201-300、301-400…），按章段取即可。
    plan_dir = Path(args.fragment).resolve().parent.parent / "_context"
    matched = False
    overlapped = False
    for plan_path in sorted(plan_dir.glob("plan-*.json")):
        try:
            items = json.loads(plan_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(items, list):
            continue
        for item in items:
            if item.get("chapter_start") == start and item.get("chapter_end") == end:
                check_non_narrative(frag, ck, item.get("non_narrative_chapters", []), analyzed)
                matched = True
            elif (item.get("chapter_start") or 0) <= end and (item.get("chapter_end") or 0) >= start:
                overlapped = True
    # 只在「本应有计划却对不上」时提醒。1-200 章的分片切片早于 plan_fragments.py，
    # 本来就没有计划文件，逐个刷警告只会训练人忽略警告。
    if not matched and overlapped:
        ck.warn(
            f"有计划文件与第 {start}-{end} 章重叠，但没有一条章段精确匹配，"
            "非正文单章检查未执行"
        )

    # 反向检查与计划文件无关，任何分片都要跑
    check_non_narrative_issues(frag, ck, analyzed)

    name = args.fragment.name
    counts = {
        k: len(v) for k, v in frag.items()
        if isinstance(v, list)
    }
    print(f"== {name} ==")
    print("  记录数：" + "  ".join(f"{k}={v}" for k, v in counts.items()))
    for w in ck.warnings:
        print(f"  [warn] {w}")
    for e in ck.errors:
        print(f"  [ERROR] {e}")
    print(f"  结果：{len(ck.errors)} error / {len(ck.warnings)} warning")

    if args.json:
        args.json.write_text(
            json.dumps(
                {"fragment": name, "counts": counts,
                 "errors": ck.errors, "warnings": ck.warnings},
                ensure_ascii=False, indent=2,
            ),
            encoding="utf-8",
        )
    return 1 if ck.errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
