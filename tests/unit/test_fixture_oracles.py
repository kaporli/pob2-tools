"""The synthetic oracles are internally consistent (P00-T02).

Two fixtures state an answer a future implementation must reproduce:

* ``search/two_choice_synergy.json`` - a space whose optimum needs a coordinated
  two-axis change, and which a one-change-at-a-time hill climber cannot reach
  (research F04 describes the current search as exactly that).
* ``combat/tiny_sequence.json`` - a three-action sequence whose DPS is
  hand-computable, including the lockout window that must be charged.

The hill climber below is a model of the search strategy under discussion, not
production code. The arithmetic here proves the fixtures agree with themselves;
it proves nothing about PoE 2.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest


@pytest.fixture(scope="module")
def synergy(fixtures_dir: Path) -> dict:
    return json.loads(
        (fixtures_dir / "search" / "two_choice_synergy.json").read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def sequence(fixtures_dir: Path) -> dict:
    return json.loads(
        (fixtures_dir / "combat" / "tiny_sequence.json").read_text(encoding="utf-8"))


# ------------------------------------------------------------ search oracle

def score_of(payoff: list[dict], point: dict) -> float:
    for row in payoff:
        if all(row[axis] == value for axis, value in point.items()):
            return row["score"]
    raise KeyError(point)


def hill_climb_one_change_at_a_time(fixture: dict) -> dict:
    """Accept a change only if that single change improves the score."""
    axes = fixture["axes"]
    current = dict(fixture["baseline"])
    improved = True
    while improved:
        improved = False
        for axis, options in axes.items():
            for option in options:
                if option == current[axis]:
                    continue
                candidate = dict(current, **{axis: option})
                if score_of(fixture["payoff"], candidate) > score_of(fixture["payoff"], current):
                    current = candidate
                    improved = True
    return current


def test_the_payoff_table_covers_the_whole_space(synergy: dict):
    axes = synergy["axes"]
    expected = len(axes["support"]) * len(axes["passive"])
    assert len(synergy["payoff"]) == expected
    assert len({(r["support"], r["passive"]) for r in synergy["payoff"]}) == expected


def test_the_declared_global_best_is_the_best(synergy: dict):
    best = max(synergy["payoff"], key=lambda r: r["score"])
    oracle = synergy["oracle"]["global_best"]
    assert (best["support"], best["passive"]) == (oracle["support"], oracle["passive"])
    assert best["score"] == oracle["score"]


def test_a_single_change_hill_climber_stops_at_the_baseline(synergy: dict):
    result = hill_climb_one_change_at_a_time(synergy)
    oracle = synergy["oracle"]["greedy_single_change_result"]

    assert result == {"support": oracle["support"], "passive": oracle["passive"]}
    assert score_of(synergy["payoff"], result) == oracle["score"]
    assert oracle["score"] < synergy["oracle"]["global_best"]["score"]


def test_the_coordinated_change_is_the_only_way_up(synergy: dict):
    baseline = synergy["baseline"]
    base_score = score_of(synergy["payoff"], baseline)
    single_step_scores = [
        row["score"] for row in synergy["payoff"]
        if sum(row[axis] != baseline[axis] for axis in baseline) == 1
    ]
    assert single_step_scores and all(s < base_score for s in single_step_scores)


# ------------------------------------------------------------ combat oracle

def test_action_time_and_damage_add_up(sequence: dict):
    total_time = sum(a["cast_time_s"] * a["repeats"] for a in sequence["actions"])
    total_damage = sum(a["damage"] * a["repeats"] for a in sequence["actions"])
    oracle = sequence["oracle"]

    assert total_time == pytest.approx(oracle["total_action_time_s"])
    assert total_damage == pytest.approx(oracle["total_damage"])
    assert total_time == pytest.approx(sequence["window_s"])


def test_dps_charges_the_lockout_window(sequence: dict):
    oracle = sequence["oracle"]
    assert oracle["dps_over_window"] == pytest.approx(
        oracle["total_damage"] / oracle["total_action_time_s"])


def test_ignoring_the_lockout_overstates_performance(sequence: dict):
    oracle = sequence["oracle"]
    lockout = next(a for a in sequence["actions"] if a["name"] == "lockout")
    busy = oracle["total_action_time_s"] - lockout["cast_time_s"] * lockout["repeats"]

    assert oracle["naive_uptime_only_dps"] == pytest.approx(oracle["total_damage"] / busy)
    assert oracle["naive_uptime_only_dps"] > oracle["dps_over_window"]


def test_no_action_is_counted_twice(sequence: dict):
    ids = [a["id"] for a in sequence["actions"]]
    assert len(ids) == len(set(ids))
