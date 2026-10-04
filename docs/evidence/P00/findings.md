# P00-T04 Characterization results

Recorded on 2026-10-04, specification version 1.0, repository commit
`6290674` plus the P00 working tree. Engine results come from the checkout at
`C:\Users\Elias\PycharmProjects\PathOfBuilding-PoE2`, commit `ce566ea` - the
same commit the `external/PathOfBuilding-PoE2` submodule pins.

Each row states what was observed, not what should happen. Expected repaired
behaviour is written as a separate strict-`xfail` test linked to its repair
task; when the repair lands, that test flips from `xfail` to a pass and the
marker is removed.

## Investigated research findings

| ID | Status | Reproduction | Expected repair | Repair task |
|---|---|---|---|---|
| F02 | Reproduced | `tests/unit/test_f02_rotation_penalties.py` (synthetic worker double, real `task_tier`) | `tests/unit/test_f02_rotation_penalties.py::test_repaired_*` | P02-T04 |
| F05 | Reproduced (4 of 4 sub-findings) | `tests/unit/test_f05_run_identity_and_assumptions.py` | same file, `test_repaired_*` | P08-T01, P02-T02 |
| F10 | Reproduced | `tests/unit/test_f10_engine_lifecycle_contract.py`, `tests/engine/test_f10_engine_state.py` | same files, `test_repaired_*` | P02-T01 |
| F11 | Reproduced | `tests/unit/test_f11_worker_wipes_imported_build.py`, `tests/engine/test_f11_import_is_wiped.py` | same files, `test_repaired_*` | P02-T01 |
| F12 | Reproduced | `tests/unit/test_f12_item_conversion_source.py`, `tests/integration/test_f12_item_conversion_luajit.py`, `tests/engine/test_f12_item_conversion_golden.py` | same files, `test_repaired_*` | P02-T05 |

### F02 Rotation correction is discarded downstream

`task_tier` computes `rot["dps"]` with the action-time model (enabler overhead,
clip reload duty, gauge burst/lockout composition) and then throws it away:

```python
base_dps = realistic if realistic else rot["dps"]
hon = concentration.honest(geom, base_dps)
```

`realistic` is a bare `worker.metrics()["dps"]` re-read after enemy conditions
are enabled, with no action-time correction. Measured on the double with a
reload duty of 0.25 and a raw 1000 DPS: `rotation_dps` is 250 and
`honest_single_target` is 1000 x the concentration multiplier - four times the
rotation it claims to describe. Halving the duty cycle again leaves
`honest_single_target` unchanged, so rotation quality has no influence at all on
the field the ranking consumes. `clear_score` takes its input from the same
unadjusted number.

### F05 Run identity, league and point budgets

Four separate problems, all reproduced:

1. **Cache identity is the filename.** `load_phase(out_dir, name)` reads
   `<out_dir>/<name>.json` and consults nothing else. A `gems.json` produced for
   one level, league, budget and PoB revision is served verbatim to any later
   request in the same directory; the persisted payload is a bare list with no
   manifest wrapper.
2. **League is a hardcoded argparse default** (`--league`, default
   `"Forbidden Rites"`), and nothing in `cli.py` resolves a league against a
   provider.
3. **Point budgets are level thresholds.** Two mutually inconsistent formulas
   coexist: `(level - 1) + (6 if level <= 30 else 12)` in the finals phase and
   `(level - 1) + 8` in two others. For level 28 they disagree by 2 points.
   Ascendancy points are `2 if level < 40 else 4`, and a second site hardcodes
   `2`. No catalog is consulted.
4. **Candidate lists are hard-capped by literal slices** (`[:15]`, `[:10]`,
   `[:8]`, `[:6]`, `[:3]`, `[:2]`), plus `--top` defaulting to 8.

### F10 Engine lifecycle

Observed at the API surface and in the running engine:

* `Pob2Engine.__init__` calls `os.chdir(self.src_dir)`. Confirmed live: after
  boot the process working directory is `<pob_root>\src`, and
  `Path("HeadlessWrapper.lua").resolve()` points into the PoB checkout. Nothing
  restores it; the test session's own fixture has to.
* The class has no `close`, `shutdown`, `restart`, `__exit__` or `__del__`.
  A crashed native state cannot be disposed of deterministically.
* `call(self, fn, args)` takes no timeout, and the word "timeout" does not
  appear in the module.
* All failures raise the same `PobEngineError`; load errors, Lua runtime errors
  and handler errors are indistinguishable by type.

**A-B-A: no leakage observed.** Equip A -> read all stats, equip B -> read,
equip A -> read reproduces the first snapshot exactly (every key, not only
DPS), as does save/reload of a build after an intervening different build. Ten
repeated evaluations of an unchanged state are identical. This is evidence for
these operations on this checkout; it is not a general determinism claim.

**Expected console noise.** The engine's LuaJIT uses an SEH exception
(`0xe24c4a02`) during startup error unwinding. `faulthandler`, which pytest
enables, prints `Windows fatal exception: code 0xe24c4a02` and a traceback each
time an engine boots. It is caught by LuaJIT and harmless. `faulthandler` was
deliberately left enabled so a genuine native crash stays visible.

### F11 Importing a build destroys it

`engine_worker.Worker.__init__` runs `load_build_xml` and then
`OPT_setup(char_level, resist_penalty)`. `OPT_setup` calls
`build.spec:ResetNodes()`, disables every socket group and clears every item
slot. Measured in the engine on a build with 36 allocated nodes and one equipped
weapon: afterwards 1 node (the class root), 0 items and 0 socket groups remain.
`OPT_setup` returns a bare `true`; nothing reports what was discarded.
`Worker.reset()` repeats the same sequence.

### F12 Three modifier categories are silently dropped

`convert_trade_item` normalizes seven arrays - `enchantMods`, `runeMods`,
`implicitMods`, `explicitMods`, `fracturedMods`, `desecratedMods`,
`craftedMods` - and emits only the first four. The other three are read,
defaulted to `{}` and never referenced again.

Reproduced three ways with identical results:

* source analysis of the handler;
* the handler executed under a stock LuaJIT with PoB's two globals stubbed;
* the handler executed inside the pinned PoB engine through `MCP_dispatch`.

The loss is not cosmetic: converting an item with and without a
`craftedMods` entry produces byte-identical output, and the resulting item
contributes no damage from that affix. The declared `Implicits:` count is
computed only from the three emitted implicit-like categories, so it stays
self-consistent and gives no hint of the loss.

## Additional observations from this task

These were not in `research.md`. They were found while characterizing the
findings above and need a reviewer decision on where they belong.

| ID | Observation | Evidence | Proposed owner |
|---|---|---|---|
| P00-OBS-01 | `load_build_xml` accepts malformed, truncated XML and returns a default level 1 character indistinguishable from `new_build`. The declared class in the document (`Huntress`) is not what loads. | `tests/engine/test_engine_build_inputs.py` | P02-T01 typed `invalid_input`; P04-T01 for the parser contract |
| P00-OBS-02 | When the loaded build has `characterLevelAutoMode="true"` - which is what PoB writes for a newly created build - `OPT_setup(level, ...)` loses the requested level. It sets `build.characterLevel`, then resets the tree, and the level is recomputed from the now-empty tree as 1, while `enemyLevel` keeps the requested value. Every candidate would be evaluated as a level 1 character against a level 28 enemy, with nothing reporting the mismatch. With the flag cleared, the requested level is honoured. | `tests/engine/test_f11_import_is_wiped.py::test_setup_silently_loses_the_requested_character_level_in_auto_mode` and `::test_the_requested_level_is_honoured_when_auto_mode_is_off` | P02-T01/P02-T02 |
| P00-OBS-03 | `alloc_nodes` on one distant passive allocates the entire path to it (1 -> 18 nodes, 17 points). `dealloc_nodes` on the same id removes only that node and leaves the 16 path nodes allocated, so allocate-then-deallocate does not return to the starting state. Whether orphaned path nodes should be pruned is a game-rule question, not a defect claim. | `tests/engine/test_engine_smoke.py::test_allocation_pathing_and_deallocation_are_not_symmetric` | P02-T03 legality rules |
| P00-OBS-04 | `build.targetVersionData` is nil on the pinned checkout; `build.targetVersion` is `"0_1"` while builds are saved with `treeVersion="0_5"`. The replaced smoke script probed `targetVersionData`, printed `version = 0`, and reported success anyway. Nothing here may be read as patch evidence. | `tests/engine/test_engine_smoke.py::test_engine_internals_are_reachable` | P02-T02 patch profile |

**Scope of P00-OBS-02 on this machine.** All four build files in the user's PoB
Builds folder have `characterLevelAutoMode="false"`, so the legacy runs captured
in `baseline/` were not affected by it. The defect is latent, not retroactive.
It does bite any build created fresh in PoB, because `new_build` produces
`characterLevelAutoMode="true"`.

## Not investigated

`research.md` lists F01, F03, F04, F06, F07, F08, F09 and F13. P00-T04 assigns
only F02, F05, F10, F11 and F12, and those are the ones characterized here.

* F01 (absent submodule) is recorded in [`environment.md`](environment.md).
* F13 (print-based smoke script) is resolved by P00-T02: the script was
  converted to `tests/engine/test_engine_smoke.py` and removed.
* F03, F04, F06, F07, F08 and F09 were **not** investigated in this task. No
  claim is made about whether they reproduce.

## Measurements

From [`measurements.json`](measurements.json), produced by
`python scripts/measure_engine.py` on the hardware recorded there (16 logical
AMD64 CPUs, 31.2 GiB RAM, CPython 3.12.4 64-bit, Windows 11 10.0.26200).

| Operation | What it is | Result |
|---|---|---|
| Cold start | `Pob2Engine(pob_root)`: load `lua51.dll`, run `HeadlessWrapper.lua`, load `bootstrap.lua` | 1.39 s (1 sample) |
| Warm reset | `load_build_xml` + reload `opt_helpers.lua` + `OPT_setup`, i.e. `Worker.reset()` | median 0.133 s, min 0.106 s, max 0.344 s, mean 0.152 s, sd 0.062 s (12 samples) |
| Evaluation | `equip_item` into Weapon 1 + `get_stats(all=True)` | median 0.0127 s, min 0.0116 s, max 0.0163 s, mean 0.0130 s, sd 0.0014 s (12 samples) |

| Memory (process working set) | Bytes |
|---|---|
| Before boot | 18 399 232 |
| After boot | 252 637 184 (+223 MiB for the engine) |
| Peak during the run | 551 841 792 (526 MiB) |

A-B-A during the same run: B differed from A (47.22 vs 106.84 `TotalDPS`) and A
reproduced exactly within `1e-6` relative tolerance.

These are measurements of these operations on this machine. They are not a
throughput claim for other hardware, for other builds, or for the future
encounter evaluator, whose cost is unknown. They do bear on the default engine
timeouts in `interfaces.md` (120 s detailed, 30 s screen): the operations
measured here are three to four orders of magnitude below those limits, but no
P07-scale evaluation has been run, so no revision is proposed.
