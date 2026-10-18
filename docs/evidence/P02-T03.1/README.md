# P02-T03.1 evidence: engine slot rules and a real item pool

Captured 2026-10-18 on Windows 11, CPython 3.12.4, from the submodule
`external/PathOfBuilding-PoE2` at `ce566eac45ea8a86477f513c7ee65a1ebe60014e`,
`git status` empty before and after (`pob_dirty_hash` null). Everything here
is PoB-derived. Nothing is a gameplay measurement.

```
POB2_ROOT=<clean checkout of ce566ea> python scripts/p02_t03_1_slot_rules.py
```

| File | What | SHA-256 |
|---|---|---|
| `slot-acceptance.json` | `rule_sources.slotAcceptance` as the engine returned it: per slot and per off-hand context, how many probe bases of each category `ItemsTab:IsItemValidForSlot` accepts at normal, unique and relic rarity | `6be152854950f4f1f5d0efeec2f13e2cc978810f89dfc3d77bf6ff9d65f95929` |
| `slot-rules.json` | The slot rules, refused rarities, 152 off-hand rules and P02-T03.1 gaps the exporter built from it | `958ff81f0c39b2e893a32cc1e7a3c8c1ecca1599b378624d221d36fc7fd276f6` |
| `real-pool.json` | A pool from 46 real items: the owner's seed character (owned, in its source slots) and poe.ninja reference 25c49 (an imported guide: not owned, availability unknown). Per item: parse status, line statuses, any unresolved line | `ccb71b88504fb7e7945a98996362ed6831e2eaaeb6f4856f8303de85185ac472` |
| `../P02/catalog-rows-slice.json` | The P02 row slice regenerated from the same clean checkout: tables unchanged, `rule_sources` gains `slotAcceptance` and citations gain `slot_validity`, so a replayed profile carries the slot rules | `5e0d18cd1714c65b0b1c2d8acb417241f3519860f746b43ab94b88a6f79d130d` |
| `offline-py312.txt`, `offline-py310.txt` | Offline suite tails | |
| `engine-py312.txt` | Targeted engine test tails | |

`real-pool.json` and `slot-rules.json` carry a `written_at` stamp and an
export time, so a rerun changes their hashes; `slot-acceptance.json` differs
only in `written_at`.

## How the rules are read

The engine has no slot-to-category table. `ItemsTab:IsItemValidForSlot`
(`src/Classes/ItemsTab.lua`) decides each case from the item type, subtype,
rarity, the tree node, the parent item and, for the off hand, the main-hand
base and three keystone flags. The new `slotAcceptance` rule source asks that
function directly: one probe item per `data.itemBases` entry (1756) at
normal, unique and relic rarity, against all 113 slots, and against both
off-hand slots once per main-hand base and flag state. The probe changes
nothing in the build.

A base category is `type`, or `type/subType` when the base has one. The
engine splits flasks by subtype, so the key needs it.

| Slot | Accepted categories (engine) |
|---|---|
| Weapon 1, Weapon 1 Swap | 18 weapon categories incl. `Staff/Warstaff` (quarterstaves), `Talisman`, `Bow`, `Two Hand Mace` |
| Weapon 2, Weapon 2 Swap | union over main hands: one-hand weapons, `Focus`, `Quiver`, `Sceptre`, shields, and two-hand axe/mace/sword (Giant's Blood only). Never spear, staff or bow |
| Helmet, Body Armour, Gloves, Boots | every subtype of that type |
| Amulet / Belt / Ring 1-3 / Charm 1-3 | `Amulet` / `Belt` / `Ring` / `Charm` |
| Flask 1 / Flask 2 | `Flask/Life` / `Flask/Mana` |
| Arm 1-2 / Leg 1-2 | `Transcendent Limb/Transcendent Arm` / `.../Transcendent Leg` |
| 19 tree jewel sockets | `Jewel`, `Jewel/Radius`, `Jewel/Timeless` (one socket `Jewel` only); 7 refuse unique and relic |
| 72 jewel sockets on items | none under the probe (parent-item condition); gap `socketed-item-jewel-slots` |

Off-hand rules, no keystone: a quarterstaff, staff, talisman, crossbow, two
hand weapon or fishing rod leaves no off hand; a bow takes only a quiver; a
wand or sceptre takes a focus, sceptre or shield; other one-hand weapons and
an empty main hand also take a one-hand weapon (not a spear). Keystones:
Giant's Blood adds two-hand axes, maces and swords; Instruments of Power lets
a staff take a focus; Lord of the Wilds lets a talisman take a non-unique
sceptre.

## Verification against the engine

`tests/engine/test_p02_t03_1_slot_rules_engine.py` loads both real builds into
PoB and asks `IsItemValidForSlot` about every loaded item in every slot that
is not an item jewel socket, with an empty main hand and with the build's own
main hand. Every answer matches the exported rule. The first run failed on
the reference build's unique Heart of the Well in seven tree sockets; that is
how the rarity rule was found, and the categories-only version would have
called it legal. The live probe also matches the committed capture.

## Real pool

Parser `p04-t01.6` / importer `p05-t02.2` (this task) changed two things.
PoB's `Unique ID:` line (44 of 46 items) and `Runic Ward:` were read as
modifier lines, which shifted each item's implicit block by one line; they
are now headers. And a line no single random affix explains gets
`stat_resolved` when its text is a catalog modifier line's (any type,
including unique, corrupted and desecrated) and its value is within what all
catalog lines of that text sum to. Typical cases: `+4 to Level of all Melee
Skills` (the item affix gives +1, other sources add), `+56% to Fire
Resistance` on a ring, Runeforged exclusive lines.

Line statuses over the 46 items: 204 resolved, 27 `stat_resolved`, 10
ambiguous (several affix tiers fit), 2 unresolved. The P04 review requires
ambiguous and out-of-range lines to keep an item `partial` and its builds
non-recommendable, so those 16 items stay `partial`. 14 of them are
`stat_known` (base resolved, every line's stat known) and the pool places
them, marked `stat_known_partial`. The other 2 each have one line that
matches no catalog text and are not placed:

| Item | Unresolved line |
|---|---|
| 25c49 Gloves (Golem Claw) | `20% more Global Evasion Rating and Energy Shiel`, truncated in the source |
| 25c49 Jewel 32763 (Spirit Wound) | `Notable Passive Skills in Radius also grant 12% increased Critical Damage Bonus for Attack Damage`; the catalog line is (5-10)% |

39 slots hold candidates: every armour and jewelry slot, all three charm
slots, both flasks, both limb pairs, Weapon 1 and Weapon 1 Swap and every
tree jewel socket. Unique jewels are kept out of the seven refusing sockets.
Only Weapon 2 and Weapon 2 Swap are empty: neither real build holds an
off-hand item (quarterstaff and talisman).

## Open gaps

| Gap | Severity | Meaning |
|---|---|---|
| `gap/p02-t03.1/socketed-item-jewel-slots` | ranking_sensitive | 72 item jewel sockets accept a jewel only when the parent item grants sockets (`canSocketJewelBase`); not modelled, so jewels there stay unplaced |
| `gap/p02-t03.1/off-hand-keystone-flags` | ranking_sensitive | Legality does not read the build's Giant's Blood, Instruments of Power or Lord of the Wilds flag; a pairing allowed only by one is `unknown` |

The P02-T02 gap `slot-accepted-base-categories` is no longer raised by a
probed export. Profiles without the probe (the committed P02 row slice) keep
it, and their rules stay empty.
