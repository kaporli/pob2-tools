# P07-T01 evidence: one traceable Flicker Strike cycle

Captured 2026-10-18 on Windows 11, CPython 3.12.4, engine `external/PathOfBuilding-PoE2`
at `ce566ea` with a clean working tree. Everything here is PoB-derived computation by
method `pob-community-v2` (owner decision, D07 amendment 2026-10-18 (2)). No gameplay
measurement, no best-build claim.

## Result for the seed

**Not eligible.** The objective field `flicker_sustained_dps` is null. The coverage gate
(`pob2opt.coverage.decide`) refuses with 21 blocking gaps and one unsettled critical rule,
`attribution/flicker-sustained-v1`; the evaluator adds `gap-p07-attribution-table-unbound`
(22 in all). Hit and Run activation is no longer blocking: the
owner's method defines it (teleport re-enables it, as PoB applies it), scoped to
`pob-community-v2` only.

Diagnostic values, labelled `NOT ELIGIBLE` in the files, scoring document (Pounce disabled):

| Quantity | Value |
|---|---|
| Sustained, [0, 120), mana-limited | 231,631 |
| Burst, [0, 5) | 241,702 |
| Same rotation, mana ignored (comparison only; first deficit 22.7 s) | 458,685 |
| PoB TotalDPS at 5 charges, no rotation time (`proxy_only`) | 1,024,807 |
| Flicker Strike uses started / strikes counted | 23 / 253, all with the Charged Staff buff |
| Time in window | Whirling Assault 34.7 s, Flicker Strike 27.1 s, Charged Staff 1.0 s, waiting for mana 57.2 s |
| Mana flask uses | 10 |
| Indefinite sustain without waiting | no: one buff period needs 6,732 mana against 2,345 from regeneration and the flask |

Seed as imported (Pounce on, PoB applies Predator's Mark x1.24): 287,223 sustained,
299,711 burst. It carries an extra blocking gap (`gap-p07-not-scoring-document`).

Blocking gaps, in four groups (full list with requests in `seed-evaluation.json#/decision/blocking`):

1. Attribution: the P09-T01.2 ownership table, persisted as
   `benchmarks/p09-flicker-v1-attribution/proposed-v1.json` (table hash
   `sha256:b0a9fd762ab6991447140bd247c0a6efe85e66f0d4e0e887df90735175a9ef6e`), is a
   proposal. Until a reviewer accepts that hash, Flicker Strike, Whirling Assault, Charged
   Staff and Living Lightning II are unassigned.
   `evaluate_flicker(..., attribution_acceptance={reviewer, evidence_ids, table_hash})`
   applies it.
2. Rules no code or evidence establishes: Way of the Stonefist (passive 39595, three
   unparsed lines), Rage (`resource/rage`), Trinity, Bhatair's Vengeance, Blazing
   Critical, Concussive Runes, Living Lightning II.
3. Protocol: patch profile 0.5.5e is stale (`gap-p09-t011-patch-profile`), the seed's
   config condition inputs (`gap-p09-t011-config-conditions`), no reference result or
   reference build (`gap-p09-t011-reference-result`).
4. Attribution protocol gap `gap-p09-t011-attribution-rules`, same cause as 1.

## Agreement with P09-T01.2

The P09-T01.2 script gives 229,857 for the same document; this evaluator gives 231,631
(+0.8%). Two causes, both deliberate: time is integer microseconds with exact piecewise
mana integration instead of 10 ms steps, and the Charged Staff buff is checked at each
decision, so a buff expiring during Whirling Assault is refreshed before the next Flicker
Strike rather than after it. Burst is identical. The test
`test_seed_matches_p09_t012_community_cycle_within_one_percent` holds this.

## Fresh-worker agreement (`fresh-worker-agreement.json`)

`python scripts/p07_t01_flicker_cycle.py --live` captures every value twice, each through
its own `EngineAdapter` and worker processes (pid sets disjoint), evaluates both and
compares. Values identical, evaluations identical (same `evaluation_id`), and every value
equals the frozen P09-T01.2 bundle exactly (max relative difference 0). The working tree
was clean before and after. Flask data and the Charged Staff duration come from the new
read-only worker operation `cycle_inputs` (fixed Lua in `evaluation/protocol.py`).

The bundle reads Whirling Assault damage and Flicker ignite on the seed document only
(Pounce on). For the scoring document those two unscored values are null offline and
present live; the scored values do not depend on them.

## Review PR-18-22 repairs (R4 to R7)

| Finding | Repair | Regression |
|---|---|---|
| R4 scored table differs from the approved one | One persisted table keyed by coverage mechanic ids, identified by `table_hash`, used for coverage assignments and scoring. Acceptance must name the hash; the coverage rule must carry exactly the table's classes and cite `attribution-table:<hash>`, otherwise `gap-p07-attribution-table-unbound` blocks | `test_r4_*` |
| R5 assumed clean pinned provenance | Engine head, dirty state, scored document SHA-256 and applied state come from the capture (live adapter or frozen bundle, the latter bound to the seed manifest's document hash). Coverage receives them unchanged; an absent dirty key is unknown. A document or state mismatch blocks | `test_r5_*`, `test_frozen_bundle_carries_the_capture_identity`, engine test |
| R6 windows share identity | Only `[0, 120)` and `[0, 5)` can fill the v1 objective; other windows return `diagnostic_window`. The evaluation id covers objective, scenario file, method, windows, document, rotation, profile, parse evidence, config options, P09 resolutions, attribution table and acceptance, registry and closure hashes, eligibility and the values without worker pids | `test_r6_*` |
| R7 unsupported method runs the simulator | Only `pob-community-v2`; anything else returns `unsupported_method` with null objective before any simulation | `test_r7_*` |

The 12 regression cases (`tests/unit/test_pr21_review_probes.py`) were run against the
reviewed head `db40827`: 11 failed, the control case passed
(`repairs/negative-control-db40827.txt`). After repair all 12 pass
(`repairs/probes-after-py312.txt`). The live capture's head, dirty state, document hashes
and state equal the frozen bundle's (`fresh-worker-agreement.json#/provenance`).

## Files

| File | SHA-256 | What |
|---|---|---|
| `seed-evaluation.json` | `c746b523712d4a386a255dd72ab5eeaec2f28bc0cca878b49667e7705b32c8d8` | Scoring document: decision, blocking gaps, diagnostic, full action/impact trace, mana ledger, repeatable-cycle check, applied resolutions, ledger history, registry and closure hashes |
| `seed-as-imported-evaluation.json` | `1cd7baac4b155e5e6d9a0bfdb7e7023b9a8d1c76e640ea9c852af7de18537cb7` | Same, document as imported (diagnostic) |
| `fresh-worker-agreement.json` | `e055a604d29fa280f433fcefb78c2fc7f370f4a4ec0c3c97481c81f8ad5801d7` | Two live captures, pids, worker history, comparison with the bundle |
| `engine-py312.txt` | | Engine test tail |
| `offline-py312.txt`, `offline-py310.txt` | | Offline suite tails |
| `repairs/negative-control-db40827.txt`, `repairs/probes-after-py312.txt` | | R4 to R7 regression cases before and after repair |

Registry after the applied resolutions: hash `aba53d0b2a00ba88f1b6a6fc6900363b811d08e5418af9b0d6e2f0ce5732a75a`,
closure hash `09109aedd2d3f86f460e9e19c5433f2b24c82c673de5002343ada2cdb652115b`.

## Repeat

```
python scripts/p07_t01_flicker_cycle.py                 # offline, frozen bundle
POB2_ROOT=<clean ce566ea> python scripts/p07_t01_flicker_cycle.py --live
python -m pytest tests/unit/test_p07_t01_flicker_cycle.py -q
python -m pytest -m engine tests/engine/test_p07_t01_flicker_cycle_engine.py
```
