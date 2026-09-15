# Overlapping story arcs and timeline rendering

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

## Rendering contract

Render one swimlane per arc (or one stacked interval row on narrow screens), with child arcs indented beneath their parent. Keep parallel lanes visible side by side. Do not merge two intervals merely because their chapter ranges overlap; merge only records with the same stable arc ID.

Each chapter row displays all active arc labels, phase, and status. Selecting a chapter range highlights every intersecting interval and presents an overlap summary listing the arc IDs, titles, events, and participating entities. Selecting an arc provides reverse links to chapters and evidence; selecting an entity or event provides all arcs that contain it.

Unknown end chapters are drawn open-ended and labelled `未完`; no end is invented. Conflicting intervals remain visible with a conflict badge and links to both evidence sets. Evidence does not become stronger because two arcs overlap.

## Ordering and accessibility

Use deterministic ordering: parent before child, then `chapter_start`, then `chapter_end` (open-ended last), then stable arc ID. Do not rely on color alone; pair lane colors with text, icons, or patterns. The mobile fallback is a chapter-indexed list that preserves all overlapping labels and the same reverse lookups. Keep active filters, overlap state, and a `清除筛选` control visible.
