# Delivery order and acceptance gates

**Current status: 2026-10-17, specification 1.1.** PR #10 is merged (`0fa6f09`, incorporating repair `0435f74`). The initial target is now maximum sustained single-target **Flicker Strike DPS**, with the existing clear/boss and survival gates retained; see [D07](../decisions/D07-flicker-strike-objective.md). No Flicker Strike optimizer or gameplay-validation gate is complete yet.

## Next assignments

Assign these as separate, reviewable deliveries. Completed infrastructure is not permission to skip their acceptance evidence.

| Order | Task | Concrete remaining work | Ready to assign? |
|---|---|---|---|
| 1 | **P02-T01.1: native engine reliability** | Reproduce growth with operation/order and process-tree memory evidence. Fix the cause or enforce bounded worker lifetime/memory with typed failures, replacement and identical fresh-worker results. Retain failed runs. No unlimited retries. The final four-hour soak remains P08-T05. | **Contained, cause not fixed**, pending review. Growth is live `ModList` data retained by PoB's shared passive-tree cache, intermittent for identical inputs; the retaining statement is not identified. Workers have hard/soft memory bounds and a consecutive-loss cap; the in-process test session exits 87 above its bound. [Worklog](../worklog/P02-T01.1.md), [evidence](../evidence/P02-T01.1/README.md). |
| 2 | **P02-T02.1: current-patch compatibility / D03** | Capture official current-patch evidence, verify an exact clean PoB/catalog revision and Flicker Strike entity/support coverage, and resolve or explicitly retain every compatibility gap. A matching label or passing XML round trip is insufficient. | Yes; can overlap item import. |
| 3 | **P05-T02: item/listing import** | Implement market import using P04 `.3` normalization. Preserve rolls/categories, currency, unknown price and availability; deduplicate stats separately from listings. Test same-name different-roll and equal-stat separate-listing cases. | Yes; offline work needs no live provider. |
| 4 | **P05-T03: equipment pools** | Populate every supported slot from imported/owned items, retain enabling interactions, enforce listing quantity, and report sampling/truncation. No price ceiling or fixed eight-item pool. | After T02. |
| Parallel evidence track | **P09-T01.1 / D04: Flicker scope and benchmark** | Start with one complete Flicker Strike export plus actual rotation. Select approved class/ascendancy scope, distinct interaction variants, real clear/boss encounters and the evidenced target for D07's DPS benchmark. Begin observation collection; one export does not close gameplay gaps. | Begin now; evidence-dependent acceptance. |
| 5 | **P08-T01.1: objective contracts** | Contract implementation and R1/R2 repairs are complete in PR #11, `p08-t01.1-contracts`, repair `740e2f0`. Prepare must still call scope resolution, hash benchmark/attribution files and freeze class contexts. | **Done for contract scope**, subject to green CI before merge; [repair verification](../reviews/P08-T01.1-repair-verification.md) records self-verification. Exact Flicker gem/effect identity and linkage are checked against the catalog. Aggregate binding is enforced on writes, batch imports and bundle validation. Local code-only suite: 1,468 unit plus nine integration passes on each interpreter, one existing prepare-service xfail. |
| 6 | **P06-T01/T02/T03: coverage** | Registry, transitive dependency checks, actionable missing inputs and patch invalidation for the approved Flicker subset. | Synthetic work can start now; practical coverage needs accepted scope/catalog. |
| 7 | **P07-T01 through T05** | Time-accounted encounters, rotations/resources/survival, Flicker damage attribution and sustained/burst output. Enforce both-capable gates before DPS ranking. | After relevant contracts and mechanics; synthetic protocol is available. |
| 8 | **P06-T04/T05; P09-T02/T03** | Sensitivity, collection requests and independent validation. Keep holdout data separate before fitting; validate the new DPS metric as well as clear/boss outcomes. | Collection starts earlier; final acceptance needs the evaluator. |
| 9 | **P08-T01 through T05; P09-T04/T05; P10-T01 through T04** | Immutable run preparation, coordinated search, recovery, fair baseline comparisons, four-hour soak and reproducible reports/exports. | Kernel/report fixtures can start earlier; production integration waits for dependencies. |

Source acquisition and live trade are separate tracks below. They do not block explicitly offline item work. P11 learning remains optional and deferred until a validated non-learning optimizer exists.

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

Required: P01; P02-T01/T02 including real engine/catalog checks; P03-T01/T02; P09-T01; recorded D01 trade disposition. Record the first approved provider or explicitly the local-file-only prototype scope, and the exact initial Flicker Strike class/interaction scope from D07. Live trade may remain unresolved. Local-file-only prototype approval does not close the first-provider requirement of full G2.

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

## Current task ledger

**Done** means reviewed and accepted only for the scope stated. **Partial** means an accepted subset exists but the full task is unfinished. **To do** means no accepted delivery establishes the capability; legacy code, scaffolding and tests do not count as a completed replacement. **Blocked** names a specific missing prerequisite. Historical reviews remain authoritative for their original revisions; the ledger below adds the D07 work without rewriting those reviews.

| Project / tasks | Status | Done | Still required / evidence |
|---|---|---|---|
| P00-T01–T05 | **Done** | Reproducible foundation, harness, diagnostics and characterization. | [G0 acceptance](../reviews/G0-PR2-fixes.md). This is not current-patch or game accuracy approval. |
| P01-T01–T05 | **Done for contract scope** | Records, identities, storage, snapshots and recovery foundation, plus repaired D07 objective contracts. | [Original acceptance](../reviews/P01-repair-verification.md); [P08-T01.1 repair verification](../reviews/P08-T01.1-repair-verification.md). Prepare/evaluator integration remains separate. |
| P02-T01–T05 | **Done within reviewed scope; follow-ups open** | Native adapter, catalog export, legality, primitive semantics, PoB conversion/round trips; PR #10 adds support-state/variant fidelity. | [PR #5](../reviews/PR-5-repair-verification.md), [PR #10](../reviews/P04-repair-verification.md). **P02-T01.1 memory containment is pending review ([worklog](../worklog/P02-T01.1.md)); P02-T02.1 current-patch/Flicker coverage remains to do.** |
| P03-T01/T02 | **Done within reviewed scope** | Source capability investigations and local/shared HTTP acquisition. | [Acceptance](../reviews/PR-6-9-final.md). No named-source live build integration established. |
| P03-T03/T04 | **Blocked / to do** | Capability dispositions exist. | D02 has no approved automatic build provider. Provider-specific import/acquisition needs accepted access and sample representations. |
| P03-T05 | **To do** | Synthetic/PoB-derived fixtures exist. | Build a real versioned corpus; fixtures do not satisfy the diverse source-corpus target. Local exports can start collection now. |
| P04-T01/T03/T04/T05 | **Done for reviewed PoB/local scope** | Parsing, entity resolution, claim extraction/search, dedup/audit; persisted partial items and strict numeric parsing repaired. | [PR #10 acceptance](../reviews/P04-repair-verification.md), parser `.3`. Real provider corpus coverage and Flicker mechanics validation are not implied. Reparse affected old `.2` records. |
| P04-T02 | **Partial; provider parsers blocked** | PoB representation supported. | Maxroll, Mobalytics and poe.ninja parsers remain dependent on D02 and real source fixtures. |
| P05-T01 | **Done as access investigation** | D01 disposition accepted; legacy transports quarantined. | [Acceptance](../reviews/PR-6-9-final.md). **No live-market capability.** Project registration concerns character import, not a listing route. |
| P05-T02/T03 | **To do — assign next** | P04 normalization is available to reuse. | Item/listing import and all-slot pools with enabling interactions, quantity and unknown availability. |
| P05-T04 | **Blocked for live transport** | Unsupported-access decision exists. | An approved listing route and live evidence are missing. Implementing typed refusal does not complete live refresh. |
| P05-T05 | **To do; live acceptance blocked** | Reporting requirements specified. | Unlimited-budget acquisition reporting, currencies and truthful availability; G4 still needs live refresh. |
| P06-T01–T05 | **To do** | Shared rule/gap records exist. | Mechanics registry, coverage, patch invalidation, sensitivity and evidence requests. |
| P07-T01–T05 | **To do** | Engine primitives and synthetic protocol available. | Detailed encounter/rotation evaluator and D07 DPS objective; no practical combat ranker accepted. |
| P08-T01–T05 | **To do; contract prerequisite done** | Persistence foundation and P08-T01.1 objective contracts, with R1/R2 repaired and self-verified in PR #11. | Prepare, coordinated search, bounded scheduling, recovery, comparisons and four-hour soak. See [handoff](../worklog/P08-T01.1.md). |
| P09-T01 | **Partial** | Synthetic protocol accepted in [PRs #6–9](../reviews/PR-6-9-final.md). | D04 representative measurements remain blocked; **P09-T01.1 Flicker scope/benchmark is to do**. Huntress selection is superseded by D07. |
| P09-T02–T05 | **To do** | Collection/validation procedures specified. | Independent observations, calibration/holdout checks, search comparisons and expansion gates. |
| P10-T01–T05 | **To do** | Report/CLI contracts specified. | User reports, exact exports, progress/cancel presentation, walkthrough and release audit. T05 requires applicable G3/G4 evidence. |
| P11-T01–T05 | **Deferred, optional** | Experiment plan only. | Do not train yet; first establish G3 and useful reviewed labels, then compare against non-learning search. |

### Gate status

| Gate | Current verdict | What prevents further acceptance |
|---|---|---|
| G0 | **Accepted for foundation scope** | No reopening from this scope update. |
| G1 | **Not accepted as a complete gate** | Final scope/provider disposition, current-patch compatibility and representative protocol remain incomplete; synthetic-prototype work has scoped task acceptance. |
| G2 | **Not accepted** | Offline equipment pools, mechanics coverage and detailed evaluation; full first-provider path remains unresolved. |
| G3 | **Not accepted** | Validated Flicker objective/scope, observations, search/reporting and bounded four-hour run. |
| G4 | **Blocked** | Live trade and named-source capability outcomes plus applicable G3 evidence. |
| G5 | **Deferred** | Optional learning experiment follows G3. |

The latest accepted implementation baseline passed 1,369 offline tests and 152 native tests on both Python 3.10 and 3.12; CI passed for `0435f74`. These are historical acceptance results for that code, not evidence that the remaining features or the new objective work.

## Blocker handling

Record a blocker with task ID, evidence, attempted route, exact missing decision/input and independent tasks that can continue. Automatic website access, real engine behavior and independent gameplay measurement cannot be replaced by mocks at their acceptance gates. A prototype can use mocks when its claims remain explicitly synthetic.

Do not assign calendar estimates before G0/G1 measurements and access studies. At each gate, the reviewer updates sequencing, task size and effort estimates based on evidence. Split a task into numbered child tasks if it contains more than one independently reviewable change; preserve the parent acceptance criteria.
