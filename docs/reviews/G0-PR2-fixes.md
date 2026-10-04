# G0 follow-up: PR #2 fixes

## Review identity

- Specification: 1.0; tasks P00-T01/T04/T05, PR2-R01/PR2-R02.
- Implementation commit: `e0aa81d7c80170911f7f2ead66ed7d023a443ddc`.
- Reviewer: Codex, 2026-10-04. Codex also implemented this follow-up at Elias's request; final GitHub approval remains with the user.
- Verdict: **accepted for P00 foundation scope; ready for user approval and merge**.
- Supersedes the outstanding findings in [the first PR #2 review](G0-PR2.md). Earlier verdicts remain historical evidence about their specified revisions.

## Evidence and acceptance

| Criterion | Evidence | Result |
|---|---|---|
| Complete native dependency locks | Native 3.10.22/3.12.4 generation; 41/39 pins | Accepted. The missing 3.10 conditional distributions are included. |
| Installation cannot silently fill gaps | Four clean local venvs; no-deps installs; exact inventory audit and pip check | Accepted. Both per-interpreter inventory pairs are identical. |
| Original defect fails closed | Isolated 3.10 scratch lock and environment omit tomli and exceptiongroup | Accepted. Audit exits 1 on the missing transitive dependencies even when inventory and scratch lock agree. |
| Reproducibility on hosted runners | [CI run 37216286664](https://github.com/kaporli/pob2-tools/actions/runs/37216286664) at the implementation commit | Both Windows jobs pass. Logs show 41 pins checked twice on 3.10 and 39 twice on 3.12; inventory comparisons pass. |
| Honest future-service expectations | Complete synthetic inputs, positive/negative contract probes, narrow missing-service exceptions | Accepted for P00. Malformed inputs, missing snapshots and broken imports are ordinary failures; an implemented service requires a production binding. |
| Local tests | Fresh 3.10 and 3.12 offline suites | 116 passed, 8 expected failures on each. |
| Engine regression and combined suite | Fresh 3.12 venv, PoB ce566ea | 146 passed, 12 expected failures, exit 0. |
| Hosted offline behavior | Both CI logs inspected | 111 unit tests passed, 7 expected failures; local integration skipped without LuaJIT; all 34 engine tests skipped for the required missing-runtime reason. |

Durable inventories and the independent negative check are in
[pr2-fixes evidence](../evidence/P00/pr2-fixes/validation.json).
The [implementation handoff](../worklog/PR2-fixes.md) records reproduction commands.

## Scope decision for PR2-R02

P01 owns normalized record schemas and P02/P08 own production adapter/preparation
coverage. The follow-up does not invent these future schemas to satisfy premature
tests. It removes invalid speculative production calls, tests the F05 behavior
probes against explicitly labelled local doubles, and uses one narrowly scoped
missing-service check for each future module. When a module appears, that check
fails until the owner supplies real accepted-record fixtures and coverage.

This is an explicit correction to P00's acceptance approach, not a claim that a
synthetic prepare service or future engine lifecycle has been implemented.
`tests/MANIFEST.md` records the required P02 cwd, bounded-timeout, worker-death and
replacement cases, including an independent hard deadline with process-tree
cleanup. The unbounded raw-Lua unit test and invented evaluate_raw API are gone.

## Reassessment and disposition

PR2-R01 and PR2-R02 are closed for P00's assigned foundation scope. Combined with
the four corrections accepted in the prior review, **G0 is accepted**. No prior
accepted gate is invalidated and no product contract changes are required.
P01-T01 can now proceed on the accepted foundation.

Residual limits: bootstrap/build tooling is explicitly unpinned; real engine CI
is not provisioned; production P02/P08 behavior, current-patch gameplay accuracy,
market access and optimization quality remain their own future gates. Expected
failures are tracked legacy defects or explicitly absent future services.

No blocking finding remains from this review. GitHub approval and merge were
not performed by the assistant. A following documentation-only commit records
this verdict; its CI must also be green before the user merges the PR.
