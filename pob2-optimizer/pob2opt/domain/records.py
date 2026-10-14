"""The shared records of contracts.md as dataclasses (P01-T01).

Field names, nullability and status vocabularies follow contracts.md exactly.
Three conventions run through the whole file:

* ``X | None`` is a *nullable* field: the fact is unknown or was not supplied.
  Per contracts.md it also obliges the producer to raise a ``DataGap``. It is
  never a stand-in for ``0`` or ``False``.
* ``X | Absent`` is an *optional* field: it does not apply to this record and
  is omitted from JSON entirely. See ``absent.py``.
* Everything else is required.

Records are frozen. A normalized record is evidence; changing one in place
would detach it from the hash and provenance already written next to it.

Nothing in this module reaches the network, PoB or Lua, and nothing here is a
claim about PoE 2 mechanics: these are containers and their statuses.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .absent import ABSENT, Absent
from .enums import (
    AccessMethod,
    AcquisitionStatus,
    ActionKind,
    Availability,
    AvailabilityMode,
    ClaimStatus,
    Compatibility,
    Completion,
    ConfigOrigin,
    CoverageState,
    DatasetSplit,
    Fidelity,
    GapKind,
    GapSeverity,
    GapStatus,
    Legality,
    ModifierCategory,
    ModifierParseStatus,
    ParseResultStatus,
    RecommendationStatus,
    RecordParseStatus,
    Redistribution,
    ResultStatus,
    ReviewVerdict,
    RuleOwner,
    RuleSupport,
    RuleValidation,
    RunMode,
    ScenarioCategory,
    ScenarioKind,
    StopStatus,
    StrEnum,
    StrengthLabel,
    ValidationLabel,
)

#: The schema version every record kind writes unless listed below.
SCHEMA_VERSION = 1
SUPPORTED_SCHEMA_VERSIONS = (1,)

#: BuildSpec version 2 adds per-support settings (``SkillEntry.supports``)
#: and the main skill group (``BuildSpec.main_skill_group``).
#: Version 1 records stay readable; they carry no support settings, so their
#: supports are unknown, not default. See ``domain/migrate.py``.
BUILD_SPEC_SCHEMA_VERSION = 2

#: Record kinds that read more than :data:`SUPPORTED_SCHEMA_VERSIONS`.
KIND_SCHEMA_VERSIONS: dict[str, tuple[int, ...]] = {
    "build_spec": (1, 2),
}


def supported_schema_versions(kind: str | None = None) -> tuple[int, ...]:
    """The versions one record kind reads; all known versions without a kind."""
    if kind is None:
        versions = set(SUPPORTED_SCHEMA_VERSIONS)
        for extra in KIND_SCHEMA_VERSIONS.values():
            versions.update(extra)
        return tuple(sorted(versions))
    return KIND_SCHEMA_VERSIONS.get(kind, SUPPORTED_SCHEMA_VERSIONS)


def _frozen(cls=None, /):
    """``@dataclass(frozen=True, slots=True)`` without repeating it 60 times."""
    def wrap(target):
        return dataclass(frozen=True, slots=True)(target)
    return wrap if cls is None else wrap(cls)


@_frozen
class RecordBase:
    """The four fields every persisted domain record carries."""

    schema_version: int
    record_id: str
    created_at: str
    provenance_ids: list[str]


# ===================================================== source acquisition ===

@_frozen
class PopularitySignal:
    kind: str
    value: float
    observed_at: str


@_frozen
class SourceDocument(RecordBase):
    provider: str
    source_url: str | None
    external_id: str | None
    acquired_at: str
    published_at: str | None
    updated_at: str | None
    access_method: AccessMethod
    media_type: str
    blob_hash: str
    byte_count: int
    acquisition_version: str
    source_manifest_id: str
    declared_patch: str | None
    author_id: str | None
    locale: str | None
    #: Empty means no signal was observed. It never means zero favourites.
    popularity: list[PopularitySignal]
    redistribution: Redistribution


@_frozen
class AcquisitionResult(RecordBase):
    """A network or file attempt. A failure never carries a SourceDocument."""

    provider: str
    source_ref: str
    access_method: AccessMethod
    status: AcquisitionStatus
    source_document_id: str | None
    http_status: int | None
    retry_eligible: bool
    #: Redacted. Never a raw response body, cookie or token.
    diagnostic: str | None
    attempted_at: str


# ============================================================== patch data ===

@_frozen
class LevelRange:
    minimum: int
    maximum: int


@_frozen
class PointBudgetRule:
    """A budget as a function of explicit progression flags, not of level."""

    rule_id: str
    level: int
    required_progression_flags: list[str]
    passive_points: int
    ascendancy_points: int
    evidence_ids: list[str]


@_frozen
class SlotRule:
    slot_id: str
    accepted_base_categories: list[str]
    weapon_set_id: str | None
    evidence_ids: list[str]


@_frozen
class SupportRestriction:
    restriction_id: str
    applies_to: list[str]
    max_supports: int | None
    description: str
    evidence_ids: list[str]


@_frozen
class WeaponSetRules:
    set_ids: list[str]
    hands_per_set: dict[str, int]
    swap_allowed: bool
    evidence_ids: list[str]


@_frozen
class CharacterRules:
    level_range: LevelRange
    class_ascendancies: dict[str, list[str]]
    gem_level_limit: int | None
    skill_level_limit: int | None
    point_budgets: list[PointBudgetRule]
    slots: list[SlotRule]
    support_restrictions: list[SupportRestriction]
    weapon_sets: WeaponSetRules
    #: Rules that are known to be missing. Absence is a gap, not a default.
    missing_rule_gap_ids: list[str]
    evidence_ids: list[str]


@_frozen
class PatchProfile(RecordBase):
    game: str
    realm: str
    league_id: str
    patch_id: str
    patch_evidence_ids: list[str]
    resolved_at: str
    pob_commit: str
    pob_dirty_hash: str | None
    catalog_hash: str
    adapter_version: str
    compatibility: Compatibility
    compatibility_evidence_ids: list[str]
    character_rules: CharacterRules


#: Entity tables a GameCatalog may declare. A key outside this set is rejected
#: rather than stored as a free-form table nobody downstream can read.
CATALOG_TABLES = (
    "classes",
    "ascendancies",
    "passive_nodes",
    "passive_edges",
    "gems",
    "granted_skills",
    "item_bases",
    "item_modifiers",
    "slots",
    "config_variables",
)


@_frozen
class CatalogEntity:
    entity_id: str
    display_names: list[str]
    aliases: list[str]
    #: Enough upstream data to reconstruct the entity. Not a flattened total.
    raw_reference: Any
    rule_references: list[str]


@_frozen
class GameCatalog(RecordBase):
    catalog_hash: str
    patch_profile_id: str
    entities: dict[str, list[CatalogEntity]]
    source_evidence_ids: list[str]


# =================================================== items and listings ===

@_frozen
class ValueRange:
    """A modifier value and the range it rolled inside. All parts nullable."""

    rolled: float | None
    minimum: float | None
    maximum: float | None


@_frozen
class ItemModifier:
    category: ModifierCategory
    source_position: int
    text: str
    native_id: str | None
    resolved_effect_ids: list[str]
    values: list[ValueRange]
    flags: dict[str, bool]
    parse_status: ModifierParseStatus


@_frozen
class Socket:
    socket_id: str
    group: int
    colour: str | None
    contents_id: str | None


@_frozen
class ItemInstance(RecordBase):
    item_hash: str
    catalog_hash: str
    base_id: str | None
    display_name: str
    rarity: str
    item_level: int | None
    requirements: dict[str, int]
    properties: dict[str, Any]
    #: Never summed during parsing; every source modifier is kept separately.
    modifiers: list[ItemModifier]
    sockets: list[Socket]
    flags: dict[str, bool]
    raw_text: str | None
    source_document_id: str | None
    parse_status: RecordParseStatus


@_frozen
class Listing(RecordBase):
    listing_id: str
    provider: str
    realm: str
    league_id: str
    item_hash: str
    #: Decimal string in the original currency. Null means price unknown.
    price_amount: str | None
    price_currency: str | None
    listed_at: str | None
    observed_at: str
    last_checked_at: str
    availability: Availability
    listing_url: str | None
    source_document_id: str
    #: How many of this item the listing offers. Null is unknown, and an
    #: unknown quantity may not be read as more than one.
    quantity: int | None


# ===================================================== builds and parsing ===

@_frozen
class Progression:
    quest_flags: dict[str, bool]
    reward_flags: dict[str, bool]
    #: Null until derived from catalog rules. Level alone never implies these.
    normal_point_budget: int | None
    ascendancy_point_budget: int | None
    evidence_ids: list[str]


@_frozen
class EquipmentSlot:
    item_hash: str
    listing_id: str | None


@_frozen
class WeaponSet:
    set_id: str
    hand_slots: dict[str, str | None]
    passive_allocations: list[str]


@_frozen
class SocketedEntity:
    node_id: str
    entity_id: str


@_frozen
class Passives:
    #: Unordered. Validated for duplicates, then treated as a set when hashed.
    allocated: list[str]
    ascendancy_allocated: list[str]
    #: Choices such as attribute selection: node ID to chosen option ID.
    choices: dict[str, str]
    socketed: list[SocketedEntity]


@_frozen
class SupportGem:
    """One support's settings (BuildSpec schema version 2).

    Null means the source did not say, never a PoB default. A null setting
    makes the build partial and blocks a recommended export.
    """

    support_id: str
    gem_id: str | None
    level: int | None
    quality: int | None
    enabled: bool | None


@_frozen
class SkillEntry:
    skill_id: str
    gem_id: str | None
    level: int
    quality: int
    enabled: bool
    #: Order is semantic and preserved in the hash.
    support_ids: list[str]
    #: Trigger nesting, preserved rather than flattened.
    #: ``from __future__ import annotations`` already defers every
    #: annotation here, so the self-reference needs no quotes. Quoting
    #: it leaves a bare string inside ``list[...]`` on Python 3.10.
    triggered: list[SkillEntry]
    #: Schema version 2 only, one entry per ``support_ids`` entry in the same
    #: order. Absent in version 1, where support settings were not recorded.
    supports: list[SupportGem] | Absent = ABSENT


@_frozen
class SkillGroup:
    group_id: str
    enabled: bool
    slot_id: str | None
    source_item_hash: str | None
    weapon_set_id: str | None
    main_skill_index: int | None
    skills: list[SkillEntry]


@_frozen
class ConfigValue:
    value: Any
    origin: ConfigOrigin
    #: An imported condition is a claim until something verifies it.
    verified: bool
    evidence_ids: list[str]


@_frozen
class UnresolvedRef:
    field_path: str
    reference: str
    reason: str


@_frozen
class BuildSpec(RecordBase):
    build_hash: str
    catalog_hash: str
    declared_patch: str | None
    name: str
    class_id: str
    #: Null only when the build explicitly has no ascendancy allocated.
    ascendancy_id: str | None
    level: int
    progression: Progression
    #: Slot ID to its content. An explicit empty slot is null.
    equipment: dict[str, EquipmentSlot | None]
    weapon_sets: list[WeaponSet]
    passives: Passives
    skill_groups: list[SkillGroup]
    config: dict[str, ConfigValue]
    #: May be empty on import, which creates a missing-rotation gap.
    rotation_ids: list[str]
    source_document_ids: list[str]
    variant_id: str | None
    family_id: str | None
    #: Original XML or build-code blobs, so a metadata-only import cannot look
    #: like a reconstructed build.
    raw_blob_hashes: list[str]
    parse_status: RecordParseStatus
    unresolved_refs: list[UnresolvedRef]
    #: Schema version 2 only: index of the skill group PoB evaluates as the
    #: main one (``Build@mainSocketGroup``). Null when there are no groups,
    #: or when the source does not say which one it is.
    main_skill_group: int | None | Absent = ABSENT


@_frozen
class CoverageCount:
    """Counts by domain. Deliberately not one misleading percentage."""

    domain: str
    present: int
    resolved: int
    missing: int


@_frozen
class ParseIssue:
    code: str
    field_path: str
    source_locator: str
    explanation: str


@_frozen
class ParseResult(RecordBase):
    status: ParseResultStatus
    parser_id: str
    parser_version: str
    source_document_id: str
    record_ids: list[str]
    field_coverage: list[CoverageCount]
    issues: list[ParseIssue]
    #: Unknown source fields are kept rather than dropped.
    raw_extensions: dict[str, Any]


# ================================================== mechanics and gaps ===

@_frozen
class MechanicClaim(RecordBase):
    subject_ids: list[str]
    #: A short excerpt or paraphrase. Data only: never executed, never
    #: compiled, never turned into Lua or Python.
    claim_text: str
    source_document_id: str
    source_locator: str
    applies_to_patch: str | None
    dependencies: list[str]
    status: ClaimStatus
    evidence_ids: list[str]


@_frozen
class MechanicRule(RecordBase):
    mechanic_id: str
    version: str
    patch_profile_ids: list[str]
    required_input_paths: list[str]
    dependency_ids: list[str]
    implementation_ref: str
    #: Exactly one owner calculates each effect, so nothing is counted twice.
    owner: RuleOwner
    support: RuleSupport
    validation: RuleValidation
    evidence_ids: list[str]
    limitations: list[str]
    tolerances: dict[str, float]


@_frozen
class DataGap(RecordBase):
    gap_id: str
    kind: GapKind
    subject_ids: list[str]
    field_paths: list[str]
    mechanic_ids: list[str]
    severity: GapSeverity
    explanation: str
    #: Must name the measurement. "Need more data" is rejected.
    needed_evidence: str
    collection_method: str
    affected_evaluation_ids: list[str]
    sensitivity_result_id: str | None
    status: GapStatus
    resolution_evidence_ids: list[str]


# ============================================== scenarios and rotations ===

@_frozen
class Position:
    x: float
    y: float
    #: Declared unit. PoB radius is not assumed to be metres.
    unit: str
    conversion_evidence_ids: list[str]


@_frozen
class TimeWindow:
    start_s: float
    end_s: float


@_frozen
class TargetEntity:
    entity_id: str
    catalog_entity_id: str | None
    count: int
    health: float | None
    defenses: dict[str, Any]
    position: Position | None
    targetable_windows: list[TimeWindow]


@_frozen
class ScheduledEvent:
    event_id: str
    at_s: float
    kind: str
    payload: dict[str, Any]


@_frozen
class CompletionCondition:
    kind: str
    parameters: dict[str, Any]


@_frozen
class AllowedPreparation:
    action_ids: list[str]
    duration_limit_s: float | None


@_frozen
class Gate:
    gate_id: str
    metric_path: str
    comparison: str
    value: float


@_frozen
class ScenarioSpec(RecordBase):
    scenario_id: str
    version: str
    category: ScenarioCategory
    kind: ScenarioKind
    patch_profile_id: str
    target_entities: list[TargetEntity]
    initial_state: dict[str, Any]
    event_schedule: list[ScheduledEvent]
    spatial_model_id: str
    movement_model_id: str
    duration_limit_s: float
    completion_condition: CompletionCondition
    incoming_damage_model_id: str
    allowed_preparation: AllowedPreparation
    rng_seeds: list[int]
    reference_build_id: str | None
    reference_result_id: str | None
    capability_floor_ratio: float
    survival_gates: list[Gate]
    resource_gates: list[Gate]
    evidence_ids: list[str]
    validation_status: RuleValidation


class PredicateOperator(StrEnum):
    """The v1 predicate vocabulary. P07 owns any extension of this set."""

    ALL = "all"
    ANY = "any"
    NOT = "not"
    EQ = "eq"
    NE = "ne"
    LT = "lt"
    LTE = "lte"
    GT = "gt"
    GTE = "gte"


#: Operators that combine sub-predicates rather than compare a state path.
COMBINING_OPERATORS = frozenset(
    {PredicateOperator.ALL, PredicateOperator.ANY, PredicateOperator.NOT}
)


@_frozen
class Predicate:
    """A structured condition. Never source code, never evaluated as text."""

    operator: PredicateOperator
    operands: list[Predicate] | Absent
    #: Catalog state path, for comparison operators.
    path: str | Absent
    value: Any | Absent


@_frozen
class RotationRule:
    rule_index: int
    action_id: str
    action: ActionKind
    skill_id: str | None
    target_selector: str
    weapon_set_id: str | None
    predicate: Predicate


@_frozen
class RotationPolicy(RecordBase):
    rotation_id: str
    version: str
    name: str
    category: ScenarioCategory
    #: A bounded priority list, highest priority first.
    rules: list[RotationRule]


# ================================================== evaluation and scores ===

@_frozen
class ErrorDetail:
    code: ResultStatus
    stage: str
    record_ids: list[str]
    #: Redacted diagnostic text.
    diagnostic: str


@_frozen
class EvaluationMetrics:
    """Null means the implementation did not produce it, and owes a gap.

    ``damage_dealt: 0.0`` is a legitimate zero and is not the same thing.
    """

    completion: Completion
    completion_time_s: float | None
    damage_dealt: float | None
    resource_starvation_s: float | None
    preparation_time_s: float | None
    actions_per_minute: float | None
    weapon_switches: int | None
    minimum_resources: dict[str, float] | None
    survival: dict[str, Any] | None


@_frozen
class EvaluationResult(RecordBase):
    evaluation_id: str
    cache_key: str
    build_hash: str
    rotation_hash: str
    scenario_id: str
    manifest_id: str
    fidelity: Fidelity
    seed: int
    status: ResultStatus
    legality: Legality
    coverage: CoverageState
    validation: ValidationLabel
    metrics: EvaluationMetrics
    gap_ids: list[str]
    assumption_ids: list[str]
    rule_ids: list[str]
    trace_blob_hash: str | None
    duration_ms: int
    error: ErrorDetail | None


@_frozen
class ScenarioGateOutcome:
    scenario_id: str
    ratio: float | None
    passed: bool | None
    reason: str | None


@_frozen
class AggregateResult(RecordBase):
    aggregate_id: str
    build_hash: str
    rotation_hash: str
    manifest_id: str
    objective_id: str
    suite_id: str
    #: Category name to score. Null when a required result is missing.
    category_scores: dict[str, float | None]
    balanced_score: float | None
    scenario_gates: list[ScenarioGateOutcome]
    eligible: bool
    strength_label: StrengthLabel | None
    recommendation_status: RecommendationStatus
    sensitivity_result_ids: list[str]
    evaluation_ids: list[str]
    #: Required whenever the candidate is not eligible.
    exclusion_reasons: list[str]


# ============================================================ observations ===

class MeasurementMethod(StrEnum):
    """How an independent gameplay observation was taken.

    PoB output, a guide claim and a ladder entry are not in this list on
    purpose: contracts.md rules them out as independent observations.
    """

    MANUAL_TIMER = "manual_timer"
    VIDEO_FRAME_COUNT = "video_frame_count"
    CLIENT_LOG = "client_log"
    INSTRUMENTED_CAPTURE = "instrumented_capture"


class TrialOutcome(StrEnum):
    SUCCESS = "success"
    FAILURE = "failure"
    #: Stopped before the completion condition; kept, never discarded.
    CENSORED = "censored"


@_frozen
class Observation(RecordBase):
    observation_id: str
    build_hash: str
    patch_profile_id: str
    scenario_id: str
    rotation_id: str
    #: Pseudonymous.
    operator_id: str
    trial_id: str
    measured_at: str
    measurement_method: MeasurementMethod
    outcome: TrialOutcome
    censoring_reason: str | None
    metrics: dict[str, float | None]
    raw_evidence_ids: list[str]
    measurement_uncertainty: dict[str, Any]
    deviations: list[str]
    dataset_split: DatasetSplit
    build_family_id: str | None
    review_status: str


# ================================================== runs and task state ===

@_frozen
class RunRequest:
    """The request file of interfaces.md. Not a persisted domain record."""

    schema_version: int
    game: str
    class_id: str = field(metadata={"json_key": "class"})
    level: int
    patch_selection: str
    league_selection: str
    mode: RunMode
    #: Null means no spending limit, which is the product default.
    budget: str | None
    scenario_suite: str
    catalog_profile: str
    corpus_path: str
    item_pool_ids: list[str]
    seed: int
    time_budget_s: int
    #: "auto" is only legal before prepare resolves it to an integer.
    workers: int | str
    memory_limit_mb: int
    allow_weapon_switch: bool
    allow_external_gear_swap: bool
    execution_profile: str


@_frozen
class DependencyHashes:
    """Every input that changes an evaluation's identity (architecture.md)."""

    patch_profile_hash: str
    catalog_hash: str
    pob_commit: str
    pob_dirty_hash: str | None
    adapter_version: str
    mechanics_registry_hash: str
    calibration_hash: str
    evaluator_version: str
    objective_hash: str
    baseline_suite_hash: str


@_frozen
class RunManifest(RecordBase):
    run_id: str
    spec_version: str
    software_commit: str
    software_dirty_hash: str | None
    resolved_request: RunRequest
    patch_profile_id: str
    dependency_hashes: DependencyHashes
    #: Ordered; order is part of the manifest identity.
    source_snapshot_ids: list[str]
    market_snapshot_ids: list[str]
    rng_seed: int
    search_parameters: dict[str, Any]
    worker_limit: int
    memory_limit_mb: int
    time_budget_s: int
    hardware_summary: dict[str, Any]
    scenario_suite_id: str
    accepted_gate_ids: list[str]
    availability_mode: AvailabilityMode


@_frozen
class Checkpoint:
    """Written atomically after each generation and at cancellation."""

    schema_version: int
    created_at: str
    run_id: str
    manifest_hash: str
    completed_generation: int
    candidate_archive_hashes: list[str]
    queued_task_ids: list[str]
    completed_task_ids: list[str]
    #: Generator name to its serialized state.
    rng_states: dict[str, str]
    accumulated_search_time_s: float
    next_generation_id: int
    stop_status: StopStatus


# ================================================================ review ===

@_frozen
class ReviewFinding:
    finding_id: str
    severity: str
    location: str
    description: str
    repair_acceptance: str


@_frozen
class ReviewRecord(RecordBase):
    task_or_gate_id: str
    spec_version: str
    implementation_commit: str
    verdict: ReviewVerdict
    reviewer: str
    reviewed_at: str
    commands_run: list[str]
    evidence_paths: list[str]
    findings: list[ReviewFinding]
    residual_limits: list[str]
    invalidated_gates: list[str]
    next_task_ids: list[str]


# ============================================================= registry ===

#: Record kind to class. The kind string is the JSON Schema file stem, the
#: ``kind`` column in storage and the name used in every error message.
RECORD_TYPES: dict[str, type] = {
    "source_document": SourceDocument,
    "acquisition_result": AcquisitionResult,
    "patch_profile": PatchProfile,
    "game_catalog": GameCatalog,
    "item_instance": ItemInstance,
    "listing": Listing,
    "build_spec": BuildSpec,
    "parse_result": ParseResult,
    "mechanic_claim": MechanicClaim,
    "mechanic_rule": MechanicRule,
    "data_gap": DataGap,
    "scenario_spec": ScenarioSpec,
    "rotation_policy": RotationPolicy,
    "evaluation_result": EvaluationResult,
    "aggregate_result": AggregateResult,
    "observation": Observation,
    "run_request": RunRequest,
    "run_manifest": RunManifest,
    "checkpoint": Checkpoint,
    "review_record": ReviewRecord,
}

RECORD_KINDS: dict[type, str] = {cls: kind for kind, cls in RECORD_TYPES.items()}

#: Records that declare their own domain identifier. ``record_id`` must equal
#: it, so storage and the domain can never drift apart.
DOMAIN_ID_FIELDS: dict[str, str] = {
    "data_gap": "gap_id",
    "listing": "listing_id",
    "evaluation_result": "evaluation_id",
    "aggregate_result": "aggregate_id",
    "observation": "observation_id",
    "scenario_spec": "scenario_id",
    "rotation_policy": "rotation_id",
    "run_manifest": "run_id",
}


def kind_of(record: Any) -> str:
    """The registered kind of a record instance or class."""
    cls = record if isinstance(record, type) else type(record)
    try:
        return RECORD_KINDS[cls]
    except KeyError:
        raise LookupError("%s is not a registered record type" % cls.__name__) from None


# Every record class, nested type, enum and module constant, plus the one
# helper function. Built from the namespace so a new record cannot be added
# without being exported.
__all__ = sorted(
    ({name for name in dir() if name[:1].isupper()}
     | {"kind_of", "supported_schema_versions"})
    - {"Any", "ABSENT", "Absent"}
)
