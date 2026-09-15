# Accuracy-preserving token optimization

Token reduction is allowed only when the same accuracy/completeness gates remain satisfied. The objective is to remove repeated and irrelevant context, never evidence or unresolved work.

## Extraction packet

Use `scripts/build_extraction_packet.py` to construct model input from a chapter range. The packet builder:

1. preserves all supplied source excerpts and candidates;
2. detects directly named entities and expands a bounded relation closure;
3. chooses R1–R4 retrieval from textual/candidate risk cues;
4. builds a provenance-bearing state capsule;
5. includes relevant relations, commitments, foreshadowing and evidence pointers;
6. emits only the schema slices that the current range can need;
7. records per-part character counts and an approximate token count.

`--max-context-chars` is diagnostic. When exceeded, `budget_exceeded=true` and `truncated_for_budget=false`. Split the work or use more context; do not drop candidates or evidence.

## Escalation

R1 is sufficient only for local explicit claims. Temporal words such as 再次/仍然/终于/此前 raise the minimum to R2. Identity, secrets, promises, romance/intimacy, foreshadowing and similar cross-chapter semantics raise it to R3. First/last/only/never/all/whole-book language raises it to R4.

A caller may request a higher minimum level. It may never request a lower level than automatic risk detection requires.

## Evidence deduplication

Validated quotations live once in `evidence[]`. Routine context packets carry evidence IDs and source coordinates; open quotation text again only when confirmation, contradiction resolution, correction, audit, or user-visible evidence requires it and the source fingerprint still matches.

## State capsules

R1 keeps the latest change for each relevant facet. R2 keeps the two most recent changes. R3/R4 retain a deeper relevant history. The capsule always carries record IDs and evidence IDs so a compact state is an index into canonical facts, not a replacement fact store.

## Accuracy regression gate

Before changing retrieval/chunking/schema/context policies in production, compare a baseline and optimized result with `scripts/accuracy_regression_gate.py`. The optimized result must not lose:

- any baseline confirmed record ID;
- any high-risk/mandatory candidate;
- any evidence link supporting a retained record.

Gold fixtures should additionally test semantic field equality for identity, temporal state, romance/intimacy, mortality, commitments, item transfer, foreshadowing/payoff and negative/universal claims.

## Recommended telemetry

Record source, candidate, entity, state, relation, event, evidence and schema character counts per job. If the model/provider exposes real input/cached/output token counts, record those alongside the approximation. Use telemetry to optimize the largest repeated component; do not optimize by lowering completeness gates.
