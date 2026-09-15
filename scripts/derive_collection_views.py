#!/usr/bin/env python3
"""Derive auditable dashboard collection views from a novel graph.

``dashboard-views.json`` is a presentation/query manifest, not a second fact
store.  This module reads it together with ``graph.json`` and produces a
stable, JSON-serializable result.  It never changes either input.

Expressions deliberately form a small set algebra:

* ``{"collection": "id"}`` references another saved collection;
* ``{"and": [...]}``, ``{"or": [...]}``, and ``{"not": expr}`` combine sets;
* ``{"type": "character"}`` filters entity kinds;
* ``{"relation": ...}`` selects endpoints of evidence-backed relations;
* ``{"arc": "arc_id"}`` selects an arc's declared entity members;
* ``{"active_at": chapter}`` filters temporally active entities, or wraps a
  nested expression with ``{"active_at": {"chapter": 12, "where": ...}}``;
* ``{"explicit_members": ["entity_id", ...]}`` supplies reviewed display
  members.

All output is deduplicated by stable entity ID.  ``memberships`` preserves the
reasons for every matching collection, so UI code can render multi-membership
chips without duplicating cards.
"""

from __future__ import annotations

import argparse
import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any


class CollectionViewError(ValueError):
    """Raised when a view manifest is structurally or semantically invalid."""


_OPERATORS = {
    "collection",
    "and",
    "or",
    "not",
    "type",
    "relation",
    "arc",
    "active_at",
    "explicit_members",
}


def _records(value: Any, field: str) -> list[dict[str, Any]]:
    """Return mapping records or reject malformed graph arrays early."""

    if value is None:
        return []
    if not isinstance(value, list) or any(not isinstance(row, Mapping) for row in value):
        raise CollectionViewError(f"graph.{field} 必须是对象数组")
    return [dict(row) for row in value]


def _chapter(value: Any, label: str) -> int:
    """Validate a non-negative chapter integer without accepting booleans."""

    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise CollectionViewError(f"{label} 必须是非负整数章节号")
    return value


def _interval_active(record: Mapping[str, Any], chapter: int, start_key: str, end_key: str) -> bool:
    """Return inclusive interval activity, with absent starts treated as zero."""

    raw_start = record.get(start_key, record.get("chapter", 0))
    start = raw_start if isinstance(raw_start, int) and not isinstance(raw_start, bool) else 0
    raw_end = record.get(end_key)
    end = raw_end if isinstance(raw_end, int) and not isinstance(raw_end, bool) else None
    return start <= chapter and (end is None or chapter <= end)


def _reason(operator: str, **values: Any) -> dict[str, Any]:
    """Build a small deterministic provenance object, omitting absent details."""

    return {"operator": operator, **{key: value for key, value in values.items() if value is not None}}


def _merge_reasons(*reason_maps: Mapping[str, list[dict[str, Any]]]) -> dict[str, list[dict[str, Any]]]:
    """Union entity sets and de-duplicate JSON reasons without changing order."""

    result: dict[str, list[dict[str, Any]]] = {}
    seen: dict[str, set[str]] = {}
    for mapping in reason_maps:
        for entity_id, reasons in mapping.items():
            bucket = result.setdefault(entity_id, [])
            fingerprints = seen.setdefault(entity_id, set())
            for item in reasons:
                fingerprint = json.dumps(item, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
                if fingerprint not in fingerprints:
                    fingerprints.add(fingerprint)
                    bucket.append(item)
    return result


def _append_reason(matches: Mapping[str, list[dict[str, Any]]], reason: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    """Add one provenance reason to each selected entity without mutation."""

    return _merge_reasons(
        matches,
        {entity_id: [reason] for entity_id in matches},
    )


class CollectionDeriver:
    """Evaluate a validated collection manifest against one immutable graph."""

    def __init__(self, graph: Mapping[str, Any], views: Mapping[str, Any], chapter: int | None = None) -> None:
        self.graph = graph
        self.entities = _records(graph.get("entities"), "entities")
        self.relations = _records(graph.get("relations"), "relations")
        self.arcs = _records(graph.get("story_arcs"), "story_arcs")
        self.evidence_ids = {
            row.get("id") for row in _records(graph.get("evidence"), "evidence")
            if isinstance(row.get("id"), str)
        }
        self.default_chapter = _chapter(chapter, "--chapter") if chapter is not None else None

        self.entity_by_id: dict[str, dict[str, Any]] = {}
        for entity in self.entities:
            entity_id = entity.get("id")
            if not isinstance(entity_id, str) or not entity_id:
                raise CollectionViewError("graph.entities 含有缺少稳定 id 的记录")
            if entity_id in self.entity_by_id:
                raise CollectionViewError(f"graph.entities 存在重复 id: {entity_id}")
            self.entity_by_id[entity_id] = entity

        self.arc_by_id: dict[str, dict[str, Any]] = {}
        for arc in self.arcs:
            arc_id = arc.get("id")
            if not isinstance(arc_id, str) or not arc_id:
                raise CollectionViewError("graph.story_arcs 含有缺少稳定 id 的记录")
            if arc_id in self.arc_by_id:
                raise CollectionViewError(f"graph.story_arcs 存在重复 id: {arc_id}")
            self.arc_by_id[arc_id] = arc

        raw_collections = views.get("collections")
        if not isinstance(raw_collections, list):
            raise CollectionViewError("dashboard-views.json.collections 必须是数组")
        self.collections: dict[str, dict[str, Any]] = {}
        for item in raw_collections:
            if not isinstance(item, Mapping):
                raise CollectionViewError("collections 含有非对象记录")
            collection = dict(item)
            collection_id = collection.get("id")
            label = collection.get("label")
            if not isinstance(collection_id, str) or not collection_id:
                raise CollectionViewError("collection.id 必须是非空稳定字符串")
            if not isinstance(label, str) or not label:
                raise CollectionViewError(f"{collection_id}: collection.label 必须是非空字符串")
            if not isinstance(collection.get("expression"), Mapping):
                raise CollectionViewError(f"{collection_id}: collection.expression 必须是对象")
            if collection_id in self.collections:
                raise CollectionViewError(f"collection id 重复: {collection_id}")
            self.collections[collection_id] = collection
        self._cache: dict[tuple[str, int | None], dict[str, list[dict[str, Any]]]] = {}
        self._visiting: list[str] = []

    def derive(self) -> dict[str, Any]:
        """Evaluate every collection and return stable members plus memberships."""

        collection_rows: list[dict[str, Any]] = []
        memberships: dict[str, dict[str, list[dict[str, Any]]]] = {}
        for collection_id in self._ordered_collection_ids():
            collection = self.collections[collection_id]
            matches = self._evaluate_collection(collection_id, self.default_chapter)
            members = [
                {"entity_id": entity_id, "matched_by": matches[entity_id]}
                for entity_id in sorted(matches)
            ]
            for member in members:
                memberships.setdefault(member["entity_id"], {})[collection_id] = member["matched_by"]
            collection_rows.append({
                "id": collection_id,
                "label": collection["label"],
                "expression": collection["expression"],
                "display": collection.get("display", {}),
                "member_count": len(members),
                "members": members,
            })

        membership_rows = {
            entity_id: {
                "collection_ids": sorted(collection_map),
                "membership_reasons": {collection_id: collection_map[collection_id] for collection_id in sorted(collection_map)},
            }
            for entity_id, collection_map in sorted(memberships.items())
        }
        return {
            "schema": "novel-knowledge-graph/collection-views-v1",
            "snapshot_chapter": self.default_chapter,
            "collections": collection_rows,
            "memberships": membership_rows,
        }

    def _ordered_collection_ids(self) -> list[str]:
        """Sort by optional display order, then stable collection ID."""

        def key(collection_id: str) -> tuple[int, str]:
            display = self.collections[collection_id].get("display")
            order = display.get("order") if isinstance(display, Mapping) else None
            return (order if isinstance(order, int) and not isinstance(order, bool) else 0, collection_id)

        return sorted(self.collections, key=key)

    def _evaluate_collection(self, collection_id: str, chapter: int | None) -> dict[str, list[dict[str, Any]]]:
        cache_key = (collection_id, chapter)
        if cache_key in self._cache:
            return self._cache[cache_key]
        if collection_id in self._visiting:
            cycle = " -> ".join([*self._visiting, collection_id])
            raise CollectionViewError(f"collection 存在循环引用: {cycle}")
        collection = self.collections.get(collection_id)
        if collection is None:
            raise CollectionViewError(f"引用了不存在的 collection: {collection_id}")
        self._visiting.append(collection_id)
        try:
            result = self._evaluate_expression(collection["expression"], chapter)
            self._cache[cache_key] = result
            return result
        finally:
            self._visiting.pop()

    def _evaluate_expression(self, expression: Any, chapter: int | None) -> dict[str, list[dict[str, Any]]]:
        if not isinstance(expression, Mapping):
            raise CollectionViewError("collection expression 必须是对象")
        keys = list(expression)
        if len(keys) != 1:
            raise CollectionViewError("collection expression 必须且只能包含一个运算符")
        operator = keys[0]
        if operator not in _OPERATORS:
            raise CollectionViewError(f"未知 collection 运算符: {operator}")
        operand = expression[operator]
        if operator == "collection":
            if not isinstance(operand, str) or not operand:
                raise CollectionViewError("collection 引用必须是非空字符串")
            child = self._evaluate_collection(operand, chapter)
            return _append_reason(child, _reason("collection", collection_id=operand))
        if operator in {"and", "or"}:
            if not isinstance(operand, list) or not operand:
                raise CollectionViewError(f"{operator} 必须是非空表达式数组")
            children = [self._evaluate_expression(child, chapter) for child in operand]
            if operator == "or":
                return _merge_reasons(*children)
            common = set(children[0])
            for child in children[1:]:
                common.intersection_update(child)
            return {entity_id: _merge_reasons(*(child for child in children if entity_id in child))[entity_id] for entity_id in sorted(common)}
        if operator == "not":
            excluded = self._evaluate_expression(operand, chapter)
            candidates = self._active_entities(chapter) if chapter is not None else set(self.entity_by_id)
            return {
                entity_id: [_reason("not", excluded_expression=operand)]
                for entity_id in sorted(candidates.difference(excluded))
            }
        if operator == "type":
            values = [operand] if isinstance(operand, str) else operand
            if not isinstance(values, list) or not values or any(not isinstance(value, str) or not value for value in values):
                raise CollectionViewError("type 必须是非空字符串或非空字符串数组")
            wanted = sorted(set(values))
            candidates = self._active_entities(chapter) if chapter is not None else set(self.entity_by_id)
            return {
                entity_id: [_reason("type", types=wanted)]
                for entity_id in sorted(candidates)
                if self.entity_by_id[entity_id].get("type") in wanted
            }
        if operator == "explicit_members":
            if not isinstance(operand, list) or any(not isinstance(value, str) or not value for value in operand):
                raise CollectionViewError("explicit_members 必须是稳定实体 ID 数组")
            unknown = sorted(set(operand).difference(self.entity_by_id))
            if unknown:
                raise CollectionViewError(f"explicit_members 引用了不存在的实体: {', '.join(unknown)}")
            candidates = self._active_entities(chapter) if chapter is not None else set(self.entity_by_id)
            return {
                entity_id: [_reason("explicit_members", entity_id=entity_id)]
                for entity_id in sorted(set(operand).intersection(candidates))
            }
        if operator == "relation":
            return self._relation_matches(operand, chapter)
        if operator == "arc":
            return self._arc_matches(operand, chapter)
        return self._active_at_matches(operand, chapter)

    def _active_entities(self, chapter: int) -> set[str]:
        """Return entities whose declared appearance interval includes a chapter.

        Missing temporal bounds are intentionally treated as eligible legacy
        records.  A query cannot manufacture activity from a name or a model
        guess; callers that need relation activity should wrap ``relation`` in
        ``active_at`` instead.
        """

        return {
            entity_id
            for entity_id, entity in self.entity_by_id.items()
            if _interval_active(entity, chapter, "first_chapter", "last_chapter")
        }

    def _relation_matches(self, operand: Any, chapter: int | None) -> dict[str, list[dict[str, Any]]]:
        if isinstance(operand, str):
            spec: dict[str, Any] = {"relation_type": operand}
        elif isinstance(operand, Mapping):
            spec = dict(operand)
        else:
            raise CollectionViewError("relation 必须是关系类型字符串或筛选对象")
        allowed = {"relation_type", "types", "role", "with_id", "source_id", "target_id"}
        unknown = sorted(set(spec).difference(allowed))
        if unknown:
            raise CollectionViewError(f"relation 含有未知筛选字段: {', '.join(unknown)}")
        raw_types = spec.get("types", spec.get("relation_type"))
        types = [raw_types] if isinstance(raw_types, str) else raw_types
        if not isinstance(types, list) or not types or any(not isinstance(value, str) or not value for value in types):
            raise CollectionViewError("relation 必须提供 relation_type 或 types")
        role = spec.get("role", "any")
        if role not in {"any", "source", "target", "other"}:
            raise CollectionViewError("relation.role 只能是 any/source/target/other")
        for key in ("with_id", "source_id", "target_id"):
            if key in spec and (not isinstance(spec[key], str) or spec[key] not in self.entity_by_id):
                raise CollectionViewError(f"relation.{key} 必须引用存在的实体 ID")
        if role == "other" and not isinstance(spec.get("with_id"), str):
            raise CollectionViewError("relation.role=other 必须同时提供 with_id")

        wanted = set(types)
        result: dict[str, list[dict[str, Any]]] = {}
        for relation in self.relations:
            source, target = relation.get("source_id"), relation.get("target_id")
            evidence_ids = relation.get("evidence_ids")
            if not isinstance(source, str) or not isinstance(target, str):
                continue
            if source not in self.entity_by_id or target not in self.entity_by_id:
                continue
            if relation.get("relation_type") not in wanted or not isinstance(evidence_ids, list) or not evidence_ids:
                continue
            missing_evidence = sorted(set(evidence_ids).difference(self.evidence_ids))
            if missing_evidence:
                raise CollectionViewError(
                    f"relation {relation.get('id')} 引用了不存在的证据: {', '.join(missing_evidence)}"
                )
            if chapter is not None and not _interval_active(relation, chapter, "valid_from", "valid_to"):
                continue
            if spec.get("source_id") not in (None, source) or spec.get("target_id") not in (None, target):
                continue
            with_id = spec.get("with_id")
            if with_id is not None and with_id not in {source, target}:
                continue
            if role == "source":
                selected = [source]
            elif role == "target":
                selected = [target]
            elif role == "other":
                selected = [target if source == with_id else source]
            else:
                selected = [source, target]
            relation_id = relation.get("id") if isinstance(relation.get("id"), str) else None
            for entity_id in selected:
                result.setdefault(entity_id, []).append(
                    _reason("relation", relation_id=relation_id, relation_type=relation.get("relation_type"), evidence_ids=sorted(evidence_ids))
                )
        return _merge_reasons(result)

    def _arc_matches(self, operand: Any, chapter: int | None) -> dict[str, list[dict[str, Any]]]:
        if isinstance(operand, str):
            arc_ids = [operand]
            descendants = False
        elif isinstance(operand, list):
            arc_ids, descendants = operand, False
        elif isinstance(operand, Mapping):
            raw_ids = operand.get("ids", operand.get("id"))
            arc_ids = [raw_ids] if isinstance(raw_ids, str) else raw_ids
            descendants = operand.get("include_descendants", False)
            if set(operand).difference({"id", "ids", "include_descendants"}):
                raise CollectionViewError("arc 含有未知筛选字段")
        else:
            raise CollectionViewError("arc 必须是剧情 ID、ID 数组或筛选对象")
        if not isinstance(arc_ids, list) or not arc_ids or any(not isinstance(value, str) or not value for value in arc_ids):
            raise CollectionViewError("arc 必须引用一个或多个剧情 ID")
        if not isinstance(descendants, bool):
            raise CollectionViewError("arc.include_descendants 必须是布尔值")
        missing = sorted(set(arc_ids).difference(self.arc_by_id))
        if missing:
            raise CollectionViewError(f"arc 引用了不存在的剧情: {', '.join(missing)}")
        selected = set(arc_ids)
        if descendants:
            changed = True
            while changed:
                changed = False
                for arc_id, arc in self.arc_by_id.items():
                    if arc.get("parent_arc_id") in selected and arc_id not in selected:
                        selected.add(arc_id)
                        changed = True
        result: dict[str, list[dict[str, Any]]] = {}
        for arc_id in sorted(selected):
            arc = self.arc_by_id[arc_id]
            if chapter is not None and not _interval_active(arc, chapter, "chapter_start", "chapter_end"):
                continue
            entity_ids = arc.get("entity_ids", [])
            if not isinstance(entity_ids, list) or any(not isinstance(value, str) for value in entity_ids):
                raise CollectionViewError(f"{arc_id}: story_arc.entity_ids 必须是实体 ID 数组")
            unknown = sorted(set(entity_ids).difference(self.entity_by_id))
            if unknown:
                raise CollectionViewError(f"{arc_id}: story_arc 引用了不存在的实体: {', '.join(unknown)}")
            for entity_id in sorted(set(entity_ids)):
                result.setdefault(entity_id, []).append(_reason("arc", arc_id=arc_id))
        return _merge_reasons(result)

    def _active_at_matches(self, operand: Any, inherited_chapter: int | None) -> dict[str, list[dict[str, Any]]]:
        if isinstance(operand, int) and not isinstance(operand, bool):
            chapter = _chapter(operand, "active_at")
            return {
                entity_id: [_reason("active_at", chapter=chapter)]
                for entity_id in sorted(self._active_entities(chapter))
            }
        if not isinstance(operand, Mapping):
            raise CollectionViewError("active_at 必须是章节号或包含 chapter/where 的对象")
        allowed = {"chapter", "where", "expression"}
        unknown = sorted(set(operand).difference(allowed))
        if unknown:
            raise CollectionViewError(f"active_at 含有未知字段: {', '.join(unknown)}")
        chapter = _chapter(operand.get("chapter"), "active_at.chapter")
        nested = operand.get("where", operand.get("expression"))
        if nested is None:
            return self._active_at_matches(chapter, inherited_chapter)
        matches = self._evaluate_expression(nested, chapter)
        active = self._active_entities(chapter)
        return _append_reason(
            {entity_id: reasons for entity_id, reasons in matches.items() if entity_id in active},
            _reason("active_at", chapter=chapter),
        )


def derive_collection_views(graph: Mapping[str, Any], views: Mapping[str, Any], chapter: int | None = None) -> dict[str, Any]:
    """Public convenience wrapper for dashboards, tests, and CLI callers."""

    return CollectionDeriver(graph, views, chapter).derive()


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--graph", required=True, type=Path, help="UTF-8 graph.json input")
    parser.add_argument("--views", required=True, type=Path, help="UTF-8 dashboard-views.json input")
    parser.add_argument("--chapter", type=int, help="Optional inclusive chapter snapshot")
    parser.add_argument("--output", type=Path, help="Write JSON here instead of stdout")
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    graph = json.loads(args.graph.resolve().read_text(encoding="utf-8"))
    views = json.loads(args.views.resolve().read_text(encoding="utf-8"))
    payload = derive_collection_views(graph, views, args.chapter)
    rendered = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    else:
        print(rendered, end="")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except CollectionViewError as exc:
        raise SystemExit(f"collection views 错误: {exc}")
