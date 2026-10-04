# Implementation handoff

## Identity

- Task IDs: G0-R01 through G0-R06 plus the five smaller corrections in [docs/reviews/G0.md](../reviews/G0.md)
- Specification version: 1.0
- Engineer: Claude (assistant), on behalf of Elias
- Starting commit: `9d58905` (the reviewed delivery)
- Implementation commit or working-tree diff reference: branch `g0-corrections`
- Status: review_ready
- Dependencies and their accepted review records: P00-T01 through P00-T05, reviewed at `9d58905`, verdict `changes_required`

## Implemented behavior

Every finding in the review is addressed. Nothing in the optimizer was rewritten
and no characterization work was rolled back, as the review's reassessment
directed. Grouped the way the review suggested.

### G0-R01 and G0-R05: dependency set and locking

`requirements-dev.txt` pinned a hand-maintained subset of transitives. It was
incomplete, and it carried `rpds-py==2026.6.3`, which requires Python 3.11, so a
clean 3.10 install could not satisfy the file the project told people to use.

- `requirements-dev.txt` now declares **only** direct dependencies.
- `scripts/lock_dependencies.py` resolves them per supported interpreter with
  pip's own resolver and writes `requirements/lock-py310-win_amd64.txt` and
  `requirements/lock-py312-win_amd64.txt`. 39 packages each. They differ in
  exactly one: `rpds-py` is `0.30.0` on 3.10 and `2026.6.3` on 3.12.
- The generation command is recorded in both files and in
  `requirements-dev.txt`. `--check` fails if a lock is stale, and CI runs it.
- The direct pins did not have to move. The minimum Python was not raised.
- Editable installs now take `-c <lock>` so the second install cannot drift the
  environment the first established.
- pip, setuptools and wheel are deliberately not locked, because they bootstrap
  the install. The lock files say so rather than implying they are covered.

### G0-R02: the CI guard accepted a failing run

Reproduced first. A pytest run with a deliberately broken fixture produced
`2 skipped, 1 error` and exit 1, and the previous guard's three conditions all
passed, because it matched console prose and discarded the exit status with
`|| true`.

- `scripts/check_engine_skips.py` reads the JUnit report and the exit code. It
  requires exit 0, zero errors, zero failures, at least one collected case,
  every case skipped, and every skip message carrying the missing-runtime
  reason, so an xfail cannot stand in for a skip.
- The workflow captures the exit code properly and calls the script.
- `tests/unit/test_engine_skip_guard.py` is the regression test the review asked
  to preserve: 14 cases covering the fixture error, a failing test, a collection
  error, an empty selection, exit 5, an interrupt, a test that actually ran, an
  xfail posing as a runtime skip, an unrelated skip, a missing report, an
  unparsable report and a report with no testsuite.

### G0-R01 again: supported interpreters are exercised

The workflow is now a 3.10 and 3.12 matrix on `windows-latest`. Each installs
from its own lock, runs `pip check`, and runs the offline groups. 3.12 also runs
the lock freshness check.

### G0-R03: run paths obstructed by a regular file

`_nearest_existing` skipped over a file and reported its writable parent, so
`--run-root <file>` and `--run-root <file>/child` both returned `ok`.
`_obstructing_component` now inspects the requested path and every existing
ancestor; any existing non-directory component is `incompatible` and blocks
`runs`. No directory is created to find this out. `os.access` is now described
as a permission indication, in the summary and in the report data.

### G0-R04: invalid or incompatible DLLs

`_pe_machine` returned `unknown` for anything it could not parse and the check
returned `ok` for every architecture outside the x86/x64 pair, so nine bytes of
text passed and so did an ARM64 header on an x64 process.

- `_pe_machine` now distinguishes `invalid` (not a readable PE binary, which
  disproves usability) from an unrecognized machine value (which only fails to
  establish it), and handles truncation at each read.
- `host_machine()` maps the running interpreter to an architecture name, and the
  check compares against that rather than pointer width.
- `invalid` is `incompatible`; an unrecognized machine or an unrecognized host is
  `unknown`. All of them block `engine`.

### G0-R06: repair expectations realigned

The F10 and F05 "repaired behaviour" tests asserted implementation text and API
shape the specification does not require, so a valid repair could stay xfailed
and a superficial one could pass.

- F10's repaired tests now target the `EngineAdapter` boundary P02-T01 promises:
  the **parent** working directory is unchanged (a worker that chdirs internally
  is explicitly accepted), a wedged request returns a typed `timeout` **within
  its bound** (an unenforced parameter does not satisfy it), and a failed worker
  is replaced by a different one that completes the next request.
- F05's repaired tests now target the P08-T01 run manifest: two different
  requests get different cache identities and an identical request reproduces
  its own, `current` is resolved to an immutable league id, point budgets carry
  `source: catalog` and a catalog hash, and the finalist limit comes from the
  request.
- The source-level checks are kept and relabelled as legacy characterization,
  with the docstrings saying the legacy path may keep its literals.
- `test_point_budgets_are_not_derived_from_a_catalog` asserted that the string
  "catalog" was absent from the whole module, which a harmless comment would
  have broken. It now checks only that the budget expressions depend on
  `args.level` and nothing else.

### Smaller corrections

1. `scripts/measure_engine.py` reloads **both** `opt_helpers.lua` and
   `tree_lib.lua`, as `Worker.reset()` does. The warm-reset median moved from
   0.133 s to 0.154 s, which is the honest figure. `--pob-root` is resolved to an
   absolute path before the engine starts. The artifact now records the PoB
   commit, branch, tracked-tree dirty state, untracked file count, a UTC
   timestamp and the SHA-256 of every fixture input.
2. The auto-mode claim is corrected. The four build files' present contents do
   not establish what they held when the unmanifested runs were made, so
   `findings.md` now says "not reproduced against the currently inspected source
   files" and "not determinable for the historical runs".
3. Each P00 worklog now carries the delivered commits, the reviewed commit, its
   first-round verdict and a link here.
4. The noise description was wrong by three orders of magnitude. Measured
   unfiltered: 6984 banners, 265 790 traceback frame lines, 286 749 console
   lines for one engine session, exit 0 throughout. The earlier figure came from
   output already filtered through `grep -v` and `tail`. `faulthandler` is now
   redirected to a per-session log rather than disabled, and
   `pytest_terminal_summary` prints its path and size. Console output dropped to
   9 lines with all 32 187 121 bytes preserved and the exit code unaffected.
5. The socket guard's real scope is documented where it lives: autouse, so test
   execution only, not import or collection; this process only, not
   subprocesses; `socket` only. The collection check's docstring now says that
   inspecting PoB's banners shows the engine did not start and is not proof that
   collection made no network call, and that both need strengthening at P03.

## Acceptance evidence

| Criterion from the review | Command or artifact | Result |
|---|---|---|
| G0-R01 dependency set installable on 3.10 | `requirements/lock-py310-win_amd64.txt` carries `rpds-py==0.30.0`; resolution performed by pip for `--python-version 3.10` | passed |
| G0-R01 clean install, `pip check`, tests on each interpreter | 3.12 verified locally in an empty venv; 3.10 runs in the CI matrix | 3.12 passed locally; **3.10 is CI-only, see Deviations** |
| G0-R01 interpreter-specific dependency evidence retained | two lock files, both committed | passed |
| G0-R02 require pytest exit 0 | `scripts/check_engine_skips.py` | passed |
| G0-R02 JUnit counts over console prose | same | passed |
| G0-R02 at least one case collected, all skipped for the intended reason | same | passed |
| G0-R02 unexpected xfails do not count | `test_an_xfail_is_not_accepted_as_a_runtime_skip` | passed |
| G0-R02 normal invocation passes | guard run against the real missing-runtime report: 34 collected, all skipped | passed |
| G0-R02 injected fixture error fails | end-to-end reproduction, see below | passed |
| G0-R02 failing test, collection error, no selected tests, interrupt all fail | `tests/unit/test_engine_skip_guard.py` | passed |
| G0-R02 regression test of the guard preserved | `tests/unit/test_engine_skip_guard.py`, 14 cases | passed |
| G0-R03 file at leaf, file at intermediate, writable dir, valid nonexistent child | four cases in `tests/unit/test_doctor_checks.py` | passed |
| G0-R03 first two block `runs` and give exit 3 | asserted in both cases | passed |
| G0-R03 `os.access` described as an indication | `writable_is_an_indication_only` in the report data and in the summary | passed |
| G0-R04 malformed/truncated PE, x86 on x64, ARM64 on x64, supported x64 | five cases in `tests/unit/test_doctor_checks.py` | passed |
| G0-R04 invalid/unknown never report engine readiness | each case asserts `incompatible` or `unknown` plus `engine` blocked | passed |
| G0-R04 no DLL loaded during the diagnostic | `test_the_diagnostic_never_loads_a_library` patches `ctypes.CDLL`/`WinDLL` to raise | passed |
| G0-R06 reject a fake fix that adds an unenforced timeout | the timeout test asserts a typed `timeout` result and a wall-clock bound | passed |
| G0-R06 accept worker isolation with internal chdir | the cwd test asserts the parent only, and says so | passed |
| G0-R06 a comment mentioning `catalog` or a display slice is not a regression | the module-wide string assertion is gone | passed |
| Smaller 1: measure the actual reset | both helper files reloaded; median 0.154 s | passed |
| Smaller 1: absolute `--pob-root`, provenance in the artifact | `measurements.json` | passed |
| Smaller 2: historical auto-mode wording | `findings.md` | passed |
| Smaller 3: delivered-commit reference | five worklogs | passed |
| Smaller 4: noise description corrected | `findings.md`, `tests/MANIFEST.md` | passed |
| Smaller 5: guard scope stated | `tests/unit/conftest.py`, `test_collection_is_offline.py` | passed |

Suite results after the corrections:

| Command | Result |
|---|---|
| `python -m pytest` (no `POB2_ROOT`) | 91 passed, 34 skipped, 13 xfailed |
| `python -m pytest` (with `POB2_ROOT`) | 121 passed, 17 xfailed |
| `python -m pytest tests/unit` | 86 passed, 12 xfailed |
| `python -m pytest -m engine` (with `POB2_ROOT`) | 30 passed, 104 deselected, 4 xfailed |
| Clean 3.12 venv from the lock, then `pip check` and `pytest tests/unit tests/integration` | no broken requirements; 66 passed, 13 xfailed |
| Two clean installs from the same lock | identical package versions |

## Reproduction

```
python scripts/lock_dependencies.py --check

python -m venv .venv-check
.venv-check\Scripts\python -m pip install -r requirements/lock-py312-win_amd64.txt
.venv-check\Scripts\python -m pip install -c requirements/lock-py312-win_amd64.txt -e ./pob2-mcp -e ./pob2-optimizer
.venv-check\Scripts\python -m pip check
.venv-check\Scripts\python -m pytest tests/unit tests/integration -q

python -m pytest -m engine -q --junitxml=engine-junit.xml
python scripts/check_engine_skips.py --exit-code 0 --junit engine-junit.xml
```

The end-to-end guard reproduction, which does not touch this repository's tests:

```
mkdir guardrepro && cd guardrepro
# conftest.py with one fixture that skips with the runtime reason and one that
# raises RuntimeError; a test module with two of the first and one of the second
python -m pytest -m engine -ra --junitxml=j.xml      # -> 2 skipped, 1 error, exit 1
python <repo>/scripts/check_engine_skips.py --exit-code 1 --junit j.xml
```

Observed: the old guard's conditions all pass on that run; the new guard exits 1
with "pytest exited 1; a clean all-skipped run exits 0".

## Adverse cases

Exercised: a nine-byte non-PE file as `lua51.dll`; a PE truncated mid-header; an
ARM64 PE on an x64 host; an x86 PE on an x64 host; an unrecognized COFF machine
value; a run root that is a file; a file as an intermediate path component; a
pytest run with a fixture error, a failing test, a collection error, an empty
selection, an interrupt and an xfail standing in for a skip; a stale lock file;
two independent clean installs.

Untested: the 3.10 lock installed on a real 3.10 interpreter outside CI; a
non-Windows host; an ACL-only read-only directory; an ARM64 Windows host, where
`host_machine()` would return `arm64` and the sense of two tests inverts, which
they handle but which has not been run.

## Artifacts and provenance

| Artifact | Kind |
|---|---|
| `requirements/lock-py310-win_amd64.txt`, `lock-py312-win_amd64.txt` | Resolved by pip against PyPI on 2026-10-04 |
| `docs/evidence/P00/measurements.json` | Remeasured on this machine, PoB `ce566ea`, now with checkout and fixture provenance |
| Noise counts (6984 / 265 790 / 286 749) | Counted from an unfiltered engine run on this machine |
| `tests/unit/test_engine_skip_guard.py` XML | Synthetic, shaped like pytest's output |

## Deviations and unresolved questions

1. **3.10 is verified in CI, not locally.** This machine has only 3.12.4 and
   installing a second interpreter is outside the repository. The lock for 3.10
   was produced by pip resolving explicitly for `--python-version 3.10`, which
   establishes satisfiability but not a successful run. The CI matrix exercises
   the real install and test run. If the reviewer wants local 3.10 evidence,
   that needs an interpreter installed on this machine first.
2. **The locks pin to what PyPI offered on 2026-10-04.** They are reproducible
   going forward, but regenerating later will move versions. `--check` makes
   drift visible rather than silent.
3. **`--only-binary=:all:`** is used when resolving, so a dependency that ships
   only an sdist would not be locked. None of the current set does.
4. **P00-OBS-02's historical scope stays undetermined.** The corrected wording
   records that, and the unmanifested runs cannot be re-attributed now.
5. **The fault log is written under pytest's tmp directory**, so it is removed by
   pytest's own retention policy after a few runs. If a reviewer wants it kept
   with the evidence bundle, that is a one-line change to the path.
6. The reviewer's observation that the engine run emitted far more noise than
   the handoff claimed is accepted in full, and the original claim is marked as
   wrong in `findings.md` rather than quietly replaced.

## Request for review

Requested verdict: `accepted` for G0-R01 through G0-R06 and the five smaller
corrections, and re-review of P00-T01, P00-T03, P00-T04 and P00-T05, whose
first-round verdicts were `changes_required`.

G0 is **not** claimed. The review's condition stands: 3.10 evidence comes from
the CI matrix on this PR, and the reviewer should confirm that lane before
treating the interpreter question as closed.

Next task proposed: P01-T01, after G0.
