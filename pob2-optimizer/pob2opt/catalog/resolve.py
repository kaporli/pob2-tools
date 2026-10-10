"""Do the exported entities resolve a real build document? (P02-T02)

A catalog is only useful if the things a saved build refers to can be found
in it. This reads the references out of a PoB build document and looks each
one up, reporting what resolved, what did not, and what was ambiguous.

This is not a parser. P04 owns turning a document into a ``BuildSpec``;
nothing here produces one, fills a missing field or repairs a document. It
reads class, ascendancy, allocated passive ids, socket-group gems and item
base lines, and answers one question about each: is it in the catalog?

Ambiguity is reported, never resolved. contracts.md: a display name is not a
stable identifier, so a name matching two entities stays unresolved.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

from ..domain.records import CatalogEntity
from .entities import entity_id

#: A PoB item block's first lines are "Rarity: X" then the item name then the
#: base type. Only the base type is looked up; a rare item's own name is not
#: a catalog entity.
_RARITY = re.compile(r"^\s*Rarity:\s*(\w+)", re.IGNORECASE)


@dataclass
class BuildResolution:
    """What a document referred to, and whether the catalog has it."""

    resolved: dict[str, str] = field(default_factory=dict)
    unresolved: list[dict[str, Any]] = field(default_factory=list)
    ambiguous: list[dict[str, Any]] = field(default_factory=list)
    counts: dict[str, int] = field(default_factory=dict)

    @property
    def complete(self) -> bool:
        return not self.unresolved and not self.ambiguous

    def to_dict(self) -> dict:
        return {
            "complete": self.complete,
            "counts": dict(sorted(self.counts.items())),
            "resolved": dict(sorted(self.resolved.items())),
            "unresolved": list(self.unresolved),
            "ambiguous": list(self.ambiguous),
        }


def _by_id(entities: Sequence[CatalogEntity]) -> dict[str, CatalogEntity]:
    return {entity.entity_id: entity for entity in entities}


def _by_name(entities: Sequence[CatalogEntity]) -> dict[str, list[str]]:
    index: dict[str, list[str]] = {}
    for entity in entities:
        for name in list(entity.display_names) + list(entity.aliases):
            index.setdefault(name, []).append(entity.entity_id)
    return index


def resolve_build_document(
        xml: str,
        entities: Mapping[str, Sequence[CatalogEntity]]) -> BuildResolution:
    """Resolve every catalog reference a build document makes."""
    result = BuildResolution()
    try:
        root = ET.fromstring(xml)
    except ET.ParseError as exc:
        result.unresolved.append({"kind": "document", "reference": "",
                                  "reason": "not parseable as XML: %s" % exc})
        return result

    classes = _by_id(entities.get("classes", ()))
    ascendancies = entities.get("ascendancies", ())
    nodes = _by_id(entities.get("passive_nodes", ()))
    gems_by_name = _by_name(entities.get("gems", ()))
    gems_by_id = _by_id(entities.get("gems", ()))
    skills_by_name = _by_name(entities.get("granted_skills", ()))
    bases_by_name = _by_name(entities.get("item_bases", ()))
    slots_by_name = _by_name(entities.get("slots", ()))

    def note(kind: str) -> None:
        result.counts[kind] = result.counts.get(kind, 0) + 1

    def resolve_named(kind: str, reference: str,
                      index: Mapping[str, Sequence[str]]) -> None:
        note(kind)
        matches = index.get(reference)
        if not matches:
            result.unresolved.append({"kind": kind, "reference": reference,
                                      "reason": "no entity carries this name"})
        elif len(set(matches)) > 1:
            result.ambiguous.append({"kind": kind, "reference": reference,
                                     "candidates": sorted(set(matches))})
        else:
            result.resolved["%s:%s" % (kind, reference)] = matches[0]

    for spec in root.iter("Spec"):
        class_id = spec.get("classId")
        if class_id is not None:
            note("class")
            wanted = entity_id("classes", class_id)
            if wanted in classes:
                result.resolved["class:%s" % class_id] = wanted
            else:
                result.unresolved.append(
                    {"kind": "class", "reference": class_id,
                     "reason": "no class with this id in the catalog"})
        ascend_id = spec.get("ascendClassId")
        if ascend_id is not None and str(ascend_id) not in ("0", "nil", ""):
            note("ascendancy")
            wanted = entity_id("ascendancies", class_id, ascend_id)
            if any(entity.entity_id == wanted for entity in ascendancies):
                result.resolved["ascendancy:%s/%s" % (class_id, ascend_id)] = wanted
            else:
                result.unresolved.append(
                    {"kind": "ascendancy",
                     "reference": "%s/%s" % (class_id, ascend_id),
                     "reason": "no ascendancy with this index on this class"})
        for raw in (spec.get("nodes") or "").split(","):
            raw = raw.strip()
            if not raw:
                continue
            note("passive_node")
            wanted = entity_id("passive_nodes", raw)
            if wanted in nodes:
                result.resolved["passive_node:%s" % raw] = wanted
            else:
                result.unresolved.append(
                    {"kind": "passive_node", "reference": raw,
                     "reason": "no passive node with this id in the catalog"})

    slots_by_id = _by_id(entities.get("slots", ()))
    for group in root.iter("Skill"):
        slot = group.get("slot")
        if slot:
            # The native key first. PoB's swap slots carry the same slotName
            # as the slots they shadow, so "Weapon 1" matches two entities by
            # display name while naming exactly one of them natively.
            note("slot")
            wanted = entity_id("slots", slot)
            if wanted in slots_by_id:
                result.resolved["slot:%s" % slot] = wanted
            else:
                matches = slots_by_name.get(slot)
                if matches and len(set(matches)) == 1:
                    result.resolved["slot:%s" % slot] = matches[0]
                elif matches:
                    result.ambiguous.append(
                        {"kind": "slot", "reference": slot,
                         "candidates": sorted(set(matches))})
                else:
                    result.unresolved.append(
                        {"kind": "slot", "reference": slot,
                         "reason": "no slot with this id or name"})
        skills_by_id = _by_id(entities.get("granted_skills", ()))
        for gem in group.iter("Gem"):
            # A saved gem carries up to three references: the gem's metadata
            # id, the granted effect it activates, and the name shown in the
            # editor. Each is resolved on its own, because a build that names
            # a gem the catalog has under a different id is a different
            # problem from one naming a skill the catalog does not have.
            gem_ref = gem.get("gemId") or gem.get("variantId")
            if gem_ref:
                note("gem")
                direct = entity_id("gems", gem_ref)
                by_alias = gems_by_name.get(gem_ref)
                if direct in gems_by_id:
                    result.resolved["gem:%s" % gem_ref] = direct
                elif by_alias and len(set(by_alias)) == 1:
                    result.resolved["gem:%s" % gem_ref] = by_alias[0]
                elif by_alias:
                    result.ambiguous.append(
                        {"kind": "gem", "reference": gem_ref,
                         "candidates": sorted(set(by_alias))})
                elif gem.get("nameSpec"):
                    resolve_named("gem_name", gem.get("nameSpec"), gems_by_name)
                else:
                    result.unresolved.append(
                        {"kind": "gem", "reference": gem_ref,
                         "reason": "no gem with this id or alias"})
            elif gem.get("nameSpec"):
                resolve_named("gem_name", gem.get("nameSpec"), gems_by_name)
            skill_ref = gem.get("skillId")
            if skill_ref:
                note("granted_skill")
                direct = entity_id("granted_skills", skill_ref)
                if direct in skills_by_id:
                    result.resolved["granted_skill:%s" % skill_ref] = direct
                else:
                    matches = skills_by_name.get(skill_ref)
                    if matches and len(set(matches)) == 1:
                        result.resolved["granted_skill:%s" % skill_ref] = matches[0]
                    elif matches:
                        result.ambiguous.append(
                            {"kind": "granted_skill", "reference": skill_ref,
                             "candidates": sorted(set(matches))})
                    else:
                        result.unresolved.append(
                            {"kind": "granted_skill", "reference": skill_ref,
                             "reason": "no granted skill with this id"})

    for item in root.iter("Item"):
        base = _item_base_line(item.text or "")
        if base:
            resolve_named("item_base", base, bases_by_name)

    return result


def _item_base_line(text: str) -> str | None:
    """The base type line of a PoB item block.

    A rarity line, then the item's own name, then the base type. A normal
    item has no separate name, so its second line is already the base. The
    name line is skipped rather than looked up: a rare's rolled name is not
    a catalog entity and treating it as one would manufacture an unresolved
    reference that does not exist.
    """
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if not lines or _RARITY.match(lines[0]) is None:
        return None
    rarity = _RARITY.match(lines[0]).group(1).lower()
    if rarity == "normal":
        return lines[1] if len(lines) > 1 else None
    return lines[2] if len(lines) > 2 else None
