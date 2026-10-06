"""P02-T05: an ItemInstance exported as PoB item text and read back.

Offline only. The comparison is ``item_identity``: base, rarity, level,
requirements, properties, every modifier with its category and flags, sockets
and item flags. Display names and provenance are excluded by that projection,
so they cannot hide a real difference.

Two kinds of case, kept apart on purpose:

* the supported shape round trips exactly, for every modifier category PoB has
  a marker for;
* a field PoB cannot carry is reported with its value and makes the item's
  export incomplete. ``ModifierCategory.unknown``, a resolved modifier's
  catalog references and roll range, and a flag recorded ``false`` are the
  three that matter, and the third is a direct consequence of the four
  no-value states in ``contracts.md``: PoB writes only the positive line, so
  ``false`` and absent become the same document.
"""

from __future__ import annotations

import pytest
from p02_t05_fixtures import (CATALOG_HASH, CREATED_AT, SYNTHETIC_NAMING,
                              every_category_weapon, false_flag_item, item,
                              modifier, resolved_modifier_item,
                              socketed_jewel, unknown_category_item,
                              variant_helmet)

from pob2opt.domain.enums import ModifierCategory
from pob2opt.domain.identity import item_hash, item_identity
from pob2opt.domain.records import Socket
from pob2opt.evaluation import export_item, import_item
from pob2opt.evaluation.roundtrip import diff_identity

SUPPORTED_ITEMS = {
    "every_category_weapon": every_category_weapon,
    "variant_helmet": variant_helmet,
    "socketed_jewel": socketed_jewel,
}


def round_trip_item(source):
    text, losses = export_item(source, SYNTHETIC_NAMING)
    restored = import_item(text, SYNTHETIC_NAMING, record_id="r",
                           created_at=CREATED_AT, catalog_hash=CATALOG_HASH)
    return text, losses.report(), restored


@pytest.mark.parametrize("name", sorted(SUPPORTED_ITEMS))
def test_a_supported_item_keeps_its_canonical_identity(name):
    source = SUPPORTED_ITEMS[name]()
    text, report, restored = round_trip_item(source)
    assert report.completeness == "complete", report.as_dict()
    assert diff_identity(item_identity(source), item_identity(restored)) == []
    assert restored.item_hash == item_hash(source)


def test_every_supported_modifier_category_survives():
    source = every_category_weapon()
    text, report, restored = round_trip_item(source)
    assert [m.category for m in restored.modifiers] == [
        m.category for m in source.modifiers]
    assert {m.category for m in restored.modifiers} == {
        ModifierCategory.ENCHANT, ModifierCategory.RUNE,
        ModifierCategory.IMPLICIT, ModifierCategory.EXPLICIT,
        ModifierCategory.FRACTURED, ModifierCategory.CRAFTED,
        ModifierCategory.DESECRATED}


def test_the_implicit_count_matches_the_implicit_like_categories():
    text, _report, _restored = round_trip_item(every_category_weapon())
    assert "Implicits: 3" in text.splitlines()


def test_a_modifier_line_flag_survives():
    _text, _report, restored = round_trip_item(every_category_weapon())
    assert restored.modifiers[4].flags == {"unscalable": True}


def test_item_variants_and_the_selected_variant_survive():
    source = variant_helmet()
    text, report, restored = round_trip_item(source)
    assert "Variant: Pre Fixture" in text.splitlines()
    assert "Selected Variant: 2" in text.splitlines()
    assert restored.properties["variants"] == ["Pre Fixture", "Current"]
    assert restored.properties["selected_variant"] == 2
    assert restored.modifiers[1].flags == {"variant:1": True}


def test_sockets_survive_by_position():
    _text, _report, restored = round_trip_item(variant_helmet())
    assert restored.sockets == [Socket(socket_id="0", group=0, colour="S",
                                       contents_id=None)]


# ------------------------------------------------ omitted and absent fields

def test_an_item_with_every_optional_field_omitted_still_round_trips():
    """Repair case: conversion must not require fields the source omitted."""
    source = item("fixture-bare", base_id="base-quarterstaff",
                  display_name="FIXTURE Bare", rarity="normal",
                  modifiers=[modifier(ModifierCategory.EXPLICIT, 0,
                                      "FIXTUREMOD bare line")])
    text, report, restored = round_trip_item(source)
    assert report.completeness == "complete"
    assert restored.item_level is None
    assert restored.requirements == {}
    assert restored.properties == {}
    assert restored.sockets == []
    assert restored.flags == {}
    assert item_hash(restored) == item_hash(source)


def test_a_normal_rarity_item_has_no_separate_title_line():
    source = item("fixture-normal", base_id="base-helmet", rarity="normal",
                  display_name="Iron Helm", modifiers=[])
    text, _report, restored = round_trip_item(source)
    assert text.splitlines()[:2] == ["Rarity: NORMAL", "Iron Helm"]
    assert restored.base_id == "base-helmet"


def test_text_with_no_rarity_line_reads_as_unique_like_pob():
    restored = import_item("Ingenuity\nUtility Belt\nImplicits: 0",
                           SYNTHETIC_NAMING, record_id="r",
                           created_at=CREATED_AT, catalog_hash=CATALOG_HASH)
    assert restored.rarity == "unique"
    assert restored.display_name == "Ingenuity"


def test_a_modifier_line_containing_a_colon_is_not_read_as_a_header():
    restored = import_item(
        "Rarity: RARE\nFIXTURE Colon\nLong Quarterstaff\nImplicits: 0\n"
        "Grants Skill: FIXTUREMOD colon line", SYNTHETIC_NAMING,
        record_id="r", created_at=CREATED_AT, catalog_hash=CATALOG_HASH)
    assert [m.text for m in restored.modifiers] == [
        "Grants Skill: FIXTUREMOD colon line"]


def test_an_empty_item_text_is_refused_rather_than_invented():
    with pytest.raises(ValueError):
        import_item("", SYNTHETIC_NAMING, record_id="r", created_at=CREATED_AT,
                    catalog_hash=CATALOG_HASH)


# ----------------------------------------------------- unsupported content

def test_an_unknown_modifier_category_is_reported_and_the_line_is_not_written():
    source = unknown_category_item()
    text, report, _restored = round_trip_item(source)
    assert report.completeness == "incomplete"
    loss = next(u for u in report.unsupported
                if u.field_path == "/modifiers/0/category")
    assert loss.preserved == "FIXTUREMOD unknown source line"
    assert "FIXTUREMOD unknown source line" not in text


def test_catalog_resolution_and_roll_ranges_are_reported_as_lost():
    source = resolved_modifier_item()
    _text, report, restored = round_trip_item(source)
    paths = report.paths()
    for field in ("native_id", "resolved_effect_ids", "values",
                  "parse_status"):
        assert "/modifiers/0/" + field in paths, field
    assert report.completeness == "incomplete"
    assert restored.modifiers[0].native_id is None
    assert restored.modifiers[0].values == []
    preserved = {u.field_path: u.preserved for u in report.unsupported}
    assert preserved["/modifiers/0/values"] == [[12.0, 10.0, 15.0]]


def test_a_flag_recorded_false_cannot_be_told_from_an_absent_one():
    source = false_flag_item()
    text, report, restored = round_trip_item(source)
    loss = next(u for u in report.unsupported
                if u.field_path == "/flags/corrupted")
    assert loss.preserved is False
    assert report.completeness == "incomplete"
    assert "Corrupted" not in text.splitlines()
    assert restored.flags == {}


def test_a_true_flag_does_survive():
    source = item("fixture-corrupt", base_id="base-quarterstaff",
                  display_name="FIXTURE Corrupt", flags={"corrupted": True},
                  modifiers=[])
    text, report, restored = round_trip_item(source)
    assert report.completeness == "complete"
    assert "Corrupted" in text.splitlines()
    assert restored.flags == {"corrupted": True}


def test_an_unresolved_base_is_reported_rather_than_invented():
    source = item("fixture-no-base", base_id=None,
                  display_name="FIXTURE No Base", modifiers=[])
    _text, report, restored = round_trip_item(source)
    loss = next(u for u in report.unsupported if u.field_path == "/base_id")
    assert loss.kind == "unresolved_name"
    assert restored.base_id is None


def test_a_requirement_other_than_level_is_reported():
    source = item("fixture-reqs", base_id="base-quarterstaff",
                  display_name="FIXTURE Requirements",
                  requirements={"level": 60, "dexterity": 120}, modifiers=[])
    _text, report, restored = round_trip_item(source)
    loss = next(u for u in report.unsupported
                if u.field_path == "/requirements/dexterity")
    assert loss.preserved == 120
    assert restored.requirements == {"level": 60}


def test_modifier_positions_that_cannot_be_renumbered_are_reported():
    """PoB writes the implicit block first and renumbers from zero."""
    source = item("fixture-order", base_id="base-quarterstaff",
                  display_name="FIXTURE Order",
                  modifiers=[modifier(ModifierCategory.EXPLICIT, 0, "one"),
                             modifier(ModifierCategory.IMPLICIT, 1, "two")])
    _text, report, _restored = round_trip_item(source)
    loss = next(u for u in report.unsupported if u.field_path == "/modifiers")
    assert loss.preserved == [0, 1]
