# Delivery order and acceptance gates

Use this order to avoid building an optimizer on unverified parsers or an unverified evaluator. Tasks are implementation work; gates are reviewer decisions. A passing test alone does not accept a gate.

## Work sequence

| Stage | Work to assign | Dependencies and outcome |
|---|---|---|
| 0 | P00-T01 through P00-T05 | Establish reproducible setup, fixtures and known limitations. Request G0. |
| 1 | P01-T01 through P01-T05 | Implement common records, identities and persistence. |
| 2 | P02-T01/T02, P03-T01/T02, P05-T01, P09-T01 | Establish engine/catalog, source access disposition, trade access disposition and initial benchmark protocol. Source/benchmark investigations can overlap after their prerequisites exist. Request G1. |
| 3 | P02-T03/T04/T05, P03-T03, P04-T01 through P04-T05, P05-T02/T03 | Faithful imports, exact engine behavior, legality and offline equipment pools. P04 catalog-dependent steps wait for P02-T02. |
| 4 | P06-T01/T02/T03, P07-T01 through P07-T05 | Coverage registry and deterministic encounter evaluation. P07 starts with accepted primitive contracts and synthetic fixtures. |
| 5 | P06-T04/T05, P09-T02/T03 | Sensitivity, actionable gaps and independent validation. Observation collection can start after protocol acceptance while simulator work continues. Request G2 for software behavior before claiming G3 practical accuracy. |
| 6 | P08-T01 through P08-T05, P09-T04/T05, P10-T01 through P10-T04 | Search, endurance checks and usable offline delivery. Pure search-kernel and report-fixture work can start earlier against accepted interfaces. Request G3. |
| 7 | P03-T04/T05, P05-T04/T05, P10-T05 | Finish named source paths and live-market integration where access is resolved. These tasks can progress earlier, but full live release requires G4. |
| 8 | P11-T01 through P11-T05 | Optional learning experiment after G3; request G5 only if adoption is justified. |

Within each project, follow task order unless a task explicitly allows earlier fixture work. Never merge a dependent production feature before the contracts and relevant gate are accepted. Prototype/synthetic work can continue while a provider is blocked, but remains labelled accordingly.

## Gate definitions

### G0 Reproducible foundation

Required: all P00 tasks; actual environment record; offline test results; known defects characterized; clear engine availability status. If PoB is absent, G0 can approve offline foundation only and record an engine sub-gate as blocked. No later real-engine gate can pass on skipped tests.

Reviewer checks: reproducibility, preserved user changes, source-versus-synthetic fixture labeling and absence of hidden network calls.

### G1 Contracts and initial scope

Required: P01; P02-T01/T02 including real engine/catalog checks; P03-T01/T02; P09-T01; recorded D01 trade disposition. Select the first provider and exact initial Huntress families. Live trade may remain unresolved.

Reviewer checks: semantic record completeness, canonical hashing, patch evidence, worker isolation, scenario protocol and practical measurement feasibility. If the encounter protocol cannot be established, accept only a named synthetic-prototype scope and keep representative evaluation blocked.

### G2 Faithful evaluation

Required: remaining P02 tasks, first provider import path, P04, P05 offline import/pools, P06 and P07. Engine round trips, legality fixtures, analytical event tests, scoring fixtures and gap behavior pass. P09 measurement collection may still be in progress.

Reviewer checks: no lost modifiers or configuration; no double-counted damage; no impossible conditions; no timing penalties discarded; no proxy relabelled as real performance. Passing G2 permits research search over the supported model, not validated gameplay claims.

### G3 Validated offline optimizer

Required: accepted representative scope, P08, P09-T02 through P09-T05, P10-T01 through P10-T04, a four-hour soak and holdout accuracy/ranking evidence. Live sources/trade are not required for this explicitly offline milestone.

Reviewer checks: source and observation lineage, held-out integrity, honest comparison with baselines, both-capable outputs, memory/recovery behavior and reproducible exports. If independent data is inadequate, release may be described as a research prototype; G3 remains unaccepted.

### G4 Live product integration

Required: P03 named-source capability outcomes/corpus, accepted P05 live path and verification, P10-T05 and the latest applicable G3 validation. Each source must have a reviewed status; unsupported automatic access is a disclosed missing feature, not a successful automatic adapter.

Reviewer checks: current-patch and final listing evidence, full equipment fidelity, rate/error behavior, no hidden budget filter and no historical market fiction. Full R05 cannot close without real supported live access. Any release omitting a requested provider or live feature needs an explicit owner-approved reduced scope; the omitted requirement remains tracked.

### G5 Optional learned search adoption

Required: all P11 experiment evidence and paired search comparison. Reviewer either accepts the learned ranker as an optional component or leaves it disabled. No model training is necessary to accept G3/G4.

## Requirement traceability

| Requirement | Main implementation | Acceptance gate |
|---|---|---|
| R01 Class restriction | P02-T02/T03, P08-T02 | G2/G3 |
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

## Initial task ledger

Each project has five tasks, T01 through T05. All 60 tasks are `planned` when this specification is delivered. This table is a summary; individual worklog/review records become the source of truth as implementation proceeds.

| Project | Tasks | Status | Immediate blocker |
|---|---|---|---|
| P00 | P00-T01 through P00-T05 | planned | None for offline investigation; engine checkout absent at inspection |
| P01 | P01-T01 through P01-T05 | planned | G0 |
| P02 | P02-T01 through P02-T05 | planned | Foundation, contracts and a configured PoB runtime |
| P03 | P03-T01 through P03-T05 | planned | Foundation/contracts; per-provider access unresolved |
| P04 | P04-T01 through P04-T05 | planned | Saved source fixtures and catalog |
| P05 | P05-T01 through P05-T05 | planned | Live route unresolved; offline import can proceed after contracts |
| P06 | P06-T01 through P06-T05 | planned | Catalog, mechanics scope and primitive semantics |
| P07 | P07-T01 through P07-T05 | planned | Accepted mechanics and scenario protocol |
| P08 | P08-T01 through P08-T05 | planned | Evaluator for production; fixtures permit earlier kernel work |
| P09 | P09-T01 through P09-T05 | planned | Protocol investigation first; independent observations not yet collected |
| P10 | P10-T01 through P10-T05 | planned | Contracts for fixtures; accepted evaluations for production |
| P11 | P11-T01 through P11-T05 | planned optional | G3 and sufficient reviewed labels |

## Blocker handling

Record a blocker with task ID, evidence, attempted route, exact missing decision/input and independent tasks that can continue. Automatic website access, real engine behavior and independent gameplay measurement cannot be replaced by mocks at their acceptance gates. A prototype can use mocks when its claims remain explicitly synthetic.

Do not assign calendar estimates before G0/G1 measurements and access studies. At each gate, the reviewer updates sequencing, task size and effort estimates based on evidence. Split a task into numbered child tasks if it contains more than one independently reviewable change; preserve the parent acceptance criteria.
