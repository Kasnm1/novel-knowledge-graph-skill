# Internal architecture v2

The product remains one user-facing `novel-knowledge-graph` Skill and one canonical `graph.json` per book/edition. The internal implementation is modular so domain growth does not create competing fact stores or duplicated temporal logic.

## Dependency direction

```text
Skill/router
  -> extraction / validation / views / export / dashboard
       -> temporal + domain rules
            -> nkg.core.GraphRuntime
                 -> canonical graph.json
```

Derived views, checkpoints, dashboards, packets, display profiles and quality reports are disposable. They never become a second story-fact source.

## Package boundaries

- `scripts/nkg/core/`: read-only indexes, cache/provenance utilities and graph query runtime.
- `scripts/nkg/temporal/`: checkpoint/fingerprint utilities and temporal replay primitives.
- `scripts/nkg/extraction/`: context closure, retrieval escalation, dynamic chunking, resume capsules, schema slicing, state capsules, wire deltas and token telemetry.
- `scripts/nkg/validation/`: semantic invariants and accuracy-regression gates.
- `scripts/nkg/views/`: audit/quality views, entity display profiles, dual-axis story time and snapshot comparisons.
- historical top-level CLI files remain compatibility entry points while implementation moves behind these modules.

## Intelligence boundary

Deterministic code owns constraints that must be reproducible: stable IDs, references, temporal replay, evidence links, spoiler closure, provenance, cache validity, serialization, and invariant checks.

AI owns judgments whose meaning depends on the actual work: which visible attributes are important, how to summarize an entity for a reader, which presentation labels are useful, whether a narrative detail is salient, and how to phrase a derived headline. These outputs stay in derived display/context artifacts and must remain evidence/time bounded.

Do not turn semantic presentation preferences into large per-genre or per-entity-type `if/else` maps. If code cannot establish a semantic interpretation without brittle heuristics, expose the underlying evidence/state to the AI and let the AI decide or leave it unresolved.

## Performance contract

Build indexes once per graph snapshot. Code that repeatedly needs entity/event/relation/state lookup should receive a `GraphRuntime` rather than rescan top-level arrays. Long-run snapshot work may prebuild chapter checkpoints. Artifact reuse is valid only when graph/input and builder fingerprints match.

## Accuracy contract

Optimization is constrained by accuracy, not the reverse. Retrieval levels are monotonic:

- R1: local scene + semantic boundary + direct evidence.
- R2: R1 + canonical identity + aliases + prior/current temporal state + contradictions.
- R3: R2 + connected entities + relevant history + distant evidence + unresolved candidates.
- R4: complete relevant/indexed coverage for universal, negative and whole-range claims.

A token budget may trigger task splitting or a larger context window. It may not silently remove mandatory candidates, direct evidence, required history, or lower the retrieval level. Incomplete evidence produces `unresolved`, not a guess.

## Quality and provenance

Quality metrics are derived audit indicators. Evidence coverage, unresolved review work, temporal provenance gaps and invariant warnings are reported separately. Do not convert them into a probability that a story fact is true.

## Compatibility

Existing commands remain supported. New internal APIs must be deterministic and side-effect free unless the command explicitly writes an artifact. Canonical writes use atomic replacement and remain serialized by the existing run-lock/publish contract.
