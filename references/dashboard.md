# Reader dashboard

One self-contained `dashboard.html`, built from the validated canonical graph. It
is derived and disposable; nothing in it writes back to the graph.

```bash
python scripts/build_reader_dashboard.py --graph <graph.json> --output <dashboard.html> \
  [--display-hints <display-hints.json>] [--ledger <coverage-ledger.json>] [--cutoff <N>] \
  [--model-output <reader-model.json>]
```

`build_expansion_artifacts.py` runs it as its `dashboard` step (the previous
unified dashboard is still written to `legacy/dashboard.html` for comparison).

## Architecture

- **Reader model** (`scripts/nkg/views/reader_model.py`, `build_reader_model.py`):
  every chapter-dependent value is precomputed as an interval `[from, to]` or a
  dated step list, using the temporal core (`nkg/temporal/asof.py`).
- **Page** (`web/`, Vite + Preact + TypeScript + Cytoscape + d3-hierarchy): built
  with `npm run build` into `assets/reader-app.html`, which is committed. The
  builder injects the model into its `<script id="nkg-model">` slot, so Skill
  users need no Node. CI rebuilds the app and fails if the committed copy is stale.
- **The browser never decides what is true at chapter N.** It only picks the
  interval or step that contains the slider chapter (`web/src/model.ts`) and
  assembles sets and trees from intervals (`web/src/sets.ts`).

## What a reader may see at chapter N

These rules live in the reader model; the page must not relax them.

- An entity appears from its first chapter. Its name follows `name_history`;
  aliases follow their first chapters, or the first quotation about the entity
  that contains them.
- A name, alias, summary or attribute with no timing is the analysed end state
  and is shown only at the terminal chapter.
- A state holds from the change that set it until the next change on the same
  facet and target. Volatile facets (`FACET_TTL` in `display_vocabulary.py`:
  location, emotion, injury …) also expire after their TTL unless an audit card
  confirms them again. Stale values are hidden, never shown.
- Relations hold over their inclusive interval; status and stance follow dated
  observations. Romance status follows `romance_status_asof`.
- With `--cutoff N` the graph is closed with `filter_graph` first, and the model
  must pass the late-name leak gate or the build fails.
- The **spoiler lock** (lock button on the chapter axis) caps the slider, links
  and search at the reader's chapter. It is stored per book in the viewer's
  browser.

## Entries

| Entry | Shows |
|---|---|
| 本章 | This chapter only: summary, continuity (承上 / 启下), scenes, events, cast with current state (▲ changed, ✓ confirmed), state and relation changes, threads touched, audit receipts, milestones, a density spark of nearby chapters, and a comparison with an earlier chapter |
| 故事 | Story arcs as lanes up to the current chapter (fixed segments when a book has no editorial arcs); arc pages with recap (after the arc ends), chapters, cast, turning points |
| 人物 | Tiered roster by type; profiles with time-stamped state ("第 X 章起"), organization chips, growth curve per level axis, dossier, relations by group, timeline, related threads |
| 关系 | Focus graph (neighbours boxed by relation group); circle view (people inside their primary organization's box, organizations nested, the unaffiliated grouped into social circles, edges on hover); recent-cast view |
| 世界 | Faction chart and map as zoomable circles in circles (subset = containment, not geography); level ladders; item and skill catalog |
| 线索 | Boards for clues, promises, romance routes and intimate acts, by status at the current chapter |

## Sets and subsets

- Membership: `affiliation`-group relations to an organization, active at N.
  Primary set: an editorial `primary_membership` hint, else the latest-starting
  active membership, else the longest. Other memberships render as dashed copies.
- Organization and place nesting: `subgroup_of` / `part_of` / `located_in`
  between entities of the same type; cycles are cut. Seats: organization →
  location; territory: location `controlled_by` organization.
- Whereabouts: an event of this chapter, else one within 5 chapters, else a
  location state that names a place exactly. No coordinates are ever invented;
  the circle charts say so on screen.
- One organization has one colour everywhere (`web/src/palette.ts`).

## Display hints

`display-hints.json` (from the editorial layer) may carry per entity: `tier`,
dated `headlines`, `arc_bios`, `relation_to_protagonist`, `primary_membership`;
and per arc `arc_recaps`. Without hints, tiers are derived from on-page events
and marked as derived.

## Performance and layout

- Precomputed indexes per model (facts / relations / events by entity); sets are
  computed once per chapter and shared by every view.
- Graphs are capped at 400 nodes; long lists fold after 8 items.
- No horizontal page scroll at 390 px; on phones the navigation is a bottom bar.
- Light theme only, paper and ink palette, CJK serif headings from system fonts.

## Checks

- `scripts/test_reader_model.py`: TTL expiry, confirmation, late names, cutoff
  gate, place links, milestones, pipeline wiring.
- `scripts/test_reader_app_browser.py` (Selenium, required in CI): every entry
  renders without browser errors, early chapters show no future content, the
  spoiler lock caps the slider.
