# Expansion workflows

This file is the operational companion to `expansion-schema.md`.

## New extraction

Use the existing event/entity/relation/state-change structures first. The only new top-level array is `commitments`.

- Battle outcome: `events[].combat`, not `duels[]`.
- Achievement: derived from canonical facts, never `achievements[]`.
- Resource balance: targeted quantity state changes + `item_roles`, never `inventory[]`.
- Secret: `concept` category `secret` + knowledge state changes, never `secrets[]`.
- Territory: temporal `controlled_by`, never `territories[]`.
- Death/revival: mortality facet + health state changes, never `deaths[]`.

Run the expanded fragment gate before merge:

```powershell
python scripts/check_fragment_expanded.py --fragment <fragment.json> --graph <graph.json> --chapters-jsonl <chapters.jsonl>
```

## Merge and publish

```powershell
python scripts/merge_graph_expanded.py --input fragments/*.json --output graph.json --manifest source_manifest.json
python scripts/validate_full_graph.py --graph graph.json --manifest source_manifest.json --base-report validation.json --extension-report validation-expansion.json
```

A publish passes only when both the base validator and expansion validator pass.

## Backfill legacy runs

First derive everything possible without rereading prose:

```powershell
python scripts/derive_novel_views.py --graph graph.json --output derived/novel-views.json
```

Then generate unresolved review candidates:

```powershell
python scripts/build_expansion_candidates.py --graph graph.json --chapters-jsonl chapters.jsonl --output derived/expansion-candidates.json
```

Resolve every candidate as confirmed, excluded, or unresolved. Do not silently drop candidates.

## Dashboard

```powershell
python scripts/build_expansion_artifacts.py --graph graph.json --output-dir dashboard-expanded
```

With a prepared chapter index, the same command also builds the evidence-linked reader:

```powershell
python scripts/build_expansion_artifacts.py --graph graph.json --chapters-jsonl chapters.jsonl --output-dir dashboard-expanded
```

## Spoiler-safe sharing

The cutoff happens before view-model construction so future records cannot leak through counters, search or tooltips:

```powershell
python scripts/build_expansion_artifacts.py --graph graph.json --chapters-jsonl chapters.jsonl --cutoff 300 --output-dir share-ch300
```

Or build a filtered graph directly:

```powershell
python scripts/filter_graph_asof.py --graph graph.json --chapter 300 --output graph-asof-300.json
```

## Run hygiene

Show real analyzed coverage rather than trusting directory names:

```powershell
python scripts/build_run_index.py --runs-root U:\chaishu\runs --json INDEX.json --html INDEX.html
```

Safe garbage collection defaults to dry-run:

```powershell
python scripts/gc_run.py --root U:\chaishu\runs
python scripts/gc_run.py --root U:\chaishu\runs --apply
```

`--apply` moves files into `_gc_archive/<timestamp>/` and writes a fingerprint manifest. Permanent deletion requires explicitly purging one of those archive directories.

## Cross-book comparison

```powershell
python scripts/compare_runs.py --graph run-a/graph.json --graph run-b/graph.json --output trope-comparison.json
```

Only aggregate metrics are combined; entity IDs from different books are never mixed.
