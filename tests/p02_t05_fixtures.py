"""Synthetic builds, items and naming tables for the P02-T05 round trips.

Everything here is invented. The catalog IDs, PoB names, modifier text and
numbers are chosen to be greppable, not to describe PoE 2 content, and nothing
here may be cited as evidence about the game or as a PoB measurement. The one
exception is marked: :func:`naming_from_document` derives a naming table from a
document PoB itself wrote, and even then the catalog IDs on the left-hand side
are made up by prefixing the native ones.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from dataclasses import replace
from typing import Mapping

from pob2opt.domain.enums import (ConfigOrigin, ModifierCategory,
                                  ModifierParseStatus, RecordParseStatus)
from pob2opt.domain.identity import item_hash
from pob2opt.domain.records import (BuildSpec, ConfigValue, EquipmentSlot,
                                    ItemInstance, ItemModifier, Passives,
                                    Progression, SkillEntry, SkillGroup,
                                    Socket, SocketedEntity, ValueRange,
                                    WeaponSet)
from pob2opt.evaluation import CatalogNaming

CREATED_AT = "2026-10-06T00:00:00Z"
CATALOG_HASH = "f" * 64

#: SYNTHETIC. Left-hand side invented catalog IDs, right-hand side the PoB
#: names a document carries. P02-T02 produces the real table from the catalog.
SYNTHETIC_NAMING = CatalogNaming(
    class_names={"class-huntress": "Huntress"},
    class_tree_ids={"class-huntress": 8},
    ascendancy_names={"asc-ritualist": "Ritualist"},
    ascendancy_tree_ids={"asc-ritualist": 1},
    node_ids={"node-a": 101, "node-b": 102, "node-c": 103, "node-d": 104,
              "node-e": 105, "node-asc": 201},
    ascendancy_node_ids=frozenset({"node-asc"}),
    attribute_options={"choice-str": "Strength", "choice-dex": "Dexterity",
                       "choice-int": "Intelligence"},
    slot_names={"slot-weapon1": "Weapon 1", "slot-weapon2": "Weapon 2",
                "slot-weapon1-swap": "Weapon 1 Swap",
                "slot-helmet": "Helmet", "slot-amulet": "Amulet"},
    weapon_set_numbers={"set-main": 1, "set-swap": 2},
    base_names={"base-quarterstaff": "Long Quarterstaff",
                "base-helmet": "Iron Helm", "base-jewel": "Emerald"},
    skill_ids={"skill-spear": "FixtureSpearThrow",
               "skill-herald": "FixtureHerald",
               "skill-trigger": "FixtureTriggered",
               "support-tempo": "FixtureSupportTempo",
               "support-conc": "FixtureSupportConcentrated"},
    gem_ids={"gem-spear": "Metadata/Fixture/SpearThrow"},
    support_skill_ids=frozenset({"support-tempo", "support-conc"}),
)


def modifier(category: ModifierCategory, position: int, text: str,
             flags: Mapping[str, bool] | None = None, **extra) -> ItemModifier:
    return ItemModifier(
        category=category, source_position=position, text=text,
        native_id=extra.get("native_id"),
        resolved_effect_ids=list(extra.get("resolved_effect_ids", ())),
        values=list(extra.get("values", ())),
        flags=dict(flags or {}),
        parse_status=extra.get("parse_status", ModifierParseStatus.RESOLVED))


def item(record_id: str, **fields) -> ItemInstance:
    """One ItemInstance with its own hash filled in."""
    base = ItemInstance(
        schema_version=1, record_id=record_id, created_at=CREATED_AT,
        provenance_ids=[], item_hash="", catalog_hash=CATALOG_HASH,
        base_id=fields.get("base_id"),
        display_name=fields.get("display_name", "FIXTURE Item"),
        rarity=fields.get("rarity", "rare"),
        item_level=fields.get("item_level"),
        requirements=dict(fields.get("requirements", {})),
        properties=dict(fields.get("properties", {})),
        modifiers=list(fields.get("modifiers", ())),
        sockets=list(fields.get("sockets", ())),
        flags=dict(fields.get("flags", {})),
        raw_text=fields.get("raw_text"),
        source_document_id=fields.get("source_document_id"),
        parse_status=fields.get("parse_status", RecordParseStatus.COMPLETE))
    return replace(base, item_hash=item_hash(base))


def every_category_weapon() -> ItemInstance:
    """One item carrying every modifier category the format can express."""
    return item(
        "fixture-item-weapon", base_id="base-quarterstaff", rarity="rare",
        display_name="FIXTURE Category Quarterstaff", item_level=82,
        requirements={"level": 65}, properties={"quality": 20},
        flags={"corrupted": True},
        modifiers=[
            modifier(ModifierCategory.ENCHANT, 0, "FIXTUREMOD enchant line"),
            modifier(ModifierCategory.RUNE, 1, "FIXTUREMOD rune line"),
            modifier(ModifierCategory.IMPLICIT, 2, "FIXTUREMOD implicit line"),
            modifier(ModifierCategory.EXPLICIT, 3, "FIXTUREMOD explicit one"),
            modifier(ModifierCategory.EXPLICIT, 4, "FIXTUREMOD explicit two",
                     {"unscalable": True}),
            modifier(ModifierCategory.FRACTURED, 5,
                     "FIXTUREMOD fractured line"),
            modifier(ModifierCategory.CRAFTED, 6, "FIXTUREMOD crafted line"),
            modifier(ModifierCategory.DESECRATED, 7,
                     "FIXTUREMOD desecrated line"),
        ])


def variant_helmet() -> ItemInstance:
    """A unique with two variants and per-variant modifier lines."""
    return item(
        "fixture-item-helmet", base_id="base-helmet", rarity="unique",
        display_name="FIXTURE Two Variant Helm", item_level=70,
        properties={"armour": 120, "variants": ["Pre Fixture", "Current"],
                    "selected_variant": 2},
        sockets=[Socket(socket_id="0", group=0, colour="S", contents_id=None)],
        modifiers=[
            modifier(ModifierCategory.IMPLICIT, 0,
                     "FIXTUREMOD helmet implicit"),
            modifier(ModifierCategory.EXPLICIT, 1,
                     "FIXTUREMOD helmet variant one", {"variant:1": True}),
            modifier(ModifierCategory.EXPLICIT, 2,
                     "FIXTUREMOD helmet variant two", {"variant:2": True}),
        ])


def socketed_jewel() -> ItemInstance:
    return item(
        "fixture-item-jewel", base_id="base-jewel", rarity="rare",
        display_name="FIXTURE Socketed Jewel", item_level=60,
        modifiers=[modifier(ModifierCategory.EXPLICIT, 0,
                            "FIXTUREMOD jewel explicit")])


def build_spec(**overrides) -> BuildSpec:
    base = dict(
        schema_version=1, record_id="fixture-build", created_at=CREATED_AT,
        provenance_ids=[], build_hash="", catalog_hash=CATALOG_HASH,
        declared_patch=None, name="SYNTHETIC P02-T05 build",
        class_id="class-huntress", ascendancy_id="asc-ritualist", level=84,
        progression=Progression(quest_flags={}, reward_flags={},
                                normal_point_budget=None,
                                ascendancy_point_budget=None, evidence_ids=[]),
        equipment={}, weapon_sets=[],
        passives=Passives(allocated=[], ascendancy_allocated=[], choices={},
                          socketed=[]),
        skill_groups=[], config={}, rotation_ids=[], source_document_ids=[],
        variant_id=None, family_id=None, raw_blob_hashes=[],
        parse_status=RecordParseStatus.COMPLETE, unresolved_refs=[])
    base.update(overrides)
    from pob2opt.domain.identity import build_hash
    spec = BuildSpec(**base)
    return replace(spec, build_hash=build_hash(spec))


def supported_build() -> tuple[BuildSpec, dict[str, ItemInstance]]:
    """Everything P02-T05 must carry, and nothing it cannot.

    Enabled and disabled groups, two weapon sets, a main skill, ordered
    supports, a passive attribute choice, a socketed jewel, item variants and
    every supported modifier category.
    """
    weapon = every_category_weapon()
    helmet = variant_helmet()
    jewel = socketed_jewel()
    items = {i.item_hash: i for i in (weapon, helmet, jewel)}
    spec = build_spec(
        equipment={
            "slot-weapon1": EquipmentSlot(item_hash=weapon.item_hash,
                                          listing_id=None),
            "slot-weapon2": None,
            "slot-weapon1-swap": None,
            "slot-helmet": EquipmentSlot(item_hash=helmet.item_hash,
                                         listing_id="fixture-listing-1"),
        },
        weapon_sets=[
            WeaponSet(set_id="set-main",
                      hand_slots={"main_hand": "slot-weapon1",
                                  "off_hand": "slot-weapon2"},
                      passive_allocations=["node-b"]),
            WeaponSet(set_id="set-swap",
                      hand_slots={"main_hand": "slot-weapon1-swap",
                                  "off_hand": None},
                      passive_allocations=["node-c"]),
        ],
        passives=Passives(
            allocated=["node-a", "node-b", "node-c", "node-d"],
            ascendancy_allocated=["node-asc"],
            choices={"node-d": "choice-dex"},
            socketed=[SocketedEntity(node_id="node-a",
                                     entity_id=jewel.item_hash)]),
        skill_groups=[
            SkillGroup(group_id="group-main", enabled=True,
                       slot_id="slot-weapon1", source_item_hash=None,
                       weapon_set_id="set-main", main_skill_index=0,
                       skills=[SkillEntry(
                           skill_id="skill-spear", gem_id="gem-spear",
                           level=20, quality=18, enabled=True,
                           support_ids=["support-tempo", "support-conc"],
                           triggered=[])]),
            SkillGroup(group_id="group-disabled", enabled=False, slot_id=None,
                       source_item_hash=None, weapon_set_id=None,
                       main_skill_index=None,
                       skills=[SkillEntry(
                           skill_id="skill-herald", gem_id=None, level=1,
                           quality=0, enabled=False, support_ids=[],
                           triggered=[])]),
        ],
        config={
            "enemyIsBoss": ConfigValue(value="Boss", origin=ConfigOrigin.SOURCE,
                                       verified=False, evidence_ids=[]),
            "conditionFullLife": ConfigValue(value=True,
                                             origin=ConfigOrigin.SOURCE,
                                             verified=False, evidence_ids=[]),
            "multiplierFixtureStacks": ConfigValue(
                value=5, origin=ConfigOrigin.SOURCE, verified=False,
                evidence_ids=[]),
        },
        source_document_ids=["fixture-source-1"])
    return spec, items


def trigger_nested_build() -> tuple[BuildSpec, dict[str, ItemInstance]]:
    """A skill that triggers another. PoB's gem list has no nesting."""
    spec = build_spec(
        record_id="fixture-build-trigger",
        skill_groups=[SkillGroup(
            group_id="group-trigger", enabled=True, slot_id=None,
            source_item_hash=None, weapon_set_id=None, main_skill_index=0,
            skills=[SkillEntry(
                skill_id="skill-spear", gem_id=None, level=20, quality=0,
                enabled=True, support_ids=[],
                triggered=[SkillEntry(
                    skill_id="skill-trigger", gem_id=None, level=10,
                    quality=0, enabled=True, support_ids=[],
                    triggered=[])])])])
    return spec, {}


def progression_build() -> tuple[BuildSpec, dict[str, ItemInstance]]:
    """Quest flags and point budgets. A PoB document records neither."""
    spec = build_spec(
        record_id="fixture-build-progression",
        progression=Progression(
            quest_flags={"fixture-quest-1": True},
            reward_flags={"fixture-reward-1": False},
            normal_point_budget=99, ascendancy_point_budget=8,
            evidence_ids=["fixture-source-1"]))
    return spec, {}


def item_granted_group_build() -> tuple[BuildSpec, dict[str, ItemInstance]]:
    """A socket group granted by an item. PoB regenerates those itself."""
    weapon = every_category_weapon()
    spec = build_spec(
        record_id="fixture-build-granted",
        equipment={"slot-weapon1": EquipmentSlot(item_hash=weapon.item_hash,
                                                 listing_id=None)},
        skill_groups=[SkillGroup(
            group_id="group-granted", enabled=True, slot_id="slot-weapon1",
            source_item_hash=weapon.item_hash, weapon_set_id=None,
            main_skill_index=0,
            skills=[SkillEntry(skill_id="skill-herald", gem_id=None, level=1,
                               quality=0, enabled=True, support_ids=[],
                               triggered=[])])])
    return spec, {weapon.item_hash: weapon}


def unresolved_catalog_build() -> tuple[BuildSpec, dict[str, ItemInstance]]:
    """A build whose catalog IDs are not in the naming table."""
    spec = build_spec(record_id="fixture-build-unresolved",
                      class_id="class-not-in-the-table",
                      ascendancy_id="asc-not-in-the-table",
                      passives=Passives(allocated=["node-not-in-the-table"],
                                        ascendancy_allocated=[], choices={},
                                        socketed=[]))
    return spec, {}


def unknown_category_item() -> ItemInstance:
    """A modifier whose source category PoB has no marker for."""
    return item("fixture-item-unknown", base_id="base-quarterstaff",
                display_name="FIXTURE Unknown Category",
                modifiers=[modifier(ModifierCategory.UNKNOWN, 0,
                                    "FIXTUREMOD unknown source line")])


def resolved_modifier_item() -> ItemInstance:
    """A modifier carrying catalog resolution and a roll range."""
    return item(
        "fixture-item-resolved", base_id="base-quarterstaff",
        display_name="FIXTURE Resolved Modifier",
        modifiers=[modifier(
            ModifierCategory.EXPLICIT, 0, "FIXTUREMOD resolved line",
            native_id="fixture-native-1",
            resolved_effect_ids=["fixture-effect-1"],
            values=[ValueRange(rolled=12.0, minimum=10.0, maximum=15.0)],
            parse_status=ModifierParseStatus.AMBIGUOUS)])


def false_flag_item() -> ItemInstance:
    """``corrupted: false`` is not ``corrupted`` absent, and PoB cannot say so."""
    return item("fixture-item-false-flag", base_id="base-quarterstaff",
                display_name="FIXTURE False Flag", flags={"corrupted": False},
                modifiers=[modifier(ModifierCategory.EXPLICIT, 0,
                                    "FIXTUREMOD plain line")])


# ------------------------------------------------- PoB-derived naming table

def naming_from_document(document: str, prefix: str = "pob") -> CatalogNaming:
    """A naming table derived from a document PoB itself wrote.

    The right-hand side is PoB's own names, read out of the document. The
    left-hand side is invented by prefixing them, because this repository has
    no catalog yet: P02-T02 owns the real catalog IDs. Use it only to exercise
    the codec against a real document.
    """
    root = ET.fromstring(document)
    build = root.find("Build")
    spec = root.find("Tree/Spec")
    class_name = (build.get("className", "") if build is not None else "")
    ascend_name = (build.get("ascendClassName", "None")
                   if build is not None else "None")
    class_id = "%s-class-%s" % (prefix, class_name)
    naming: dict[str, object] = {
        "class_names": {class_id: class_name},
        "class_tree_ids": {class_id: int(spec.get("classId", "0"))
                           if spec is not None else 0},
        "ascendancy_names": {}, "ascendancy_tree_ids": {},
    }
    if ascend_name not in ("", "None"):
        ascendancy_id = "%s-asc-%s" % (prefix, ascend_name)
        naming["ascendancy_names"] = {ascendancy_id: ascend_name}
        naming["ascendancy_tree_ids"] = {
            ascendancy_id: int(spec.get("ascendClassId", "0"))}

    node_ids: dict[str, int] = {}
    if spec is not None:
        natives = set()
        for text in [spec.get("nodes", "")] + [
                child.get("nodes", "") for child in spec
                if child.tag.startswith("WeaponSet")]:
            natives.update(int(part) for part in text.replace(" ", "").split(",")
                           if part)
        override = spec.find("Overrides/AttributeOverride")
        if override is not None:
            for key in ("strNodes", "dexNodes", "intNodes"):
                natives.update(int(part) for part
                               in (override.get(key) or "").replace(" ", "").split(",")
                               if part)
        for socket in spec.findall("Sockets/Socket"):
            natives.add(int(socket.get("nodeId", "0")))
        node_ids = {"%s-node-%d" % (prefix, native): native
                    for native in sorted(natives)}

    slot_names: dict[str, str] = {}
    base_names: dict[str, str] = {}
    items = root.find("Items")
    if items is not None:
        for slot in items.findall("ItemSet/Slot"):
            name = slot.get("name", "")
            slot_names["%s-slot-%s" % (prefix, name)] = name
        for index, node in enumerate(items.findall("Item")):
            lines = [line.strip() for line in (node.text or "").split("\n")]
            lines = [line for line in lines if line]
            if len(lines) >= 3 and lines[0].startswith("Rarity: "):
                rarity = lines[0][len("Rarity: "):].strip().lower()
                base = lines[2] if rarity in ("rare", "unique", "relic") else lines[1]
                base_names.setdefault("%s-base-%d" % (prefix, index), base)

    skill_ids: dict[str, str] = {}
    gem_ids: dict[str, str] = {}
    skills = root.find("Skills")
    if skills is not None:
        for gem in skills.iter("Gem"):
            native = gem.get("skillId")
            if native:
                skill_ids["%s-skill-%s" % (prefix, native)] = native
            native_gem = gem.get("gemId")
            if native_gem:
                gem_ids["%s-gem-%s" % (prefix, native_gem)] = native_gem

    return CatalogNaming(
        class_names=naming["class_names"],
        class_tree_ids=naming["class_tree_ids"],
        ascendancy_names=naming["ascendancy_names"],
        ascendancy_tree_ids=naming["ascendancy_tree_ids"],
        node_ids=node_ids, ascendancy_node_ids=frozenset(),
        attribute_options={"%s-choice-str" % prefix: "Strength",
                           "%s-choice-dex" % prefix: "Dexterity",
                           "%s-choice-int" % prefix: "Intelligence"},
        slot_names=slot_names,
        weapon_set_numbers={"%s-set-1" % prefix: 1, "%s-set-2" % prefix: 2},
        base_names=_unique_values(base_names), skill_ids=skill_ids,
        gem_ids=gem_ids, support_skill_ids=frozenset())


def _unique_values(table: Mapping[str, str]) -> dict[str, str]:
    """Drop later duplicates so the table stays invertible."""
    seen: dict[str, str] = {}
    out: dict[str, str] = {}
    for key, value in table.items():
        if value in seen:
            continue
        seen[value] = key
        out[key] = value
    return out
