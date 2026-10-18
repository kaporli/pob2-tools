# Delivery order and acceptance gates

**Current status: 2026-10-18, specification 1.1 plus the recorded D07 amendment in PR #17.** PRs #10–14 are merged. PR #14 is accepted for its catalog/evidence scope; the five findings in PRs #15–17 are repaired and locally verified, pending merge after green checks on the pushed heads. The target remains maximum sustained single-target **Flicker Strike DPS**, with clear/boss and survival gates retained. No working Flicker optimizer or gameplay-validation gate is complete.

The owner amendment recorded in [PR #17](https://github.com/kaporli/pob2-tools/pull/17) accepts pinned PoB damage against a fixed Pinnacle configuration; in-game DPS recordings are optional. This changes the DPS validation work, not the requirements to account for setup, charges, activation conditions, mana, elapsed time and attribution. Actual clear/boss capability claims still need independent evidence. Merge the amendment with the repaired protocol; this reassessment does not restore superseded in-game DPS requirements.

| PR and original reviewed head | Current repair status | What is usable / still missing |
|---|---|---|
| #14 `83f7a54` | **Accepted within delivered scope; merged as `3046609`** | Verbatim release evidence and engine-tested Flicker catalog coverage. Compatibility remains partial; [review](../reviews/P02-T02.1.md). |
| #15 `63d8a58` | **R1/R2 repaired; based on main** | Unterminated reminders are refused; actual calendar timestamps are checked; [review](../reviews/P05-T02.md). |
| #16 `644c7b8` | **R1/R2 repaired; stacked on #15** | Catalog/realm/league scope is enforced before matching; conflicting duplicate readiness/content is refused deterministically. Real slot categories remain missing; [review](../reviews/P05-T03.md). |
| #17 `9f32dfe` | **R1 repaired; retargeted to main** | Activation and attribution remain open blocking prerequisites, including when every other blocker is resolved. Seed/scope/protocol evidence exists; no cycle score yet; [review](../reviews/P09-T01.1.md). |

[Repair verification](../reviews/PR-15-17-repair-verification.md) records 1,606 / 1,646 / 1,569 offline passes for #15 / #16 / #17 respectively on both interpreters, one existing prepare-service xfail each, and 11 native item-conversion passes on each interpreter. Thirty-seven new regression cases fail on the original reviewed heads and pass after repair. Final GitHub checks must match the heads being merged. These are software checks, not acceptance of an optimizer or gameplay gate.

## Next assignments

Assign these as separate, reviewable deliveries. Completed infrastructure is not permission to skip their acceptance evidence.

| Order | Task | Concrete remaining work | Ready to assign? |
|---|---|---|---|
| 1 | **Land repaired #15–17** | Repairs and regression evidence are complete. #14 is merged; #15 and #17 are based on main, #16 includes repaired #15. Retarget/reconcile #16 after #15 lands if needed. | Merge #15 before #16; #17 is independent. Verify final-head CI. |
| 2A | **P02-T03.1 follow-up: real slot-category rules** | Export accepted base categories from pinned PoB; verify positive and negative slot assignments against real engine behavior. Build a pool from real imported items across supported weapons/sets, armor, jewelry and auxiliary/socketed equipment. Unsupported rules stay explicit. | Next equipment milestone; depends on #14 and repaired #15/#16. Empty real pools do not satisfy it. |
| 2B | **P09-T01.1 follow-up: clean seed replay and cycle inputs** | Reproduce the seed/charge table with a clean pinned checkout and exact settings. Resolve Combo/charge generation, Charged Staff placement and buff ownership, Hit and Run reuse, timing, mana/flasks and damage ownership. Keep missing inputs typed. | Can run alongside slot work. Owner Q10 supplies the seed's Charged Staff schedule; independent mechanics work can proceed meanwhile. |
| 3 | **P06-T01/T02/T03: executable coverage** | Turn the declared seed dependencies into a registry and transitive checks. Missing data, missing code, unsupported rules and stale patch must produce distinct actionable gaps. An unvalidated activation rule cannot become informational merely to allow a score. | Start now against the pinned model; expand with each implemented variant. |
| 4 | **P07 first slice: one traceable Flicker cycle** | Evaluate the seed over 120 seconds, report the first 5 seconds separately, count every setup/action/wait, consume/generate actual resources and attribute only approved damage. Output a state/damage trace and fresh-worker agreement, or a typed blocking gap. | After the relevant 2B rules. This is a model benchmark, not a best-build recommendation. |
| Parallel evidence track | **P09-T02/T03: clear/boss evidence** | Name representative encounters (Q11), set survival thresholds, collect independent completion/survival evidence, and retain a holdout. DPS recordings are optional under the amendment; clear/boss claims are not certified by PoB DPS. | Begin selection/collection now; final acceptance needs the evaluator. |
| 5 | **Remaining P07; P06-T04/T05** | Implement clear/boss workloads, resource/survival gates, sensitivity and collection requests. Integrate them with the PoB-based DPS benchmark before recommending winners. | After the seed slice; independent analytical fixtures can start earlier. |
| 6 | **P08-T01/T02/T03; P09-T04** | Prepare immutable class-bound contexts and pools; search coordinated gear/tree/support/rotation changes. Respect all 23 approved ascendancies and three charge-source variants, reporting unsupported/excluded contexts. Compare against seeds and finite-space baselines. | Search kernels can start on synthetic spaces; real search needs working coverage/evaluation and gear pools. |
| 7 | **P08-T04/T05; P09-T05; P10-T01–T04** | Bounded scheduling, checkpoint/resume, fresh-worker finalist verification, campaign-wide four-hour soak, reproducible exports and reports explaining assumptions, strengths, execution and gaps. | Final offline milestone; no blanket “absolute best” claim beyond the searched/modelled universe. |

Already done: P02-T01.1 worker containment and P08-T01.1 objective contracts
are merged. The underlying PoB cause, unbounded MCP server and engine-test
process isolation remain reliability follow-ups. Current-patch compatibility
still needs a supported update or an explicit evidence-backed review; research
on the pinned model must retain its partial label. Building the seed slice
first does not reduce the approved all-class/variant product scope.

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

## Current task ledger

**Done** means reviewed and accepted only for the scope stated. **Partial** means an accepted subset exists but the full task is unfinished. **To do** means no accepted delivery establishes the capability; legacy code, scaffolding and tests do not count as a completed replacement. **Blocked** names a specific missing prerequisite. Historical reviews remain authoritative for their original revisions; the ledger below adds the D07 work without rewriting those reviews.

| Project / tasks | Status | Done | Still required / evidence |
|---|---|---|---|
| P00-T01–T05 | **Done** | Reproducible foundation, harness, diagnostics and characterization. | [G0 acceptance](../reviews/G0-PR2-fixes.md). This is not current-patch or game accuracy approval. |
| P01-T01–T05 | **Done for contract scope** | Records, identities, storage, snapshots and recovery foundation, plus repaired D07 objective contracts. | [Original acceptance](../reviews/P01-repair-verification.md); [P08-T01.1 repair verification](../reviews/P08-T01.1-repair-verification.md). Prepare/evaluator integration remains separate. |
| P02-T01–T05 | **Done within reviewed scope; follow-ups open** | Native adapter, catalog export, legality, primitive semantics, PoB conversion/round trips. PR #13 containment and #14 catalog/evidence extension are merged. | [P02-T02.1 review](../reviews/P02-T02.1.md). Current-patch compatibility remains partial; real slot-category rules are P02-T03.1 next. Root cause, MCP isolation and full endurance remain open. |
| P03-T01/T02 | **Done within reviewed scope** | Source capability investigations and local/shared HTTP acquisition. | [Acceptance](../reviews/PR-6-9-final.md). No named-source live build integration established. |
| P03-T03/T04 | **Blocked / to do** | Capability dispositions exist. | D02 has no approved automatic build provider. Provider-specific import/acquisition needs accepted access and sample representations. |
| P03-T05 | **To do** | Synthetic/PoB-derived fixtures exist. | Build a real versioned corpus; fixtures do not satisfy the diverse source-corpus target. Local exports can start collection now. |
| P04-T01/T03/T04/T05 | **Done for reviewed PoB/local scope** | Parsing, entity resolution, claim extraction/search, dedup/audit; persisted partial items and strict numeric parsing repaired. | [PR #10 acceptance](../reviews/P04-repair-verification.md), parser `.3`. Real provider corpus coverage and Flicker mechanics validation are not implied. Reparse affected old `.2` records. |
| P04-T02 | **Partial; provider parsers blocked** | PoB representation supported. | Maxroll, Mobalytics and poe.ninja parsers remain dependent on D02 and real source fixtures. |
| P05-T01 | **Done as access investigation** | D01 disposition accepted; legacy transports quarantined. | [Acceptance](../reviews/PR-6-9-final.md). **No live-market capability.** Project registration concerns character import, not a listing route. |
| P05-T02/T03 | **Reviewed defects repaired in #15/#16; pending merge** | Manual item/listing import and synthetic-tested all-slot pool builder exist; normal unit/native cases pass. | [T02 review](../reviews/P05-T02.md), [T03 review](../reviews/P05-T03.md): all four findings repaired; see the linked repair verification above. Real imported pools still need slot rules. Parser `.5` requires reparsing affected older inputs. |
| P05-T04 | **Blocked for live transport** | Unsupported-access decision exists. | An approved listing route and live evidence are missing. Implementing typed refusal does not complete live refresh. |
| P05-T05 | **To do; live acceptance blocked** | Reporting requirements specified. | Unlimited-budget acquisition reporting, currencies and truthful availability; G4 still needs live refresh. |
| P06-T01–T05 | **To do** | Shared rule/gap records exist. | Mechanics registry, coverage, patch invalidation, sensitivity and evidence requests. |
| P07-T01–T05 | **To do** | Engine primitives and synthetic protocol available. | Detailed encounter/rotation evaluator and D07 DPS objective; no practical combat ranker accepted. |
| P08-T01–T05 | **To do; contract prerequisite merged** | Persistence foundation and P08-T01.1 objective contracts, with R1/R2 repaired in merged PR #11. | Prepare, coordinated search, bounded scheduling, recovery, comparisons and four-hour soak. See [handoff](../worklog/P08-T01.1.md). |
| P09-T01 | **Partial; #17 protocol repair complete, pending merge** | Seed XML/rotation, approved all-23-ascendancy scope and three variant proposals, fixed PoB target, explicit gaps and frozen protocol files exist. | [Review](../reviews/P09-T01.1.md). Activation/attribution are now blocking. Replay the seed cleanly and resolve cycle inputs (21 blocking and 3 ranking-sensitive gaps remain open). D04 remains blocked for practical clear/boss claims; no DPS cycle value exists. |
| P09-T02–T05 | **To do, DPS scope amended** | Procedures specified; PoB accepted as damage source for the fixed benchmark. | Independent clear/boss observations, holdout checks, search comparisons and expansion gates. In-game DPS measurements are optional; reviewed cycle mechanics and computation are required. |
| P10-T01–T05 | **To do** | Report/CLI contracts specified. | User reports, exact exports, progress/cancel presentation, walkthrough and release audit. T05 requires applicable G3/G4 evidence. |
| P11-T01–T05 | **Deferred, optional** | Experiment plan only. | Do not train yet; first establish G3 and useful reviewed labels, then compare against non-learning search. |

### Gate status

| Gate | Current verdict | What prevents further acceptance |
|---|---|---|
| G0 | **Accepted for foundation scope** | No reopening from this scope update. |
| G1 | **Not accepted as a complete gate** | Class/variant scope is recorded in #17, but representative evaluation, current-patch compatibility and first-provider/local-file gate disposition remain incomplete. Synthetic-prototype work has scoped task acceptance. |
| G2 | **Not accepted** | Offline equipment pools, mechanics coverage and detailed evaluation; full first-provider path remains unresolved. |
| G3 | **Not accepted** | Validated Flicker objective/scope, observations, search/reporting and bounded four-hour run. |
| G4 | **Blocked** | Live trade and named-source capability outcomes plus applicable G3 evidence. |
| G5 | **Deferred** | Optional learning experiment follows G3. |

The PR #10 repair baseline passed 1,369 offline tests and 152 native tests on both Python 3.10 and 3.12; CI passed for `0435f74`. These are historical results for that code. The newer task reviews above state their own exact heads and checks; none of these counts establishes the unfinished optimizer or gameplay gates.

## Blocker handling

Record a blocker with task ID, evidence, attempted route, exact missing decision/input and independent tasks that can continue. Automatic website access, real engine behavior and independent gameplay measurement cannot be replaced by mocks at their acceptance gates. A prototype can use mocks when its claims remain explicitly synthetic.

Do not assign calendar estimates before G0/G1 measurements and access studies. At each gate, the reviewer updates sequencing, task size and effort estimates based on evidence. Split a task into numbered child tasks if it contains more than one independently reviewable change; preserve the parent acceptance criteria.
