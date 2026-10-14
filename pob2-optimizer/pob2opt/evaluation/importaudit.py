"""Select active PoB sets and retain content the BuildSpec cannot represent."""
from __future__ import annotations

import xml.etree.ElementTree as ET

from .naming import CatalogNaming, UnresolvedName
from .support import (NOT_REPRESENTABLE, PARTIAL, UNRESOLVED_NAME,
                      LossCollector)


def audit_document(root: ET.Element, naming: CatalogNaming,
                   losses: LossCollector) -> None:
    """Normalize only the private parse tree; every discarded set is retained.

    Tree.activeSpec is a one-based position. The other selectors refer to IDs.
    Missing selectors default to 1, matching the upstream loaders.
    """
    for tag, child_tag, selector in (
        ("Skills", "SkillSet", "activeSkillSet"),
        ("Items", "ItemSet", "activeItemSet"),
        ("Tree", "Spec", "activeSpec"),
        ("Config", "ConfigSet", "activeConfigSet"),
    ):
        container = root.find(tag)
        if container is None:
            continue
        children = container.findall(child_tag)
        if not children:
            continue  # legacy flat Skills/Config containers
        selected = container.get(selector, "1")
        matches = [node for index, node in enumerate(children, 1)
                   if (str(index) if tag == "Tree" else node.get("id")) == selected]
        if len(matches) != 1:
            losses.add("/%s/@%s" % (tag, selector), PARTIAL,
                       "active selector is missing, ambiguous or invalid",
                       ET.tostring(container, encoding="unicode"), True)
        for node in children:
            if len(matches) == 1 and node is matches[0]:
                continue
            losses.add("/%s/%s" % (tag, child_tag), PARTIAL,
                       "additional or unresolved variant is not represented",
                       ET.tostring(node, encoding="unicode"), True)
            container.remove(node)

    def resolve(table, value, path):
        try:
            return naming.reverse(table, value)
        except UnresolvedName:
            losses.add(path, UNRESOLVED_NAME,
                       "native reference is absent from " + table, value, True)
            return None

    build = root.find("Build")
    if build is not None:
        resolve("class_names", build.get("className", ""), "/Build/@className")
        ascendancy = build.get("ascendClassName", "None")
        if ascendancy not in ("", "None"):
            resolve("ascendancy_names", ascendancy, "/Build/@ascendClassName")
    for slot in root.findall("Items/ItemSet/Slot"):
        resolve("slot_names", slot.get("name", ""), "/Items/Slot/@name")
    item_ids = {node.get("id") for node in root.findall("Items/Item")}
    for node in root.findall("Items/ItemSet/Slot") + root.findall("Tree/Spec/Sockets/Socket"):
        item_id = node.get("itemId", "0")
        if item_id != "0" and item_id not in item_ids:
            losses.add("/items/@itemId", UNRESOLVED_NAME,
                       "item reference is absent from the document", item_id, True)
    spec = root.find("Tree/Spec")
    if spec is not None:
        for node in spec.iter():
            if node.tag.startswith("WeaponSet"):
                resolve("weapon_set_numbers", int(node.tag[len("WeaponSet"):]),
                        "/Tree/" + node.tag)
            if node.tag == "AttributeOverride":
                for attr, option in (("strNodes", "Strength"),
                                     ("dexNodes", "Dexterity"),
                                     ("intNodes", "Intelligence")):
                    if node.get(attr):
                        resolve("attribute_options", option,
                                "/Tree/AttributeOverride/@" + attr)
            for attr in ("nodes", "strNodes", "dexNodes", "intNodes", "nodeId"):
                for value in node.get(attr, "").replace(" ", "").split(","):
                    if value:
                        resolve("node_ids", int(value), "/Tree/%s/@%s" % (node.tag, attr))
    groups = root.findall("Skills/SkillSet/Skill") + root.findall("Skills/Skill")
    for group_index, group in enumerate(groups):
        group_path = "/Skills/Skill/%d" % group_index
        if group.get("source"):
            _audit_generated(group, group_path, losses)
            continue
        if group.get("slot"):
            resolve("slot_names", group.get("slot"), "/Skills/Skill/@slot")
        _audit_attributes(group, GROUP_DEFAULTS, GROUP_DISPLAY_ONLY,
                          group_path, losses)
        seen_active = False
        for gem_index, gem in enumerate(group.findall("Gem")):
            gem_path = "%s/Gem/%d" % (group_path, gem_index)
            skill_id = resolve("skill_ids", gem.get("skillId", ""), "/Skills/Gem/@skillId")
            if gem.get("gemId"):
                try:
                    naming.reverse_gem(gem.get("gemId"), gem.get("variantId"))
                except UnresolvedName:
                    losses.add("/Skills/Gem/@gemId", UNRESOLVED_NAME,
                               "native gemId/variantId pair is absent from "
                               "gem_ids", [gem.get("gemId"),
                                           gem.get("variantId")], True)
            is_support = skill_id in naming.support_skill_ids
            if is_support and not seen_active:
                losses.add(gem_path, PARTIAL,
                           "a support with no active skill before it in the "
                           "group has nothing to attach to in BuildSpec",
                           ET.tostring(gem, encoding="unicode"), True)
            if skill_id is not None and not is_support:
                seen_active = True
            if is_support:
                for name in ("level", "quality", "enabled"):
                    if gem.get(name) is None:
                        losses.add("%s/@%s" % (gem_path, name), PARTIAL,
                                   "support %s is not stated; it stays "
                                   "unknown rather than taking PoB's "
                                   "default" % name, None, False)
                for name in ("level", "quality"):
                    value = gem.get(name)
                    if value is not None and not _is_int(value):
                        losses.add("%s/@%s" % (gem_path, name), PARTIAL,
                                   "support %s is not an integer" % name,
                                   value, True)
            _audit_attributes(gem, GEM_DEFAULTS, GEM_DISPLAY_ONLY, gem_path,
                              losses)
            for child in gem:
                losses.add("%s/%s" % (gem_path, child.tag), PARTIAL,
                           "per-effect gem setting is not represented",
                           ET.tostring(child, encoding="unicode"), True)


    _audit_items_and_config(root, losses)


def _audit_generated(group: ET.Element, path: str,
                     losses: LossCollector) -> None:
    """A group PoB generates. Only settings the author changed are losses.

    PoB rebuilds these groups from the equipment, the tree or a mechanic
    when it loads a document, so the group itself is not imported. What PoB
    cannot rebuild is a choice made on it: a disabled group, a different
    active skill, a minion or skill-part selection. Those block the record.
    """
    losses.add(path + "/@source", NOT_REPRESENTABLE,
               "PoB generates this group from %r and generates it again on "
               "load; it is not imported" % group.get("source"),
               group.get("source"), False)
    changed = []
    if group.get("enabled", "true") != "true":
        changed.append("enabled=%s" % group.get("enabled"))
    if group.get("mainActiveSkill") not in (None, "nil", "1"):
        changed.append("mainActiveSkill=%s" % group.get("mainActiveSkill"))
    for name, allowed in GROUP_DEFAULTS.items():
        value = group.get(name)
        if value is not None and value not in allowed:
            changed.append("%s=%s" % (name, value))
    for gem in group.findall("Gem"):
        for name, allowed in GENERATED_GEM_DEFAULTS.items():
            value = gem.get(name)
            if value is not None and value not in allowed:
                changed.append("%s %s=%s" % (gem.get("skillId"), name, value))
    if changed:
        losses.add(path, PARTIAL,
                   "settings changed on a PoB-generated group are not "
                   "represented: " + ", ".join(changed),
                   ET.tostring(group, encoding="unicode"), True)


def _audit_items_and_config(root: ET.Element, losses: LossCollector) -> None:
    """Item-set, item and config state that BuildSpec does not hold."""
    items = root.find("Items")
    if items is not None:
        sets = items.findall("ItemSet") or [items]
        if items.get("useSecondWeaponSet") == "true" or any(
                s.get("useSecondWeaponSet") == "true" for s in sets):
            losses.add("/Items/@useSecondWeaponSet", PARTIAL,
                       "PoB is set to use the second weapon set; BuildSpec "
                       "does not record which weapon set is active", "true",
                       True)
        for item_set in sets:
            for slot in item_set.findall("Slot"):
                if slot.get("active") == "true":
                    losses.add("/Items/ItemSet/Slot/@active", PARTIAL,
                               "an activated flask or charm slot; BuildSpec "
                               "does not record activation",
                               slot.get("name"), True)
            for rune in item_set.findall("RuneSlot"):
                if rune.get("runeName", "None") != "None":
                    losses.add("/Items/ItemSet/RuneSlot", PARTIAL,
                               "a rune selected in a rune slot is not "
                               "represented", ET.tostring(rune, encoding="unicode"),
                               True)
        for item in items.findall("Item"):
            for name, value in item.attrib.items():
                if name.startswith("variantAlt"):
                    losses.add("/Items/Item/@" + name, PARTIAL,
                               "an alternate unique variant selection is not "
                               "represented", value, True)
    for spec in root.findall("Tree/Spec"):
        secondary = spec.get("secondaryAscendClassId")
        if secondary not in (None, "nil", "0"):
            losses.add("/Tree/Spec/@secondaryAscendClassId", PARTIAL,
                       "a secondary ascendancy is not represented", secondary,
                       True)
        if spec.get("masteryEffects"):
            losses.add("/Tree/Spec/@masteryEffects", PARTIAL,
                       "mastery effect choices are not represented",
                       spec.get("masteryEffects"), True)
    for config_set in root.findall("Config/ConfigSet") + root.findall("Config"):
        for child in config_set:
            if child.tag in ("Input", "Placeholder", "ConfigSet"):
                continue
            if child.tag == "CustomModifierBlock":
                if (child.text or "").strip() and child.get("enabled") != "false":
                    losses.add("/Config/CustomModifierBlock", PARTIAL,
                               "custom modifier text changes calculations "
                               "and is not represented", child.text, True)
                continue
            losses.add("/Config/" + child.tag, PARTIAL,
                       "a config element BuildSpec does not represent",
                       ET.tostring(child, encoding="unicode"), True)


#: Gem attributes BuildSpec does not hold, with the values the pinned PoB
#: writes when nothing was chosen (SkillsTab.lua save; "nil" is PoB writing
#: ``tostring(nil)``). Any other value is a gameplay setting this record loses.
GEM_DEFAULTS = {
    "count": ("1",),
    "enableGlobal1": ("true",),
    "enableGlobal2": ("false",),
    "corrupted": ("false",),
    "corruptLevel": ("0",),
    "statSetIndex": ("nil", "1"),
    "skillPart": (),
    "skillStageCount": (),
    "skillMineCount": (),
    "skillMinion": (),
    "skillMinionItemSet": (),
    "skillMinionSkill": (),
}

#: Calcs-tab selections. CalcsTab.lua reads them for its own display output,
#: not for the main output a build is evaluated on, so losing one is reported
#: without blocking the record.
#: PoB writes generated gems with both global effects on, and an empty
#: placeholder gem with "nil" settings. Anything else is an author's choice.
GENERATED_GEM_DEFAULTS = {
    name: tuple(allowed) + ("nil",) for name, allowed in GEM_DEFAULTS.items()}
GENERATED_GEM_DEFAULTS["enableGlobal2"] = ("false", "true", "nil")

GEM_DISPLAY_ONLY = {
    "statSetIndexCalcs": ("nil", "1"),
    "skillPartCalcs": (),
    "skillStageCountCalcs": (),
    "skillMineCountCalcs": (),
    "skillMinionCalcs": (),
    "skillMinionItemSetCalcs": (),
    "skillMinionSkillCalcs": (),
}

GROUP_DEFAULTS = {
    "includeInFullDPS": ("nil", "false"),
    "groupCount": ("nil", "1"),
    "skillPart": (),
}

GROUP_DISPLAY_ONLY = {
    "mainActiveSkillCalcs": ("1", "nil"),
}


def _is_int(text: str) -> bool:
    try:
        int(text)
    except ValueError:
        return False
    return True


def _audit_attributes(node: ET.Element, defaults, display_only, path: str,
                      losses: LossCollector) -> None:
    for table, blocking in ((defaults, True), (display_only, False)):
        for name, allowed in table.items():
            value = node.get(name)
            if value is None or value in allowed:
                continue
            if blocking:
                losses.add("%s/@%s" % (path, name), PARTIAL,
                           "BuildSpec does not represent this setting and "
                           "the value differs from PoB's default",
                           value, True)
            else:
                losses.add("%s/@%s" % (path, name), NOT_REPRESENTABLE,
                           "Calcs-tab display selection; not represented and "
                           "not part of the main output", value, False)
