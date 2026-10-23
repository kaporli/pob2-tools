# Final repair review evidence — 2026-10-20

[Review and merge disposition](../../reviews/PR-19-22-final-review.md).

Exact reviewed heads are recorded in `github-heads-and-checks.json`: #19 `96d8914`, #21 `9ee474e`, #22 `321cc2a`. The previous #18/#20 heads are unchanged.

## Independent probes

The previous review script was run unchanged:

```powershell
python docs/evidence/PR-19-22-rereview/probes.py .venv/final-review-pr19 docs/evidence/PR-19-22-final-review/pr19-probes.json
python docs/evidence/PR-19-22-rereview/probes.py .venv/final-review-pr21 docs/evidence/PR-19-22-final-review/pr21-probes.json
python docs/evidence/PR-19-22-rereview/probes.py .venv/final-review-pr22 docs/evidence/PR-19-22-final-review/pr22-probes.json
```

The first two now block enabled custom modifiers, including a null evaluator objective. The third now records unknown legality instead of a false violation. These are software fixtures, not gameplay evidence.

## Submitted checks

Focused `python -m pytest -q` runs on exact-head detached worktrees:

| PR | Paths under tests/unit | Python 3.12 result |
|---|---|---|
| #19 | `test_p06_coverage.py test_p06_review_pr19.py` | 60 passed |
| #21 | `test_p07_t01_flicker_cycle.py test_pr21_review_probes.py` | 51 passed |
| #22 | `test_p02_t03_1_slot_rules.py test_p02_t03_1_item_lines.py` | 35 passed |

`.venv/final-review-stack` starts at #21 and merges #22 without committing. Git ancestry checks confirmed #18, #20 and repaired #19 are included. The only conflict is two adjacent native-test rows in `tests/MANIFEST.md`; both were kept in the working file. No production branch was changed.

Combined offline command: `python -m pytest -q tests/unit tests/integration`, repeated with `.venv/pr2-validation/py310-a/Scripts/python.exe`. Complete outputs are `stack-py312.txt` and `stack-py310.txt`; the expected xfail is the unbuilt prepare-service contract binding.

Results: **1,856 passed, 1 xfailed each**. Python 3.12.4 took 152.60 s; Python 3.10.22 took 163.95 s. Both processes exited successfully.

## Native checks

`native-summary.json` and `native-py312.txt` preserve the bounded run's metadata and test output: **9 passed**, 73.6 s including monitoring overhead, no guard event, peak process-tree RSS 1,051,881,472 bytes.

The existing monitor ran these files in the combined checkout:

```text
tests/engine/test_p06_loadout_selection.py
tests/engine/test_p07_t01_flicker_cycle_engine.py
tests/engine/test_p02_t03_1_slot_rules_engine.py
```

Environment: `POB2_ROOT` points to the clean `.venv/review-pob-clean` worktree at `ce566eac45ea8a86477f513c7ee65a1ebe60014e`; `POB2_RUN_REPO` points to `.venv/final-review-stack`; `POB2_PLUGIN=0`, `POB2_MEM_LIMIT_MB=2048`, `POB2_TIME_LIMIT_S=240`. Invocation: `python docs/evidence/P02-T01.1/run_memtrace.py final-review-pr19-22-native-py312 24 <the three paths above>`.

All prior root changes and the tracked submodule deletion were preserved. No approval was posted to GitHub, no production fix was pushed and no PR was merged. Native Python 3.10, the full native suite, gameplay/live-trade checks and a campaign soak were not rerun.
