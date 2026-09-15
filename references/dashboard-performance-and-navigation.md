# Dashboard repository navigation and rendering performance

The repository is a set of navigable views, not one unbounded list. Every view must provide an explicit category, a stable sort, pagination or virtual scrolling, and a bounded render window. This applies to characters, items, skills, relationships, timelines, romance lines, intimacy events, foreshadowing, and style observations.

## View model

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

## Required categories

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

## Pagination and filtering

Use server/worker-side filtering and sorting before rendering. For ordinary card and table repositories, default to 24 records per page with controls for 12/24/48/96. For very large or continuously growing lists, use cursor pagination (`next_cursor`) rather than offset pagination; cursors must encode the stable sort key and be invalidated when the underlying snapshot changes.

Always show total matched count when known, current page/range, active filters, and a “清除筛选” action. Search is debounced and must search indexed fields rather than repeatedly scanning and rerendering the complete graph. Empty, loading, and error states are explicit. Do not silently truncate results.

## Timeline, romance, and intimacy views

Timelines use a chapter-window navigator: choose a start/end range, then render only arcs and events intersecting that range while preserving overlap semantics. Large ranges switch to a chapter-indexed list or condensed overview; details load on expansion.

Romance lines are grouped by route or pair, with one route card per stable route ID. Show stage, first/last evidence chapter, open questions, and related events; paginate routes and virtualize event histories inside an expanded route.

Intimacy events are grouped by chapter range and participants, not placed in an unbounded flat feed. The default view shows a privacy-conscious event summary and evidence status; full excerpts are loaded only when the user expands an event. Do not infer intimacy from generic contact events, and do not merge distinct events merely because participants match.

## Rendering budget and virtualization

The initial render must be bounded: render at most 50 list rows/cards or 400 graph nodes in the viewport plus a small overscan window. Use virtualization (`IntersectionObserver`, a virtual-list component, or an equivalent framework-neutral implementation) for lists, graph labels, event feeds, and nested histories. Destroy off-screen detail panels and release observers when views change.

Load heavy sections progressively: summary counts first, then visible cards, then relationships/events/evidence on demand. Cache immutable snapshot-derived summaries by `(snapshot_id, view_id, query_hash)` and invalidate on snapshot change. Never recompute the entire graph for a local filter or page turn.

If a query would exceed the render budget, show a condensed aggregate with the exact matched count and offer narrower filters. A performance fallback must preserve navigation and evidence links; it may reduce decoration or collapse secondary labels, but must not drop records from the underlying result set.

## Accessibility and consistency

Pagination, virtual scrolling, and category tabs must be keyboard reachable and expose accessible labels. Announce page changes and result counts. Keep card heights predictable where possible to prevent scroll jumps; preserve focus when rows are recycled. Do not rely on color alone for category or relationship distinctions.
