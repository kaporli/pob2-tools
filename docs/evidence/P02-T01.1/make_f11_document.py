"""Write f11-populated.xml: the build the test_f11 fixture makes, saved by PoB.

Nodes 47157 and 2955 are what ``search_nodes("projectile damage")`` returned in
every recorded repro run. Run once; the soak reads the saved file.
"""
import os
from pathlib import Path

from pob2mcp.engine import Pob2Engine

HERE = Path(__file__).resolve().parent
WEAPON = "\n".join(["Rarity: Rare", "Fixture Stave", "Long Quarterstaff", "Quality: 20",
                    "Item Level: 82", "Adds 60 to 90 Physical Damage",
                    "30% increased Attack Speed"])

engine = Pob2Engine(os.environ["POB2_ROOT"])
engine.call("new_build")
engine.call("alloc_nodes", {"ids": [47157, 2955]})
engine.call("equip_item", {"raw": WEAPON, "slot": "Weapon 1"})
xml = engine.call("save_build_xml")["xml"]
(HERE / "f11-populated.xml").write_text(xml, encoding="utf-8")
print(len(xml))
os._exit(0)
