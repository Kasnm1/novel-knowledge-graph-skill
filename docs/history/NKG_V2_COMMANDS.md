# NKG v2 operational commands

The public Skill remains one Skill. These commands expose the modular internal runtime without breaking historical entry points.

```powershell
# Build the smallest complete, accuracy-preserving model packet
python scripts/build_extraction_packet.py --graph <graph.json> --excerpts-jsonl <range.jsonl> --chapter-start 301 --chapter-end 310 --candidates <candidates.json> --output <packet.json>

# Semantic story-world invariants
python scripts/audit_graph_invariants.py --graph <graph.json> --report <invariants.json>

# A/B gate before accepting a token/retrieval optimization
python scripts/accuracy_regression_gate.py --baseline <baseline.json> --optimized <optimized.json> --report <accuracy.json>

# Provenance/completeness quality metrics
python scripts/build_quality_report.py --graph <graph.json> --output <quality.json>

# Compare two spoiler-safe snapshots
python scripts/build_snapshot_diff.py --graph <graph.json> --from-chapter 300 --to-chapter 400 --output <diff.json>

# Optional checkpoints for long books
python scripts/build_snapshot_checkpoints.py --graph <graph.json> --output-dir <checkpoints> --interval 50

# Final fail-closed artifact build, with optional checkpoints
python scripts/build_expansion_artifacts.py --graph <graph.json> --output-dir <derived> --checkpoint-interval 50
```

Accuracy rule: if a packet exceeds its configured context budget, split/retrieve more intelligently; do not truncate mandatory candidates, evidence or required history.
