# Retrieval, efficiency and accuracy-preserving optimization

How much context a task retrieves, how caches and budgets work, and the rule that optimization never trades away accuracy.

## Retrieval levels, caching and validation cost

Use the smallest context that contains the dependencies of the intended claim. Reduce repetition, never required evidence.

### Default retrieval

For ordinary chapter extraction, load:

- the assigned chapter/scene plus a small semantic boundary overlap;
- compact current state for named entities/items;
- unresolved references entering the range;
- candidate hits from source indexes;
- the required output fields and local gates.

Query indexes and FACTS before prose. Open exact source excerpts only for candidates that may become records, conflicts, corrections, or user-visible evidence. Store quotation text once in the evidence store and pass evidence IDs thereafter when the source fingerprint still matches.

### Automatic expansion

Expand to connected history when the claim involves:

- aliases, disguises, body sharing, clones, or identity reveals;
- possession, skills, health, knowledge, affiliation, or relationship state;
- retrospective words such as 再次、仍然、终于、原来、此前;
- an event or scene cut by a fragment boundary;
- romance/intimacy, foreshadowing payoff, or a contradiction;
- first, last, only, never, all, none, whole-book style, or another global claim.

For global/negative claims, search the declared complete range through indexes, then open candidate excerpts. If coverage remains incomplete, use a scope-qualified unknown instead of a definitive assertion.

Aliases improve recall but never authorize entity merging. Chapter order, story-world time, flashback, prophecy, and reported events remain distinct.

### Compact outputs

Emit delta-only JSONL or equivalent fragment records. Do not restate unchanged entities, complete prior summaries, input chapters, or verbose reasoning. An ordinary fragment carries compact coverage metadata:

```json
{
  "range": [101, 110],
  "base_snapshot_id": "...",
  "source_fingerprint": "...",
  "candidate_counts": {"romance": 0, "intimacy": 2},
  "resolved_candidate_ids": ["..."],
  "unresolved_issue_ids": [],
  "status": "complete"
}
```

Use a full `coverage_receipt` only for high-risk confirmation, corrections, explicit audits, and global/negative conclusions. Use a run-level execution receipt only when measuring or tuning performance; do not require one sidecar per routine fragment.

### Candidate completeness

Source-side candidate scanners intentionally over-recall. Every candidate must become a confirmed record, an explicit non-match with reason, or an unresolved issue. This is especially important for romance and intimacy because checking only existing graph events cannot detect when both an event and its detailed record were omitted.

Candidate lists are review queues, not facts. A candidate scanner must be encoding-safe and return a machine-readable unresolved count. A task may continue after advisory candidates, but it may not claim the affected category complete until all mandatory candidates are resolved.

### Performance

Prefer deterministic scripts for sorting, counting, hashing, ID lookup, range/set operations, schema checks, pagination, and view aggregation. Cache parsed chapters, indexes, evidence locators, accepted fragments, and derived views by source/schema/Skill fingerprints. Compatible Skill updates invalidate only affected cache namespaces.

Batch accepted deltas and rebuild only affected entity summaries, indexes, view pages, and timeline lanes. Full rebuild is reserved for incompatible schema/index changes, source reordering, or global identity reconciliation.

If a model packet grows too large, remove repeated prose, replace validated quotations with evidence IDs, split independent candidates, and persist a compact resume capsule. Never solve budget pressure by dropping candidates or evidence.

### Validation cost

Run cheap structural/evidence checks per fragment. Run dependency-specific checks only for changed IDs. High-risk records keep their direct-evidence and expanded-retrieval gates. Run whole-run completeness checks at publication/finalization rather than after every small fragment.

## Accuracy-preserving token optimization

Token reduction is allowed only when the same accuracy/completeness gates remain satisfied. The objective is to remove repeated and irrelevant context, never evidence or unresolved work.

### Extraction packet

Use `scripts/build_extraction_packet.py` to construct model input from a chapter range. The packet builder:

1. preserves all supplied source excerpts and candidates;
2. detects directly named entities and expands a bounded relation closure;
3. chooses R1–R4 retrieval from textual/candidate risk cues;
4. builds a provenance-bearing state capsule;
5. includes relevant relations, commitments, foreshadowing and evidence pointers;
6. emits only the schema slices that the current range can need;
7. records per-part character counts and an approximate token count.

`--max-context-chars` is diagnostic. When exceeded, `budget_exceeded=true` and `truncated_for_budget=false`. Split the work or use more context; do not drop candidates or evidence.

### Escalation

R1 is sufficient only for local explicit claims. Temporal words such as 再次/仍然/终于/此前 raise the minimum to R2. Identity, secrets, promises, romance/intimacy, foreshadowing and similar cross-chapter semantics raise it to R3. First/last/only/never/all/whole-book language raises it to R4.

A caller may request a higher minimum level. It may never request a lower level than automatic risk detection requires.

### Evidence deduplication

Validated quotations live once in `evidence[]`. Routine context packets carry evidence IDs and source coordinates; open quotation text again only when confirmation, contradiction resolution, correction, audit, or user-visible evidence requires it and the source fingerprint still matches.

### State capsules

R1 keeps the latest change for each relevant facet. R2 keeps the two most recent changes. R3/R4 retain a deeper relevant history. The capsule always carries record IDs and evidence IDs so a compact state is an index into canonical facts, not a replacement fact store.

### Accuracy regression gate

Before changing retrieval/chunking/schema/context policies in production, compare a baseline and optimized result with `scripts/accuracy_regression_gate.py`. The optimized result must not lose:

- any baseline confirmed record ID;
- any high-risk/mandatory candidate;
- any evidence link supporting a retained record.

Gold fixtures should additionally test semantic field equality for identity, temporal state, romance/intimacy, mortality, commitments, item transfer, foreshadowing/payoff and negative/universal claims.

### Recommended telemetry

Record source, candidate, entity, state, relation, event, evidence and schema character counts per job. If the model/provider exposes real input/cached/output token counts, record those alongside the approximation. Use telemetry to optimize the largest repeated component; do not optimize by lowering completeness gates.
