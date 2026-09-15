#!/usr/bin/env python3
"""Run the historical fragment gate plus expansion-specific structural checks."""
from __future__ import annotations

import json
import sys

from controlled_vocab import (
    CLIFFHANGER_TYPES, COMBAT_KINDS, COMBAT_OUTCOMES, COMBAT_RESOLUTIONS,
    COMMITMENT_KINDS, COMMITMENT_STATUSES, CONCEPT_CATEGORIES,
    INFORMATION_MODES, PAYOFF_KINDS, SKILL_CATEGORIES, category_ids,
)
from schema_expansion import install_required_fields


def validate_fragment_extensions(fragment: dict) -> list[str]:
    errors: list[str] = []
    for c in fragment.get("commitments", []) if isinstance(fragment.get("commitments"), list) else []:
        if not isinstance(c, dict):
            errors.append("commitments 中存在非对象记录")
            continue
        rid = c.get("id", "<无 id>")
        if c.get("kind") not in COMMITMENT_KINDS:
            errors.append(f"{rid}: commitment.kind 不合法：{c.get('kind')!r}")
        if c.get("status") not in COMMITMENT_STATUSES:
            errors.append(f"{rid}: commitment.status 不合法：{c.get('status')!r}")
        for field in ("promisor_ids", "counterparty_ids", "stake_ids", "evidence_ids", "observations"):
            if field in c and not isinstance(c.get(field), list):
                errors.append(f"{rid}: commitment.{field} 必须是数组")
    for event in fragment.get("events", []) if isinstance(fragment.get("events"), list) else []:
        if not isinstance(event, dict):
            continue
        rid = event.get("id", "<无 id>")
        combat = event.get("combat")
        if combat is not None:
            if not isinstance(combat, dict):
                errors.append(f"{rid}: combat 必须是对象")
            else:
                if combat.get("kind") is not None and combat.get("kind") not in COMBAT_KINDS:
                    errors.append(f"{rid}: combat.kind 不合法")
                if combat.get("resolution") is not None and combat.get("resolution") not in COMBAT_RESOLUTIONS:
                    errors.append(f"{rid}: combat.resolution 不合法")
                participants = combat.get("participants")
                if not isinstance(participants, list) or not participants:
                    errors.append(f"{rid}: combat.participants 必须是非空数组")
                else:
                    for participant in participants:
                        if not isinstance(participant, dict) or participant.get("outcome") not in COMBAT_OUTCOMES:
                            errors.append(f"{rid}: combat participant/outcome 不合法")
        info = event.get("information")
        if isinstance(info, dict) and info.get("mode") is not None and info.get("mode") not in INFORMATION_MODES:
            errors.append(f"{rid}: information.mode 不合法")
        payoff = event.get("payoff")
        if isinstance(payoff, dict) and payoff.get("kind") is not None and payoff.get("kind") not in PAYOFF_KINDS:
            errors.append(f"{rid}: payoff.kind 不合法")
    for entity in fragment.get("entities", []) if isinstance(fragment.get("entities"), list) else []:
        if not isinstance(entity, dict):
            continue
        allowed = SKILL_CATEGORIES if entity.get("type") == "skill" else CONCEPT_CATEGORIES if entity.get("type") == "concept" else None
        if allowed is not None:
            for category in category_ids(entity.get("categories")):
                if category not in allowed:
                    errors.append(f"{entity.get('id')}: categories 包含未知值 {category}")
    for summary in fragment.get("chapter_summaries", []) if isinstance(fragment.get("chapter_summaries"), list) else []:
        if not isinstance(summary, dict):
            continue
        if summary.get("cliffhanger_type") is not None and summary.get("cliffhanger_type") not in CLIFFHANGER_TYPES:
            errors.append(f"{summary.get('id')}: cliffhanger_type 不合法")
        if summary.get("scene_count") is not None and (
            not isinstance(summary.get("scene_count"), int) or isinstance(summary.get("scene_count"), bool) or summary.get("scene_count") < 0
        ):
            errors.append(f"{summary.get('id')}: scene_count 必须是非负整数")
    return errors


def main() -> int:
    install_required_fields()
    import check_fragment
    base = check_fragment.main()
    try:
        idx = sys.argv.index("--fragment")
        path = sys.argv[idx + 1]
        fragment = json.loads(open(path, "r", encoding="utf-8").read())
    except Exception as exc:
        print(f"扩展门禁无法读取 fragment：{exc}", file=sys.stderr)
        return 1
    errors = validate_fragment_extensions(fragment)
    print("== expansion fragment contract ==")
    for error in errors:
        print(f"  [ERROR] {error}")
    print(f"  结果：{len(errors)} error")
    return 1 if base or errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
