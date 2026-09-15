# Final delivery command map

The final system keeps `graph.json` as the only story-fact source and exposes one authoritative chapter snapshot plus one unified Dashboard.

```powershell
# Fragment gate
python scripts/check_fragment_expanded.py --fragment <fragment.json> --graph <graph.json> --chapters-jsonl <chapters.jsonl>

# Merge (supports commitments and safe relation intervals)
python scripts/merge_graph_expanded.py --input <fragments...> --output <graph.json> --manifest <source_manifest.json>

# Publish validation: base + expansion contracts
python scripts/validate_full_graph.py --graph <graph.json> --manifest <source_manifest.json>

# Authoritative Python as-of snapshot used by audits/tests/other consumers
python scripts/derive_asof_views.py --graph <graph.json> --chapter 300 --output <snapshot-300.json>

# Final fail-closed build: unified Dashboard + views + candidate audit + optional reader
python scripts/build_expansion_artifacts.py --graph <graph.json> --chapters-jsonl <chapters.jsonl> --collection-manifest <dashboard-views.json> --output-dir <dir>

# Spoiler-safe share build. All output surfaces are closed to chapter 300 before publication.
python scripts/build_expansion_artifacts.py --graph <graph.json> --chapters-jsonl <chapters.jsonl> --collection-manifest <dashboard-views.json> --cutoff 300 --output-dir <dir>

# Build manifest
# <dir>/artifact-manifest.json records every step return code and SHA-256 for required artifacts.

# Auditable legacy backfill candidates
python scripts/build_expansion_candidates.py --graph <graph.json> --chapters-jsonl <chapters.jsonl> --chapter-start 1 --chapter-end 500 --cutoff 500 --output <candidates.json>

# Reader only (strict cutoff and overlap-aware evidence highlighting)
python scripts/build_reader_overlay.py --graph <graph.json> --chapters-jsonl <chapters.jsonl> --cutoff 300 --output <reader.html>

# Real coverage index / cross-book comparison
python scripts/build_run_index.py --runs-root <runs> --json <INDEX.json> --html <INDEX.html>
python scripts/compare_runs.py --graph <run1/graph.json> --graph <run2/graph.json> --output <comparison.json>

# GC is dry-run by default. Inspect the plan before --apply.
python scripts/gc_run.py --root <runs>
python scripts/gc_run.py --root <runs> --apply

# Restore an applied archive
python scripts/gc_run.py --root <runs> --restore <runs/_gc_archive/<timestamp>>

# Purge only after manifest and fingerprints validate
python scripts/gc_run.py --root <runs> --purge <runs/_gc_archive/<timestamp>>
```

`build_expansion_dashboard.py` remains only as a compatibility renderer for older workflows. New builds use `build_unified_dashboard.py` through `build_expansion_artifacts.py` so graph, repository, story arcs, collections and expansion panels share one slider state.
