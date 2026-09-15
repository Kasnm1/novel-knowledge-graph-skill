from __future__ import annotations

DOMAIN_STORAGE: dict[str, tuple[str, ...]] = {
    "combat": ("events.combat", "state_changes"),
    "resources": ("entities:item", "item_roles", "state_changes"),
    "world": ("entities:location", "relations:located_in", "relations:part_of", "relations:controlled_by"),
    "skills": ("entities:skill", "relations", "state_changes"),
    "commitments": ("commitments",),
    "favors": ("relations:owes_favor_to",),
    "knowledge": ("entities:concept", "state_changes:knowledge", "events.information"),
    "mortality": ("events.mortality", "state_changes:health"),
    "economy": ("events.transaction", "state_changes:wealth"),
    "romance": ("romance_routes", "intimate_acts", "relations"),
    "foreshadowing": ("foreshadowing", "events.payoff"),
    "narrative": ("chapter_summaries", "style_observations"),
}


def canonical_storage_for(domain: str) -> tuple[str, ...]:
    return DOMAIN_STORAGE.get(domain, ())
