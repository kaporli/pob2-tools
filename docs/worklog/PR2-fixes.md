# PR #2 review corrections

## Identity

- Task IDs: PR2-R01 / G0-R05 and PR2-R02 / G0-R06; P00-T01/T04/T05.
- Specification version: 1.0.
- Engineer: Codex, at Elias's request to implement and push the fixes.
- Starting commit: `089e065e2e0ceb8c6be9efa71e3726d51aa0ce8a`.
- Implementation commit: `e0aa81d7c80170911f7f2ead66ed7d023a443ddc`.
- Follow-up verdict and hosted CI: [G0-PR2-fixes.md](../reviews/G0-PR2-fixes.md).
- Status: review_ready.
- Dependencies: [PR #2 review](../reviews/G0-PR2.md); no product scope change.

## Implemented behavior

The dependency generator now runs once under each native Windows x64 interpreter.
The Python 3.10 lock contains all 41 resolved distributions, including exceptiongroup
and tomli; Python 3.12 contains 39. Regeneration remains an explicit network action.
`--check` now audits the installed environment offline against direct pins and the
complete lock, rejects missing/extra/wrong versions, and runs `pip check`.

CI creates two clean venvs per interpreter, installs only the locked runtime/test
distributions with `--no-deps`, installs editable projects with `--no-deps
--no-build-isolation`, audits both inventories and compares them. It uploads both
inventories. pip/setuptools/wheel remain explicit unpinned bootstrap/build tools.
The test lane runs from the first audited venv. Setup documentation was updated.

The F05 repair probes now use complete offline requests and materialized synthetic
catalog/profile/scenario/corpus/item/league snapshots. Positive and deliberately
broken test doubles exercise their assertions. Their observation format is only
a test projection, not a required production return type. Invalid inputs and
missing files raise ordinary errors instead of becoming expected failures.

The premature production F05/F10 calls have been replaced with narrowly scoped
missing-service checks. Only a genuinely absent module gets the expected-failure
exception. Once either future service exists, its check fails until the owner binds
real acceptance tests to accepted P01 records. No None build records, assumed
`evaluate_raw` API or unbounded Lua loop remain in the offline unit suite.

## Acceptance evidence

| Criterion | Command/artifact | Result |
|---|---|---|
| Native marker resolution | Run `scripts/lock_dependencies.py` with native 3.10.22 and 3.12.4 | 41/39 distributions; conditional 3.10 dependencies present. |
| Two reproducible installations per interpreter | `docs/evidence/P00/pr2-fixes/inventory-py*-*.json` | Both pairs identical; all four installed without dependency resolution and passed `--check` / `pip check`. |
| Offline suite on both interpreters | `python -m pytest tests/unit tests/integration -q` | 116 passed, 8 expected failures on each. |
| Combined real-engine and offline suite, clean 3.12 venv | Set POB2_ROOT, then `python -m pytest -ra` | 146 passed, 12 expected failures; exit 0. |
| Original omission fails closed | Remove tomli/exceptiongroup from a scratch lock and isolated 3.10 installation; run audit | Exit 1; pip check identifies all three unsatisfied dependency edges. |
| Good/wrong synthetic prepare behavior | `tests/unit/test_f05_run_identity_and_assumptions.py` | Good behavior accepted; wrong cache, league, budget and limit rejected. |
| Unrelated failures remain visible | `tests/unit/test_repair_bindings.py`, validation and missing-snapshot cases | Broken imports/input/files cannot become missing-service xfails. |

## Reproduction

From the repository root, for each native CPython 3.10/3.12 interpreter, create
and activate an empty venv and run (select its matching lock):

```powershell
python -m pip install --upgrade pip setuptools wheel
python -m pip install --no-deps -r requirements/lock-py310-win_amd64.txt
python -m pip install --no-deps --no-build-isolation -e ./pob2-mcp -e ./pob2-optimizer
python scripts/lock_dependencies.py --check --inventory inventory.json
python -m pytest tests/unit tests/integration -q
```

Repeat in another empty venv; compare inventory JSON. The workflow does this on
both interpreters. To regenerate, run `py -3.10 scripts/lock_dependencies.py` and
`py -3.12 scripts/lock_dependencies.py` (or the actual executable paths). Do not
cross-resolve with `--python-version`.

For engine checks, set `POB2_ROOT` to the existing checkout at `ce566ea` and run
`python -m pytest -ra`. No live provider credential is needed. A repo-local
uv-managed 3.10.22 under ignored `.venv/` supplied the second interpreter here;
system Python and global editable installs were left alone.

## Adverse cases

Confirmed the exact missing-transitive defect fails even when installed inventory
matches the incomplete scratch lock. Also tested unexpected installed packages,
missing/wrong versions, changed direct pins, unsupported pin syntax, duplicate
pins and attempts to generate a Windows lock on another platform.

Production worker lifecycle behavior is still P02 work. The explicit follow-up
cases in `tests/MANIFEST.md` require valid inputs, worker-only cwd changes, a hard
outer timeout with process-tree cleanup, and worker replacement after death.
These were not falsely counted as implemented features.

## Artifacts and provenance

Durable evidence is under `docs/evidence/P00/pr2-fixes/`: four inventories, the
negative dependency-check output and a machine-readable validation summary.
The prepare snapshots are generated test-double data. The full-suite result
includes actual PoB characterization, not gameplay validation. Original review
artifacts are retained unchanged for the reviewed starting revision.

## Deviations and unresolved questions

The original PR prescribed speculative production request/return types before P01
schemas exist. Those calls were removed instead of fabricating normalized records.
P00 now proves its synthetic oracles and tracks missing production bindings;
P02/P08 must supply full production coverage. No feature is claimed from doubles.

No game rule, objective, public interface or release threshold changed. The
meaning of the development-only `--check` switch is now installed-lock validity,
not equality to whatever versions the package index offers today.

## Request for review

Review closure of PR2-R01/PR2-R02 and acceptance of G0 for P00 foundation scope.
Confirm the pushed revision's Windows 3.10/3.12 CI before approval and merge.
Next task after G0 acceptance: P01-T01. This handoff does not approve its own merge.
