"""RunRequest and AggregateResult schema version 2: the D07 objective (P08-T01.1).

Version 2 requests replace ``class`` with an explicit ``class_scope`` and add
an ``objective`` selection; version 2 aggregates bind the score to a
registered objective version and hash. These tests pin the version rules,
the refusal of unknown objectives, the v1 migration, the objective identity
and its binding into the manifest and aggregate cache key.

Contract work only: no prepare service, evaluator or catalog resolution is
exercised. Skill and class ids are synthetic placeholders, not PoE 2 entities.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import replace

import pytest
from objective_fixtures import (CASES, H, flicker_objective,
                                resolved_selection, v1_request, v2_aggregate,
                                v2_manifest, v2_request)

from pob2opt.domain import (RECORD_TYPES, from_jsonable, manifest_hash,
                            to_jsonable)
from pob2opt.domain import objectives as objectives_module
from pob2opt.domain.absent import ABSENT
from pob2opt.domain.cache import AggregateComponent, AggregateKey
from pob2opt.domain.identity import (UnresolvedObjective, content_hash,
                                     objective_hash)
from pob2opt.domain.migrate import upgrade_run_request
from pob2opt.domain.objectives import (BALANCED_V1, FLICKER_SUSTAINED_DPS_V1,
                                       ObjectiveWindow, UnknownObjective,
                                       get_objective)
from pob2opt.domain.records import (ClassScope, ObjectiveSelection,
                                    RunRequest, supported_schema_versions)
from pob2opt.domain.schemas import UnknownSchemaVersion, check_schema_version
from pob2opt.domain.validation import validate_record

def codes(payload: dict, kind: str) -> set[str]:
    return {e.code for e in validate_record(payload, kind=kind).errors}


def paths(payload: dict, kind: str) -> set[str]:
    return {e.field_path for e in validate_record(payload, kind=kind).errors}


# ------------------------------------------------------------- versions ===

def test_request_and_aggregate_read_versions_one_and_two():
    for kind in ("run_request", "aggregate_result"):
        assert supported_schema_versions(kind) == (1, 2)
        assert check_schema_version(2, kind) == 2
        with pytest.raises(UnknownSchemaVersion):
            check_schema_version(3, kind)
    request = v2_request()
    request["schema_version"] = 3
    assert codes(request, "run_request") == {"unsupported_schema_version"}


def test_a_flicker_request_validates():
    assert validate_record(v2_request(), kind="run_request").ok


def test_version_two_retires_class_and_version_one_keeps_it():
    with_class = v2_request()
    with_class["class"] = "fixture-class-a"
    assert "schema_violation" in codes(with_class, "run_request")

    no_class = v1_request()
    del no_class["class"]
    assert "schema_violation" in codes(no_class, "run_request")

    for key in ("class_scope", "objective"):
        early = v1_request()
        early[key] = v2_request()[key]
        assert "schema_violation" in codes(early, "run_request"), key


def test_version_two_requires_scope_and_objective():
    for key in ("class_scope", "objective"):
        request = v2_request()
        del request[key]
        assert "schema_violation" in codes(request, "run_request"), key


def test_a_version_one_request_is_unchanged():
    """Old requests decode, re-encode byte-identically and keep their hash."""
    payload = v1_request()
    decoded = from_jsonable(RunRequest, payload)
    assert decoded.class_scope is ABSENT and decoded.objective is ABSENT
    assert to_jsonable(decoded) == payload
    assert validate_record(payload, kind="run_request").ok
    manifest = CASES["run_manifest"]["valid"]
    assert manifest_hash(from_jsonable(RECORD_TYPES["run_manifest"],
                                       manifest)) == content_hash(manifest)
    assert validate_record(manifest, kind="run_manifest").ok


# --------------------------------------------------- objective refusal ===

@pytest.mark.parametrize("objective_id, version", [
    ("fixture-unknown-objective", 1),
    ("flicker_sustained_dps", 2),
    ("balanced_score", 9),
])
def test_an_unknown_objective_is_refused(objective_id, version):
    request = v2_request(objective_id=objective_id, objective_version=version)
    report = validate_record(request, kind="run_request")
    assert {e.code for e in report.errors} == {"unknown_objective"}
    assert report.errors[0].field_path == "/objective/objective_id"
    with pytest.raises(UnknownObjective):
        get_objective(objective_id, version)


def test_a_suite_filename_does_not_select_the_objective():
    request = v2_request()
    request["scenario_suite"] = "benchmarks/flicker-strike-v1/suite.json"
    request["objective"] = flicker_objective(objective_id="flicker")
    assert codes(request, "run_request") == {"unknown_objective"}


@pytest.mark.parametrize("changes, code, path", [
    ({"target_skill_ids": []}, "missing_target_skill",
     "/objective/target_skill_ids"),
    ({"target_skill_ids": ["fixture-skill-flicker", "fixture-skill-flicker"]},
     "duplicate_target_skill", "/objective/target_skill_ids/1"),
    ({"benchmark_scenario": None}, "missing_benchmark_scenario",
     "/objective/benchmark_scenario"),
    ({"attribution_rules": None}, "missing_attribution_rules",
     "/objective/attribution_rules"),
])
def test_the_flicker_objective_needs_its_skill_and_benchmark(changes, code,
                                                              path):
    request = v2_request(**changes)
    assert codes(request, "run_request") == {code}
    assert paths(request, "run_request") == {path}


def test_the_balanced_objective_takes_no_skill_or_benchmark():
    request = v2_request(objective_id="balanced_score",
                         target_skill_ids=[], benchmark_scenario=None,
                         attribution_rules=None)
    assert validate_record(request, kind="run_request").ok
    request["objective"]["target_skill_ids"] = ["fixture-skill-flicker"]
    request["objective"]["attribution_rules_hash"] = H["attr"]
    assert codes(request, "run_request") == {"unexpected_target_skill",
                                             "unexpected_benchmark"}


@pytest.mark.parametrize("scope, code", [
    ([], "empty_class_scope"),
    ([{"class_id": "fixture-class-a", "ascendancy_ids": None},
      {"class_id": "fixture-class-a", "ascendancy_ids": None}],
     "duplicate_class_scope"),
    ([{"class_id": "fixture-class-a", "ascendancy_ids": []}],
     "empty_ascendancy_scope"),
    ([{"class_id": "fixture-class-a",
       "ascendancy_ids": ["fixture-asc", "fixture-asc"]}],
     "duplicate_ascendancy_scope"),
])
def test_the_class_scope_is_explicit(scope, code):
    request = v2_request()
    request["class_scope"] = scope
    assert codes(request, "run_request") == {code}


def test_a_class_id_cannot_be_empty():
    request = v2_request()
    request["class_scope"] = [{"class_id": "", "ascendancy_ids": None}]
    assert "schema_violation" in codes(request, "run_request")


# ----------------------------------------------------------- migration ===

def test_a_version_one_request_upgrades_to_the_balanced_objective():
    old = from_jsonable(RunRequest, v1_request())
    new = upgrade_run_request(old)
    assert new.schema_version == 2 and new.class_id is ABSENT
    assert new.class_scope == [ClassScope(class_id=old.class_id,
                                          ascendancy_ids=None)]
    assert (new.objective.objective_id, new.objective.objective_version) == \
        (BALANCED_V1.objective_id, BALANCED_V1.version)
    assert new.objective.target_skill_ids == []
    assert validate_record(new).ok
    # Everything else is carried over unchanged.
    assert replace(new, schema_version=1, class_id=old.class_id,
                   class_scope=ABSENT, objective=ABSENT) == old


def test_an_upgrade_never_selects_a_skill_objective():
    new = upgrade_run_request(from_jsonable(RunRequest, v1_request()))
    assert new.objective.objective_id != FLICKER_SUSTAINED_DPS_V1.objective_id
    assert new.objective.benchmark_scenario is None


def test_a_version_two_request_is_not_upgraded_again():
    with pytest.raises(ValueError):
        upgrade_run_request(from_jsonable(RunRequest, v2_request()))


# ---------------------------------------------------- objective identity ===

def test_a_request_file_objective_has_no_identity_yet():
    with pytest.raises(UnresolvedObjective):
        objective_hash(from_jsonable(ObjectiveSelection, flicker_objective()))


def test_an_unknown_objective_has_no_identity():
    with pytest.raises(UnknownObjective):
        objective_hash(resolved_selection(objective_version=2))


@pytest.mark.parametrize("changes", [
    {"target_skill_ids": ["fixture-skill-other"]},
    {"target_skill_ids": ["fixture-skill-flicker", "fixture-skill-granted"]},
    {"benchmark_scenario_hash": H["other"]},
    {"attribution_rules_hash": H["other"]},
])
def test_skill_benchmark_and_attribution_change_the_identity(changes):
    assert objective_hash(resolved_selection(**changes)) != \
        objective_hash(resolved_selection())


def test_locators_and_skill_order_do_not_change_the_identity():
    base = resolved_selection(target_skill_ids=["fixture-a", "fixture-b"])
    assert objective_hash(base) == objective_hash(resolved_selection(
        target_skill_ids=["fixture-b", "fixture-a"],
        benchmark_scenario="elsewhere/bench.json",
        attribution_rules="elsewhere/rules.json"))


def test_the_objective_identity_differs_between_objectives():
    balanced = from_jsonable(ObjectiveSelection, flicker_objective(
        objective_id="balanced_score", target_skill_ids=[],
        benchmark_scenario=None, attribution_rules=None))
    assert objective_hash(balanced) != objective_hash(resolved_selection())


def test_editing_a_window_without_a_new_version_changes_the_identity(
        monkeypatch):
    """A silent edit to a registered rule cannot reuse old aggregates."""
    before = objective_hash(resolved_selection())
    edited = replace(FLICKER_SUSTAINED_DPS_V1, windows=(
        ObjectiveWindow("sustained", 0.0, 60.0),
        ObjectiveWindow("burst", 0.0, 5.0)))
    monkeypatch.setitem(objectives_module.OBJECTIVES,
                        ("flicker_sustained_dps", 1), edited)
    assert objective_hash(resolved_selection()) != before


def test_the_registered_flicker_windows_are_the_d07_defaults():
    windows = {w.name: (w.start_s, w.end_s)
               for w in FLICKER_SUSTAINED_DPS_V1.windows}
    assert windows == {"sustained": (0.0, 120.0), "burst": (0.0, 5.0)}
    assert FLICKER_SUSTAINED_DPS_V1.score_metric == "flicker_sustained_dps"
    assert FLICKER_SUSTAINED_DPS_V1.tie_tolerance == 1e-6


# ------------------------------------------------ manifest and cache key ===

def test_a_manifest_binds_the_resolved_objective():
    assert validate_record(v2_manifest(), kind="run_manifest").ok


def test_a_manifest_cannot_freeze_an_unresolved_objective():
    manifest = v2_manifest()
    manifest["resolved_request"]["objective"]["attribution_rules_hash"] = None
    report = validate_record(manifest, kind="run_manifest")
    assert {e.code for e in report.errors} == {"unresolved_objective"}
    assert report.errors[0].field_path == \
        "/resolved_request/objective/attribution_rules_hash"


def test_a_manifest_objective_hash_must_identify_the_objective():
    manifest = v2_manifest()
    manifest["resolved_request"]["objective"]["target_skill_ids"] = [
        "fixture-skill-other"]
    report = validate_record(manifest, kind="run_manifest")
    assert {e.code for e in report.errors} == {"objective_hash_mismatch"}


def test_class_scope_is_part_of_the_manifest_identity():
    manifest = v2_manifest()
    narrowed = deepcopy(manifest)
    narrowed["resolved_request"]["class_scope"] = \
        manifest["resolved_request"]["class_scope"][:1]
    assert validate_record(narrowed, kind="run_manifest").ok
    cls = RECORD_TYPES["run_manifest"]
    assert manifest_hash(from_jsonable(cls, narrowed)) != \
        manifest_hash(from_jsonable(cls, manifest))
    # Per-class contexts share one objective identity.
    assert narrowed["dependency_hashes"]["objective_hash"] == \
        manifest["dependency_hashes"]["objective_hash"]


def test_changing_the_main_skill_changes_the_aggregate_key():
    cls = RECORD_TYPES["run_manifest"]
    components = [AggregateComponent("fixture-flicker-bench", "e" * 64)]

    def key(manifest):
        return AggregateKey.from_components(
            from_jsonable(cls, manifest), build_hash="f" * 64,
            rotation_hash="0" * 64, components=components).cache_key()

    assert key(v2_manifest()) != key(v2_manifest(
        target_skill_ids=["fixture-skill-other"]))


# ------------------------------------------------------------ aggregates ===

def test_a_flicker_aggregate_validates():
    assert validate_record(v2_aggregate(), kind="aggregate_result").ok


def test_a_version_one_aggregate_cannot_carry_objective_fields():
    aggregate = deepcopy(CASES["aggregate_result"]["valid"])
    aggregate["objective_score"] = 1.0
    assert "schema_violation" in codes(aggregate, "aggregate_result")


def test_a_version_one_aggregate_keeps_its_free_form_objective_name():
    assert validate_record(CASES["aggregate_result"]["valid"],
                           kind="aggregate_result").ok


def test_an_aggregate_for_an_unknown_objective_is_refused():
    aggregate = v2_aggregate(objective_id="fixture-objective-balanced")
    assert codes(aggregate, "aggregate_result") == {"unknown_objective"}


def test_the_score_is_never_filled_from_the_balanced_score():
    aggregate = v2_aggregate(
        category_scores={"clear": 0.9, "boss": 0.8}, balanced_score=0.85,
        objective_metrics={"flicker_sustained_dps": None,
                           "flicker_burst_dps": None},
        objective_score=0.85, objective_gap_ids=["fixture-gap-1"])
    assert codes(aggregate, "aggregate_result") == {"objective_score_mismatch"}


def test_burst_cannot_stand_in_for_sustained():
    aggregate = v2_aggregate(objective_score=1500.0)
    assert codes(aggregate, "aggregate_result") == {"objective_score_mismatch"}


def test_missing_objective_metrics_stay_null_with_gaps():
    metrics = {"flicker_sustained_dps": None, "flicker_burst_dps": 1500.0}
    without_gap = v2_aggregate(objective_metrics=metrics, objective_score=None)
    assert codes(without_gap, "aggregate_result") == {
        "unexplained_missing_objective"}
    with_gap = v2_aggregate(objective_metrics=metrics, objective_score=None,
                            objective_gap_ids=["fixture-gap-1"])
    assert validate_record(with_gap, kind="aggregate_result").ok


def test_an_eligible_candidate_needs_an_objective_score():
    aggregate = v2_aggregate(
        category_scores={"clear": 0.9, "boss": 0.8}, balanced_score=0.85,
        eligible=True, strength_label="balanced", recommendation_status=
        "recommended", exclusion_reasons=[],
        objective_metrics={"flicker_sustained_dps": None,
                           "flicker_burst_dps": None},
        objective_score=None, objective_gap_ids=["fixture-gap-1"])
    assert codes(aggregate, "aggregate_result") == {
        "eligible_without_objective_score"}


@pytest.mark.parametrize("metrics", [
    {"flicker_sustained_dps": 1000.0},
    {"flicker_sustained_dps": 1000.0, "flicker_burst_dps": 1.0,
     "balanced_score": 0.5},
])
def test_an_aggregate_states_exactly_the_objective_metrics(metrics):
    aggregate = v2_aggregate(objective_metrics=metrics)
    assert codes(aggregate, "aggregate_result") == {
        "objective_metrics_mismatch"}


def test_damage_per_second_cannot_be_negative():
    aggregate = v2_aggregate(
        objective_metrics={"flicker_sustained_dps": 1000.0,
                           "flicker_burst_dps": -1.0})
    assert codes(aggregate, "aggregate_result") == {
        "negative_objective_metric"}


def test_a_balanced_objective_aggregate_scores_by_balanced_score():
    aggregate = v2_aggregate(
        objective_id="balanced_score", objective_metrics={},
        category_scores={"clear": 0.9, "boss": 0.8}, balanced_score=0.85,
        objective_score=0.85)
    assert validate_record(aggregate, kind="aggregate_result").ok
    aggregate["objective_score"] = 0.9
    assert codes(aggregate, "aggregate_result") == {"objective_score_mismatch"}


def test_the_balanced_objective_keeps_the_scenarios_tie_break():
    assert BALANCED_V1.tie_tolerance == 1e-6
    assert BALANCED_V1.tie_breakers == ("min_clear_boss",
                                        "canonical_build_rotation_hash")


def test_the_required_skill_mapping_is_part_of_objective_identity(monkeypatch):
    before = objective_hash(resolved_selection())
    edited = replace(FLICKER_SUSTAINED_DPS_V1,
                     target_skill=replace(FLICKER_SUSTAINED_DPS_V1.target_skill,
                                          granted_skill_id="DifferentSkill"))
    monkeypatch.setitem(objectives_module.OBJECTIVES,
                        (edited.objective_id, edited.version), edited)
    assert objective_hash(resolved_selection()) != before
