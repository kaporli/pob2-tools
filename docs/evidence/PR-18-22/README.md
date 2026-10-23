# PR #18–22 review evidence

Review: [verdicts and repair acceptance](../../reviews/PR-18-22.md), 2026-10-18.
No production code changed or pushed. All worktrees below are isolated review checkouts.

## Heads and execution

`github-heads-and-checks.json` records the open PR heads, bases and CI results.
Review worktrees `.venv/review-pr18` through `.venv/review-pr22` pin those exact commits.
The combined `.venv/review-stack` starts at #21 `db40827` and merges #22 `2f9a9f7` without committing. The sole conflict, `tests/MANIFEST.md`, was resolved by preserving both new native-test rows. Nothing was removed from either side. This tree includes all five deliveries.

Focused command per checkout: `python -m pytest -q <paths>`; repeated using
`.venv/pr2-validation/py310-a/Scripts/python.exe` (3.10.22).
Default interpreter was Python 3.12.4.

| PR | Paths | 3.12 / 3.10 passes |
|---|---|---|
| #18 | `tests/unit/test_p05_t03_pools.py` | 25 / 25 |
| #19 | `tests/unit/test_p06_coverage.py` | 33 / 33 |
| #20 | `tests/unit/test_p09_t01_2_seed_replay.py` | 26 / 26 |
| #21 | `tests/unit/test_p07_t01_flicker_cycle.py` | 26 / 26 |
| #22 | `tests/unit/test_p02_t03_1_slot_rules.py tests/unit/test_p02_t03_1_item_lines.py` | 26 / 26 |

Combined tree: `python -m pytest -q tests/unit tests/integration`, repeated on 3.10:

- `stack-offline-py312.txt`: **1795 passed, 1 xfailed**, 109.92 s.
- `stack-offline-py310.txt`: **1795 passed, 1 xfailed**, 117.05 s.
- Expected failure: production prepare service/contract binding is not implemented.

## Independent adverse cases

From the repository root:

```powershell
python docs/evidence/PR-18-22/review_probes.py .venv/review-pr19 docs/evidence/PR-18-22/probes-pr19.json
python docs/evidence/PR-18-22/review_probes.py .venv/review-pr21 docs/evidence/PR-18-22/probes-pr21.json
python docs/evidence/PR-18-22/slot_probes.py .venv/review-pr22 docs/evidence/PR-18-22/probes-pr22.json
```

The scripts intentionally record current incorrect behavior instead of asserting that it is correct. See R1–R8 for required post-repair behavior. They import the submitted tests' settled fixtures to isolate the eligibility boundary and use new adverse mutations. They do not start PoB or access the network and are not gameplay fixtures.

## Native checks

`native-summary.json` records exact args, interpreter, implementation head, time, peak process-tree RSS and monitor result. Matching `review-*.txt` files preserve pytest output.

All runs use `docs/evidence/P02-T01.1/run_memtrace.py`, `POB2_PLUGIN=0`, `POB2_MEM_LIMIT_MB=2048` and a 180 or 240 s parent deadline. `POB2_RUN_REPO` selects the reviewed checkout.

- #22 slot matrix: **4 passed**, 15.8 s, peak 736,706,560 bytes. Used the existing standalone pinned PoB; it has untracked scratch files, so this is not a clean-checkout provenance claim.
- Initial #20/#21 run: **6 skipped** because the existing PoB checkout is dirty through untracked files. Not a pass.
- Re-run #20/#21 on a new clean pinned worktree: **6 passed**, 34.7 s, peak 637,399,040 bytes. Four charge/document replay cases and two live capture/fresh-worker cases.
- #22 item conversion and golden tests on that clean worktree: **19 passed**, 8.2 s, peak 529,309,696 bytes.

The fresh engine worktree is `.venv/review-pob-clean`, checked out from the existing PoB repository at `ce566eac45ea8a86477f513c7ee65a1ebe60014e`; status remained clean after execution. No existing scratch files were deleted or excluded to obtain this result. No native guard fired in passing runs.

The original tracked submodule deletion and all earlier user/review changes in the root checkout were preserved. Native Python 3.10, the full native suite, the entire replay generator, live trade, gameplay measurements and a campaign soak were not rerun.
