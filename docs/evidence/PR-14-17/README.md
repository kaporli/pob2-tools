# Independent PR #14–17 review evidence

Reviewed 2026-10-18 in detached worktrees at the four submitted heads:

| PR | Exact head | Focused Python 3.12.4 | Focused Python 3.10.22 |
|---|---|---|---|
| #14 | `83f7a54140c8323fe3f22b2ed430636e4687b210` | 75 passed (new current-patch plus existing catalog module) | 25 passed (new current-patch module) |
| #15 | `63d8a58baf01304f0a15f59e49e8f767d07ceb03` | 40 passed | 40 passed |
| #16 | `644c7b858750136b356dc7fcfea059ff52260cc0` | 15 passed | 15 passed |
| #17 | `9f32dfe3ffe1aa0657b1771449a7d17e9f956059` | 35 passed | 35 passed |

The `pr*-focused-tests.json` files retain command outputs and exit codes.
Modules selected:

- #14: `tests/unit/test_p02_t02_1_current_patch.py` and, on 3.12 only,
  `tests/unit/test_p02_t02_catalog.py`.
- #15: `tests/unit/test_p05_t02_item_import.py`.
- #16: `tests/unit/test_p05_t03_pools.py`.
- #17: `tests/unit/test_p09_t01_1_flicker_suite.py`.

Run each with `python -m pytest <module(s)> -q` from its checkout. Python 3.10
is `.venv/pr2-validation/py310-a/Scripts/python.exe` in the main workspace.
All eight hosted CI interpreter checks were green at these heads. This review
did not independently repeat four complete offline suites or a combined merge.

## Adversarial probes

From the main workspace, for example:

```powershell
python docs/evidence/PR-14-17/review_probes.py 15 .venv/review-pr15
```

Repeat with PR numbers 14, 16 and 17 and their corresponding checkouts.
The script writes observations, including defects, rather than asserting that
the observed behavior is correct. The saved `pr*-probes-py312.json` files are
the outputs. All inputs are synthetic except the already committed #14/#17
evidence read for integrity/protocol checks. No provider or account is called.

Confirmed failures: lost modifier after an unterminated reminder, impossible
listing timestamps accepted, foreign-catalog/realm/league pool candidates,
input-order-dependent duplicate selection, and nonblocking classification of
an unresolved skill activation condition. The additional ownership observation
illustrates the caller assumption of `owned_from_build`; it is not labelled a
separate confirmed runtime defect in the review.

## Native checks

Clean tracked PoB pin `ce566eac45ea8a86477f513c7ee65a1ebe60014e`, existing
standalone checkout. Preexisting untracked scratch files were not modified.
Only Python 3.12 native tests were repeated, serially:

- #14: four new Flicker/catalog tests; 4 passed in 13.21 s.
- #15: new item-conversion module; 11 passed in 6.06 s.

Used `docs/evidence/P02-T01.1/run_memtrace.py` with `POB2_RUN_REPO` selecting
the reviewed checkout, `POB2_PLUGIN=0`, `POB2_MEM_LIMIT_MB=2048` (parent stop
at 3 GiB aggregate RSS), and time limits 300 s / 180 s respectively.

Complete native stdout/stderr and process-tree samples:
[PR #14 summary](../P02-T01.1/suite-runs/review-pr14-py312/summary.json),
[PR #15 summary](../P02-T01.1/suite-runs/review-pr15-py312/summary.json).
Both exit codes are zero, neither guard fired. The monitor's `last_line`
contains a late native startup log; the pytest pass summaries are earlier in
`stdout.txt`. Peak aggregate RSS: 940,736,512 / 540,991,488 bytes respectively.

The seed charge table in #17 was not independently recaptured. Nothing here
establishes gameplay accuracy, a combined-branch pass or a four-hour soak.

Reviews: [#14](../../reviews/P02-T02.1.md), [#15](../../reviews/P05-T02.md),
[#16](../../reviews/P05-T03.md), [#17](../../reviews/P09-T01.1.md).
