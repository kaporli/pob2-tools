"""What the validator is given to decide with (P02-T03).

Three inputs beyond the build and the profile, and each one changes what can
be decided rather than what the answer is:

* a ``GameCatalog``: without it nothing about entity membership, tree
  connectivity or item bases can be resolved, and those checks say so;
* the ``ItemInstance`` records for the equipped items: without them an item's
  own level requirement and parse status are not available;
* an ``ImportedState``: what the pinned engine holds after loading the build's
  own document. Without it the verdict rests on what the record claims.

A reference this catalog does not carry stays unresolved. contracts.md is
explicit that a display name is not an identifier and that an ambiguous name
must remain unresolved; an absent entity is the same kind of answer. It is
not evidence that the entity is illegal, because the catalog can be
incomplete, and it is not evidence that it is legal either.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping, Sequence

from ...catalog.entities import entity_id
from ...domain.records import CatalogEntity, GameCatalog

#: Pool names the engine reports and this validator reads.
POOLS = ("spirit", "mana", "life")
ATTRIBUTES = ("strength", "dexterity", "intelligence")

_ATTRIBUTE_BY_ENGINE_KEY = {"Str": "strength", "Dex": "dexterity",
                            "Int": "intelligence"}


def normalize_id(table: str, reference: Any) -> str:
    """A catalog entity id, whether the reference is already one or native.

    P04 has not fixed whether a parsed build stores entity ids or the native
    keys they are built from, so both are accepted and neither is guessed at
    beyond this: a value that already starts with the namespace is used
    unchanged.
    """
    text = str(reference)
    if text.startswith("poe2/"):
        return text
    return entity_id(table, text)


def native_key(table: str, reference: Any) -> str:
    """The native key behind an entity id, or the reference as given."""
    prefix = "poe2/%s/" % table
    text = str(reference)
    return text[len(prefix):] if text.startswith(prefix) else text


def _as_map(value: Any) -> dict:
    """dkjson encodes an empty Lua table as ``[]``; read that back as ``{}``."""
    if isinstance(value, dict):
        return dict(value)
    return {}


def _as_int(value: Any) -> int | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _as_float(value: Any) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


# ------------------------------------------------------------- the catalog ---

class CatalogIndex:
    """Lookups over one exported catalog. Never invents an entity.

    ``empty`` is true when no catalog was supplied at all, which is a
    different statement from "the catalog does not have this entity" and the
    checks report it differently.
    """

    def __init__(self, catalog: GameCatalog | None = None, *,
                 entities: Mapping[str, Sequence[CatalogEntity]] | None = None
                 ) -> None:
        tables: Mapping[str, Sequence[CatalogEntity]]
        if catalog is not None:
            tables = catalog.entities
        elif entities is not None:
            tables = entities
        else:
            tables = {}
        self.catalog = catalog
        self.catalog_hash = catalog.catalog_hash if catalog is not None else None
        self.empty = not tables
        self.tables = {name: {entity.entity_id: entity for entity in rows}
                       for name, rows in tables.items()}
        self._adjacency: dict[str, set[str]] | None = None

    # -- membership --------------------------------------------------------

    def table(self, name: str) -> dict[str, CatalogEntity]:
        return self.tables.get(name, {})

    def get(self, table: str, reference: Any) -> CatalogEntity | None:
        return self.table(table).get(normalize_id(table, reference))

    def has(self, table: str, reference: Any) -> bool:
        return self.get(table, reference) is not None

    def has_table(self, name: str) -> bool:
        return bool(self.tables.get(name))

    # -- the tree ----------------------------------------------------------

    @property
    def adjacency(self) -> dict[str, set[str]]:
        """Undirected neighbours per passive node entity id.

        Built from the exported ``passive_edges`` table, which P02-T02 derives
        from the nodes' own link lists and stores once per pair. A node with no
        edge in the export has no neighbours here; it is not connected by
        assumption.
        """
        if self._adjacency is None:
            graph: dict[str, set[str]] = {}
            for edge in self.table("passive_edges").values():
                raw = edge.raw_reference if isinstance(edge.raw_reference, dict) else {}
                low, high = raw.get("from"), raw.get("to")
                if low is None or high is None:
                    continue
                a = entity_id("passive_nodes", low)
                b = entity_id("passive_nodes", high)
                graph.setdefault(a, set()).add(b)
                graph.setdefault(b, set()).add(a)
            self._adjacency = graph
        return self._adjacency

    def class_start_node(self, class_reference: Any) -> str | None:
        entity = self.get("classes", class_reference)
        if entity is None or not isinstance(entity.raw_reference, dict):
            return None
        start = entity.raw_reference.get("startNodeId")
        if start is None:
            return None
        return entity_id("passive_nodes", start)

    def ascendancy_start_nodes(self) -> dict[str, str]:
        """Ascendancy name to the entity id of its start node."""
        out: dict[str, str] = {}
        for node in self.table("passive_nodes").values():
            raw = node.raw_reference if isinstance(node.raw_reference, dict) else {}
            if raw.get("isAscendancyStart") and raw.get("ascendancyName"):
                out[str(raw["ascendancyName"])] = node.entity_id
        return out

    def node_raw(self, reference: Any) -> dict:
        entity = self.get("passive_nodes", reference)
        if entity is None or not isinstance(entity.raw_reference, dict):
            return {}
        return entity.raw_reference

    def gem_raw(self, reference: Any) -> dict:
        entity = self.get("gems", reference)
        if entity is None or not isinstance(entity.raw_reference, dict):
            return {}
        return entity.raw_reference

    def base_raw(self, reference: Any) -> dict:
        entity = self.get("item_bases", reference)
        if entity is None or not isinstance(entity.raw_reference, dict):
            return {}
        return entity.raw_reference

    def gem_by_name(self, name: str) -> list[CatalogEntity]:
        matches = []
        for entity in self.table("gems").values():
            if name in entity.display_names or name in entity.aliases:
                matches.append(entity)
        return matches


# ----------------------------------------------------------- engine reads ---

@dataclass(frozen=True, slots=True)
class PoolState:
    """One resource pool as the engine calculated it.

    ``unreserved`` is the engine's unclamped difference, so a negative value
    is over-reservation. ``reserved`` is clamped upstream and cannot show it.
    ``None`` means the engine did not calculate the value, never zero.
    """

    pool: str
    total: float | None
    reserved: float | None
    unreserved: float | None

    def to_dict(self) -> dict:
        return {"pool": self.pool, "total": self.total,
                "reserved": self.reserved, "unreserved": self.unreserved}


@dataclass(frozen=True, slots=True)
class MeasuredState:
    """Character quantities nothing in this package recomputes."""

    source: str
    attributes: Mapping[str, float | None] = field(default_factory=dict)
    pools: Mapping[str, PoolState] = field(default_factory=dict)

    def attribute(self, name: str) -> float | None:
        return self.attributes.get(name)

    def pool(self, name: str) -> PoolState | None:
        return self.pools.get(name)

    def to_dict(self) -> dict:
        return {"source": self.source,
                "attributes": {k: self.attributes.get(k) for k in ATTRIBUTES},
                "pools": {name: pool.to_dict()
                          for name, pool in sorted(self.pools.items())}}

    @classmethod
    def from_wire(cls, payload: Mapping[str, Any], *, source: str) -> "MeasuredState":
        attributes: dict[str, float | None] = {}
        for entry in payload.get("attributes") or ():
            if not isinstance(entry, dict):
                continue
            name = _ATTRIBUTE_BY_ENGINE_KEY.get(str(entry.get("attribute")))
            if name is not None:
                attributes[name] = _as_float(entry.get("value"))
        pools: dict[str, PoolState] = {}
        for entry in payload.get("pools") or ():
            if not isinstance(entry, dict):
                continue
            name = str(entry.get("pool") or "").lower()
            if name not in POOLS:
                continue
            pools[name] = PoolState(pool=name,
                                    total=_as_float(entry.get("total")),
                                    reserved=_as_float(entry.get("reserved")),
                                    unreserved=_as_float(entry.get("unreserved")))
        return cls(source=source, attributes=attributes, pools=pools)


@dataclass(frozen=True, slots=True)
class ImportedItem:
    slot_id: str
    name: str | None
    base_name: str | None
    rarity: str | None
    item_level: int | None
    requirements: Mapping[str, float]
    sockets: int
    weapon_set: int | None
    corrupted: bool


@dataclass(frozen=True, slots=True)
class ImportedGem:
    index: int
    name: str | None
    gem_id: str | None
    skill_id: str | None
    level: int | None
    quality: int | None
    enabled: bool
    support: bool
    natural_max_level: int | None


@dataclass(frozen=True, slots=True)
class ImportedGroup:
    index: int
    label: str | None
    enabled: bool
    slot: str | None
    source: str | None
    source_item: str | None
    gems: tuple[ImportedGem, ...]


@dataclass(frozen=True, slots=True)
class ImportedState:
    """What the pinned engine holds after loading a build document.

    This is the engine's own answer, not the record's claim. The two are
    compared, and a difference is a violation rather than a correction: a
    validator that silently preferred one of them would be repairing the
    build.
    """

    document_hash: str
    build_hash: str | None
    class_name: str | None
    class_id: int | None
    ascendancy_name: str | None
    ascendancy_id: int | None
    level: int | None
    allocated_nodes: tuple[int, ...]
    ascendancy_nodes: tuple[int, ...]
    unreadable_node_keys: tuple[str, ...]
    class_start_node: int | None
    points_used: int | None
    ascendancy_points_used: int | None
    weapon_set_points_used: tuple[int | None, int | None]
    jewel_sockets_used: int | None
    items: Mapping[str, ImportedItem]
    groups: tuple[ImportedGroup, ...]
    measured: MeasuredState
    calculated: bool

    @classmethod
    def from_wire(cls, payload: Mapping[str, Any], *, document_hash: str,
                  build_hash: str | None = None) -> "ImportedState":
        items: dict[str, ImportedItem] = {}
        for slot_name, raw in sorted(_as_map(payload.get("items")).items()):
            if not isinstance(raw, dict):
                continue
            items[str(slot_name)] = ImportedItem(
                slot_id=entity_id("slots", slot_name),
                name=raw.get("name"),
                base_name=raw.get("baseName"),
                rarity=raw.get("rarity"),
                item_level=_as_int(raw.get("itemLevel")),
                requirements={str(k): float(v)
                              for k, v in _as_map(raw.get("requirements")).items()
                              if _as_float(v) is not None},
                sockets=_as_int(raw.get("sockets")) or 0,
                weapon_set=_as_int(raw.get("weaponSet")),
                corrupted=bool(raw.get("corrupted")))
        groups: list[ImportedGroup] = []
        for raw in payload.get("socketGroups") or ():
            if not isinstance(raw, dict):
                continue
            gems = []
            for gem in raw.get("gems") or ():
                if not isinstance(gem, dict):
                    continue
                gems.append(ImportedGem(
                    index=_as_int(gem.get("index")) or 0,
                    name=gem.get("nameSpec"),
                    gem_id=gem.get("gemId"),
                    skill_id=gem.get("skillId"),
                    level=_as_int(gem.get("level")),
                    quality=_as_int(gem.get("quality")),
                    enabled=bool(gem.get("enabled")),
                    support=bool(gem.get("support")),
                    natural_max_level=_as_int(gem.get("naturalMaxLevel"))))
            groups.append(ImportedGroup(
                index=_as_int(raw.get("index")) or 0,
                label=raw.get("label"),
                enabled=bool(raw.get("enabled")),
                slot=raw.get("slot"),
                source=raw.get("source"),
                source_item=raw.get("sourceItem"),
                gems=tuple(gems)))
        return cls(
            document_hash=document_hash,
            build_hash=build_hash,
            class_name=payload.get("class"),
            class_id=_as_int(payload.get("classId")),
            ascendancy_name=payload.get("ascendancy"),
            ascendancy_id=_as_int(payload.get("ascendClassId")),
            level=_as_int(payload.get("level")),
            allocated_nodes=tuple(sorted(
                value for value in
                (_as_int(node) for node in payload.get("allocatedNodes") or ())
                if value is not None)),
            ascendancy_nodes=tuple(sorted(
                value for value in
                (_as_int(node) for node in payload.get("ascendancyNodes") or ())
                if value is not None)),
            unreadable_node_keys=tuple(
                str(key) for key in payload.get("unreadableNodeKeys") or ()),
            class_start_node=_as_int(payload.get("classStartNode")),
            points_used=_as_int(payload.get("pointsUsed")),
            ascendancy_points_used=_as_int(payload.get("ascendancyPointsUsed")),
            weapon_set_points_used=(_as_int(payload.get("weaponSet1PointsUsed")),
                                    _as_int(payload.get("weaponSet2PointsUsed"))),
            jewel_sockets_used=_as_int(payload.get("jewelSocketsUsed")),
            items=items,
            groups=tuple(groups),
            measured=MeasuredState.from_wire(payload, source="pob_import"),
            calculated=bool(payload.get("calculated")))

    def to_dict(self) -> dict:
        return {
            "document_hash": self.document_hash,
            "build_hash": self.build_hash,
            "class": self.class_name,
            "class_id": self.class_id,
            "ascendancy": self.ascendancy_name,
            "ascendancy_id": self.ascendancy_id,
            "level": self.level,
            "allocated_nodes": list(self.allocated_nodes),
            "ascendancy_nodes": list(self.ascendancy_nodes),
            "unreadable_node_keys": list(self.unreadable_node_keys),
            "points_used": self.points_used,
            "ascendancy_points_used": self.ascendancy_points_used,
            "weapon_set_points_used": list(self.weapon_set_points_used),
            "jewel_sockets_used": self.jewel_sockets_used,
            "items": {slot: item.slot_id for slot, item in sorted(self.items.items())},
            "socket_groups": len(self.groups),
            "measured": self.measured.to_dict(),
            "calculated": self.calculated,
        }
