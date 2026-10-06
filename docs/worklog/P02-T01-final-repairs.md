# P02-T01 final lifecycle repairs

- Task/specification: P02-T01, version 1.0.
- Starting implementation: `5260237f4594bcceae5326ec297bef295791c04e`.
- Author/date: Codex, 2026-10-06.
- Findings: P02-T01-R12 and R13 in the [independent follow-up review](../reviews/P02-T01-followup.md).

## Changes

R12: every mutating worker request invalidates the cached document/state before dispatch. Successful exact loads publish their known baseline; primitive evaluations publish reusable state only after reply validation, identity retrieval and deadline checks. A nonfatal failure during configuration, exact loading or blank creation therefore forces the next evaluation to load its document again. Fatal recovery and identical successful-request reuse remain supported.

R13: worker startup completes under its separate startup allowance. A single monotonic deadline then covers document loading, state/primitive work and any identity request. Each stage receives only the remaining allowance; late success is rejected, and timeout disposes of the worker. `PrimitiveSnapshot.timeout_s` is the total evaluation allowance; `load_timeout_s` is the remaining portion when loading starts, not extra time. Cleanup retains the existing bounded taskkill/join grace.

The adapter version is now **p02-t01.2**. Do not reuse evaluations produced under p02-t01.1 as results from this implementation. Record schemas, migrations, game rules, legality and primitive semantics are unchanged.

## Regression coverage

- Stateful synthetic worker fails after mutation during primitives, exact load and blank creation. The next evaluation restores configuration and selected-skill defaults without caller-issued reloads.
- Real PoB fails after changing enemy level but before completing skill selection. Both the original document and a document with a non-default enemy level recover their exact baseline values and character summary.
- Independent process supervisor covers combined-stage overrun, slow loading, slow primitive calculation, slow identity retrieval, a wedged load and a successful request that fits the shared budget. Every timeout case verifies worker disposal and successful evaluation in a new process.
- Existing ordinary A-B-A, repeated-request reuse, fatal malformed-load recovery and process-death tests remain in the suites.

## Validation and artifacts

- `python -m pytest tests/unit/test_p02_t01_adapter.py tests/unit/test_p02_t01_timeout_supervisor.py -q`: 62 passed.
- `python -m pytest tests/unit tests/integration -q`: 631 passed, 5 xfailed (Python 3.12.4).
- `.venv/pr2-validation/py310-a/Scripts/python.exe -m pytest tests/unit tests/integration -q`: 631 passed, 5 xfailed (Python 3.10.22).
- With `POB2_ROOT` set, `python -m pytest tests/engine/test_p02_t01_engine_adapter.py -q`: 16 passed.
- With `POB2_ROOT` set, `python -m pytest -m engine -q`: 48 passed, 1 xfailed, 636 deselected.
- `python scripts/generate_schemas.py --check`: 20 schemas match.
- [Independent probes after repair](../evidence/P02/repair-r12-r13-probes.json): zero changed keys after failed state application; a combined evaluation with a one-second budget now raises timeout, including roughly 0.094 seconds of cleanup. The [original failing results](../evidence/P02/review_5260237_probes.json) remain unchanged.
- `python scripts/p02_t01_evidence.py --out docs/evidence/P02/lifecycle.json`, with `POB2_ROOT` set: regenerated [lifecycle evidence](../evidence/P02/lifecycle.json) at adapter version p02-t01.2; A-B-A compares 675 keys with zero difference.
- `git diff --check`: passed.

Evidence is synthetic or PoB-derived for synthetic fixtures, not gameplay measurement. Engine checks use the existing separate PoB ce566ea checkout with its previously recorded dirty status. Full engine-suite outcome and the reviewed implementation commit are recorded in the final repair verification.

## Remaining scope

Only P02-T01 acceptance is requested. Content-level engine pinning and patch profiles remain T02, legality T03, primitive units/ownership T04 and export fidelity T05. Concurrent workers, actual native crashes and end-to-end gameplay accuracy are not established here. No owner preference or contract change is required for these repairs.
