# Test manifest

What each group of tests is, what it needs, and the exact command to run it
(P00-T05). Run everything from the repository root.

## Prerequisites

Create and activate a clean venv for your interpreter. Install the explicitly
unpinned bootstrap tools with `python -m pip install --upgrade pip setuptools wheel`.
Then install the complete lock and both projects without dependency resolution:

```
python -m pip install --no-deps -r requirements/lock-py312-win_amd64.txt
python -m pip install --no-deps --no-build-isolation -e ./pob2-mcp -e ./pob2-optimizer
```

Use `lock-py310-win_amd64.txt` on Python 3.10. Run
`python scripts/lock_dependencies.py --check` afterward: it rejects extra,
missing or differently versioned distributions and runs `pip check`. CI repeats
this in two clean venvs per interpreter and compares the saved inventories.

The second line also matters for a different reason: if the packages are
installed editable from another checkout, `tests/unit/test_import_provenance.py`
fails on purpose. See `docs/evidence/P00/environment.md`.

`requirements-dev.txt` holds only the direct dependencies. Regenerate both locks
after changing it with `py -3.10 scripts/lock_dependencies.py` and
`py -3.12 scripts/lock_dependencies.py`. Generation resolves on the actual
interpreter; cross-target pip flags do not establish correct marker evaluation.

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
| Installed lock audit | `python scripts/lock_dependencies.py --check` | Clean locked venv; no network | Checks direct pins, exact installed inventory and dependency consistency. Does not demand newly released versions. |
| Engine skip guard | `python scripts/check_engine_skips.py --exit-code N --junit engine-junit.xml` | Nothing | What CI uses to decide that engine tests skipped for the right reason. |
| Schema freshness | `python scripts/generate_schemas.py --check` | Nothing | Fails when `pob2opt/schemas/v1` no longer matches `pob2opt/domain/records.py`. Regenerate with the same command minus `--check`. |
| P01 end-to-end example | `python scripts/p01_demo_run.py` | Nothing | Not a test; rewrites `docs/evidence/P01/demo-run.json`. `tests/unit/test_p01_demo_run.py` re-runs it and compares. |
| P01 review probes | `python docs/evidence/P01/review-repair-probes.py` | Nothing | Not a test; re-asks the review's questions of the repaired code. The reviewer's original `review-ae4303e-probes.py` is kept unchanged as evidence about `ae4303e`. |
| P02-T01 failure probe | `python scripts/p02_t01_timeout_probe.py --mode wedge --timeout 2.0` | Nothing | Not a test; one adapter failure case as its own process, so a supervisor can bound it. Modes: `wedge`, `crash`, `revive`. |
| P02-T01 evidence | `python scripts/p02_t01_evidence.py` | PoB for the `pob` section | Not a test; rewrites `docs/evidence/P02/lifecycle.json`. Without a checkout the `pob` section records `unavailable`. |
| P02-T01 review probes | `python docs/evidence/P02/review-eca7afe-adversarial-probes.py` | PoB | Not a test; re-asks the review's seven questions. Its recorded answers are the pre-repair ones in `review-eca7afe-adversarial.json`. |
| P02-T05 evidence | `python scripts/p02_t05_evidence.py` | PoB for the `pob` section | Not a test; rewrites `docs/evidence/P02/roundtrips.json`, `roundtrip-synthetic.xml` and `roundtrip-pob-export.xml`. Without a checkout the `pob` section records `unavailable`. |
| P02-T05 item conversion report | `luajit tests/integration/lua/convert_probe.lua pob2-mcp/pob2mcp/bootstrap.lua <item.lua> report` | `luajit` | Not a test; prints the repaired `convert_trade_item` completeness report for one item table instead of the item string. |

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
| `test_f12_item_conversion_source.py` | Research F12 from the handler source, migrated to the P02-T05 repair: every modifier array the handler reads is emitted, nothing is written back into the caller's item, and the result reports what it could not place. |
| `test_engine_skip_guard.py` | The CI engine-skip guard rejects a fixture error, a failing test, a collection error, an empty selection, an interrupt, a test that actually ran, and an xfail posing as a runtime skip. |
| `test_p01_t01_records.py` | P01-T01: every record kind's valid and invalid examples, the four no-value states, unknown schema versions, NaN, unknown and missing fields, unresolved references. |
| `test_p01_t01_schemas.py` | P01-T01: `schemas/v1` is regenerated from the dataclasses, each schema compiles, `$ref`s resolve locally, no annotation is left unresolved. |
| `test_p01_t02_identity.py` | P01-T02: what does and does not change a build, item, listing, rotation or scenario identity, including Windows newline variations. |
| `test_p01_t03_storage.py` | P01-T03: blob reuse and corruption, immutable records, source history, migrations, cache-key uniqueness, two fault injections around the ingest transaction. |
| `test_p01_t04_cache.py` | P01-T04: every dependency forces a cache miss, miss reasons are persisted, a run bundle survives its corpus being deleted, legacy phase output is never cache-eligible. |
| `test_p01_t03_references.py` | P01-T03: the reference inventory is complete (every identifier field is resolved or listed with a reason), an empty index is an empty corpus, and only the record that provides an identifier vouches for it. |
| `test_p01_t05_tasks.py` | P01-T05: task states and transitions, the four interruption points, checkpoint validation, and all 15 documented inspection queries. |
| `test_p01_review_regressions.py` | The five defects in `docs/reviews/P01.md`, each with the probe that found it: cancelled-task revival, null in a free-form field, incomplete bundles, one candidate with several evaluation tasks, and aggregate cache collisions. |
| `test_p01_demo_run.py` | Re-runs `scripts/p01_demo_run.py` and checks the claims `docs/evidence/P01/demo-run.json` records. |
| `test_p02_t01_adapter.py` | P02-T01 offline lane: parent working directory, exact versus blank loading, build-document sourcing and blob ambiguity, patch-profile mismatch, typed errors, process replacement, state scoped to the worker generation, fidelity bounds covering the load, pre-spawn path resolution, helper hashing, checkout identity. Synthetic workers only. |
| `test_p02_t01_timeout_supervisor.py` | P02-T01 bounded requests, run through `scripts/p02_t01_timeout_probe.py` under a hard outer deadline with process-tree cleanup, so an unenforced bound fails instead of hanging. |
| `test_p02_t05_build_round_trip.py` | P02-T05 offline lane: a BuildSpec exported and reimported, compared on `build_identity`. Enabled and disabled groups, main skill, ordered supports, passive attribute choices, the ordinary/ascendancy split, socketed jewels, weapon sets, the three config value types and an explicitly empty slot. Unsupported fields (trigger nesting, progression, item-granted groups, unnamed catalog IDs) are labelled incomplete and not recommended, with the value preserved in the report. Includes the invariant that a complete export never differs on reimport. |
| `test_p02_t05_item_round_trip.py` | P02-T05 offline lane: an ItemInstance as PoB item text and back, compared on `item_identity`. Every supported modifier category, modifier line flags, item variants, sockets, omitted optional fields, a modifier line containing a colon. Unsupported: the `unknown` category, a modifier's catalog resolution and roll range, a flag recorded `false`, a requirement other than level, and modifier positions PoB would renumber. |
| `test_p02_t05_no_mutation.py` | P02-T05: neither direction changes the BuildSpec, the items or the naming table it was given, checked on canonical JSON of the whole input. Includes a monkeypatched mutating exporter, so the guard fails when something does mutate. |

### `tests/integration` - local tools, still no PoB and no network

| File | Covers |
|---|---|
| `test_f12_item_conversion_luajit.py` | Runs the real `convert_trade_item` handler under a stock LuaJIT via `lua/convert_probe.lua`, migrated to the P02-T05 repair: the fractured, desecrated and crafted lines are present with PoB's own markers, they sit after the implicit block, and an unknown item field is reported. The probe's third argument `report` prints the handler's completeness report instead of the item string. |

### `tests/engine` - requires the PoB runtime

| File | Covers |
|---|---|
| `test_engine_smoke.py` | The assertion-based replacement for the removed `pob2-mcp/test_engine.py`. |
| `test_engine_build_inputs.py` | Legitimate zero full-DPS versus malformed build input (observation P00-OBS-01). |
| `test_f10_engine_state.py` | Working-directory leak and A-B-A stability in the live engine. |
| `test_f11_import_is_wiped.py` | What survives `load_build_xml` + `OPT_setup` (and observation P00-OBS-02). |
| `test_f12_item_conversion_golden.py` | The same conversion inside the pinned engine, migrated to the P02-T05 repair: PoB reads the recovered lines back in the right category and the previously lost affix now raises the calculated damage. |
| `test_p02_t01_engine_adapter.py` | P02-T01 against the real engine: worker/coordinator working directories, checkout and helper identity, exact load keeping tree/gear/groups, blank build still clearing them, malformed document as typed `invalid_input`, recovery from it without a blank character, A-B-A with B read, two documents under one build hash, configuration isolation between evaluations, forced termination and replacement. |
| `test_p02_t05_pob_round_trip.py` | P02-T05 against the real engine: a build PoB saved, imported, exported, loaded back into PoB and saved again. PoB accepts the document and reports the same tree, gear and socket groups; the deterministic primitives agree within the P02-T01 tolerance; `build_identity` is unchanged while the XML bytes are not. Includes a damaged export, so the equality assertions cannot pass on an empty document. |

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

Latest P02-T01 repair results: [final repair handoff](../docs/worklog/P02-T01-final-repairs.md).
Adapter p02-t01.2: 631 offline passes and 5 expected failures on each supported
interpreter; 48 engine passes and 1 expected failure. The supervised deadline
probe also accepts `combined`, `slow_load`, `slow_primitives`, `slow_identity`,
`within_budget` and `wedged_load` modes.

Specification version 1.0, 2026-10-06, repository commit `5ba4b9a` plus the
P02-T01 working tree, PoB `ce566ea`:

| Command | Result |
|---|---|
| `python -m pytest` (no `POB2_ROOT`) | 622 passed, 47 skipped, 5 xfailed |
| `python -m pytest` (with `POB2_ROOT`) | 668 passed, 6 xfailed |
| `python -m pytest tests/unit` | 617 passed, 4 xfailed |
| `python -m pytest tests/integration` | 5 passed, 1 xfailed |
| `python -m pytest -m engine` (with `POB2_ROOT`) | 46 passed, 627 deselected, 1 xfailed |

The earlier P00 figures, for comparison: 91/34/13, 121/17, 86/12 and 30/104/4
at commit `6290674`.

Every `xfail` is `strict` and names the repair task that will turn it into a
pass. A non-strict xfail is not used anywhere: an expectation that passes early
must fail the suite so the marker gets removed.

## PR #2 repair-contract correction

The prior broad F05/F10 xfails were removed. There are now two strictly scoped
missing-service expectations, which catch only `MissingFutureService`. Once
`pob2opt.search` or `pob2opt.evaluation` exists, its binding check fails and
requires the owning task to install real acceptance coverage. Broken imports,
validation errors and missing fixture files are not accepted repair outcomes.

`tests/repair_contracts.py` materializes a complete offline request and local
synthetic profile, catalog, league, scenario, corpus and item-pool snapshots.
F05 probes accept the labelled synthetic service and reject constant cache keys,
unresolved leagues, incorrect/untraceable budgets and ignored candidate limits.
The snapshots are test-double data, not accepted P01 record schemas or evidence
of production preparation. P08 owns the mapping from actual validated records
to the test observation format; no production return type is imposed by P00.

P02-T01 replaced its missing-service check with these acceptance cases:

| Case | Where |
|---|---|
| 1. Parent working directory unchanged, including a worker that moves its own | `tests/unit/test_p02_t01_adapter.py`, `tests/engine/test_p02_t01_engine_adapter.py` |
| 2. Wedged worker, typed bounded timeout, hard outer deadline and process-tree cleanup | `tests/unit/test_p02_t01_timeout_supervisor.py` with `scripts/p02_t01_timeout_probe.py` |
| 3. Forced worker death, next request completes in a *different* process | `tests/unit/test_p02_t01_adapter.py`, `tests/engine/test_p02_t01_engine_adapter.py` |
| 4. Real PoB evaluations, synthetic lane stays offline | `tests/engine/test_p02_t01_engine_adapter.py` |

No public `evaluate_raw` was added. The two F11 unit expectations and the F10
and F11 engine expectations were migrated rather than deleted; each migrated
test says what changed and why, and the `tests/unit/test_f10_engine_lifecycle_contract.py`
placeholder now asserts that the three covering files exist.

Three characterizations recorded defects that P02-T01 fixed, so they now pin
the repaired behaviour instead:

* `pob2mcp.engine.Pob2Engine` has a deterministic `close` and a `PobEngineClosed`
  state (it previously had no teardown at all);
* `pob2opt.engine_worker.Worker.__init__` loads the document and stops;
  `create_blank_build` is the separate destructive step, reached through
  `new_blank_worker` (research F11);
* `load_build_xml` rejects a document PoB cannot read instead of returning a
  default level 1 character (observation P00-OBS-01).

## P02-T05 recorded results

Specification version 1.0, 2026-10-06, branch `p02-t05-roundtrips` off
`0df64dd`, CPython 3.12.4, Windows 11, PoB `ce566ea`:

| Command | Result |
|---|---|
| `python -m pytest tests/unit` | 693 passed, 3 xfailed |
| `python -m pytest tests/integration` | 9 passed |
| `python -m pytest -m engine` (with `POB2_ROOT`) | 59 passed, 705 deselected |
| `python -m pytest` (with `POB2_ROOT`) | 761 passed, 3 xfailed |
| `python -m pytest` (no `POB2_ROOT`) | 702 passed, 59 skipped, 3 xfailed |
| `python scripts/generate_schemas.py --check` | 20 schema files match `pob2opt/domain/records.py` |

The three strict xfails that named P02-T05 are gone, because the F12 repair
turned them into ordinary passes:

| Test | Now |
|---|---|
| `tests/unit/test_f12_item_conversion_source.py::test_repaired_handler_emits_every_normalized_modifier_array` | passes; every modifier array the handler reads is emitted |
| `tests/integration/test_f12_item_conversion_luajit.py::test_repaired_conversion_preserves_every_modifier_category` | passes; the three recovered categories are in the item string |
| `tests/engine/test_f12_item_conversion_golden.py::test_repaired_conversion_preserves_every_modifier_category` | passes; PoB reads them back in the right category |

The three remaining xfails belong to P02-T04 and P08-T01.

One ordering hazard found while running the engine lane: a second
`Pob2Engine` in the same process shares the native state, so closing the
throwaway one leaves the session `engine` fixture unusable for every test
after it. `tests/engine/test_p02_t05_pob_round_trip.py` builds its fixture
document in the session engine for that reason.
