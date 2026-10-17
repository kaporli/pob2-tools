"""Build the ``schemas/v1`` JSON Schemas from the record dataclasses (P01-T01).

The schemas are generated, not hand-maintained, because a hand-written schema
drifts from its dataclass silently and the first symptom is an imported
modifier that validates and then does not exist. ``scripts/generate_schemas.py``
writes the files; ``tests/unit/test_p01_t01_schemas.py`` regenerates them in
memory and fails if the committed files differ. Adding a record field is
therefore automatically a schema change, as contracts.md requires.

Structure comes from the annotations. Everything a Python annotation cannot
say is declared here instead:

* ``SHA256_FIELDS`` and the ``_at`` suffix pin content identities and UTC
  timestamps to patterns.
* ``_s`` / ``_ms`` suffixes and ``NON_NEGATIVE`` forbid negative durations and
  counts.
* ``OVERRIDES`` holds the per-field remainder, keyed by (class, field).

Two things JSON Schema cannot express and the semantic pass owns instead:
NaN/Infinity (a Python ``float('nan')`` satisfies ``{"type": "number"}``) and
every cross-record reference. See ``validation.py``.
"""

from __future__ import annotations

import dataclasses
import types
import typing
from enum import Enum
from typing import Any, Union, get_args, get_origin

from .absent import Absent
from .codec import hints_for, json_key
from .records import (KIND_SCHEMA_VERSIONS, RECORD_KINDS, RECORD_TYPES,
                      SUPPORTED_SCHEMA_VERSIONS)

SCHEMA_DIALECT = "https://json-schema.org/draft/2020-12/schema"
SCHEMA_BASE = "https://pob2-tools.invalid/schemas/v1/"

#: SHA-256 content identity, lower-case hex.
SHA256 = {"type": "string", "pattern": "^[0-9a-f]{64}$"}
#: RFC 3339 in UTC with a literal ``Z``, as contracts.md requires.
RFC3339_UTC = {
    "type": "string",
    "pattern": r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?Z$",
}
#: Decimal string in the original currency; never a float.
DECIMAL_STRING = {"type": "string", "pattern": r"^-?\d+(\.\d+)?$"}
NON_EMPTY_STRING = {"type": "string", "minLength": 1}

#: Field names holding one SHA-256, or a list of them.
SHA256_FIELDS = frozenset({
    "blob_hash", "build_hash", "cache_key", "calibration_hash", "catalog_hash",
    "item_hash", "manifest_hash", "objective_hash", "baseline_suite_hash",
    "mechanics_registry_hash", "patch_profile_hash", "pob_dirty_hash",
    "rotation_hash", "software_dirty_hash", "source_item_hash",
    "trace_blob_hash", "raw_blob_hashes", "candidate_archive_hashes",
    "benchmark_scenario_hash", "attribution_rules_hash",
})

#: Numeric fields that may not be negative but are not covered by a suffix.
NON_NEGATIVE = frozenset({
    "ascendancy_point_budget", "ascendancy_points", "byte_count", "count",
    "completed_generation", "duration_ms", "gem_level_limit", "group",
    "item_level", "level", "main_skill_index", "max_supports", "memory_limit_mb",
    "missing", "next_generation_id", "normal_point_budget", "passive_points",
    "present", "quality", "resolved", "rule_index", "seed", "rng_seed",
    "skill_level_limit", "source_position", "weapon_switches",
})

#: Numeric fields that must be at least one.
AT_LEAST_ONE = frozenset({"quantity", "worker_limit"})

#: Top-level fields introduced by a later schema version of one record kind.
VERSION_FIELDS: dict[str, dict[int, tuple[str, ...]]] = {
    "aggregate_result": {2: ("objective_version", "objective_hash",
                             "objective_metrics", "objective_score",
                             "objective_gap_ids")},
    "build_spec": {2: ("main_skill_group",)},
    "run_request": {2: ("class_scope", "objective")},
}

#: Top-level fields a later schema version of one record kind retires:
#: required before that version, forbidden from it on.
RETIRED_FIELDS: dict[str, dict[int, tuple[str, ...]]] = {
    "run_request": {2: ("class",)},
}

#: Per-field keywords that no naming rule should be stretched to cover.
OVERRIDES: dict[tuple[str, str], dict[str, Any]] = {
    ("SourceDocument", "provider"): NON_EMPTY_STRING,
    ("SourceDocument", "media_type"): NON_EMPTY_STRING,
    ("PatchProfile", "game"): {"const": "poe2"},
    ("PatchProfile", "pob_commit"): NON_EMPTY_STRING,
    ("GameCatalog", "entities"): {"propertyNames": {"type": "string"}},
    ("Listing", "price_amount"): DECIMAL_STRING,
    ("Listing", "price_currency"): NON_EMPTY_STRING,
    ("ItemInstance", "rarity"): NON_EMPTY_STRING,
    ("BuildSpec", "class_id"): NON_EMPTY_STRING,
    ("DataGap", "needed_evidence"): {"type": "string", "minLength": 40},
    ("DataGap", "collection_method"): NON_EMPTY_STRING,
    ("MechanicClaim", "claim_text"): {"type": "string", "minLength": 1,
                                      "maxLength": 1000},
    ("MechanicClaim", "source_locator"): NON_EMPTY_STRING,
    ("ScenarioSpec", "capability_floor_ratio"): {"type": "number",
                                                 "exclusiveMinimum": 0},
    ("Position", "unit"): NON_EMPTY_STRING,
    ("Gate", "comparison"): {"enum": ["eq", "ne", "lt", "lte", "gt", "gte"]},
    ("LevelRange", "minimum"): {"type": "integer", "minimum": 1},
    ("LevelRange", "maximum"): {"type": "integer", "minimum": 1},
    ("RunRequest", "schema_version"): {"enum": list(SUPPORTED_SCHEMA_VERSIONS)},
    ("RunRequest", "game"): {"const": "poe2"},
    ("RunRequest", "budget"): DECIMAL_STRING,
    ("RunRequest", "workers"): {
        "anyOf": [{"type": "integer", "minimum": 1}, {"const": "auto"}],
    },
    ("RunRequest", "level"): {"type": "integer", "minimum": 1},
    ("ClassScope", "class_id"): NON_EMPTY_STRING,
    ("ObjectiveSelection", "objective_id"): NON_EMPTY_STRING,
    ("ObjectiveSelection", "objective_version"): {"type": "integer",
                                                  "minimum": 1},
    ("AggregateResult", "objective_version"): {"type": "integer",
                                               "minimum": 1},
    ("RecordBase", "schema_version"): {"enum": list(SUPPORTED_SCHEMA_VERSIONS)},
    ("RecordBase", "record_id"): NON_EMPTY_STRING,
    ("Checkpoint", "schema_version"): {"enum": list(SUPPORTED_SCHEMA_VERSIONS)},
}


def _split_union(ann: Any) -> tuple[bool, bool, list[Any]]:
    origin = get_origin(ann)
    if origin is not Union and origin is not types.UnionType:
        return False, False, [ann]
    allows_none = allows_absent = False
    rest: list[Any] = []
    for member in get_args(ann):
        if member is type(None):
            allows_none = True
        elif member is Absent:
            allows_absent = True
        else:
            rest.append(member)
    return allows_none, allows_absent, rest


def _nullable(schema: dict[str, Any]) -> dict[str, Any]:
    """Allow null without burying a simple type in an ``anyOf``.

    ``enum`` and ``const`` constrain the value itself, so widening ``type``
    alone would still exclude null; both have to list it.
    """
    if not schema:
        return {}
    merged = dict(schema)
    if "const" in merged:
        merged["enum"] = [merged.pop("const"), None]
    elif "enum" in merged:
        merged["enum"] = list(merged["enum"]) + [None]
    if isinstance(merged.get("type"), str):
        merged["type"] = [merged["type"], "null"]
        return merged
    if "enum" in merged and "type" not in merged:
        return merged
    return {"anyOf": [schema, {"type": "null"}]}


class _Builder:
    def __init__(self, root: type) -> None:
        self.root = root
        self.defs: dict[str, Any] = {}

    def schema_for(self, ann: Any, owner: str, name: str) -> dict[str, Any]:
        allows_none, _absent, members = _split_union(ann)
        if len(members) == 1:
            base = self._member(members[0], owner, name)
        else:
            base = {"anyOf": [self._member(m, owner, name) for m in members]}
        override = OVERRIDES.get((owner, name))
        if override is not None:
            # Merged, not substituted: an override adds the keyword the
            # annotation could not express and leaves the generated structure
            # (object/array/$ref) in place.
            base = {**base, **override}
        else:
            base = self._apply_name_rules(base, name)
        return _nullable(base) if allows_none else base

    def _apply_name_rules(self, base: dict[str, Any], name: str) -> dict[str, Any]:
        if base.get("type") == "array" and name in SHA256_FIELDS:
            return {"type": "array", "items": dict(SHA256)}
        if name in SHA256_FIELDS:
            return dict(SHA256)
        if name.endswith("_at"):
            return dict(RFC3339_UTC)
        if base.get("type") in ("number", "integer"):
            if name.endswith("_s") or name.endswith("_ms") or name in NON_NEGATIVE:
                return dict(base, minimum=0)
            if name in AT_LEAST_ONE:
                return dict(base, minimum=1)
        return base

    def _member(self, target: Any, owner: str, name: str) -> dict[str, Any]:
        if target is Any:
            return {}
        origin = get_origin(target)
        if isinstance(target, type) and issubclass(target, Enum):
            return {"type": "string", "enum": [m.value for m in target]}
        if origin in (list, typing.List):
            (item_ann,) = get_args(target) or (Any,)
            return {"type": "array", "items": self.schema_for(item_ann, owner, name)}
        if origin in (dict, typing.Dict):
            args = get_args(target)
            value_ann = args[1] if len(args) == 2 else Any
            return {
                "type": "object",
                "additionalProperties": self.schema_for(value_ann, owner, name),
            }
        if dataclasses.is_dataclass(target):
            return self._reference(target)
        return {"type": {str: "string", int: "integer", float: "number",
                         bool: "boolean"}[target]}

    def _reference(self, target: type) -> dict[str, Any]:
        kind = RECORD_KINDS.get(target)
        if kind is not None and target is not self.root:
            return {"$ref": "%s.json" % kind}
        name = target.__name__
        if name not in self.defs:
            self.defs[name] = {}  # placeholder, so recursion terminates
            self.defs[name] = self.object_schema(target)
        return {"$ref": "#/$defs/%s" % name}

    def object_schema(self, cls: type) -> dict[str, Any]:
        hints = hints_for(cls)
        properties: dict[str, Any] = {}
        required: list[str] = []
        for fld in dataclasses.fields(cls):
            key = json_key(fld)
            owner = _declaring_class(cls, fld.name)
            properties[key] = self.schema_for(hints[fld.name], owner, fld.name)
            _, allows_absent, _ = _split_union(hints[fld.name])
            if not allows_absent:
                required.append(key)
        schema: dict[str, Any] = {
            "type": "object",
            "properties": properties,
            "required": required,
            "additionalProperties": False,
        }
        # ``dataclass`` synthesizes a signature-shaped docstring when the class
        # has none. Repeating it in the schema adds noise, not meaning.
        doc = (cls.__doc__ or "").strip()
        if doc and not doc.startswith(cls.__name__ + "("):
            schema["description"] = doc.splitlines()[0]
        return schema


def _declaring_class(cls: type, field_name: str) -> str:
    """Name of the class a field was declared on, for ``OVERRIDES`` lookup."""
    for base in cls.__mro__:
        if field_name in getattr(base, "__annotations__", {}):
            return base.__name__
    return cls.__name__


def build_schema(kind: str) -> dict[str, Any]:
    """The complete JSON Schema document for one record kind."""
    cls = RECORD_TYPES[kind]
    builder = _Builder(cls)
    body = builder.object_schema(cls)
    schema = {
        "$schema": SCHEMA_DIALECT,
        "$id": SCHEMA_BASE + kind + ".json",
        "title": cls.__name__,
    }
    schema.update(body)
    if kind in KIND_SCHEMA_VERSIONS:
        schema["properties"]["schema_version"] = {
            "enum": list(KIND_SCHEMA_VERSIONS[kind])}
    added = VERSION_FIELDS.get(kind, {})
    retired = RETIRED_FIELDS.get(kind, {})
    for version in sorted(set(added) | set(retired)):
        # Added fields are required from ``version`` on and forbidden before
        # it; retired fields the reverse. Nested fields such as
        # SkillEntry.supports are checked by the semantic pass.
        names, gone = added.get(version, ()), retired.get(version, ())
        then: dict[str, Any] = {"required": list(names)}
        otherwise: dict[str, Any] = {"properties": {n: False for n in names}}
        if gone:
            then["properties"] = {n: False for n in gone}
            otherwise["required"] = list(gone)
        schema.setdefault("allOf", []).append({
            "if": {"properties": {"schema_version": {"exclusiveMinimum":
                                                     version - 1}}},
            "then": then,
            "else": otherwise,
        })
    if builder.defs:
        schema["$defs"] = dict(sorted(builder.defs.items()))
    return schema


def build_all() -> dict[str, dict[str, Any]]:
    """Every record kind's schema, keyed by its file stem."""
    return {kind: build_schema(kind) for kind in sorted(RECORD_TYPES)}
