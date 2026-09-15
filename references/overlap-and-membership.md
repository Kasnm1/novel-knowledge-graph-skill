# Overlapping timelines and multi-membership rendering

This contract is normative for dashboard views.

## Purpose

Story arcs and dashboard collections are query and presentation dimensions. They are not mutually exclusive partitions of the story or of the entity set. A character, item, skill, event, or chapter may therefore appear in more than one collection and in more than one arc at the same time.

## Stable membership contract

Every rendered entity card must distinguish three kinds of membership:

1. **主归属** (`primary_memberships`): at most one manually selected or deterministic display membership used for compact ordering only.
2. **其他归属** (`additional_memberships`): all other evidence-backed memberships, shown as chips or a count that can be expanded.
3. **交集／并集来源** (`derived_memberships`): collections produced by an expression. Show the expression path (for example `当前有效 ∩ 感情线`) and never silently convert it into an ordinary factual group.

The same entity is rendered once per view, not once per matching collection. Each card exposes “属于 N 个集合” and an expandable membership list. Collection chips use stable IDs and labels; labels alone must not be used as keys. If a membership lacks evidence, mark it `待核` and keep it out of the confirmed count.

When a compact layout cannot show every chip, show the first deterministic three (primary first, then lexical stable ID order) and a `+N 个归属` affordance. Never drop memberships merely because the entity also matched another collection. Filtering by multiple collections is an AND/OR query over membership IDs and must report the active operator.

## Collection expression rendering

The supported display operators are:

- `and`: intersection; display “同时属于” and the operand labels.
- `or`: union; display “满足任一” and deduplicate entities by stable entity ID.
- `not`: exclusion; display the excluded collection and the reason for exclusion.

For every derived result, retain `matched_by` (the operand IDs that matched) so users can explain why an entity is present. Explicit/manual members and inferred members must use different badges. Name similarity, shared surnames, or model intuition are not evidence for relationship collections.

## Overlapping timeline contract

Arc intervals are closed chapter ranges (`chapter_start`, `chapter_end`) and may overlap. A chapter must not be forced into one arc. Render arcs as independent horizontal swimlanes (or stacked interval rows on narrow screens), grouped by `parent_arc_id`; nested arcs are indented and parallel arcs remain side by side. Identical or overlapping intervals are not merged unless they have the same stable arc ID.

The `dominant_arc_id` field, when present in a chapter summary, is only a sorting/highlight hint. Label it “主显示剧情（非排他）”; it must never hide the chapter's other `arc_ids`. A chapter row shows all active arcs, with phase badges such as `起始／发展／转折／高潮／收束` and status `进行中／已结束`.

Timeline interaction must support:

- chapter-range brushing that highlights every intersecting arc;
- toggling parent, child, and parallel lanes independently;
- an overlap indicator listing the chapter range and the participating arc IDs;
- reverse lookup from an arc to chapters, events, and entities, and from an entity/event to all arcs.

If an interval has an unknown end, render it as open-ended and mark the range `未完`; do not invent an end chapter. If ranges conflict with evidence, keep both records, display a conflict badge, and link their evidence IDs for review.

## Accessibility and readability

Do not rely on color alone to distinguish memberships or lanes. Use text labels, icons/patterns, and accessible lists. Keep entity identity visible while filtering, show active filters and operator above results, and provide a “清除筛选” action. On small screens, collapse membership chips into an expandable list and switch the timeline to a chapter-indexed list preserving the same overlap semantics.
