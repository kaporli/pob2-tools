"""P05-T03: equipment pools across catalog slots. Offline, synthetic.

Acceptance cases from docs/specs/projects/P05-trade.md, by test name:

* a weak standalone enabler survives pool construction and enables the best
  pair: ``test_acceptance_weak_enabler_survives_and_enables_the_best_pair``;
* a listing cannot occupy both ring slots without sufficient quantity:
  ``test_acceptance_one_listing_cannot_fill_both_ring_slots``;
* changed equipment rechecks full-build requirements and resources:
  ``test_acceptance_changed_equipment_rechecks_the_whole_build``;
* no-budget mode never generates a price maximum:
  ``test_acceptance_no_budget_mode_never_generates_a_price_maximum``;
* pairwise evaluation is deferred to P08, not replaced by per-slot gains:
  ``test_acceptance_pools_hold_no_score_or_per_slot_gain``.

The catalog and profile come from the P02-T03 invented world through the real
exporter. Its slot rules name no accepted base categories (the P02 gap), so
the populated-pool tests give three slots categories in a labelled synthetic
copy of the profile, as a catalog that supplied them would.
"""

from __future__ import annotations

import dataclasses
import hashlib
import inspect
import itertools
import json
from dataclasses import replace

import pytest

import legality_fixtures as lf
import p05_fixtures as fx
from pob2opt import cli
from pob2opt.domain.codec import to_jsonable
from pob2opt.domain.enums import (Availability, CandidateAvailability,
                                  EnablingQueryStatus, ModifierCategory,
                                  ModifierParseStatus, PoolSlotStatus,
                                  RecordParseStatus)
from pob2opt.domain.records import (SCHEMA_VERSION, EnablingQueryOutcome,
                                    EquipmentPool, EquipmentSlot, ItemModifier,
                                    Listing, PoolCandidate, SlotPool)
from pob2opt.domain.validation import RecordIndex, validate_record
from pob2opt.evaluation.legality import MeasuredState
from pob2opt.market import pools as pools_module
from pob2opt.market.pools import (EnablingQuery, OwnedItem, build_pool,
                                  change_equipment, equipment_conflicts,
                                  owned_from_build, pool_report, sampling,
                                  sampling_parameters)
from pob2opt.parsers.cli import _load_catalog
from pob2opt.storage import RunStore

CREATED = "2026-10-17T00:00:00Z"
RING = "poe2/item_bases/Iron Ring"
AXE = "poe2/item_bases/Iron Greataxe"
TUNIC = "poe2/item_bases/Linen Tunic"
RING_1, RING_2 = "poe2/slots/Ring 1", "poe2/slots/Ring 2"
WEAPON_1 = "poe2/slots/Weapon 1"


@pytest.fixture(scope="module")
def world():
    return lf.load_world()


def with_categories(profile):
    """SYNTHETIC: three slot rules given the categories the export lacks."""
    categories = {RING_1: ["Ring"], RING_2: ["Ring"], WEAPON_1: ["Two Handed Axe"]}
    rules = profile.character_rules
    slots = [replace(rule, accepted_base_categories=categories.get(rule.slot_id, []))
             for rule in rules.slots]
    return replace(profile, character_rules=replace(rules, slots=slots))


def h(name: str) -> str:
    return hashlib.sha256(name.encode()).hexdigest()


def item(name, base, *lines, status=RecordParseStatus.COMPLETE, catalog="c" * 64):
    mods = [ItemModifier(category=ModifierCategory.EXPLICIT, source_position=i,
                         text=text, native_id=None, resolved_effect_ids=[],
                         values=[], flags={},
                         parse_status=ModifierParseStatus.RESOLVED)
            for i, text in enumerate(lines)]
    return replace(lf.make_item(h(name), {"catalog_hash": catalog,
                                          "base_id": base, "display_name": name,
                                          "requirements": {"level": 1}}),
                   modifiers=mods, parse_status=status)


def listing(name, item_hash, *, amount="1", currency="exalted", quantity=1,
            availability=Availability.OBSERVED):
    key = "listing/fixture/poe2/League/%s" % name
    return Listing(schema_version=SCHEMA_VERSION, record_id=key, created_at=CREATED,
                   provenance_ids=["src"], listing_id=key, provider="fixture",
                   realm="poe2", league_id="League", item_hash=item_hash,
                   price_amount=amount, price_currency=None if amount is None
                   else currency, listed_at=None, observed_at=CREATED,
                   last_checked_at=CREATED, availability=availability,
                   listing_url=None, source_document_id="src", quantity=quantity)


def market(catalog_hash):
    """Six rings and four axes, each listed once. One ring enables, one axe
    pays off; both are the weakest of their slot on their own."""
    rings = [item("ring-%d" % n, RING, "FIXTUREMOD +%d to Strength" % (10 * n),
                  catalog=catalog_hash) for n in range(1, 7)]
    enabler = item("ring-enabler", RING, "FIXTUREMOD Hits ignite",
                   catalog=catalog_hash)
    axes = [item("axe-%d" % n, AXE, "FIXTUREMOD %d%% increased Damage" % (20 * n),
                 catalog=catalog_hash) for n in range(1, 4)]
    payoff = item("axe-payoff", AXE, "FIXTUREMOD Triple damage against Ignited",
                  catalog=catalog_hash)
    items = rings + [enabler] + axes + [payoff]
    listings = [listing(i.display_name, i.item_hash) for i in items]
    return items, listings, enabler, payoff


STANDALONE = {"Hits ignite": 1, "Triple damage": 1}


def standalone(it) -> float:
    """SYNTHETIC test scorer: the number in the line, or the table above."""
    text = it.modifiers[0].text
    for key, value in STANDALONE.items():
        if key in text:
            return value
    return float("".join(c for c in text if c.isdigit()))


def pair_value(axe, ring) -> float:
    """SYNTHETIC: the payoff with the enabler is worth far more than any
    pair of strong standalone items. Stands in for P08's evaluation."""
    bonus = 1000 if ("Triple damage" in axe.modifiers[0].text
                     and "Hits ignite" in ring.modifiers[0].text) else 0
    return standalone(axe) + standalone(ring) + bonus


QUERIES = (
    EnablingQuery("ignite-enabler", "a ring whose hits ignite",
                  slot_ids=(RING_1, RING_2), modifier_patterns=(r"Hits ignite",)),
    EnablingQuery("ignite-payoff", "a weapon that pays off ignite",
                  slot_ids=(WEAPON_1,), modifier_patterns=(r"against Ignited",)),
)


def make_pool(world, items, listings, **kwargs):
    kwargs.setdefault("profile", with_categories(world.profile))
    return build_pool(catalog=world.catalog, items=items, listings=listings,
                      gaps=world.gaps, created_at=CREATED, **kwargs)


def slot(pool, slot_id) -> SlotPool:
    return next(s for s in pool.slots if s.slot_id == slot_id)


# ---------------------------------------------------------- acceptance ===

def test_acceptance_weak_enabler_survives_and_enables_the_best_pair(world):
    items, listings, enabler, payoff = market(world.catalog.catalog_hash)
    pool = make_pool(world, items, listings, queries=QUERIES,
                     bounds=sampling(listings_per_slot=2))
    by_hash = {i.item_hash: i for i in items}
    rings = slot(pool, RING_1)
    assert rings.truncated and rings.considered_count == 7
    kept = {c.item_hash: c for c in rings.candidates}
    assert kept[enabler.item_hash].retained_for == ["enabling:ignite-enabler"]
    weapons = slot(pool, WEAPON_1)
    assert payoff.item_hash in {c.item_hash for c in weapons.candidates}

    # Exhaustive pairs over the pool, with a synthetic scorer standing in for
    # P08: the best pair is the enabler with the payoff.
    best = max(itertools.product(weapons.candidates, rings.candidates),
               key=lambda pair: pair_value(by_hash[pair[0].item_hash],
                                           by_hash[pair[1].item_hash]))
    assert (best[0].item_hash, best[1].item_hash) == (payoff.item_hash,
                                                      enabler.item_hash)
    # A cut by standalone value would have lost both halves of that pair.
    ring_items = [i for i in items if i.base_id == RING]
    top = sorted(ring_items, key=standalone, reverse=True)[:2]
    assert enabler not in top


def test_acceptance_one_listing_cannot_fill_both_ring_slots(world):
    items, listings, *_ = market(world.catalog.catalog_hash)
    ring = items[0]
    one = listing("single", ring.item_hash, quantity=1)
    two = listing("pair", ring.item_hash, quantity=2)
    unknown = listing("unknown", ring.item_hash, quantity=None)

    def build(listing_id):
        base = lf.make_build({"class_id": "poe2/classes/1", "level": 10},
                             catalog_hash=world.catalog.catalog_hash)
        return replace(base, equipment={
            RING_1: EquipmentSlot(ring.item_hash, listing_id),
            RING_2: EquipmentSlot(ring.item_hash, listing_id)})

    listed = [one, two, unknown]
    conflicts = equipment_conflicts(build(one.listing_id), listings=listed)
    assert [(c.code, c.allowed, c.used) for c in conflicts] == [
        ("listing_over_quantity", 1, 2)]
    assert equipment_conflicts(build(two.listing_id), listings=listed) == []
    assert [c.code for c in equipment_conflicts(
        build(unknown.listing_id), listings=listed)] == ["listing_over_quantity"]
    # Not owned and not listed: one physical item at most.
    assert [c.code for c in equipment_conflicts(build(None))] == [
        "unlisted_item_reused"]
    assert equipment_conflicts(build(None), owned=[
        OwnedItem(ring.item_hash, count=2)]) == []
    assert [c.code for c in equipment_conflicts(build(None), owned=[
        OwnedItem(ring.item_hash, count=1)])] == ["owned_over_count"]


def test_acceptance_changed_equipment_rechecks_the_whole_build(world):
    """Swapping a ring rechecks the axe in another slot with a new
    measurement of the new build; the old one is never reused."""
    cases = lf.load_cases()
    items = lf.make_items(cases, world.catalog.catalog_hash)
    base = lf.make_build({"class_id": "poe2/classes/1", "level": 40,
                          "equipment": {"Weapon 1": {"item": "greataxe"},
                                        "Ring 1": {"item": "ring"}}},
                         catalog_hash=world.catalog.catalog_hash)
    measured = []

    def measure(new_build):
        measured.append(new_build.build_hash)
        return MeasuredState(source="fixture: after the ring change",
                             attributes={"strength": 60, "dexterity": 50,
                                         "intelligence": 50})

    candidate = PoolCandidate(item_hash="ring2", listing_id=None,
                              availability=CandidateAvailability.OWNED,
                              quantity=1, retained_for=["owned"])
    change = change_equipment(base, "Ring 1", candidate, profile=world.profile,
                              catalog=world.catalog, items=items,
                              measure=measure)
    assert measured == [change.build.build_hash] != [base.build_hash]
    assert change.build.equipment["Ring 1"].item_hash == "ring2"
    violations = [(v.code, v.field_paths) for v in change.legality.violations]
    assert violations == [("item_attribute_requirement_not_met",
                           ("/equipment/poe2/slots/Weapon 1",))]

    unmeasured = change_equipment(base, "Ring 1", candidate,
                                  profile=world.profile, catalog=world.catalog,
                                  items=items)
    codes = {u.code for u in unmeasured.legality.unknowns}
    assert "attribute_total_unmeasured" in codes
    assert unmeasured.legality.legality.value != "legal"

    too_high = change_equipment(
        replace(base, level=32), "Weapon 1",
        PoolCandidate(item_hash="greataxe_listed", listing_id="listing/7",
                      availability=CandidateAvailability.OBSERVED, quantity=1,
                      retained_for=["sample"]),
        profile=world.profile, catalog=world.catalog, items=items)
    assert "item_level_requirement_not_met" in {
        v.code for v in too_high.legality.violations}


def test_acceptance_no_budget_mode_never_generates_a_price_maximum(world):
    params = inspect.signature(build_pool).parameters
    assert not any("price" in p or "budget" in p or "cap" in p for p in params)
    items, listings, *_ = market(world.catalog.catalog_hash)
    cheap = make_pool(world, items, listings, bounds=sampling(3))
    priced = [replace(l, price_amount=amount, price_currency=currency)
              for l, (amount, currency) in zip(listings, itertools.cycle(
                  [("1000000", "divine"), (None, None), ("0", "exalted"),
                   ("3.5", "chaos")]))]
    dear = make_pool(world, items, priced, bounds=sampling(3))
    assert to_jsonable(dear.slots) == to_jsonable(cheap.slots)
    text = json.dumps(to_jsonable(dear))
    assert "price" not in text and "budget" not in text
    for query in to_jsonable(make_pool(world, items, listings,
                                       queries=QUERIES).enabling_queries):
        assert not any("price" in key for key in query)


def test_acceptance_pools_hold_no_score_or_per_slot_gain():
    for cls in (EquipmentPool, SlotPool, PoolCandidate, EnablingQueryOutcome):
        names = {f.name for f in dataclasses.fields(cls)}
        assert not {n for n in names
                    if any(w in n for w in ("score", "dps", "gain", "value"))}
    source = inspect.getsource(pools_module)
    assert ".price_amount" not in source and ".price_currency" not in source


# ------------------------------------------------------ slots and bounds ===

def test_every_profile_slot_gets_a_pool_entry(world):
    items, listings, *_ = market(world.catalog.catalog_hash)
    pool = make_pool(world, items, listings)
    assert [s.slot_id for s in pool.slots] == sorted(
        r.slot_id for r in world.profile.character_rules.slots)
    statuses = {s.slot_id: s.status for s in pool.slots}
    assert statuses[RING_1] is PoolSlotStatus.POPULATED
    assert statuses["poe2/slots/Body Armour"] is PoolSlotStatus.MISSING_CATEGORY_RULE
    report = pool_report(pool)
    assert "poe2/slots/Amulet" in report["missing_category_slots"]
    assert pool.gap_ids == ["gap/p02-t02/slot-accepted-base-categories"]


def test_the_exported_profile_places_no_imported_item_by_guess(world):
    """With the rules as exported, only owned items placed by a build fit."""
    items, listings, *_ = market(world.catalog.catalog_hash)
    owned = [OwnedItem(items[0].item_hash, 1, ("Ring 1",))]
    pool = make_pool(world, items, listings, profile=world.profile, owned=owned)
    assert {s.status for s in pool.slots} == {PoolSlotStatus.MISSING_CATEGORY_RULE}
    ring = slot(pool, RING_1)
    assert [(c.item_hash, c.availability) for c in ring.candidates] == [
        (items[0].item_hash, CandidateAvailability.OWNED)]
    assert slot(pool, RING_2).candidates == []
    assert len(pool.unplaced_item_hashes) == len(items) - 1


def test_bounds_are_configurable_recorded_and_default_to_500_and_100(world):
    assert sampling() == sampling(500, 100)
    assert sampling_parameters(sampling(7, 3)) == {"pool_sampling": {
        "listings_per_slot": 7, "enabling_queries_per_run": 3}}
    with pytest.raises(ValueError):
        sampling(-1)
    items, listings, *_ = market(world.catalog.catalog_hash)
    pool = make_pool(world, items, listings, bounds=sampling(7, 3))
    assert (pool.sampling.listings_per_slot,
            pool.sampling.enabling_queries_per_run) == (7, 3)
    other = make_pool(world, items, listings, bounds=sampling(8, 3))
    assert pool.pool_id != other.pool_id
    again = make_pool(world, items, listings, bounds=sampling(7, 3))
    assert pool.pool_id == again.pool_id == pool.record_id


def test_queries_past_the_bound_are_reported_and_not_applied(world):
    items, listings, enabler, payoff = market(world.catalog.catalog_hash)
    pool = make_pool(world, items, listings, queries=QUERIES,
                     bounds=sampling(listings_per_slot=1,
                                     enabling_queries_per_run=1))
    outcomes = {q.query_id: q for q in pool.enabling_queries}
    assert outcomes["ignite-enabler"].status is EnablingQueryStatus.UNEXECUTED
    assert "D01" in outcomes["ignite-enabler"].reason
    assert outcomes["ignite-enabler"].matched_item_hashes == [enabler.item_hash]
    assert outcomes["ignite-payoff"].status is EnablingQueryStatus.OVER_BOUND
    assert outcomes["ignite-payoff"].matched_item_hashes == []
    weapons = slot(pool, WEAPON_1)
    assert not any(r.startswith("enabling:") for c in weapons.candidates
                   for r in c.retained_for)
    report = pool_report(pool)["queries"]
    assert report == {"declared": 2, "unexecuted": 1, "over_bound": 1,
                      "executed": 0, "locally_matched": 1}


def test_truncation_keeps_bases_and_stat_combinations_diverse(world):
    c = world.catalog.catalog_hash
    same = [item("same-%d" % n, RING, "FIXTUREMOD +%d to Strength" % n,
                 catalog=c) for n in range(1, 6)]
    other = [item("life", RING, "FIXTUREMOD +5 to maximum Life", catalog=c),
             item("speed", RING, "FIXTUREMOD 5% increased Attack Speed",
                  catalog=c)]
    items = same + other
    pool = make_pool(world, items, [listing(i.display_name, i.item_hash)
                                    for i in items], bounds=sampling(3))
    ring = slot(pool, RING_1)
    assert ring.truncated and (ring.considered_count, ring.retained_count) == (7, 3)
    kept = {cand.item_hash for cand in ring.candidates}
    assert {other[0].item_hash, other[1].item_hash} <= kept
    assert len(kept & {i.item_hash for i in same}) == 1
    assert {cand.retained_for[0] for cand in ring.candidates} == {"sample"}


def test_unavailable_listings_and_partial_items_are_counted_not_offered(world):
    c = world.catalog.catalog_hash
    sold = item("sold", RING, "FIXTUREMOD +1 to Strength", catalog=c)
    partial = item("partial", RING, "FIXTUREMOD +2 to Strength", catalog=c,
                   status=RecordParseStatus.PARTIAL)
    unlisted = item("unlisted", RING, "FIXTUREMOD +3 to Strength", catalog=c)
    pool = make_pool(world, [sold, partial, unlisted], [
        listing("sold", sold.item_hash, availability=Availability.UNAVAILABLE)])
    ring = slot(pool, RING_1)
    assert (ring.unavailable_count, ring.partial_count) == (1, 1)
    assert [(cand.item_hash, cand.availability, cand.listing_id)
            for cand in ring.candidates] == [
        (unlisted.item_hash, CandidateAvailability.UNKNOWN, None)]


def test_owned_items_come_from_a_build_and_are_not_listings(world):
    base = lf.make_build({"class_id": "poe2/classes/1", "level": 10},
                         catalog_hash=world.catalog.catalog_hash)
    build = replace(base, equipment={
        "Ring 1": EquipmentSlot("a" * 64, None),
        "Ring 2": EquipmentSlot("a" * 64, None),
        "Weapon 1": EquipmentSlot("b" * 64, "listing/x"),
        "Amulet": None})
    assert owned_from_build(build) == [OwnedItem("a" * 64, 2,
                                                 ("Ring 1", "Ring 2"))]


def test_a_pool_candidate_must_come_from_that_slots_pool(world):
    items, listings, enabler, _ = market(world.catalog.catalog_hash)
    pool = make_pool(world, items, listings, queries=QUERIES,
                     bounds=sampling(2))
    enabler_listing = next(l for l in listings if l.item_hash == enabler.item_hash)
    base = lf.make_build({"class_id": "poe2/classes/1", "level": 10},
                         catalog_hash=world.catalog.catalog_hash)
    good = replace(base, equipment={
        "Ring 1": EquipmentSlot(enabler.item_hash, enabler_listing.listing_id)})
    assert equipment_conflicts(good, listings=listings, pool=pool) == []
    bad = replace(base, equipment={
        "Weapon 1": EquipmentSlot(enabler.item_hash, enabler_listing.listing_id)})
    assert [c.code for c in equipment_conflicts(bad, listings=listings,
                                                pool=pool)] == ["not_in_pool"]


def test_the_pool_record_validates_with_its_references(world):
    items, listings, *_ = market(world.catalog.catalog_hash)
    pool = make_pool(world, items, listings, queries=QUERIES)
    index = RecordIndex(
        catalog_hashes={world.catalog.catalog_hash},
        patch_profile_ids={world.profile.record_id},
        item_hashes={i.item_hash for i in items},
        listing_ids={l.listing_id for l in listings},
        gap_ids={g.gap_id for g in world.gaps},
        record_ids={pool.record_id, world.catalog.record_id})
    report = validate_record(pool, index=index)
    assert report.ok, report.errors
    assert not validate_record(pool, index=RecordIndex()).ok


# --------------------------------------------- real catalog, T02 corpus ===

@pytest.fixture(scope="module")
def bundle(tmp_path_factory):
    return fx.export_bundle(tmp_path_factory.mktemp("p05t03catalog"))


def test_a_pool_over_the_pinned_catalog_and_an_imported_capture(tmp_path,
                                                                bundle, capsys):
    """The pinned export has no slot categories: every slot reports it, the
    imported items stay unplaced, and the stored pool resolves."""
    capture = tmp_path / "capture.json"
    capture.write_bytes(fx.capture_bytes())
    corpus = tmp_path / "corpus"
    assert cli.main(["market", "import", "--input", str(capture), "--corpus",
                     str(corpus), "--catalog", str(bundle)]) == 0
    capsys.readouterr()
    catalog, profile, gaps, *_ = _load_catalog(bundle)
    with RunStore.open_corpus(corpus) as store:
        items = list(store.iter_normalized("item_instance"))
        listings = list(store.iter_normalized("listing"))
        pool = build_pool(catalog=catalog, profile=profile, items=items,
                          listings=listings, gaps=gaps, created_at=CREATED)
        store.import_batch([pool])
        assert store.unresolved_references() == {}
    report = pool_report(pool)
    assert len(pool.slots) == len(profile.character_rules.slots) > 100
    assert len(report["missing_category_slots"]) == len(pool.slots)
    assert sorted(pool.unplaced_item_hashes) == sorted(i.item_hash for i in items)
    assert pool.gap_ids == [g.gap_id for g in gaps
                            if "/character_rules/slots" in g.field_paths]
