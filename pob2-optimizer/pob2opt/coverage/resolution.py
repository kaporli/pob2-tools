"""Evidence resolution and patch invalidation (P06-T03).

A gap closes only through a :class:`Resolution` that cites evidence and
supplies a corrected rule or input. Every accepted change creates a new rule
version, so the registry hash changes and coverage reports made earlier no
longer satisfy :func:`pob2opt.coverage.analysis.decide`. History is kept in
order; nothing is overwritten.

Contradicting evidence for a rule that already has an accepted outcome does
not replace it and is not averaged: the rule becomes ``contradicted`` and the
gap reopens as ``conflicting_evidence``.

This is how mechanics work on other branches plugs in: the evidence for Hit
and Run reuse, charge generation or attribution arrives as a resolution of
the rule, not as an edit of the seeded registry.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Any, Iterable, Mapping

from ..domain.enums import GapKind, GapStatus, RuleValidation
from ..domain.records import DataGap
from .registry import MechanicsRegistry, RuleEntry, bump

#: Rule fields a resolution may correct.
RULE_FIELDS = ("support", "validation", "limitations", "tolerances",
               "required_input_paths", "dependency_ids", "implementation_ref", "owner")
#: Entry fields a resolution may correct.
ENTRY_FIELDS = ("satisfied_by", "assignments", "provides_paths", "requires_events",
                "damage_source", "tests", "config_values")


class ResolutionRefused(ValueError):
    pass


@dataclass(frozen=True)
class Resolution:
    resolution_id: str
    gap_id: str
    evidence_ids: tuple[str, ...]
    author: str
    resolved_at: str
    reviewer: str | None = None
    mechanic_id: str | None = None
    rule_changes: Mapping[str, Any] = field(default_factory=dict)
    entry_changes: Mapping[str, Any] = field(default_factory=dict)
    #: JSON pointer to the corrected input value.
    input_values: Mapping[str, Any] = field(default_factory=dict)
    #: The claim the evidence establishes, compared across resolutions of the
    #: same rule to detect contradictions, e.g. ``teleport_satisfies=false``.
    outcome: str = ""


@dataclass(frozen=True)
class EntityDiff:
    """What changed in the catalog between two patch profiles.

    ``changed``: gameplay entities whose data differ (``skill:<id>``,
    ``support:<id>``, ``passive:<id>``, ``config:<var>``).
    ``display_only``: entities whose only change is display text.
    ``unknown_families``: subject prefixes whose impact could not be
    determined; every rule touching them is marked stale.
    """

    changed: frozenset[str] = frozenset()
    display_only: frozenset[str] = frozenset()
    unknown_families: frozenset[str] = frozenset()


@dataclass(frozen=True)
class LedgerEvent:
    kind: str
    at: str
    detail: str
    gap_id: str | None = None
    mechanic_id: str | None = None
    resolution_id: str | None = None


class CoverageLedger:
    """Registry versions, gap states, accepted evidence and their history."""

    def __init__(self, registry: MechanicsRegistry, gaps: Iterable[DataGap] = ()):
        self.registry = registry
        self.gaps: dict[str, DataGap] = {g.gap_id: g for g in gaps}
        self.history: list[LedgerEvent] = []
        self.accepted: dict[str, list[Resolution]] = {}
        self.inputs: dict[str, Any] = {}
        self._evaluations: dict[str, tuple[frozenset[str], frozenset[str]]] = {}
        self.superseded: dict[str, str] = {}

    # -- tracking ---------------------------------------------------------

    def add_gaps(self, gaps: Iterable[DataGap]) -> None:
        for gap in gaps:
            self.gaps.setdefault(gap.gap_id, gap)

    def track_evaluation(self, evaluation_id: str, rule_ids: Iterable[str],
                         field_paths: Iterable[str] = ()) -> None:
        """Remember which rules and inputs an evaluation used."""
        self._evaluations[evaluation_id] = (frozenset(rule_ids), frozenset(field_paths))

    def current_evaluations(self) -> list[str]:
        return sorted(e for e in self._evaluations if e not in self.superseded)

    def _supersede(self, at: str, *, rules: set[str] = frozenset(),
                   paths: set[str] = frozenset(), why: str) -> list[str]:
        hit = []
        for eid, (used, used_paths) in sorted(self._evaluations.items()):
            if eid in self.superseded:
                continue
            if used & rules or used_paths & paths:
                self.superseded[eid] = why
                hit.append(eid)
                self.history.append(LedgerEvent("evaluation_superseded", at,
                                                "%s: %s" % (eid, why)))
        return hit

    # -- resolution -------------------------------------------------------

    def resolve(self, res: Resolution) -> MechanicsRegistry:
        if not res.evidence_ids:
            raise ResolutionRefused("%s: a resolution must cite evidence" % res.resolution_id)
        if res.gap_id not in self.gaps:
            raise ResolutionRefused("%s: unknown gap %r" % (res.resolution_id, res.gap_id))
        if not (res.rule_changes or res.entry_changes or res.input_values):
            raise ResolutionRefused("%s: evidence alone does not resolve a gap; supply the "
                                    "corrected rule or input" % res.resolution_id)
        bad = (set(res.rule_changes) - set(RULE_FIELDS)) | (set(res.entry_changes) - set(ENTRY_FIELDS))
        if bad:
            raise ResolutionRefused("%s: fields %s cannot be resolved" % (
                res.resolution_id, sorted(bad)))
        changed_rules: set[str] = set()
        if res.rule_changes or res.entry_changes:
            if res.mechanic_id is None or res.mechanic_id not in self.registry:
                raise ResolutionRefused("%s: rule changes need a registered mechanic_id"
                                        % res.resolution_id)
            prior = [r for r in self.accepted.get(res.mechanic_id, ()) if r.outcome]
            if res.outcome and prior and prior[-1].outcome != res.outcome:
                return self._contradiction(res, prior[-1])
            entry = self.registry[res.mechanic_id]
            rule_changes = dict(res.rule_changes)
            rule_changes["evidence_ids"] = sorted(set(entry.rule.evidence_ids) | set(res.evidence_ids))
            new_entry = bump(entry, **rule_changes)
            entry_changes = dict(res.entry_changes)
            for key in ("satisfied_by", "provides_paths", "requires_events", "tests"):
                if key in entry_changes and entry_changes[key] is not None:
                    entry_changes[key] = tuple(entry_changes[key])
            new_entry = replace(new_entry, reviewed_by=res.reviewer, **entry_changes)
            self.registry = self.registry.with_entry(new_entry, version=self._next_version())
            changed_rules = {res.mechanic_id} | self._dependents(res.mechanic_id)
            self.accepted.setdefault(res.mechanic_id, []).append(res)
        self.inputs.update(res.input_values)
        gap = self.gaps[res.gap_id]
        self.gaps[res.gap_id] = replace(
            gap, status=GapStatus.RESOLVED,
            resolution_evidence_ids=sorted(set(gap.resolution_evidence_ids) | set(res.evidence_ids)))
        self.history.append(LedgerEvent(
            "resolved", res.resolved_at,
            "by %s, reviewed by %s; evidence %s" % (res.author, res.reviewer or "nobody yet",
                                                   ", ".join(res.evidence_ids)),
            gap_id=res.gap_id, mechanic_id=res.mechanic_id, resolution_id=res.resolution_id))
        self._supersede(res.resolved_at, rules=changed_rules, paths=set(res.input_values),
                        why="resolution %s changed %s" % (
                            res.resolution_id,
                            ", ".join(sorted(changed_rules | set(res.input_values)))))
        return self.registry

    def _contradiction(self, res: Resolution, prior: Resolution) -> MechanicsRegistry:
        entry = self.registry[res.mechanic_id]
        new_entry = bump(entry, validation=RuleValidation.CONTRADICTED,
                         evidence_ids=sorted(set(entry.rule.evidence_ids) | set(res.evidence_ids)))
        self.registry = self.registry.with_entry(replace(new_entry, reviewed_by=None),
                                                 version=self._next_version())
        gap = self.gaps[res.gap_id]
        self.gaps[res.gap_id] = replace(
            gap, kind=GapKind.CONFLICTING_EVIDENCE, status=GapStatus.OPEN,
            resolution_evidence_ids=[],
            explanation="%s Contradiction: %s (%s) versus %s (%s)." % (
                gap.explanation, prior.outcome, prior.resolution_id, res.outcome, res.resolution_id))
        self.history.append(LedgerEvent(
            "contradicted", res.resolved_at,
            "%r from %s contradicts accepted %r from %s" % (
                res.outcome, res.resolution_id, prior.outcome, prior.resolution_id),
            gap_id=res.gap_id, mechanic_id=res.mechanic_id, resolution_id=res.resolution_id))
        changed = {res.mechanic_id} | self._dependents(res.mechanic_id)
        self._supersede(res.resolved_at, rules=changed,
                        why="contradicting evidence for %s" % res.mechanic_id)
        return self.registry

    def _dependents(self, mechanic_id: str) -> set[str]:
        out: set[str] = set()
        frontier = {mechanic_id}
        while frontier:
            nxt = {e.mechanic_id for e in self.registry
                   if set(e.rule.dependency_ids) & frontier and e.mechanic_id not in out}
            out |= nxt
            frontier = nxt
        return out

    def _next_version(self) -> str:
        try:
            return str(int(self.registry.version) + 1)
        except ValueError:
            return self.registry.version + "+1"

    # -- patches ----------------------------------------------------------

    def invalidate_for_patch(self, new_profile_id: str, diff: EntityDiff | None,
                             *, at: str) -> MechanicsRegistry:
        """Move the registry to a new patch profile.

        Rules touching changed entities, unknown-impact families, or (with no
        diff at all) every rule become ``stale`` on their old profile.
        Everything that depends on a stale rule is stale too. Other rules
        carry forward to the new profile. Display-only changes affect nothing.
        """
        affected: set[str] = set()
        for entry in self.registry:
            subjects = set(entry.subject_ids)
            if diff is None:
                affected.add(entry.mechanic_id)
            elif subjects & diff.changed:
                affected.add(entry.mechanic_id)
            elif any(s.startswith(f) for s in subjects for f in diff.unknown_families):
                affected.add(entry.mechanic_id)
        for mid in list(affected):
            affected |= self._dependents(mid)
        entries: list[RuleEntry] = []
        for entry in self.registry:
            if entry.mechanic_id in affected:
                entries.append(replace(bump(entry, validation=RuleValidation.STALE),
                                       reviewed_by=None))
            else:
                ids = sorted(set(entry.rule.patch_profile_ids) | {new_profile_id})
                entries.append(replace(entry, rule=replace(entry.rule, patch_profile_ids=ids)))
        self.registry = MechanicsRegistry(self.registry.registry_id, self._next_version(), entries)
        self.history.append(LedgerEvent(
            "patch_invalidation", at,
            "to %s: %d stale, %d carried forward%s" % (
                new_profile_id, len(affected), len(entries) - len(affected),
                "; no diff, everything stale" if diff is None else "")))
        self._supersede(at, rules=affected, why="patch %s made rules stale" % new_profile_id)
        return self.registry
