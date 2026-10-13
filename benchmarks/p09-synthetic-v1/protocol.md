# Measurement protocol, suite `p09-synthetic-v1`

Task P09-T01. Specification version 1.0. Written 2026-10-10. Status: proposed,
not accepted.

This protocol defines two clearing workloads and two boss workloads in the four
shapes of `docs/specs/scenarios.md`, and states for every field of every
workload where its value comes from. It freezes the scenario definitions and
their hashes. It does not freeze a reference, because no reference build exists.

**Read this first.** Everything numeric in this suite is synthetic. No enemy
statistic, encounter timing, build family or threshold in it was measured, and
none may be cited as evidence about Path of Exile 2. A result produced on this
suite is not map clear speed and not boss kill time. The suite exists so P07 can
be built and tested before any encounter has been measured.

## What is frozen

| Artefact | Path |
|---|---|
| Scenario and rotation records, gaps, oracle | `tests/fixtures/combat/p09_synthetic_suite.v1.json` |
| Reference manifest and hashes | `benchmarks/p09-synthetic-v1/suite.json` |
| Field sourcing table | `docs/evidence/P09/protocol-fields.json` |
| Generator | `scripts/p09_t01_suite.py` |

`baseline_suite_hash` is `b1dcea97eb24842a60a680abd1ba67acec8b269454c67081c65f99fb35193e54`.
It is computed over four scenarios whose `reference_build_id` and
`reference_result_id` are both null, so it freezes the scenario definitions and
nothing else. Freezing a reference later changes that hash and starts a separate
leaderboard, which is what `docs/specs/scenarios.md` requires.

## The four workloads

| Scenario | Shape in `scenarios.md` | Category | What it isolates |
|---|---|---|---|
| `p09-syn-clear-dense` | `clear_dense` | clear | One cluster of 20 targets, no travel. |
| `p09-syn-clear-spread` | `clear_spread` | clear | The same total target health in four packs of 5, with three declared route legs between them. |
| `p09-syn-boss-short` | `boss_short` | boss | One target, continuously hittable, inside a short limit. |
| `p09-syn-boss-sustained` | `boss_sustained` | boss | Four times the health, and two windows in which the target cannot be hit. |

Both clear workloads carry the same 2000.0 total synthetic health, so a
difference between them is caused by cluster size and by the route and by
nothing else. The two boss workloads differ by health and by targetability, so a
difference between them is caused by sustained output and by the handling of
untargetable time.

### Initial state

Each workload starts the character at the origin on a `synthetic_grid` with zero
synthetic charges, and declares its route as a list of leg durations. The grid
unit converts to nothing: it is not metres, and it is not a PoB radius unit. The
real conversion is `gap-p09-t01-spatial-unit`.

The resource a character actually holds when an encounter begins is
`gap-p09-t01-initial-resources`. Zero charges here is a test constant chosen so
the boss rotation must build before it can spend.

### Legal preparation

`allowed_preparation` permits one action id, `synthetic_prepare`, within 5.0 s.
The shape comes from `docs/specs/product.md`: one gear, passive and gem
configuration across scenarios, no party buffs, no outside resource generation,
and in-game weapon-set changes allowed when represented and timed. The 5.0 s
limit is a test constant. Which pre-encounter actions persist into a real
encounter, and for how long, is `gap-p09-t01-preparation-allowance`.

### Survival pass condition

Every workload carries one survival gate: `/metrics/survival/deaths` `eq` `0.0`.
This is definitional, from `docs/specs/scenarios.md`: death and timeout are
failures, not missing trials to discard. It needs no measurement.

No other survival gate is stated. A minimum life or energy shield margin would
be a fitted threshold, and this suite applies no incoming damage at all, so a
margin gate over it would certify nothing. That is
`gap-p09-t01-survival-threshold`, and the damage input it depends on is
`gap-p09-t01-incoming-damage`.

### Resource pass condition

Every workload carries one resource gate:
`/metrics/minimum_resources/synthetic_charges` `gte` `0.0`. A pool that empties
is downtime, not illegality, and `scenarios.md` forbids an arbitrary minimum
uptime, so the only bound this task can state is that a pool never goes
negative. Any stricter bound is `gap-p09-t01-survival-threshold`.

### Timeout

| Scenario | `duration_limit_s` (the horizon) | Declared route over the horizon | Declared untargetable time over the horizon |
|---|---|---|---|
| `p09-syn-clear-dense` | 60.0 | 0.0 s | 0.0 s |
| `p09-syn-clear-spread` | 90.0 | 12.0 s | 0.0 s |
| `p09-syn-boss-short` | 60.0 | 0.0 s | 0.0 s |
| `p09-syn-boss-sustained` | 300.0 | 0.0 s | 30.0 s |

The last two columns describe the whole configured horizon. They are workload
metadata, not a lower bound on any single evaluation: none of that time has to
elapse before the target dies, and the sustained boss's first untargetable
window does not even begin until 60 s.

A timeout is a failed evaluation, which `scenarios.md` explicitly permits, and
not evidence that the evaluator is broken. A hypothetical build dealing one
damage per second cannot kill a 40,000 health target inside 300 s however
correct the evaluator is. An operational error is a different outcome and must
stay distinguishable from this one.

These limits are test constants. In a representative suite a limit decides
which builds are reported as failing, so setting one needs observed completion
times, which is `gap-p09-t01-duration-limit`.

### Measurable completion events

| Scenario | `completion_condition` | Event |
|---|---|---|
| Both clear workloads | `all_targets_dead` | Every declared target entity is dead. The clock runs from scenario start and includes movement, targeting, preparation and cleanup. |
| Both boss workloads | `target_dead` with the entity id | The single declared target is dead. The clock runs from scenario start to that moment and stops there, so it includes preparation and only the untargetable windows that elapse before the kill. A window later in the horizon is not part of a completed evaluation. |

### Worked completion times

Hand-calculated for `p09-syn-boss-sustained`, whose declared targetable windows
are [0, 60], [75, 150] and [165, 300] against 40,000 health. Each row applies a
hypothetical constant damage rate while the target is targetable. The rates are
invented and describe no build; the rows exist so that the difference between a
horizon total and an elapsed time is checkable rather than asserted. They are
carried in the suite's `oracle.worked_examples` and recomputed in
`tests/unit/test_p09_t01_scenarios.py`.

| Hypothetical damage/s | Completion | Untargetable time elapsed | Outcome |
|---|---|---|---|
| 2000 | 20.0 s | 0.0 s | completed inside the first window |
| 400 | 115.0 s | 15.0 s | completed after one window |
| 250 | 190.0 s | 30.0 s | completed after both windows |
| 1 | none | 30.0 s | timed out: a valid failed evaluation |

The first row is the case this protocol previously got wrong: the horizon's
30 s of untargetable time was described as a floor every boss evaluation had to
clear, and a kill at 20 s elapses none of it.

Both completion conditions are observable from the scenario state alone and
need no judgement call from an operator. `scenarios.md` requires exactly this: dense and spread measure
time to finish a fixed enemy and route workload; boss scenarios measure time
from scenario start to kill.

## Rotations

Two `RotationPolicy` records, both synthetic bounded priority lists over the v1
predicate vocabulary.

`p09-syn-rotation-clear`: use an area skill on a cluster of at least two living
targets; otherwise use a single-target skill while a living target is in range;
otherwise advance to the next route leg.

`p09-syn-rotation-boss`: spend when the target is targetable and at least three
synthetic charges are held; otherwise build while the target is targetable;
otherwise wait. The wait rule is the point of the boss suite: an evaluator that
keeps dealing damage through an untargetable window fails the oracle.

Costs and durations of the real skills these stand in for come from mechanic
rules that do not exist yet. The skill ids here are synthetic.

## Field sourcing

`docs/evidence/P09/protocol-fields.json` holds one row per `ScenarioSpec` field
with its basis and, where the field is unresolved for a representative suite,
the gaps that would have to close. Summarised:

| Basis | Fields |
|---|---|
| Specification source | `scenario_id`, `category`, `kind`, `spatial_model_id`, `completion_condition`, `capability_floor_ratio`, `validation_status`, and the shape of `survival_gates` and `resource_gates` |
| Product default | `version`, `rng_seeds`, and the shape of `allowed_preparation` |
| Declared synthetic test constant | every entity count, health, position, targetable window, event time, duration limit and preparation limit |
| Direct measurement | none. Nothing in this suite was measured |
| Unresolved input | 17 of the 26 rows, each naming at least one gap |

There is no direct measurement anywhere in this protocol. That is the honest
state of the inputs, not an omission.

A representative `ScenarioSpec` cannot be written today even as a skeleton:
`duration_limit_s`, `capability_floor_ratio` and the entity health fields are
required and non-nullable in `docs/specs/contracts.md`, so an unresolved value
cannot be stored as null in a scenario record. The unresolved inputs therefore
live in the field table and in the `DataGap` records instead of in a half-filled
scenario.

## Open gaps

Fourteen `DataGap` records ship inside the fixture. Eleven are `blocking`, three
are `ranking_sensitive`.

| Gap | Kind | Blocks |
|---|---|---|
| `gap-p09-t01-enemy-health` | missing_input | Any representative target entity |
| `gap-p09-t01-enemy-defenses` | missing_input | Time to kill |
| `gap-p09-t01-encounter-density` | missing_input | Both clear shapes |
| `gap-p09-t01-spatial-unit` | unresolved_entity | Comparing a distance with a skill's reach |
| `gap-p09-t01-movement-model` | unsupported_rule | The replayed route |
| `gap-p09-t01-incoming-damage` | missing_input | Every survival claim |
| `gap-p09-t01-boss-windows` | missing_input | Both boss shapes |
| `gap-p09-t01-initial-resources` | missing_input | The declared start state |
| `gap-p09-t01-preparation-allowance` | missing_input | Legal preparation |
| `gap-p09-t01-duration-limit` | missing_input | The timeout verdict |
| `gap-p09-t01-survival-threshold` | missing_input | Any gate stricter than deaths equal zero |
| `gap-p09-t01-reference-build` | missing_input | Every ratio in the ranking formula |
| `gap-p09-t01-build-families` | access_blocked | Selecting the three Huntress families |
| `gap-p09-t01-patch-profile` | missing_input | Naming a verified patch for a measurement |

Each record states its own `needed_evidence` and `collection_method`. Read them
there rather than paraphrasing this table.

## Build families: not selected

P09-T01 asks for three Huntress build families from the source corpus. There is
no source corpus. P03-T01 recorded, on 2026-10-10, that Mobalytics returns HTTP
403 to this client on every build path including its own terms page, that
Maxroll's `robots.txt` prohibits automated retrieval outright and names this
client's agent family in a disallow-all group, and that poe.ninja documents its
builds and profiles API as internal and not available for third-party use.

Naming three families now would mean inventing them. This protocol does not.
The selection stays open, and `gap-p09-t01-build-families` records what closing
it needs: either a corpus from a provider whose terms and client behaviour
permit retrieval, or a set of build files the owner exports by hand, each naming
the skills, supports and ascendancy its family depends on. One manually captured
build is enough to begin; three families are not needed before P07 can be built
against this suite.

The four workloads above are shapes, not family-specific encounters. They stay
valid whichever families are eventually selected, because nothing in them refers
to a skill, a support or an ascendancy.

## How another operator repeats this

```
python scripts/p09_t01_suite.py
python -m pytest tests/unit/test_p09_t01_scenarios.py tests/unit/test_p09_t01_protocol.py -q
```

The generator is deterministic and offline. It rewrites the three artefacts
above; the recorded SHA-256 in `suite.json` and in `tests/fixtures/manifest.json`
must not change unless the suite itself changed, in which case the suite needs a
new `suite_id` rather than an edit in place.

To run the suite against an evaluator, load the four `ScenarioSpec` records and
the two `RotationPolicy` records from the fixture, evaluate, and check the
result against the `oracle` block: total target health, route time, targetable
time and untargetable time. Nothing in that check is a claim about the game.

## What this protocol refuses

It states no enemy statistic, no encounter timing, no build family and no
threshold as if it were measured. It fits no constant: `scenarios.md`'s
provisional floors of 0.50 per scenario and 0.80 per category are carried over
unchanged, and P09-T01 proposes no replacement for them. It freezes no reference
result. It declares D04 blocked for practical claims rather than filling the
suite with plausible numbers; see `docs/decisions/D04-encounter-suite.md`.
