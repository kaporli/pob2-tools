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
| P02-T02 catalog export (engine) | `python -m pob2opt.cli catalog export --profile docs/evidence/P02/catalog-profile-request.json --out DIR` | A PoB2 checkout | Not a test; writes a catalog, patch profile, gaps and evidence bundle. Exit 3 without a checkout. |
| P02-T02 catalog export (offline) | `python -m pob2opt.cli catalog export --profile docs/evidence/P02/catalog-profile-request.json --out DIR --rows docs/evidence/P02/catalog-rows-slice.json` | Nothing | The same export over the committed row slice. No PoB, no network. |
| P02-T02 evidence | `python scripts/p02_t02_evidence.py` | PoB | Not a test; rewrites `docs/evidence/P02/catalog-export.json` and `catalog-rows-slice.json`. Without a checkout the summary records `unavailable`. |
| P02-T03 evidence | `python scripts/p02_t03_evidence.py` | PoB for the `pob_derived` section | Not a test; rewrites `docs/evidence/P02/legality.json`: the verdict for every fixture case, and one real import validated in the pinned engine. Without a checkout that section records `unavailable`. |
| P02-T04 primitive fixtures | `python scripts/p02_t04_primitive_fixtures.py` | PoB | Not a test; builds the thirteen controlled fixture documents, reads them through the adapter and rewrites `docs/evidence/P02/primitives.json`. Without a checkout it records `unavailable`. `tests/engine/test_p02_t04_primitive_semantics.py` imports its fixture builder. |
| P02-T05 evidence | `python scripts/p02_t05_evidence.py` | PoB for the `pob` section | Not a test; rewrites `docs/evidence/P02/roundtrips.json`, `roundtrip-synthetic.xml` and `roundtrip-pob-export.xml`. Without a checkout the `pob` section records `unavailable`. |
| P02-T05 item conversion report | `luajit tests/integration/lua/convert_probe.lua pob2-mcp/pob2mcp/bootstrap.lua <item.lua> report` | `luajit` | Not a test; prints the repaired `convert_trade_item` completeness report for one item table instead of the item string. |
| P09-T01 synthetic suite | `python scripts/p09_t01_suite.py` | Nothing | Not a test; rewrites `tests/fixtures/combat/p09_synthetic_suite.v1.json`, `benchmarks/p09-synthetic-v1/suite.json` and `docs/evidence/P09/protocol-fields.json`. Deterministic and offline. Changing the suite needs a new `suite_id`, not an edit in place. |
| P03-T01 source inspect | `python -m pob2opt.cli source inspect --provider NAME --out DIR` | Nothing | Reports the capability manifest recorded in `docs/evidence/P03`. Offline by construction: it has no fetch path and no flag that adds one. Providers: `mobalytics`, `maxroll`, `poe-ninja`. Exit 3 for an unknown provider or a missing manifest, 4 for a manifest that fails the structure. |
| P03-T02 ingest | `python -m pob2opt.cli ingest --provider NAME --input PATH_OR_URL --corpus DIR` | Nothing | Not a test; stores one input as a raw record. A URL needs `--allow-host`: no host is approved by default. Exit 3 for blocked/missing/unapproved access, 4 for a malformed or timed-out one. |
| P03-T02 evidence | `python scripts/p03_t02_evidence.py` | Nothing | Not a test; rewrites `docs/evidence/P03/acquisition.json` from a scripted transport. No provider, no socket, no PoB. |

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
| `test_p02_t02_catalog.py` | P02-T02 offline lane: the real exporter over the committed row slice. Bundle self-validation, sample builds resolving, duplicate display names staying distinct, upstream commit changing the context identity, every compatibility verdict including the one path to `verified`, a historical pinned profile staying historical, and each missing upstream rule being a gap rather than a constant. No PoB, no network. |
| `test_p02_t02_catalog_cli.py` | P02-T02 `pob2opt catalog export` as a command: bundle layout, blobs matching their documents, exit codes 0, 2 and 3, an unknown request key, a missing release directory, and the doctor's `patch_profile_owner` claim now naming a command that exists. |
| `test_p02_t03_legality.py` | P02-T03 offline lane: one fixture case per rule, each violating that rule alone, the legal boundary beside it, and one combined case. Also that an unknown always cites a gap, that a check that did not run is unknown, that attributes and Spirit together are not a verdict, that nothing is repaired, and that the shipped profile's empty slot categories make equipment undecidable. No PoB, no network. |
| `test_p02_t04_primitive_semantics.py` | P02-T04 declaration rules: one owner and one unit per primitive, no engine key claimed twice, every inventoried category covered, a missing native output as a gap, and `CombinedDPS` unresolved until the engine flag that decides its unit is present. No PoB. |
| `test_p02_t04_rotation_estimates.py` | P02-T04 F02 repair through the real `task_tier`: setup time reduces the sustained estimate, an unrelated condition scales the rotation instead of replacing it, an unknown reload duty or delivery geometry is a gap, the deprecated `floor`/`ceiling`/`honest_*` names carry a legacy status, and the arithmetic stays in `pob2opt.legacy_estimates`. |
| `test_p02_t05_build_round_trip.py` | P02-T05 offline lane: a BuildSpec exported and reimported, compared on `build_identity`. Enabled and disabled groups, main skill, ordered supports, passive attribute choices, the ordinary/ascendancy split, socketed jewels, weapon sets, the three config value types and an explicitly empty slot. Unsupported fields (trigger nesting, progression, item-granted groups, unnamed catalog IDs) are labelled incomplete and not recommended, with the value preserved in the report. Includes the invariant that a complete export never differs on reimport. |
| `test_p02_t05_item_round_trip.py` | P02-T05 offline lane: an ItemInstance as PoB item text and back, compared on `item_identity`. Every supported modifier category, modifier line flags, item variants, sockets, omitted optional fields, a modifier line containing a colon. Unsupported: the `unknown` category, a modifier's catalog resolution and roll range, a flag recorded `false`, a requirement other than level, and modifier positions PoB would renumber. |
| `test_p02_t05_no_mutation.py` | P02-T05: neither direction changes the BuildSpec, the items or the naming table it was given, checked on canonical JSON of the whole input. Includes a monkeypatched mutating exporter, so the guard fails when something does mutate. |
| `test_p09_t01_scenarios.py` | P09-T01: the four synthetic workloads validate against the P01 contracts, carry the four shapes of `scenarios.md`, keep the synthetic label inside every record, leave both reference slots null, and match the frozen scenario and suite hashes. Plus the oracle: equal total health across the two clear shapes, route time charged only where a route is declared, and untargetable time counted only on the sustained boss. |
| `test_p09_t01_protocol.py` | P09-T01: every `ScenarioSpec` field appears in the field table, a field marked `unresolved_input` names a gap that exists and any other field names none, no row claims a direct measurement, every gap is open and states a collectable request, and no build family is named anywhere in the suite. Also that the protocol document and the D04 record exist and do not present themselves as accepted. |
| `test_p05_t01_access_decision.py` | P05-T01: the recorded access disposition. D01 carries every section `docs/decisions/README.md` requires, allows an explicit reviewer acceptance while preserving capability limits, keeps the public market route at `unsupported_access` and the account route conditional on a registration we do not have, blesses no cookie or borrowed `client_id`, and specifies the `market refresh` unsupported payload (exit 3, no retry, listings to `unknown`). Also that nothing under `docs/evidence/P05/` is shaped like a credential. Reads documents only. |
| `test_p03_t01_capabilities.py` | P03-T01: the three recorded manifests hold their shape. Every provider is either reproducible or specifically blocked, the three support flags are separate and each cites evidence, all five representative categories are answered rather than dropped, redistribution and access values stay inside the contract, the recorded limits are never looser than `interfaces.md`, no manifest carries anything resembling a credential, and the D02 proposal keeps every required section and stays unresolved. Reads evidence files only. |
| `test_p03_t01_source_inspect.py` | P03-T01: `pob2opt source inspect` as a command. Report contents per provider, exit codes 0, 2, 3 and 4, an unknown provider, a missing manifest directory, a malformed manifest, and the subcommand refusing anything but `inspect`. Then the validator's rejection cases: a supported flag without confirmation, a dropped category, a substituted category, a missing reason, an unresolvable evidence reference, an access method outside the contract, a loosened limit, and a manifest with neither an example nor a block. Also that the reader imports no HTTP client. |
| `test_p03_t02_local.py` | P03-T02 local acquisition: XML, HTML, JSON and a build code each round trip to a raw record with a matching hash; the same bytes are one blob and one document however often they arrive; a missing file, an unknown kind, malformed JSON, unsafe XML, a truncated or oversized build code and an oversized file each get a typed status and write nothing. Also the `ingest` command, the engine-free import checked in a fresh interpreter, and the rule that nothing acquired is ever executed, checked on the syntax tree. |
| `test_p03_t02_repairs.py` | P03-T02 review repairs, one group per finding in `docs/reviews/P03-T02.md`: credentials stay origin-scoped while validators are bound to the exact final resource, including ordered query values; unsafe XML is refused independently of encoding; ordinary UTF-8, UTF-16, Latin-1 and Windows-1252 documents preserve their raw bytes, direct and compressed; two resources differing only in a redacted query value no longer share a validator, and two authorization contexts no longer share an entry; `RequestsTransport` closes a response on every early return and on a partial read, against a fake session that opens nothing; a 429 cooldown holds the provider's other URLs, leaves other providers alone and survives a restart; a 304 after a redirect resolves against the URL that was asked for, and a changed redirect target does not reuse the cached representation; a dot segment cannot leave an approved path, checked against what `requests` would prepare; and 2,000-level JSON is a typed refusal on both interpreters. |
| `test_p03_t02_http.py` | P03-T02 shared HTTP layer, transport injected: the empty-by-default host allow list, refusals for plain http, another host, credentials in a URL and a redirect off the list; 403, 404, 429, an oversized body, a timeout and malformed content as typed statuses that store nothing; the 10/30 second timeouts and 20 MiB cap reaching the transport; a provider tightening but never loosening them; three attempts for a transient failure and one for the rest; a short retry delay waited in full and a long one scheduled rather than cut; conditional requests and 304; and that no token reaches a blob, a record, a log line or the state file. |
| `test_p04_support_schema.py` | P02 follow-up: BuildSpec schema version 2. Per-kind schema versions, support settings mirroring `support_ids` in order, a null setting blocking `complete` and the deliverable, `main_skill_group` range and version rules, the version 1 identity unchanged, every support setting and the main group inside the version 2 identity, the v1-to-v2 upgrade inventing nothing, a known support state round tripping, and gems resolving on the (gemId, variantId) pair. |
| `test_p04_t01_parse.py` | P04-T01: format chosen by signature, a declared format that disagrees, refusals for an empty, unknown, PoE 1, malformed, doctype, truncated-code and decompression-bomb payload, a code and its XML giving the same build, all twelve PoB-written fixtures parsing with validating records, determinism, no socket, one BuildSpec per loadout linked to the shared document, an unlinked set reported and not merged, ambiguous loadout titles, missing tree/items/skills as unknown rather than empty, a layout change, an unknown class and coverage by domain. |
| `test_p04_t02_sources.py` | P04-T02: provider pages and JSON exports blocked on D02 with no build, visible text without scripts, missing gear, an explicitly empty slot, an old tree version, a declared patch kept as a declaration, an unknown skill or passive kept unresolved, absent popularity staying absent, popularity not changing a parse, and a display label not overriding structured data. |
| `test_p04_t03_resolve.py` | P04-T03: naming tables from the catalog with native keys first, a PoB name claimed twice left out and reported, exact name lookup with ambiguous candidates and no fuzzy match or translation, migration recording renames and removals without substituting, affix lines resolving to one tier, unknown and ambiguous affixes, duplicate item names staying distinct, name-only template claims, and every complete fixture passing the P02 round trip. |
| `test_p04_t04_claims.py` | P04-T04: unverified claims from sentences naming catalog entities, retrieval of the exact passage, short excerpts, declared patches, conflicting statements kept with conflict status, the SQLite index searching headings and text with entity filters and quoting user text, popularity never grading a claim, imperative text stored as text, PoB notes as claims, and no code execution in the parsers package. |
| `test_p04_t05_corpus.py` | P04-T05: the field audit over ten complete variants at 100% exact agreement and over every partial and ambiguous fixture with all differences declared, the audit failing on a wrong support setting and a dropped modifier line, exact duplicates keeping every creator, identical copies counted once, family proposals, review-only family IDs, and holdout splits never dividing a family. |
| `test_p04_parse_cli.py` | `pob2opt parse` end to end: a locally ingested document and a catalog bundle exported from committed rows give stored, validating records with no unresolved reference; a second run reports the stored result; exit codes 2 and 3. |

### `tests/integration` - local tools, still no PoB and no network

| File | Covers |
|---|---|
| `test_f12_item_conversion_luajit.py` | Runs the real `convert_trade_item` handler under a stock LuaJIT via `lua/convert_probe.lua`, migrated to the P02-T05 repair: the fractured, desecrated and crafted lines are present with PoB's own markers, they sit after the implicit block, and an unknown item field is reported. The probe's third argument `report` prints the handler's completeness report instead of the item string. |
| `test_p05_legacy_quarantine.py` | The six quarantined MCP entry points (`authenticate_poe`, `list_characters`, `import_character`, `trade_leagues`, `trade_search`, `trade_evaluate`) each raise a capability error naming D01, and none of them constructs a legacy client on the way: the client classes are replaced with a function that fails if called. `pob2mcp.server` references neither `PoeApi` nor `Trade2Client` anywhere in its syntax tree and imports neither module, checked in a clean interpreter. The client factories refuse before constructing anything, the eighteen local engine tools are untouched, `quarantine.py` reads no environment variable, and both legacy modules are still on disk. Registered MCP handler calls preserve the safe capability explanation and D01 reference as intentional errors; local import, item evaluation and export still dispatch through MCP. |

### `tests/engine` - requires the PoB runtime

| File | Covers |
|---|---|
| `test_engine_smoke.py` | The assertion-based replacement for the removed `pob2-mcp/test_engine.py`. |
| `test_engine_build_inputs.py` | Legitimate zero full-DPS versus malformed build input (observation P00-OBS-01). |
| `test_f10_engine_state.py` | Working-directory leak and A-B-A stability in the live engine. |
| `test_f11_import_is_wiped.py` | What survives `load_build_xml` + `OPT_setup` (and observation P00-OBS-02). |
| `test_f12_item_conversion_golden.py` | The same conversion inside the pinned engine, migrated to the P02-T05 repair: PoB reads the recovered lines back in the right category and the previously lost affix now raises the calculated damage. |
| `test_p02_t01_engine_adapter.py` | P02-T01 against the real engine: worker/coordinator working directories, checkout and helper identity, exact load keeping tree/gear/groups, blank build still clearing them, malformed document as typed `invalid_input`, recovery from it without a blank character, A-B-A with B read, two documents under one build hash, configuration isolation between evaluations, forced termination and replacement. |
| `test_p02_t02_catalog_engine.py` | P02-T02 against the real engine: the typed Lua catalog operations paging stably over every table, an unknown table refused as `unsupported` without killing the worker, a catalog read leaving a loaded build untouched, the behaviour fixtures actually running, a PoB-saved build resolving completely, duplicate display names surviving as distinct entities, and a replay of the captured rows reproducing the live catalog hash. |
| `test_p02_t03_legality_engine.py` | P02-T03 against the real engine: `legality_state` reporting the allocation, equipment and calculated pools the engine holds, a document PoB imports cleanly still being illegal, a record whose claims its own document does not produce, connectivity decided against the real passive tree, and a legality read leaving a loaded build untouched. |
| `test_p02_t04_primitive_semantics.py` | P02-T04 against the real engine: thirteen controlled fixture documents settling what each primitive contains. `TotalDPS` as damage per use times the rate, hit probability and crit already inside damage per use, extra projectiles changing nothing, damage over time as a duration-independent rate, five meta gems leaving the socketed spell's cadence unchanged, a cooldown becoming the use rate, and `CombinedDPS` switching unit with `showAverage`. |
| `test_p02_t05_pob_round_trip.py` | P02-T05 against the real engine: a build PoB saved, imported, exported, loaded back into PoB and saved again. PoB accepts the document and reports the same tree, gear and socket groups; the deterministic primitives agree within the P02-T01 tolerance; `build_identity` is unchanged while the XML bytes are not. Includes a damaged export, so the equality assertions cannot pass on an empty document. |
| `test_p04_round_trips.py` | P04 and the P02 support follow-up against the real engine: for twelve PoB-written fixtures, PoB evaluates our export with the same group count, main skill and every numeric output; identity survives PoB's own save; a changed support state is carried through PoB and back; switching a support off moves PoB's outputs; each loadout variant evaluates as PoB evaluates that loadout selected in the source. |

### `tests/fixtures`

Synthetic. `manifest.json` records every file with its SHA-256, its purpose
and an explicit caveat. The `p04/` files have origin `pob_derived`: synthetic
compositions that the pinned PoB loaded and saved (`scripts/p04_make_fixtures.py`).
Nothing here is a provider response or a gameplay measurement.

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

Specification version 1.0, 2026-10-06, repository commit `0df64dd` plus the
P02-T04 working tree, PoB `ce566ea`:

| Command | Result |
|---|---|
| `python -m pytest` (no `POB2_ROOT`) | 673 passed, 67 skipped, 3 xfailed |
| `python -m pytest` (with `POB2_ROOT`) | 739 passed, 4 xfailed |
| `python -m pytest tests/unit` | 668 passed, 2 xfailed |
| `python -m pytest tests/integration` | 5 passed, 1 xfailed |
| `python -m pytest -m engine` (with `POB2_ROOT`) | 66 passed, 676 deselected, 1 xfailed |
| `python scripts/generate_schemas.py --check` | 20 schema files match `pob2opt/domain/records.py` |

The two F02 xfails are gone: P02-T04 repaired the path, so
`test_repaired_concentration_consumes_the_rotation_adjusted_dps` and
`test_repaired_single_target_responds_to_rotation_quality` are plain passes
and the three characterizations beside them were migrated in place.

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

## P02-T02 catalog export

Specification version 1.0, 2026-10-06, branch `p02-t02-catalog` off `origin/main`
(`0df64dd`), PoB `ce566ea` with a modified working tree, CPython 3.12.4,
Windows 11:

| Command | Result |
|---|---|
| `python -m pytest tests/unit` | 686 passed, 4 xfailed |
| `python -m pytest` (no `POB2_ROOT`) | 691 passed, 64 skipped, 5 xfailed |
| `python -m pytest` (with `POB2_ROOT`) | 754 passed, 6 xfailed |
| `python -m pytest -m engine` (with `POB2_ROOT`) | 63 passed, 696 deselected, 1 xfailed |
| `python scripts/generate_schemas.py --check` | 20 schema files match `pob2opt/domain/records.py` |

The export itself, on that checkout: catalog hash
`e82da2ea8a9cb567693f15d848f3f322f0ba5149f560687ebb44da7d63d3ba6f`, 24 355
entities across the ten tables, patch `0.5.5e`, compatibility **partial** for
four stated reasons, nine gaps, and both sample builds resolving with nothing
unresolved or ambiguous. `docs/evidence/P02/catalog-export.json` has the
detail.

The adapter can now ask the engine for a catalog page, so the version string
moved. The primitive path did not change. A `PatchProfile`
pinned to a different adapter is now refused rather than accepted silently,
which is why the P02-T01 fixtures repin `adapter_version` the way they already
repinned `pob_commit`.

## P02-T03 legality validation

Specification version 1.0, 2026-10-06, branch `p02-t03-legality` off
`p02-t02-catalog` (`28796a5`), PoB `ce566ea` with a modified working tree,
CPython 3.12.4, Windows 11:

| Command | Result |
|---|---|
| `python -m pytest tests/unit` | 710 passed, 4 xfailed |
| `python -m pytest` (no `POB2_ROOT`) | 715 passed, 71 skipped, 5 xfailed |
| `python -m pytest` (with `POB2_ROOT`) | 785 passed, 6 xfailed |
| `python -m pytest -m engine` (with `POB2_ROOT`) | 70 passed, 720 deselected, 1 xfailed |
| `python scripts/generate_schemas.py --check` | 20 schema files match `pob2opt/domain/records.py` |

The validator answers eighteen declared checks and the overall verdict is
`legal` only when every one of them is. On a profile exported from this
engine a build with any equipment cannot reach that: `SlotRule.accepted_base_categories`
is empty with a blocking gap, so slot legality is `unknown` and cites it. Six
more answers are `unknown` for a cited gap rather than guessed: quest passive
points, the ascendancy unlock schedule, weapon-set point unlock levels, gem
levels above a natural maximum, a skill with no gem, and the option list of a
choice node. `docs/evidence/P02/legality.json` has the verdict for every
fixture case and for one real import.

The adapter can now ask the engine for the legality state it holds after a
load. The primitive path did not change.

P02-T02, T03 and T04 each bumped `ADAPTER_VERSION` on their own branch. The
integrated adapter is none of those three, so it is `p02.1`: a cached result
stamped with one task's string would name an adapter that never ran.
## P02-T05 recorded results
Specification version 1.0, 2026-10-06, branch `p02-t05-roundtrips` off
`0df64dd`, CPython 3.12.4, Windows 11, PoB `ce566ea`:
| `python -m pytest tests/unit` | 693 passed, 3 xfailed |
| `python -m pytest tests/integration` | 9 passed |
| `python -m pytest -m engine` (with `POB2_ROOT`) | 59 passed, 705 deselected |
| `python -m pytest` (with `POB2_ROOT`) | 761 passed, 3 xfailed |
| `python -m pytest` (no `POB2_ROOT`) | 702 passed, 59 skipped, 3 xfailed |
The three strict xfails that named P02-T05 are gone, because the F12 repair
turned them into ordinary passes:
| Test | Now |
| `tests/unit/test_f12_item_conversion_source.py::test_repaired_handler_emits_every_normalized_modifier_array` | passes; every modifier array the handler reads is emitted |
| `tests/integration/test_f12_item_conversion_luajit.py::test_repaired_conversion_preserves_every_modifier_category` | passes; the three recovered categories are in the item string |
| `tests/engine/test_f12_item_conversion_golden.py::test_repaired_conversion_preserves_every_modifier_category` | passes; PoB reads them back in the right category |
The three remaining xfails belong to P02-T04 and P08-T01.
One ordering hazard found while running the engine lane: a second
`Pob2Engine` in the same process shares the native state, so closing the
throwaway one leaves the session `engine` fixture unusable for every test
after it. `tests/engine/test_p02_t05_pob_round_trip.py` builds its fixture
document in the session engine for that reason.
## P09-T01 recorded results

Specification version 1.0, 2026-10-10, branch `p09-t01-protocol` off
`c2c2d02`, CPython 3.12.4, Windows 11:

| Command | Result |
|---|---|
| `python -m pytest tests/unit` | 873 passed, 1 xfailed |
| `python -m pytest` (no `POB2_ROOT`) | 882 passed, 99 skipped, 1 xfailed |
| `python -m pytest` (with `POB2_ROOT`) | 981 passed, 1 xfailed |
| `python scripts/generate_schemas.py --check` | 20 schema files match `pob2opt/domain/records.py` |
The 99 skips are the engine lane with no PoB checkout. A skip is not an engine
pass, and P09-T01 needs no engine: the suite is built and checked entirely from
the P01 records.
The two new files add 36 tests. Neither reaches PoB, the network or the game.
What they cannot check is whether the suite is a good encounter model, because
no encounter has been measured and no evaluator exists to run it through. The
suite is `kind: synthetic` and `validation_status: untested` for that reason.

### After the P09-T01 review repairs

Branch `p09-benchmarks`, 2026-10-11, after `docs/reviews/P09-T01.md` R1 and R2:

| Command | Python 3.12.4 | Python 3.10.22 |
|---|---|---|
| `python -m pytest tests/unit/test_p09_t01_scenarios.py tests/unit/test_p09_t01_protocol.py` | 32 passed | 32 passed |
| `python -m pytest tests/unit tests/integration -m 'not engine and not network and not longrun'` | 883 passed, 1 xfailed | not re-run |
| `python scripts/generate_schemas.py --check` | 20 schema files match | not re-run |

One test was removed and two added.
`test_every_limit_leaves_headroom_over_its_own_floor` is gone: it compared
constants and called the difference headroom over a floor that no evaluation
has to reach. `test_the_horizon_totals_account_for_the_whole_limit` says what
the two horizon figures are, and `test_the_completion_clock_stops_at_death`
recomputes the four worked completion times from the declared windows rather
than reading the stored numbers back.

`baseline_suite_hash` is unchanged, so the suite keeps its `suite_id`: no
`ScenarioSpec` or `RotationPolicy` record changed. The fixture file's SHA-256
did change, because the oracle block lives in that file, and it is updated in
both places that record it.

## P03-T01 recorded results

Specification version 1.0, 2026-10-10, branch `p03-t01-capabilities` off
`c2c2d02`, CPython 3.12.4, Windows 11. No PoB, no network:

| Command | Result |
|---|---|
| `python -m pytest tests/unit` | 897 passed, 1 xfailed |
| `python scripts/generate_schemas.py --check` | 20 schema files match `pob2opt/domain/records.py` |
| `python -m pob2opt.cli source inspect --provider mobalytics --out DIR` | exit 0, `access_blocked`, 0 of 5 categories inspected |
| `python -m pob2opt.cli source inspect --provider maxroll --out DIR` | exit 0, `unsupported_access`, 0 of 5 categories inspected |
| `python -m pob2opt.cli source inspect --provider poe-ninja --out DIR` | exit 0, `unsupported_access`, 0 of 5 categories inspected |

The one xfail belongs to P08-T01 and is unrelated. The 55 new tests run in the
offline unit lane; none is marked `network`, because none of them touches a
provider. The manifests they read came from a one-off bounded inspection that is
deliberately not re-runnable as a test: re-running it means contacting three
providers, which the unit lane forbids and which P03-T01 bounds to a handful of
requests. A `network`-marked smoke check belongs to P03-T03, against whichever
provider the D02 review approves.
## P03-T02 recorded results

Specification version 1.0, 2026-10-10, branch `p03-t02-acquisition` off
`c2c2d02`, CPython 3.12.4, Windows 11, no PoB checkout present:

| Command | Result |
|---|---|
| `python -m pytest tests/unit` | 917 passed, 1 xfailed |
| `python -m pytest` | 926 passed, 99 skipped, 1 xfailed |
| `python -m pytest -m network` | 1026 deselected, 0 collected |
| `python scripts/p03_t02_evidence.py` | wrote `docs/evidence/P03/acquisition.json` |
The 99 skips are the engine lane: this worktree has no PoB checkout. P03-T02
adds no engine test and needs none. The `-m network` line is the point of the
marker: acquisition ships no test that would contact a provider, so selecting
that marker collects nothing.

## P03 repair results

After the repairs for `docs/reviews/P03-T01.md` and `docs/reviews/P03-T02.md`,
branch `p03-acquisition`, Windows 11, no PoB checkout, no socket:

| Command | Python 3.12.4 | Python 3.10.22 |
|---|---|---|
| `python -m pytest tests/unit tests/integration -m 'not engine and not network and not longrun'` | 1018 passed, 1 xfailed | 1018 passed, 1 xfailed |
| `python -m pytest tests/unit/test_p03_t02_repairs.py` | 36 passed | 36 passed |
| `python scripts/generate_schemas.py --check` | 20 schema files match | not re-run |

The one xfail belongs to P08-T01 and is unrelated. The repair suite is written
so that reverting any single repair fails it: each test reproduces the
reviewer's case rather than reading back a configured value. R8 is the clearest
example, because it is the one finding whose behaviour differed between the two
interpreters: `json.loads` on a 2,000-level document still raises
`RecursionError` on 3.10.22 and still succeeds on 3.12.4, and the bound in
`content.py` is what makes acquisition answer `json_too_deep` on both.
