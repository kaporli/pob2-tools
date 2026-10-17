# D04 Encounter suite and credible measurements

> **Current scope update, 2026-10-17:** [D07](D07-flicker-strike-objective.md) replaces the initial Huntress/three-Huntress-family target with sustained Flicker Strike DPS and a reviewed class/interaction scope. The historical investigation below and accepted `p09-synthetic-v1` artifacts retain their original wording/hashes. Their synthetic software acceptance remains valid; they do not establish the new objective. The next collection input is one complete **Flicker Strike** export with its actual rotation, followed by representative encounter and controlled-DPS evidence under P09-T01.1. Missing measurements, reference results and patch compatibility remain open; this scope change closes none of those gaps. See the [current ledger](../specs/delivery.md#current-task-ledger).

> **P09-T01.1, 2026-10-17:** the seed Flicker Strike export (Monk / Martial Artist) and the owner's one-sentence rotation are stored in `docs/evidence/P09-T01.1/`. Suite `benchmarks/p09-flicker-v1/` proposes the class scope, three interaction variants, the four workloads and `flicker_sustained_v1`, with 25 open `DataGap` records. The export begins reference selection and closes no measurement gap. No encounter, enemy statistic, benchmark target or threshold is selected, so D04 stays blocked for practical claims. Proposed, not accepted.

Raised by: P09-T01. Specification version 1.0.

## Question

Which encounters does this project measure performance against, and what counts
as a credible measurement of a build's performance in them? `docs/specs/scenarios.md`
fixes the four shapes and the ranking formula and defers the actual PoE 2
encounter data to P09. D04 is that deferred choice: the named encounters, their
enemy statistics, their timings, the reference builds and the pass conditions.

## Sources consulted

| Source | What was read |
|---|---|
| `docs/specs/scenarios.md` | The four shapes, the ranking formula, the provisional floors, the rule that synthetic results are never reported as measured times |
| `docs/specs/product.md` | The solo softcore default, one configuration across scenarios, no party buffs, no complexity penalty, and the four no-value behaviours |
| `docs/specs/contracts.md` | `ScenarioSpec`, `RotationPolicy`, `Observation`, `DataGap` and their nullability rules |
| `docs/specs/projects/P09-validation.md` | P09-T01 through P09-T05, including the instruction not to invent enemy statistics |
| `docs/evidence/P03/mobalytics-capabilities.json` (branch `p03-t01-capabilities`) | Capability manifest, 2026-10-10 |
| `docs/evidence/P03/maxroll-capabilities.json` (same branch) | Capability manifest, 2026-10-10 |
| `docs/evidence/P03/poe-ninja-capabilities.json` (same branch) | Capability manifest, 2026-10-10 |
| `docs/evidence/P00/findings.md`, `tests/fixtures/` | The existing synthetic fixtures and what they are allowed to establish |
| `docs/evidence/P02/catalog-export.json` | The one exported patch profile, whose compatibility is `partial` |

No provider was contacted by this task, and no acquisition was attempted. P03
owns that and it is blocked.

## What was observed

**There is no source corpus.** P03-T01 recorded on 2026-10-10 that Mobalytics
returned HTTP 403 to this client on every requested path, including its listing,
one guide, its sitemap and its own terms page, so no guide content and no build
file was retrieved and no term about automated access was read. Maxroll's
`robots.txt` carries a header prohibiting automated retrieval without written
permission and a disallow-all group naming roughly two hundred automation
agents, including this client's agent family; after reading it, no further
request was made. poe.ninja serves no `robots.txt` and states in its own API
reference that the builds and profiles API is internal, undocumented,
unsupported and not available for third-party use, with player privacy given as
one of the reasons; its builds page returns a navigation shell with no character
rows in the server response.

**There are no measured encounters.** No PoE 2 monster life, resistance, armour,
evasion or ailment threshold is held anywhere in this repository. No pack size,
pack spacing, route time, boss phase timing, invulnerability window, incoming
damage event or completion time has been recorded. `docs/evidence/P00/findings.md`
and `tests/fixtures/` contain synthetic fixtures only, and every one of them is
labelled as such.

**There is no reference build.** `docs/specs/scenarios.md` requires one approved
reference build and result per scenario, and every ratio in the ranking formula
divides by that reference time. No legal complete build exists here, so every
`reference_build_id` and `reference_result_id` is null.

**There is no verified patch profile.** The one profile P02-T02 exported reports
compatibility `partial`.

**The distance unit is unresolved.** `contracts.md` forbids assuming a PoB
radius is metres, and no conversion evidence exists, so no scenario distance can
yet be compared with a skill's reach.

## Proposed choice

**D04 is blocked for practical claims.** Specifically:

1. Adopt `p09-synthetic-v1` (`benchmarks/p09-synthetic-v1/protocol.md`) as the
   software-testing suite. It implements the four shapes with declared synthetic
   test constants and frozen hashes, so P07 can be built and tested now. Its
   `kind` is `synthetic` and its `validation_status` is `untested`.
2. Select no encounters, no enemy statistics, no timings and no reference builds
   for a representative suite. Those stay unresolved inputs with the fourteen
   `DataGap` records shipped in
   `tests/fixtures/combat/p09_synthetic_suite.v1.json`.
3. Select no Huntress build families. P09-T01 was asked for three from the
   source corpus; there is no corpus, and inventing three would be the exact
   failure this task exists to prevent.
4. Fit no constant. The floors of `scenarios.md` (0.50 per scenario, 0.80 per
   category) and the thresholds of P09-T03 (15% median, 30% at the 90th
   percentile) stand unchanged as provisional product settings. P09-T01 proposes
   no replacement and no calibration.
5. Any evaluation run on `p09-synthetic-v1` carries
   `validation: synthetic_only` and is never reported as clear speed or kill
   time. Per `docs/specs/product.md`, insufficient independent validation means
   `model_estimate` or `proxy_only`, never validated practical superiority.

This is a proposal. It is not accepted, and P09-T01 does not accept it.

## What would unblock it, and who can supply it

Two inputs, in this order. The first is small and the owner can supply it
alone; the second is the real cost.

Each input below is described by what it actually measures. An artifact closes
a gap only when it carries the quantity, in a stated unit, with the context the
gap names, and a reviewer accepts it. "Supplying a build" and "closing the
reference gap" are two different events, and an earlier version of this record
ran them together.

**1. One complete Huntress build, exported by hand.** A PoB build file or build
code carrying equipment with full modifier text, passive allocations,
ascendancy, skill groups with levels, quality and supports, weapon-set
bindings, and the rotation the operator plays. Imported through P03-T02 local
acquisition, with no provider access.

| Gap | What this closes | What it does not |
|---|---|---|
| `gap-p09-t01-reference-build` | **Begins** reference selection: it supplies a complete, importable configuration, which is the first of the two things the gap asks for. | It does not close the gap. The gap also requires an observed completion time for that configuration on the scenario, and an export contains no trial. A reference result is frozen by an accepted configuration plus an accepted observation, never by an export alone. |
| `gap-p09-t01-build-families` | Nothing on its own. | One build does not name a family. Three builds across three distinct families, each accepted, would close it. |

**2. Recorded gameplay for one named encounter.** For a single named boss and a
single named map layout, at a stated area level and patch. What a recording can
support depends on what is legible in it, so the gaps are listed separately
rather than as a block:

| Gap | Artifact and extractable quantity | Required context | Uncertainty | Accepted when |
|---|---|---|---|---|
| `gap-p09-t01-boss-windows` | Phase and invulnerability start and end times, read off the recording's clock in seconds | Named boss, area level, patch, at least five attempts | Frame rate and the operator's reaction time bound the precision; state it | A reviewer accepts the attempt set and the stated precision |
| `gap-p09-t01-duration-limit` | Completion time per attempt, including the failures | The same | As above | The same |
| `gap-p09-t01-movement-model` | Per-leg walked route times | Named map layout, the route walked, movement speed and movement skills used | As above | The same |
| `gap-p09-t01-encounter-density` | Pack size and spacing along that route | The same | Spacing is in whatever unit the recording permits; see the spatial gap | The same |
| `gap-p09-t01-incoming-damage` | Timestamped damage events | Named encounter and patch; the character's maximum/current life and energy shield, mitigation, recovery and other simultaneous resource changes | A fractional character health bar needs a known maximum; net loss alone cannot separate damage, absorption and recovery | A reviewer accepts the character resource context and a method isolating the damage quantity; enemy maximum life is not this prerequisite |
| `gap-p09-t01-initial-resources` | The resource state at the start event | The same | Legibility of the resource display | A reviewer accepts the reading |
| `gap-p09-t01-enemy-health` | **Not closed by a health bar.** A bar shows a fraction of an unknown maximum | Absolute maximum life needs an identified catalog row for that monster at that area level and rarity, or a controlled experiment with a known damage figure | Identification of the catalog row is the uncertainty | A reviewer accepts the catalog row or the experiment |
| `gap-p09-t01-enemy-defenses` | **Not closed by a recording.** Mitigation is not visible | As above | As above | As above |
| `gap-p09-t01-spatial-unit` | **Not closed by a recording.** Positions are in screen or minimap space | The conversion between that space and the game's units needs its own identified evidence | The conversion factor is the unknown | A reviewer accepts the conversion |

A recording that shows boss timings but no spatial conversion closes the timing
gaps and leaves the spatial one open. A recording with a legible fractional
health bar and no absolute-life evidence closes neither
`gap-p09-t01-enemy-health` nor `gap-p09-t01-incoming-damage`. None of these may
be reported as satisfying the four-scenario, multi-family observation target:
one dataset for one boss on one map is one dataset.

Collection is what P09-T02 owns, per `docs/specs/contracts.md` `Observation`.
None of it can be supplied by reading a guide, by a PoB number or by a
character level.

**Who can supply it.** Owner gameplay is a concrete and available collection
path, and it is not the only permitted one. Independently sourced or exported
data is acceptable on the same terms as anything else here: it closes what it
measures, with its provenance recorded, and a reviewer accepts it. The
supplemental explicit-link path P03-T01 identifies is one such source for build
configurations. What is true today is narrower than the earlier wording: no
provider in P03-T01's manifests offers a permitted automatic route, and this
project runs no in-game automation.

A third input is cheaper and partial: an accepted patch profile with
compatibility `verified` rather than `partial`, from P02-T02 against the live
patch plus the D03 decision. It closes `gap-p09-t01-patch-profile` and nothing
else, but every representative scenario needs it.

## Contracts affected

| Contract | Effect |
|---|---|
| `ScenarioSpec` | No change proposed. The suite uses `kind: synthetic` and `validation_status: untested`, and leaves both reference slots null. Noted for the reviewer: `duration_limit_s`, `capability_floor_ratio` and the entity health fields are required and non-nullable, so a representative scenario cannot be stored half-filled with nulls. The unresolved inputs live in `DataGap` records and in `docs/evidence/P09/protocol-fields.json` instead. |
| `RotationPolicy` | No change proposed. Both suite rotations use the existing v1 predicate vocabulary. |
| `DataGap` | No change proposed. Fourteen records added, eleven `blocking` and three `ranking_sensitive`. |
| `EvaluationResult` | No change proposed. Results on this suite must carry `validation: synthetic_only` and cite the suite's gaps. |
| `Observation` | No change proposed. D04 remaining blocked is what keeps P09-T02's corpus from being substituted by synthetic trials. |
| `AggregateResult` | No change proposed. With both reference slots null, every ratio is unresolved, so aggregate scores are null and `recommendation_status` cannot become a recommendation. |

No schema change is required, and `python scripts/generate_schemas.py --check`
passes unchanged.

## Reviewer

Partly resolved, 2026-10-11, by the external review in
`docs/reviews/P09-T01.md`. The record is deliberately not resolved as a whole,
because the two halves of it answer to different people.

**Resolved.** Items 1, 4 and 5 of the proposed choice, which are technical. The
direction is approved: proceed toward synthetic prototype testing only, retain
the provisional product thresholds, fit no game constants, and make no
practical build-superiority claim. Adoption of `p09-synthetic-v1` is subject to
the R1 and R2 repairs in that review, which are applied.

**Unresolved.** Items 2 and 3. Representative encounters and the three Huntress
families stay unselected, and the fourteen `DataGap` records stay open. No
gameplay validation and no gate is accepted by this.

**Owner's, not a reviewer's.** The unblocking inputs above are requests for the
owner's time, so they go to Elias as concrete alternatives rather than as a
design question. The reviewer's scope does not extend to deciding them.

## Date

2026-10-10.
