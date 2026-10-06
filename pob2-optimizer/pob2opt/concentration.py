"""Practicality layer: convert PoB's idealised DPS into honest single-target and
clear numbers, using each skill's delivery geometry.

PoB computes damage as if every hit lands on the target. Real combat imposes
spatial scatter (a rain skill sprays an area; a point target catches few of the
projectiles) and per-enemy hit-rate caps. This module classifies a skill's
delivery archetype from primitives PoB already emits, then applies a
concentration multiplier (single-target) and a coverage multiplier (clear).

The multipliers are closed-form in the geometry primitives, parameterised by a
small set of constants in calibration.json. Those constants are physics-informed
defaults, refined by fitting against real (predicted, observed) data points
collected via `pob2opt feedback` and the ladder puller. No ML, no simulator —
geometry + a dozen calibrated numbers.
"""

from __future__ import annotations

import json
import math
import os
import sys

_CALIB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "calibration.json")

# ------------------------------------------------------------------ constants

DEFAULT_CONSTANTS = {
    # target footprint radii (metres) — how much area a target presents to a rain
    "boss_radius_m": 0.9,
    "white_radius_m": 0.35,
    "pack_mob_density": 1.3,     # white mobs per m^2 in a leveling pack
    "pack_cap": 9,               # max simultaneous targets that matter for clear
    # per-archetype single-target concentration fudge (1.0 = PoB is right).
    # These are what calibration moves.
    "st_fudge": {
        "single_projectile": 1.0,
        "forward_pierce": 1.0,
        "centered_aoe": 1.0,
        "ground_rain": 1.0,       # formula already discounts; fudge stays ~1
        "channel_beam": 1.0,
        "melee_arc": 1.0,
        "dot": 1.0,
        "minion": 1.0,
        "unknown": 1.0,
    },
    "clear_fudge": {k: 1.0 for k in
                    ("single_projectile", "forward_pierce", "centered_aoe", "ground_rain",
                     "channel_beam", "melee_arc", "dot", "minion", "unknown")},
}


#: Archetypes `classify` can return and the multipliers are defined for.
#: "unknown" is deliberately absent: an unrecognised delivery geometry is a
#: gap, and 1.0 would be the most favourable answer available (P02-T04).
KNOWN_ARCHETYPES = frozenset(DEFAULT_CONSTANTS["st_fudge"]) - {"unknown"}


def load_constants() -> dict:
    if os.path.exists(_CALIB_PATH):
        try:
            data = json.load(open(_CALIB_PATH, encoding="utf-8"))
        except (OSError, ValueError) as exc:
            print("pob2opt: ignoring unreadable %s (%s: %s)"
                  % (_CALIB_PATH, type(exc).__name__, exc), file=sys.stderr)
        else:
            c = json.loads(json.dumps(DEFAULT_CONSTANTS))  # deep copy
            c.update({k: v for k, v in data.get("constants", {}).items() if k not in ("st_fudge", "clear_fudge")})
            for k in ("st_fudge", "clear_fudge"):
                c[k].update(data.get("constants", {}).get(k, {}))
            return c
    return json.loads(json.dumps(DEFAULT_CONSTANTS))


# ------------------------------------------------------------------ classify

def classify(prim: dict) -> str:
    """prim: {tags, proj, aoe, pierce, chain, fork, maxHitRate, channelling}."""
    tags = (prim.get("tags") or "").lower()
    proj = prim.get("proj") or 1
    aoe = prim.get("aoe") or 0
    pierce = prim.get("pierce") or 0
    chain = prim.get("chain") or 0
    fork = prim.get("fork") or 0
    max_hit = prim.get("maxHitRate")

    if "minion" in tags:
        return "minion"
    # a per-enemy hit-rate cap + sustained/area = a rain/storm that scatters
    if max_hit and ("sustained" in tags or "storm" in tags or proj > 3):
        return "ground_rain"
    if "channelling" in tags:
        return "channel_beam"
    if (pierce and pierce >= 100) or (fork and pierce) or chain >= 3:
        return "forward_pierce"
    if "melee" in tags and "aoe" in tags:
        return "melee_arc"
    if "aoe" in tags and proj <= 1 and not max_hit:
        return "centered_aoe"
    if proj <= 1 and aoe == 0 and "aoe" not in tags:
        return "single_projectile"
    if proj > 1:
        # multiple forward projectiles (not a rain) — spread but not point-capped
        return "forward_pierce"
    if "duration" in tags and ("chaos" in tags or "fire" in tags) and aoe:
        return "dot"
    return "centered_aoe" if aoe else "single_projectile"


# ------------------------------------------------------------- multipliers

def _area(r):
    return math.pi * max(r, 0.01) ** 2


def single_target_mult(arch: str, prim: dict, c: dict, boss: bool = True) -> float:
    """Fraction of PoB single-target DPS that actually lands on ONE target."""
    fudge = c["st_fudge"].get(arch, 1.0)
    if arch == "ground_rain":
        # PoB assumes all `proj` arrows contribute; a point target of footprint f
        # in a rain of N arrows over area A catches ~ N*f/A of them (expected),
        # and no more than the per-enemy hit-rate allows.
        N = max(prim.get("proj") or 1, 1)
        R = prim.get("aoe") or 2.0
        A = _area(R)
        f = _area(c["boss_radius_m"] if boss else c["white_radius_m"])
        spatial = min(1.0, N * f / A) / N * N  # expected arrows on target / N * N... simplify below
        expected_on_target = min(N, N * f / A)
        frac = expected_on_target / N
        return max(0.03, min(1.0, frac)) * fudge
    if arch in ("single_projectile", "forward_pierce", "channel_beam", "dot", "melee_arc", "minion"):
        return 1.0 * fudge          # concentrate on / apply fully to the target
    if arch == "centered_aoe":
        return 1.0 * fudge          # the target sits in the AoE centre
    return fudge


def clear_mult(arch: str, prim: dict, c: dict) -> float:
    """Effective simultaneous targets (multiplier on single-target-hit damage)."""
    fudge = c["clear_fudge"].get(arch, 1.0)
    cap = c["pack_cap"]
    density = c["pack_mob_density"]
    R = prim.get("aoe") or 0
    proj = max(prim.get("proj") or 1, 1)
    pierce = prim.get("pierce") or 0
    chain = prim.get("chain") or 0
    fork = prim.get("fork") or 0
    if arch == "ground_rain":
        targets = min(cap, _area(R) * density)          # blankets the whole area
    elif arch in ("centered_aoe", "melee_arc", "dot"):
        targets = min(cap, max(1.0, _area(R) * density))
    elif arch == "channel_beam":
        targets = min(cap, 4 if pierce >= 100 else 2)   # a line through the pack
    elif arch == "forward_pierce":
        reach = 1 + (pierce if pierce < 100 else cap) + chain + fork
        targets = min(cap, max(proj, reach))
    elif arch == "single_projectile":
        targets = 1.0 + chain + fork
    elif arch == "minion":
        targets = min(cap, 3)
    else:
        targets = 1.0
    return max(1.0, targets) * fudge


def honest(prim: dict, pob_dps: float, constants: dict = None):
    """Return {archetype, single_target, clear} for a delivery geometry.

    An unrecognised archetype returns None for both numbers. It used to return
    the input unchanged through a 1.0 fudge, which is the most favourable
    answer there is and indistinguishable from a measured one (P02-T04).
    """
    c = constants or load_constants()
    arch = classify(prim)
    if arch not in KNOWN_ARCHETYPES:
        return {"archetype": arch, "single_target": None, "clear": None}
    st = pob_dps * single_target_mult(arch, prim, c, boss=True)
    clr = pob_dps * single_target_mult(arch, prim, c, boss=False) * clear_mult(arch, prim, c)
    return {"archetype": arch, "single_target": st, "clear": clr}
