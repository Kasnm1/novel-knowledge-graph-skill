"""Shared test fixtures, so test modules no longer import each other."""
from __future__ import annotations

FUTURE = "FUTURE_MARKER_777"


def fixture_graph() -> dict:
    evidence = [{"id":f"e{i}","chapter":i,"quote":f"chapter {i} evidence text long enough","source_line_start":1,"source_line_end":1} for i in range(1,10)]
    return {
        "metadata":{"title":"final-delivery-fixture","chapter_start":1,"chapter_end":9,"analyzed_chapters":list(range(1,10)),"protagonist_ids":["hero"],"alias_first_chapter":{"hero":{FUTURE:8}},"summary_first_chapter":{"hero":8},"attribute_first_chapter":{"hero":{"future_rank":8}}},
        "entities":[
            {"id":"hero","type":"character","name":"最终正式名","name_first_chapter":8,"name_history":[{"valid_from":1,"valid_to":7,"name":"早期名"},{"valid_from":8,"name":"最终正式名"}],"aliases":[FUTURE],"first_chapter":1,"summary":FUTURE,"attributes":{"future_rank":FUTURE},"attribute_history":[{"id":"ah1","chapter":2,"key":"realm","value":"early"}],"tags":["protagonist"],"evidence_ids":["e1"]},
            {"id":"ally","type":"character","name":"同伴","first_chapter":1,"evidence_ids":["e1"]},
            {"id":"skill","type":"skill","name":"身法","first_chapter":1,"categories":[{"id":"movement"}],"evidence_ids":["e1"]},
            {"id":"item","type":"item","name":"灵石","first_chapter":1,"tags":["rarity/common","supply/repeatable"],"evidence_ids":["e1"]},
            {"id":"loc","type":"location","name":"城","first_chapter":1,"evidence_ids":["e1"]},
            {"id":"world","type":"location","name":"世界","first_chapter":1,"evidence_ids":["e1"]},
        ],
        "events":[
            {"id":"ev2","type":"encounter","chapter":2,"title":"早期事件","description":"早期","participant_ids":["hero","ally"],"location_id":"loc","evidence_ids":["e2"]},
            {"id":"ev8","type":"payoff","chapter":8,"title":FUTURE,"description":FUTURE,"participant_ids":["hero"],"evidence_ids":["e8"],"payoff":{"kind":"reversal","setup_ids":[]}},
        ],
        "relations":[
            {"id":"rel_loc","source_id":"loc","target_id":"world","relation_type":"located_in","valid_from":1,"status":"active","evidence_ids":["e1"]},
            {"id":"rel_skill","source_id":"hero","target_id":"skill","relation_type":"uses","valid_from":8,"status":"active","evidence_ids":["e8"]},
        ],
        "state_changes":[
            {"id":"q2","entity_id":"hero","target_id":"item","facet":"inventory_quantity","action":"gained","chapter":2,"before":0,"after":1,"reason":"获得","evidence_ids":["e2"],"confidence":"explicit"},
            {"id":"q8","entity_id":"hero","target_id":"item","facet":"inventory_quantity","action":"gained","chapter":8,"before":1,"after":99,"reason":FUTURE,"evidence_ids":["e8"],"confidence":"explicit"},
        ],
        "item_roles":[{"id":"ir2","item_id":"item","entity_id":"hero","role":"holder","valid_from":2,"action":"gained","cause_event_id":"ev2","evidence_ids":["e2"],"confidence":"explicit"}],
        "commitments":[{"id":"cm","kind":"promise","promisor_ids":["hero"],"counterparty_ids":["ally"],"terms":"会回来","created_chapter":1,"deadline_chapter":None,"deadline_story_time":None,"stake_ids":[],"status":"fulfilled","resolved_chapter":8,"resolution":FUTURE,"observations":[{"chapter":8,"status":"fulfilled","evidence_ids":["e8"]}],"evidence_ids":["e1"],"confidence":"explicit"}],
        "style_observations":[{"id":"voice8","entity_id":"hero","chapter":8,"observation":FUTURE,"evidence_ids":["e8"]}],
        "chapter_summaries":[{"id":"cs2","chapter":2,"summary":"early summary","evidence_ids":["e2"],"pov_entity_ids":["hero"],"scene_count":1,"cliffhanger_type":"none"},{"id":"cs8","chapter":8,"summary":FUTURE,"evidence_ids":["e8"],"pov_entity_ids":["hero"],"scene_count":1,"cliffhanger_type":"reversal"}],
        "evidence":evidence,"romance_routes":[],"intimate_acts":[],"level_conversions":[],"character_traits":[],"story_arcs":[],"foreshadowing":[],"review_issues":[],
    }


AUDIT_FUTURE = "CODE_AUDIT_FUTURE_991"


def temporal_graph() -> dict:
    return {
        "metadata": {
            "title": "audit",
            "chapter_start": 1,
            "chapter_end": 10,
            "analyzed_chapters": list(range(1, 11)),
            "name_first_chapter": {"hero": 1, "ally": 1},
            "summary_first_chapter": {"hero": 8},
            "attribute_first_chapter": {"hero": {"rank": 8}},
        },
        "entities": [
            {
                "id": "hero",
                "type": "character",
                "name": "Hero",
                "name_history": [{"chapter": 1, "name": "Hero"}],
                "first_chapter": 1,
                "summary": AUDIT_FUTURE,
                "attributes": {"rank": AUDIT_FUTURE},
                "evidence_ids": ["e1"],
            },
            {"id": "ally", "type": "character", "name": "Ally", "name_first_chapter": 1, "first_chapter": 1, "evidence_ids": ["e1"]},
        ],
        "events": [],
        "relations": [
            {
                "id": "r1",
                "source_id": "hero",
                "target_id": "ally",
                "relation_type": "friend_of",
                "valid_from": 1,
                "valid_to": 9,
                "status": "ended",
                "observations": [
                    {"chapter": 1, "status": "active", "evidence_ids": ["e1"]},
                    {"chapter": 9, "status": "ended", "evidence_ids": ["e9"]},
                ],
                "evidence_ids": ["e1", "e9"],
            }
        ],
        "state_changes": [],
        "romance_routes": [
            {
                "id": "rr1",
                "protagonist_id": "hero",
                "character_id": "ally",
                "status": "spouse",
                "inclusion_basis": "romantic_ambiguity",
                "consent_context": "unknown",
                "first_meeting_chapter": 1,
                "first_meeting_evidence_ids": ["e1"],
                "ambiguity_started_chapter": 3,
                "ambiguity_evidence_ids": ["e3"],
                "confirmed_chapter": 8,
                "confirmed_evidence_ids": ["e8"],
                "first_sex_chapter": None,
                "first_sex_evidence_ids": [],
                "notes": "",
                "confidence": "explicit",
            }
        ],
        "intimate_acts": [],
        "level_conversions": [],
        "character_traits": [],
        "chapter_summaries": [],
        "story_arcs": [],
        "item_roles": [],
        "commitments": [
            {
                "id": "c1",
                "kind": "promise",
                "promisor_ids": ["hero"],
                "counterparty_ids": ["ally"],
                "terms": "return",
                "created_chapter": 2,
                "deadline_chapter": None,
                "deadline_story_time": None,
                "stake_ids": [],
                "status": "fulfilled",
                "resolved_chapter": 8,
                "resolution": "done",
                "observations": [{"chapter": 8, "status": "fulfilled", "evidence_ids": ["e8"]}],
                "evidence_ids": ["e2", "e8"],
                "confidence": "explicit",
            }
        ],
        "foreshadowing": [],
        "evidence": [
            {"id": f"e{chapter}", "chapter": chapter, "quote": f"evidence chapter {chapter} text long enough", "source_line_start": 1, "source_line_end": 1}
            for chapter in range(1, 11)
        ],
        "review_issues": [],
    }
