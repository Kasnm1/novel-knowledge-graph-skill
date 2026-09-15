# Novel Knowledge Graph Skill

Evidence-backed tooling for turning novels and serialized fiction into replayable temporal knowledge graphs, story bibles, and readable dashboards.

面向小说和连载文本的证据驱动拆书 Skill：把章节事实整理为可回放的时序知识图谱、故事圣经、关系与剧情视图，以及受预算约束的 AI 上下文包。

## What it provides

- Stable one-run-per-book/edition workflow with collision-resistant run identity.
- Evidence-linked extraction for chapters, characters, items, abilities, locations, organizations, relationships, romance and intimacy.
- Story arcs, overlapping timelines, collections and membership views for intersecting groups.
- Controlled taxonomies for item roles, ability categories, organization/location hierarchies and relationship lanes.
- Foreshadowing/payoff tracking, style observations, chapter pacing and bounded AI exports.
- Deterministic merge, validation, snapshot, audit and dashboard-generation scripts.
- Growth/world expansion: protagonist achievements, battle records with as-of realms, resources, fictional-world topology, territory replay, side-character relation coverage, commitments, secret/knowledge views, mortality, economy and narrative rhythm.
- Reader-mode spoiler cutoff, evidence-linked source reader, safe run garbage collection, true-coverage run index, and cross-book trope comparison.

## Growth / world expansion

The expansion keeps `graph.json` as the only story-fact source. It adds exactly one optional top-level fact family, `commitments[]`; achievements, combat tables, inventories, death lists, knowledge matrices and map layouts are derived.

For legacy runs, use the compatibility-aware entry points:

```powershell
python scripts/check_fragment_expanded.py --fragment <fragment.json> --graph <graph.json>
python scripts/merge_graph_expanded.py --input <fragments...> --output <graph.json>
python scripts/validate_full_graph.py --graph <graph.json>
python scripts/build_expansion_artifacts.py --graph <graph.json> --output-dir <derived-dir>
```

Optional reader-safe delivery:

```powershell
python scripts/build_expansion_artifacts.py --graph <graph.json> --chapters-jsonl <chapters.jsonl> --cutoff 300 --output-dir <share-dir>
```

The extended dashboard includes one chapter slider shared by achievements, battle records, resources, world/territory, skill categories, side-character relations/co-occurrence, commitments/favors, secret propagation, foreshadowing/payoff, level progression, chapter rhythm, romance milestones, mortality/inheritance, economy and rules.

See `references/expansion-schema.md` and `references/expansion-workflows.md`.

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

The test suite checks the deterministic contracts used by merge, validation, views, exports and dashboard readability. If your Codex installation includes the `skill-creator` utility, also run its `quick_validate.py` against this directory to check Skill structure and frontmatter.

## Scope and data hygiene

This repository contains the reusable Skill only. It intentionally does **not** contain novels, extracted chapters, canonical runs, dashboards generated for a particular book, credentials, or private run data. Keep those in a separate workspace such as `U:\chaishu\runs`.

The bundled Cytoscape runtime is distributed with its accompanying license notice at `assets/CYTOSCAPE-LICENSE.txt`.

## License

No repository license is declared yet. Add one before redistributing under a specific open-source license.
