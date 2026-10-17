"""Resolve source references against one patch catalog (P04-T03).

Four jobs, each refusing to guess:

* :func:`naming_from_catalog` builds the catalog ID to PoB name tables the
  document importer and exporter need, from a ``GameCatalog``'s entities.
  Native keys come first: a class by tree class id, a passive by node id, a
  gem by ``gameId`` and ``variantId``, a skill by granted effect id. When two
  entities claim one PoB value in a table, both are left out and listed as
  ambiguous, so a reference to that value stays unresolved.
* :func:`resolve_name` maps a display name to an entity by exact name or
  alias, within one entity type and locale. Several candidates come back as
  ``ambiguous`` with their IDs. There is no fuzzy matching.
* :func:`migrate_build` re-targets a BuildSpec to another patch's catalog. It
  returns a new record and a list of changes; the original is untouched. An
  entity missing from the target catalog stays unresolved, never replaced.
* :func:`resolve_item_modifiers` matches each item modifier line to modifier
  templates in the catalog. Category, text and rolled values are kept as
  they are; only ``native_id``, ``resolved_effect_ids`` and the modifier's
  ``parse_status`` change. :func:`item_readiness` separates an item with
  actual stats from a name-only template claim.

The catalog's display names come from the pinned PoB, which ships English
names only. A request for another locale is unresolved, not translated.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, replace
from typing import Any, Iterable, Mapping, Sequence

from ..catalog.entities import entity_id
from ..domain.absent import ABSENT
from ..domain.enums import ModifierParseStatus, RecordParseStatus
from ..domain.identity import build_hash, item_hash
from ..domain.records import (BuildSpec, CatalogEntity, ItemInstance,
                              SkillEntry, UnresolvedRef)
from ..evaluation.naming import CatalogNaming

#: Locale of the names the pinned catalog carries.
CATALOG_LOCALE = "en"

#: PoB's attribute override vocabulary (PassiveSpec ``AttributeOverride``).
#: These are PoB document values, not catalog rows, so their IDs live in a
#: namespace of their own.
ATTRIBUTE_OPTIONS = ("Strength", "Dexterity", "Intelligence")

#: PoB's two weapon sets.
WEAPON_SETS = (1, 2)


@dataclass(frozen=True)
class NamingReport:
    """The tables, plus every entity left out of them and why."""

    naming: CatalogNaming
    ambiguous: tuple[dict[str, Any], ...] = ()
    skipped: tuple[dict[str, Any], ...] = ()


def _unique(table: str, pairs: Iterable[tuple[str, Any]],
            ambiguous: list[dict[str, Any]]) -> dict[str, Any]:
    """Keep pairs whose value is claimed once; report the rest."""
    by_value: dict[Any, list[str]] = {}
    for key, value in pairs:
        if value is None:
            continue
        by_value.setdefault(value, []).append(key)
    out: dict[str, Any] = {}
    for value, keys in sorted(by_value.items(), key=lambda kv: str(kv[0])):
        if len(keys) == 1:
            out[keys[0]] = value
        else:
            ambiguous.append({"table": table, "value": value,
                              "candidates": sorted(keys)})
    return out


def _raw(entity: CatalogEntity) -> Mapping[str, Any]:
    raw = entity.raw_reference
    return raw if isinstance(raw, Mapping) else {}


def naming_from_catalog(entities: Mapping[str, Sequence[CatalogEntity]], *,
                        class_id: str | None = None) -> NamingReport:
    """CatalogNaming tables for documents read against this catalog.

    ``class_id`` limits the ascendancy tree-id table to one class: PoB
    numbers ascendancies per class, so the numbers repeat across classes and
    could not be read back otherwise. Without it that table is empty and an
    export reports the ascendancy's tree id as unresolved.
    """
    ambiguous: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    classes = list(entities.get("classes", ()))
    ascendancies = list(entities.get("ascendancies", ()))
    nodes = list(entities.get("passive_nodes", ()))
    gems = list(entities.get("gems", ()))
    skills = list(entities.get("granted_skills", ()))

    class_names = _unique("class_names", (
        (e.entity_id, _raw(e).get("name")) for e in classes), ambiguous)
    class_tree_ids = _unique("class_tree_ids", (
        (e.entity_id, _int(_raw(e).get("classId"))) for e in classes),
        ambiguous)
    ascendancy_names = _unique("ascendancy_names", (
        (e.entity_id, _raw(e).get("name")) for e in ascendancies), ambiguous)
    ascendancy_tree_ids: dict[str, int] = {}
    if class_id is not None:
        native_class = class_tree_ids.get(class_id)
        ascendancy_tree_ids = _unique("ascendancy_tree_ids", (
            (e.entity_id, _int(_raw(e).get("index"))) for e in ascendancies
            if _int(_raw(e).get("classId")) == native_class), ambiguous)
    node_ids = _unique("node_ids", (
        (e.entity_id, _int(_raw(e).get("id"))) for e in nodes), ambiguous)
    ascendancy_node_ids = frozenset(
        e.entity_id for e in nodes
        if _raw(e).get("ascendancyName") and e.entity_id in node_ids)
    slot_names = _unique("slot_names", (
        (e.entity_id, _raw(e).get("name")) for e in entities.get("slots", ())),
        ambiguous)
    base_names = _unique("base_names", (
        (e.entity_id, _raw(e).get("name"))
        for e in entities.get("item_bases", ())), ambiguous)
    skill_ids = _unique("skill_ids", (
        (e.entity_id, _raw(e).get("id")) for e in skills), ambiguous)
    support_skill_ids = frozenset(
        e.entity_id for e in skills
        if _raw(e).get("support") is True and e.entity_id in skill_ids)

    pairs = _unique("gem_ids/gem_variant_ids", (
        (e.entity_id, (_raw(e).get("gameId"), _raw(e).get("variantId")))
        for e in gems if _raw(e).get("gameId")), ambiguous)
    gem_ids = {key: pair[0] for key, pair in pairs.items()}
    gem_variant_ids = {key: pair[1] for key, pair in pairs.items()
                       if pair[1] is not None}
    for e in gems:
        if not _raw(e).get("gameId"):
            skipped.append({"table": "gem_ids", "entity_id": e.entity_id,
                            "reason": "gem row carries no gameId"})

    naming = CatalogNaming(
        class_names=class_names, class_tree_ids=class_tree_ids,
        ascendancy_names=ascendancy_names,
        ascendancy_tree_ids=ascendancy_tree_ids,
        node_ids=node_ids, ascendancy_node_ids=ascendancy_node_ids,
        attribute_options={entity_id("attribute_options", name): name
                           for name in ATTRIBUTE_OPTIONS},
        slot_names=slot_names,
        weapon_set_numbers={entity_id("weapon_sets", n): n
                            for n in WEAPON_SETS},
        base_names=base_names, skill_ids=skill_ids, gem_ids=gem_ids,
        gem_variant_ids=gem_variant_ids,
        support_skill_ids=support_skill_ids)
    naming.check_invertible()
    return NamingReport(naming=naming, ambiguous=tuple(ambiguous),
                        skipped=tuple(skipped))


def class_for_document_name(entities: Mapping[str, Sequence[CatalogEntity]],
                            class_name: str) -> str | None:
    """The class entity whose PoB name is exactly ``class_name``, if unique."""
    matches = [e.entity_id for e in entities.get("classes", ())
               if _raw(e).get("name") == class_name]
    return matches[0] if len(matches) == 1 else None


def _int(value: Any) -> int | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


# ----------------------------------------------------------- name lookup ---

RESOLVED = "resolved"
AMBIGUOUS = "ambiguous"
UNRESOLVED = "unresolved"


@dataclass(frozen=True)
class NameResolution:
    status: str
    name: str
    table: str
    entity_id: str | None = None
    candidates: tuple[str, ...] = ()
    reason: str = ""


def resolve_name(entities: Mapping[str, Sequence[CatalogEntity]], table: str,
                 name: str, *, locale: str = CATALOG_LOCALE) -> NameResolution:
    """Exact display name or alias, inside one entity table and locale."""
    if locale != CATALOG_LOCALE:
        return NameResolution(UNRESOLVED, name, table, reason=(
            "the catalog carries %s names only; %r is not translated"
            % (CATALOG_LOCALE, locale)))
    if table not in entities:
        return NameResolution(UNRESOLVED, name, table,
                              reason="no %s table in this catalog" % table)
    candidates = sorted({
        e.entity_id for e in entities[table]
        if name in e.display_names or name in e.aliases})
    if len(candidates) == 1:
        return NameResolution(RESOLVED, name, table, entity_id=candidates[0])
    if candidates:
        return NameResolution(AMBIGUOUS, name, table,
                              candidates=tuple(candidates),
                              reason="%d entities share this exact name"
                              % len(candidates))
    return NameResolution(UNRESOLVED, name, table,
                          reason="no entity has this exact name or alias")


# -------------------------------------------------------------- migration ---

@dataclass(frozen=True)
class EntityChange:
    field_path: str
    entity_id: str
    change: str  # "renamed" | "removed"
    before: tuple[str, ...] = ()
    after: tuple[str, ...] = ()


@dataclass(frozen=True)
class Migration:
    build: BuildSpec
    changes: tuple[EntityChange, ...]

    @property
    def removed(self) -> tuple[EntityChange, ...]:
        return tuple(c for c in self.changes if c.change == "removed")


def _references(build: BuildSpec) -> list[tuple[str, str, str]]:
    """(field path, catalog table, entity id) for every catalog reference.

    Weapon set and attribute option IDs, config input names and item hashes
    are not catalog table rows (``records.CATALOG_TABLES``), so they are not
    listed; items carry their own catalog references.
    """
    refs: list[tuple[str, str, str]] = [("/class_id", "classes", build.class_id)]
    if build.ascendancy_id is not None:
        refs.append(("/ascendancy_id", "ascendancies", build.ascendancy_id))
    for i, node in enumerate(build.passives.allocated):
        refs.append(("/passives/allocated/%d" % i, "passive_nodes", node))
    for i, node in enumerate(build.passives.ascendancy_allocated):
        refs.append(("/passives/ascendancy_allocated/%d" % i,
                     "passive_nodes", node))
    for i, socketed in enumerate(build.passives.socketed):
        refs.append(("/passives/socketed/%d/node_id" % i, "passive_nodes",
                     socketed.node_id))
    for i, weapon_set in enumerate(build.weapon_sets):
        for j, node in enumerate(weapon_set.passive_allocations):
            refs.append(("/weapon_sets/%d/passive_allocations/%d" % (i, j),
                         "passive_nodes", node))
    for node in sorted(build.passives.choices):
        refs.append(("/passives/choices/%s" % node, "passive_nodes", node))
    for slot in build.equipment:
        refs.append(("/equipment/%s" % slot, "slots", slot))

    def skill(path: str, entry: SkillEntry) -> None:
        refs.append((path + "/skill_id", "granted_skills", entry.skill_id))
        if entry.gem_id is not None:
            refs.append((path + "/gem_id", "gems", entry.gem_id))
        for k, support_id in enumerate(entry.support_ids):
            refs.append(("%s/support_ids/%d" % (path, k), "granted_skills",
                         support_id))
        if entry.supports is not ABSENT:
            for k, support in enumerate(entry.supports):
                refs.append(("%s/supports/%d/support_id" % (path, k),
                             "granted_skills", support.support_id))
                if support.gem_id is not None:
                    refs.append(("%s/supports/%d/gem_id" % (path, k), "gems",
                                 support.gem_id))
        for k, child in enumerate(entry.triggered):
            skill("%s/triggered/%d" % (path, k), child)

    for i, group in enumerate(build.skill_groups):
        if group.slot_id is not None:
            refs.append(("/skill_groups/%d/slot_id" % i, "slots",
                         group.slot_id))
        for j, entry in enumerate(group.skills):
            skill("/skill_groups/%d/skills/%d" % (i, j), entry)
    return refs


def migrate_build(build: BuildSpec,
                  source: Mapping[str, Sequence[CatalogEntity]],
                  target: Mapping[str, Sequence[CatalogEntity]], *,
                  target_catalog_hash: str, record_id: str,
                  created_at: str) -> Migration:
    """A new BuildSpec against ``target``; renamed and removed entities listed.

    An entity keeps its ID across patches when its native key is unchanged,
    which is how catalog IDs are built (``catalog/entities.py``). A changed
    display name is recorded as ``renamed``. An entity absent from the target
    is ``removed``: the reference stays as it was, is listed in
    ``unresolved_refs`` and makes the new record partial. Nothing is
    substituted, so a removed gem or passive is never silently replaced.
    """
    target_index = {(table, e.entity_id): e
                    for table, rows in target.items() for e in rows}
    source_index = {(table, e.entity_id): e
                    for table, rows in source.items() for e in rows}
    changes: list[EntityChange] = []
    unresolved: list[UnresolvedRef] = []
    for path, table, ident in _references(build):
        after = target_index.get((table, ident))
        if after is None:
            changes.append(EntityChange(path, ident, "removed"))
            unresolved.append(UnresolvedRef(
                field_path=path, reference=ident,
                reason="absent from the target patch catalog; not substituted"))
            continue
        before = source_index.get((table, ident))
        if before is not None and list(before.display_names) != list(
                after.display_names):
            changes.append(EntityChange(path, ident, "renamed",
                                        tuple(before.display_names),
                                        tuple(after.display_names)))
    status = build.parse_status
    if unresolved and status is RecordParseStatus.COMPLETE:
        status = RecordParseStatus.PARTIAL
    migrated = replace(
        build, record_id=record_id, created_at=created_at,
        catalog_hash=target_catalog_hash,
        provenance_ids=list(build.provenance_ids) + [build.record_id],
        parse_status=status,
        unresolved_refs=list(build.unresolved_refs) + unresolved)
    migrated = replace(migrated, build_hash=build_hash(migrated))
    return Migration(build=migrated, changes=tuple(changes))


# -------------------------------------------------------- item modifiers ---

_NUMBER = r"[+-]?\d+(?:\.\d+)?"
_SLOT = re.compile(r"\((" + _NUMBER + r")-(" + _NUMBER + r")\)|(" + _NUMBER + r")")
_HAS_RANGE = re.compile(r"\(" + _NUMBER + r"-" + _NUMBER + r"\)")

#: Modifier types drawn from the random affix pool. Unique, implicit and
#: other fixed modifiers are "Exclusive" upstream and not matched here.
AFFIX_TYPES = ("Prefix", "Suffix")


@dataclass(frozen=True)
class _Template:
    entity_id: str
    line: str
    pattern: re.Pattern[str]
    #: Per numeric slot: (low, high), equal for a fixed number.
    slots: tuple[tuple[float, float], ...]
    weights: tuple[tuple[str, float], ...]


def _compile(entity_id: str, line: str,
             weights: tuple[tuple[str, float], ...]) -> _Template:
    parts, slots, position = [], [], 0
    for match in _SLOT.finditer(line):
        parts.append(re.escape(line[position:match.start()]))
        parts.append("(" + _NUMBER + ")")
        if match.group(3) is not None:
            value = float(match.group(3))
            slots.append((value, value))
        else:
            low, high = float(match.group(1)), float(match.group(2))
            slots.append((min(low, high), max(low, high)))
        position = match.end()
    parts.append(re.escape(line[position:]))
    return _Template(entity_id, line, re.compile("^" + "".join(parts) + "$"),
                     tuple(slots), weights)


def _affix_templates(entities: Mapping[str, Sequence[CatalogEntity]]
                     ) -> list[_Template]:
    out = []
    for entity in entities.get("item_modifiers", ()):
        raw = _raw(entity)
        if raw.get("type") not in AFFIX_TYPES:
            continue
        weights = tuple(zip(raw.get("weightKey") or (),
                            (float(v) for v in raw.get("weightVal") or ())))
        for line in raw.get("lines") or ():
            out.append(_compile(entity.entity_id, str(line), weights))
    return out


def _spawns_on(template: _Template, tags: Sequence[str] | None) -> bool:
    """PoB's spawn rule: the first weight key the base has decides."""
    if tags is None:
        return True
    for key, weight in template.weights:
        if key in tags:
            return weight > 0
    return False


def _matches(template: _Template, text: str) -> bool:
    if _HAS_RANGE.search(text):
        # A line still in template form, as PoB writes a crafted roll.
        return text == template.line
    match = template.pattern.match(text)
    if match is None:
        return False
    for value, (low, high) in zip(match.groups(), template.slots):
        number = float(value)
        if not low <= number <= high:
            return False
    return True


@dataclass(frozen=True)
class ModifierMatch:
    source_position: int
    category: str
    text: str
    status: str
    candidates: tuple[str, ...] = ()


def _base_tags(item: ItemInstance,
               entities: Mapping[str, Sequence[CatalogEntity]]
               ) -> Sequence[str] | None:
    if item.base_id is None:
        return None
    for entity in entities.get("item_bases", ()):
        if entity.entity_id == item.base_id:
            tags = _raw(entity).get("tags")
            return list(tags) if isinstance(tags, (list, tuple)) else None
    return None


def resolve_item_modifiers(item: ItemInstance,
                           entities: Mapping[str, Sequence[CatalogEntity]]
                           ) -> tuple[ItemInstance, tuple[ModifierMatch, ...]]:
    """Match each modifier line to affix templates; never merge or sum.

    A template matches when its text matches with every rolled number inside
    the template's range, and it can spawn on the item's base (its first
    weight key present in the base's tags has a positive weight). One match
    resolves the line. Several leave it ``ambiguous`` with the candidate IDs;
    none leaves it ``unresolved``. Category, text and values are untouched.
    The returned item is partial when any line is not resolved.
    """
    templates = _affix_templates(entities)
    tags = _base_tags(item, entities)
    matches: list[ModifierMatch] = []
    modifiers = []
    for modifier in item.modifiers:
        candidates = tuple(sorted({
            t.entity_id for t in templates
            if _spawns_on(t, tags) and _matches(t, modifier.text)}))
        if len(candidates) == 1:
            status = ModifierParseStatus.RESOLVED
            modifier = replace(modifier, native_id=candidates[0],
                               resolved_effect_ids=[candidates[0]],
                               parse_status=status)
        else:
            status = (ModifierParseStatus.AMBIGUOUS if candidates
                      else ModifierParseStatus.UNRESOLVED)
            modifier = replace(modifier, native_id=None,
                               resolved_effect_ids=[], parse_status=status)
        modifiers.append(modifier)
        matches.append(ModifierMatch(modifier.source_position,
                                     modifier.category.value, modifier.text,
                                     status.value, candidates))
    resolved = all(m.parse_status is ModifierParseStatus.RESOLVED
                   for m in modifiers)
    parse_status = item.parse_status
    if not resolved and parse_status is RecordParseStatus.COMPLETE:
        parse_status = RecordParseStatus.PARTIAL
    out = replace(item, modifiers=modifiers, parse_status=parse_status)
    return replace(out, item_hash=item_hash(out)), tuple(matches)


TEMPLATE_CLAIM = "template_claim"
READY = "ready"


def item_readiness(item: ItemInstance) -> str:
    """``template_claim`` for a named item without stats; ``ready`` otherwise.

    A name such as a unique's is a claim about which item is meant, not the
    rolled item a calculation needs. Without any modifier line and with no
    resolved base, there is nothing to calculate from.
    """
    if not item.modifiers and not item.properties and item.base_id is None:
        return TEMPLATE_CLAIM
    if not item.modifiers and item.rarity in ("unique", "rare", "magic"):
        return TEMPLATE_CLAIM
    return READY
