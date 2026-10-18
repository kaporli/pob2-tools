"""PR #19 R1 against the real engine: coverage reads the sets PoB selects.

The seed export is rewritten into a two-loadout document with non-consecutive
ids in all four set types; the seed's own sets are the selected ones, placed
second. PoB's loaded state (selected ids, socket groups, allocated nodes,
equipped items and config inputs) must equal what ``build_facts_from_pob_xml``
reads. Run alone: one engine, real PoB checkout.
"""

from __future__ import annotations

import copy
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from pob2opt.coverage.inputs import build_facts_from_pob_xml

pytestmark = pytest.mark.engine

SEED = Path(__file__).resolve().parents[2] / "docs/evidence/P09-T01.1/seed/export-flicker-main.xml"

STATE_LUA = r"""
local out = { groups = {}, nodes = {}, items = {}, inputs = {} }
out.selection = {
  Tree = tostring(build.treeTab.activeSpec),
  Skills = tostring(build.skillsTab.activeSkillSetId),
  Items = tostring(build.itemsTab.activeItemSetId),
  Config = tostring(build.configTab.activeConfigSetId),
}
for _, group in ipairs(build.skillsTab.socketGroupList) do
  local ids = {}
  for _, gem in ipairs(group.gemList) do ids[#ids + 1] = gem.skillId or "" end
  out.groups[#out.groups + 1] = ids
end
for id in pairs(build.spec.allocNodes) do out.nodes[#out.nodes + 1] = tostring(id) end
for name, slot in pairs(build.itemsTab.slots) do
  if slot.selItemId and slot.selItemId ~= 0 and build.itemsTab.items[slot.selItemId] then
    out.items[#out.items + 1] = { slot = name, id = tostring(slot.selItemId) }
  end
end
local set = build.configTab.configSets[build.configTab.activeConfigSetId]
for var, value in pairs(set.input) do
  if type(value) ~= "table" then out.inputs[#out.inputs + 1] = { var = var, value = value } end
end
return out
"""


def two_loadout_seed() -> str:
    root = ET.fromstring(SEED.read_bytes())
    skills = root.find("Skills")
    seed_set = skills.find("SkillSet")
    other = ET.Element("SkillSet", {"id": "3"})
    other.append(copy.deepcopy(seed_set.find("Skill")))
    seed_set.set("id", "7")
    skills.insert(0, other)
    skills.set("activeSkillSet", "7")

    tree = root.find("Tree")
    spec = tree.find("Spec")
    first = copy.deepcopy(spec)
    first.set("nodes", ",".join(spec.get("nodes").split(",")[:5]))
    for child in list(first):
        if child.tag == "Sockets":
            first.remove(child)
    tree.insert(list(tree).index(spec), first)
    tree.set("activeSpec", "2")

    items = root.find("Items")
    seed_items = items.find("ItemSet")
    other_items = ET.Element("ItemSet", {"id": "4"})
    seed_items.set("id", "9")
    items.insert(list(items).index(seed_items), other_items)
    items.set("activeItemSet", "9")

    config = root.find("Config")
    seed_config = config.find("ConfigSet")
    other_config = ET.Element("ConfigSet", {"id": "2"})
    ET.SubElement(other_config, "Input", {"name": "conditionOnslaught", "boolean": "true"})
    seed_config.set("id", "5")
    config.insert(0, other_config)
    config.set("activeConfigSet", "5")
    return ET.tostring(root, encoding="unicode")


def test_facts_match_pobs_selected_loadout(engine):
    doc = two_loadout_seed()
    facts = build_facts_from_pob_xml(doc)
    assert not facts.loadout_problems
    assert dict(facts.selection) == {"Tree": "2", "Skills": "7", "Items": "9", "Config": "5"}
    engine.call("load_build_xml", {"xml": doc, "name": "p06-loadout"})
    state = engine.eval_lua(STATE_LUA)
    assert state["selection"] == dict(facts.selection)
    assert [list(g) for g in state["groups"]] == [[gem.skill_id for gem in g.gems]
                                                  for g in facts.groups]
    assert sorted(state["nodes"], key=int) == list(facts.passive_ids)
    assert {(i["slot"], i["id"]) for i in state["items"]} == {
        (i.slot, i.item_id) for i in facts.items}
    inputs = {i["var"]: i["value"] for i in state["inputs"]}
    assert "conditionOnslaught" not in inputs
    for var, value in facts.config_explicit.items():
        engine_value = inputs.get(var)
        if isinstance(value, str):
            assert engine_value.split() == value.split(), var
        else:
            assert engine_value == value, var
