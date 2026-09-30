# Known gaps

> **Historical archive, not an operating contract.** Current tasks follow `SKILL.md` and `reference-routing.json`. Earlier freeze-toolchain, run-local copy, and whole-build locking proposals below are superseded by `run-isolation.md`: use the current Skill, a lightweight version receipt, immutable worker fragments, and only a short merge/publish lock. Do not load this archive during ordinary continuation work.

> **Current display policy (2026-09-14): spoiler-visible.** Sections about hiding future chapter numbers, aliases, prose, or foreshadowing document historical failures under the former policy. They remain useful evidence about renderer drift, but they are no longer delivery gates. Current chapter verification checks dynamic-state replay only; full-range summaries, names, evidence, history, and payoffs may show future chapters.

> **Current correction policy.** E1 is addressed for new work by append-only `corrections.jsonl` plus deterministic `apply_corrections.py`; legacy in-place fragment repairs remain historical exceptions and should not be copied into new runs.

Weaknesses this workflow has actually shown, with the run that showed them. Each
entry names the evidence and the fix; the ones marked **fixed** were repaired in
the round that found them, while any remaining note must be rechecked against
the current routed references before being treated as open.

Evidence comes from `runs/我的狐仙老婆-full/` (1—550 of 1,319 chapters, 69
fragments, 9,005 records, 4,907 evidence records), which exercised every stage
hard enough to break it. Entries A5—A8, D9, E4 and F1—F2 come from the 501—550
round and the backfill pass over 1—500; **A10—A12 and B5 come from the full-library
re-read of 1—550** (a coverage defect the reader found, not the pipeline).

---

## A. Gaps that lose information silently

### A1. A "reuse only these N" list that is not generated will be incomplete — **fixed, but the pattern is general**

`TASK-SPEC.md` told every parallel worker 「只允许复用下面**五**个已有等级轴，不要新建等级轴」 and then listed **four**. The missing one was `axis_xiuluo_rank`, whose vocabulary (修罗／修罗将军／修罗王) recurs in the next range. A worker with no ID to reuse and a rule forbidding a new one loses the level information without any error.

The half-fix is instructive: deriving the **count** from the graph made the prose correct while the **table** stayed hand-written, so the document contradicted itself. Derive the whole artifact, not the sentence that mentions it.

Two general rules:
- Any list a later round reads must be generated from the graph by the same script that refreshes the spec, and the script must **warn when it adds a row** the previous table did not have (that warning is how the omission surfaced).
- Every prohibition needs an escape hatch. 「不要新建 X」 must be paired with 「遇到新的 X 就记进 `review_issues` 并附引文」, or the worker's only compliant option is to drop the fact.

### A2. The level ladder had no chain-continuity check, and the skill said so — **fixed**

`SKILL.md` admitted it: the audit "checks `before` against `after` *within* a record, so a `before` that fails to chain from the previous record's `after` … is invisible to it and needs a manual read of the ladder." A known blind spot left to manual review is a blind spot.

It cost a reader-visible wrong endpoint: 陈才 has three chapter-343 level changes (baseline 13 / loss 13→5 / recovery 5→10), `rollup_levels.py` orders same-chapter steps **by record ID**, and `_lost < _ten < _thirteen` put the baseline last — so his ladder ended on **十三颗星璇** while the text ends on **十星的修罗王**. That specific bug was fixed by renaming the baseline to `sc_f42_chen_cai_star_13_baseline` so it sorts first (`normalize_backfill_ids.py`), and `TASK-SPEC.md` now requires same-chapter record IDs to be ordered by narrative sequence.

**Implemented** as three checks in `rollup_levels.py`, reported under `ladder_checks` and summarised in `summary`:

- `chain_breaks` — step *n*'s `before` ≠ step *n−1*'s `after` (both non-null). This is the check the skill had documented as missing.
- `cross_axis_labels` — a `before`/`after` label that is **exactly** a tier name belonging to a *different* axis.
- `action_value_conflicts` — `upgraded`/`gained` whose number fell, or `lost`/`decreased` whose number rose.

`--strict` exits non-zero on any hit, so a rebuild script can gate on it.

Two design notes, both learned from the data:

- The originally planned `terminal_mismatch` ("ladder terminal ≠ last step's `after`") is **vacuous** — the terminal is assigned from the last step, so it can never differ. The real cause was step *ordering*, which is why the check that matters is the chain, not the endpoint.
- Exact-match, not containment, for `cross_axis_labels`. 陈才's `after: {label: "修罗将军", value: 5}` is filed under 星级·修为, and 修罗将军 is a 修罗道阶位 rung (位次 4) whose own axis defines it as "大概有九颗星的实力". So the same word carries two numbers under two axes. A containment test would also fire on the legitimate `十星修罗王`, so only equality counts.

Hits on the real run — every one a genuine finding, none a false positive:

| check | hits | what it found |
|---|---|---|
| `chain_breaks` | 3 | 刘弈's 大耀日掌 ladder reads `1→2→3→4→8→5→7→8` because ch318's `before` restates 第四掌 when the running value was 第八掌 (ch317), and ch341 does it again; 晏秋红 ch291 `八星九星左右` → ch383 `before` 九星 |
| `cross_axis_labels` | 2 | 陈才 ch343, both sides of the 修罗将军 records filed under 星级·修为 |
| `action_value_conflicts` | 0 | — |

The 刘弈 case is a modelling gap, not a typo: the axis conflates "highest palm mastered" (monotone: 1,2,3,4,8) with "palm named in this chapter" (the author reveals 5 and 7 *after* 8). See D8.

### A3. Artifact staleness is undetectable — the machine cannot see a rule it only documents — **fixed**

`merge_graph.py` recorded `metadata.fragment_sources` as **paths only**, and `generated_at` was never compared to anything. So when `fragment-37` was edited after `graph.json` was written, `validation.json` still said `valid: true` with one record missing.

`SKILL.md` stated the procedure ("a fragment change means a full rebuild, not a re-validation") but nothing enforced it. **Now enforced:** `merge_graph.py` writes `metadata.input_fingerprint` (`{basename: sha256}` for every input fragment), and `validate_graph.py` recomputes it — a changed fragment is a `stale_inputs` **error**, a fragment that has gone missing is a `missing_inputs` **warning** (a moved run directory is not a defect in the graph), and a graph with no fingerprint at all gets an `input_fingerprint_missing` observation telling you to re-merge.

Verified both ways: the real run validates clean with 49 fragments fingerprinted; a copy with one byte appended to `fragment-49` fails with `stale_inputs` naming that fragment.

This is the general lesson: **a discipline the machine cannot check will be broken.** Whenever the fix for a gap is "remember to do X after Y", look for the artifact that proves X happened and compare it.

### A4. The level audit had no chapter-window bound, so its numbers were a property of the disk — **fixed**

`prepare_novel.py` splits the whole book (here **1,319** chapters). The graph covers **1—400**. `rollup_levels.py`'s audit walked *every prepared chapter it could find*, with no bound.

The consequence was invisible because it looked like a normal result: the delivered `level_rollup.json` reported **13** `candidate_gaps` at chapters `[134, 165, 190, 268, 325, 409, 455, 751, 995, 1238, 1270, 1271, 1285]`. Eight of the thirteen are chapters **this run never analyzed** — they could not be gaps in the graph, because nothing was ever extracted from them. `RESULTS.md` had already noticed the odd shape ("落在 1—300 章范围内的 5 条已逐条核对") without recognising the cause, and reported "13 candidates" as if it were a property of the graph.

Three things are wrong with that:

- The count is not reproducible. Re-preparing more chapters changes the audit without touching the graph, and nothing fingerprints the chapter set — `input_fingerprint` covers fragments only.
- It destroys the signal-to-noise ratio of the one actionable list in the level pass. 5 in-scope candidates is a triage task; 13 with 8 impossible ones teaches the reader to skim.
- A number derived from the environment leaked into a delivered document.

**Fixed:** the audit now defaults to `metadata.chapter_end`, with `--max-chapter` to override, and records what it did in `audit_window` (`chapters_on_disk`, `chapters_scanned`, `chapters_skipped_out_of_window`) plus a stderr note when it truncates. On the real run `candidate_gaps` drops **13 → 5** and `restatements` **17 → 13** — i.e. the four extra restatements were also out-of-window noise.

**General rule:** any script that reads a *directory* rather than the graph must bound itself by something the graph declares, and must report the bound. Otherwise its output silently depends on how much data happens to be sitting on disk.

### A5. The fragment gate was **stricter** than the pipeline contract — a post-merge invariant evaluated pre-merge — **fixed**

`rebuild.sh` step 0 runs `check_fragment.py --no-siblings` over every fragment **before** the merge. With `--no-siblings` the set of IDs "declared elsewhere" is built from `graph.json` alone — and at that moment `graph.json` still holds the *previous* round's merge, so anything this round introduces is invisible.

The sanctioned way to push a foreshadowing spine forward is a supplementary record carrying only `{id, progression:[...]}` (`analysis-protocol.md`): `label` / `planted_chapter` / `observation` / `interpretation` / `related_entity_ids` / `confidence` come from the fragment that originally declared the id. When the base declaration *and* the progression are both new in the same round, the gate cannot see the base declarer and emits ~40 `[ERROR] … 为必填（本片是唯一声明者）` lines naming the progression-only fragments (63 / 65 / 66) as sole declarer.

This is the mirror image of the 401—500 round's finding (`RESULTS.md` §十一 item 17, where the gate was too strict about `chapter_range` and `analyzed_chapters`). Both are the same shape: **a check that needs the merged graph was run before the merge.**

**Fixed** in `check_fragment.py`: a foreshadowing record that carries `progression` and lacks the base fields is a `warn`, not an `error`. The safety net is unchanged — after the merge `validate_graph.py` applies the same `required_fields` table, so an id whose base fields nobody declares is still an error, just at the stage that can see the whole graph.

General rule: **a check that needs the merged graph must not run before the merge.** Where it must run early (to fail fast), degrade the verdict to a warning and name the stage that will decide.

### A6. The fragment gate was **looser** than the contract — `review_issue.related_ids` — **fixed**

`validate_graph.py` has always required `review_issue.related_ids` to be an array ("empty is allowed for global issues"); `check_fragment.py` never looked at it. So all ten `ri_f66_*` records (and fragment-67's three) passed the fragment gate cleanly and blew up at the validator with nine `related_ids must be an array` errors — *after* the merge, on the third pipeline run of the round.

**Fixed** by adding `"review_issue": ("related_ids",)` to `required_fields.REQUIRED_KEYS` — the "key must exist, value may be null" table, which is exactly this shape (the key is mandatory, `[]` is legal).

General rule: **diff the two checkers, do not trust them.** Every field `validate_graph.py` validates must appear in `required_fields.py`, under `REQUIRED` (non-empty) or `REQUIRED_KEYS` (may be empty). This bug class has now cost a full pipeline run twice (the other instance is A5).

### A7. `resolve_evidence.py` silently skips already-located records — **open**

The script finds each quote in the chapter text and writes `source_line_start` / `source_line_end`. Records that **already carry** those two fields are skipped. So correcting a quote and re-running leaves the **old line number** behind: the record now points at a line that no longer contains its quote, and every downstream check still passes, because the fields are populated.

Four spliced quotes in `fragment-65` were repaired this way and each needed the two fields `pop`ped by hand first.

Fix: when a record already has both fields, re-locate anyway and *report* a moved line (`行号 812 → 815`), or add a `--relocate` flag. A silent no-op that looks like success is the worst of the three options.

### A8. Two as-of checks were green because their input table was empty — **fixed**

`SKILL.md` documents `annotate_alias_chapters.py` ("Run it after the merge and before the renderers; it is idempotent") and says both renderers need `metadata.alias_first_chapter`. The run's `rebuild.sh` **never called it**, so the key was absent from `metadata` entirely.

The consequence is not a crash, it is a **pair of false passes**:

- `build_dashboard.py`'s `aliasVisible()` reads `const c = m[a]; return !c || c <= chapter`. With `m` empty, `c` is `undefined`, `!c` is true, so **every alias is visible at every chapter**. `visibleNameList()` likewise pushes all aliases. An alias is a name, and a rename leaks a name into an earlier snapshot exactly as easily as a note leaks a chapter number — that is the whole reason the script exists.
- `verify_chapter_views.py` printed `未来别名 0 处`, and `audit_asof_prose.py` printed `（别名定年表 0 条）`. Both numbers were **structurally incapable of being non-zero**, and both look identical to a pass.

`export_ai_context.py` reads the same key, so the AI-facing artifact had the same hole.

**Fixed** by adding step `3b` to `rebuild.sh` (after the merge, before the renderers). On the real run it dates **721 aliases, 645 with an attested chapter, 76 left undated** — and undated aliases stay always-visible on purpose, because absence of an attestation is not evidence that a name is late.

Two general rules:

- **A check whose input is empty must say so.** `0 hits` and `0 because there was nothing to check` are different results and must not print the same string. Any report that reads a map/table should print the table's size next to the hit count — `audit_asof_prose.py` already did (`别名定年表 0 条`), and that parenthetical is what made this findable; `verify_chapter_views.py` did not, and hid it. **Fixed:** it now prints `别名定年表 N 条`, appends `⚠️ 表为空：别名核查正在空转，先跑 annotate_alias_chapters.py` when the map is empty, and reports how many alias-directed probes each snapshot used (8 default probes vs 18—20 once the map exists — that gap is the measure of how much was never looked at).
- **The documented step and the executed step are different artifacts.** A3 fixed this for fragments (fingerprints); this is the same failure one layer down, on a derived metadata field. When `SKILL.md` says "run X after Y", the proof that X ran is the artifact X writes — and here the artifact was missing while the pipeline reported success.

### A9. Fixing A8 grew the obligation list — and three of its rows were not wired — **fixed**

`audit_asof_prose.py` exists to enumerate **which fields carry the as-of obligation**, precisely so that adding a prose field cannot quietly escape the renderer's `asOf()`. With the alias map empty (A8) its name-based section reported `0 处 / 0 组合`. With the map populated it reports **62 hits across 10 field combos** — and three of the ten were not wired:

| combo | hits | was it wired? |
|---|---|---|
| `events.description` | 14 | yes |
| `review_issues.description` | 14 | yes |
| `state_changes.reason` | 9 | yes |
| **`events.title`** | 7 | **no** — `esc(e.title)` in `showEvent` and in the timeline feed |
| `foreshadowing.observation` | 6 | yes |
| `relations.description` | 4 | yes |
| `entities.summary` | 3 | yes (`summaryHtml`, a stronger whole-range rule) |
| `foreshadowing.interpretation` | 3 | yes |
| **`entities.description`** | 1 | **no** — not rendered by the dashboard at all (only `export_ai_context.py` emits it, and its `prose_fields` already lists `title`/`label`) |
| **`foreshadowing.label`** | 1 | **no** — `esc(f.label)` in `showForeshadow` and in the foreshadow feed |

A title is prose like any other: a ch148 clue titled 「林彤的师父」 names a form of address the text does not use until much later, and the title was printed verbatim in the ch1…ch147 snapshots.

**Fixed** by wrapping `e.title`, `f.label`, the timeline feed's `x.title`, the foreshadow feed's `f.label` and the cause-event title row in `asOf()`. The record-label resolver (`labelOfRecord`, which turns a `related_ids` token into readable text) needed a different treatment — its output goes inside a chip, where a paragraph-long "已隐去" block is wrong — so it falls back to `伏笔（名称尚未出现）` / `事件（名称尚未出现）` when the resolved label names a future name.

Why `verify_chapter_views.py` said PASS anyway: it probes 8 entities × 6 snapshots, and none of those panels is a leaking event or clue. That limitation is documented, and it is exactly why the obligation inventory must be complete: the snapshot check proves the panels it visits are clean, the inventory proves nothing was forgotten.

General rule: **an inventory is only as good as its wiring.** After fixing the input to a check, re-read its output — the count going from 0 to 62 is not a regression, it is the check starting to work, and the new rows are the ones to inspect.

### A10. A record-existence check is not a coverage check — **fixed**

`validate_graph.py` verified that every `intimate_acts` record had a legal shape, that its `evidence_ids` resolved, and that its `chapter` was inside the analysed range. It never compared the record **set** against the source. So a scene could be written up as a plain `intimate_contact` **event** and stay invisible forever.

The run held 15 `intimate_acts` records across 7 chapters while 62 `intimate_contact` events spanned 56 chapters. Among the 49 chapters with no record was **第334章** — the book's first sexual relationship (刘弈 × 西川洋子, in a KTV washroom) — recorded only as an event, with its partner having **no `romance_route` at all**. The reader found it; the pipeline could not.

Two things made it mechanically checkable after the fact, and both are generalisable:

- **The book's own retrospective lines.** 第381章 「尤其刘弈已经不是初哥了，品尝过一次双修运动之后」 and 第496章 「刘弈！你竟然已经破身了！」 re-state a first-time milestone. A "first" is almost always referred back to later; those lines are free cross-checks for a milestone the graph claims not to have.
- **The event set is the worklist, not a marker list.** The 62 `intimate_contact` events *are* the extractor's own reading of which chapters contain a scene. Comparing 62 events / 56 chapters against 7 chapters with records is a graph-internal arithmetic check. A text-marker scan (Tier A/B/C) is a weaker instrument: on this book it flagged 9 Tier-A chapters and a 239-chapter Tier-B list, and the true gap was better found from the graph.

**Fixed** by adding a coverage figure to `build_results_facts.py` (`intimacy_coverage`): every `intimate_contact` event must either have an `intimate_acts` record in its chapter, or be named in a `review_issue.related_ids` explaining why it is not one. `intimate_contact_events_unsilenced` must be 0 and now sits in the FACTS block. The backfill itself took 74 new records across 47 chapters, plus 7 romance routes (including 林彤, the female lead, who had none).

The text-marker auditor (`audit_intimacy_coverage.py`) stays as a **separate, complementary** check: it scans the *source* for signals; the FACTS figure compares *records*. Neither replaces the other, and the `RESULTS.md` command list says so.

General rule: **for any hand-filled array, ask what would notice if an entry were missing.** "Is each record legal?" and "is every scene recorded?" are different questions, and only the second catches an omission. The tell is an array whose size is never compared against anything else in the graph — 15 records is a fine number in isolation; 15 against 62 events is a defect.

### A11. The pipeline fingerprints its inputs but not its code — **fixed**

`metadata.input_fingerprint` covers the 69 fragment files. Nothing covered the scripts that transform them. So the same command over the same fragments could produce a different graph with no warning at all.

Observed on 2026-09-14: `annotate_alias_chapters.py` was edited between two `rebuild.sh` runs (gaining the `PROPER_NOUN_TYPES` filter). The alias table went **1454 names / 1317 dated → 1105 / 1014**, and both runs reported green. There is no VCS in this workspace, so the only evidence of the ordering is file mtimes against the run windows — which is exactly the point: a change to the toolchain left no trace in the artifact.

The consequence is not cosmetic. The alias table is what gates future names in the as-of views (A8). A change to its scope silently changes how much of the graph the reader can see at each chapter, and `RESULTS.md`'s numbers move with it.

Detection is not enough, because the worse failure is a **torn build**. `rebuild.sh` runs ~15 scripts in sequence; if `build_dashboard.py` is saved between step 9 and step 10, the run renders with the old renderer and exports with the new one. Every stage exits 0, the run reports green, and the artifact is a mixture of two code versions that nobody can reproduce. The same run printed 「别名定年表 **0** 条」 at step 8 and 「别名定年表 **1014** 条」 at step 12 — two checks disagreeing about the same table inside one build, both looking exactly like a pass, because the shared script had been swapped mid-run. A hash comparison cannot catch this: by the time you can compare hashes the torn artifact is already written and looks fine.

**Fixed** in three layers, deliberately ordered by how much they can be trusted:

1. **Prevention — `scripts/freeze_toolchain.py`.** `rebuild.sh` copies the whole `scripts/` (and `assets/`) into `<run>/_toolchain/` at step 0a and runs **that** copy for the entire build, so a concurrent save cannot reach a running pipeline; step 13b runs `--verify` to prove the frozen copy did not change. The copy **mirrors the skill's layout** (`_toolchain/scripts` + `_toolchain/assets`) and that is not cosmetic: `build_dashboard.py` locates its vendored library as `Path(__file__).resolve().parent.parent / "assets" / "cytoscape-3.34.3.min.js"`, so a flat copy renders the dashboard **without the graph library** — a silent content failure of exactly the kind this script exists to prevent. `assets/` is copied but not hashed (third-party artifact).
2. **Coverage of un-frozen runs — `merge_graph.py` records `metadata.toolchain_fingerprint`** at merge time, and `build_results_facts.py` compares it with the present value and warns loudly that the build was torn. This needs no edit to any run's `rebuild.sh`, so the four runs that have not adopted the freeze still get detection.
3. **Visibility of later drift — the FACTS block carries three hashes**: `pipeline_scripts_sha256` (code that built this), `pipeline_scripts_live_sha256` (shared dir now), `pipeline_scripts_at_merge_sha256` (recorded in `graph.json`). A stale artifact is flagged from either direction, and all three agreeing is the evidence that a build was internally consistent.

Two landmines found by actually running the fix, both worth remembering:

* **The freeze must not `rmtree` its destination.** This workspace's delete guard counts files removed per turn and refuses more than 50 (`[safe-delete][SAFE_DELETE_BULK_CONFIRM_REQUIRED]`); rebuilding the tree means deleting ~80 files at once, so step 0a died with exit 1 before the pipeline had done anything — and an interrupted `rmtree` leaves a half-copy behind. `sync_files()` overwrites same-named files and deletes only what has disappeared from the source, so the steady-state delete count is **0** and stale files still get cleaned. Two other runs hit the same wall independently (their `_rebuild_*.log` carry the same message) and worked around it by pre-deleting with an external `rm -rf`; the sync removes the need for that.
* **`__pycache__` counts.** Bytecode is not in the fingerprint's file list (`.py`/`.js` only) and `--verify` hashes only those, so a `.pyc` growing inside the frozen copy is a real change to the frozen directory that the check cannot see — a check that claims "nothing in the frozen copy changed" must not be blind to it. `PYTHONDONTWRITEBYTECODE=1` is set explicitly by `rebuild.sh` rather than relied on from the ambient environment, and `sync_files()` prunes `__pycache__` file by file. A sibling run measured the frozen directory at 96 files once bytecode was included, against 38 without.

Verified on the 我的狐仙老婆-full run: all 15 steps green, step 8 and step 12 both reporting the alias table at 1014, and the three fingerprints identical at `4b0ab224de7c` (built = live = at-merge).

### A12. A generated spec's template is the gate — **fixed**

`TASK-SPEC.md`'s fragment template listed `events` / `relations` / `state_changes` / `romance_routes` / `foreshadowing` / `evidence` / `review_issues` — and **no `intimate_acts` key at all**. Every parallel worker was handed a schema with no slot for an intimate act, so the omission was structural, not careless. The enum section likewise had no `act_type` / `consent` table.

This is A1's pattern one level down: not "a list that is not generated", but "a template that is not checked against the validator's own required-fields table". `scripts/required_fields.py` is the single authority for field names; the spec is prose that nothing compares it to.

**Fixed** by adding the key to the template, the 24 `act_type` values and 8 `consent` values to the enum section, and two hard rules: every `intimate_contact` event needs a record or a naming `review_issue`, and `intimate_acts` records only what the text states (no skipping a scene for being explicit or coercive — the book is a published, already-cleared title and the run's rule is to record faithfully).

General rule: **when a field is missing from the template, look for what else is missing from it.** The same edit that added `intimate_acts` also added `coverage_gap` / `event_typing` / `text_ambiguity` / `consent_ambiguity` / `evidence_fit` to the `review_issues[].category` list and noted that `chapter` is required — three categories the graph had been using for rounds while the spec told workers only five existed.

**Second instance, found 2026-09-14 and still open: `character_traits`.** The template has no slot for it either, so the 我的狐仙老婆-full run shipped **0 traits across 734 entities** — and 0 is indistinguishable from "this book describes nobody's appearance", which is why it survived 550 chapters and six rounds. Everything else was already in place: `character_traits.py` defines the four facets (`appearance` / `personality` / `speech` / `habit`) with aliases and labels, `required_fields.py` gives the record shape, `validate_graph.py` checks it, `build_dashboard.py:777` renders a per-facet panel filtered by `chapter <= N`, and `export_ai_context.py` writes a 「人物特征」 section with the change history. The slot in the *spec* was the only missing piece.

The consequence is that the graph has almost no description of anyone: only **9 of 734** entities carry a `summary` at all, and the only 10 with `attributes` are level axes (keys: 单位 / 越高越强 / 分级依据 / 下限 / 上限 / 档位). So appearance and personality are not "stored somewhere else" — they were never extracted.

Two lessons. (1) The general rule above needs to be applied as a *diff*, not as a mood: `required_fields.ARRAY_KINDS` lists **12** arrays and the TASK-SPEC template has **10** — the three missing ones are exactly `character_traits`, `chapter_summaries`, `level_conversions`. Reading the spec and "seeing what's missing" missed this for six rounds; the check has to be mechanical. (2) **An empty array that renders nothing is invisible, and a count in a summary table is not a gate.** `traitPanel()` returns `''` when there are no records, so the character panel shows no empty section and no warning — but the number *was* on screen the whole time: `AI_CONTEXT.md`'s 数据概况 has said 「人物特征：0」 in every delivered build. It survived six rounds because nothing compares a count against anything. That is the same distinction as `intimate_contact_events_unsilenced`: one is a **display**, the other is a **gate**. So the fix has two halves — make every `ARRAY_KINDS` entry appear in the FACTS table (add the three missing ones to `build_results_facts.ARRAYS`), and make an empty expected-non-empty kind **fail** rather than merely print 0.

---

## B. Gaps that produce false signals

### B1. `candidate_gaps` has a precision of zero — **partly addressed**

13 candidates; the 5 inside the 1—300 range were each read back against the source and **all five were scanner errors** — the heuristic takes "a line contains the character's name and a level number" as that character's level, so a level mentioned *about* someone else, or in dialogue, becomes a candidate.

Two separate problems were tangled here. The window bound (A4) removed 8 of the 13 as out-of-scope, so the actionable list is now the honest 5 — but those 5 are still all false, so the heuristic itself is still zero-precision. Fix: require the level word to be **predicated on** the character (the name adjacent to the number with no intervening subject change), or move it behind a `--deep` flag. **Open.**

### B2. A legitimately non-monotonic ladder reads as a defect

大耀日掌's palm count is learned out of order (ch317 第八掌 → ch318 第五掌 → ch319 第七掌). The tool marks `monotonic_nondecreasing: false`, and `SKILL.md` instructs the reader to confirm every ladder is monotonic before treating it as evidence — so a **correctly recorded** fact looks like a data error.

Fix: let an axis declare `ordered: false` (or give each change a `chain_anchor`), so a non-total order is an expressed intent rather than a red flag.

### B3. `alias_collision` enforces a display constraint as a data constraint

`validate_graph.py` requires name + aliases to be unique across the whole graph. But the source genuinely gives one noun two referents: 修罗 is both a rung of 修罗道阶位 and a `creature` entity, and so are 修罗将军 and 修罗王. The rule is about **what the reader sees**, not about what exists.

Fix: name the resolution in the warning (`creature_xiuluo` for the individual; the rung name lives only in `axis_*.attributes.档位[].名称`) instead of leaving the author to invent a workaround, and consider a scoped `disambiguator` so an invented name is not the only option.

### B4. A relation status the vocabulary did not know rendered as a raw English key — **fixed**

`relation.status` has three values in use (`active` 381, `ended` 45, `ambiguous` 4), and `ambiguous` was in **neither** the run's `display-vocabulary.json` nor `build_dashboard.DEFAULT_VOCABULARY`. `term()` falls back to the raw key, so four relations — 刘弈↔西川洋子, 冥羽雪芬→刘弈, 陈才→蛇女, 犬女小芬→刘弈 — printed the English word `ambiguous` in the relation header. That is precisely what `SKILL.md` forbids ("never expose untranslated ontology keys in the reader-facing interface"), and it survived because the values are rare.

Found by enumerating every value the graph actually uses and diffing against **`merge_vocabulary(DEFAULT_VOCABULARY, run_vocabulary)`** — the merged table, not either half. The previous round's check covered 14 groups; this pass widened it to 16 by adding `level_conversion_relations` and `intimacy_act_types` (the latter is filled from `intimacy_types.py` at import time and is legitimately empty in the run file, which is why checking the run file alone misreports it as a gap).

**Fixed** in both places: the run vocabulary gained `"ambiguous": "关系未定"`, and the renderer default gained the same key so future runs are covered. Result: 16 groups, 0 gaps, 0 non-string leaves.

Note that `export_ai_context.py` imports `DEFAULT_VOCABULARY` from `build_dashboard`, so a default fix reaches both renderers at once — prefer the default for any value that is not book-specific.

### B5. A vocabulary label is not narrative content — **fixed**

With the alias table populated (A8), `verify_chapter_views.py` began reporting:

```
FAIL
  - N=1: concept_honglingxia 面板出现未来别名「修仙」
```

The panel contained no such name. The hit came from panel chrome:

```html
<div class="eyebrow">修仙设定 · 第 1 章状态</div>
```

`concept`'s display label is 「修仙设定」, and the book has an entity whose formal name is 「修仙」 (first chapter 4). At N=1 「修仙」 is a late name, so the substring test matched *inside the label*. The same holds for `relation_types` / `facets` / `actions` / `issue_categories` labels: in this run exactly 3 late names are proper substrings of a label — 「修仙」⊂「修仙设定」, 「影」⊂「受能力影响」, 「第二人格」⊂「同一人的第二人格」.

**Fixed** by treating the renderer's whole label set as always-visible names. `asof_names.label_strings()` walks the merged vocabulary (`build_dashboard.merge_vocabulary(DEFAULT_VOCABULARY, <book vocabulary>)` — the same merge the renderer uses, since `graph.metadata.display_vocabulary` is empty here and the vocabulary arrives via `--vocabulary`), and `LateNameIndex` takes it as `extra_visible`. The container test only ever suppresses a match that sits *inside a longer* name, so a label can mask a late name only when that name is its proper substring — the three above, all correctly. `verify_chapter_views.py` gained `--vocabulary` and prints the label count, because an empty label set would put the false positives straight back.

Measured before shipping, so the exclusion could not hide a real leak: **0 prose fields change verdict** (190 → 190 name-side hits across all records). The exclusion therefore touches panel chrome only — which is why the renderer's JS side needs no matching change today. It is a latent divergence: the Python judgement now sees a larger visible-name set than the JS one, and if a future field ever renders *prose* through a label, the two would disagree. `audit_asof_prose.py`'s name-side count is where that would show up.

And a lesson about the check itself: this FAIL appeared only once the alias table grew. A check that has never had enough input to fail has not been tested — the same shape as A8, one round later.

### B6. A substring check on a runtime-rendered artifact reports the data and the checker's own source — **fixed**

A final-verification script asserted `"fragment-" not in dashboard.html`, meaning to prove that no internal fragment numbering reached the reader. It failed, and the failure was **entirely spurious**.

`dashboard.html` is a single-page app: the reader-visible text is produced by JS **at runtime**, so the static file contains no prose at all. `fragment-N` appeared in exactly two non-rendered places:

1. `build_dashboard.py` inlines the whole graph as `const graph=<payload>;`. `metadata.fragment_sources` holds absolute local paths, and `metadata.notes` accumulates each fragment's own note (`merge_graph.py` extends it from every input's `metadata.notes`).
2. `reader_prose_js()` inlines the cleaner's rule array `RP_NEUTRALISE` — which **itself contains `/fragment-\d+/g`**.

53 hits in the file, **0 in the rendered region**. It took two rewrites of the check to see that: the first excluded the data payload, and only then did the cleaner's own source show up.

Note the contrast with `source_line_start`, where a whole-file check happens to be correct: there the renderer deletes the key outright (`reader_safe_data()` drops `source_line_start` / `source_line_end`), so the string cannot survive anywhere. Which of the two you are looking at is a property of the **renderer**, not of the string.

**Rule: a static substring check is only valid for an artifact that *is* its own final text (`AI_CONTEXT.md`, `RESULTS.md`). For an artifact whose text is generated at runtime, check the generated text — `verify_chapter_views.py` drives the real page and reads the real panels — or assert on the authoritative report (`audit_reader_prose.py`'s story-side count).** The replacement check asserts structure (the cleaner is inlined, so `asOf()` really runs it) and parses the audit's number; it cannot pass by scanning a region that was never going to contain the string.

Also worth keeping: this whole detour was triggered by a **newly added** check, and the correct first question was not "how do I make it green" but "does this check measure the thing I think it measures". Rewriting the check to be *precise* (scope it to the rendered region) is legitimate; rewriting it to be *loose* (delete the assertion) would have hidden the very class it was added for.

### B7. The prose cleaner removes only *unresolvable* IDs, and the audit exempts a whole array — so resolvable IDs reach the reader with a green gate — **open in delivered range**

Two independent scoping choices compose into a blind spot.

`reader_prose.py`'s `FRAGMENT_LOCAL_ID` matches only IDs that exist **inside one fragment and nowhere else** — `前缀_` followed by a two-digit local suffix (`sc_f48_xxx`, `char_B01`). Those are artifacts of the authoring pass and are deleted. A **resolvable** record ID (`char_shi_xing`, `item_jinse_paoguan`, `fs_*`) is *deliberately left intact*: the cleaner is not a name resolver, and stripping it would delete a legitimate cross-reference. But in prose, an ID is never legitimate — it is an internal key in a field the reader reads.

`audit_reader_prose.py` then exempts the entire `review_issues` array via `ANALYST_ARRAYS = {"review_issues"}`, on the sound reasoning that this text *is* addressed to an analyst and may name things the reader never sees. The exemption is defensible for the *reasoning*, but it also exempts the field most likely to contain internal keys, because issue descriptions are written by whoever noticed the problem and routinely cite the records involved.

Result: the gate is green and internal keys are present. Full scan of the delivered 1—500 run found **93 review_issue records** carrying at least one resolvable ID — all in `fragment-01`…`fragment-48`.

But then reading all 93 changes the verdict, and this is the part worth recording. They are **not** leaked narrative prose. Nearly every one is a *naming or coverage note whose subject is the identifier itself*:

- `只能用描述性命名的实体 ID（char_huo_muqin / char_gongjue / char_gongjue_furen）`
- `本文件按规范统一使用固定 ID concept_haodong_zhili（浩冬之力）`
- `合并时已统一为 char_yan_shaozhe`
- `记录了 sc_ch036_shilaike_kongming_lost 与 …_gain 两条对应变化`

Substituting the display name for the ID in these sentences **destroys the information being reported** — the note exists precisely to say *which record* was used or unified. The exemption is therefore correct by design, and the six records rewritten in the 451—500 round (where the ID sat inside an otherwise narrative sentence about a person's attributes) were the exception, not the rule.

Revised rule, replacing the too-strong version this entry started with:

- **An exemption must be paired with a compensating scan** — but the scan's output is a *classification*, not a defect list. Measure first, then decide: 93 raw hits, 0 narrative leaks. Without the scan you cannot tell "analyst note" from "leaked key", and both directions are wrong (mass substitution loses facts; doing nothing leaves real leaks). Same shape as C2: a filtered check must print what it filtered.
- **Fix a real leak where it is cheapest.** If an ID ever does reach a reader in narrative prose, the repair is renderer-side (resolve through the entity index, exactly as `build_dashboard.py` already does for `review_issue.related_ids` via `nameOf()`), not 100+ hand-edited descriptions. Content edits are for content errors.

---

## C. Gaps that let documents drift

### C1. Nothing checks the numbers in `RESULTS.md` — **fixed**

Numbers are hand-typed prose. Two rounds in a row got them wrong: per-axis change counts written as 55/2/12/13 against a real 72/1/8/6/2, and eight more figures in the 301—400 and backfill sections (entity/state-change/evidence/review totals that predated a late fragment, `RENAMES` count, reference-rewrite count, bare-ID counts). Every one was only caught by re-deriving it from the fragments and the graph.

**Implemented** as `build_results_facts.py`:

```
python scripts/build_results_facts.py --run-dir runs/<book-range>          # print facts as JSON
python scripts/build_results_facts.py --run-dir runs/<book-range> --write  # (re)generate the block
python scripts/build_results_facts.py --run-dir runs/<book-range> --check  # exit 1 on drift
```

It recomputes 33 figures (37 after the 501—550 round added the as-of name rows and the alias-map size) from `graph.json`, `validation.json`, the fragment files, and by *invoking* `rollup_levels.py` and `audit_asof_prose.py` (so each number has exactly one definition), then writes them into `RESULTS.md` between `<!-- FACTS:BEGIN -->` and `<!-- FACTS:END -->`. `--check` re-derives and compares, exiting non-zero on any mismatch, missing row, or stale row.

Verified both directions on the real run: `--check` passes at 33/33, and changing the embedded entity count from 484 to 211 fails with `不一致 entities_total：文档 211 ≠ 产物 484`.

Two limits worth stating plainly, because the block is a spine and not a proof:

- Numbers **outside** the block are still hand-written. The block cannot catch a wrong figure in a prose sentence; only the finalization rule can.
- The block covers **graph totals**. `RESULTS.md` also quotes per-round *deltas* (§五's "实体 211／证据 1058" is the raw output of `fragment-38`～`fragment-47` before normalization, a different and legitimate scope). Two scopes in one document is itself a hazard: label every table with its scope.

The finalization checklist must say plainly: **every number in `RESULTS.md` must be produced by a script, never typed.**

### C2. Checks default to silence

Two independent instances, both repaired: `agent_detection.NON_AGENT_TYPES` did `continue` before scoring, so a type-excluded entity appeared in **no** report (this is how a second personality stayed invisible for several rounds); and `nameOf` fell through to the raw ID, so an unresolved reference printed an internal key rather than announcing itself.

Same shape twice, so make it an invariant: **a check that filters must print what it filtered.** Grep the scripts for `continue` and fall-through returns without an accompanying report line.

---

## D. Domain modelling the protocol does not cover

### D1. One noun, two referents: a ladder rung and an individual of that rung

Covered above (B3) as a validator issue, but the extraction pass needs the rule too: the `Level pass` in `analysis-protocol.md` says nothing about a tier name that is also a creature. It is a common pattern in this genre and it recurs (`修罗` 841 uses as rung *and* monster).

### D2. An honorific that looks like a higher tier, in a text that contradicts itself

ch309 states the axis is 「分为五个级别的生物」, highest 修罗王. ch312 introduces 修罗神 (69 uses), described as a shared honorific for a few of the strongest. The graph records five tiers and files the contradiction as a review issue — but nothing in the protocol says that is the right move.

A reusable technique that settled it: **count the term before deciding it is a tier.** 修罗 841 / 修罗道 173 / 修罗神 69 / 修罗王 65 / 修罗将军 14 / 修罗魔 3 / 修罗鬼 1 / 修罗五阶 0. An honorific with 69 uses is not a rung with 1 use; the enumeration in the text is the axis, and the extra name is a `title`/`concept` plus a review issue citing both passages.

### D3. `before: null` baselines are an ordering trap the protocol actively recommends

`analysis-protocol.md` Level pass step 3: "Record the level the character starts from as `before: null` when the range contains no earlier baseline." Combined with same-chapter steps ordered by ID, this is exactly how 陈才's baseline ended up last. The protocol creates the bug that A2 describes.

Fix: amend step 3 to require a sortable suffix (`_baseline`, `_step1`, …) whenever one chapter carries more than one change for the same entity + axis, and put the ordering rule in the **Level pass**, where the worker reads it, not only in `SKILL.md`.

### D4. "Trained in a system, but the text never gives a rank"

刘弈 and 陈才 spend 500 years in 修罗道 together; the text gives a rank ladder for 陈才 only. The graph declines to invent one and files a review issue. The protocol covers "a plan or an estimate is not a change" but not "participated in a system without a stated rank".

### D5. A clue that never resolves cannot say *why*

284 of 290 foreshadowings are `open`/`suspected` in a 1—400 slice of a 1,319-chapter book. The status vocabulary cannot distinguish "open because the analyzed range ended" from "open because the author dropped it", so a downstream reader cannot tell whether a payoff exists later.

Fix: a **derived** export field, `open_at_range_end`, stating that the clue was still open when the range ended and that the book continues. Derived, so no fragment changes and no false claim about the full text.

### D6. Coverage figures with no closure path get re-litigated every round

157 non-character entities are referenced by no record. The skill correctly calls this a coverage observation rather than a defect — but there is no way to *reduce* it, so each round re-argues the same list. Fix: a one-time triage — entities appearing in ≥2 chapters or referenced by a clue/relation are defects; one-off background nouns get `standalone: true` and stop being counted.

### D7. A rule the workflow cannot enforce retroactively

"Never rewrite finished fragments" means the level-in-`attribute` overlap in fragments 01—16 is permanent, even though the protocol forbids it. Either grant an explicit, scoped exception for a normalizing pass, or state that such records stay as known debt. Leaving it unstated means it is rediscovered as a surprise every round.

### D8. Out-of-order tier revelation has no representation — the new `chain_breaks` hit

The `chain_breaks` check (A2) fires 3 times on the real run, and the 刘弈 case is not a typo:

- ch317 「大耀日掌的第八掌！」 → ladder records 第四掌 → **第八掌**
- ch318 「大耀日掌第五掌，防守如风」 → `before` restated as **第四掌**, but the running value was 第八掌
- ch319 「大耀日掌第七掌！」 → `before` 第五掌, `after` 第七掌

The author reveals palms **5 and 7 after 8**. The axis conflates two different facts:

1. *highest palm mastered* — genuinely monotone (1, 2, 3, 4, 8);
2. *palm named in this chapter* — not monotone at all, because the narrator fills in names out of order.

Recorded as one ladder, the reader sees the palm count go **backwards twice** (8 → 5, 7 → 4). Each per-chapter fragment was locally correct; only the assembled ladder is wrong, which is exactly why no fragment-level check could see it.

Fix options, none yet chosen:

- give the axis a `highest_known` semantic and record out-of-order revelations as evidence on the existing step rather than as a new step;
- or let the axis declare `ordered: false` (see B2) and make the chain check report an *observation* for that axis instead of a warning;
- or allow a change to carry `chain_anchor` naming the step it actually continues from, so a non-sequential reveal is expressed rather than inferred.

Until one is chosen, the honest state is: the ladder is faithful to the text, and the check flags it for a human to explain. `ri_f49_dayaori_zhang_out_of_order` carries the current explanation.

### D9. A romance route whose partner is not a `character` had no representation — **fixed**

The backfill fragment for 401—530 recovered three routes the 401—500 round had dropped, one of which is 小米: the 犬女 the source gives a name, speech, a habit of calling the protagonist 「主人」, and a kiss on the cheek (ch356). The graph types her `creature` (`creature_xiaomi`, aliases 犬女 / 犬女小米 / 小白狗 / 阿拉斯加犬), and `validate_graph.py` required both `protagonist_id` and `character_id` to reference `type == "character"` — so the route could not exist at all. The run failed at the validator with one `bad_character_ref`, *after* the merge.

Two ways to read it, and they conflict:

- the field is named `character_id`, so a non-character is a data error;
- but the harem panel is a *reader-facing* view of who the protagonist is involved with, and the source puts 小米 in it. This is the same shape as B3 (`alias_collision` enforcing a display constraint as a data constraint) — a constraint about what the panel shows, expressed as a constraint on what may exist.

The run's standing rule is 「感情线一律保留，不做删除式清洗」, so dropping the route was not available. **Fixed** by allowing it, but only by explicit declaration: a route may carry `character_type` naming the partner's actual type, and `validate_graph.py` then emits a `non_character_romance_partner` **observation** instead of an error. Without the declaration the error stands, so the allowance cannot swallow a typo. `protagonist_id` stays character-only.

The verdict is an observation and not a warning on purpose: the completion gate is 0 errors / 0 warnings, and this is a *declared* modelling choice rather than something to go and look at — the same category as the standing `event_type_outside_recommended_set`. A warning here would have forced every future round to carry a permanent non-zero warning count, which is how a gate stops meaning anything.

Documented in `schema.md` (Romance routes) so the next round knows the escape hatch exists rather than rediscovering the error. `ri_f67_xiaomi_creature_route` keeps the extraction-side note, and `rel_f43_xiaomi_liu_ambiguity` (romantic_ambiguity, from ch356) had already recorded the same fact as a relation — which is why the information was never actually at risk, only its structured form.

---

## E. Workflow protocol gaps

### E1. Supplementary fragments cannot express three classes of correction — and the in-place protocol is undefined

`SKILL.md` now lists the limits (`STRICT_KINDS` byte-equality, list union, entity rename), but not the **safety protocol for the in-place edit** they force. Three lessons cost real time this round:

1. The clash guard must compare against **other fragments only**. Comparing against `graph.json` fails on the second run, because the graph already contains the script's own previous output.
2. A guard on `related_ids` must validate against **all record IDs**, not just entities — mirroring `validate_graph.py`'s `known_ids`, which spans every array.
3. The patch must be **idempotent** (early-return guard on the already-applied state), or re-running the pipeline rewrites the file and breaks byte-comparison downstream.

Write these as a protocol, and require a backup of the fragment plus a note in the supplementary fragment's `notes`.

### E2. Normalization effort is unpredictable

This run needed 3 normalize scripts, 4 fragment-builders, and 2 in-place patch scripts on top of 48 worker fragments. The observed rate is useful: **188 → 152 entity IDs per 100 chapters, i.e. ~36 collisions**, plus 96 marker-bearing entity IDs to strip. `parallel-extraction.md` covers partitioning but never says to budget a normalization pass of this size.

### E3. Level-axis discovery is an afterthought

The Level pass says to create each axis "once, before recording changes" — but in practice a worker discovers a new system mid-chapter, after extraction has started. Handing the spec a list of existing axes is not enough; the spec must also ask each pass to **report** any ranked system it meets that is not on the list. This round's escape hatch (A1) covers "met a new system"; it does not yet ask the pass to go looking.

### E4. Audit hits are acknowledged in a hand-maintained list nothing validates — **open**

`rollup_levels.py`'s three self-checks and `audit_entity_links.py` both produce hits that are, in the skill's own words, "not errors — read them once". The mechanism for recording that a human read them is `_context/acknowledged.json`: `level_ladder_checks.{chain_breaks,cross_axis_labels,action_value_conflicts}` and `link_audit.items[{key, reason, review_issue}]`. Passed with `--acknowledged`, `--strict` then gates only on **new** hits, and both scripts fingerprint the list (`acknowledged_sha256`) so an edited list is visible.

That is the right shape, and this round it did its job: `unacknowledged_hits: 0` with 3 `chain_breaks` + 2 `cross_axis_labels` carried over, and one new `link_audit` item added (`identity_clue:concept_wuling_dahui` — 五灵大会 is a contest, not a character's possession; same class as the already-acknowledged 天榜).

Two holes, both cheap to close:

- The `review_issue` named in an item is **only echoed to stdout** — neither script checks that the id exists in the graph. A typo, or an issue later removed, silently degrades the acknowledgement to an unexplained string.
- Nothing expires an acknowledgement when the underlying record changes. A `chain_break` acknowledged as "the author reveals palms out of order" stays acknowledged even if the ladder is later edited for a different reason.

### E5. A loop that deletes one file per iteration kills the build at the 50th deletion — and the failure reads as a content failure

The AI-text snapshot check ends each iteration with `rm -f "_asof_$N.md"`. Thirteen iterations, thirteen deletions. On the seventh (`N=290`) the sandbox refused:

```
[safe-delete][SAFE_DELETE_BULK_CONFIRM_REQUIRED] {"count":50,"threshold":50,"scope":"turn","targets":[".../_asof_290.md"],"targetCount":1}
EXIT=1
```

Under `set -euo pipefail` that non-zero exit **terminates the whole build**, and the log's last successful line is 「第 250 章快照：未来章号 0 处」. Every reading of that is wrong: it looks like chapter 290 leaks a future chapter number, which is the most serious defect the pipeline can report. Running the same snapshot by hand gives 未来章号 0 处 — there was never a leak. The same guard is what left `_toolchain-aborted-20260914T1200/` half-deleted in an earlier round (`rmtree` of 59 files).

Two rules:

- **Never delete inside a loop.** Write to one fixed path and overwrite it — overwriting is not a deletion. A scratch file that persists under a working directory (`_context/`) is cheaper than a build that dies for a reason the log misattributes.
- **A failure whose message is a harness message is not a data verdict.** `[safe-delete]`, `[SAFE_DELETE_*]`, `returncode=3221225794` and similar belong to the runner. Read the failing *step*, reproduce its check by hand, and only then believe a content diagnosis. This round would have "fixed" a leak that did not exist.

Worth stating for the pipeline's own sake: the check that failed was correct and valuable — the bug was in how the harness around it cleaned up.

### E5. Extending the analysed range re-runs a **delete** command — `prepare_novel.py --force` drops every chapter outside `--start..--end` — **open (documented, not guarded)**

Continuation rounds add chapters at the *end* of the range, so the natural command is "prepare 201—300". That command **deletes chapters 1—200**:

```python
if args.force:
    written = {chapters_dir / f"{chapter_no:03d}.txt" for chapter_no in records}
    for stale in sorted(chapters_dir.glob("*.txt")):
        if stale not in written and stale.stem.isdigit():
            stale.unlink()
```

The intent is sound (a leftover `000.txt` with no `chapters.jsonl` record is invisible to validation but visible to an extraction glob). The hazard is the *direction of the range*: `--force` means "this range is the whole book", so the only safe continuation is `--start 1 --end <new end>`. It does print `NOTE: --force 清理过期章节文件 …` to stderr, but the standard invocation redirects the whole build to a log, where the line sits between hundreds of others.

What the re-prepare costs even when the range is right: the newer packager trims whitespace-only lines, so **every earlier chapter's `char_count` and `sha256` change** while its `source_line_start` / `source_line_end` stay byte-identical. Verified on the 1—300 round: joint `sha256` `a64647a9e9e06ecf` → `0bc87fae226e9827`, **0** chapters with a changed line span, **1713 / 1713** existing quotes still verbatim substrings.

Rules:

- **Continuation always re-prepares `--start 1`.** A range that starts above 1 is a delete of everything below it.
- **To check "did the earlier chapters change?", compare `source_line_start` / `source_line_end`, not file hashes.** The hash moves for a cosmetic reason; the line span is what every quote depends on.
- Back up `chapters/` + `chapters.jsonl` + `source_manifest.json` before the first re-prepare of a continuation round.

### E6. `check_fragment.py` does not exempt `metadata.supplementary` from the coverage check — 1 phantom error per supplementary fragment

The gate compares `analyzed_chapters` against `[chapter_start..chapter_end]`. A supplementary fragment (A5 / E1) legitimately declares only the chapters it actually writes evidence for, so `fragment-P.json` / `fragment-P2.json` / `fragment-SUPP.json` each report one error — `analyzed_chapters 不等于范围 […]` — in every round, on every run, forever. `plan_reconciliation.py` already reads `metadata.supplementary: true` and classifies them correctly; the fragment gate does not read it at all.

Same family as A5/A6: **two checkers that disagree about the same file.** The fix is a one-line exemption in `check_fragment.py` (`if metadata.get("supplementary"): skip the coverage comparison`), not a data edit — writing the missing chapters into `analyzed_chapters` would falsify the coverage declaration.

---

## F. Authoring hazards (the fragment itself)
### F1. Hand-written JSON for a 100+-field document is a defect source — **fixed by process**

Three separate parse failures in one round, all in `fragment-65`, all from writing JSON by hand: a bare `"` after a numeric field (`"chapter": 538"`, twice) and one extra `}` closing each of the three `romance_routes`' `notes` strings. Each took a parse-error bisect to find, in a 2,000-line file.

The durable fix is to **stop writing JSON by hand**. Build the fragment from a Python script (`_tmp_gen_f66.py` / `_tmp_gen_f67.py`) and `json.dump` it. Every quote is produced by an anchor helper:

```python
def q(eid, ch, anchor, pre=0, post=0):
    t = ctext(ch); idx = t.find(anchor)
    if idx < 0: FAIL.append((eid, ch, 'anchor', anchor)); return eid
    seg = t[idx - pre: idx + len(anchor) + post]
    if '\n' in seg or len(seg) < 4: FAIL.append((eid, ch, 'bad', seg)); return eid
    EV.append({'id': eid, 'chapter': ch, 'quote': seg}); return eid
```

The script aborts before writing if any anchor failed. Result: `fragment-66` (195 evidence) and `fragment-67` (24) went in with **zero** quote errors and **zero** JSON errors, against four quote errors and three parse failures in the hand-written `fragment-65`.

The helper also enforces two constraints the spec states but nothing checked: the quote must be a **contiguous verbatim substring** (§〇 forbids splicing two sentences into one — that is exactly what produced all four of `fragment-65`'s bad quotes) and it must be **single-line** (a multi-line quote breaks line-number resolution). Making the constraint a function that can fail is what turned a recurring manual review into a machine check.

### F2. Two parallel edits to one file silently drop one — **open**

Two `Edit` calls issued in the same message against the same file are applied without mutual exclusion; one is lost and nothing reports it. This round it cost a `rollup_levels.py` change: the `summary` counters landed, the `ladder_checks` key did not, and the only symptom was a missing key in the output — found by reading the product, not the diff.

Rule: **serialise edits to a single file.** Parallel tool calls are for different files.

---

## G. Gaps found while continuing 谁让他修仙的 to 1–400 (2026-09-15)

Four new ones, all found by running the gates rather than by reading them.

### G1. `plan_reconciliation.py` has no "one name, two IDs" check — **open**

Its check 1 is `duplicate_entity_ids`: *one ID declared twice with a different name or
type*. The mirror-image defect — **one entity minted under two different IDs** — is
invisible to it. Ten parallel 10-chapter passes produced four of them: 石化骨
(`char_shi_huagu` / `char_shihua_gu`), 吞天噬地 (`skill_tuntian` /
`skill_tuntian_shidi`), 当世青州州牧 (`char_zhoumu` /
`char_qingzhou_zhoumu_dangdai`), 国师制度 (`concept_guoshi` /
`concept_guoshi_zhidu`), plus one alias that collided with another entity's real name
(天庭教 carrying 「天庭」). Every check in the script was green; only a hand-written
five-part scan (same name→many IDs, same ID→differing name/type/first_chapter,
out-of-range declaration, name-implies-ownership-without-an-edge, alias collides with
another entity's name) found them.

Why the existing checks miss it: check 2 (`entity_first_chapter`) groups by **ID**, so
two IDs for one person just look like two people with the same name. A cheap fix would
be to add a `duplicate_entity_names` check keyed on `name`, reported as a question
rather than an error. Until then: **run a name→ID scan yourself before merging.**

### G2. The intimacy gate wants the *event* in `related_ids`, not the participants — **open**

`build_results_facts.py` collects "events already explained" from
`review_issues[].related_ids`. A `review_issue` that names only the two characters
does **not** silence an `intimacy` event; the event's own ID must appear in the list.
Cost this round: one wasted full rebuild — the issue was written, the gate still
failed, and nothing said why. The gate's message ("既无亲密行为记录，也没有待核问题
说明") reads as "you wrote no issue" when the truth is "your issue doesn't point at
the event".

### G3. `duplicate_trait_anchor` has no documented remedy, and none of the obvious ones work — **open**

`character_traits.FACETS` has exactly four values (`appearance`, `personality`,
`speech`, `habit`), so "give the second statement a different facet" only works when
the facet was genuinely wrong. Two distinct facts from one chapter for one facet
cannot be separated, and deleting one loses content. What does work is **merging**:
join the statements with 「；」 (dropping the interior full stops), union
`evidence_ids` preserving order, keep the strongest `confidence`. Seven groups were
merged this way; the trait count dropped 572→565 while losing no fact. The validator
message says "同一时点只应保留一条" but never says *how* — worth stating.

### G4. `audit_schema_coverage.py` checks a path a run may not have, and the pipeline swallowed the failure — **open**

Two independent failures on the same step:

1. The script accepts only `--run-dir` / `--task-spec`. A `rebuild.sh` line written as
   `--json _schema_coverage.json` makes argparse exit 2 with
   `unrecognized arguments`, and because that line carried `|| true` the step became a
   **silent no-op**: no artifact, no message, whole chain green. Same family as
   `audit_reader_prose.py` (which also has no `--graph`). The fix is not "remove the
   flag" — it is to make argument rejection **fail the build**, because the next
   wrong flag will be written by someone else.
2. Its check [2] reads `fragments/TASK-SPEC.md` and requires a fenced block containing
   `metadata` and `evidence`. A run that keeps its specs in `EXTRACTION-SPEC-*.md`
   files (as this one did for three rounds) has **no `TASK-SPEC.md` at all**, so the
   check reports "找不到模板块" — a real failure, but one that only appears once the
   script is actually invoked. `references/TASK-SPEC.template.md` says "copy this
   structure into a run's `fragments/TASK-SPEC.md`"; nothing enforces that step.

### G5. The new retrieval-coverage gate cannot be applied retroactively — **open by design**

`audit_context_coverage.py` takes coverage receipts produced *during* extraction. A
run that predates the gate has none, and writing them afterwards would fabricate a
record of retrieval that never happened. The honest handling is a conditional step in
`rebuild.sh` that runs the gate when receipts exist and prints
「[未运行] … 不伪造检索记录」 when they do not, plus a line in `RESULTS.md`'s residual
gaps. Anything else turns a new gate into a new lie.

---

## What held up

Worth recording, because these are the parts not to change:

- **Quote-only evidence with central line resolution.** 3,331 evidence records, every one verified by source SHA256 and contiguous-substring audit.
- **Strict kinds + list union.** The constraints are correct; the gap was documenting what they *prevent*, not the constraints themselves.
- **`plan_reconciliation.py` before merging.** Its check 7 (cast no fragment declared) is the reason the cross-pass divergence did not become a duplicate-entity problem.
- **Two independent renderers with one resolver contract.** They disagreed once (both leaked bare IDs); the smoke test caught it.
- **Running the real renderer, not a re-implementation, for as-of checks.** The Python mirror missed a chapter-22 fact in a chapter-17 view for several rounds; the real-renderer check found it on the first run.
- **`plan_reconciliation.py` before merging** — again. This round it caught three entity IDs a fragment re-declared as new (`char_wang_erhuo` first seen ch503, `org_xiaodao_hui` ch506, `concept_wuling_dahui` ch517, all already declared by fragments 62/63). They became **field-level restatements** with `first_chapter` corrected and a `description` that says so, instead of duplicate entities that the merge would have quietly coalesced with the wrong `first_chapter` (min wins, so the *later* wrong value would have been silently discarded — the good outcome for the wrong reason).
- **The self-verifying fragment generator (F1).** The first fragment of this round with zero quote defects, and the first whose JSON never needed repairing.
- **The `--acknowledged` + `--strict` split (E4).** Turning "a human looked at this" into a fingerprinted file is what lets `--strict` stay a real gate across rounds instead of being switched off once the baseline is non-empty.
