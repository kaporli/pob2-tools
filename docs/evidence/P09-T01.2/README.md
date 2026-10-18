# P09-T01.2 evidence: clean seed replay, cycle rules and damage ownership

Captured 2026-10-18 on Windows 11, CPython 3.12.4, against
`external/PathOfBuilding-PoE2` at `ce566ea` with an empty
`git status --porcelain --untracked-files=all` before and after every run.
Everything here is PoB-derived or secondary web text. Nothing is a gameplay
measurement and no `pob-cycle-v1` value is computed.

| File | What |
|---|---|
| `replay.json` | The seed loaded through `EngineAdapter` on the clean pin: all outputs with Flicker Strike main, 0 to 5 forced charges with Charged Staff on and off, Whirling Assault, Charged Staff, a one-group-at-a-time sweep, four benchmark documents (Pounce off; with and without Charged Staff and Hit and Run), and read-only diagnostics (enemy values, Config-sourced, conditional and enemy modifiers, speed and added-damage sources, flasks) |
| `mechanics-rules.json` | 19 rules for the cycle with status, parameters and evidence (engine citations with file SHA-256 and line), and the proposed damage ownership table |
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

Resolved (10): extra strikes, no charge gain during Flicker Strike, Perpetual
Charge per charge, Surpassing distribution, Combo cap and decay, Whirling
Assault use, Charged Staff use, Pounce mark off, persistent buffs, PoB
default states.

Conditional (3): strike timing, Charged Staff buff ownership, 'consumed a
Power Charge Recently'.

Blocking (6): Flicker Strike mana per use or per strike, Combo per strike,
Whirling Assault's own Combo, Hit and Run reuse, mana sustain, Charged Staff
period N (owner Q10: "Once per N cycles").

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
| `python -m pytest tests/unit tests/integration -q` | 1698 passed, 1 xfailed |
| `python -m pytest tests/engine/test_p09_t01_2_seed_replay_engine.py tests/engine/test_p02_t02_1_flicker_engine.py -q` (clean pin) | 8 passed |
| `python scripts/generate_schemas.py --check` | 21 schema files match |
