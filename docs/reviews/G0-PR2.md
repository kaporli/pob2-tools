# G0 correction review — PR #2

## Review identity

- Task/gate: P00 correction delivery; G0-R01 through G0-R06.
- Specification: 1.0.
- PR: https://github.com/kaporli/pob2-tools/pull/2
- Base: `e3ee6de8c7b08da708a25bd5a703efcf49d65f2c`.
- Reviewed head: `089e065e2e0ceb8c6be9efa71e3726d51aa0ce8a`.
- Reviewer/date: Codex, 2026-10-04.
- Verdict: **changes_required; do not merge this revision yet**.
- Previous review: [G0](G0.md). Machine-readable evidence: [review-089e065.json](../evidence/P00/review-089e065.json).

## Findings

### PR2-R01 — P2: Resolve dependency markers for the target interpreter

Location: [scripts/lock_dependencies.py](../../scripts/lock_dependencies.py), lines 63–79; install/check steps in [.github/workflows/offline-tests.yml](../../.github/workflows/offline-tests.yml), lines 53–65.

The Python 3.10 lock is still incomplete. The generator runs pip under `sys.executable` and uses cross-target wheel options to generate both locks. Those options have not made dependency marker evaluation match Python 3.10: its lock omits `exceptiongroup` and `tomli`, which are active dependencies below Python 3.11. Evaluating the installed pytest/anyio metadata with a Python 3.10 Windows marker environment independently confirms the omissions.

This is observable in the PR's actual [Python 3.10 CI log](https://github.com/kaporli/pob2-tools/actions/runs/37206558162/job/111448840768): pip downloads and installs **exceptiongroup 1.3.1** and **tomli 2.4.1** outside the checked-in pins. The job passes because dependency resolution remains enabled. `pip check` checks compatibility, not whether every installed dependency was locked, and `--check` repeats the same incomplete resolution on Python 3.12. Later installs can therefore select different versions with an unchanged lock. G0-R05 remains open; this does not invalidate the successful Python 3.10 compatibility run for G0-R01.

Required change and acceptance:

1. Generate each lock using its actual supported interpreter on Windows, or a resolver demonstrated to evaluate all dependency markers against the target environment. Do not fix only these two names by hand while retaining the faulty generator.
2. In clean Python 3.10 and 3.12 environments, install the locked runtime/test distributions with dependency resolution disabled, then install the two editable project packages without resolving additional runtime dependencies. Keep the documented bootstrap/build-tool exception explicit.
3. Run `pip check` and compare the installed runtime/test distribution names and versions against the applicable lock. Account explicitly for the two editable projects and bootstrap tooling. An omitted active transitive dependency must make CI fail rather than be fetched silently.
4. Regenerate from scratch and confirm that Python 3.10 includes the conditional dependencies. Retain two-clean-install package inventories per supported interpreter, as required by G0-R05.

### PR2-R02 — P2: Supply valid fixtures to the new repair expectations

Location: [tests/unit/test_f05_run_identity_and_assumptions.py](../../tests/unit/test_f05_run_identity_and_assumptions.py), lines 156–160 and the four repaired-behavior tests below them.

`BASE_REQUEST` omits ten keys explicitly required by [interfaces.md](../specs/interfaces.md): `scenario_suite`, `catalog_profile`, `corpus_path`, `item_pool_ids`, `time_budget_s`, `workers`, `memory_limit_mb`, `allow_weapon_switch`, `allow_external_gear_swap`, and `execution_profile`. A P08 implementation that correctly validates the request will reject every one of these tests before it reaches cache identity, league resolution, budget derivation or candidate-limit behavior. Their unrestricted `xfail(strict=True)` markers accept that unrelated exception too; strict mode only detects an unexpected pass.

Independent reproduction: substitute a synthetic `prepare` which enforces exactly the documented required keys. All four tests stop with `ValidationError: 'scenario_suite' is a required property`, before the relevant assertions. This is evidence about the submitted test inputs, not a claim that the future production schema or prepare service already exists.

Required change and acceptance:

1. Supply a complete request using the documented offline example as the field checklist. Provide deterministic local catalog/profile, scenario, corpus, item-pool and league-resolution fixtures; merely adding paths to nonexistent data is insufficient.
2. Separate missing-implementation expectations from behavior assertions so schema, fixture and dependency failures cannot be reported as the intended repair failure. Until the service exists, an explicitly scoped missing-service expectation is acceptable; once it exists, input validation must pass independently and unexpected exceptions must fail.
3. Demonstrate that a contract-compliant synthetic prepare service can reach and satisfy each behavior assertion, and that deliberately wrong cache identity, unresolved league, untraceable budget and ignored candidate limit are rejected. These doubles validate the test contract only; full production coverage remains P02/P08 work.
4. Apply the same valid-input rule to the new cwd test at [test_f10_engine_lifecycle_contract.py](../../tests/unit/test_f10_engine_lifecycle_contract.py), line 105: `primitives(build=None, state=None, profile=None)` does not establish that an actual evaluation leaves the parent cwd unchanged.

G0-R06 is improved in direction, but is not closed: permitted legacy implementation details are no longer forbidden, while valid future implementations can still fail the new expectations for unrelated reasons.

## Evidence inspected and reproduced

| Check | Result |
|---|---|
| Local `python -m pytest tests/unit tests/integration -ra` | 91 passed, 13 xfailed; exit 0. |
| Local `python -m pytest -m engine -ra`, with `POB2_ROOT=C:/Users/Elias/PycharmProjects/PathOfBuilding-PoE2` | 30 passed, 4 xfailed, 104 deselected; exit 0; 55.21 seconds. |
| Real-engine diagnostics redirection | 38,958,382-byte log retained under pytest temporary storage; the terminal reports its path. |
| GitHub Actions run `37206558162`, reviewed head | Windows Python 3.10 and 3.12 jobs both succeeded. Reviewed logs directly, including the unpinned 3.10 installations. |
| Independent target-marker check | pytest requires exceptiongroup and tomli on Python 3.10; anyio also requires exceptiongroup; both missing from that lock. |
| Independent request-validation challenge | All four revised F05 expectations fail input validation before reaching their intended assertions. |
| Doctor and skip-guard regressions | Included in the passing local suite: malformed/mismatched PE, obstructed paths, and guard rejection of error/failure/empty/unrelated-skip outcomes. |

The local interpreter is Python 3.12.4. Python 3.10 execution evidence comes from the actual CI job, not a local installation. The engine checkout is the separately available PoB checkout identified by the delivery as `ce566eac45ea8a86477f513c7ee65a1ebe60014e`. The pre-existing deleted submodule working-tree entry was preserved. No application code was changed, no PR review was posted, and no merge was performed.

The updated measurement script and artifact were inspected; the full measurement campaign and two-clean-install claim were not independently rerun in this review. Engine tests establish characterization behavior, not current-patch gameplay correctness or optimization quality.

## Acceptance mapping

| Previous finding | Disposition | Reason |
|---|---|---|
| G0-R01: Python 3.10 compatibility | accepted | The compatible rpds-py pin and real 3.10 CI run address the incompatible dependency. |
| G0-R02: CI ignores pytest errors | accepted | Exit status is preserved and required to be zero; JUnit checks and regression cases address the reported failure. |
| G0-R03: run path obstruction | accepted | Leaf and intermediate regular files now block run output. |
| G0-R04: invalid/mismatched DLL | accepted for the requested header/architecture diagnostic scope | Malformed, unknown and mismatched architectures block engine capability; this does not prove that a DLL will successfully load. |
| G0-R05: complete dependency locking | changes_required | PR2-R01; CI installs dependencies missing from the lock. |
| G0-R06: architecture-aligned repair tests | changes_required | PR2-R02; new tests still cannot accept a validating implementation using the submitted inputs. |

The smaller corrections generally address the previous feedback: warm reset loads both helper files, the script resolves its path before engine startup, measurement provenance was added, historical auto-mode claims were narrowed, delivery references were added, and native diagnostic noise is retained without flooding the terminal. The limits of the socket/collection checks are now stated accurately.

One follow-up for the lifecycle harness: the new timeout test calls potentially non-returning code directly and checks elapsed time only afterward (lines 121–125). Before exercising a real worker, supervise the probe in a separate process with a hard outer deadline and child cleanup. Keep synthetic worker tests runnable without PoB; real Lua execution belongs in the engine lane. `evaluate_raw` is a proposed test seam rather than a required public interface in the spec.

## Reassessment and final disposition

P00-T03's reported diagnostic defects are resolved. P00-T01/P00-T05 still need complete dependency-lock enforcement, and P00-T04 needs valid acceptance fixtures. G0 remains `changes_required`; there is no previously accepted G0 to invalidate. No product contract or Python support policy needs changing.

Correct PR2-R01 and PR2-R02, attach refreshed per-interpreter evidence, and request another review before merge. P01-T01 design and isolated work can continue, but do not claim dependency-approved completion until G0 is accepted. No owner preference decision is needed for these corrections.
