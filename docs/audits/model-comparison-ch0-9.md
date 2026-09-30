# Model comparison: 逆天邪神 chapters 0–9 under audit protocol 2

Two workers audited the same ten chapters independently with the new protocol
(audit cards, ID registry, one fragment, gate to 0 errors). A third agent verified
each result blind (labelled A/B). The baseline is the existing run's records for
the same chapters, produced by the old 20-chapter-per-worker process.

- Workers: Opus 5.5 and Sonnet 5.5. Reasoning effort could not be set from this
  environment (the subagent interface selects the model only), so both ran at their
  default effort, not "Opus medium / Sonnet low" as requested.
- Verifier: Opus 5.5 (default effort), a separate instance per bundle, blind to which
  model wrote it. Every reported issue had to carry a verbatim quote; all quotes were
  confirmed to exist in the chapter text.

## Results

| | baseline (old process) | Opus 5.5 | Sonnet 5.5 |
|---|---|---|---|
| events per chapter | 2.2 | 5.3 | 7.0 |
| state changes per chapter | 4.1 | 5.9 | 10.4 |
| character traits per chapter | 1.6 | 5.1 | 6.6 |
| evidence per chapter | 19.3 | 30.3 | 51.3 |
| chapter summaries (mean length) | none | 153 chars | 188 chars |
| audit cards complete | 0 / 10 | 10 / 10 | 10 / 10 |
| characters named ≥3× in a chapter with no record | 8 | 4 | 1 |
| open recall candidates | 38 | 18 | 14 |
| non-canonical relation / event types | 3 / 3 | 0 / 0 | 0 / 0 |
| records the verifier checked | — | 254 | 370 |
| missed (major / minor) | — | 0 / 5 | 2 / 6 |
| wrong (major / minor) | — | 0 / 6 | 0 / 9 |
| wrong per record checked | — | 2.4% | 2.4% |
| gate runs before passing | — | 3 | 15 |
| tokens / tool calls / wall time | — | 278k / 31 / 17 min | 320k / 65 / 23 min |

Verification cost: 216k tokens (Opus result) and 247k tokens (Sonnet result).

## What the verifiers found

- **Sonnet, major misses (spot-checked, both real):** 萧鸿's promise to protect 萧澈 on
  the way to fetch the bride (ch3, 「迎亲路上我会全力保护少爷周全」) has no commitment
  record; and ch5 attributes mockery to 萧云海, who congratulates them 「面相温和」 — the
  mockery belongs to 萧离 and 萧博.
- **Opus, most serious (all minor):** participants listed in scenes they had left, a
  location change that did not happen (ch8), a relation change among the four elders
  not recorded (ch6), and 萧莹 missing from a chapter's roster.
- **A verifier error, on both bundles:** both verifiers counted the ch3 kiss proposal
  (「你亲我一下，我就答应」) as a wrongly recorded intimate act. The protocol requires an
  explicit intimate proposal to be recorded even when it does not happen, and the Opus
  record says so plainly. The verifier prompt should state this rule.

## Reading

1. **The protocol matters more than the model.** Both workers roughly doubled to
   tripled the baseline's depth, completed every audit card, used only canonical
   vocabularies and cut unrecorded on-stage characters from 8 to 4 and 1.
2. **Sonnet was more exhaustive, Opus more careful.** Sonnet wrote about 45% more
   records (and was checked on them) at the same wrong-record rate, but was the only
   one with major misses, and needed five times as many gate runs. Opus wrote fewer
   records with no major miss.
3. **Token use was similar.** Sonnet used slightly more tokens here because of the
   extra gate iterations; per-token prices differ between the models.
4. **Limits.** Ten chapters, one verifier instance per bundle (verifier strictness is
   not calibrated between the two), effort not controllable, and verifier judgments
   include at least one error. Treat these as indicative, not a benchmark.

## Recommendation

- Deep chapter audit: either model is viable **with the verifier loop on**; the misses
  above are exactly what one correction round fixes. Where a major miss is costly
  (identity, deaths, promises, intimate acts), prefer Opus, or keep Sonnet and verify
  with Opus.
- Verifier: keep it a different model from the extractor where possible, and add the
  "proposals are recorded" rule to `references/verifier-prompt.md`.
- Before a full-book run, measure on the ten-chapter gold set with effort controlled
  (via the API or a session where effort can be set).
