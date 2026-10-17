"""Objective scope resolution and aggregate binding (P08-T01.1).

The scope resolver checks a version 2 request's target skill ids and class
scope against a catalog by exact entity id. A display name is reported with
its candidate ids and never substituted. The binding check ties a version 2
aggregate to the objective its manifest froze.

Offline. The catalog rows are synthetic; the required skill's native keys
match the registered D07 identity. They establish no gameplay behavior.
"""

from __future__ import annotations

import pytest
from copy import deepcopy
from dataclasses import replace
from objective_fixtures import v1_request, v2_aggregate, v2_manifest, v2_request
from record_fixtures import load_cases

from pob2opt.catalog.scope import resolve_objective_scope, skill_candidates
from pob2opt.domain import RECORD_TYPES, from_jsonable
from pob2opt.domain.records import CatalogEntity, RunRequest
from pob2opt.domain.validation import aggregate_binding_errors

GEM = "poe2/gems/Metadata/Items/Gems/SkillGemFlickerStrike"
GRANTED = "poe2/granted_skills/FlickerStrikePlayer"
OTHER_GEM = "poe2/gems/fixture/SkillGemEcho"


def entity(entity_id, names, aliases=(), raw=None):
    return CatalogEntity(entity_id=entity_id, display_names=list(names),
                         aliases=list(aliases), raw_reference=raw or {},
                         rule_references=[])


CATALOG = {
    "gems": [entity(GEM, ["Fixture Strike"], raw={
                 "id": "Metadata/Items/Gems/SkillGemFlickerStrike",
                 "grantedEffectId": "FlickerStrikePlayer", "isSupport": False}),
             entity(OTHER_GEM, ["Fixture Echo"], ["Fixture Strike"])],
    "granted_skills": [entity(GRANTED, ["Fixture Strike"], raw={
        "id": "FlickerStrikePlayer", "support": False})],
    "classes": [entity("poe2/classes/1", ["Fixture Class A"],
                       raw={"classId": 1}),
                entity("poe2/classes/2", ["Fixture Class B"],
                       raw={"classId": 2})],
    "ascendancies": [entity("poe2/ascendancies/1/1", ["Fixture Asc A1"],
                            raw={"classId": 1}),
                     entity("poe2/ascendancies/2/1", ["Fixture Asc B1"],
                            raw={"classId": 2})],
}


def request(skills=(GEM, GRANTED), scope=None) -> RunRequest:
    data = v2_request(target_skill_ids=list(skills))
    data["class_scope"] = scope if scope is not None else [
        {"class_id": "poe2/classes/1", "ascendancy_ids": None},
        {"class_id": "poe2/classes/2",
         "ascendancy_ids": ["poe2/ascendancies/2/1"]},
    ]
    return from_jsonable(RunRequest, data)


def codes(report):
    return [(i.code, i.field_path) for i in report.issues]


# -------------------------------------------------------------- scope ===

def test_exact_ids_resolve():
    assert resolve_objective_scope(CATALOG, request()).ok


def test_a_display_name_is_never_accepted_as_an_id():
    report = resolve_objective_scope(CATALOG, request(skills=["Fixture Strike"]))
    (issue,) = report.issues
    assert issue.code == "unresolved_target_skill"
    assert issue.field_path == "/objective/target_skill_ids/0"
    # Every exact-name match is offered, including the alias on another gem;
    # none is applied.
    assert issue.candidates == tuple(sorted((OTHER_GEM, GEM, GRANTED)))


def test_an_unknown_skill_id_blocks():
    report = resolve_objective_scope(CATALOG,
                                     request(skills=["poe2/gems/missing"]))
    assert codes(report) == [("unresolved_target_skill",
                              "/objective/target_skill_ids/0")]
    assert report.issues[0].candidates == ()


def test_the_template_placeholder_class_is_refused():
    report = resolve_objective_scope(CATALOG, request(scope=[
        {"class_id": "REPLACE_WITH_REVIEWED_CLASS", "ascendancy_ids": None}]))
    assert codes(report) == [("unresolved_class", "/class_scope/0/class_id")]


def test_a_class_name_is_offered_not_applied():
    report = resolve_objective_scope(CATALOG, request(scope=[
        {"class_id": "Fixture Class A", "ascendancy_ids": None}]))
    assert report.issues[0].candidates == ("poe2/classes/1",)


def test_an_ascendancy_must_belong_to_its_class():
    report = resolve_objective_scope(CATALOG, request(scope=[
        {"class_id": "poe2/classes/1",
         "ascendancy_ids": ["poe2/ascendancies/2/1", "poe2/ascendancies/9/9"]}]))
    assert codes(report) == [
        ("ascendancy_class_mismatch", "/class_scope/0/ascendancy_ids/0"),
        ("unresolved_ascendancy", "/class_scope/0/ascendancy_ids/1")]


def test_a_version_one_request_must_be_upgraded_first():
    with pytest.raises(ValueError):
        resolve_objective_scope(CATALOG, from_jsonable(RunRequest,
                                                       v1_request()))


def test_skill_candidates_search_both_skill_tables():
    assert skill_candidates(CATALOG, "Fixture Echo") == (OTHER_GEM,)
    assert skill_candidates(CATALOG, "No Such Skill") == ()


# ------------------------------------------------------------ binding ===

def manifest(**changes):
    return from_jsonable(RECORD_TYPES["run_manifest"], v2_manifest(**changes))


def aggregate(**changes):
    return from_jsonable(RECORD_TYPES["aggregate_result"],
                         v2_aggregate(**changes))


def binding(agg, man):
    return [(e.code, e.field_path) for e in aggregate_binding_errors(agg, man)]


def test_an_aggregate_binds_to_its_run():
    assert binding(aggregate(), manifest()) == []


def test_an_aggregate_from_a_different_skill_does_not_bind():
    assert binding(aggregate(), manifest(
        target_skill_ids=["fixture-skill-other"])) == [
        ("objective_hash_mismatch", "/objective_hash")]


def test_an_aggregate_for_another_objective_does_not_bind():
    agg = aggregate(objective_id="balanced_score", objective_metrics={},
                    objective_score=None, objective_gap_ids=["fixture-gap"])
    assert ("objective_mismatch", "/objective_id") in binding(agg, manifest())


def test_an_aggregate_names_its_run():
    assert binding(aggregate(manifest_id="fixture-run-2"), manifest()) == [
        ("manifest_mismatch", "/manifest_id")]


def test_a_version_one_aggregate_cannot_rank_in_a_version_two_run():
    old = from_jsonable(RECORD_TYPES["aggregate_result"],
                        load_cases()["aggregate_result"]["valid"])
    assert binding(old, manifest()) == [("unbound_objective",
                                         "/schema_version")]


def test_a_version_one_run_keeps_version_one_aggregates():
    cases = load_cases()
    old_manifest = from_jsonable(RECORD_TYPES["run_manifest"],
                                 cases["run_manifest"]["valid"])
    old = from_jsonable(RECORD_TYPES["aggregate_result"],
                        cases["aggregate_result"]["valid"])
    assert binding(old, old_manifest) == []
    assert binding(aggregate(), old_manifest) == [
        ("objective_not_in_run", "/objective_id")]


# ------------------------------------------------- shipped v2 example ===

def _example(repo_root):
    import json
    return json.loads((repo_root / "docs/specs/examples/request.flicker.json")
                      .read_text(encoding="utf-8"))


def test_the_flicker_request_example_validates(repo_root):
    from pob2opt.domain.validation import validate_record

    report = validate_record(_example(repo_root), kind="run_request")
    assert report.ok, report.errors
    assert report.record.objective.objective_id == "flicker_sustained_dps"


def test_the_example_placeholder_class_blocks_and_its_skill_ids_are_exact(
        repo_root):
    """The skill ids are the shape the catalog export gives Flicker Strike;
    the class stays a placeholder until P09-T01.1 approves a scope."""
    gem, granted = _example(repo_root)["objective"]["target_skill_ids"]
    catalog = {
        "gems": [entity(gem, ["Flicker Strike"], raw=CATALOG["gems"][0].raw_reference)],
        "granted_skills": [entity(granted, ["Flicker Strike"],
                                  raw=CATALOG["granted_skills"][0].raw_reference)],
        "classes": [], "ascendancies": [],
    }
    report = resolve_objective_scope(
        catalog, from_jsonable(RunRequest, _example(repo_root)))
    assert codes(report) == [("unresolved_class", "/class_scope/0/class_id")]


@pytest.mark.parametrize("skills", [(GEM,), (GRANTED,), (GEM, GRANTED)])
def test_each_registered_representation_resolves_with_catalog_evidence(skills):
    assert resolve_objective_scope(CATALOG, request(skills=skills)).ok


@pytest.mark.parametrize("skills", [(OTHER_GEM,), (GEM, OTHER_GEM),
                                   (GRANTED, OTHER_GEM)])
def test_an_unrelated_exact_id_cannot_be_the_flicker_objective(skills):
    report = resolve_objective_scope(CATALOG, request(skills=skills))
    assert not report.ok
    assert report.issues[0].code == "objective_skill_mismatch"


def test_a_support_with_the_flicker_display_name_is_not_the_target():
    catalog = deepcopy(CATALOG)
    catalog["gems"][1] = entity(OTHER_GEM, ["Flicker Strike"], raw={"isSupport": True})
    assert not resolve_objective_scope(catalog, request(skills=[OTHER_GEM])).ok


@pytest.mark.parametrize("table,key,value", [
    ("gems", "grantedEffectId", "AnotherPlayerSkill"),
    ("gems", "id", "AnotherGem"),
    ("gems", "isSupport", True),
    ("gems", "isSupport", None),
    ("granted_skills", "id", "AnotherPlayerSkill"),
    ("granted_skills", "support", True),
    ("granted_skills", "support", None),
])
def test_catalog_must_evidence_the_active_gem_effect_pair(table, key, value):
    catalog = deepcopy(CATALOG)
    catalog[table][0].raw_reference[key] = value
    report = resolve_objective_scope(catalog, request())
    assert report.issues[0].code == "unverified_objective_skill"


@pytest.mark.parametrize("table", ["gems", "granted_skills"])
@pytest.mark.parametrize("defect", ["missing", "duplicate", "missing_raw"])
def test_missing_or_ambiguous_catalog_evidence_blocks(table, defect):
    catalog = deepcopy(CATALOG)
    if defect == "missing":
        catalog[table] = []
    elif defect == "duplicate":
        catalog[table].append(catalog[table][0])
    else:
        catalog[table][0] = replace(catalog[table][0], raw_reference={})
    # Even selecting only the other representation requires the pair's evidence.
    skills = [GRANTED] if table == "gems" else [GEM]
    assert not resolve_objective_scope(catalog, request(skills=skills)).ok


def test_balanced_scope_does_not_require_a_flicker_catalog():
    from pob2opt.domain.migrate import upgrade_run_request
    old = from_jsonable(RunRequest, v1_request())
    upgraded = upgrade_run_request(replace(old, class_id="poe2/classes/1"))
    assert resolve_objective_scope({"classes": CATALOG["classes"]}, upgraded).ok
