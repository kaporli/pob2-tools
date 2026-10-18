# P09-T01.2 evidence: clean seed replay, cycle rules and damage ownership

Captured 2026-10-18 on Windows 11, CPython 3.12.4, against
`external/PathOfBuilding-PoE2` at `ce566ea` with an empty
`git status --porcelain --untracked-files=all` before and after every run.
Everything here is PoB-derived or secondary web text. Nothing is a gameplay
measurement. The `pob-community-v2` value (owner's method, D07 amendment 2) is
computed; no `pob-cycle-v1` value is.

| File | What |
|---|---|
| `replay.json` | The seed loaded through `EngineAdapter` on the clean pin: all outputs with Flicker Strike main, 0 to 5 forced charges with Charged Staff on and off, Whirling Assault, Charged Staff, a one-group-at-a-time sweep, four benchmark documents (Pounce off; with and without Charged Staff and Hit and Run), and read-only diagnostics (enemy values, Config-sourced, conditional and enemy modifiers, speed and added-damage sources, flasks) |
| `community-cycle.json` | `pob-community-v2`: the full 120 s action and strike timeline for the seed as imported and with Pounce off, sustained and burst values, time per action, a mana ledger, plain PoB numbers and the community reference's conditions on the seed |
| `mechanics-rules.json` | 22 rules for the cycle with status, parameters and evidence (engine citations with file SHA-256 and line), and the proposed damage ownership table |
| `web-evidence.json` | Retrieved web text with URL and date, and the pages that refused automated access |
| `offline-py312.txt`, `engine-py312.txt` | Test logs |

## Replay agreement

`python scripts/p09_t01_2_seed_replay.py` compares against P09-T01.1:
734 of 734 imported outputs, 36 charge-table values, 8 Charged Staff disabled
values, 5 Whirling Assault values and 7 enemy values agree exactly
(relative tolerance 1e-9, 0 differences). The earlier capture's unchecked
working tree therefore did not change these numbers;
`gap-p09-t011-engine-checkout-state` is resolved with `replay.json`.

## What the sweep found

| Finding | Effect on Flicker Strike | Rule |
|---|---|---|
| Pounce's Predator's Mark counts Whirling Assault's 8 Living Lightning minions: enemy takes 24% increased damage | x1.24 per-strike damage | `pounce-predators-mark`: off in benchmark documents (owner Q4) |
| Herald of Ice, Herald of Thunder | about 4% and 5% each | `persistent-buffs`: kept (owner Q4) |
| Charged Staff buff | +9.7% at 5 stacks; PoB reads stacks from the same charge count as the extra strikes | `charged-staff-buff-ownership`: stacks from charges Charged Staff consumed |
| Hit and Run | 40% more speed only (9.3279 vs 6.6588 strikes per second) | `hit-and-run-reuse`: blocking, three variants |
| Other groups and every imported config input | none | `pob-default-states` |

## Rule status

Resolved (14): extra strikes, no charge gain during Flicker Strike, Perpetual
Charge per charge, Surpassing distribution, Combo cap and decay, Whirling
Assault use, Charged Staff use, Pounce mark off, persistent buffs, PoB
default states, Flicker Strike's "Bypass CD?" default (no effect on the pin),
Charged Staff period (owner Q10 and decision 2: pressed when the 37.5 s buff
expires), Flicker Strike mana once per use (PoB's ManaCost is an upfront
per-use cost; its ManaPerSecondCost multiplies by the strike rate and is not
used), mana sustain (pool, regeneration and the seed's mana flask from PoB;
Mageblood grants Mage's Legacy stat bonuses only and leaves flasks unchanged).

Conditional (5): strike timing, Charged Staff buff ownership, 'consumed a
Power Charge Recently', enemy distance (PoB placeholder 2 m; 1 m gives +10.5%,
3.5 m gives -15.1% per strike), Way of the Stonefist (PoB leaves it, Martial
Adept and Martial Master unparsed; the imported gloves are already Fists of
Stone).

Blocking (3): Combo per strike, Whirling Assault's own Combo, Hit and Run
reuse. Under `pob-community-v2` these and the Surpassing, Perpetual Charge,
buff ownership and 'recently' rules are waived by the owner's decision;
mana and attribution still apply. Each rule names its P06 registry mechanic,
and `p06_ledger_resolutions` holds resolved rules in the
`pob2opt.coverage.CoverageLedger.resolve` shape (only the engine-checkout one
is ready to close a gap).

## pob-community-v2 values (owner's method, not a supported score)

| Document | Sustained (waits for mana) | Burst [0, 5) | Without waiting (not attainable) | PoB TotalDPS | PoB per use |
|---|---|---|---|---|---|
| Seed as imported | 285,023 | 299,711 | 572,246 | 1,270,761 | 1,498,554 |
| Pounce off | 229,857 | 241,702 | 461,488 | 1,024,807 | 1,208,512 |

Mana decides the value. The seed's one mana flask (356.5 per use, 10 of 75
charges, 0.25 charges per second, charges full at t = 0) is used 10 times.
With waiting, the window holds 34.7 s of Whirling Assault, 0.95 s of Charged
Staff (3 presses), 27.1 s of Flicker Strike (23 uses) and 57.2 s waiting for
mana. Without waiting the same rotation runs 9,393 mana short (first
unaffordable action at 22.7 s). Applying the community reference's condition
inputs (Onslaught, Rage 30, enemy shocked, chilled, frozen and others) to the
seed raises PoB's per-use value to 4,634,311; those are reported, not
adopted. Still blocking a supported score: attribution (proposed table, not
accepted) and config conditions (Pounce's mark in the owner's PoB).

The Combo rules conflict with the owner's "whirling assault to get 5 power
charges": at most 10 Combo gives 2 or 3 charges per Whirling Assault use, so
5 needs charges carried by Perpetual Charge. `mechanics-rules.json` records
this conflict instead of fitting a rule to it.

Mana: 887 pool, 47.9 per second regeneration, flask 356.5 per use (10 of 75
charges, 0.25 charges per second, no kill charges on the benchmark). One
Whirling Assault plus one Flicker Strike costs 408 mana with per-use charging,
so the 120 s window includes waiting for mana. Whether to wait is the
evaluator's job; the inputs are here.

## Web evidence

poe2wiki.net refused automated access for every page tried. The Surpassing
rule rests on a search summary of its page plus the pinned stat text; a
reviewer may want a tooltip capture instead. No retrieved page says whether a
teleport counts as Hit and Run movement.

## Tests

| Command | Result |
|---|---|
| `python -m pytest tests/unit tests/integration -q` | 1709 passed, 1 xfailed |
| `python -m pytest tests/engine/test_p09_t01_2_seed_replay_engine.py tests/engine/test_p02_t02_1_flicker_engine.py -q` (clean pin) | 8 passed |
| `python scripts/generate_schemas.py --check` | 21 schema files match |
