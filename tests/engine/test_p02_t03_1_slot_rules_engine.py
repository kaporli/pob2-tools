"""P02-T03.1 against the real PoB engine: slot rules versus real items.

What only the engine can establish:

* the slot acceptance probe the exporter reads is what the pinned engine
  returns now, and matches the committed capture the offline lane replays;
* for every real item of two real builds (the owner's seed character and
  the poe.ninja reference 25c49), loaded into PoB, the engine's own
  `ItemsTab:IsItemValidForSlot` agrees with the exported rule for every slot:
  the slots each item came from (positive) and every other slot (negative);
* the off-hand rule for the real main hand agrees with the engine when the
  off-hand slot is asked with that main hand equipped.

Both builds are PoB-derived configurations, not gameplay measurements.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from pob2opt.catalog.slotrules import read_acceptance

pytestmark = pytest.mark.engine

REPO_ROOT = Path(__file__).resolve().parents[2]
CAPTURE = REPO_ROOT / "docs" / "evidence" / "P02-T03.1" / "slot-acceptance.json"
SEED = REPO_ROOT / "docs" / "evidence" / "P09-T01.1" / "seed" / "export-flicker-main.xml"
NINJA = (REPO_ROOT / "docs" / "evidence" / "P09-T01.1" / "reference-ninja-25c49"
         / "decoded.xml")

#: Asks the engine about every loaded item in every slot that is not a jewel
#: socket on an item. The off-hand slots are asked twice: with an empty main
#: hand, and with the main hand the build actually holds.
CROSS_CHECK = r"""
local itemsTab = build.itemsTab
local function key(item)
  if item.base.subType then return item.type .. "/" .. item.base.subType end
  return item.type
end
local set = itemsTab.activeItemSet
local empty = { ["Weapon 1"] = { selItemId = 0 }, ["Weapon 1 Swap"] = { selItemId = 0 } }
local noFlags = { giantsBlood = false, instrumentsOfPower = false, lordOfTheWilds = false }
local held = {}
for name, slot in pairs(itemsTab.slots) do
  local id = set[name] and set[name].selItemId or 0
  if id ~= 0 then held[id] = held[id] or {}; table.insert(held[id], name) end
end
local mains = {}
for _, main in ipairs({ "Weapon 1", "Weapon 1 Swap" }) do
  local id = set[main] and set[main].selItemId or 0
  mains[main] = (id ~= 0 and itemsTab.items[id]) and key(itemsTab.items[id]) or "Unarmed"
end
local out = {}
for id, item in pairs(itemsTab.items) do
  if item.base then
    local verdicts, withMain = {}, {}
    for name in pairs(itemsTab.slots) do
      if not name:match("Jewel Socket") then
        verdicts[name] = itemsTab:IsItemValidForSlot(item, name, empty, noFlags) and true or false
      end
    end
    for _, off in ipairs({ "Weapon 2", "Weapon 2 Swap" }) do
      withMain[off] = itemsTab:IsItemValidForSlot(item, off, set, noFlags) and true or false
    end
    out[#out + 1] = { id = id, key = key(item), name = item.name,
      rarity = string.lower(tostring(item.rarity)),
      held = held[id] or {}, verdicts = verdicts, withMain = withMain }
  end
end
return { items = out, mains = mains }
"""


@pytest.fixture(scope="module")
def live_probe(engine):
    engine.call("new_build")
    return engine.call("catalog_rule_sources")["slotAcceptance"]


def test_the_live_probe_matches_the_committed_capture(live_probe):
    live = read_acceptance(live_probe)
    capture = read_acceptance(
        json.loads(CAPTURE.read_text(encoding="utf-8"))["slotAcceptance"])
    assert live.probe_count == capture.probe_count
    assert not live.probe_failures
    assert live.accepted == capture.accepted
    assert live.partial == capture.partial == {}
    assert sorted(live.off_hand, key=repr) == sorted(capture.off_hand, key=repr)


def test_the_probe_leaves_the_build_untouched(engine, live_probe):
    after = engine.eval_lua(
        "local n = 0 for _ in pairs(build.itemsTab.items) do n = n + 1 end "
        "return { items = n, probe = build.itemsTab.items[-987654] ~= nil }")
    assert after == {"items": 0, "probe": False}


def _expected(acceptance, slot, category, rarity, main_category=None):
    off = acceptance.off_hand_slots
    if slot in off:
        main = main_category or "Unarmed"
        rules = [c for c in acceptance.off_hand if c.off_slot == slot
                 and c.main_category == main and c.flag == "none"]
        assert len(rules) == 1, (slot, main)
        return (category in rules[0].accepted
                and rarity not in rules[0].refused_rarities)
    return (category in acceptance.accepted.get(slot, [])
            and rarity not in acceptance.refused_rarities.get(slot, []))


@pytest.mark.parametrize("document", [SEED, NINJA], ids=["seed", "ninja-25c49"])
def test_real_items_agree_with_the_rules_in_every_slot(engine, live_probe,
                                                       document):
    acceptance = read_acceptance(live_probe)
    engine.call("load_build_xml", {"xml": document.read_text(encoding="utf-8"),
                                   "name": document.stem})
    try:
        state = engine.eval_lua(CROSS_CHECK)
    finally:
        engine.call("new_build")
    items = state["items"]
    assert len(items) >= 15
    positives = negatives = 0
    held_somewhere = 0
    unprobed = set()
    for item in items:
        for slot, valid in item["verdicts"].items():
            if slot not in acceptance.accepted:
                unprobed.add(slot)
                continue
            expected = _expected(acceptance, slot, item["key"],
                                 item["rarity"])
            assert valid == expected, (item["name"], item["key"], slot)
            positives += valid
            negatives += not valid
        for slot in item["held"]:
            held_somewhere += 1
            if "Jewel Socket" in slot:
                continue
            # Positive case: the slot the real build put the item in.
            assert item["verdicts"][slot], (item["name"], slot)
        main_for = {"Weapon 2": state["mains"]["Weapon 1"],
                    "Weapon 2 Swap": state["mains"]["Weapon 1 Swap"]}
        for slot, valid in item["withMain"].items():
            assert valid == _expected(acceptance, slot, item["key"],
                                      item["rarity"], main_for[slot]),                 (item["name"], slot)
    # A build on another tree version has other jewel sockets; the probe was
    # read on a blank build of the default tree, so those are not compared.
    assert all(slot.startswith("Jewel ") for slot in unprobed), unprobed
    assert positives > len(items) and negatives > 10 * len(items)
    if document is NINJA:
        # A unique jewel the engine keeps out of some tree sockets: the
        # rarity rule, not the category rule, refuses it there.
        uniques = [i for i in items if i["key"] == "Jewel"
                   and i["rarity"] == "unique"]
        assert uniques and any(not v for i in uniques
                               for s, v in i["verdicts"].items()
                               if s in acceptance.refused_rarities)
    assert held_somewhere >= 15
