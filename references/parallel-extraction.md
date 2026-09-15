# Parallel fragment extraction at scale

Use this reference when a run covers enough chapters that one pass would exceed a single context window
(roughly 40+ chapters, or 300k+ characters). It records the procedure that was verified end to end on a
50-chapter run and the failure modes it prevents.

## Why split

Chapter extraction is per-chapter evidence work, so it parallelizes cleanly along chapter ranges. The risk is
not the extraction itself but **divergent conventions between passes**: the same entity getting two IDs, the
same evidence field written two ways, or coverage boundaries that do not line up. Everything below exists to
control that risk.

## Single-agent mode

Parallel extraction is the default because it is faster, but it is not always available: subagent dispatch
gets rate-limited (the run this section came from lost nine passes to 429 and waited five hours for the reset),
the user may ask for one thread, and a range under about thirty chapters is not worth the coordination. The
work is identical — only the scheduling changes.

**The binding constraint is context, not effort.** Ten chapters of source run to roughly 35k characters, and the
fragment you write back is comparable, so a main agent holds two or three ranges before its window is full.
Plan for that instead of discovering it at range four.

1. **Take five to ten chapters at a time.** Fewer and the fixed cost of re-reading the spec and checking the
   fragment dominates; more and the fragment you are still composing competes with the source you are reading.
2. **Write the fragment to disk the moment it is drafted.** The fragment is the durable artefact; the chapter
   text you just read is not. Once the JSON is on disk that range can be let go — which is what makes room for
   the next one.
3. **Never re-read a finished range to answer a question.** The answer is in its fragment. Re-reading is exactly
   how a single-agent run runs out of context at range three.
4. **Keep a progress file** at `fragments/_progress.json`:

   ```json
   {"completed_ranges": [[1, 10], [11, 20]],
    "next_range": [21, 30],
    "notes": "第 21 章起改为第三人称；21-30 无感情线推进"}
   ```

   Update it after every range. When the window does fill, a new session reads this file and resumes at
   `next_range` rather than re-deriving where the last one stopped. This is the only part of single-agent mode
   that cannot be reconstructed afterwards — everything else lives in the fragments.

5. **Run the same gates per range**: `resolve_evidence.py`, then `check_fragment.py`. One validation pass at the
   end of the run cannot tell you *which* range produced a defect, and by then the source has left context.
6. **The command chain is unchanged** — merge, validate, dashboard, export — because a fragment is a fragment
   regardless of who wrote it. `merge_graph.py` never asks how many agents were involved.

**Write the progress file before the context is full, not after.** The failure mode is a session that ends
mid-range with nothing on disk recording which ranges are done; the next session then either redoes work or
silently skips a range, and neither shows up as a validation error.

## Procedure

1. **Prepare once, deterministically.** Run `prepare_novel.py` for the full range. Every fragment must read the
   same `chapters/NNN.txt` files so source line mapping is identical across passes.

   **Check for front matter before trusting the split.** `prepare_novel.py` only recognises a line matching
   `第<numeral>章`, and it requires `--start >= 1`. A 序章 / 楔子 / 引子 heading, or any prose before the first
   numbered heading, is therefore discarded with no warning: it does not appear in `prepared_chapters`, not in
   `missing_chapters`, and not in `detected_heading_count`. Compare `prepared_characters` against the source
   byte count and skim the head of the file. When a prologue exists it is usually load-bearing — in the run that
   prompted this line the 序章 (2,906 chars) held the protagonist's entire motive — so add it as `chapters/000.txt`
   with a prepended `chapters.jsonl` record and `chapter_start: 0` in the manifest, and record the manual step in
   the results file. Chapter 0 is a legal chapter number everywhere downstream (`resolve_evidence.py`,
   `validate_graph.py`, and both renderers accept it), but note that a `|| 1` fallback on a chapter number
   silently turns 0 into 1, so verify the prologue is actually reachable in the delivered dashboard.

2. **Classify chapters before extracting.** Scan `char_count` and keyword hits to find non-narrative chapters
   (author notes, vote requests, announcements). These must appear in `metadata.analyzed_chapters` — coverage is
   validated against it — but must yield no entities, events, or evidence. Give each one a `review_issues`
   record with a dedicated category.

   The same material is often **not its own chapter but a tail block inside a story chapter** — an author's note,
   a vote request, or an announcement appended after the last narrative paragraph. Chapter-level classification
   cannot see it, and a pass that reads to the end of the file will quote it as story. Put the rule in the spec:
   the last block of a chapter is not story when it addresses the reader, and no entity, event, or evidence may
   be drawn from it. A serialised web novel has one of these every few chapters, so this is a standing rule, not
   an exception.

3. **Write one shared extraction spec** into `fragments/EXTRACTION-SPEC.md` and have every pass read it. It must
   contain, at minimum:
   - the exact output JSON shape and the `metadata.analyzed_chapters` rule;
   - the evidence rule (see below);
   - a **fixed entity ID table** for the main cast, plus the naming rule for new entities — and, alongside it,
     a **cast-ownership table** saying which pass owns each main character. The ID table alone does not close
     the commonest gap in a multi-pass run: a supporting character who looks like scenery in the pass that
     first meets them and like a speaking role in the next, so neither pass creates the entity. Assign every
     named character who speaks more than a handful of times to exactly one pass, and write the assignment
     down. Verify the table against the source before shipping it: a table that lists an alias the text never
     uses, or misses the form it does use (a pass calling her `小宁` while the text also says `天仙少女`),
     sends every pass looking for the wrong string;
   - the **undeclared-cast rule**: a pass that repeatedly attributes speech to a name for which no entity
     exists must either create the entity or record the decision in `review_issues`. `plan_reconciliation.py`
     check 7 reports what was missed, so write the rule so that it and the check agree on what "repeatedly"
     means — speech context, not raw mentions, since 「自己」 appears 700 times and is not a character;
   - the **masked-text rule**: TXT compilations sometimes replace words with `**` — the 流氓老师 source has
     74 of them across 26 chapters, always the same kind of word. Treat the asterisks as opaque: never guess
     the masked word, never write a guess into a `label`, `summary`, or `attributes`, and never let the
     masking change what a sentence is recorded as evidence *for*. Quote it verbatim, because `**` is source
     text and the scrub pass must never touch `quote`. Record the count and the chapters in the run's results
     file as a known limitation — this is a defect of the copy, not of the book, and a reader comparing the
     graph against a clean edition will otherwise find an unexplained difference;
   - required fields per record type, copied from `schema.md`;
   - the content-discipline rules. **These are about what is worth recording, not about filtering the
     book.** Every source in these runs is a published, state-reviewed edition that national review has found
     legal and compliant, so a pass records what the text says and leaves the judgement to the reader and to
     human review: a contested or uncomfortable fact — violence, an explicit sexual act, a rape, anything
     involving a minor — is kept and, where it is genuinely contested, flagged in `review_issues` (with
     `severity` and a reason). It is **never** dropped, thinned out, softened, censored, euphemised, or
     accompanied by a disclaimer, and a pass never declines to record an act because it is explicit. Copy the
     global rule from `SKILL.md` into the spec **verbatim** rather than paraphrasing it. Write that rule into
     the spec explicitly, or a pass will quietly leave things out — the run that prompted this line had a pass
     omit a minor character's records and had to restore them from a script afterwards.

   The spec is **per range, not per book**: regenerating it for the next range has to refresh the chapter
   range, the fragment-number examples (`F=`, `event_fN_xxx`, `ev_fN_001`), and the entity ID table — a table
   that still lists 200 entities when the graph has 333 is what makes a pass invent a second ID for a
   character that already exists. **Derive the fragment number from what is already on disk** (highest existing
   `fragment-NN` + 1), never hardcode it: backfill fragments (levels, foreshadow dates, persona, identities)
   take numbers above the chapter-range ones, so a hardcoded value hands two fragments the same `F=` prefix and
   their evidence IDs (`ev_f36_001` …) silently overwrite each other on merge. If the spec carries a long prose
   section of hard-won rules, verify it survives regeneration (`grep` for a marker phrase) rather than assuming
   the refresh only touches the parts it is supposed to.

4. **Give each pass a disjoint chapter range — and make it contiguous.** Partition story chapters into roughly
   equal character counts (not equal chapter counts — chapter length varies several-fold). Allocate every
   non-narrative chapter to exactly one pass so the union of `analyzed_chapters` equals the full prepared range.

   The ranges must be **unbroken spans**. A pass can only reason about continuity inside the chapters it owns:
   its later `before` values come from its own earlier `after` values, and it reads the chapter immediately
   before its range to pick up the first one. An interleaved assignment destroys both. A greedy "assign each
   chapter to the lightest bucket" loop balances the weights perfectly and produces exactly that failure — the
   first attempt in the Douluo run handed one pass `ch051-141` as a scatter of non-adjacent chapters. Use
   `scripts/plan_fragments.py`, which does a DP over contiguous cuts, asserts the partition covers every chapter
   exactly once, and also flags the non-narrative chapters inside each block so each pass is told which ones in
   its range are notes.

5. **Have passes emit quote-only evidence.** Instruct each pass to write only `id`, `chapter`, and `quote` for
   evidence and to omit `source_line_start` / `source_line_end` entirely. Agents cannot reliably compute source
   line numbers, and asking them to try produces wrong ranges that fail the audit. Fill the line numbers
   afterwards with a resolver script that searches the prepared chapter text.

6. **Resolve quotes centrally.** The resolver maps a chapter-relative line index to an absolute source line as
   `source_line_start + index`. It must match within a **single line** — so require quotes to be contiguous text
   from one paragraph, never spanning lines. Report and repair any quote it cannot find before merging; a
   resolver failure means the evidence is not real.

   The resolver takes the **first** line that contains the quote and never reports a tie, so a chapter that
   repeats a paragraph silently resolves to the earlier copy and the later copy's line range is never recorded.
   Pirated TXT compilations do repeat paragraphs — the run that prompted this line had an identical opening
   paragraph at chapter-relative lines 5 and 81 of chapter 1 (it happened to be quoted by no record, so nothing
   broke, but that was luck). Check for it after resolving: for each evidence record, count how many times its
   quote occurs in its chapter and review any count above 1, or the reader-facing chapter attribution is still
   right while the internal line range points at the wrong copy.

7. **Detect cross-pass divergence before merging.** Run `plan_reconciliation.py` — it is read-only and exits 0,
   and it does the comparison mechanically instead of by eye. It reports one entity with two IDs, an ID with two
   `first_chapter` values, several romance routes for one pair (printed as ready-to-paste `--id-map` lines), an
   `ev_*` id referenced but declared by no fragment, the same record ID on a non-strict kind in two fragments,
   a quote that occurs twice inside its own chapter, and **cast that no fragment declared**. Classify each
   finding by inspecting the linked evidence quotes, not by name similarity — except the last, where the quote
   is what you add.

   The cast check is worth understanding rather than just running, because its output decides whether a
   supplementary fragment is needed. It reads *attributed speech*, not names in isolation: the prose writes
   `陈天明高兴地说道` and `旁边的冯豪急了，说道`, never the bare `陈天明说道`, so a name is taken as the front of a
   short speech-attribution window, as 2- and 3-character prefixes, and it must be concentrated in speech context
   (小宁 speaks in 19 of its 46 occurrences; 自己 speaks in 17 of 705). Every hit names the fragment that owned
   its first chapter, so the question is addressed to one pass. A hit is either a real entity you add in a
   supplementary fragment, or a decision you record in `review_issues` — 「司机」「护士」may warrant an entity
   where 「瘦小」never will, and the script cannot tell you which.

8. **Merge with `--id-map OLD=NEW`** for every confirmed synonym, then confirm `metadata.merge_conflicts` is
   empty. Record the mapping in the run's results file so a later pass reuses the canonical ID.

9. **Validate, then regenerate every downstream artifact.** Never hand-edit `graph.json`; fix the fragment and
   re-merge so the run stays reproducible.

## Failure modes this prevents

| Symptom | Cause | Fix |
|---|---|---|
| `quote_not_found` on many records | Passes computed line numbers themselves | Quote-only evidence plus a central resolver |
| `duplicate_relation` | Two passes each created an edge for one unchanged relationship | Symmetric types and overlapping validity intervals are coalesced at merge; keep one record and append evidence |
| `chapter_outside_coverage` | A pass recorded a chapter outside `analyzed_chapters` | Allocate every prepared chapter to exactly one pass |
| `coverage_mismatch` | Union of `analyzed_chapters` does not match manifest bounds | Assign non-narrative chapters explicitly |
| Validator crashes on a fragment field | A pass used the wrong JSON shape for an optional field (for example `progression` as a string, or `aliases: null`) | Fix the fragment; the validator should report a clear error rather than raise |
| One entity, several IDs | No shared ID table — or the table lists only the IDs already declared, so a continuation pass has to invent a spelling for an entity that first appears inside its own range | Ship the generated table (`export_id_table.py`) in the spec, and **rewrite the losing ID in the fragment that declares it**, never with a merge-time `--id-map`. `--id-map` remaps the merged graph while the stale token stays on disk; the next continuation round reads it back and mints the duplicate entity all over again |
| A continuation round merges cleanly, yet an entity's `summary` lost three fragments' worth of findings | `summary` is a scalar and `merge_value` keeps the **last** input's copy, so four passes writing complementary summaries leave only one | Write one consolidated `summary` in the fragment that declares the entity *last*, folding in every earlier pass's text. `notes` on a shared `romance_routes` record behaves the same way. Nothing warns: the merge reports no conflict and validation passes |
| A whole fragment's `state_change` records are rejected with `state_change.reason is required` | The pass omitted one required field on most of its records while filling every other field | Group the failures by fragment before fixing. One missing field spread over 24 records of a single fragment is one pass's habit, not 24 independent mistakes — read the chapter and write the reason |
| An entity's `first_chapter` is later than the text's first mention, and the fragment's own `notes` admits it | The pass recorded the earliest chapter **inside its own range** and documented the discrepancy instead of correcting the field | Fix the field and add an evidence record for the true first chapter. A value its own note already flags as wrong still reads as reviewed, which is worse than an unflagged one |
| A `confidence: "explicit"` record whose evidence supports only half of it (evidence shows the demand, the record asserts the handover) | The pass quoted the nearest line and stopped there | Downgrade to `inferred` and say in `reason` which half is the inference. The validator cannot see this: the quote exists and matches |
| Chapter text contains `<divclass="contentadv">`, `<center>高速本站域名</center>show_yuedu3;`, or a `&#91;…&#93;` entity-encoded promo URL | Front-matter trimming covers only the block *before* the first heading, so site furniture past it survives into the text every pass quotes from | `prepare_novel.py` strips it per line (`clean_inline_packaging`). Clean in place, never by deleting lines — `source_line_start` is a source line number and the resolver locates quotes by it. Keep `【…】` blocks: in this corpus they also carry real setting material (a level table, an item description, a currency note), so a blanket drop deletes world-building |
| The merged graph says it came from the last fragment alone (`fragment-11-ch091-100` for a twelve-fragment book) | `metadata.fragment` is a fragment-level scalar, and scalar merge keeps the last input's value | `merge_graph.py` drops it; the real source list is `metadata.fragment_sources` |
| `incompatible duplicate` on a strict-kind record | A supplementary pass re-declared an evidence/event/state_change ID that already exists with different text | Do not re-declare it; reference the existing ID. Strict kinds are compared by full equality, so even a shorter paraphrase of the same quote counts as a conflict |
| `alias_collision` between two entities that are genuinely different things | One in-world word names two things (a technique and the bug it uses; a move and the weapon it conjures; a species and the individual of it) | Do not merge them. Give one of them a different name taken from the text's own alternative wording, and drop the shared word from the other's `aliases`. Record the decision as a `review_issues` entry |
| A level ladder shows a false regression mid-curve | Two or three passes each recorded the same step (the same palm, the same layer) and the later ones reset `before` to the previous rung | Keep the earliest record, fold the later ones' evidence into it, delete the duplicates |
| A level ladder shows a step whose `before` skips over an earlier loss | The loss (damaged core, sealed power) was recorded by a different pass | Expected: replay is chronological. Confirm the loss has a `reason`, then leave it |
| The graph claims coverage far beyond what was analyzed | `merge_graph.py` unioned the manifest's `prepared_chapters` into `analyzed_chapters` | Coverage must come from the fragments only. The manifest supplies title / source file / SHA256 and nothing else; fall back to it only when no fragment declares coverage |
| The prologue is absent from the graph and nothing warned | `prepare_novel.py` matches only `第<numeral>章` and rejects `--start < 1`, so a 序章 / 楔子 heading and any prose before the first numbered heading are dropped silently — missing from `prepared_chapters`, `missing_chapters`, and `detected_heading_count` alike | Compare `prepared_characters` against the source byte count and read the head of the file before extracting; when a prologue exists, add it as `chapters/000.txt` plus a `chapters.jsonl` record and `chapter_start: 0` |
| The event-type facet offers no usable grouping | No shared type set, so every pass coined its own labels: 112 events produced 55 types, 35 of them used once | Fix the set in `scripts/event_types.py` (merge folds the aliases onto it and both renderers take their labels from it), and put the specifics in `tags`. `validate_graph.py` lists the labels left outside the set as an observation |
| A reader-facing label shows `未分类` or `[object Object]` | The display vocabulary is missing an enum value the graph actually uses; the schema required the field but never listed its allowed values, so a pass invented a scale (`high` / `medium` / `suspected` for a `confidence` whose real values are `explicit` / `inferred` / `uncertain`); or a value was written as an object instead of a string | Before rendering, diff every enum the graph uses against the vocabulary groups and fill the gaps; read allowed values from the record type that documents them rather than inventing a scale |
| A personality, avatar, or possessing double is in the graph but nowhere in either deliverable | It was typed `concept` (or another `NON_AGENT_TYPES` member), so `agent_detection.py` skips it before scoring and it can never reach the character layout | Retype it to `character` and add a relation back to the host. `agent_detection.py` prints a second list of type-excluded entities that act like people, so check it before delivery |
| Two entities are "the same person" but nothing in the graph says so | The split was extracted as two entities with no edge between them, so the reader cannot tell they share a body | Add an `alter_ego_of` / `same_body_as` relation and a vocabulary entry for it; without the edge the split is invisible even though both entities exist |
| A takeover appears in one agent's timeline but not the other's | Only one end was recorded | Record both: the host loses control, the other self gains it, each with its own `reason`. Same rule as any other loss or transfer |
| An ID's prefix contradicts its `type` (`concept_dark_liu_yi` typed `character`) | The entity was retyped without renaming, and a fragment cannot rename an ID | Rewrite the ID in the fragments with a reference-rewriting script, then carry the type change in a supplementary fragment. Keep the two halves separate: renaming is mechanical, retyping is a semantic claim |
| The item or skill shelf shows 归属未明 for something whose name says whose it is (`陈才的召唤异能`) | The entity was created from the text without a relation to its bearer; validation only checks that references resolve, not that a reader can tell whose a thing is | Add the edge in the same fragment that creates the entity (`owns` for a belonging, `disguised_as` for a cover identity), and run `scripts/audit_entity_links.py` over the whole graph — this is never one entity, it is a habit |
| A cover identity is invisible beside the person who wears it (`血皇` has no edge to 刘弈) | The name contains no hint of the bearer, so no name-based check can find it | Nothing catches it mechanically. Make it a step in the pass: when the text gives a character a new name, title, or codename, decide then whether an entity is needed and add the edge in the same fragment |
| Two fragments share an `F=` prefix, so their evidence IDs collide | The spec's fragment number was hardcoded and a backfill fragment had already taken it | Derive the number from the highest `fragment-NN` on disk. Symptoms are quiet: the second fragment's `ev_fNN_001` merges onto the first's and one pass's evidence silently disappears |
| The merged graph is missing a record a fragment declares, yet validation still says `valid: true` | The fragment was edited after the merge, so `graph.json` predates it. Validation proves the graph is self-consistent, never that it is current | Re-run the whole pipeline from `merge_graph.py` after **any** fragment change. A validator run alone is not a rebuild |
| `prepare_novel.py` writes one chapter file and a tiny `prepared_characters`, and most of the requested range is `missing_chapters` | The volume prefix wording is not the one the script recognises (a book that opens chapters with `第一卷 第1章` against a `第X集`-only prefix regex), so every heading line is rejected | Sanity-check `prepared_characters` against the source byte count **before** extracting; a 13 MB novel cannot prepare as 3,000 characters. Extend `VOLUME_PREFIX_RE` to the book's own wording (`[集卷部篇]`) rather than rewriting the chapters by hand. The script now self-checks and prints `WARNING: 自检未通过` with a non-zero exit when the heading count and the chapter count disagree this badly, so read the warnings rather than only the exit code |
| The 内容简介 / blurb is included as chapter 0, so the first thing a reader sees is a three-sentence summary of the ending | `--front-matter auto` judged the block by shape, and a title page plus blurb is long prose lines | The script now vetoes any front-matter block carrying packaging markers (`内容简介`, `作者：`, `声明`, `版权`, `.com` …) and records them under `front_matter.packaging_markers`. If a real prologue is dropped because it mentions one of those words, pass `--front-matter prologue` |
| Two or more `romance_routes` for one character (`rom_f01_hetao`, `rom_f02_hetao`, …), so the merged graph reports several routes for the same woman | Each pass minted its own route id instead of reusing the one the first pass created, however explicitly the spec asked for it | Do not rely on the passes: `plan_reconciliation.py` check 3 prints the `--id-map rom_fNN_<slug>=rom_<slug>` lines to paste, and `validate_graph.py` reports the leftovers as a `duplicate_romance_pair` observation after the merge. Then add a supplementary fragment that restates each route with the consolidated `status` / `inclusion_basis` / `consent_context` and one `notes` covering every mixed case, because the scalar merge otherwise lets the last fragment's wording win silently |
| A route's `first_meeting_chapter` / `first_meeting_evidence_ids` is empty and validation fails with `missing_milestone` | The first meeting is in an earlier pass's range, so the pass that created the route could not quote it | Have the supplementary fragment supply the milestone using the **earlier pass's existing evidence id** (never re-declare the quotation), and check every referenced `ev_*` id actually exists in the merged graph before rebuilding. Write it into the fragment that already holds that route's full record — do **not** add a route stub carrying only `id` plus the new field. A stub is invisible to `merge_graph.py` (it merges field by field and the full record survives) but blind to every *pre-merge* reader: `plan_reconciliation.py` groups routes by `(protagonist_id, character_id)`, so three stubs collapse into one bogus ("", "") pair and get reported as "the same woman". If a canonical romance fragment already exists, restate the milestone there |
| Validation fails with `bad_entity_ref` for an organization or location the passes only mentioned in prose | No pass created the entity, but a foreshadowing or relation record already references its id | Add the missing entity in the supplementary fragment, reusing the existing evidence ids that named it |
| A supporting character speaks across several chapters and appears in no fragment's `entities` | It looked like scenery in the pass that first saw it and like a speaking role in the next, so neither pass owned it | Run `plan_reconciliation.py` and read check 7: it reports the name, its speech-context share, and the fragment that owned its first chapter. Add the entity in a supplementary fragment, or record in `review_issues` why none is warranted. 「司机」「护士」may deserve an entity where 「瘦小」never will — the script ranks, it does not decide |
| An evidence record points at the wrong line range while its chapter is right | The quote occurs more than once in the chapter, and the resolver takes the first match without reporting a tie | Check 6 of `plan_reconciliation.py` lists every evidence id whose quote occurs more than once in its own chapter; re-quote a longer span that is unique in the chapter |
| One pass returns a chat reply but no file on disk — its range merges as "nothing happened here" | The pass narrated its result instead of writing it. Nothing catches this by default: `merge_graph.py --input fragments/fragment-*.json` globs whatever exists, so a missing fragment is indistinguishable from a thin range until the post-merge error pile appears | End every pass's prompt with "write the file, then confirm it exists and is non-empty — a reply without a file is not a result". Before merging, run `plan_reconciliation.py` check 0: it asserts the fragment count equals the planned pass count and that each file parses with a non-empty `evidence` array and the `analyzed_chapters` you assigned it. A lost pass otherwise surfaces as a wall of `bad_participant_ref` errors that reads like a modelling mistake |
| A clue is planted in one pass's range and advanced in a later pass's, yet the advance never reaches the foreshadowing record (`fs_E02` plants 十个愿望换灵魂 at ch43; the first wish is actually spent at ch67) | Foreshadowing is inherently cross-range — planted in one chapter, progressed in another — but each pass writes only the steps it witnessed, and nothing reconciles the halves the way check 3 does for `romance_routes` | Add the missing dated `progression` step in a supplementary fragment, referencing the later pass's existing `ev_*` id rather than re-declaring the quotation, and never set a resolving `status` without such a step. Before delivery, group `foreshadowing` by `related_entity_ids` and read the groups: two records over the same cast with adjacent `planted_chapter` values are usually one clue split by a fragment boundary, not two clues |
| One entity id carries two different `name` spellings across passes (`org_guangyuan_xueyuan` is 广元学院 in two fragments and 广元国际经济学院 in a third), so the reader-facing name depends on merge order | The passes each wrote the short form they used in their own chapters, and `merge_value` keeps the **last** fragment's scalar without reporting a conflict | `plan_reconciliation.py` check 1 lists every such id. Decide the canonical `name` from the fullest text-attested form and push the others into `aliases` in a supplementary fragment — do not leave the selection to fragment order |

## Coverage integrity

`analyzed_chapters` is a claim about what was read, and `validate_graph.py` uses it to reject records
outside the analyzed range. It must therefore be derived from the fragments — each fragment's
`analyzed_chapters`, or the span implied by its `chapter_range` / `chapter_start`+`chapter_end` — and
never from the manifest. `prepared_chapters` means "these chapters were split into files", which for a
full-novel prepare step is the whole book; unioning it in silently turns a 300-chapter run into a
1319-chapter claim, makes `chapter_outside_coverage` vacuous, and lets the page and the AI text
advertise chapters nobody read. Check the merged `metadata.chapter_start` / `chapter_end` against the
fragment ranges before trusting any downstream artifact.

## Continuation rounds: extending a finished run into later chapters

A second round over chapters 151-200 of a run that already covers 1-150 is not a fresh extraction. It inherits a
graph, an ID vocabulary, and a body of state the new chapters take for granted, and it has three specific ways to
drift from it. Each has a script, and the scripts are the reason the round converges:

- **Ranges drift into interleaving.** Use `scripts/plan_fragments.py` (see step 4). Balance by character count,
  keep every range contiguous, and let it name the non-narrative chapters in each range.
- **IDs drift into duplicates.** Use `scripts/export_id_table.py --chapter-end <last analyzed>` and hand the
  output to the spec. An inline ID table in a spec goes stale the moment the graph grows; the generated one is
  read from `graph.json` and cannot. Left to invent, a pass writes `char_xuanshui_dan` beside an existing
  `item_xuanshui_dan` for one pill, and the divergence surfaces only after merging.
- **`before` values drift into guesses.** Use `scripts/export_state_digest.py --chapter <last analyzed>` for the
  state digest and `--foreshadowing` for the open-clue digest. A pass that writes a `before` the chapter text
  does not restate must take it from here, not infer it. The unfiltered digest covers every entity and is too
  large to hand to one pass; `--mentioned-in START-END --chapters-dir chapters` keeps only the entities named in
  that pass's chapters and brings it back to a handable size.

Also give each pass the chapter immediately before its range as a read-only anchor (state only, never extracted
from, never listed in `analyzed_chapters`), and have it chain `before` from the previous `after` inside its own
range. When the round finishes, regenerate the ID table and the state digest for the *new* boundary, so the next
round starts from them instead of from a stale pair.

Two duties the ID table cannot carry, so put them in the spec as explicit instructions:

- **Name the entities that first appear inside the range.** The generated table only lists what is already
  declared. For an entity the book introduces in chapter 57 of a run that so far covers 0-50, no pass owns the
  name, and two passes will mint two spellings of it (`char_puhe` and `char_pu_he`; `item_yanlong_xuandan` and
  `item_wangxuan_longdan`). Give the naming rule, and make the *earliest* pass declare such entities so the later
  ones can reuse the ID rather than guess it.
- **Consolidate `summary` by hand at the end.** Because the scalar merge keeps the last writer's text, the round
  is not finished until one fragment carries a `summary` per multiply-declared entity that folds in every pass's
  findings. Compare the pre-merge declarations (`summary` is in each fragment) against the merged entity before
  trusting it.

One thing the level audit will not catch for you: it checks `before` against `after` *within* a record, so a
record whose `before` silently restates an older value — a pass writing "二十级瓶颈" when chapter 47 already
recorded 约二十二级 — produces a ladder that reads 22 → 20 and no error. Read the ladders, not just
`summary.regressions`.

## Chapter-scoped snapshots must not leak the future

Every renderer has a "截至第 N 章" mode, so every field it prints has to be datable. Most are
(chapter-stamped state changes, events, relations with `valid_from`). Several are not, and each leaks:

- **A foreshadowing `status` of `resolved` / `partially_resolved` / `progressed` / `false_lead`.** The
  status is a single final value on the record; printing it at chapter 17 reveals a payoff that happens
  at chapter 120. Give the record dated `progression` steps (`kind: payoff`) for the resolving chapter
  and print the resolving status only once such a step is at or before the snapshot — or once the
  snapshot reaches the end of the analyzed range. Non-resolving statuses (`open`, `suspected`) carry no
  forward information and can be printed as-is.
- **A `progression` list.** Filter it by chapter too; otherwise the detail panel lists future steps.
- **A relation's `valid_to`.** A relation that is still open at the snapshot must not print the
  chapter it ends at: `第 9 章起，至第 19 章` shown at chapter 10 tells the reader the relationship
  ends later. Gate the end chapter on `valid_to <= chapter` (both the character-panel relation line
  and the relation inspector) and keep only `第 N 章起` while it is still open. `build_dashboard.py`
  exposes `relSpan` / `relSpanTight` for this; a verifier that scans the rendered panel HTML for
  `第 X 章` with `X > N` catches it, and it must strip the timeline navigation dots and the
  `下次变化` button first, because those are deliberate navigation affordances rather than content.
- **Prose that cites the chapter that confirmed it.** `reason`, `description`, `observation`,
  `interpretation`, `notes`, and attribute values are hand-written and routinely name a later chapter —
  a chapter-6 change whose `reason` reads 「第6章首次修炼…；第14章回述其此前处于第一重…」, or an attribute
  value 「玉小刚直系后代（第7章自述）」. A word-list leak check misses these entirely because the giveaway is a
  *chapter number*, not a spoiler noun. The renderer's prose guard (`asOf`) must therefore wrap **every**
  value it prints, not only the obvious prose fields: the Douluo run's guard covered `reason` /
  `description` / `observation` but not `value()` or the attribute rows, so the same leak survived in
  those two paths after the prose fields were fixed. In the AI text, the equivalent single choke point is
  `scrub_text()` in `export_ai_context.py` — put the guard there so it covers every prose field and every
  string attribute value at once, and check the field list is complete (`notes` was missing from it).
  Withhold the whole field rather than trimming the clause: a partially-rewritten sentence is harder to
  audit than a visible 「已隐去」 marker, and `quote` must never be touched.
- **`current_state`.** It is not chapter-stamped, so a renderer may only merge it when the snapshot
  reaches the end of the analyzed range — and it must tolerate both shapes. `build_dashboard.py` assumed
  an object (`{facet: value}`) and ran `Object.entries()`, so a book that stores it as a string rendered
  the sentence one character per row (`0｜仅`, `1｜三`, `2｜人`). Accept a string as a single
  「当前状态」 row. Because it is easy to leave stale, treat `current_state` as an optional convenience:
  `state_changes` remains the single source of truth, and a frozen 1-50-era `current_state` shown at the
  final chapter contradicts the ladder it is displayed beside.

Audit this with a script that mirrors the page's filters rather than by eye: for the final chapter and
one early chapter, replay the same predicates (state changes ≤ N, relations valid at N, foreshadowing
planted ≤ N with a dated resolving status, no evidence line numbers) and assert nothing displayed
carries a chapter beyond N. Run `scripts/verify_chapter_views.py --run-dir <run-dir> --snapshot <N>`: it
extracts the real renderer, drives the real `setChapter(N)` under a Node DOM stub, strips the timeline
navigation affordances, and reports both leaks and an unreachable snapshot. Pass `--snapshot 0` when the
book has a prologue. Do not keep a per-run copy of the script — the copies drift, and each carries the
previous book's default entity IDs and snapshot chapters.

## Display vocabulary is a gate, not a nicety

The page translates every enum through the vocabulary and falls back to a single `fallback` string, so a
missing entry is invisible in validation and only shows up as a wall of `未分类` in the UI. Before
regenerating a renderer, diff the values the graph actually uses against the vocabulary groups:

```
entity_types, facets, actions, relations, relation_statuses, confidences, romance_statuses,
romance_inclusion_bases, consent_contexts, foreshadow_statuses, progression_kinds, event_types,
issue_categories, issue_severities
```

Also assert every vocabulary value is a plain string — a nested object renders as `[object Object]`.

## One body, several agents is an entity-scope decision, not a display tweak

A second personality, avatar, or possessing double is the failure mode that hides best, because both
halves of the mistake look reasonable in isolation: the extraction pass sees one body and files the
other self as a `concept`, and the renderer dutifully draws it as an abstract idea. Nothing errors.
The user then asks why the two are not shown as one person with two sides.

The checklist, in order:

1. **Decide by agency.** Does it speak, decide, cultivate, or seize the body on its own initiative? Then
   it is an agent. Does the same person merely wear a costume or a cover name, with nothing acting
   behind it? Then it is not — keep it an alias, or at most a `concept` for the disguise. **Either way
   it needs an edge to the person**, so the decision changes *which* relation you add, not whether to
   add one: `alter_ego_of` when something acts behind it, `disguised_as` when nothing does.
2. **Type it `character`** — for the agent case only. `concept`, `location`, `organization`, and `title`
   are in `agent_detection.NON_AGENT_TYPES` and are skipped *before* scoring, so no amount of evidence
   can promote them. `is_agent: true` also works, but then the node keeps the wrong shape, colour, and
   filter, and the 人物库 shelf cannot group it with people. Do **not** retype a cover identity: the
   layout is not the problem there, the missing edge is.
3. **Match the ID prefix to the type** — again, only when the type changes. `normalize_persona.py`
   (rename, mechanical, exact-string only) plus a supplementary fragment (type, name, relation,
   history) keeps the two kinds of change auditable instead of blurring them into one edit.
4. **Add the edge.** No relation means the split is invisible however well both entities are modelled.
   `alter_ego_of` / `disguised_as` with a display-vocabulary entry is the minimum; a `description`
   recording the phases (first appearance, formation, takeovers, fusion) is what makes it readable.
5. **Record takeovers from both ends**, and keep the two agents' level ladders, skills, and relations
   separate. A second personality can hold its own tier.
6. **Sweep the whole graph for the same defect, then verify on the artifact.** Run
   `audit_entity_links.py` — the 我的狐仙老婆 run found five more unlinked "belongs to X" entities
   (`刘弈的右手`, `冷沫的光剑刀柄`, `小璇的换装功能`, `陈才的召唤异能`, plus the identities) that no
   one had noticed, because a name like `陈才的召唤异能` reads as self-explanatory until the skill
   shelf says 归属未明. Then run `agent_detection.py` (it prints the type-excluded list), open the
   entity in `smoke_dashboard.py`, and check the 人物库 shelf and the chapter slider: an alter ego
   must be absent before its `first_chapter` and grouped as another side of the protagonist from it
   onward.

## Supplementary fragments for late-discovered facets

Extraction passes work from a spec, and a spec written before the first pass can miss a whole
dimension — a ranked progression system, a second currency of status, a relationship type nobody
anticipated. The wrong fix is to go back and edit validated fragments: they are the audit trail,
and rewriting them makes it impossible to tell a genuine correction from a fabricated addition.

Add a new fragment instead. `fragments/build_level_fragment.py` in the Douluo run is a worked
example of the shape:

1. **Generate the fragment from a script, not by hand.** The script holds the new entities and the
   new state changes as a literal table, and pulls each quotation out of the prepared chapter file
   by absolute source line. Quotes are then verbatim by construction, and the script is the record
   of what was added and why.
2. **Reuse evidence that already exists.** A supplementary pass usually finds that earlier passes
   already quoted the relevant lines for other reasons. Referencing those IDs keeps the evidence
   count honest; re-declaring them fails as an incompatible duplicate.
3. **Do not re-declare existing entities to restate facts.** Only the genuinely new entities belong in the fragment. The one exception is a *field-level correction* on an existing record: when a pass discovers that a record needs a field it was missing, the fragment restates that record with its `id` and **only the added field** — no copied summary, no copied attributes, no re-declared evidence. `merge_graph.py` merges every array field by field (not just entities), so the restatement adds the field and leaves everything else from the original fragments untouched. This is also the way to date a late-discovered fact without rewriting a frozen fragment: the 我的狐仙老婆 run used it to give six already-resolved foreshadowings a dated `progression` step (`fragment-35`) so the chapter-scoped views would stop showing the payoff early. Never use this as cover for rewriting narrative content in an old fragment. Note that the character-style layout for a non-human actor is **not** such a field: `agent_detection.py` derives it from the graph, so a spirit beast earns it by being given attributed speech and its own state changes, not by a restatement fragment. A wrong `type` **is** such a field — restating `{"id": ..., "type": "character"}` overrides the original, because `merge_value` lets a later fragment win a scalar. The matching ID rename cannot go in a fragment, so it belongs in a reference-rewriting script: `fragments/normalize_persona.py` in the 我的狐仙老婆 run is the worked example — it substitutes the old ID only as an exact string (so a mention embedded in prose is reported rather than silently rewritten), prints every JSON path it touched, and refuses to touch anything else.
4. **Write the fragment's array order chronologically.** `merge_graph.py` preserves first-appearance
   order, and both renderers keep array order for records that share a chapter. Sorting by ID as a
   tiebreaker also helps, so choose IDs whose numeric suffix sorts the way the ladder reads.
5. **Re-merge every fragment, then re-validate.** The supplementary fragment is not a patch applied
   after validation; it goes through the same merge and the same full source audit.
6. **Keep a single rebuild entry point.** A `rebuild.sh` that regenerates the supplementary
   fragment, re-merges, re-validates, re-runs the audit, and rebuilds both renderers makes the
   whole pipeline reproducible in one command and prevents the fragment from drifting from
   `graph.json`.

Then audit the new dimension against the source rather than trusting the backfill. For levels that
means `scripts/rollup_levels.py`, which replays each ladder and splits source mentions into
recorded / restatement / candidate-gap buckets. It is a triage tool: nearest-name attribution will
still assign another character's level to whoever stands closest in a long sentence, so every
candidate needs a human read before it becomes a record.

## Reporting

The final results file should state the real coverage, the record counts, every applied `--id-map`, the open
review issues that still need human judgement, and the limits of the extraction. Structural validation passing
means the records are self-consistent and auditable — it is **not** a claim that the chapters were exhausted.
