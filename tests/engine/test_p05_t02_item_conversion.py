"""P05-T02 against the pinned engine: game item text, our record and PoB.

Two checks per fixture in ``tests/fixtures/p05/game-items.json``:

* PoB reads the same game clipboard text into the same modifier categories,
  texts, item level, level requirement, sockets and item flags as
  ``parsers/gametext.py``. PoB's reading is taken from the document it saves.
* Our record exported as PoB item text, equipped and saved by PoB, reads back
  with the same canonical item identity (the P02 conversion round trip).

Synthetic items; nothing here is a gameplay measurement.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from dataclasses import replace

import pytest

import p05_fixtures as fx
from pob2opt.domain.identity import item_identity
from pob2opt.evaluation import export_item, import_item
from pob2opt.evaluation.roundtrip import diff_identity
from pob2opt.parsers.dispatch import read_item_text
from pob2opt.parsers.resolve import naming_from_catalog

pytestmark = pytest.mark.engine

#: Fixture -> PoB slot. Every fixture our reader completes without loss.
CASES = {
    "ring_shared_name_a": "Ring 1",
    "ring_shared_name_b": "Ring 1",
    "bow_every_category": "Weapon 1",
    "magic_ring": "Ring 1",
}


def ours(name):
    text = fx.game_items()[name]
    read = read_item_text(text, fx.document(text.encode()), fx.context(),
                          record_id="ours")
    assert read.item is not None
    return read.item


def naming():
    return naming_from_catalog(fx.context().entities).naming


def pob_saved_item(engine, raw: str, slot: str):
    """Equip ``raw`` in a new build and read the item from PoB's own save."""
    engine.call("new_build")
    engine.call("equip_item", {"raw": raw, "slot": slot})
    xml = engine.call("save_build_xml")["xml"]
    items = ET.fromstring(xml).findall("Items/Item")
    assert len(items) == 1, xml
    text = "".join(items[0].itertext())
    return import_item(text, naming(), record_id="pob",
                       created_at=fx.context().created_at,
                       catalog_hash=fx.context().catalog_hash)


def lines(item):
    return [(m.category.value, m.text) for m in item.modifiers]


@pytest.mark.parametrize("name", sorted(CASES))
def test_pob_reads_the_game_text_as_we_do(engine, name):
    record = ours(name)
    pob = pob_saved_item(engine, fx.game_items()[name], CASES[name])
    assert lines(pob) == lines(record)
    assert pob.item_level == record.item_level
    assert pob.requirements.get("level") == record.requirements.get("level")
    assert [s.colour for s in pob.sockets] == [s.colour for s in record.sockets]
    assert pob.flags == record.flags
    assert pob.base_id == record.base_id
    assert pob.rarity == record.rarity


@pytest.mark.parametrize("name", sorted(CASES))
def test_our_record_survives_pob_load_and_save(engine, name):
    record = ours(name)
    text, losses = export_item(record, naming())
    assert losses.report().completeness == "complete"
    back = pob_saved_item(engine, text, CASES[name])
    assert diff_identity(item_identity(record), item_identity(back)) == []


def test_pob_writes_level_zero_for_an_item_without_a_requirement(engine):
    """Not silent: the comparison names the one field PoB adds.

    Without a ``Requires`` line the record keeps the level requirement
    unknown; PoB saves ``LevelReq: 0``.
    """
    raw = fx.game_items()["magic_ring"].replace(
        "Requires: Level 11\n--------\n", "")
    record = read_item_text(raw, fx.document(raw.encode()), fx.context(),
                            record_id="ours").item
    assert "level" not in record.requirements
    text, _ = export_item(record, naming())
    back = pob_saved_item(engine, text, "Ring 1")
    differences = diff_identity(item_identity(record), item_identity(back))
    assert [(d.path, d.before, d.after) for d in differences] == [
        ("/requirements/level", None, 0)]


def test_pob_moves_rune_lines_ahead_of_enchant_lines(engine):
    """PoB keeps every line and category but reorders the implicit block,
    so source positions change. Reported here, not hidden."""
    raw = fx.game_items()["bow_every_category"]
    rune = ("FIXTUREMOD 10% increased Physical Damage (rune)\n"
            "FIXTUREMOD 6% increased Attack Speed (rune)\n--------\n")
    enchant = "FIXTUREMOD 12% increased Projectile Speed (enchant)\n--------\n"
    swapped = raw.replace(rune + enchant, enchant + rune)
    assert swapped != raw
    record = read_item_text(swapped, fx.document(swapped.encode()),
                            fx.context(), record_id="ours").item
    pob = pob_saved_item(engine, swapped, "Weapon 1")
    assert sorted(lines(pob)) == sorted(lines(record))
    assert lines(pob) != lines(record)
    assert [c for c, _ in lines(pob)[:3]] == ["rune", "rune", "enchant"]


def test_a_named_rune_survives_pob_load_and_save(engine):
    """PoB's ``Rune:`` lines read as rune names, not as modifier lines."""
    record = ours("bow_every_category")
    named = replace(record, properties=dict(record.properties,
                                            runes=["None", "Iron Rune"]))
    text, losses = export_item(named, naming())
    assert losses.report().completeness == "complete"
    assert "Rune: Iron Rune" in text
    back = pob_saved_item(engine, text, "Weapon 1")
    assert back.properties.get("runes") == ["None", "Iron Rune"]
    assert not any(m.text.startswith("Rune:") for m in back.modifiers)
