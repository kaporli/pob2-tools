"""What the catalog says about one active skill and its supports (P02-T02.1).

D07 needs Flicker Strike resolved to exact gem and granted-skill ids, and
needs to know what the catalog records about it: skill types, weapon
restriction, costs, stat sets and which support gems apply. This module reads
those facts out of exported ``CatalogEntity`` rows and nothing else.

Support compatibility is the ``supportedBy`` list the engine computed with
its own ``calcLib.canGrantedEffectSupportActiveSkill`` on the skill's base
types. It is not re-derived here. Types a weapon, another support or a minion
adds at runtime are not applied, so the list is the catalog's answer, not a
particular build's.

A missing or ambiguous match is an issue, never a substitute: no other skill
and no name match stands in for the registered ids.
"""

from __future__ import annotations

from typing import Any, Mapping, Sequence

from ..domain.objectives import FLICKER_SUSTAINED_DPS_V1, ObjectiveSkill
from ..domain.records import CatalogEntity
from .entities import entities_from_rows, entity_id

Entities = Mapping[str, Sequence[CatalogEntity]]


def _rows_by_id(entities: Entities, table: str, key: str) -> list[CatalogEntity]:
    return [e for e in entities.get(table, ()) if e.entity_id == key]


def _named(entities: Entities, table: str, name: str) -> list[str]:
    return sorted(e.entity_id for e in entities.get(table, ())
                  if name in e.display_names)


def skill_coverage(entities: Entities, skill: ObjectiveSkill) -> dict[str, Any]:
    """Catalog facts for one registered gem/granted-skill pair.

    ``issues`` is empty only when both ids resolve to exactly one row, the
    gem names the granted skill, neither is a support, and no other gem or
    granted skill shares the display name.
    """
    gem_key = entity_id("gems", skill.gem_id)
    skill_key = entity_id("granted_skills", skill.granted_skill_id)
    issues: list[str] = []
    gems = _rows_by_id(entities, "gems", gem_key)
    granted = _rows_by_id(entities, "granted_skills", skill_key)
    for key, found in ((gem_key, gems), (skill_key, granted)):
        if len(found) != 1:
            issues.append("expected one row for %s, found %d" % (key, len(found)))
    if issues:
        return {"gem_entity_id": gem_key, "granted_skill_entity_id": skill_key,
                "issues": issues}
    gem = gems[0].raw_reference
    active = granted[0].raw_reference
    if gem.get("grantedEffectId") != skill.granted_skill_id:
        issues.append("gem %s grants %r, not %s"
                      % (gem_key, gem.get("grantedEffectId"), skill.granted_skill_id))
    if gem.get("isSupport") is not False or active.get("support") is not False:
        issues.append("the registered skill is recorded as a support")
    name = gem.get("name")
    same_name = {table: _named(entities, table, name)
                 for table in ("gems", "granted_skills")}
    for table, key in (("gems", gem_key), ("granted_skills", skill_key)):
        if same_name[table] != [key]:
            issues.append("%s shares the name %r with %s"
                          % (key, name, ", ".join(i for i in same_name[table]
                                                  if i != key) or "nothing"))
    if "supportedBy" not in active:
        issues.append("the granted-skill row carries no supportedBy list; "
                      "re-export with adapter p02.2 or later")
    if active.get("supportCheckErrors"):
        issues.append("the engine could not check %d support(s): %s"
                      % (len(active["supportCheckErrors"]),
                         ", ".join(active["supportCheckErrors"])))

    supported = list(active.get("supportedBy") or ())
    accepted = set(supported)
    compatible, incompatible = [], []
    for entity in entities.get("gems", ()):
        raw = entity.raw_reference
        if raw.get("isSupport") is not True:
            continue
        entry = {"gem_entity_id": entity.entity_id, "name": raw.get("name"),
                 "granted_effect_id": raw.get("grantedEffectId")}
        (compatible if raw.get("grantedEffectId") in accepted
         else incompatible).append(entry)
    return {
        "gem_entity_id": gem_key,
        "granted_skill_entity_id": skill_key,
        "issues": issues,
        "name": name,
        "gem": {key: gem.get(key) for key in (
            "gemType", "tags", "tagString", "weaponRequirements", "reqStr",
            "reqDex", "reqInt", "naturalMaxLevel", "tier")},
        "granted_skill": {key: active.get(key) for key in (
            "skillTypeNames", "weaponTypes", "castTime", "cannotBeSupported",
            "levelCount", "statSets", "costs")},
        "supported_by_effect_ids": supported,
        "compatible_support_gems": sorted(compatible, key=lambda e: e["gem_entity_id"]),
        "incompatible_support_gem_count": len(incompatible),
    }


def flicker_coverage(gem_rows: Sequence[Mapping[str, Any]],
                     skill_rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """``skill_coverage`` for D07's registered Flicker Strike, from raw rows."""
    entities = {"gems": entities_from_rows("gems", gem_rows),
                "granted_skills": entities_from_rows("granted_skills", skill_rows)}
    return skill_coverage(entities, FLICKER_SUSTAINED_DPS_V1.target_skill)
