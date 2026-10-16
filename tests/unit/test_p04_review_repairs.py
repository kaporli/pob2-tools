"""Repairs for the PR #10 review (docs/reviews/P04.md, R1 to R8). Offline.

Each section names its finding. Documents are the committed P04 fixtures,
changed in place where a case needs it; each change is labelled SYNTHETIC.
``fixtures/p04/review/generated-support.xml`` is the reviewer's PoB-saved
document: b09's generated Spear Stab with an added support gem.
"""

from __future__ import annotations

import copy
import re
import xml.etree.ElementTree as ET
from dataclasses import replace

import pytest

import p04_fixtures as fx
from pob2opt.domain.absent import ABSENT
from pob2opt.domain.enums import ModifierParseStatus, RecordParseStatus
from pob2opt.domain.identity import build_hash
from pob2opt.domain.migrate import legacy_main_group, upgrade_build_spec
from pob2opt.domain.records import SkillGroup
from pob2opt.evaluation import export_build
from pob2opt.evaluation.itemtext import export_item
from pob2opt.parsers import (audit_variant, migrate_build,
                             naming_from_catalog, parse_document)
from pob2opt.parsers.resolve import class_for_document_name

REVIEW_FIXTURE = fx.FIXTURES / "review" / "generated-support.xml"


# Follow-up F1/F2: identical item validation at both public entry points.
@pytest.mark.parametrize("case", ["known", "unknown", "ambiguous",
                                  "out-of-range", "name-only"])
def test_item_text_and_xml_have_the_same_persisted_readiness(case, tmp_path):
    from pob2opt.domain.codec import from_jsonable, to_jsonable
    from pob2opt.domain.records import EquipmentSlot, ItemInstance
    from pob2opt.parsers import resolve_item_modifiers
    from pob2opt.domain.validation import validate_record
    import json

    root = ET.fromstring(fx.document_bytes("b01"))
    node, _ = equipped_rare(root)
    entities = dict(fx.entities())
    if case == "unknown":
        node.text += "\nSYNTHETIC +3 to unknown things\n"
    elif case == "out-of-range":
        lines = node.text.splitlines()
        start = next(i for i, line in enumerate(lines) if "Implicits:" in line) + 1
        index = next(i for i in range(start, len(lines)) if re.search(r"\d", lines[i]))
        lines[index] = re.sub(r"\d+", "99999", lines[index], count=1)
        node.text = "\n".join(lines)
    elif case == "name-only":
        node.text = "\n".join(line for line in node.text.splitlines() if line.strip())
        node.text = "\n".join(node.text.splitlines()[:3])
    elif case == "ambiguous":
        baseline = parse(fx.document_bytes("b01"))
        item = next(i for i in baseline.items if i.rarity == "rare")
        _, matches = resolve_item_modifiers(item, entities)
        entity = next(e for e in entities["item_modifiers"]
                      if e.entity_id == matches[0].candidates[0])
        entities["item_modifiers"] = [*entities["item_modifiers"],
                                     replace(entity, entity_id=entity.entity_id + "-clone")]
    xml = ET.tostring(root, encoding="utf-8")
    payload = node.text.encode("utf-8")
    standalone = parse_document(fx.source(payload, media_type="text/plain"),
                                payload, fx.context(entities=entities))
    wrapped = parse(xml, entities=entities)
    (item,) = standalone.items
    xml_item = next(i for i in wrapped.items if i.display_name == item.display_name)
    assert xml_item.raw_text.strip() == item.raw_text.strip()
    assert item.item_hash == xml_item.item_hash
    assert item.modifiers == xml_item.modifiers
    expected = "complete" if case == "known" else "partial"
    assert item.parse_status.value == xml_item.parse_status.value == expected
    assert standalone.result.status.value == expected
    assert validate_record(item).ok
    # Reload just the item, without its ParseResult, then equip it on a clean
    # build. Completeness must not depend on remembering a separate issue list.
    path = tmp_path / "item.json"
    path.write_text(json.dumps(to_jsonable(item)), encoding="utf-8")
    stored = from_jsonable(ItemInstance, json.loads(path.read_text(encoding="utf-8")))
    assert stored.raw_text == node.text
    _, losses = export_item(stored, naming_for(xml))
    assert losses.report().complete == (case == "known")
    clean = parse(fx.document_bytes("b01"))
    build = clean.builds[0]
    original = next(i for i in clean.items if i.display_name == item.display_name)
    equipment = {slot: EquipmentSlot(stored.item_hash, value.listing_id)
                 if value and value.item_hash == original.item_hash else value
                 for slot, value in build.equipment.items()}
    build = replace(build, equipment=equipment)
    items = {i.item_hash: i for i in clean.items}
    items[stored.item_hash] = stored
    assert export_build(build, items, naming_for(xml)).recommended_deliverable \
        == (case == "known")


BAD_ITEM_NUMBERS = [("Quality", "broken"), ("Armour", "broken"),
                    ("Energy Shield", "broken"), ("Quality", "1e999"),
                    ("Armour", "-1e999"), ("Energy Shield", "NaN"),
                    ("Item Level", "-1"), ("LevelReq", "-1"),
                    ("Implicits", "-1")]


@pytest.mark.parametrize("standalone", [False, True])
@pytest.mark.parametrize("label,value", BAD_ITEM_NUMBERS)
def test_invalid_item_number_is_a_typed_parse_failure(label, value, standalone):
    root = ET.fromstring(fx.document_bytes("b01"))
    node, _ = equipped_rare(root)
    node.text += "\n%s: %s\n" % (label, value)
    payload = node.text.encode("utf-8") if standalone else ET.tostring(root)
    outcome = parse(payload)
    assert outcome.result.status.value == "invalid"
    assert not outcome.items and not outcome.builds
    (issue,) = outcome.result.issues
    prefix = "" if standalone else "/Items/Item/0"
    assert (issue.code, issue.field_path) == ("malformed_value", prefix + "/text/" + label)


@pytest.mark.parametrize("value", ["1e999", "-1e999", "NaN", "Infinity"])
def test_nonfinite_config_is_a_typed_parse_failure(value):
    data = changed("b01", lambda r: ET.SubElement(
        r.find("Config/ConfigSet"), "Input", name="enemyLevel", number=value))
    outcome = parse(data)
    assert outcome.result.status.value == "invalid"
    assert not outcome.builds and not outcome.items
    (issue,) = outcome.result.issues
    assert issue.code == "malformed_value"
    assert issue.field_path == "/Config/Input[@name='enemyLevel']/@number"


@pytest.mark.parametrize("value,expected", [("1.25", 1.25), ("2e1", 20),
                                          ("-1.25e-2", -0.0125)])
def test_valid_decimal_and_exponent_properties_are_not_rejected(value, expected):
    root = ET.fromstring(fx.document_bytes("b01"))
    node, _ = equipped_rare(root)
    node.text += "\nQuality: %s\n" % value
    ET.SubElement(root.find("Config/ConfigSet"), "Input", name="enemyLevel", number=value)
    outcome = parse(ET.tostring(root))
    assert outcome.result.status.value == "complete"
    item = next(i for i in outcome.items if i.raw_text.strip() == node.text.strip())
    assert item.properties["quality"] == expected
    assert outcome.builds[0].config["enemyLevel"].value == expected


def parse(data, **context):
    return parse_document(fx.source(data), data, fx.context(**context))


def naming_for(data):
    class_id = class_for_document_name(
        fx.entities(), ET.fromstring(data).find("Build").get("className"))
    return naming_from_catalog(fx.entities(), class_id=class_id).naming


def changed(name, change):
    root = ET.fromstring(fx.document_bytes(name))
    change(root)
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


def recommended(outcome, data):
    items = {i.item_hash: i for i in outcome.items}
    return [export_build(b, items, naming_for(data)).recommended_deliverable
            for b in outcome.builds]


# --------------------------------------- R1: supports on generated groups ---

def generated_group(root):
    return next(g for g in root.iter("Skill") if g.get("source"))


def support_gem(**attributes):
    """b12's cold support gem, with ``attributes`` replacing its own."""
    gem = next(g for g in ET.fromstring(fx.document_bytes("b12")).iter("Gem")
               if g.get("skillId") == "SupportAddedColdDamagePlayer")
    gem = copy.deepcopy(gem)
    if attributes.pop("bare", False):
        for name in list(gem.attrib):
            if name not in ("skillId", "gemId", "variantId"):
                del gem.attrib[name]
    for name, value in attributes.items():
        gem.set(name, value)
    return gem


def test_the_reviewers_document_is_partial_and_never_recommended():
    data = REVIEW_FIXTURE.read_bytes()
    outcome = parse(data)
    (build,) = outcome.builds
    assert build.parse_status is RecordParseStatus.PARTIAL
    assert recommended(outcome, data) == [False]
    paths = [i.field_path for i in outcome.result.issues]
    assert "/variants/0/Skills/Skill/0/Gem/1" in paths
    assert any(r.field_path == "/Skills/Skill/0/Gem/1"
               for r in build.unresolved_refs)


def test_generated_groups_with_only_defaults_stay_complete():
    for name in fx.COMPLETE_BUILDS:
        data = fx.document_bytes(name)
        outcome = parse(data)
        assert [b.parse_status for b in outcome.builds] == [
            RecordParseStatus.COMPLETE], name


@pytest.mark.parametrize("gems", [
    [dict(enabled="true")],
    [dict(enabled="false")],
    [dict(bare=True)],  # every setting at PoB's default: still user content
    [dict(enabled="true"), dict(enabled="false", level="2")],
], ids=["enabled", "disabled", "all-defaults", "two-gems"])
def test_an_added_gem_on_a_generated_group_blocks_the_record(gems):
    def add(root):
        group = generated_group(root)
        for attributes in gems:
            group.append(support_gem(**attributes))  # SYNTHETIC
    data = changed("b09", add)
    outcome = parse(data)
    (build,) = outcome.builds
    assert build.parse_status is RecordParseStatus.PARTIAL
    assert recommended(outcome, data) == [False]
    added = [i for i in outcome.result.issues
             if re.search(r"/Skill/\d+/Gem/[1-9]$", i.field_path)]
    assert len(added) == len(gems)


def test_a_changed_setting_on_a_generated_group_blocks_the_record():
    data = changed("b09", lambda r: generated_group(r).set("enabled",
                                                           "false"))
    (build,) = parse(data).builds  # SYNTHETIC: generated group disabled
    assert build.parse_status is RecordParseStatus.PARTIAL


# ---------------------------------- R2: item checks reach stored records ---

def equipped_rare(root):
    """(Item element, its slot name) of the first equipped rare."""
    texts = {i.get("id"): i for i in root.findall("Items/Item")}
    for slot in root.findall("Items/ItemSet/Slot"):
        item = texts.get(slot.get("itemId"))
        if item is not None and "Rarity: RARE" in (item.text or ""):
            return item, slot.get("name")
    raise AssertionError("no equipped rare")


def with_item_text(name, edit):
    def change(root):
        item, _ = equipped_rare(root)
        item.text = edit(item.text)
    return changed(name, change)


def assert_blocked(outcome, data, status):
    (build,) = outcome.builds
    assert build.parse_status is RecordParseStatus.PARTIAL
    refs = [r for r in build.unresolved_refs
            if r.field_path.startswith("/equipment/")]
    assert refs, build.unresolved_refs
    items = {i.item_hash: i for i in outcome.items}
    hashes = {r.reference.split("/")[0] for r in refs}
    for item_hash in hashes:
        item = items[item_hash]
        assert item.parse_status is RecordParseStatus.PARTIAL
        if status is not None:
            assert status in [m.parse_status for m in item.modifiers]
        _, losses = export_item(item, naming_for(data))
        assert not losses.report().complete
    assert recommended(outcome, data) == [False]


def test_an_unknown_affix_taints_the_item_and_the_build():
    data = with_item_text("b01", lambda t: t.rstrip()
                          + "\nSYNTHETIC +3 to unknown things\n")
    assert_blocked(parse(data), data, ModifierParseStatus.UNRESOLVED)


def test_an_out_of_range_roll_taints_the_item_and_the_build():
    def absurd(text):
        lines = text.split("\n")
        start = next(i for i, l in enumerate(lines) if "Implicits:" in l) + 1
        for index in range(start, len(lines)):
            if re.search(r"\d", lines[index]):
                lines[index] = re.sub(r"\d+", "99999", lines[index], count=1)
                return "\n".join(lines)
        raise AssertionError("no numeric affix")
    data = with_item_text("b01", absurd)  # SYNTHETIC
    assert_blocked(parse(data), data, ModifierParseStatus.UNRESOLVED)


def test_an_ambiguous_affix_taints_the_item_and_the_build():
    data = fx.document_bytes("b01")
    first = parse(data)
    rare = next(i for i in first.items if i.rarity == "rare")
    from pob2opt.parsers import resolve_item_modifiers
    _, matches = resolve_item_modifiers(rare, fx.entities())
    entity = next(e for e in fx.entities()["item_modifiers"]
                  if e.entity_id == matches[0].candidates[0])
    entities = dict(fx.entities())
    entities["item_modifiers"] = list(entities["item_modifiers"]) + [
        replace(entity, entity_id=entity.entity_id + "-clone")]  # SYNTHETIC
    outcome = parse(data, entities=entities)
    assert "ambiguous_affix" in [i.code for i in outcome.result.issues]
    assert_blocked(outcome, data, ModifierParseStatus.AMBIGUOUS)


def test_a_name_only_equipped_item_taints_the_build():
    def name_only(text):
        lines = [l.strip() for l in text.splitlines() if l.strip()]
        return "\n".join(lines[:3]) + "\n"
    data = with_item_text("b01", name_only)  # SYNTHETIC
    outcome = parse(data)
    assert "template_claim" in [i.code for i in outcome.result.issues]
    assert_blocked(outcome, data, None)


def test_an_item_only_one_variant_uses_leaves_the_other_complete():
    root = ET.fromstring(fx.document_bytes("variants"))
    outcome = parse(fx.document_bytes("variants"))
    first, second = outcome.builds
    used_first = {s.item_hash for s in first.equipment.values() if s}
    only_second = [s.item_hash for s in second.equipment.values()
                   if s and s.item_hash not in used_first]
    assert only_second
    target = next(i for i in outcome.items if i.item_hash == only_second[0])
    node = next(n for n in root.findall("Items/Item")
                if target.display_name in (n.text or ""))
    node.text = node.text.rstrip() + "\nSYNTHETIC +3 to unknown things\n"
    data = ET.tostring(root, encoding="utf-8", xml_declaration=True)
    again = parse(data)
    assert [b.parse_status.value for b in again.builds] == ["complete",
                                                            "partial"]


def test_notes_alone_never_taint_a_build():
    def note(root):
        notes = root.find("Notes")
        if notes is None:
            notes = ET.SubElement(root, "Notes")
        notes.text = "SYNTHETIC note: level gems before maps."
    data = changed("b03", note)
    (build,) = parse(data).builds
    assert build.parse_status is RecordParseStatus.COMPLETE


# --------------------------------------------- R4: support gem migration ---

def b01_support():
    (build,) = parse(fx.document_bytes("b01")).builds
    support = next(s for g in build.skill_groups for sk in g.skills
                   for s in sk.supports)
    return build, support


def migrate(build, target):
    return migrate_build(build, fx.entities(), target,
                         target_catalog_hash="1" * 64, record_id="m",
                         created_at=fx.CREATED_AT)


def test_a_removed_support_gem_is_reported_and_blocks():
    build, support = b01_support()
    target = dict(fx.entities())
    target["gems"] = [e for e in target["gems"]
                      if e.entity_id != support.gem_id]
    migration = migrate(build, target)
    removed = {(c.field_path, c.entity_id) for c in migration.removed}
    assert any(path.endswith("/supports/0/gem_id") and ident == support.gem_id
               for path, ident in removed)
    assert migration.build.parse_status is RecordParseStatus.PARTIAL
    assert build.parse_status is RecordParseStatus.COMPLETE  # source kept
    items = {i.item_hash: i for i in parse(fx.document_bytes("b01")).items}
    assert not export_build(migration.build, items, naming_for(
        fx.document_bytes("b01"))).recommended_deliverable


def test_a_removed_support_effect_with_its_gem_kept_is_reported():
    build, support = b01_support()
    target = dict(fx.entities())
    target["granted_skills"] = [e for e in target["granted_skills"]
                                if e.entity_id != support.support_id]
    migration = migrate(build, target)
    paths = [c.field_path for c in migration.removed
             if c.entity_id == support.support_id]
    assert any(p.endswith("/supports/0/support_id") for p in paths)
    assert any("/support_ids/" in p for p in paths)
    assert migration.build.parse_status is RecordParseStatus.PARTIAL


def test_a_renamed_support_gem_keeps_its_id_and_is_recorded():
    build, support = b01_support()
    target = dict(fx.entities())
    target["gems"] = [replace(e, display_names=["SYNTHETIC renamed"])
                      if e.entity_id == support.gem_id else e
                      for e in target["gems"]]
    migration = migrate(build, target)
    renamed = [c for c in migration.changes if c.change == "renamed"]
    assert [c.entity_id for c in renamed] == [support.gem_id]
    assert migration.build.parse_status is RecordParseStatus.COMPLETE


# ---------------------------------------------- R5: v1 main group upgrade ---

def v1_build(main_indices):
    """b03 as a version 1 record without supports; ``main_indices`` per group."""
    (build,) = parse(fx.document_bytes("b03")).builds
    groups = [replace(g, main_skill_index=index, skills=[
        replace(s, support_ids=[], supports=ABSENT) for s in g.skills])
        for g, index in zip(build.skill_groups, main_indices)]
    legacy = replace(build, schema_version=1, main_skill_group=ABSENT,
                     skill_groups=groups)
    return replace(legacy, build_hash=build_hash(legacy))


def main_socket_group(build):
    items = {i.item_hash: i for i in parse(fx.document_bytes("b03")).items}
    xml = export_build(build, items, naming_for(fx.document_bytes("b03"))).xml
    return ET.fromstring(xml).find("Build").get("mainSocketGroup")


@pytest.mark.parametrize("indices, expected", [
    ((0, 0), 1),       # both set: the legacy exporter picked group 2
    ((0, None), 0),    # only the first set
    ((None, 0), 1),    # only the second set
    ((None, None), 0),  # neither set: PoB's default group 1
])
def test_the_upgrade_keeps_the_v1_exporters_main_group(indices, expected):
    legacy = v1_build(indices)
    assert legacy_main_group(legacy.skill_groups) == expected
    upgraded = upgrade_build_spec(legacy, record_id="u",
                                  created_at=fx.CREATED_AT)
    assert upgraded.main_skill_group == expected
    assert main_socket_group(upgraded) == main_socket_group(legacy) == str(
        expected + 1)


def test_legacy_main_group_rule_cases():
    def groups(*indices):
        return [SkillGroup(group_id="g%d" % i, enabled=True, slot_id=None,
                           source_item_hash=None, weapon_set_id=None,
                           main_skill_index=index, skills=[])
                for i, index in enumerate(indices)]
    assert legacy_main_group([]) is None
    assert legacy_main_group(groups(0)) == 0
    assert legacy_main_group(groups(None, None, 0)) == 2
    assert legacy_main_group(groups(0, None, 0)) == 2
    assert legacy_main_group(groups(None, 0, 0)) == 1


def test_an_upgrade_without_groups_has_no_main_group():
    legacy = replace(v1_build((None, None)), skill_groups=[])
    legacy = replace(legacy, build_hash=build_hash(legacy))
    upgraded = upgrade_build_spec(legacy, record_id="u",
                                  created_at=fx.CREATED_AT)
    assert upgraded.main_skill_group is None


def test_the_v1_hash_is_unchanged_by_the_repair():
    legacy = v1_build((0, 0))
    assert build_hash(legacy) == legacy.build_hash


# ----------------------------------------------- R6: malformed numbers ---

MALFORMED = {
    "build-level": (lambda r: r.find("Build").set("level", "not-a-number"),
                    "/Build/@level"),
    "passive-id": (lambda r: r.find("Tree/Spec").set("nodes", "broken"),
                   "/Tree/Spec/@nodes"),
    "active-gem-level": (
        lambda r: next(g for g in r.iter("Skill") if not g.get("source"))
        .find("Gem").set("level", "broken"), "/Gem/@level"),
    "active-gem-quality": (
        lambda r: next(g for g in r.iter("Skill") if not g.get("source"))
        .find("Gem").set("quality", "broken"), "/Gem/@quality"),
    "slot-item-id": (lambda r: r.find("Items/ItemSet/Slot").set("itemId", "x"),
                     "/@itemId"),
    "item-level": (lambda r: r.find("Items/Item").__setattr__(
        "text", r.find("Items/Item").text.replace("Item Level: 80",
                                                  "Item Level: x")),
        "/text/Item Level"),
}


@pytest.mark.parametrize("case", sorted(MALFORMED))
def test_a_malformed_number_is_an_invalid_parse_naming_the_field(case):
    change, path = MALFORMED[case]
    data = changed("b01", change)  # SYNTHETIC
    outcome = parse(data)
    assert outcome.result.status.value == "invalid"
    assert outcome.builds == ()
    (issue,) = outcome.result.issues
    assert issue.code == "malformed_value"
    assert issue.field_path.endswith(path), issue.field_path


@pytest.mark.parametrize("field", ["level", "quality"])
def test_a_malformed_support_setting_is_partial_not_a_crash(field):
    def change(root):
        group = next(g for g in root.iter("Skill") if not g.get("source"))
        group.findall("Gem")[1].set(field, "broken")  # SYNTHETIC
    data = changed("b04", change)
    outcome = parse(data)
    (build,) = outcome.builds
    assert build.parse_status is RecordParseStatus.PARTIAL
    assert recommended(outcome, data) == [False]


@pytest.mark.parametrize("tag, selector", [
    ("Items", "activeItemSet"), ("Skills", "activeSkillSet"),
    ("Tree", "activeSpec"), ("Config", "activeConfigSet")])
def test_a_malformed_selector_is_named(tag, selector):
    data = changed("b01", lambda r: r.find(tag).set(selector, "x"))
    outcome = parse(data)
    assert outcome.result.status.value == "partial"
    (issue,) = [i for i in outcome.result.issues
                if i.code == "invalid_selector"]
    assert issue.field_path == "/%s/@%s" % (tag, selector)
    # The one loadout PoB lists is still the author's own sets.
    assert all(b.equipment or b.skill_groups for b in outcome.builds)


# -------------------------------------------- R8: the independent audit ---

def audit(name, edit):
    data = fx.document_bytes(name)
    outcome = parse(data)
    (build,) = outcome.builds
    broken = edit(build)
    broken = replace(broken, build_hash=build_hash(broken))
    return audit_variant(data.decode("utf-8"),
                         outcome.split.variants[0].selection, broken,
                         {i.item_hash: i for i in outcome.items},
                         naming_for(data))


def edit_group(build, index, **changes):
    groups = list(build.skill_groups)
    groups[index] = replace(groups[index], **changes)
    return replace(build, skill_groups=groups)


def single_mismatch(result, path):
    assert not result.passed
    assert [m.field_path for m in result.mismatches] == [path]


def test_a_different_main_group_fails_the_audit():
    result = audit("b03", lambda b: replace(
        b, main_skill_group=1 - b.main_skill_group))
    single_mismatch(result, "/main_skill_group")


def test_a_different_group_main_skill_fails_the_audit():
    def edit(build):
        index = build.main_skill_group
        group = build.skill_groups[index]
        other = None if group.main_skill_index is not None else 0
        return edit_group(build, index, main_skill_index=other)
    single_mismatch(audit("b03", edit), "/skill_groups/%d/main_skill_index"
                    % parse(fx.document_bytes("b03")).builds[0]
                    .main_skill_group)


def test_a_disabled_group_fails_the_audit():
    single_mismatch(audit("b03", lambda b: edit_group(
        b, 0, enabled=not b.skill_groups[0].enabled)),
        "/skill_groups/0/enabled")


def test_a_different_support_gem_identity_fails_the_audit():
    def edit(build):
        group = build.skill_groups[0]
        skill = group.skills[0]
        supports = list(skill.supports)
        supports[0] = replace(supports[0], gem_id=supports[0].gem_id + "-x")
        return edit_group(build, 0, skills=[replace(skill, supports=supports)]
                          + list(group.skills[1:]))
    result = audit("b04", edit)
    assert not result.passed
    (mismatch,) = result.mismatches
    assert mismatch.domain == "skills_and_supports"
    assert re.fullmatch(r"/skill_groups/0/gems/\d+", mismatch.field_path)


def test_a_different_active_gem_identity_fails_the_audit():
    def edit(build):
        group = build.skill_groups[0]
        skill = group.skills[0]
        return edit_group(build, 0, skills=[replace(
            skill, gem_id=(skill.gem_id or "") + "-x")]
            + list(group.skills[1:]))
    single_mismatch(audit("b04", edit), "/skill_groups/0/gems/0")
