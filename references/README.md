# Reference map

- `overlapping-timelines-and-membership.md` — normative rendering and data
  rules for overlapping story arcs and entities that belong to multiple
  collection views.
- `visualization.md` — dashboard presentation guidance, including timeline
  lanes, graph surfaces, and repository cards.
- `overlap-membership-fixture.json` — tiny regression fixture: overlapping
  arcs, one entity in three collections, and unique-ID union/intersection
  expectations.
# Dashboard and analysis references

Context and processing references:

- `retrieval-and-efficiency.md` — the active compact context, escalation, candidate, caching, and validation-cost contract.
- `reference-routing.json` — exact reference set for each operation mode.
- `resume-capsule.template.json` — compact cross-turn and cross-agent continuation state.
- `retrieval-profiles.json` and `coverage-receipt.template.json` — optional detailed audit artifacts for high-risk/global claims; routine fragments use compact coverage metadata.
- `execution-profiles.json` — compact per-mode input/output and validation profiles.
- `execution-receipt.template.json` — optional run-level performance telemetry, not a per-fragment requirement.

Before changing repository or dashboard rendering, also read `dashboard-performance-and-navigation.md`.

Additional normative references:

- `collection-views.md` — saved collection expressions, set operators, provenance, and multi-membership cards.
- `story-arcs.md` — inclusive overlapping intervals, nested/parallel arcs, and deterministic lane rendering.
- `style-analysis.md` — evidence-backed prose, narration, speech, and behavior observations.
- `overlap-and-membership.md` — shared fallback and accessibility rules for overlap-heavy views.
- `dashboard-performance-and-navigation.md` — repository categories, pagination, virtualized rendering, lazy loading, and performance budgets.
- `dashboard-taxonomy-and-relation-layout.md` — generic canonical-name, item/relationship taxonomy, hierarchy, readable graph, level-axis, and broad intimate-route rules.
