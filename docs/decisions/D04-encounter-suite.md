# D04 Encounter suite and credible measurements

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

**1. One complete Huntress build, supplied by the owner (Elias).** A PoB build
file or build code exported by hand, carrying equipment with full modifier text,
passive allocations, ascendancy, skill groups with levels, quality and supports,
weapon-set bindings, and the rotation the operator plays. Imported through
P03-T02 local acquisition, with no provider access. This closes
`gap-p09-t01-reference-build` for one configuration and lets the build-family
question be reopened honestly: a family can be named once a build exists that
belongs to it. Three builds across three families would close
`gap-p09-t01-build-families` without any corpus.

**2. Recorded gameplay for one named encounter, supplied by the owner or by an
operator the owner names.** For a single named boss and a single named map
layout, at a stated area level and patch: monster life and mitigation,
pack size and pack spacing along the walked route, per-leg route times, boss
phase and invulnerability start and end times across at least five attempts,
timestamped incoming damage events, the resource state at the start event, and
the completion time of each attempt including the failures. This is what P09-T02
collects, and it closes the remaining eleven gaps. It cannot be supplied by
reading a guide, by a PoB number or by a character level, per
`docs/specs/contracts.md` `Observation`.

Nobody else can supply either input today. No provider in P03-T01's manifests
offers a permitted automatic route, and this project runs no in-game automation.

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

Unresolved. No reviewer has seen this record.

The reviewing assistant resolves items 1, 4 and 5 of the proposed choice, which
are technical. Items 2 and 3, and the two unblocking inputs above, are requests
to the owner: supplying a build file and recording gameplay are the owner's
time, not an implementation choice, so they go to Elias as concrete
alternatives rather than as a design question.

## Date

2026-10-10.
