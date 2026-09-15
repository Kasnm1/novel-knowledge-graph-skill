# Dashboard collection views

Collections are saved dashboard queries, not additional story facts. Store them in a run-local `dashboard-views.json` (or equivalent view manifest) and keep their definitions separate from `graph.json`.

## Definition

```json
{
  "collections": [
    {
      "id": "active_and_romantic",
      "label": "当前有效且有感情线",
      "expression": {
        "and": [
          {"collection": "active_relations"},
          {"collection": "romance_routes"}
        ]
      },
      "display": {"primary": true, "order": 10}
    }
  ]
}
```

The expression vocabulary is deliberately small and auditable:

- `collection`: reference another saved collection;
- `and`, `or`, `not`: set operations;
- `type`: filter entity kinds;
- `relation`: filter by an evidence-backed relation predicate;
- `arc`: filter by story-arc membership;
- `active_at`: filter temporal validity at a chapter;
- `explicit_members`: manually confirmed display members.

Unknown operators, circular collection references, and references to missing collections are validation errors. A collection must carry a stable ID, a human label, its expression, and a deterministic member order.

## Multi-membership rules

An entity can match any number of collections. The renderer deduplicates by stable entity ID and keeps a `membership_reasons` map from collection ID to the evidence or expression operands that produced the match. It must not create duplicate entity cards for each matched collection.

Every card shows one compact primary badge, a count of additional memberships, and an expandable list of all memberships. “Primary” is a display preference only; it is never a claim that the entity belongs exclusively to that set. Derived (query) membership, explicit membership, and inferred membership have distinct badges.

Use an explicit filter operator in the toolbar:

- `同时满足` (AND) for intersection;
- `满足任一` (OR) for union;
- `排除` (NOT) for subtraction.

The active expression and result count remain visible while scrolling. If the viewport cannot fit all chips, show at most three deterministic chips followed by `+N 个归属`; expanding the card reveals the full list. Color is supplemental only: labels and icons must preserve meaning in monochrome and for color-blind users.

Relationship collections (family, school, faction, guild, nation, teacher/student, allies, rivals, romance, identity) may only be produced from explicit relation records and their evidence IDs. Name, surname, co-occurrence, or model intuition is not sufficient.

## Empty and uncertain states

An empty result is a valid result and should say which expression produced it. Members whose supporting evidence is unresolved are shown under `待核` and excluded from the confirmed count unless the user enables “包括待核”. Never silently promote an inferred relationship to a confirmed collection member.
