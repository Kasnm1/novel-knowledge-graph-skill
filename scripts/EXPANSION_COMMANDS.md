# Expansion command map

Use these entry points for the growth/world expansion contract.

```powershell
# Fragment gate
python scripts/check_fragment_expanded.py --fragment <fragment.json> --graph <graph.json> --chapters-jsonl <chapters.jsonl>

# Merge (supports commitments and safe relation intervals)
python scripts/merge_graph_expanded.py --input <fragments...> --output <graph.json> --manifest <source_manifest.json>

# Publish validation: base + expansion contracts
python scripts/validate_full_graph.py --graph <graph.json> --manifest <source_manifest.json>

# Build all derived views/dashboard/audits
python scripts/build_expansion_artifacts.py --graph <graph.json> --chapters-jsonl <chapters.jsonl> --output-dir <dir>

# Spoiler-safe share build
python scripts/build_expansion_artifacts.py --graph <graph.json> --chapters-jsonl <chapters.jsonl> --cutoff 300 --output-dir <dir>

# Legacy backfill candidates
python scripts/build_expansion_candidates.py --graph <graph.json> --chapters-jsonl <chapters.jsonl> --output <candidates.json>

# Real coverage index / safe GC / cross-book comparison
python scripts/build_run_index.py --runs-root <runs> --json <INDEX.json> --html <INDEX.html>
python scripts/gc_run.py --root <runs>
python scripts/compare_runs.py --graph <run1/graph.json> --graph <run2/graph.json> --output <comparison.json>
```
