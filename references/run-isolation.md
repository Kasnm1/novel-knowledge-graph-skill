# Canonical run, version adoption, and concurrency

## One run per book edition

Resolve a stable `book_id` from title/edition plus source lineage. Treat the full source hash as a revision fingerprint, not the permanent run identity: appending later chapters to the same edition reuses the canonical run. A materially different edition, translation, or rewritten source may use another edition ID.

Maintain a small registry entry mapping `book_id` to its canonical run directory. If legacy duplicates exist, stop automatic writes and report them for reconciliation; do not create another run.

Resolve before every initialize/continue/backfill task. Use the same explicit IDs even when the source file grows or the prompt requests a different chapter range:

```powershell
python scripts/resolve_run.py --source <novel.txt> --runs-root <runs> --book-id <stable-book-id> --edition <edition-id>
```

Acquire `--claim --owner <task-id>` only immediately before merge/publish, then `--release` after the atomic transaction. Workers analyzing chapters do not claim the run.

## Use the current Skill

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

## Short merge lock

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

## Minimal run-local task configuration

Run-local worker configuration contains only book-specific values:

- `book_id`, edition/source paths, and source revision;
- requested/covered chapter range;
- language and display vocabulary;
- user inclusion rules and explicit overrides;
- canonical run/staging paths and base snapshot ID.

Schema fields, extraction rules, validators, and visualization contracts come from the current Skill through `reference-routing.json`. Do not copy the shared TASK-SPEC template into a run as a long-lived authority.
