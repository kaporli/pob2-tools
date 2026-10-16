# P04 / PR #10 repair review — 2026-10-16

- Specification: 1.0; P01/P02 support-state follow-up and P04-T01 through T05.
- Reviewed head: `f7561b91bf41277d4d6bcacc541da2999715b495`, against `08d400f6ac571b840d1754ba35fa792a899e34d2`.
- Reviewer: Codex.
- Verdict: **changes_required**. The original reproduction cases are repaired, but R2 and R6 have remaining paths below. Engine-suite stability is separately unresolved.

This supplements [the original review](P04.md); the historical probe files and their old results are preserved.

## Findings

### F1 — P1 — R2 remains open for standalone item text

Location: `pob2-optimizer/pob2opt/parsers/dispatch.py:58`–96 (`_item`), compared with `parsers/pob.py:451` (`_check_items`).

The PoB XML path now applies catalog affix checks and propagates failures correctly. The public item-text path still calls `import_item`, checks only the base and name-only readiness, and returns the item without the affix checks. This is a format-dependent bypass of the new protection.

Independent reproduction on both interpreters: take the b01 equipped rare and append `SYNTHETIC +3 to unknown things`. As part of the XML document, it is partial, has `unresolved_affix`, and its item export is incomplete. The identical item text passed to `parse_document` directly is **complete**, has **no issues**, leaves the unknown modifier **resolved**, and produces a **complete item export**. This route is part of P04's advertised format dispatcher and is the input path future equipment pools will consume.

Required repair: share the item readiness/affix validation between standalone item parsing and build parsing. Preserve raw text and modifier categories; do not assign invented native IDs merely to satisfy export. Ensure the returned ItemInstance and ParseResult both retain unknown/ambiguous/out-of-range status, and any build using that item remains non-recommendable.

Acceptance: feed identical known, unknown, ambiguous, out-of-range and name-only items through both entry points against the same catalog. Assert consistent readiness/status. Persist/reload the standalone item without its ParseResult and verify that its export and an equipped build's export cannot become complete. Keep the complete supported item as a positive control.

### F2 — P2 — R6 does not yet enforce finite, valid numeric values across the parser

Locations: `evaluation/support.py:161` (`source_number`), `evaluation/itemtext.py:110` (`_parse_number`) and `:390` (item-level conversion), `parsers/pob.py:306` (only the build is validated here).

The reported malformed integer cases now become typed invalid parses. Three related boundaries remain, independently reproduced on Python 3.10 and 3.12:

1. A config input with `number="1e999"` is converted to infinity. Build hashing then raises uncaught **NotANumber**, rather than returning a field-specific ParseIssue. The outer handler catches MalformedSource, which this path does not raise.
2. `Quality: broken` is still converted into the string `"broken"` by the old permissive `_parse_number`. The public parser returns **complete with no issues** and an ItemInstance whose quality is that string. The downstream exporter refuses this value, but the parser's completeness claim is already wrong.
3. `Item Level: -1` returns **complete with no issues** and a **recommended build export**. Independently calling `validate_record` on the item rejects it. Build validation alone does not validate the referenced ItemInstance, and a later corpus write cannot substitute for a typed parse result.

Required repair: use strict finite-number conversion for documented numeric fields, and enforce the existing record range constraints before successful parser output. Validate produced items as well as builds. Return a precise source field/path for recognized input failures; do not catch arbitrary programming exceptions or replace malformed values with defaults. Item-property parsing must not silently reinterpret a numeric field as free text.

Acceptance: API and CLI cases for overflowing config/item numbers, malformed quality/armour/energy shield, and negative values forbidden by the relevant schema. Results must be invalid or explicitly partial/non-recommendable, not complete or uncaught exceptions. Preserve source evidence and confirm valid decimal/exponent values still work.

## Original findings reassessed

| Finding | Disposition at this head | Independent evidence |
|---|---|---|
| R1 generated-group supports | Behavioral repair accepted | Original PoB-saved Spear Stab case is now partial and non-recommended. The preview still loses the support, correctly disclosed rather than certified. Default-setting extra gems are covered by focused regressions. |
| R2 persisted readiness | Repaired for builds parsed from XML; **still open** for standalone item text | Original unknown-affix/name-only build cases are partial and non-recommended. F1 demonstrates the remaining route. |
| R3 context-aware parse identity | Repair accepted for reviewed scenarios | Independent catalog A/B replay now yields different parse IDs and correctly bound builds. Tests cover A→B→A, changed tree/format options, stored references and cached unsupported exit codes. |
| R4 support gem migration | Repair accepted | Removing the support gem while retaining its effect now records the missing gem and makes the migrated build partial. Walker includes nested support entries, passive-choice nodes and group slots. |
| R5 v1 main group | Behavioral repair accepted | Independent pinned-engine probe: both exports select Ball Lightning and report TotalDPS **81.75**. Legacy identity behavior is preserved. |
| R6 malformed numeric inputs | Original cases repaired; **still open** at numeric boundaries | Invalid level/node/active-gem integers return invalid. F2 covers unhandled finite/range/property checks. |
| R7 numeric comparator | Repair accepted for parity semantics | Zero→nonzero and added-stat probes now report differences; tolerance and explicit non-finite rules have unit coverage. Equality of two non-finite outputs establishes only parity, never usable optimizer output. |
| R8 independent audit | Repair accepted for declared fields | The original valid main-group corruption now produces a mismatch. Focused cases cover group enabled/index and gem identity. Worklog now explicitly excludes config, other item properties and attribute choices from its audit claim. |

The schema versioning, conservative generated-group refusal and documented PoB-only scope remain reasonable. Provider parser acceptance is still blocked on D02. This review does not request provider integration or real gameplay measurements in this repair.

## Verification

| Check | Reviewer result |
|---|---|
| GitHub checks, exact head | Python 3.10 and 3.12 success |
| Focused repair/CLI/comparator tests, Python 3.12 | 64 passed |
| Full offline unit/integration suite, Python 3.12.4 | 1,326 passed, 1 existing P08-T01 xfailed |
| Full offline unit/integration suite, Python 3.10.22 | 1,326 passed, 1 existing P08-T01 xfailed |
| Schema freshness | 20 files match |
| Original offline probes plus new edge cases | Reproduced on both interpreters; matching observations |
| Full engine suite, monitored | **Stopped at memory limit**, not a pass: 24 progress dots, 4,625,018,880-byte sampled working set, 34.93 s |
| P04-only engine module, fresh monitored process | **Stopped at memory limit**, not a pass: 47 progress dots, 4,617,752,576-byte sampled working set, 46.84 s |
| Short independent generated-support/v1 engine probe | Completed exit 0, sampled peak 458,506,240 bytes, 6.08 s |

The engineer's committed log records a successful 152-test engine run. That run is not denied, but neither attempted pytest engine run completed in this review. The 33/40 old-head regression-failure count was not independently repeated; the old independent probes were replayed instead.

Commands for offline checks:

```powershell
python -m pytest tests/unit/test_p04_review_repairs.py tests/unit/test_p04_parse_cli.py tests/unit/test_p04_stat_compare.py -q -p no:cacheprovider
python -m pytest tests/unit tests/integration -q -p no:cacheprovider
& '.venv/pr2-validation/py310-a/Scripts/python.exe' -m pytest tests/unit tests/integration -q -p no:cacheprovider
python scripts/generate_schemas.py --check
python docs/evidence/PR-10/followup/review_followup.py
& '.venv/pr2-validation/py310-a/Scripts/python.exe' docs/evidence/PR-10/followup/review_followup.py
```

The old offline probe is run in memory with only its renamed test-comparator call changed from `_stat_differences` to `stat_differences`. Historical scripts/results are unchanged. New observations are in `docs/evidence/PR-10/followup/observations-py310.json` and `observations-py312.json`; the isolated original replay is also saved as `offline-py310.json` and `offline-py312.json`.

Pinned engine: `ce566eac45ea8a86477f513c7ee65a1ebe60014e` at `C:/Users/Elias/PycharmProjects/PathOfBuilding-PoE2`, with existing untracked files and no tracked modifications reported. Native probes ran serially. Their XML fixtures are synthetic compositions saved by PoB, not gameplay evidence.

The two pytest runs used a PowerShell parent checking its own child process's working set every two seconds, terminating that process above 4 GiB; this explains the recorded exit -1. Limits are review safeguards, not changes to pytest or the engine. The first run also had a 240-second time limit, the second 180 seconds; both hit memory first. Logs/measurements are `engine-*` and `p04-engine-*` under the followup directory. The reusable `monitor_engine.ps1` performs the same commands/4-GiB guard (240-second limit) with lanes `full`, `p04`, or `probe`. The successful short probe has `probe-*` monitoring output and `engine-observations-py312.json`; it redirects the old engine probe's output directory so original evidence is preserved.

## Engine reliability and next steps

Memory growth is now independently observed in both the full suite and the isolated P04 module. It is not confined to the older file named in the handoff. Progress-dot counts locate the point reached in collection order but are not stack traces or proof of which operation caused the growth. The cause and whether this PR introduced it remain unverified; this review did not run a matched baseline memory experiment.

Track a separate engine reliability investigation before accepting long-lived evaluation or a four-hour search. Its concrete deliverable should be: the failing test/order with `-vv` and per-test memory samples, a bounded reproduction against both baseline and repaired heads under the same pinned engine, and a fix or worker-lifecycle containment backed by bounded repeat runs. Preserve failing evidence; do not select only successful retries. If isolation/recycling is the chosen containment, verify that it preserves semantic results and enforce a coordinator memory bound. This is not permission to relabel killed runs as passes.

Repair F1/F2 before merging this head, then rerun the affected offline and persistence tests. Retain the successful R1/R3/R4/R5/R7/R8 evidence rather than re-opening those behavioral findings without cause. Revisit full engine acceptance when the reliability investigation provides reproducible evidence. P05/P06 production consumers must not rely on the remaining complete flags; independent synthetic development can proceed. No new owner preference or access decision is needed for these repairs.

No production code, dependency installation or original evidence was changed. The pre-existing deletion of `external/PathOfBuilding-PoE2` is preserved. This review adds only local review artifacts; no GitHub review/comment, push or merge was performed.
