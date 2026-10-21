"""Rotation policies and their interpreter (P07-T03, first slice).

A ``RotationPolicy`` is a priority list: at each decision the first rule
whose predicate holds is used. Predicates use the finite v1 vocabulary over
named simulator state paths; an unknown operator or path is refused before a
run, never evaluated as text and never skipped.
"""

from __future__ import annotations

from typing import Any, Mapping

from ..domain.absent import ABSENT
from ..domain.enums import ActionKind, ScenarioCategory
from ..domain.records import Predicate, PredicateOperator, RotationPolicy, RotationRule
from ..domain.validation import validate_record

#: State paths this simulator maintains, with their value types.
STATE_PATHS = {
    "state.power_charges": int,
    "buff.charged_staff.active": bool,
}

FLICKER_ID = "FlickerStrikePlayer"
WHIRLING_ID = "WhirlingAssaultPlayer"
STAFF_ID = "ChargedStaffPlayer"

#: Owner rotation, recorded 2026-10-18 (D07 amendment (2) item 1).
SEED_ROTATION_ID = "p07-flicker-seed-rotation"
SEED_ROTATION_SOURCE = ("docs/decisions/D07-flicker-strike-objective.md#amendment-2026-10-18-2: "
                        "whirling assault to generate charges, charged staff, whirling assault to "
                        "generate charges, flicker, whirling, flicker, whirling, flicker, etc until "
                        "charged runs out & repeat")


class PolicyError(ValueError):
    def __init__(self, problems: list[str]):
        self.problems = problems
        super().__init__("; ".join(problems))


def compare(path: str, op: str, value: Any) -> Predicate:
    return Predicate(operator=PredicateOperator(op), operands=ABSENT, path=path, value=value)


def all_of(*operands: Predicate) -> Predicate:
    return Predicate(operator=PredicateOperator.ALL, operands=list(operands),
                     path=ABSENT, value=ABSENT)


def use(index: int, action_id: str, skill_id: str, predicate: Predicate) -> RotationRule:
    return RotationRule(rule_index=index, action_id=action_id, action=ActionKind.USE_SKILL,
                        skill_id=skill_id, target_selector="single_target",
                        weapon_set_id=None, predicate=predicate)


def seed_rotation() -> RotationPolicy:
    """The owner's rotation as a priority policy.

    Whirling Assault supplies the charges (assumed under pob-community-v2).
    With charges held, Charged Staff is pressed when its buff is down,
    otherwise Flicker Strike uses them. The buff check happens at the
    decision after each Whirling Assault, so a buff that expires during
    Whirling Assault is refreshed before the next Flicker Strike.
    """
    return RotationPolicy(
        schema_version=1, record_id=SEED_ROTATION_ID, created_at="2026-10-18T00:00:00Z",
        provenance_ids=[SEED_ROTATION_SOURCE],
        rotation_id=SEED_ROTATION_ID, version="1",
        name="Flicker seed: Whirling Assault, Charged Staff when down, else Flicker Strike",
        category=ScenarioCategory.BOSS,
        rules=[
            use(0, "refresh-charged-staff", STAFF_ID, all_of(
                compare("state.power_charges", "gte", 1),
                compare("buff.charged_staff.active", "eq", False))),
            use(1, "flicker-strike", FLICKER_ID, compare("state.power_charges", "gte", 1)),
            use(2, "whirling-assault", WHIRLING_ID, compare("state.power_charges", "eq", 0)),
        ])


def validate_policy(policy: RotationPolicy, skills: set[str]) -> None:
    """Refuse a policy this simulator cannot run as written."""
    problems = []
    report = validate_record(policy)
    if not report.ok:
        problems += ["%s: %s" % (e.path, e.message) for e in report.errors]
    for rule in policy.rules:
        where = "rule %d (%s)" % (rule.rule_index, rule.action_id)
        if rule.action is not ActionKind.USE_SKILL:
            problems.append("%s: action %s has no timing rule in this simulator"
                            % (where, rule.action.value))
        elif rule.skill_id not in skills:
            problems.append("%s: skill %s has no values" % (where, rule.skill_id))
        problems += ["%s: %s" % (where, p) for p in _check(rule.predicate)]
    if problems:
        raise PolicyError(problems)


def _check(predicate: Predicate) -> list[str]:
    op = predicate.operator
    if op in (PredicateOperator.ALL, PredicateOperator.ANY, PredicateOperator.NOT):
        return [p for operand in predicate.operands for p in _check(operand)]
    if predicate.path not in STATE_PATHS:
        return ["unknown state path %r: unreachable predicate" % predicate.path]
    if not isinstance(predicate.value, STATE_PATHS[predicate.path]):
        return ["path %s compares with %r, expected %s" % (
            predicate.path, predicate.value, STATE_PATHS[predicate.path].__name__)]
    return []


def holds(predicate: Predicate, state: Mapping[str, Any]) -> bool:
    op = predicate.operator
    if op is PredicateOperator.ALL:
        return all(holds(p, state) for p in predicate.operands)
    if op is PredicateOperator.ANY:
        return any(holds(p, state) for p in predicate.operands)
    if op is PredicateOperator.NOT:
        return not holds(predicate.operands[0], state)
    left, right = state[predicate.path], predicate.value
    if op is PredicateOperator.EQ:
        return left == right
    if op is PredicateOperator.NE:
        return left != right
    if op is PredicateOperator.LT:
        return left < right
    if op is PredicateOperator.LTE:
        return left <= right
    if op is PredicateOperator.GT:
        return left > right
    if op is PredicateOperator.GTE:
        return left >= right
    raise PolicyError(["unknown operator %r" % op])


def choose(policy: RotationPolicy, state: Mapping[str, Any]) -> RotationRule | None:
    for rule in policy.rules:
        if holds(rule.predicate, state):
            return rule
    return None
