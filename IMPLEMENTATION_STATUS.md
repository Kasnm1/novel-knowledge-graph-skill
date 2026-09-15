# Novel Knowledge Graph expansion — final delivery status

The expansion is implemented as a compatibility-safe layer over the existing Skill while preserving `graph.json` as the only story-fact source.

## Implemented

- `commitments[]` as the only new top-level fact family.
- Controlled vocabularies for skill/concept/resource/combat/commitment/payoff/cliffhanger semantics.
- Structured event facets: combat, transaction, mortality, information and payoff.
- Battle records using chapter-time level replay instead of final realm state.
- Derived protagonist achievements, resource ledger, fictional-world topology, territory replay and travel paths.
- Side-character co-occurrence matrix, high-co-occurrence/no-relation review candidates and relation timeline.
- Skill category matrix and resource rarity/supply semantics.
- Commitments lifecycle and `owes_favor_to` favor ledger.
- Secret knowledge histories and information propagation edges.
- Foreshadowing gantt data, payoff spans, level progression, chapter rhythm/POV/cliffhanger, romance milestones and chapter diff.
- Mortality/revival, inheritance/teaching/item-lineage, economy/transactions, rule concepts and style/voice exports.

## Final integration layer

- `derive_asof_views(graph, chapter)` creates one authoritative Python chapter snapshot before any downstream derivation.
- Strict spoiler closure filters future entities, names/aliases, summary/description, attributes/current state, evidence, event/relation/state histories, commitments, romance status, foreshadowing payoff and style observations.
- Untimed legacy prose/aliases/attributes are treated as temporal-provenance gaps instead of silently leaking into a share build.
- `build_unified_dashboard.py` merges the original relationship graph, entity repository, story arcs and collections with all expansion panels.
- The unified Dashboard has one slider and one `snapshotAt(chapter)` object; every panel renders from that same state.
- `build_expansion_artifacts.py` is fail-closed: every child process return code is checked, all required artifacts must exist, and `artifact-manifest.json` records step results plus artifact SHA-256 fingerprints.
- Backfill candidates include an auditable scan receipt: requested/actual ranges, readable/missing chapters, malformed index rows, per-kind hit/emission/truncation counts, cutoff and unresolved/confirmed/excluded review progress.
- Candidate scans return nonzero when requested source coverage is incomplete.
- The source reader fails on missing prepared text and supports overlapping evidence highlights without one quote erasing another.
- GC is transactional: parent/child candidates are deduplicated, an operation manifest is written before mutation, partial failures roll back, applied archives can be restored, and purge requires a valid manifest plus matching fingerprints.
- True-coverage run index and cross-book trope comparison remain available.
- Compatibility entry points for fragment check, merge and full validation remain available.
- Safe relation coalescing in the expanded merge prevents an overlapping open restatement from erasing a known `valid_to`.

## Canonical commands

```powershell
python scripts/check_fragment_expanded.py --fragment <fragment.json> --graph <graph.json>
python scripts/merge_graph_expanded.py --input <fragments...> --output <graph.json>
python scripts/validate_full_graph.py --graph <graph.json>
python scripts/derive_asof_views.py --graph <graph.json> --chapter 300 --output <snapshot.json>
python scripts/build_expansion_artifacts.py --graph <graph.json> --chapters-jsonl <chapters.jsonl> --collection-manifest <dashboard-views.json> --output-dir <derived-dir>
```

## Acceptance coverage

The CI suite now covers:

- schema/extension compatibility and battle-time level replay;
- unified as-of commitment/resource/skill/voice state;
- spoiler-marker absence from strict artifacts;
- candidate cutoff, missing-source and review-progress receipts;
- overlapping evidence highlighting;
- fail-closed one-command builds;
- GC parent/child dedupe, rollback, restore, valid purge and tamper rejection;
- a real headless-Chrome slider test across graph/repository/arcs/collections and expansion panels;
- non-monotonic chapter-slider movement to catch stale final-state caches;
- a 1200-chapter / 450-character performance and peak-memory acceptance fixture.

`build_expansion_dashboard.py` is retained only for backward compatibility. New delivery builds use the unified Dashboard.
