"""The one place the legacy phase pipeline turns engine numbers into estimates.

This is the legacy comparison path named in `docs/specs/architecture.md`, not
production evaluation. It exists in one module for two reasons.

**Research finding F02.** ``phases.task_tier`` computed a rotation-adjusted DPS
and then threw it away, feeding the concentration layer a bare
``worker.metrics()["dps"]`` re-read after enemy conditions were switched on. The
reported single-target number was four times the rotation it claimed to
describe, and halving the rotation's duty cycle changed it not at all. The
arithmetic now lives here, takes the rotation-adjusted number as its only damage
input, and applies the condition measurement as a ratio, so a timing penalty
cannot be reset by enabling a condition.

**Naming.** The legacy "floor" and "ceiling" are not bounds on anything. They
are one measurement with every scoped condition off and one with them on, so
they are reported as ``condition_off_estimate`` and ``condition_on_estimate``.
The old keys remain as deprecated aliases and every row carries
``estimate_status`` saying what they are worth.

What this module refuses to do: replace a number the engine did not supply with
a convenient constant. An unmeasured condition uplift, an unavailable delivery
geometry and an unknown reload duty each produce ``None`` and a named gap.
"""

from __future__ import annotations

from typing import Any, Mapping

from . import concentration

#: Every row this module produces carries it. These estimates are a heuristic
#: that P07 replaces; nothing may read them as a validated combat result.
LEGACY_STATUS = "legacy_heuristic_unvalidated"

CONDITION_OFF_KEY = "condition_off_estimate"
CONDITION_ON_KEY = "condition_on_estimate"
SINGLE_TARGET_KEY = "single_target_estimate"
CLEAR_KEY = "clear_estimate"

#: Deprecated name -> current name. Kept so existing phase JSON and the legacy
#: report keep working; both are written, and the deprecated one is never the
#: only name a value has.
DEPRECATED_ALIASES: Mapping[str, str] = {
    "floor": CONDITION_OFF_KEY,
    "ceiling": CONDITION_ON_KEY,
    "honest_single_target": SINGLE_TARGET_KEY,
    "clear_score": CLEAR_KEY,
}


def with_aliases(row: dict) -> dict:
    """Add the deprecated aliases for whatever current keys ``row`` has."""
    for old, new in DEPRECATED_ALIASES.items():
        if new in row:
            row[old] = row[new]
    return row


def legacy_value(row: Mapping[str, Any], name: str):
    """Read an estimate by either name. Missing stays missing.

    Returns None when neither name is present or the value is None. A caller
    that wants a number must decide what to do with the absence; this function
    will not invent one.
    """
    current = DEPRECATED_ALIASES.get(name, name)
    if current in row and row[current] is not None:
        return row[current]
    for old, new in DEPRECATED_ALIASES.items():
        if new == current and row.get(old) is not None:
            return row[old]
    return None


def sort_key(row: Mapping[str, Any], name: str) -> tuple[int, float]:
    """Descending sort key that puts rows without the estimate last."""
    value = legacy_value(row, name)
    if value is None:
        return (1, 0.0)
    return (0, -float(value))


# ------------------------------------------------------------ screen scoring

def screen_score(metrics: Mapping[str, Any]) -> float | None:
    """The legacy per-skill screening number, with its units checked.

    ``metrics["dps"]`` is PoB's ``CombinedDPS``, which is damage per second for
    most skills and damage *per use* for skills whose data sets ``showAverage``
    (P02-T04 fixture F-UNIT: Incinerate reports ``CombinedDPS`` 23.32 against
    ``TotalDPS`` 93.28). ``max(dps, full)`` therefore used to compare a per-use
    number with a per-second one. When the flag says the units differ, only the
    per-second number is used, and when neither number is present the result is
    None rather than zero.
    """
    full = metrics.get("full")
    dps = metrics.get("dps")
    if metrics.get("show_average"):
        return None if full is None else float(full)
    candidates = [float(v) for v in (dps, full) if v is not None]
    return max(candidates) if candidates else None


def condition_estimates(off: float | None, on: float | None,
                        assumptions: list | tuple) -> dict:
    """One measurement with scoped conditions off, one with them on."""
    row = {CONDITION_OFF_KEY: off, CONDITION_ON_KEY: on,
           "assumptions": list(assumptions), "estimate_status": LEGACY_STATUS}
    return with_aliases(row)


# -------------------------------------------------------- sustained estimates

#: Gap codes a caller can act on without parsing prose.
GAP_NO_ROTATION = "rotation_dps_unknown"
GAP_NO_UPLIFT = "condition_uplift_unmeasured"
GAP_NO_GEOMETRY = "delivery_geometry_unavailable"
GAP_NO_ARCHETYPE = "delivery_archetype_unrecognised"


def condition_uplift(bare_dps: float | None, conditioned_dps: float | None,
                     enabled: list | tuple) -> tuple[float | None, str | None]:
    """How much the self-applied enemy conditions changed the engine's number.

    A ratio of the same output read twice, so the unit cancels and it is safe
    to take even when that output is ``CombinedDPS``. Returns ``(None, gap)``
    when it could not be measured; the caller must not substitute 1.0, because
    1.0 is the answer for "no condition applied", not for "not measured".
    """
    if not enabled:
        return 1.0, None
    if not bare_dps or conditioned_dps is None:
        return None, GAP_NO_UPLIFT
    return conditioned_dps / bare_dps, None


def sustained_estimates(rotation_dps: float | None,
                        geometry: Mapping[str, Any] | None,
                        uplift: float | None, *,
                        uplift_gap: str | None = None,
                        geometry_gap: str | None = None,
                        constants: dict | None = None) -> dict:
    """Compose the legacy single-target and clear estimates.

    ``rotation_dps`` is the only damage input, and it is the action-time
    corrected number: enabler overhead, reload duty and gauge lockout are
    already in it. That is the whole of the F02 repair. The condition
    measurement enters as a multiplier so it scales the rotation rather than
    replacing it.
    """
    gaps: list[str] = []
    if uplift_gap:
        gaps.append(uplift_gap)
    if geometry_gap:
        gaps.append(geometry_gap)

    if rotation_dps is None:
        gaps.append(GAP_NO_ROTATION)
        off = on = None
    else:
        off = float(rotation_dps)
        on = None if uplift is None else off * float(uplift)

    reported = on if on is not None else off
    archetype = single_target = clear = None
    if geometry is None:
        if GAP_NO_GEOMETRY not in gaps:
            gaps.append(GAP_NO_GEOMETRY)
    elif reported is not None:
        honest = concentration.honest(dict(geometry), reported, constants)
        archetype = honest["archetype"]
        single_target = honest["single_target"]
        clear = honest["clear"]
        if single_target is None or clear is None:
            gaps.append(GAP_NO_ARCHETYPE)

    row = {
        "rotation_dps": rotation_dps,
        "condition_uplift": uplift,
        "sustained_dps_condition_off": off,
        "sustained_dps_condition_on": on,
        SINGLE_TARGET_KEY: single_target,
        CLEAR_KEY: clear,
        "archetype": archetype,
        "estimate_status": LEGACY_STATUS,
        "estimate_gaps": gaps,
    }
    return with_aliases(row)
