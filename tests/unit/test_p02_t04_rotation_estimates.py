"""P02-T04 offline lane: the F02 repair and the centralized legacy arithmetic.

Everything here drives the real ``phases.task_tier`` and
``pob2opt.legacy_estimates`` against synthetic worker doubles. The numbers are
invented to make one data path observable; none of them is evidence about PoE 2
or about PoB.

Acceptance covered:

* increasing setup time reduces the sustained estimate;
* enabling an unrelated condition does not reset the timing penalties;
* an unknown reload duty or an unavailable delivery geometry is a gap, not a
  favourable constant;
* the deprecated ``floor``/``ceiling``/``honest_*`` names survive only with an
  explicit legacy status.
"""

from __future__ import annotations

import inspect

import pytest

from pob2opt import cli, concentration, legacy_estimates, phases, policy
from testdoubles import FakeWorker

GEOMETRY = {"tags": "attack", "proj": 1, "aoe": 0}

MAIN = {"skill": "FIXTURE Main", "label": "OPT: FIXTURE Main",
        "combined": 1000.0, "avgUse": 500.0, "castTime": 0.5, "speed": 2.0,
        "duration": 0, "cooldown": 0}

#: One enabler the rotation has to pay for. ``duration`` is its period, so the
#: setup cost is castTime / duration and the fixture can vary it directly.
def enabler(cast_time: float) -> dict:
    return {"skill": "FIXTURE Enabler", "label": "OPT: FIXTURE Enabler",
            "combined": 0.0, "avgUse": 0.0, "castTime": cast_time,
            "speed": 1.0, "duration": 10.0, "cooldown": 0}


TASK = {"main": "FIXTURE Main", "main_desc": "deals damage", "enablers": [],
        "weapon": None, "points": 50, "asc_points": 4, "max_act": 2}

METRICS = {"dps": 1000.0, "full": 1000.0, "life": 2000.0,
           "str": 100, "dex": 100, "int": 100,
           "reqStr": 0, "reqDex": 0, "reqInt": 0, "spiritUnreserved": 0}


class NoGeometryWorker(FakeWorker):
    """A double whose engine cannot answer ``OPT_geometry``."""

    def lua(self, code: str):
        if "OPT_geometry" in code:
            raise RuntimeError("synthetic: no delivery geometry available")
        return super().lua(code)


class ConditionedWorker(FakeWorker):
    """A double whose engine number rises once an enemy condition is set.

    That is the situation F02 describes: the condition reading was substituted
    for the rotation-adjusted number instead of scaling it.
    """

    uplift = 2.0

    def metrics(self):
        values = super().metrics()
        if any(name.startswith("conditionEnemy") and value
               for name, value in self.configs_set.items()):
            values["dps"] = values["dps"] * self.uplift
            values["full"] = values["full"] * self.uplift
        return values


def run(worker_cls=FakeWorker, *, clip_duty=1.0, setup_time=None,
        geometry=GEOMETRY, damage_profile=None, **task_over):
    primitives = [dict(MAIN)]
    task = dict(TASK)
    if setup_time is not None:
        primitives.append(enabler(setup_time))
        task["enablers"] = ["FIXTURE Enabler"]
    worker = worker_cls(metrics=dict(METRICS), primitives=primitives,
                        geometry=None if geometry is None else dict(geometry),
                        damage_profile=dict(damage_profile or {}),
                        clip_duty=clip_duty)
    task.update(task_over)
    return worker, phases.task_tier(worker, task)


def multiplier() -> float:
    return concentration.honest(dict(GEOMETRY), 1.0)["single_target"]


# ------------------------------------- acceptance: setup time costs something

@pytest.mark.parametrize("setup_time", [0.5, 1.0, 2.0, 3.0])
def test_increasing_setup_time_reduces_the_sustained_estimate(setup_time):
    _, cheap = run(setup_time=0.5)
    _, result = run(setup_time=setup_time)

    assert result["rotation_dps"] <= cheap["rotation_dps"]
    assert result["single_target_estimate"] <= cheap["single_target_estimate"]
    if setup_time > 0.5:
        assert result["single_target_estimate"] < cheap["single_target_estimate"]


def test_the_sustained_estimate_is_the_rotation_number_not_the_engine_number():
    _, result = run(setup_time=2.0)

    assert result["rotation_dps"] < result["pob_dps"]
    assert result["single_target_estimate"] == pytest.approx(
        result["rotation_dps"] * multiplier())


def test_a_saturated_rotation_says_so_instead_of_looking_flat():
    """The legacy model clamps overhead at 0.60. Past it the row records that.

    P07 replaces the model; until then a number that stopped responding is
    marked rather than presented as a measurement.
    """
    _, saturated = run(setup_time=9.0)

    assert saturated["rotation_saturated"] is True
    assert any("clamped" in gap or "floor" in gap
               for gap in saturated["estimate_gaps"])


# ------------------------- acceptance: a condition does not reset the penalty

def test_enabling_an_unrelated_condition_does_not_reset_the_timing_penalty():
    """The shock condition has nothing to do with the reload duty.

    Before the repair the condition reading replaced the rotation number, so
    switching a condition on restored the full unadjusted DPS.
    """
    _, plain = run(clip_duty=0.25)
    worker, conditioned = run(ConditionedWorker, clip_duty=0.25,
                              damage_profile={"lightning": True})

    assert conditioned["conditions_enabled"] == ["conditionEnemyShocked"]
    assert conditioned["condition_uplift"] == pytest.approx(
        ConditionedWorker.uplift)
    assert conditioned["rotation_dps"] == pytest.approx(plain["rotation_dps"])
    # The condition scales the rotation; it does not replace it.
    assert conditioned["single_target_estimate"] == pytest.approx(
        conditioned["rotation_dps"] * ConditionedWorker.uplift * multiplier())
    assert conditioned["single_target_estimate"] < (
        conditioned["realistic_dps"] * multiplier())


def test_a_worse_rotation_still_loses_with_the_condition_on():
    _, good = run(ConditionedWorker, clip_duty=0.5,
                  damage_profile={"lightning": True})
    _, bad = run(ConditionedWorker, clip_duty=0.125,
                 damage_profile={"lightning": True})

    assert good["condition_uplift"] == bad["condition_uplift"]
    assert bad["single_target_estimate"] < good["single_target_estimate"]


def test_no_condition_enabled_is_a_measured_uplift_of_one():
    _, result = run(damage_profile={})

    assert result["conditions_enabled"] == []
    assert result["condition_uplift"] == 1.0
    assert legacy_estimates.GAP_NO_UPLIFT not in result["estimate_gaps"]


# ----------------------------------- acceptance: a gap, not a helpful constant

def test_an_unknown_reload_duty_produces_no_number_at_all():
    worker, result = run(clip_duty=None)

    assert result["rotation_dps"] is None
    assert result["single_target_estimate"] is None
    assert result["clear_estimate"] is None
    assert any(gap.startswith("reload_duty_unknown")
               for gap in result["estimate_gaps"])


def test_an_unavailable_geometry_produces_no_number_at_all():
    """The old fallback used ``realistic or rot["dps"]`` with a 1.0 multiplier."""
    _, result = run(NoGeometryWorker)

    assert result["rotation_dps"] is not None
    assert result["single_target_estimate"] is None
    assert result["archetype"] is None
    assert any(legacy_estimates.GAP_NO_GEOMETRY in gap
               for gap in result["estimate_gaps"])


def test_an_unrecognised_delivery_archetype_is_not_scored_as_one_to_one(monkeypatch):
    """``single_target_mult`` used to return a 1.0 fudge for anything unknown."""
    assert "unknown" not in concentration.KNOWN_ARCHETYPES
    monkeypatch.setattr(concentration, "classify", lambda prim: "unknown")

    honest = concentration.honest(dict(GEOMETRY), 100.0)

    assert honest["archetype"] == "unknown"
    assert honest["single_target"] is None
    assert honest["clear"] is None


def test_an_unmeasured_condition_uplift_is_not_silently_one():
    uplift, gap = legacy_estimates.condition_uplift(
        None, 1000.0, ["conditionEnemyShocked"])

    assert uplift is None
    assert gap == legacy_estimates.GAP_NO_UPLIFT
    row = legacy_estimates.sustained_estimates(250.0, GEOMETRY, uplift,
                                               uplift_gap=gap)
    assert row["sustained_dps_condition_on"] is None
    assert row["sustained_dps_condition_off"] == 250.0
    # The condition-off measurement still produces an estimate; it is simply
    # not presented as the conditioned one.
    assert row["single_target_estimate"] == pytest.approx(250.0 * multiplier())


# --------------------------------------------------- units of the screen score

def test_the_screen_score_refuses_to_mix_damage_per_use_with_damage_per_second():
    """PoB fixture F-UNIT: CombinedDPS is per use when showAverage is set."""
    per_second = {"dps": 93.28, "full": 105.65}
    assert legacy_estimates.screen_score(per_second) == pytest.approx(105.65)

    per_use = {"dps": 23.32, "full": 105.65, "show_average": True}
    assert legacy_estimates.screen_score(per_use) == pytest.approx(105.65)

    unusable = {"dps": 23.32, "show_average": True}
    assert legacy_estimates.screen_score(unusable) is None


def test_the_screen_score_of_nothing_is_nothing():
    assert legacy_estimates.screen_score({}) is None


# ------------------------------------------------- naming and legacy status

def test_condition_estimates_carry_both_names_and_a_legacy_status():
    row = legacy_estimates.condition_estimates(10.0, 25.0, ["someCondition"])

    assert row["condition_off_estimate"] == 10.0
    assert row["condition_on_estimate"] == 25.0
    assert row["floor"] == 10.0
    assert row["ceiling"] == 25.0
    assert row["estimate_status"] == legacy_estimates.LEGACY_STATUS


def test_legacy_value_reads_either_name_and_invents_nothing():
    assert legacy_estimates.legacy_value({"ceiling": 5.0}, "condition_on_estimate") == 5.0
    assert legacy_estimates.legacy_value({"condition_on_estimate": 5.0}, "ceiling") == 5.0
    assert legacy_estimates.legacy_value({}, "ceiling") is None
    assert legacy_estimates.legacy_value({"ceiling": None}, "ceiling") is None


def test_rows_without_an_estimate_sort_last_instead_of_counting_as_zero():
    rows = [{"ceiling": 1.0}, {}, {"ceiling": 7.0}]
    ordered = sorted(rows, key=lambda r: legacy_estimates.sort_key(r, "ceiling"))

    assert ordered[0]["ceiling"] == 7.0
    assert ordered[-1] == {}


def test_a_phase_row_from_the_screen_task_uses_the_current_names():
    worker = FakeWorker(metrics=dict(METRICS), primitives=[dict(MAIN)],
                        geometry=dict(GEOMETRY))
    row = phases.task_screen(worker, {"gem": "FIXTURE Main", "weapon": None})

    assert row["condition_off_estimate"] == row["floor"]
    assert row["condition_on_estimate"] == row["ceiling"]
    assert row["estimate_status"] == legacy_estimates.LEGACY_STATUS


# ------------------------------------------------------- centralization guard

def test_the_phase_pipeline_no_longer_does_this_arithmetic_itself():
    """F02 came back once the same composition existed in two places.

    ``legacy_estimates`` is the only caller of the concentration model, so a
    future edit to ``phases`` cannot reintroduce an unadjusted input without
    this failing.
    """
    source = inspect.getsource(phases)

    assert "concentration." not in source
    assert "legacy_estimates.sustained_estimates" in source


def test_no_report_reads_a_legacy_honest_field_directly():
    source = inspect.getsource(cli)

    assert "honest_single_target" not in source
    assert "legacy_estimates.SINGLE_TARGET_KEY" in source
    assert "legacy_estimates.LEGACY_STATUS" in source


def test_a_missing_estimate_is_rendered_as_unknown_not_as_a_number():
    assert cli._num({}, "condition_on_estimate") == "unknown"
    assert cli._num({"ceiling": 12.4}, "condition_on_estimate") == "12"


def test_the_rotation_model_reports_the_assumptions_it_made():
    row = policy.rotation_dps(
        [dict(MAIN, role="main"),
         {"skill": "E", "role": "enabler", "castTime": 1.0, "duration": 0,
          "cooldown": 0}],
        {"kind": "spam"})

    assert any("assumed 6s" in a for a in row["assumptions"])
    assert row["saturated"] is False
