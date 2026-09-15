# Task specification template

Generate this envelope for the current task. Do not copy it into a run as a permanent replacement for the current Skill.

## Run-specific envelope

- Operation mode:
- Book/edition ID:
- Canonical run path:
- Source path and revision fingerprint:
- Base graph snapshot ID:
- Assigned chapter/query range:
- Task-local staging path:
- User inclusion rules/overrides:
- Language/display vocabulary:
- Allowed outputs:
- Forbidden writes:

All schema, extraction, retrieval, validation, and visualization rules come from the current Skill route selected in `reference-routing.json`.

## Fragment shape

The fenced keys must stay aligned with `scripts/required_fields.py`:

```json
{
  "metadata": {},
  "entities": [],
  "events": [],
  "relations": [],
  "state_changes": [],
  "romance_routes": [],
  "intimate_acts": [],
  "level_conversions": [],
  "character_traits": [],
  "item_roles": [],
  "chapter_summaries": [],
  "story_arcs": [],
  "foreshadowing": [],
  "evidence": [],
  "review_issues": []
}
```

The task envelope may narrow the source range or user-facing output. It may not disable a supported record type, forbid evidence-backed new entities/routes, weaken source/evidence requirements, or redefine canonical schema keys.

## Compact completion data

Each fragment includes its range, base snapshot, source fingerprint, candidate counts, resolved candidate IDs, unresolved issue IDs, and validation status. Full coverage receipts are required only for high-risk/global claims or an explicit audit.
