"""Research finding F02, characterized (P00-T04).

``pob2opt/phases.py`` ``task_tier`` builds two different damage numbers:

* ``rot["dps"]`` - the rotation-adjusted number. It pays for enabler casts,
  reload duty on clip weapons and gauge-skill lockout windows.
* ``realistic`` - a bare ``worker.metrics()["dps"]`` re-read after enemy
  conditions are switched on. It carries no action-time correction at all.

The final concentration step then prefers ``realistic``::

    base_dps = realistic if realistic else rot["dps"]
    hon = concentration.honest(geom, base_dps)

so ``honest_single_target`` - the field the ranking and report consume - drops
every action-time penalty whenever ``realistic`` is non-zero.

These tests run the real ``task_tier`` against a synthetic worker double. They
make no claim about PoE 2 mechanics; they only pin the data path. The repair is
P02-T04 ("Reproduce and fix the F02 path that drops rotation correction").
"""

from __future__ import annotations

import pytest

from pob2opt import concentration, phases
from testdoubles import FakeWorker

#: A main-skill primitive with no enablers: before the reload duty is applied,
#: the rotation model reproduces the raw per-use DPS exactly.
MAIN_PRIMITIVE = {
    "skill": "FIXTURE Main", "label": "OPT: FIXTURE Main",
    "combined": 1000.0, "avgUse": 500.0, "castTime": 0.5, "speed": 2.0,
    "duration": 0, "cooldown": 0,
}

GEOMETRY = {"tags": "attack", "proj": 1, "aoe": 0}

#: A clip weapon that spends three quarters of its time reloading.
CLIP_DUTY = 0.25

TASK = {
    "main": "FIXTURE Main",
    "main_desc": "deals damage",   # -> classify_rotation == "spam"
    "enablers": [],
    "weapon": None,                # -> unarmed; no crafted-item lookups
    "points": 50,
    "asc_points": 4,
    "max_act": 2,
}


def run_task_tier(**over):
    worker = FakeWorker(
        metrics={"dps": 1000.0, "full": 1000.0, "life": 2000.0,
                 "str": 100, "dex": 100, "int": 100,
                 "reqStr": 0, "reqDex": 0, "reqInt": 0, "spiritUnreserved": 0},
        primitives=[dict(MAIN_PRIMITIVE)],
        geometry=dict(GEOMETRY),
        clip_duty=over.pop("clip_duty", CLIP_DUTY),
    )
    task = dict(TASK)
    task.update(over)
    return worker, phases.task_tier(worker, task)


def honest_multiplier() -> float:
    """``concentration.honest`` is linear in its DPS input; recover the factor."""
    return concentration.honest(dict(GEOMETRY), 1.0)["single_target"]


# ------------------------------------------------------- current behaviour

def test_rotation_dps_does_carry_the_reload_penalty():
    """The rotation number itself is correct: the duty cycle is applied to it."""
    _, result = run_task_tier()
    assert result["rotation_dps"] == pytest.approx(1000.0 * CLIP_DUTY)


def test_concentration_currently_consumes_the_unadjusted_dps():
    """CURRENT behaviour (F02): the reload penalty is discarded downstream."""
    _, result = run_task_tier()

    assert result["realistic_dps"] == pytest.approx(1000.0)
    assert result["rotation_dps"] < result["realistic_dps"]
    assert result["honest_single_target"] == pytest.approx(
        result["realistic_dps"] * honest_multiplier())
    # The reported single-target number is four times the rotation it claims to
    # describe. This is the defect, pinned so a repair cannot pass silently.
    assert result["honest_single_target"] == pytest.approx(
        result["rotation_dps"] * honest_multiplier() / CLIP_DUTY)


def test_a_worse_rotation_does_not_change_the_reported_single_target():
    """Halving the duty cycle again changes nothing downstream."""
    _, baseline = run_task_tier(clip_duty=0.5)
    _, worse = run_task_tier(clip_duty=0.125)

    assert worse["rotation_dps"] < baseline["rotation_dps"]
    assert worse["honest_single_target"] == pytest.approx(baseline["honest_single_target"])


def test_clear_score_shares_the_same_unadjusted_input():
    _, result = run_task_tier()
    expected = concentration.honest(dict(GEOMETRY), result["realistic_dps"])
    assert result["clear_score"] == pytest.approx(expected["clear"])


# ------------------------------------------------------- repaired behaviour

@pytest.mark.xfail(
    strict=True,
    reason="F02 repair is P02-T04: the concentration layer must consume the "
           "rotation-adjusted DPS so action-time penalties survive.",
)
def test_repaired_concentration_consumes_the_rotation_adjusted_dps():
    _, result = run_task_tier()
    assert result["honest_single_target"] == pytest.approx(
        result["rotation_dps"] * honest_multiplier())


@pytest.mark.xfail(
    strict=True,
    reason="F02 repair is P02-T04: a slower rotation must lower the reported "
           "single-target performance.",
)
def test_repaired_single_target_responds_to_rotation_quality():
    _, baseline = run_task_tier(clip_duty=0.5)
    _, worse = run_task_tier(clip_duty=0.125)
    assert worse["honest_single_target"] < baseline["honest_single_target"]
