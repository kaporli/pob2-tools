"""Shared helpers for the engine-backed tests (P00-T02).

Kept outside ``tests/engine/conftest.py`` because a test module cannot import
from a conftest by name: ``import conftest`` resolves to the root one.
"""

from __future__ import annotations

#: A synthetic rare weapon. The values are invented; it exists to give the
#: engine something deterministic to calculate, not to describe a real item.
FIXTURE_WEAPON = "\n".join([
    "Rarity: Rare",
    "Fixture Stave",
    "Long Quarterstaff",
    "Quality: 20",
    "Item Level: 82",
    "Adds 60 to 90 Physical Damage",
    "30% increased Attack Speed",
])

STRONGER_WEAPON = FIXTURE_WEAPON.replace("60 to 90", "120 to 180")


def allocated_count(engine) -> int:
    return len(engine.call("get_tree")["allocated"])


def equipped_count(engine) -> int:
    items = engine.call("get_items")
    return len(items) if items else 0


def socket_group_count(engine) -> int:
    return len(engine.call("get_skills")["groups"])
