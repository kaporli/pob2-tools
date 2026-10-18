# PRs 15–17 repair verification

Date: 2026-10-18. Self-verification of the requested repairs; no product gate
or gameplay claim is accepted by this report. The original reviews and their
probe outputs remain unchanged. PR #14 is merged as `3046609`.

## Findings repaired

| PR / original head | Finding | Result |
|---|---|---|
| #15 / `63d8a58` | R1: unterminated reminder discards modifiers | Refused at the section boundary or EOF with `unterminated_reminder`; no reduced item or listing is emitted. Balanced single/multiline and nested reminders preserve the following modifier and identity. |
| #15 / `63d8a58` | R2: impossible capture timestamps accepted | Strict UTC representation plus calendar/time parsing; capture observed time, listing override and listing creation time all reject invalid dates. CLI exits 2 and stores no items/listings. Valid leap days and fractional seconds are preserved. |
| #16 / `644c7b8` | R1: foreign catalog/realm/league enters pool | Refuse the whole mixed-scope input before deduplication, enabling matching or sampling. Errors sort the offending record IDs. Empty listing scope does not match a populated profile scope. |
| #16 / `644c7b8` | R2: duplicate readiness depends on order | Same-hash records with different canonical item data or parse readiness are refused in either order. Equivalent duplicates are collapsed deterministically; all-partial duplicates remain excluded. |
| #17 / `9f32dfe` | R1: activation and attribution are nonblocking | Both remain open **blocking** gaps. Method prerequisites and measurement dependencies explicitly include them. Resolving every other gap still blocks the protocol. First-use activation and reuse need evidence or timed movement; unassigned secondary damage cannot enter the score. |

The final adversarial pass also found that a modifier ending in `(crafted)`
could falsely close an earlier reminder. The parser now tracks parenthesis
depth, refuses unbalanced sections and preserves valid nested reminders.
The two malformed-tail cases and one valid nested case are regressions.

Parser version is `p04-t01.5`. Its version participates in both ordinary parse
and market-import cache keys. Reparse affected older sources; previously
persisted results are not retroactively certified or silently deleted.

Pool callers must supply items for the pinned catalog and listings for the
profile's exact realm/league. They must reconcile duplicate readiness/content
conflicts upstream; the pool never picks whichever record happened to arrive
first. Two synthetic fixture scopes were corrected to match their profiles.

The P09 files were regenerated and hashed. The suite hash is
`d0820302432a1a047e11f1a066f0ae5b1ec12db141f84583db4afbf1349c6505`.
There are still 28 gaps: 4 resolved and 24 open (21 blocking, 3 ranking
sensitive). No new mechanics evidence or numerical cycle result was invented.
P06/P07 must implement the protocol before a score can be produced.

## Verification

Windows, Python 3.12.4 and 3.10.22. Full offline command:
`python -m pytest tests/unit tests/integration -q -p no:cacheprovider --tb=short`.

| Checkout tested | Python 3.12 | Python 3.10 | Evidence |
|---|---|---|---|
| #15 code `2892116` on merged #14 | 1,606 passed, 1 xfailed | 1,606 passed, 1 xfailed | `docs/evidence/P05-T02/repairs/offline-py*.txt` |
| #16 code `0dfea0f`, including repaired #15 | 1,646 passed, 1 xfailed | 1,646 passed, 1 xfailed | `docs/evidence/P05-T03/repairs/offline-py*.txt` |
| #17 code `01c3aea` on merged #14 | 1,569 passed, 1 xfailed | 1,569 passed, 1 xfailed | `docs/evidence/P09-T01.1/repairs/offline-py*.txt` |

The existing xfail is the unimplemented P08 prepare service. Schema freshness
checks pass (20 files on #15/#17; 21 on #16). Pyflakes and diff whitespace checks
pass on the changed Python files. Final commits additionally carry documentation,
evidence and branch reconciliation; GitHub checks must pass on those pushed heads.

All 11 affected native item-conversion tests pass on **each** interpreter
against clean pinned PoB `ce566ea`. External monitor: 8.8 seconds / 523,739,136
bytes peak tree RSS on 3.12; 8.3 seconds / 565,305,344 bytes on 3.10; no guard
trigger. Logs are in `docs/evidence/P02-T01.1/suite-runs/repair-pr15-final-py312/`
and `repair-pr15-final-py310/`. These tests cover synthetic conversion fidelity,
not game observations. The unrelated whole native suite was not repeated.

Negative controls copied only the new tests onto the original reviewed heads,
then selected the repair cases on Python 3.12:

- #15: 26 failures, 8 passing valid-input controls.
- #16: 8 failures, 2 passing equivalent-duplicate controls.
- #17: 3 failures, including both independently unresolved prerequisites.

All selected cases pass in the repaired suites. Outputs are the
`negative-control-py312.txt` files beside each project's offline logs.

## Merge and remaining scope

#15 is rebased onto main after #14. #16 remains stacked on #15; merge #15
first, then retarget/reconcile #16 onto main if the merge method requires it.
#17 is rebased and retargeted to main. Shared delivery documentation is identical
across the repaired branches so it retains the full reassessment when they land.
Do not merge an obsolete checked-out feature branch over these repaired heads.

These repairs complete the reviewed import/pool/protocol slices. They do not
complete real slot-category coverage, clean seed replay, activation/charge/mana
rules, executable coverage, the 120-second evaluator, search, clear/boss
validation, four-hour recovery testing or reports. Provider ingestion and live
trade remain separate blocked tracks. See [delivery.md](../specs/delivery.md)
for concrete next assignments and preserved gate boundaries.
