"""Two-pass record validation (P01-T01).

``validate_record`` runs the passes contracts.md requires, in order, and stops
at the first pass that fails so later errors are not noise from earlier ones:

1. **version** - an unsupported ``schema_version`` is rejected with a message
   naming the versions this build implements.
2. **schema** - the generated JSON Schema for the record kind.
3. **shape** - decoding into the dataclass, which rejects unknown fields and
   type confusions the schema cannot express.
4. **semantic** - rules about the record's own meaning (NaN, negative
   durations, duplicate allocations, a metric that is null without a gap) and
   cross-record references resolved against a :class:`RecordIndex`.

Every error carries ``field_path``, a JSON Pointer into the record, so a
failure names the field rather than the record.

Nothing here guesses. A reference that does not resolve is an error; it never
becomes a freshly invented record, and a missing number never becomes zero.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field as dc_field
from typing import Any, Iterable, Protocol, Sequence

from jsonschema.exceptions import best_match

from . import identity
from .absent import ABSENT
from .objectives import UnknownObjective, get_objective
from .codec import CodecError, NotANumber, from_jsonable, to_jsonable
from .enums import (
    AcquisitionStatus,
    CandidateAvailability,
    Compatibility,
    EnablingQueryStatus,
    Fidelity,
    PoolSlotStatus,
    ResultStatus,
    RunMode,
)
from .records import (
    CATALOG_TABLES,
    COMBINING_OPERATORS,
    DOMAIN_ID_FIELDS,
    RECORD_TYPES,
    PredicateOperator,
    TrialOutcome,
    kind_of,
)
from .schemas import UnknownSchemaVersion, check_schema_version, validator_for

#: Phrases that are not an evidence request. contracts.md: "Need more data" is
#: not acceptable; ``needed_evidence`` must name the measurement.
_VACUOUS_EVIDENCE = (
    "need more data", "more data", "more information", "more evidence",
    "unknown", "tbd", "todo", "investigate", "n/a", "unclear",
)


@dataclass(frozen=True, slots=True)
class ValidationError:
    code: str
    field_path: str
    message: str
    phase: str

    def __str__(self) -> str:
        return "%s %s: %s" % (self.field_path, self.code, self.message)


@dataclass(frozen=True, slots=True)
class ValidationReport:
    kind: str
    errors: tuple[ValidationError, ...] = ()
    #: The decoded record, when the shape pass got far enough to build one.
    record: Any = None

    @property
    def ok(self) -> bool:
        return not self.errors

    def codes(self) -> tuple[str, ...]:
        return tuple(e.code for e in self.errors)

    def paths(self) -> tuple[str, ...]:
        return tuple(e.field_path for e in self.errors)

    def raise_for_errors(self) -> Any:
        if self.errors:
            raise RecordInvalid(self)
        return self.record


class RecordInvalid(ValueError):
    def __init__(self, report: ValidationReport) -> None:
        self.report = report
        super().__init__(
            "%s failed validation:\n  %s"
            % (report.kind, "\n  ".join(str(e) for e in report.errors))
        )


# ----------------------------------------------------------- record index ===

#: Every namespace a reference can resolve into. ``ANY_RECORD`` is the union,
#: used where contracts.md allows a field to name more than one kind of thing.
NAMESPACES = (
    "record_ids", "blob_hashes", "catalog_hashes", "item_hashes",
    "build_hashes", "rotation_hashes", "manifest_hashes", "listing_ids",
    "source_document_ids", "patch_profile_ids", "scenario_ids",
    "rotation_ids", "evaluation_ids", "manifest_ids", "gap_ids",
    "mechanic_ids",
)
ANY_RECORD = "any_record"


# A record owns these identities; attributes on other kinds are citations.
PROVIDED_FIELDS = {
    "source_document": (("source_document_ids", "record_id"),),
    "patch_profile": (("patch_profile_ids", "record_id"),),
    "listing": (("listing_ids", "listing_id"),),
    "scenario_spec": (("scenario_ids", "scenario_id"),),
    "rotation_policy": (("rotation_ids", "rotation_id"),),
    "evaluation_result": (("evaluation_ids", "evaluation_id"),),
    "run_manifest": (("manifest_ids", "run_id"),),
    "data_gap": (("gap_ids", "gap_id"),),
    "mechanic_rule": (("mechanic_ids", "mechanic_id"),),
    "item_instance": (("item_hashes", "item_hash"),),
    "build_spec": (("build_hashes", "build_hash"),),
    "game_catalog": (("catalog_hashes", "catalog_hash"),),
}


def provided_identifiers(record: Any):
    """Typed identities supplied by a record, never its outgoing references.

    Shared by in-memory validation and snapshot traversal. Blob ownership
    requires actual bytes and must be supplied separately by the store.
    """
    kind = kind_of(record)
    for attribute in ("record_id", "evaluation_id", "gap_id",
                      "observation_id", "run_id"):
        value = getattr(record, attribute, None)
        if value is not None:
            yield "record_ids", value
            break
    for namespace, attribute in PROVIDED_FIELDS.get(kind, ()):
        yield namespace, getattr(record, attribute)
    if kind == "rotation_policy":
        yield "rotation_hashes", identity.rotation_hash(record)
    if kind == "run_manifest":
        yield "manifest_hashes", identity.manifest_hash(record)


class ReferenceIndex(Protocol):
    """What a reference is allowed to resolve to.

    Two implementations exist: :class:`RecordIndex` holds sets in memory, and
    ``pob2opt.storage.StoreIndex`` answers the same question with indexed SQL
    so a corpus does not have to be materialized to validate one record.
    """

    def contains(self, namespace: str, value: str) -> bool:
        ...  # pragma: no cover - protocol


@dataclass
class RecordIndex:
    """An in-memory corpus of known identifiers.

    Passing ``index=None`` to :func:`validate_record` skips reference checking
    entirely, which is what acquisition and parsing do before their output is
    accepted anywhere. Passing an index, **including an empty one**, means
    "resolve against this corpus": an empty corpus resolves nothing. Those are
    different statements and conflating them hid unresolved references
    (review finding P01-R03).
    """

    record_ids: set[str] = dc_field(default_factory=set)
    blob_hashes: set[str] = dc_field(default_factory=set)
    catalog_hashes: set[str] = dc_field(default_factory=set)
    item_hashes: set[str] = dc_field(default_factory=set)
    build_hashes: set[str] = dc_field(default_factory=set)
    rotation_hashes: set[str] = dc_field(default_factory=set)
    manifest_hashes: set[str] = dc_field(default_factory=set)
    listing_ids: set[str] = dc_field(default_factory=set)
    source_document_ids: set[str] = dc_field(default_factory=set)
    patch_profile_ids: set[str] = dc_field(default_factory=set)
    scenario_ids: set[str] = dc_field(default_factory=set)
    rotation_ids: set[str] = dc_field(default_factory=set)
    evaluation_ids: set[str] = dc_field(default_factory=set)
    manifest_ids: set[str] = dc_field(default_factory=set)
    gap_ids: set[str] = dc_field(default_factory=set)
    mechanic_ids: set[str] = dc_field(default_factory=set)

    def contains(self, namespace: str, value: str) -> bool:
        if namespace == ANY_RECORD:
            return any(value in getattr(self, name) for name in NAMESPACES)
        return value in getattr(self, namespace)

    def add(self, record: Any) -> "RecordIndex":
        for namespace, value in provided_identifiers(record):
            getattr(self, namespace).add(value)
        return self

    def add_blob(self, blob_hash: str) -> "RecordIndex":
        self.blob_hashes.add(blob_hash)
        return self

    @classmethod
    def from_records(cls, records: Iterable[Any],
                     blob_hashes: Iterable[str] = ()) -> "RecordIndex":
        index = cls()
        for record in records:
            index.add(record)
        for blob_hash in blob_hashes:
            index.add_blob(blob_hash)
        return index


# -------------------------------------------------------------- entry point ===

def validate_record(
    record: Any,
    *,
    kind: str | None = None,
    index: RecordIndex | None = None,
) -> ValidationReport:
    """Validate a record instance or its JSON form. Never raises on bad data."""
    if kind is None:
        if isinstance(record, dict):
            raise TypeError("kind is required when validating a plain dict")
        kind = kind_of(record)
    if kind not in RECORD_TYPES:
        raise LookupError("unknown record kind %r" % kind)

    if isinstance(record, dict):
        data = record
    else:
        try:
            data = to_jsonable(record)
        except CodecError as exc:
            return ValidationReport(kind, (_codec_error(exc),))

    # 1. version
    try:
        check_schema_version(data.get("schema_version"), kind)
    except UnknownSchemaVersion as exc:
        return ValidationReport(kind, (ValidationError(
            "unsupported_schema_version", "/schema_version", str(exc), "version"),))

    # 2. schema
    errors = tuple(sorted(
        (_schema_error(err) for err in validator_for(kind).iter_errors(data)),
        key=lambda e: e.field_path,
    ))
    if errors:
        return ValidationReport(kind, errors)

    # 3. shape. Always decoded, including when a dataclass was passed in: an
    # instance built by hand can hold a wire value where a typed one belongs
    # (``status="ok"`` instead of ``ResultStatus.OK``), and the semantic pass
    # would then fail with a bare AttributeError instead of a report
    # (review finding P01-R02). Semantics only ever see a decoded record, and
    # ``report.record`` is the canonical instance callers should persist.
    try:
        instance = from_jsonable(RECORD_TYPES[kind], data)
    except CodecError as exc:
        return ValidationReport(kind, (_codec_error(exc),))

    # 4. semantics
    semantic = tuple(_semantic_errors(kind, data, instance, index))
    return ValidationReport(kind, semantic, instance if not semantic else None)


def validate_records(
    records: Sequence[Any], *, index: RecordIndex | None = None
) -> dict[str, ValidationReport]:
    """Validate a batch against one index, keyed by ``record_id``."""
    if index is None:
        index = RecordIndex.from_records(records)
    return {getattr(r, "record_id", "#%d" % i): validate_record(r, index=index)
            for i, r in enumerate(records)}


def validate_rule_registry(rules: Sequence[Any]) -> tuple[ValidationError, ...]:
    """One owner calculates each effect (contracts.md MechanicRule).

    Two rules for the same ``mechanic_id`` claiming different owners is the
    shape double counting takes, so it is rejected at the registry level
    rather than inside either rule.
    """
    owners: dict[str, set[str]] = {}
    for rule in rules:
        owners.setdefault(rule.mechanic_id, set()).add(str(rule.owner.value))
    return tuple(
        ValidationError(
            "ambiguous_mechanic_owner", "/mechanic_id",
            "mechanic %r is claimed by %s; exactly one owner may calculate an "
            "effect" % (mechanic_id, ", ".join(sorted(found))), "semantic")
        for mechanic_id, found in sorted(owners.items()) if len(found) > 1
    )


# ------------------------------------------------------------- semantics ===

def _pointer(parts: Iterable[Any]) -> str:
    rendered = "/".join(str(p) for p in parts)
    return "/" + rendered if rendered else "/"


def _codec_error(exc: CodecError) -> ValidationError:
    if isinstance(exc, NotANumber):
        return ValidationError("not_a_number", exc.path, exc.message, "shape")
    return ValidationError("shape_violation", exc.path, exc.message, "shape")


def _schema_error(err: Any) -> ValidationError:
    """Report the deepest failing field, not the branch that contained it.

    A nullable nested record is ``anyOf: [$ref, null]``, and jsonschema
    reports such a failure against the whole branch. ``best_match`` descends
    into the sub-errors, so the path names the field a person has to fix.
    """
    leaf = best_match([err]) or err
    return ValidationError("schema_violation", _pointer(leaf.absolute_path),
                           leaf.message, "schema")


def _semantic_errors(kind, data, record, index):
    yield from _numeric_errors(data, "")
    yield from _provenance_errors(kind, record)
    yield from _identity_errors(kind, record)
    checker = _PER_KIND.get(kind)
    if checker is not None:
        yield from checker(record)
    # ``index is None`` means "do not check references"; an empty index means
    # "resolve against an empty corpus", which resolves nothing.
    if index is not None:
        yield from _reference_errors(kind, record, index)


def _numeric_errors(value, path):
    """NaN, Infinity and negative durations, including inside free-form maps.

    A ``float('nan')`` satisfies ``{"type": "number"}``, so the schema pass
    cannot catch it, and ``dict[str, Any]`` payloads are not covered by the
    generated minimums at all.
    """
    if isinstance(value, bool):
        return
    if isinstance(value, float):
        if math.isnan(value):
            yield ValidationError("not_a_number", path or "/",
                                  "NaN is not a value", "semantic")
        elif math.isinf(value):
            yield ValidationError("not_a_number", path or "/",
                                  "Infinity is not a value", "semantic")
        return
    if isinstance(value, dict):
        for key, item in value.items():
            child = "%s/%s" % (path, key)
            if isinstance(item, (int, float)) and not isinstance(item, bool):
                if (key.endswith("_s") or key.endswith("_ms")) and item < 0:
                    yield ValidationError(
                        "negative_duration", child,
                        "duration %r is negative" % (item,), "semantic")
            yield from _numeric_errors(item, child)
        return
    if isinstance(value, list):
        for i, item in enumerate(value):
            yield from _numeric_errors(item, "%s/%d" % (path, i))


def _provenance_errors(kind, record):
    if not hasattr(record, "provenance_ids"):
        return
    if not record.provenance_ids:
        yield ValidationError(
            "missing_provenance", "/provenance_ids",
            "a persisted %s must trace back to at least one source, "
            "acquisition or derivation record" % kind, "semantic")


def _identity_errors(kind, record):
    domain_field = DOMAIN_ID_FIELDS.get(kind)
    if domain_field is None:
        return
    domain_id = getattr(record, domain_field)
    if domain_id != record.record_id:
        yield ValidationError(
            "identity_mismatch", "/%s" % domain_field,
            "record_id %r and %s %r must be the same identity"
            % (record.record_id, domain_field, domain_id), "semantic")


def _duplicates(values):
    seen, dupes = set(), []
    for i, value in enumerate(values):
        if value in seen:
            dupes.append((i, value))
        seen.add(value)
    return dupes


# -- per kind ---------------------------------------------------------------

def _check_acquisition_result(record):
    ok = record.status is AcquisitionStatus.OK
    if ok and record.source_document_id is None:
        yield ValidationError(
            "missing_source_document", "/source_document_id",
            "a successful acquisition must reference the stored document",
            "semantic")
    if not ok and record.source_document_id is not None:
        yield ValidationError(
            "fabricated_source_document", "/source_document_id",
            "a %s acquisition has no SourceDocument" % record.status.value,
            "semantic")


def _check_patch_profile(record):
    if record.game != "poe2":
        yield ValidationError("wrong_game", "/game",
                              "this implementation is PoE 2 only", "semantic")
    if (record.compatibility is Compatibility.VERIFIED
            and not record.compatibility_evidence_ids):
        yield ValidationError(
            "unevidenced_compatibility", "/compatibility_evidence_ids",
            "verified compatibility requires evidence", "semantic")
    rules = record.character_rules
    if rules.level_range.minimum > rules.level_range.maximum:
        yield ValidationError("inverted_level_range", "/character_rules/level_range",
                              "minimum exceeds maximum", "semantic")
    for i, budget in enumerate(rules.point_budgets):
        if not budget.evidence_ids:
            yield ValidationError(
                "unevidenced_rule", "/character_rules/point_budgets/%d/evidence_ids" % i,
                "a point budget without evidence is a guessed constant",
                "semantic")


def _check_game_catalog(record):
    for table in sorted(record.entities):
        if table not in CATALOG_TABLES:
            yield ValidationError(
                "unknown_catalog_table", "/entities/%s" % table,
                "unknown entity table %r; known tables are %s"
                % (table, ", ".join(CATALOG_TABLES)), "semantic")


def _check_item_instance(record):
    for i, modifier in enumerate(record.modifiers):
        for j, value in enumerate(modifier.values):
            path = "/modifiers/%d/values/%d" % (i, j)
            lo, hi = value.minimum, value.maximum
            if lo is not None and hi is not None and lo > hi:
                yield ValidationError("inverted_range", path,
                                      "minimum exceeds maximum", "semantic")
    positions = [(m.category.value, m.source_position) for m in record.modifiers]
    for i, (category, position) in _duplicates(positions):
        yield ValidationError(
            "duplicate_source_position", "/modifiers/%d/source_position" % i,
            "%s position %d appears twice; a repeated modifier needs its own "
            "position" % (category, position), "semantic")


def _check_listing(record):
    # A price is an amount in a named currency. An amount without one cannot
    # be read; a currency without an amount is still an unknown price.
    if record.price_amount is not None and record.price_currency is None:
        yield ValidationError(
            "price_without_currency", "/price_currency",
            "a price amount needs its original currency", "semantic")
    if record.price_amount is not None and record.price_amount.startswith("-"):
        yield ValidationError("negative_price", "/price_amount",
                              "a listed price cannot be negative", "semantic")


def _check_equipment_pool(record):
    in_bound = [q for q in record.enabling_queries
                if q.status is not EnablingQueryStatus.OVER_BOUND]
    if len(in_bound) > record.sampling.enabling_queries_per_run:
        yield ValidationError(
            "enabling_queries_over_bound", "/enabling_queries",
            "%d queries are inside a bound of %d"
            % (len(in_bound), record.sampling.enabling_queries_per_run),
            "semantic")
    for i, slot in enumerate(record.slots):
        path = "/slots/%d" % i
        missing = not slot.accepted_base_categories
        if missing != (slot.status is PoolSlotStatus.MISSING_CATEGORY_RULE):
            yield ValidationError(
                "slot_status_mismatch", path + "/status",
                "missing_category_rule is the status of exactly the slots "
                "whose rule names no accepted base category", "semantic")
        if slot.truncated != (slot.considered_count > slot.retained_count):
            yield ValidationError(
                "truncation_mismatch", path + "/truncated",
                "truncated must equal considered_count > retained_count",
                "semantic")
        seen = set()
        for j, candidate in enumerate(slot.candidates):
            cpath = "%s/candidates/%d" % (path, j)
            owned = candidate.availability is CandidateAvailability.OWNED
            if owned and candidate.listing_id is not None:
                yield ValidationError(
                    "owned_with_listing", cpath + "/listing_id",
                    "an owned candidate is not a listing", "semantic")
            key = (candidate.item_hash, candidate.listing_id, owned)
            if key in seen:
                yield ValidationError(
                    "duplicate_candidate", cpath,
                    "the same candidate appears twice in one slot", "semantic")
            seen.add(key)


def _check_build_spec(record):
    allocations = {
        "/passives/allocated": record.passives.allocated,
        "/passives/ascendancy_allocated": record.passives.ascendancy_allocated,
    }
    for i, weapon_set in enumerate(record.weapon_sets):
        allocations["/weapon_sets/%d/passive_allocations" % i] = \
            weapon_set.passive_allocations
    for path, values in allocations.items():
        for i, value in _duplicates(values):
            yield ValidationError(
                "duplicate_allocation", "%s/%d" % (path, i),
                "passive %r is allocated twice" % (value,), "semantic")

    group_ids = [g.group_id for g in record.skill_groups]
    for i, group_id in _duplicates(group_ids):
        yield ValidationError("duplicate_skill_group", "/skill_groups/%d/group_id" % i,
                              "group %r appears twice" % (group_id,), "semantic")

    for i, group in enumerate(record.skill_groups):
        if group.main_skill_index is not None and \
                group.main_skill_index >= len(group.skills):
            yield ValidationError(
                "main_skill_out_of_range", "/skill_groups/%d/main_skill_index" % i,
                "index %d but the group has %d skills"
                % (group.main_skill_index, len(group.skills)), "semantic")

    yield from _support_setting_errors(record)

    if record.parse_status.value == "complete" and record.unresolved_refs:
        yield ValidationError(
            "inconsistent_parse_status", "/parse_status",
            "parse_status is complete while %d reference(s) are unresolved"
            % len(record.unresolved_refs), "semantic")
    if not record.raw_blob_hashes:
        yield ValidationError(
            "missing_raw_payload", "/raw_blob_hashes",
            "the original build payload must be preserved, so a metadata-only "
            "import cannot look like a reconstructed build", "semantic")


def _each_skill(groups):
    for i, group in enumerate(groups):
        stack = [("/skill_groups/%d/skills/%d" % (i, j), skill)
                 for j, skill in enumerate(group.skills)]
        while stack:
            path, skill = stack.pop(0)
            yield path, skill
            stack.extend(("%s/triggered/%d" % (path, k), child)
                         for k, child in enumerate(skill.triggered))


def _main_group_errors(record):
    group = record.main_skill_group
    if record.schema_version < 2:
        if group is not ABSENT:
            yield ValidationError(
                "main_group_needs_v2", "/main_skill_group",
                "main_skill_group exists from BuildSpec schema version 2",
                "semantic")
        return
    if group is ABSENT:
        yield ValidationError(
            "missing_main_skill_group", "/main_skill_group",
            "a schema version 2 BuildSpec states its main skill group, null "
            "when it has none or it is unknown", "semantic")
    elif group is None:
        if record.skill_groups and record.parse_status.value == "complete":
            yield ValidationError(
                "inconsistent_parse_status", "/main_skill_group",
                "parse_status is complete while the main skill group is "
                "unknown", "semantic")
    elif group >= len(record.skill_groups):
        yield ValidationError(
            "main_group_out_of_range", "/main_skill_group",
            "index %d but the build has %d skill groups"
            % (group, len(record.skill_groups)), "semantic")


def _support_setting_errors(record):
    """Support settings belong to schema version 2 and mirror support_ids."""
    yield from _main_group_errors(record)
    version = record.schema_version
    complete = record.parse_status.value == "complete"
    for path, skill in _each_skill(record.skill_groups):
        if version < 2:
            if skill.supports is not ABSENT:
                yield ValidationError(
                    "support_settings_need_v2", path + "/supports",
                    "support settings exist from BuildSpec schema version 2; "
                    "a version 1 record cannot carry them", "semantic")
            continue
        if skill.supports is ABSENT:
            yield ValidationError(
                "missing_support_settings", path + "/supports",
                "a schema version 2 skill lists its support settings, empty "
                "when it has no supports", "semantic")
            continue
        listed = [s.support_id for s in skill.supports]
        if listed != list(skill.support_ids):
            yield ValidationError(
                "support_settings_mismatch", path + "/supports",
                "supports %r must name support_ids %r in the same order"
                % (listed, list(skill.support_ids)), "semantic")
        for k, support in enumerate(skill.supports):
            unknown = [name for name in ("level", "quality", "enabled")
                       if getattr(support, name) is None]
            if complete and unknown:
                yield ValidationError(
                    "inconsistent_parse_status", "%s/supports/%d" % (path, k),
                    "parse_status is complete while support setting(s) %s "
                    "are unknown" % ", ".join(unknown), "semantic")


def _check_data_gap(record):
    text = record.needed_evidence.strip().lower().rstrip(".")
    if text in _VACUOUS_EVIDENCE or any(
            text == phrase or text.startswith(phrase + " ")
            for phrase in _VACUOUS_EVIDENCE):
        yield ValidationError(
            "vacuous_evidence_request", "/needed_evidence",
            "name the measurement, interaction and conditions; %r is not a "
            "collectable request" % record.needed_evidence, "semantic")
    if record.status.value == "resolved" and not record.resolution_evidence_ids:
        yield ValidationError(
            "unevidenced_resolution", "/resolution_evidence_ids",
            "a resolved gap must cite the evidence that resolved it", "semantic")


def _check_rotation_policy(record):
    for i, rule in enumerate(record.rules):
        if rule.rule_index != i:
            yield ValidationError(
                "priority_gap", "/rules/%d/rule_index" % i,
                "rule_index %d is out of order at position %d"
                % (rule.rule_index, i), "semantic")
        yield from _check_predicate(rule.predicate, "/rules/%d/predicate" % i)
        if rule.action.value == "use_skill" and rule.skill_id is None:
            yield ValidationError("missing_skill", "/rules/%d/skill_id" % i,
                                  "a use_skill action needs a skill", "semantic")


def _check_predicate(predicate, path):
    combining = predicate.operator in COMBINING_OPERATORS
    if combining:
        if predicate.operands is ABSENT or not predicate.operands:
            yield ValidationError("missing_operands", "%s/operands" % path,
                                  "%s needs at least one operand"
                                  % predicate.operator.value, "semantic")
        if predicate.path is not ABSENT or predicate.value is not ABSENT:
            yield ValidationError("misplaced_comparison", path,
                                  "%s combines predicates and takes no path or "
                                  "value" % predicate.operator.value, "semantic")
        if predicate.operator is PredicateOperator.NOT and \
                predicate.operands is not ABSENT and len(predicate.operands) != 1:
            yield ValidationError("wrong_arity", "%s/operands" % path,
                                  "not takes exactly one operand", "semantic")
        if predicate.operands is not ABSENT:
            for i, operand in enumerate(predicate.operands):
                yield from _check_predicate(operand, "%s/operands/%d" % (path, i))
        return
    if predicate.path is ABSENT:
        yield ValidationError("missing_path", "%s/path" % path,
                              "a comparison needs a state path", "semantic")
    if predicate.value is ABSENT:
        yield ValidationError("missing_value", "%s/value" % path,
                              "a comparison needs a value", "semantic")
    if predicate.operands is not ABSENT:
        yield ValidationError("misplaced_operands", "%s/operands" % path,
                              "a comparison takes no operands", "semantic")


def _check_scenario_spec(record):
    if record.duration_limit_s <= 0:
        yield ValidationError("non_positive_limit", "/duration_limit_s",
                              "a scenario needs a positive time limit", "semantic")
    for i, target in enumerate(record.target_entities):
        for j, window in enumerate(target.targetable_windows):
            if window.end_s < window.start_s:
                yield ValidationError(
                    "inverted_window",
                    "/target_entities/%d/targetable_windows/%d" % (i, j),
                    "window ends before it starts", "semantic")
    for i, event in enumerate(record.event_schedule):
        if event.at_s > record.duration_limit_s:
            yield ValidationError(
                "event_after_limit", "/event_schedule/%d/at_s" % i,
                "event at %rs is past the %rs limit"
                % (event.at_s, record.duration_limit_s), "semantic")


def _check_evaluation_result(record):
    metrics = record.metrics
    missing = [name for name in (
        "completion_time_s", "damage_dealt", "resource_starvation_s",
        "preparation_time_s", "actions_per_minute", "weapon_switches",
        "minimum_resources", "survival") if getattr(metrics, name) is None]
    if missing and not record.gap_ids:
        for name in missing:
            yield ValidationError(
                "unexplained_missing_metric", "/metrics/%s" % name,
                "%s is null, which requires a DataGap naming the missing "
                "implementation; null is not zero" % name, "semantic")
    if record.fidelity is Fidelity.SCREEN and metrics.completion_time_s is not None:
        yield ValidationError(
            "screen_cannot_time_an_encounter", "/metrics/completion_time_s",
            "a screening calculation has no encounter model and cannot produce "
            "a completion time", "semantic")
    if record.status is ResultStatus.OK and record.error is not None:
        yield ValidationError("contradictory_error", "/error",
                              "an ok result carries no error", "semantic")
    if record.status is not ResultStatus.OK and record.error is None:
        yield ValidationError("missing_error_detail", "/error",
                              "a %s result must say what failed"
                              % record.status.value, "semantic")
    if record.status is not ResultStatus.OK and record.error is not None and \
            record.error.code is not record.status:
        yield ValidationError("error_code_mismatch", "/error/code",
                              "error code %r does not match status %r"
                              % (record.error.code.value, record.status.value),
                              "semantic")


def _check_aggregate_result(record):
    unresolved = [name for name, score in record.category_scores.items()
                  if score is None]
    if unresolved and record.balanced_score is not None:
        yield ValidationError(
            "fabricated_balanced_score", "/balanced_score",
            "category %s unresolved, so every aggregate score is null"
            % ", ".join(sorted(unresolved)), "semantic")
    if unresolved and record.eligible:
        yield ValidationError("eligible_without_scores", "/eligible",
                              "a candidate with unresolved scores is not "
                              "eligible", "semantic")
    if not record.eligible and not record.exclusion_reasons:
        yield ValidationError("unexplained_exclusion", "/exclusion_reasons",
                              "an ineligible candidate must say why", "semantic")
    if not record.eligible and record.strength_label is not None:
        yield ValidationError("label_without_eligibility", "/strength_label",
                              "strength labels are for qualifying candidates "
                              "only", "semantic")
    if record.schema_version >= 2:
        yield from _aggregate_objective_errors(record)


def _aggregate_objective_errors(record):
    """A version 2 aggregate states its objective's own metrics and score."""
    try:
        definition = get_objective(record.objective_id,
                                   record.objective_version)
    except UnknownObjective as exc:
        yield ValidationError("unknown_objective", "/objective_id", str(exc),
                              "semantic")
        return
    metrics = record.objective_metrics
    expected = set(definition.metric_names)
    if set(metrics) != expected:
        yield ValidationError(
            "objective_metrics_mismatch", "/objective_metrics",
            "objective %s v%d states exactly %s; got %s"
            % (definition.objective_id, definition.version,
               sorted(expected) or "no metrics", sorted(metrics) or "none"),
            "semantic")
        return
    if definition.score_metric is None:
        source, wanted = "/balanced_score", record.balanced_score
    else:
        source = "/objective_metrics/%s" % definition.score_metric
        wanted = metrics[definition.score_metric]
        for name in definition.metric_names:
            value = metrics[name]
            if value is not None and value < 0:
                yield ValidationError(
                    "negative_objective_metric", "/objective_metrics/" + name,
                    "%s is %r; damage per second cannot be negative"
                    % (name, value), "semantic")
    if record.objective_score != wanted:
        yield ValidationError(
            "objective_score_mismatch", "/objective_score",
            "objective_score must equal %s (%r), got %r; it is never filled "
            "from another score" % (source, wanted, record.objective_score),
            "semantic")
    missing = [name for name in definition.metric_names
               if metrics[name] is None]
    if record.objective_score is None and definition.score_metric is None:
        missing.append("balanced_score")
    if missing and not record.objective_gap_ids:
        yield ValidationError(
            "unexplained_missing_objective", "/objective_gap_ids",
            "%s null without a gap" % ", ".join(missing), "semantic")
    if record.eligible and record.objective_score is None:
        yield ValidationError(
            "eligible_without_objective_score", "/eligible",
            "a candidate without an objective score is not eligible",
            "semantic")


def _check_observation(record):
    if record.outcome is TrialOutcome.CENSORED and record.censoring_reason is None:
        yield ValidationError("unexplained_censoring", "/censoring_reason",
                              "a censored trial must record why it stopped",
                              "semantic")
    if not record.raw_evidence_ids:
        yield ValidationError(
            "unevidenced_observation", "/raw_evidence_ids",
            "an independent observation must retain its raw evidence",
            "semantic")


def _check_run_request(record):
    if record.mode is RunMode.THEORETICAL:
        yield ValidationError(
            "mode_disabled", "/mode",
            "theoretical mode is disabled until item-generation legality rules "
            "and their accepted scope exist (interfaces.md)", "semantic")
    if record.mode in (RunMode.MARKET, RunMode.OFFLINE_ITEMS) and \
            not record.item_pool_ids:
        yield ValidationError(
            "unresolved_item_pool", "/item_pool_ids",
            "an empty item pool is an unresolved input, not a request to "
            "invent equipment", "semantic")
    if record.level < 1:
        yield ValidationError("invalid_level", "/level",
                              "level must be at least 1", "semantic")
    if record.schema_version >= 2:
        yield from _class_scope_errors(record.class_scope)
        yield from _objective_selection_errors(record.objective)


def _class_scope_errors(scope):
    if not scope:
        yield ValidationError(
            "empty_class_scope", "/class_scope",
            "a campaign names its approved classes explicitly; an empty list "
            "is not every class", "semantic")
    for i, class_id in _duplicates([entry.class_id for entry in scope]):
        yield ValidationError("duplicate_class_scope",
                              "/class_scope/%d/class_id" % i,
                              "class %r is listed twice" % (class_id,),
                              "semantic")
    for i, entry in enumerate(scope):
        path = "/class_scope/%d/ascendancy_ids" % i
        if entry.ascendancy_ids is None:
            continue
        if not entry.ascendancy_ids:
            yield ValidationError(
                "empty_ascendancy_scope", path,
                "an empty list approves no ascendancy; use null for every "
                "ascendancy of the class", "semantic")
        for j, ascendancy in _duplicates(entry.ascendancy_ids):
            yield ValidationError("duplicate_ascendancy_scope",
                                  "%s/%d" % (path, j),
                                  "ascendancy %r is listed twice"
                                  % (ascendancy,), "semantic")


def _objective_selection_errors(selection):
    try:
        definition = get_objective(selection.objective_id,
                                   selection.objective_version)
    except UnknownObjective as exc:
        yield ValidationError("unknown_objective", "/objective/objective_id",
                              str(exc), "semantic")
        return
    skills = selection.target_skill_ids
    if definition.requires_target_skill and not skills:
        yield ValidationError(
            "missing_target_skill", "/objective/target_skill_ids",
            "objective %s needs the exact catalog ids of its main skill"
            % definition.objective_id, "semantic")
    if not definition.requires_target_skill and skills:
        yield ValidationError(
            "unexpected_target_skill", "/objective/target_skill_ids",
            "objective %s has no skill constraint" % definition.objective_id,
            "semantic")
    for i, skill in _duplicates(skills):
        yield ValidationError("duplicate_target_skill",
                              "/objective/target_skill_ids/%d" % i,
                              "skill %r is listed twice" % (skill,),
                              "semantic")
    if definition.requires_benchmark:
        for name in ("benchmark_scenario", "attribution_rules"):
            if getattr(selection, name) is None:
                yield ValidationError(
                    "missing_" + name, "/objective/" + name,
                    "objective %s is measured on a named benchmark with "
                    "reviewed attribution rules" % definition.objective_id,
                    "semantic")
    else:
        for name in ("benchmark_scenario", "benchmark_scenario_hash",
                     "attribution_rules", "attribution_rules_hash"):
            if getattr(selection, name) is not None:
                yield ValidationError(
                    "unexpected_benchmark", "/objective/" + name,
                    "objective %s has no DPS benchmark"
                    % definition.objective_id, "semantic")


def _check_run_manifest(record):
    if not isinstance(record.resolved_request.workers, int):
        yield ValidationError(
            "unresolved_workers", "/resolved_request/workers",
            "workers must be a measured bounded integer in the manifest, not "
            "%r" % (record.resolved_request.workers,), "semantic")
    if record.resolved_request.patch_selection == "current":
        yield ValidationError(
            "unresolved_patch", "/resolved_request/patch_selection",
            "patch_selection must be resolved to an immutable profile before "
            "the manifest is written", "semantic")
    if record.worker_limit < 1:
        yield ValidationError("invalid_worker_limit", "/worker_limit",
                              "at least one worker is required", "semantic")
    yield from _check_run_request_nested(record.resolved_request)
    if record.resolved_request.schema_version >= 2:
        yield from _manifest_objective_errors(record)


def aggregate_binding_errors(aggregate, manifest) -> tuple[ValidationError, ...]:
    """Errors binding an aggregate to the run manifest it claims.

    A record index holds identifiers only, so this needs both records, like
    ``storage.validate_checkpoint``. A version 2 aggregate must carry the
    objective the manifest froze; a version 1 aggregate has no objective
    binding and cannot be ranked in a version 2 run.
    """
    errors = []
    if aggregate.manifest_id != manifest.run_id:
        errors.append(ValidationError(
            "manifest_mismatch", "/manifest_id",
            "aggregate names run %r, not %r"
            % (aggregate.manifest_id, manifest.run_id), "semantic"))
    request = manifest.resolved_request
    if request.schema_version < 2:
        if aggregate.schema_version >= 2:
            errors.append(ValidationError(
                "objective_not_in_run", "/objective_id",
                "run %r has no objective selection; a version 2 aggregate "
                "cannot belong to it" % manifest.run_id, "semantic"))
        return tuple(errors)
    if aggregate.schema_version < 2:
        errors.append(ValidationError(
            "unbound_objective", "/schema_version",
            "a version 1 aggregate has no objective binding and cannot be "
            "ranked in run %r" % manifest.run_id, "semantic"))
        return tuple(errors)
    selection = request.objective
    if (aggregate.objective_id, aggregate.objective_version) != \
            (selection.objective_id, selection.objective_version):
        errors.append(ValidationError(
            "objective_mismatch", "/objective_id",
            "aggregate is scored for %s v%s; the run optimizes %s v%s"
            % (aggregate.objective_id, aggregate.objective_version,
               selection.objective_id, selection.objective_version),
            "semantic"))
    if aggregate.objective_hash != manifest.dependency_hashes.objective_hash:
        errors.append(ValidationError(
            "objective_hash_mismatch", "/objective_hash",
            "aggregate objective_hash differs from the manifest's",
            "semantic"))
    return tuple(errors)


def _manifest_objective_errors(record):
    """A manifest freezes the objective: hashes resolved and bound."""
    selection = record.resolved_request.objective
    try:
        definition = get_objective(selection.objective_id,
                                   selection.objective_version)
    except UnknownObjective:
        return  # already reported by the nested request check
    if definition.requires_benchmark:
        unresolved = [name for name in ("benchmark_scenario_hash",
                                        "attribution_rules_hash")
                      if getattr(selection, name) is None]
        for name in unresolved:
            yield ValidationError(
                "unresolved_objective", "/resolved_request/objective/" + name,
                "%s must be resolved to content before the manifest is "
                "written" % name, "semantic")
        if unresolved:
            return
    expected = identity.objective_hash(selection)
    if record.dependency_hashes.objective_hash != expected:
        yield ValidationError(
            "objective_hash_mismatch", "/dependency_hashes/objective_hash",
            "objective_hash does not identify the resolved objective "
            "(expected %s)" % expected, "semantic")


def _check_run_request_nested(request):
    for error in _check_run_request(request):
        yield ValidationError(error.code, "/resolved_request" + error.field_path,
                              error.message, "semantic")


def _check_checkpoint(record):
    overlap = sorted(set(record.queued_task_ids) & set(record.completed_task_ids))
    if overlap:
        yield ValidationError(
            "task_in_two_states", "/queued_task_ids",
            "task(s) %s are both queued and completed" % ", ".join(overlap),
            "semantic")
    for i, task_id in _duplicates(record.completed_task_ids):
        yield ValidationError("duplicate_completed_task",
                              "/completed_task_ids/%d" % i,
                              "task %r is counted twice" % (task_id,), "semantic")


def _check_mechanic_claim(record):
    if "\x00" in record.claim_text:
        yield ValidationError("unsafe_claim_text", "/claim_text",
                              "claim text must be plain text", "semantic")
    if record.status.value != "unverified" and not record.evidence_ids:
        yield ValidationError(
            "unevidenced_claim_status", "/evidence_ids",
            "only an unverified claim may have no evidence", "semantic")


def _check_parse_result(record):
    if record.status.value == "complete" and record.issues:
        yield ValidationError("inconsistent_parse_status", "/status",
                              "a complete parse has no issues", "semantic")
    for i, coverage in enumerate(record.field_coverage):
        if coverage.resolved > coverage.present:
            yield ValidationError(
                "impossible_coverage", "/field_coverage/%d/resolved" % i,
                "resolved %d exceeds present %d"
                % (coverage.resolved, coverage.present), "semantic")


_PER_KIND = {
    "acquisition_result": _check_acquisition_result,
    "aggregate_result": _check_aggregate_result,
    "build_spec": _check_build_spec,
    "checkpoint": _check_checkpoint,
    "data_gap": _check_data_gap,
    "evaluation_result": _check_evaluation_result,
    "game_catalog": _check_game_catalog,
    "item_instance": _check_item_instance,
    "listing": _check_listing,
    "equipment_pool": _check_equipment_pool,
    "mechanic_claim": _check_mechanic_claim,
    "observation": _check_observation,
    "parse_result": _check_parse_result,
    "patch_profile": _check_patch_profile,
    "rotation_policy": _check_rotation_policy,
    "run_manifest": _check_run_manifest,
    "run_request": _check_run_request,
    "scenario_spec": _check_scenario_spec,
}


# -- references -------------------------------------------------------------

#: Identifier-shaped fields that are deliberately **not** resolved, and why.
#: Every such field on every record is either traversed by :func:`_references`
#: below or listed here. The completeness test in
#: ``tests/unit/test_p01_t03_references.py`` fails when a new field is
#: neither, so "unchecked" can never quietly become "forgotten".
UNCHECKED_REFERENCE_FIELDS: dict[tuple[str, str], str] = {
    # Record types that do not exist yet. Each names the task that creates it.
    ("source_document", "source_manifest_id"):
        "a SourceAdapter capability manifest; P03-T01 owns that record type",
    ("aggregate_result", "sensitivity_result_ids"):
        "sensitivity results are a P06-T04 record type that does not exist yet",
    ("data_gap", "sensitivity_result_id"):
        "the same absent P06-T04 record type",
    ("observation", "build_family_id"):
        "families are assigned by P09-T03; no record type yet",
    ("run_request", "item_pool_ids"):
        "equipment_pool records (P05-T03); a request names them before "
        "prepare (P08-T01) resolves them",
    ("build_spec", "variant_id"): "deduplication metadata assigned by P04",
    ("build_spec", "family_id"): "deduplication metadata assigned by P09",

    # Catalog entities and model names, not records in this corpus.
    ("mechanic_claim", "subject_ids"):
        "catalog entity ids such as a skill or a modifier, not records",
    ("build_spec", "class_id"): "a catalog entity",
    ("build_spec", "ascendancy_id"): "a catalog entity",
    ("run_request", "class_id"): "a catalog entity",
    ("scenario_spec", "spatial_model_id"): "a model name owned by P07",
    ("scenario_spec", "movement_model_id"): "a model name owned by P07",
    ("scenario_spec", "incoming_damage_model_id"): "a model name owned by P07",
    ("aggregate_result", "objective_id"):
        "a registered objective name, checked against domain/objectives.py",
    ("aggregate_result", "objective_hash"):
        "a derived objective identity; the manifest binds it",
    ("aggregate_result", "suite_id"): "a scenario-suite name owned by P09",
    ("run_manifest", "scenario_suite_id"): "a suite name owned by P09",
    ("parse_result", "parser_id"): "a parser name, not a record",
    ("mechanic_rule", "implementation_ref"):
        "a Python import path resolved by P06 and P07, not a record",
    ("mechanic_rule", "required_input_paths"):
        "JSON Pointers into a build, not record identifiers",

    # Provider and tooling labels.
    ("patch_profile", "league_id"): "a league name from the provider",
    ("patch_profile", "patch_id"): "a patch name from the provider",
    ("listing", "league_id"): "a league name from the provider",
    ("observation", "operator_id"): "a pseudonym, deliberately not a record",
    ("observation", "trial_id"): "an operator-local label for one trial",
    ("review_record", "task_or_gate_id"): "a task or gate name, not a record",
    ("review_record", "invalidated_gates"): "gate names",
    ("review_record", "next_task_ids"): "task ids from the delivery plan",
    ("review_record", "implementation_commit"): "a git commit, not a record",
    ("run_manifest", "accepted_gate_ids"): "gate names such as G0, not records",

    # Working-tree digests and derived identities, not stored content.
    ("patch_profile", "pob_dirty_hash"): "a working-tree digest, not content",
    ("run_manifest", "software_dirty_hash"): "a working-tree digest, not content",
    ("evaluation_result", "cache_key"):
        "a derived content identity recomputed by the evaluator",
    ("checkpoint", "candidate_archive_hashes"):
        "search-archive artifacts owned by P08",

    # Task rows live in their own table, not in the corpus.
    ("checkpoint", "run_id"):
        "validated against the run by storage.validate_checkpoint, which has "
        "the manifest that a bare record does not",
    ("checkpoint", "queued_task_ids"): "task rows, not corpus records",
    ("checkpoint", "completed_task_ids"): "task rows, not corpus records",


    # Catalog entities, provider labels and version control.
    ("item_instance", "base_id"): "a catalog entity",
    ("source_document", "external_id"):
        "the provider identifier for the page",
    ("source_document", "author_id"): "an author handle from the provider",
    ("patch_profile", "pob_commit"): "a git commit of the engine",
    ("run_manifest", "software_commit"): "a git commit, not a record",
    ("run_manifest", "dependency_hashes"):
        "cache-key inputs (see cache.py), not references into the corpus",
    ("checkpoint", "next_generation_id"): "a counter",
    ("mechanic_rule", "mechanic_id"):
        "this rule provides the mechanic id that other records cite",
}


#: Content hashes a record *provides* rather than cites.
_OWN_CONTENT_HASH = {
    "item_instance": "item_hash",
    "build_spec": "build_hash",
    "game_catalog": "catalog_hash",
}


def own_identity_fields(kind: str) -> set[str]:
    """Fields that are this record's own identity, not a reference out.

    ``record_id``, the domain id it must equal, and the content hash the
    record provides. ``_identity_errors`` checks the first two agree; none
    of them is resolved against the corpus, because a record cannot be
    evidence for itself.
    """
    fields = {"record_id"}
    domain_field = DOMAIN_ID_FIELDS.get(kind)
    if domain_field is not None:
        fields.add(domain_field)
    content_hash_field = _OWN_CONTENT_HASH.get(kind)
    if content_hash_field is not None:
        fields.add(content_hash_field)
    return fields


def _reference_errors(kind, record, index):
    for path, value, namespace in _references(kind, record):
        if value is None:
            continue
        if not index.contains(namespace, value):
            yield ValidationError(
                "unresolved_reference", path,
                "%r does not resolve to a known %s in this corpus or run"
                % (value, _namespace_label(namespace)), "semantic")


#: Readable names for error messages. Naive singularization turned
#: "catalog_hashes" into "catalog hashe".
_NAMESPACE_LABELS = {
    ANY_RECORD: "record",
    "record_ids": "record",
    "blob_hashes": "stored payload",
    "catalog_hashes": "catalog",
    "item_hashes": "item",
    "build_hashes": "build",
    "rotation_hashes": "rotation",
    "manifest_hashes": "run manifest",
    "listing_ids": "listing",
    "source_document_ids": "source document",
    "patch_profile_ids": "patch profile",
    "scenario_ids": "scenario",
    "rotation_ids": "rotation",
    "evaluation_ids": "evaluation",
    "manifest_ids": "run",
    "gap_ids": "gap",
    "mechanic_ids": "mechanic rule",
}


def _namespace_label(namespace: str) -> str:
    return _NAMESPACE_LABELS.get(namespace, namespace.replace("_", " "))


def _each(path, values, namespace):
    for i, value in enumerate(values):
        yield "%s/%d" % (path, i), value, namespace


def _evidence(path, values):
    """Evidence resolves against any record in the corpus.

    A source document, a parse result, a claim or an independent observation
    can all be cited as evidence, so these use the union namespace rather
    than one specific kind.
    """
    return _each(path, values, ANY_RECORD)


def _references(kind, record):
    """Every cross-record and blob reference, with the namespace it resolves in.

    Paths are JSON Pointers into the record, so an unresolved reference names
    the exact field a person has to fix.
    """
    if hasattr(record, "provenance_ids"):
        yield from _each("/provenance_ids", record.provenance_ids, ANY_RECORD)

    if kind == "source_document":
        yield "/blob_hash", record.blob_hash, "blob_hashes"

    elif kind == "acquisition_result":
        yield "/source_document_id", record.source_document_id, "source_document_ids"

    elif kind == "patch_profile":
        yield "/catalog_hash", record.catalog_hash, "catalog_hashes"
        yield from _evidence("/patch_evidence_ids", record.patch_evidence_ids)
        yield from _evidence("/compatibility_evidence_ids",
                             record.compatibility_evidence_ids)
        rules = record.character_rules
        yield from _evidence("/character_rules/evidence_ids", rules.evidence_ids)
        yield from _each("/character_rules/missing_rule_gap_ids",
                         rules.missing_rule_gap_ids, "gap_ids")
        for i, budget in enumerate(rules.point_budgets):
            yield from _evidence(
                "/character_rules/point_budgets/%d/evidence_ids" % i,
                budget.evidence_ids)
        for i, slot in enumerate(rules.slots):
            yield from _evidence("/character_rules/slots/%d/evidence_ids" % i,
                                 slot.evidence_ids)
        for i, restriction in enumerate(rules.support_restrictions):
            yield from _evidence(
                "/character_rules/support_restrictions/%d/evidence_ids" % i,
                restriction.evidence_ids)
        yield from _evidence("/character_rules/weapon_sets/evidence_ids",
                             rules.weapon_sets.evidence_ids)

    elif kind == "game_catalog":
        yield "/patch_profile_id", record.patch_profile_id, "patch_profile_ids"
        yield from _evidence("/source_evidence_ids", record.source_evidence_ids)
        for table in sorted(record.entities):
            for i, entity in enumerate(record.entities[table]):
                yield from _each(
                    "/entities/%s/%d/rule_references" % (table, i),
                    entity.rule_references, "mechanic_ids")

    elif kind == "item_instance":
        yield "/catalog_hash", record.catalog_hash, "catalog_hashes"
        yield "/source_document_id", record.source_document_id, "source_document_ids"

    elif kind == "listing":
        yield "/item_hash", record.item_hash, "item_hashes"
        yield "/source_document_id", record.source_document_id, "source_document_ids"

    elif kind == "equipment_pool":
        yield "/catalog_hash", record.catalog_hash, "catalog_hashes"
        yield "/patch_profile_id", record.patch_profile_id, "patch_profile_ids"
        for i, slot in enumerate(record.slots):
            for j, candidate in enumerate(slot.candidates):
                path = "/slots/%d/candidates/%d" % (i, j)
                yield path + "/item_hash", candidate.item_hash, "item_hashes"
                yield path + "/listing_id", candidate.listing_id, "listing_ids"
        for i, query in enumerate(record.enabling_queries):
            yield from _each("/enabling_queries/%d/matched_item_hashes" % i,
                             query.matched_item_hashes, "item_hashes")
        yield from _each("/unplaced_item_hashes", record.unplaced_item_hashes,
                         "item_hashes")
        yield from _each("/gap_ids", record.gap_ids, "gap_ids")

    elif kind == "build_spec":
        yield "/catalog_hash", record.catalog_hash, "catalog_hashes"
        yield from _evidence("/progression/evidence_ids",
                             record.progression.evidence_ids)
        for slot, content in sorted(record.equipment.items()):
            if content is None:
                continue
            yield "/equipment/%s/item_hash" % slot, content.item_hash, "item_hashes"
            yield "/equipment/%s/listing_id" % slot, content.listing_id, "listing_ids"
        for i, group in enumerate(record.skill_groups):
            yield ("/skill_groups/%d/source_item_hash" % i,
                   group.source_item_hash, "item_hashes")
        for key in sorted(record.config):
            yield from _evidence("/config/%s/evidence_ids" % key,
                                 record.config[key].evidence_ids)
        yield from _each("/rotation_ids", record.rotation_ids, "rotation_ids")
        yield from _each("/source_document_ids", record.source_document_ids,
                         "source_document_ids")
        yield from _each("/raw_blob_hashes", record.raw_blob_hashes, "blob_hashes")

    elif kind == "parse_result":
        yield "/source_document_id", record.source_document_id, "source_document_ids"
        yield from _each("/record_ids", record.record_ids, ANY_RECORD)

    elif kind == "mechanic_claim":
        yield "/source_document_id", record.source_document_id, "source_document_ids"
        yield from _each("/dependencies", record.dependencies, ANY_RECORD)
        yield from _evidence("/evidence_ids", record.evidence_ids)

    elif kind == "mechanic_rule":
        yield from _each("/patch_profile_ids", record.patch_profile_ids,
                         "patch_profile_ids")
        yield from _each("/dependency_ids", record.dependency_ids, "mechanic_ids")
        yield from _evidence("/evidence_ids", record.evidence_ids)

    elif kind == "data_gap":
        yield from _each("/subject_ids", record.subject_ids, ANY_RECORD)
        yield from _each("/mechanic_ids", record.mechanic_ids, "mechanic_ids")
        yield from _each("/affected_evaluation_ids",
                         record.affected_evaluation_ids, "evaluation_ids")
        yield from _evidence("/resolution_evidence_ids",
                             record.resolution_evidence_ids)

    elif kind == "scenario_spec":
        yield "/patch_profile_id", record.patch_profile_id, "patch_profile_ids"
        yield "/reference_build_id", record.reference_build_id, "build_hashes"
        yield "/reference_result_id", record.reference_result_id, "evaluation_ids"
        yield from _evidence("/evidence_ids", record.evidence_ids)
        for i, target in enumerate(record.target_entities):
            if target.position is not None:
                yield from _evidence(
                    "/target_entities/%d/position/conversion_evidence_ids" % i,
                    target.position.conversion_evidence_ids)

    elif kind == "evaluation_result":
        yield "/build_hash", record.build_hash, "build_hashes"
        yield "/rotation_hash", record.rotation_hash, "rotation_hashes"
        yield "/scenario_id", record.scenario_id, "scenario_ids"
        yield "/manifest_id", record.manifest_id, "manifest_ids"
        yield "/trace_blob_hash", record.trace_blob_hash, "blob_hashes"
        yield from _each("/gap_ids", record.gap_ids, "gap_ids")
        yield from _each("/rule_ids", record.rule_ids, "mechanic_ids")
        yield from _each("/assumption_ids", record.assumption_ids, ANY_RECORD)

    elif kind == "aggregate_result":
        yield "/build_hash", record.build_hash, "build_hashes"
        yield "/rotation_hash", record.rotation_hash, "rotation_hashes"
        yield "/manifest_id", record.manifest_id, "manifest_ids"
        yield from _each("/evaluation_ids", record.evaluation_ids, "evaluation_ids")
        if record.objective_gap_ids is not ABSENT:
            yield from _each("/objective_gap_ids", record.objective_gap_ids,
                             "gap_ids")
        for i, gate in enumerate(record.scenario_gates):
            yield ("/scenario_gates/%d/scenario_id" % i, gate.scenario_id,
                   "scenario_ids")

    elif kind == "observation":
        yield "/build_hash", record.build_hash, "build_hashes"
        yield "/patch_profile_id", record.patch_profile_id, "patch_profile_ids"
        yield "/scenario_id", record.scenario_id, "scenario_ids"
        yield "/rotation_id", record.rotation_id, "rotation_ids"
        yield from _evidence("/raw_evidence_ids", record.raw_evidence_ids)

    elif kind == "run_manifest":
        yield "/patch_profile_id", record.patch_profile_id, "patch_profile_ids"
        yield from _each("/source_snapshot_ids", record.source_snapshot_ids,
                         "source_document_ids")
        yield from _each("/market_snapshot_ids", record.market_snapshot_ids,
                         "listing_ids")

    elif kind == "checkpoint":
        yield "/manifest_hash", record.manifest_hash, "manifest_hashes"
