# pob2-optimizer

Exhaustive Path of Building 2 build-space search you run yourself. Finds the
highest-damage build for a character by sweeping:

- **every active skill gem** × every compatible weapon type (crafted minimal
  rares AND live-trade uniques/rares under your budget)
- **enabler → payoff combos** (whirlwinds→Twister, curses→Hexblast, corpses,
  freeze/ignite/shock payoffs, "Empower next attack" skills like Barrage and
  Ice-Tipped Arrows), auto-paired from gem descriptions
- **multi-entity stacking**: minions, companions, totems, triggered skills
  added on top of the main skill, scored by PoB's FullDPS aggregation with
  Spirit feasibility enforced
- full pipeline for the finalists: greedy supports (compat-checked), passive
  tree hill-climb with ascendancy selection, attribute-requirement repair,
  honest **floor/ceiling** DPS for every conditional mechanic (PoB config vars
  scoped to your skills — ceiling = all conditions up, floor = none)

## Setup

Requires sibling checkouts of
[PathOfBuilding-PoE2](https://github.com/PathOfBuildingCommunity/PathOfBuilding-PoE2)
and `pob2-mcp` (the engine bridge). Defaults assume
`C:\Users\Elias\PycharmProjects\{PathOfBuilding-PoE2,pob2-mcp}`; override with
`POB2_ROOT` / `POB2_MCP_PATH` env vars.

```
pip install -e .
```

## Usage

```
# quick smoke test (~5 min): 40 tasks, no trade
pob2opt screen --level 28 --limit 40 --no-trade --out runs\smoke

# full sweep at one level (hours; resumable — rerun the same command to continue)
pob2opt all --level 60 --budget 5 --league "Forbidden Rites" --out runs\l60

# individual phases
pob2opt harvest --level 60 --budget 5 --out runs\l60
pob2opt combos  --level 60 --out runs\l60
pob2opt report  --level 60 --out runs\l60
```

Output: `<out>/report.md` (ranked table with floor/ceiling DPS and the
assumption list per build) plus `build_NN_<skill>.xml` files importable into
Path of Building 2.

Phases checkpoint to `<out>/<phase>.json`; delete a file or pass `--force` to
redo that phase. `--workers N` controls parallel engine processes (each takes
~1 GB RAM and ~20 s to boot).

## Honesty model

Every conditional mechanic (whirlwind stages, curse present, charges, corpse
availability...) is reported as a floor/ceiling pair instead of a single
number. The ceiling assumes perfect uptime of every condition PoB scopes to
your active skills; the floor assumes none. Real play sits in between and the
gap tells you how rotation-dependent a build is.

Known limits:
- Some cross-skill empowerments are not modeled by PoB itself (e.g. Barrage's
  repeat on the next attack) — such combos are UNDERstated.
- Trigger meta-gem wraps (`triggers` phase, Cast on X > spell) are constructed
  correctly but PoB does not differentiate trigger/energy rates without
  per-build hand configuration — all metas currently score identically, so
  treat that phase as a build-construction aid, not a ranking.
- Glory/stun-gated ultimates are reported per burst window in their own report
  section; judge them by rotation, not sustained DPS.
- Count-type conditions only enter ceilings when listed in `policy.COUNT_CAPS`;
  trade listings go stale.
