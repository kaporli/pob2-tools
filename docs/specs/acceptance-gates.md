# Acceptance definitions

These are technical acceptance definitions, not a status ledger. Gate verdicts and dependencies are tracked in [GitHub Issues](https://github.com/kaporli/pob2-tools/issues/23). Historical acceptance remains scoped to its exact implementation and evidence.

## Model based delivery

The owner cannot supply gameplay recordings. [D08](../decisions/D08-model-based-evidence.md) defines a model-based delivery tier without changing the meaning of independently gameplay-validated results.

### G3M Model based offline optimizer

Require accepted mechanics/legality coverage for the declared scope, reproducible PoB and analytical checks, explicit modeled clear/boss/survival/resource workloads, immutable preparation, coordinated search and finite-space baselines, bounded recovery, a four-hour soak, fresh-worker finalists and faithful reports/exports. Compare winners only under the same patch, objective, attribution and assumptions. Reports identify model predictions and unsupported scope. Owner recordings and a live provider are not prerequisites for this tier. Missing critical mechanics remain blockers.

Original G3 below remains the separate empirical tier; G3M does not assert practical gameplay superiority. Gate review requests: [G3M](https://github.com/kaporli/pob2-tools/issues/40) and [G3](https://github.com/kaporli/pob2-tools/issues/41).

## Original gate definitions and requirement traceability

### G0 Reproducible foundation

Required: all P00 tasks; actual environment record; offline test results; known defects characterized; clear engine availability status. If PoB is absent, G0 can approve offline foundation only and record an engine sub-gate as blocked. No later real-engine gate can pass on skipped tests.

Reviewer checks: reproducibility, preserved user changes, source-versus-synthetic fixture labeling and absence of hidden network calls.

### G1 Contracts and initial scope

Required: P01; P02-T01/T02 including real engine/catalog checks; P03-T01/T02; P09-T01; recorded D01 trade disposition. Record the first approved provider or explicitly the local-file-only prototype scope, and the exact initial Flicker Strike class/interaction scope from D07. Live trade may remain unresolved. Local-file-only prototype approval does not close the first-provider requirement of full G2.

Reviewer checks: semantic record completeness, canonical hashing, patch evidence, worker isolation, scenario protocol and practical measurement feasibility. If the encounter protocol cannot be established, accept only a named synthetic-prototype scope and keep representative evaluation blocked.

### G2 Faithful evaluation

Required: remaining P02 tasks, first provider import path, P04, P05 offline import/pools, P06 and P07. Engine round trips, legality fixtures, analytical event tests, scoring fixtures and gap behavior pass. P09 measurement collection may still be in progress.

Reviewer checks: no lost modifiers or configuration; no double-counted damage; no impossible conditions; no timing penalties discarded; no proxy relabelled as real performance. Passing G2 permits research search over the supported model, not validated gameplay claims.

### G3 Validated offline optimizer

Required: accepted representative scope, P08, P09-T02 through P09-T05, P10-T01 through P10-T04, a four-hour soak and holdout accuracy/ranking evidence for practical clear/boss claims. Under the recorded D07 amendment, the DPS benchmark uses pinned PoB damage plus reviewed time/resource/attribution computation; in-game DPS observations are optional. Live sources/trade are not required for this explicitly offline milestone.

Reviewer checks: source and observation lineage, held-out integrity, honest comparison with baselines, both-capable outputs, memory/recovery behavior and reproducible exports. If independent data is inadequate, release may be described as a research prototype; G3 remains unaccepted.

### G4 Live product integration

Required: P03 named-source capability outcomes/corpus, accepted P05 live path and verification, P10-T05 and the latest applicable G3 validation. Each source must have a reviewed status; unsupported automatic access is a disclosed missing feature, not a successful automatic adapter.

Reviewer checks: current-patch and final listing evidence, full equipment fidelity, rate/error behavior, no hidden budget filter and no historical market fiction. Full R05 cannot close without real supported live access. Any release omitting a requested provider or live feature needs an explicit owner-approved reduced scope; the omitted requirement remains tracked.

### G5 Optional learned search adoption

Required: all P11 experiment evidence and paired search comparison. Reviewer either accepts the learned ranker as an optional component or leaves it disabled. No model training is necessary to accept G3/G4.

## Requirement traceability

| Requirement | Main implementation | Acceptance gate |
|---|---|---|
| R01 Flicker Strike constraint and explicit class scope | P02-T02/T03, P08-T01/T02 | G2/G3 |
| R02 Clearing and bossing | P07-T05, P09, P10-T02 | G3 |
| R03 Strengths and execution | P07-T03, P10-T02 | G3 |
| R04 Unlimited budget | P05-T02/T03/T05, P08-T01 | G3 offline; G4 live |
| R05 Trade availability | P05-T01/T04/T05 | G4 |
| R06 Current patch | P02-T02, P06-T03, P09-T05 | G1, rechecked for G3/G4 |
| R07 Demanding execution | P07-T03/T04, P10-T02 | G3 |
| R08 Community knowledge | P03, P04 | First path G2; named-source scope G4 |
| R09 Missing evidence | P06, P10-T01 | G2/G3 |
| R10 Long runs | P01-T05, P08-T04/T05 | G3 |
| R11 Discovery | P08-T02/T03/T05 | G3 |
| R12 Review and reassessment | All task handoffs and gate reviews | Every gate |
