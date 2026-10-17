"""Validated records, canonical hashing, statuses and units (P01).

This layer is pure data. Per architecture.md it makes no network call, starts
no Lua state and ranks nothing. Everything above it exchanges these records
instead of loosely interpreted dictionaries.

Read in this order:

* ``absent`` - why ``None``, ``ABSENT``, ``0`` and ``False`` are four things.
* ``enums`` - the closed status vocabularies.
* ``records`` - the contracts.md dataclasses.
* ``schemas`` / ``schema_gen`` - the generated JSON Schemas in ``schemas/v1``.
* ``validation`` - ``validate_record``: version, schema, shape, semantics.
* ``identity`` - canonical JSON and the hash projections.
* ``cache`` - evaluation and aggregate cache identity.
* ``objectives`` - the registered search objectives (D07).
"""

from __future__ import annotations

from .absent import ABSENT, Absent, is_present
from .cache import (
    DEPENDENCY_FIELDS,
    AggregateComponent,
    AggregateKey,
    CacheDecision,
    EvaluationKey,
    decide,
)
from .codec import CodecError, from_jsonable, to_jsonable
from .identity import (
    baseline_suite_hash,
    build_hash,
    build_identity,
    canonical_json,
    canonical_text,
    content_hash,
    document_hash,
    item_hash,
    item_identity,
    listing_snapshot_hash,
    manifest_hash,
    objective_hash,
    objective_identity,
    rotation_hash,
    rotation_identity,
    scenario_hash,
    scenario_identity,
)
from .records import (
    RECORD_KINDS,
    RECORD_TYPES,
    SCHEMA_VERSION,
    SUPPORTED_SCHEMA_VERSIONS,
    kind_of,
)
from .schemas import (
    UnknownRecordKind,
    UnknownSchemaVersion,
    available_kinds,
    check_schema_version,
    schema_for,
    validator_for,
)
from .validation import (
    ANY_RECORD,
    NAMESPACES,
    RecordIndex,
    RecordInvalid,
    ValidationError,
    ValidationReport,
    validate_record,
    validate_records,
    validate_rule_registry,
)

__all__ = [
    "ABSENT", "Absent", "AggregateComponent", "AggregateKey",
    "CacheDecision", "CodecError",
    "DEPENDENCY_FIELDS", "EvaluationKey", "RECORD_KINDS", "RECORD_TYPES",
    "ANY_RECORD", "NAMESPACES", "RecordIndex", "RecordInvalid",
    "SCHEMA_VERSION",
    "SUPPORTED_SCHEMA_VERSIONS", "UnknownRecordKind", "UnknownSchemaVersion",
    "ValidationError", "ValidationReport", "available_kinds",
    "baseline_suite_hash", "build_hash", "build_identity", "canonical_json",
    "canonical_text", "check_schema_version", "content_hash", "decide",
    "document_hash", "from_jsonable", "is_present", "item_hash",
    "item_identity", "kind_of", "listing_snapshot_hash", "manifest_hash",
    "objective_hash", "objective_identity",
    "rotation_hash", "rotation_identity", "scenario_hash", "scenario_identity",
    "schema_for", "to_jsonable", "validate_record", "validate_records",
    "validate_rule_registry", "validator_for",
]
