"""The profile's rules and the build, arranged for the checks (P02-T03).

``RuleView`` reads ``CharacterRules`` and answers "what does the profile say"
with ``None`` when it says nothing. No number here is a literal: the point
maximums, the level range, the support limit and the weapon-set shape all come
from the record P02-T02 exported, and an absent rule stays absent.

``Context`` holds everything a check needs and settles one question up front:
when an ``ImportedState`` is present, allocation and equipment are read from
the engine, not from the record, because the record is a claim about a
document and the engine is what the document became.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

from ...domain.records import (BuildSpec, CharacterRules, ItemInstance,
                               PatchProfile, PointBudgetRule, SlotRule,
                               SupportRestriction, WeaponSetRules)
from .gaps import GapFactory
from .inputs import CatalogIndex, ImportedItem, ImportedState, MeasuredState, native_key

#: Progression flags P02-T02 stamps on the budget rules it exports.
FLAG_LEVELLING = "levelling_points_only"
FLAG_MAXIMUM = "ascendancy_points_maximum"
FLAG_WEAPON_SET = "weapon_set_points"


class RuleView:
    """Read-only access to one profile's character rules."""

    def __init__(self, rules: CharacterRules) -> None:
        self.rules = rules
        self.slots_by_id: dict[str, SlotRule] = {
            slot.slot_id: slot for slot in rules.slots}
        self.weapon_sets: WeaponSetRules = rules.weapon_sets

    # -- level and membership ---------------------------------------------

    @property
    def level_minimum(self) -> int:
        return self.rules.level_range.minimum

    @property
    def level_maximum(self) -> int:
        return self.rules.level_range.maximum

    @property
    def class_ascendancies(self) -> Mapping[str, Sequence[str]]:
        return self.rules.class_ascendancies

    # -- budgets -----------------------------------------------------------

    def _by_flag(self, flag: str) -> list[PointBudgetRule]:
        return [rule for rule in self.rules.point_budgets
                if flag in rule.required_progression_flags]

    def levelling_budget(self, level: int) -> PointBudgetRule | None:
        for rule in self._by_flag(FLAG_LEVELLING):
            if rule.level == level:
                return rule
        return None

    def maximum_budget(self) -> PointBudgetRule | None:
        rules = self._by_flag(FLAG_MAXIMUM)
        return rules[0] if rules else None

    def weapon_set_budget(self) -> PointBudgetRule | None:
        rules = self._by_flag(FLAG_WEAPON_SET)
        return rules[0] if rules else None

    # -- supports and slots ------------------------------------------------

    @property
    def support_restrictions(self) -> Sequence[SupportRestriction]:
        return self.rules.support_restrictions

    def support_limit(self) -> SupportRestriction | None:
        """The restriction that carries a maximum, if the profile has one."""
        for restriction in self.rules.support_restrictions:
            if restriction.max_supports is not None:
                return restriction
        return None

    def slot(self, slot_id: str) -> SlotRule | None:
        return self.slots_by_id.get(slot_id)

    @property
    def gem_level_limit(self) -> int | None:
        return self.rules.gem_level_limit

    @property
    def skill_level_limit(self) -> int | None:
        return self.rules.skill_level_limit


@dataclass(frozen=True, slots=True)
class Equipped:
    """One occupied equipment slot, from the record and from the engine.

    Either side can be absent: an item the record equips that the engine does
    not hold is a different problem from one the engine holds that the record
    does not mention, and both are reported.
    """

    slot_id: str
    item_hash: str | None
    listing_id: str | None
    record: ItemInstance | None
    imported: ImportedItem | None

    @property
    def label(self) -> str:
        if self.record is not None and self.record.display_name:
            return self.record.display_name
        if self.imported is not None and self.imported.name:
            return str(self.imported.name)
        return self.item_hash or self.slot_id

    def requirement(self, name: str) -> float | None:
        """Validate imported equipment; disagreements are reported separately."""
        if self.imported is not None:
            value = self.imported.requirements.get(name)
            if value is not None:
                return float(value)
        if self.record is not None:
            value = self.record.requirements.get(name)
            if value is not None:
                return float(value)
        return None

    @property
    def sourced(self) -> bool:
        """True when the item traces to a document or a listing."""
        if self.listing_id:
            return True
        return bool(self.record is not None and self.record.source_document_id)


@dataclass
class Context:
    build: BuildSpec
    profile: PatchProfile
    rules: RuleView
    catalog: CatalogIndex
    items: Mapping[str, ItemInstance]
    imported: ImportedState | None
    measured: MeasuredState | None
    gaps: GapFactory
    equipped: tuple[Equipped, ...] = ()
    allocated: tuple[str, ...] = ()
    ascendancy_allocated: tuple[str, ...] = ()
    allocation_source: str = "record"
    equipment_source: str = "record"
    unresolved: list[str] = field(default_factory=list)

    @property
    def level(self) -> int:
        """The level legality is decided at: the engine's when there is one."""
        if self.imported is not None and self.imported.level is not None:
            return int(self.imported.level)
        return int(self.build.level)

    @property
    def points_used(self) -> int:
        """Ordinary passive points spent.

        The engine's own count when there is one: it excludes the class start
        node and any node the tree grants for free, which counting allocated
        ids does not.
        """
        if self.imported is not None and self.imported.points_used is not None:
            return int(self.imported.points_used)
        return len(set(self.allocated))

    @property
    def ascendancy_points_used(self) -> int:
        if (self.imported is not None
                and self.imported.ascendancy_points_used is not None):
            return int(self.imported.ascendancy_points_used)
        return len(set(self.ascendancy_allocated))

    @property
    def points_basis(self) -> str:
        return ("the engine's own point count"
                if self.allocation_source == "engine"
                else "the record's allocation list")

    def item_for(self, item_hash: str | None) -> ItemInstance | None:
        if not item_hash:
            return None
        return self.items.get(item_hash)

    def slot_ids(self) -> tuple[str, ...]:
        return tuple(entry.slot_id for entry in self.equipped)


def build_context(build: BuildSpec, profile: PatchProfile, *,
                  catalog: CatalogIndex,
                  items: Mapping[str, ItemInstance],
                  imported: ImportedState | None,
                  measured: MeasuredState | None,
                  gaps: GapFactory) -> Context:
    """Assemble the context, choosing engine state over record claims."""
    from .inputs import normalize_id

    rules = RuleView(profile.character_rules)
    ctx = Context(build=build, profile=profile, rules=rules, catalog=catalog,
                  items=dict(items), imported=imported,
                  measured=measured if measured is not None
                  else (imported.measured if imported is not None else None),
                  gaps=gaps)

    # -- allocation --------------------------------------------------------
    if imported is not None:
        ctx.allocation_source = "engine"
        ctx.allocated = tuple(normalize_id("passive_nodes", node)
                              for node in imported.allocated_nodes)
        ctx.ascendancy_allocated = tuple(normalize_id("passive_nodes", node)
                                         for node in imported.ascendancy_nodes)
    else:
        ctx.allocated = tuple(normalize_id("passive_nodes", node)
                              for node in build.passives.allocated)
        ctx.ascendancy_allocated = tuple(
            normalize_id("passive_nodes", node)
            for node in build.passives.ascendancy_allocated)

    # -- equipment ---------------------------------------------------------
    record_slots: dict[str, tuple[str | None, str | None]] = {}
    for slot_id, entry in build.equipment.items():
        if entry is None:
            continue
        record_slots[normalize_id("slots", slot_id)] = (entry.item_hash,
                                                        entry.listing_id)
    imported_slots: dict[str, ImportedItem] = {}
    if imported is not None:
        ctx.equipment_source = "engine"
        for item in imported.items.values():
            imported_slots[item.slot_id] = item

    equipped: list[Equipped] = []
    for slot_id in sorted(set(record_slots) | set(imported_slots)):
        item_hash, listing_id = record_slots.get(slot_id, (None, None))
        equipped.append(Equipped(
            slot_id=slot_id,
            item_hash=item_hash,
            listing_id=listing_id,
            record=ctx.item_for(item_hash),
            imported=imported_slots.get(slot_id)))
    ctx.equipped = tuple(equipped)
    return ctx


def numeric_node(reference: str) -> int | None:
    key = native_key("passive_nodes", reference)
    try:
        return int(key)
    except (TypeError, ValueError):
        return None


def numeric_class(reference: Any) -> int | None:
    key = native_key("classes", reference)
    try:
        return int(key)
    except (TypeError, ValueError):
        return None
