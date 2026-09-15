# Temporal novel graph schema

Read this file before extracting, merging, or correcting graph data.

**Fidelity rule.** Treat the supplied fiction as source material and record relevant events faithfully, including violence, intimacy, and non-consensual acts when present. `confidence` reflects evidence strength, not comfort or narrative neatness. Distinguish source silence, bounded search misses, and unresolved interpretation in `review_issues`; do not claim a source's legal/review status unless the user supplied evidence for it.

## Reader-facing prose

`notes`, `summary`, `description`, `reason`, `observation`, `interpretation` and
`resolution` are **reader-facing**. Whatever is written there is printed in the dashboard
and in the AI story bible, so it must read as something addressed to a reader — not to the
next analyst.

Do not write the work's own bookkeeping into them. Measured across the runs in this
project, the recurring offenders were the merge journal (`本条由主 Agent 从 N 条分片记录
合并（rom_A01、…）`, appended once per consolidation and often duplicated two or three
times in one field), hand-off instructions (`请主 Agent 裁决`, `交由主 Agent 合并补填`,
`请由更早分片补充`), per-fragment bookkeeping (`本分片…留空`, `（依据固定实体表说明）`,
`[rom_su_ji 第1章]`), and English machine keys left inside Chinese sentences
(`first_sex_chapter`, `consent_context`, `altered_state`, `status`).

Where the same information has to be kept, put it somewhere that is not rendered:
`metadata.notes`, or a `review_issues` entry — which is itself analyst-facing and may say
"请人工裁决" freely.

Two guards exist, and they do different jobs. `strip_process_text()`
(`scripts/reader_prose.py`) cleans the prose **on the way out**, so an already-delivered
graph renders cleanly without a data rewrite; both renderers call it, from one shared
definition, so the page and the AI text cannot disagree. `scripts/audit_reader_prose.py`
names the records whose **stored** text still carries the junk, because cleaning at render
time hides the problem rather than fixing it. Neither one may remove story content: the
renderer drops whole sentences and never cuts inside one, deletes only record IDs that
cannot be resolved (a fragment-local `rom_A01` has no label anywhere, while
`char_huo_muqin` does), and hands a field back to the caller rather than printing a
sentence fragment when almost everything in it was bookkeeping.

## Top-level object

`graph.json` is UTF-8 JSON with `metadata`, `entities`, `events`, `relations`, `state_changes`, `foreshadowing`, `evidence`, and `review_issues`. It may also contain `romance_routes`, `item_roles`, and the other optional arrays defined below; legacy graphs that omit them are treated as having empty arrays.

`metadata` contains `title`, `source_file`, `source_sha256`, `chapter_start`, `chapter_end`, `analyzed_chapters`, `generated_at`, and optional `notes`. `analyzed_chapters` lists chapters actually processed, not the intended range.

## Stable identifiers

Use lowercase ASCII IDs with a type prefix and semantic slug when practical: `char_tang_san`, `item_24_bridges`, `skill_xuantian_gong`, `event_ch003_awaken_twins`, `ev_ch003_l420_424`, `sc_ch013_tang_hao_departure`, `fs_tang_san_second_martial_soul`.

Do not encode mutable status in an ID. Never reuse an ID for a different object.

**An entity ID and a record ID follow different rules.** An entity ID is `<type>_<pinyin>` and must **not** carry a fragment marker, because it is what every later extraction round reads and reuses: `char_liu_yi`, `skill_suixin_gu`, `creature_huolong`. A record ID must carry one, because two workers extracting in parallel would otherwise mint the same ID for different records: `ev_f38_001`, `rel_f38_*`, `sc_f38_*`, `fs_f38_*`, `ri_f38_*`. A marker on an entity ID is not cosmetic — the next round reads `_f29_` as belonging to that round's fragment and either drops the record at merge or creates a second entity for the same thing. When an ID must change (a marker to strip, a malformed slug), rewrite it in the fragment that declares it; a merge-time `--id-map` leaves the stale token on disk for the next round to re-import.

## Entities

Required: `id`, `type`, `name`, `first_chapter`, `evidence_ids`.

Supported types: `character`, `skill`, `item`, `organization`, `location`, `creature`, `martial_soul`, `title`, `concept`, `level_axis`.

Useful optional fields: `aliases`, `historical_names`, `titles`, `name_history`, `summary`, `attributes`, `categories`, `current_state`, `last_chapter`, `tags`. Attributes are only for stable or explicitly scoped facts. Put time-varying properties in `state_changes`.

`aliases`, `historical_names`, and `titles` remain string arrays for compatibility with all indexes. Evidence and validity live in `name_history`: `{"name": "旧称", "kind": "former_name", "valid_from": 1, "valid_to": 20, "evidence_ids": ["ev_..."]}`. Every historical/alias identity whose timing is known appears both in the appropriate lookup string array and in `name_history`; quotation text is not duplicated. `categories` is a multi-valued classification list, primarily for items, and each new entry uses `{"id": "weapon", "primary": true, "confidence": "explicit", "evidence_ids": ["ev_..."]}`. At most one entry is display-primary; every other category remains visible as an additional membership. Default item category IDs are `weapon`, `armor`, `accessory`, `luxury_collectible`, `consumable`, `resource_material`, `book_manual_contract`, `vehicle_container_dwelling`, `token_credential`, `ordinary`, and `unresolved`. A category is not inferred from an item's name alone.

### Canonical names and display identity

Keep the current canonical name separate from `aliases`, `titles`, `historical_names`, and contextual display names. When the text explicitly reveals a later or authoritative name, update the canonical `name` through an evidence-backed correction or supplementary fragment and retain the earlier name as an alias with its chapter/evidence context. Do not permanently render multiple names as a parenthetical composite unless the source treats that composite as one stable name. Historical chapter views use the name valid at that chapter; current views use the latest confirmed canonical name. Similar spelling, surname, or co-occurrence is not identity evidence.

Attribute keys are reader-facing. Write them in the book's own language (`物种`, `属性`, `出身`, `备注`), never as internal English keys. The dashboard and the AI text render exactly what is stored here, so an English key becomes visible English in the delivered artifact. `scripts/attribute_keys.py` holds the alias table and folds English schema spellings back onto the book's wording during merge, and `validate_graph.py` rejects an entity that carries both spellings of one attribute — so a fragment may write `gender` and the merge will produce `性别`, but new data should write the book's wording directly. The table also folds Chinese synonyms (one fragment's `分类` onto the canonical `类别`), because that is the same defect one language over: one fact displayed under two labels.

A non-human entity's character-style layout is **derived, never declared**. `scripts/agent_detection.py` reads the graph and decides which non-character entities act like people: a weighted score over four evidenced signals (speech attributed to it, its own identity/title/goal/emotion/knowledge/affiliation changes, participation in several events, being the subject of several clues) counts only if the entity shows at least one *core* signal — speech attribution or a self-owned state change. A skill or item always has a relation to its user and is often foreshadowed, so the core-signal gate is what keeps them out. Detected entities keep their real `type`, so a spirit beast is still a `creature` with the creature node shape and colour and still appears under 魂兽 in the type filter, but it receives the full character-style layout in both deliverables: a change timeline, per-facet state groups, and its own entry under 人物档案 (labelled 拟人主体 in the dashboard, with the deciding reasons shown). A creature that only appears as a monster, mount, or scenery scores zero and needs no manual exclusion. `"is_agent": true` still works as an explicit override and `false` as a veto, but a hand-written flag is never required.

That derivation only covers entities whose `type` is outside `NON_AGENT_TYPES`. `concept`, `location`, `organization`, and `title` are excluded outright — which is right for an abstract noun (a quotation like 「修仙，只能增强我们自己的体魄」 puts a speech verb next to 修仙 without 修仙 being a speaker) but is a trap for a *person* filed under the wrong type. `agent_detection.py` therefore also prints a second list, "entities that act like people but their type excludes them", for every excluded entity that speaks or changes its own identity. Treat a hit as a decision to make, not noise: retype it, or write `is_agent: false` to record that it was checked and is scenery.

## One body, several agents

A second personality, an avatar, a possessing spirit, or a projected double can act as its own agent while sharing one body with the protagonist. Model it as **its own entity**, not as a facet of the host, and give it its own history:

- **Judge by agency, not by appearance.** If it speaks, decides, cultivates, or takes over the body on its own initiative, it is a separate agent. If the same person merely wears a costume or a cover name and nothing acts behind it, it is not: keep the mask as an alias, or at most a `concept` for the disguise, and do not invent a second person. **A cover identity still needs a relation to whoever wears it** (`disguised_as`), because the reader otherwise cannot tell whose it is. The same obligation covers any entity whose own name declares a bearer — `刘弈的右手`, `冷沫的光剑刀柄`, `陈才的召唤异能` — and `scripts/audit_entity_links.py` exists to find the ones that were missed. Nothing catches a bare codename such as `血皇`, so add the edge when the entity is created rather than hoping a check will find it later.
- **Type it `character`.** This is the one case where the type must be the layout-bearing type: a personality typed `concept` is excluded by `NON_AGENT_TYPES` and can never reach the character layout, however much evidence accumulates. Its ID prefix must then match its type, because the ID is what later extraction rounds read.
- **Add a relation back to the host.** Without the edge the split is invisible: the reader sees two unrelated entities and cannot tell they are one person. Use `alter_ego_of` (`source` = host, `target` = the other self; listed in `SYMMETRIC_RELATION_TYPES`), or `same_body_as` / `avatar_of` where those fit better, and describe the phases in `description`. Every display vocabulary needs an entry for whichever type you pick, or the relation renders as 未分类.
- **Record a takeover from both ends.** When the other self seizes control, the host records 本人格主导 → 该人格接管 and the other self records that it gained control; when control returns, the host records the reverse and the other self records a loss. `lost` needs its `reason` like any other loss. Recording only one end leaves one agent's timeline with a hole.
- **Never merge their ladders, skills, or relations.** A second personality may cultivate independently, hold its own tier, and form its own enmities — the three star-shas a dark personality lit in secret are *not* the host's. Keep the level axes, skills, and relations separate, and if the text is ambiguous about whether the two share one pool, record the ambiguity in `review_issues` rather than picking one reading.
- **Do not merge the two entities to "clean up".** Same-body is not same-entity; `alias_collision` warnings about the two names are a false alarm here, because the names genuinely are two spellings of one person's two sides.

Worked example: 刘弈 (`char_liu_yi`) and 腹黑刘弈 (`char_dark_liu_yi`) in `runs/我的狐仙老婆-full`. The dark personality was first extracted as a `concept`, so it had no panel and no relations; the correction fragment retyped it, added the `alter_ego_of` edge, and added its own eleven state changes, including the takeovers the host already recorded from the other side. The same run's `fragment-37` is the contrast case: 红领巾侠 and 血皇 are 刘弈's cover identities, so they keep `concept` and gain a `disguised_as` edge instead of a panel — a link audit had found five entities whose names declared a bearer but had no edge to it, and two of them were these identities.

## Evidence

Required: `id`, `chapter`, `quote`, `source_line_start`, `source_line_end`.

Optional: `source_file`, `note`. Quotes must be exact, short enough to audit, and sufficient to support the linked claim. Line numbers refer to the immutable source file or prepared chapter mapping.

## Events

Required: `id`, `type`, `chapter`, `title`, `description`, `participant_ids`, `evidence_ids`.

Optional: `location_id`, `cause_event_ids`, `consequence_event_ids`, `tags`. Events are causal anchors for state changes, not chapter summaries.

`type` is the record field; the display vocabulary group that translates it is `event_types`. Write `type`, never `event_type` — a vocabulary group name is not a field name.

Take `type` from `scripts/event_types.py`, which holds the set (`RECOMMENDED_EVENT_TYPES`) plus the synonym folds: `merge_graph.py` folds the unambiguous aliases onto the canonical spelling and both renderers take their labels from the same module, so the set has exactly one definition. Keep the type small and reusable and put the specifics in `tags`. A type names the *kind* of thing that happened; narrative role (`climax`, `turning_point`, `cliffhanger`, `plot`) is a different axis and belongs in `tags` as well. When nothing fits, use `other` and describe it in `tags`: a run whose types are nearly as numerous as its events cannot be filtered by type at all, and `validate_graph.py` reports the labels outside the set as an observation.

The record field is `type`; the display vocabulary group that translates it is `event_types`. Write `type`, never `event_type` — the group name is not the field name, and an event that carries only `event_type` has no required `type` at all.

Keep the type set small and reusable. Prefer a shared handful — `battle`, `breakthrough`, `affliction`, `alliance`, `revelation`, `ceremony`, `journey`, `crisis`, `intimacy`, `payoff` — and put specifics in `tags`. A run whose distinct event types approach its event count cannot be filtered by type: five parallel passes inventing labels independently produced 55 types across 112 events, 35 of them used exactly once, which made the type facet useless and the vocabulary 62 entries long.

## Relations

Required: `id`, `source_id`, `target_id`, `relation_type`, `valid_from`, `status`, `evidence_ids`.

Optional: `valid_to`, `direction`, `strength`, `description`, `change_ids`, `observations`, `close_reason`. When present, `strength` is an integer from 1 to 3; confidence belongs in evidence or state-change records, not this field. A later change closes or revises an interval; do not rewrite the earlier relationship as if it never existed.

Within one uninterrupted validity episode, one semantic relationship must have exactly one relation record. Repeated chapter evidence is appended to that record's `evidence_ids`; it must not create parallel edges. For symmetric relationships such as friendship, reversing `source_id` and `target_id` does not make a distinct relation. A genuinely ended and later resumed relationship remains separate temporal episodes.

Each canonical relation has a stable `pair_key` derived from canonicalized endpoints and `relation_type`, plus an `episode_id` when the same semantics end and later resume. `observations` is an append-only list of source restatements or status transitions with `chapter`, `evidence_ids`, and optional `description`, `status`, `valid_from`, and `valid_to`. Coalescing may update the compatibility fields on the relation, but it must retain every non-empty description and status transition in `observations`; a later fragment must never silently overwrite an earlier qualification.

Examples: `parent_of`, `sibling_of`, `teacher_of`, `friend_of`, `rival_of`, `member_of`, `family_member_of`, `sect_member_of`, `school_member_of`, `citizen_of`, `affiliated_with`, `part_of`, `subgroup_of`, `located_in`, `owns`, `uses`, `learned`, `knows_about`, `alter_ego_of`, `disguised_as`.

Use `part_of`, `subgroup_of`, and `located_in` for evidence-backed hierarchy. A family, sect, school, faction, nation, organization, or place may have several parents; no field implies exclusive membership. Use the more specific character membership predicates when the text supports them. `member_of` is the transparent fallback, not a reason to collapse family, school, nation, and faction into one reader-facing group. Direct relations and inherited ancestors are distinguished in derived views, and current versus historical membership follows the relation validity interval.

## Item roles

`item_roles` is the explicit temporal authority for who owns, holds, uses, or safeguards an item. Legacy graphs may derive equivalent roles from `relations` and `possession` state changes, but new extraction should write role records whenever the distinction matters.

Required: `id`, `item_id`, `entity_id`, `role`, `valid_from`, `action`, `evidence_ids`, `confidence`. Optional: `valid_to`, `reason`, `cause_event_id`, `notes`.

`role` is one of `owner`, `holder`, `user`, `custodian`. `action` is one of `gained`, `lost`, `transferred`, `confirmed`. A transfer closes the former holder episode and opens the recipient episode; it never changes legal ownership unless the text says so. Current ownership and possession are derived at a chapter, never guessed from names or summaries.

## State changes

Required: `id`, `entity_id`, `facet`, `action`, `chapter`, `before`, `after`, `reason`, `evidence_ids`, `confidence`.

Optional: `target_id`, `cause_event_id`, `end_chapter`, `notes`.

Facets include `attribute`, `level`, `skill`, `possession`, `identity`, `title`, `health`, `location`, `affiliation`, `relationship`, `knowledge`, `goal`, and `emotion`.

Actions include `gained`, `lost`, `changed`, `transferred`, `upgraded`, `downgraded`, `sealed`, `unsealed`, `damaged`, `repaired`, `learned`, `forgotten`, `joined`, `left`, `revealed`, and `concealed`.

Use `confidence` values `explicit`, `inferred`, or `uncertain`. `before` and `after` may be strings, numbers, booleans, objects, or null, but must not be equal.

## Level axes

Ranked progression is book-agnostic and must not be modelled as loose prose inside `attribute`. Any system where a character, skill, organization, or other entity advances through named or numbered tiers gets its own `level_axis` entity: cultivation or power level, profession or craft grade, official rank, military rank, mastery tier, organizational rank, exam grade, and so on.

### `level_axis` entity

Required: `id`, `type` (`level_axis`), `name`, `first_chapter`, `evidence_ids`.

Useful optional fields: `aliases`, `summary`, `system_key`, `attributes`, `current_state`, `tags`. `system_key` is a stable book-local identifier for compatibility (for example `cultivation-main`), unchanged when the source later reveals a new label or tier. Put the axis definition in `attributes`, using reader-facing keys so no internal English key reaches the dashboard or the AI text: `{"单位": "级", "下限": 1, "上限": 99, "越高越强": true, "档位": [{"名称": "第一境", "区间": [1, 10]}, {"名称": "第二境", "区间": [11, 20]}]}`. A free-form tier rule that is not a range goes in `分级依据` instead of `档位`. An axis is a world object, so it is created once per book and referenced by every change on it.

Before creating an axis for unfamiliar wording, retrieve existing axes and compare `system_key`, governing rule, unit, neighboring tiers, and explicit conversions. If compatible, append the new tier/alias and evidence to the existing axis. Two axes with the same `system_key` are invalid. Create a new axis only when the scale is genuinely incomparable; translations and later-revealed tiers do not create a new system.

Use the `axis_` ID prefix: `axis_cultivation_level`, `axis_soul_engineer_grade`.

### Level changes

A level change is a normal `state_change` with `facet: "level"` and `target_id` pointing at the `level_axis` entity. `before` and `after` describe the value on that axis and must take one of these shapes:

- a number, when the axis is purely numeric (`before: 11, after: 12`);
- an object `{"value": <number|null>, "label": "<in-world wording>"}`, when the axis has both a numeric position and its own terminology (`{"value": 12, "label": "十二级巅峰"}`);
- an object with `"value": null` and only a `label`, when the axis has named tiers but no usable number (`{"value": null, "label": "入微"}`).

`value` is the machine-readable position used for comparison and for drawing a level curve; higher means more advanced unless the axis says otherwise. `label` is what a reader sees. Keep the axis' own wording in `label` rather than translating it.

Rules:

- One axis per distinct progression system. Never merge two systems into one axis even when they advance together, and never split one system into several axes.
- Record **every** evidenced level change, including small ones and ones only mentioned in passing. Missing an intermediate step breaks the level curve and hides a gain.
- A restatement of the current level with no change is not a change record. Do not invent a change just because a level is mentioned again.
- When a level is first established with no prior baseline, use `before: null` and action `gained`.
- When the text only implies the change occurred between two chapters, use `confidence: "inferred"` and say so in `reason`; when a value is the narrator's or a character's estimate, use `"uncertain"`.
- Distinguish a level change from a stage or tier label derived from it: if the underlying number does not move, the tier wording belongs in `label`, not in a second change record.
- Never write a level into `attributes` or `current_state` as free text and also as a level change; the level change is the single source of truth.
- Axis `attributes` keys and tier names are reader-facing. Write them in the book's own language and never emit internal English keys (`unit`, `min`, `max`, `higher_is_more_advanced`, `tiers`, `range`, `label`, `definition`) — the dashboard and the AI text render exactly what is stored here, so an English key becomes visible English in the delivered artifact.
- Only the `before`/`after` value shape (`{"value": …, "label": …}`) keeps its English machine keys; that shape is never printed raw and is always rendered through the localized level formatter.

## Level conversions

`level_conversions` is an optional top-level array holding the places where **the text itself lines two ranked systems up**. A book that runs several systems at once — a star scale, a hunter grade, a named rank ladder, a skill's layer count — usually states how they compare, and those statements are the only way a reader can answer "what is a 修罗将军 in 星". Left in prose they are invisible: the level warehouse can list every ladder and still not convert between them.

Required: `id`, `chapter`, `from`, `to`, `relation`, `description`, `evidence_ids`. Optional: `confidence`, `notes`.

```json
{
  "id": "lc_f31_001", "chapter": 309,
  "from": {"axis_id": "axis_xiuluo_rank", "label": "修罗王", "value": 5},
  "to":   {"axis_id": "axis_star_rank", "label": "十星", "value": 10},
  "relation": "equals",
  "description": "原文称修罗王有十颗星的实力，明显突破人阶走入地阶。",
  "confidence": "explicit", "evidence_ids": ["ev_f31_012"]
}
```

**An endpoint always names its `axis_id` and must pin something.** `value` is a point on that axis; `range` is a band (`[10, 18]` for 地阶), for when the text only fixes a band; `label` keeps the book's own wording. An endpoint carrying only `axis_id` says nothing and is rejected. Write `value` in the same numeric space the axis' own `level` changes use, or the conversion cannot be compared against a character's position.

**`relation` says how the two sides compare, and it is not decoration.** `equals` is the same scale (「与修仙者的星级同尺」); `approximately_equals` is the text hedging (「大概有九颗星的实力」); `at_least` is a floor rather than an equivalence (「第三掌山岚按常理须四星方可修炼」) and is the only **directional** relation — `from` requires `to`, never the reverse; `band_equivalent` lines up only at tier granularity because one side is named tiers with no numbers (「A 级猎人相当于修仙者中的地阶」); `scales_with` is a stated ratio rather than a value (「每修炼到三颗星璇即打开一层心法」).

Rules:

- One record per stated comparison. A sentence that names three pairings is three records.
- `description` states what the text says, in the text's own terms. Do not compute the missing pairs — the renderer derives one-hop conversions itself and marks them as derived.
- Every record carries evidence. A conversion with no quotation is an inference, and an inference must be labelled `confidence: "inferred"` at minimum, or left out.
- Never record a conversion the text does not support merely because two ladders look similar. Two axes both saying "higher is stronger" are not thereby comparable.
- Keep the direction as the text gives it. If the text states 甲 needs 乙, the record goes `from` 甲 `to` 乙 with `at_least`; reversing it silently turns a floor into a ceiling.
- An axis pair may appear more than once with different values — a ladder that is pinned at several rungs is several records, and that is what makes the correspondence usable.
- Where the text states a ratio but the resulting mapping is contested, still record it and set `confidence: "uncertain"`, with the conflict named in `description` and open in `review_issues`. An unusable-looking conversion that is honestly limited beats a silent gap.
- Conversion `description` is full-range analyst prose and may name later chapters inside the analyzed range. The selected snapshot chapter affects only whether a conversion is considered dynamically established by then; it does not censor the complete reference entry.

## Romance routes

Use `romance_routes` for evidence-backed romantic or ambiguous milestones involving a protagonist. Do not overload ordinary relation prose with milestone dates.

Required: `id`, `protagonist_id`, `character_id`, `status`, `inclusion_basis`, `consent_context`, `first_meeting_chapter`, `first_meeting_evidence_ids`, `ambiguity_started_chapter`, `ambiguity_evidence_ids`, `confirmed_chapter`, `confirmed_evidence_ids`, `first_sex_chapter`, `first_sex_evidence_ids`, `confidence`, and `notes`.

`protagonist_id` must reference a `character`. `character_id` normally does too, but a harem book can give the protagonist a partner the source treats as a person while the graph types her as something else — a 妖宠 / 犬女 / 式神 who talks, is named, and initiates contact. For that case only, declare the type explicitly:

```json
{"id": "rr_xiaomi", "protagonist_id": "char_liu_yi", "character_id": "creature_xiaomi",
 "character_type": "creature", ...}
```

`validate_graph.py` then records a `non_character_romance_partner` **observation** naming the type instead of a `bad_character_ref` error. The declaration is required on purpose: without it the reference is still an error, so a genuine typo cannot hide behind the allowance. Route inclusion never implies consent or confirmed romance.

Statuses: `provisional_intimate`, `ambiguous`, `one_sided`, `mutual_interest`, `confirmed_relationship`, `spouse`, `betrothed`, `coerced_or_forced`, `accidental_or_contextual`, `excluded_nonromantic`, `ended`, `uncertain`.

Inclusion bases: `romantic_ambiguity`, `intimate_contact`, `explicit_intimate_proposal`, `repeated_attachment`, `intimate_psychology`, `marriage`, `betrothal`, and `spouse_relation`. Consent contexts: `mutual`, `one_sided`, `accidental`, `coerced`, `forced`, `ability_induced`, `altered_state`, `uncertain`. Use the closest primary context and explain mixed cases in `notes`.

- When the user's requested harem rule includes any intimate act, add a route for an evidence-backed kiss, embrace, clearly intimate touch, or explicit intimate proposal even if it is accidental, coerced, ability-induced, or performed in an altered state. Record that distinction in `inclusion_basis` and `consent_context`; route inclusion never implies consent or confirmed romance.
- Under a broad intimate/harem rule, any protagonist-linked intimate act, repeated attachment, explicit intimate proposal, marriage/betrothal/spouse relation, or text-described intimate longing/jealousy/tension creates at least a `provisional_intimate` route candidate. A candidate may later be reclassified as one-sided, contextual, coerced, excluded-nonromantic, or confirmed; it must not disappear merely because mutual romance is unproven.
- First meeting and the first qualifying ambiguity/contact require exact evidence. `ambiguity_started_chapter` is the first qualifying chapter under the active inclusion rule. Relationship confirmation remains `null` unless the text establishes mutual confirmation; one-sided pursuit or intimate contact alone is not confirmation.
- Milestone order must be chronological: first meeting ≤ first ambiguity ≤ relationship confirmation ≤ first explicit sexual relationship, ignoring null milestones.

## Intimate acts

`intimate_acts` records each specific intimate or sexual act. It is optional, and a graph without it is valid — but it is the only place that answers *what happened, between whom, and was it consensual*.

The reason it exists as its own array: `events[].type` has exactly one value for this territory, `intimacy`, and it is the right granularity for an event list and the wrong one for a harem book. A kiss, a grope, oral sex, intercourse, and rape all collapse into that one label. `romance_routes.first_sex_chapter` is worse for the purpose: it records the *date* of one act and never its nature. A run that keeps only those two fields can say "something intimate happened in chapter 96" and nothing else.

Required: `id`, `chapter`, `act_type`, `description`, `evidence_ids`, `confidence`, and **at least one** of `initiator_ids` / `recipient_ids` / `observer_ids`.

Recommended: `consent`, `nudity`.

Optional: `initiator_ids`, `recipient_ids`, `observer_ids`, `nudity_note`, `ejaculation_site`, `location_id`, `cause_event_ids`, `tags`, `notes`.

Take `act_type` from `scripts/intimacy_types.py`, which holds the set plus the synonym folds; both renderers take their labels from the same module, so the set has exactly one definition. Write `act_type`, never `act` or `intimacy_type`.

| Group | `act_type` values |
|---|---|
| 观看与暴露 | `witness_nudity`, `witness_intimacy`, `voyeurism`, `exposure`, `peeping_attempt` |
| 触碰 | `embrace`, `kiss`, `groping_breast`, `groping_buttock`, `groping_genital`, `fondling`, `stripping` |
| 性行为 | `manual_stimulation`, `oral_sex`, `intercourse`, `anal_intercourse`, `masturbation`, `ejaculation` |
| 强迫与侵害 | `sexual_harassment`, `molestation`, `attempted_rape`, `rape` |
| 其他 | `sexual_proposition`, `other_intimate` |

**Participant roles are what make the record usable.** `initiator_ids` names who acted, `recipient_ids` who was acted on, `observer_ids` who saw it. Fill every role the text supports; leave a role off rather than guessing. `observer_ids` is the one that gets forgotten and it is the only thing that keeps a witnessed scene in the graph at all — a character who walks in on a couple takes part in `witness_intimacy` as an observer, and without that field the scene has no participant and cannot exist.

**`consent` is required in practice, not optional in spirit.** Values come from `CONSENT_CONTEXTS` in `intimacy_types.py`: `mutual`, `one_sided`, `accidental`, `coerced`, `forced`, `ability_induced`, `altered_state`, `uncertain`. `coerced` is pressure, threat, or unequal power; `forced` is violence or physical inability to resist. They are separate on purpose: a reader filtering for non-consensual acts needs both, and collapsing them hides the difference between being talked into something and being held down. Use `uncertain` when the text does not say — and add a `review_issues` entry rather than defaulting to `mutual`.

`nudity` is a boolean: did the act involve anyone being naked or partially unclothed. Put *who and what* in `nudity_note`, not in `description` alone, so the panel can show it as a facet.

`ejaculation_site` is one of `internal`, `oral`, `external`, `on_body`, `none`, `unknown`. Only fill it when the text supports it; leave the field off otherwise. Do not infer it.

Rules:

- **One record per act, not per scene.** A chapter where a character is kissed, then groped, then raped is three records. Merging them destroys the escalation that the run exists to capture.
- **`description` says how it happened.** "两人发生了关系" is not a description. Name who initiated, what was done to whom, with what, and where it led. Two to four sentences, objective, no euphemism and no judgement.
- **Record the attempt separately.** `attempted_rape` is not `rape` with a qualifier; it is a different act with different consequences and its own evidence.
- **Witnessing counts.** Seeing someone naked, walking in on a couple, or spying through a window is an act with the observer as participant. Do not drop it because "nothing physical happened".
- **An act is not a relationship.** Recording a rape does not upgrade a `romance_routes.status`, and recording mutual sex does not confirm one. Keep the two arrays independent and let `consent_context` carry the distinction.
- **Keep the act's own evidence.** Every record needs its own `evidence_ids` with exact quotations; do not point at a neighbouring event's evidence.
- Non-consensual acts are recorded the same way as any other. Do not soften `act_type` or `description` to protect a protagonist; the graph is a record of the text, not a defence of it.

## Character traits

`character_traits` records what a character *looks like, acts like, and sounds like* — one assertion per row, dated by the chapter it first holds.

Optional **as a protocol**: a graph without it is structurally valid, and every validator will pass. The pipeline, however, treats it as expected non-empty — `required_fields.EXPECTED_NON_EMPTY` lists it, and `build_results_facts.py --check` fails when it is zero. A book with named characters that yields zero rows means the extraction never happened, not that the book has no traits; the two cases are indistinguishable from the count alone, which is exactly why the declaration exists. A run that genuinely has none writes `<run>/expected_kinds.json` with `{"character_traits": false}` — an explicit, auditable exemption rather than a silent one.

Why it is not `entities[].attributes`: those are scalars, and `merge_value` keeps the **last** fragment's spelling. A trait that changes — hair cut short in chapter 40, a scar taken in chapter 30, a dialect that softens once the character trusts someone — overwrites the earlier description instead of joining it, and the reader loses the version that held for the first thirty chapters. A scalar also has nowhere to put *when*, which is the whole point.

Required: `id`, `entity_id`, `facet`, `statement`, `chapter`, `evidence_ids`, `confidence`.

Optional: `status`, `tags`, `notes`.

`facet` comes from `scripts/character_traits.py`, which holds the set and the synonym folds; both renderers take their labels from the same module.

| facet | 内容 |
|---|---|
| `appearance` | 体貌、发型、穿着风格、随身标志物 |
| `personality` | 性情、处事方式、价值取向 |
| `speech` | 语气、语速、口头禅、称谓习惯、方言 |
| `habit` | 习惯动作、癖好、下意识反应 |

**Write a baseline, then only the changes.** The point of `chapter` is that most chapters need nothing: record one row per facet when the character first appears, and a new row *only* where the text actually shifts something. A renderer takes the newest row with `chapter <= N`, so a trait that never changes is never restated — and still shows up in every chapter view. The habit this prevents is the opposite one: re-describing the same appearance every ten chapters, which inflates the graph and makes a real change indistinguishable from noise.

**Do not build a `supersedes` chain.** Parallel passes each see ten chapters, so a chain crossing a fragment boundary breaks, and repairing it costs more than it explains. Ordering by `chapter` is enough, and it lets one wrong row be deleted and rewritten without touching its neighbours.

**Evidence may not come from a later chapter than the row's own.** A row dated chapter 1 asserts "this holds from chapter 1 on"; citing chapter 37 to support it is proving the premise with its consequence. This is a temporal-evidence error even though the full-range display allows spoilers. When later text supplies better evidence, add a second row at that chapter instead. The same goes for two rows sharing a `(entity, facet, chapter)`: they render side by side as two competing assertions.

`status` covers the case where a trait stops applying *and nothing replaces it* — 断臂之后「惯用右手」失效，而新事实只是「只剩左手」，不是一句性格描述。Values: `current` (default), `superseded`, `uncertain`.

`statement` must be a sentence a reader can picture, not a label. 「漂亮」adds nothing the entity `summary` has not already said; 「个子高，常穿深色外套，右眉有一道旧疤」is something they can see. Validation rejects a `statement` under 5 characters, and a bare 6-character word carrying no punctuation.

## Chapter summaries

`chapter_summaries` holds one row per analysed chapter: what happened in it, at the length of a paragraph a reader can scan. It is optional, and a graph without it is valid.

Everything else in the graph is indexed by *entity*. A reader moving forward through the book — or a later pass deciding what it may assume — is asking a chapter-shaped question. `chapters.jsonl` has titles and line ranges but no content, and `events` are selective by design: a chapter of dialogue and character work may produce no event at all and would otherwise be invisible.

Required: `id`, `chapter`, `summary`, `evidence_ids`.

Optional: `title`, `key_event_ids`, `notable_character_ids`, `tags`, `arc_ids`, `dominant_arc_id`, `narrative_phase`.

Write `summary` in three to six sentences covering the chapter's own arc, not a list of names. `title` mirrors `chapters.jsonl` when the source has one — never invent a chapter title. `key_event_ids` points at the `events` recorded for that chapter, which is what keeps a summary attached to the graph instead of floating beside it.

One row per chapter, `chapter` unique within the graph. A non-narrative chapter (作者的话、公告、重复章节) gets a row saying so rather than being skipped in silence, so the summary count stays comparable with the chapter count.

`arc_ids` contains every story arc active in the chapter. It is many-to-many: overlapping or nested arcs are all retained. `dominant_arc_id`, when present, must also occur in `arc_ids` and is only a “主显示剧情（非排他）” hint. `narrative_phase` uses the same phase vocabulary as the focused arc and does not erase other active phases.

## Story arcs

`story_arcs` is the evidence-backed editorial timeline for continuous, recurring, nested, or parallel plots. It is optional for legacy graphs but is the formal source for the dashboard's 大剧情／子剧情／并行剧情 lanes.

Required: `id`, `title`, `chapter_start`, `status`, `evidence_ids`.

Required keys whose values may be null or empty arrays: `chapter_end`, `parent_arc_id`, `phase`, `event_ids`, `entity_ids`, `turning_point_ids`.

Ranges are inclusive. `chapter_end: null` means the arc is still open within the analyzed boundary; no end is invented. `parent_arc_id` creates a nested sub-arc and must resolve without cycles. Independent simultaneous plots have no parent and may overlap freely. `event_ids` and `turning_point_ids` reference events; `entity_ids` references every directly participating person, place, organization, or item without making their membership exclusive.

Statuses are `open`, `active`, `paused`, `resolved`, and `uncertain`. Phases are `setup`, `development`, `escalation`, `turning_point`, `climax`, `resolution`, `aftermath`, `interlude`, `recurring`, and `uncertain`; a null phase is allowed when the text supports the interval but not a finer phase. Labels are localized at render time.

## Foreshadowing

Required: `id`, `label`, `status`, `planted_chapter`, `observation`, `interpretation`, `related_entity_ids`, `evidence_ids`, `confidence`.

Optional: `progression`, `payoff_chapter`, `payoff_event_id`, `alternative_interpretations`. `progression` entries contain `chapter`, `kind`, `description`, and `evidence_ids`.

Statuses: `suspected`, `open`, `progressed`, `partially_resolved`, `resolved`, `false_lead`. Prefer `suspected` when authorial intent is uncertain.

`confidence` uses the same three values as state changes: `explicit`, `inferred`, `uncertain`. Do not reuse the `status` words here — `suspected` is a status, not a confidence, and a pass that writes it renders as 未分类. The allowed values live only in the state-change section otherwise, so read them there rather than inventing a scale such as `high` / `medium` / `low`.

## Review issues

Store unresolved ambiguity instead of hiding it. Each issue has `id`, `severity`, `category`, `description`, `related_ids`, `chapter`, and optional `evidence_ids` and `resolution`.

`severity` is one of `info`, `warning`, `error`.

`related_ids` is a list of record IDs and may name **any** record, not only an entity: an issue about six foreshadowings names the six foreshadowings, one about a state change names the change, one about a relation names the relation. Validation accepts any ID the graph defines. That makes it a rendering obligation rather than a data one — a reader-facing surface must resolve `fs_*` / `ev_*` / `sc_*` / `rel_*` to their own label instead of printing the raw ID, and must also rewrite known IDs that appear inside `description` prose.

Write `description` for a reader. It is displayed verbatim in the 待核问题 panel and in the AI text, so do not name a record by its internal ID inside a sentence — say 辉煌废弃工厂, not `location_huihuang_feichang`.

Typical categories: `alias_conflict`, `contradiction`, `missing_cause`, `weak_evidence`, `time_ambiguity`, `possible_foreshadowing`, `coverage_gap`.

## Book profile, coverage, corrections, and approved snapshots

These files live beside `graph.json`; they are workflow contracts rather than competing fact stores.

- `book-profile.json` identifies the edition/source, genre, protagonist IDs, chapter policy, relationship symmetry overrides, romance inclusion rule, item-role policy, locale/display vocabulary version, and a deterministic `profile_sha256`. Rendering and continuation use this file instead of scattering book-specific decisions across prompts.
- `coverage-ledger.json` records one row per prepared chapter with `chapter`, `status` (`planned`, `analyzed`, `validated`, `rendered`, `excluded`), fragment IDs, record counts, quote-audit status, optional non-narrative reason, gap/review IDs, and the snapshot ID. Prepared chapters never become analyzed merely by appearing in this ledger.
- `corrections.jsonl` is append-only. Each correction records `correction_id`, `parent_snapshot_id`, `target_record_id`, `operation` (`replace`, `append`, `retract`, `rekey`), `before_hash`, `after_hash`, `reason`, `evidence_ids`, declaring fragment, application time, and toolchain fingerprint. Apply corrections by deterministic replay with dry-run support; never hand-edit a built `graph.json` and call that history.
- `snapshot-manifest.json` identifies an immutable approved build with `snapshot_id`, optional `parent_snapshot_id`, approval status/time/actor, chapter range, source and graph hashes, validation hash, toolchain fingerprint, book-profile hash, and coverage-ledger hash. `valid: true` is validation, not approval. Renderers bind to the manifest when present and report clearly when the graph is only a draft.

The shared `scripts/snapshot.py` computes derived chapter views. A snapshot chapter filters dynamic state, relationship validity, item roles, and level values; it does **not** hide full-range summaries, aliases, later evidence, events, or foreshadowing payoffs. The derived snapshot is disposable and must be reproducible from `graph.json` plus the workflow contracts above.
