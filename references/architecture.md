# Architecture and run isolation

Internal module boundaries, and the lightweight run / version / concurrency contract.

## Module boundaries

The product remains one user-facing `novel-knowledge-graph` Skill and one canonical `graph.json` per book/edition. The internal implementation is modular so domain growth does not create competing fact stores or duplicated temporal logic.

### Dependency direction

```text
Skill/router
  -> extraction / validation / views / export / dashboard
       -> temporal + domain rules
            -> nkg.core.GraphRuntime
                 -> canonical graph.json
```

Derived views, checkpoints, dashboards, packets, display profiles and quality reports are disposable. They never become a second story-fact source.

### Package boundaries

- `scripts/nkg/core/`: read-only indexes, cache/provenance utilities and graph query runtime.
- `scripts/nkg/temporal/`: checkpoint/fingerprint utilities and temporal replay primitives.
- `scripts/nkg/extraction/`: context closure, retrieval escalation, dynamic chunking, resume capsules, schema slicing, state capsules, wire deltas and token telemetry.
- `scripts/nkg/validation/`: semantic invariants and accuracy-regression gates.
- `scripts/nkg/views/`: audit/quality views, entity display profiles, dual-axis story time and snapshot comparisons.
- historical top-level CLI files remain compatibility entry points while implementation moves behind these modules.

### Intelligence boundary

Deterministic code owns constraints that must be reproducible: stable IDs, references, temporal replay, evidence links, spoiler closure, provenance, cache validity, serialization, and invariant checks.

AI owns judgments whose meaning depends on the actual work: which visible attributes are important, how to summarize an entity for a reader, which presentation labels are useful, whether a narrative detail is salient, and how to phrase a derived headline. These outputs stay in derived display/context artifacts and must remain evidence/time bounded.

Do not turn semantic presentation preferences into large per-genre or per-entity-type `if/else` maps. If code cannot establish a semantic interpretation without brittle heuristics, expose the underlying evidence/state to the AI and let the AI decide or leave it unresolved.

### Performance contract

Build indexes once per graph snapshot. Code that repeatedly needs entity/event/relation/state lookup should receive a `GraphRuntime` rather than rescan top-level arrays. Long-run snapshot work may prebuild chapter checkpoints. Artifact reuse is valid only when graph/input and builder fingerprints match.

### Accuracy contract

Optimization is constrained by accuracy, not the reverse. Retrieval levels are monotonic:

- R1: local scene + semantic boundary + direct evidence.
- R2: R1 + canonical identity + aliases + prior/current temporal state + contradictions.
- R3: R2 + connected entities + relevant history + distant evidence + unresolved candidates.
- R4: complete relevant/indexed coverage for universal, negative and whole-range claims.

A token budget may trigger task splitting or a larger context window. It may not silently remove mandatory candidates, direct evidence, required history, or lower the retrieval level. Incomplete evidence produces `unresolved`, not a guess.

### Quality and provenance

Quality metrics are derived audit indicators. Evidence coverage, unresolved review work, temporal provenance gaps and invariant warnings are reported separately. Do not convert them into a probability that a story fact is true.

### Compatibility

Existing commands remain supported. New internal APIs must be deterministic and side-effect free unless the command explicitly writes an artifact. Canonical writes use atomic replacement and remain serialized by the existing run-lock/publish contract.

## Run isolation, versions and concurrency

### One run per book edition

Resolve a stable `book_id` from title/edition plus source lineage. Treat the full source hash as a revision fingerprint, not the permanent run identity: appending later chapters to the same edition reuses the canonical run. A materially different edition, translation, or rewritten source may use another edition ID.

Maintain a small registry entry mapping `book_id` to its canonical run directory. If legacy duplicates exist, stop automatic writes and report them for reconciliation; do not create another run.

Resolve before every initialize/continue/backfill task. Use the same explicit IDs even when the source file grows or the prompt requests a different chapter range:

```powershell
python scripts/resolve_run.py --source <novel.txt> --runs-root <runs> --book-id <stable-book-id> --edition <edition-id>
```

Acquire `--claim --owner <task-id>` only immediately before merge/publish, then `--release` after the atomic transaction. Workers analyzing chapters do not claim the run.

### Use the current Skill

There is one active Skill source. Runs must not contain operational copies of `SKILL.md`, references, scripts, assets, or TASK-SPEC. Legacy `_toolchain` directories may be read to understand old output but are not refreshed or executed for new work.

Record the currently applied implementation in `.skill-version.json`:

```json
{
  "skill_name": "novel-knowledge-graph",
  "skill_root": "U:/chaishu/skills/novel-knowledge-graph",
  "skill_fingerprint": "...",
  "schema_version": "...",
  "task_spec_fingerprint": "...",
  "applied_at": "..."
}
```

This receipt is diagnostic metadata, not a frozen dependency. A compatible Skill update may process an older run directly and invalidates only affected caches/derived artifacts. An incompatible schema update requires an explicit migration in the same run. Fingerprint mismatch alone is never a reason to create a new run.

### Short merge lock

Do not hold `RUN.lock` for an entire reading or model task. Parallel workers may:

- read the same immutable snapshot;
- analyze different chapter ranges or candidate sets;
- write immutable fragments in task-local staging directories;
- run read-only audits.

Only merge/publish requires the lock:

1. acquire it atomically with owner/task/time metadata;
2. compare the fragment's `base_snapshot_id` with the current graph snapshot;
3. rebase or reject conflicting/stale deltas;
4. merge, validate, and atomically publish affected artifacts;
5. release the lock promptly.

Different books use different locks and run independently. A stale lock may be cleared only after confirming the recorded owner is no longer active; preserve an audit note.

### Minimal run-local task configuration

Run-local worker configuration contains only book-specific values:

- `book_id`, edition/source paths, and source revision;
- requested/covered chapter range;
- language and display vocabulary;
- user inclusion rules and explicit overrides;
- canonical run/staging paths and base snapshot ID.

Schema fields, extraction rules, validators, and visualization contracts come from the current Skill through `reference-routing.json`. Do not copy the shared TASK-SPEC template into a run as a long-lived authority.
