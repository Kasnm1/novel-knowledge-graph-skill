# Authoring a fragment with a generator script

Read this before writing a fragment by hand. Hand-written JSON for a 100+-field
document fails in ways that cost more time to diagnose than the script costs to
write. Measured on `runs/我的狐仙老婆-full/`: one hand-written fragment produced
**three** JSON parse failures and **four** quote defects; the two fragments built
with the script below produced **zero** of either.

The defects are not random — they are all the same two mistakes, and the script
makes both impossible:

| defect | how it appeared | why a script prevents it |
|---|---|---|
| a bare `"` after a numeric value | `"chapter": 538"` — twice in one file | the script never emits JSON by hand; `json.dump` does |
| one extra `}` closing a long prose string | each `romance_routes[].notes` ended `"…" } },` | same |
| a quote that is not in the source | `而慕容蝶…` where the source reads `而那慕容蝶…` | the anchor helper **aborts** on a miss |
| a quote spliced from two sentences | a closing `”` appended where the source continues | the helper only emits a contiguous slice |

The last two matter most: `TASK-SPEC` §〇 requires verbatim quotes, and
`resolve_evidence.py` cannot locate a spliced one — but it reports that *after*
you have finished the file, one quote at a time.

## The pattern

Write `_tmp_gen_fNN.py` next to the run. It loads the chapter text, defines one
helper per record kind, and refuses to write if anything failed.

```python
import json, re, sys
from pathlib import Path

RUN = Path("runs/我的狐仙老婆-full")
FAIL = []          # (id, chapter, kind, detail) — aborts the run
EV = []            # evidence records, in the order the helpers were called

_cache = {}
def ctext(ch: int) -> str:
    """Chapter text with line endings normalised to \\n."""
    if ch not in _cache:
        raw = (RUN / "chapters" / f"{ch:03d}.txt").read_text(encoding="utf-8")
        _cache[ch] = raw.replace("\r\n", "\n").replace("\r", "\n")
    return _cache[ch]

def q(eid, ch, anchor, pre=0, post=0):
    """Cut one verbatim, single-line quote around `anchor`."""
    t = ctext(ch)
    idx = t.find(anchor)
    if idx < 0:
        FAIL.append((eid, ch, "anchor", anchor)); return eid
    seg = t[idx - pre: idx + len(anchor) + post]
    if "\n" in seg or len(seg) < 4:
        FAIL.append((eid, ch, "bad", seg)); return eid
    EV.append({"id": eid, "chapter": ch, "quote": seg})
    return eid
```

Then one helper per record kind, each taking the evidence IDs it needs:

```python
def ent(eid, etype, name, first, evs, aliases=None, extra=None): ...
def ev(eid, etype, ch, title, desc, parts, evs, extra=None): ...
def rel(rid, s, rtype, t, frm, status, evs, extra=None): ...
def sc(sid, eid, facet, action, ch, before, after, reason, evs, conf, target=None): ...
def fs(fid, label, status, planted, obs, interp, rel_ents, evs, conf): ...
def prog(fid, ch, kind, desc, evs): ...   # {id, progression:[...]} only
def ri(rid, sev, cat, desc, ch, related=None): ...
```

At the end, abort before writing, and re-verify what you wrote:

```python
if FAIL:
    for row in FAIL: print("引文失败:", row)
    sys.exit(1)

frag = { "metadata": {...}, "entities": ENT, "events": EVENTS, ... }
out = RUN / "fragments" / "fragment-66-ch541-550.json"
out.write_text(json.dumps(frag, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

# second pass: every quote must still be a verbatim substring
bad = 0
for e in EV:
    if e["quote"] not in ctext(e["chapter"]):
        print("非连续子串:", e["id"], e["quote"]); bad += 1
print(f"evidence={len(EV)} 引文失败={len(FAIL)} 二次校验失败={bad}")
sys.exit(1 if bad else 0)
```

`resolve_evidence.py` then fills `source_line_start` / `source_line_end`. Do not
pre-fill them — it **skips** records that already carry both, so a stale line
number survives an edit (see `known-gaps.md` A7).

## What the helpers should assert

Each of these has cost a round at least once:

- **The quote is a contiguous slice.** Never assemble a quote from two fragments
  of text, and never add a closing `”` the source does not have there.
- **The quote is single-line.** A quote spanning a line break breaks line-number
  resolution and reads as two quotes in the panel.
- **`len(quote) >= 4`.** Below that the gate reports `weak_quote`.
- **Aim for 15—60 characters.** Longer is trimmed by review; shorter is advisory.
  When trimming, re-cut from the anchor with a different `pre`/`post` — do not
  hand-edit the string, or you lose contiguity (this is exactly how
  `ev_f65_047` failed its first repair).
- **Record IDs carry the fragment marker** (`ev_f66_001`, `sc_f66_…`); **entity
  IDs never do** (`char_liu_yi`). A script makes this trivial to get right —
  derive the prefix from one constant.
- **Every `intimate_act` needs its own `evidence_ids`**, even though
  `required_fields.py` does not list the field. Point it at the act's own line,
  not at a neighbouring event's.
- **Every `review_issue` needs `related_ids`** (an array; `[]` is legal for a
  global issue).
- **Never re-declare an entity another fragment already declared.** Run
  `plan_reconciliation.py` before merging; if it flags a duplicate ID, rewrite
  the record as a field-level restatement with the true `first_chapter` and a
  `description` that says 「第N章已首次出场（本片为字段级重述）」.

## Checklist before handing the fragment to the pipeline

1. `python scripts/resolve_evidence.py <frag> --run-dir <run> --auto-chapter` —
   expect `定位 N 条` and no `全库找不到引文`.
2. `python scripts/check_fragment.py --fragment <frag> --graph <run>/graph.json
   --chapters-jsonl <run>/chapters.jsonl` — expect `0 error`. Warnings are
   advisory; read them.
3. `python scripts/plan_reconciliation.py --run-dir <run>` — expect no duplicate
   entity IDs and no undeclared evidence references.
4. Only then run the full pipeline. A fragment change invalidates the whole
   chain (`metadata.input_fingerprint` enforces it).
