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
