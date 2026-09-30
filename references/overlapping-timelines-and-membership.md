# Overlapping timelines and multi-membership

Normative data and rendering rules for overlapping story arcs and entities in several collections.

## Data and rendering rules

This contract keeps two distinct ideas separate:

- a **story arc** is an evidence-backed editorial record about a continuous or
  recurring plot line;
- a **collection** is a dashboard query over graph facts. It is a view, not a
  new story fact and not an additional copy of an entity.

An entity may appear in any number of arcs and collections. Never duplicate an
entity record merely to make it appear in a second place.

### Story timelines may overlap

Do not model the novel as one exclusive lane. An arc may overlap another arc in
chapter range when, for example, a family conflict continues while an academy
tournament is underway. A child arc is allowed to overlap its parent; parallel
arcs are also allowed to overlap without a parent relationship. A chapter can
have zero, one, or several `arc_ids`; `dominant_arc_id`, if present, is only
the reading/default focus and does not make the other memberships inactive.

For every arc, store and render at least its stable ID, reader-facing title,
chapter start/end, status, parent arc (when applicable), participating event
and entity IDs, and evidence IDs. Use a separate field or marker for major
turning points. Ranges are inclusive. Do not infer an arc merely because two
events happen near each other: a title, range, membership, and summary need
textual evidence or an explicitly labelled editorial inference.

#### Timeline rendering

Render arcs as horizontal range bars on independent rows rather than trying to
pack them into a single chapter strip. Overlapping bars must remain separately
clickable. Nest child arcs under their parent with indentation; put unrelated
parallel arcs in separate swimlanes. A recurring or long-running arc may have
multiple visible segments joined by a subtle continuation connector, while its
underlying arc ID stays the same.

When space is limited:

1. show the focused arc in full and collapse non-focused lanes into a count;
2. keep chapter ticks and the selected chapter marker visible;
3. expose a filter for status, parent/parallel lane, and participant;
4. open an arc detail panel with its complete chapter range, event sequence,
   people/items, turning points, evidence, and related foreshadowing.

Never resolve overlap by silently truncating a bar, assigning a chapter to only
one arc, or sorting one arc "above" another as though that established causal
priority.

### Multi-collection membership

Collections are query results derived from graph facts (for example "academy
members", "the main character's allies", "appears in arc A", or their
intersection). A collection expression may use `and`, `or`, `not`, `type`,
`relation`, `arc`, `active_at`, and `explicit_members`. Each result needs an
explainable membership reason: the matched predicate(s), source fact IDs, and
evidence IDs where available.

#### Avoiding unreadable duplication

Use **one canonical card per entity in the current result surface**. Do not
render a person or item once per matching collection. Put compact membership
chips on that card, such as `学院`, `主角阵营`, and `考核篇`; show at most three
chips followed by `+N`. Clicking `+N` opens a stable, sorted membership list
with the reason and evidence for each membership.

For an intersection query, show the entity once and state the matching path,
for example `学院 ∩ 主角盟友` or `满足 2/2 条件`. For a union query, show it once
with all matching collection chips; do not concatenate collection result lists.
For a negated condition, label the active inclusion rule rather than displaying
the absence as a story fact.

Use the following levels of display:

| Surface | Default presentation | Drill-down |
| --- | --- | --- |
| Collection overview | collection cards with counts and query labels | members and membership reasons |
| Entity repository | one entity card with capped chips | all memberships, evidence, active chapter range |
| Graph canvas | one node; color for type, not membership | selected-node membership list or filtered overlay |
| Timeline | one participant marker per visible arc row | entity detail shows every related arc |

If many memberships are selected, switch from coloured chips to textual labels
and counts. Colour is supplementary only: do not assign a different permanent
colour to every collection. Keep entity type, relationship state, and
collection membership visually distinct so the same badge never has two
meanings.

#### Filtering behaviour

Collection filters compose explicitly. The interface must show whether the
current mode is "match all" (intersection) or "match any" (union), and must
show exclusions in the active-filter summary. Clearing a filter must never
remove the underlying graph fact or a manually curated collection definition.
The result count is the count of unique entity IDs, not the sum of collection
counts.

When an entity is a member through an inferred relation or editorial arc
assignment, label that status (`推断` / `编辑归类`) and retain counterevidence or
scope limitations. Do not derive family, sect, faction, or identity membership
from surnames, name similarity, or model intuition.

### Required review examples

Before accepting a dashboard implementation, exercise these cases with a small
fixture:

1. two overlapping arcs both cover chapter 24 and stay independently visible;
2. a chapter belongs to two arcs while one is the dominant focus;
3. one character belongs to three collections and appears once in a union;
4. the same character appears once in an intersection and exposes both reasons;
5. a person and an item share collections without the renderer treating them as
   the same entity type;
6. a collection count uses unique entity IDs and does not double-count a member
   reached by two predicates.

## Fallback and accessibility rules

This contract is normative for dashboard views.

### Purpose

Story arcs and dashboard collections are query and presentation dimensions. They are not mutually exclusive partitions of the story or of the entity set. A character, item, skill, event, or chapter may therefore appear in more than one collection and in more than one arc at the same time.

### Stable membership contract

Every rendered entity card must distinguish three kinds of membership:

1. **主归属** (`primary_memberships`): at most one manually selected or deterministic display membership used for compact ordering only.
2. **其他归属** (`additional_memberships`): all other evidence-backed memberships, shown as chips or a count that can be expanded.
3. **交集／并集来源** (`derived_memberships`): collections produced by an expression. Show the expression path (for example `当前有效 ∩ 感情线`) and never silently convert it into an ordinary factual group.

The same entity is rendered once per view, not once per matching collection. Each card exposes “属于 N 个集合” and an expandable membership list. Collection chips use stable IDs and labels; labels alone must not be used as keys. If a membership lacks evidence, mark it `待核` and keep it out of the confirmed count.

When a compact layout cannot show every chip, show the first deterministic three (primary first, then lexical stable ID order) and a `+N 个归属` affordance. Never drop memberships merely because the entity also matched another collection. Filtering by multiple collections is an AND/OR query over membership IDs and must report the active operator.

### Collection expression rendering

The supported display operators are:

- `and`: intersection; display “同时属于” and the operand labels.
- `or`: union; display “满足任一” and deduplicate entities by stable entity ID.
- `not`: exclusion; display the excluded collection and the reason for exclusion.

For every derived result, retain `matched_by` (the operand IDs that matched) so users can explain why an entity is present. Explicit/manual members and inferred members must use different badges. Name similarity, shared surnames, or model intuition are not evidence for relationship collections.

### Overlapping timeline contract

Arc intervals are closed chapter ranges (`chapter_start`, `chapter_end`) and may overlap. A chapter must not be forced into one arc. Render arcs as independent horizontal swimlanes (or stacked interval rows on narrow screens), grouped by `parent_arc_id`; nested arcs are indented and parallel arcs remain side by side. Identical or overlapping intervals are not merged unless they have the same stable arc ID.

The `dominant_arc_id` field, when present in a chapter summary, is only a sorting/highlight hint. Label it “主显示剧情（非排他）”; it must never hide the chapter's other `arc_ids`. A chapter row shows all active arcs, with phase badges such as `起始／发展／转折／高潮／收束` and status `进行中／已结束`.

Timeline interaction must support:

- chapter-range brushing that highlights every intersecting arc;
- toggling parent, child, and parallel lanes independently;
- an overlap indicator listing the chapter range and the participating arc IDs;
- reverse lookup from an arc to chapters, events, and entities, and from an entity/event to all arcs.

If an interval has an unknown end, render it as open-ended and mark the range `未完`; do not invent an end chapter. If ranges conflict with evidence, keep both records, display a conflict badge, and link their evidence IDs for review.

### Accessibility and readability

Do not rely on color alone to distinguish memberships or lanes. Use text labels, icons/patterns, and accessible lists. Keep entity identity visible while filtering, show active filters and operator above results, and provide a “清除筛选” action. On small screens, collapse membership chips into an expandable list and switch the timeline to a chapter-indexed list preserving the same overlap semantics.
