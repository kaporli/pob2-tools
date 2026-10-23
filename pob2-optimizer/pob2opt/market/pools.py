"""Equipment pools across every catalog slot (P05-T03).

A pool lists, per slot of the patch profile, the items a search may equip:
owned items, imported listings and imported items without a listing. It
replaces the legacy weapon-only harvester for new work.

Which items fit a slot comes only from the profile's ``SlotRule``
``accepted_base_categories`` matched against the catalog base's category
(``type``, or ``type/subType``; see ``catalog/slotrules.py``). A slot whose
rule names no category is ``missing_category_rule``: imported items are not
placed there by guess, only owned items a source build put in that slot.
Profiles exported before P02-T03.1 name no category for any slot (gap
``slot-accepted-base-categories``); since P02-T03.1 the categories are read
from the engine and only conditional slots stay empty.

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

from ..catalog.slotrules import (ACCEPTED, REFUSED, UNDECIDED, decide,
                                 rule_gaps)
from ..domain.enums import (Availability, CandidateAvailability,
                            EnablingQueryStatus, ModifierParseStatus,
                            PoolSlotStatus, RecordParseStatus)
from ..domain.identity import build_hash, item_identity, pool_hash
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


#: Where a build came from, for ``owned_from_build``.
OWNED_CHARACTER = "owned_character"
IMPORTED_GUIDE = "imported_guide"


def owned_from_build(build: BuildSpec, *, origin: str) -> list[OwnedItem]:
    """The items a build equips, with the slots it equips them in.

    ``origin`` is required: only the user's own character (an account import
    the user asked for) proves ownership. An imported guide or any other
    build owns nothing, and an item without a listing is not thereby owned.
    An item equipped through a listing is not owned. Each equipped slot is one
    physical item, so an item hash in two slots counts two.
    """
    if origin == IMPORTED_GUIDE:
        return []
    if origin != OWNED_CHARACTER:
        raise ValueError("origin must be %r or %r, not %r"
                         % (OWNED_CHARACTER, IMPORTED_GUIDE, origin))
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


#: ``retained_for`` marks. Every exploratory candidate carries EXPLORATORY
#: plus its reason; a slot holding only exploratory candidates is
#: ``exploratory_only``, never ``populated``, and none of them counts as
#: complete or recommendation-ready coverage.
EXPLORATORY = "exploratory"
#: A partial item placed because its stats are known (``stat_known``). A
#: build using it stays partial and non-recommendable.
STAT_KNOWN_PARTIAL = "stat_known_partial"
#: The slot rule leaves this base, category or rarity undecided.
SLOT_RULE_UNDECIDED = "slot_rule_undecided"
#: An owned item kept in its source slot although the rule does not accept it.
OWNED_SLOT_UNVERIFIED = "owned_slot_unverified"
_STAT_KNOWN = (ModifierParseStatus.RESOLVED, ModifierParseStatus.AMBIGUOUS,
               ModifierParseStatus.STAT_RESOLVED)


def stat_known(item: ItemInstance) -> bool:
    """A partial item whose every stat is a catalog stat (P02-T03.1).

    Its base is resolved, it has modifier lines, and each line is resolved,
    ambiguous between catalog affixes, or ``stat_resolved``: the stats are
    known and only which affix rolled a line is not. Such an item is placed in
    the pool, marked ``stat_known_partial``; it is not made complete, so a
    build equipping it keeps its P04 partial status. An item with an
    unresolved line or base is never placed.
    """
    statuses = [m.parse_status for m in item.modifiers]
    # Partial for an affix identity and nothing else: at least one line is
    # not resolved, and every line's stat is known.
    return (item.parse_status is RecordParseStatus.PARTIAL
            and item.base_id is not None
            and any(st is not ModifierParseStatus.RESOLVED for st in statuses)
            and all(st in _STAT_KNOWN for st in statuses))


def marks(item: ItemInstance, verdict: str = ACCEPTED) -> list[str]:
    """Exploratory marks for one item in one slot; empty when it is neither."""
    out = []
    if item.parse_status is not RecordParseStatus.COMPLETE:
        out.append(STAT_KNOWN_PARTIAL)
    if verdict == UNDECIDED:
        out.append(SLOT_RULE_UNDECIDED)
    elif verdict == REFUSED:
        out.append(OWNED_SLOT_UNVERIFIED)
    return [EXPLORATORY, *out] if out else []


def is_exploratory(candidate: PoolCandidate) -> bool:
    return EXPLORATORY in candidate.retained_for


def _undecided_categories(rule) -> list:
    value = getattr(rule, "undecided_categories", None)
    return list(value) if isinstance(value, list) else []


def build_pool(*, catalog: GameCatalog, profile: PatchProfile,
               items: Iterable[ItemInstance], listings: Iterable[Listing] = (),
               owned: Iterable[OwnedItem] = (),
               queries: Sequence[EnablingQuery] = (),
               bounds: PoolSampling | None = None,
               gaps: Iterable[DataGap] = (), created_at: str,
               provenance_ids: Sequence[str] = ()) -> EquipmentPool:
    """One pool over every slot of ``profile``. Takes no price or budget.

    All inputs must belong to the pinned catalog and exact realm/league.
    Mixed scopes and conflicting item identities/readiness are refused before
    matching or sampling. Reparse/reconcile those records before retrying;
    input order must never promote a partial item to a complete candidate.
    """
    if catalog.catalog_hash != profile.catalog_hash:
        raise ValueError("the catalog is %s and the profile pins %s"
                         % (catalog.catalog_hash, profile.catalog_hash))
    items, listings = list(items), list(listings)
    wrong_items = sorted({i.record_id for i in items
                          if i.catalog_hash != profile.catalog_hash})
    wrong_listings = sorted({l.listing_id for l in listings
                            if (l.realm, l.league_id) !=
                            (profile.realm, profile.league_id)})
    if wrong_items or wrong_listings:
        raise ValueError("pool input scope mismatch: items=%r; listings=%r"
                         % (wrong_items, wrong_listings))
    bounds = bounds or sampling()
    raws = {entity.entity_id: entity.raw_reference
            for entity in catalog.entities.get("item_bases", ())}
    by_hash: dict[str, ItemInstance] = {}
    conflicting = set()
    for item in sorted(items, key=lambda i: (i.item_hash, i.record_id)):
        previous = by_hash.setdefault(item.item_hash, item)
        if (previous.parse_status != item.parse_status or
                item_identity(previous) != item_identity(item)):
            conflicting.add(item.item_hash)
    if conflicting:
        raise ValueError("conflicting pool item identity or parse status: %s"
                         % ", ".join(sorted(conflicting)))
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
    undecided_gaps: set[str] = set()
    slots: list[SlotPool] = []
    for rule in sorted(profile.character_rules.slots, key=lambda r: r.slot_id):
        accepted = set(rule.accepted_base_categories)

        def verdict(item: ItemInstance) -> str:
            if item.base_id not in raws:
                return REFUSED
            return decide(rule, raws[item.base_id], item.rarity)

        def fits(item: ItemInstance) -> bool:
            return verdict(item) in (ACCEPTED, UNDECIDED)

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
            if (item.parse_status is not RecordParseStatus.COMPLETE
                    and not stat_known(item)):
                partial += 1
                continue
            placed.add(item_hash)
            if own is not None:
                owned_here.append(PoolCandidate(
                    item_hash=item_hash, listing_id=None,
                    availability=CandidateAvailability.OWNED,
                    quantity=own.count,
                    retained_for=["owned", *reasons(item),
                                  *marks(item, verdict(item))]))
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
            replace(c, retained_for=(reasons(item) or ["sample"])
                    + marks(item, verdict(item)))
            for item, c in kept]
        if any(SLOT_RULE_UNDECIDED in c.retained_for for c in candidates):
            undecided_gaps.update(rule_gaps(rule))
        if not accepted and not _undecided_categories(rule):
            status = PoolSlotStatus.MISSING_CATEGORY_RULE
        elif any(not is_exploratory(c) for c in candidates):
            status = PoolSlotStatus.POPULATED
        elif candidates:
            status = PoolSlotStatus.EXPLORATORY_ONLY
        else:
            status = PoolSlotStatus.EMPTY
        slots.append(SlotPool(
            slot_id=rule.slot_id, weapon_set_id=rule.weapon_set_id,
            accepted_base_categories=sorted(accepted), status=status,
            candidates=candidates, considered_count=len(others),
            retained_count=len(kept), truncated=len(others) > len(kept),
            unavailable_count=unavailable, partial_count=partial))

    gap_ids = set(undecided_gaps)
    if any(s.status is PoolSlotStatus.MISSING_CATEGORY_RULE for s in slots):
        gap_ids.update(g.gap_id for g in gaps
                       if SLOT_RULES_PATH in g.field_paths)
    gap_ids = sorted(gap_ids)
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
                              "complete_candidates": sum(
                                  1 for c in s.candidates
                                  if not is_exploratory(c)),
                              "exploratory_candidates": sum(
                                  1 for c in s.candidates if is_exploratory(c)),
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
        # Coverage counts only complete, rule-accepted candidates.
        "populated_slots": [s.slot_id for s in pool.slots
                            if s.status is PoolSlotStatus.POPULATED],
        "exploratory_only_slots": [
            s.slot_id for s in pool.slots
            if s.status is PoolSlotStatus.EXPLORATORY_ONLY],
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
