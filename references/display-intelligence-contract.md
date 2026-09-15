# Display intelligence contract

The canonical graph stores story facts. Display intelligence is a **derived, disposable presentation layer** that may be authored by an AI after reading the relevant canonical facts and evidence.

## Principle

Code protects facts; AI interprets importance.

Do not hard-code semantic importance by entity type (for example, `character -> realm/faction/identity`, `item -> rarity/holder`). Different books make different attributes important. The presentation layer may therefore choose free-form labels, headlines, badges, ordering, and highlighted source keys.

The code layer still enforces the non-negotiable boundaries:

- entity IDs must resolve to the canonical graph;
- a highlighted canonical attribute is referenced by `source_key`, not copied as a second fact value;
- free-form headlines must carry a visibility interval and evidence when they make a factual claim;
- future display hints must not appear before `valid_from`;
- unknown evidence IDs are reported as display-profile issues;
- display profiles never write facts back to `graph.json`;
- absence of an AI profile falls back to current visible attributes without inventing importance.

## Derived hint shape

```json
{
  "schema_version": 1,
  "profiles": {
    "char_001": {
      "headlines": [
        {
          "text": "宗门年轻一代的核心剑修",
          "valid_from": 120,
          "valid_to": null,
          "evidence_ids": ["evd_120_04"]
        }
      ],
      "important_attributes": [
        {
          "source_key": "境界",
          "label": "当前境界",
          "valid_from": 8,
          "valid_to": null,
          "reason": "该属性持续影响战斗判断"
        }
      ],
      "badges": [
        {
          "label": "关键人物",
          "valid_from": 120,
          "valid_to": null
        }
      ]
    }
  }
}
```

`label`, `reason`, `headline` and badge wording are intentionally not controlled vocabularies. They are presentation language, not canonical ontology.

## Temporal behavior

A profile may be generated against the full private run, but every entry must be chapter-aware. If `valid_from` cannot be established from evidence or the canonical attribute timeline, the builder uses a conservative visibility boundary rather than showing the hint early.

For spoiler-safe exports, build profiles from the already filtered as-of graph or pass the same cutoff used for the final build.

## Entity detail UX

Opening an entity should make the following immediately visible:

1. canonical/display name and entity type;
2. **首次出现：第 N 章**;
3. **重要属性：...** chosen by the AI profile when available, otherwise a neutral current-attribute fallback;
4. current state facets, active relationships and recent events;
5. evidence links that can open the reader at the supporting chapter/quotation.

The detail panel is a view over the current chapter snapshot. It must not render final-state values while the shared chapter slider is positioned in the past.
