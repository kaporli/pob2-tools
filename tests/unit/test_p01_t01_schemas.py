"""The committed JSON Schemas match the record dataclasses (P01-T01).

``schemas/v1`` is generated from ``pob2opt/domain/records.py``. If the two can
drift, a record field can be added, persisted and then silently fail to
validate somewhere else. This module is the lock: it regenerates in memory and
compares, so adding a field without regenerating fails here, by name.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from pob2opt.domain import RECORD_TYPES, available_kinds
from pob2opt.domain.schema_gen import SCHEMA_BASE, build_all, build_schema
from pob2opt.domain.schemas import SCHEMA_DIR, registry, schema_for, validator_for


def test_committed_schemas_are_regenerated_from_the_records():
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
    from generate_schemas import main

    assert main(["--check"]) == 0, (
        "schemas/v1 is stale; run python scripts/generate_schemas.py")


def test_there_is_exactly_one_schema_file_per_record_kind():
    on_disk = {p.stem for p in SCHEMA_DIR.glob("*.json")}
    assert on_disk == set(RECORD_TYPES)
    assert set(available_kinds()) == on_disk


@pytest.mark.parametrize("kind", sorted(RECORD_TYPES))
def test_each_schema_is_a_valid_2020_12_document(kind: str):
    validator_for(kind)  # calls check_schema


@pytest.mark.parametrize("kind", sorted(RECORD_TYPES))
def test_every_field_is_required_unless_it_may_be_absent(kind: str):
    schema = schema_for(kind)
    optional = set(schema["properties"]) - set(schema["required"])
    # Only the Predicate members are optional in v1, and they live in $defs.
    assert optional == set(), "%s has unexpected optional fields %s" % (
        kind, sorted(optional))
    assert schema["additionalProperties"] is False


def test_identifiers_never_resolve_to_a_real_host():
    """``$id`` uses a reserved TLD so validation cannot reach the network."""
    assert SCHEMA_BASE.startswith("https://pob2-tools.invalid/")
    for kind in RECORD_TYPES:
        assert schema_for(kind)["$id"].startswith(SCHEMA_BASE)


def test_cross_file_references_resolve_from_the_local_registry():
    manifest = schema_for("run_manifest")
    assert manifest["properties"]["resolved_request"] == {
        "$ref": "run_request.json"}
    resolved = registry().resolver().lookup("run_request.json")
    assert resolved.contents["title"] == "RunRequest"


def test_no_annotation_is_left_as_an_unresolved_string():
    """A quoted self-reference inside ``list[...]`` stays a bare string on
    Python 3.10, where ``get_type_hints`` does not descend into it. The
    schema generator then fails with a ``KeyError`` naming the class, which
    is a confusing way to learn that 3.10 is still supported."""
    import dataclasses
    from typing import get_args

    from pob2opt.domain.codec import hints_for

    def walk(annotation, where: str, seen: set[type]):
        assert not isinstance(annotation, str), \
            "%s is an unresolved forward reference %r" % (where, annotation)
        for arg in get_args(annotation):
            walk(arg, where, seen)
        if dataclasses.is_dataclass(annotation) and annotation not in seen:
            seen.add(annotation)
            for name, nested in hints_for(annotation).items():
                walk(nested, "%s.%s" % (annotation.__name__, name), seen)

    seen: set[type] = set()
    for kind, cls in sorted(RECORD_TYPES.items()):
        for name, annotation in hints_for(cls).items():
            walk(annotation, "%s.%s" % (kind, name), seen)


def test_schema_files_are_stable_across_regeneration():
    first = build_all()
    second = build_all()
    assert json.dumps(first, sort_keys=True) == json.dumps(second, sort_keys=True)


def test_a_new_field_changes_the_schema():
    """Adding a field must be a schema change, not a silent extension."""
    from dataclasses import make_dataclass

    from pob2opt.domain import records

    before = build_schema("listing")
    extended = make_dataclass("Listing", [("fixture_new_field", str)],
                              bases=(records.Listing,), frozen=True)
    original = records.RECORD_TYPES["listing"]
    records.RECORD_TYPES["listing"] = extended
    try:
        after = build_schema("listing")
    finally:
        records.RECORD_TYPES["listing"] = original
    assert "fixture_new_field" in after["properties"]
    assert "fixture_new_field" not in before["properties"]
    assert after != before
