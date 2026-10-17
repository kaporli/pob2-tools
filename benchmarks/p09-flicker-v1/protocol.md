# Measurement protocol, suite `p09-flicker-v1`

Task P09-T01.1. Specification version 1.1. Written 2026-10-17. Status:
proposed, not accepted.

This protocol starts the Flicker Strike scope of D07 from one owner export and
the owner's rotation. It defines two clear workloads, two boss workloads and
D07's `flicker_sustained_v1` benchmark, and states for every field a source or
the DataGap that has to close first. It proposes a class list and three
interaction variants. It freezes definitions and hashes. It freezes no
reference result, because nothing has been measured.

**Read this first.** No enemy statistic, encounter timing, threshold or
performance value here was measured. The seed export is a configuration, not
a trial. PoB numbers are `proxy_only`. D04 stays blocked for practical claims.

## What is frozen

| Artefact | Path | SHA-256 |
|---|---|---|
| Scenario definitions, rotation record, owner questions, DataGaps | `benchmarks/p09-flicker-v1/scenarios.json` | `bd0c19da6861f2cce6291facd467456a8b97a167a840f1a50b1fc9e8206ef17a` |
| Reference manifest | `benchmarks/p09-flicker-v1/references.json` | `80e9104af49e2be3a5de5b49f81adc97e16563f72661e8e4b8056592ef15e62f` |
| Suite manifest and hashes | `benchmarks/p09-flicker-v1/suite.json` | see the file |
| Seed export manifest | `docs/evidence/P09-T01.1/seed/manifest.json` | `6a2ba0c4c810e436fb0e9592c910baa71b080594a70f17d7748bc6dc1fbedf35` |
| Scope and variant proposal | `docs/evidence/P09-T01.1/scope-proposal.json` | `6c0031595810de856947c448dd3cbe91877c892209dcb0d8b355bcafa696a75a` |
| Pinned engine data extract | `docs/evidence/P09-T01.1/mechanics.json` | `5ea1a78d03d9f8e56847bbadd99525900dae6421d2a56d40a5397e6f53c6feec` |

`suite_hash` is `89667d09ddf1aa803e107225256d65615ddd7d4375e3388300139b93e97a5549`.

| Scenario | `definition_hash` |
|---|---|
| `p09-flk-clear-dense` | `a0a6203f86f1a27d91747979200a2544dd438093d5fba13e844ecf7a93f8948b` |
| `p09-flk-clear-spread` | `6abb7f26de302916a11ee4dbab078301993291c5b64c27d68cd6acf55c4c520b` |
| `p09-flk-boss-short` | `d6eb9af8a2b5c5ef329ee07c4b5f88de9112da511c41b807d9e8deb969cf2c2b` |
| `p09-flk-boss-sustained` | `f33589cdb5b00989ec4f9e99ea50ed7996d2b80a6045e153caa6a7936400c9d6` |
| `flicker_sustained_v1` | `fcb3c156f878ff50b7e0bb541fac22fb058241963bd79f1b64fb3ca687e58dd5` |

Hashing follows `pob2opt/domain/identity.py`: files by SHA-256 of their raw
bytes, each scenario object by `content_hash` (canonical JSON), and the suite
by `content_hash` of the sorted definition hashes with their reference slots.
`scenario_hash` over a `ScenarioSpec` does not apply yet: `duration_limit_s`
and the entity health fields are required and non-nullable, and they are
unknown. Every reference slot is null; freezing one changes `suite_hash` and
starts a separate leaderboard.

## The seed export

Owner-supplied 2026-10-17: the owner's Forbidden Rites character, Monk /
Martial Artist, level 93, 116 passive points, imported from the account API
through the operator's `pob2` MCP server. This is account-character import,
which D01 keeps separate from market access; no provider build source was
used. The name is recorded once, in the seed manifest, for provenance.

Stored under `docs/evidence/P09-T01.1/seed/`: the PoB document as imported
(main skill Herald of Ice) and with Flicker Strike selected, the share code
(decodes to the first document byte for byte), raw item text, socket groups
with gem and granted-effect ids, allocated passive nodes, PoB config input
and the PoB stat output with Flicker Strike as main skill. The engine was the
operator's checkout at the pinned HEAD `ce566ea`; its working tree was not
checked, so those stats carry `gap-p09-t011-engine-checkout-state`.

Facts the export supplies (configuration only):

- Flicker Strike 20/23 with Hit and Run, Concentrated Area, Close Combat II,
  Perpetual Charge, Rakiata's Flow.
- Whirling Assault 18/20 with Living Lightning II, Culmination II, Ailith's
  Chimes, Rage II, Oisin's Oath.
- Rare Sinister Quarterstaff; Nettle Talisman in weapon swap (Sanguine
  Revelry); Mageblood.
- Maximum Power Charges 5: base 3 plus Overflowing Power +2 (passive 65204).
- Chaos Inoculation (passive 56349): maximum life 1, energy shield 3902.
- Martial Artist notables: Martial Adept, Martial Master, Runic Meridians, Way
  of the Stonefist.

PoB with Flicker Strike selected reports TotalDPS 1,048,349.886 with 0 Power
Charges in the calculation (one strike per use), enemy preset Pinnacle, level
82, elemental resistances 50, mana cost 248 per use. This is `proxy_only`. It
is not D07's time-accounted benchmark and not a measurement.

## Owner's rotation

Verbatim, the only rotation evidence:

> whirling assault to get 5 power charges & then flicker strike, rince and repeat

What the pinned engine data says about the parts it names (citations are
`mechanic_id`s in `mechanics.json`):

| Part | Evidence |
|---|---|
| Power Charge source | Ailith's Chimes on Whirling Assault: "25% Surpassing chance to gain a Power Charge when expending Combo with Supported Skills per Combo expended" (`support/SupportAilithLineagePlayer`, `statdesc/chance_%_to_gain_power_charges_per_combo_spent`). Requires ComboStacking, which Culmination II adds. |
| Combo | Culmination II: Combo gained when striking with other melee attacks, up to 10, all expended on use, 6000 ms decay delay (`support/SupportCulminationPlayerTwo`). Seed Martial Adept: an additional Combo per Combo gained; Martial Master: Combo from all Attack Hits (`passive/41751`, `passive/61586`). |
| Maximum charges | 5 in the seed (`passive/65204`), matching the owner's "5 power charges". |
| Charges consumed by Flicker Strike | Consumes Power Charges; "Teleports and Strikes 2 additional times per Power Charge"; "You cannot gain Power Charges while using this Skill" (`skill/FlickerStrikePlayer` and its two statdesc entries). PoB counts extra strikes as 2 x removable Power Charges (`engine/removable-power-charges`). |
| Perpetual Charge | 25% chance to not remove Charges but still count as consuming them (`support/SupportPerpetualChargePlayer`). |
| Movement condition | Hit and Run: usable after moving 10 metres, unusable again after use, 40% more skill speed (`support/SupportHitAndRunPlayer`). |
| Competing consumer | Charged Staff, also in the seed, consumes all Power Charges and requires 1 (`skill/ChargedStaffPlayer`). |
| Mana | Flicker Strike base cost 85 at level 20; PoB 248 per use against 887 mana (proxy). |

Not stated, and not filled in: how many Whirling Assault uses reach 5 charges,
how the first charges arise from 0 Combo, whether heralds, Wind Dancer, Ghost
Dance, Charged Staff, Pounce, Trinity, Remnants of Kalguur or the weapon swap
are pressed, what supplies Hit and Run's movement, and flask use. These are
`gap-p09-t011-rotation-details`, `gap-p09-t011-charge-cycle-rules` and
`gap-p09-t011-hit-and-run-movement`, and questions Q1 to Q6 below. The
rotation is stored as a record, not a `RotationPolicy`: writing predicates
would invent the missing details.

## Proposed class and ascendancy scope

Product scope is the owner's decision; this is a proposal
(`scope-proposal.json`).

Flicker Strike needs a Quarterstaff and 50 Dex / 50 Int at base (137 / 115 at
the seed's level 20, PoB-derived). The gem row names no class, and no catalog
character rule binds a gem or weapon to a class. Absence in PoB data is not
proof the game has no such rule.

| Status | Ascendancies |
|---|---|
| `evidenced_by_seed` | Monk / Martial Artist |
| `catalog_possible`, with a cited node naming charges or melee triggers | Huntress / Amazon (consuming a Charge triggers Elemental Surge), Monk / Invoker (Elemental Expression on Melee Critical Hit) |
| `catalog_possible` | Monk / Acolyte of Chayula; Ranger / Deadeye, Pathfinder; Huntress / Spirit Walker, Ritualist; Warrior / Titan, Warbringer, Smith of Kitava; Mercenary / Tactician, Witchhunter, Gemling Legionnaire; Druid / Oracle, Shaman; Witch / Infernalist, Blood Mage, Lich (its power charge node is Spell-only), Abyssal Lich; Sorceress / Stormweaver, Chronomancer, Disciple of Varashta |
| `excluded` | none: no evidence makes Flicker Strike unusable for any ascendancy |

Proposed first campaign: Monk / Martial Artist only, the one ascendancy with an
export. Every other ascendancy is reported as not searched until the owner adds
it (`gap-p09-t011-class-scope-decision`).

## Proposed interaction variants

Three variants, distinct by the event that grants the Power Charges Flicker
Strike consumes. All share Flicker Strike on a Quarterstaff, 2 extra strikes
per consumed charge, and no charge gain while it is used.

| Variant | Charge source | Required mechanics | Status | Benchmark applicability |
|---|---|---|---|---|
| `flk-var-combo-expend` | Combo expended by a Culmination-supported melee attack other than Flicker Strike, with Ailith's Chimes | Culmination II, Ailith's Chimes, a melee attack to carry them (seed: Whirling Assault) | `evidenced_by_seed` | No kill dependency in the text; usable in `flicker_sustained_v1` subject to `gap-p09-t011-charge-cycle-rules` |
| `flk-var-shock-consume` | Siphoning Strike consumes the target's Shock and grants a Power Charge | Siphoning Strike, plus a separate Shock source (Siphoning Strike has `never_shock`) | `catalog_only` | Needs a target that can be Shocked (`gap-p09-t011-benchmark-target`) |
| `flk-var-cull-kill` | Killing Palm kills or culls (below 10% life): 1 charge normal/magic, 2 rare, 3 unique | Killing Palm | `catalog_only` | Kill-dependent: D07 allows no kill events, so it supplies no charges in `flicker_sustained_v1` |

Not proposed: Perpetual Charge (changes consumption, not source), Charged
Staff (consumes charges), Power Siphon (same kill/cull event as the third
variant), Lingering Illusion (needs enemy damage on the copy), Devour and Wing
Blast (Wyvern shapeshift, compatibility with a Quarterstaff Flicker Strike not
checked). Only the first variant has an export (`gap-p09-t011-variant-exports`).

## The five workloads

| Scenario | Shape | Category | Selection criterion |
|---|---|---|---|
| `p09-flk-clear-dense` | `clear_dense` | clear | One named area whose packs stand close together |
| `p09-flk-clear-spread` | `clear_spread` | clear | One named area whose packs are spread along a route |
| `p09-flk-boss-short` | `boss_short` | boss | One named boss that stays targetable |
| `p09-flk-boss-sustained` | `boss_sustained` | boss | One named boss with phases or untargetable windows |
| `flicker_sustained_v1` | D07 benchmark | dps_benchmark | One non-dying, continuously targetable enemy |

No encounter is named yet (`gap-p09-t011-encounter-selection`, Q7).

### Initial state

All five start from the seed configuration
(`seed/export-as-imported.xml`). For the four workloads, the resource state
at the start event is unresolved (`gap-p09-t011-initial-resources`). For
`flicker_sustained_v1` this protocol proposes 0 Power Charges, 0 Combo,
energy shield and mana full: D07 forbids free maximum-state toggles, and zero
needs no unproven obtainability. It is a `protocol_choice` pending reviewer
acceptance.

### Legal preparation

The four workloads: one configuration across scenarios, no party buffs, no
outside resource generation, weapon-set changes allowed when represented and
timed (`docs/specs/product.md`). The benchmark: D07 counts preparation,
support actions and movement inside the 120 s window. Which seed buffs persist
into an encounter is `gap-p09-t011-preparation-allowance` (Q4).

### Survival pass conditions

Every workload carries two gates:

1. Event gate `/metrics/survival/deaths` `eq` `0`: a character death during
   the trial (death screen in a recording, death event in an evaluator).
   Definitional, from `scenarios.md`.
2. Numeric gate `/metrics/minimum_resources/energy_shield_fraction` `gte` T,
   with T unresolved (`gap-p09-t011-survival-threshold`). Energy shield, not
   life, because the seed runs Chaos Inoculation (maximum life 1).

### Resource pass conditions

`/metrics/minimum_resources/mana` `gte` `0` (an empty pool is downtime, not
illegality) and `/metrics/maximum_resources/power_charges` `lte` `5` (the
seed's maximum; a higher count is an evaluator error).

### Timeout

| Scenario | Limit | Basis |
|---|---|---|
| Four workloads | unresolved | `gap-p09-t011-duration-limit`: needs observed completion times |
| `flicker_sustained_v1` | 120.0 s fixed window | D07 item 2 |

A timeout is a failed evaluation, not an operational error. Recorded trials
are stochastic, so a minimum success fraction must be fixed before collection
(`gap-p09-t011-success-fraction`).

### Measurable completion events

| Scenario | Start event | Completion event |
|---|---|---|
| Clear workloads | First frame in the named area | The last declared target of the fixed workload dies; the clock includes movement, targeting, preparation and cleanup |
| Boss workloads | Encounter start in the arena | The named boss dies; the clock stops at the kill and includes only untargetable windows elapsed before it |
| `flicker_sustained_v1` | Scenario time zero with the stated initial state | t = 120 s; no kill or completion event |

Failure events everywhere: character death; for the four workloads also the
duration limit.

### `flicker_sustained_v1`

From D07 and `objectives.py` (`flicker_sustained_dps` v1): window [0, 120),
burst [0, 5) reported separately and never the most favourable segment, one
target, no adds, no kill events, sustained DPS = attributed damage in
[0, 120) / 120. Blocking and open: target identity, level and defenses
(`gap-p09-t011-benchmark-target`), how attributed damage is measured in game
(`gap-p09-t011-benchmark-measurement`), which seed damage sources count as
Flicker Strike (`gap-p09-t011-attribution-rules`), and whether the cycle
sustains (`gap-p09-t011-sustain-cycle`). P09-T02 cannot collect DPS
observations until the first two close.

## Field sourcing

`scenarios.json` holds every field with `basis`, `source`, `value` and
`gap_ids`. A null value always names a gap.

| Scenario | Fields | Unresolved (null) | Sourced from spec, D07, defaults, seed, catalog, owner | Protocol choice |
|---|---|---|---|---|
| each clear and boss workload | 33 | 16 | 17 | 0 |
| `flicker_sustained_v1` | 38 | 11 | 26 | 1 |

No field is a direct performance measurement. The seed export is the only
direct read, and it is configuration.

## Open gaps

25 `DataGap` records ship in `scenarios.json`: 21 blocking, 3 ranking
sensitive, 1 informational. Each states its own `needed_evidence` and
`collection_method`.

| Gap | Kind | Severity |
|---|---|---|
| `gap-p09-t011-encounter-selection` | missing_input | blocking |
| `gap-p09-t011-enemy-health` | missing_input | blocking |
| `gap-p09-t011-enemy-defenses` | missing_input | blocking |
| `gap-p09-t011-encounter-density` | missing_input | blocking |
| `gap-p09-t011-spatial-unit` | unresolved_entity | blocking |
| `gap-p09-t011-movement-model` | unsupported_rule | blocking |
| `gap-p09-t011-incoming-damage` | missing_input | blocking |
| `gap-p09-t011-boss-windows` | missing_input | blocking |
| `gap-p09-t011-duration-limit` | missing_input | blocking |
| `gap-p09-t011-success-fraction` | missing_input | blocking |
| `gap-p09-t011-reference-result` | missing_input | blocking |
| `gap-p09-t011-benchmark-target` | missing_input | blocking |
| `gap-p09-t011-benchmark-measurement` | unsupported_rule | blocking |
| `gap-p09-t011-attribution-rules` | unsupported_rule | blocking |
| `gap-p09-t011-rotation-details` | missing_input | blocking |
| `gap-p09-t011-charge-cycle-rules` | unsupported_rule | blocking |
| `gap-p09-t011-hit-and-run-movement` | unsupported_rule | blocking |
| `gap-p09-t011-sustain-cycle` | missing_input | blocking |
| `gap-p09-t011-patch-profile` | stale_patch | blocking |
| `gap-p09-t011-variant-exports` | missing_input | blocking |
| `gap-p09-t011-class-scope-decision` | missing_input | blocking |
| `gap-p09-t011-engine-checkout-state` | missing_input | informational |
| `gap-p09-t011-survival-threshold` | missing_input | ranking_sensitive |
| `gap-p09-t011-initial-resources` | missing_input | ranking_sensitive |
| `gap-p09-t011-preparation-allowance` | missing_input | ranking_sensitive |

## Questions for the owner

| Id | Question | Gaps |
|---|---|---|
| Q1 | After a Flicker Strike, how many Whirling Assault uses before the next Flicker Strike? Do you watch the charge counter reach 5, and what if it shows fewer? | rotation-details, charge-cycle-rules |
| Q2 | At fight start with no charges and no Combo, what do you press first? Does the first Whirling Assault already give charges? | rotation-details, charge-cycle-rules, initial-resources |
| Q3 | When do you press Charged Staff? It consumes all Power Charges. | rotation-details, attribution-rules |
| Q4 | Which of Herald of Ice, Herald of Thunder, Wind Dancer, Ghost Dance, Pounce, Trinity, Remnants of Kalguur, Sanguine Revelry (weapon swap), Quarterstaff Strike do you press in a boss fight, which stay on, which go unused? | rotation-details, preparation-allowance, attribution-rules |
| Q5 | Hit and Run needs 10 metres of movement before each Flicker Strike. What supplies it: Whirling Assault's advance, walking, dodge roll? | hit-and-run-movement, movement-model |
| Q6 | Do you use the mana flask in the cycle, and do you run out of mana? | sustain-cycle |
| Q7 | Two maps (packs close together; spread out) and two bosses (no breaks; phases or untargetable time), with tier or area level and modifiers. | encounter-selection |
| Q8 | Do you know an in-game enemy that does not die and stays targetable for 2 minutes? If not, the DPS benchmark stays blocked unless you approve a substitute. | benchmark-target |
| Q9 | Approve or change the scope: first campaign Monk / Martial Artist only, and the three variants. | class-scope-decision |

## Recordings that would close gaps

Video with the HUD legible (life/energy shield and mana globes, charge and
Combo counters), frame rate stated, every attempt kept including failures.
A recording closes only what it measures, and a reviewer accepts it.

| Recording | Closes | Does not close |
|---|---|---|
| 20 or more Whirling Assault to Flicker Strike cycles on one boss, counters legible | `charge-cycle-rules` (observed counts), `rotation-details` (with Q1 to Q6), `hit-and-run-movement`, `sustain-cycle` | anything about damage |
| Five or more attempts per named boss, start to kill | `boss-windows`, `duration-limit` for that boss, `initial-resources`, `incoming-damage` if the reviewer accepts a method separating damage from recovery | `enemy-health`, `enemy-defenses`: a health bar is a fraction of an unknown maximum |
| Five or more full runs per named clear area, route visible | `encounter-density` (counts), `movement-model` (leg times), `duration-limit` for that area | `spatial-unit`: screen distance has no conversion |
| One skill of known catalog radius used at two measured distances | `spatial-unit` | nothing else |
| Any of the above | a seed observation toward `reference-result` after protocol acceptance | the 12 configurations and three variant groups P09-T02 targets |

`enemy-health`, `enemy-defenses` and `benchmark-target` need catalog rows from
an accepted patch profile or a controlled experiment, not a recording.
`patch-profile` needs a P02-T02 re-export against an engine data release for
the live patch.

## How another operator repeats this

```
POB2_ROOT=<clean checkout of ce566ea> python scripts/p09_t01_1_mechanics.py   # optional, needs PoB
python scripts/p09_t01_1_flicker_suite.py
python -m pytest tests/unit/test_p09_t01_1_flicker_suite.py -q
```

The first command refuses a checkout that is not the pin or is dirty. The
second is offline and deterministic; it rewrites the seed manifest, scope
proposal, `scenarios.json`, `references.json` and `suite.json`. A changed
definition needs a new `suite_id`, not an edit in place.

To repeat the seed capture: import the character through the `pob2` MCP
server, then follow the call list in `seed/manifest.json`. A new capture is a
new seed; it does not replace this one.

## What this protocol refuses

It states no enemy statistic, encounter timing, threshold or completion time.
It fits no constant: `scenarios.md`'s 0.50 and 0.80 floors and P09-T03's
thresholds are carried over unchanged. It writes no `RotationPolicy` from a
one-sentence rotation. It freezes no reference result: the seed export begins
reference selection and closes no performance gap. It does not decide product
scope. `p09-synthetic-v1` and its reviews are untouched.
