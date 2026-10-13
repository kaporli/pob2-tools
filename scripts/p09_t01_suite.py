"""Build the P09-T01 measurement protocol artefacts.

Run it to regenerate everything this task freezes:

    python scripts/p09_t01_suite.py

It writes three files and invents nothing about PoE 2:

* ``tests/fixtures/combat/p09_synthetic_suite.v1.json`` - four SYNTHETIC
  ScenarioSpec records in the four shapes of ``docs/specs/scenarios.md``, two
  SYNTHETIC RotationPolicy records, and the fourteen DataGap records that name
  the inputs a representative suite still needs. Every number in the scenarios
  is a test constant chosen so the arithmetic is hand-checkable. None is an
  enemy statistic, an encounter timing or a measurement.
* ``benchmarks/p09-synthetic-v1/suite.json`` - the frozen reference manifest:
  per-scenario ``scenario_hash``, the suite hash, the fixture path and its
  SHA-256, and the reference build and result slots, which are null because no
  reference build exists.
* ``docs/evidence/P09/protocol-fields.json`` - every ScenarioSpec field for
  every workload with its basis: a specification source, a product default, a
  declared synthetic test constant, or an unresolved input naming its gap.

Nothing here reaches the network, PoB or the game. Nothing here is gameplay
evidence, and the synthetic suite must never be reported as map clear speed or
boss kill time.
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
for _pkg in (REPO_ROOT / "pob2-mcp", REPO_ROOT / "pob2-optimizer"):
    if str(_pkg) not in sys.path:
        sys.path.insert(0, str(_pkg))

from pob2opt.domain.absent import ABSENT  # noqa: E402
from pob2opt.domain.codec import to_jsonable  # noqa: E402
from pob2opt.domain.enums import (  # noqa: E402
    ActionKind,
    GapKind,
    GapSeverity,
    GapStatus,
    RuleValidation,
    ScenarioCategory,
    ScenarioKind,
)
from pob2opt.domain.identity import baseline_suite_hash, scenario_hash  # noqa: E402
from pob2opt.domain.records import (  # noqa: E402
    SCHEMA_VERSION,
    PredicateOperator,
    AllowedPreparation,
    CompletionCondition,
    DataGap,
    Gate,
    Position,
    Predicate,
    RotationPolicy,
    RotationRule,
    ScenarioSpec,
    ScheduledEvent,
    TargetEntity,
    TimeWindow,
)
from pob2opt.domain.validation import validate_record  # noqa: E402

SUITE_ID = "p09-synthetic-v1"
PROTOCOL_ID = "p09-syn-protocol-v1"
CREATED_AT = "2026-10-10T00:00:00Z"
PATCH_PROFILE_ID = "p09-syn-patch-profile"

FIXTURE_PATH = REPO_ROOT / "tests" / "fixtures" / "combat" / "p09_synthetic_suite.v1.json"
SUITE_PATH = REPO_ROOT / "benchmarks" / SUITE_ID / "suite.json"
FIELDS_PATH = REPO_ROOT / "docs" / "evidence" / "P09" / "protocol-fields.json"

NOT_A_CLAIM = (
    "SYNTHETIC. Every entity, count, health value, position, duration and "
    "window below is a test constant invented for software testing. None is a "
    "PoE 2 monster, a recorded encounter timing or any other measurement, and "
    "none may be cited as evidence about PoE 2. A result produced on this "
    "suite is not map clear speed and not boss kill time."
)

#: Repeated inside every scenario's initial_state so the label survives any
#: extraction of a single record from the bundle.
SYNTHETIC_MARK = {
    "synthetic": True,
    "not_a_claim": NOT_A_CLAIM,
    "suite_id": SUITE_ID,
}


# ------------------------------------------------------------------- gaps ===

def _gap(gap_id, kind, severity, field_paths, explanation, needed_evidence,
         collection_method, subject_ids=()):
    return DataGap(
        schema_version=SCHEMA_VERSION,
        record_id=gap_id,
        created_at=CREATED_AT,
        provenance_ids=[PROTOCOL_ID],
        gap_id=gap_id,
        kind=kind,
        subject_ids=list(subject_ids),
        field_paths=list(field_paths),
        mechanic_ids=[],
        severity=severity,
        explanation=explanation,
        needed_evidence=needed_evidence,
        collection_method=collection_method,
        affected_evaluation_ids=[],
        sensitivity_result_id=None,
        status=GapStatus.OPEN,
        resolution_evidence_ids=[],
    )


ALL_SCENARIO_IDS = [
    "p09-syn-clear-dense",
    "p09-syn-clear-spread",
    "p09-syn-boss-short",
    "p09-syn-boss-sustained",
]
CLEAR_IDS = ALL_SCENARIO_IDS[:2]
BOSS_IDS = ALL_SCENARIO_IDS[2:]


def build_gaps():
    return [
        _gap(
            "gap-p09-t01-enemy-health",
            GapKind.MISSING_INPUT,
            GapSeverity.BLOCKING,
            ["/target_entities/*/health"],
            "A representative scenario needs the life of each monster it "
            "contains. No value is held for any PoE 2 monster, so the "
            "representative suite cannot be written.",
            "Maximum life of each named monster and boss used by a "
            "representative scenario, at a stated area level, monster rarity "
            "and patch, with the capture or catalog row the value was read "
            "from. One value per named entity, not a range for a tier.",
            "An identified catalog row for that monster at that area level "
            "and rarity, from an accepted patch profile, or a controlled "
            "experiment with a known damage figure. A recording's health bar "
            "shows a fraction of an unknown maximum and does not establish "
            "absolute life on its own.",
            ALL_SCENARIO_IDS,
        ),
        _gap(
            "gap-p09-t01-enemy-defenses",
            GapKind.MISSING_INPUT,
            GapSeverity.BLOCKING,
            ["/target_entities/*/defenses"],
            "Life alone does not fix time to kill. Mitigation decides how much "
            "of a hit lands, and no mitigation value is held for any monster.",
            "Per named monster at a stated area level and patch: elemental and "
            "chaos resistance values, armour, evasion, and any ailment "
            "threshold the scenario's completion depends on, each with the "
            "catalog row or capture it came from.",
            "Catalog export from an accepted patch profile, or a measured "
            "damage-taken comparison against a known hit value.",
            ALL_SCENARIO_IDS,
        ),
        _gap(
            "gap-p09-t01-encounter-density",
            GapKind.MISSING_INPUT,
            GapSeverity.BLOCKING,
            ["/target_entities/*/count", "/target_entities/*/position"],
            "The dense and spread shapes differ only by how many monsters "
            "stand together and how far apart the packs are. Neither count nor "
            "spacing is held for any PoE 2 area.",
            "For one named map layout at a stated area level: monsters per "
            "pack, packs per completed run, and the distance between "
            "successive packs along the route an operator actually walked, "
            "with the unit that distance is expressed in.",
            "Operator recording of a full run of one named map, with the route "
            "and the pack positions marked, repeated enough times to state a "
            "spread rather than one layout roll.",
            CLEAR_IDS,
        ),
        _gap(
            "gap-p09-t01-spatial-unit",
            GapKind.UNRESOLVED_ENTITY,
            GapSeverity.BLOCKING,
            ["/target_entities/*/position/unit",
             "/target_entities/*/position/conversion_evidence_ids",
             "/spatial_model_id"],
            "contracts.md forbids assuming a PoB radius is metres. Until the "
            "unit a position is expressed in is tied to the unit a skill's "
            "area of effect is expressed in, no distance in a representative "
            "scenario can be compared with a skill's reach.",
            "The conversion between the distance unit the pinned PoB catalog "
            "uses for skill area and radius and the distance unit a measured "
            "encounter route is recorded in, with the two measurements that "
            "establish the ratio.",
            "A controlled measurement: one skill of known declared radius used "
            "against a target at a measured distance, repeated at two "
            "distances so the ratio is over-determined.",
            CLEAR_IDS,
        ),
        _gap(
            "gap-p09-t01-movement-model",
            GapKind.UNSUPPORTED_RULE,
            GapSeverity.BLOCKING,
            ["/movement_model_id", "/initial_state/route"],
            "No pathfinding is implemented. scenarios.md permits a replayed "
            "route and action-time model instead, but the replayed route must "
            "come from a recorded run and no run has been recorded.",
            "For one named map layout: the time an operator took on each leg "
            "between packs, with the character's movement speed modifiers at "
            "the time, and whether a movement skill was used on that leg.",
            "Operator recording with per-leg timestamps, plus the character "
            "sheet that states movement speed for the same attempt.",
            CLEAR_IDS,
        ),
        _gap(
            "gap-p09-t01-incoming-damage",
            GapKind.MISSING_INPUT,
            GapSeverity.BLOCKING,
            ["/incoming_damage_model_id", "/event_schedule"],
            "scenarios.md requires each representative scenario to specify its "
            "damage input. Static life and resistance totals do not certify "
            "survival, and no damage event has been recorded.",
            "A timestamped list of damage events taken during one named "
            "encounter: time, damage type, magnitude before mitigation where "
            "readable, and whether the event was avoidable, for a character "
            "whose defensive sheet is captured in the same attempt.",
            "Operator recording of the encounter with a combat log or a "
            "frame-accurate life bar, plus the character sheet for that "
            "attempt.",
            ALL_SCENARIO_IDS,
        ),
        _gap(
            "gap-p09-t01-boss-windows",
            GapKind.MISSING_INPUT,
            GapSeverity.BLOCKING,
            ["/target_entities/*/targetable_windows", "/event_schedule"],
            "The boss shapes differ by whether the target can be hit "
            "continuously. No phase or invulnerability timing is held for any "
            "PoE 2 boss.",
            "For one named boss: the start and end time of every phase in "
            "which it cannot be damaged, measured from encounter start, across "
            "at least five recorded attempts, and whether each window is "
            "triggered by elapsed time or by remaining life.",
            "Operator recordings of repeated attempts at the same named boss, "
            "timestamped from the same start event.",
            BOSS_IDS,
        ),
        _gap(
            "gap-p09-t01-initial-resources",
            GapKind.MISSING_INPUT,
            GapSeverity.BLOCKING,
            ["/initial_state"],
            "A scenario starts the character in a declared state. Which "
            "resources a character actually holds when an encounter begins, "
            "under the solo softcore default of product.md, is not recorded.",
            "For the declared starting condition of each shape: life, mana, "
            "energy shield, charges and flask or charge-equivalent state at "
            "the instant the completion clock starts, for a named build on a "
            "named encounter.",
            "Operator recording that shows the resource bars at the start "
            "event, together with the rule the operator used to decide when "
            "the encounter started.",
            ALL_SCENARIO_IDS,
        ),
        _gap(
            "gap-p09-t01-preparation-allowance",
            GapKind.MISSING_INPUT,
            GapSeverity.RANKING_SENSITIVE,
            ["/allowed_preparation"],
            "Legal preparation decides how much of a build's power is "
            "available at the start event. Which pre-encounter actions persist "
            "into the encounter, and for how long, is not recorded.",
            "For each action an operator may take before the start event: "
            "whether its effect is still active at the start event, its "
            "remaining duration there, and the time the action itself cost, "
            "for a named build on a named encounter.",
            "Operator recording of the preparation sequence and the start "
            "event in one unbroken capture.",
            ALL_SCENARIO_IDS,
        ),
        _gap(
            "gap-p09-t01-duration-limit",
            GapKind.MISSING_INPUT,
            GapSeverity.RANKING_SENSITIVE,
            ["/duration_limit_s"],
            "A timeout is a failure verdict, so its value decides which builds "
            "are reported as failing. No observed distribution of completion "
            "times exists to place it against.",
            "Completion times for the chosen encounter across the reference "
            "configurations, including attempts that failed, so a limit can be "
            "set above the slowest intended-to-pass attempt rather than "
            "chosen.",
            "P09-T02 observation import, once the reference configurations "
            "exist.",
            ALL_SCENARIO_IDS,
        ),
        _gap(
            "gap-p09-t01-survival-threshold",
            GapKind.MISSING_INPUT,
            GapSeverity.RANKING_SENSITIVE,
            ["/survival_gates", "/resource_gates"],
            "Death equals zero is definitional and needs no evidence. Any "
            "stricter gate, such as a minimum life fraction held through the "
            "encounter, is a threshold that would have to be fitted, and "
            "fitting is forbidden before reviewer acceptance.",
            "The lowest life, energy shield and resource level observed during "
            "successful attempts at the chosen encounter, per reference "
            "configuration, so a margin gate can be justified or shown "
            "unjustifiable.",
            "P09-T02 observation import, reading the minimum from recorded "
            "attempts rather than from a sheet.",
            ALL_SCENARIO_IDS,
        ),
        _gap(
            "gap-p09-t01-reference-build",
            GapKind.MISSING_INPUT,
            GapSeverity.BLOCKING,
            ["/reference_build_id", "/reference_result_id"],
            "scenarios.md requires one approved reference build and result per "
            "scenario, and every ratio in the ranking formula divides by that "
            "reference time. No legal complete build exists in this "
            "repository, so every reference slot is null and no ratio can be "
            "computed.",
            "One complete legal Huntress configuration per scenario: "
            "equipment with full modifier text, passive allocations, "
            "ascendancy, skill groups with levels, quality and supports, "
            "weapon-set bindings, and the rotation the operator played, plus "
            "the completion time that configuration achieved on that scenario.",
            "A PoB build file or build code the owner exports and supplies as "
            "a local file, imported through P03-T02 local acquisition, "
            "followed by a P09-T02 observation of the same configuration.",
            ALL_SCENARIO_IDS,
        ),
        _gap(
            "gap-p09-t01-build-families",
            GapKind.ACCESS_BLOCKED,
            GapSeverity.BLOCKING,
            ["/reference_build_id"],
            "P09-T01 is asked to propose three Huntress build families from "
            "the source corpus. P03-T01 found no named source that permits "
            "automatic acquisition to this client, so there is no corpus and "
            "no family can be selected without inventing it.",
            "Either a source corpus of imported Huntress builds with their "
            "required mechanics, from a provider whose terms and client "
            "behaviour permit retrieval, or a set of build files the owner "
            "exports by hand, each naming the skills, supports and ascendancy "
            "its family depends on.",
            "P03-T02 local acquisition of owner-supplied build files, or "
            "P03-T03 automatic acquisition once a permitted access route "
            "exists for any provider.",
            ALL_SCENARIO_IDS,
        ),
        _gap(
            "gap-p09-t01-patch-profile",
            GapKind.MISSING_INPUT,
            GapSeverity.BLOCKING,
            ["/patch_profile_id"],
            "The synthetic suite points at a synthetic profile id that is not "
            "an exported PatchProfile. A representative scenario must name a "
            "profile whose compatibility is verified, and the one profile "
            "P02-T02 exported reports compatibility partial.",
            "An exported PatchProfile for the league the measurements are "
            "taken in, whose compatibility is verified rather than partial, "
            "and whose catalog hash matches the catalog the measured builds "
            "were evaluated against.",
            "P02-T02 catalog export against the live patch, plus the D03 "
            "patch identity decision.",
            ALL_SCENARIO_IDS,
        ),
    ]


# -------------------------------------------------------------- scenarios ===

def _position(x, y):
    return Position(
        x=x,
        y=y,
        unit="synthetic_grid",
        # Empty on purpose: a synthetic grid converts to nothing. The real
        # conversion is gap-p09-t01-spatial-unit.
        conversion_evidence_ids=[],
    )


def _survival_gate(scenario_id):
    """Death is a failure (scenarios.md). Definitional, not a fitted value."""
    return Gate(
        gate_id="%s-no-death" % scenario_id,
        metric_path="/metrics/survival/deaths",
        comparison="eq",
        value=0.0,
    )


def _resource_gate(scenario_id):
    """An empty pool is downtime, not illegality (scenarios.md). The only
    bound this task can state is that a pool never goes negative."""
    return Gate(
        gate_id="%s-resource-non-negative" % scenario_id,
        metric_path="/metrics/minimum_resources/synthetic_charges",
        comparison="gte",
        value=0.0,
    )


def _scenario(scenario_id, category, shape, targets, initial_state, events,
              duration_limit_s, completion, movement_model_id):
    state = dict(SYNTHETIC_MARK)
    state["shape"] = shape
    state.update(initial_state)
    return ScenarioSpec(
        schema_version=SCHEMA_VERSION,
        record_id=scenario_id,
        created_at=CREATED_AT,
        provenance_ids=[PROTOCOL_ID],
        scenario_id=scenario_id,
        version="1",
        category=category,
        kind=ScenarioKind.SYNTHETIC,
        patch_profile_id=PATCH_PROFILE_ID,
        target_entities=targets,
        initial_state=state,
        event_schedule=events,
        spatial_model_id="synthetic_declared_positions_v1",
        movement_model_id=movement_model_id,
        duration_limit_s=duration_limit_s,
        completion_condition=completion,
        incoming_damage_model_id="synthetic_no_incoming_damage_v1",
        allowed_preparation=AllowedPreparation(
            action_ids=["synthetic_prepare"], duration_limit_s=5.0),
        rng_seeds=[1],
        reference_build_id=None,
        reference_result_id=None,
        capability_floor_ratio=0.50,
        survival_gates=[_survival_gate(scenario_id)],
        resource_gates=[_resource_gate(scenario_id)],
        evidence_ids=[],
        # No encounter evaluator exists yet, so nothing has checked these
        # against one.
        validation_status=RuleValidation.UNTESTED,
    )


def build_scenarios():
    #: clear_dense - one cluster, no travel. 20 x 100 = 2000 synthetic health.
    dense_targets = [
        TargetEntity(
            entity_id="synthetic_dense_pack",
            catalog_entity_id=None,
            count=20,
            health=100.0,
            defenses={"synthetic": True, "flat_damage_reduction": 0.0},
            position=_position(0.0, 0.0),
            targetable_windows=[TimeWindow(start_s=0.0, end_s=60.0)],
        )
    ]
    dense = _scenario(
        "p09-syn-clear-dense",
        ScenarioCategory.CLEAR,
        "clear_dense",
        dense_targets,
        {
            "character_position": {"x": 0.0, "y": 0.0, "unit": "synthetic_grid"},
            "character_resources": {"synthetic_charges": 0.0},
            "route": {"leg_durations_s": [], "note": "one cluster, no travel"},
        },
        [ScheduledEvent(event_id="synthetic-dense-spawn", at_s=0.0,
                        kind="synthetic_spawn", payload={"entity_id": "synthetic_dense_pack"})],
        60.0,
        CompletionCondition(kind="all_targets_dead", parameters={}),
        "synthetic_stationary_v1",
    )

    #: clear_spread - the same 2000 synthetic health in four packs, with three
    #: declared 4.0 s route legs between them. Replayed route, per scenarios.md.
    spread_targets = [
        TargetEntity(
            entity_id="synthetic_spread_pack_%d" % i,
            catalog_entity_id=None,
            count=5,
            health=100.0,
            defenses={"synthetic": True, "flat_damage_reduction": 0.0},
            position=_position(float(i) * 40.0, 0.0),
            targetable_windows=[TimeWindow(start_s=0.0, end_s=90.0)],
        )
        for i in range(4)
    ]
    spread = _scenario(
        "p09-syn-clear-spread",
        ScenarioCategory.CLEAR,
        "clear_spread",
        spread_targets,
        {
            "character_position": {"x": 0.0, "y": 0.0, "unit": "synthetic_grid"},
            "character_resources": {"synthetic_charges": 0.0},
            "route": {
                "leg_durations_s": [4.0, 4.0, 4.0],
                "note": "replayed route: three legs between four packs, "
                        "charged whether or not the evaluator models movement",
            },
        },
        [
            ScheduledEvent(
                event_id="synthetic-spread-spawn-%d" % i,
                at_s=0.0,
                kind="synthetic_spawn",
                payload={"entity_id": "synthetic_spread_pack_%d" % i},
            )
            for i in range(4)
        ],
        90.0,
        CompletionCondition(kind="all_targets_dead", parameters={}),
        "synthetic_replay_route_v1",
    )

    #: boss_short - one target, always hittable.
    short_targets = [
        TargetEntity(
            entity_id="synthetic_boss_short",
            catalog_entity_id=None,
            count=1,
            health=10000.0,
            defenses={"synthetic": True, "flat_damage_reduction": 0.0},
            position=_position(0.0, 0.0),
            targetable_windows=[TimeWindow(start_s=0.0, end_s=60.0)],
        )
    ]
    boss_short = _scenario(
        "p09-syn-boss-short",
        ScenarioCategory.BOSS,
        "boss_short",
        short_targets,
        {
            "character_position": {"x": 0.0, "y": 0.0, "unit": "synthetic_grid"},
            "character_resources": {"synthetic_charges": 0.0},
            "route": {"leg_durations_s": [], "note": "stationary single target"},
        },
        [ScheduledEvent(event_id="synthetic-short-start", at_s=0.0,
                        kind="synthetic_encounter_start", payload={})],
        60.0,
        CompletionCondition(kind="target_dead",
                            parameters={"entity_id": "synthetic_boss_short"}),
        "synthetic_stationary_v1",
    )

    #: boss_sustained - four times the health and two 15.0 s windows in which
    #: the target cannot be hit, so 270.0 s of the 300.0 s limit are usable.
    sustained_targets = [
        TargetEntity(
            entity_id="synthetic_boss_sustained",
            catalog_entity_id=None,
            count=1,
            health=40000.0,
            defenses={"synthetic": True, "flat_damage_reduction": 0.0},
            position=_position(0.0, 0.0),
            targetable_windows=[
                TimeWindow(start_s=0.0, end_s=60.0),
                TimeWindow(start_s=75.0, end_s=150.0),
                TimeWindow(start_s=165.0, end_s=300.0),
            ],
        )
    ]
    boss_sustained = _scenario(
        "p09-syn-boss-sustained",
        ScenarioCategory.BOSS,
        "boss_sustained",
        sustained_targets,
        {
            "character_position": {"x": 0.0, "y": 0.0, "unit": "synthetic_grid"},
            "character_resources": {"synthetic_charges": 0.0},
            "route": {"leg_durations_s": [], "note": "stationary single target"},
        },
        [
            ScheduledEvent(event_id="synthetic-sustained-start", at_s=0.0,
                           kind="synthetic_encounter_start", payload={}),
            ScheduledEvent(event_id="synthetic-untargetable-1-begin", at_s=60.0,
                           kind="synthetic_untargetable_begin", payload={}),
            ScheduledEvent(event_id="synthetic-untargetable-1-end", at_s=75.0,
                           kind="synthetic_untargetable_end", payload={}),
            ScheduledEvent(event_id="synthetic-untargetable-2-begin", at_s=150.0,
                           kind="synthetic_untargetable_begin", payload={}),
            ScheduledEvent(event_id="synthetic-untargetable-2-end", at_s=165.0,
                           kind="synthetic_untargetable_end", payload={}),
        ],
        300.0,
        CompletionCondition(kind="target_dead",
                            parameters={"entity_id": "synthetic_boss_sustained"}),
        "synthetic_stationary_v1",
    )

    return [dense, spread, boss_short, boss_sustained]


# -------------------------------------------------------------- rotations ===

def _cmp(operator, path, value):
    return Predicate(operator=operator, operands=ABSENT, path=path, value=value)


def build_rotations():
    clear = RotationPolicy(
        schema_version=SCHEMA_VERSION,
        record_id="p09-syn-rotation-clear",
        created_at=CREATED_AT,
        provenance_ids=[PROTOCOL_ID],
        rotation_id="p09-syn-rotation-clear",
        version="1",
        name="Synthetic clear policy",
        category=ScenarioCategory.CLEAR,
        rules=[
            RotationRule(
                rule_index=0,
                action_id="synthetic-clear-area",
                action=ActionKind.USE_SKILL,
                skill_id="synthetic_area_skill",
                target_selector="largest_cluster",
                weapon_set_id="synthetic_set_a",
                predicate=_cmp(PredicateOperator.GTE,
                               "/state/selected_cluster/living_count", 2),
            ),
            RotationRule(
                rule_index=1,
                action_id="synthetic-clear-single",
                action=ActionKind.USE_SKILL,
                skill_id="synthetic_single_skill",
                target_selector="nearest_living",
                weapon_set_id="synthetic_set_a",
                predicate=_cmp(PredicateOperator.GTE,
                               "/state/living_targets_in_range", 1),
            ),
            RotationRule(
                rule_index=2,
                action_id="synthetic-clear-advance",
                action=ActionKind.MOVE,
                skill_id=None,
                target_selector="next_route_leg",
                weapon_set_id=None,
                predicate=_cmp(PredicateOperator.EQ,
                               "/state/living_targets_in_range", 0),
            ),
        ],
    )

    boss = RotationPolicy(
        schema_version=SCHEMA_VERSION,
        record_id="p09-syn-rotation-boss",
        created_at=CREATED_AT,
        provenance_ids=[PROTOCOL_ID],
        rotation_id="p09-syn-rotation-boss",
        version="1",
        name="Synthetic boss policy",
        category=ScenarioCategory.BOSS,
        rules=[
            RotationRule(
                rule_index=0,
                action_id="synthetic-boss-spend",
                action=ActionKind.USE_SKILL,
                skill_id="synthetic_spender_skill",
                target_selector="primary_target",
                weapon_set_id="synthetic_set_a",
                predicate=Predicate(
                    operator=PredicateOperator.ALL,
                    operands=[
                        _cmp(PredicateOperator.EQ, "/state/primary_target/targetable", True),
                        _cmp(PredicateOperator.GTE, "/state/resources/synthetic_charges", 3),
                    ],
                    path=ABSENT,
                    value=ABSENT,
                ),
            ),
            RotationRule(
                rule_index=1,
                action_id="synthetic-boss-build",
                action=ActionKind.USE_SKILL,
                skill_id="synthetic_builder_skill",
                target_selector="primary_target",
                weapon_set_id="synthetic_set_a",
                predicate=_cmp(PredicateOperator.EQ,
                               "/state/primary_target/targetable", True),
            ),
            RotationRule(
                rule_index=2,
                action_id="synthetic-boss-wait",
                action=ActionKind.WAIT,
                skill_id=None,
                target_selector="none",
                weapon_set_id=None,
                predicate=_cmp(PredicateOperator.EQ,
                               "/state/primary_target/targetable", False),
            ),
        ],
    )
    return [clear, boss]


# ----------------------------------------------------------------- oracle ===

def build_oracle(scenarios):
    """Hand-computable totals a future evaluator must reproduce.

    Arithmetic over the synthetic constants only. It establishes nothing about
    PoE 2 and it is not a performance expectation.
    """
    out = {}
    for s in scenarios:
        total_health = sum(t.health * t.count for t in s.target_entities)
        targetable = sum(
            w.end_s - w.start_s
            for t in s.target_entities for w in t.targetable_windows
        ) / max(len(s.target_entities), 1)
        legs = s.initial_state["route"]["leg_durations_s"]
        out[s.scenario_id] = {
            "total_target_health": total_health,
            "route_time_s": float(sum(legs)),
            "horizon_s": s.duration_limit_s,
            "horizon_targetable_time_s": targetable,
            "horizon_untargetable_time_s": round(
                s.duration_limit_s - targetable, 6),
            "preparation_limit_s": s.allowed_preparation.duration_limit_s,
            "duration_limit_s": s.duration_limit_s,
        }
    out["derivation"] = (
        "total_target_health is health x count summed over the declared "
        "entities. route_time_s is the sum of the declared replayed route "
        "legs. The two horizon_ figures describe the whole configured "
        "horizon: how much of duration_limit_s the declared windows make "
        "targetable and how much they do not. They are workload metadata, "
        "not a per-evaluation elapsed time. An evaluation's elapsed time runs "
        "from scenario start to completion and stops there, so only the "
        "windows intersecting [start, completion] are part of it; a kill "
        "before the first untargetable window elapses none of it. Both clear "
        "shapes carry the same 2000.0 total health so that a difference "
        "between them is caused by the route and the cluster size and by "
        "nothing else."
    )
    out["worked_examples"] = WORKED_EXAMPLES
    return out


#: Hand-calculated completion times for ``p09-syn-boss-sustained``, whose
#: declared windows are [0, 60], [75, 150] and [165, 300] against 40,000
#: health. Each assumes a hypothetical constant damage rate applied only while
#: the target is targetable. They are arithmetic over invented constants and
#: say nothing about any build or about PoE 2; they exist so the difference
#: between a horizon total and an elapsed time is checkable rather than
#: asserted.
WORKED_EXAMPLES = [
    {
        "scenario_id": "p09-syn-boss-sustained",
        "hypothetical_damage_per_s": 2000.0,
        "completion_time_s": 20.0,
        "untargetable_time_elapsed_s": 0.0,
        "windows_intersecting_completion": 1,
        "outcome": "completed",
        "note": "Dies inside the first targetable window. None of the "
                "horizon's 30 s of untargetable time elapses, so none of it "
                "may be added to the elapsed time.",
    },
    {
        "scenario_id": "p09-syn-boss-sustained",
        "hypothetical_damage_per_s": 400.0,
        "completion_time_s": 115.0,
        "untargetable_time_elapsed_s": 15.0,
        "windows_intersecting_completion": 2,
        "outcome": "completed",
        "note": "24,000 in [0, 60], then 16,000 more from 75 s at 400/s. One "
                "untargetable window elapsed.",
    },
    {
        "scenario_id": "p09-syn-boss-sustained",
        "hypothetical_damage_per_s": 250.0,
        "completion_time_s": 190.0,
        "untargetable_time_elapsed_s": 30.0,
        "windows_intersecting_completion": 3,
        "outcome": "completed",
        "note": "15,000 in [0, 60], 18,750 in [75, 150], the remaining 6,250 "
                "from 165 s at 250/s. Both untargetable windows elapsed.",
    },
    {
        "scenario_id": "p09-syn-boss-sustained",
        "hypothetical_damage_per_s": 1.0,
        "completion_time_s": None,
        "untargetable_time_elapsed_s": 30.0,
        "windows_intersecting_completion": 3,
        "outcome": "timed_out",
        "note": "270 damage over the whole targetable horizon against 40,000 "
                "health. A correct evaluator times out here. That is a failed "
                "evaluation, which scenarios.md permits, not an operational "
                "error and not evidence the evaluator is wrong.",
    },
]


# ------------------------------------------------------------------ fields ==

#: One row per ScenarioSpec field. ``basis`` says where the synthetic suite's
#: value comes from; ``representative_status`` says what the same field would
#: be in a representative scenario today. A row with representative_status
#: ``unresolved_input`` must name at least one gap, and a row with any other
#: status must name none. tests/unit/test_p09_t01_protocol.py enforces both.
FIELD_PLAN = [
    ("scenario_id", "specification",
     "docs/specs/scenarios.md: the four shapes clear_dense, clear_spread, "
     "boss_short, boss_sustained", "sourced", []),
    ("version", "product_default",
     "docs/specs/scenarios.md: a reference or scenario version change starts a "
     "separate aggregate identity", "sourced", []),
    ("category", "specification",
     "docs/specs/contracts.md ScenarioCategory; two clear and two boss per "
     "docs/specs/product.md first release", "sourced", []),
    ("kind", "specification",
     "docs/specs/scenarios.md: synthetic fixtures implement the shapes first; "
     "representative scenarios are a separate dataset", "sourced", []),
    ("patch_profile_id", "test_constant",
     "A synthetic id. The one real profile P02-T02 exported reports "
     "compatibility partial", "unresolved_input", ["gap-p09-t01-patch-profile"]),
    ("target_entities.count", "test_constant",
     "20 in one pack, and 4 packs of 5, so both clear shapes carry equal total "
     "health", "unresolved_input", ["gap-p09-t01-encounter-density"]),
    ("target_entities.health", "test_constant",
     "100.0 per minion and 10000.0 / 40000.0 per boss, chosen round so the "
     "oracle is checkable by hand", "unresolved_input", ["gap-p09-t01-enemy-health"]),
    ("target_entities.defenses", "test_constant",
     "Zero mitigation, declared synthetic, so the synthetic suite tests the "
     "encounter loop and not a mitigation model", "unresolved_input",
     ["gap-p09-t01-enemy-defenses"]),
    ("target_entities.position", "test_constant",
     "Declared coordinates on a synthetic_grid that converts to nothing",
     "unresolved_input", ["gap-p09-t01-encounter-density", "gap-p09-t01-spatial-unit"]),
    ("target_entities.targetable_windows", "test_constant",
     "boss_sustained withholds the target for two 15.0 s windows; the other "
     "three shapes are continuously targetable", "unresolved_input",
     ["gap-p09-t01-boss-windows"]),
    ("initial_state", "test_constant",
     "Character at the origin with zero synthetic charges and the declared "
     "route", "unresolved_input", ["gap-p09-t01-initial-resources"]),
    ("event_schedule", "test_constant",
     "Spawn at 0.0 s, and the two untargetable windows of boss_sustained",
     "unresolved_input", ["gap-p09-t01-boss-windows", "gap-p09-t01-incoming-damage"]),
    ("spatial_model_id", "specification",
     "docs/specs/scenarios.md permits declared positions when pathfinding is "
     "not implemented, with a stated applicability limit", "sourced", []),
    ("movement_model_id", "specification",
     "docs/specs/scenarios.md: an explicit replayed route and action-time "
     "model, with a declared applicability limit", "unresolved_input",
     ["gap-p09-t01-movement-model"]),
    ("duration_limit_s", "test_constant",
     "60.0, 90.0, 60.0 and 300.0 s. A limit bounds the horizon; it is not a "
     "performance expectation, and a timeout under it is a valid failed "
     "evaluation rather than proof the evaluator is broken",
     "unresolved_input", ["gap-p09-t01-duration-limit"]),
    ("completion_condition", "specification",
     "docs/specs/scenarios.md: clear shapes finish a fixed enemy and route "
     "workload; boss shapes measure start to kill", "sourced", []),
    ("incoming_damage_model_id", "test_constant",
     "No incoming damage, declared synthetic. A survival gate over zero damage "
     "is a plumbing test, not a survival claim", "unresolved_input",
     ["gap-p09-t01-incoming-damage"]),
    ("allowed_preparation", "product_default",
     "docs/specs/product.md: one configuration, no party buffs, no outside "
     "resource generation, weapon-set changes allowed when represented and "
     "timed. The 5.0 s limit itself is a test constant", "unresolved_input",
     ["gap-p09-t01-preparation-allowance"]),
    ("rng_seeds", "product_default",
     "docs/specs/scenarios.md: the default suite is deterministic, so one "
     "fixed seed", "sourced", []),
    ("reference_build_id", "unresolved",
     "No legal complete build exists in this repository", "unresolved_input",
     ["gap-p09-t01-reference-build", "gap-p09-t01-build-families"]),
    ("reference_result_id", "unresolved",
     "No reference evaluation has been run, because there is no reference "
     "build and no evaluator", "unresolved_input",
     ["gap-p09-t01-reference-build"]),
    ("capability_floor_ratio", "specification",
     "docs/specs/scenarios.md: every scenario ratio at least 0.50, a "
     "provisional product setting", "sourced", []),
    ("survival_gates", "specification",
     "docs/specs/scenarios.md: death and timeout are failures. Deaths equal "
     "zero is definitional; any stricter margin is not", "unresolved_input",
     ["gap-p09-t01-survival-threshold"]),
    ("resource_gates", "specification",
     "docs/specs/scenarios.md: an empty pool is downtime, not illegality, and "
     "no arbitrary minimum uptime is allowed. A pool never going negative is "
     "the only bound stated here", "unresolved_input",
     ["gap-p09-t01-survival-threshold"]),
    ("evidence_ids", "unresolved",
     "Empty. A synthetic fixture cites no evidence because it is not evidence",
     "unresolved_input", ["gap-p09-t01-incoming-damage", "gap-p09-t01-enemy-health"]),
    ("validation_status", "specification",
     "docs/specs/contracts.md RuleValidation. untested, because no encounter "
     "evaluator exists to check these records against", "sourced", []),
]


def build_field_plan(gap_ids):
    rows = []
    for field, basis, source, status, gaps in FIELD_PLAN:
        unknown = [g for g in gaps if g not in gap_ids]
        if unknown:
            raise SystemExit("field %s names unknown gaps %s" % (field, unknown))
        rows.append({
            "field": field,
            "applies_to": "all four workloads",
            "synthetic_basis": basis,
            "source_or_reason": source,
            "representative_status": status,
            "gap_ids": gaps,
        })
    return rows


# ------------------------------------------------------------------ output ==

def _dump(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=False) + "\n"
    path.write_text(text, encoding="utf-8", newline="\n")
    return hashlib.sha256(text.encode("utf-8")).hexdigest(), len(text.encode("utf-8"))


def main() -> int:
    scenarios = build_scenarios()
    rotations = build_rotations()
    gaps = build_gaps()

    failures = []
    for record in list(scenarios) + list(rotations) + list(gaps):
        report = validate_record(record)
        if report.errors:
            failures.append((record.record_id, [str(e) for e in report.errors]))
    if failures:
        for rid, errs in failures:
            print("INVALID %s" % rid)
            for err in errs:
                print("   %s" % err)
        return 1

    fixture = {
        "kind": "synthetic",
        "purpose": (
            "The P09-T01 synthetic encounter suite: four ScenarioSpec records "
            "in the four shapes of docs/specs/scenarios.md, two RotationPolicy "
            "records, and the DataGap records naming every input a "
            "representative suite still needs. It exists so P07 can be built "
            "and tested before any encounter has been measured."
        ),
        "not_a_claim": NOT_A_CLAIM,
        "schema_version": SCHEMA_VERSION,
        "suite_id": SUITE_ID,
        "protocol": "benchmarks/%s/protocol.md" % SUITE_ID,
        "generated_by": "scripts/p09_t01_suite.py",
        "records": {
            "scenario_spec": [to_jsonable(s) for s in scenarios],
            "rotation_policy": [to_jsonable(r) for r in rotations],
            "data_gap": [to_jsonable(g) for g in gaps],
        },
        "oracle": build_oracle(scenarios),
    }
    fixture_sha, fixture_bytes = _dump(FIXTURE_PATH, fixture)

    gap_ids = [g.gap_id for g in gaps]
    suite = {
        "suite_id": SUITE_ID,
        "kind": "synthetic",
        "schema_version": SCHEMA_VERSION,
        "not_a_claim": NOT_A_CLAIM,
        "protocol": "benchmarks/%s/protocol.md" % SUITE_ID,
        "scenario_source": {
            "path": "tests/fixtures/combat/p09_synthetic_suite.v1.json",
            "sha256": fixture_sha,
            "bytes": fixture_bytes,
        },
        "scenarios": [
            {
                "scenario_id": s.scenario_id,
                "version": s.version,
                "category": s.category.value,
                "shape": s.initial_state["shape"],
                "scenario_hash": scenario_hash(s),
                "rotation_id": ("p09-syn-rotation-clear"
                                if s.category is ScenarioCategory.CLEAR
                                else "p09-syn-rotation-boss"),
                "reference_build_id": s.reference_build_id,
                "reference_result_id": s.reference_result_id,
                "reference_status": "unresolved",
                "reference_gap_ids": ["gap-p09-t01-reference-build",
                                      "gap-p09-t01-build-families"],
            }
            for s in scenarios
        ],
        "baseline_suite_hash": baseline_suite_hash(scenarios),
        "baseline_suite_note": (
            "Computed over four scenarios whose reference_build_id and "
            "reference_result_id are both null. It freezes the scenario "
            "definitions, not a baseline. Freezing a reference later changes "
            "this hash and starts a separate leaderboard, which is what "
            "docs/specs/scenarios.md requires."
        ),
        "open_gaps": gap_ids,
        "usable_for": [
            "exercising a P07 encounter loop end to end",
            "regression tests over the ranking formula in docs/specs/scenarios.md",
            "checking that untargetable time is not billed as damage time",
            "checking that a replayed route leg is charged",
        ],
        "not_usable_for": [
            "any statement about PoE 2 clear speed or boss kill time",
            "calibrating or fitting any constant",
            "ranking real builds",
            "a D04 practical claim",
        ],
    }
    _dump(SUITE_PATH, suite)

    fields = {
        "task": "P09-T01",
        "suite_id": SUITE_ID,
        "evidence_class": "synthetic",
        "not_a_claim": NOT_A_CLAIM,
        "statement": (
            "Every ScenarioSpec field, with where the synthetic suite's value "
            "comes from and what the same field is in a representative "
            "scenario today. A representative_status of unresolved_input "
            "names the gaps that would have to close first."
        ),
        "fields": build_field_plan(set(gap_ids)),
        "representative_suite_expressibility": (
            "A representative ScenarioSpec cannot be written today even as a "
            "skeleton: duration_limit_s, capability_floor_ratio and the "
            "entity health fields are required and non-nullable in "
            "docs/specs/contracts.md, so an unresolved value cannot be stored "
            "as null. The unresolved inputs therefore live in this file and in "
            "the DataGap records, not in a half-filled scenario record."
        ),
    }
    _dump(FIELDS_PATH, fields)

    print("suite %s" % SUITE_ID)
    print("  fixture   %s  sha256 %s" % (FIXTURE_PATH.relative_to(REPO_ROOT), fixture_sha))
    print("  manifest  %s" % SUITE_PATH.relative_to(REPO_ROOT))
    print("  fields    %s" % FIELDS_PATH.relative_to(REPO_ROOT))
    print("  scenarios %d, rotations %d, open gaps %d"
          % (len(scenarios), len(rotations), len(gaps)))
    print("  baseline_suite_hash %s" % suite["baseline_suite_hash"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
