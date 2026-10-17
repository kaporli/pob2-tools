"""Resolve a RunRequest version 2 objective scope against a catalog (P08-T01.1).

D07 requires the target skill and the class scope to be exact catalog
identities. This module checks that and nothing more:

* target skills must represent the objective's registered gem/active-effect
  pair, whose identities and relationship are verified against the catalog;
* every ``class_scope`` class must be a ``classes`` entity, and every listed
  ascendancy an ``ascendancies`` entity of that class.

A display name is never accepted as an id. When an unresolved entry matches
names, the matching ids are reported as candidates for a reviewer to choose;
they are never substituted. Any issue blocks preparation.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Sequence

from ..domain.records import CatalogEntity, ClassScope, ObjectiveSelection
from ..domain.objectives import UnknownObjective, get_objective
from ..parsers.resolve import AMBIGUOUS, RESOLVED, resolve_name
from .entities import entity_id

#: Catalog tables a target skill id may come from.
SKILL_TABLES = ("gems", "granted_skills")

Entities = Mapping[str, Sequence[CatalogEntity]]


@dataclass(frozen=True)
class ScopeIssue:
    code: str
    field_path: str
    value: str
    message: str
    #: Exact-name matches a reviewer may choose from. Never applied.
    candidates: tuple[str, ...] = ()


@dataclass(frozen=True)
class ScopeReport:
    issues: tuple[ScopeIssue, ...]

    @property
    def ok(self) -> bool:
        return not self.issues


def _by_id(entities: Entities, table: str) -> dict[str, CatalogEntity]:
    return {e.entity_id: e for e in entities.get(table, ())}


def skill_candidates(entities: Entities, name: str) -> tuple[str, ...]:
    """Ids of every gem or granted skill with this exact name or alias."""
    found: list[str] = []
    for table in SKILL_TABLES:
        result = resolve_name(entities, table, name)
        if result.status == RESOLVED:
            found.append(result.entity_id)
        elif result.status == AMBIGUOUS:
            found.extend(result.candidates)
    return tuple(sorted(found))


def _class_candidates(entities: Entities, table: str,
                      name: str) -> tuple[str, ...]:
    result = resolve_name(entities, table, name)
    if result.status == RESOLVED:
        return (result.entity_id,)
    return tuple(result.candidates)


def _native_class_id(entity: CatalogEntity) -> str | None:
    raw = entity.raw_reference if isinstance(entity.raw_reference, dict) else {}
    value = raw.get("classId")
    return None if value is None else str(value)


def resolve_target_skills(entities: Entities,
                          selection: ObjectiveSelection) -> list[ScopeIssue]:
    issues = []
    try:
        definition = get_objective(selection.objective_id,
                                   selection.objective_version)
    except UnknownObjective as exc:
        return [ScopeIssue("unknown_objective", "/objective/objective_id",
                           selection.objective_id, str(exc))]
    for i, skill_id in enumerate(selection.target_skill_ids):
        path = "/objective/target_skill_ids/%d" % i
        owners = [table for table in SKILL_TABLES
                  for entity in entities.get(table, ())
                  if entity.entity_id == skill_id]
        if len(owners) == 1:
            continue
        if owners:
            issues.append(ScopeIssue(
                "ambiguous_target_skill", path, skill_id,
                "%r is an id in %s" % (skill_id, " and ".join(owners))))
            continue
        candidates = skill_candidates(entities, skill_id)
        issues.append(ScopeIssue(
            "unresolved_target_skill", path, skill_id,
            "%r is not a gem or granted-skill id in this catalog%s"
            % (skill_id, "; it matches %d entity name(s)" % len(candidates)
               if candidates else ""),
            candidates))
    if issues:
        return issues
    expected = definition.target_skill
    if expected is None:
        if selection.target_skill_ids or definition.requires_target_skill:
            issues.append(ScopeIssue(
                "unexpected_target_skill", "/objective/target_skill_ids",
                selection.objective_id, "objective has no registered target skill"))
        return issues
    if not selection.target_skill_ids:
        return [ScopeIssue("missing_target_skill", "/objective/target_skill_ids",
                           selection.objective_id,
                           "supply an exact catalog identity of the required skill")]
    expected_ids = (entity_id("gems", expected.gem_id),
                    entity_id("granted_skills", expected.granted_skill_id))
    for i, skill_id in enumerate(selection.target_skill_ids):
        if skill_id not in expected_ids:
            issues.append(ScopeIssue(
                "objective_skill_mismatch", "/objective/target_skill_ids/%d" % i,
                skill_id, "this entity is not the objective's required skill",
                expected_ids))
    if issues:
        return issues
    # Verify both ends even when the request names only one representation.
    # Names/aliases cannot establish ownership or turn a support into an attack.
    pair = []
    for table, key in zip(SKILL_TABLES, expected_ids):
        matches = [e for e in entities.get(table, ()) if e.entity_id == key]
        if len(matches) != 1:
            issues.append(ScopeIssue(
                "unresolved_objective_skill", "/objective/target_skill_ids", key,
                "expected exactly one catalog row for %s; found %d; acquire "
                "or review this patch's gem/active-effect mapping" % (key, len(matches))))
        else:
            pair.append(matches[0].raw_reference)
    if issues:
        return issues
    gem, granted = pair
    if (not isinstance(gem, dict) or not isinstance(granted, dict)
            or gem.get("id") != expected.gem_id
            or granted.get("id") != expected.granted_skill_id
            or gem.get("grantedEffectId") != expected.granted_skill_id
            or gem.get("isSupport") is not False
            or granted.get("support") is not False):
        issues.append(ScopeIssue(
            "unverified_objective_skill", "/objective/target_skill_ids",
            selection.objective_id,
            "catalog must evidence the registered native IDs, their grantedEffectId "
            "link, and isSupport/support=false; acquire or review these fields"))
    return issues


def resolve_class_scope(entities: Entities,
                        scope: Sequence[ClassScope]) -> list[ScopeIssue]:
    classes = _by_id(entities, "classes")
    ascendancies = _by_id(entities, "ascendancies")
    issues = []
    for i, entry in enumerate(scope):
        path = "/class_scope/%d" % i
        cls = classes.get(entry.class_id)
        if cls is None:
            issues.append(ScopeIssue(
                "unresolved_class", path + "/class_id", entry.class_id,
                "%r is not a class id in this catalog" % entry.class_id,
                _class_candidates(entities, "classes", entry.class_id)))
            continue
        native = _native_class_id(cls)
        for j, ascendancy_id in enumerate(entry.ascendancy_ids or ()):
            apath = "%s/ascendancy_ids/%d" % (path, j)
            ascendancy = ascendancies.get(ascendancy_id)
            if ascendancy is None:
                issues.append(ScopeIssue(
                    "unresolved_ascendancy", apath, ascendancy_id,
                    "%r is not an ascendancy id in this catalog"
                    % ascendancy_id,
                    _class_candidates(entities, "ascendancies",
                                      ascendancy_id)))
            elif native is None or _native_class_id(ascendancy) != native:
                issues.append(ScopeIssue(
                    "ascendancy_class_mismatch", apath, ascendancy_id,
                    "%r does not belong to class %r"
                    % (ascendancy_id, entry.class_id)))
    return issues


def resolve_objective_scope(entities: Entities,
                            request) -> ScopeReport:
    """Every scope issue of a version 2 request. Empty means resolved."""
    if request.schema_version < 2:
        raise ValueError("objective scope exists from RunRequest schema "
                         "version 2; upgrade the request first")
    return ScopeReport(tuple(
        resolve_target_skills(entities, request.objective)
        + resolve_class_scope(entities, request.class_scope)))
