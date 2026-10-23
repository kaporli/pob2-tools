# P04 / PR #10 follow-up repair verification

> Historical review of the commits named below. Current task state and follow-ups are on [GitHub Issues](https://github.com/kaporli/pob2-tools/issues/23); this snapshot is not a current assignment list.

- Specification: 1.0; P02-T05 support/variant follow-up and P04-T01 through T05, with provider access still bounded by D02.
- Implementer and reviewer: Codex, 2026-10-17. This is self-verification, not a second independent reviewer.
- Starting implementation: `f7561b91bf41277d4d6bcacc541da2999715b495`.
- Repair identity: the commit introducing this report, parser version `p04-t01.3`.
- Verdict: **accepted for the declared parser scope**. F1 and F2 in [the follow-up review](P04-followup.md) are closed. Merge PR #10 once both checks on the pushed head succeed. Engine longevity is not accepted by this verdict.

## Repairs and acceptance

| Finding | Change | Verification |
|---|---|---|
| F1: standalone item-text bypass | Both entry points use the same affix/readiness checks. Failed modifiers and the item itself retain partial status; XML builds propagate it to equipped variants. Raw text and modifier categories are retained. | Known, unknown, ambiguous, out-of-range and name-only items agree across both paths. Serialized/reloaded standalone items still block item and build exports when equipped on an otherwise clean build. CLI corpus reload independently confirms the unknown-affix case. |
| F2: numeric boundaries | Numeric item properties use strict finite conversion. Invalid integer ranges are rejected at their source fields. Produced items are schema/semantically validated, with source provenance attached, before successful parser output. Config overflow becomes a typed invalid parse before hashing. | API cases cover invalid quality/armour/energy shield, overflow, NaN/infinity and negative item level/requirement/count. CLI repeats invalid parses through the cache and verifies stored issues and unchanged original bytes. Valid decimal/exponent inputs remain supported. |
| Stale successful parse reuse | Parser version advances from `p04-t01.2` to `.3`, which is part of parse identity. | Original context-aware cache probes still pass. Re-ingest is unnecessary: reparse retained source bytes to replace affected normalized records. |

No record schema or existing canonical identity definition changed. No affix IDs were invented to satisfy export. Partial items remain valid records that cannot produce complete exports. A malformed recognized number produces no normalized build or item.

## Evidence

All paths below are under [PR-10/repairs](../evidence/PR-10/repairs/). Historical failing probes and memory-limit terminations remain under [followup](../evidence/PR-10/followup/); none was overwritten or relabelled a pass.

| Check | Result |
|---|---|
| Offline unit/integration suite, CPython 3.12.4 | 1,369 passed, 1 pre-existing P08-T01 xfailed; `offline-py312.txt` |
| Same suite, CPython 3.10.22 | 1,369 passed, same xfail; `offline-py310.txt` |
| New regression evidence against unchanged production code at f7561b9 | 36 failures and 57 passes across the two repair/CLI modules; `regressions-on-f7561b9.txt`. All 93 pass on the repair. Of 43 additions, 36 expose old failures and seven are controls/already-rejected cases. |
| Original independent probes plus follow-up edge cases, both interpreters | Original repairs retained; standalone unknown affix is partial/export-incomplete; all three numeric boundary probes are typed invalid; `observations-py310.json`, `observations-py312.json` |
| Schema freshness | All 20 schema files match |
| Pyflakes, changed production/test Python files | No findings |
| Full native engine suite, Python 3.12 | 152 passed in 105.22 s; sampled pytest working-set peak 1,312,374,784 bytes; `baseline-full-*` |
| Full native engine suite, Python 3.10 | 152 passed in 79.12 s; sampled aggregate process-tree working-set peak 1,479,012,352 bytes; `final-py310-full-*` |

Native tests use PoB `ce566eac45ea8a86477f513c7ee65a1ebe60014e` at `C:/Users/Elias/PycharmProjects/PathOfBuilding-PoE2`. The existing checkout and deleted submodule were not changed. The native bridge/bootstrap were not changed. These tests compare synthetic PoB-derived fixtures, not gameplay.

Commands from the repository root:

```powershell
python -m pytest tests/unit tests/integration -q -p no:cacheprovider --tb=short
& '.venv/pr2-validation/py310-a/Scripts/python.exe' -m pytest tests/unit tests/integration -q -p no:cacheprovider --tb=short
python scripts/generate_schemas.py --check
python docs/evidence/PR-10/followup/review_followup.py
& '.venv/pr2-validation/py310-a/Scripts/python.exe' docs/evidence/PR-10/followup/review_followup.py
& docs/evidence/PR-10/repairs/monitor_engine.ps1 -Lane full -Run final-py310 -Python .venv/pr2-validation/py310-a/Scripts/python.exe
```

The 3.12 native run used the same monitor's initial revision, which sampled only its pytest process; the final revision also accounts for descendants, including Windows venv launchers. Both versions sample every two seconds and stop at 4 GiB or 240 s. Sampling is a diagnostic safeguard, not a strict production memory ceiling. Use a new `-Run` name to avoid overwriting evidence. The regression replay used an isolated f7561b9 checkout with only the two new test modules copied in; production files remained at that commit.

## Memory investigation: still open

This repair does **not** fix or explain the intermittent native memory growth. This session's bounded native runs all completed; successful retries do not invalidate the previous 4+ GiB terminations or the engineer's 17.6 GB observation.

In addition to the two full-suite runs:

- The older F11 module passed alone: six tests, sampled peak 545,898,496 bytes (`baseline-f11-*`).
- Repaired P04 passed twice without instrumentation: 53 tests each, peaks 882,610,176 and 922,390,528 bytes (`baseline-p04-*`, `baseline2-p04-*`). The `baseline` prefix refers to the unchanged native bridge; these runs include the parser repairs.
- Per-call instrumentation on repaired P04 passed: 53 tests, peak 858,492,928 bytes (`trace-p04-*`). It logs test names, handler names, XML hashes and Lua heap after each call. Lua heap fell to about 145 MiB at final explicit collection.
- Exact f7561b9 P04 passed with the same per-call instrumentation and again in quiet mode without instrumentation: 53 tests each, peaks 918,654,976 and 856,522,752 bytes (`exact-f7561b9-p04-*`, `exact-f7561b9-quiet-p04-*`). No native runs overlapped.

Because there was no failing diagnostic run, there is no identified failing operation or causal comparison. No speculative GC/JIT change or automatic retry was shipped. The diagnostic plugin and monitor are evidence tools only. Production worker memory enforcement/recycling remains unimplemented; timeout recovery does not establish a memory bound.

This is a separate unresolved reliability issue, not a remaining parser correctness finding. Merge acceptance here covers P04's offline normalization and tested round-trip behavior. It does **not** authorize a four-hour search or a production release requiring long-lived engine reliability. Before that capability is accepted, reproduce a failing operation and repair it, or implement bounded worker lifecycle containment with failure/recovery and semantic-parity evidence as required by the follow-up review.

## Reassessment

P05 offline item import/pool work may consume reparsed `.3` records. Reparse sources previously accepted by the standalone item route and invalidate evaluations derived from affected normalized records. D02 provider parsers remain blocked. No production search, live-trade, gameplay-validation or longevity gate is opened by this review. The next independent engineering task is the native worker reliability issue above; do not treat these successful runs as its completion.
