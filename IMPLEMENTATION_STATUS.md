# Novel Knowledge Graph expansion — implementation status

This expansion is implemented as a compatibility-safe layer over the existing Skill.

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
- One chapter-synchronized dashboard containing all expansion panels.
- Spoiler-safe as-of filtering before rendering.
- Evidence-linked side-by-side source reader.
- Legacy-run backfill candidate scanner with unresolved/confirmed/excluded workflow.
- Coverage reports with explicit denominators; zero input is never reported as a completeness pass.
- Safe run garbage collection with dry-run default, SHA-256 manifest and recoverable archive.
- True-coverage run index and cross-book trope comparison.
- Compatibility entry points for fragment check, merge and full validation.
- Safe relation coalescing in the expanded merge: an overlapping open restatement no longer erases a known `valid_to`.

## Primary commands

```powershell
python scripts/check_fragment_expanded.py --fragment <fragment.json> --graph <graph.json>
python scripts/merge_graph_expanded.py --input <fragments...> --output <graph.json>
python scripts/validate_full_graph.py --graph <graph.json>
python scripts/build_expansion_artifacts.py --graph <graph.json> --output-dir <derived-dir>
```

## Verification

The expansion test suite covers schema validation, battle-time level replay, derived-view presence, spoiler filtering, candidate generation, dashboard panel coverage, cross-run metrics and GC candidate discovery.
