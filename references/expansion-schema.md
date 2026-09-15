# Growth, world and narrative expansion contract

This reference defines the next-stage schema and derived-view contract.  It keeps
`graph.json` as the only story-fact source and deliberately adds only one new
top-level record array: `commitments`.

## Architectural rule

Store a fact only when it cannot be reconstructed deterministically from existing
facts.  Achievements, combat tables, resource ledgers, co-occurrence networks,
knowledge matrices, mortality lists and world-map layouts are derived views.
Do **not** add `achievements`, `duels`, `inventory`, `secrets`, `deaths` or
`territories` arrays.

The current monolithic pipeline predates `commitments`; during the compatibility
period use:

```powershell
python scripts/check_fragment_expanded.py --fragment <fragment.json> [...]
python scripts/merge_graph_expanded.py --input <fragments...> --output <graph.json> [...]
python scripts/validate_full_graph.py --graph <graph.json> [...]
python scripts/derive_novel_views.py --graph <graph.json> --output <derived/novel-views.json>
```

`validate_full_graph.py` runs the historical validator and the expansion
validator.  A publish is valid only when both pass.

## Commitments

`commitments[]` is the only new top-level record family.

Required:

- `id`
- `kind`
- `promisor_ids`
- `counterparty_ids`
- `terms`
- `created_chapter`
- `status`
- `evidence_ids`
- `confidence`

Required keys that may be null/empty:

- `deadline_chapter`
- `deadline_story_time`
- `stake_ids`
- `resolved_chapter`
- `resolution`
- `observations`

Controlled kinds: `promise`, `oath`, `agreement`, `wager`, `revenge_vow`.

Controlled statuses: `active`, `fulfilled`, `partially_fulfilled`, `broken`,
`expired`, `waived`, `uncertain`.

`observations` is append-only lifecycle history.  A terminal status should carry
`resolved_chapter`; evidence stays attached to both the commitment and material
lifecycle observations.

Favors/debts do not become commitments merely because they motivate a character.
Use a temporal `owes_favor_to` relation with `strength` 1..3 and append repayment
or escalation evidence to `observations`.

## Event facets: structure without event-type inflation

Keep `events[].type` in the small canonical vocabulary.  Domain detail goes into
optional facets and controlled tags.

### `combat`

Use on battle events when result semantics matter.

```json
{
  "combat": {
    "kind": "duel",
    "participants": [
      {"entity_id": "char_a", "side": "A", "outcome": "victory"},
      {"entity_id": "char_b", "side": "B", "outcome": "defeat"}
    ],
    "stake_ids": [],
    "killed_ids": [],
    "resolution": "decisive"
  }
}
```

Outcomes are `victory`, `defeat`, `draw`, `escaped`, `interrupted`, `uncertain`.
Never store a participant's "current level" inside combat.  Combat-record views
must replay temporal state at `event.chapter` so an early fight can never inherit
a late-book realm.

### `transaction`

May carry `buyer_ids`, `seller_ids`, `item_ids`, `currency_id`, `amount` and
source-faithful unit information.  Currency itself remains a `concept`.

### `mortality`

May carry `deceased_ids`, `killer_ids`, `witness_ids`, `cause`,
`revival_mechanism` and `cost`.  Death/revival lists are derived from events plus
health state changes.

### `information`

May carry `revealer_id`, `audience_ids`, `secret_ids` and controlled `mode`.
Secrets are `concept` entities classified as `secret`; who knows them is a
`knowledge` state change, not a separate secret ledger.

### `payoff`

May carry `setup_ids` and controlled `kind`.  Setup-to-payoff distance is derived
from chapter numbers and must not be copied as a second fact.

## Entity classifications

Skill entities use multi-valued `categories`.  Controlled IDs live in
`scripts/controlled_vocab.py`: movement, cultivation, attack, defense, control,
support, healing, perception, crafting, formation, passive, transformation,
summoning, utility and unresolved.

Concept categories are secret, rule, prohibition, curse, currency, recipe,
world_lore and unresolved.

Items retain the existing item category system.  Resource semantics use reserved
tags instead of a new entity type:

- `rarity/common|uncommon|rare|very_rare|unique|unresolved`
- `supply/repeatable|limited|unique|unresolved`

Quantity changes use a targeted state change (`target_id = item_id`) with a
quantity facet such as `inventory_quantity`.  Acquisition place is normally
resolved through `item_roles.cause_event_id -> events[].location_id`.

## World and territory

Fictional geography is topological by default.  Use evidence-backed
`located_in` / `part_of` relations for location hierarchy.  Do not fabricate
latitude/longitude.  Dashboard coordinates are layout data only.

Territorial control uses a temporal relation:

```text
location --controlled_by--> organization
```

with `valid_from`, optional `valid_to`, evidence and observations.  The map view
can therefore replay control at a chapter without storing a second territory
snapshot.

## Relationship completeness

Extraction must not privilege protagonist edges.  Generate side-character
candidates from shared events, direct dialogue, battle, aid, gifts, kinship,
teaching and repeated co-occurrence.  Each candidate must become one of:

- confirmed relation;
- explicit exclusion/non-match;
- unresolved review issue.

Co-occurrence is a recall signal only.  It never proves friendship, hostility or
membership.  `derive_novel_views.py` emits high-co-occurrence/no-relation pairs
as review candidates.

## Chapter narrative fields

`chapter_summaries` may additionally carry:

- `story_time`: only the precision supported by the source;
- `pov_entity_ids`;
- `scene_count`;
- `cliffhanger_type`.

Controlled cliffhanger values: crisis, suspense, reversal, revelation,
breakthrough, romance, none, uncertain.

## Derived view contract

`scripts/derive_novel_views.py` writes a derived-only JSON model containing:

- protagonist achievement timeline;
- combat records with as-of level snapshots;
- resource/item ledger with source event and location;
- world hierarchy, territorial control and travel path;
- character co-occurrence matrix and side-character relation-gap candidates;
- skill classification matrix source data;
- commitment lifecycle rows;
- knowledge/secret histories.

The file is disposable and reproducible.  Never merge it back into `graph.json`.

## Coverage is not a zero-error count

`scripts/extension_contracts.py` reports both numerator and denominator for:

- battle -> structured combat;
- skill classification;
- location hierarchy;
- event location;
- item-role cause event;
- chapter summaries;
- resource tags.

If the denominator is zero, the report says so explicitly.  An empty input is not
a completeness pass.

## Backfill order

For legacy runs use three passes:

1. deterministic derivation from the current graph;
2. candidate scan for missing location hierarchy, combat outcome, skill category,
   side-character relations, item acquisition causes, commitments and knowledge;
3. evidence-closure re-read around candidates, resolving each as confirmed,
   excluded or unresolved.

Do not reread the whole novel merely to populate a new dashboard field.

## Complete derived view set

The expansion dashboard and `novel-views.json` additionally expose deterministic:

- foreshadowing gantt rows and setup-to-payoff spans;
- level progression series;
- chapter rhythm, POV, scene count, story-time and cliffhanger rows;
- romance milestone tracks;
- per-chapter state-change diff rows;
- mortality/revival register;
- parent/teacher/learned/crafted-from/derived-from lineage edges;
- transaction and wealth-change views;
- world-rule/prohibition/curse/currency/recipe concepts;
- favor/debt ledger from `owes_favor_to`;
- secret propagation edges from `events[].information`;
- voice/style exports where style observations exist.

These are all derived and must never be merged back into `graph.json`.

## Spoiler-safe rendering

A shareable chapter cutoff is a rendering/build concern, not a canonical-data
mutation. `filter_graph_asof.py` removes future entities, evidence, events,
relations, state changes, aliases with known first chapters, future romance
milestones, future commitment resolutions and future foreshadowing payoffs before
view-model construction. Hiding nodes after the full model is built is not
sufficient because search, counters and tooltips can otherwise leak future facts.

## Reader overlay and run hygiene

`build_reader_overlay.py` places prepared chapter text beside events/evidence and
highlights exact evidence quotations. `build_run_index.py` reports real coverage
from `metadata.analyzed_chapters`; directory names are not coverage authority.
`gc_run.py` is dry-run by default and moves candidates into a recoverable
fingerprinted archive before any optional purge.

## Relation interval safety

The expanded merge preserves a known `valid_to` when a later overlapping record
merely restates the relation as active/open. A true resumed relationship begins
after the previous close and becomes a new temporal episode. This prevents old
relationships from being accidentally drawn through every later chapter.
