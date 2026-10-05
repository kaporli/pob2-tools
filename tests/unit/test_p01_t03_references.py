"""Cross-record reference closure (review finding P01-R03).

The review found three separate holes: the reference inventory covered only
some fields, an empty index silently disabled checking, and a bundle called
itself readable without its dependency graph. This module covers the first
two; `test_p01_t04_cache.py` covers the bundle.

The completeness test is the important one. It walks every identifier-shaped
field on every record and fails unless the field is either resolved by
`_references` or listed in `UNCHECKED_REFERENCE_FIELDS` with a reason, so a
field added later cannot quietly go unchecked.
"""

from __future__ import annotations

import dataclasses
from dataclasses import replace

import pytest

from record_fixtures import all_records, closed_index, records

from pob2opt.domain import RECORD_TYPES, RecordIndex, kind_of, validate_record
from pob2opt.domain.codec import hints_for
from pob2opt.domain.validation import (
    ANY_RECORD,
    NAMESPACES,
    UNCHECKED_REFERENCE_FIELDS,
    _references,
    own_identity_fields,
)

R = records()

#: A field whose name ends like this is an identifier of something.
_IDENTIFIER_SUFFIXES = ("_id", "_ids", "_hash", "_hashes", "_references",
                        "_commit")
_IDENTIFIER_NAMES = ("dependencies", "provenance_ids")


def _identifier_fields(cls: type) -> set[str]:
    out = set()
    for field in dataclasses.fields(cls):
        if field.name in _IDENTIFIER_NAMES or \
                field.name.endswith(_IDENTIFIER_SUFFIXES):
            out.add(field.name)
    return out


def _probe(kind: str):
    """The fixture record with every top-level identifier field filled.

    `_references` yields nothing for an empty list, so measuring coverage
    against the fixture as-is would score an unchecked empty field as
    checked. Filling them first makes the walk visit every one.
    """
    record = R[kind]
    hints = hints_for(RECORD_TYPES[kind])
    changes = {}
    for name in _identifier_fields(RECORD_TYPES[kind]):
        annotation = str(hints[name])
        if name in own_identity_fields(kind):
            continue
        if annotation.startswith("list["):
            changes[name] = ["__probe__"]
        elif "str" in annotation and getattr(record, name, "") in (None, ""):
            changes[name] = "__probe__"
    return replace(record, **changes) if changes else record


def _checked_fields(kind: str, record) -> set[str]:
    """Top-level field names `_references` actually walks for this record."""
    return {path.lstrip("/").split("/")[0]
            for path, _value, _namespace in _references(kind, record)}


# -------------------------------------------------- the inventory is complete

@pytest.mark.parametrize("kind", sorted(RECORD_TYPES))
def test_every_identifier_field_is_classified(kind: str):
    declared = _identifier_fields(RECORD_TYPES[kind]) - own_identity_fields(kind)
    checked = _checked_fields(kind, _probe(kind))
    for name in sorted(declared - checked):
        assert (kind, name) in UNCHECKED_REFERENCE_FIELDS, (
            "%s.%s is neither resolved by _references nor listed in "
            "UNCHECKED_REFERENCE_FIELDS with a reason" % (kind, name))
        assert UNCHECKED_REFERENCE_FIELDS[(kind, name)].strip()


def test_the_unchecked_list_has_no_stale_entries():
    for (kind, name) in sorted(UNCHECKED_REFERENCE_FIELDS):
        assert kind in RECORD_TYPES, "%s is not a record kind" % kind
        fields = {f.name for f in dataclasses.fields(RECORD_TYPES[kind])}
        assert name in fields, "%s has no field %s" % (kind, name)


def test_a_records_own_identity_is_never_a_reference_out():
    """A record cannot be evidence that it exists."""
    for kind in RECORD_TYPES:
        own = own_identity_fields(kind)
        assert "record_id" in own
        walked = _checked_fields(kind, _probe(kind))
        assert not (own & walked), (kind, own & walked)


def test_every_namespace_a_reference_uses_exists():
    for kind in RECORD_TYPES:
        for path, _value, namespace in _references(kind, _probe(kind)):
            assert namespace in NAMESPACES or namespace == ANY_RECORD, \
                "%s %s uses unknown namespace %r" % (kind, path, namespace)


# ------------------------------------------- an empty index is an empty corpus

def test_no_index_means_references_are_not_checked():
    """Acquisition and parsing run before anything is placed in a corpus."""
    assert validate_record(R["build_spec"]).ok


def test_an_empty_index_resolves_nothing():
    """Review finding P01-R03: an empty index used to disable checking."""
    report = validate_record(R["build_spec"], index=RecordIndex())
    assert not report.ok
    paths = [e.field_path for e in report.errors
             if e.code == "unresolved_reference"]
    assert "/catalog_hash" in paths
    assert "/equipment/fixture-slot-weapon/item_hash" in paths
    assert "/raw_blob_hashes/0" in paths


def test_the_closed_fixture_graph_resolves_completely():
    index = closed_index()
    for record in all_records():
        report = validate_record(record, index=index)
        assert report.ok, (kind_of(record), report.errors)


# ------------------------------------- the fields the review found unchecked

@pytest.mark.parametrize("kind,field,value,path", [
    ("patch_profile", "patch_evidence_ids", ["missing-evidence"],
     "/patch_evidence_ids/0"),
    ("mechanic_rule", "dependency_ids", ["missing-mechanic"],
     "/dependency_ids/0"),
    ("run_manifest", "source_snapshot_ids", ["missing-snapshot"],
     "/source_snapshot_ids/0"),
])
def test_the_reviews_unchecked_fields_are_now_reported(kind, field, value, path):
    broken = replace(R[kind], **{field: value})
    report = validate_record(broken, index=closed_index())
    assert "unresolved_reference" in report.codes(), report.errors
    assert path in report.paths()


@pytest.mark.parametrize("kind,field,value,path", [
    ("patch_profile", "compatibility_evidence_ids", ["nope"],
     "/compatibility_evidence_ids/0"),
    ("mechanic_claim", "evidence_ids", ["nope"], "/evidence_ids/0"),
    ("observation", "raw_evidence_ids", ["nope"], "/raw_evidence_ids/0"),
    ("data_gap", "subject_ids", ["nope"], "/subject_ids/0"),
    ("parse_result", "record_ids", ["nope"], "/record_ids/0"),
    ("evaluation_result", "assumption_ids", ["nope"], "/assumption_ids/0"),
    ("run_manifest", "market_snapshot_ids", ["nope"],
     "/market_snapshot_ids/0"),
])
def test_the_rest_of_the_inventory_is_resolved_too(kind, field, value, path):
    broken = replace(R[kind], **{field: value})
    report = validate_record(broken, index=closed_index())
    assert path in report.paths(), report.errors


def test_nested_evidence_inside_character_rules_is_resolved():
    rules = R["patch_profile"].character_rules
    broken = replace(R["patch_profile"], character_rules=replace(
        rules, point_budgets=[replace(rules.point_budgets[0],
                                      evidence_ids=["nope"])]))
    report = validate_record(broken, index=closed_index())
    assert "/character_rules/point_budgets/0/evidence_ids/0" in report.paths()


def test_a_catalog_entity_rule_reference_is_resolved():
    catalog = R["game_catalog"]
    entity = catalog.entities["classes"][0]
    broken = replace(catalog, entities={"classes": [
        replace(entity, rule_references=["no-such-rule"])]})
    report = validate_record(broken, index=closed_index())
    assert "/entities/classes/0/rule_references/0" in report.paths()


# -------------------------------------------------- who vouches for what

def test_an_item_citing_a_catalog_does_not_prove_the_catalog_exists():
    index = RecordIndex.from_records([R["item_instance"], R["build_spec"]])
    assert not index.contains("catalog_hashes", R["item_instance"].catalog_hash)


def test_a_patch_profile_pins_a_catalog_but_does_not_provide_it():
    index = RecordIndex.from_records([R["patch_profile"]])
    assert not index.contains("catalog_hashes", R["patch_profile"].catalog_hash)
    with_catalog = RecordIndex.from_records([R["game_catalog"]])
    assert with_catalog.contains("catalog_hashes",
                                 R["game_catalog"].catalog_hash)


def test_a_source_document_naming_a_blob_does_not_prove_the_bytes_are_here():
    """Payload availability is separate from a record claiming its hash."""
    index = RecordIndex.from_records([R["source_document"]])
    assert not index.contains("blob_hashes", R["source_document"].blob_hash)
    index.add_blob(R["source_document"].blob_hash)
    assert index.contains("blob_hashes", R["source_document"].blob_hash)


def test_any_record_is_the_union_of_the_namespaces():
    index = closed_index()
    assert index.contains(ANY_RECORD, "fixture-source-1")
    assert index.contains(ANY_RECORD, R["build_spec"].build_hash)
    assert not index.contains(ANY_RECORD, "nothing-like-this")
