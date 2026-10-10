"""Engine rows into P01 ``CatalogEntity`` records (P02-T02).

Two rules decide everything in this module.

**A display name is not an identifier.** Every entity is keyed on the native
upstream key, so the four gem names and 577 passive-node names that repeat on
the pinned checkout stay four and 577 distinct entities. The names go in
``display_names``; nothing merges two entities because they read alike.

**Keep what upstream carries.** ``raw_reference`` holds the row as the engine
reported it, so a consumer can reconstruct the entity. Modifier text is never
summed and item bases are never reduced to a damage number.
"""

from __future__ import annotations

from typing import Any, Iterable, Mapping, Sequence

from ..domain.identity import content_hash
from ..domain.records import CATALOG_TABLES, CatalogEntity

#: Namespace prefix for every catalog entity id. The patch and catalog scope
#: come from the ``GameCatalog`` the entity lives in, which carries both
#: ``catalog_hash`` and ``patch_profile_id``.
ID_PREFIX = "poe2"

#: The order tables are exported and hashed in. Same set as
#: ``records.CATALOG_TABLES``; fixed here so two runs produce the same bytes.
CATALOG_TABLE_ORDER = tuple(CATALOG_TABLES)

#: Row fields that are maps upstream. dkjson encodes an empty Lua table as a
#: JSON array, so an absent map arrives as ``[]`` and is normalized back.
_MAP_FIELDS = ("req", "weapon", "armour", "flask", "baseFlags")

CatalogTables = dict[str, list[CatalogEntity]]


def entity_id(table: str, *parts: Any) -> str:
    """``poe2/<table>/<native key>``. Parts are joined, never hashed.

    A hashed key would hide which upstream entity an id refers to, and the
    native key is already unique inside its table.
    """
    return "/".join([ID_PREFIX, table, *(str(part) for part in parts)])


def _clean(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(k): _clean(v) for k, v in sorted(value.items(),
                                                     key=lambda kv: str(kv[0]))}
    if isinstance(value, (list, tuple)):
        return [_clean(v) for v in value]
    return value


def _raw(row: Mapping[str, Any], *, drop: Sequence[str] = ()) -> dict:
    out: dict[str, Any] = {}
    for key, value in row.items():
        if key in drop or value is None:
            continue
        if key in _MAP_FIELDS and isinstance(value, list) and not value:
            value = {}
        out[str(key)] = _clean(value)
    return dict(sorted(out.items()))


def _names(*candidates: Any) -> list[str]:
    """Display names in order, deduplicated, with blanks dropped."""
    out: list[str] = []
    for candidate in candidates:
        if isinstance(candidate, str) and candidate.strip() and candidate not in out:
            out.append(candidate)
    return out


def _aliases(primary: Sequence[str], *candidates: Any) -> list[str]:
    out: list[str] = []
    for candidate in candidates:
        if (isinstance(candidate, str) and candidate.strip()
                and candidate not in primary and candidate not in out):
            out.append(candidate)
    return out


# ------------------------------------------------------------ per-table ---

def _classes(rows: Iterable[Mapping[str, Any]]) -> list[CatalogEntity]:
    out = []
    for row in rows:
        names = _names(row.get("name"))
        out.append(CatalogEntity(
            entity_id=entity_id("classes", row.get("classId")),
            display_names=names,
            aliases=_aliases(names, str(row.get("classId"))),
            raw_reference=_raw(row),
            rule_references=[]))
    return out


def _ascendancies(rows: Iterable[Mapping[str, Any]]) -> list[CatalogEntity]:
    """Ascendancies come from the class rows; index 0 is "no ascendancy".

    Index 0 is not an ascendancy a character can take, so it is not an
    entity. ``BuildSpec.ascendancy_id`` is nullable for exactly that state.
    """
    out = []
    for row in rows:
        class_id = row.get("classId")
        for ascendancy in row.get("ascendancies") or ():
            index = ascendancy.get("index")
            if index in (0, "0", None):
                continue
            names = _names(ascendancy.get("name"), ascendancy.get("id"))
            out.append(CatalogEntity(
                entity_id=entity_id("ascendancies", class_id, index),
                display_names=names,
                aliases=_aliases(names, ascendancy.get("id")),
                raw_reference=_raw({**ascendancy, "classId": class_id,
                                    "className": row.get("name")}),
                rule_references=[]))
    return out


def _passive_nodes(rows: Iterable[Mapping[str, Any]]) -> list[CatalogEntity]:
    out = []
    for row in rows:
        names = _names(row.get("name"))
        out.append(CatalogEntity(
            entity_id=entity_id("passive_nodes", row.get("id")),
            display_names=names,
            aliases=_aliases(names, row.get("stringId")),
            raw_reference=_raw(row),
            rule_references=[]))
    return out


def derive_passive_edges(
        rows: Iterable[Mapping[str, Any]]) -> list[CatalogEntity]:
    """Undirected edges, derived from the nodes' own link lists.

    An edge is stored once under the ordered pair, so a link reported from
    both ends does not become two entities. Only links whose other end is a
    node in this export become edges; a dangling link is kept on the node's
    raw reference and reported as unresolved rather than invented.
    """
    known = set()
    links: list[tuple[int, int]] = []
    rows = list(rows)
    for row in rows:
        node_id = row.get("id")
        if node_id is not None:
            known.add(int(node_id))
    seen: set[tuple[int, int]] = set()
    for row in rows:
        node_id = row.get("id")
        if node_id is None:
            continue
        for other in row.get("linked") or ():
            if other is None or int(other) not in known:
                continue
            pair = (int(node_id), int(other))
            pair = (min(pair), max(pair))
            if pair[0] == pair[1] or pair in seen:
                continue
            seen.add(pair)
            links.append(pair)
    out = []
    for low, high in sorted(links):
        out.append(CatalogEntity(
            entity_id=entity_id("passive_edges", "%d-%d" % (low, high)),
            display_names=[],
            aliases=[],
            raw_reference={"from": low, "to": high, "directed": False},
            rule_references=[]))
    return out


def _gems(rows: Iterable[Mapping[str, Any]]) -> list[CatalogEntity]:
    out = []
    for row in rows:
        names = _names(row.get("name"), row.get("baseTypeName"))
        out.append(CatalogEntity(
            entity_id=entity_id("gems", row.get("id")),
            display_names=names,
            aliases=_aliases(names, row.get("gameId"), row.get("variantId"),
                             row.get("grantedEffectId")),
            raw_reference=_raw(row),
            rule_references=[]))
    return out


def _granted_skills(rows: Iterable[Mapping[str, Any]]) -> list[CatalogEntity]:
    out = []
    for row in rows:
        names = _names(row.get("name"))
        out.append(CatalogEntity(
            entity_id=entity_id("granted_skills", row.get("id")),
            display_names=names,
            aliases=_aliases(names, row.get("modSource")),
            raw_reference=_raw(row),
            rule_references=[]))
    return out


def _item_bases(rows: Iterable[Mapping[str, Any]]) -> list[CatalogEntity]:
    out = []
    for row in rows:
        names = _names(row.get("name"))
        out.append(CatalogEntity(
            entity_id=entity_id("item_bases", row.get("name")),
            display_names=names,
            aliases=[],
            raw_reference=_raw(row),
            rule_references=[]))
    return out


def _item_modifiers(rows: Iterable[Mapping[str, Any]]) -> list[CatalogEntity]:
    """Neither the group nor the mod id is unique on its own.

    Modifier ids repeat across groups upstream, so the entity id carries
    both. Modifiers have no display name; their text stays in the raw
    reference as separate lines and is never summed.
    """
    out = []
    for row in rows:
        out.append(CatalogEntity(
            entity_id=entity_id("item_modifiers", row.get("group"),
                                row.get("id")),
            display_names=[],
            aliases=_aliases([], row.get("affix")),
            raw_reference=_raw(row),
            rule_references=[]))
    return out


def _slots(rows: Iterable[Mapping[str, Any]]) -> list[CatalogEntity]:
    out = []
    for row in rows:
        names = _names(row.get("label"), row.get("slotName"), row.get("name"))
        out.append(CatalogEntity(
            entity_id=entity_id("slots", row.get("name")),
            display_names=names,
            aliases=[],
            raw_reference=_raw(row),
            rule_references=[]))
    return out


def _config_variables(rows: Iterable[Mapping[str, Any]]) -> list[CatalogEntity]:
    out = []
    for row in rows:
        names = _names(row.get("label"))
        out.append(CatalogEntity(
            entity_id=entity_id("config_variables", row.get("var")),
            display_names=names,
            aliases=_aliases(names, row.get("var")),
            raw_reference=_raw(row),
            rule_references=[]))
    return out


_BUILDERS = {
    "classes": _classes,
    "ascendancies": _ascendancies,
    "passive_nodes": _passive_nodes,
    "passive_edges": derive_passive_edges,
    "gems": _gems,
    "granted_skills": _granted_skills,
    "item_bases": _item_bases,
    "item_modifiers": _item_modifiers,
    "slots": _slots,
    "config_variables": _config_variables,
}


def entities_from_rows(table: str,
                       rows: Iterable[Mapping[str, Any]]) -> list[CatalogEntity]:
    """Build one table's entities, sorted by id so two runs agree."""
    builder = _BUILDERS.get(table)
    if builder is None:
        raise KeyError("no entity builder for catalog table %r" % table)
    return sorted(builder(rows), key=lambda entity: entity.entity_id)


def catalog_hash(entities: Mapping[str, Sequence[CatalogEntity]]) -> str:
    """Content identity of the entity tables.

    Covers every exported field of every entity, so a changed modifier line
    or a renamed node forks the catalog. Deliberately excludes the record
    metadata around it: when the catalog was exported is not what it is.
    """
    projection = {
        table: [
            {
                "entity_id": entity.entity_id,
                "display_names": list(entity.display_names),
                "aliases": list(entity.aliases),
                "raw_reference": entity.raw_reference,
                "rule_references": list(entity.rule_references),
            }
            for entity in entities.get(table, ())
        ]
        for table in CATALOG_TABLE_ORDER
    }
    return content_hash(projection)
