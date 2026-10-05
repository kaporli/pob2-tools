"""Records, schemas and validate_record (P01-T01).

Every record kind in contracts.md has one valid example and at least two
invalid ones in ``tests/fixtures/records``. This module runs all of them and
checks that each failure names the right code and the right field path: an
error that does not say which field is wrong is not usable by a parser, a
reviewer or the person who has to fix the source file.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

import pytest

from record_fixtures import (
    apply_patch,
    closed_index,
    load_cases,
    load_files,
    valid_payloads,
)

from pob2opt.domain import (
    ABSENT,
    RECORD_TYPES,
    RecordIndex,
    available_kinds,
    from_jsonable,
    to_jsonable,
    validate_record,
)
from pob2opt.domain.absent import Absent
from pob2opt.domain.codec import CodecError
from pob2opt.domain.records import SUPPORTED_SCHEMA_VERSIONS
from pob2opt.domain.schemas import UnknownSchemaVersion, check_schema_version

CASES = load_cases()

@pytest.fixture(scope="module")
def index() -> RecordIndex:
    """A corpus in which every fixture reference resolves.

    Nothing is whitelisted into it: it is built from the fixture records
    themselves, so a reference that does not resolve is a real hole in the
    graph rather than a missing entry in a test-local allow list.
    """
    return closed_index()


# ----------------------------------------------------- coverage of the set

def test_every_contract_record_has_a_schema_and_a_class():
    assert set(available_kinds()) == set(RECORD_TYPES)


def test_every_record_kind_has_fixture_examples():
    assert set(CASES) == set(RECORD_TYPES)


@pytest.mark.parametrize("kind", sorted(CASES))
def test_each_kind_has_one_valid_and_two_invalid_examples(kind: str):
    entry = CASES[kind]
    assert isinstance(entry["valid"], dict)
    assert len(entry["invalid"]) >= 2, "%s needs at least two invalid examples" % kind
    names = [case["name"] for case in entry["invalid"]]
    assert len(set(names)) == len(names)


def test_fixture_files_declare_themselves_synthetic():
    for name, doc in load_files().items():
        assert doc["kind"] == "synthetic", name
        assert "invented" in doc["not_a_claim"], name


# ------------------------------------------------------------- valid cases

@pytest.mark.parametrize("kind", sorted(CASES))
def test_valid_example_passes_every_pass(kind: str, index: RecordIndex):
    report = validate_record(CASES[kind]["valid"], kind=kind, index=index)
    assert report.ok, report.errors
    assert report.record is not None


@pytest.mark.parametrize("kind", sorted(CASES))
def test_valid_example_round_trips_byte_stable(kind: str):
    payload = CASES[kind]["valid"]
    record = from_jsonable(RECORD_TYPES[kind], payload)
    assert to_jsonable(record) == payload
    again = from_jsonable(RECORD_TYPES[kind], to_jsonable(record))
    assert to_jsonable(again) == payload


@pytest.mark.parametrize(
    "kind,case",
    [(kind, case) for kind in sorted(CASES) for case in CASES[kind]["also_valid"]],
    ids=lambda v: v["name"] if isinstance(v, dict) else str(v),
)
def test_alternative_valid_examples_are_accepted(kind, case, index: RecordIndex):
    payload = apply_patch(CASES[kind]["valid"], case["patch"])
    report = validate_record(payload, kind=kind, index=index)
    assert report.ok, (case["name"], report.errors)


# ----------------------------------------------------------- invalid cases

@pytest.mark.parametrize(
    "kind,case",
    [(kind, case) for kind in sorted(CASES) for case in CASES[kind]["invalid"]],
    ids=lambda v: v["name"] if isinstance(v, dict) else str(v),
)
def test_invalid_example_is_rejected_with_a_field_path(kind, case, index):
    payload = apply_patch(CASES[kind]["valid"], case["patch"])
    report = validate_record(payload, kind=kind, index=index)
    assert not report.ok, "%s: %s was accepted" % (kind, case["name"])
    assert case["expect_code"] in report.codes(), \
        "%s: expected %s, got %s" % (case["name"], case["expect_code"],
                                     report.errors)
    matching = [e for e in report.errors if e.code == case["expect_code"]]
    assert any(e.field_path == case["expect_path"] for e in matching), \
        "%s: expected path %s, got %s" % (case["name"], case["expect_path"],
                                          [e.field_path for e in matching])
    for error in report.errors:
        assert error.field_path.startswith("/")
        assert error.message


# --------------------------------------------- the four kinds of "no value"

def test_absent_is_not_none_not_false_and_not_zero():
    assert ABSENT is not None
    assert ABSENT is not False
    assert ABSENT != 0
    with pytest.raises(TypeError, match="no truth value"):
        bool(ABSENT)


def test_absent_fields_are_omitted_while_null_fields_are_written():
    """A nullable field says "unknown"; an absent one says "not applicable"."""
    payload = CASES["rotation_policy"]["valid"]
    policy = from_jsonable(RECORD_TYPES["rotation_policy"], payload)
    comparison = policy.rules[0].predicate.operands[0]
    combining = policy.rules[0].predicate

    assert comparison.operands is ABSENT
    assert combining.path is ABSENT
    rendered = to_jsonable(policy)["rules"][0]["predicate"]
    assert "path" not in rendered and "value" not in rendered
    assert "operands" not in rendered["operands"][0]
    # The nullable sibling is written, with null, in the same record.
    assert rendered["operands"][0]["value"] == 10
    assert to_jsonable(policy)["rules"][0]["weapon_set_id"] == "fixture-set-1"


def test_zero_and_false_survive_a_round_trip_as_themselves():
    payload = apply_patch(CASES["item_instance"]["valid"], {
        "/item_level": 0,
        "/flags/corrupted": False,
        "/requirements/fixture_attribute": 0,
    })
    item = from_jsonable(RECORD_TYPES["item_instance"], payload)
    assert item.item_level == 0 and item.item_level is not None
    assert item.flags["corrupted"] is False
    assert to_jsonable(item)["item_level"] == 0


def test_absent_singleton_survives_copy_and_pickle():
    import copy
    import pickle

    assert copy.deepcopy(ABSENT) is ABSENT
    assert pickle.loads(pickle.dumps(ABSENT)) is ABSENT
    assert Absent() is ABSENT


# ------------------------------------------------------------ schema version

@pytest.mark.parametrize("kind", sorted(CASES))
def test_unknown_schema_version_names_the_supported_versions(kind: str):
    payload = apply_patch(CASES[kind]["valid"], {"/schema_version": 99})
    report = validate_record(payload, kind=kind)
    assert report.codes() == ("unsupported_schema_version",)
    message = report.errors[0].message
    assert "99" in message
    for supported in SUPPORTED_SCHEMA_VERSIONS:
        assert str(supported) in message


def test_check_schema_version_rejects_true_as_a_version():
    """``True == 1`` in Python; a boolean is still not a schema version."""
    with pytest.raises(UnknownSchemaVersion):
        check_schema_version(True)
    assert check_schema_version(1) == 1


# ------------------------------------------------------------------ NaN

def test_nan_and_infinity_are_rejected_wherever_they_hide():
    for marker, label in (("__nan__", "NaN"), ("__inf__", "Infinity")):
        payload = apply_patch(CASES["evaluation_result"]["valid"],
                              {"/metrics/damage_dealt": marker})
        report = validate_record(payload, kind="evaluation_result")
        assert "not_a_number" in report.codes(), (label, report.errors)
        assert report.errors[0].field_path == "/metrics/damage_dealt"


def test_nan_cannot_be_serialized_even_if_it_reaches_a_record():
    record = from_jsonable(RECORD_TYPES["item_instance"],
                           CASES["item_instance"]["valid"])
    record.properties["fixture_damage"] = math.nan
    with pytest.raises(CodecError, match="NaN"):
        to_jsonable(record)


# --------------------------------------------------------- shape violations

def test_unknown_fields_are_rejected_rather_than_dropped():
    payload = dict(CASES["listing"]["valid"], fixture_extra_field="kept?")
    report = validate_record(payload, kind="listing")
    assert "schema_violation" in report.codes()
    assert any("fixture_extra_field" in e.message for e in report.errors)


def test_a_missing_required_field_names_itself():
    payload = apply_patch(CASES["listing"]["valid"],
                          {"/price_currency": "__remove__"})
    report = validate_record(payload, kind="listing")
    assert "schema_violation" in report.codes()
    assert any("price_currency" in e.message for e in report.errors)


def test_validating_a_dict_without_a_kind_is_a_programming_error():
    with pytest.raises(TypeError, match="kind is required"):
        validate_record(CASES["listing"]["valid"])
    with pytest.raises(LookupError):
        validate_record({}, kind="not_a_record")


# ------------------------------------------------- cross-record references

def test_unresolved_reference_is_reported_against_an_empty_corpus():
    report = validate_record(CASES["listing"]["valid"], kind="listing",
                             index=RecordIndex().add_blob("0" * 64))
    assert "unresolved_reference" in report.codes()
    assert "/item_hash" in report.paths()


def test_references_are_not_checked_when_no_corpus_is_supplied():
    report = validate_record(CASES["listing"]["valid"], kind="listing")
    assert report.ok, report.errors


def test_one_owner_calculates_each_effect():
    from dataclasses import replace

    from pob2opt.domain.enums import RuleOwner
    from pob2opt.domain.validation import validate_rule_registry

    rule = from_jsonable(RECORD_TYPES["mechanic_rule"],
                         CASES["mechanic_rule"]["valid"])
    other = replace(rule, record_id="fixture-rule-2", owner=RuleOwner.POB)
    assert validate_rule_registry([rule]) == ()
    errors = validate_rule_registry([rule, other])
    assert [e.code for e in errors] == ["ambiguous_mechanic_owner"]
    assert "pob" in errors[0].message and "simulator" in errors[0].message


# ------------------------------------------------------------- the request

def test_request_example_in_the_specification_still_validates(repo_root: Path):
    """docs/specs/examples/request.offline.json is the shipped RunRequest."""
    payload = json.loads(
        (repo_root / "docs/specs/examples/request.offline.json")
        .read_text(encoding="utf-8"))
    report = validate_record(payload, kind="run_request")
    # ``workers: auto`` and ``patch_selection: current`` are legal in a
    # request; only the manifest has to have resolved them.
    assert report.ok, report.errors
    assert report.record.workers == "auto"
    assert report.record.budget is None
