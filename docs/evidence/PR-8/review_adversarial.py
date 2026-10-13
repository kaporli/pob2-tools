"""Analytical counterexamples to PR8's unconditional downtime floor.

This is independent arithmetic over the fixture, not an encounter evaluator
and not a claim about the DPS of any actual or synthetic build.
"""
import json
from pathlib import Path

root = Path(__file__).resolve().parents[3]
bundle = json.loads((root / "tests/fixtures/combat/p09_synthetic_suite.v1.json").read_text())
scenario = next(s for s in bundle["records"]["scenario_spec"] if s["scenario_id"] == "p09-syn-boss-sustained")
target = scenario["target_entities"][0]
windows = target["targetable_windows"]

def kill_time(dps):
    remaining = target["health"]
    for window in windows:
        capacity = (window["end_s"] - window["start_s"]) * dps
        if remaining <= capacity:
            return window["start_s"] + remaining / dps
        remaining -= capacity
    return None

observed = {"whole_horizon_unavailable_s": 30,
    "kill_before_first_window_s": kill_time(2000),
    "kill_after_one_window_s": kill_time(400),
    "kill_after_two_windows_s": kill_time(250),
    "one_damage_per_second_times_out": kill_time(1) is None}
assert observed["kill_before_first_window_s"] == 20
assert observed["kill_after_one_window_s"] == 115
assert observed["kill_after_two_windows_s"] == 190
assert observed["one_damage_per_second_times_out"]
print(json.dumps(observed, indent=2, sort_keys=True))
