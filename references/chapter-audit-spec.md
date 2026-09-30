# Chapter audit card (audit protocol 2)

This Skill exists to have an AI audit a novel **chapter by chapter**. A fragment that records nothing
for a chapter and a fragment that never looked are indistinguishable from their records, so every
analysed narrative chapter answers one fixed checklist — the *audit card* — and every checklist item
is either **recorded N** or **none, because …**. `check_fragment.py` holds each receipt against the
records the fragment actually carries (`scripts/chapter_audit.py`).

Why this exists, measured on a 999-chapter run audited without it: 1.16 events per chapter and never
more than 4; no state change in 624 chapters; 546 "thin" chapters (≤ 1 event, no state change); 804
character mentions in chapter summaries with no record of that character in that chapter; 418
summaries under three sentences; 2 of 33 core characters with a speech trait. Run
`scripts/audit_chapter_depth.py` to get the same report for any graph.

## Opting in

A fragment declares `"metadata": {"audit_protocol": 2, ...}`. Then:

- every analysed chapter that is not declared `non_narrative_chapter` in `review_issues` must have a
  `chapter_summaries` row carrying the card fields below;
- record-level rules apply: canonical `relation_type` (`scripts/relation_types.py`), event `type` from
  `RECOMMENDED_EVENT_TYPES`, `level_axis.applies_to` on every newly declared axis, and state values as
  `null` or `{value, label, note}` with notes kept out of `label`.

Supplementary fragments (`metadata.supplementary`) are exempt from the per-chapter requirement but not
from the record rules. Legacy fragments without the flag are only checked when they carry a card.

## Work unit

The survey, ID registry, lane/unit plan, state capsule and verifier loop are in `ai-workflow.md`.

Audit **3–5 chapters per worker**, one card per chapter, written while the chapter is in front of you.
Ten chapters per worker is what produced the thin run above: the checklist gets compressed into
"the main plot point" per chapter. Contiguous ranges, `plan_fragments.py`, immutable fragments and the
short merge lock are unchanged.

## The card

The card is the chapter's `chapter_summaries` row (no new top-level array):

```json
{
  "id": "cs_f12_118", "chapter": 118, "title": "第一百一十八章 …",
  "summary": "三到六句：本章要完成什么、发生了什么变化、为后文铺了什么。",
  "evidence_ids": ["ev_f12_031"],
  "continuity": {"from_previous": "承上：接上一章哪条线", "sets_up": "启下：留下什么悬念或任务"},
  "scenes": [
    {"location_id": "loc_x", "location_label": "", "time_label": "当夜",
     "participant_ids": ["char_a", "char_b"], "pov_entity_id": "char_a",
     "purpose": "这一场要完成什么", "event_ids": ["event_f12_040"]}
  ],
  "presence": [
    {"entity_id": "char_a", "mode": "present", "role": "本章在做什么", "state_check": "changed"},
    {"entity_id": "char_c", "mode": "mentioned", "role": "被提起的原因"}
  ],
  "narrative": {"functions": ["payoff", "face_slap"], "cliffhanger_type": "crisis", "pacing": "fast",
                "quote_evidence_ids": ["ev_f12_035"]},
  "audit": {
    "events": {"status": "recorded", "count": 4},
    "commitments": {"status": "none", "count": 0, "reason": "本章没有任何许诺、誓言或赌约"}
  }
}
```

`audit` carries one receipt for **every** key below. `recorded` must equal the number of records the
fragment carries for that item in that chapter; `none` requires zero such records and a reason that
says what the text lacks.

| key | checklist item | what is counted |
|---|---|---|
| `scenes` | 场景切分 | `scenes[]` |
| `presence` | 出场名册 | `presence[]` |
| `events` | 情节点 | events in the chapter — **no cap**; every plot-moving beat, with location and cause |
| `state_check` | 在场人物状态确认 | state changes other than level/skill/possession/knowledge |
| `levels` | 等级变化 | `level` state changes |
| `skills_items` | 功法与物品得失 | `skill`/`possession` changes + `item_roles` opened or closed |
| `relations` | 关系变化 | relations starting, ending or gaining an observation |
| `knowledge` | 信息与秘密 | `knowledge` changes + events with an `information` facet |
| `combat` | 战斗与伤亡 | events with `combat` or `mortality` facets |
| `transactions` | 交易与财富 | events with a `transaction` facet |
| `romance_intimacy` | 感情与亲密 | route milestones + `intimate_acts` |
| `commitments` | 承诺 | commitments created or resolved |
| `foreshadowing` | 伏笔与悬念 | foreshadowing planted, progressed or paid off (`kind`: `foreshadowing` / `question`) |
| `traits` | 外貌、性格与说话方式 | `character_traits` |
| `narrative` | 叙事功能与名句 | `narrative.functions` + `narrative.quote_evidence_ids` |

## Rules the checker enforces

- **Presence is complete.** Every event participant and every character with a state change in the
  chapter is on the roster. Scene participants are `present`; a POV entity is on the roster.
- **Only present characters take part in events.** A character who is only `mentioned` (dead, elsewhere,
  talked about) cannot be an event participant unless the event is a recollection or report tagged
  `tags: ["recalled"]`.
- **Every present character gets a state check.** `changed` requires a state change for them in this
  chapter; `confirmed_unchanged` forbids one; `not_tracked` is for walk-ons. This is what keeps the
  reader's "as of chapter N" card current: a core character who appears is either updated or
  explicitly confirmed, never silently carried forward.
- **Scenes explain the chapter.** Each scene has a purpose and a place (`location_id` or
  `location_label`); an event that belongs to no scene is reported.
- **Summary** is at least three sentences; `continuity.from_previous` (except chapter 1) and
  `continuity.sets_up` are required — write 「本章收束，无新悬念」 when that is the truth.
- **Narrative** has at least one function from `NARRATIVE_FUNCTIONS`, a controlled
  `cliffhanger_type`, and a `pacing` of fast / medium / slow. Notable lines are quoted as evidence and
  referenced, never paraphrased.

## Worker procedure per chapter

1. Read the chapter once for scenes: cut it at changes of place, time or POV, and write the scene list.
2. Build the roster: every named entity present or mentioned. Unnamed walk-ons stay out.
3. Walk each scene for events, then walk the roster: for each present character check identity,
   location, health, emotion, goal and affiliation against the state you were handed; record changes,
   otherwise mark `confirmed_unchanged`.
4. Run the item passes from `analysis-protocol.md` (level, trait, romance, intimacy, commitments,
   foreshadowing) — the recording discipline there applies unchanged: record what the text says,
   completely, without softening or omission.
5. Write the summary, continuity and narrative last, then fill every receipt from the records you wrote.
6. Resolve evidence and run `check_fragment.py`; a card that does not pass is not done.

After the range, `audit_chapter_depth.py` on the merged graph shows which chapters still look thin.
