"""The engine parity comparator itself (review R7). Offline."""

from __future__ import annotations

import pytest

from stat_compare import MISSING, stat_differences


@pytest.mark.parametrize("before, after, expected", [
    ({"Damage": 0}, {"Damage": 1000}, {"Damage": (0, 1000)}),
    ({"Damage": 1000}, {"Damage": 0}, {"Damage": (1000, 0)}),
    ({"Damage": 0}, {"Damage": 0}, {}),
    ({"Damage": 0}, {"Damage": 1e-12}, {}),
    ({"Damage": 0}, {"Damage": 1e-6}, {"Damage": (0, 1e-6)}),
    ({"Damage": 1000.0}, {"Damage": 1000.0005}, {}),
    ({"Damage": 1000.0}, {"Damage": 1000.01}, {"Damage": (1000.0, 1000.01)}),
    ({"Damage": 10}, {"Damage": 10, "Bonus": 1000},
     {"Bonus": (MISSING, 1000)}),
    ({"Damage": 10, "Bonus": 0}, {"Damage": 10}, {"Bonus": (0, MISSING)}),
    ({"Damage": float("inf")}, {"Damage": float("inf")}, {}),
    ({"Damage": float("nan")}, {"Damage": float("nan")}, {}),
    ({"Damage": float("inf")}, {"Damage": 1e300},
     {"Damage": (float("inf"), 1e300)}),
    ({"Damage": float("inf")}, {"Damage": float("-inf")},
     {"Damage": (float("inf"), float("-inf"))}),
])
def test_comparator(before, after, expected):
    got = stat_differences(before, after)
    assert set(got) == set(expected)
    for key, (a, b) in expected.items():
        assert repr(got[key]) == repr((a, b))


def test_nan_against_a_number_differs():
    (key,) = stat_differences({"x": float("nan")}, {"x": 1.0})
    assert key == "x"
