# P02-T01 final repair verification

- PR: [#4](https://github.com/kaporli/pob2-tools/pull/4), specification 1.0.
- Verified implementation: `478aaae4606d32e35bed1ef3e47001659792a665`.
- Follow-up: load-allowance metadata is capped against floating-point deadline roundoff, with a deterministic clock regression; see the repair handoff's hosted-CI note.
- Author/reviewer: Codex, 2026-10-06. This verifies my own repairs; it is not a separate engineer's review.
- Verdict: **accepted for P02-T01 scope**, conditional on successful hosted checks for the PR head before merge.

## Finding disposition

R12 is resolved: load, blank creation and primitive requests invalidate reusable state before mutation. Successful evaluation publishes state only after the whole operation succeeds. Both synthetic partial failures and real-PoB configuration-then-skill-selection failures force a clean reload on the next request. The independent probe now has zero changed output keys after recovery, including truthful reload provenance.

R13 is resolved: loading, primitives and required identity retrieval consume one monotonic evaluation deadline. Startup and cleanup retain separate documented bounds. Independent supervised tests cover individually short stages exceeding the combined budget, slow individual stages, a wedged load, disposal/recovery and a successful request that fits. The original combined-stage probe now raises timeout instead of returning a late success.

Earlier verified repairs remain covered: ordinary A-B-A, content-sensitive loading, fatal malformed-load recovery, exact versus blank loading, parent cwd, typed errors and worker replacement. No remaining blocker was identified in the final diff and regressions. Adapter version p02-t01.2 separates this behavior from p02-t01.1; lifecycle evidence was regenerated.

## Validation

| Check | Observed result |
|---|---|
| Offline unit/local integration, Python 3.12.4 | 631 passed, 5 xfailed |
| Offline unit/local integration, Python 3.10.22 | 631 passed, 5 xfailed |
| Narrow adapter/supervisor suite | 62 passed |
| Real-engine adapter suite | 16 passed |
| Full real-engine suite, Python 3.12.4 | 48 passed, 1 xfailed, 636 deselected |
| Generated schemas | All 20 match |
| Lifecycle A-B-A | 675 keys, zero difference |

Commands and acceptance mapping: [repair handoff](../worklog/P02-T01-final-repairs.md).
Adverse-case results: [replayed independent probes](../evidence/P02/repair-r12-r13-probes.json).
Original failed results and the [independent follow-up review](P02-T01-followup.md) are retained.

## Reassessment

P02-T01 is accepted for process isolation, faithful initial loading, state isolation, bounded evaluation and tested recovery. G0 and P01 remain accepted. The next planned task is P02-T02; this acceptance does **not** grant G1 or accept P02-T02 through T05.

The PoB checkout is the existing ce566ea checkout with recorded local modifications. These are synthetic and PoB-derived checks, not gameplay accuracy evidence. Content-level pinning/patch compatibility, legality, primitive units/ownership and semantic export checks remain their later tasks. Actual native crashes and concurrent worker pools remain unverified. Expected failures still name future P02/P08 work.

The user retains GitHub approval and merge; no approval or merge was submitted by this verification.
