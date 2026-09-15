# Interactive dashboard contract

The dashboard is a view of `graph.json`; it must not become an independent source of truth.

## Required interactions

Apply `references/dashboard-taxonomy-and-relation-layout.md` for relationship layout, canonical names and aliases, repository categories, protagonist-linked relation labels, and entity detail sections. Appearance heat is not a primary layout. Use grouped lanes and list/tree fallbacks instead of an unbounded force-directed cloud.

Apply `references/dashboard-taxonomy-and-relation-layout.md` for the relationship graph, canonical-name display, category navigation, protagonist-linked relation labels, and entity detail panel. Do not expose appearance heat as a primary layout. Use grouped lanes/list fallbacks instead of an unbounded force-directed cloud.

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

## Presentation defaults

- Use color for entity type, not moral alignment.
- Localize all reader-facing entity types, state facets, actions, relations, statuses, confidence levels, event types, and review categories. Choose setting-native terms per book; keep stable English schema keys only inside data and code.
- Visually distinguish explicit facts, inferences, and uncertainty.
- Label chapter ranges on relations and state changes.
- Keep quotations collapsed or compact until selected.
- Evidence summaries deduplicate IDs, state the evidence count and chapter span, and show short one-line previews before expansion. Never shorten or rewrite the quotation stored in `graph.json`; truncation is display-only.
- For large graphs, show important connected entities first and retain filters for the rest.
- Keep chapter scrubbing responsive: coalesce slider input to at most one render per animation frame, pre-index relations and state changes by entity, lazily render only the active feed/repository, avoid relabelling every node on each chapter change, and reduce layout work for large visible sets. Show visible/total node and relation counts so filtering remains legible.
- Keep the page vertically scrollable at every breakpoint. The detail panel and repository may have their own overflow regions, but no fixed-height container may trap content without a visible scrollbar or keyboard access.

## Privacy and portability

Prefer a self-contained local HTML file with embedded graph data and no remote runtime dependency. Do not upload novel text or API keys. Include only short evidence excerpts needed for verification.
# Overlay rules for timelines and collection membership

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
# Overlay rules for timelines and collection membership

Treat arc membership and collection membership as many-to-many relationships;
follow `references/overlapping-timelines-and-membership.md` for the normative
contract. Timeline arcs render on independent lanes, preserving overlapping
chapter ranges and multi-arc chapter markers. Repository and graph surfaces
render one canonical entity card/node, with capped membership chips and an
expandable list of all matched collections, reasons, provenance, and evidence.
Union/intersection counts deduplicate stable entity IDs and visibly announce
match-any versus match-all filtering. Keep type, relation state, arc, and
collection semantics on separate visual channels; color alone is insufficient.
## Repository navigation and performance

Apply `dashboard-performance-and-navigation.md`: expose explicit categories, stable sorting, pagination or cursor navigation, and virtualized/lazy rendering. Characters, items, timelines, romance routes, and intimacy events must be deduplicated by stable ID while retaining all category memberships. Initial rendering is bounded; large ranges use chapter-window filtering and progressive detail loading.
