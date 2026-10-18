"""P02-T03.1 offline lane: slot rules from the engine's slot acceptance probe.

The probe is the capture in `docs/evidence/P02-T03.1/slot-acceptance.json`,
read out of the pinned engine by `scripts/p02_t03_1_slot_rules.py`. It is
replayed here through the real P02-T02 exporter over the committed P02 row
slice, so the rules under test come from the catalog code, not from this
file. The expected categories were read from the engine's
`ItemsTab:IsItemValidForSlot` by hand; the engine lane
(`tests/engine/test_p02_t03_1_slot_rules_engine.py`) checks real items.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

import legality_fixtures as fixtures
from pob2opt.catalog import (ExportRequest, MappingCatalogReader,
                             PobCatalogProvider)
from pob2opt.catalog.slotrules import accepts, base_category, read_acceptance
from pob2opt.catalog.sources import citations_from_payload
from pob2opt.domain.absent import Absent
from pob2opt.domain.codec import from_jsonable, to_jsonable
from pob2opt.domain.enums import GapSeverity, Legality
from pob2opt.domain.validation import RecordIndex, validate_record
from pob2opt.evaluation.legality import (CHECK_HANDS, CHECK_SLOTS,
                                         LegalityValidator)
from pob2opt.evaluation.legality.gaps import (T02_SLOT_CATEGORIES,
                                              T031_OFF_HAND_FLAGS)

REPO_ROOT = Path(__file__).resolve().parents[2]
SLICE = REPO_ROOT / "docs" / "evidence" / "P02" / "catalog-rows-slice.json"
PROBE = REPO_ROOT / "docs" / "evidence" / "P02-T03.1" / "slot-acceptance.json"
S = "poe2/slots/"


#: The engine's Diamond jewel base row, added to the slice so a jewel can be
#: placed; the slice keeps no jewel base.
DIAMOND = {"armour": [], "flask": [], "hidden": False, "implicit": None,
           "name": "Diamond", "req": [], "tags": ["default", "jewel"],
           "type": "Jewel", "weapon": []}


def _export(slot_acceptance):
    rows = json.loads(SLICE.read_text(encoding="utf-8"))
    rows["tables"]["item_bases"] = [*rows["tables"]["item_bases"], DIAMOND]
    rule_sources = dict(rows["rule_sources"])
    rule_sources.pop("slotAcceptance", None)
    if slot_acceptance is not None:
        rule_sources["slotAcceptance"] = slot_acceptance
    provider = PobCatalogProvider(
        MappingCatalogReader(rows["tables"], rule_sources, source=str(SLICE)),
        citations=citations_from_payload(rows["citations"]),
        pob_commit=rows["pob_commit"], pob_dirty_hash=rows["pob_dirty_hash"],
        fixtures={"fixture_set_version": 0, "recorded_from": {}, "fixtures": []},
        clock=lambda: "2026-10-18T00:00:00Z")
    return provider.export(ExportRequest())


@pytest.fixture(scope="module")
def probe():
    return json.loads(PROBE.read_text(encoding="utf-8"))["slotAcceptance"]


@pytest.fixture(scope="module")
def probed(probe):
    return _export(probe)


def _slots(export):
    return {r.slot_id: r.accepted_base_categories
            for r in export.profile.character_rules.slots}


def _off_hand(export, main, flag="none", off="Weapon 2"):
    rules = [r for r in export.profile.character_rules.weapon_sets.off_hand_rules
             if r.off_hand_slot_id == S + off and r.main_hand_category == main
             and r.required_flag == flag]
    assert len(rules) == 1, (main, flag, off)
    return rules[0].accepted_base_categories


# ------------------------------------------------------------ category key

def test_base_category_includes_the_subtype_only_when_there_is_one():
    assert base_category({"type": "Flask", "subType": "Life"}) == "Flask/Life"
    assert base_category({"type": "Ring"}) == "Ring"
    assert base_category({"type": "Ring", "subType": None}) == "Ring"
    assert base_category({}) is None and base_category(None) is None
    assert accepts(["Flask/Life"], {"type": "Flask", "subType": "Life"})
    assert not accepts(["Flask/Life"], {"type": "Flask", "subType": "Mana"})
    # A bare type does not widen to its subtypes.
    assert not accepts(["Flask"], {"type": "Flask", "subType": "Mana"})


# ------------------------------------------------------- the real capture

def test_the_capture_comes_from_a_clean_pinned_checkout():
    capture = json.loads(PROBE.read_text(encoding="utf-8"))
    assert capture["pob_commit"].startswith("ce566eac")
    assert capture["pob_dirty_hash"] is None
    acceptance = read_acceptance(capture["slotAcceptance"])
    assert acceptance.probe_count > 1000 and not acceptance.probe_failures


def test_probed_profile_closes_the_p02_slot_category_gap(probed):
    ids = {gap.gap_id for gap in probed.gaps}
    assert T02_SLOT_CATEGORIES not in ids
    assert T02_SLOT_CATEGORIES not in \
        probed.profile.character_rules.missing_rule_gap_ids
    assert not probed.validation_errors


def test_positive_and_negative_slot_categories(probed):
    slots = _slots(probed)
    assert slots[S + "Ring 1"] == slots[S + "Ring 2"] == slots[S + "Ring 3"] \
        == ["Ring"]
    assert slots[S + "Amulet"] == ["Amulet"]
    assert slots[S + "Belt"] == ["Belt"]
    assert slots[S + "Flask 1"] == ["Flask/Life"]
    assert slots[S + "Flask 2"] == ["Flask/Mana"]
    assert slots[S + "Charm 1"] == ["Charm"]
    assert slots[S + "Arm 1"] == ["Transcendent Limb/Transcendent Arm"]
    assert slots[S + "Leg 2"] == ["Transcendent Limb/Transcendent Leg"]
    assert "Body Armour/Armour/Energy Shield" in slots[S + "Body Armour"]
    assert all(c.startswith("Helmet") for c in slots[S + "Helmet"])
    weapon = slots[S + "Weapon 1"]
    assert {"Staff/Warstaff", "Bow", "Two Hand Mace", "Talisman"} <= set(weapon)
    assert not {"Shield/Evasion", "Focus", "Quiver", "Ring"} & set(weapon)
    assert slots[S + "Weapon 1 Swap"] == weapon
    off = slots[S + "Weapon 2"]
    assert {"Shield/Evasion", "Focus", "Quiver", "One Hand Mace"} <= set(off)
    # The engine never lets a spear, staff or bow into the off hand.
    assert not {"Spear", "Staff/Warstaff", "Staff", "Bow"} & set(off)
    assert "Ring" not in slots[S + "Amulet"]


def test_tree_jewel_sockets_accept_jewels_and_item_sockets_stay_conditional(
        probed):
    slots = _slots(probed)
    tree = [k for k in slots if k.startswith(S + "Jewel ")]
    assert tree and all("Jewel" in slots[k] for k in tree)
    item_sockets = [k for k in slots if "Jewel Socket" in k]
    assert len(item_sockets) == 72
    assert all(slots[k] == [] for k in item_sockets)
    gap = [g for g in probed.gaps
           if g.gap_id == "gap/p02-t03.1/socketed-item-jewel-slots"]
    assert gap and gap[0].severity is GapSeverity.RANKING_SENSITIVE
    assert "Helmet Jewel Socket 1" in gap[0].explanation


def test_off_hand_rules_follow_the_main_hand(probed):
    assert _off_hand(probed, "Staff/Warstaff") == []
    assert _off_hand(probed, "Two Hand Mace") == []
    assert _off_hand(probed, "Bow") == ["Quiver"]
    one_hand = _off_hand(probed, "One Hand Mace")
    assert "Shield/Evasion" in one_hand and "Quiver" not in one_hand
    assert "Shield/Evasion" in _off_hand(probed, "Unarmed")
    assert "Two Hand Mace" not in _off_hand(probed, "Unarmed")
    # Keystone flags, as the engine reads them.
    assert "Shield/Evasion" in _off_hand(probed, "Two Hand Mace", "GiantsBlood")
    assert "Two Hand Mace" in _off_hand(probed, "One Hand Mace", "GiantsBlood")
    assert _off_hand(probed, "Staff/Warstaff", "InstrumentsOfPower") == ["Focus"]
    assert _off_hand(probed, "Talisman", "LordOfTheWilds") == ["Sceptre"]
    assert _off_hand(probed, "Staff/Warstaff", off="Weapon 2 Swap") == []


def test_profile_with_off_hand_rules_round_trips_and_validates(probed):
    profile = probed.profile
    data = to_jsonable(profile)
    assert data["character_rules"]["weapon_sets"]["off_hand_rules"]
    assert from_jsonable(type(profile), data) == profile
    index = RecordIndex.from_records(probed.records)
    assert validate_record(profile, index=index).ok


# ------------------------------------------------------- refusal paths

def test_without_the_probe_the_original_gap_and_empty_rules_remain():
    export = _export(None)
    assert all(not r.accepted_base_categories
               for r in export.profile.character_rules.slots)
    assert T02_SLOT_CATEGORIES in {g.gap_id for g in export.gaps}
    assert isinstance(export.profile.character_rules.weapon_sets.off_hand_rules,
                      Absent)


def test_a_partially_accepted_category_is_not_widened(probe):
    probe = copy.deepcopy(probe)
    for row in probe["slots"]:
        if row["slot"] == "Amulet":
            row["categories"]["Amulet"]["accepted"] -= 1
    export = _export(probe)
    assert _slots(export)[S + "Amulet"] == []
    gap = [g for g in export.gaps
           if g.gap_id == "gap/p02-t03.1/slot-partial-categories"]
    assert gap and "Amulet" in gap[0].explanation
    assert gap[0].severity is GapSeverity.BLOCKING


def test_a_main_hand_category_with_mixed_results_gets_no_rule(probe):
    probe = copy.deepcopy(probe)
    for row in probe["offHand"]:
        if row["mainCategory"] == "Bow" and row["flag"] == "none":
            row["variants"] = 2
            row["categories"] = None
    export = _export(probe)
    rules = export.profile.character_rules.weapon_sets.off_hand_rules
    assert not [r for r in rules if r.main_hand_category == "Bow"
                and r.required_flag == "none"]
    assert "gap/p02-t03.1/off-hand-mixed-main-hand" in {
        g.gap_id for g in export.gaps}


# ------------------------------------------------------- legality

def _item(export, item_hash, base, rarity="rare"):
    return fixtures.make_item(item_hash, {
        "catalog_hash": export.catalog.catalog_hash, "base_id": base,
        "display_name": item_hash, "requirements": {"level": 1},
        "rarity": rarity, "source_document_id": "source/invented"})


def _validate(export, equipment, rarity=None):
    items = {h: _item(export, h, base, (rarity or {}).get(h, "rare"))
             for h, (slot, base) in equipment.items()}
    build = fixtures.make_build(
        {"class_id": "poe2/classes/8", "level": 5, "allocated": [],
         "equipment": {slot: {"item": h}
                       for h, (slot, base) in equipment.items()}},
        catalog_hash=export.catalog.catalog_hash)
    return LegalityValidator(catalog=export.catalog, items=items).validate(
        build, export.profile)


def test_a_quarterstaff_in_the_main_hand_is_legal_for_the_slot(probed):
    report = _validate(probed, {"staff": ("Weapon 1", "Long Quarterstaff")})
    assert report.decision(CHECK_SLOTS) is Legality.LEGAL
    assert report.decision(CHECK_HANDS) is Legality.LEGAL


def test_a_ring_in_the_amulet_slot_is_illegal(probed):
    report = _validate(probed, {"ring": ("Amulet", "Amethyst Ring")})
    assert report.decision(CHECK_SLOTS) is Legality.ILLEGAL
    assert "base_category_not_accepted" in report.violation_codes


def test_a_shield_next_to_a_one_hand_mace_is_legal(probed):
    report = _validate(probed, {"club": ("Weapon 1", "Akoyan Club"),
                                "shield": ("Weapon 2", "Aegis Buckler")})
    assert report.decision(CHECK_HANDS) is Legality.LEGAL


def test_a_shield_next_to_a_quarterstaff_is_illegal(probed):
    report = _validate(probed, {"staff": ("Weapon 1", "Long Quarterstaff"),
                                "shield": ("Weapon 2", "Aegis Buckler")})
    assert report.decision(CHECK_HANDS) is Legality.ILLEGAL
    assert "off_hand_not_accepted" in report.violation_codes


def test_a_one_hand_mace_next_to_a_two_hand_mace_needs_a_keystone(probed):
    report = _validate(probed, {"maul": ("Weapon 1", "Aberrant Sledge"),
                                "club": ("Weapon 2", "Akoyan Club")})
    assert report.decision(CHECK_HANDS) is Legality.UNKNOWN
    assert "off_hand_needs_keystone" in report.unknown_codes
    assert T031_OFF_HAND_FLAGS in report.cited_gap_ids


def test_a_focus_with_an_empty_main_hand_is_legal(probed):
    report = _validate(probed, {"focus": ("Weapon 2", "Antler Focus")})
    assert report.decision(CHECK_HANDS) is Legality.LEGAL
    assert report.decision(CHECK_SLOTS) is Legality.LEGAL


def test_a_jewel_socket_on_an_item_stays_unknown_and_cites_its_gap(probed):
    report = _validate(probed, {"ring": ("Helmet Jewel Socket 1",
                                         "Amethyst Ring")})
    assert "slot_base_category_undecidable" in report.unknown_codes
    assert "gap/p02-t03.1/socketed-item-jewel-slots" in report.cited_gap_ids
    assert T02_SLOT_CATEGORIES not in report.cited_gap_ids


# ------------------------------------------------------- rarity conditions

def _refusing(export):
    return sorted(r.slot_id for r in export.profile.character_rules.slots
                  if r.refused_rarities)


def test_some_tree_sockets_refuse_unique_and_relic_jewels(probed):
    refusing = _refusing(probed)
    assert refusing and all(s.startswith(S + "Jewel ") for s in refusing)
    rules = {r.slot_id: r for r in probed.profile.character_rules.slots}
    assert all(rules[s].refused_rarities == ["relic", "unique"]
               for s in refusing)
    assert rules[S + "Jewel 21984"].refused_rarities == []
    assert rules[S + "Ring 1"].refused_rarities == []
    assert "gap/p02-t03.1/slot-rarity-partial" not in {
        g.gap_id for g in probed.gaps}


def test_a_unique_jewel_in_a_refusing_socket_is_illegal(probed):
    socket = _refusing(probed)[0][len(S):]
    unique = _validate(probed, {"jewel": (socket, "Diamond")},
                       rarity={"jewel": "unique"})
    assert unique.decision(CHECK_SLOTS) is Legality.ILLEGAL
    assert "rarity_not_accepted" in unique.violation_codes
    rare = _validate(probed, {"jewel": (socket, "Diamond")})
    assert rare.decision(CHECK_SLOTS) is Legality.LEGAL
    elsewhere = _validate(probed, {"jewel": ("Jewel 21984", "Diamond")},
                          rarity={"jewel": "unique"})
    assert elsewhere.decision(CHECK_SLOTS) is Legality.LEGAL


def test_a_pool_keeps_unique_jewels_out_of_refusing_sockets(probed):
    from pob2opt.market.pools import build_pool
    unique = _item(probed, "u" * 64, "poe2/item_bases/Diamond", "unique")
    rare = _item(probed, "r" * 64, "poe2/item_bases/Diamond", "rare")
    pool = build_pool(catalog=probed.catalog, profile=probed.profile,
                      items=[unique, rare], created_at="2026-10-18T00:00:00Z")
    by_slot = {s.slot_id: {c.item_hash for c in s.candidates}
               for s in pool.slots}
    socket = _refusing(probed)[0]
    assert by_slot[socket] == {"r" * 64}
    assert by_slot[S + "Jewel 21984"] == {"u" * 64, "r" * 64}
    assert by_slot[S + "Ring 1"] == set()


def test_a_rarity_refused_for_only_some_categories_is_a_gap(probe):
    probe = copy.deepcopy(probe)
    for row in probe["slots"]:
        if row["slot"] == "Weapon 1":
            row["byRarity"]["unique"].pop("Bow")
    export = _export(probe)
    rules = {r.slot_id: r for r in export.profile.character_rules.slots}
    assert rules[S + "Weapon 1"].refused_rarities == []
    gap = [g for g in export.gaps
           if g.gap_id == "gap/p02-t03.1/slot-rarity-partial"]
    assert gap and "Weapon 1" in gap[0].explanation


def test_a_stat_known_partial_ring_is_placed_and_marked(probed):
    """Parser `.6`: the stats are known, only the affix is not."""
    from pob2opt.market.pools import STAT_KNOWN_PARTIAL, build_pool
    from pob2opt.domain.enums import RecordParseStatus

    def ring(name, status):
        item = fixtures.make_item(name * 64, {
            "catalog_hash": probed.catalog.catalog_hash,
            "base_id": "poe2/item_bases/Amethyst Ring", "rarity": "rare",
            "modifiers": [{"text": "+56% to Fire Resistance",
                           "parse_status": status}],
            "parse_status": "partial"})
        return item
    known, unknown = ring("k", "stat_resolved"), ring("u", "unresolved")
    pool = build_pool(catalog=probed.catalog, profile=probed.profile,
                      items=[known, unknown], created_at="2026-10-18T00:00:00Z")
    (slot,) = [s for s in pool.slots if s.slot_id == S + "Ring 1"]
    assert [(c.item_hash, c.retained_for) for c in slot.candidates] == [
        (known.item_hash, ["sample", STAT_KNOWN_PARTIAL])]
    assert slot.partial_count == 1
    assert known.parse_status is RecordParseStatus.PARTIAL
