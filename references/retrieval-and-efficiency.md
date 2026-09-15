# Retrieval, accuracy, and efficiency

Use the smallest context that contains the dependencies of the intended claim. Reduce repetition, never required evidence.

## Default retrieval

For ordinary chapter extraction, load:

- the assigned chapter/scene plus a small semantic boundary overlap;
- compact current state for named entities/items;
- unresolved references entering the range;
- candidate hits from source indexes;
- the required output fields and local gates.

Query indexes and FACTS before prose. Open exact source excerpts only for candidates that may become records, conflicts, corrections, or user-visible evidence. Store quotation text once in the evidence store and pass evidence IDs thereafter when the source fingerprint still matches.

## Automatic expansion

Expand to connected history when the claim involves:

- aliases, disguises, body sharing, clones, or identity reveals;
- possession, skills, health, knowledge, affiliation, or relationship state;
- retrospective words such as 再次、仍然、终于、原来、此前;
- an event or scene cut by a fragment boundary;
- romance/intimacy, foreshadowing payoff, or a contradiction;
- first, last, only, never, all, none, whole-book style, or another global claim.

For global/negative claims, search the declared complete range through indexes, then open candidate excerpts. If coverage remains incomplete, use a scope-qualified unknown instead of a definitive assertion.

Aliases improve recall but never authorize entity merging. Chapter order, story-world time, flashback, prophecy, and reported events remain distinct.

## Compact outputs

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

## Candidate completeness

Source-side candidate scanners intentionally over-recall. Every candidate must become a confirmed record, an explicit non-match with reason, or an unresolved issue. This is especially important for romance and intimacy because checking only existing graph events cannot detect when both an event and its detailed record were omitted.

Candidate lists are review queues, not facts. A candidate scanner must be encoding-safe and return a machine-readable unresolved count. A task may continue after advisory candidates, but it may not claim the affected category complete until all mandatory candidates are resolved.

## Performance

Prefer deterministic scripts for sorting, counting, hashing, ID lookup, range/set operations, schema checks, pagination, and view aggregation. Cache parsed chapters, indexes, evidence locators, accepted fragments, and derived views by source/schema/Skill fingerprints. Compatible Skill updates invalidate only affected cache namespaces.

Batch accepted deltas and rebuild only affected entity summaries, indexes, view pages, and timeline lanes. Full rebuild is reserved for incompatible schema/index changes, source reordering, or global identity reconciliation.

If a model packet grows too large, remove repeated prose, replace validated quotations with evidence IDs, split independent candidates, and persist a compact resume capsule. Never solve budget pressure by dropping candidates or evidence.

## Validation cost

Run cheap structural/evidence checks per fragment. Run dependency-specific checks only for changed IDs. High-risk records keep their direct-evidence and expanded-retrieval gates. Run whole-run completeness checks at publication/finalization rather than after every small fragment.
