"""Equipment pools across every catalog slot (P05-T03).

A pool lists, per slot of the patch profile, the items a search may equip:
owned items, imported listings and imported items without a listing. It
replaces the legacy weapon-only harvester for new work.

Which items fit a slot comes only from the profile's ``SlotRule``
``accepted_base_categories`` matched against the catalog base's ``type``.
A slot whose rule names no category is ``missing_category_rule``: imported
items are not placed there by guess, only owned items a source build put in
that slot. The pinned P02 export names no category for any slot (its gap
``slot-accepted-base-categories``), so a pool built from it holds owned items
only, and says so per slot.

Bounds are sampling bounds, recorded in the pool and for the run manifest
(``sampling_parameters``): up to ``listings_per_slot`` non-owned candidates
per slot and ``enabling_queries_per_run`` enabling declarations. Past the
listing bound, candidates are taken round-robin over (base, modifier
signature) groups, so bases and stat combinations stay represented. Nothing
is ordered, capped or rejected by price, and no score is computed: pairs and
full configurations are evaluated by P08, never by adding per-slot gains.

An enabling declaration names bases and modifier patterns. Items it matches
are kept in every slot it applies to, past the bound, whatever their
standalone value. No approved route can run it as a market query (D01), so
its status is ``unexecuted``; declarations past the run bound are
``over_bound`` and are not applied.
"""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from dataclasses import dataclass, replace
from typing import Callable, Iterable, Mapping, Sequence

from ..domain.enums import (Availability, CandidateAvailability,
                            EnablingQueryStatus, PoolSlotStatus,
                            RecordParseStatus)
from ..domain.identity import build_hash, pool_hash
from ..domain.records import (SCHEMA_VERSION, BuildSpec, DataGap,
                              EnablingQueryOutcome, EquipmentPool,
                              EquipmentSlot, GameCatalog, ItemInstance,
                              Listing, PatchProfile, PoolCandidate,
                              PoolSampling, SlotPool)
from ..evaluation.legality.inputs import normalize_id

DEFAULT_LISTINGS_PER_SLOT = 500
DEFAULT_ENABLING_QUERIES_PER_RUN = 100

#: The DataGap field path that marks missing slot category rules.
SLOT_RULES_PATH = "/character_rules/slots"

UNEXECUTED_REASON = ("no approved market route can run it (D01: public market "
                     "access is unsupported_access); matched against imported "
                     "and owned items only")
OVER_BOUND_REASON = "past the run's enabling-query bound of %d; not applied"

_NUMBER = re.compile(r"\d+(?:\.\d+)?")


def sampling(listings_per_slot: int = DEFAULT_LISTINGS_PER_SLOT,
             enabling_queries_per_run: int = DEFAULT_ENABLING_QUERIES_PER_RUN
             ) -> PoolSampling:
    for name, value in (("listings_per_slot", listings_per_slot),
                        ("enabling_queries_per_run", enabling_queries_per_run)):
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise ValueError("%s must be a non-negative integer" % name)
    return PoolSampling(listings_per_slot, enabling_queries_per_run)


def sampling_parameters(bounds: PoolSampling) -> dict:
    """The bounds as ``RunManifest.search_parameters`` records them."""
    return {"pool_sampling": {
        "listings_per_slot": bounds.listings_per_slot,
        "enabling_queries_per_run": bounds.enabling_queries_per_run}}


@dataclass(frozen=True)
class EnablingQuery:
    """An explicit enabling-interaction declaration.

    An item matches when its base is in ``base_ids`` (if given) and every
    pattern in ``modifier_patterns`` (regular expressions) matches one of its
    modifier lines (if given). At least one of the two is required.
    """

    query_id: str
    description: str
    slot_ids: tuple[str, ...] = ()
    base_ids: tuple[str, ...] = ()
    modifier_patterns: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.query_id.strip():
            raise ValueError("an enabling query needs an id")
        if not self.base_ids and not self.modifier_patterns:
            raise ValueError("enabling query %r names no base and no modifier "
                             "pattern" % self.query_id)
        for pattern in self.modifier_patterns:
            re.compile(pattern)

    def applies_to(self, slot_id: str) -> bool:
        return not self.slot_ids or slot_id in self.slot_ids

    def matches(self, item: ItemInstance) -> bool:
        if self.base_ids and item.base_id not in self.base_ids:
            return False
        return all(any(re.search(pattern, m.text) for m in item.modifiers)
                   for pattern in self.modifier_patterns)


@dataclass(frozen=True)
class OwnedItem:
    """An item the user has. ``slot_ids`` are slots a source build put it in."""

    item_hash: str
    count: int = 1
    slot_ids: tuple[str, ...] = ()


def owned_from_build(build: BuildSpec) -> list[OwnedItem]:
    """The items a build equips, with the slots it equips them in.

    An item equipped through a listing is not owned. Each equipped slot is one
    physical item, so an item hash in two slots counts two.
    """
    slots: dict[str, list[str]] = defaultdict(list)
    for slot_id, content in sorted(build.equipment.items()):
        if content is not None and content.listing_id is None:
            slots[content.item_hash].append(slot_id)
    return [OwnedItem(item_hash, len(ids), tuple(ids))
            for item_hash, ids in sorted(slots.items())]


def _signature(item: ItemInstance) -> tuple:
    return tuple(sorted({(m.category.value, _NUMBER.sub("#", m.text))
                         for m in item.modifiers}))


def _sample(candidates: list[tuple[ItemInstance, PoolCandidate]],
            limit: int) -> list[tuple[ItemInstance, PoolCandidate]]:
    """Round-robin over (base, signature) groups; deterministic, price-blind."""
    if len(candidates) <= limit:
        return candidates
    groups: dict[tuple, list] = defaultdict(list)
    for entry in candidates:
        groups[(entry[0].base_id or "", _signature(entry[0]))].append(entry)
    queues = [groups[key] for key in sorted(groups)]
    out: list = []
    depth = 0
    while len(out) < limit:
        taken = False
        for queue in queues:
            if depth < len(queue):
                out.append(queue[depth])
                taken = True
                if len(out) == limit:
                    break
        if not taken:
            break
        depth += 1
    return out


def _candidate_key(entry) -> tuple:
    item, candidate = entry
    return (item.item_hash, candidate.listing_id or "")


def build_pool(*, catalog: GameCatalog, profile: PatchProfile,
               items: Iterable[ItemInstance], listings: Iterable[Listing] = (),
               owned: Iterable[OwnedItem] = (),
               queries: Sequence[EnablingQuery] = (),
               bounds: PoolSampling | None = None,
               gaps: Iterable[DataGap] = (), created_at: str,
               provenance_ids: Sequence[str] = ()) -> EquipmentPool:
    """One pool over every slot of ``profile``. Takes no price or budget."""
    if catalog.catalog_hash != profile.catalog_hash:
        raise ValueError("the catalog is %s and the profile pins %s"
                         % (catalog.catalog_hash, profile.catalog_hash))
    bounds = bounds or sampling()
    categories = {entity.entity_id: (entity.raw_reference or {}).get("type")
                  for entity in catalog.entities.get("item_bases", ())}
    by_hash: dict[str, ItemInstance] = {}
    for item in items:
        by_hash.setdefault(item.item_hash, item)
    listed: dict[str, list[Listing]] = defaultdict(list)
    for listing in listings:
        listed[listing.item_hash].append(listing)
    owned_by_hash: dict[str, OwnedItem] = {}
    for entry in owned:
        if entry.count < 1:
            raise ValueError("owned count for %s must be at least one"
                             % entry.item_hash)
        if entry.item_hash not in by_hash:
            raise ValueError("owned item %s is not among the items"
                             % entry.item_hash)
        owned_by_hash[entry.item_hash] = entry

    repeated = [k for k, n in Counter(q.query_id for q in queries).items()
                if n > 1]
    if repeated:
        raise ValueError("enabling query ids repeat: %s" % ", ".join(repeated))
    in_bound = list(queries[:bounds.enabling_queries_per_run])
    outcomes = [EnablingQueryOutcome(
        query_id=q.query_id, description=q.description,
        slot_ids=list(q.slot_ids), base_ids=list(q.base_ids),
        modifier_patterns=list(q.modifier_patterns),
        status=EnablingQueryStatus.UNEXECUTED, reason=UNEXECUTED_REASON,
        matched_item_hashes=sorted(h for h, item in by_hash.items()
                                   if q.matches(item)))
        for q in in_bound]
    outcomes += [EnablingQueryOutcome(
        query_id=q.query_id, description=q.description,
        slot_ids=list(q.slot_ids), base_ids=list(q.base_ids),
        modifier_patterns=list(q.modifier_patterns),
        status=EnablingQueryStatus.OVER_BOUND,
        reason=OVER_BOUND_REASON % bounds.enabling_queries_per_run,
        matched_item_hashes=[])
        for q in queries[bounds.enabling_queries_per_run:]]
    matched = {o.query_id: set(o.matched_item_hashes) for o in outcomes}

    placed: set[str] = set()
    slots: list[SlotPool] = []
    for rule in sorted(profile.character_rules.slots, key=lambda r: r.slot_id):
        accepted = set(rule.accepted_base_categories)

        def fits(item: ItemInstance) -> bool:
            return bool(accepted) and categories.get(item.base_id) in accepted

        def reasons(item: ItemInstance) -> list[str]:
            return ["enabling:%s" % q.query_id for q in in_bound
                    if q.applies_to(rule.slot_id)
                    and item.item_hash in matched[q.query_id]]

        partial = unavailable = 0
        owned_here: list[PoolCandidate] = []
        others: list[tuple[ItemInstance, PoolCandidate]] = []
        for item_hash in sorted(by_hash):
            item = by_hash[item_hash]
            own = owned_by_hash.get(item_hash)
            here = fits(item) or (own is not None and rule.slot_id in {
                normalize_id("slots", slot) for slot in own.slot_ids})
            if not here:
                continue
            if item.parse_status is not RecordParseStatus.COMPLETE:
                partial += 1
                continue
            placed.add(item_hash)
            if own is not None:
                owned_here.append(PoolCandidate(
                    item_hash=item_hash, listing_id=None,
                    availability=CandidateAvailability.OWNED,
                    quantity=own.count,
                    retained_for=["owned", *reasons(item)]))
            if not fits(item):
                continue
            item_listings = sorted(listed.get(item_hash, ()),
                                   key=lambda listing: listing.listing_id)
            for listing in item_listings:
                if listing.availability is Availability.UNAVAILABLE:
                    unavailable += 1
                    continue
                others.append((item, PoolCandidate(
                    item_hash=item_hash, listing_id=listing.listing_id,
                    availability=CandidateAvailability(listing.availability.value),
                    quantity=listing.quantity, retained_for=[])))
            if not item_listings and own is None:
                others.append((item, PoolCandidate(
                    item_hash=item_hash, listing_id=None,
                    availability=CandidateAvailability.UNKNOWN, quantity=None,
                    retained_for=[])))

        required = [e for e in others if reasons(e[0])]
        rest = [e for e in others if not reasons(e[0])]
        room = max(0, bounds.listings_per_slot - len(required))
        kept = sorted(required, key=_candidate_key) + _sample(
            sorted(rest, key=_candidate_key), room)
        candidates = owned_here + [
            replace(c, retained_for=reasons(item) or ["sample"])
            for item, c in kept]
        if not accepted:
            status = PoolSlotStatus.MISSING_CATEGORY_RULE
        elif candidates:
            status = PoolSlotStatus.POPULATED
        else:
            status = PoolSlotStatus.EMPTY
        slots.append(SlotPool(
            slot_id=rule.slot_id, weapon_set_id=rule.weapon_set_id,
            accepted_base_categories=sorted(accepted), status=status,
            candidates=candidates, considered_count=len(others),
            retained_count=len(kept), truncated=len(others) > len(kept),
            unavailable_count=unavailable, partial_count=partial))

    gap_ids = []
    if any(s.status is PoolSlotStatus.MISSING_CATEGORY_RULE for s in slots):
        gap_ids = sorted(g.gap_id for g in gaps
                         if SLOT_RULES_PATH in g.field_paths)
    pool = EquipmentPool(
        schema_version=SCHEMA_VERSION, record_id="", created_at=created_at,
        provenance_ids=list(dict.fromkeys(
            [catalog.record_id, profile.record_id, *provenance_ids])),
        pool_id="",
        catalog_hash=catalog.catalog_hash, patch_profile_id=profile.record_id,
        sampling=bounds, slots=slots, enabling_queries=outcomes,
        unplaced_item_hashes=sorted(set(by_hash) - placed), gap_ids=gap_ids)
    pool_id = "equipment-pool/" + pool_hash(pool)
    return replace(pool, record_id=pool_id, pool_id=pool_id)


def pool_report(pool: EquipmentPool) -> dict:
    """Truncation, missing categories and query coverage, for a report."""
    statuses = Counter(q.status.value for q in pool.enabling_queries)
    return {
        "pool_id": pool.pool_id,
        "sampling": {"listings_per_slot": pool.sampling.listings_per_slot,
                     "enabling_queries_per_run":
                         pool.sampling.enabling_queries_per_run,
                     "claim": "sampling bounds, not an exhaustive market"},
        "slots": {s.slot_id: {"status": s.status.value,
                              "candidates": len(s.candidates),
                              "considered": s.considered_count,
                              "retained": s.retained_count,
                              "truncated": s.truncated,
                              "unavailable": s.unavailable_count,
                              "partial": s.partial_count}
                  for s in pool.slots},
        "truncated_slots": [s.slot_id for s in pool.slots if s.truncated],
        "missing_category_slots": [
            s.slot_id for s in pool.slots
            if s.status is PoolSlotStatus.MISSING_CATEGORY_RULE],
        "empty_slots": [s.slot_id for s in pool.slots
                        if s.status is PoolSlotStatus.EMPTY],
        "queries": {"declared": len(pool.enabling_queries),
                    "unexecuted": statuses.get("unexecuted", 0),
                    "over_bound": statuses.get("over_bound", 0),
                    "executed": 0,
                    "locally_matched": sum(
                        1 for q in pool.enabling_queries
                        if q.matched_item_hashes)},
        "unplaced_items": len(pool.unplaced_item_hashes),
        "gap_ids": list(pool.gap_ids),
    }


# ------------------------------------------------- assignment checks ===

@dataclass(frozen=True)
class EquipmentConflict:
    """Equipment a build cannot hold at once, or outside the pool."""

    code: str
    slot_ids: tuple[str, ...]
    item_hash: str
    listing_id: str | None
    allowed: int
    used: int


def equipment_conflicts(build: BuildSpec, *,
                        listings: Mapping[str, Listing] | Iterable[Listing] = (),
                        owned: Iterable[OwnedItem] = (),
                        pool: EquipmentPool | None = None
                        ) -> list[EquipmentConflict]:
    """Physical-item conflicts in ``build.equipment``.

    One listing fills at most ``quantity`` slots; an unknown quantity counts
    as one. An owned item fills at most its owned count. An item with neither
    a listing nor ownership is one physical item at most. With ``pool``, each
    slot's item must be one of that slot's candidates.
    """
    if not isinstance(listings, Mapping):
        listings = {listing.listing_id: listing for listing in listings}
    owned_count = {entry.item_hash: entry.count for entry in owned}
    by_listing: dict[str, list[str]] = defaultdict(list)
    by_item: dict[str, list[str]] = defaultdict(list)
    out: list[EquipmentConflict] = []
    slot_pools = {s.slot_id: s for s in pool.slots} if pool else {}
    for slot_id, content in sorted(build.equipment.items()):
        if content is None:
            continue
        if content.listing_id is not None:
            by_listing[content.listing_id].append(slot_id)
        else:
            by_item[content.item_hash].append(slot_id)
        if pool is not None and not _in_pool(
                slot_pools.get(normalize_id("slots", slot_id)), content):
            out.append(EquipmentConflict("not_in_pool", (slot_id,),
                                         content.item_hash, content.listing_id,
                                         0, 1))
    for listing_id, slot_ids in sorted(by_listing.items()):
        listing = listings.get(listing_id)
        allowed = (listing.quantity if listing is not None
                   and listing.quantity is not None else 1)
        if len(slot_ids) > allowed:
            item_hash = build.equipment[slot_ids[0]].item_hash
            out.append(EquipmentConflict("listing_over_quantity",
                                         tuple(slot_ids), item_hash,
                                         listing_id, allowed, len(slot_ids)))
    for item_hash, slot_ids in sorted(by_item.items()):
        allowed = owned_count.get(item_hash, 1)
        if len(slot_ids) > allowed:
            code = ("owned_over_count" if item_hash in owned_count
                    else "unlisted_item_reused")
            out.append(EquipmentConflict(code, tuple(slot_ids), item_hash,
                                         None, allowed, len(slot_ids)))
    return out


def _in_pool(slot: SlotPool | None, content: EquipmentSlot) -> bool:
    if slot is None:
        return False
    return any(c.item_hash == content.item_hash
               and c.listing_id == content.listing_id
               for c in slot.candidates)


# --------------------------------------------------- equipment change ===

@dataclass(frozen=True)
class EquipmentChange:
    build: BuildSpec
    #: The full-build legality report of the changed build.
    legality: object
    conflicts: tuple[EquipmentConflict, ...]


def change_equipment(build: BuildSpec, slot_id: str,
                     candidate: PoolCandidate | None, *,
                     profile: PatchProfile, catalog: GameCatalog | None,
                     items: Mapping[str, ItemInstance] | Iterable[ItemInstance],
                     measure: Callable[[BuildSpec], object] | None = None,
                     listings: Mapping[str, Listing] | Iterable[Listing] = (),
                     owned: Iterable[OwnedItem] = (),
                     pool: EquipmentPool | None = None) -> EquipmentChange:
    """Put ``candidate`` in ``slot_id`` and recheck the whole build.

    Every equipped item's requirements and the build's resources are checked
    again by the P02-T03 validator, not only the changed slot. Character
    attributes and resource pools depend on all equipment, so a measurement
    of the old build is never reused: ``measure`` is called with the new
    build, and without it those checks are ``unknown``.
    """
    from ..evaluation.legality import LegalityValidator

    equipment = dict(build.equipment)
    equipment[slot_id] = (None if candidate is None else EquipmentSlot(
        item_hash=candidate.item_hash, listing_id=candidate.listing_id))
    changed = replace(build, equipment=equipment)
    new_hash = build_hash(changed)
    changed = replace(changed, build_hash=new_hash, record_id=new_hash)
    measured = measure(changed) if measure is not None else None
    report = LegalityValidator(catalog=catalog, items=items,
                               measured=measured).validate(changed, profile)
    conflicts = equipment_conflicts(changed, listings=listings, owned=owned,
                                    pool=pool)
    return EquipmentChange(changed, report, tuple(conflicts))
