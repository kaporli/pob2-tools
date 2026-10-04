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
from typing import Any, Iterable, Sequence

from jsonschema.exceptions import best_match

from .absent import ABSENT
from .codec import CodecError, NotANumber, from_jsonable, to_jsonable
from .enums import (
    AcquisitionStatus,
    Compatibility,
    Fidelity,
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

@dataclass
class RecordIndex:
    """What a reference is allowed to resolve to.

    An empty index means "do not check references", which is what a parser
    does before its output is placed in a corpus. A populated index is the
    second semantic pass contracts.md asks for: every cross-record reference
    must resolve inside the exported run or corpus.
    """

    record_ids: set[str] = dc_field(default_factory=set)
    blob_hashes: set[str] = dc_field(default_factory=set)
    catalog_hashes: set[str] = dc_field(default_factory=set)
    item_hashes: set[str] = dc_field(default_factory=set)
    build_hashes: set[str] = dc_field(default_factory=set)
    listing_ids: set[str] = dc_field(default_factory=set)
    source_document_ids: set[str] = dc_field(default_factory=set)
    patch_profile_ids: set[str] = dc_field(default_factory=set)
    scenario_ids: set[str] = dc_field(default_factory=set)
    rotation_ids: set[str] = dc_field(default_factory=set)
    evaluation_ids: set[str] = dc_field(default_factory=set)
    manifest_ids: set[str] = dc_field(default_factory=set)
    gap_ids: set[str] = dc_field(default_factory=set)
    mechanic_ids: set[str] = dc_field(default_factory=set)

    #: Checking is off until something is added, so a bare index is inert.
    enabled: bool = False

    def add(self, record: Any) -> "RecordIndex":
        kind = kind_of(record)
        self.enabled = True
        rid = getattr(record, "record_id", None)
        if rid is not None:
            self.record_ids.add(rid)
        bucket = {
            "source_document": ("source_document_ids", "record_id"),
            "patch_profile": ("patch_profile_ids", "record_id"),
            "listing": ("listing_ids", "listing_id"),
            "scenario_spec": ("scenario_ids", "scenario_id"),
            "rotation_policy": ("rotation_ids", "rotation_id"),
            "evaluation_result": ("evaluation_ids", "evaluation_id"),
            "run_manifest": ("manifest_ids", "run_id"),
            "data_gap": ("gap_ids", "gap_id"),
            "mechanic_rule": ("mechanic_ids", "mechanic_id"),
        }.get(kind)
        if bucket is not None:
            getattr(self, bucket[0]).add(getattr(record, bucket[1]))
        if kind == "source_document":
            self.blob_hashes.add(record.blob_hash)
        if kind == "item_instance":
            self.item_hashes.add(record.item_hash)
        if kind == "build_spec":
            self.build_hashes.add(record.build_hash)
        # Only a catalog or the profile that pinned it vouches for a catalog
        # hash. An item citing a catalog is not evidence the catalog exists.
        if kind in ("game_catalog", "patch_profile"):
            self.catalog_hashes.add(record.catalog_hash)
        return self

    def add_blob(self, blob_hash: str) -> "RecordIndex":
        self.enabled = True
        self.blob_hashes.add(blob_hash)
        return self

    @classmethod
    def from_records(cls, records: Iterable[Any]) -> "RecordIndex":
        index = cls()
        for record in records:
            index.add(record)
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
        instance = None
    else:
        try:
            data = to_jsonable(record)
        except CodecError as exc:
            return ValidationReport(kind, (_codec_error(exc),))
        instance = record

    # 1. version
    try:
        check_schema_version(data.get("schema_version"))
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

    # 3. shape
    if instance is None:
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
    if index is not None and index.enabled:
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

def _reference_errors(kind, record, index):
    for path, value, namespace in _references(kind, record):
        if value is None:
            continue
        known = getattr(index, namespace)
        if value not in known:
            yield ValidationError(
                "unresolved_reference", path,
                "%r does not resolve to a known %s in this corpus or run"
                % (value, namespace.rstrip("s").replace("_", " ")), "semantic")


def _each(path, values, namespace):
    for i, value in enumerate(values):
        yield "%s/%d" % (path, i), value, namespace


def _references(kind, record):
    if hasattr(record, "provenance_ids"):
        yield from _each("/provenance_ids", record.provenance_ids, "record_ids")
    if kind == "source_document":
        yield "/blob_hash", record.blob_hash, "blob_hashes"
    elif kind == "acquisition_result":
        yield "/source_document_id", record.source_document_id, "source_document_ids"
    elif kind == "patch_profile":
        yield "/catalog_hash", record.catalog_hash, "catalog_hashes"
    elif kind == "game_catalog":
        yield "/patch_profile_id", record.patch_profile_id, "patch_profile_ids"
    elif kind == "item_instance":
        yield "/catalog_hash", record.catalog_hash, "catalog_hashes"
        yield "/source_document_id", record.source_document_id, "source_document_ids"
    elif kind == "listing":
        yield "/item_hash", record.item_hash, "item_hashes"
        yield "/source_document_id", record.source_document_id, "source_document_ids"
    elif kind == "build_spec":
        yield "/catalog_hash", record.catalog_hash, "catalog_hashes"
        for slot, content in sorted(record.equipment.items()):
            if content is None:
                continue
            yield "/equipment/%s/item_hash" % slot, content.item_hash, "item_hashes"
            yield "/equipment/%s/listing_id" % slot, content.listing_id, "listing_ids"
        for i, group in enumerate(record.skill_groups):
            yield ("/skill_groups/%d/source_item_hash" % i,
                   group.source_item_hash, "item_hashes")
        yield from _each("/rotation_ids", record.rotation_ids, "rotation_ids")
        yield from _each("/source_document_ids", record.source_document_ids,
                         "source_document_ids")
        yield from _each("/raw_blob_hashes", record.raw_blob_hashes, "blob_hashes")
    elif kind == "parse_result":
        yield "/source_document_id", record.source_document_id, "source_document_ids"
        yield from _each("/record_ids", record.record_ids, "record_ids")
    elif kind == "mechanic_claim":
        yield "/source_document_id", record.source_document_id, "source_document_ids"
    elif kind == "data_gap":
        yield from _each("/mechanic_ids", record.mechanic_ids, "mechanic_ids")
        yield from _each("/affected_evaluation_ids", record.affected_evaluation_ids,
                         "evaluation_ids")
    elif kind == "scenario_spec":
        yield "/patch_profile_id", record.patch_profile_id, "patch_profile_ids"
        yield "/reference_build_id", record.reference_build_id, "build_hashes"
        yield "/reference_result_id", record.reference_result_id, "evaluation_ids"
    elif kind == "evaluation_result":
        yield "/build_hash", record.build_hash, "build_hashes"
        yield "/scenario_id", record.scenario_id, "scenario_ids"
        yield "/manifest_id", record.manifest_id, "manifest_ids"
        yield "/trace_blob_hash", record.trace_blob_hash, "blob_hashes"
        yield from _each("/gap_ids", record.gap_ids, "gap_ids")
        yield from _each("/rule_ids", record.rule_ids, "mechanic_ids")
    elif kind == "aggregate_result":
        yield "/build_hash", record.build_hash, "build_hashes"
        yield "/manifest_id", record.manifest_id, "manifest_ids"
        yield from _each("/evaluation_ids", record.evaluation_ids, "evaluation_ids")
    elif kind == "observation":
        yield "/build_hash", record.build_hash, "build_hashes"
        yield "/patch_profile_id", record.patch_profile_id, "patch_profile_ids"
        yield "/scenario_id", record.scenario_id, "scenario_ids"
        yield "/rotation_id", record.rotation_id, "rotation_ids"
    elif kind == "run_manifest":
        yield "/patch_profile_id", record.patch_profile_id, "patch_profile_ids"
