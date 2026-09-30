# Dashboard and reader views

Everything the derived reader dashboard must honour. All of it is derived from the canonical graph and disposable; the frontend rewrite (W4) keeps these contracts.

## Presentation

The dashboard is a view of `graph.json`; it must not become an independent source of truth.

### Required interactions

Apply `the taxonomy section below` for relationship layout, canonical names and aliases, repository categories, protagonist-linked relation labels, and entity detail sections. Appearance heat is not a primary layout. Use grouped lanes and list/tree fallbacks instead of an unbounded force-directed cloud.

Apply `the taxonomy section below` for the relationship graph, canonical-name display, category navigation, protagonist-linked relation labels, and entity detail panel. Do not expose appearance heat as a primary layout. Use grouped lanes/list fallbacks instead of an unbounded force-directed cloud.

- Search entities by name or alias.
- Filter by entity type and chapter.
- Provide explicit single-select and multi-select modes for entity-type filters, with visible selection state; multi-select mode also provides select-all and clear controls.
- Provide dedicated, searchable character, ability, and equipment/item repositories derived from the same graph and synchronized with the selected chapter for dynamic ownership and relationships. Repository cards open the canonical entity detail rather than a separate copy of the data. Group characters into explicit friends, harem/romance routes, enemies, and others using chapter-valid evidence-backed relationships, with romance taking display precedence when categories overlap. Group abilities by current holder/user or unknown ownership and offer useful sorting. Group equipment/items prominently by explicit role: owner, current holder, user, custodian, former holder, or unknown; never infer a role from an item name or summary.
- Offer both readable cards and a keyboard-accessible compact repository table. Both views use the same derived read model and the same search, sorting, and result filters (all, protagonist-related, currently active, changed, or carrying unresolved review issues); switching views must never change counts or state wording.
- Click a node to inspect attributes, current state, history, relations, and evidence.
- Put a compact derived summary below every entity title: current-state field count, chapter-valid relation count, full-history change count, deduplicated evidence count, unresolved-issue count, and the latest already-effective change chapter. Prefer up to three stable-priority highlights (level, identity/title, location/affiliation) over arbitrary object order. This summary is a view over the graph, never stored back into it.
- Show a **current-level panel** at the top of any entity detail that has `level` changes: one row per level axis the entity has advanced on, giving the axis name and its value as of the selected chapter, with an explicit "as of chapter N" label. The panel must follow the chapter control, so scrubbing back to an early chapter shows the level held then, not the latest one. Render the axis' own `label` wording; use `value` only for ordering and comparison.
- When an axis value is numeric, additionally show the change points on the entity timeline so a reader can see when each gain happened.
- For character details, group possessions, identity, levels, abilities, relationships, knowledge, goals, and other facets into collapsed setting-localized categories; each category keeps both the selected-chapter state and prior changes.
- Give each character category a semantic summary (for example current level, active/ended relationships, current possessions, total changes, and latest change) rather than generic item/record counts. Label current state, complete history, and evidence as separate blocks; show only the three most recent history/evidence rows initially and let the reader expand the exact remainder count.
- Provide a character-scoped chapter timeline with visible change points and previous/next-change navigation, synchronized with the graph's chapter state.
- Click a relation to inspect validity interval and evidence.
- Browse a chronological change/event timeline.
- Browse foreshadowing by status and open supporting passages.
- Browse romance routes in a dedicated localized view showing inclusion basis, consent/interaction context, first meeting, first qualifying intimacy or ambiguity, relationship confirmation, and the sexual-milestone status.
- Show a character's linked romance route in a collapsed character category. Details opened from a character profile must include a dedicated return-to-character-overview control; details opened globally must not pretend to have a character return target.
- Display coverage and validation status.
- Default to full-range, spoiler-visible dossiers. The chapter control means “dynamic state as of chapter N”; it does not hide later summaries, aliases, evidence, events, foreshadowing payoffs, or other full-range reference material. Visually separate **截至第 N 章的动态状态**, **完整变化历史**, and **全范围资料** so the scope is never ambiguous.
- On desktop, let the reader drag the detail panel's left divider to widen or narrow it, persist that preference locally, and retain a keyboard-accessible resize control. Disable the divider in the stacked mobile layout.
- Show reader-facing clues and quotations with chapter numbers only. Keep exact source line ranges inside the machine-readable graph and validation layer for auditing, but do not expose them in the dashboard.

### Presentation defaults

- Use color for entity type, not moral alignment.
- Localize all reader-facing entity types, state facets, actions, relations, statuses, confidence levels, event types, and review categories. Choose setting-native terms per book; keep stable English schema keys only inside data and code.
- Visually distinguish explicit facts, inferences, and uncertainty.
- Label chapter ranges on relations and state changes.
- Keep quotations collapsed or compact until selected.
- Evidence summaries deduplicate IDs, state the evidence count and chapter span, and show short one-line previews before expansion. Never shorten or rewrite the quotation stored in `graph.json`; truncation is display-only.
- For large graphs, show important connected entities first and retain filters for the rest.
- Keep chapter scrubbing responsive: coalesce slider input to at most one render per animation frame, pre-index relations and state changes by entity, lazily render only the active feed/repository, avoid relabelling every node on each chapter change, and reduce layout work for large visible sets. Show visible/total node and relation counts so filtering remains legible.
- Keep the page vertically scrollable at every breakpoint. The detail panel and repository may have their own overflow regions, but no fixed-height container may trap content without a visible scrollbar or keyboard access.

### Privacy and portability

Prefer a self-contained local HTML file with embedded graph data and no remote runtime dependency. Do not upload novel text or API keys. Include only short evidence excerpts needed for verification.
## Overlay rules for timelines and collection membership

The dashboard must treat arc membership and collection membership as many-to-many
relationships. Follow the normative details in
`references/overlapping-timelines-and-membership.md`.

Timeline lanes are independent: overlapping chapter ranges remain visible on
separate rows, child arcs are indented beneath parents, and parallel arcs use
separate swimlanes. A chapter marker may appear in several lanes. The selected
arc is a focus state only; it must not hide or rewrite other memberships.

Repository and graph surfaces use one canonical card/node per entity. Render
collection membership as compact, capped chips plus an expandable “all
memberships” view showing the matched expression, reason, provenance, and
evidence. Union and intersection views deduplicate by stable entity ID and
announce whether the filter means match-any or match-all. Keep entity type,
relation state, arc membership, and collection membership on separate visual
channels; color alone is never the membership explanation.
## Overlay rules for timelines and collection membership

Treat arc membership and collection membership as many-to-many relationships;
follow `references/overlapping-timelines-and-membership.md` for the normative
contract. Timeline arcs render on independent lanes, preserving overlapping
chapter ranges and multi-arc chapter markers. Repository and graph surfaces
render one canonical entity card/node, with capped membership chips and an
expandable list of all matched collections, reasons, provenance, and evidence.
Union/intersection counts deduplicate stable entity IDs and visibly announce
match-any versus match-all filtering. Keep type, relation state, arc, and
collection semantics on separate visual channels; color alone is insufficient.
### Repository navigation and performance

Apply the performance section below: expose explicit categories, stable sorting, pagination or cursor navigation, and virtualized/lazy rendering. Characters, items, timelines, romance routes, and intimacy events must be deduplicated by stable ID while retaining all category memberships. Initial rendering is bounded; large ranges use chapter-window filtering and progressive detail loading.

## Performance and navigation

The repository is a set of navigable views, not one unbounded list. Every view must provide an explicit category, a stable sort, pagination or virtual scrolling, and a bounded render window. This applies to characters, items, skills, relationships, timelines, romance lines, intimacy events, foreshadowing, and style observations.

### View model

Each repository view declares:

```json
{
  "view_id": "characters",
  "category": "人物",
  "group_by": "story_arc",
  "sort": {"field": "last_seen_chapter", "direction": "desc"},
  "page_size": 24,
  "render_mode": "virtual",
  "filters": [],
  "search_fields": ["label", "aliases", "roles"]
}
```

`view_id`, category, grouping, sort, and pagination settings must be deterministic. The UI must preserve the current query, category, sort, page/cursor, and expanded state when navigating to a detail view and returning.

### Required categories

Categories are intentionally visible as first-class navigation rather than hidden in a single “全部” dropdown. The user can switch between category, group, and detail modes without losing the active query.

The default repository navigation exposes separate top-level categories:

- 人物：主角、重要人物、配角、阵营／家族／门派、当前活跃、已退场、待核；
- 物品：武器、防具、道具、信物、资源、地点性物件、未分类；
- 技能：能力、功法、职业技能、被动特征、状态变化、待核；
- 关系：家族、门派／学院、国家／势力、师徒、朋友、敌对、感情线、身份／分身；
- 剧情：大剧情、子剧情、并行剧情、关键事件、转折点、伏笔；
- 感情线：对象、阶段、关键推进、阻碍、当前状态、证据；
- 亲密行为：事件时间、参与者、行为类型、同意／边界字段（若有）、证据和待核状态；
- 风格分析：全文行文、叙事、人物刻画、语言风格、行为风格。

Categories are views and may overlap. An entity can appear in several category results, but the same result set must deduplicate by stable ID and show membership badges rather than duplicate cards.

### Pagination and filtering

Use server/worker-side filtering and sorting before rendering. For ordinary card and table repositories, default to 24 records per page with controls for 12/24/48/96. For very large or continuously growing lists, use cursor pagination (`next_cursor`) rather than offset pagination; cursors must encode the stable sort key and be invalidated when the underlying snapshot changes.

Always show total matched count when known, current page/range, active filters, and a “清除筛选” action. Search is debounced and must search indexed fields rather than repeatedly scanning and rerendering the complete graph. Empty, loading, and error states are explicit. Do not silently truncate results.

### Timeline, romance, and intimacy views

Timelines use a chapter-window navigator: choose a start/end range, then render only arcs and events intersecting that range while preserving overlap semantics. Large ranges switch to a chapter-indexed list or condensed overview; details load on expansion.

Romance lines are grouped by route or pair, with one route card per stable route ID. Show stage, first/last evidence chapter, open questions, and related events; paginate routes and virtualize event histories inside an expanded route.

Intimacy events are grouped by chapter range and participants, not placed in an unbounded flat feed. The default view shows a privacy-conscious event summary and evidence status; full excerpts are loaded only when the user expands an event. Do not infer intimacy from generic contact events, and do not merge distinct events merely because participants match.

### Rendering budget and virtualization

The initial render must be bounded: render at most 50 list rows/cards or 400 graph nodes in the viewport plus a small overscan window. Use virtualization (`IntersectionObserver`, a virtual-list component, or an equivalent framework-neutral implementation) for lists, graph labels, event feeds, and nested histories. Destroy off-screen detail panels and release observers when views change.

Load heavy sections progressively: summary counts first, then visible cards, then relationships/events/evidence on demand. Cache immutable snapshot-derived summaries by `(snapshot_id, view_id, query_hash)` and invalidate on snapshot change. Never recompute the entire graph for a local filter or page turn.

If a query would exceed the render budget, show a condensed aggregate with the exact matched count and offer narrower filters. A performance fallback must preserve navigation and evidence links; it may reduce decoration or collapse secondary labels, but must not drop records from the underlying result set.

### Accessibility and consistency

Pagination, virtual scrolling, and category tabs must be keyboard reachable and expose accessible labels. Announce page changes and result counts. Keep card heights predictable where possible to prevent scroll jumps; preserve focus when rows are recycled. Do not rely on color alone for category or relationship distinctions.

## Taxonomy, naming and relation layout

This contract is generic for every book. A book-specific vocabulary may supply labels, but examples from one novel must never become hard-coded global names.

### Appearance heat and relationship views

Do not expose appearance heat or mention count as a primary layout, ranking, or default sort. Relationship views start from a focal entity or selected set, show first-degree links by default, group links into typed lanes, collapse high-degree nodes, and provide list/table/tree fallbacks. Support filters for relation type, depth, chapter/as-of state, current validity, protagonist relevance, and category grouping. Preserve direction, evidence, validity interval, and conflict state.

### Canonical names and aliases

Keep the entity's canonical `name` separate from `aliases`, `titles`, `historical_names`, and `display_context`. When the text explicitly reveals a later or authoritative name, use it as the current reader-facing canonical name; preserve earlier names as aliases with chapter/evidence context. Historical timelines use the name valid at that chapter. Do not permanently concatenate names into a parenthetical form such as “A（B）” unless the source treats that as one stable name. Nicknames, cover names, titles, and identity masks remain separately labelled.

Name normalization never merges entities solely from spelling, surname, co-occurrence, or model intuition. Ambiguous identities remain candidates with `待核` until evidence supports a merge. A book-specific display vocabulary may choose local labels, but the generic Skill must not hard-code any book's names.

### Item categories

Items may have multiple evidence-backed category memberships. Default categories are 武器、防具／护具、饰品、奢侈品／珍藏、消耗品／药剂／丹药、资源／材料、书卷／秘籍／契约、交通／容器／住所性物件、信物／凭证、普通物品、待分类. Show one display-primary category plus additional category chips; retain function, owner, user, transfer, loss, use, and category evidence independently.

### Existing level systems

When new level wording appears, extend an existing compatible `level_axis` if the text places it in that system or explicitly relates it to that system. Do not create a new axis merely because a label is unfamiliar, translated differently, or appears later. Create a new axis only for a genuinely different scale, unit, governing rule, or incomparable progression. Explicit cross-system conversions are recorded; unstated equivalences are not calculated.

### Hierarchical places and powers

Represent places, families, sects, schools, clans, nations, organizations, and powers as parent/child sets that may overlap. Preserve direct versus inherited membership. Character detail separately exposes faction, family, sect/school, nation, current faction, historical faction, and identity/alter-ego memberships, with validity chapters and evidence.

### Human relationship categories

Make family, sibling, friend/ally, mentor/student, enemy/rival, romance/intimacy, faction/organization, item, and identity relations independently filterable. Do not collapse friends or siblings into a generic “人物关系” card. Reciprocal edges may render as one card while preserving both underlying directions.

### Broad intimate-route discovery

Keep `intimate_acts` (concrete behavior/proposal/context/evidence) separate from `romance_routes` (the broader route and stage). Under a broad harem/intimate tracking rule, create a `provisional_intimate` route candidate when protagonist-linked evidence shows any intimate behavior, repeated attachment, explicit intimate proposal, marriage/betrothal/spouse relation, or described intimate longing, jealousy, or relationship tension.

Use distinct stages for `provisional_intimate`, `one_sided`, `mutual_interest`, `confirmed_relationship`, `spouse`, `betrothed`, `coerced_or_forced`, `accidental_or_contextual`, and `excluded_nonromantic`. One act does not prove mutual love or consent, but it does require a route candidate or an evidence-backed exclusion; it must not disappear because no `intimacy` event was emitted. Medical, rescue, accidental, coerced, and witnessed contact remains visible as an act and may be contextual rather than romantic.

### Protagonist-linked relation labels

Do not show a protagonist-linked person or object as merely “未分类” when an evidence-backed predicate exists. Map it to reader-facing classes such as 赠予／馈赠、保护／救助、伤害／攻击、敌对／追杀、师徒／教导、家族／婚姻／婚约、朋友／盟友、感情／亲密、物品持有／转交、身份／秘密、事件共同参与者. Keep the original predicate and evidence visible. “其他” is a transparent fallback with review status, not a silent sink.

### Entity detail panel

Opening any character, item, place, or faction shows canonical name/aliases, all category memberships, hierarchy memberships, current and historical state, relationship categories, romance/intimacy stage, item/skill history, story arcs, evidence, and unresolved issues. Separate `当前有效／历史／待核`; never hide additional memberships behind a single generic label.

## Display intelligence (AI-authored display hints)

The canonical graph stores story facts. Display intelligence is a **derived, disposable presentation layer** that may be authored by an AI after reading the relevant canonical facts and evidence.

### Principle

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

### Derived hint shape

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

### Temporal behavior

A profile may be generated against the full private run, but every entry must be chapter-aware. If `valid_from` cannot be established from evidence or the canonical attribute timeline, the builder uses a conservative visibility boundary rather than showing the hint early.

For spoiler-safe exports, build profiles from the already filtered as-of graph or pass the same cutoff used for the final build.

### Entity detail UX

Opening an entity should make the following immediately visible:

1. canonical/display name and entity type;
2. **首次出现：第 N 章**;
3. **重要属性：...** chosen by the AI profile when available, otherwise a neutral current-attribute fallback;
4. current state facets, active relationships and recent events;
5. evidence links that can open the reader at the supporting chapter/quotation.

The detail panel is a view over the current chapter snapshot. It must not render final-state values while the shared chapter slider is positioned in the past.

## Collection views

Collections are saved dashboard queries, not additional story facts. Store them in a run-local `dashboard-views.json` (or equivalent view manifest) and keep their definitions separate from `graph.json`.

### Definition

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

### Multi-membership rules

An entity can match any number of collections. The renderer deduplicates by stable entity ID and keeps a `membership_reasons` map from collection ID to the evidence or expression operands that produced the match. It must not create duplicate entity cards for each matched collection.

Every card shows one compact primary badge, a count of additional memberships, and an expandable list of all memberships. “Primary” is a display preference only; it is never a claim that the entity belongs exclusively to that set. Derived (query) membership, explicit membership, and inferred membership have distinct badges.

Use an explicit filter operator in the toolbar:

- `同时满足` (AND) for intersection;
- `满足任一` (OR) for union;
- `排除` (NOT) for subtraction.

The active expression and result count remain visible while scrolling. If the viewport cannot fit all chips, show at most three deterministic chips followed by `+N 个归属`; expanding the card reveals the full list. Color is supplemental only: labels and icons must preserve meaning in monochrome and for color-blind users.

Relationship collections (family, school, faction, guild, nation, teacher/student, allies, rivals, romance, identity) may only be produced from explicit relation records and their evidence IDs. Name, surname, co-occurrence, or model intuition is not sufficient.

### Empty and uncertain states

An empty result is a valid result and should say which expression produced it. Members whose supporting evidence is unresolved are shown under `待核` and excluded from the confirmed count unless the user enables “包括待核”. Never silently promote an inferred relationship to a confirmed collection member.

## Story arcs

Story arcs are interval records over chapter numbers. Intervals are inclusive and may overlap, nest, or remain open-ended. The model must not force one chapter into exactly one arc.

```json
{
  "id": "arc_f01_001",
  "title": "新生考核与黄金之路",
  "chapter_start": 20,
  "chapter_end": 35,
  "parent_arc_id": null,
  "status": "resolved",
  "phase": "收束",
  "event_ids": [],
  "entity_ids": [],
  "turning_point_ids": [],
  "evidence_ids": []
}
```

Nested sub-arcs use `parent_arc_id`; independent simultaneous plots are parallel arcs. A long-running arc may overlap many shorter arcs. `chapter_summaries.arc_ids` contains every applicable arc. An optional `dominant_arc_id` is a non-exclusive ordering hint and must be labelled “主显示剧情（非排他）”.

### Rendering contract

Render one swimlane per arc (or one stacked interval row on narrow screens), with child arcs indented beneath their parent. Keep parallel lanes visible side by side. Do not merge two intervals merely because their chapter ranges overlap; merge only records with the same stable arc ID.

Each chapter row displays all active arc labels, phase, and status. Selecting a chapter range highlights every intersecting interval and presents an overlap summary listing the arc IDs, titles, events, and participating entities. Selecting an arc provides reverse links to chapters and evidence; selecting an entity or event provides all arcs that contain it.

Unknown end chapters are drawn open-ended and labelled `未完`; no end is invented. Conflicting intervals remain visible with a conflict badge and links to both evidence sets. Evidence does not become stronger because two arcs overlap.

### Ordering and accessibility

Use deterministic ordering: parent before child, then `chapter_start`, then `chapter_end` (open-ended last), then stable arc ID. Do not rely on color alone; pair lane colors with text, icons, or patterns. The mobile fallback is a chapter-indexed list that preserves all overlapping labels and the same reverse lookups. Keep active filters, overlap state, and a `清除筛选` control visible.

## Style analysis

Style analysis is an analytical view, not a replacement for story facts. Keep observations in a separate run artifact (for example `style-observations.json`) and link every claim to chapter ranges and evidence IDs.

```json
{
  "id": "sty_char_f01_001",
  "scope": "character",
  "entity_id": "char_main",
  "dimension": "speech",
  "claim": "正式场合使用克制短句，亲近关系中增加调侃语气。",
  "chapter_start": 1,
  "chapter_end": 80,
  "stability": "contextual",
  "evidence_ids": [],
  "counterexamples": [],
  "confidence": "inferred"
}
```

Required fields are `scope`, `dimension`, `claim`, chapter range, evidence IDs, confidence (`explicit`, `inferred`, or `uncertain`), and stability (`stable`, `evolving`, or `contextual`). Unsupported subjective labels must not be emitted as facts. Counterexamples and limitations should be recorded whenever the claim is not universal.

Cover these dimensions when evidence permits:

- 作品行文：句长、标点、对话比例、描写密度、段落节奏、章末钩子；
- 叙事方式：视角、时间顺序、倒叙／插叙、聚焦、信息释放、冲突升级；
- 人物刻画：外貌、行为、心理、关系差异与跨阶段变化；
- 关键人物语言：口头禅、语气词、称呼、礼貌等级、句末形式、语言功能；
- 关键人物行为：冲突反应、决策方式、对弱者态度、隐瞒／谈判／行动模式。

The dashboard must distinguish measured statistics from interpretive observations. Show the chapter range, confidence, stability, evidence count, and counterexample count beside every conclusion. When observations across ranges disagree, show both as evolving or contextual instead of averaging them into one timeless trait. Style views may be filtered by character, arc, chapter range, and evidence status, and should link back to the exact source excerpts without exposing internal field names to readers.

Validate this artifact before dashboard generation:

```powershell
python scripts/validate_style_observations.py --graph <graph.json> --style-observations <style-observations.json> --output <style-validation.json>
```

`build_dashboard.py` performs the same validation when it auto-discovers the file beside `graph.json` or receives `--style-observations`.
