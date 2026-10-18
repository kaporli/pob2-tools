"""P02-T03 offline lane: legality validation with no PoB and no network.

Two sources of rules, neither of them this test file:

* `tests/fixtures/legality/p02_t03_world.json`, an invented world in the row
  shapes the engine reports, exported by the **real P02-T02 exporter**. The
  rules the validator reads are therefore produced by the catalog code, and
  the level cap, the point maximums and the support limit come from the real
  citations captured from the pinned checkout;
* `docs/evidence/P02/catalog-rows-slice.json`, the committed slice of real
  engine rows, exported the same way. That lane checks the claims this task
  makes about the *shipped* profile: that its slot rules carry the engine's
  categories (P02-T03.1), that its budgets count levelling points only, and that the validator says so
  instead of filling them in.

The expected violations and unknowns live in `p02_t03_cases.json`, written by
hand from the rules. Nothing here was produced by running the validator and
recording its answer.
"""

from __future__ import annotations

import copy
import dataclasses
import json
from pathlib import Path

import pytest

import legality_fixtures as fixtures
from pob2opt.catalog import (ExportRequest, MappingCatalogReader,
                             PobCatalogProvider)
from pob2opt.catalog.sources import citations_from_payload
from pob2opt.domain.enums import GapSeverity, Legality
from pob2opt.domain.validation import RecordIndex, validate_record
from pob2opt.evaluation.legality import (CHECK_ASCENDANCY_BUDGET, CHECK_CLASS,
                                         CHECK_IMPORT, CHECK_ITEM_REQUIREMENTS,
                                         CHECK_PASSIVE_BUDGET,
                                         CHECK_RESERVATION, CHECK_SLOTS,
                                         DECLARED_CHECKS, CatalogIndex,
                                         LegalityValidator, ReportBuilder)
from pob2opt.evaluation.legality.gaps import (T02_QUEST_PASSIVE_POINTS,
                                              T02_SLOT_CATEGORIES)

REPO_ROOT = Path(__file__).resolve().parents[2]
SLICE = REPO_ROOT / "docs" / "evidence" / "P02" / "catalog-rows-slice.json"


# ------------------------------------------------------------------ fixtures

@pytest.fixture(scope="module")
def world():
    return fixtures.load_world()


@pytest.fixture(scope="module")
def cases():
    return fixtures.load_cases()


@pytest.fixture(scope="module")
def items(cases, world):
    return fixtures.make_items(cases, world.catalog.catalog_hash)


def _validator(world, items, case):
    return LegalityValidator(
        catalog=world.catalog, items=items,
        imported=fixtures.make_imported(case.get("imported"),
                                        build_hash="build/p02-t03"),
        measured=fixtures.make_measured(case.get("measured")),
        clock=lambda: "2026-10-06T00:00:00Z")


def _build(cases, world, case):
    spec = {**cases["base"], **case["build"]}
    return fixtures.make_build(spec, catalog_hash=world.catalog.catalog_hash)


def _ids(cases):
    return [case["id"] for case in cases["cases"]]


# --------------------------------------------------- the case-driven lane ---

def test_every_case_matches_the_expectations_written_beside_it(cases, world, items):
    """One assertion loop, so a case that is wrong fails with its own id."""
    failures = []
    for case in cases["cases"]:
        build = _build(cases, world, case)
        report = _validator(world, items, case).validate(build, world.profile)
        expect = case["expect"]
        problems = []
        if report.legality.value != expect["legality"]:
            problems.append("legality %s, expected %s"
                            % (report.legality.value, expect["legality"]))
        if "violations" in expect:
            got = sorted(set(report.violation_codes))
            want = sorted(set(expect["violations"]))
            if got != want:
                problems.append("violations %s, expected %s" % (got, want))
        if "unknowns" in expect:
            got = sorted(set(report.unknown_codes))
            want = sorted(set(expect["unknowns"]))
            if got != want:
                problems.append("unknowns %s, expected %s" % (got, want))
        for code in expect.get("unknowns_include", ()):
            if code not in report.unknown_codes:
                problems.append("missing unknown %s (got %s)"
                                % (code, sorted(set(report.unknown_codes))))
        for code in expect.get("unknowns_exclude", ()):
            if code in report.unknown_codes:
                problems.append("unexpected unknown %s" % code)
        for gap_id in expect.get("cited_gaps", ()):
            if gap_id not in report.cited_gap_ids:
                problems.append("missing cited gap %s (got %s)"
                                % (gap_id, list(report.cited_gap_ids)))
        for check_id, decision in expect.get("checks", {}).items():
            got = report.decision(check_id).value
            if got != decision:
                problems.append("check %s is %s, expected %s"
                                % (check_id, got, decision))
        if problems:
            failures.append("%s: %s" % (case["id"], "; ".join(problems)))
    assert not failures, "\n".join(failures)


def test_the_fixture_covers_every_declared_check(cases, world, items):
    """Every check is exercised by at least one case, in each direction it has."""
    seen: dict[str, set[str]] = {check: set() for check in DECLARED_CHECKS}
    for case in cases["cases"]:
        build = _build(cases, world, case)
        report = _validator(world, items, case).validate(build, world.profile)
        for outcome in report.checks:
            seen[outcome.check_id].add(outcome.decision.value)
    missing = sorted(check for check, states in seen.items()
                     if "illegal" not in states and "unknown" not in states)
    assert not missing, "no case exercises a non-legal answer for %s" % missing
    never_legal = sorted(check for check, states in seen.items()
                         if "legal" not in states)
    assert not never_legal, "no case passes %s" % never_legal


def test_a_violation_names_the_rule_and_the_field(cases, world, items):
    for case in cases["cases"]:
        build = _build(cases, world, case)
        report = _validator(world, items, case).validate(build, world.profile)
        for finding in report.violations:
            assert finding.message.strip(), finding.code
            assert finding.check_id in DECLARED_CHECKS
            assert not finding.gap_ids, (
                "%s is a violation and cites a gap" % finding.code)


def test_every_unknown_cites_a_gap(cases, world, items):
    for case in cases["cases"]:
        build = _build(cases, world, case)
        report = _validator(world, items, case).validate(build, world.profile)
        for finding in report.unknowns:
            assert finding.gap_ids, "%s cites no gap" % finding.code
            assert not finding.evidence_ids, (
                "%s is an unknown and cites rule evidence" % finding.code)


def test_the_builder_refuses_an_unknown_without_a_gap():
    out = ReportBuilder()
    with pytest.raises(ValueError, match="cites no gap"):
        out.unknown(CHECK_CLASS, "invented", "no gap here")


# ------------------------------------------------- no silent repair at all ---

def test_validation_does_not_touch_the_build_or_the_profile(cases, world, items):
    case = next(c for c in cases["cases"] if c["id"] == "combined_violations")
    build = _build(cases, world, case)
    before_build = copy.deepcopy(dataclasses.asdict(build))
    before_profile = copy.deepcopy(dataclasses.asdict(world.profile))
    report = _validator(world, items, case).validate(build, world.profile)
    assert report.legality is Legality.ILLEGAL
    assert dataclasses.asdict(build) == before_build
    assert dataclasses.asdict(world.profile) == before_profile


def test_the_same_build_validates_the_same_way_twice(cases, world, items):
    case = next(c for c in cases["cases"] if c["id"] == "combined_violations")
    build = _build(cases, world, case)
    first = _validator(world, items, case).validate(build, world.profile)
    second = _validator(world, items, case).validate(build, world.profile)
    assert first.to_dict() == second.to_dict()


# --------------------------------------------- what a verdict may rest on ---

def test_attributes_and_spirit_alone_are_not_a_legality_verdict(cases, world, items):
    """Both pass, sixteen other checks exist, and the verdict is not legal."""
    case = {"build": {"level": 40,
                      "equipment": {"Weapon 1": {"item": "greataxe"}}},
            "measured": {"strength": 100, "dexterity": 50, "intelligence": 50,
                         "pools": {"spirit": {"total": 100, "reserved": 10,
                                              "unreserved": 90}}}}
    build = _build(cases, world, case)
    report = _validator(world, items, case).validate(build, world.profile)
    assert report.decision(CHECK_RESERVATION) is Legality.LEGAL
    assert report.decision(CHECK_ITEM_REQUIREMENTS) is Legality.LEGAL
    assert report.legality is Legality.UNKNOWN
    assert report.decision(CHECK_SLOTS) is Legality.UNKNOWN
    assert any("two of the %d declared checks" % len(DECLARED_CHECKS) in note
               for note in report.notes)


def test_a_check_that_did_not_run_is_unknown():
    out = ReportBuilder()
    out.ran(CHECK_CLASS, "ran")
    assert out.decision_for(CHECK_CLASS) is Legality.LEGAL
    assert out.decision_for(CHECK_IMPORT) is Legality.UNKNOWN
    report = out.build(build_hash="b", patch_profile_id="p", catalog_hash="c")
    assert report.legality is Legality.UNKNOWN
    assert report.check(CHECK_IMPORT).summary.startswith("the check did not run")


def test_an_unverified_import_can_never_be_legal(cases, world, items):
    case = {"build": {}}
    build = _build(cases, world, case)
    report = _validator(world, items, case).validate(build, world.profile)
    assert report.decision(CHECK_IMPORT) is Legality.UNKNOWN
    assert report.legality is Legality.UNKNOWN


# ------------------------------------------------------- the raised gaps ---

def test_raised_gaps_are_valid_p01_records(cases, world, items):
    case = next(c for c in cases["cases"] if c["id"] == "item_record_not_supplied")
    build = _build(cases, world, case)
    report = _validator(world, items, case).validate(build, world.profile)
    assert report.gaps
    index = RecordIndex.from_records([build, world.profile, *report.gaps])
    for gap in report.gaps:
        issues = validate_record(gap, index=index)
        assert issues.ok, issues.codes
        assert gap.needed_evidence.strip()
        assert "more data" not in gap.needed_evidence.lower()
        assert gap.collection_method.strip()


def test_a_gap_names_everything_it_was_raised_for(cases, world, items):
    """The unresolvable names go in the explanation, not in subject_ids.

    contracts.md requires every reference to resolve, and the whole point of
    these two is that they do not. The report's findings carry them as
    fields; the stored record names them as text.
    """
    case = {"build": {"level": 10,
                      "equipment": {"Ring 1": {"item": "ghost"},
                                    "Ring 2": {"item": "phantom"}}}}
    build = _build(cases, world, case)
    report = _validator(world, items, case).validate(build, world.profile)
    gap = next(gap for gap in report.gaps
               if gap.gap_id.endswith("item-record-not-supplied"))
    assert "ghost" in gap.explanation and "phantom" in gap.explanation
    assert set(gap.subject_ids) == {build.record_id, world.profile.record_id}
    subjects = {subject for finding in report.unknowns
                for subject in finding.subject_ids}
    assert {"ghost", "phantom"} <= subjects


# ---------------------------------------- the real profile from the slice ---

@pytest.fixture(scope="module")
def shipped():
    """The real P02-T02 export over the committed slice of engine rows."""
    rows = json.loads(SLICE.read_text(encoding="utf-8"))
    provider = PobCatalogProvider(
        MappingCatalogReader(rows["tables"], rows["rule_sources"],
                             source=str(SLICE)),
        citations=citations_from_payload(rows["citations"]),
        pob_commit=rows["pob_commit"],
        pob_dirty_hash=rows["pob_dirty_hash"],
        fixtures={"fixture_set_version": 0, "recorded_from": {}, "fixtures": []},
        clock=lambda: "2026-10-06T00:00:00Z")
    return provider.export(ExportRequest())


def _shipped_build(shipped, **overrides):
    spec = {"class_id": "poe2/classes/8", "level": 5, "allocated": [],
            **overrides}
    return fixtures.make_build(spec, catalog_hash=shipped.catalog.catalog_hash)


def test_the_shipped_profile_carries_engine_slot_categories(shipped):
    """P02-T03 found none; the slice regenerated in P02-T03.1 carries the
    engine's slot acceptance probe, so the categories are now decided."""
    rules = {r.slot_id: r for r in shipped.profile.character_rules.slots}
    assert "Staff/Warstaff" in rules["poe2/slots/Weapon 1"].accepted_base_categories
    assert T02_SLOT_CATEGORIES not in {gap.gap_id for gap in shipped.gaps}


def test_equipment_on_the_shipped_profile_is_decided(shipped):
    item_hash = "shipped-item"
    item = fixtures.make_item(item_hash, {
        "catalog_hash": shipped.catalog.catalog_hash,
        "base_id": "Long Quarterstaff", "display_name": "A real base",
        "requirements": {"level": 1},
        "source_document_id": "source/invented"})
    build = _shipped_build(shipped,
                           equipment={"Weapon 1": {"item": item_hash}})
    report = LegalityValidator(catalog=shipped.catalog,
                               items={item_hash: item}).validate(
        build, shipped.profile)
    assert report.decision(CHECK_SLOTS) is Legality.LEGAL
    assert T02_SLOT_CATEGORIES not in report.cited_gap_ids
    wrong = _shipped_build(shipped, equipment={"Amulet": {"item": item_hash}})
    report = LegalityValidator(catalog=shipped.catalog,
                               items={item_hash: item}).validate(
        wrong, shipped.profile)
    assert report.decision(CHECK_SLOTS) is Legality.ILLEGAL


def test_the_shipped_class_list_decides_membership(shipped):
    legal = _shipped_build(shipped, class_id="poe2/classes/8")
    assert LegalityValidator(catalog=shipped.catalog).validate(
        legal, shipped.profile).decision(CHECK_CLASS) is Legality.LEGAL
    invented = _shipped_build(shipped, class_id="poe2/classes/4242")
    report = LegalityValidator(catalog=shipped.catalog).validate(
        invented, shipped.profile)
    assert report.decision(CHECK_CLASS) is Legality.ILLEGAL
    assert "unknown_class" in report.violation_codes


def test_the_shipped_budget_is_a_lower_bound_and_says_so(shipped):
    """No `(level - 1) + 8` anywhere: over the levelling budget is unknown."""
    build = _shipped_build(shipped, level=5, allocated=[1, 2, 3, 4, 5])
    report = LegalityValidator(catalog=shipped.catalog).validate(
        build, shipped.profile)
    assert report.decision(CHECK_PASSIVE_BUDGET) is Legality.UNKNOWN
    assert "passive_points_above_levelling_budget" in report.unknown_codes
    assert T02_QUEST_PASSIVE_POINTS in report.cited_gap_ids
    constraint = next(c for c in report.constraints if c.name == "passive_points")
    assert constraint.used == 5 and constraint.allowed is None


def test_the_shipped_level_range_is_the_engines(shipped):
    rules = shipped.profile.character_rules
    at_maximum = _shipped_build(shipped, level=rules.level_range.maximum)
    over = _shipped_build(shipped, level=rules.level_range.maximum + 1)
    assert LegalityValidator(catalog=shipped.catalog).validate(
        at_maximum, shipped.profile).decision("character_level") is Legality.LEGAL
    assert LegalityValidator(catalog=shipped.catalog).validate(
        over, shipped.profile).decision("character_level") is Legality.ILLEGAL


def test_the_shipped_ascendancy_list_decides_membership(shipped):
    rules = shipped.profile.character_rules
    mine = rules.class_ascendancies["poe2/classes/8"][0]
    someone_elses = rules.class_ascendancies["poe2/classes/1"][0]
    ok = _shipped_build(shipped, ascendancy_id=mine)
    assert LegalityValidator(catalog=shipped.catalog).validate(
        ok, shipped.profile).decision("ascendancy_membership") is Legality.LEGAL
    wrong = _shipped_build(shipped, ascendancy_id=someone_elses)
    report = LegalityValidator(catalog=shipped.catalog).validate(
        wrong, shipped.profile)
    assert "ascendancy_not_on_class" in report.violation_codes


# --------------------------------------------------------- caller mistakes ---

def test_a_catalog_the_profile_does_not_pin_is_refused(world, shipped):
    build = fixtures.make_build({"class_id": "poe2/classes/1", "level": 5},
                                catalog_hash=world.catalog.catalog_hash)
    with pytest.raises(ValueError, match="profile pins"):
        LegalityValidator(catalog=shipped.catalog).validate(build, world.profile)


def test_a_build_resolved_against_another_catalog_is_refused(world):
    build = fixtures.make_build({"class_id": "poe2/classes/1", "level": 5},
                                catalog_hash="deadbeef")
    with pytest.raises(ValueError, match="re-resolve"):
        LegalityValidator(catalog=world.catalog).validate(build, world.profile)


def test_an_imported_state_from_another_build_is_refused(cases, world, items):
    build = _build(cases, world, {"build": {}})
    imported = fixtures.make_imported({"class_id": 1, "level": 4},
                                      build_hash="build/somebody-else")
    with pytest.raises(ValueError, match="belongs to build"):
        LegalityValidator(catalog=world.catalog, imported=imported).validate(
            build, world.profile)


def test_without_a_catalog_nothing_is_resolved_and_the_checks_say_so(cases, world):
    build = _build(cases, world, {"build": {}})
    report = LegalityValidator().validate(build, world.profile)
    assert report.legality is Legality.UNKNOWN
    assert "no_passive_tree" in report.unknown_codes
    assert any(gap.gap_id.endswith("catalog-not-supplied")
               for gap in report.gaps)
    assert CatalogIndex().empty


# ------------------------------------------------------------- constraints ---

def test_the_report_carries_the_derived_constraints(cases, world, items):
    case = {"build": {"level": 10,
                      "weapon_sets": [{"set_id": "poe2/weapon_sets/1",
                                       "hands": {"main": "Weapon 1"},
                                       "passives": [8001, 8002]}]},
            "measured": {"pools": {"spirit": {"total": 100, "reserved": 25,
                                              "unreserved": 75}}}}
    build = _build(cases, world, case)
    report = _validator(world, items, case).validate(build, world.profile)
    names = {c.name: c for c in report.constraints}
    assert names["character_level"].used == 10
    assert names["passive_points"].used == 3
    assert names["ascendancy_points"].used == 0
    assert names["weapon_set_points"].used == 2
    assert names["weapon_set_points"].allowed == 24
    assert names["weapon_set_points"].decision is Legality.UNKNOWN
    assert names["spirit_reservation"].used == 25
    assert names["spirit_reservation"].allowed == 100
    assert names["spirit_reservation"].decision is Legality.LEGAL


def test_an_absent_rule_is_not_an_unlimited_one(cases, world, items):
    case = {"build": {"level": 10, "ascendancy_allocated": [1101],
                      "ascendancy_id": "poe2/ascendancies/1/1"}}
    build = _build(cases, world, case)
    report = _validator(world, items, case).validate(build, world.profile)
    constraint = next(c for c in report.constraints
                      if c.name == "ascendancy_points")
    assert constraint.decision is Legality.UNKNOWN
    assert report.decision(CHECK_ASCENDANCY_BUDGET) is Legality.UNKNOWN
