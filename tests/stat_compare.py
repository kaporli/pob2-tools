"""Numeric PoB output comparison for engine parity checks (P04).

Two outputs agree when they have the same numeric keys and every value
agrees. A value agrees when ``|a - b| <= max(ABS_TOLERANCE, REL_TOLERANCE *
max(|a|, |b|))``, so a change away from zero is measured absolutely and can
never pass as a relative error of zero. A non-finite value agrees only with
the same non-finite value (NaN with NaN, +inf with +inf).
"""

from __future__ import annotations

import math

REL_TOLERANCE = 1e-6
ABS_TOLERANCE = 1e-9

#: Marks a key present on one side only.
MISSING = "<missing>"


def numeric(stats):
    """The numeric outputs of a ``get_stats`` result; booleans excluded."""
    return {k: v for k, v in stats.items()
            if isinstance(v, (int, float)) and not isinstance(v, bool)}


def values_agree(a, b) -> bool:
    a, b = float(a), float(b)
    if not (math.isfinite(a) and math.isfinite(b)):
        return (math.isnan(a) and math.isnan(b)) or a == b
    tolerance = max(ABS_TOLERANCE, REL_TOLERANCE * max(abs(a), abs(b)))
    return abs(a - b) <= tolerance


def stat_differences(before, after):
    """``{key: (before, after)}`` for every key that does not agree.

    Covers the union of both key sets; a key on one side only is reported
    with :data:`MISSING` on the other.
    """
    out = {}
    for key in sorted(set(before) | set(after)):
        if key not in after:
            out[key] = (before[key], MISSING)
        elif key not in before:
            out[key] = (MISSING, after[key])
        elif not values_agree(before[key], after[key]):
            out[key] = (before[key], after[key])
    return out
