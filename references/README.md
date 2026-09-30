# Reference map

Load references through `reference-routing.json`: each operation mode lists the
files it loads; `lookup` files are opened only for a specific question.

| File | What it holds |
|---|---|
| `schema.md` | canonical graph schema: entities, events, relations, state changes, evidence |
| `expansion-schema.md` | commitments, event facets (combat, mortality, transactions…), world geography, and their workflows |
| `analysis-protocol.md` | how a chapter is read and what is recorded, the rules behind the audit |
| `chapter-audit-spec.md` | audit protocol 2: the per-chapter audit card and its receipts |
| `fragment-authoring.md` | writing a fragment, including the `FragmentBuilder` helper |
| `ai-workflow.md` | survey → registry → lanes → capsule → extraction → verification → reconcile → editorial → backfill |
| `verifier-prompt.md` | the independent blind verifier's prompt and verdict format |
| `retrieval-and-efficiency.md` | retrieval levels R1–R4, caching, budgets, the accuracy A/B gate |
| `temporal-view-contract.md` | as-of views and spoiler closure |
| `overlapping-timelines-and-membership.md` | overlapping arcs and multi-membership, data and rendering |
| `dashboard.md` | reader dashboard contracts: presentation, performance, taxonomy, display hints, collections, arcs, style |
| `architecture.md` | module boundaries and the run / version / concurrency contract |
| `ai-context.md` | bounded AI context exports |
| `TASK-SPEC.template.md` | per-run task spec template |

JSON companions: `execution-profiles.json`, `retrieval-profiles.json`,
`coverage-receipt.template.json`, `execution-receipt.template.json`,
`resume-capsule.template.json`, and the fixtures `accuracy-context-fixture.json`,
`dashboard-performance-fixture.json`, `overlap-membership-fixture.json`.

Development history (old contracts, gap logs, the pre-protocol-2 parallel
extraction notes) lives in `docs/history/` and is not loaded by any mode.

## Upstream design notes

The workflow was informed by the following pinned GitHub revisions. The local
Python helpers were independently authored for this skill; no upstream source
files are vendored into the skill.

| Project | Revision | License | Adopted design idea |
|---|---|---|---|
| QQ-L-XX/novel-deconstruct | `c75702bece3d110674452226528c0cb92c1b194a` | MIT | Scene-aware chapter analysis and value-change tracking |
| Ce-Legend/novel-analysis-agent | `93e45864937cb3bc0794a5bdcfaaebe94e154c02` | MIT | Staged ingest/split/analyze/aggregate/evaluate artifacts, resumability, and report checks |
| google/langextract | `bd5d1ebb51db51e9f6d054c026489d1d8127b005` | Apache-2.0 | Exact source grounding, multi-pass long-document extraction, and reviewable HTML output |
| Mochocyang/QMAI | `03fe77563ef766257979d949b9a8eca47fb33460` | GPL-3.0 | Alias normalization, pinned evidence records, graph entity types, and foreshadowing lifecycle |
| wordflowlab/novel-writer | `e4190d407e736affa42ba55a70d91961c6ce3932` | MIT | Character arc, relationship evolution, and story-structure analysis categories |
| cytoscape/cytoscape.js | `3.34.3` | MIT | Graph rendering, layouts, selection, zooming, and interaction in the local dashboard |

Do not redistribute or incorporate QMAI's GPL-licensed code into a differently
licensed product without honoring GPL-3.0. Cytoscape.js is bundled under
`assets/` with its license in `assets/CYTOSCAPE-LICENSE.txt`.
