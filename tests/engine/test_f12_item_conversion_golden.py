"""Research finding F12 inside the pinned engine (P00-T04).

The LuaJIT probe in ``tests/integration`` runs the handler source in isolation.
This repeats it through ``MCP_dispatch`` in the real PoB process, with PoB's own
``escapeGGGString``, and additionally shows what the loss costs: the converted
item is equipped and its missing affix is absent from the calculation.

The repair is P02-T05.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

pytestmark = pytest.mark.engine

DROPPED_CATEGORIES = ("fractured", "desecrated", "crafted")
EMITTED_CATEGORIES = ("enchant", "rune", "implicit", "explicit")


@pytest.fixture(scope="module")
def fixture_item(fixtures_dir: Path) -> dict:
    payload = json.loads(
        (fixtures_dir / "trade" / "item_all_mod_categories.json").read_text(encoding="utf-8"))
    return payload["item"]


@pytest.fixture()
def converted(blank_build, fixture_item: dict) -> str:
    return blank_build.call("convert_trade_item", {"item": fixture_item})["item_string"]


def test_supported_categories_survive(converted: str):
    for category in EMITTED_CATEGORIES:
        assert "FIXTUREMOD %s line one" % category in converted, category


def test_fractured_desecrated_and_crafted_modifiers_are_lost(converted: str):
    for category in DROPPED_CATEGORIES:
        assert "FIXTUREMOD %s line one" % category not in converted, category


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


def test_a_dropped_affix_does_not_reach_the_calculation(blank_build):
    """The loss is not cosmetic: a real affix stops contributing damage."""
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
    assert only_explicit == with_extra, "the crafted affix left no trace at all"

    blank_build.call("equip_item", {"raw": with_extra, "slot": "Weapon 1"})
    stats = blank_build.call("get_stats", {"all": True})
    assert stats.get("FireDamage", 0) == 0


def test_conversion_does_not_mutate_the_caller_object(blank_build, fixture_item: dict):
    before = json.dumps(fixture_item, sort_keys=True)
    blank_build.call("convert_trade_item", {"item": fixture_item})
    assert json.dumps(fixture_item, sort_keys=True) == before


# ------------------------------------------------------- repaired behaviour

@pytest.mark.xfail(
    strict=True,
    reason="F12 repair is P02-T05: every modifier category must be preserved in "
           "the converted item or reported as unsupported.",
)
def test_repaired_conversion_preserves_every_modifier_category(converted: str):
    for category in DROPPED_CATEGORIES:
        assert "FIXTUREMOD %s line one" % category in converted, category
