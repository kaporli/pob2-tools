"""Research finding F02, characterized (P00-T04) and repaired (P02-T04).

``pob2opt/phases.py`` ``task_tier`` builds two different damage numbers:

* ``rot["dps"]`` - the rotation-adjusted number. It pays for enabler casts,
  reload duty on clip weapons and gauge-skill lockout windows.
* ``realistic`` - a bare ``worker.metrics()["dps"]`` re-read after enemy
  conditions are switched on. It carries no action-time correction at all.

The concentration step used to prefer ``realistic``::

    base_dps = realistic if realistic else rot["dps"]
    hon = concentration.honest(geom, base_dps)

so ``honest_single_target`` - the field the ranking and report consume -
dropped every action-time penalty whenever ``realistic`` was non-zero.

P02-T04 moved that arithmetic into ``pob2opt.legacy_estimates``, where the
rotation-adjusted number is the only damage input and the condition
measurement enters as a ratio. The tests below were written against the broken
behaviour and are **migrated in place**, each saying what it used to assert, so
the data path stays pinned rather than being deleted with the defect.

These tests run the real ``task_tier`` against a synthetic worker double. They
make no claim about PoE 2 mechanics; they only pin the data path.
"""

from __future__ import annotations

import pytest

from pob2opt import concentration, legacy_estimates, phases
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


# -------------------------------------------------- the data path, unchanged

def test_rotation_dps_does_carry_the_reload_penalty():
    """The rotation number itself is correct: the duty cycle is applied to it."""
    _, result = run_task_tier()
    assert result["rotation_dps"] == pytest.approx(1000.0 * CLIP_DUTY)


# ------------------------------------------- migrated: was the F02 defect

def test_the_reported_single_target_now_keeps_the_rotation_correction():
    """Migrated from ``test_concentration_currently_consumes_the_unadjusted_dps``.

    That test asserted the defect: ``honest_single_target`` equalled
    ``realistic_dps`` times the concentration multiplier, four times the
    rotation it claimed to describe. It is kept, inverted, so a regression to
    the unadjusted input fails here rather than passing silently.
    """
    _, result = run_task_tier()

    assert result["realistic_dps"] == pytest.approx(1000.0)
    assert result["rotation_dps"] < result["realistic_dps"]
    assert result["single_target_estimate"] == pytest.approx(
        result["rotation_dps"] * honest_multiplier())
    assert result["single_target_estimate"] != pytest.approx(
        result["realistic_dps"] * honest_multiplier())


def test_a_worse_rotation_now_changes_the_reported_single_target():
    """Migrated from ``test_a_worse_rotation_does_not_change_the_reported_single_target``.

    Halving the duty cycle used to change nothing downstream.
    """
    _, baseline = run_task_tier(clip_duty=0.5)
    _, worse = run_task_tier(clip_duty=0.125)

    assert worse["rotation_dps"] < baseline["rotation_dps"]
    assert worse["single_target_estimate"] < baseline["single_target_estimate"]


def test_clear_shares_the_rotation_corrected_input():
    """Migrated from ``test_clear_score_shares_the_same_unadjusted_input``.

    The clear number took the same unadjusted input as the single-target one.
    It still shares the input; the input is now the rotation-adjusted number.
    """
    _, result = run_task_tier()
    expected = concentration.honest(dict(GEOMETRY), result["rotation_dps"])
    assert result["clear_estimate"] == pytest.approx(expected["clear"])


# ------------------------------------------------------- repaired behaviour

def test_repaired_concentration_consumes_the_rotation_adjusted_dps():
    _, result = run_task_tier()
    assert result["honest_single_target"] == pytest.approx(
        result["rotation_dps"] * honest_multiplier())


def test_repaired_single_target_responds_to_rotation_quality():
    _, baseline = run_task_tier(clip_duty=0.5)
    _, worse = run_task_tier(clip_duty=0.125)
    assert worse["honest_single_target"] < baseline["honest_single_target"]


def test_the_deprecated_aliases_are_still_written_and_marked_legacy():
    """``honest_*`` survives for the legacy pipeline, with its status attached."""
    _, result = run_task_tier()

    assert result["honest_single_target"] == result["single_target_estimate"]
    assert result["clear_score"] == result["clear_estimate"]
    assert result["estimate_status"] == legacy_estimates.LEGACY_STATUS
