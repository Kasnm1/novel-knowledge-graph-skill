# AI workflow: survey → lanes → chapter audits → verification

How the work is divided between agents, and what each one receives and returns.
The per-chapter checklist itself is `chapter-audit-spec.md`; every command below is
a subcommand of `scripts/audit_workflow.py`.

## 1. Survey the whole book first

A cheap, fast model reads the whole book once, before any chapter is audited.

```bash
python scripts/audit_workflow.py survey-scaffold --chapters-jsonl <run>/chapters.jsonl --output <run>/survey-scaffold.json
# the survey model fills <run>/survey.json from the book, using the scaffold's hints
python scripts/audit_workflow.py survey-check --survey <run>/survey.json --chapters-jsonl <run>/chapters.jsonl --registry <run>/ids.json
```

`survey.json` holds the cast (names, aliases, pinyin slug, tier), the level
systems, the arcs (volume / arc / sub-arc with chapter ranges), a one-line
outline per chapter and the non-narrative chapters. `survey-check` validates it
and issues IDs for the cast and level systems, so no chapter worker ever
invents an ID for a main character. The survey is a plan: chapter audits confirm
or correct it with evidence, and it never becomes a fact.

## 2. IDs are issued, not guessed

`<run>/ids.json` is the registry. Before creating an entity a worker asks it:

```bash
python scripts/audit_workflow.py ids --registry <run>/ids.json --lookup 黄虎
python scripts/audit_workflow.py ids --registry <run>/ids.json --claim character 黄虎 huang_hu --alias 刀疤男 --first-chapter 298 --by L03-U12
python scripts/audit_workflow.py ids --registry <run>/ids.json --issue-fragment L03-U12 --fragments-dir <run>/fragments
```

A known name or alias returns the existing ID. A name bound to two entities is
refused as ambiguous: deciding identity is a judgment, recorded with evidence or
as a review issue, never a string match. Fragment numbers and record markers
(`f37`) come from `--issue-fragment`, never from counting files by hand. An
existing run seeds the registry from its graph with `--seed-graph`.

## 3. Lanes run in parallel, units run in order

```bash
python scripts/audit_workflow.py plan --chapters-jsonl <run>/chapters.jsonl --survey <run>/survey.json --density --output <run>/plan.json
```

- A **lane** is one top-level arc (or a fixed window when there is no survey).
  Lanes are independent; each starts from the checkpoint at the chapter before it.
- A **unit** is 3-5 chapters inside a lane, sized to about 10k characters weighted
  by plot density. Units in a lane run strictly in order (`depends_on`), because
  each one needs the state its predecessor left.
- A unit's `read_only_context` names the tail of the chapter before and the head
  of the chapter after. Read them so a scene crossing the boundary is whole;
  record facts only inside the unit's own chapters.

Run and resume from `audit-state.json` (kept beside `plan.json`):

```bash
python scripts/audit_workflow.py status --run-dir <run>                     # lanes, ready units, tokens spent and projected
python scripts/audit_workflow.py next --run-dir <run> --graph <run>/graph.json --count 4   # claim ready units: fragment name, marker, capsule
python scripts/audit_workflow.py update --run-dir <run> --unit L03-U12 --status done --gate-runs 2 --verify-rounds 1 --tokens-extract 41000 --tokens-verify 15000
```

Merge each finished unit before claiming the next unit in its lane, so the next capsule starts
from the state that unit left. A new session resumes from `audit-state.json` alone.

Parallel ten-chapter slices are not allowed: they are what left the sample run
with stale states, unclosed relations and 546 thin chapters.

## 4. What a chapter worker receives

For each chapter of its unit:

- the chapter text plus the read-only context;
- the **state capsule** — the graph closed at the previous chapter, for the
  entities this chapter mentions, with their open threads:

  ```bash
  python scripts/audit_workflow.py capsule --graph <run>/graph.json --chapter 301 --chapters-jsonl <run>/chapters.jsonl --output capsule-301.json
  ```

- the ID table limited to those entities (`ids --output`), `chapter-audit-spec.md`,
  and the book profile.

Keep the spec, schema summary and ID table in a fixed prompt prefix so they are
cached across calls; only the chapter, context and capsule change.

## 5. Three steps per chapter

1. **Reading notes, in free text**: the scenes, who is present, every beat, every
   change to every present character, anything that might be a clue. Save them as
   `<run>/fragments/notes/<unit>-<chapter>.md`. Writing a hundred-field JSON while
   reading is where beats get compressed and characters dropped.
2. **Structure the notes** into the fragment with `FragmentBuilder`
   (`scripts/nkg/workflow/authoring.py`, see `fragment-authoring.md`), never as hand-typed JSON.
   It numbers IDs, deduplicates evidence and computes the audit receipts for you.
3. **Fill the audit card last**: every receipt from the records just written, every
   `state_check` answered against the capsule. Then `resolve_evidence.py` and
   `check_fragment.py`; a card that fails is not done.

## 6. Independent verification

A different agent — preferably a different model — verifies each chapter. It
receives the chapter text, the fragment's records for that chapter and the recall
candidates, and **not** the extractor's notes or reasoning:

```bash
python scripts/audit_workflow.py recall --graph <fragment-or-graph.json> --chapter 301 --chapters-jsonl <run>/chapters.jsonl --output recall-301.json
```

It follows `verifier-prompt.md` and returns a verdict. Missed or wrong records go
back to the extractor for one correction round; a second failure becomes a
`review_issues` entry. Then:

```bash
python scripts/audit_workflow.py score --graph <fragment-or-graph.json> --chapter 301 --recall recall-301.json --verifier verdict-301.json --ledger <run>/coverage-ledger.json
```

Additionally re-audit a random 10% of chapters blind (a second extractor from
scratch) and compare the two structurally:

```bash
python scripts/compare_fragments.py --a <first>.json --b <second>.json --chapters 301-305
```

Agreement per record kind (events, state changes, relations, traits, intimate acts,
commitments, clues) shows where the audit is unstable. On the ten-chapter trial,
Opus and Sonnet agreed at 0.75 overall, 1.0 on intimate acts and 0.64 on state changes.

## 7. Models

| stage | model | why |
|---|---|---|
| survey | small, fast | volume; coverage matters more than nuance |
| chapter audit | strongest available | identity, implied state change, consent and clue judgments decide recall |
| verifier | strong, different from the extractor | errors should not be correlated |
| reconcile, editorial (arcs, tiers, dated headlines) | strongest available | cross-chapter judgment |

Structure — IDs, time, evidence, receipts, spoiler closure — is enforced by code,
so a weaker model cannot return a malformed result. It can still miss things: the
difference between models shows up as recall, wrong records and extra correction
rounds, and is measured, not assumed.

## 8. Gold chapters

Keep about ten human-checked chapters as a gold set. Before changing a prompt, the
unit size, the capsule or a model, audit the gold chapters with the new setting and gate:

```bash
python scripts/compare_fragments.py --a <new>.json --b <gold>.json --gold --min-recall 0.8 --previous <last-gold-report>.json --output <gold-report>.json
```

It fails when any record kind falls below the recall floor or below the previous report.
(`accuracy_regression_gate.py` remains the ID-level gate for re-running the *same* run.)

## 9. Book profile focus

`book-profile.json` may declare the genre and what deserves extra depth (levels
and artifacts for cultivation, identity and wealth for urban stories, routes and
intimacy for harem stories). The profile changes how closely each checklist item
is read; it never removes an item or its receipt.
