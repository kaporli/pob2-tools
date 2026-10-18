"""The mechanics registry (P06-T01).

A registry is a versioned set of :class:`RuleEntry` objects. Each entry wraps
one contracts.md ``MechanicRule`` record, which is the persisted part, and
adds what coverage analysis needs to find the rule from a build: the catalog
subjects that pull it in, the state paths it provides, whether it is a
critical activation or attribution rule, and the P09 protocol gaps that state
its open question.

One ``mechanic_id`` is one effect with one owner. The registry refuses
duplicate ids, dependencies on ids it does not hold, and static dependency
cycles. Temporal trigger loops are simulator rules with their own bound, not
static dependencies.

Nothing here decides how a game mechanic works. An entry records what is
known, who calculates it and how far that is validated; unknown rules are
entries with ``support: unknown``, never dropped.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Iterable, Mapping

from ..domain.codec import to_jsonable
from ..domain.enums import RuleOwner, RuleSupport, RuleValidation
from ..domain.identity import content_hash
from ..domain.records import MechanicRule
from ..domain.validation import validate_record, validate_rule_registry

#: Coverage domains. A finding is reported per domain.
DOMAINS = (
    "skill", "support", "passive", "item", "damage", "timing", "cost",
    "resource", "activation", "attribution", "target", "initial_state",
    "config", "engine", "patch", "buff", "rotation", "scenario",
)

#: Critical rule kinds (D07; P09-T01.1 R1). Their gaps can never be lowered.
CRITICAL_KINDS = ("activation", "attribution")

#: Validation levels that count as checked for a critical rule.
CHECKED = (RuleValidation.FIXTURE_CHECKED, RuleValidation.GAMEPLAY_CHECKED)

#: Classification of a damage source by the attribution rule.
ATTRIBUTION_CLASSES = ("flicker_direct", "flicker_secondary", "unrelated")

PATCH_PROFILE_ID = "patch-profile/0.5.5e/ac0e930898cb3951"


class RegistryError(ValueError):
    """A registry that would let an effect be counted wrongly or not at all."""

    def __init__(self, problems: list[str]):
        super().__init__("; ".join(problems))
        self.problems = problems


@dataclass(frozen=True)
class RuleEntry:
    rule: MechanicRule
    #: Display only. Excluded from every identity hash.
    title: str
    domain: str
    #: Catalog subjects that pull this rule into a candidate's coverage:
    #: ``skill:<granted effect id>``, ``support:<id>``, ``passive:<node id>``,
    #: ``config:<PoB var>``, ``scenario:<scenario id>``, ``always``.
    subject_ids: tuple[str, ...] = ()
    #: State paths this rule produces for rotation predicates.
    provides_paths: tuple[str, ...] = ()
    critical: str | None = None
    #: P09 protocol DataGaps that state this rule's open question.
    protocol_gap_ids: tuple[str, ...] = ()
    #: Test node ids that check the rule's implementation.
    tests: tuple[str, ...] = ()
    #: The subject deals damage, so the attribution rule must classify it.
    damage_source: bool = False
    #: Activation rules: actions that re-enable the gated skill, as
    #: ``move`` or ``skill:<id>``. ``None`` means not established.
    satisfied_by: tuple[str, ...] | None = None
    #: The attribution rule: damage source subject to its class.
    assignments: Mapping[str, str] = field(default_factory=dict)
    #: Who accepted the evidence for the current version. Required before a
    #: critical rule can permit a score.
    reviewed_by: str | None = None
    #: Scenario events the effect needs (``kill``, ``incoming_hit``). In a
    #: scenario without them the effect supplies nothing.
    requires_events: tuple[str, ...] = ()

    @property
    def mechanic_id(self) -> str:
        return self.rule.mechanic_id

    def identity(self) -> dict:
        """Everything that changes a calculation. ``title`` is left out."""
        return {
            "rule": _rule_identity(self.rule),
            "domain": self.domain,
            "subject_ids": sorted(self.subject_ids),
            "provides_paths": sorted(self.provides_paths),
            "critical": self.critical,
            "protocol_gap_ids": sorted(self.protocol_gap_ids),
            "tests": sorted(self.tests),
            "damage_source": self.damage_source,
            "satisfied_by": None if self.satisfied_by is None else sorted(self.satisfied_by),
            "assignments": dict(sorted(self.assignments.items())),
            "reviewed_by": self.reviewed_by,
            "requires_events": sorted(self.requires_events),
        }

    def is_settled(self) -> bool:
        """Implemented, checked and reviewed: the bar for a critical rule."""
        return (self.rule.support is RuleSupport.IMPLEMENTED
                and self.rule.validation in CHECKED
                and bool(self.rule.evidence_ids)
                and self.reviewed_by is not None)


def _rule_identity(rule: MechanicRule) -> dict:
    data = to_jsonable(rule)
    for key in ("record_id", "created_at", "provenance_ids"):
        data.pop(key, None)
    return data


def make_rule(mechanic_id: str, *, owner: RuleOwner, support: RuleSupport,
              validation: RuleValidation, version: str = "1",
              patch_profile_ids: Iterable[str] = (PATCH_PROFILE_ID,),
              required_input_paths: Iterable[str] = (),
              dependency_ids: Iterable[str] = (),
              implementation_ref: str = "none",
              evidence_ids: Iterable[str] = (),
              limitations: Iterable[str] = (),
              tolerances: Mapping[str, float] | None = None,
              created_at: str = "2026-10-18T00:00:00Z",
              provenance_ids: Iterable[str] = ("p06-registry",)) -> MechanicRule:
    return MechanicRule(
        schema_version=1,
        record_id="mechanic-rule/%s@%s" % (mechanic_id, version),
        created_at=created_at,
        provenance_ids=list(provenance_ids),
        mechanic_id=mechanic_id,
        version=version,
        patch_profile_ids=list(patch_profile_ids),
        required_input_paths=list(required_input_paths),
        dependency_ids=list(dependency_ids),
        implementation_ref=implementation_ref,
        owner=owner,
        support=support,
        validation=validation,
        evidence_ids=list(evidence_ids),
        limitations=list(limitations),
        tolerances=dict(tolerances or {}),
    )


class MechanicsRegistry:
    """A validated, hashable set of rule entries. Immutable once built."""

    def __init__(self, registry_id: str, version: str,
                 entries: Iterable[RuleEntry]):
        self.registry_id = registry_id
        self.version = version
        self._entries: dict[str, RuleEntry] = {}
        problems: list[str] = []
        for entry in entries:
            if entry.mechanic_id in self._entries:
                problems.append("duplicate mechanic_id %r" % entry.mechanic_id)
            self._entries[entry.mechanic_id] = entry
        problems.extend(self._check())
        if problems:
            raise RegistryError(problems)
        self._by_subject: dict[str, list[str]] = {}
        for entry in self._entries.values():
            for subject in entry.subject_ids:
                self._by_subject.setdefault(subject, []).append(entry.mechanic_id)

    # -- validation -------------------------------------------------------

    def _check(self) -> list[str]:
        problems = []
        for entry in self._entries.values():
            report = validate_record(entry.rule)
            problems.extend("%s: %s" % (entry.mechanic_id, err)
                            for err in report.errors)
            if entry.domain not in DOMAINS:
                problems.append("%s: unknown domain %r" % (entry.mechanic_id, entry.domain))
            if entry.critical is not None and entry.critical not in CRITICAL_KINDS:
                problems.append("%s: unknown critical kind %r" % (entry.mechanic_id, entry.critical))
            for dep in entry.rule.dependency_ids:
                if dep not in self._entries:
                    problems.append("%s depends on unregistered %r" % (entry.mechanic_id, dep))
            for source, cls in entry.assignments.items():
                if cls not in ATTRIBUTION_CLASSES:
                    problems.append("%s: %s has unknown attribution class %r"
                                    % (entry.mechanic_id, source, cls))
        problems.extend(str(e) for e in validate_rule_registry(
            [e.rule for e in self._entries.values()]))
        cycle = self._find_cycle()
        if cycle:
            problems.append("static dependency cycle: %s" % " -> ".join(cycle))
        return problems

    def _find_cycle(self) -> list[str] | None:
        state: dict[str, int] = {}
        stack: list[str] = []

        def visit(node: str) -> list[str] | None:
            state[node] = 1
            stack.append(node)
            for dep in sorted(self._entries[node].rule.dependency_ids):
                if dep not in self._entries:
                    continue
                if state.get(dep) == 1:
                    return stack[stack.index(dep):] + [dep]
                if dep not in state:
                    found = visit(dep)
                    if found:
                        return found
            stack.pop()
            state[node] = 2
            return None

        for node in sorted(self._entries):
            if node not in state:
                found = visit(node)
                if found:
                    return found
        return None

    # -- queries ----------------------------------------------------------

    def __contains__(self, mechanic_id: str) -> bool:
        return mechanic_id in self._entries

    def __getitem__(self, mechanic_id: str) -> RuleEntry:
        return self._entries[mechanic_id]

    def __iter__(self):
        return iter(self._entries[k] for k in sorted(self._entries))

    def __len__(self) -> int:
        return len(self._entries)

    def for_subject(self, subject: str) -> list[RuleEntry]:
        return [self._entries[m] for m in sorted(self._by_subject.get(subject, ()))]

    def providing(self, path: str) -> list[RuleEntry]:
        return [e for e in self if path in e.provides_paths]

    def closure(self, mechanic_ids: Iterable[str]) -> list[str]:
        """The ids and everything they depend on, sorted."""
        seen: set[str] = set()
        todo = [m for m in mechanic_ids if m in self._entries]
        while todo:
            current = todo.pop()
            if current in seen:
                continue
            seen.add(current)
            todo.extend(d for d in self._entries[current].rule.dependency_ids
                        if d not in seen)
        return sorted(seen)

    def critical(self, kind: str) -> list[RuleEntry]:
        return [e for e in self if e.critical == kind]

    # -- identity ---------------------------------------------------------

    def registry_hash(self) -> str:
        return content_hash({
            "registry_id": self.registry_id,
            "version": self.version,
            "entries": [e.identity() for e in self],
        })

    def closure_hash(self, mechanic_ids: Iterable[str]) -> str:
        """Identity of the rules one evaluation used, for cache keys.

        Changing an unrelated rule or a display title leaves it unchanged.
        """
        ids = self.closure(mechanic_ids)
        return content_hash([self._entries[m].identity() for m in ids])

    def records(self) -> list[MechanicRule]:
        return [e.rule for e in self]

    def with_entry(self, entry: RuleEntry, *, version: str | None = None) -> MechanicsRegistry:
        """A new registry with one entry replaced or added."""
        entries = dict(self._entries)
        entries[entry.mechanic_id] = entry
        return MechanicsRegistry(self.registry_id, version or self.version,
                                 entries.values())

    def summary(self) -> dict:
        counts: dict[str, int] = {}
        for entry in self:
            key = "%s/%s" % (entry.rule.support.value, entry.rule.validation.value)
            counts[key] = counts.get(key, 0) + 1
        return {"registry_id": self.registry_id, "version": self.version,
                "registry_hash": self.registry_hash(), "rules": len(self),
                "by_support_validation": dict(sorted(counts.items()))}


def bump(entry: RuleEntry, **rule_changes) -> RuleEntry:
    """A new version of an entry's rule. The version string becomes n+1."""
    old = entry.rule
    try:
        version = str(int(old.version) + 1)
    except ValueError:
        version = old.version + "+1"
    rule = replace(old, version=version,
                   record_id="mechanic-rule/%s@%s" % (old.mechanic_id, version),
                   **rule_changes)
    return replace(entry, rule=rule)
