"""P02-T05: a BuildSpec exported, reimported and compared on identity.

Offline only: no PoB, no network. The naming table is the synthetic one in
``tests/p02_t05_fixtures.py``; the engine lane in
``tests/engine/test_p02_t05_pob_round_trip.py`` repeats the same comparison
against documents PoB itself wrote.

The acceptance split this file pins:

* representable fields keep their canonical identity; support IDs alone are
  insufficient to certify their enabled/level/quality state;
* a fixture carrying an unsupported field is labelled ``incomplete``, is not a
  recommended deliverable, and the export names the field with its value;
* no export that reports itself complete may differ on reimport. That is the
  invariant separating a declared limitation from a defect here.
"""

from __future__ import annotations

import pytest
from p02_t05_fixtures import (SYNTHETIC_NAMING, item_granted_group_build,
                              progression_build, supported_build,
                              trigger_nested_build, unresolved_catalog_build)

from pob2opt.domain.identity import build_identity
from pob2opt.evaluation import (AmbiguousNaming, CatalogNaming, export_build,
                                import_build, round_trip)

ALL_FIXTURES = {
    "supported": supported_build,
    "trigger_nested": trigger_nested_build,
    "progression": progression_build,
    "item_granted_group": item_granted_group_build,
    "unresolved_catalog": unresolved_catalog_build,
}


@pytest.fixture(scope="module")
def supported():
    return round_trip(*supported_build(), SYNTHETIC_NAMING)


# ------------------------------------------------------- supported fixture

def test_a_supported_build_keeps_its_canonical_identity(supported):
    assert supported.build_hash_before == supported.build_hash_after
    assert supported.differences == ()
    # IDs survive, but the schema cannot certify support settings.
    assert supported.status == "incomplete"
    assert supported.recommended_deliverable is False


def test_support_settings_are_incomplete_and_metadata_is_still_named(supported):
    report = supported.export
    assert report.completeness == "incomplete"
    assert report.identity_losses == ()
    # Metadata a PoB file does not carry is reported anyway, with its value,
    # so a caller can keep it out of band.
    paths = report.paths()
    assert "/name" in paths
    assert "/source_document_ids" in paths
    assert "/equipment/slot-helmet/listing_id" in paths
    preserved = {u.field_path: u.preserved for u in report.unsupported}
    assert preserved["/name"] == "SYNTHETIC P02-T05 build"


def test_enabled_and_disabled_groups_both_survive(supported):
    before, _ = supported_build()
    after = import_build(supported.document, SYNTHETIC_NAMING,
                         record_id="r", created_at="1970-01-01T00:00:00Z",
                         catalog_hash=before.catalog_hash).build
    assert [g.enabled for g in after.skill_groups] == [True, False]
    assert [g.group_id for g in after.skill_groups] == ["group-main",
                                                        "group-disabled"]


def test_the_main_skill_selection_survives(supported):
    before, _ = supported_build()
    identity = build_identity(before)
    document = supported.document
    assert 'mainActiveSkill="1"' in document
    assert identity["skill_groups"][0]["main_skill_index"] == 0
    assert identity["skill_groups"][1]["main_skill_index"] is None


def test_ordered_supports_survive_a_flat_gem_list(supported):
    before, _ = supported_build()
    after = import_build(supported.document, SYNTHETIC_NAMING, record_id="r",
                         created_at="1970-01-01T00:00:00Z",
                         catalog_hash=before.catalog_hash).build
    assert after.skill_groups[0].skills[0].support_ids == ["support-tempo",
                                                           "support-conc"]


def test_passive_attribute_choices_survive(supported):
    assert 'dexNodes="104"' in supported.document
    before, _ = supported_build()
    after = import_build(supported.document, SYNTHETIC_NAMING, record_id="r",
                         created_at="1970-01-01T00:00:00Z",
                         catalog_hash=before.catalog_hash).build
    assert after.passives.choices == {"node-d": "choice-dex"}


def test_the_ordinary_and_ascendancy_split_survives(supported):
    before, _ = supported_build()
    after = import_build(supported.document, SYNTHETIC_NAMING, record_id="r",
                         created_at="1970-01-01T00:00:00Z",
                         catalog_hash=before.catalog_hash).build
    assert after.passives.allocated == sorted(before.passives.allocated)
    assert after.passives.ascendancy_allocated == ["node-asc"]


def test_socketed_jewels_survive(supported):
    before, items = supported_build()
    after = import_build(supported.document, SYNTHETIC_NAMING, record_id="r",
                         created_at="1970-01-01T00:00:00Z",
                         catalog_hash=before.catalog_hash).build
    assert [(s.node_id, s.entity_id) for s in after.passives.socketed] == [
        (s.node_id, s.entity_id) for s in before.passives.socketed]
    assert after.passives.socketed[0].entity_id in items


def test_weapon_sets_survive_with_their_own_allocations(supported):
    before, _ = supported_build()
    after = import_build(supported.document, SYNTHETIC_NAMING, record_id="r",
                         created_at="1970-01-01T00:00:00Z",
                         catalog_hash=before.catalog_hash).build
    assert [(w.set_id, w.passive_allocations) for w in after.weapon_sets] == [
        ("set-main", ["node-b"]), ("set-swap", ["node-c"])]
    assert after.weapon_sets[0].hand_slots == {"main_hand": "slot-weapon1",
                                               "off_hand": "slot-weapon2"}


def test_a_weapon_set_allocation_is_also_allocated_in_the_document(supported):
    """PoB reads the allocation from Spec@nodes and only the set from WeaponSetN."""
    assert 'nodes="101,102,103,104,201"' in supported.document
    assert '<WeaponSet1 nodes="102" />' in supported.document
    assert '<WeaponSet2 nodes="103" />' in supported.document


def test_config_keeps_its_three_value_types(supported):
    before, _ = supported_build()
    after = import_build(supported.document, SYNTHETIC_NAMING, record_id="r",
                         created_at="1970-01-01T00:00:00Z",
                         catalog_hash=before.catalog_hash).build
    assert after.config["enemyIsBoss"].value == "Boss"
    assert after.config["conditionFullLife"].value is True
    assert after.config["multiplierFixtureStacks"].value == 5
    assert isinstance(after.config["multiplierFixtureStacks"].value, int)


def test_an_explicitly_empty_slot_stays_empty_and_is_not_dropped(supported):
    before, _ = supported_build()
    after = import_build(supported.document, SYNTHETIC_NAMING, record_id="r",
                         created_at="1970-01-01T00:00:00Z",
                         catalog_hash=before.catalog_hash).build
    assert after.equipment["slot-weapon2"] is None
    assert "slot-weapon2" in after.equipment


def test_the_document_pins_the_character_level(supported):
    """PoB recomputes the level from the tree in auto mode (P00-OBS-02)."""
    assert 'characterLevelAutoMode="false"' in supported.document
    assert 'level="84"' in supported.document


# ----------------------------------------------------- unsupported fixtures

@pytest.mark.parametrize("name,expected_path", [
    ("trigger_nested", "/skill_groups/0/skills/0/triggered"),
    ("progression", "/progression"),
    ("item_granted_group", "/skill_groups/0/source_item_hash"),
    ("unresolved_catalog", "/class_id"),
])
def test_an_unsupported_field_makes_the_export_incomplete(name, expected_path):
    report = round_trip(*ALL_FIXTURES[name](), SYNTHETIC_NAMING)
    assert report.export.completeness == "incomplete"
    assert report.recommended_deliverable is False
    assert report.status == "incomplete"
    assert expected_path in report.export.paths()


def test_an_unsupported_field_is_preserved_in_the_report_not_dropped():
    report = round_trip(*trigger_nested_build(), SYNTHETIC_NAMING)
    loss = next(u for u in report.export.unsupported
                if u.field_path.endswith("/triggered"))
    assert loss.preserved == ["skill-trigger"]
    assert "no trigger nesting" in loss.reason


def test_progression_flags_are_preserved_in_the_report():
    report = round_trip(*progression_build(), SYNTHETIC_NAMING)
    loss = next(u for u in report.export.unsupported
                if u.field_path == "/progression")
    assert loss.preserved["quest_flags"] == {"fixture-quest-1": True}
    assert loss.preserved["normal_point_budget"] == 99


@pytest.mark.parametrize("name", sorted(ALL_FIXTURES))
def test_a_complete_export_never_differs_on_reimport(name):
    """The invariant: a declared limitation is reported, a defect is not."""
    report = round_trip(*ALL_FIXTURES[name](), SYNTHETIC_NAMING)
    assert report.status != "unfaithful", [d.as_dict() for d in report.differences]
    if report.export.complete:
        assert report.identity_preserved


@pytest.mark.parametrize("name", sorted(ALL_FIXTURES))
def test_every_reported_identity_loss_names_a_field_that_actually_differs(name):
    """A report that over-claims is as useless as one that under-claims."""
    report = round_trip(*ALL_FIXTURES[name](), SYNTHETIC_NAMING)
    if not report.export.identity_losses:
        return
    assert report.differences, "losses reported but nothing differs"
    roots = {u.field_path.split("/")[1] for u in report.export.identity_losses}
    changed = {d.path.split("/")[1] for d in report.differences}
    assert changed <= roots, (changed, roots)


# ------------------------------------------------------------------ naming

def test_a_naming_table_that_cannot_be_inverted_is_refused():
    naming = CatalogNaming(class_names={"class-a": "Huntress",
                                        "class-b": "Huntress"})
    with pytest.raises(AmbiguousNaming):
        naming.check_invertible()
    with pytest.raises(AmbiguousNaming):
        export_build(supported_build()[0], {}, naming)


def test_an_unnamed_catalog_id_is_reported_and_never_guessed():
    report = round_trip(*unresolved_catalog_build(), SYNTHETIC_NAMING)
    paths = report.export.paths()
    assert "/class_id" in paths
    assert "/ascendancy_id" in paths
    assert "/passives/allocated" in paths
    preserved = [u.preserved for u in report.export.unsupported
                 if u.field_path == "/passives/allocated"]
    assert preserved == ["node-not-in-the-table"]


def test_an_item_hash_with_no_instance_is_reported_not_written_as_empty():
    build, _items = supported_build()
    export = export_build(build, {}, SYNTHETIC_NAMING)
    assert export.completeness == "incomplete"
    assert export.item_ids == {}
    assert [u.field_path for u in export.report.unsupported].count(
        "/equipment") == 3
