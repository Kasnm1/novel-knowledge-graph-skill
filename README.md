# Novel Knowledge Graph Skill

Evidence-backed tooling for turning novels and serialized fiction into replayable temporal knowledge graphs, story bibles, and readable dashboards.

面向小说和连载文本的证据驱动拆书 Skill：把章节事实整理为可回放的时序知识图谱、故事圣经、关系与剧情视图，以及受预算约束但不牺牲准确率的 AI 上下文包。

## What it provides

- Stable one-run-per-book/edition workflow with collision-resistant run identity.
- Evidence-linked extraction for chapters, characters, items, abilities, locations, organizations, relationships, romance and intimacy.
- Story arcs, overlapping timelines, collections and membership views for intersecting groups.
- Controlled taxonomies for item roles, ability categories, organization/location hierarchies and relationship lanes.
- Foreshadowing/payoff tracking, style observations, chapter pacing and bounded AI exports.
- Deterministic merge, validation, snapshot, audit and dashboard-generation scripts.
- Growth/world expansion: protagonist achievements, battle records with as-of realms, resources, fictional-world topology, territory replay, side-character relation coverage, commitments, secret/knowledge views, mortality, economy and narrative rhythm.
- Strict reader-mode spoiler closure, evidence-linked source reader, transactional run garbage collection, true-coverage run index, and cross-book trope comparison.
- Modular `scripts/nkg/` runtime with pre-indexed graph access, accuracy-preserving extraction packets, semantic story invariants, data-quality views, snapshot diffs and long-run checkpoints.

## Canonical temporal model

`graph.json` remains the only story-fact source. The expansion adds exactly one optional top-level fact family, `commitments[]`; achievements, combat tables, inventories, death lists, knowledge matrices, quality metrics and map layouts are derived.

For any historical chapter, use one authoritative snapshot:

```powershell
python scripts/derive_asof_views.py --graph <graph.json> --chapter 300 --output <snapshot-300.json>
```

The snapshot closes future names/aliases, summaries/attributes, current state, evidence, events, relations, commitments, romance milestones, foreshadowing payoff and timed style observations before derived views are built. Untimed legacy prose is treated as a temporal-provenance gap instead of silently leaking into a spoiler-safe share artifact.

## Modular runtime and token-efficient extraction

The public product remains one Skill. Internally, reusable logic is split into `nkg/core`, `nkg/temporal`, `nkg/extraction`, `nkg/validation`, `nkg/views` and `nkg/domains`. Historical top-level CLI names remain compatibility entry points.

Build an extraction packet with:

```powershell
python scripts/build_extraction_packet.py \
  --graph <graph.json> \
  --excerpts-jsonl <range.jsonl> \
  --chapter-start 301 --chapter-end 310 \
  --candidates <candidates.json> \
  --output <packet.json>
```

Retrieval escalates monotonically from R1 local evidence to R4 complete relevant coverage. Token budgets are diagnostic only: mandatory candidates, evidence and required history are never silently truncated. If the complete packet is too large, split the task or expand the context window; unresolved evidence remains unresolved rather than guessed.

Before accepting a retrieval/token optimization, compare its structured result with a baseline:

```powershell
python scripts/accuracy_regression_gate.py --baseline <baseline.json> --optimized <optimized.json> --report <accuracy.json>
```

Confirmed record recall, high-risk candidate recall and evidence linkage may not regress.

## One unified Dashboard

New builds no longer split the old graph/repository/story-arc/collection UI from the growth/world panels. `build_unified_dashboard.py` produces one Dashboard with one chapter slider and one shared snapshot state for:

- relationship graph and entity repository;
- story arcs and saved collections;
- achievements, battle records, resources and skill categories;
- world/territory, side-character relations/co-occurrence;
- commitments/favors, secrets/knowledge propagation;
- foreshadowing/payoff, level progression, chapter rhythm;
- romance milestones, mortality/inheritance, economy, rules and narrative voice.

`build_expansion_dashboard.py` remains only for backward compatibility.

For audit-oriented data views:

```powershell
python scripts/build_quality_report.py --graph <graph.json> --output <quality.json>
python scripts/build_snapshot_diff.py --graph <graph.json> --from-chapter 300 --to-chapter 400 --output <diff.json>
```

Quality indicators report provenance/completeness risk; they are not probabilities that a story fact is true.

## Final one-command build

```powershell
python scripts/build_expansion_artifacts.py \
  --graph <graph.json> \
  --chapters-jsonl <chapters.jsonl> \
  --collection-manifest <dashboard-views.json> \
  --checkpoint-interval 50 \
  --output-dir <derived-dir>
```

Spoiler-safe share build:

```powershell
python scripts/build_expansion_artifacts.py \
  --graph <graph.json> \
  --chapters-jsonl <chapters.jsonl> \
  --collection-manifest <dashboard-views.json> \
  --cutoff 300 \
  --output-dir <share-dir>
```

The build is fail-closed. Structural validation, expansion validation, semantic invariants, spoiler closure, derived views, quality audit, Dashboard, candidate scan and reader are checked individually. Any required step or artifact failure makes the command fail. `artifact-manifest.json` records subprocess return codes, timings and SHA-256 fingerprints of required outputs. Optional checkpoints prebuild strict snapshots for repeated long-book navigation.

## Auditable backfill

Legacy candidate scanning reports the requested and actually readable chapter ranges, missing/unreadable source text, malformed index rows, per-kind total/emitted/truncated matches, cutoff and review progress (`unresolved / confirmed / excluded`). Incomplete requested source coverage returns nonzero rather than being reported as a completed scan.

## Safe GC

`gc_run.py` is dry-run by default. `--apply` writes an operation manifest before moving anything, deduplicates parent/child candidates and rolls back partial failures. Applied archives can be restored. Permanent `--purge` requires a valid manifest and matching fingerprints.

See `scripts/NKG_V2_COMMANDS.md`, `references/architecture-v2.md`, `references/accuracy-preserving-token-optimization.md`, `references/expansion-schema.md`, and `references/expansion-workflows.md`.

## Install

Copy this directory to the Codex skills directory and keep the folder name `novel-knowledge-graph`:

```text
%CODEX_HOME%\skills\novel-knowledge-graph
```

On a default Windows installation this is usually:

```text
C:\Users\<you>\.codex\skills\novel-knowledge-graph
```

The skill is automatically discoverable by its `SKILL.md` frontmatter. Read only the reference documents relevant to the current workflow; scripts are intended to be run from a novel's canonical run directory.

## Validate

From this directory:

```powershell
python -m unittest discover -s scripts -p "test_*.py"
```

CI additionally installs real Chrome/Selenium and runs non-monotonic slider tests, cross-panel chapter consistency, spoiler-marker leakage checks, overlapping-evidence highlighting, GC apply/rollback/restore/purge checks, accuracy/runtime regression tests, and a 1200-chapter / 450-character performance fixture.

## Scope and data hygiene

This repository contains the reusable Skill only. It intentionally does **not** contain novels, extracted chapters, canonical runs, dashboards generated for a particular book, credentials, or private run data. Keep those in a separate workspace such as `U:\chaishu\runs`.

The bundled Cytoscape runtime is distributed with its accompanying license notice at `assets/CYTOSCAPE-LICENSE.txt`.

## License

No repository license is declared yet. Add one before redistributing under a specific open-source license.
