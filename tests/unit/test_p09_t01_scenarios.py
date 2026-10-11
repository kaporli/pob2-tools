"""The synthetic encounter suite is valid, frozen and honestly labelled (P09-T01).

The suite exists so P07 can be built before any encounter has been measured.
These tests check three things and nothing else:

1. Every record in it passes the P01 contract validation.
2. The committed file is what ``scripts/p09_t01_suite.py`` produces, and the
   hashes in ``benchmarks/p09-synthetic-v1/suite.json`` are the hashes of those
   records.
3. The synthetic label survives anywhere a record could be lifted out of the
   bundle, and no reference slot has been quietly filled.

None of this says anything about Path of Exile 2. The arithmetic below is
arithmetic over invented constants.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

import p09_t01_suite as suite
from pob2opt.domain.codec import to_jsonable
from pob2opt.domain.identity import baseline_suite_hash, scenario_hash
from pob2opt.domain.validation import validate_record

SUITE_ID = "p09-synthetic-v1"
SHAPES = {
    "p09-syn-clear-dense": ("clear", "clear_dense"),
    "p09-syn-clear-spread": ("clear", "clear_spread"),
    "p09-syn-boss-short": ("boss", "boss_short"),
    "p09-syn-boss-sustained": ("boss", "boss_sustained"),
}


@pytest.fixture(scope="module")
def bundle(fixtures_dir: Path) -> dict:
    path = fixtures_dir / "combat" / "p09_synthetic_suite.v1.json"
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def manifest(repo_root: Path) -> dict:
    path = repo_root / "benchmarks" / SUITE_ID / "suite.json"
    return json.loads(path.read_text(encoding="utf-8"))


# ------------------------------------------------------------- the records

def test_every_record_passes_contract_validation():
    # No index: the suite cites a synthetic patch profile and no evidence
    # records, so reference resolution is not the question here. The gap
    # records in the bundle are what name those missing inputs.
    records = suite.build_scenarios() + suite.build_rotations() + suite.build_gaps()
    for record in records:
        report = validate_record(record)
        assert not report.errors, (record.record_id, [str(e) for e in report.errors])


def test_the_four_shapes_of_scenarios_md_are_all_present(bundle: dict):
    seen = {
        s["scenario_id"]: (s["category"], s["initial_state"]["shape"])
        for s in bundle["records"]["scenario_spec"]
    }
    assert seen == SHAPES


def test_each_category_has_two_workloads(bundle: dict):
    categories = [s["category"] for s in bundle["records"]["scenario_spec"]]
    assert categories.count("clear") == 2
    assert categories.count("boss") == 2


def test_one_rotation_policy_per_category(bundle: dict):
    policies = {r["rotation_id"]: r["category"] for r in bundle["records"]["rotation_policy"]}
    assert policies == {
        "p09-syn-rotation-clear": "clear",
        "p09-syn-rotation-boss": "boss",
    }


def test_the_boss_rotation_can_stop_attacking():
    """An evaluator that damages through an untargetable window is wrong, so
    the policy must have a rule that fires when the target is not targetable."""
    boss = next(r for r in suite.build_rotations() if r.rotation_id == "p09-syn-rotation-boss")
    waits = [r for r in boss.rules if r.action.value == "wait"]
    assert len(waits) == 1
    assert waits[0].predicate.path == "/state/primary_target/targetable"
    assert waits[0].predicate.value is False


# ------------------------------------------------------------- the freezing

def test_the_committed_bundle_is_what_the_generator_produces(bundle: dict):
    built = {
        "scenario_spec": [to_jsonable(s) for s in suite.build_scenarios()],
        "rotation_policy": [to_jsonable(r) for r in suite.build_rotations()],
        "data_gap": [to_jsonable(g) for g in suite.build_gaps()],
    }
    assert bundle["records"] == built


def test_the_manifest_hashes_are_the_hashes_of_these_scenarios(manifest: dict):
    scenarios = suite.build_scenarios()
    by_id = {s.scenario_id: s for s in scenarios}
    for row in manifest["scenarios"]:
        assert row["scenario_hash"] == scenario_hash(by_id[row["scenario_id"]])
    assert manifest["baseline_suite_hash"] == baseline_suite_hash(scenarios)


def test_the_manifest_records_the_bundle_it_describes(repo_root: Path, manifest: dict):
    import hashlib

    source = manifest["scenario_source"]
    data = (repo_root / source["path"]).read_bytes()
    assert hashlib.sha256(data).hexdigest() == source["sha256"]
    assert len(data) == source["bytes"]


# ------------------------------------------------------------- the labelling

def test_every_scenario_carries_the_synthetic_label_inside_itself(bundle: dict):
    for s in bundle["records"]["scenario_spec"]:
        assert s["kind"] == "synthetic"
        state = s["initial_state"]
        assert state["synthetic"] is True
        assert "SYNTHETIC" in state["not_a_claim"]
        assert state["suite_id"] == SUITE_ID


def test_every_target_entity_is_declared_synthetic(bundle: dict):
    for s in bundle["records"]["scenario_spec"]:
        for target in s["target_entities"]:
            assert target["entity_id"].startswith("synthetic_")
            # A synthetic entity resolves to no catalog entity, which is how a
            # reader can tell it names nothing in the game.
            assert target["catalog_entity_id"] is None
            assert target["defenses"]["synthetic"] is True
            assert target["position"]["unit"] == "synthetic_grid"


def test_no_scenario_has_been_given_a_reference(bundle: dict):
    for s in bundle["records"]["scenario_spec"]:
        assert s["reference_build_id"] is None
        assert s["reference_result_id"] is None
        assert s["evidence_ids"] == []
        assert s["validation_status"] == "untested"


def test_the_bundle_refuses_the_uses_it_cannot_support(manifest: dict):
    refused = " ".join(manifest["not_usable_for"]).lower()
    assert "clear speed" in refused
    assert "kill time" in refused
    assert "fitting" in refused or "fit" in refused


# --------------------------------------------------------------- the oracle

def test_the_two_clear_shapes_carry_equal_total_health(bundle: dict):
    oracle = bundle["oracle"]
    dense = oracle["p09-syn-clear-dense"]["total_target_health"]
    spread = oracle["p09-syn-clear-spread"]["total_target_health"]
    assert dense == spread == 2000.0


def test_the_oracle_totals_match_the_declared_entities(bundle: dict):
    for s in bundle["records"]["scenario_spec"]:
        expected = sum(t["health"] * t["count"] for t in s["target_entities"])
        assert bundle["oracle"][s["scenario_id"]]["total_target_health"] == expected


def test_only_the_spread_shape_charges_route_time(bundle: dict):
    oracle = bundle["oracle"]
    assert oracle["p09-syn-clear-spread"]["route_time_s"] == 12.0
    for scenario_id in ("p09-syn-clear-dense", "p09-syn-boss-short",
                        "p09-syn-boss-sustained"):
        assert oracle[scenario_id]["route_time_s"] == 0.0


def test_only_the_sustained_boss_withholds_the_target(bundle: dict):
    """Over the whole configured horizon. Not an elapsed time: see
    ``test_the_completion_clock_stops_at_death``."""
    oracle = bundle["oracle"]
    sustained = oracle["p09-syn-boss-sustained"]
    assert sustained["horizon_untargetable_time_s"] == 30.0
    assert sustained["horizon_targetable_time_s"] == 270.0
    assert sustained["horizon_s"] == 300.0
    for scenario_id in ("p09-syn-clear-dense", "p09-syn-clear-spread",
                        "p09-syn-boss-short"):
        assert oracle[scenario_id]["horizon_untargetable_time_s"] == 0.0


def test_the_untargetable_windows_are_the_gaps_between_targetable_ones(bundle: dict):
    sustained = next(s for s in bundle["records"]["scenario_spec"]
                     if s["scenario_id"] == "p09-syn-boss-sustained")
    windows = sustained["target_entities"][0]["targetable_windows"]
    gaps = [
        windows[i + 1]["start_s"] - windows[i]["end_s"]
        for i in range(len(windows) - 1)
    ]
    assert gaps == [15.0, 15.0]
    assert sum(gaps) == bundle["oracle"]["p09-syn-boss-sustained"][
        "horizon_untargetable_time_s"]


def test_the_horizon_totals_account_for_the_whole_limit(bundle: dict):
    """What the two horizon figures are: a partition of the configured
    horizon into declared targetable and declared untargetable time.

    This replaces a test that compared route time plus untargetable time plus
    preparation against the duration limit and called the result headroom. It
    proved an inequality between constants and nothing else. Those quantities
    are not a lower bound on any evaluation's elapsed time, because none of
    them has to elapse before the target dies.
    """
    for scenario_id, row in bundle["oracle"].items():
        if scenario_id in ("derivation", "worked_examples"):
            continue
        assert (row["horizon_targetable_time_s"]
                + row["horizon_untargetable_time_s"]) == row["horizon_s"]
        assert row["horizon_s"] == row["duration_limit_s"]


def test_the_completion_clock_stops_at_death(bundle: dict):
    """R1. A future window is not part of an evaluation that already ended.

    Each example applies a hypothetical constant damage rate to the sustained
    boss, only while it is targetable, and is recomputed here from the
    declared windows. The arithmetic is over invented constants: it describes
    no build and measures nothing about PoE 2.
    """
    sustained = next(s for s in bundle["records"]["scenario_spec"]
                     if s["scenario_id"] == "p09-syn-boss-sustained")
    windows = [(w["start_s"], w["end_s"])
               for w in sustained["target_entities"][0]["targetable_windows"]]
    health = sustained["target_entities"][0]["health"]
    horizon = sustained["duration_limit_s"]

    examples = [e for e in bundle["oracle"]["worked_examples"]
                if e["scenario_id"] == "p09-syn-boss-sustained"]
    assert len(examples) == 4

    for example in examples:
        rate = example["hypothetical_damage_per_s"]
        completion, elapsed_untargetable = _simulate(windows, health, rate,
                                                     horizon)
        assert completion == example["completion_time_s"], example
        assert elapsed_untargetable == example["untargetable_time_elapsed_s"]
        assert example["outcome"] == ("timed_out" if completion is None
                                      else "completed")

    by_rate = {e["hypothetical_damage_per_s"]: e for e in examples}
    # The case the protocol used to get wrong: a kill at 20 s inside the first
    # window, with none of the horizon's 30 s of invulnerability elapsed.
    assert by_rate[2000.0]["completion_time_s"] == 20.0
    assert by_rate[2000.0]["untargetable_time_elapsed_s"] == 0.0
    assert by_rate[400.0]["completion_time_s"] == 115.0
    assert by_rate[250.0]["completion_time_s"] == 190.0
    # And a timeout is a valid failed evaluation, not a broken evaluator.
    assert by_rate[1.0]["completion_time_s"] is None
    assert by_rate[1.0]["outcome"] == "timed_out"


def _simulate(windows, health, rate, horizon):
    """Completion time and untargetable time elapsed before it, or None."""
    remaining = health
    previous_end = None
    untargetable = 0.0
    for start, end in windows:
        if start >= horizon:
            break
        if previous_end is not None:
            untargetable += min(start, horizon) - previous_end
        previous_end = min(end, horizon)
        available = previous_end - start
        if rate * available >= remaining:
            return round(start + remaining / rate, 6), untargetable
        remaining -= rate * available
    return None, untargetable
