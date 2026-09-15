from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import Any, Iterable, Mapping


def records(value: object) -> list[dict[str, Any]]:
    return [row for row in value if isinstance(row, dict)] if isinstance(value, list) else []


def chapter_value(value: object) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def interval_active(record: Mapping[str, Any], chapter: int, start_key: str = "valid_from", end_key: str = "valid_to") -> bool:
    start = chapter_value(record.get(start_key))
    end = chapter_value(record.get(end_key))
    return (start is None or start <= chapter) and (end is None or chapter <= end)


@dataclass(frozen=True)
class RuntimeStats:
    entities: int
    events: int
    relations: int
    state_changes: int
    evidence: int


class GraphRuntime:
    """Pre-indexed read-only facade over one canonical graph snapshot.

    The class centralizes O(1)/O(k) lookups that previously required repeated
    whole-array scans. It never mutates the canonical graph and therefore can be
    safely reused by extraction packets, validators, views and exports.
    """

    def __init__(self, graph: Mapping[str, Any]):
        self.graph = graph
        self.entities = records(graph.get("entities"))
        self.events = records(graph.get("events"))
        self.relations = records(graph.get("relations"))
        self.state_changes = records(graph.get("state_changes"))
        self.evidence = records(graph.get("evidence"))
        self.item_roles = records(graph.get("item_roles"))
        self.commitments = records(graph.get("commitments"))
        self.foreshadowing = records(graph.get("foreshadowing"))
        self.chapter_summaries = records(graph.get("chapter_summaries"))

        self.entity_by_id = {str(row["id"]): row for row in self.entities if isinstance(row.get("id"), str)}
        self.event_by_id = {str(row["id"]): row for row in self.events if isinstance(row.get("id"), str)}
        self.evidence_by_id = {str(row["id"]): row for row in self.evidence if isinstance(row.get("id"), str)}
        self.commitment_by_id = {str(row["id"]): row for row in self.commitments if isinstance(row.get("id"), str)}
        self.foreshadowing_by_id = {str(row["id"]): row for row in self.foreshadowing if isinstance(row.get("id"), str)}
        self.chapter_summary_by_chapter = {
            row["chapter"]: row for row in self.chapter_summaries if chapter_value(row.get("chapter")) is not None
        }

        self.events_by_chapter: dict[int, list[dict[str, Any]]] = defaultdict(list)
        self.events_by_entity: dict[str, list[dict[str, Any]]] = defaultdict(list)
        self.relations_by_entity: dict[str, list[dict[str, Any]]] = defaultdict(list)
        self.state_changes_by_entity: dict[str, list[dict[str, Any]]] = defaultdict(list)
        self.state_changes_by_entity_facet: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
        self.item_roles_by_item: dict[str, list[dict[str, Any]]] = defaultdict(list)
        self.item_roles_by_entity: dict[str, list[dict[str, Any]]] = defaultdict(list)
        self.evidence_by_chapter: dict[int, list[dict[str, Any]]] = defaultdict(list)

        for event in self.events:
            chapter = chapter_value(event.get("chapter"))
            if chapter is not None:
                self.events_by_chapter[chapter].append(event)
            for entity_id in event.get("participant_ids", []) if isinstance(event.get("participant_ids"), list) else []:
                if isinstance(entity_id, str):
                    self.events_by_entity[entity_id].append(event)
            location_id = event.get("location_id")
            if isinstance(location_id, str):
                self.events_by_entity[location_id].append(event)

        for relation in self.relations:
            for key in ("source_id", "target_id"):
                entity_id = relation.get(key)
                if isinstance(entity_id, str):
                    self.relations_by_entity[entity_id].append(relation)

        for change in self.state_changes:
            entity_id = change.get("entity_id")
            if not isinstance(entity_id, str):
                continue
            self.state_changes_by_entity[entity_id].append(change)
            facet = str(change.get("facet") or "")
            self.state_changes_by_entity_facet[(entity_id, facet)].append(change)

        for role in self.item_roles:
            item_id, entity_id = role.get("item_id"), role.get("entity_id")
            if isinstance(item_id, str):
                self.item_roles_by_item[item_id].append(role)
            if isinstance(entity_id, str):
                self.item_roles_by_entity[entity_id].append(role)

        for evidence in self.evidence:
            chapter = chapter_value(evidence.get("chapter"))
            if chapter is not None:
                self.evidence_by_chapter[chapter].append(evidence)

        for rows in (
            self.events_by_entity.values(),
            self.relations_by_entity.values(),
            self.state_changes_by_entity.values(),
            self.state_changes_by_entity_facet.values(),
            self.item_roles_by_item.values(),
            self.item_roles_by_entity.values(),
        ):
            for group in rows:
                group.sort(key=self._record_sort_key)

    @staticmethod
    def _record_sort_key(row: Mapping[str, Any]) -> tuple[int, str]:
        chapter = next(
            (chapter_value(row.get(key)) for key in ("chapter", "valid_from", "created_chapter", "first_chapter") if chapter_value(row.get(key)) is not None),
            0,
        )
        return int(chapter or 0), str(row.get("id") or "")

    @property
    def stats(self) -> RuntimeStats:
        return RuntimeStats(len(self.entities), len(self.events), len(self.relations), len(self.state_changes), len(self.evidence))

    def entity(self, entity_id: str) -> dict[str, Any] | None:
        return self.entity_by_id.get(entity_id)

    def name(self, entity_id: str | None) -> str | None:
        if entity_id is None:
            return None
        row = self.entity_by_id.get(entity_id)
        return str(row.get("name") or entity_id) if row else entity_id

    def evidence_record(self, evidence_id: str) -> dict[str, Any] | None:
        return self.evidence_by_id.get(evidence_id)

    def events_between(self, start: int, end: int) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = []
        for chapter in range(min(start, end), max(start, end) + 1):
            result.extend(self.events_by_chapter.get(chapter, ()))
        return result

    def events_for(self, entity_id: str, start: int | None = None, end: int | None = None) -> list[dict[str, Any]]:
        rows = list(self.events_by_entity.get(entity_id, ()))
        if start is None and end is None:
            return rows
        return [
            row for row in rows
            if (chapter_value(row.get("chapter")) is None or start is None or row["chapter"] >= start)
            and (chapter_value(row.get("chapter")) is None or end is None or row["chapter"] <= end)
        ]

    def relations_for(self, entity_id: str, chapter: int | None = None) -> list[dict[str, Any]]:
        rows = list(self.relations_by_entity.get(entity_id, ()))
        return rows if chapter is None else [row for row in rows if interval_active(row, chapter)]

    def connected_entities(self, seeds: Iterable[str], chapter: int | None = None, hops: int = 1) -> set[str]:
        seen = {value for value in seeds if value in self.entity_by_id}
        frontier = set(seen)
        for _ in range(max(0, hops)):
            nxt: set[str] = set()
            for entity_id in frontier:
                for relation in self.relations_for(entity_id, chapter):
                    for key in ("source_id", "target_id"):
                        value = relation.get(key)
                        if isinstance(value, str) and value in self.entity_by_id and value not in seen:
                            nxt.add(value)
            if not nxt:
                break
            seen.update(nxt)
            frontier = nxt
        return seen

    def state_history(self, entity_id: str, facet: str | None = None, chapter: int | None = None) -> list[dict[str, Any]]:
        rows = (
            self.state_changes_by_entity_facet.get((entity_id, facet), ())
            if facet is not None
            else self.state_changes_by_entity.get(entity_id, ())
        )
        if chapter is None:
            return list(rows)
        return [row for row in rows if chapter_value(row.get("chapter")) is None or row["chapter"] <= chapter]

    def state_at(self, entity_id: str, chapter: int, facet: str | None = None) -> dict[str, Any]:
        latest: dict[str, dict[str, Any]] = {}
        for change in self.state_history(entity_id, facet, chapter):
            change_chapter = chapter_value(change.get("chapter"))
            end = chapter_value(change.get("end_chapter"))
            if change_chapter is None or change_chapter > chapter or (end is not None and chapter > end):
                continue
            key = str(change.get("facet") or "")
            latest[key] = change
        return {
            key: {
                "value": row.get("after") if "after" in row else row.get("target_id"),
                "chapter": row.get("chapter"),
                "record_id": row.get("id"),
                "evidence_ids": list(row.get("evidence_ids") or []),
            }
            for key, row in latest.items()
        }

    def state_capsule(self, entity_ids: Iterable[str], chapter: int, history_depth: int = 1) -> dict[str, Any]:
        capsule: dict[str, Any] = {}
        for entity_id in entity_ids:
            if entity_id not in self.entity_by_id:
                continue
            history = self.state_history(entity_id, chapter=chapter)
            by_facet: dict[str, list[dict[str, Any]]] = defaultdict(list)
            for row in history:
                by_facet[str(row.get("facet") or "")].append(row)
            facets: dict[str, Any] = {}
            for facet, rows in by_facet.items():
                selected = rows[-max(1, history_depth):]
                facets[facet] = [
                    {
                        "chapter": row.get("chapter"),
                        "before": row.get("before"),
                        "after": row.get("after"),
                        "action": row.get("action"),
                        "record_id": row.get("id"),
                        "evidence_ids": list(row.get("evidence_ids") or []),
                    }
                    for row in selected
                ]
            capsule[entity_id] = {"name": self.name(entity_id), "facets": facets}
        return capsule
