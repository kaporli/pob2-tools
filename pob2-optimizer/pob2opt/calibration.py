"""Calibration store + fitter for the concentration model.

Holds the constants and a log of observations — (skill, archetype, predicted DPS
or clear, observed rating). `fit()` adjusts the per-archetype fudge factors so
predictions match observations, by least-squares on the log-ratio. This is the
"training": a dozen numbers regressed against real play/ladder data, persisted
to calibration.json.
"""

from __future__ import annotations

import json
import math
import os

from . import concentration

_PATH = concentration._CALIB_PATH


def _load():
    if os.path.exists(_PATH):
        try:
            return json.load(open(_PATH, encoding="utf-8"))
        except Exception:
            pass
    return {"constants": {}, "observations": []}


def _save(data):
    json.dump(data, open(_PATH, "w", encoding="utf-8"), indent=1)


def add_observation(skill: str, archetype: str, axis: str, model_honest: float,
                    observed: float, note: str = ""):
    """Store a correction: observed / model_honest, where model_honest is the
    concentration model's CURRENT honest prediction (geometry already applied).
    correction > 1 means the model was too harsh; < 1 too generous. The fudge is
    then this correction (it multiplies the geometry estimate)."""
    correction = (observed / model_honest) if (observed and model_honest) else 1.0
    data = _load()
    data.setdefault("observations", []).append({
        "skill": skill, "archetype": archetype, "axis": axis,
        "model_honest": model_honest, "observed": observed,
        "correction": correction, "note": note,
    })
    _save(data)
    return len(data["observations"])


def fit():
    """Fit per-archetype fudge = geometric mean of observed_ratio for that
    (archetype, axis). Robust to a handful of points; converges toward reality
    as the log grows. Untouched archetypes keep default 1.0."""
    data = _load()
    obs = data.get("observations", [])
    if not obs:
        return {"fitted": 0}
    by = {}
    for o in obs:
        by.setdefault((o["axis"], o["archetype"]), []).append(max(1e-3, o.get("correction", 1.0)))
    consts = data.setdefault("constants", {})
    st = consts.setdefault("st_fudge", {})
    cl = consts.setdefault("clear_fudge", {})
    n = 0
    for (axis, arch), ratios in by.items():
        gm = math.exp(sum(math.log(r) for r in ratios) / len(ratios))
        (st if axis == "single" else cl)[arch] = round(gm, 3)
        n += 1
    _save(data)
    return {"fitted": n, "constants": consts}


def status():
    data = _load()
    return {"observations": len(data.get("observations", [])),
            "constants": data.get("constants", {})}
