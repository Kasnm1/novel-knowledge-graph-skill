# Verifier instructions

You verify one chapter's audit. You are not the extractor and you have not seen
its notes or reasoning. You receive:

1. the chapter text;
2. the records the fragment carries for this chapter, including its audit card;
3. `recall-<chapter>.json`: deterministic recall candidates.

The recording discipline of `analysis-protocol.md` applies to you as well: the
book records what it says, completely. A missing violent, sexual or
non-consensual act is a missed record like any other; never ask for softening.

## What to check

- **Recall.** Every plot-moving beat is an event; every present named character is
  on the roster; every change the text shows to a present character's identity,
  location, health, emotion, goal, affiliation, level, skills or possessions is a
  state change; relations that start or end, promises made or kept, clues planted
  or paid off, intimate acts, deaths, money and items changing hands are recorded.
- **Precision.** Each record says what the text says: right participants, right
  entity (an item's grade is not its wielder's level), right facet (an action is
  not an identity), right chapter, evidence that actually supports it, consent
  exactly as the text shows it.
- **Not errors.** An explicit intimate proposal is recorded as an intimate act even when
  nothing happens (`analysis-protocol.md`, intimacy pass step 1); a witnessed act is recorded
  with the witness as observer. Do not report these as wrong.
- **The audit card.** Receipts that claim `none` while the text shows the thing;
  `confirmed_unchanged` for a character whose state visibly changed.
- **Every recall candidate.** Answer each one: `recorded` (a record covers it),
  `not_applicable` (the marker is incidental — say why) or `missed`.

Do not re-extract the chapter and do not rewrite records yourself. Report.

## Verdict format

Return JSON only:

```json
{
  "chapter": 301,
  "rounds": 1,
  "candidates": {"rc_0301_001": "missed", "rc_0301_002": "not_applicable"},
  "missed": 2,
  "wrong": 1,
  "issues": [
    {"type": "missed", "what": "黄虎当场毙命，没有死亡记录", "quote": "黄虎喉头一甜，当场断了气", "suggest": "state_change health + events[].mortality"},
    {"type": "wrong", "record_id": "sc_f31_004", "what": "身份写成了一个动作", "quote": "……", "suggest": "改为 event；身份不变则 confirmed_unchanged"}
  ]
}
```

`missed` and `wrong` count the issues listed. The extractor gets one correction
round; what remains after it becomes a `review_issues` entry. `score` turns the
verdict into the chapter's quality in `coverage-ledger.json`.
