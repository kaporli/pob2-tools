"""Closed status vocabularies from contracts.md (P01-T01).

Every value here is spelled exactly as the specification spells it, because the
same strings are the JSON Schema enums in ``pob2opt/schemas/v1``. A value that
is not in this file is an unknown status and is rejected, never coerced to a
neighbouring one.

These are software statuses. None of them is a claim about PoE 2 mechanics.
"""

from __future__ import annotations

from enum import Enum


class StrEnum(str, Enum):
    """``str`` subclass so json.dumps and SQLite parameters work directly.

    ``enum.StrEnum`` only exists from Python 3.11 and architecture.md retains
    3.10 support.
    """

    def __str__(self) -> str:  # pragma: no cover - repr convenience only
        return str(self.value)


# --------------------------------------------------------------- acquisition

class AccessMethod(StrEnum):
    LOCAL_FILE = "local_file"
    PUBLIC_PAGE = "public_page"
    DOCUMENTED_API = "documented_api"
    PROVIDER_EXPORT = "provider_export"
    MANUAL_CAPTURE = "manual_capture"


class Redistribution(StrEnum):
    ALLOWED = "allowed"
    RESTRICTED = "restricted"
    UNKNOWN = "unknown"


class AcquisitionStatus(StrEnum):
    OK = "ok"
    NOT_FOUND = "not_found"
    ACCESS_BLOCKED = "access_blocked"
    RATE_LIMITED = "rate_limited"
    INVALID_RESPONSE = "invalid_response"
    TIMEOUT = "timeout"
    UNSUPPORTED_ACCESS = "unsupported_access"


# ------------------------------------------------------------------- catalog

class Compatibility(StrEnum):
    VERIFIED = "verified"
    PARTIAL = "partial"
    UNKNOWN = "unknown"
    STALE = "stale"


# ------------------------------------------------------------- items, builds

class ModifierCategory(StrEnum):
    IMPLICIT = "implicit"
    EXPLICIT = "explicit"
    ENCHANT = "enchant"
    RUNE = "rune"
    FRACTURED = "fractured"
    CRAFTED = "crafted"
    DESECRATED = "desecrated"
    UNKNOWN = "unknown"


class ModifierParseStatus(StrEnum):
    RESOLVED = "resolved"
    UNRESOLVED = "unresolved"
    AMBIGUOUS = "ambiguous"


class RecordParseStatus(StrEnum):
    """``parse_status`` of an ItemInstance or BuildSpec."""

    COMPLETE = "complete"
    PARTIAL = "partial"
    INVALID = "invalid"


class ParseResultStatus(StrEnum):
    """``status`` of a ParseResult; adds the unsupported-format outcome."""

    COMPLETE = "complete"
    PARTIAL = "partial"
    INVALID = "invalid"
    UNSUPPORTED_FORMAT = "unsupported_format"


class Availability(StrEnum):
    OBSERVED = "observed"
    RECHECKED = "rechecked"
    UNAVAILABLE = "unavailable"
    UNKNOWN = "unknown"


# ---------------------------------------------------- equipment pools (P05-T03)

class PoolSlotStatus(StrEnum):
    POPULATED = "populated"
    EMPTY = "empty"
    #: The slot rule names no accepted base category, so imported items
    #: cannot be placed in it. Only owned items placed by a source build are.
    MISSING_CATEGORY_RULE = "missing_category_rule"


class CandidateAvailability(StrEnum):
    """A pool candidate's availability: owned, or its listing's evidence."""

    OWNED = "owned"
    OBSERVED = "observed"
    RECHECKED = "rechecked"
    #: An imported item without listing evidence, or a listing whose current
    #: state is unknown.
    UNKNOWN = "unknown"


class EnablingQueryStatus(StrEnum):
    #: Declared inside the run bound; no approved route ran it (D01).
    UNEXECUTED = "unexecuted"
    #: Past the run's enabling-query bound; neither run nor applied.
    OVER_BOUND = "over_bound"


class ConfigOrigin(StrEnum):
    SOURCE = "source"
    SCENARIO = "scenario"
    DERIVED = "derived"
    MANUAL = "manual"


# ----------------------------------------------------------------- mechanics

class ClaimStatus(StrEnum):
    UNVERIFIED = "unverified"
    CORROBORATED = "corroborated"
    CONTRADICTED = "contradicted"
    SUPERSEDED = "superseded"


class RuleOwner(StrEnum):
    POB = "pob"
    SIMULATOR = "simulator"
    SCENARIO = "scenario"


class RuleSupport(StrEnum):
    IMPLEMENTED = "implemented"
    PARTIAL = "partial"
    UNSUPPORTED = "unsupported"
    UNKNOWN = "unknown"


class RuleValidation(StrEnum):
    UNTESTED = "untested"
    FIXTURE_CHECKED = "fixture_checked"
    GAMEPLAY_CHECKED = "gameplay_checked"
    CONTRADICTED = "contradicted"
    STALE = "stale"


class GapKind(StrEnum):
    MISSING_INPUT = "missing_input"
    UNRESOLVED_ENTITY = "unresolved_entity"
    UNSUPPORTED_RULE = "unsupported_rule"
    CONFLICTING_EVIDENCE = "conflicting_evidence"
    STALE_PATCH = "stale_patch"
    UNVALIDATED_PREDICTION = "unvalidated_prediction"
    ACCESS_BLOCKED = "access_blocked"


class GapSeverity(StrEnum):
    BLOCKING = "blocking"
    RANKING_SENSITIVE = "ranking_sensitive"
    INFORMATIONAL = "informational"


class GapStatus(StrEnum):
    OPEN = "open"
    RESOLVED = "resolved"
    SUPERSEDED = "superseded"


# ------------------------------------------------------ scenarios, rotations

class ScenarioCategory(StrEnum):
    CLEAR = "clear"
    BOSS = "boss"


class ScenarioKind(StrEnum):
    SYNTHETIC = "synthetic"
    REPRESENTATIVE = "representative"


class ActionKind(StrEnum):
    USE_SKILL = "use_skill"
    SWITCH_WEAPON_SET = "switch_weapon_set"
    MOVE = "move"
    WAIT = "wait"


# ------------------------------------------------------------------ evaluation

class Fidelity(StrEnum):
    SCREEN = "screen"
    DETAILED = "detailed"


class ResultStatus(StrEnum):
    """The architecture.md error boundary."""

    OK = "ok"
    INVALID_INPUT = "invalid_input"
    LEGALITY_UNKNOWN = "legality_unknown"
    UNSUPPORTED = "unsupported"
    TIMEOUT = "timeout"
    ENGINE_CRASH = "engine_crash"
    INTERNAL_ERROR = "internal_error"


class Legality(StrEnum):
    LEGAL = "legal"
    ILLEGAL = "illegal"
    UNKNOWN = "unknown"


class CoverageState(StrEnum):
    SUPPORTED = "supported"
    PARTIAL = "partial"
    UNSUPPORTED = "unsupported"


class ValidationLabel(StrEnum):
    SYNTHETIC_ONLY = "synthetic_only"
    MODEL_ESTIMATE = "model_estimate"
    GAMEPLAY_VALIDATED = "gameplay_validated"
    STALE = "stale"


class Completion(StrEnum):
    SUCCESS = "success"
    TIMEOUT = "timeout"
    DEATH = "death"
    UNKNOWN = "unknown"


class StrengthLabel(StrEnum):
    CLEAR_FOCUSED = "clear_focused"
    BOSS_FOCUSED = "boss_focused"
    BALANCED = "balanced"


class RecommendationStatus(StrEnum):
    RECOMMENDED = "recommended"
    NOT_RECOMMENDED = "not_recommended"
    EXCLUDED = "excluded"
    UNRESOLVED = "unresolved"


# -------------------------------------------------------------- observations

class DatasetSplit(StrEnum):
    CALIBRATION = "calibration"
    VALIDATION = "validation"
    HOLDOUT = "holdout"


# ------------------------------------------------------------ runs and tasks

class RunMode(StrEnum):
    MARKET = "market"
    OFFLINE_ITEMS = "offline_items"
    THEORETICAL = "theoretical"


class AvailabilityMode(StrEnum):
    LIVE_MARKET = "live_market"
    OFFLINE_SNAPSHOT = "offline_snapshot"


class StopStatus(StrEnum):
    RUNNING = "running"
    BUDGET_EXHAUSTED = "budget_exhausted"
    CONVERGED = "converged"
    CANCELLED = "cancelled"
    FAILED = "failed"


class TaskState(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


#: Transitions the coordinator may record. Anything else is a programming
#: error. ``running -> queued`` is restart recovery only, never a live move.
TASK_TRANSITIONS: dict[TaskState, frozenset[TaskState]] = {
    TaskState.QUEUED: frozenset({TaskState.RUNNING, TaskState.CANCELLED}),
    TaskState.RUNNING: frozenset(
        {TaskState.COMPLETED, TaskState.FAILED, TaskState.CANCELLED, TaskState.QUEUED}
    ),
    TaskState.COMPLETED: frozenset(),
    TaskState.FAILED: frozenset({TaskState.QUEUED}),
    TaskState.CANCELLED: frozenset(),
}

TERMINAL_TASK_STATES = frozenset(
    {TaskState.COMPLETED, TaskState.FAILED, TaskState.CANCELLED}
)


# ----------------------------------------------------------------- reviewing

class ReviewVerdict(StrEnum):
    ACCEPTED = "accepted"
    CHANGES_REQUIRED = "changes_required"
    BLOCKED = "blocked"
    SUPERSEDED = "superseded"


# --------------------------------------------------------------------- cache

class CacheOutcome(StrEnum):
    HIT = "hit"
    MISS = "miss"


class CacheReason(StrEnum):
    """Why a lookup hit or missed. Persisted with every decision (P01-T04)."""

    EXACT_MATCH = "exact_match"
    NO_ENTRY = "no_entry"
    FIDELITY_INSUFFICIENT = "fidelity_insufficient"
    LEGACY_IMPORT = "legacy_import"
    DEPENDENCY_CHANGED = "dependency_changed"
