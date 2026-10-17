"""Resolve a RunRequest version 2 objective scope against a catalog (P08-T01.1).

D07 requires the target skill and the class scope to be exact catalog
identities. This module checks that and nothing more:

* every ``target_skill_ids`` entry must be the ``entity_id`` of exactly one
  entity in ``gems`` or ``granted_skills``;
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
from ..parsers.resolve import AMBIGUOUS, RESOLVED, resolve_name

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
    tables = {table: _by_id(entities, table) for table in SKILL_TABLES}
    issues = []
    for i, skill_id in enumerate(selection.target_skill_ids):
        path = "/objective/target_skill_ids/%d" % i
        owners = [table for table in SKILL_TABLES if skill_id in tables[table]]
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
