# Measurement protocol, suite `p09-flicker-v1`

Task P09-T01.1. Specification version 1.1. Written 2026-10-17, updated
2026-10-18 with the owner's answers and two owner decisions, and again on
2026-10-18 by P09-T01.2 (clean replay, rule table, Q10 answer). Status:
proposed, not accepted.

This protocol starts the Flicker Strike scope of D07 from one owner export,
the owner's rotation and the owner's answers. It defines two clear workloads,
two boss workloads and D07's `flicker_sustained_v1` benchmark, and states for
every field a source or the DataGap that has to close first. It records the
approved class and variant scope. It freezes definitions and hashes, and no
reference result.

**Read this first.** No enemy statistic, encounter timing, threshold or
completion time here was measured. The seed export is a configuration, not a
trial. Under the D07 amendment of 2026-10-18, PoB is the damage source for
`flicker_sustained_v1`. Under its amendment 2 (owner decision, same day) the
benchmark's method is `pob-community-v2`: community-style PoB per-use damage
with charges assumed, inside a time-accounted 120 s rotation. Its seed value
is computed below as evidence, not frozen as a reference, and is not a
supported score while sustain and attribution stay open. `pob-cycle-v1`
(generated charges) stays defined and uncomputed. PoB's displayed DPS stays
`proxy_only` and is reported beside. D04 stays blocked for practical claims about the clear and
boss workloads.

## What is frozen

| Artefact | Path | SHA-256 |
|---|---|---|
| Scenario definitions, rotation record, owner questions, DataGaps | `benchmarks/p09-flicker-v1/scenarios.json` | `0342553d85a2aa6a95131b0424074a499ba1f3afee38f8c04c7256124ba2ffba` |
| Reference manifest | `benchmarks/p09-flicker-v1/references.json` | `d063c88d22fffe495b05f7b509ad4ca691d6dfda369a83924282d40cd1cde4e8` |
| Suite manifest and hashes | `benchmarks/p09-flicker-v1/suite.json` | see the file |
| Seed export manifest, owner answers and decisions | `docs/evidence/P09-T01.1/seed/manifest.json` | `7ba0ec309f9c9454c28147cec8ddb744484a8749d68b922ab43da6fc31ba4866` |
| Approved scope | `docs/evidence/P09-T01.1/scope-proposal.json` | `60989673642d43489d9dd19368ab3c229cdcb4dac112da5d6e6580c4dad1b522` |
| Pinned engine data extract | `docs/evidence/P09-T01.1/mechanics.json` | `731127814c2bbe9b7ac3eeb46ab623a810fd4d5531bb9b74384fdece0cbe285b` |
| PoB outputs at 0 to 5 charges | `docs/evidence/P09-T01.1/pob-charge-table.json` | `55a210a331e40fe32b6bb34592d9a0dc424ff634a20b1ffad24419fcc6567701` |
| Community reference build (poe.ninja 25c49) | `docs/evidence/P09-T01.1/reference-ninja-25c49/` | `share-code.txt` `a51102cb6b54535cd2bf6d6861c8e00cae5712df7bcb6ec823b176ab7666ce7f`, `evaluation.json` `5cdc2c7596cdc5a2404bf4f2e2db2205b1d3286051fee39afa3a344fb7aac4b3` |

`suite_hash` is `92240e43c3b68f8bef8b64bb56e0e8103f136688cd76f0701610ed3f0b8030b5`.

| Scenario | `definition_hash` |
|---|---|
| `p09-flk-clear-dense` | `4b7d6696feb5a876ffc02de543e52201844e8027417467fe193bc20bd7d9e1b3` |
| `p09-flk-clear-spread` | `400cb3eaa2dccc212fd6743f25e94aaff8d95c3f35530901fd849efc7dea6a3c` |
| `p09-flk-boss-short` | `7411db3bac8aba1e638aacc5def95c429ae87ea6d61c1cc2debc0332130282da` |
| `p09-flk-boss-sustained` | `cac1917b7e94d5784fd8d19057fc591be2d943fcb55020291f0cd6b406afeae1` |
| `flicker_sustained_v1` | `f1d992cc851cc0430198b81f55ab420ce2d7840081e385d3ed128036323a7c58` |

Hashing follows `pob2opt/domain/identity.py`: files by SHA-256 of their raw
bytes, each scenario object by `content_hash` (canonical JSON), and the suite
by `content_hash` of the sorted definition hashes with their reference slots.
`scenario_hash` over a `ScenarioSpec` does not apply yet: required
non-nullable fields of the four workloads are unknown. Every reference slot
is null; freezing one changes `suite_hash`. The suite was never accepted, so
the 2026-10-18 update re-freezes it under the same `suite_id`.

## The seed export

Owner-supplied 2026-10-17: the owner's Forbidden Rites character, Monk /
Martial Artist, level 93, 116 passive points, imported from the account API
through the operator's `pob2` MCP server. Account-character import, which
D01 keeps separate from market access; no provider build source. The name is
recorded once, in the seed manifest.

Stored under `docs/evidence/P09-T01.1/seed/`: the PoB document as imported
(main skill Herald of Ice) and with Flicker Strike selected, the share code
(decodes to the first document byte for byte), raw item text, socket groups
with gem and granted-effect ids, allocated passive nodes, PoB config input,
PoB stats with Flicker Strike as main skill, and the manifest. The engine was
the operator's checkout at the pinned HEAD `ce566ea` with an unchecked working
tree. P09-T01.2 replayed it on a clean checkout of the pin through
`EngineAdapter`: all 734 outputs, the charge table, Whirling Assault and the
enemy agree exactly (`docs/evidence/P09-T01.2/replay.json`), which resolves
`gap-p09-t011-engine-checkout-state`.

Facts the export supplies (configuration only): Flicker Strike 20/23 with Hit
and Run, Concentrated Area, Close Combat II, Perpetual Charge, Rakiata's Flow;
Whirling Assault 18/20 with Living Lightning II, Culmination II, Ailith's
Chimes, Rage II, Oisin's Oath; rare Sinister Quarterstaff; Nettle Talisman in
weapon swap; Mageblood; maximum Power Charges 5 (base 3, Overflowing Power
+2); Chaos Inoculation, maximum life 1, energy shield 3902.

## Owner's rotation and answers

Rotation, verbatim, 2026-10-17:

> whirling assault to get 5 power charges & then flicker strike, rince and repeat

Answers, 2026-10-18 (verbatim where quoted; all in `seed/manifest.json`):

| Q | Answer | Recorded as |
|---|---|---|
| Q1 | "just 1" | One Whirling Assault use per Flicker Strike use |
| Q2 | "whirling assault" | Opener at 0 charges, 0 Combo |
| Q3 | "when i have a charge" | Charged Staff pressed with at least one charge; place in the cycle unresolved (Q10) |
| Q4 | Spirit skills always active; "I press pounce, but only for mobility" | Herald of Ice, Herald of Thunder, Wind Dancer, Ghost Dance, Trinity, Remnants of Kalguur persistent, not rotation actions; Pounce movement only |
| Q5 | "the dash from flicker itself" | Flicker Strike's teleport supplies Hit and Run's 10 metres; owner statement, unconfirmed by the catalog (blocking until activation is evidenced) |
| Q6 | "yes when i'm on a boss & my refund 2% mana on kill jewel doesnt see use" | Mana flask on bosses; mana on kill does nothing there |
| Q7 | T16 maps comfortably; struggles with "monsters have increased ailment threshold" | Clear workloads on T16 maps, one with that modifier; bosses not named |
| Q8 | "we damage calc with PoB, not ingame testing" | Decision 1: D07 amendment 2026-10-18 |
| Q9 | "any class, any ascendancy, any variant" | Decision 2: all 23 ascendancies and all three variants approved |
| Q10 | "Once per N cycles" | Charged Staff pressed once per N cycles to refresh its buff |
| Decision 3 | "it's obvious, whirling assault to generate charges, charged staff, whirling assault to generate charges, flicker, whirling, flicker, whirling, flicker, etc until charged runs out & repeat? but again, look at how those other PoBs did DPS calcs, don't stray from their methods, match them. Assume we have charges for flicker for the dps calcs" | D07 amendment 2026-10-18 (2): rotation fixed; method `pob-community-v2` below |

What the pinned engine data says about the parts of the cycle (citations are
`mechanic_id`s in `mechanics.json`):

| Part | Evidence |
|---|---|
| Power Charge source | Ailith's Chimes on Whirling Assault: "25% Surpassing chance to gain a Power Charge when expending Combo with Supported Skills per Combo expended" (`support/SupportAilithLineagePlayer`). Requires ComboStacking, which Culmination II adds. |
| Combo | Culmination II: Combo gained when striking with other melee attacks, up to 10, all expended on use, 6000 ms decay delay (`support/SupportCulminationPlayerTwo`). Martial Adept: an additional Combo per Combo gained; Martial Master: Combo from all Attack Hits (`passive/41751`, `passive/61586`). |
| Maximum charges | 5 (`passive/65204`). |
| Flicker Strike | Consumes Power Charges; 2 additional teleporting strikes per charge; no charge gain while used (`skill/FlickerStrikePlayer`, statdescs). PoB: AverageBurstHits = 1 + 2 x removable charges (`engine/removable-power-charges`). |
| Perpetual Charge | 25% chance to not remove Charges but still count as consuming them. |
| Hit and Run | Usable after moving 10 metres, unusable again after use, 40% more skill speed. |
| Charged Staff | Consumes all Power Charges, requires 1. In PoB its per-charge added lightning reads the same charges as Flicker Strike's strikes (`pob-charge-table.json`). |

## Approved scope

Owner decision 2026-10-18: "any class, any ascendancy, any variant". The
evidence statuses stay as found; the approval puts every row in scope
(`scope-proposal.json` `approval`, `in_approved_scope`).

| Evidence status | Ascendancies |
|---|---|
| `evidenced_by_seed` | Monk / Martial Artist |
| `catalog_possible`, with a cited node naming charges or melee triggers | Huntress / Amazon, Monk / Invoker |
| `catalog_possible` | the other 20 (Lich's power charge node is Spell-only) |
| `excluded` | none |

Flicker Strike needs a Quarterstaff and 50 Dex / 50 Int at base; no catalog row
binds the gem or weapon to a class.

| Variant | Charge source | Required mechanics | Evidence |
|---|---|---|---|
| `flk-var-combo-expend` | Combo expended by a Culmination-supported melee attack, Ailith's Chimes | Culmination II, Ailith's Chimes, a melee attack to carry them (seed: Whirling Assault) | seed |
| `flk-var-shock-consume` | Siphoning Strike consumes the target's Shock | Siphoning Strike plus a separate Shock source (it has `never_shock`); in the benchmark the Shock must be sustained, not toggled | catalog only |
| `flk-var-cull-kill` | Killing Palm kills or culls: 1, 2 or 3 charges by rarity | Killing Palm; supplies no charges in `flicker_sustained_v1` (no kill events) | catalog only |

Only the first variant has an export (`gap-p09-t011-variant-exports`).

## The five workloads

| Scenario | Shape | Category | Selection |
|---|---|---|---|
| `p09-flk-clear-dense` | `clear_dense` | clear | T16 map, packs close together, **with "monsters have increased ailment threshold"** (the owner's weak case; placing it on the dense shape is this protocol's choice) |
| `p09-flk-clear-spread` | `clear_spread` | clear | T16 map, packs spread along a route |
| `p09-flk-boss-short` | `boss_short` | boss | A boss that stays targetable. Proposed enemy configuration: PoB Guardian/Pinnacle Boss tier |
| `p09-flk-boss-sustained` | `boss_sustained` | boss | A boss with phases or untargetable windows. Proposed enemy configuration: PoB Uber Pinnacle Boss tier |
| `flicker_sustained_v1` | D07 benchmark | dps_benchmark | PoB calculation against the fixed Pinnacle preset |

PoB has no named PoE 2 boss preset: its boss skill presets are PoE 1 bosses
(Atziri, Shaper, Sirus, Cortex, Exarch, Eater, Maven; `engine/boss-skill-presets`)
and its PoE 2 enemy choices are the tiers Standard Boss, Guardian/Pinnacle
Boss and Uber Pinnacle Boss. The boss tiers above are proposals; map and boss
names stay open (`gap-p09-t011-encounter-selection`, Q11).

### Initial state

All five start from the seed configuration with the persistent Spirit skills
active (Q4). For the four workloads the resource state at the start event is
unresolved (`gap-p09-t011-initial-resources`). For `flicker_sustained_v1`:
0 Power Charges, 0 Combo, energy shield and mana full, a `protocol_choice`
pending reviewer acceptance (D07 forbids free maximum-state toggles).

### Legal preparation

The four workloads: one configuration across scenarios, no party buffs, no
outside resource generation, weapon-set changes allowed when represented and
timed (`docs/specs/product.md`). Spirit skills persistent; Pounce movement
only (Q4). The benchmark: preparation counts inside the window (D07 item 2).

### Survival pass conditions

The four workloads carry two gates:

1. Event gate `/metrics/survival/deaths` `eq` `0`: a character death during
   the trial (death screen in a recording, death event in an evaluator).
2. Numeric gate `/metrics/minimum_resources/energy_shield_fraction` `gte` T,
   T unresolved (`gap-p09-t011-survival-threshold`). Energy shield, because
   the seed runs Chaos Inoculation.

`flicker_sustained_v1` carries the death gate only: the PoB calculation has
no incoming damage (D07 amendment).

### Resource pass conditions

`/metrics/minimum_resources/mana` `gte` `0` and
`/metrics/maximum_resources/power_charges` `lte` `5`.

### Timeout

| Scenario | Limit | Basis |
|---|---|---|
| Four workloads | unresolved | `gap-p09-t011-duration-limit` |
| `flicker_sustained_v1` | 120.0 s fixed window | D07 item 2 |

A timeout is a failed evaluation, not an operational error. Recorded trials
need a minimum success fraction fixed before collection
(`gap-p09-t011-success-fraction`).

### Measurable completion events

| Scenario | Start event | Completion event |
|---|---|---|
| Clear workloads | First frame in the named area | The last declared target of the fixed workload dies; clock includes movement, targeting, preparation and cleanup |
| Boss workloads | Encounter start in the arena | The named boss dies; clock stops at the kill, includes only untargetable windows elapsed before it |
| `flicker_sustained_v1` | Scenario time zero with the stated initial state | t = 120 s; no kill or completion event |

## `flicker_sustained_v1`

Target (D07 amendment): PoB `enemyIsBoss = Pinnacle` (Guardian/Pinnacle
Boss), no boss skill preset, on engine `ce566ea`: level 82, fire, cold and
lightning resistance 50, chaos 0, armour 8063, evasion 1175 as PoB reads them
back (`engine/pinnacle-enemy-preset`, `pob-charge-table.json` `enemy`). Window
[0, 120), burst [0, 5), one target, no adds, no kill events. Condition inputs
in the seed's PoB config must be sustained by the build or switched off
(`gap-p09-t011-config-conditions`).

### How PoB computes Flicker Strike

`act_int.lua` `FlickerStrikePlayer` sets `base_skill_show_average_damage_instead_of_dps`
and, in `preDamageFunc`, `averageBurstHits = 1 + AdditionalFlickersPerPowerCharge`,
the latter being 2 per removable Power Charge. PoB outputs: AverageDamage
(per strike), AverageBurstHits, AverageBurstDamage (per use), Speed (strike
rate, with the skill's 285% more attack speed), TotalDPS = AverageDamage x
Speed, which ignores charge generation time.

Seed, Flicker Strike selected, imported config (`pob-charge-table.json`):

| Charges | AverageBurstHits | AverageDamage | AverageBurstDamage | Speed |
|---|---|---|---|---|
| 0 | 1 | 112,388.628 | 112,388.628 | 9.3279 |
| 1 | 3 | 126,632.067 | 379,896.200 | 9.3279 |
| 2 | 5 | 129,033.877 | 645,169.387 | 9.3279 |
| 3 | 7 | 131,433.321 | 920,033.250 | 9.3279 |
| 4 | 9 | 133,830.398 | 1,204,473.586 | 9.3279 |
| 5 | 11 | 136,232.222 | 1,498,554.438 | 9.3279 |

With Charged Staff disabled, per-strike AverageDamage is 124,231.438 at both 1
and 5 charges: PoB adds Charged Staff's per-charge buff from the same charges
(`gap-p09-t011-charged-staff-shared-charges`). Whirling Assault (group 8):
Speed 0.769368 uses/s, Time 1.299768 s, ManaCost 160.

Community reference (poe.ninja 25c49, community build, not a measurement):
Monk / Martial Artist level 98, headline Falling Thunder (CombinedDPS
134,981,934 on our engine; the coordinator reports about 127M on poe.ninja).
With Flicker Strike selected: AverageBurstDamage 9,253,368, AverageBurstHits
17 (8 removable charges from 7 forced above a maximum of 6), AverageDamage
544,316, Speed 9.9158, TotalDPS 5,397,326, with forced Combo 10, Rage 30,
Onslaught and enemy conditions. The coordinator reports 14 tree nodes missing
on the pin; not re-checked here, so values may differ from poe.ninja's. That
method is burst per use at forced charges.

### Method `pob-cycle-v1`

Inputs, each traced:

| Input | Meaning | Source | Seed value |
|---|---|---|---|
| t_WA | seconds per Whirling Assault use | PoB Time, group 8 | 1.299768 |
| S_F(c) | Flicker strikes per second at c charges | PoB Speed, group 6 | 9.3279 at 0 to 5 |
| H(c) | strikes per Flicker use | PoB AverageBurstHits = 1 + 2c | 1 to 11 |
| D(c) | damage per Flicker use | PoB AverageBurstDamage at c forced charges | table above; which table is the shared-charge gap |
| C_max | maximum charges | PoB PowerChargesMax | 5 |
| p | charge chance per Combo expended | Ailith's Chimes 25, Surpassing | 0.25 |
| K_max | Combo cap | Culmination II 10 | 10 |
| q | chance a consumed charge is kept | Perpetual Charge 25 | 0.25 |
| g | Combo gained by Whirling Assault per Flicker strike and per own hit | unknown | `gap-p09-t011-charge-cycle-rules` |
| m_F, m_WA | mana per use | PoB ManaCost | 248, 160 |

Procedure:

1. t = 0: 0 Power Charges, 0 Combo, persistent Spirit skills active, energy
   shield and mana full.
2. Cycle k = 1, 2, ...: one Whirling Assault use lasting t_WA, then one Flicker
   Strike use (Q1, Q2). Charged Staff's place is unresolved (Q10); no value is
   computed until it closes.
3. At Whirling Assault use k: Combo K_k = min(K_max, Combo gained since the
   previous Whirling Assault use, per g). It is expended; charges gained follow
   Ailith's Chimes, expected p x K_k, with the distribution the Surpassing rule
   gives. Charges held C_k = min(C_max, carried + gained). No charge is gained
   during the Flicker Strike use.
4. Flicker Strike use k performs H(C_k) strikes, each lasting 1 / S_F(C_k)
   (`gap-p09-t011-flicker-strike-timing`). D(C_k) is credited in equal parts at
   each strike's end. Over a charge distribution, E[D] = sum over c of
   P(C_k = c) x D(c); D is never interpolated between charge counts.
5. Carry into cycle k + 1: each consumed charge kept with probability q,
   capped at C_max.
6. flicker_sustained_dps = credited damage with strike end in [0, 120) / 120;
   flicker_burst_dps = credited damage with strike end in [0, 5) / 5. Only
   completed strikes count.
7. Report mana per use against maximum mana and regeneration, flask use
   (`gap-p09-t011-sustain-cycle`), and whether the cycle reaches a repeating
   charge state.
8. Whirling Assault's own damage and every other skill's damage are reported
   separately, never in the score.

Status: defined, not computed. Blocking: charge-cycle rules, Charged Staff
shared charges, config conditions, mana sustain and Flicker Strike's mana
charging, Hit and Run activation/reuse, and damage attribution. The
clean-engine rerun, the rotation and the Charged Staff period are resolved
and stay listed as met prerequisites. Under D07 amendment 2 this method is
the generated-charge alternative; the benchmark's method is
`pob-community-v2`.
`docs/evidence/P09-T01.2/mechanics-rules.json` holds the rule table: each
rule resolved, conditional (alternatives written out) or blocking, with
citations into the pinned engine. The method's
`required_gap_ids` enumerates these prerequisites; they also appear in the
measurement field's `gap_ids`. Resolving every other gap does not permit a
score while either activation or attribution remains unresolved.

Before the first and every subsequent Flicker Strike use, establish the
activation condition. If teleport does not re-enable Hit and Run, provide an
evidenced movement action and count its time, or retain a blocking gap. An
owner statement alone does not establish the mechanic. Unassigned secondary
damage cannot enter D(c) or the score. PoB damage acceptance and optional
recordings do not waive either prerequisite. This is a protocol contract;
P06/P07 must implement its enforcement before computing a result.

### Method `pob-community-v2` (owner decision, D07 amendment 2)

Per-use Flicker Strike damage is PoB's own output at the build's maximum
Power Charges with the Charged Staff buff as PoB applies it; charges for
Flicker Strike are assumed, as community PoB builds assume them. Hit and Run
is taken as PoB applies it. These are the owner's chosen method, not
verified game mechanics.

1. Rotation: Whirling Assault, Charged Staff (consumes 5 charges), then
   Whirling Assault and Flicker Strike repeated until the buff expires, then
   again. Buff: 6 s per stack x 1.25 (PoB's increased duration on the seed)
   x 5 = 37.5 s.
2. Time: PoB Time of Whirling Assault (1.2998 s) and Charged Staff
   (0.3181 s); a Flicker Strike use is 11 strikes at 1 / Speed.
3. Damage: each strike is credited PoB AverageDamage at its end, with the
   buff value while the buff lasts and the Charged Staff disabled value
   after. Sustained = strikes ending in [0, 120) / 120; burst = [0, 5) / 5.
4. Reported beside: PoB AverageBurstDamage and TotalDPS at maximum charges;
   the community reference's condition inputs applied to the seed; the
   Pounce-off document; a mana ledger.

Computed in `docs/evidence/P09-T01.2/community-cycle.json`
(`python scripts/p09_t01_2_community_cycle.py`), not frozen as a reference:

| Seed document | Sustained | Burst | PoB TotalDPS (plain) | PoB per use |
|---|---|---|---|---|
| As imported (owner's PoB) | 572,246 | 299,711 | 1,270,761 | 1,498,554 |
| Pounce off | 461,488 | 241,702 | 1,024,807 | 1,208,512 |

Waived by the decision: `charge-cycle-rules`, `charged-staff-shared-charges`,
`hit-and-run-movement`. Still blocking a supported score: `sustain-cycle`
(the schedule needs 19,540 mana in 120 s against a 887 pool and 5,748 regenerated;
the first unaffordable action is at 7.9 s without a flask),
`flicker-mana-charging`, `attribution-rules` (proposed table, not accepted),
`config-conditions` (Pounce's Predator's Mark is in the owner's PoB).

## Field sourcing

`scenarios.json` holds every field with `basis`, `source`, `value` and
`gap_ids`. A null value always names a gap.

| Scenario | Fields | Unresolved (null) | Protocol choice | Other sourced |
|---|---|---|---|---|
| each clear workload | 33 | 15 | 0 | 18 |
| each boss workload | 33 | 15 | 1 | 17 |
| `flicker_sustained_v1` | 43 | 3 | 2 | 38 |

No field is a gameplay measurement.

## Gaps

30 `DataGap` records ship in `scenarios.json`. Resolved (7):
`benchmark-target` and `benchmark-measurement` (D07 amendment),
`class-scope-decision` (Q9), `preparation-allowance` (Q4),
`engine-checkout-state` (P09-T01.2 replay), `rotation-details` and
`charged-staff-period` (Q10 and D07 amendment 2). Open (23): 20 blocking, 3
ranking sensitive, 0 informational.

| Gap | Kind | Severity | Status |
|---|---|---|---|
| `gap-p09-t011-encounter-selection` | missing_input | blocking | open |
| `gap-p09-t011-enemy-health` | missing_input | blocking | open |
| `gap-p09-t011-enemy-defenses` | missing_input | blocking | open |
| `gap-p09-t011-encounter-density` | missing_input | blocking | open |
| `gap-p09-t011-spatial-unit` | unresolved_entity | blocking | open |
| `gap-p09-t011-movement-model` | unsupported_rule | blocking | open |
| `gap-p09-t011-incoming-damage` | missing_input | blocking | open |
| `gap-p09-t011-boss-windows` | missing_input | blocking | open |
| `gap-p09-t011-duration-limit` | missing_input | blocking | open |
| `gap-p09-t011-success-fraction` | missing_input | blocking | open |
| `gap-p09-t011-reference-result` | missing_input | blocking | open |
| `gap-p09-t011-rotation-details` | missing_input | blocking | resolved |
| `gap-p09-t011-charge-cycle-rules` | unsupported_rule | blocking | open |
| `gap-p09-t011-charged-staff-shared-charges` | unsupported_rule | blocking | open |
| `gap-p09-t011-sustain-cycle` | missing_input | blocking | open |
| `gap-p09-t011-config-conditions` | unsupported_rule | blocking | open |
| `gap-p09-t011-patch-profile` | stale_patch | blocking | open |
| `gap-p09-t011-engine-checkout-state` | missing_input | blocking | resolved |
| `gap-p09-t011-variant-exports` | missing_input | blocking | open |
| `gap-p09-t011-attribution-rules` | unsupported_rule | blocking | open |
| `gap-p09-t011-flicker-strike-timing` | unvalidated_prediction | ranking_sensitive | open |
| `gap-p09-t011-survival-threshold` | missing_input | ranking_sensitive | open |
| `gap-p09-t011-initial-resources` | missing_input | ranking_sensitive | open |
| `gap-p09-t011-hit-and-run-movement` | unsupported_rule | blocking | open |
| `gap-p09-t012-charged-staff-period` | missing_input | blocking | resolved |
| `gap-p09-t012-flicker-mana-charging` | unsupported_rule | blocking | open |
| `gap-p09-t011-benchmark-target` | missing_input | blocking | resolved |
| `gap-p09-t011-benchmark-measurement` | unsupported_rule | blocking | resolved |
| `gap-p09-t011-class-scope-decision` | missing_input | blocking | resolved |
| `gap-p09-t011-preparation-allowance` | missing_input | ranking_sensitive | resolved |

## Open questions for the owner

| Id | Question | Gaps |
|---|---|---|
| Q11 | Which T16 maps (packs close together; spread out) and which two bosses (no breaks; phases or untargetable time)? Are PoB's Pinnacle and Uber tiers acceptable enemy configurations for them? | encounter-selection |

## Recordings (optional for the DPS benchmark)

Under the D07 amendment, recordings validate but do not gate
`flicker_sustained_v1`. They are still the evidence the four clear and boss
workloads need. Video with the HUD legible, frame rate stated, every attempt
kept. A recording closes only what it measures, and a reviewer accepts it.

| Recording | Closes | Does not close |
|---|---|---|
| 20 or more Whirling Assault to Flicker Strike cycles, Combo and charge counters legible | evidence toward `charge-cycle-rules`, `flicker-strike-timing`, `hit-and-run-movement`, `sustain-cycle` | damage values |
| Five or more attempts per named boss, start to kill | `boss-windows`, `duration-limit` for that boss, `initial-resources`; `incoming-damage` with an accepted method | `enemy-health`, `enemy-defenses` |
| Five or more full runs per named T16 map, route visible | `encounter-density`, `movement-model`, `duration-limit` for that map | `spatial-unit` |
| One skill of known catalog radius at two measured distances | `spatial-unit` | nothing else |

## How another operator repeats this

```
POB2_ROOT=<clean checkout of ce566ea> python scripts/p09_t01_1_mechanics.py   # optional, needs PoB
python scripts/p09_t01_1_flicker_suite.py
python -m pytest tests/unit/test_p09_t01_1_flicker_suite.py -q
POB2_ROOT=<clean checkout of ce566ea> python scripts/p09_t01_2_seed_replay.py   # needs PoB
POB2_ROOT=<clean checkout of ce566ea> python scripts/p09_t01_2_mechanics_rules.py
python scripts/p09_t01_2_community_cycle.py
python -m pytest tests/unit/test_p09_t01_2_seed_replay.py -q
```

The extract refuses an unpinned or dirty checkout. The generator is offline
and deterministic. The PoB charge table is captured by the procedure in
`pob-charge-table.json` through the `pob2` MCP server; the seed capture by the
call list in `seed/manifest.json`.

## What this protocol refuses

It states no enemy statistic, encounter timing, threshold or completion time
for the clear and boss workloads. It fits no constant. It computes no
`pob-cycle-v1` value while the charge-cycle rules are unknown. Under D07
amendment 2 it forces only Power Charges at the build's maximum and the
Charged Staff buff, as the owner's method; forced Combo and other toggled
conditions are reported, never scored. It freezes
no reference result. `p09-synthetic-v1` and its reviews are untouched.
