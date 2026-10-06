"""What a legality verdict is made of (P02-T03).

Three things leave the validator, and the contract keeps them apart:

* **violations**: a rule in the patch profile is broken. The build is illegal
  and the finding names the rule, the field and the value;
* **unknowns**: the rule needed to decide is missing from the profile, or the
  input needed to apply it was not supplied. Each one cites the ``DataGap``
  that says what to collect. An unknown is never an acceptance;
* **constraints**: the derived point and resource numbers, each with what it
  was measured against, or ``None`` when nothing could be derived.

The overall verdict is ``illegal`` if anything was violated, ``unknown`` if
anything could not be decided, and ``legal`` only when every declared check
answered ``legal``. Attribute and Spirit alone cannot produce that verdict:
they are two checks out of eighteen, and the list is explicit here so nobody
has to infer which checks a verdict rests on.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable, Sequence

from ...domain.enums import Legality
from ...domain.records import DataGap

#: Bumped when a check changes what it decides or how it decides it.
VALIDATOR_VERSION = "p02-t03.0"

# -- the declared checks ------------------------------------------------------

CHECK_CLASS = "class_membership"
CHECK_ASCENDANCY = "ascendancy_membership"
CHECK_LEVEL = "character_level"
CHECK_PASSIVE_BUDGET = "passive_point_budget"
CHECK_ASCENDANCY_BUDGET = "ascendancy_point_budget"
CHECK_CONNECTIVITY = "passive_connectivity"
CHECK_CHOICES = "passive_choices"
CHECK_SOCKETED = "passive_socketed_entities"
CHECK_SLOTS = "equipment_slots"
CHECK_HANDS = "equipment_hands"
CHECK_ITEM_REQUIREMENTS = "item_requirements"
CHECK_ITEM_CONSTRUCTION = "item_construction"
CHECK_SKILLS = "skill_restrictions"
CHECK_SUPPORTS = "support_restrictions"
CHECK_GEM_LEVELS = "gem_levels"
CHECK_RESERVATION = "reservation_resources"
CHECK_WEAPON_SETS = "weapon_set_rules"
CHECK_IMPORT = "post_import_verification"

#: Every check that must answer ``legal`` before the build is legal. Declared
#: as one list so a caller can see that passing two of them decides nothing.
DECLARED_CHECKS: tuple[str, ...] = (
    CHECK_CLASS,
    CHECK_ASCENDANCY,
    CHECK_LEVEL,
    CHECK_PASSIVE_BUDGET,
    CHECK_ASCENDANCY_BUDGET,
    CHECK_CONNECTIVITY,
    CHECK_CHOICES,
    CHECK_SOCKETED,
    CHECK_SLOTS,
    CHECK_HANDS,
    CHECK_ITEM_REQUIREMENTS,
    CHECK_ITEM_CONSTRUCTION,
    CHECK_SKILLS,
    CHECK_SUPPORTS,
    CHECK_GEM_LEVELS,
    CHECK_RESERVATION,
    CHECK_WEAPON_SETS,
    CHECK_IMPORT,
)


@dataclass(frozen=True, slots=True)
class Finding:
    """One named violation or one named unknown.

    ``evidence_ids`` are the rule's own citations, so a violation can be
    traced to the upstream line it was read from. ``gap_ids`` are the gaps an
    unknown cites. A violation carries no gap and an unknown carries no
    evidence; nothing here mixes the two.
    """

    check_id: str
    code: str
    message: str
    rule_id: str | None = None
    field_paths: tuple[str, ...] = ()
    subject_ids: tuple[str, ...] = ()
    evidence_ids: tuple[str, ...] = ()
    gap_ids: tuple[str, ...] = ()

    def to_dict(self) -> dict:
        return {
            "check_id": self.check_id,
            "code": self.code,
            "message": self.message,
            "rule_id": self.rule_id,
            "field_paths": list(self.field_paths),
            "subject_ids": list(self.subject_ids),
            "evidence_ids": list(self.evidence_ids),
            "gap_ids": list(self.gap_ids),
        }


@dataclass(frozen=True, slots=True)
class Constraint:
    """A derived point or resource constraint.

    ``allowed`` is ``None`` when the profile carries no rule for it. That is
    not "unlimited": the decision says ``unknown`` and the gap says what is
    missing.
    """

    name: str
    used: float | None
    allowed: float | None
    decision: Legality
    basis: str
    rule_ids: tuple[str, ...] = ()
    gap_ids: tuple[str, ...] = ()

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "used": self.used,
            "allowed": self.allowed,
            "decision": self.decision.value,
            "basis": self.basis,
            "rule_ids": list(self.rule_ids),
            "gap_ids": list(self.gap_ids),
        }


@dataclass(frozen=True, slots=True)
class CheckOutcome:
    check_id: str
    decision: Legality
    summary: str

    def to_dict(self) -> dict:
        return {"check_id": self.check_id, "decision": self.decision.value,
                "summary": self.summary}


@dataclass(frozen=True, slots=True)
class LegalityReport:
    """The answer of ``LegalityValidator.validate``."""

    build_hash: str
    patch_profile_id: str
    catalog_hash: str
    validator_version: str
    legality: Legality
    checks: tuple[CheckOutcome, ...]
    violations: tuple[Finding, ...]
    unknowns: tuple[Finding, ...]
    constraints: tuple[Constraint, ...]
    #: Gaps the validator raised itself. Gaps it only cited are referenced by
    #: id and belong to whoever recorded them.
    gaps: tuple[DataGap, ...]
    #: Statements about what this verdict does and does not rest on.
    notes: tuple[str, ...]

    # -- reading the answer ------------------------------------------------

    @property
    def violation_codes(self) -> tuple[str, ...]:
        return tuple(finding.code for finding in self.violations)

    @property
    def unknown_codes(self) -> tuple[str, ...]:
        return tuple(finding.code for finding in self.unknowns)

    @property
    def cited_gap_ids(self) -> tuple[str, ...]:
        seen: list[str] = []
        for finding in (*self.violations, *self.unknowns):
            for gap_id in finding.gap_ids:
                if gap_id not in seen:
                    seen.append(gap_id)
        return tuple(seen)

    def decision(self, check_id: str) -> Legality:
        return self.check(check_id).decision

    def check(self, check_id: str) -> CheckOutcome:
        for outcome in self.checks:
            if outcome.check_id == check_id:
                return outcome
        raise LookupError("no check %r in this report" % check_id)

    def findings_for(self, check_id: str) -> tuple[Finding, ...]:
        return tuple(finding for finding in (*self.violations, *self.unknowns)
                     if finding.check_id == check_id)

    def to_dict(self) -> dict:
        return {
            "build_hash": self.build_hash,
            "patch_profile_id": self.patch_profile_id,
            "catalog_hash": self.catalog_hash,
            "validator_version": self.validator_version,
            "legality": self.legality.value,
            "checks": [outcome.to_dict() for outcome in self.checks],
            "violations": [finding.to_dict() for finding in self.violations],
            "unknowns": [finding.to_dict() for finding in self.unknowns],
            "constraints": [constraint.to_dict() for constraint in self.constraints],
            "raised_gap_ids": [gap.gap_id for gap in self.gaps],
            "cited_gap_ids": list(self.cited_gap_ids),
            "notes": list(self.notes),
        }


class ReportBuilder:
    """Collects findings while the checks run, then decides the verdict.

    A check that records nothing is ``legal``; a check that records an unknown
    is ``unknown``; a check that records a violation is ``illegal``, whatever
    else it recorded. A check that was never run at all is ``unknown`` with a
    summary saying so, because a check that did not run is not a pass.
    """

    def __init__(self, *, declared_checks: Sequence[str] = DECLARED_CHECKS) -> None:
        self.declared_checks = tuple(declared_checks)
        self._violations: list[Finding] = []
        self._unknowns: list[Finding] = []
        self._constraints: list[Constraint] = []
        self._gaps: dict[str, DataGap] = {}
        self._summaries: dict[str, str] = {}
        self._ran: set[str] = set()
        self._notes: list[str] = []

    # -- recording ---------------------------------------------------------

    def ran(self, check_id: str, summary: str) -> None:
        self._require_declared(check_id)
        self._ran.add(check_id)
        self._summaries[check_id] = summary

    def violation(self, check_id: str, code: str, message: str, **kwargs) -> None:
        self._require_declared(check_id)
        self._ran.add(check_id)
        self._violations.append(_finding(check_id, code, message, **kwargs))

    def unknown(self, check_id: str, code: str, message: str, *,
                gaps: Iterable[DataGap] = (), **kwargs) -> None:
        self._require_declared(check_id)
        self._ran.add(check_id)
        gap_ids = list(kwargs.pop("gap_ids", ()) or ())
        for gap in gaps:
            self._gaps[gap.gap_id] = gap
            if gap.gap_id not in gap_ids:
                gap_ids.append(gap.gap_id)
        if not gap_ids:
            raise ValueError(
                "unknown %r on check %r cites no gap; an undecidable check "
                "must say what evidence would decide it" % (code, check_id))
        self._unknowns.append(
            _finding(check_id, code, message, gap_ids=tuple(gap_ids), **kwargs))

    def constraint(self, constraint: Constraint) -> None:
        self._constraints.append(constraint)

    def note(self, text: str) -> None:
        if text not in self._notes:
            self._notes.append(text)

    # -- deciding ----------------------------------------------------------

    def decision_for(self, check_id: str) -> Legality:
        if any(f.check_id == check_id for f in self._violations):
            return Legality.ILLEGAL
        if check_id not in self._ran:
            return Legality.UNKNOWN
        if any(f.check_id == check_id for f in self._unknowns):
            return Legality.UNKNOWN
        return Legality.LEGAL

    def outcomes(self) -> tuple[CheckOutcome, ...]:
        out = []
        for check_id in self.declared_checks:
            decision = self.decision_for(check_id)
            summary = self._summaries.get(
                check_id, "the check did not run, so it decided nothing")
            out.append(CheckOutcome(check_id, decision, summary))
        return tuple(out)

    def build(self, *, build_hash: str, patch_profile_id: str,
              catalog_hash: str) -> LegalityReport:
        outcomes = self.outcomes()
        decisions = {outcome.decision for outcome in outcomes}
        if Legality.ILLEGAL in decisions:
            overall = Legality.ILLEGAL
        elif Legality.UNKNOWN in decisions:
            overall = Legality.UNKNOWN
        else:
            overall = Legality.LEGAL
        return LegalityReport(
            build_hash=build_hash,
            patch_profile_id=patch_profile_id,
            catalog_hash=catalog_hash,
            validator_version=VALIDATOR_VERSION,
            legality=overall,
            checks=outcomes,
            violations=tuple(self._violations),
            unknowns=tuple(self._unknowns),
            constraints=tuple(self._constraints),
            gaps=tuple(self._gaps[key] for key in sorted(self._gaps)),
            notes=tuple(self._notes))

    def _require_declared(self, check_id: str) -> None:
        if check_id not in self.declared_checks:
            raise LookupError(
                "%r is not a declared check; add it to DECLARED_CHECKS so a "
                "caller can see what the verdict rests on" % check_id)


def _finding(check_id: str, code: str, message: str, *,
             rule_id: str | None = None,
             field_paths: Sequence[str] = (),
             subject_ids: Sequence[str] = (),
             evidence_ids: Sequence[str] = (),
             gap_ids: Sequence[str] = ()) -> Finding:
    return Finding(check_id=check_id, code=code, message=message,
                   rule_id=rule_id, field_paths=tuple(field_paths),
                   subject_ids=tuple(subject_ids),
                   evidence_ids=tuple(evidence_ids), gap_ids=tuple(gap_ids))
