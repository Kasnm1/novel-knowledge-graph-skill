# Dashboard view contracts index

Use these references together when changing dashboard-facing Skill behavior:

- `collection-views.md`: saved collection DSL, set operators, provenance, and multi-membership cards;
- `story-arcs.md`: inclusive chapter intervals, nested/parallel arcs, overlap interactions, and deterministic ordering;
- `overlap-and-membership.md`: shared rendering rules for entities that match several sets and chapters that belong to several arcs;
- `style-analysis.md`: evidence and uncertainty requirements for prose, narration, character speech, and behavior observations.

The graph remains the source of story facts. Collection expressions, lane layout, filters, and badges are derived views. Any new factual field or top-level record type still requires the full schema/FACTS/validator/TASK-SPEC contract update described by the main Skill instructions.

## Renderer singularity (added 2026-09-17)

`build_unified_dashboard.py` is the canonical dashboard generator. `build_dashboard.py`
remains in the tree only as the shared vocabulary/derivation source and as the
legacy renderer; **a run must publish exactly one dashboard, and it must be the
unified one.**

This rule exists because the workspace actually shipped two divergent renderers.
`runs/book-9d37baf0822f/` built `dashboard.html` with the legacy generator
(4.49 MB, no chapter-synchronized entity detail) while `build_unified_dashboard.py`
wrote a complete 21-panel page to `_udash/` that was **never promoted and never
mentioned in `RESULTS.md`**. Ten graph data faces (aliases 720, events 1159, state
changes 534, relations 823, character traits 611, item roles 177, intimate acts
362, chapter summaries 999, evidence 6168, level conversions 5) were present in
the payload and invisible to the reader. The user's report was "it doesn't show
what I want to see" — the graph was fine, the published renderer was not.

### Defects the unified generator had, and why each was silent

Every one of these exited 0 and rendered a page that looked like a code problem
but was actually a template problem:

1. **`<style>` never closed.** `TEMPLATE` opened `<style>` and lost `</style>`
   when a CSS block was patched in. The HTML parser then treated `<body>` and the
   entire 5 MB script as CSS text: `document.scripts.length === 0`,
   `document.body.innerHTML.length === 0`, **zero console errors**, and
   `typeof render === 'undefined'`. Diagnose by counting tag pairs in the emitted
   file (`raw.count(b"</style>")`), never by reading the template.
2. **`buildIndexes()` defined but never called.** `entityById`, `changesByEntity`,
   `relationsByEntity`, `traitsByEntity` and `itemRolesByItem` all stayed empty,
   so entity detail, evidence lookup and item custody were dead. The surfaced
   error (`showEntity is not defined`) pointed away from the cause.
3. **`_display_vocabulary` written by the other renderer only.** The legacy
   generator sets `graph["_display_vocabulary"]` at build time; the unified one
   only read it, so every enum printed as a raw English key (`gropping_breast`,
   `mutual`, `explicit`, `level`). Import `DEFAULT_VOCABULARY` and
   `merge_vocabulary` from `build_dashboard` — **do not fork a second vocabulary**,
   which is how `ambiguous` leaked once before.
4. **Level axis identity read from the wrong field.** `views.levels.series[].facets`
   contains only the key `level`; the real axis is the `level_axis` entity that
   `state_changes[].target_id` points at. Resolve through `record_id`, and note
   that `level_axis.attributes.档位` is an **array of objects**
   (`{名称, 说明}` / `{名称, 区间}`), while `attributes.分级` is the ladder string.

### Acceptance that would have caught all four

- Emitted-file tag balance (`<style>`/`</style>`, `<body>`/`</body>`, `<script>`/`</script>`).
- `document.scripts.length` and `document.body.innerHTML.length` > 0 before screenshotting.
- Iterate **every** tab and assert `#main.innerText.length >= 20`, so a data-zero
  panel is distinguishable from an unrendered one.
- Compare screenshot hashes across tabs: identical hashes mean the **click
  selector was wrong** (`data-p` vs `data-panel`), not that rendering failed.
- Measure slider latency **per panel**, not on one panel. The default view
  (`overview`) measured p95 28.8 ms while the 362-card `intimacy` panel measured
  p95 151 ms on the same build; a single-panel measurement reports the wrong
  verdict in either direction.

## Renderer singularity, second revision (added 2026-09-17, later the same day)

`build_atlas.py` is now the intended canonical generator; `build_unified_dashboard.py`
and `build_dashboard.py` remain in the tree as the vocabulary source
(`DEFAULT_VOCABULARY`, `merge_vocabulary`) and as legacy renderers. The rule is
unchanged — **a run publishes exactly one dashboard** — but the reader rejected the
unified build outright: dark theme, one panel behind each button, and a force-directed
graph that collapsed the cast into a grey mass. The replacement is a light,
single-page, streaming layout (three tiers plus an appendix) in which every panel is
on one scroll and the graph uses a fixed polar layout.

### The graph layout: three failures worth not repeating

1. **Coordinates under `data.x`/`data.y`.** Cytoscape's `preset` layout reads
   `position` from the *element*, not from `data`. Every node sat at the origin.
   The unit-disc coordinates were also passed as pixels, so 420 nodes occupied a
   2×2 patch; `fit: true` then zoomed that patch to the viewport, and because node
   sizes are fixed pixels the markers scaled with the coordinates, so the blob
   survived the zoom. Emit `position: {x, y}` in pixels and use
   `layout: { name: "preset", fit: false, padding: 0 }`.
2. **Both obvious ways to hand out sector angles are wrong.** Splitting the circle
   by headcount lets a narrow wedge overflow (81 organisations into a 29° wedge
   that seats 58); solving each wedge for the *smallest angle that seats its
   members* and then normalising those back onto the circle starves the small
   types — nine `level_axis` nodes asked for about a degree and were granted 0.4°,
   narrower than one label. Blend the two (geometric requirement weighted over the
   headcount share) and give small types a readability floor that **scales with
   their headcount** (`ceil(n/4)` nodes abreast, so any type keeps roughly four
   rings to work with). A fixed two-abreast floor is not enough: it buys horizontal
   room by spending radial room, and a small type has no radial room to spare.
3. **An edge guard expressed as a fraction of the sweep disappears on a narrow
   wedge.** 6% of 0.4° is 0.02°, so the last node of one type lands on the first
   node of the next. Express the guard in **slots** and convert it to degrees per
   wedge; the arc a slot occupies is roughly constant whatever the angle.

Result on `book-9d37baf0822f`: global nearest-neighbour spacing 2.3 px → **14.9 px**,
and the `level_axis` wedge 0.4° → 10.9°.

### Labels have to be tiered, or the layout fix is invisible

980 names on a 1000 px disc is the same complaint as the old overlap, wearing better
geometry. Name only the connected core by default (top ~22% by degree, plus
protagonists and every level axis); reveal a whole sector's names on legend hover, and
only past 1.35× zoom, because 354 names 20 px apart still collide. Gate both tiers:
assert that a hovered sector lights nodes, that it names **none** of them at the
default zoom, and that zooming names them all.

### Two defects that made the acceptance harness lie

- **`scheduleGraph()` short-circuited on a stale chapter number.** Re-rendering the
  graph section replaces `#cy` with a fresh empty div while `CY` and `graphChapter`
  still describe the old node, so the "already drawn" guard fired and the legend and
  canvas stayed blank until an unrelated repaint. Compare the DOM node
  (`CY.container() === host`), not a cached number.
- **`let CY` at the top level of a classic script is not on `window`.** Every
  `!!window.CY` check in the harness was therefore permanently false, and the harness
  reported "the graph never finished drawing" while the canvas sat there fully drawn.
  **A check that can never be true is worse than no check.** Export it with
  `Object.defineProperty(window, "CY", {get, set})`.

Also: the graph block is emitted through the generic `block()` helper and so carries
**no id of its own**. Anchor probes on the section id (`#graph`) or on `#cy`;
`#block-graph` is null and a probe that scrolls a null element measures an undrawn
canvas and calls it a failure.

Screenshots that the reader is asked to judge must be written **by the acceptance
script**, not taken ad-hoc during development. Two of them went stale across two
rebuilds and showed a layout that no longer existed.

## Fifth revision: the panel is a site, not a page (added 2026-09-18)

The reader asked for four things in one message, and they are one change, not four:
each subject gets **its own page**; locations and every scene get their own pages;
the sidebar stops floating and **is fixed to the left**; and the graph stops being
only a pie. The full contract set lives in `runs/<run>/dashboard-view-contracts.md`
§3; what belongs in the Skill is the reasoning that generalizes.

### Route, do not stack drawers

A single local file has no server to fall back on, so **use a hash route, not
`pushState`** — deep links survive a refresh, and the browser's own back/forward
becomes the navigation stack for free. `#/char/<id>`, `#/loc/<id>`, `#/event/<id>`,
`#/chapter/<n>`, `#/index/<kind>`. Double-state rendering: a `body.paged` class
switches between the home stream and a subject page, and the two painters are
mutually exclusive, so neither has to know the other exists.

Keep `ROUTE_TYPE` and its inverse in one place. Two mistakes cost real time here:

- **A route name can already be taken.** `ROUTE` was the romance-route index from an
  earlier round (`const SUMMARY = new Map(), ROUTE = new Map()`), and shadowing it did
  not warn — it stopped the whole script from parsing. Name route state something the
  data has not claimed.
- **`let RT` at script top level is not on `window`.** The harness read `window.RT`,
  got `''`, and reported six route failures against a page that was working
  (`pageChars = 96845`). Same lesson as `CY`, one round later. **Anything a probe must
  observe has to be exported explicitly**, or the probe measures `undefined` and calls
  it a bug.

### Four graph modes answer four questions

The pie answers "what is this world made of". It cannot answer "who is around this
person", "how did this consequence travel", or "what contains what". Ship those as
separate modes rather than more decoration on one: `sector`, `mind`, `flow`, `tree`.
Each gate asserts **its own** drawn count, not that "a graph exists" — a single
generic check would pass with three of the four modes still broken.

One outlier destroys a chain view. The longest path was 206 steps and laid out
36,668 px wide; after `fit` the other eleven chains collapsed into a hairline. Cap
chain length (`CHAIN_MAX = 14`), then re-sort, then slice.

Likewise, cap neighbour count on subject pages (`RING_CAP`). Spreading all 261
neighbours around a ring pushed the radius to 3490 px and `fit` shrank every node to
a sub-pixel dot. **Draw the readable few and list the rest as text** — drawing less
is not the same as losing information. Turn edge labels off by default for the same
reason; 261 rotated labels are not readable at any zoom.

### Name placement: rank is not a place

The reader asked for labels **directly below the node, not overlapping**. Adding a
geometric pass was not optional: ranking by degree alone put the top 45 names inside
the same 132° wedge, because degree correlates with where the layout clusters them.
"Take the top N by weight" silently degrades into "take whatever shares a location"
whenever nothing checks the destination. Measured 50 overlapping pairs of 63 labelled
names; after a greedy `chairs`/`fits` pass over candidate positions, **0**.

Use two box sizes and say why: the at-rest pass runs while the node array is being
built, **before any Cytoscape instance exists**, so its collision box must be a
constant; the hover/zoom pass runs after, so it can measure
`renderedBoundingBox({includeLabels:true})` and account for labels that wrap. A
shared constant underestimates wrapped labels; a shared measurement cannot run at all
in the first pass. Bind the `zoom` listener inside `ready()` — registering it at the
top of `wire()` reads `CY` before it exists and never fires.

### Clear every layer on mode switch

`CY.destroy()` does not clear a sibling SVG that a layout painted into. Switching away
from the sector view left eight coloured wedges sitting on top of the new mode. Clear
the container **and** every side-channel layer at the top of the build, not at the
bottom of each branch.

### Let the sidebar be a column

Floating panels cover the thing the reader is reading. Make it `position: fixed` and
reserve its width with **`margin-left` on the content**, never
`padding-left` + `margin: 0 auto` — that double-counts the width (the padding pushes
content right, then auto-centring re-centres the padded box), leaving the right edge
empty. Assert `mainLeft - sideRight > 0`, i.e. the two do not overlap.

Counts in a rebuilt list need their own staleness guard. Assert that **every** target
exists in the live list (`dangling: []`, `missing: []`) rather than comparing row
counts: a rebuilt list legitimately contains group headings, so count equality is the
wrong invariant.

## Sixth revision: classify an index, and let shape carry type (added 2026-09-18)

The reader looked at the finished five-round site and reported two things:

> An index page has no classification, everything is just laid flat. And characters,
> items, places and so on should not all be circles.

Both are the same failure wearing two hats: **the page had all the information and no
handhold for finding any of it.** The location index showed 113 cards in one untitled
grid — every fact present, no answer to "which pile do I look in". The graph showed 980
nodes with all eight types drawn identically.

### Choose an index axis by measured coverage, not by which field sounds like a category

This is the expensive lesson of the round. Five axes were built against the real graph
and four were rejected on the numbers:

| candidate axis | measured | verdict |
|---|---|---|
| location by city | **20 of 113 rows mention any city** | rejected — a loose regex yields 42 groups, 32 of them singletons |
| item by 品级 | 25% coverage, 25 distinct values | rejected |
| skill by 类别 | 13% coverage | rejected |
| org by 性质 | 30% coverage | rejected |
| creature by 物种 | 64% coverage, but **19 of 20 groups are singletons** | rejected — those values are *names*, not a taxonomy |
| every kind by `first_chapter` | **980/980** | adopted — eight bands of 6–26 rows each |
| character by relation count | 100% available | adopted (characters get their own axis) |

Coverage alone is necessary and **not sufficient**: the creature axis looked healthy at
64% and was worthless, because the question is not "how many rows have this field" but
"how many rows **share** a value". Measure both.

A tight-looking axis with 15% coverage produces one 90-row bucket plus twenty
one-card headings — that is the flat grid again with extra railings.

Three failure modes worth naming:

- **Prose fields are not categorical fields.** `所在地` values read "矗立川江旁的山",
  "黑龙会／御前家族" — the field exists, the category does not. The city axis was
  attempted three ways (attribute-first: 42 groups/32 singletons; summary-first with a
  prefix filter: the 其他 bucket swallowed 105 rows; extract-then-judge: covered 5
  groups and left 100 rows unplaced) before concluding **the data does not contain this
  axis**. Forcing it only renames the flat list.
- **The 的 trap.** In Chinese prose summaries 的 is the most frequent particle and it
  appears inside almost every *prefix* ("秦朝毕业后落脚的北方城市"). Splitting on it to
  extract a place name returns an adjectival prefix. Worse: the legitimacy test was
  being run on the whole summary instead of on the extracted token — the check pointed
  at the wrong object.
- **A group of one is a heading with a card under it.** That is a table of contents
  pretending to be a classification. Fold any name only one row uses back into 其他
  (`MIN_GROUP = 2`), so the group count reports how many *categories* the data supports
  rather than how many distinct strings it contains.

**Group order follows the axis's own semantics, not group size.** Chronological bands
sort by chapter with `numeric: true` (otherwise 第 497 章 precedes 第 249 章). Cast bands
sort `主要人物 → 次要人物 → 过场人物` — sorting by size puts the 207 walk-ons first and
makes the reader scroll past everyone who does not matter to reach the 44 who do. The
axis *is* the ordering.

### Shape carries the entity type

Colour alone fails the two readers who need it most: the one with a colour-vision
deficiency and the one who printed the page in black and white. Shape is a redundant
encoding, and the assignment should be a small diagram of what the type *is* —
character `ellipse` (a person is a dot), location `round-rectangle` (a bounded area),
organization `hexagon` (a body with members), creature `diamond` (not human, pointed),
item `tag`, skill `pentagon`, concept `rectangle`, level_axis `barrel`.

Two rules that make it hold up:

- **Shape is fixed per type and never varies by chapter.** A reader who learned
  "hexagon means 势力" at chapter 100 must still be right at chapter 900. Only position
  and emphasis change over time. A type whose nodes disagree among themselves turns the
  legend into a lie, so gate on it: assert at least two distinct shapes and **no type
  with mixed shapes**.
- **The legend must draw the real shape.** Swatches become inline SVG (`shapeSwatch()`
  with a small path table), not coloured dots. A legend that draws a circle while the
  canvas draws hexagons is *worse than no legend* — it teaches the reader something
  false. In the disabled state, stroke the shape instead of filling it so the outline
  still reads.

### Gate on "grouped", and on "grouped correctly"

Asserting only that `.ix-group` exists lets a bad axis through. The gate needs all
four: group count ≥ 2; **every group has ≥ 2 cards**; the per-group card counts sum to
the page total (no card outside a group); and, when groups > 3, the jump list has one
link per group. Measured on the reference graph: `char=3g/425c loc=8g/113c org=8g/81c
creature=8g/33c axis=4g/9c item=8g/111c skill=8g/103c concept=8g/105c`, with zero
singleton groups outside the chronological bands.

Every number in a report has to be re-read from the artifact at write time, **not
recalled from the previous round**. Two of them here were: the perf figures were one
run stale (65.0/73.7 written where the re-run measured 64.1/75.0) and the byte count
came from memory rather than `os.path.getsize`.

The exemption for chronological bands must be **principled, not a threshold**: the
band bounds are fixed in advance, so a band holding one row is a true statement about
the story (nothing else appeared in those 125 chapters), and chronological bands are
dense enough that they cannot manufacture the sparse singletons a weak field produces.
An earlier draft used `rows < 32` as the escape hatch and the creature index (33 rows,
one singleton band) failed it — a magic number is not a reason.

## Seventh revision: verify what is painted, not what is configured (added 2026-09-18)

The sixth revision shipped a shape channel and a classification for the index pages, and
both were signed off against gates that read **style strings**. A screenshot taken at the
default zoom then showed the truth: every node was the same grey, at 6-7px, and the shapes
were indistinguishable. Four separate defects, none of which any assertion could see.

### The check that would have caught all four

`CY.nodes()[].style("shape")` returns the *intent*. `renderedWidth()` returns the *pixels*.
`pstyle('background-color').value` returns the *numbers the renderer will paint with*.
Only the last two can fail when the feature is broken, because a style string is correct
the moment you write it down — it is a statement about the source, not about the screen.

So every visual property needs its assertion on the rendered side:

| property | wrong (configured) | right (rendered) |
|---|---|---|
| node size | `style("width") == "11px"` | `renderedWidth() >= 10` |
| node colour | `style("background-color")` is a CSS var | `pstyle("background-color").value` is not the fallback |
| shape | `style("shape") == "hexagon"` | plus the size floor that makes a hexagon resolvable |
| card text | `.sm` element exists | the values are *distinct across rows* |

### Cytoscape does not resolve CSS custom properties

This is the one that had been silently wrong since the palette was centralized. Node style
said `"background-color": ele => ZONE_COLOR(ele.data("zone"))`. Cytoscape could not parse it and
fell back to `rgb(153,153,153)` for **all 640 nodes** — while the legend swatches beside the
canvas, which go through the DOM, rendered the correct colours. The legend and the canvas
disagreed, which is worse than having no legend.

Keep the custom property as the single source of truth, but resolve it before handing it to
the renderer, and cache the result — a `getComputedStyle` call inside the element-building
loop is in the measured frame budget.

```js
function ZONE_RGB(t){
  const v = getComputedStyle(document.documentElement)
    .getPropertyValue(`--type-${t}`).trim().replace(/^['"]|['"]$/g, "");
  return /^#([0-9a-f]{3}|[0-9a-f]{6})$|^(rgb|hsl)a?\(/i.test(v) ? v : "#6b7280";
}
```

Note the `replace(/^['"]|['"]$/g, "")`: a custom property can come back quoted, and a
quoted hex is exactly the kind of near-miss that parses as "some string" and paints as grey.
And the deliberate fallback is a *palette* colour rather than the renderer's default, so a
type that forgot its token is visibly grey-on-purpose rather than grey-by-accident.

### A floor under the marker size, chosen from the seat pitch

The shape channel was invisible because the markers were 5.5-8.3px. At 7px a hexagon, a
diamond, a tag, a pentagon and a rectangle are the same seven pixels. The band was widened
to 11-16px — and the upper bound was not guessed either. Seat pitch on this graph is 0.0549
unit-disc units against a ~686px container, i.e. **neighbouring seats are 37.7px apart**, so
a 16px marker keeps a 2.3x clearance. The old floor was using under a fifth of the room the
layout had already reserved. Gate both bounds: a fix that trades illegibly-small nodes for
overcrowded-large ones has fixed nothing.

### A line that is the same on every card is not information

The index cards' second line was "N 条关系". Measured: 0 relations on 94% of locations, 100%
of level axes, 89% of skills, 85% of concepts. 106 of 113 cards carried a byte-identical
line while *looking* populated. Replace it with the field that is both universal and
specific — `summary` — and keep the relation count only where it is non-zero, where it
actually discriminates.

When the field is genuinely absent (2 of 9 level axes have an empty `summary`), fall back to
another field the extraction *did* fill before printing a blank row. Those two axes store
their ladder in `attributes` (`第一层`..`第四层`, `下忍`/`中忍`/`上忍`). Reading a second
filled field is not synthesising content; printing a blank row and letting the reader
conclude the entry is empty *is* a fabrication of a different kind.

The gate asserts **coverage and distinctness together**, because either alone is passable by
a useless line: a field present on every card but identical across them is decoration, and a
perfectly specific field present on 15% of cards is a half-filled page.

### Say what the page does not contain

Of 823 relations, 697 have a character at one end. Per-entity averages: 2.97 for characters,
3.28 for organizations, but **0.07 for locations, 0.14 for skills, 0.21 for concepts**. A
reader opening the location index sees 113 subjects with almost no edges and concludes the
panel is broken. It is not — the extraction recorded those subjects through `summary` and
`item_roles` rather than `relations`.

So the page states the limitation, computed from the live projection rather than
hand-written, and follows the run's standing rule: an unresolved state is registered as
unresolved rather than left looking like a settled fact. The difference is between "this
place has no connections" (false) and "this panel does not draw connections for this kind"
(true).

One trap worth recording: the first version of that measurement read `S.rels` / `S.ent`, and
`S` has neither key. Both fell through `|| []`, the average came out 0.0 for every type, and
every index page — characters included — would have claimed its type has no relations.
**`|| []` turns a typo into a confident wrong answer.** Nothing failed, because an empty
iteration is a legal value.


## Eighth revision: an empty field is not an empty record (added 2026-09-18)

The previous revision closed with a statement that was too strong, and this one exists
because that statement cost a round. It said the sparse relation graph was an extraction
gap the renderer could not address. That was written after checking **one** field.

### The symptom: a page that contradicts its own summary

A location page read:

> 奥西村 · 玛门帝国边境的平民恶魔村落，法朵与森普的故乡。西瓦·法尔蓝为报复秦朝，以黑焰召火焰兽将全村焚毁成废墟。

and directly below it:

> 参与剧情 0 · 图谱中没有记录到相关剧情。

The summary names an event, three entities and a cause. The section beneath it asserts
nothing was recorded. Both strings were generated by the same build.

### The cause: one field read, its emptiness reported as absence

`eventsFor()` filtered on `participant_ids` alone. MEASURED against the event bodies
(`title` + `description`), counting entities whose name appears literally:

| type | entities | listed as participant | **named in text only** |
|---|---:|---:|---:|
| character | 425 | 3883 | 788 |
| organization | 81 | 35 | 602 |
| skill | 103 | **0** | **658** |
| item | 111 | 16 | 548 |
| concept | 105 | 20 | 522 |
| location | 113 | **0** | **323** |
| creature | 33 | 48 | 133 |
| level_axis | 9 | **0** | 3 |

764 of 1159 events (66%) name a sparse-type entity that is not in `participant_ids`.

### The rule

**A field being empty is not a fact about the record. Before rendering "no record", ask
whether the claim rests on a second field — or only on the one you happened to read.**

And the corollary, which is the harder half: **before writing "cannot be fixed", enumerate
every field that could carry the information.** The previous revision generalised from one
field to "the renderer cannot help here", and that error survived a whole round because it
was written in a document rather than asserted by a gate. An over-strong conclusion is
itself a defect, and gate 35 cannot catch it — only the habit of enumerating can.

### The fix: a second channel, kept separate

`MENTIONS` is built once at index time: entity name plus every alias, **longest name
first** so `奥西·法尔蓝` is not pre-empted by `奥西村` inside the same string, matched
literally against event text, then **minus anything already in `participant_ids`**.

Three constraints, recorded so a later round does not "simplify" them away:

- **Do not merge the two lists.** "Was there" and "was named in the account of it" are
  different evidence strengths, and this workspace's whole contract is that a reader can
  tell claims apart.
- **Show it only when it carries information gain.** The threshold is
  `mentions > participantEvents`. A protagonist with 1043 participations does not get the
  section; a location with 0 participations and 3 mentions gets nothing else.
- **A mention row must carry the participants, as links.** A list of titles with no
  people is still a dead end — the reader has to open each event to learn who it was about.

### Two assertions, not one

Gate 34 checks the channel exists and every chip carries `data-goto`, and every row links
to an event page (measured: `dead == 0`, `badRoute == 0` across 129 chips).
Gate 35 drives a real click and reads the drawer title (measured: `char_qin_chao`,
drawer 80,661 chars).

They are separate on purpose. **"Present" and "correct" are two different failures.** The
first version of the row put `entityHref(id)` — a hash route — into `data-goto`, while the
handler resolves that attribute against `ENT`:

```js
const gotoEl = t.closest("[data-goto]");
if (gotoEl){ openDrawerLink(gotoEl.dataset.goto); return; }
```

A route looked up in an id map finds nothing and opens an empty drawer. Gate 34 alone would
have passed 129 impeccably attributed chips that all lead nowhere. A chip that renders as a
name and goes nowhere is worse than no chip, because it spends the reader's trust.


## Ninth revision: an inference needs an audit trail, not a green light (added 2026-09-18)

The eighth revision added a channel that infers a connection from a literal string match.
It shipped with two gates and both passed. Then I hand-read 30 matches with their context
and found **10% plainly wrong**:

- a concept credited by the alias 土系至宝 when the text meant a hand item;
- 姬媛媛 credited by the bare title 长老 on all 15 events containing that word, including
  one about 长老龙子羽, a different person;
- 残心剑阵 claimed by both a skill and an item at once.

Every gate passed throughout. Gates 34 and 35 asked whether the section rendered and
whether its chips led anywhere. **Neither asked whether the inference was any good**, and no
gate could have: a substring hit and a real hit print identically.

### What the fix had to be, and the fix I first wrote

First attempt: drop any name that is a proper substring of another entity's name. That cost
秦朝 all 33 of its matches — because 秦朝 is a substring of 秦朝家, 秦朝的母亲, 秦朝住的出租屋.

The error was treating a **positional** ambiguity as a **global** one. The name 秦朝 is
unambiguous; only particular occurrences are contested. The rule that works is per
occurrence:

> Walk names longest-first. Claim the text span on each match. A name counts only those
> occurrences no longer name has already claimed.

`秦朝家` eats the span inside 秦朝家; a standalone 秦朝 still counts. 秦朝 keeps 33, the
false positives disappear.

### Titles are not names

姬媛媛 carried 「长老」 as an alias. A title has no referent on its own, so matching on one
manufactures evidence. `TITLE_WORDS` skips them outright.

This was the second attempt. The first assumed longest-name-first would handle it, on the
strength of a Python simulation that showed zero title hits. **The simulation was not the
shipped rule** — it did an extra cross-entity arbitration the renderer did not. The
lesson generalises: **whatever a simulation does that the implementation does not is
exactly where the implementation will fail.**

### Assert what the reader needs to judge

A machine cannot decide whether a match is correct. So gate 36 asserts the three things a
reader needs in order to decide for themselves:

- no row matches on a bare title word;
- every row states the literal name it matched (`withVia == rows`);
- a name shared between entities is flagged as shared.

Measured: `84/84` rows carry provenance, `titleHits` empty, `81` flagged as shared.

### And a gate that cannot fail is not a gate

The first version of gate 36 measured one subject, 奥西村, whose name has no multi-owner
collision. `sharedMarked` was therefore structurally 0 and the shared-name assertion could
never have fired. It now scans four subjects including the canonical collision
(`skill_canxin_zhenjian` / `item_canxin_zhenjian_mujian`).

**Before trusting a new gate, ask what it would take for it to fail.** If the answer is
"nothing I can construct", it is decoration.

## Tenth revision — a lifetime is a set of intervals, and you have to find every field first

`relActive()` asked one field, `valid_to`, whether a relation was still live:

```js
const relActive = (r, c) => ...
  && (N(r.valid_to) == null || r.valid_to === 0 || r.valid_to >= c);
```

One relation in 823 records its end elsewhere:

```
rel_f01_016  罗德 possesses 秦朝
  valid_from: 1   end_chapter: 1   status: active   valid_to: (absent)
  observations[]: ch1 ended · ch322 active
```

With `valid_to` absent the guard passed at every chapter, so the page drew the possession as
live across all 400 chapters while the data said its first episode ended at chapter 1.
Rendered proof: `relActive(r, c)` returned `true` at c = 1, 2, 100, 321, 322, 400.

Nothing caught it because every gate asked whether a relation was *drawn*, and none asked
*where its end is written*. The same defect class had already been catalogued for the previous
renderer generation — but the fix went into the **merger**, not the renderer, so it survived
here under a different field name.

### The first fix was wrong, and the wrongness was informative

Reading `end_chapter` into a single `relEnd()` made `rel_f01_016` live only at chapter 1 —
and hid the genuine second episode (chapters 322 onwards) for the last 80 chapters of the book.
The top-level `end_chapter: 1` summarises **the first episode**, not the relation.

The correct model is a set of intervals:

- when `observations[]` exist, **they are the intervals**; the top-level scalars are a summary
  of the first one and must not be applied across an episode boundary;
- an episode with no explicit end is closed by **the start of the next episode** — for
  `rel_f01_016` that boundary is the only statement of where episode one ends;
- only the final episode may run to the end of the book;
- a single top-level span is the whole story only when there are no observations at all.

### Regression discipline for a semantics change

Comparing old and new `relActive` across all 823 relations at c ∈ {1, 50, 100, 200, 300, 400}
gives **zero differences**. The change is a strict generalisation: it reads more fields and
evaluates per episode, without altering any answer the build previously produced. The old
behaviour was correct for this record by coincidence of field choice, not by construction.

### The gate for it was also wrong first

Gate 37 v1 compared the shipped predicate against a naive `valid_to`-only one and demanded
they differ somewhere. It cannot fail: the *union* of `rel_f01_016`'s two intervals is
`[1, ∞)`, which is exactly what the naive reading yields. Deliberately downgrading the
predicate to the buggy version left `naiveDiffers` at 0 — the attempt to falsify the gate
falsified the gate instead.

The rewrite asserts the discriminating observable: a relation naming its end only in
`end_chapter` must not resolve to one open interval, and observations-bearing relations must
yield more than one interval. Downgrade test now fires: `intervals` 2→1, `firstTo` 322→null,
`ignored` false→true.

Measured on the shipped build: `relations=823 endChapter=1 obs=823 multiIv=110 bounded=147
holes=0`, `rel_f01_016: end=0 open=True liveAt400=True`.

**Three rounds, three fake gates** (36, then 37). "Ask what it would take for this gate to
fail" is not satisfied by reading the assertion back — it has to be executed, by breaking the
code the gate guards and confirming the gate goes red.

## Eleventh revision — a control that looks like one, a rail that describes another page, and a probe that lied about both

The complaint was three sentences: *"单独人物的信息栏，分类没做好，然后左侧还有很多点不了。再者，可视化没做出我想要的集合效果"* — the detail panel is badly classified, the left column has dead
elements, and the graph does not show who belongs with whom.

### What the numbers said

| complaint | measurement | finding |
|---|---|---|
| classification | 秦朝 page = 96,845 chars | **80,542 (83%)** was one unclassified "complete archive" blob; `参与剧情 1043 → 40 shown`, `关系 276 → 158 shown` |
| dead elements | 8 elements look like controls | 4 group headings, 2 section headings, a hint, a badge — all inert |
| grouping | 640 nodes | connectivity weight **0**; label propagation separates real social circles |

### The three fixes

- **Grouping** → weak components + label propagation. `74 circles / 500 members / 480 isolated
  / 19 components / giant 456`. Names are real: `秦朝 · 罗德 · 陈四 112`,
  `黑龙会 · 御前千代 · 安晴家族 28`. Rendered: `offCanvas=0 inner=547 bridge=276 rings=75`.
  A one-person circle is **structurally impossible** — every linked node adopts a neighbour's
  label — so the "isolated spine" branch was dead code.
- **Classification** → 8 anchored sections + sticky table of contents + 16 fold buttons.
  TOC click gives `scrollY 0 → 20396` with **hash unchanged**.
- **Dead elements** → folding, an up-trail, and more buttons. `kinds 9→0→9`, `chapters 20→0→20`,
  `rail 17→12→17`, breadcrumb `总览 › 人物 › 秦朝` walks back level by level, `↑ 顶部` `6000 → 0`.

### The rail has two halves, and that is the whole story

`#rail` describes two different things at once: the **page half** (the current route's
sections) and the **mirrored half** (the sections of whatever subject is open in the drawer).
They share **one** `rail.dataset.sig`.

Every defect in this revision came out of that sharing:

- **Two write sites.** The signature claimed one thing while `innerHTML` held another — PAGE
  signature over the previous route's seventeen home rows. Once in that state **every later
  pass agreed the rail was already correct**, so even calling `buildRail()` by hand could not
  recover it. Fix: `mirrorDrawer()` is the only place that writes.
- **Signature from the caller.** The guard compared the caller's idea of the page half against
  whatever the last write happened to leave, and skipped a write that had never happened. Fix:
  the signature is a **function of the markup about to be written**, plus a
  `rail.innerHTML === markup` belt.
- **`|| html` never fires.** The paged branch passed `trimMirror(rail.innerHTML) || html`;
  `rail.innerHTML` is non-empty on arrival, so the stale markup was written back under a fresh
  signature. Fix: pass the `html` just derived from this page's own sections.
- **`wireRail()` had zero call sites.** The heading kept its pointer cursor, looked like a
  control, and answered a click with nothing. Fix: the binding lives inside `buildRail()`.
- **Boot order.** `setChapter(MAX_CH, true)` ran *before* `applyRoute()`, but `applyRoute()` is
  what sets `body.paged` and `setChapter()` reads it to choose between repainting the page and
  repainting the stream — so a deep link always took the stream branch and filled the rail with
  home rows. Fix: `applyRoute()` first, and `setChapter()` reads `RT.view` rather than
  `body.paged` (which means "did `applyRoute` run", not "is the reader on a page").
- **`data-entity` means two things.** Inside the drawer it swaps the panel; on a page it opens
  that subject's own page. Binding every `[data-entity]` to `showEntity()` meant page cards
  re-pointed the side panel and never navigated. The alias chips were `href="#"`, so a click
  pushed an empty hash, the router read it as "no route", and the reader was thrown back to the
  overview.
- **A `<b>` that looks clickable.** The breadcrumb's last segment is now a real button.

### Gate 39 was reporting four false positives, and they were its own

The probe had been saying "these rows answer a click with nothing" for several rounds. All four
were the probe's fault, and each is a reusable lesson:

1. **A wrapper is not a control.** `#side-tree>*` and `#rail>*` exist to catch a row demoted
   from a button to a plain element — and a demoted row has no children. But the wrappers
   around the rows match the same arms, and their `innerText` is the concatenation of everything
   below (`人物425  地点113`, `1234567…`). Two container arms, two concatenations, two reported
   defects that did not exist.
2. **Stale element references.** A click that navigates or collapses rebuilds `#side-tree` and
   `#rail`; every later reference in a snapshot-then-iterate list then points at a **detached**
   node, and `click()` on a detached button fires no delegated handler. Eight working rail rows
   were reported broken this way. Collecting **by label** and re-resolving at click time fixed
   it — and revealed that the gate had been clicking **7** controls while claiming to check the
   sidebar. After the fix: **201**.
3. **Cross-check state leakage.** `RAIL_COLLAPSED` is a module-level set and survives
   navigation. After gate 39 clicked the rail's group heading, gate 41 saw a collapsed rail on
   every route and reported `the page has 8 sections but the rail lists none of them`. Each
   check now establishes its own clean start.
4. **Already at the destination.** A row pointing at the page's last block scrolls to the
   maximum offset; if the viewport is already there, `window.scrollY` cannot see the change.
   That is the control **working**. The probe now backs off 700px first, the same reasoning it
   already applied to the "top" button.

The signature also had to grow: it sampled the page and the route but not the rail's own
disclosure state, so collapsing a group — which deliberately changes nothing else — read as
inert.

### Gate 41, and the downgrade test that makes it real

New check: the rail must describe the page the reader is looking at, and its rows must move the
viewport. Both section shapes count (`section.pblock[id]` **and** `section.ix-group[id]`) —
matching only the first rejected a correct rail on `#/index/<kind>`, whose rows point at `ixg-*`.

Then the part that cannot be skipped: the paged branch of `buildRail()` was replaced with a bare
`return`, the build was redone, and the gate went red exactly as designed —
`the page has 8 sections but the rail lists none of them — it is describing some other page`,
with the diagnostic showing `railHead` fallen back to the home stream's `T1` group. The code was
restored and `DEGRADED` verified absent (`grep -c` → 0).

Final state: **ALL CHECKS PASS**, 41 gates, `sidebar click: tested=201 inert=[]`.

**A number that is only printed is not a gate.** Gate 39 printed `tested=7` for rounds without
anyone noticing the sidebar has 52 rows. The count only became visible when the probe stopped
lying about which elements it had clicked.

## Twelfth revision — "nothing on this page is clickable", and the gate that could not see it (added 2026-09-18/19)

The reader's words: *"nothing on this page is clickable, fix it — and there are probably a lot of
pages like this one."* The screenshot was `#/chapter/251`.

### Scan every route before touching the one that was reported

22 routes × `{view, pageLen, secs, railLen, railRows, links}`. The damage was not one page, it
was three classes:

| Route | Symptom | Blast radius |
|---|---|---|
| `#/chapter/*` | `railLen 0`, `railRows 0` | **999 pages** |
| `#/event/<id>` | `secs 0` but `railRows 4` — **the home stream's stale rows** | **1159 pages** |
| `#/index/chapter`, `#/index/event` | `pageLen 256/258`, renders 「找不到这个索引」 | every index page's jump list, every chapter breadcrumb |

Then a real click on every control, to find the actual boundary of "not clickable". The links on
a chapter page **were** clickable (no page errors, `elementFromPoint` showed nothing covering
them). What was broken was the rail — blank on chapters, stale on events — and the index pages'
jump lists, which threw the reader back to the overview.

### Seven defects

1. **`pageChapter` emitted four `section.pblock` with no id.** `#page section.pblock[id]` matched
   zero, so `buildRail()` took its "the page has not painted yet" exit and **all 999 chapter pages
   had an empty rail**. After: `railRows: 3`, labels `['石鑫的男友','本章剧情 1','登场人物 6']`.
2. **`buildRail` excluded `chapter` from paged** (`RT.view !== "home" && RT.view !== "chapter"`).
   The home branch's blocks are `display:none` under `body.paged` and measure 0×0, so it found
   nothing and wrote a blank rail. The exclusion existed only because those blocks had no id
   (defect 1) — with ids, the route belongs on the paged side.
3. **`pageEvent` emitted five `section.pblock` with no id**, so **all 1159 event pages advertised
   the previous route's seventeen home rows**, every one of which points at a `display:none`
   block. After: `['ev-facts','ev-story','ev-evidence','ev-siblings']`.
4. **`buildRail` left stale content when a paged route had no sections.** The comment said "the
   page has not painted yet", but *not painted yet* and *painted with nothing to list* are
   **indistinguishable from inside that function**, and the second is real (`pageMissing`, and any
   route whose builder emits no id). Clearing is the honest answer: an empty rail says "nothing to
   list here"; a stale one says "here is the table of contents" and lies.
5. **`#/index/chapter` and `#/index/event` were dead pages.** `pageIndex` dispatched through
   `ROUTE_ENTITY[kind]`, which holds only the eight **entity** types. New builders band by where
   in the story each record happens — the one axis every record has — and render **lines**, not
   cards: 999 chapters and 1132 events are scanned by number, not browsed by box. After:
   `rows=999 / 1132`, `railRows=8`.
6. **`.ix-jump` anchors had no `data-toc`.** A bare fragment is not "scroll to this element" to a
   hash router, it is "navigate to the route named `ixg-…`" — no match, resolves to home.
   MEASURED on `#/index/item`: `pageLen 28574 → 0`, view `index` → `home`. The handler that reads
   `data-toc` **already existed and its comment already stated this exact reason**; the jump list
   was added later and did not read it.
7. **The sidebar's 「剧情 1159」 row pointed at `#/`** (to dodge defect 5), so clicking it threw
   the reader to the overview — the same dead end as the empty rail, one level up. The breadcrumb
   parents were the same: a chapter page's 「按章回放」 was a scroll-to-top control even though
   `#/index/chapter` exists.

### Gate 41 was green because the broken pages were not in its route list

It checked exactly two routes: `#/char/char_qin_chao` and `#/index/item`. The chapter page and the
event page — **the two that got this wrong** — were not among them. Widening the list to four
immediately produced:

```
rail on #/chapter/251: clicking row `ch-summary` left the viewport at scrollY=0 — the row does nothing
```

### That one was a false positive too, and it pointed at a real problem

MEASURED: `#/chapter/251` has `scrollHeight === innerHeight === 1050` — one event, six people,
exactly one viewport, **zero scroll room**. `scrollTo` is a no-op by physics and all three
sections measured `UNREACHABLE`. The gate read `scrollY < 20` as failure and accused a correct row
on 999 chapter pages.

Before blaming the page, check the other hypothesis: measure the ten heaviest chapters (`ch1` 4
events, `ch265` 12 people, `ch443` 4 events …). `overflowY: visible`, `page.scrollHeight` tracks
content (903 / 756 / 851 / …), **nothing overflows and nothing is clipped**. The page is simply
short.

The correct assertion is "the window reached the **reachable target** `min(want, maxScroll)`".
Plus an anti-degeneration assertion: **at least two routes must actually have moved the window**,
or the whole check can pass on nothing but short pages. MEASURED `verified 3/4`
(`#/char/char_qin_chao` 21530, `#/index/item` 3531, `#/event/event_f26_001` 989;
`#/chapter/251` no room).

A third false positive came from the same family: `behavior: "smooth"` **animates**, so a single
sample after a fixed delay measures the animation, not the destination. A **9,437 px** jump on the
Qin Chao page was still **1,006 px** short after 700 ms and was reported as `the row does
nothing` — while the row was doing exactly what it should. Sampling now **polls until the position
stops changing** (two consecutive equal readings, capped at ~3 s). The `.rail-flash` check runs
*before* the poll, because the flash only lives 1.3 s.

That is probe defect class five, and it shares a root with the first four: **treating "I did not
measure it" as "it did not happen"** — substituting a proxy (displacement, a single reading) for
the target (arrival, settled value). It showed up three times in this round alone
(`scrollY < 20` as failure, the `want < 20` early exit, and fixed-delay sampling).

### The missing half of the feedback: `.rail-flash`

Fixing the gate's judgement did not fix the reader's problem. On `#/chapter/251`, clicking
「本章剧情」 changed **nothing on screen** — indistinguishable from a dead link. *No movement* is
not *no effect*, but the reader cannot tell the difference, so the difference has to be made
visible: the target block gets `.rail-flash` for 1.2 s.

```
== #/chapter/251 ==  scrollRoom=0
   ch-summary     flash=True  scrollY=0      ← the exact row the gate had accused
== #/char/char_qin_chao ==  scrollRoom=21587
   sec-changes    flash=True  scrollY=2366
```

Gate 41 gained the matching assertion (`noFlash: []`). On a page with no scroll room, this is the
**only** feedback that can be asserted at all.

### Gate 42, and a **partial** downgrade test

New gate: no in-page anchor may lack `data-toc` (the attribute half), clicking one must leave the
reader on the same route (the behavioural half), and the two non-entity index pages must render
rows, groups, and a rail that lists them.

The downgrade test is not optional, and this time it was **partial**: only `pageIndexChapters` lost
its marker, the other four sites kept theirs. A gate that only fires when everything is broken
cannot catch a single-route regression.

```
== DEGRADED build ==
   #/index/chapter   anchors= 1009 unhandled=  8  <-- BARE LINKS
   #/index/item      anchors=  121 unhandled=  0
   #/index/event     anchors= 1169 unhandled=  0
== SHIPPED build ==
   gate reports nothing
```

It named the one broken route and left the other five at zero.

### A self-inflicted wound: concurrent browsers killed the gate

The first re-run of the full suite overlapped with three of my own probes (`_d14.py` once,
`_d15.py` twice), four Chromium instances in total. The gate process was killed and its log was
**0 bytes with no output at all** — while its job was to confirm "42 gates green", so it read like
"finished, nothing to report". Two rules came out of it: **never run another browser while the
acceptance suite is running**, and run long jobs with `-u`, because "killed" and "still running"
are both blank in a buffered log.

### Three reusable lessons

1. **A gate's coverage decides what it can see.** Gate 41 was green because the two broken page
   kinds were absent from its route list. **Widening the route list was worth more than any new
   assertion.**
2. **"Not painted yet" and "painted with nothing to list" are usually indistinguishable inside the
   function that has to choose** — and when they are, keeping the old content is a lie while
   clearing is honest.
3. **A comment that states the right reason does not make later code obey it.** The `data-toc`
   handler's comment says in as many words that an in-page anchor pushes a hash the router will
   read as a route; `.ix-jump` was written afterwards and never read it. **A comment is not a
   gate.**

## Thirteenth revision — a chapter page that was a stub, and a leak scan that never left home (added 2026-09-19)

### What the chapter page was answering

Reading a chapter page is the most basic thing a reader does with this atlas, and the page
answered "what happened here" with four sections: summary, events, changes, people. On
`#/chapter/251` that produced **1,604 characters** — shorter than the viewport, which is why its
rail rows had nothing to scroll to and why the page read as a placeholder. The graph was already
carrying eight more per-chapter channels and the builder was dropping them on the floor.

### Coverage was measured before a line was rendered

The rule for choosing a **grouping axis** is "reject anything under ~50% coverage" (contract:
*choose an index axis by measured coverage*). That rule does **not** transfer to a **section**,
and getting this wrong in either direction is expensive, so the coverage was measured across all
999 chapters first:

| Per-chapter channel | Chapters with rows | Coverage |
|---|---|---|
| relation episodes | 468 | 46.8% |
| character traits | 441 | 44.1% |
| state changes | 375 | 37.5% |
| open issues | 328 | 32.8% |
| planted foreshadowing | 286 | 28.6% |
| intimacy | 267 | 26.7% |
| commitments made | 183 | 18.3% |
| item roles | 142 | 14.2% |

**Why the criterion moves.** An axis covered by 14% buries the other 86% underneath it. A
*section* covered by 14% is simply absent from 86% of pages — and that absence **is the truth
about those chapters**. A section is emitted only when it has rows, so a sparse channel costs a
chapter nothing. Measured: 3.03 new rows per chapter on average (median 3, max 18), and only
**12 chapters (1.2%)** gain nothing at all — 284, 285, 287, 296, 397, 567, 608, 644, 766, 768,
792, 816, which were thin to begin with.

The six new sections are `ch-rel`, `ch-traits`, `ch-threads`, `ch-intimate`, `ch-items` and
`ch-review`. **`ch-review` is last on purpose**: it is audit material, not story. A reader came
for the chapter; this section only says that some of what is above is uncertain, and putting it
at the end keeps it available without letting it lead.

Two constraints on the content itself:

- **Relation movement reads the intervals, never the scalar.** `relMoves` walks every episode in
  `relIntervals(r)`, because since the tenth revision a relation's lifetime is a **set** of
  intervals and the top-level `valid_from` only summarises the first one. `rel_f01_016` is the
  record that forced this: its second episode starts at 322 while the scalar says 1.
- **Consent carries the same weight as the act.** This workspace's rule is that inclusion in the
  intimacy log never implies willingness, so 「单方面」/「受迫」 are tagged at the same visual
  weight as the act rather than tucked into small grey type.

### The nav had to be an anchor, and the first version was a button

Reading is a walk, so the walk needs a next step. The sidebar's 20-cell chapter grid gets the
reader to a neighbourhood, not to the chapter after this one. So the body now leads with
`← 第 N-1 章 / 章节索引 / 第 N+1 章 →`.

**It has to be `<a href="#/chapter/N">`, not a `data-goto-chapter` button.** That attribute is
handled by `openChapterDrawer()`, which re-scrubs the page and opens a drawer **without touching
the route** — on a chapter page it repaints from `RT.n`, and `RT.n` is still the chapter the
reader is already standing on. MEASURED: clicking 「第 252 章 →」 left the hash at
`#/chapter/251` and the page unchanged. Changing the hash is what actually navigates, and an
anchor is also the honest element for "go somewhere else".

It sits at the top of the body rather than inside `.pg-title`, because that row is
`align-items: baseline` for the h1 and the tags, and a row of buttons set on a text baseline
looks broken. It is a bare `div`, not a `section.pblock`, so the rail does not list it.

### The leak scan had never seen a chapter page

The leak scan near the top of the acceptance suite evaluates `document.body.innerText` on `#/`
and **never navigates**. So neither `LEAK_KEYS` nor the snake_case regex had ever seen a chapter
page. MEASURED: five dangling ids reached readers — `item_xiewang_jian` on `#/chapter/322`,
`item_huazhuang_he` on `#/chapter/375`, and `char_ding_lei` / `item_chuangguo_yuoxi` /
`org_jinxing_baoan` on `#/chapter/631` — while the suite stayed green.

They came from `review_issues[].description`, which cites the ids it reconciled against
(「旧表记方雯（char_fang_wen）首见第 11 章…」). `resolveIds()` substitutes an id it knows and
**leaves one it does not**, which is right for prose but wrong here: these five are precisely the
ids the audit could not place, which is *why* the issue citing them exists. So the reader got
`（char_ding_lei）` printed into a Chinese sentence.

This is the twelfth revision's first lesson recurring verbatim: **a gate's coverage decides what
it can see.** That round widened gate 41's route list; this round had to widen the leak scan's.

### `issueText`: resolve first, then drop

The order matters. Resolving first lets a citation whose entity still exists **collapse into the
name already sitting in front of it** — 「方雯（char_fang_wen）」 becomes 「方雯」 rather than
「方雯（方雯）」. Only then are the dead ones dropped. An id is a fact about the extraction, not
about the story, so dropping the citation keeps the sentence.

One implementation trap: a single issue cites
「金刚经（item_jingang_jing/skill_jingang_jing/axis_jingjing）」 — **one name, three ids** — so a
rule that expects a single id before the closing bracket leaves `（//）` behind. The pattern has to
match a *list* of ids. MEASURED over all 386 issues: `changed=283 unchanged=103 residual=0`.

### Gate 43, and what it has to assert

Two halves, both about coverage rather than cleverness:

1. **Ten sections, asserted by emission.** A gate that only checked "the page has sections" would
   stay green with every new section deleted, so the assertion is that each of the ten ids is
   emitted by *some* chapter in the sample. The sample is 19 chapters spanning the book, and it
   was measured before the gate was written: `ch-intimate` and `ch-items` appear in only 6 of
   those 19, so a narrower sample would have produced a **false positive on a channel that is
   merely rare**.
2. **The leak scan, on six route shapes.** `#/` (already covered elsewhere), a chapter page, an
   entity page, an event page, an index page, a location page and a level-axis page.

Plus the behavioural half of the nav: clicking `next` / `prev` must change the route, asserted on
`location.hash` and `__atlasRoute.view`, not on the DOM — a repaint of the same chapter would
satisfy any DOM-shaped assertion.

**Downgrade test (mandatory), and it was run as a partial break.** Two breaks in one build,
because the two halves are independent assertion branches:

| Break | Reported |
|---|---|
| `ch-items` emission changed to `false &&` | that section was never emitted |
| the nav's next/prev anchors both point at the current chapter | the route did not change |

The other six new sections and the index link were left intact. Result: **exactly three failures,
one per break, with the other 42 gates silent.** Two details are worth keeping:

- The coverage assertion named **only `ch-items`** — the other nine sections were still correctly
  seen as emitted. That is what "assert per id" buys over "assert a count".
- The nav probe printed `found: True, hash: '#/chapter/251'` — the link **was there**, and the
  route did not move. A gate that only asserted "`.ch-nav a` exists" would have been **green**.

The degraded artifact is built by byte-exact copy and substitution (`read_bytes` / `write_bytes`):
`read_text` / `write_text` rewrites LF as CRLF on Windows and added **6,105 bytes** — a downgrade
test has to isolate one variable. After substitution the size delta was exactly **+1** (9 added by
`false && `, 8 removed by two shorter `href`s), matching the arithmetic.

### One measured side effect, and one measurement trap

The chapter-page expansion **closed a standing gap without being aimed at it**: `#/chapter/251`
had `scrollHeight === innerHeight === 1050`, zero scroll room, so gate 41 could only verify
`.rail-flash` there and not scrolling. After the expansion the same page has **136 px** of room,
and the suite now reports `rail verified on 4/4 routes; no scroll room on []`. The gap itself
remains for genuinely thin chapters (120, 284, 820, 999 in a 19-chapter sample still have zero
room) — it is a data fact, not a defect.

The trap: this round compared a fresh `innerText.length` against a historical
`innerHTML.length` and read the mismatch as a regression. `#/chapter/1` has an `innerText` of
exactly **1,604** characters, which is also the pre-expansion `innerHTML` of `#/chapter/251` — a
coincidence that made a correct page look broken. **When you change which quantity you measure,
the old numbers stop being comparable.**

## Fourteenth revision — the event page, and a measurement that said "not this one" (added 2026-09-19)

### The assumption, and the measurement that killed it

After the chapter page turned out to be a 1,604-character stub, the obvious next move was the
event page — 1,159 of them, the same `pageEvent`-with-four-sections shape. So it was measured
before it was touched, and **the measurement said no**:

| | chapter page (before) | event page (measured) |
|---|---|---|
| rendered length, median | 1,604 | **5,047** |
| scroll room, median | 0 | **858** |
| pages with zero scroll room | most | **0 of 25** |
| rail rows vs sections | mismatched | **identical** |

The event page was never a stub. It carries four to five sections, a full participant /
location / item / same-source list, and an evidence block. **Two pages can look like the same
disease from the outside and be nothing alike inside; the judgement has to come from a
measurement, not from an analogy.**

What it *did* have was the same *shape of gap*: channels the graph carries and the builder
drops. That is a supplement, not a repair, and it was scoped as one.

### The join key was already on the page

`pageEvent` already had a 「同源记录」 card joining relations to an event by **`evidence_ids`
intersection** — "the same line of the text supports both records". Every other record type in
this graph carries `evidence_ids` too, so the same join reaches all of them with no new field
and no new inference. Measured across all 1,159 events before anything was rendered:

| channel | events joined | rows per event |
|---|---|---|
| character traits | 36.8% | 0.47 |
| state changes | 34.3% | 0.46 (already used via `cause_event_id`) |
| foreshadowing | 26.2% | 0.30 |
| intimacy | 17.3% | 0.23 |
| commitments | 15.4% | 0.16 |
| item roles | 11.8% | 0.14 |

**Union: 805 events (69.5%) gain at least one row**, 1.31 rows per event. The other 354 (30.5%)
gain nothing — and because a section is emitted only when it has rows, they are unaffected
rather than made worse.

### A tight join, on purpose

The join matches on the exact evidence id and nothing else. A looser join is available and
tempting: same chapter, or same participant set. Both would attach a character's trait to
**every scene they appear in**, which is not what the record says — the record says the trait
was observed *at that line*. **A join that is merely plausible is not a join that is correct**,
and the distinction only shows up when you read the rows it produces.

### `ev.location_id`: a field nobody read

496 of 1,159 events (42.8%) record where they happened. The builder never read the field: it
derived a location from each participant's state, which yields nothing for a scene whose actors
have no location on record — precisely the crowd scenes. The recorded field now leads and the
derived rows follow, so a page can show both without conflating them.

This is the eighth revision's lesson in a new place: **an empty field is not an empty record,
but neither is a populated field a read field.** The value was there the whole time.

### The nav, and the ordering that makes it possible

Events get the same previous/next treatment as chapters, which needs a book order. MEASURED:
sorting the 1,159 events by `id` alone leaves only **2 adjacent chapter inversions**, so the id
carries book order almost exactly — but `chapter` is still the primary key, because those 2
exist. The controls are `<a href="#/event/ID">`, for the reason in the thirteenth revision:
`data-goto-chapter`-style controls repaint without touching the route, which on a page that
already shows that record is a no-op.

### Gate 44

Asserted per section id across a 40-event sample, not as a count — a gate that checked "the
page has sections" would stay green with all four new ones deleted. Plus: the recorded-location
row must appear on at least one sampled page (42.8% of events carry the field, so its absence
means the join broke, not that the data is thin), and next/prev must change the route, asserted
on `location.hash` and `__atlasRoute.view`.

**Downgrade test:** see `RESULTS.md`.

## Fifteenth revision — two true causes behind one word ("crash"), and a gate that failed for being right (added 2026-09-22)

### One symptom, two unrelated causes

The suite died reproducibly with `Page.evaluate: Target crashed`, a frozen log, and no
traceback — and a build from the *unchanged* baseline died the same way. That made it look
as if the existing "44 gates, ALL CHECKS PASS" had never been reproducible. It was two
independent problems, and the word "crash" reported them as one.

### Cause A: a loop keyed on display text

```js
const el = snap().find(e => !done.has(labelOf(e)));   // the key contains a count
```

The sidebar renders `人物 340` and `剧情 957`; chapter cells render `18` / `19`.
**Clicking a chapter cell changes the chapter, which changes every count in the tree**, so
`人物 340` becomes `人物 359` becomes `人物 378` and `done.has()` is false forever. The
per-click log shows **186 rounds clicking 186 mutually distinct labels**; the only bound was
`rounds < 400` at ~2.5 s each — **about 17 minutes**. Two of the three "crashes" were this
loop still running when the harness gave up.

The fix is to strip the count before comparing, because a count is display text, not identity:

```js
const keyOf = el => labelOf(el).replace(/\s*\d[\d,]*\s*$/, '').trim() || labelOf(el);
```

MEASURED: same start state (sector, CY=640) went from **crashing at 107 s** to **passing in
78 s with `tested=44`**. A `hitCap` flag now asserts that a probe which stops because it ran
out of rounds is not a probe that finished — the second instance of a non-signal after
`tested=None`.

### Cause B: machine memory pressure

| moment | load | available | outcome |
|---|---|---|---|
| earlier green run | 81% | 5.9 GB | gate 39 alone, 367 s, pass |
| failing run | **94%** | **1.64 GB** | died at gate 44 |
| isolated retries | 71–84% | 5.0–9.0 GB | intermittent, **moving death point** |

A **moving** death point (gates 22 / 39 / 32 / 44 at different times) is the signature of an
external kill; a page defect dies in the same place every time. `usedJSHeapSize` stayed flat
at 21–22 MB throughout, while the Chromium tree's working set went **459 MB → 851 MB and kept
growing** — so the JS heap could never have revealed this. `accept.json` now carries a
`machine` fingerprint (time / load / total / available). **A "pass" without a record of the
environment it passed in is not a delivery guarantee.**

### `pg.evaluate` is bounded by neither timeout

`default_timeout` governs actions, `default_navigation_timeout` governs navigations, and a
long `async` in-page `evaluate` is bounded by neither — so a non-converging probe **hangs the
whole suite** instead of erroring. The fix is a `guarded()` wrapper that **names the case**:
`renderer died mid-probe` / `probe exceeded its budget` / `probe threw`.

### The tag leak: the third time a field had a value and no reader

`e.tags` sits on 9 entities and contains 5 pure-English values (`protagonist`, `antagonist`,
`minor`, `assassin`, `mokuui`), and the renderer never mentioned `e.tags`. Both leak scans
walked past it: `LEAK_KEYS` is a hand-written list that does not contain `tags`, and the
snake_case regex requires an underscore, which none of those five words has. **A field nobody
renders and a field that leaks are the same omission — if nobody reads it, nobody translates
it.** The fix is to translate and show it (`entity_tags` vocabulary, a `sec-tags` block, and
`data-tag` carrying the *raw* value so a gate can assert `shown != raw`), not to hide it.

### A gate that failed because it was right about the wrong thing

`vocab_coverage` was extended with an `entity_tags` group, and the full run reported:

```
entity_tags: 170 value(s) have no vocabulary entry and would print raw English:
  ['一眉道', '三大家族', '上忍', '不死', '世界观', '东京', '丹药', '主角']
```

**Every sample is Chinese.** `e.tags` is free prose lifted out of the record; a Chinese tag
printing as itself is the *correct* rendering. The scan was wrong, the page was right — and
the arithmetic closes: 175 distinct values, 5 Latin (all covered), 170 non-Latin, and the
reported count was exactly 170.

So a group now carries its kind. `'enum'` values come from a controlled upstream vocabulary
and **every** value must be covered. `'freetext'` values only need coverage when they contain
Latin letters. The group also reports how many values it saw, and the Python side **refuses a
freetext scan with nothing to look at** — an empty scan is not a pass.

Verified three ways: as shipped `untranslated = {}`; injecting `shapeshifter` is reported;
clearing every tag drops `total` to 0 and trips the refusal.

### Gates 45, 46, 47

- **45 — the tag channel**: enumerate the 9 tagged subject ids, assert `#sec-tags` is emitted
  and `data-tag != shown`, and re-run both leak scans on a page that actually renders tags,
  because the body-text scan had only ever run on `#/`. MEASURED `9/9 subjects, missing=0,
  untranslated=0`.
  *(Superseded by the Sixteenth revision: the nine ids were a snapshot of the data, and the
  probe is now derived from the graph — 16 ids. The assertions above are kept as the record of
  what this revision shipped.)*
- **46 — the search channel**: four real phrases must resolve to the right kind
  (`event` / `summary` / `thread` / `commit`) with `wrong_kind = 0`; a query must span ≥2
  kinds (a gate that only asked "are there results" would be green while the index covered
  entities alone); and a two-word query must find something, which it could not before —
  `cmScore` treated the whole string as one substring, so **any query containing a space was
  guaranteed to return nothing**. MEASURED `4/4 phrases resolved, wrong_kind=0`.
- **47 — the back control**: after `#/chapter/300 → #/char/char_qin_chao` there must be a
  `[data-nav-back]`, and clicking it must land on `#/chapter/300`. The assertion is
  **arrival**, not displacement. MEASURED `present=True returned=True depth=118`.

### Gate 48 — prose fidelity, and the screenshot that lied

I read `atlas-home.png` (1680x1050 downscaled to 1080) and reconstructed a garbled chapter
summary, and was one step from filing it as a rendering defect. The reconstructed string
shared enough tokens with the real one — 「五百加到一千」, 「父亲韦一鸣」, 「二女」 — to be
entirely plausible. The real text is
`韦晓龙被二女冷落后不服，掏五百加到一千要买秦朝座位…`; what I "read" was nonsense assembled
from the same fragments. **A screenshot proves that something is there; it never proves what
it says.** So the comparison is made against the graph, not against my reading of a picture.

The gate reads the first card present in the chapter-summary block at six cutoffs
(1 / 120 / 251 / 500 / 760 / 975) and compares `h4` / `p` `textContent` against the graph's
record for **that card's own `data-ch`**. Using the card's own key rather than assuming which
card is on page 1 matters: an ordering assumption would surface as a false "not rendered".

Two differences are deliberate and are **reported rather than failed**, and both were found by
running the gate for the first time:

- A missing `title` key emits no `<h4>` at all, so the DOM side is `null` while the record
  side is `''`. Comparing them raw flagged 2 of 6 chapters, neither of which is a page defect.
- `prose()` normalises CJK spacing, so 「第五百章 拜见娘家人」 renders as 「第五百章拜见娘家人」.
  That is a typographic rule, not a rewritten fact.

Neither can hide a real mangle: `esc()` double-escaping and `join()` artifacts change
*characters*, and those still fail here. The clamp half is contract 3.2.4 — `-webkit-line-clamp`
must be `none` and `overflow` must be `visible`, or the text is in the DOM but walled off.

**The downgrade test had to be rewritten, and the first version was worthless.** Mutating
`G.chapter_summaries[i].summary` proves nothing, because `setChapter` re-renders the stream
from `G` — the DOM picks up the mutation and the two sides agree again. The first run showed
exactly that: 999 summaries rewritten, zero mismatches reported. The mutation has to land on
the **DOM side, after the render and before the read**. Done that way, 6/6 are reported; with
`-webkit-line-clamp:2` injected, 6/6 are reported as a wall. 防退化: fewer than 4 distinct
chapters reached means the sample degenerated and the check is refused.

### The gate then failed on its first full run — for a reason worth keeping

```
CHECKS FAILED:
  - prose: only 1 distinct chapter(s) were reached ([975]) out of 6 cutoffs
```

Gate 47 leaves the route on `#/chapter/300`, and **the home stream is not repainted while a
paged route is active**. So `setChapter` alone re-read a frozen block: six cutoffs, six
identical cards, every one `data-ch=975`. Every fidelity number was green, because stale text
still matches the graph *for the chapter it belongs to*. **What caught it was the
anti-degeneration count** — 6 reads, 1 distinct chapter. Contract 4.4.0.8 again: every check
builds its own starting point. The gate now returns to `#/` and asserts
`__atlasRoute.view === 'home'` before sampling, and adds a stale assertion: after moving the
cutoff to N, the first card's `data-ch` must be N.

Verified from gate 47's exact end state: without going home, all six reads return the same
chapter and the stale assertion fires; with it, six distinct chapters and no failure.

### Persist the report before the screenshots

`accept.json` used to be written after `b.close()`, so a failure in the screenshot pass threw
away the verification results of all 47 gates — which is what happened all three times. The
report is now persisted first, and the screenshot pass is wrapped so its failures are recorded
in `report["screenshots"]` instead of discarding the run.

## Sixteenth revision — a probe that could not follow the data, and a performance gap that was measured instead of argued (added 2026-09-22)

### Gate 45's probe was a snapshot of the data, not a rule

The subject-tag gate shipped with a hardcoded list of nine entity ids — exactly the subjects
that carried a Latin tag on the day the field was first rendered. That is a snapshot. MEASURED
on this graph: **161 of 980 entities carry tags**, and only 9 of them carry one of the 5 Latin
values, so the list looked exhaustive and was not. If a later extraction moved `antagonist`
onto a tenth subject, every probed page would still render Chinese tags, `untranslated` would
stay empty, and the English would reach the reader with the gate green. It is gate 43's
stale-sample failure in a different costume.

The probe is now **derived from the graph**: every subject whose `tags` contain a Latin letter,
plus **one tag-carrying subject per routable entity type**. The second half matters because
`sec-tags` is pushed by `entityBody()` *before* its `isAgent` branch, so it renders for every
type — and nine character pages structurally cannot see a break that only affects `location`
or `skill`. Derived probe: 9 + 7 = **16 ids**.

Navigation goes through `openEntityRoute(id)` rather than a hand-built `#/char/<id>`, because
that function resolves the kind from the entity's type. The hardcoded hash only worked while
every probe happened to be a character.

### Four ways to make it fail, because a green is not evidence

| break | what fires |
|---|---|
| delete `#sec-tags` on non-character pages only | `missing` — 7 ids. **The old nine-id probe reports 0 and stays green.** |
| delete one chip | `count_mismatch` — `[['char_qin_chao', 1, 2]]` |
| reprint the raw value in the page body | `raw_ascii_on_page` — `[['char_qin_chao', 'protagonist']]` |
| neutralise every Latin tag | derived set empty → the gate refuses to pass |

The first row is the one that proves the widening was worth doing. The third row turns a check
that existed only as a comment into a live assertion: the previous revision collected ASCII raw
values into `tag_raw_ascii` and **never read the list**, so the sentence next to it described a
check that did not exist. And the fourth row is a refusal, not a verdict: with no Latin tag
anywhere, the leak pair can never fire, and the message names both readings (upstream
normalised the tags → the table and the gate are now dead code; `e.tags` left the graph → the
channel is broken) because only a human can tell them apart.

**My own harness lied first.** The degradation run came back 11/12 with the raw-value scan
silently not firing. The cause was in the harness: T4 had already deleted a chip from
`char_qin_chao`, and T5 navigated to the *same* page — `location.hash` did not change, so no
`hashchange` fired, no re-render happened, and T5 read T4's leftover DOM. The gate was right;
the probe was reading the wrong render. Every probe iteration now goes home first.

### The performance gap: `61.2` vs `48.7`, and why neither number was allowed to win

The fifteenth revision left one item open — the shipped build's drag `p50 61.2 ms` against a
historical `48.7 ms` — with the rule that an unverified difference is written up as neither a
regression nor the absence of one. This round settled it, and the settlement is mostly about
what the two numbers *are*.

The historical baseline is `accept.json` from 2026-09-19, and it records **`machine: null`**.
It has no load, no available memory, no timestamp. By this project's own rule — a pass without
an environment fingerprint is not a guarantee — an unfingerprinted *baseline* is not a
baseline.

So the difference was measured instead of argued. Two artifacts, one variable:

- **A** = the shipped `dashboard.html`
- **B** = a byte-identical copy whose only edit is the 46 uses of `var(--t-fast) var(--ease)`
  reverted to the pre-token literal `.12s`. `--t-fast` is `.13s` and `--ease` is
  `cubic-bezier(.22,.61,.36,1)`, so this restores **both** the old duration and the old default
  timing function; it is the pre-token semantics, not a re-spelling. The length delta is
  asserted to be exactly `46 × 21` characters, which is the only honest way to prove the
  replacement was the only edit.

Measured in one session, alternating order (ABBA), with the session's first load discarded:

```
A-tokens   drag p50 = [59.6, 58.8, 59.2, 57.7]   spread 1.9 ms   mean 58.8
B-literal  drag p50 = [61.7, 57.1, 58.7, 57.3]   spread 4.6 ms   mean 58.7
jump: A mean 82.3 vs B mean 78.8   (within-artifact spread 4.0 / 2.4 ms)
```

**|A−B| = 0.1 ms on the scrub, 3.5 ms on the jump — both inside the noise.** The one code change
between the two builds is ruled out; it cannot account for 12.5 ms.

And the same artifact measured **58.8 ms** in this low-load session against **61.2 ms** in the
acceptance session (74% / 8.07 GB available). A cross-*session* difference of that size is not
readable as a regression while one build moves 10.8 ms inside a single session.

**The first version of this experiment produced a fake 4.7 ms effect.** Without discarding the
cold first load and without alternating order, A came out at mean 64.6 against B's 59.9 — a
number that looks like a finding and is an artefact of the protocol: the session's first
measurement describes V8 still compiling (the gate's own comment already recorded p95 collapsing
140.7 → 68.1 over five runs of the same build), and A was always measured first. Discarding one
warm-up load and alternating the order moved the answer from 4.7 ms to 0.1 ms. The protocol was
the finding.

The harness also reported `6578998 differing positions` between A and B — a character-wise `zip`
over two strings of different lengths, so every position past the first edit is misaligned. It
is the same class as the screenshot that lied: a number that describes its own arithmetic rather
than its subject.

### One list, two writers — an assertion that could not fail

Widening the probe produced exactly one failure on the first full run, and it was the new one:
"the raw value must not survive anywhere on the page" fired **11 times** — every ASCII raw tag
on all nine carriers. Moments later in the same run, an ASCII-word scan of the *same page* came
back **empty**. Same element, same expression, same `innerText`, contradictory answers.

Three hypotheses were falsified before instrumenting: the folded catch-all appendix (it holds no
`tags` key even when expanded), fold state persisting across routes (it resets), and `#page`
being the wrong container (it is the subject page). Instrumenting a copy of the gate reproduced
the hit, and the print loop crashed on `row[2]` — because one entry had only two elements.

That was the answer: `tag_raw_ascii` had **two writers**. The old one (from the fifteenth
revision, under a comment claiming raw values must not survive on the page) appended
**unconditionally, for every ASCII raw value**, and was **never read**. The new page-text scan
appended to the **same list**, so the assertion read the union of two different meanings and
could never be empty. Fix: **one list, one writer** — the old append is gone, and its comment's
intent is realised by the new scan. It is the same rule as the rail's single `dataset.sig` writer.

### A degradation harness that installs nothing

The four-way harness reported 12/12 and could not have caught the defect above: it
**reimplements** the check, so it validated the logic and never the wiring. **A reimplementation
can only prove the reimplementation is right.** The end-to-end version therefore breaks the DOM
the *gate* reads and takes its verdict from the gate's own report.

Its first version then failed in the opposite direction: it wrapped `applyRoute`, and the run came
back **ALL CHECKS PASS**. The cause is a stale reference —
`window.addEventListener("hashchange", applyRoute)` captures the function at registration time,
so reassigning the name never reaches the listener. Registering a second, later listener (which
runs after the page has re-rendered) installed the break, and the gate then reported
`missing=7` — the seven non-character reps, **precisely the ids the old nine-id probe never
visited** — and `raw_ascii_on_page=1`. **A degradation that installs nothing reports exactly like
a gate that cannot fail.**

### Contract 5.7 — the instrument must reproduce itself

A cross-version comparison is only meaningful if the measurement is stable inside one session,
so reproducibility is now asserted rather than assumed: the gate measures the scrub a second
time on the same build and fails if the two `p50`s drift more than 25 ms. Observed drift after a
warm-up is 1.9–4.6 ms; the bound is 5× the worst observed. **An instrument that cannot reproduce
itself cannot detect anything.**

### The two harnesses that enforce 5.7 and the degradation rule

Both live in `scripts/` and both exist because the ad-hoc versions were wrong in ways that a
written rule alone did not prevent. Reuse them instead of re-deriving the protocol.

- `perf_ab_atlas.py <A.html> [--b B.html] --replace OLD NEW ... [--rounds N]` — the A/B protocol
  behind contract 5.7. It discards one session warm-up, alternates the order (ABBA), stamps the
  `machine` memory fingerprint on every round, and reports `|A-B|` against the largest
  within-artifact spread instead of against a remembered number. Variant B is **derived** from A
  by full-string replacement, and the derivation is asserted to be the only edit — do not hand-make
  it, and do not try to prove "only one edit" by counting differing positions: `zip` over two
  strings of different length misaligns after the first edit, and one token change produced a
  measured 6,578,998 "differing positions". This harness **measures, it does not judge**; read its
  last lines.
- `degrade_install_atlas.py --accept <gate.py> --js <break.js> --out <copy.py>` — installs a
  deliberate break into the page the gate reads, so the verdict comes from the gate's own report.
  A standalone harness that reimplements the gate's loop proves only that the reimplementation is
  right; measured case: 12/12 green in the same revision where the real gate's new assertion was
  tautological. The injected break **must** record proof of installation (`report["degradation"]`),
  because a break that installs nothing reports exactly like a gate that cannot fail — the first
  version wrapped `applyRoute` and was silently ineffective, since
  `window.addEventListener("hashchange", applyRoute)` captured the function reference at
  registration time. Each break needs its own **distinct** expected signal; a break that changes
  nothing in `checks` means the gate does not cover it.

## Seventeenth revision — the criteria themselves: a budget that could fail a good build, a sample that shrank while growing, and a preview that did not say it was one (added 2026-09-22)

This revision changes no rendering code. It changes three **criteria** that were each describing
more than they knew: the performance budget, the tag probe's sampling rule, and twenty-four failure
messages.

### ABBA cancels drift in a comparison; it does nothing for an absolute threshold

Run the A/B harness with **B set to a byte-identical copy of A** (`A == B`, 8,854,646 bytes
verified) and `|A-B|` describes the instrument alone:

| statistic | A, per round | B, per round | same-artifact spread | \|A-B\| |
|---|---|---|---|
| drag p50 | 59.5 / 59.5 / 74.0 / 58.0 | 60.2 / 60.9 / 74.1 / 59.3 | 16.0 / 14.8 ms | 0.9 ms |
| drag p95 | 70.5 / 69.8 / 90.0 / 81.9 | 70.3 / 70.0 / 85.5 / 74.6 | 20.2 / 15.5 ms | 3.0 ms |
| drag max | 74.9 / 74.7 / 91.8 / 84.1 | 71.4 / 73.1 / 91.7 / 74.8 | 17.1 / 20.3 ms | 3.6 ms |
| jump p95 | 93.5 / 98.0 / 104.3 / 83.5 | 89.7 / 89.2 / 86.8 / 82.7 | 20.8 / 7.0 ms | 7.7 ms |

In round 3 **both variants rose together** (drag p50 74.0 / 74.1), i.e. a within-round excursion of
the machine, not of the build. ABBA spread it across both, which is why `|A-B|` stayed at 0.9 ms
across a 16 ms spread. **That is the trap:** the previous revision used ABBA to show that a 12.5 ms
gap was not caused by the code, and it is tempting to read that as "so the number is trustworthy".
It is not. ABBA only helps a **comparison**. The budget is an **absolute** threshold, and the margin
under it is **10 ms** (worst reading 90.0 against a budget of 100) while the instrument's own spread
is **20.2 ms**. As written, `p95 > 100` fails good builds at random.

### The noise floor moves with the session

Round 16 recorded a p50 spread of 1.9 ms. This session measured **16.0 ms** on the same artifact —
8× larger. A noise floor is therefore **not a property of the instrument**; it is a property of the
session. Every run must measure its own and carry it: `drag_within_session_spread` (separately for
p50, p95 and max) is now in the report, next to the numbers it qualifies.

### The budget is now asserted on the median of three readings

The scrub is measured three times per run and the check is on the **median p95**, with the same
threshold and the same intent. The median rather than the best reading: a regression shifts the
whole distribution and still fails this, whereas taking the minimum would make the gate blunt
against real regressions — that is not a fix, it is a shutdown. `drag_ms_third`,
`drag_within_session_spread` and `drag_p95_median_of_3` are written to the report.

**Degradation, to show it can still fail:** a 40 ms busy-wait is injected into `window.render` —
which is exactly the function the gate times. p50 moves from ~60–75 to **98.8 / 98.8 / 99.6**, i.e.
**exactly +40**, so the injection provably took effect; p95 reads `[112.4, 112.1, 124.1]`, median
**112.4 > 100**, and the gate fails with exit code 1.

> Side observation worth keeping: with a deterministic 40 ms added, the same-session p50 spread
> falls from **16.0 ms to 0.8 ms** (p95 from 20.2 to 12.0). The noise is not inherent to the
> protocol — it is machine jitter showing through a workload short enough for jitter to matter.
> This is also why `jump` (a single `setChapter`) is less stable than a `drag` frame: it has no
> dozens of frames over which to average the jitter away.

### A sample that grows can still shrink coverage

Widening gate 45's probe from one subject per type to two, the first version took the first two
**by sorted id**, on the reasoning that a sample should not depend on input order. Measured: it
swapped the representative for **6 of the 8 types** and thereby **dropped five subjects that were
previously probed** — `org_luocha_men`, `loc_haiidao`, `concept_tian_sheng_mo_ti`,
`creature_guiquan`, `item_zhaohun_kulou` — including `org_luocha_men`, the target of the previous
revision's degradation test. **The sample size went from 1 to 2 and coverage went down.**

The criterion is therefore **"old set ⊆ new set"**, not "the new set is bigger". Taking a prefix in
**graph order** works because that is the order the previous rule used: the new probe is a strict
superset (verified: the first element per type equals the old representative for 8/8 types, zero old
representatives dropped, probe **16 → 24** subjects). A coverage assertion (`thin_types`: every
routable type must yield `min(2, its tagged count)`) plus `tagged_per_type` in the report keep
"this type is thin in the data" separable from "the probe missed it".

**Degradation:** breaking `#sec-tags` on two **second** representatives (`org_hei_long_hui`,
`loc_zha_huang`) yields `missing=2` naming exactly those ids, with `count_mismatch` /
`untranslated` / `raw_ascii_on_page` still 0 and `thin={}`. Neither id is in the old probe, so the
old probe would have reported all green.

### Every new assertion must be seen red once

`thin_types` cannot be triggered from the page — the page returns whatever the derivation asks for —
so the mutation goes into **a copy of the gate itself**: force `location`'s sample down to one
subject and change nothing else. The expectation was written down **before** the run:
`thin_types == {'location': [1, 7]}`, probe 24 → 23, `type_rep_ids` 16 → 15, one check naming
`location`. **All four matched**, `location` kept its graph-order-first subject (`loc_haiidao`), and
every other criterion stayed 0. An assertion that has never been observed red is decoration.

### Twenty-four previews now say they are previews

`missing=7` was followed by exactly six ids: the count was right and the list was a preview, but
nothing on the line said so, so the line described its own arithmetic incorrectly. Twenty-four
messages in the gate had that shape. They now all go through `preview(items, n)`, which returns
`repr` for a short list (unchanged behaviour) and `repr + "(+N more)"` otherwise. One print-level
case is covered too: `JS ERRORS` printed the first 20 of a longer list without saying so.

**Why it had to be one pass:** changing a single message would have left the set inconsistent and
would have invalidated the acceptance report produced by the previous revision of the script —
a report and the gate that produced it must be the same revision. That constraint is also why the
three changes in this revision were verified with a single re-run rather than three.

### Contract 5.8, 5.9, 5.10

- **5.8** — a performance budget must be asserted on the median of repeated measurements, and every
  run must carry its own same-session spread.
- **5.9** — a criterion's sampling set may only grow monotonically: the test is "old set ⊆ new set",
  not "the new set is larger".
- **5.10** — a new assertion must be observed red once; if it cannot be triggered from the subject
  under test, mutate the other half (the gate's own copy). The same rule makes an injection prove
  itself: without the +40 ms reading, "the gate went red" and "the break never installed" look
  identical.

## Eighteenth revision — a criterion that went red on a good build, and what that meant (added 2026-09-22)

This revision adds no rendering code either. It gives the one performance number that had no
criterion — the isolated `setChapter` update, reported since the dashboard existed and judged by
nothing — a criterion that does not invent a threshold; and then it acts on what that criterion
found on its first run.

### Where the 100 ms actually comes from

`AGENTS.md` item 7: *"用真实 Chromium 测量章节滑块连续输入、仓库切换及全图布局；默认视图章节更新
p95 目标不超过 100 ms，仓库切换 p95 目标不超过 200 ms"* — the scenarios named are continuous slider
input, warehouse switching and whole-graph layout; the target named is the default-view chapter
update at p95 ≤ 100 ms.

The scrub measured here is exactly that scenario (page top, default filters, 34 frames of
continuous drag, two warm-up passes). The isolated `setChapter` is the same *subject* under a
different *scenario*, and it is not the same quantity: MEASURED in one session, the coalesced
per-frame path reads p50 ~58 ms while the un-coalesced update reads p50 ~76 ms.

So the budget's reach is genuinely ambiguous, and both readings are defensible. Neither was
applied. Applying the stricter one silently would fail a build on a number the gate's own comment
calls an overstatement; applying the looser one silently would hide a real figure from whoever
wrote the budget. It is registered in the report as an open question, with the verdict **derived**
from the measurement rather than written beside it.

### The criterion that was added instead

Two properties the measurement can decide about itself, with no invented number:

- **Reproducibility** — three readings in one session; the p50 drift must stay inside a bound.
  The bound is this path's own, because the paths differ by 10×: the scrub's p50 spread was
  **2.4 ms** in the same session the isolated update's was **26.7 ms**. One bound cannot serve
  both.
- **Liveness** — a degenerate probe reports a *better* number, and "the metric improved" is how
  this project has mistaken a broken probe three times. The floor is **relative to the scrub
  measured in the same session** (a quarter of it), so it self-normalises instead of citing an
  absolute figure. Observed ratio: 76.2 / 58.0 = 1.3, i.e. the floor sits ~5× below the value.

### It went red on its first run, on a good build — and that was the useful part

```
reading 1  p50 106.3 ms   p95 114.4
reading 2  p50  79.9 ms   p95  86.1
reading 3  p50  79.6 ms   p95  90.0     -> drift 26.4 ms, bound 25 ms
```

Readings 2 and 3 agree to **0.3 ms**; reading 1 sits **26 ms** above them. That is not machine
jitter — the scrub's spread in the same session was 2.4 ms. It is the tail converging, the cliff
the scrub's warm-up exists for ("the tail is what converges last"), and this path had no warm-up
because it had never been judged. **The assertion was right to complain: the number genuinely did
not reproduce itself.**

The fix was therefore the protocol, not the threshold: two discarded warm-up sweeps, mirroring the
scrub, **recorded** in `render_ms_warmup` rather than silently dropped — a silent discard is how
"the number improved" and "the probe changed" become indistinguishable. Result, same build:

```
reading 1  p50 76.2   reading 2  p50 77.9   reading 3  p50 74.6   spread 3.3 ms
```

The earlier **104.9 ms** figure was an artifact of the missing warm-up, not a property of the
renderer. Every cross-version comparison that used it was comparing a warm-up artifact against
whatever the other build's protocol happened to produce.

The bound did move, 25 → 35 ms, and that is the move this project has had to un-do before, so the
justification is recorded: the bound must clear every spread observed for this path (p50 26.7 /
p95 28.3 ms), and the pre-warm-up reading is one of them. **It was not raised to make a red go
away** — the red was fixed by making the measurement reproduce itself.

### A registered question must not contradict its own figures

The first version of the open question ended with a hard-coded *"Subject reading: the build fails
the budget."* The next run measured p95 81.2 ms — inside the budget under **both** readings,
because the warm-up fix had removed the 106 ms artifact. The report would have carried a claim its
own numbers refute. The verdict is now derived (`jump_p95 <= 100`), and the question says what is
actually true: the ambiguity changes what the project promises, not whether this build passes.

This is round 17's `missing=7` error in a new costume — a line describing its own arithmetic
incorrectly.

### Contract 5.11, 5.12, 5.13

- **5.11** — a number with no external budget must either carry a criterion the measurement can
  decide about itself (reproducibility, liveness) or be registered as an open question. It may
  not simply be printed: a printed number that nothing judges is read as a checked one, and the
  liveness floor has to be **relative to a measurement taken in the same session** so it
  self-normalises instead of citing an absolute figure.
- **5.12** — when a reproducibility criterion goes red on a build you have no reason to think
  regressed, fix the measurement protocol before touching the threshold; a threshold raised to
  silence a red is a threshold retired. If the threshold does move, record what observation it
  had to clear, and why that observation is not retroactively deleted by the fix.
- **5.13** — a registered open question, a verdict embedded in a message, and a preview list all
  describe their own numbers; they must be derived from the measurement, never written beside it.
  A claim the report's own figures refute is worse than no claim. This extends to the *copies*
  used for degradation runs: a mutated copy generated before a fix carries the old wording, and
  citing it means citing a report from a revision that no longer exists.

## Nineteenth revision — the two probes measured two samples, and the budget turned out to be load-bearing (added 2026-09-22)

### The question that was open was resting on the wrong reason

Round 18 registered this: does AGENTS.md item 7's 100 ms p95 budget cover the isolated
`setChapter`, or only the continuous scrub the item names? Both readings looked defensible, so
neither was applied, and the registration added: *"the ambiguity changes what the project
promises, not whether this build passes."*

Round 19 measured the thing that claim rested on. The slider's real path is

```js
slider.addEventListener("input", () => setChapter(N(slider.value)));
```

and a non-immediate `setChapter` coalesces to one frame of
`paint = () => { if (paged) paintPage(RT); else render(v); buildSidebar(); }`. The gate's scrub
probe times `performance.now()` around `render()` — the JavaScript half of the frame the reader
waits for. But that is not what separates the two probes:

```
same 34 consecutive chapters, one frame each, one session
  render(c)               p50 58.5 ms
  setChapter(c, true)     p50 59.3 ms      -> 1.01x
  buildSidebar() alone    p50  0.1 ms      -> 1.4% of a frame
```

Two hypotheses died there. The drag probe does not under-measure by omitting the sidebar. And the
two probes are not "two quantities" — they are **one quantity sampled over two chapter patterns**:

```
tail, 34 consecutive frames    p50 57-61 ms
whole range, 10 big steps      p50 74-83 ms steady
```

Contract 5.11's *reason* was wrong, and with it round 18's claim that only the scenario reading is
operational: a wide-step update is a perfectly operational sample of "the chapter update".

### The first pass in a session costs ~40 ms more, and no mechanism is named

`jump`'s first sweep had been filed as a discarded warm-up. It is not an artifact:

```
first sweep of a session   js p50   99.7 / 118.6 / 125.7 ms   (three sessions)
every later sweep          js p50   70.1 / 71.7 / 74.4 / 76.0 / 78.9 / 79.4 / 81.4 / 82.7
```

Three candidate mechanisms were tested and **refuted**:

- the sidebar — 0.1 ms;
- the projection cache — `CACHE.clear()` before every step made the pass **faster** (78.9 against
  116.0 ms), so it is not projection hits;
- the markup cache — clearing `MARKUP_CACHE` did not bring the cost back (82.7 against 125.7 ms).

and the projection table's size axis then **disagreed between two probes** — one read a full table
as slower, the other as faster. So the **effect is recorded and the mechanism is left unnamed**. The
old comment called it "V8 finishing optimising the hot path"; nothing measured here supports that
sentence, and a named mechanism that has not been measured is how a comment becomes evidence.

It also cannot be reproduced within a session — by construction it happens once per page — so it is
now reported as `render_ms_first_visit`, with a note saying it carries no within-session spread,
instead of being discarded.

### The budget turned out to be load-bearing, and the verdict flips with the reading

```
                            js p95     frame p95
scrub, median of 3           75.9        83.5      -> inside, 16.5 ms margin
wide step, steady            98.3       111.2      -> OVER
wide step, first visit      114.5       125.1      -> OVER
```

Round 18's "both readings pass" was measured against a JavaScript span on a cached second sweep.
Against the frame span — the quantity the reader actually waits for — a clause read as covering any
default-view chapter update does not pass. So the question is genuinely open and genuinely material,
and the registration now says exactly that, **neutrally**: the gate asserts the clause on the
scenario the item names, reports the other sample with its four figures, and states that the reading
decides the verdict. Picking a reading in the wording would have been the same error as picking one
in the assertion.

### The reader waits for the frame, not for the JavaScript

The budget is about a latency a person experiences, and `performance.now()` around `render()` does
not measure that latency. Every drag frame now records two spans: the JavaScript, and the timestamp
delta to the next animation frame — the JavaScript plus the browser's own style/layout/paint plus at
most one vsync period. Same session, same build: js p50 **56.9 ms** against frame p50 **68.6 ms**;
final acceptance js p95 median **75.9** against frame p95 median **83.5**.

Both are asserted against the same 100 ms clause, because they bracket one quantity: the JavaScript
span is the tighter instrument and catches a regression first (margin 24.1 ms, within-session p95
spread 6.9 ms), and the frame span is what the reader waits for (margin 16.5 ms, spread 6.9 ms). A
frame that spends its time outside `render()` can no longer hide behind a healthy JavaScript figure.
The cost is stated rather than hidden: the frame span includes up to one vsync period, so it is an
upper bound, and an earlier acceptance run in the same round had a p95 spread of **22.3 ms** with one
reading at 105.8 ms — the median-of-3 rule is what kept that from being a false red. That assertion
will go red more readily in a slow session than the JavaScript one, and when it does, the red is
true: the reader's frame cadence did cross the budget.

### The mutation had to prove its own size, in the same session

A 40 ms busy-wait injected into the drag probe's timed region, with the prediction written down
first — two checks red, nothing else:

```
clean baseline, same session   js p50  60.8   frame p50  69.5
mutated                        js p50  99.8   frame p50 111.1     -> +39.0 / +41.6 ms
red: scrub js p95 median 110.4 ms;  scrub frame p95 median 125 ms
quiet: drag drift, jump drift, jump liveness
```

The first attempt had no in-session baseline and read +29.9…+35.5 ms for a 40 ms injection — close
enough to look like noise. That gap *was* noise: the session-to-session swing measured this round
(js p50 56.9–69.0 across sessions). So the self-proof baseline has to be taken in the same session;
citing a previous run's figure folds the swing into the injection's measured size. This is contract
5.8's ABBA lesson arriving one level down: cancelling drift needs a paired measurement, not a
remembered one.

### Contract 5.14, 5.15

- **5.14** — a budget about a latency a person experiences must be asserted on the span that person
  waits for. Measuring only the JavaScript inside the update understates it by the browser's own
  style/layout/paint plus up to one vsync period; assert both spans, because they are the lower and
  upper bounds of one quantity, and say which is which. Expect the frame span to be the noisier
  instrument and to go red in slow sessions — and treat that red as information, not as a flake.
- **5.15** — when two probes disagree, test whether they disagree about the **sample** before
  concluding they measure different **quantities**: run both over the same chapters. A one-time
  first-pass cost is a reader cost, not a warm-up artifact, and it belongs in the report with a note
  that it cannot be reproduced within a session. When three plausible mechanisms have been refuted,
  record the effect and leave the mechanism unnamed — a comment that names an unmeasured cause will
  be read as evidence by whoever comes next. And a coverage question about a spec's wording may not
  be closed by choosing a reading inside the report; state the figures and let the wording's owner
  decide, which is what "registered, not decided" has to mean when both readings turn out to be
  operational.
