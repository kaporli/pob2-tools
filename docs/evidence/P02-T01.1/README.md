# P02-T01.1 evidence: native engine memory growth

Pinned engine `ce566eac45ea8a86477f513c7ee65a1ebe60014e` (untracked files, no
tracked modifications), LuaJIT `2.1.1784580905`, Python 3.12.4, Windows 11.
Every run is kept, including failed and broken ones. Nothing here was rerun
until it passed.

Memory figures are private committed bytes (`pob2opt.evaluation.memory`)
unless a file says `rss` or `tree_rss` (psutil working set of the process
tree).

## What grows

The growth is live Lua data that a full collection cannot free, and it is
intermittent for identical inputs.

1. **Reproduced on clean `origin/main` (`f75fe0a`), uninstrumented.**
   `runs/base-noplugin-s11` and `s13` reached 4.1 GB in 35 to 37 s and were
   killed by the runner guard; `s12` passed (152 tests, 1.38 GB). Both
   failures were in `tests/engine/test_f11_import_is_wiped.py`, during
   `test_setup_silently_loses_the_requested_character_level_in_auto_mode`
   (its fixture runs `new_build`, `alloc_nodes`, `equip_item`,
   `save_build_xml`, then the test loads it and runs `OPT_setup`).
   `runs/branch-noplugin-s21`/`s22` (this branch, before the test guard)
   failed the same way.
2. **Bounded reproduction** (`repro_f11.py`): that sequence repeated ten
   times in one in-process engine. Of 106 child processes, 35 stopped early,
   always in the sixth to eighth iteration, during `alloc_nodes`, `load_build_xml`,
   `equip_item` or `OPT_setup`. Every completed child peaked at or below
   812 MB; stopped ones passed 3 to 5 GB. `search_nodes` returned the same
   two nodes (47157, 2955) in every child.
3. **Not the JIT.** JIT on: 4 of 5 stopped (`repro/f11-jit-on.jsonl`). JIT
   off: 1 of 5 (`f11-jit-off.jsonl`). The `hook` and `gccheck` modes install
   a count hook, which also stops trace recording; they still stopped 30 of
   96 times.
4. **Not a hang.** Call chains sampled every 100k Lua instructions after the
   threshold (`repro/out-f11-hook4`) walk through one ordinary
   `loadBuildFromXML` (tree load, path building, cluster graphs, calcs).
   Execution proceeds; memory grows with it.
5. **Live, not garbage.** At 1.5 GiB of Lua heap a full collection freed
   little: 2567 to 2383, 2425 to 2258, 2561 to 1307 MiB
   (`repro/out-f11-gccheck`). A healthy run at 250 MiB collects to about
   130 MiB (`repro/out-f11-census-healthy`).
6. **What is live.** A reachability census from `_G` and the registry
   (`repro/out-f11-census6`, `out-f11-census7`): about 1.0 M `ModList`
   objects and 775 k mod tables in each failing child, against about 13 k mod
   tables and no ModList among the top kinds in a healthy one. The ModLists
   are reached from the shared passive-tree cache,
   `build.latestTree.nodes[*].options[*].modList` (class variants of
   switchable nodes) and some plain `latestTree.nodes[*].modList`, through
   chains of PoB class-proxy links (`_object`, `__newindex`). That cache
   outlives `new_build`, so only a new process clears it.

**Not established:** which PoB statement links each new ModList into that
chain, and what makes it intermittent. The passive spec itself stays normal
(4914 nodes, longest path 40). PoB is a pinned external checkout and is not
patched here.

## Containment

`EngineAdapter` workers are bounded (see `docs/worklog/P02-T01.1.md`). The
real-engine soak (`soak_adapter.py`) repeats `create_blank_build` plus an
exact load of the F11 build through bounded workers and compares every result
with a fresh unbounded worker's (P02-T01 tolerance):

| Soak | Bounds (hard / recycle) | Evaluations | Matched | Workers | Recycles | Kills |
|---|---|---|---|---|---|---|
| `soak/soak300-a` | 2048 / 1280 MB | 300 | 300 | 6 | 5 (memory) | 0 |
| `soak/soak300-defaults` | 3072 / 2048 MB | 300 | 300 | 1 | 0 | 0 |

With the defaults the worker rose from 309 MB to about 1.39 GB by evaluation
75 and stayed there for the remaining 225 (GC pacing; PoB sets
`collectgarbage("setpause", 400)`). The runaway did not occur on this path in
600 evaluations, so the hard-limit kill is shown by the deterministic engine
test (64 MB limit at startup) and the synthetic runaway, not by a real
runaway.

The in-process test session now exits with code 87 above
`POB2_TEST_MEMORY_LIMIT_MB` (default 3072), naming the running test.

`runs/permodule-*`: every engine module in its own pytest process on this
branch: 12 modules, 156 passed, peak 879 MB.

## Instrumented runs, kept for the record

- `runs/full-s1`, `full-s2`: this branch's working tree mid-edit, with the
  in-process `memtrace.py` plugin. Both report native access violations
  inside `lua_pcall` (s1: 18 errors from the P02-T04 module fixture, which
  boots a second in-process engine; s2: one error in the first module). No
  uninstrumented run produced one. The plugin runs a sampling thread while
  `tests/conftest.py` routes every LuaJIT SEH exception through an
  all-threads faulthandler dump; that combination is suspected, not shown.
- `runs/full-s3`: broken by a half-written `adapter.py` edit (NameError at
  import). Not evidence.
- `repro/seh-round1.jsonl`: 2000 erroring Lua calls under each combination
  of faulthandler and a busy thread; no access violation, no growth.
- `repro/f11-census5-NOTE.txt`: six children that died on a Lua syntax error
  in the diagnostic itself. Their logs were removed; rerun as `f11-census6`.
- `repro_f11.py` gained modes between runs; earlier `out-*` files have the
  older formats.

## Commands

```powershell
$env:POB2_ROOT = 'C:/Users/Elias/PycharmProjects/PathOfBuilding-PoE2'
$env:PYTHONPATH = 'pob2-mcp;pob2-optimizer'
python docs/evidence/P02-T01.1/run_memtrace.py NAME SEED           # whole engine suite, guarded
$env:POB2_PLUGIN = '0'                                             # without the in-process plugin
python docs/evidence/P02-T01.1/repro_f11.py run NAME on 10 5      # modes: on, off, hook, gccheck
python docs/evidence/P02-T01.1/soak_adapter.py NAME 300 3072 2048
```

`run_memtrace.py` takes `POB2_RUN_REPO` to test another checkout (the
baseline runs used a detached worktree at `f75fe0a`). `repro_f11.py` takes
`REPRO_LIMIT_MB` and, for `gccheck`, `CENSUS_MIB`.
