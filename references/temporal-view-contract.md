# Temporal view and spoiler-closure contract

All historical and reader-safe surfaces must answer **what was knowable at chapter N**, not merely filter records whose primary `chapter` exceeds N.

## One state boundary

Use `derive_asof_views(graph, chapter)` as the Python authority. Dashboards use one shared chapter snapshot and must not let individual panels implement independent final-state shortcuts.

A historical snapshot closes, at minimum:

- entities not yet introduced;
- canonical names and aliases not yet established;
- entity summary/description prose written from later knowledge;
- attributes and current-state values acquired later;
- future evidence, events, relations, state changes and item roles;
- commitment observations/status/resolution;
- romance milestones/status;
- foreshadowing payoff/status;
- timed style/voice observations;
- derived labels that embed entity names.

## Temporal provenance for new extraction

New or backfilled data should carry enough timing to make those projections deterministic.

### Names and aliases

Prefer `name_history[]` rows with `valid_from` / optional `valid_to`. If a stable scalar canonical name is retained, record `name_first_chapter` when it first becomes safe to display. String aliases need `metadata.alias_first_chapter[entity_id][alias]` or should be converted to timed alias records.

### Entity prose

For summary/description that changes with story knowledge, prefer `summary_history[]` / `description_history[]` with chapter or validity start. A scalar may instead carry `summary_first_chapter` / `description_first_chapter`, including metadata maps for compatibility.

### Attributes

Time-varying attributes belong in `state_changes` when they are state. Descriptive attributes that remain on the entity need `attribute_history[]` or `metadata.attribute_first_chapter[entity_id][key]`.

### Style and character voice

Every `style_observation` used in an as-of or reader view must carry at least one temporal anchor: `chapter`, `chapter_start`, or `valid_from`. A whole-book aggregate without a temporal anchor is a final-book analytic and is hidden from historical snapshots.

## Legacy compatibility

Legacy records without temporal provenance are not silently treated as early-book facts. Strict spoiler mode hides them and records a temporal-provenance gap. `build_expansion_candidates.py` emits review candidates:

- `temporal_name`
- `temporal_summary`
- `temporal_attribute`
- `temporal_style`

Resolve those candidates by evidence-backed timing, explicit exclusion, or a documented decision to keep the field final-book-only.

## Regression rule

Spoiler tests should seed unmistakable future marker text and assert that strict graph snapshots, cutoff Dashboards, candidate outputs and readers contain none of it. Browser tests must also move the slider backward after visiting a later chapter to catch stale final-state caches.
