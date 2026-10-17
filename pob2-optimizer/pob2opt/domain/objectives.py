"""Registered search objectives (D07, P08-T01.1).

An objective is fixed by its id and version. Windows, metric names and
tie-break rules belong to the version: changing any of them is a new version,
never an edit, so an old aggregate keeps its meaning. A request or aggregate
naming an id/version pair that is not listed here is refused.

The values below are the engineering defaults D07 records. They are not
claims about PoE 2 mechanics, and registering an objective does not mean an
evaluator can produce its metrics yet.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ObjectiveWindow:
    """A half-open time window ``[start_s, end_s)`` from scenario time zero."""

    name: str
    start_s: float
    end_s: float


@dataclass(frozen=True, slots=True)
class ObjectiveDefinition:
    objective_id: str
    version: int
    #: Metric in ``AggregateResult.objective_metrics`` that is the ranked
    #: score. None: the score is ``balanced_score``.
    score_metric: str | None
    #: Every metric an aggregate under this objective must state, in order.
    metric_names: tuple[str, ...]
    windows: tuple[ObjectiveWindow, ...]
    #: True when a request must name exact target skill ids.
    requires_target_skill: bool
    #: True when a request must name a benchmark scenario and attribution rules.
    requires_benchmark: bool
    #: Relative tolerance inside which two scores tie; None: exact comparison.
    tie_tolerance: float | None
    #: Ordered tie-break rule names applied after the score.
    tie_breakers: tuple[str, ...]


#: The spec 1.0 default: maximum balanced score over the clear/boss suite,
#: with the scenarios.md tie-break. Version 1 requests mean this objective.
BALANCED_V1 = ObjectiveDefinition(
    objective_id="balanced_score",
    version=1,
    score_metric=None,
    metric_names=(),
    windows=(),
    requires_target_skill=False,
    requires_benchmark=False,
    tie_tolerance=1e-6,
    tie_breakers=("min_clear_boss", "canonical_build_rotation_hash"),
)

#: D07: sustained single-target Flicker Strike DPS on ``flicker_sustained_v1``.
FLICKER_SUSTAINED_DPS_V1 = ObjectiveDefinition(
    objective_id="flicker_sustained_dps",
    version=1,
    score_metric="flicker_sustained_dps",
    metric_names=("flicker_sustained_dps", "flicker_burst_dps"),
    windows=(
        ObjectiveWindow("sustained", 0.0, 120.0),
        ObjectiveWindow("burst", 0.0, 5.0),
    ),
    requires_target_skill=True,
    requires_benchmark=True,
    tie_tolerance=1e-6,
    tie_breakers=("min_clear_boss", "canonical_build_rotation_hash"),
)

OBJECTIVES: dict[tuple[str, int], ObjectiveDefinition] = {
    (o.objective_id, o.version): o
    for o in (BALANCED_V1, FLICKER_SUSTAINED_DPS_V1)
}


class UnknownObjective(LookupError):
    """An objective id/version pair this build does not implement."""

    def __init__(self, objective_id: object, version: object) -> None:
        self.objective_id = objective_id
        self.version = version
        known = ", ".join("%s v%d" % key for key in sorted(OBJECTIVES))
        super().__init__("unknown objective %r version %r; this build knows %s"
                         % (objective_id, version, known))


def get_objective(objective_id: str, version: int) -> ObjectiveDefinition:
    try:
        return OBJECTIVES[(objective_id, version)]
    except (KeyError, TypeError):
        raise UnknownObjective(objective_id, version) from None


def definition_identity(definition: ObjectiveDefinition) -> dict:
    """Every rule the definition fixes, so a silent edit changes the hash."""
    return {
        "objective_id": definition.objective_id,
        "version": definition.version,
        "score_metric": definition.score_metric,
        "metric_names": list(definition.metric_names),
        "windows": [{"name": w.name, "start_s": w.start_s, "end_s": w.end_s}
                    for w in definition.windows],
        "requires_target_skill": definition.requires_target_skill,
        "requires_benchmark": definition.requires_benchmark,
        "tie_tolerance": definition.tie_tolerance,
        "tie_breakers": list(definition.tie_breakers),
    }
