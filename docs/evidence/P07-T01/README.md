# P07-T01 evidence: one traceable Flicker Strike cycle

Captured 2026-10-18 on Windows 11, CPython 3.12.4, engine `external/PathOfBuilding-PoE2`
at `ce566ea` with a clean working tree. Everything here is PoB-derived computation by
method `pob-community-v2` (owner decision, D07 amendment 2026-10-18 (2)). No gameplay
measurement, no best-build claim.

## Result for the seed

**Not eligible.** The objective field `flicker_sustained_dps` is null. The coverage gate
(`pob2opt.coverage.decide`) refuses with 21 blocking gaps and one unsettled critical rule,
`attribution/flicker-sustained-v1`. Hit and Run activation is no longer blocking: the
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

1. Attribution: the P09-T01.2 ownership table is a proposal. Until a reviewer accepts it,
   Flicker Strike, Whirling Assault, Charged Staff and Living Lightning II are unassigned.
   `evaluate_flicker(..., attribution_acceptance={reviewer, evidence_ids})` applies it.
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

## Files

| File | SHA-256 | What |
|---|---|---|
| `seed-evaluation.json` | `4cb1cfb7deb79b7cb13cc56c98f90312c95d1e5e6e43ef2354110e7f5d62586d` | Scoring document: decision, blocking gaps, diagnostic, full action/impact trace, mana ledger, repeatable-cycle check, applied resolutions, ledger history, registry and closure hashes |
| `seed-as-imported-evaluation.json` | `c5f4e3a214de2d713a85e3b5b360ae402ed0bcb962aafc09d1ee810304f83f99` | Same, document as imported (diagnostic) |
| `fresh-worker-agreement.json` | `a5e89942391f7eeb26024ee2fda3341b501da2262e6baf93d3ec095c2dcee643` | Two live captures, pids, worker history, comparison with the bundle |
| `engine-py312.txt` | | Engine test tail |
| `offline-py312.txt`, `offline-py310.txt` | | Offline suite tails |

Registry after the applied resolutions: hash `aba53d0b2a00ba88f1b6a6fc6900363b811d08e5418af9b0d6e2f0ce5732a75a`,
closure hash `09109aedd2d3f86f460e9e19c5433f2b24c82c673de5002343ada2cdb652115b`.

## Repeat

```
python scripts/p07_t01_flicker_cycle.py                 # offline, frozen bundle
POB2_ROOT=<clean ce566ea> python scripts/p07_t01_flicker_cycle.py --live
python -m pytest tests/unit/test_p07_t01_flicker_cycle.py -q
python -m pytest -m engine tests/engine/test_p07_t01_flicker_cycle_engine.py
```
