"""Research finding F12 and its repair inside the pinned engine (P00-T04, P02-T05).

The LuaJIT probe in ``tests/integration`` runs the handler source in isolation.
This repeats it through ``MCP_dispatch`` in the real PoB process, with PoB's own
``escapeGGGString``, and additionally shows what the repair recovers: the
converted item is equipped and its previously lost affix now reaches the
calculation.

The characterization here was that fractured, desecrated and crafted modifiers
were dropped and the loss cost real damage. P02-T05 repaired it, so those
assertions were migrated in place: they now pin the recovered affix instead of
the loss. The reason is written here rather than in a deleted file.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

pytestmark = pytest.mark.engine

#: Categories the original handler dropped, with the marker PoB writes.
REPAIRED_CATEGORIES = (("fractured", "{fractured}"),
                       ("desecrated", "{desecrated}"),
                       ("crafted", "{crafted}"))
EMITTED_CATEGORIES = ("enchant", "rune", "implicit", "explicit")


@pytest.fixture(scope="module")
def fixture_item(fixtures_dir: Path) -> dict:
    payload = json.loads(
        (fixtures_dir / "trade" / "item_all_mod_categories.json").read_text(encoding="utf-8"))
    return payload["item"]


@pytest.fixture()
def conversion(blank_build, fixture_item: dict) -> dict:
    return blank_build.call("convert_trade_item", {"item": fixture_item})


@pytest.fixture()
def converted(conversion: dict) -> str:
    return conversion["item_string"]


def test_supported_categories_survive(converted: str):
    for category in EMITTED_CATEGORIES:
        assert "FIXTUREMOD %s line one" % category in converted, category


def test_fractured_desecrated_and_crafted_modifiers_are_preserved(converted: str):
    """Was the F12 characterization: the three categories were lost."""
    for category, marker in REPAIRED_CATEGORIES:
        line = marker + "FIXTUREMOD %s line one" % category
        assert line in converted.splitlines(), line


def test_the_engine_agrees_with_the_standalone_probe(converted: str):
    """Same handler, same output: the probe's stubs do not change the result."""
    assert converted.splitlines()[:6] == [
        "Rarity: Rare",
        "FIXTURE Mod Category Probe",
        "Long Quarterstaff",
        "Item Level: 82",
        "Quality: 20",
        "LevelReq: 65",
    ]
    assert "Implicits: 3" in converted.splitlines()


def test_the_handler_reports_a_complete_conversion(conversion: dict):
    assert conversion["complete"] is True
    assert conversion["unsupported"] in ([], {})
    assert conversion["emitted_mod_counts"]["craftedMods"] == 1
    assert conversion["emitted_mod_counts"]["explicitMods"] == 2


def test_pob_reads_the_recovered_lines_back_in_the_right_category(blank_build,
                                                                  converted: str):
    """PoB's own parser, not ours, decides what each marker means."""
    blank_build.call("equip_item", {"raw": converted, "slot": "Weapon 1"})
    rebuilt = blank_build.call("get_items", {"raw": True})["Weapon 1"]["raw"]
    for category, marker in REPAIRED_CATEGORIES:
        assert marker + "FIXTUREMOD %s line one" % category in rebuilt.splitlines()


def test_a_recovered_affix_reaches_the_calculation(blank_build):
    """Was: the crafted affix left no trace at all and contributed no damage."""
    base = {
        "rarity": "Rare",
        "name": "Fixture Affix Probe",
        "typeLine": "Long Quarterstaff",
        "ilvl": 82,
        "explicitMods": [{"description": "Adds 60 to 90 Physical Damage"}],
    }
    with_crafted = dict(base, craftedMods=[{"description": "Adds 200 to 300 Fire Damage"}])

    only_explicit = blank_build.call("convert_trade_item", {"item": base})["item_string"]
    with_extra = blank_build.call("convert_trade_item", {"item": with_crafted})["item_string"]
    assert only_explicit != with_extra, "the crafted affix left no trace"
    assert "{crafted}Adds 200 to 300 Fire Damage" in with_extra.splitlines()

    blank_build.call("equip_item", {"raw": only_explicit, "slot": "Weapon 1"})
    without = blank_build.call("get_stats", {"keys": ["CombinedAvg"]})["CombinedAvg"]
    blank_build.call("new_build")
    blank_build.call("equip_item", {"raw": with_extra, "slot": "Weapon 1"})
    with_affix = blank_build.call("get_stats", {"keys": ["CombinedAvg"]})["CombinedAvg"]
    # The engine chooses the stat names; only the direction is asserted, and
    # this is a PoB calculation, not a gameplay measurement.
    assert with_affix > without, (without, with_affix)


def test_conversion_does_not_mutate_the_caller_object(blank_build, fixture_item: dict):
    before = json.dumps(fixture_item, sort_keys=True)
    blank_build.call("convert_trade_item", {"item": fixture_item})
    assert json.dumps(fixture_item, sort_keys=True) == before


def test_repaired_conversion_preserves_every_modifier_category(converted: str):
    """Was an xfail naming P02-T05. The repair makes it a pass."""
    for category, _marker in REPAIRED_CATEGORIES:
        assert "FIXTUREMOD %s line one" % category in converted, category
