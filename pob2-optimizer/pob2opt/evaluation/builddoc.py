"""A BuildSpec as a PoB document, and back again (P02-T05).

P02-T01 refused to write a BuildSpec out, because the only faithful document
was the one the build was parsed from. This module is the export it named, and
it is deliberately not a silent one: everything the PoB format cannot carry is
reported as an :class:`~pob2opt.evaluation.support.UnsupportedField`, and an
export that loses anything inside the canonical build identity is labelled
``incomplete`` and is not a recommended deliverable.

The document shape follows the pinned PoB's own savers: ``Build``, ``Skills``
with one ``SkillSet``, ``Tree`` with one ``Spec``, ``Items`` with one
``ItemSet`` and ``Config`` with one ``ConfigSet``. PoB reassigns its own
internal numeric item and node IDs on load, so a round trip is compared on
``build_identity``, never on XML bytes.

What this module refuses to do:

* translate a catalog ID on its own. Class, ascendancy, slot, base, skill, gem
  and passive node names come from a caller-supplied
  :class:`~pob2opt.evaluation.naming.CatalogNaming`; a missing entry is
  reported, not guessed. P02-T02 owns the real table;
* invent a value the record does not hold. A support gem has no level in a
  BuildSpec, so the document omits the attribute rather than writing one;
* resolve modifier text into effects. That is P04.

Neither direction mutates its input.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from dataclasses import dataclass, replace
from typing import Any, Mapping, Sequence

from ..domain.enums import ConfigOrigin, RecordParseStatus
from ..domain.records import (BuildSpec, ConfigValue, EquipmentSlot,
                              ItemInstance, Passives, Progression, SkillEntry,
                              SkillGroup, SocketedEntity, WeaponSet)
from .itemtext import export_item, import_item
from .naming import CatalogNaming, UnresolvedName
from .support import (NOT_REPRESENTABLE, PARTIAL, UNRESOLVED_NAME,
                      LossCollector, SupportReport)

#: Written so PoB does not recompute the level from an empty tree
#: (observation P00-OBS-02).
CHARACTER_LEVEL_AUTO_MODE = "false"

#: The attribute names PoB's ``AttributeOverride`` element carries.
ATTRIBUTE_NODE_ATTRIBUTES = {"Strength": "strNodes", "Dexterity": "dexNodes",
                             "Intelligence": "intNodes"}

SUPPORT = {
    "round_trips": (
        "class_id, ascendancy_id, level",
        "equipment, including an explicitly empty slot",
        "weapon sets: hand slots and per-set passive allocations",
        "passive allocations, the ordinary and ascendancy split, and "
        "attribute choices",
        "jewel sockets on passive nodes",
        "skill groups: order, enabled flag, slot, weapon-set binding, main "
        "skill index, and each skill with its ordered supports",
        "config values of type boolean, number and string",
    ),
    "not_representable": (
        "progression: PoB records no quest or reward flags and no point "
        "budgets",
        "SkillGroup.source_item_hash: PoB regenerates an item-granted group "
        "from the item, and an unknown source string makes it discard the "
        "group",
        "SkillEntry.triggered: a PoB socket group is a flat gem list with no "
        "nesting",
        "a passive choice that is not one of Strength, Dexterity or "
        "Intelligence",
        "more than two weapon sets",
        "BuildSpec.name, variant_id, family_id, rotation_ids, "
        "source_document_ids, declared_patch and unresolved_refs: metadata "
        "the build identity excludes",
    ),
}


@dataclass(frozen=True)
class BuildExport:
    """An exported document and everything it could not carry."""

    xml: str
    report: SupportReport
    #: item_hash -> the numeric ``Item@id`` written for it. PoB may renumber.
    item_ids: Mapping[str, int]

    @property
    def completeness(self) -> str:
        return self.report.completeness

    @property
    def recommended_deliverable(self) -> bool:
        return self.report.recommended_deliverable


@dataclass(frozen=True)
class BuildImport:
    """A BuildSpec read back out of a document, with the items it carried."""

    build: BuildSpec
    items: Mapping[str, ItemInstance]


# ------------------------------------------------------------------ export

def _node_list(ids: Sequence[str], naming: CatalogNaming,
               losses: LossCollector, path: str) -> list[int]:
    out: list[int] = []
    for passive_id in ids:
        try:
            out.append(int(naming.resolve("node_ids", passive_id)))
        except UnresolvedName:
            losses.add(path, UNRESOLVED_NAME,
                       "CatalogNaming.node_ids has no native tree node for "
                       "this passive; PoB reads Spec@nodes as integers only",
                       passive_id, True)
    return out


def _export_tree(build: BuildSpec, naming: CatalogNaming,
                 losses: LossCollector, jewel_ids: Mapping[str, int],
                 tree_version: str) -> ET.Element:
    tree = ET.Element("Tree", {"activeSpec": "1"})
    spec_attrib = {"treeVersion": tree_version, "secondaryAscendClassId": "0"}
    try:
        spec_attrib["classId"] = str(naming.resolve("class_tree_ids",
                                                    build.class_id))
    except UnresolvedName:
        losses.add("/class_id", UNRESOLVED_NAME,
                   "CatalogNaming.class_tree_ids has no numeric tree class ID",
                   build.class_id, True)
        spec_attrib["classId"] = "0"
    if build.ascendancy_id is None:
        spec_attrib["ascendClassId"] = "0"
    else:
        try:
            spec_attrib["ascendClassId"] = str(
                naming.resolve("ascendancy_tree_ids", build.ascendancy_id))
        except UnresolvedName:
            losses.add("/ascendancy_id", UNRESOLVED_NAME,
                       "CatalogNaming.ascendancy_tree_ids has no numeric tree "
                       "ascendancy ID", build.ascendancy_id, True)
            spec_attrib["ascendClassId"] = "0"

    ordinary = _node_list(sorted(build.passives.allocated), naming, losses,
                          "/passives/allocated")
    ascend = _node_list(sorted(build.passives.ascendancy_allocated), naming,
                        losses, "/passives/ascendancy_allocated")
    for passive_id in sorted(build.passives.ascendancy_allocated):
        if passive_id not in naming.ascendancy_node_ids:
            losses.add("/passives/ascendancy_allocated", NOT_REPRESENTABLE,
                       "PoB keeps ordinary and ascendancy allocations in one "
                       "nodes list; CatalogNaming.ascendancy_node_ids must "
                       "declare this node or the split cannot be read back",
                       passive_id, True)
    for passive_id in sorted(build.passives.allocated):
        if passive_id in naming.ascendancy_node_ids:
            losses.add("/passives/allocated", NOT_REPRESENTABLE,
                       "this passive is declared an ascendancy node, so it "
                       "would read back in the other list", passive_id, True)
    allocated = set(build.passives.allocated) | set(
        build.passives.ascendancy_allocated)
    set_nodes: list[tuple[int, list[int]]] = []
    for weapon_set in build.weapon_sets:
        if not weapon_set.passive_allocations:
            continue
        try:
            number = int(naming.resolve("weapon_set_numbers",
                                        weapon_set.set_id))
        except UnresolvedName:
            continue  # _check_weapon_sets reports the missing table entry
        if number not in (1, 2):
            losses.add("/weapon_sets", NOT_REPRESENTABLE,
                       "PoB has two weapon sets", weapon_set.set_id, True)
            continue
        for passive_id in sorted(weapon_set.passive_allocations):
            if passive_id not in allocated:
                losses.add("/weapon_sets/" + weapon_set.set_id
                           + "/passive_allocations", NOT_REPRESENTABLE,
                           "PoB records a weapon set on an allocated node, so "
                           "a per-set allocation of a node the build does not "
                           "allocate cannot be written", passive_id, True)
        nodes = _node_list(sorted(weapon_set.passive_allocations), naming,
                           losses, "/weapon_sets/passive_allocations")
        set_nodes.append((number, sorted(nodes)))

    # PoB reads the allocation from Spec@nodes and only the set from
    # WeaponSetN, so a set node missing from nodes would not be allocated.
    every_node = sorted(set(ordinary) | set(ascend)
                        | {n for _, nodes in set_nodes for n in nodes})
    spec_attrib["nodes"] = ",".join(str(n) for n in every_node)
    spec = ET.SubElement(tree, "Spec", spec_attrib)
    for number, nodes in sorted(set_nodes):
        ET.SubElement(spec, "WeaponSet%d" % number,
                      {"nodes": ",".join(str(n) for n in nodes)})

    sockets = ET.SubElement(spec, "Sockets")
    for socketed in sorted(build.passives.socketed,
                           key=lambda s: (s.node_id, s.entity_id)):
        item_id = jewel_ids.get(socketed.entity_id)
        if item_id is None:
            losses.add("/passives/socketed", UNRESOLVED_NAME,
                       "the socketed entity is not one of the items supplied "
                       "to the export, so no Item element exists to point at",
                       socketed.entity_id, True)
            continue
        try:
            node_id = int(naming.resolve("node_ids", socketed.node_id))
        except UnresolvedName:
            losses.add("/passives/socketed", UNRESOLVED_NAME,
                       "CatalogNaming.node_ids has no native tree node for "
                       "the socket", socketed.node_id, True)
            continue
        ET.SubElement(sockets, "Socket", {"nodeId": str(node_id),
                                          "itemId": str(item_id)})

    overrides = ET.SubElement(spec, "Overrides")
    attribute_nodes: dict[str, list[int]] = {k: [] for k in
                                             ATTRIBUTE_NODE_ATTRIBUTES}
    for node_key in sorted(build.passives.choices):
        option = build.passives.choices[node_key]
        try:
            attribute = naming.resolve("attribute_options", option)
        except UnresolvedName:
            losses.add("/passives/choices/" + node_key, NOT_REPRESENTABLE,
                       "PoB's AttributeOverride carries only Strength, "
                       "Dexterity and Intelligence choices", option, True)
            continue
        if attribute not in ATTRIBUTE_NODE_ATTRIBUTES:
            losses.add("/passives/choices/" + node_key, NOT_REPRESENTABLE,
                       "not a PoB attribute choice", attribute, True)
            continue
        try:
            attribute_nodes[attribute].append(
                int(naming.resolve("node_ids", node_key)))
        except UnresolvedName:
            losses.add("/passives/choices/" + node_key, UNRESOLVED_NAME,
                       "CatalogNaming.node_ids has no native tree node for "
                       "the chosen passive", node_key, True)
    ET.SubElement(overrides, "AttributeOverride", {
        attribute: ",".join(str(n) for n in sorted(attribute_nodes[name]))
        for name, attribute in ATTRIBUTE_NODE_ATTRIBUTES.items()})
    return tree


def _export_skills(build: BuildSpec, naming: CatalogNaming,
                   losses: LossCollector) -> tuple[ET.Element, int]:
    skills = ET.Element("Skills", {"activeSkillSet": "1",
                                   "sortGemsByDPS": "true",
                                   "sortGemsByDPSField": "CombinedDPS"})
    skill_set = ET.SubElement(skills, "SkillSet", {"id": "1",
                                                   "title": "Default"})
    main_socket_group = 1
    for index, group in enumerate(build.skill_groups):
        path = "/skill_groups/%d" % index
        attrib: dict[str, str] = {
            "enabled": "true" if group.enabled else "false",
            "label": group.group_id,
        }
        if group.slot_id is not None:
            try:
                attrib["slot"] = naming.resolve("slot_names", group.slot_id)
            except UnresolvedName:
                losses.add(path + "/slot_id", UNRESOLVED_NAME,
                           "CatalogNaming.slot_names has no PoB slot name",
                           group.slot_id, True)
        if group.source_item_hash is not None:
            losses.add(path + "/source_item_hash", NOT_REPRESENTABLE,
                       "PoB regenerates an item-granted group from the item "
                       "itself and discards a group whose source string it "
                       "does not recognise", group.source_item_hash, True)
        set1, set2 = True, True
        if group.weapon_set_id is not None:
            try:
                number = int(naming.resolve("weapon_set_numbers",
                                            group.weapon_set_id))
            except UnresolvedName:
                losses.add(path + "/weapon_set_id", UNRESOLVED_NAME,
                           "CatalogNaming.weapon_set_numbers has no PoB "
                           "weapon set number", group.weapon_set_id, True)
                number = 0
            set1, set2 = number == 1, number == 2
        attrib["set1"] = "true" if set1 else "false"
        attrib["set2"] = "true" if set2 else "false"
        if group.main_skill_index is not None:
            attrib["mainActiveSkill"] = str(group.main_skill_index + 1)
            if main_socket_group == 1:
                main_socket_group = index + 1
        node = ET.SubElement(skill_set, "Skill", attrib)
        for skill_index, skill in enumerate(group.skills):
            _export_skill(node, skill, naming, losses,
                          "%s/skills/%d" % (path, skill_index))
    return skills, main_socket_group


def _export_skill(parent: ET.Element, skill: SkillEntry,
                  naming: CatalogNaming, losses: LossCollector,
                  path: str) -> None:
    attrib = {"level": str(skill.level), "quality": str(skill.quality),
              "enabled": "true" if skill.enabled else "false", "count": "1"}
    try:
        attrib["skillId"] = naming.resolve("skill_ids", skill.skill_id)
    except UnresolvedName:
        losses.add(path + "/skill_id", UNRESOLVED_NAME,
                   "CatalogNaming.skill_ids has no PoB skill ID",
                   skill.skill_id, True)
    if skill.gem_id is not None:
        try:
            attrib["gemId"] = naming.resolve("gem_ids", skill.gem_id)
        except UnresolvedName:
            losses.add(path + "/gem_id", UNRESOLVED_NAME,
                       "CatalogNaming.gem_ids has no PoB gem ID",
                       skill.gem_id, True)
    ET.SubElement(parent, "Gem", attrib)
    for support_index, support_id in enumerate(skill.support_ids):
        support_path = "%s/support_ids/%d" % (path, support_index)
        if support_id not in naming.support_skill_ids:
            losses.add(support_path, NOT_REPRESENTABLE,
                       "a PoB socket group is a flat gem list; without "
                       "CatalogNaming.support_skill_ids declaring this ID a "
                       "support, it reads back as another active skill",
                       support_id, True)
        try:
            support_attrib = {"skillId": naming.resolve("skill_ids",
                                                        support_id),
                              "enabled": "true", "count": "1"}
        except UnresolvedName:
            losses.add(support_path, UNRESOLVED_NAME,
                       "CatalogNaming.skill_ids has no PoB skill ID for this "
                       "support", support_id, True)
            continue
        # A BuildSpec records no level or quality for a support, so none is
        # written. Inventing one would be a gameplay claim this task does not
        # own; PoB applies its own default instead.
        losses.add(support_path, PARTIAL,
                   "BuildSpec carries no level or quality for a support gem, "
                   "so the document omits both and PoB applies its default",
                   support_id, False)
        ET.SubElement(parent, "Gem", support_attrib)
    if skill.triggered:
        losses.add(path + "/triggered", NOT_REPRESENTABLE,
                   "a PoB socket group is a flat gem list with no trigger "
                   "nesting; the nested skills would read back as siblings",
                   [child.skill_id for child in skill.triggered], True)


def _export_items(build: BuildSpec, items: Mapping[str, ItemInstance],
                  naming: CatalogNaming,
                  losses: LossCollector) -> tuple[ET.Element, dict[str, int]]:
    element = ET.Element("Items", {"activeItemSet": "1",
                                   "useSecondWeaponSet": "false"})
    wanted: list[str] = []
    for slot_id in sorted(build.equipment):
        content = build.equipment[slot_id]
        if content is not None and content.item_hash not in wanted:
            wanted.append(content.item_hash)
    for socketed in sorted(build.passives.socketed,
                           key=lambda s: (s.node_id, s.entity_id)):
        if socketed.entity_id not in wanted:
            wanted.append(socketed.entity_id)

    item_ids: dict[str, int] = {}
    for item_hash in wanted:
        item = items.get(item_hash)
        if item is None:
            losses.add("/equipment", UNRESOLVED_NAME,
                       "no ItemInstance was supplied for this item hash, so "
                       "the document cannot carry the item", item_hash, True)
            continue
        item_id = len(item_ids) + 1
        item_ids[item_hash] = item_id
        text, item_losses = export_item(item, naming,
                                        prefix="/items/" + item_hash)
        losses.extend(item_losses.report().unsupported)
        node = ET.SubElement(element, "Item", {"id": str(item_id)})
        node.text = "\n" + text + "\n"

    item_set = ET.SubElement(element, "ItemSet", {"id": "1", "title": "Default",
                                                  "useSecondWeaponSet": "false"})
    for slot_id in sorted(build.equipment):
        content = build.equipment[slot_id]
        try:
            slot_name = naming.resolve("slot_names", slot_id)
        except UnresolvedName:
            losses.add("/equipment/" + slot_id, UNRESOLVED_NAME,
                       "CatalogNaming.slot_names has no PoB slot name",
                       None if content is None else content.item_hash, True)
            continue
        item_id = 0 if content is None else item_ids.get(content.item_hash, 0)
        ET.SubElement(item_set, "Slot", {"name": slot_name,
                                         "itemId": str(item_id)})
        if content is not None and content.listing_id is not None:
            losses.add("/equipment/" + slot_id + "/listing_id",
                       NOT_REPRESENTABLE,
                       "a PoB document records no listing; build identity "
                       "excludes it too", content.listing_id, False)
    _check_weapon_sets(build, naming, losses)
    return element, item_ids


def _expected_hand_slots(number: int, naming: CatalogNaming,
                         equipment: Mapping[str, Any]) -> dict[str, Any]:
    """What PoB weapon set ``number`` reads back as, given this equipment."""
    suffix = "" if number == 1 else " Swap"
    expected: dict[str, Any] = {}
    for hand, pob_name in (("main_hand", "Weapon 1" + suffix),
                           ("off_hand", "Weapon 2" + suffix)):
        slot_id = _reverse(naming, "slot_names", pob_name)
        expected[hand] = slot_id if slot_id in equipment else None
    return expected


def _check_weapon_sets(build: BuildSpec, naming: CatalogNaming,
                       losses: LossCollector) -> None:
    """Report every weapon set the document would not read back as declared.

    PoB has two fixed sets and no list of its own: a set exists in a document
    because a hand slot is filled or a per-set node list names it. So a
    declared set that leaves no trace, and an undeclared set the equipment
    implies, are both reported.
    """
    declared = {weapon_set.set_id: weapon_set
                for weapon_set in build.weapon_sets}
    for weapon_set in build.weapon_sets:
        if weapon_set.set_id not in naming.weapon_set_numbers:
            losses.add("/weapon_sets/" + weapon_set.set_id, UNRESOLVED_NAME,
                       "CatalogNaming.weapon_set_numbers has no PoB weapon "
                       "set number for this set", weapon_set.set_id, True)
    for set_id, number in sorted(naming.weapon_set_numbers.items(),
                                 key=lambda pair: pair[1]):
        if number not in (1, 2):
            continue
        expected = _expected_hand_slots(number, naming, build.equipment)
        weapon_set = declared.get(set_id)
        allocations = [] if weapon_set is None else list(
            weapon_set.passive_allocations)
        implied = any(expected.values()) or bool(allocations)
        if weapon_set is None:
            if implied:
                losses.add("/weapon_sets", NOT_REPRESENTABLE,
                           "equipment fills PoB weapon set %d, so the "
                           "document reads back a weapon set this build does "
                           "not declare" % number, expected, True)
            continue
        if not implied:
            losses.add("/weapon_sets/" + set_id, NOT_REPRESENTABLE,
                       "a weapon set with no per-set passive allocation and "
                       "no hand slot in equipment leaves no trace in a PoB "
                       "document", dict(weapon_set.hand_slots), True)
            continue
        if dict(weapon_set.hand_slots) != expected:
            losses.add("/weapon_sets/" + set_id + "/hand_slots",
                       NOT_REPRESENTABLE,
                       "PoB's weapon sets are the fixed slot pairs "
                       "Weapon 1/Weapon 2 and their Swap pair, read back as "
                       "main_hand and off_hand; these read back as %r"
                       % (expected,), dict(weapon_set.hand_slots), True)


def _export_config(build: BuildSpec, losses: LossCollector) -> ET.Element:
    config = ET.Element("Config", {"activeConfigSet": "1"})
    config_set = ET.SubElement(config, "ConfigSet", {"id": "1",
                                                     "title": "Default"})
    for name in sorted(build.config):
        entry = build.config[name]
        value = entry.value
        if isinstance(value, bool):
            attrib = {"name": name, "boolean": "true" if value else "false"}
        elif isinstance(value, int):
            attrib = {"name": name, "number": str(value)}
        elif isinstance(value, float):
            attrib = {"name": name, "number": repr(value)}
        elif isinstance(value, str):
            attrib = {"name": name, "string": value}
        else:
            losses.add("/config/" + name, NOT_REPRESENTABLE,
                       "a PoB config input is a boolean, a number or a string",
                       value, True)
            continue
        if entry.origin is not ConfigOrigin.SOURCE:
            losses.add("/config/" + name + "/origin", NOT_REPRESENTABLE,
                       "a PoB document records no config origin; identity "
                       "excludes it", entry.origin.value, False)
        ET.SubElement(config_set, "Input", attrib)
    return config


def export_build(build: BuildSpec, items: Mapping[str, ItemInstance],
                 naming: CatalogNaming, *,
                 tree_version: str = "0_5",
                 target_version: str = "0_1") -> BuildExport:
    """A BuildSpec as a PoB document, with everything it could not carry.

    ``items`` maps item hash to the ItemInstance for every equipped item and
    every socketed jewel. A hash with no instance is reported, never written
    as an empty slot.
    """
    naming.check_invertible()
    losses = LossCollector()

    for path, value in (("/name", build.name),
                        ("/variant_id", build.variant_id),
                        ("/family_id", build.family_id),
                        ("/declared_patch", build.declared_patch)):
        if value is not None and value != "":
            losses.add(path, NOT_REPRESENTABLE,
                       "a PoB document does not carry this; build identity "
                       "excludes it too", value, False)
    if build.rotation_ids:
        losses.add("/rotation_ids", NOT_REPRESENTABLE,
                   "rotations are this project's records, not PoB's",
                   list(build.rotation_ids), False)
    if build.source_document_ids:
        losses.add("/source_document_ids", NOT_REPRESENTABLE,
                   "provenance is not part of a PoB document",
                   list(build.source_document_ids), False)
    if build.unresolved_refs:
        losses.add("/unresolved_refs", NOT_REPRESENTABLE,
                   "a PoB document records no parse state",
                   [ref.field_path for ref in build.unresolved_refs], False)
    progression = build.progression
    if (progression.quest_flags or progression.reward_flags
            or progression.normal_point_budget is not None
            or progression.ascendancy_point_budget is not None):
        losses.add("/progression", NOT_REPRESENTABLE,
                   "PoB records no quest or reward flags and no point "
                   "budgets, so none of this reads back",
                   {"quest_flags": dict(progression.quest_flags),
                    "reward_flags": dict(progression.reward_flags),
                    "normal_point_budget": progression.normal_point_budget,
                    "ascendancy_point_budget":
                        progression.ascendancy_point_budget}, True)

    items_element, item_ids = _export_items(build, items, naming, losses)
    tree_element = _export_tree(build, naming, losses, item_ids, tree_version)
    skills_element, main_socket_group = _export_skills(build, naming, losses)
    config_element = _export_config(build, losses)

    build_attrib = {
        "level": str(build.level),
        "targetVersion": target_version,
        "viewMode": "TREE",
        "mainSocketGroup": str(main_socket_group),
        "characterLevelAutoMode": CHARACTER_LEVEL_AUTO_MODE,
    }
    try:
        build_attrib["className"] = naming.resolve("class_names",
                                                   build.class_id)
    except UnresolvedName:
        losses.add("/class_id", UNRESOLVED_NAME,
                   "CatalogNaming.class_names has no PoB class name",
                   build.class_id, True)
        build_attrib["className"] = ""
    if build.ascendancy_id is None:
        build_attrib["ascendClassName"] = "None"
    else:
        try:
            build_attrib["ascendClassName"] = naming.resolve(
                "ascendancy_names", build.ascendancy_id)
        except UnresolvedName:
            losses.add("/ascendancy_id", UNRESOLVED_NAME,
                       "CatalogNaming.ascendancy_names has no PoB ascendancy "
                       "name", build.ascendancy_id, True)
            build_attrib["ascendClassName"] = "None"

    root = ET.Element("PathOfBuilding2")
    ET.SubElement(root, "Build", build_attrib)
    ET.SubElement(root, "Import")
    ET.SubElement(root, "Calcs")
    root.append(skills_element)
    root.append(tree_element)
    root.append(items_element)
    root.append(config_element)
    ET.SubElement(root, "Notes")
    ET.SubElement(root, "TreeView", {"searchStr": "", "zoomLevel": "3",
                                     "zoomX": "0", "zoomY": "0",
                                     "showStatDifferences": "true"})
    ET.indent(root, space="\t")
    body = ET.tostring(root, encoding="unicode")
    document = '<?xml version="1.0" encoding="UTF-8"?>\n' + body + "\n"
    return BuildExport(xml=document, report=losses.report(),
                       item_ids=item_ids)


# ------------------------------------------------------------------ import

def _reverse(naming: CatalogNaming, table: str, value) -> str | None:
    try:
        return naming.reverse(table, value)
    except UnresolvedName:
        return None


def _split_ids(text: str | None) -> list[int]:
    if not text:
        return []
    return [int(part) for part in text.replace(" ", "").split(",") if part]


def import_build(document: str, naming: CatalogNaming, *, record_id: str,
                 created_at: str, catalog_hash: str,
                 provenance_ids: Sequence[str] = ()) -> BuildImport:
    """Read a PoB document back into a BuildSpec and its items.

    Only the document decides the result. Nothing is carried over from the
    record it was written from, so a round trip measures the document.
    """
    from ..domain.identity import build_hash as _build_hash

    naming.check_invertible()
    root = ET.fromstring(document)
    build_element = root.find("Build")
    if build_element is None:
        raise ValueError("document has no Build element")

    class_id = _reverse(naming, "class_names",
                        build_element.get("className", ""))
    ascend_name = build_element.get("ascendClassName", "None")
    ascendancy_id = (None if ascend_name in ("", "None")
                     else _reverse(naming, "ascendancy_names", ascend_name))
    level = int(build_element.get("level", "1"))

    items, item_by_id = _import_items(root, naming, record_id, created_at,
                                      catalog_hash)
    equipment, slot_ids_by_name = _import_equipment(root, naming, item_by_id)
    passives, weapon_set_nodes = _import_tree(root, naming, item_by_id)
    weapon_sets = _import_weapon_sets(naming, weapon_set_nodes,
                                      slot_ids_by_name)
    skill_groups = _import_skills(root, naming)
    config = _import_config(root)

    build = BuildSpec(
        schema_version=1, record_id=record_id, created_at=created_at,
        provenance_ids=list(provenance_ids), build_hash="",
        catalog_hash=catalog_hash, declared_patch=None, name="",
        class_id=class_id if class_id is not None else "",
        ascendancy_id=ascendancy_id, level=level,
        progression=Progression(quest_flags={}, reward_flags={},
                                normal_point_budget=None,
                                ascendancy_point_budget=None,
                                evidence_ids=[]),
        equipment=equipment, weapon_sets=weapon_sets, passives=passives,
        skill_groups=skill_groups, config=config, rotation_ids=[],
        source_document_ids=[], variant_id=None, family_id=None,
        raw_blob_hashes=[], parse_status=RecordParseStatus.COMPLETE,
        unresolved_refs=[])
    build = replace(build, build_hash=_build_hash(build))
    return BuildImport(build=build, items=items)


def _import_items(root: ET.Element, naming: CatalogNaming, record_id: str,
                  created_at: str, catalog_hash: str):
    items: dict[str, ItemInstance] = {}
    item_by_id: dict[int, str] = {}
    container = root.find("Items")
    if container is None:
        return items, item_by_id
    for index, node in enumerate(container.findall("Item")):
        text = (node.text or "").strip("\n")
        if not text.strip():
            continue
        item = import_item(text, naming,
                           record_id="%s-item-%d" % (record_id, index),
                           created_at=created_at, catalog_hash=catalog_hash)
        items[item.item_hash] = item
        numeric = node.get("id")
        if numeric is not None:
            item_by_id[int(numeric)] = item.item_hash
    return items, item_by_id


def _import_equipment(root: ET.Element, naming: CatalogNaming,
                      item_by_id: Mapping[int, str]):
    equipment: dict[str, EquipmentSlot | None] = {}
    hand_slots: dict[str, str] = {}
    container = root.find("Items")
    if container is None:
        return equipment, hand_slots
    item_set = container.find("ItemSet")
    if item_set is None:
        return equipment, hand_slots
    for node in item_set.findall("Slot"):
        name = node.get("name", "")
        slot_id = _reverse(naming, "slot_names", name)
        if slot_id is None:
            continue
        hand_slots[name] = slot_id
        item_id = int(node.get("itemId", "0"))
        item_hash = item_by_id.get(item_id)
        equipment[slot_id] = (None if item_hash is None
                              else EquipmentSlot(item_hash=item_hash,
                                                 listing_id=None))
    return equipment, hand_slots


def _import_tree(root: ET.Element, naming: CatalogNaming,
                 item_by_id: Mapping[int, str]):
    allocated: list[str] = []
    ascendancy_allocated: list[str] = []
    choices: dict[str, str] = {}
    socketed: list[SocketedEntity] = []
    weapon_set_nodes: dict[int, list[str]] = {}
    tree = root.find("Tree")
    spec = None if tree is None else tree.find("Spec")
    if spec is None:
        return (Passives(allocated=[], ascendancy_allocated=[], choices={},
                         socketed=[]), weapon_set_nodes)

    for native in _split_ids(spec.get("nodes")):
        passive_id = _reverse(naming, "node_ids", native)
        if passive_id is None:
            continue
        if passive_id in naming.ascendancy_node_ids:
            ascendancy_allocated.append(passive_id)
        else:
            allocated.append(passive_id)

    for child in spec:
        if child.tag.startswith("WeaponSet"):
            number = int(child.tag[len("WeaponSet"):])
            names = [_reverse(naming, "node_ids", native)
                     for native in _split_ids(child.get("nodes"))]
            weapon_set_nodes[number] = [n for n in names if n is not None]
        elif child.tag == "Sockets":
            for socket in child.findall("Socket"):
                node_id = _reverse(naming, "node_ids",
                                   int(socket.get("nodeId", "0")))
                entity = item_by_id.get(int(socket.get("itemId", "0")))
                if node_id is not None and entity is not None:
                    socketed.append(SocketedEntity(node_id=node_id,
                                                   entity_id=entity))
        elif child.tag == "Overrides":
            for override in child.findall("AttributeOverride"):
                for attribute, key in ATTRIBUTE_NODE_ATTRIBUTES.items():
                    option_id = _reverse(naming, "attribute_options",
                                         attribute)
                    if option_id is None:
                        continue
                    for native in _split_ids(override.get(key)):
                        passive_id = _reverse(naming, "node_ids", native)
                        if passive_id is not None:
                            choices[passive_id] = option_id

    passives = Passives(allocated=sorted(allocated),
                        ascendancy_allocated=sorted(ascendancy_allocated),
                        choices=choices, socketed=socketed)
    return passives, weapon_set_nodes


def _import_weapon_sets(naming: CatalogNaming,
                        weapon_set_nodes: Mapping[int, Sequence[str]],
                        hand_slots: Mapping[str, str]) -> list[WeaponSet]:
    """Rebuild the weapon sets PoB's two fixed sets can express.

    PoB has exactly two: ``Weapon 1``/``Weapon 2`` and their ``Swap`` pair.
    A set exists in the document when it has its own node list or one of its
    hand slots is in the item set. A set that leaves neither trace is not
    invented here; the export reports that it could not be written.
    """
    sets: list[WeaponSet] = []
    for set_id, number in sorted(naming.weapon_set_numbers.items(),
                                 key=lambda pair: pair[1]):
        suffix = "" if number == 1 else " Swap"
        hands: dict[str, str | None] = {}
        for hand, pob_name in (("main_hand", "Weapon 1" + suffix),
                               ("off_hand", "Weapon 2" + suffix)):
            hands[hand] = hand_slots.get(pob_name)
        allocations = sorted(weapon_set_nodes.get(number, []))
        if not allocations and not any(hands.values()):
            continue
        sets.append(WeaponSet(set_id=set_id, hand_slots=hands,
                              passive_allocations=allocations))
    return sets


def _import_skills(root: ET.Element, naming: CatalogNaming) -> list[SkillGroup]:
    groups: list[SkillGroup] = []
    container = root.find("Skills")
    if container is None:
        return groups
    skill_set = container.find("SkillSet")
    nodes = (container if skill_set is None else skill_set).findall("Skill")
    for node in nodes:
        slot_name = node.get("slot")
        slot_id = (None if slot_name is None
                   else _reverse(naming, "slot_names", slot_name))
        set1 = node.get("set1", "true") == "true"
        set2 = node.get("set2", "true") == "true"
        weapon_set_id = None
        if set1 != set2:
            weapon_set_id = _reverse(naming, "weapon_set_numbers",
                                     1 if set1 else 2)
        main_attribute = node.get("mainActiveSkill")
        main_skill_index = (None if main_attribute is None
                            else int(main_attribute) - 1)
        skills: list[SkillEntry] = []
        for gem in node.findall("Gem"):
            skill_id = _reverse(naming, "skill_ids", gem.get("skillId", ""))
            if skill_id is None:
                continue
            if skill_id in naming.support_skill_ids and skills:
                current = skills[-1]
                skills[-1] = replace(
                    current, support_ids=list(current.support_ids) + [skill_id])
                continue
            gem_id = (None if gem.get("gemId") is None
                      else _reverse(naming, "gem_ids", gem.get("gemId")))
            skills.append(SkillEntry(
                skill_id=skill_id, gem_id=gem_id,
                level=int(gem.get("level", "0")),
                quality=int(gem.get("quality", "0")),
                enabled=gem.get("enabled", "true") == "true",
                support_ids=[], triggered=[]))
        groups.append(SkillGroup(
            group_id=node.get("label", ""),
            enabled=node.get("enabled", "false") == "true",
            slot_id=slot_id, source_item_hash=None,
            weapon_set_id=weapon_set_id, main_skill_index=main_skill_index,
            skills=skills))
    return groups


def _import_config(root: ET.Element) -> dict[str, ConfigValue]:
    config: dict[str, ConfigValue] = {}
    container = root.find("Config")
    if container is None:
        return config
    config_set = container.find("ConfigSet")
    source = container if config_set is None else config_set
    for node in source.findall("Input"):
        name = node.get("name")
        if name is None:
            continue
        if node.get("boolean") is not None:
            value: Any = node.get("boolean") == "true"
        elif node.get("number") is not None:
            text = node.get("number", "")
            value = float(text) if any(c in text for c in ".eE") else int(text)
        elif node.get("string") is not None:
            value = node.get("string")
        else:
            continue
        config[name] = ConfigValue(value=value, origin=ConfigOrigin.SOURCE,
                                   verified=False, evidence_ids=[])
    return config
