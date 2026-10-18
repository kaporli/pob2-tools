"""Write the P05-T02 fixtures in tests/fixtures/p05 (synthetic).

    python scripts/p05_make_fixtures.py

Rewrites ``game-items.json`` and ``capture-example5.json``. Update their
entries in ``tests/fixtures/manifest.json`` after a change.
"""

from __future__ import annotations

import json
from pathlib import Path

OUT = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "p05"


def lines(*parts: str) -> str:
    return "\n".join(parts) + "\n"


RING_A = lines(
    "Item Class: Rings", "Rarity: Rare", "Shared Name", "Iron Ring", "--------",
    "Requires: Level 44", "--------", "Item Level: 79", "--------",
    "Adds 1 to 4 Physical Damage to Attacks (implicit)", "--------",
    "Adds 9 to 15 Cold damage to Attacks", "+21 to Dexterity", "--------",
    "Corrupted")
RING_B = RING_A.replace("Adds 9 to 15 Cold", "Adds 10 to 17 Cold")

ITEMS = {
    "ring_shared_name_a": RING_A,
    "ring_shared_name_b": RING_B,
    "ring_other_name_same_stats_as_b": RING_B.replace("Shared Name",
                                                      "Other Name"),
    "ring_shared_name_a_with_note": RING_A.replace(
        "Corrupted", "Note: ~price 5 exalted\n--------\nCorrupted"),
    "bow_every_category": lines(
        "Item Class: Bows", "Rarity: Rare", "FIXTURE Category Probe",
        "Crude Bow", "--------",
        "Quality: +20% (augmented)", "Physical Damage: 7-11 (augmented)",
        "Critical Hit Chance: 5.00%", "Attacks per Second: 1.20", "--------",
        "Requires: Level 70", "--------", "Sockets: S S", "--------",
        "Item Level: 82", "--------",
        "FIXTUREMOD 10% increased Physical Damage (rune)",
        "FIXTUREMOD 6% increased Attack Speed (rune)", "--------",
        "FIXTUREMOD 12% increased Projectile Speed (enchant)", "--------",
        "FIXTUREMOD 20% chance to Pierce an Enemy (implicit)", "--------",
        "+21 to Dexterity", "Gain 30 Life per enemy killed (fractured)",
        "Attacks with this Weapon Penetrate 20% Fire Resistance (desecrated)",
        "FIXTUREMOD +10% to Cold Resistance (crafted) (unscalable)",
        "--------",
        "Mirrored"),
    "spear_attribute_requirements": lines(
        "Item Class: Spears", "Rarity: Rare", "FIXTURE Brood Edge",
        "Hunting Spear", "--------",
        "Physical Damage: 33-61 (augmented)",
        "Critical Hit Chance: 8.70% (augmented)", "--------",
        "Requires: Level 59, 33 Str, 81 (unmet) Dex", "--------",
        "Item Level: 76", "--------",
        "20% chance to Maim on Hit (implicit)", "--------",
        "Grants Skill: Spear Throw", "--------",
        "+21 to Dexterity"),
    "unique_with_flavour_text": lines(
        "Item Class: Body Armours", "Rarity: Unique", "FIXTURE Unique Vest",
        "Leather Vest", "--------",
        "Evasion Rating: 120 (augmented)", "--------",
        "Requirements:", "Level: 30", "Dex: 40 (unmet)", "--------",
        "Item Level: 60", "--------",
        "FIXTUREMOD +40 to maximum Life",
        "FIXTUREMOD 30% increased Evasion Rating", "--------",
        "FIXTURE flavour text, first line", "and its second line"),
    "magic_ring": lines(
        "Item Class: Rings", "Rarity: Magic", "Iron Ring of the Fixture",
        "--------", "Requires: Level 11", "--------", "Item Level: 40",
        "--------", "Adds 1 to 4 Physical Damage to Attacks (implicit)",
        "--------", "+13 to Dexterity"),
    "advanced_copy": lines(
        "Item Class: Rings", "Rarity: Rare", "Shared Name", "Iron Ring",
        "--------", "Item Level: 79", "--------",
        '{ Suffix Modifier "of the Fox" (Tier: 5) - Attribute }',
        "+21(21-24) to Dexterity"),
}

GAME_ITEMS = {
    "kind": "synthetic",
    "purpose": "Game clipboard item texts for P05-T02: same-name different "
               "rolls, equal stats under another name, every modifier "
               "category marker, attribute requirements, a unique with "
               "flavour text, a magic item and a refused advanced copy.",
    "not_a_claim": "Hand-written in the section layout of PoB's own parser "
                   "tests (spec/System/TestItemParse_spec.lua at ce566ea). "
                   "FIXTURE names and FIXTUREMOD lines are invented; other "
                   "affix lines were chosen to match rows of "
                   "tests/fixtures/p04/catalog-slice.json. Nothing was copied "
                   "from the game or a trade site.",
    "items": ITEMS,
}

CAPTURE = {
    "format": "pob2opt.market_capture",
    "format_version": 1,
    "kind": "synthetic",
    "purpose": "acceptance-examples.md example 5: L1 and L2 share a display "
               "name with different rolls; L2 and L3 have equal stats; L3 "
               "has no price; a fourth item has no listing.",
    "not_a_claim": "Invented listings. No provider was contacted; the "
                   "provider, league and listing ids are placeholders.",
    "provider": "fixture-market",
    "realm": "poe2",
    "league_id": "Fixture League",
    "observed_at": "2026-10-16T18:00:00Z",
    "entries": [
        {"item_text": RING_A,
         "listing": {"listing_id": "L1", "quantity": 1,
                     "price": {"amount": "5", "currency": "exalted"}}},
        {"item_text": RING_B,
         "listing": {"listing_id": "L2", "quantity": 1,
                     "price": {"amount": "1000", "currency": "divine"}}},
        {"item_text": RING_B,
         "listing": {"listing_id": "L3", "price": None}},
        {"item_text": ITEMS["magic_ring"], "listing": None},
    ],
}


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    for name, data in (("game-items.json", GAME_ITEMS),
                       ("capture-example5.json", CAPTURE)):
        (OUT / name).write_text(json.dumps(data, indent=2) + "\n",
                                encoding="utf-8", newline="\n")
        print(OUT / name)


if __name__ == "__main__":
    main()
