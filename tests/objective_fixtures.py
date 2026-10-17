"""Request, manifest and aggregate builders for the D07 objective tests.

Synthetic: skill and class ids are placeholders, not PoE 2 entities. The
version 1 bases come from ``fixtures/records``.
"""

from __future__ import annotations

from copy import deepcopy

from record_fixtures import load_cases

from pob2opt.domain import from_jsonable
from pob2opt.domain.identity import objective_hash
from pob2opt.domain.records import ObjectiveSelection

CASES = load_cases()
H = {name: ch * 64 for name, ch in (("bench", "b"), ("attr", "c"),
                                    ("other", "d"))}


def v1_request() -> dict:
    return deepcopy(CASES["run_request"]["valid"])


def flicker_objective(**changes) -> dict:
    objective = {
        "objective_id": "flicker_sustained_dps",
        "objective_version": 1,
        "target_skill_ids": ["fixture-skill-flicker"],
        "benchmark_scenario": "fixture/flicker_sustained_v1.json",
        "benchmark_scenario_hash": None,
        "attribution_rules": "fixture/attribution-v1.json",
        "attribution_rules_hash": None,
    }
    objective.update(changes)
    return objective


def v2_request(**objective_changes) -> dict:
    request = v1_request()
    del request["class"]
    request["schema_version"] = 2
    request["class_scope"] = [
        {"class_id": "fixture-class-a", "ascendancy_ids": None},
        {"class_id": "fixture-class-b",
         "ascendancy_ids": ["fixture-ascendancy-b1"]},
    ]
    request["objective"] = flicker_objective(**objective_changes)
    return request


def resolved_selection(**changes) -> ObjectiveSelection:
    data = flicker_objective(benchmark_scenario_hash=H["bench"],
                             attribution_rules_hash=H["attr"])
    data.update(changes)
    return from_jsonable(ObjectiveSelection, data)


def v2_manifest(**objective_changes) -> dict:
    manifest = deepcopy(CASES["run_manifest"]["valid"])
    request = v2_request(benchmark_scenario_hash=H["bench"],
                         attribution_rules_hash=H["attr"],
                         **objective_changes)
    request["workers"] = manifest["resolved_request"]["workers"]
    request["patch_selection"] = manifest["resolved_request"]["patch_selection"]
    manifest["resolved_request"] = request
    selection = from_jsonable(ObjectiveSelection, request["objective"])
    manifest["dependency_hashes"]["objective_hash"] = objective_hash(selection)
    return manifest


def v2_aggregate(**changes) -> dict:
    aggregate = deepcopy(CASES["aggregate_result"]["valid"])
    aggregate.update({
        "schema_version": 2,
        "objective_id": "flicker_sustained_dps",
        "objective_version": 1,
        "objective_hash": objective_hash(resolved_selection()),
        "objective_metrics": {"flicker_sustained_dps": 1000.0,
                              "flicker_burst_dps": 1500.0},
        "objective_score": 1000.0,
        "objective_gap_ids": [],
    })
    aggregate.update(changes)
    return aggregate
