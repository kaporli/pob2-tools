# Benchmarks and independent validation

Project ID: P09. This project starts early. T01 depends on P00 and initial source/catalog evidence, not on a completed simulator. T02 can collect evidence while P07 is built. T03/T04 require P07/P08. Goal: prevent consistency with PoB from being mistaken for accuracy in the game.

## P09-T01 Freeze the first scope and measurement protocol

**P09-T01.1 — Flicker Strike scope follow-up, still to do:** supersedes the Huntress-family selection from spec 1.0. Start with one complete Flicker Strike export plus the operator's actual rotation. Propose an explicit compatible class/ascendancy list and three distinct interaction variants within Flicker Strike from evidence, with their exact required mechanics. Select two clearing workloads and two boss workloads, reference builds, initial state, legal preparation, survival/resource pass conditions, timeout and measurable completion events. Use the four shapes in `scenarios.md`, plus [D07](../../decisions/D07-flicker-strike-objective.md)'s controlled sustained-DPS benchmark. A seed export starts scope selection; it supplies no independent performance measurement.

For each field attach a source, direct measurement or an explicit unresolved input. Obtain reviewer acceptance of the protocol and domain interpretation before fitting any constants. If domain knowledge or encounters are unavailable, create synthetic scenarios for software testing and record D04 as blocked for practical claims. Do not ask a junior engineer to invent plausible enemy stats.

Acceptance: `benchmarks/<suite_id>/protocol.md`, scenario JSON and reference manifests specify exact procedures another operator can repeat. Every survival gate has a numerical or event-based definition. Suite/reference hashes are frozen. Reviewer records scope exclusions and accepted provisional thresholds.

## P09-T02 Collect and import independent observations

Target at least 12 complete configurations across three reviewed Flicker Strike interaction variants, with at least five trials for each configuration in each of the four clear/boss scenarios: 240 attempted trials, retaining failures. Additionally target five independent controlled-DPS observations per configuration (60 attempts; 300 total with encounter trials). P09-T01.1 must establish a feasible method and applicability to D07's target/window before collection; do not assume an immortal target exists in the game or use PoB numbers as observations. Missing comparable DPS evidence blocks practical DPS claims. Record exact gear/tree/skills, patch, rotation, encounter conditions, operator, timestamps and deviations. Use manual gameplay recording or reliable exported measurements; no in-game automation is required or included.

Assign entire reviewed interaction-variant groups and near-duplicate lineages to calibration, validation or holdout before fitting. Initial allocation: one variant group/four configurations per split; expand later because this small corpus cannot validate all Flicker Strike variants or all PoE 2. Reuse reviewed family IDs for this grouping, with its narrowed meaning declared in the manifest. If three genuinely independent groups are unavailable, report the shortage and obtain scope review before inspecting results; never fabricate diversity. Keep calibration and holdout physically separate with manifest hashes.

Acceptance: observation importer rejects missing context; timings can be independently checked from evidence; failed/censored trials are preserved. PoB DPS, guide text, character level and favorites are never accepted as measured labels. Insufficient observations keep practical approval blocked; synthetic substitutes do not count.

## P09-T03 Validate and calibrate the evaluator

First check mechanics fixtures and reference parity with pinned PoB; then compare predicted encounter outcomes against independent observations. Fit only evidenced parameters using the calibration split. Use validation to select revisions. Freeze evaluator/calibration versions before opening holdout results. Changing after a holdout failure requires a new independent holdout before claiming a fresh pass.

Initial proposed release thresholds: median absolute percentage error no greater than 15% and 90th percentile no greater than 30% on successful held-out completion-time medians, separately for clear and boss categories. Survival/pass-fail mismatches that would recommend a failing build are release blockers. Report sample counts, all failures and trial variability. These thresholds are product gates, not assertions that this accuracy is achievable from present data.

For D07, apply those provisional error thresholds separately to comparable held-out sustained-DPS medians, and the directional-ranking criterion below separately to sustained DPS. Report burst validation separately; it cannot substitute for sustained validation. No percentage error can be computed against an unknown/zero denominator; retain the case with an explicit metric-appropriate check or unresolved gap, rather than dropping it. Successful clear/boss validation alone does not validate the new objective.

For pairwise ranking, compare observed medians using trial ranges as a conservative ambiguity screen: if ranges overlap, label the pair inconclusive. Of conclusive pairs, require at least six per category and at least 90% directional agreement. Report exclusion counts; too few conclusive pairs means insufficient evidence. Do not call the ranges confidence intervals.

Acceptance: reproducible validation report includes family-specific error and coverage, held-out split integrity and mismatches. Broad archetype fudge factors without causal justification cannot be used to hide a broken interaction. Reviewer accepts, requests fixes or narrows the validated scope explicitly.

## P09-T04 Run end to end search comparisons

Use P08's seed-only, greedy, random and population-search baselines. Freeze equipment pool and the same preparation/rotation allowances. Show best eligible score over evaluation count and wall time, family diversity, unsupported candidates and between-seed variability. Compare top discovered builds against observed reference performance where feasible.

Acceptance: all exported winners are legal, pass both categories and reproduce under fresh workers. Improvements smaller than measurement uncertainty are reported as unproven practical gains. A counterexample where search exploits the evaluator becomes a mechanics/validation defect with a new regression fixture, not a successful discovery.

## P09-T05 Maintain regression and expansion gates

Create a benchmark registry linking each mechanic family and patch to accepted tests, observation scope and validation report. On patch/catalog/evaluator changes, rerun affected mechanics, reference scenarios and holdout checks appropriate to the change. Unknown impact requires a broader rerun; do not assert unchanged behavior without evidence.

For each new class/family, create an expansion packet: required rules, data sources, imported examples, exact fixtures, scenario applicability and independent observations. Require P06/P07/P09 review before changing supported status. Issue new child tasks with permanent IDs and acceptance cases; do not let engineers add unsupported families via config alone.

Acceptance: the reviewer can identify exactly which claims survive a patch and which are stale. The four-hour soak, validation report and source/parser coverage are included in the release evidence. No claim of full-game or unrestricted Flicker Strike coverage emerges from three interaction variants.
