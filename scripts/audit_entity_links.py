#!/usr/bin/env python3
"""Report entities that declare a bearer or an identity but have no relation to it.

A knowledge graph can be structurally perfect and still leave a reader unable to answer
"whose is this?". Two patterns cause it, and neither is caught by `validate_graph.py`:

- **A name that declares its bearer.** `刘弈的右手`, `冷沫的光剑刀柄`, `陈才的召唤异能`,
  `红领巾侠（刘弈的除妖伪装身份）` — the entity's own name says who it belongs to, but no
  relation links the two, so the item/skill shelf shows 归属未明 and the concept sits
  orphaned next to the person it belongs to.
- **An identity that declares nothing.** `血皇` is 刘弈's cover name, and the string
  contains no hint of him. Only a human can spot it — but the graph does record that it is
  the subject of a clue whose label is about an identity (`面具男子的公众称号血皇`), so the
  clue is the signal to look at.

A third pattern is the extreme case: **no relation at all.** An entity can carry
evidence and still have no edge to the story, in which case a reader can neither
find it from anywhere nor tell where it belongs. A *character* in that state is
always a defect — someone wrote a quote for them, so they are in the book, and the
graph should be able to say how. A skill, item, or location can legitimately stand
alone (a background place never revisited needs no owner), so those are reported
separately and are a coverage observation rather than a fault.

A second personality is the same problem one type over: `fragment-36` in the 我的狐仙老婆
run exists because 腹黑刘弈 had no edge to 刘弈. The difference is what to do about it —
an identity with nothing acting behind it (a cover name, a codename) keeps its own type
and gains a relation; a self-acting personality becomes its own `character`.

This is a report, not a gate: it exits 0 and lists candidates for human judgement. A
hit is not automatically an error — `张三的传说` as a concept is not owned by 张三 — so
resolve each hit by adding the edge, or by recording why it needs none.

    python scripts/audit_entity_links.py --graph runs/<book>/graph.json
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path


# A name containing 「X的」 where X is a character is an explicit ownership claim.
POSSESSIVE = "的"
# Words that mark an entity as somebody's identity rather than a thing in the world.
IDENTITY_WORDS = ("身份", "称号", "代号", "化身", "伪装", "马甲", "真身")


def names_of(entity: dict) -> list[str]:
    names = [str(entity.get("name") or "")]
    names.extend(str(alias) for alias in (entity.get("aliases") or []))
    return [name for name in names if name]


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--graph", required=True, type=Path)
    parser.add_argument("--json", type=Path, help="Optional path to write the report as JSON")
    parser.add_argument(
        "--acknowledged", type=Path, default=None,
        help="已人工判定的命中清单（JSON，与 rollup_levels.py 共用一份文件）。"
             "列入清单的项照旧列出但不计入待判断数；key 形如 `identity_clue:concept_tianbang`。",
    )
    args = parser.parse_args()

    graph = json.loads(args.graph.resolve().read_text(encoding="utf-8"))
    entities = [e for e in graph.get("entities", []) if isinstance(e, dict) and e.get("id")]
    relations = [r for r in graph.get("relations", []) if isinstance(r, dict)]
    characters = [e for e in entities if e.get("type") == "character"]

    def linked(left: str, right: str) -> bool:
        return any({r.get("source_id"), r.get("target_id")} == {left, right} for r in relations)

    def linked_to_any_character(entity_id: str) -> bool:
        return any(linked(entity_id, c["id"]) for c in characters)

    # Longest names first so 刘弈的爷爷 is matched as itself, not as 刘弈 plus 的爷爷.
    char_names = sorted(
        ((name, c["id"]) for c in characters for name in names_of(c) if len(name) >= 2),
        key=lambda pair: len(pair[0]),
        reverse=True,
    )

    bearer_claimed: list[dict] = []
    identity_claimed: list[dict] = []
    identity_clue: list[dict] = []

    # Everything the graph already points at. An entity that appears in none of
    # these and in no relation is unreachable from the reader's side.
    referenced: set[str] = set()
    for relation in relations:
        for key in ("source_id", "target_id"):
            if relation.get(key):
                referenced.add(relation[key])
    for event in graph.get("events", []):
        if not isinstance(event, dict):
            continue
        for key in ("participant_ids", "cause_event_ids", "consequence_event_ids"):
            for item in event.get(key) or []:
                referenced.add(item)
    for change in graph.get("state_changes", []):
        if not isinstance(change, dict):
            continue
        for key in ("entity_id", "target_id"):
            if change.get(key):
                referenced.add(change[key])
    for clue in graph.get("foreshadowing", []):
        if not isinstance(clue, dict):
            continue
        for item in clue.get("related_entity_ids") or []:
            referenced.add(item)

    relation_ends: set[str] = set()
    for relation in relations:
        for key in ("source_id", "target_id"):
            if relation.get(key):
                relation_ends.add(relation[key])

    orphan_characters: list[dict] = []
    relationless_characters = 0
    unreferenced: list[dict] = []

    for entity in entities:
        entity_id = entity["id"]
        if entity.get("type") == "character":
            if entity_id in relation_ends:
                continue
            relationless_characters += 1
            # A character who only ever appears *inside* events is normal -- the
            # relation set models standing relationships, not every encounter. A
            # character the graph never mentions anywhere else is not: the reader
            # cannot reach them from any panel, yet a quote was written for them.
            if entity_id not in referenced:
                orphan_characters.append(
                    {
                        "entity_id": entity_id,
                        "name": entity.get("name"),
                        "first_chapter": entity.get("first_chapter"),
                        "why": "人物没有任何关系连线，且未被任何事件／变化／伏笔引用",
                    }
                )
        elif entity_id not in referenced:
            unreferenced.append(
                {
                    "entity_id": entity_id,
                    "type": entity.get("type"),
                    "name": entity.get("name"),
                    "first_chapter": entity.get("first_chapter"),
                }
            )

    for entity in entities:
        if entity.get("type") == "character":
            continue
        names = names_of(entity)
        joined = " ".join(names)

        for name, character_id in char_names:
            if f"{name}{POSSESSIVE}" in joined and not linked(entity["id"], character_id):
                bearer_claimed.append(
                    {
                        "entity_id": entity["id"],
                        "type": entity.get("type"),
                        "name": entity.get("name"),
                        "bearer_id": character_id,
                        "why": f"名称含「{name}的」，但没有连到该角色",
                    }
                )
                break

        if any(word in joined for word in IDENTITY_WORDS) and not linked_to_any_character(entity["id"]):
            identity_claimed.append(
                {
                    "entity_id": entity["id"],
                    "type": entity.get("type"),
                    "name": entity.get("name"),
                    "why": "名称含身份类词，但与任何角色都没有关系",
                }
            )

    for clue in graph.get("foreshadowing", []):
        if not isinstance(clue, dict):
            continue
        text = f"{clue.get('label', '')}{clue.get('observation', '')}"
        if not any(word in text for word in IDENTITY_WORDS):
            continue
        for entity_id in clue.get("related_entity_ids") or []:
            entity = next((e for e in entities if e["id"] == entity_id), None)
            if entity is None or entity.get("type") == "character":
                continue
            if linked_to_any_character(entity_id):
                continue
            if any(item["entity_id"] == entity_id for item in identity_clue):
                continue
            identity_clue.append(
                {
                    "entity_id": entity_id,
                    "type": entity.get("type"),
                    "name": entity.get("name"),
                    "clue_id": clue.get("id"),
                    "why": f"是身份类线索 {clue.get('id')} 的涉及对象，但与任何角色都没有关系",
                }
            )

    # ---- 已人工判定的项 ---------------------------------------------------
    # 与 rollup_levels.py 的 --acknowledged 同一机制、同一份文件。理由见
    # references/known-gaps.md A2：清单命中不是错误，是要人读一遍；但读过的结论
    # 必须能被机器记住，否则每轮重跑都要重读，读者很快学会忽略整个清单。
    # key 形如 `<section>:<entity_id>`，用实体 ID 而不是行号或序号，分片增删不会失效。
    ack_doc: dict = {}
    ack_sha = None
    if args.acknowledged and args.acknowledged.exists():
        raw = args.acknowledged.read_bytes()
        ack_sha = hashlib.sha256(raw).hexdigest()
        try:
            ack_doc = json.loads(raw.decode("utf-8"))
        except json.JSONDecodeError as exc:
            print(f"警告：确认清单不是合法 JSON（{exc}），按空清单继续", file=sys.stderr)
            ack_doc = {}
    acked: dict[str, dict] = {}
    for item in (ack_doc.get("link_audit") or {}).get("items") or []:
        if isinstance(item, dict) and isinstance(item.get("key"), str):
            acked[item["key"]] = item

    def annotate(section: str, items: list[dict]) -> tuple[list[dict], list[dict]]:
        known, fresh = [], []
        for item in items:
            entry = acked.get(f"{section}:{item['entity_id']}")
            if entry:
                item["acknowledged"] = True
                item["acknowledged_reason"] = entry.get("reason")
                item["acknowledged_review_issue"] = entry.get("review_issue")
                known.append(item)
            else:
                item["acknowledged"] = False
                fresh.append(item)
        return known, fresh

    b_known, b_fresh = annotate("bearer_claimed", bearer_claimed)
    i_known, i_fresh = annotate("identity_claimed", identity_claimed)
    c_known, c_fresh = annotate("identity_clue", identity_clue)
    o_known, o_fresh = annotate("orphan_characters", orphan_characters)

    report = {
        "graph": str(args.graph.resolve()),
        "entities_scanned": len(entities),
        "characters": len(characters),
        "bearer_claimed": bearer_claimed,
        "identity_claimed": identity_claimed,
        "identity_clue": identity_clue,
        "orphan_characters": orphan_characters,
        "unreferenced_entities": unreferenced,
        "acknowledged_source": (str(args.acknowledged) if args.acknowledged else None),
        "acknowledged_sha256": ack_sha,
        "summary": {
            "unacknowledged": len(b_fresh) + len(i_fresh) + len(c_fresh) + len(o_fresh),
            "acknowledged": len(b_known) + len(i_known) + len(c_known) + len(o_known),
        },
    }

    print(f"扫描 {len(entities)} 个实体（其中人物 {len(characters)} 个）、{len(relations)} 条关系")
    sections = [
        ("名称声明归属但无连线", b_fresh),
        ("名称含身份类词但无归属", i_fresh),
        ("身份类线索指向但无归属", c_fresh),
        ("人物完全孤立（无关系、也未被任何记录引用）", o_fresh),
    ]
    for title, items in sections:
        print()
        print(f"## {title}：{len(items)} 项")
        for item in items:
            print(f"  - {item['name']}（{item['entity_id']}，{item.get('type', 'character')}）：{item['why']}")
        if not items:
            print("  （无）")

    print()
    print(f"（另有 {relationless_characters - len(orphan_characters)} 个人物只参与事件、没有任何关系连线——"
          "关系表记录的是持续关系，不是每一次相遇，属正常。）")

    # Reported last and without a verdict: a skill or a background place that is
    # never revisited needs no owner, so this is a coverage figure, not a fault.
    print()
    print(f"## 非人物实体未被任何记录引用：{len(unreferenced)} 项（覆盖度观察，不是缺陷）")
    by_type: dict[str, int] = {}
    for item in unreferenced:
        by_type[str(item.get("type"))] = by_type.get(str(item.get("type")), 0) + 1
    if unreferenced:
        print("  按类型：" + "、".join(f"{key} {value}" for key, value in sorted(by_type.items())))

    total = len(b_fresh) + len(i_fresh) + len(c_fresh) + len(o_fresh)
    print()
    print(f"合计 {total} 项待人工判断：有归属就补关系；确无归属就记入 review_issues 说明理由。")
    print("注意：纯代号（名字里不含归属者，如「血皇」）只能靠人工判断，本脚本只覆盖名称与线索两条路径。")

    known_all = [
        ("名称声明归属但无连线", b_known),
        ("名称含身份类词但无归属", i_known),
        ("身份类线索指向但无归属", c_known),
        ("人物完全孤立", o_known),
    ]
    known_total = sum(len(items) for _, items in known_all)
    if known_total:
        print()
        print(f"## 已确认（已人工判定并写入确认清单）：{known_total} 项，不再计入待判断")
        for title, items in known_all:
            for item in items:
                print(f"  - [{title}] {item['name']}（{item['entity_id']}）")
                print(f"      {item.get('acknowledged_reason') or ''}")
                if item.get("acknowledged_review_issue"):
                    print(f"      见 {item['acknowledged_review_issue']}")

    if args.json:
        args.json.resolve().write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\nwrote {args.json.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
