"""Smoke test for the engine layer (run directly: python test_engine.py)."""

import json
import sys

sys.path.insert(0, r"C:\Users\Elias\PycharmProjects\pob2-mcp")

from pob2mcp.engine import Pob2Engine

e = Pob2Engine()

print("== new_build ==")
print(json.dumps(e.call("new_build"), indent=2))

print("== eval: engine internals reachable ==")
print(e.eval_lua("return { version = build.targetVersionData and 1 or 0, classes = #build.spec.tree.classes }"))

print("== search_nodes ==")
nodes = e.call("search_nodes", {"text": "projectile damage", "limit": 5})
print(json.dumps(nodes[:3], indent=2))

print("== alloc a node ==")
if nodes:
    r = e.call("alloc_nodes", {"ids": [nodes[0]["id"]]})
    print("pointsUsed:", r["pointsUsed"])

print("== get_stats ==")
stats = e.call("get_stats")
print(json.dumps(stats, indent=2)[:800])

print("== equip a test weapon ==")
weapon = """Rarity: Rare
Storm Bite
Long Quarterstaff
Quality: 20
Item Level: 82
Adds 60 to 90 Physical Damage
Adds 20 to 35 Lightning Damage
30% increased Attack Speed
+3 to Level of all Melee Skills"""
r = e.call("equip_item", {"raw": weapon, "slot": "Weapon 1"})
print("equipped:", r["name"])

print("== items ==")
print(json.dumps(e.call("get_items"), indent=2))

print("== test_item (non-destructive compare) ==")
better = weapon.replace("60 to 90", "120 to 180")
r = e.call("test_item", {"raw": better, "slot": "Weapon 1"})
print(json.dumps(r, indent=2)[:600])

print("== save/load round trip ==")
xml = e.call("save_build_xml")["xml"]
print("xml length:", len(xml))
r = e.call("load_build_xml", {"xml": xml})
print(json.dumps(r, indent=2))

print("== convert_trade_item ==")
fake_trade_item = {
    "rarity": "Rare",
    "name": "Doom Knuckle",
    "typeLine": "Long Quarterstaff",
    "ilvl": 81,
    "implicitMods": [],
    "explicitMods": [
        {"description": "Adds 50 to 80 Physical Damage"},
        {"description": "25% increased Attack Speed"},
    ],
}
r = e.call("convert_trade_item", {"item": fake_trade_item})
print(r["item_string"])

print("ALL OK")
