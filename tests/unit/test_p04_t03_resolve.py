"""P04-T03: entities against the patch catalog, offline.

Ambiguous names, renamed entities, stale tree IDs, unknown affixes and
duplicate item names, against the committed slice of the pinned catalog.
Changes to the catalog are made on copies of the slice; each is labelled
where it happens.
"""

from __future__ import annotations

from dataclasses import replace

import pytest

import p04_fixtures as fx
from pob2opt.domain.enums import (ModifierParseStatus,
                                  RecordParseStatus)
from pob2opt.evaluation import round_trip
from pob2opt.parsers import (item_readiness, migrate_build,
                             naming_from_catalog, parse_document,
                             resolve_item_modifiers, resolve_name)
from pob2opt.parsers.resolve import (AMBIGUOUS, RESOLVED, TEMPLATE_CLAIM,
                                     UNRESOLVED, class_for_document_name)


def parse(name):
    data = fx.document_bytes(name)
    return parse_document(fx.source(data, record_id="src/" + name), data,
                          fx.context())


def with_entities(table, rows):
    out = dict(fx.entities())
    out[table] = rows
    return out


# --------------------------------------------------------------- naming ---

def test_native_ids_come_first():
    naming = naming_from_catalog(fx.entities()).naming
    node = fx.entities()["passive_nodes"][0]
    assert naming.node_ids[node.entity_id] == node.raw_reference["id"]
    gem = fx.entities()["gems"][0]
    assert naming.gem_ids[gem.entity_id] == gem.raw_reference["gameId"]


def test_two_entities_claiming_one_pob_name_are_both_left_out():
    bases = list(fx.entities()["item_bases"])
    twin = replace(bases[0], entity_id=bases[0].entity_id + "-twin")  # SYNTHETIC
    report = naming_from_catalog(with_entities("item_bases", bases + [twin]))
    assert bases[0].entity_id not in report.naming.base_names
    assert twin.entity_id not in report.naming.base_names
    (entry,) = [a for a in report.ambiguous if a["table"] == "base_names"]
    assert entry["candidates"] == sorted([bases[0].entity_id, twin.entity_id])


def test_ascendancy_numbers_are_only_read_for_one_class():
    entities = fx.entities()
    class_id = class_for_document_name(entities, "Huntress")
    scoped = naming_from_catalog(entities, class_id=class_id).naming
    unscoped = naming_from_catalog(entities).naming
    assert scoped.ascendancy_tree_ids and not unscoped.ascendancy_tree_ids
    assert all(key.startswith("poe2/ascendancies/8/")
               for key in scoped.ascendancy_tree_ids)


# ----------------------------------------------------------- name lookup ---

def test_an_exact_name_resolves():
    entities = fx.entities()
    gem = entities["gems"][0]
    found = resolve_name(entities, "gems", gem.display_names[0])
    assert found.status == RESOLVED and found.entity_id == gem.entity_id


def test_a_shared_name_is_ambiguous_with_its_candidates():
    nodes = fx.entities()["passive_nodes"]
    names = {}
    for node in nodes:
        for name in node.display_names:
            names.setdefault(name, []).append(node.entity_id)
    shared = next(name for name, ids in names.items() if len(ids) > 1)
    found = resolve_name(fx.entities(), "passive_nodes", shared)
    assert found.status == AMBIGUOUS
    assert set(found.candidates) == set(names[shared])
    assert found.entity_id is None


def test_no_fuzzy_match():
    gem = fx.entities()["gems"][0]
    near = gem.display_names[0].lower()
    assert resolve_name(fx.entities(), "gems", near).status == UNRESOLVED
    assert resolve_name(fx.entities(), "gems",
                        gem.display_names[0][:-1]).status == UNRESOLVED


def test_another_locale_is_not_translated():
    gem = fx.entities()["gems"][0]
    found = resolve_name(fx.entities(), "gems", gem.display_names[0],
                         locale="de")
    assert found.status == UNRESOLVED and "de" in found.reason


# -------------------------------------------------------------- migration ---

def test_a_renamed_entity_keeps_its_id_and_is_recorded():
    (build,) = parse("b01").builds
    source = fx.entities()
    node_id = build.passives.allocated[0]
    renamed = [replace(n, display_names=["SYNTHETIC renamed"])
               if n.entity_id == node_id else n
               for n in source["passive_nodes"]]
    target = with_entities("passive_nodes", renamed)
    migration = migrate_build(build, source, target,
                              target_catalog_hash="1" * 64, record_id="m",
                              created_at=fx.CREATED_AT)
    (change,) = migration.changes
    assert (change.change, change.entity_id) == ("renamed", node_id)
    assert migration.build.passives.allocated == build.passives.allocated
    assert migration.build.parse_status is RecordParseStatus.COMPLETE


def test_a_removed_gem_is_never_substituted():
    (build,) = parse("b04").builds
    source = fx.entities()
    skill_id = build.skill_groups[0].skills[0].skill_id
    target = with_entities("granted_skills", [
        s for s in source["granted_skills"] if s.entity_id != skill_id])
    migration = migrate_build(build, source, target,
                              target_catalog_hash="1" * 64, record_id="m",
                              created_at=fx.CREATED_AT)
    assert [c.entity_id for c in migration.removed] == [skill_id]
    assert migration.build.skill_groups[0].skills[0].skill_id == skill_id
    assert migration.build.parse_status is RecordParseStatus.PARTIAL
    assert skill_id in [r.reference for r in migration.build.unresolved_refs]


def test_a_stale_tree_id_is_removed_not_replaced():
    (build,) = parse("b03").builds
    stale = build.passives.allocated[-1]
    source = fx.entities()
    target = with_entities("passive_nodes", [
        n for n in source["passive_nodes"] if n.entity_id != stale])
    migration = migrate_build(build, source, target,
                              target_catalog_hash="1" * 64, record_id="m",
                              created_at=fx.CREATED_AT)
    assert stale in [c.entity_id for c in migration.removed]
    assert stale in migration.build.passives.allocated


def test_migration_makes_a_new_record_and_keeps_the_original():
    (build,) = parse("b05").builds
    migration = migrate_build(build, fx.entities(), fx.entities(),
                              target_catalog_hash="1" * 64, record_id="m",
                              created_at=fx.CREATED_AT)
    assert migration.build.record_id == "m" and build.record_id != "m"
    assert migration.build.catalog_hash == "1" * 64
    assert build.catalog_hash == fx.slice_catalog_hash()
    assert build.record_id in migration.build.provenance_ids
    assert migration.changes == ()


# --------------------------------------------------------- item modifiers ---

def items_of(name):
    return list(parse(name).items)


def test_rolled_affixes_resolve_to_one_tier():
    item = next(i for i in items_of("b01") if i.rarity == "rare")
    resolved, matches = resolve_item_modifiers(item, fx.entities())
    assert matches and all(m.status == "resolved" for m in matches)
    for before, after in zip(item.modifiers, resolved.modifiers):
        assert after.category is before.category
        assert after.text == before.text
        assert after.values == before.values
        assert after.native_id is not None


def test_an_unknown_affix_is_unresolved_and_the_item_partial():
    item = next(i for i in items_of("b01") if i.rarity == "rare")
    odd = replace(item.modifiers[0], text="SYNTHETIC +3 to unknown things")
    changed = replace(item, modifiers=[odd] + list(item.modifiers[1:]))
    resolved, matches = resolve_item_modifiers(changed, fx.entities())
    assert matches[0].status == "unresolved"
    assert resolved.modifiers[0].parse_status is ModifierParseStatus.UNRESOLVED
    assert resolved.parse_status is RecordParseStatus.PARTIAL


def test_two_templates_matching_one_line_are_ambiguous():
    item = next(i for i in items_of("b01") if i.rarity == "rare")
    _, matches = resolve_item_modifiers(item, fx.entities())
    entity = next(e for e in fx.entities()["item_modifiers"]
                  if e.entity_id == matches[0].candidates[0])
    clone = replace(entity, entity_id=entity.entity_id + "-clone")  # SYNTHETIC
    entities = with_entities("item_modifiers",
                             list(fx.entities()["item_modifiers"]) + [clone])
    _, again = resolve_item_modifiers(item, entities)
    assert again[0].status == "ambiguous"
    assert set(again[0].candidates) == {entity.entity_id, clone.entity_id}


def test_a_roll_outside_every_tier_is_unresolved():
    item = next(i for i in items_of("b01") if i.rarity == "rare")
    first = item.modifiers[0]
    import re
    absurd = re.sub(r"\d+", "99999", first.text, count=1)
    changed = replace(item, modifiers=[replace(first, text=absurd)]
                      + list(item.modifiers[1:]))
    _, matches = resolve_item_modifiers(changed, fx.entities())
    assert matches[0].status == "unresolved"


def test_an_affix_parse_reports_unknown_lines_as_issues():
    import xml.etree.ElementTree as ET
    root = ET.fromstring(fx.document_bytes("b01"))
    item = root.find("Items/Item")
    item.text = item.text.rstrip() + "\nSYNTHETIC +3 to unknown things\n"
    data = ET.tostring(root, encoding="utf-8", xml_declaration=True)
    outcome = parse_document(fx.source(data), data, fx.context())
    codes = [i.code for i in outcome.result.issues]
    assert "unresolved_affix" in codes
    affixes = {c.domain: c for c in outcome.result.field_coverage}["item_affixes"]
    assert affixes.missing == 1


def test_duplicate_item_names_stay_distinct_items():
    a, b = [i for i in items_of("b04") if i.rarity == "rare"][:2]
    twin = replace(b, display_name=a.display_name)
    assert twin.display_name == a.display_name
    from pob2opt.domain.identity import item_hash
    assert item_hash(twin) != item_hash(a)


def test_a_name_without_stats_is_a_template_claim():
    item = items_of("b01")[0]
    bare = replace(item, modifiers=[], properties={})
    assert item_readiness(item) == "ready"
    assert item_readiness(bare) == TEMPLATE_CLAIM


def test_item_text_with_only_a_name_parses_partial():
    payload = b"Rarity: UNIQUE\nSYNTHETIC Famous Unique\nCrude Bow\n"
    outcome = parse_document(fx.source(payload, media_type="text/plain"),
                             payload, fx.context())
    assert outcome.result.status.value == "partial"
    assert TEMPLATE_CLAIM in [i.code for i in outcome.result.issues]
    (item,) = outcome.items
    assert item.parse_status is RecordParseStatus.PARTIAL


# ------------------------------------------------------ P02 round trips ---

@pytest.mark.parametrize("name", fx.COMPLETE_BUILDS)
def test_a_complete_supported_import_passes_the_p02_round_trip(name):
    outcome = parse(name)
    (build,) = outcome.builds
    import xml.etree.ElementTree as ET
    class_id = class_for_document_name(
        fx.entities(),
        ET.fromstring(fx.document_bytes(name)).find("Build").get("className"))
    naming = naming_from_catalog(fx.entities(), class_id=class_id).naming
    items = {i.item_hash: i for i in outcome.items}
    trip = round_trip(build, items, naming)
    assert trip.status == "faithful", trip.as_dict()


@pytest.mark.parametrize("name", fx.PARTIAL_BUILDS)
def test_a_partial_import_stays_out_of_recommendation(name):
    (build,) = parse(name).builds
    assert build.parse_status is RecordParseStatus.PARTIAL
