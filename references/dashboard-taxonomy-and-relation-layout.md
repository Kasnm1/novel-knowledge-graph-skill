# Dashboard taxonomy and relation layout

This contract is generic for every book. A book-specific vocabulary may supply labels, but examples from one novel must never become hard-coded global names.

## Appearance heat and relationship views

Do not expose appearance heat or mention count as a primary layout, ranking, or default sort. Relationship views start from a focal entity or selected set, show first-degree links by default, group links into typed lanes, collapse high-degree nodes, and provide list/table/tree fallbacks. Support filters for relation type, depth, chapter/as-of state, current validity, protagonist relevance, and category grouping. Preserve direction, evidence, validity interval, and conflict state.

## Canonical names and aliases

Keep the entity's canonical `name` separate from `aliases`, `titles`, `historical_names`, and `display_context`. When the text explicitly reveals a later or authoritative name, use it as the current reader-facing canonical name; preserve earlier names as aliases with chapter/evidence context. Historical timelines use the name valid at that chapter. Do not permanently concatenate names into a parenthetical form such as “A（B）” unless the source treats that as one stable name. Nicknames, cover names, titles, and identity masks remain separately labelled.

Name normalization never merges entities solely from spelling, surname, co-occurrence, or model intuition. Ambiguous identities remain candidates with `待核` until evidence supports a merge. A book-specific display vocabulary may choose local labels, but the generic Skill must not hard-code any book's names.

## Item categories

Items may have multiple evidence-backed category memberships. Default categories are 武器、防具／护具、饰品、奢侈品／珍藏、消耗品／药剂／丹药、资源／材料、书卷／秘籍／契约、交通／容器／住所性物件、信物／凭证、普通物品、待分类. Show one display-primary category plus additional category chips; retain function, owner, user, transfer, loss, use, and category evidence independently.

## Existing level systems

When new level wording appears, extend an existing compatible `level_axis` if the text places it in that system or explicitly relates it to that system. Do not create a new axis merely because a label is unfamiliar, translated differently, or appears later. Create a new axis only for a genuinely different scale, unit, governing rule, or incomparable progression. Explicit cross-system conversions are recorded; unstated equivalences are not calculated.

## Hierarchical places and powers

Represent places, families, sects, schools, clans, nations, organizations, and powers as parent/child sets that may overlap. Preserve direct versus inherited membership. Character detail separately exposes faction, family, sect/school, nation, current faction, historical faction, and identity/alter-ego memberships, with validity chapters and evidence.

## Human relationship categories

Make family, sibling, friend/ally, mentor/student, enemy/rival, romance/intimacy, faction/organization, item, and identity relations independently filterable. Do not collapse friends or siblings into a generic “人物关系” card. Reciprocal edges may render as one card while preserving both underlying directions.

## Broad intimate-route discovery

Keep `intimate_acts` (concrete behavior/proposal/context/evidence) separate from `romance_routes` (the broader route and stage). Under a broad harem/intimate tracking rule, create a `provisional_intimate` route candidate when protagonist-linked evidence shows any intimate behavior, repeated attachment, explicit intimate proposal, marriage/betrothal/spouse relation, or described intimate longing, jealousy, or relationship tension.

Use distinct stages for `provisional_intimate`, `one_sided`, `mutual_interest`, `confirmed_relationship`, `spouse`, `betrothed`, `coerced_or_forced`, `accidental_or_contextual`, and `excluded_nonromantic`. One act does not prove mutual love or consent, but it does require a route candidate or an evidence-backed exclusion; it must not disappear because no `intimacy` event was emitted. Medical, rescue, accidental, coerced, and witnessed contact remains visible as an act and may be contextual rather than romantic.

## Protagonist-linked relation labels

Do not show a protagonist-linked person or object as merely “未分类” when an evidence-backed predicate exists. Map it to reader-facing classes such as 赠予／馈赠、保护／救助、伤害／攻击、敌对／追杀、师徒／教导、家族／婚姻／婚约、朋友／盟友、感情／亲密、物品持有／转交、身份／秘密、事件共同参与者. Keep the original predicate and evidence visible. “其他” is a transparent fallback with review status, not a silent sink.

## Entity detail panel

Opening any character, item, place, or faction shows canonical name/aliases, all category memberships, hierarchy memberships, current and historical state, relationship categories, romance/intimacy stage, item/skill history, story arcs, evidence, and unresolved issues. Separate `当前有效／历史／待核`; never hide additional memberships behind a single generic label.
