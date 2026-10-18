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
| `slot-acceptance.json` | `rule_sources.slotAcceptance` as the engine returned it: per slot and per off-hand context, how many probe bases of each category `ItemsTab:IsItemValidForSlot` accepts at normal, unique and relic rarity | `785494be51f61cbde66108f1e20c56c980048b09553866314f74a8b6014d8915` |
| `slot-rules.json` | The slot rules, refused rarities, 152 off-hand rules and P02-T03.1 gaps the exporter built from it | `fce92377119db79d789e0084298bcfd01046691675c6568b8b77ab270643ee90` |
| `real-pool.json` | A pool from 46 real items: the owner's seed character (owned, in its source slots) and poe.ninja reference 25c49 (an imported guide: not owned, availability unknown) | `5986b8f44649e07289558688df9b101f1dbf54eb28ce35909628aaa45cd3084f` |
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

46 real items: 30 complete, 16 partial. 35 slots hold candidates, including
both rings, all three charm slots, both flasks, both limb pairs, both weapon
sets and every tree jewel socket; unique jewels are kept out of the seven
refusing sockets.

| Empty slot | Why |
|---|---|
| Amulet, Helmet, Gloves, Boots | Both real items of each are `partial`: the P05-T02 importer leaves lines such as `+4 to Level of all Melee Skills` or `40% increased Energy Shield` unresolved, so the pool refuses them. Issues are listed per input |
| Weapon 2, Weapon 2 Swap | Neither real build holds an off-hand item (quarterstaff and talisman) |

## Open gaps

| Gap | Severity | Meaning |
|---|---|---|
| `gap/p02-t03.1/socketed-item-jewel-slots` | ranking_sensitive | 72 item jewel sockets accept a jewel only when the parent item grants sockets (`canSocketJewelBase`); not modelled, so jewels there stay unplaced |
| `gap/p02-t03.1/off-hand-keystone-flags` | ranking_sensitive | Legality does not read the build's Giant's Blood, Instruments of Power or Lord of the Wilds flag; a pairing allowed only by one is `unknown` |

The P02-T02 gap `slot-accepted-base-categories` is no longer raised by a
probed export. Profiles without the probe (the committed P02 row slice) keep
it, and their rules stay empty.
