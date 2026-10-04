# Concrete acceptance examples

These examples specify expected behavior for future tests. All numbers and item/skill names in this document are synthetic. They are not PoE 2 mechanics claims. Implement them with small test doubles where appropriate; actual engine/provider acceptance still requires its own evidence.

## Example 1 Balanced scoring

Reference completion times are `[100, 100, 100, 100]` seconds, ordered dense clear, spread clear, short boss, sustained boss. Assume all legality, coverage and survival gates pass.

| Candidate times | Scenario ratios | C | B | S | Outcome |
|---|---|---|---|---|---|
| `[100,100,100,100]` | `[1,1,1,1]` | 1 | 1 | 1 | Eligible, balanced |
| `[50,50,100,100]` | `[2,2,1,1]` | 2 | 1 | 1.4142135623730951 | Eligible, clear focused |
| `[200,200,50,50]` | `[0.5,0.5,2,2]` | 0.5 | 2 | 1 | Ineligible because C is below 0.8 |
| `[250,25,100,100]` | `[0.4,4,1,1]` | 1.2649110640673518 | 1 | 1.1246826503806981 | Ineligible because one scenario ratio is below 0.5 |
| `[100,100,null,100]` | Unresolved | null | null | null | Missing required evaluation; no aggregate ranking |

Use `1e-9` numerical tolerance in this synthetic fixture. Even with all ratios at one, changing survival to fail must make the candidate ineligible. Do not recalculate reference times when adding a stronger candidate.

## Example 2 Setup time cannot disappear

There is one stationary immortal target, no defenses, unlimited resources and no other damage. A main action deals 100 damage at the end of its one-second cast. The scenario lasts ten seconds and processes impacts at exactly the final timestamp.

- Policy A casts the main action repeatedly: ten impacts, 1,000 damage, 100 average DPS.
- Policy B alternates a one-second zero-damage preparation action and the same one-second main action: five impacts, 500 damage, 50 average DPS.
- Setting an unrelated enemy flag that does not affect either action must leave Policy B at 50 DPS. A code path that returns 100 has dropped setup time.

This is a timing fixture, not a recommendation scenario: the immortal target cannot satisfy a kill completion condition.

## Example 3 Resource starvation is downtime

Initial resource is 10. Main action spends 10 at cast start, deals 100 at the end of a one-second cast, and resource regenerates continuously at 5 per second up to 10. Policy uses the action as soon as it can pay; no other effects. In five seconds, casts start at t=0,2,4 and impacts occur at t=1,3,5. Expected damage is 300, not 500. Record two seconds of waiting caused by resources. A zero-regeneration variant has only the first impact and four seconds of waiting.

## Example 4 Coordinated search escapes a greedy trap

A finite legal configuration has two optional binary choices A and B. All other legality/scenario gates pass. Define balanced score by an exact lookup table:

| A | B | Score |
|---|---|---|
| absent | absent | 100 |
| present | absent | 90 |
| absent | present | 90 |
| present | present | 200 |

Complete enumeration proves the optimum is 200 in this four-candidate fixture. A strict one-change improving search starting at neither choice stops at 100. The coordinated-mutation search must propose and evaluate both present. On this fixture require success for each of the 20 recorded seeds; its tiny state space should not require a probabilistic pass criterion.

## Example 5 Unlimited budget and item identity

Create three imported synthetic listings:

| Listing ID | Display name | Damage property | Price |
|---|---|---|---|
| L1 | Shared Name | 100 | 5 exalted |
| L2 | Shared Name | 200 | 1000 divine |
| L3 | Shared Name | 200 | unknown |

Expected: all three listings survive unlimited-budget import. L1 and L2 have different item hashes. If every other gameplay property matches, L2 and L3 share an item hash but remain distinct listings. Missing price stays null. No price conversion is needed to retain or evaluate them. One physical L2 item cannot fill two item slots at once.

## Example 6 Missing rules cannot become neutral multipliers

A candidate uses a parsed modifier `Synthetic trigger repeats X`. The catalog resolves the item, but the mechanics registry has no repeat rule. Legality may still be legal, while coverage is unsupported. Required result: `DataGap(kind=unsupported_rule)` naming the modifier and affected action; no comparable production score. Do not assume one repeat, zero repeats or multiplier one. A parser recognizing the words is not mechanics support.

## Example 7 Imported variants remain separate

A saved guide has variant V1 with passive IDs `[1,2]` and item L1, and V2 with IDs `[1,3]` and item L2. Expected: two BuildSpecs with distinct variant IDs/hashes and one shared source reference. No result may contain V1's tree and V2's gear unless the optimizer deliberately creates and records that mutation later.

## Example 8 Cache and recovery

Evaluate candidate H under scenario S, registry R, engine E and calibration K. Rename H's display title: cache hit. Change its item roll: miss. Keep H but change R, E, K or S: miss. Change only listing price: combat cache hit, refreshed report acquisition metadata.

Then interrupt after the database commits task T but before checkpoint replacement. Resume must reuse T's completed result once and dispatch only pending tasks. An engine timeout is a failed attempt, not a completed zero-score evaluation.

## Example 9 Market refresh distinguishes failure from absence

Refresh L1, L2 and L3. Provider returns explicit missing for L1, a successful observed listing for L2, and a timeout for L3. Expected availability: unavailable, rechecked, unknown respectively. A build requiring all three cannot be labelled verified at the final snapshot. Keep L3's last known item properties without claiming it was sold.

## Example 10 Correlated evidence is not independent validation

Import a guide claiming 1,000 DPS, a poe.ninja record whose 1,000 DPS was calculated by PoB, and a local PoB calculation of 1,000 DPS. Expected: three linked claims/calculation records, zero independent gameplay observations. Agreement does not advance the mechanic to gameplay-checked status. Five manually timed trials with full build/scenario context can be proposed as observations for reviewer acceptance.

## Example 11 Rank-sensitive uncertainty

Candidate A scores 1.1 when a supported assumption has value X and 0.8 when it has value Y. Candidate B scores 1.0 under both. X and Y are both supported by plausible but conflicting evidence. Expected: mark A versus B ranking unresolved/conditional, create a ranking-sensitive gap and describe the measurement that distinguishes X from Y. Do not select A as unconditionally superior or interpret `[0.8,1.1]` as a confidence interval.

## Example 12 Fresh export verification

Evaluate candidate A, export it, start a fresh worker and reimport the export. Compare all required gameplay fields and deterministic primitive metrics. If a modifier category is lost while a main DPS number happens to stay equal, round-trip acceptance still fails. Numerical coincidence cannot substitute for semantic fidelity.

## Request file example

[request.offline.json](examples/request.offline.json) shows a complete target RunRequest using product defaults and explicit paths. IDs and paths are illustrative and must be replaced by actual accepted artifacts. It is not an executable demo today; P10 delivers that demo after implementation. It selects offline items deliberately, so it does not imply that live trade integration is complete.
