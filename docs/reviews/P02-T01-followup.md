# P02-T01 independent follow-up review

> Historical review of the commits named below. Current task state and follow-ups are on [GitHub Issues](https://github.com/kaporli/pob2-tools/issues/23); this snapshot is not a current assignment list.

## Review identity

- PR: [#4](https://github.com/kaporli/pob2-tools/pull/4), P02-T01 only, specification 1.0.
- Reviewed head: `5260237f4594bcceae5326ec297bef295791c04e`.
- Previous implementation: `eca7afe531345afbeb4bae311386abe25cd21593`.
- Reviewer/date: Codex, 2026-10-06. I did not write these implementation repairs.
- Verdict: **changes_required. Do not approve or merge this revision.**

The normal state-change path and fatal malformed-load recovery are repaired. Two acceptance gaps remain. Finding numbers below continue the repository's R01–R11 numbering in its submitted self-review.

## Findings

### P02-T01-R12 — P1: Invalidate reusable state after a partially applied failed request

Locations: [adapter.py](../../pob2-optimizer/pob2opt/evaluation/adapter.py), lines 378–384 (invalidation only when the handle dies), 469–472 (fresh-load state) and 504–513 (reuse and state application). [worker.py](../../pob2-optimizer/pob2opt/evaluation/worker.py), lines 141–147, applies configuration before selecting the main skill.

A fresh load records `_applied_state` as empty. If `OP_PRIMITIVES` sets some configuration and then fails, a nonfatal EngineError leaves the cached empty state intact even though PoB has already mutated. The next empty-state request therefore skips reloading and reads the partially changed engine. Updating `_applied_state` only after a successful reply is insufficient: the old cached value stops being trustworthy as soon as mutation begins.

Real-engine reproduction:

1. Evaluate the populated fixture with `EngineState()`; `TotalDPS` is `47.222385956304`.
2. Evaluate with `config={"enemyLevel": 120}` and `main_skill=(999999, 1)`. The config succeeds, then skill selection returns `internal_error` at `primitives:set_main_skill`.
3. Catch the error and evaluate the same build with `EngineState()` again.

The third request returns successfully with `document.reloaded=False`, an empty reported config and `TotalDPS=44.690258680949`. Thirty-eight output fields differ from the original baseline. An explicit document reload restores the original values. The repair thus still permits results whose declared state does not describe the actual engine state.

Required repair:

1. Mark cached state unknown before any operation that can mutate it. Publish a reusable document/state/generation tuple only after the complete operation succeeds.
2. On any state-application error, force the next evaluation to reload its exact document; terminating the worker is also acceptable where its health is uncertain. Do not limit invalidation to errors that already killed the worker.
3. Preserve the original error classification and generation handling. A successful retry must not require callers to reload manually.

Acceptance: add a real-engine regression for the sequence above, asserting restored baseline primitives within `1e-6` relative or `1e-9` absolute tolerance and truthful state/reload provenance. Add a stateful synthetic case that fails after its first mutation. Cover document defaults and main-skill restoration, and retain the repaired ordinary A-B-A and fatal-load recovery cases. Include failures during blank/exact loading wherever partial mutation can leave a previously cached load misleading.

### P02-T01-R13 — P2: Enforce one evaluation deadline across load and primitive stages

Location: [adapter.py](../../pob2-optimizer/pob2opt/evaluation/adapter.py), lines 496–514, especially the full `timeout_s` passed separately at lines 509 and 512.

The repair correctly applies the selected fidelity bound to a slow load. However, it then grants the primitives request another full bound. Adding `load_timeout_s` documents two allowances but does not satisfy interfaces.md's per-evaluation bound or the earlier request for a shared deadline.

Independent synthetic reproduction: finish worker startup first, configure a 1-second screening timeout, and delay loading and primitive evaluation by 0.6 seconds each. Both stages individually fit; the evaluation returns success after **1.203 seconds**, with `timeout_s=1.0`, `load_timeout_s=1.0` and `duration_ms=1202`. No startup or cleanup time is included. The submitted slow-load test cannot catch this because its first stage alone exceeds the limit.

Required repair: compute a monotonic evaluation deadline and pass the remaining time to each load, state/primitive and necessary identity request. Reject an exhausted budget before starting another stage. Keep separately configured startup and cleanup allowances explicit; do not redefine the evaluation timeout as a per-stage timeout without changing the contract through review.

Acceptance: under the existing independent supervisor, test two stages that individually fit but exceed the combined budget, as well as a slow load and a slow primitive stage. Expect a typed timeout, worker disposal and a fresh subsequent evaluation. Also retain a successful multi-stage case whose combined duration fits. Record the configured evaluation allowance consistently in the resulting evidence.

## Evidence inspected and reproduced

- Inspected the repair diff in adapter, protocol, checkout, documents and worker code, the revised handoff/self-review, lifecycle evidence and the expanded unit/engine cases against P02-T01 and interfaces.md.
- Narrow adapter and timeout-supervisor suites: **53 passed**, Python 3.12.4.
- `python -m pytest tests/unit tests/integration -q`: **622 passed, 5 xfailed**, Python 3.12.4.
- `.venv/pr2-validation/py310-a/Scripts/python.exe -m pytest tests/unit tests/integration -q`: **622 passed, 5 xfailed**, Python 3.10.22.
- With `POB2_ROOT` set to the separate checkout, `python -m pytest -m engine -q`: **46 passed, 1 xfailed, 627 deselected**, Python 3.12.4.
- `python scripts/generate_schemas.py --check`: **20 schemas match**.
- [CI run 37465872738](https://github.com/kaporli/pob2-tools/actions/runs/37465872738) reports successful offline Python 3.10 and 3.12 jobs at this exact head. Status inspected; hosted tests were not independently rerun.
- New [executable probe](../evidence/P02/review_5260237_probes.py) and [recorded results](../evidence/P02/review_5260237_probes.json). Set `POB2_ROOT` and run `python docs/evidence/P02/review_5260237_probes.py`.
- The real probes use PoB `ce566eac45ea8a86477f513c7ee65a1ebe60014e`, with the handoff's existing modified-checkout status hash. Values are PoB-derived results for synthetic fixture inputs, not gameplay measurements or a clean-checkout claim.

## Acceptance and prior-finding disposition

| Area | Disposition |
|---|---|
| Ordinary same-build state A-B-A | Independently reproduced as repaired: B differs and the final A exactly matches the original. |
| Fatal malformed load followed by primitives | Independently reproduced as repaired: a new PID returns the original level-28 character, 36 nodes, 1 item, 1 group and matching values. |
| Successful document-content changes under one build hash | Content identity is now part of load reuse; expanded submitted tests pass. |
| Failed state changes | Still fail isolation, R12; the state-isolation finding is only partially closed. |
| Evaluation budget | Slow individual loads are bounded; combined stages are not, R13. The deadline finding is only partially closed. |
| Parent cwd, initial exact/blank split and basic worker lifecycle | Existing and expanded regression suites pass. |

The previous independent review's fatal-load recovery finding is closed. Its broader state isolation and full evaluation deadline requirements remain open through R12/R13. The repository self-review's statement that all findings are closed does not establish task acceptance.

## Reassessment and final disposition

P02-T01 remains **changes_required**. G0 and P01 acceptance are unaffected, and G1 is not granted. Repair cache invalidation after partial failure first, then the shared deadline; rerun both interpreter lanes, the real-engine lane, and these adverse cases before another review. Ensure repaired behavior has an appropriate adapter version and regenerate affected lifecycle/cache evidence before downstream reuse.

P02-T02 investigation can continue, but production evaluation must not depend on this revision's results being independent of request history. Primitive semantics remain undeclared pending P02-T04; verified checkout content/pinning and patch profiles remain P02-T02; legality and export fidelity remain T03/T05. Real native crashes, concurrent workers and gameplay validation are not established by these tests. No user scope decision is needed to fix the two defects.

Only review documentation and evidence were written. No application changes, commit, push, GitHub review submission, approval or merge was performed. The pre-existing deleted submodule entry was preserved.
