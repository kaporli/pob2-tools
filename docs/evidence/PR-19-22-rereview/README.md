# Repair re-review evidence — 2026-10-19

See [review and acceptance criteria](../../reviews/PR-19-22-rereview.md).

Exact heads: #19 `128064ce40c10be47234dde48bee053fd1eb74d4`, #21 `f73a7501de635f7b17acc0d797fe01b69120d78a`, #22 `c04d1c5bcb5f758f71aa52e15032cc2aa5c1f261`. `github-heads-and-checks.json` records the current remote state.

## Reproduce adverse cases

```powershell
python docs/evidence/PR-19-22-rereview/probes.py .venv/rereview-pr19 docs/evidence/PR-19-22-rereview/pr19-probes.json
python docs/evidence/PR-19-22-rereview/probes.py .venv/rereview-pr21 docs/evidence/PR-19-22-rereview/pr21-probes.json
python docs/evidence/PR-19-22-rereview/probes.py .venv/rereview-pr22 docs/evidence/PR-19-22-rereview/pr22-probes.json
```

Each checkout is a detached worktree at the corresponding head. The script uses submitted settled software fixtures with independently chosen mutations. JSON records current incorrect behavior, not acceptance expectations. These are not gameplay fixtures.

## Combined checks

`.venv/rereview-stack` is #21 merged with #22 without a commit. The only conflict, `tests/MANIFEST.md`, is resolved in the working file by retaining both new rows. No production branch was changed.

`python -m pytest -q tests/unit tests/integration`, repeated with `.venv/pr2-validation/py310-a/Scripts/python.exe`:

- `stack-py312.txt`: Python 3.12.4, **1839 passed, 1 xfailed**, 107.37 s.
- `stack-py310.txt`: Python 3.10.22, **1839 passed, 1 xfailed**, 115.85 s.
- The expected failure is the unbuilt production prepare/contract-binding service.

Focused Python 3.12 commands used the exact PR worktrees:

- #19: `tests/unit/test_p06_coverage.py tests/unit/test_p06_review_pr19.py` — 53 passed.
- #21: `tests/unit/test_p07_t01_flicker_cycle.py tests/unit/test_pr21_review_probes.py` — 44 passed.
- #22: `tests/unit/test_p02_t03_1_slot_rules.py tests/unit/test_p02_t03_1_item_lines.py` — 32 passed.

## Native proof

`test_custom_modifier_native.py` was copied only into the isolated combined checkout as `tests/engine/test_review_custom_modifier.py` so its normal engine fixtures apply. It reads the seed, adds a custom block, probes before/after, and checks the bound parse capture. `REVIEW_NATIVE_OUTPUT` selects the durable JSON output path.

The existing `docs/evidence/P02-T01.1/run_memtrace.py` ran the native tests with `POB2_ROOT=.venv/review-pob-clean` (absolute path), `POB2_RUN_REPO` selecting the combined checkout, `POB2_PLUGIN=0`, and `POB2_MEM_LIMIT_MB=2048`. `native-summary.json` records exact args, process bounds and timings; the associated text files preserve test output. The clean PoB head was `ce566eac45ea8a86477f513c7ee65a1ebe60014e`, unchanged after the checks.

First run: 7 submitted native tests passed; the reviewer probe failed its assumption of exactly 11x damage (observed 11.069157x). This was an incorrect probe expectation, not a submitted regression. The revised test checks only the intended hypothesis, a material damage increase plus omission from capture; its separate rerun passed. Both native JSON outputs and both test logs are retained. No guard fired.

No changes were made to the user's existing PoB checkout, tracked submodule deletion or earlier root review files except the deliberate review/status additions. No production fixes, pushes or merges were performed.
