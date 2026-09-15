# Upstream design notes

The workflow was informed by the following pinned GitHub revisions. The local Python helpers were independently authored for this skill; no upstream source files are vendored into the skill.

| Project | Revision | License | Adopted design idea |
|---|---|---|---|
| QQ-L-XX/novel-deconstruct | `c75702bece3d110674452226528c0cb92c1b194a` | MIT | Scene-aware chapter analysis and value-change tracking |
| Ce-Legend/novel-analysis-agent | `93e45864937cb3bc0794a5bdcfaaebe94e154c02` | MIT | Staged ingest/split/analyze/aggregate/evaluate artifacts, resumability, and report checks |
| google/langextract | `bd5d1ebb51db51e9f6d054c026489d1d8127b005` | Apache-2.0 | Exact source grounding, multi-pass long-document extraction, and reviewable HTML output |
| Mochocyang/QMAI | `03fe77563ef766257979d949b9a8eca47fb33460` | GPL-3.0 | Alias normalization, pinned evidence records, graph entity types, and foreshadowing lifecycle |
| wordflowlab/novel-writer | `e4190d407e736affa42ba55a70d91961c6ce3932` | MIT | Character arc, relationship evolution, and story-structure analysis categories |
| cytoscape/cytoscape.js | `3.34.3` | MIT | Mature graph rendering, layouts, selection, zooming, and interaction in the local dashboard |

Local inspection copies are stored outside the skill under the workspace directory `novel-knowledge-graph-workflow/upstream/`. QMAI was sparse-checked out to the relevant analysis and graph paths. Do not redistribute or incorporate its GPL-licensed code into a differently licensed product without honoring GPL-3.0.

## Deliberate differences

- This workflow analyzes the requested contiguous range rather than sampling later chapters.
- Temporal state changes are first-class records; a latest-state snapshot never replaces history.
- Loss-like changes require a causal reason and supporting quotation.
- Foreshadowing keeps observation, interpretation, confidence, progression, and payoff separate.
- The dashboard is generated from one canonical `graph.json` and contains no remote JavaScript dependency.
- Cytoscape.js is bundled locally under `assets/`; its license is preserved as `assets/CYTOSCAPE-LICENSE.txt`.
