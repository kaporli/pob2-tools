# Test manifest

What each group of tests is, what it needs, and the exact command to run it
(P00-T05). Run everything from the repository root.

## Prerequisites

Install from the lock for your interpreter, then the two packages under that
same lock as a constraint:

```
python -m pip install -r requirements/lock-py312-win_amd64.txt
python -m pip install -c requirements/lock-py312-win_amd64.txt -e ./pob2-mcp -e ./pob2-optimizer
```

Use `lock-py310-win_amd64.txt` on Python 3.10. The constraint on the second
command is what stops it from drifting the environment the first one
established; `python -m pip check` confirms the result.

The second line also matters for a different reason: if the packages are
installed editable from another checkout, `tests/unit/test_import_provenance.py`
fails on purpose. See `docs/evidence/P00/environment.md`.

`requirements-dev.txt` holds only the direct dependencies. Regenerate both locks
after changing it with `python scripts/lock_dependencies.py`.

Check the environment before blaming a test:

```
python -m pob2opt.cli doctor --json
```

Exit `0` means every blocking check passed. Exit `3` means a missing dependency
- read `summary.blocked_capabilities` to see which capability it takes out.

## Groups

| Group | Command | Needs | Notes |
|---|---|---|---|
| Offline unit | `python -m pytest tests/unit` | Nothing beyond the dev install | Outbound sockets are blocked for the whole directory by `tests/unit/conftest.py`. |
| Local integration | `python -m pytest tests/integration` | `luajit` on `PATH` | Skips with a reason when absent. No network, no PoB. |
| Engine | `python -m pytest -m engine` | A PoB2 checkout and its LuaJIT runtime | Skips with a reason when absent. A skip is **not** an engine pass. |
| Everything selectable by default | `python -m pytest` | As above | Excludes `network` and `longrun`. |
| Measurements | `python scripts/measure_engine.py --out docs/evidence/P00/measurements.json` | A PoB2 checkout | Not a test; writes evidence. |
| Lock freshness | `python scripts/lock_dependencies.py --check` | Network | Fails if a lock is stale against `requirements-dev.txt`. |
| Engine skip guard | `python scripts/check_engine_skips.py --exit-code N --junit engine-junit.xml` | Nothing | What CI uses to decide that engine tests skipped for the right reason. |

Selecting the PoB checkout:

```
# PowerShell
$env:POB2_ROOT = "C:\path\to\PathOfBuilding-PoE2"
# Git Bash
export POB2_ROOT=/c/path/to/PathOfBuilding-PoE2
```

Without `POB2_ROOT` the `external/PathOfBuilding-PoE2` submodule is used.

## Markers

| Marker | Meaning | Selected by default |
|---|---|---|
| `engine` | Needs a real PoB checkout and runtime | Yes - so its absence shows as an explicit skip |
| `network` | Contacts an external provider | No |
| `longrun` | Takes minutes or more | No |

`addopts` in `pytest.ini` carries `-m "not network and not longrun"`. A `-m` on
the command line replaces it, so `python -m pytest -m engine` runs only engine
tests and `python -m pytest -m network` would run only network tests (there are
none yet).

## What each file covers

### `tests/unit` - no PoB, no network

| File | Covers |
|---|---|
| `test_doctor_checks.py` | P00-T03 acceptance: missing directory, missing DLL, incompatible profile, valid offline environment, no secrets in output, no working-directory change, no run directory created, paths with spaces, exit codes 0/2/3. |
| `test_import_provenance.py` | The suite exercises this working tree, not an installed copy. |
| `test_collection_is_offline.py` | Collection does not boot PoB; no stray test module outside `tests/`. |
| `test_fixture_manifest.py` | Fixture inventory, hashes and synthetic labelling are accurate. |
| `test_fixture_oracles.py` | The synthetic search and combat oracles agree with themselves. |
| `test_f02_rotation_penalties.py` | Research F02, via a synthetic worker double through the real `task_tier`. |
| `test_f05_run_identity_and_assumptions.py` | Research F05: phase cache identity, hardcoded league, point-budget guesses, literal result caps. |
| `test_f10_engine_lifecycle_contract.py` | Research F10 at the API surface: `chdir`, no teardown, no timeout, undifferentiated errors. |
| `test_f11_worker_wipes_imported_build.py` | Research F11, via a recording engine double. |
| `test_f12_item_conversion_source.py` | Research F12 from the handler source. |
| `test_engine_skip_guard.py` | The CI engine-skip guard rejects a fixture error, a failing test, a collection error, an empty selection, an interrupt, a test that actually ran, and an xfail posing as a runtime skip. |

### `tests/integration` - local tools, still no PoB and no network

| File | Covers |
|---|---|
| `test_f12_item_conversion_luajit.py` | Runs the real `convert_trade_item` handler under a stock LuaJIT via `lua/convert_probe.lua`. |

### `tests/engine` - requires the PoB runtime

| File | Covers |
|---|---|
| `test_engine_smoke.py` | The assertion-based replacement for the removed `pob2-mcp/test_engine.py`. |
| `test_engine_build_inputs.py` | Legitimate zero full-DPS versus malformed build input (observation P00-OBS-01). |
| `test_f10_engine_state.py` | Working-directory leak and A-B-A stability in the live engine. |
| `test_f11_import_is_wiped.py` | What survives `load_build_xml` + `OPT_setup` (and observation P00-OBS-02). |
| `test_f12_item_conversion_golden.py` | The same conversion inside the pinned engine, and what the dropped affix costs. |

### `tests/fixtures`

Synthetic only. `manifest.json` records every file with its SHA-256, its purpose
and an explicit caveat. Nothing here is PoB output, a provider response, or a
gameplay measurement.

## Expected noise

PoB's LuaJIT raises an SEH exception (`0xe24c4a02`) as part of ordinary error
unwinding, and `faulthandler` reports every one. Measured on one unfiltered
engine session: **6984 banners, 265 790 traceback frame lines, 286 749 console
lines**, with pytest exiting 0 throughout. An earlier version of this file
described it as "once per engine boot", which was wrong.

`tests/conftest.py` now redirects `faulthandler` to a per-session log file for
the duration of the engine session and restores stderr afterwards. The run
prints the log's path and size instead:

```
native fault diagnostics: 32187121 bytes at ...\pytest-N\engine-faults0\faulthandler.log
  LuaJIT raises SEH 0xe24c4a02 during ordinary error unwinding, so this file is
  large and is not by itself a crash.
```

Nothing is suppressed: every banner is in that file, and a genuine native crash
still shows up in pytest's exit code. PoB's own startup output
(`Loading main script...`, `missing node <id>`) may still appear, because the
Lua runtime writes to the process stdout handle directly.

## Recorded results

Specification version 1.0, 2026-10-04, repository commit `6290674` plus the P00
working tree, PoB `ce566ea`:

| Command | Result |
|---|---|
| `python -m pytest` (no `POB2_ROOT`) | 91 passed, 34 skipped, 13 xfailed |
| `python -m pytest` (with `POB2_ROOT`) | 121 passed, 17 xfailed |
| `python -m pytest tests/unit` | 86 passed, 12 xfailed |
| `python -m pytest -m engine` (with `POB2_ROOT`) | 30 passed, 104 deselected, 4 xfailed |
| Clean install from `lock-py312-win_amd64.txt` in an empty venv, then `pip check` and `pytest tests/unit tests/integration` | `No broken requirements found.`; 66 passed, 13 xfailed |

Every `xfail` is `strict` and names the repair task that will turn it into a
pass. A non-strict xfail is not used anywhere: an expectation that passes early
must fail the suite so the marker gets removed.
