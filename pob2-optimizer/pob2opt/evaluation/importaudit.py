"""Select active PoB sets and retain content the BuildSpec cannot represent."""
from __future__ import annotations

import xml.etree.ElementTree as ET

from .naming import CatalogNaming, UnresolvedName
from .support import LossCollector, PARTIAL, UNRESOLVED_NAME


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
    for group in root.findall("Skills/SkillSet/Skill") + root.findall("Skills/Skill"):
        if group.get("slot"):
            resolve("slot_names", group.get("slot"), "/Skills/Skill/@slot")
        for gem in group.findall("Gem"):
            skill_id = resolve("skill_ids", gem.get("skillId", ""), "/Skills/Gem/@skillId")
            if gem.get("gemId"):
                resolve("gem_ids", gem.get("gemId"), "/Skills/Gem/@gemId")
            if skill_id in naming.support_skill_ids:
                losses.add("/Skills/Gem/support", PARTIAL,
                           "BuildSpec support IDs cannot retain enabled, level or quality settings",
                           ET.tostring(gem, encoding="unicode"), False)
