# Review and reassessment procedure

The engineer implements and submits evidence. The reviewing assistant inspects the actual changes, reproduces relevant checks, issues a verdict and reassesses dependent work. This process applies when work is brought back for review; it does not imply unattended monitoring of future changes.

## Task lifecycle

`planned -> in_progress -> review_ready -> accepted`

Alternative transitions are `in_progress -> blocked`, `review_ready -> changes_required -> in_progress`, and any state to `superseded` with a replacement reference. Engineers may set work to review-ready or blocked. Only the reviewer records accepted. Blocked access never becomes accepted after a timeout.

Each task needs a worklog from [the handoff template](templates/handoff.md). Do not paste massive logs into prose: save relevant redacted artifacts and provide stable paths, hashes and command summaries. Store durable review evidence under `docs/evidence/<task-or-gate>/` or a referenced content-addressed artifact bundle; ignored `runs/` files alone are insufficient for another engineer's handoff.

## Engineer submission checklist

1. Cite task IDs, spec version, starting/current commits and changed files.
2. Map every acceptance criterion to a test, artifact or an explicitly unexecuted/blocked check.
3. Include exact commands, versions, fixture IDs, run IDs, outcomes and prerequisites.
4. Include negative cases and one end-to-end example where the task affects a pipeline.
5. Explain deviations from the spec. Do not silently change thresholds, schemas or scope.
6. Identify unsupported inputs and downstream consequences.
7. State which tasks/gates should now be reviewed or invalidated.

Do not mark a task complete because a mock passes where the criterion requires engine/live/gameplay evidence. Do not report a test as passed merely because it collected zero cases or skipped all cases.

## Reviewer procedure

### Inspect the implementation and its dependencies

Read the task, shared contracts and prior gate verdicts. Inspect git diff and surrounding call sites. Verify that the implementation is in the assigned layer and no alternate ranking/parser schema was introduced. Check preserved user changes. Separate observed defects from untested concerns.

### Reproduce the critical behavior

Run the narrow relevant test group first, then the prescribed integration acceptance checks. Inspect actual artifacts rather than relying on engineer screenshots or summaries. Where execution is impossible, state why and keep the corresponding criterion blocked. Recheck serialized identities and raw source evidence when parsing, caching or export changed.

### Challenge correctness

Use at least one independent adversarial case relevant to the change, such as an unknown modifier, partial build, simultaneous effect expiry, resource-starved rotation, unavailable listing, duplicate configuration, stale patch or worker crash. Use inputs not copied from the implementation's own expected-output generator.

### Issue a verdict

Write `docs/reviews/TASK-ID.md` using the [review template](templates/review.md). Verdict is `accepted`, `changes_required`, `blocked` or `superseded`. Include findings in severity order, exact code locations, impact and repair acceptance cases. Acceptance includes residual scope limits; it does not automatically approve unrelated dependent gates.

### Reassess the plan

At each task, state whether its findings change contracts, assumptions or dependencies. At each milestone, update delivery sequencing and make a concrete next-task recommendation. If a defect invalidates earlier evidence, identify and reopen those gates before dependent release claims proceed.

## Mandatory milestone questions

| Area | Reviewer must answer |
|---|---|
| Data fidelity | Can an imported record be traced to original fields, and does its export preserve gameplay semantics? |
| Game coverage | Which exact rules and families are implemented, untested, unsupported or stale? |
| Numerical correctness | Are timing, units, stacking and damage counted exactly once under declared semantics? |
| Practical accuracy | What independent held-out observations support the results, and which claims exceed them? |
| Search quality | Does additional compute help under equal budgets? Can the search discover coordinated changes? |
| Robustness | Can the run recover, remain bounded and reproduce accepted results after fresh-worker evaluation? |
| Availability | Is live-market capability demonstrated, and are selected items actually observed/rechecked? |
| Product fit | Does the build pass both categories and explain execution without hiding missing evidence? |
| Learning | Does the model improve end-to-end search beyond its training/serving cost and bias? |

## Regression invalidation rules

- Parser/item-conversion change: rerun affected golden imports, canonical hash checks and PoB round trips; invalidate affected normalized data/evaluations.
- Catalog/patch change: reevaluate legality and mechanics compatibility; invalidate affected observations' applicability, not their historical records.
- Primitive/simulator change: rerun analytical fixtures, reference evaluations and affected independent validation. Score comparisons across evaluator versions are separate campaigns.
- Objective/reference change: rerun aggregate scoring; do not compare old/new scores without recomputing both under the same objective.
- Market refresh: preserve combat results for unchanged items; update availability and reevaluate substituted gear.
- Search change: rerun finite-space optima, paired-budget comparisons and recovery tests when scheduling/state changes.
- Learning change: repeat held-out and paired-search checks; core correctness gates remain mandatory.

## What engineers must not decide alone

Engineers can make routine implementation choices inside this spec. They must submit a concrete decision record for new game-rule interpretations, changing public record semantics, relaxing release thresholds, substituting an unavailable provider, redefining encounter objectives, or claiming previously unsupported mechanics. The reviewer resolves technical matters; Elias resolves genuine scope/preferences when evidence cannot determine them.

## Acceptance versus reassessment

A useful review may conclude that the code meets its task but the project should change direction. For example, the trade study can be complete as an investigation while R05 remains blocked; a learning experiment can be correctly executed and rejected for adoption. Record both task quality and product outcome so successful engineering is not confused with successful capability delivery.
