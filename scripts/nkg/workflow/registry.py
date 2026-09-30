"""The run's ID registry: entity IDs and fragment numbers are issued, not guessed.

Parallel workers used to mint IDs independently and the merge discovered the
collisions afterwards — one character with two IDs, two characters with one —
and the "highest fragment number + 1" rule lived only in prose, so two
fragments could share an evidence prefix and silently overwrite each other.

`ids.json` is the single table every worker consults before creating an entity:
a known name or alias returns the existing ID; an unknown one is claimed under a
validated `<type-prefix>_<ascii slug>` and recorded with who claimed it. A name
already bound to two different entities is ambiguous and raises instead of
picking one: identity is a judgment, never a string match.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping

from nkg.core.records import records

TYPE_PREFIXES: dict[str, str] = {
    "character": "char", "skill": "skill", "item": "item", "organization": "org",
    "location": "loc", "creature": "creature", "concept": "concept", "level_axis": "axis",
    "title": "title", "martial_soul": "ms",
}
SLUG = re.compile(r"[a-z0-9]+(?:_[a-z0-9]+)*")
FRAGMENT_NAME = re.compile(r"fragment-(\d+)\.json$")


class AmbiguousName(ValueError):
    """A name or alias maps to more than one entity; a human or AI must decide."""


class RegistryError(ValueError):
    pass


class IdRegistry:
    def __init__(self, data: Mapping[str, Any] | None = None):
        data = dict(data or {})
        self.entities: dict[str, dict[str, Any]] = {k: dict(v) for k, v in (data.get("entities") or {}).items()}
        self.fragments: dict[str, Any] = dict(data.get("fragments") or {"next": 1, "issued": {}})
        self.warnings: list[str] = list(data.get("warnings") or [])
        self._names: dict[str, set[str]] = {}
        for entity_id, row in self.entities.items():
            self._index(entity_id, row)

    # ---- persistence ----
    @classmethod
    def load(cls, path: Path) -> "IdRegistry":
        return cls(json.loads(path.read_text(encoding="utf-8"))) if path.exists() else cls()

    def save(self, path: Path) -> None:
        from io_utils import atomic_write_json
        atomic_write_json(path, self.to_json())

    def to_json(self) -> dict[str, Any]:
        return {"version": 1, "entities": dict(sorted(self.entities.items())),
                "fragments": self.fragments, "warnings": self.warnings}

    # ---- lookup ----
    def _index(self, entity_id: str, row: Mapping[str, Any]) -> None:
        for name in [row.get("name"), *(row.get("aliases") or [])]:
            if isinstance(name, str) and name.strip():
                self._names.setdefault(name.strip(), set()).add(entity_id)

    def lookup(self, name: str) -> list[str]:
        """Every entity whose canonical name or alias is exactly `name`."""
        return sorted(self._names.get(name.strip(), ()))

    def resolve(self, names: Iterable[str]) -> str | None:
        """The one entity all given names agree on; AmbiguousName when they disagree."""
        found = {entity_id for name in names for entity_id in self.lookup(name)}
        if len(found) > 1:
            raise AmbiguousName(f"{sorted(names)} match several entities: {sorted(found)}")
        return next(iter(found), None)

    # ---- claiming ----
    def claim(self, entity_type: str, name: str, slug: str, *, aliases: Iterable[str] = (),
              first_chapter: int | None = None, claimed_by: str = "") -> tuple[str, bool]:
        """Return (entity_id, created). A known name or alias reuses its entity."""
        aliases = [a for a in aliases if isinstance(a, str) and a.strip()]
        existing = self.resolve([name, *aliases])
        if existing:
            row = self.entities[existing]
            added = [a for a in [name, *aliases] if a != row.get("name") and a not in (row.get("aliases") or [])]
            if added:
                row["aliases"] = [*(row.get("aliases") or []), *added]
                self._index(existing, row)
            if isinstance(first_chapter, int) and (row.get("first_chapter") is None or first_chapter < row["first_chapter"]):
                row["first_chapter"] = first_chapter
            return existing, False
        prefix = TYPE_PREFIXES.get(entity_type)
        if prefix is None:
            raise RegistryError(f"unknown entity type {entity_type!r}")
        if not SLUG.fullmatch(slug):
            raise RegistryError(f"slug {slug!r} must be lowercase ASCII words joined by underscores (pinyin)")
        entity_id = f"{prefix}_{slug}"
        if entity_id in self.entities:
            raise RegistryError(f"{entity_id} is already {self.entities[entity_id].get('name')!r}; choose another slug")
        row = {"type": entity_type, "name": name, "aliases": aliases, "first_chapter": first_chapter,
               "claimed_by": claimed_by, "claimed_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
        self.entities[entity_id] = row
        self._index(entity_id, row)
        return entity_id, True

    def seed_from_graph(self, graph: Mapping[str, Any], source: str = "graph") -> int:
        """Register every entity already in a merged graph; returns how many were new."""
        added = 0
        for entity in records(graph.get("entities")):
            entity_id = entity.get("id")
            if not isinstance(entity_id, str) or entity_id in self.entities:
                continue
            etype = str(entity.get("type") or "")
            prefix = TYPE_PREFIXES.get(etype)
            if prefix and not entity_id.startswith(prefix + "_"):
                self.warnings.append(f"{entity_id}: prefix does not match type {etype}")
            if not re.fullmatch(r"[a-z]+_[a-z0-9_]+", entity_id):
                self.warnings.append(f"{entity_id}: not a lowercase ASCII ID")
            row = {"type": etype, "name": entity.get("name"), "aliases": list(entity.get("aliases") or []),
                   "first_chapter": entity.get("first_chapter"), "claimed_by": source}
            self.entities[entity_id] = row
            self._index(entity_id, row)
            added += 1
        for name, ids in sorted(self._names.items()):
            if len(ids) > 1:
                self.warnings.append(f"name {name!r} is shared by {sorted(ids)}")
        return added

    # ---- fragments ----
    def issue_fragment(self, unit_id: str, existing_dir: Path | None = None) -> dict[str, str]:
        """Allocate the next fragment file name and its record-ID marker (`fNN`)."""
        number = int(self.fragments.get("next") or 1)
        if existing_dir is not None and existing_dir.is_dir():
            on_disk = [int(m.group(1)) for p in existing_dir.glob("fragment-*.json") if (m := FRAGMENT_NAME.search(p.name))]
            number = max([number, *(n + 1 for n in on_disk)])
        issued = self.fragments.setdefault("issued", {})
        for name, row in issued.items():
            if row.get("unit") == unit_id:
                return {"fragment": name, "marker": row["marker"]}
        name = f"fragment-{number:02d}"
        issued[name] = {"unit": unit_id, "marker": f"f{number:02d}",
                        "issued_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
        self.fragments["next"] = number + 1
        return {"fragment": name, "marker": f"f{number:02d}"}

    def id_table(self, entity_ids: Iterable[str] | None = None) -> str:
        """A Markdown table for a worker prompt, optionally limited to some IDs."""
        wanted = sorted(self.entities) if entity_ids is None else sorted(set(entity_ids) & set(self.entities))
        lines = ["| ID | 类型 | 名称 | 别名 |", "|---|---|---|---|"]
        for entity_id in wanted:
            row = self.entities[entity_id]
            lines.append(f"| {entity_id} | {row.get('type')} | {row.get('name')} | {'、'.join(row.get('aliases') or [])} |")
        return "\n".join(lines)
