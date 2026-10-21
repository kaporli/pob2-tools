# P06 evidence: executable coverage for the Flicker seed

Captured 2026-10-18 on Windows 11, CPython 3.12.4 and 3.10.22. Nothing here
is a gameplay measurement or a score.

| File | What |
|---|---|
| `seed-engine-mod-support.json` | PoB-derived. For the P09-T01.1 seed export loaded on a clean checkout of `ce566ea`: every equipped item line and allocated passive line with PoB's parse verdict (`parsed`, unparsed remainder `extra`), and every config variable holding an input or placeholder with PoB's own `control.shown` test |
| `seed-coverage-<scenario>.json` | Coverage of the seed under registry `p06-flicker-v1` for each of the five `p09-flicker-v1` scenarios: registry hash, PoB inputs used, findings, DataGaps and the `decide` result |
| `offline-py312.txt`, `offline-py310.txt` | Offline suite logs |
| `repair-negative-control-3cc334d-py312.txt` | PR #19 review probes as regression tests, run on the reviewed head `3cc334d`: 5 failed |
| `repair-review-probes-py312.json` | `docs/evidence/PR-18-22/review_probes.py` run on the repaired tree |
| `repair-engine-loadout-py312.txt` | Native checks that coverage reads the loadout and custom modifier blocks PoB selects |
| `repair-f1-negative-control-128064c-py312.txt` | Re-review F1 case on `128064c`: fails |
| `repair-f1-rereview-probes-py312.json` | `docs/evidence/PR-19-22-rereview/probes.py` on the repaired tree |

## What the engine probe found

The capture is bound to the document hash, selected sets, clean engine
commit, each equipped item's id and text hash (18 items, three of them
jewels), the 126 allocated nodes and the config inputs.

15 item lines and 7 passive lines that PoB leaves unparsed or without a
modifier list, including Martial Adept ("When you gain Combo, gain an
additional Combo"), Martial Master ("Gain Combo from all Attack Hits"), Way of
the Stonefist (glove transformation), Polcirkeln's shatter line and the charm
use conditions. Config: PoB applies `FlickerStrikeBypassCD = true` (an
option default, invisible in the XML) and the `enemyDistance` placeholder 20;
both are shown for this build. Other default-on options are hidden by PoB's
own test and are reported as not applicable.

## `flicker_sustained_v1` coverage of the seed

Not eligible. Unsettled critical rules: `activation/hit-and-run-reuse`,
`attribution/flicker-sustained-v1`. 32 blocking findings, 11 ranking
sensitive, 59 not applicable, plus 10 open blocking P09 gaps.

| Class | Rules or subjects |
|---|---|
| missing data | clean engine rerun, rotation policy, `/target_entities.conditions`, reference build and result |
| missing implementation | Combo, Power Charge state, Culmination II, Ailith's Chimes, Perpetual Charge, Martial Adept, Martial Master, Charged Staff consumption, Rage, mana flask and sustain, attribution, Way of the Stonefist lines |
| unknown rule | Hit and Run reuse, Flicker `Bypass CD` default, Trinity, Bhatair's Vengeance, Blazing Critical, Concussive Runes, Living Lightning II |
| unassigned damage | Flicker Strike, Whirling Assault, Charged Staff, Living Lightning II, default Quarterstaff attack (no rotation, so every manual skill counts) |
| unvalidated (ranking) | PoB-owned skill, support, mana and timing rules; `enemyDistance`; one ring line PoB gives no modifier |
| not applicable | kill-, hit- and flask-dependent effects (Herald of Ice/Thunder, Wind Dancer, Ghost Dance, charm and flask lines, on-kill charges) |

The four clear and boss workloads add their own missing scenario data and the
kill and hit dependent effects become blocking there.

## Reproduce

```
POB2_ROOT=<clean checkout of ce566ea> python scripts/p06_seed_engine_mod_support.py   # engine
python scripts/p06_seed_coverage.py            # offline
python scripts/p06_seed_coverage.py --check
python -m pytest tests/unit/test_p06_coverage.py -q
```
