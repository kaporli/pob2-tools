"""Adversarial PR #5 cases; no engine, filesystem writes or network required."""
import copy
import json
import xml.etree.ElementTree as ET
from dataclasses import replace

import pytest

import legality_fixtures as lf
from p02_t05_fixtures import SYNTHETIC_NAMING, supported_build
from pob2opt.catalog import ExportRequest, MappingCatalogReader, PobCatalogProvider
from pob2opt.catalog.release import load_release_capture
from pob2opt.catalog.sources import citations_from_payload
from pob2opt.domain.enums import RecordParseStatus
from pob2opt.evaluation import export_build, import_build, round_trip
from pob2opt.evaluation.legality import LegalityValidator


def fixture_document():
    build, items = supported_build()
    # A fully representable control: support settings need a future schema.
    build = replace(build, skill_groups=[replace(g, skills=[
        replace(s, support_ids=[]) for s in g.skills]) for g in build.skill_groups])
    return ET.fromstring(export_build(build, items, SYNTHETIC_NAMING).xml)


def read(root):
    return import_build(ET.tostring(root, encoding="unicode"), SYNTHETIC_NAMING,
                        record_id="pr5", created_at="2026-10-10T00:00:00Z",
                        catalog_hash="f" * 64)


def assert_incomplete(parsed):
    assert parsed.build.parse_status == RecordParseStatus.PARTIAL
    assert parsed.build.unresolved_refs
    assert not parsed.report.complete
    assert not export_build(parsed.build, parsed.items, SYNTHETIC_NAMING).recommended_deliverable
    assert not round_trip(parsed.build, parsed.items, SYNTHETIC_NAMING).recommended_deliverable


def test_fully_representable_control_is_recommended():
    parsed = read(fixture_document())
    assert parsed.report.complete, parsed.report.as_dict()
    assert parsed.build.parse_status == RecordParseStatus.COMPLETE
    assert round_trip(parsed.build, parsed.items, SYNTHETIC_NAMING).recommended_deliverable


@pytest.mark.parametrize("path,attr,value", [
    ("Tree/Spec", "nodes", "101,99999999"),
    ("Build", "className", "UnknownClass"),
    ("Build", "ascendClassName", "UnknownAscendancy"),
    ("Skills/SkillSet/Skill/Gem", "skillId", "UnknownSkill"),
    ("Skills/SkillSet/Skill/Gem", "gemId", "UnknownGem"),
    ("Items/ItemSet/Slot", "name", "UnknownSlot"),
    ("Tree/Spec/Sockets/Socket", "itemId", "99999999"),
    ("Tree/Spec/Sockets/Socket", "nodeId", "99999999"),
])
def test_unresolved_content_survives_and_blocks_recommendation(path, attr, value):
    root = fixture_document()
    root.find(path).set(attr, value)
    parsed = read(root)
    assert value in parsed.source_document
    assert any(value.split(",")[-1] in ref.reference for ref in parsed.build.unresolved_refs)
    assert parsed.build.raw_blob_hashes
    assert_incomplete(parsed)


@pytest.mark.parametrize("enabled", ["false", "true"])
def test_support_settings_are_preserved_as_gameplay_data(enabled):
    """R2, superseded by BuildSpec schema version 2.

    The settings are now held in the record rather than only preserved as
    source XML, so the import is complete and the export carries them.
    """
    root = fixture_document()
    ET.SubElement(root.find("Skills/SkillSet/Skill"), "Gem", {
        "skillId": "FixtureSupportTempo", "enabled": enabled, "level": "7", "quality": "19"})
    parsed = read(root)
    assert parsed.build.schema_version == 2
    assert parsed.build.parse_status == RecordParseStatus.COMPLETE
    support = parsed.build.skill_groups[0].skills[0].supports[0]
    assert (support.support_id, support.level, support.quality, support.enabled) == (
        "support-tempo", 7, 19, enabled == "true")
    trip = round_trip(parsed.build, parsed.items, SYNTHETIC_NAMING)
    assert trip.status == "faithful", trip.as_dict()
    gem = [g for g in ET.fromstring(trip.document).iter("Gem")
           if g.get("skillId") == "FixtureSupportTempo"][0]
    assert (gem.get("enabled"), gem.get("level"), gem.get("quality")) == (enabled, "7", "19")


@pytest.mark.parametrize("missing", ["level", "quality", "enabled"])
def test_an_unknown_support_setting_still_blocks_recommendation(missing):
    """The R2 guard is not relaxed: an absent setting is unknown, not a default."""
    root = fixture_document()
    attrib = {"skillId": "FixtureSupportTempo", "enabled": "true", "level": "7",
              "quality": "19"}
    del attrib[missing]
    ET.SubElement(root.find("Skills/SkillSet/Skill"), "Gem", attrib)
    parsed = read(root)
    support = parsed.build.skill_groups[0].skills[0].supports[0]
    assert getattr(support, missing) is None
    export = export_build(parsed.build, parsed.items, SYNTHETIC_NAMING)
    assert not export.recommended_deliverable
    assert any(u.field_path.endswith("/supports/0") for u in export.report.unsupported)


def test_a_version_1_build_with_supports_still_exports_incomplete():
    build, items = supported_build()
    assert build.schema_version == 1 and build.skill_groups[0].skills[0].support_ids
    export = export_build(build, items, SYNTHETIC_NAMING)
    assert not export.recommended_deliverable
    assert not round_trip(build, items, SYNTHETIC_NAMING).recommended_deliverable


@pytest.mark.parametrize("tag,child,selector", [
    ("Skills", "SkillSet", "activeSkillSet"),
    ("Items", "ItemSet", "activeItemSet"),
    ("Tree", "Spec", "activeSpec"),
    ("Config", "ConfigSet", "activeConfigSet"),
])
def test_active_variant_is_selected_and_others_are_retained(tag, child, selector):
    root = fixture_document()
    container = root.find(tag)
    second = copy.deepcopy(container.find(child))
    second.set("id", "2")
    if tag == "Skills":
        second.find("Skill").set("label", "selected variant")
    elif tag == "Items":
        second.find("Slot").set("itemId", "0")
    elif tag == "Tree":
        second.set("nodes", "101")
    else:
        ET.SubElement(second, "Input", {"name": "reviewVariant", "number": "2"})
    container.append(second)
    container.set(selector, "2")
    parsed = read(root)
    if tag == "Skills":
        assert parsed.build.skill_groups[0].group_id == "selected variant"
    elif tag == "Items":
        name = second.find("Slot").get("name")
        assert parsed.build.equipment[SYNTHETIC_NAMING.reverse("slot_names", name)] is None
    elif tag == "Tree":
        assert parsed.build.passives.allocated == ["node-a"]
    else:
        assert parsed.build.config["reviewVariant"].value == 2
    assert_incomplete(parsed)  # inactive variants cannot be represented by one BuildSpec
    assert any("variant" in loss.reason for loss in parsed.report.unsupported)
    if tag != "Tree":  # tree selectors are positional; other selectors are IDs
        container.remove(second)
        container.insert(0, second)
        assert read(root).build.build_hash == parsed.build.build_hash
    container.set(selector, "999")
    invalid = read(root)
    assert_incomplete(invalid)
    assert any("selector" in loss.reason for loss in invalid.report.unsupported)


def export_captures(captures, **request):
    world = json.loads(lf.WORLD.read_text(encoding="utf-8"))
    citations = citations_from_payload(json.loads(lf.SLICE.read_text(encoding="utf-8"))["citations"])
    return PobCatalogProvider(
        MappingCatalogReader(world["tables"], world["rule_sources"]),
        citations=citations, release_captures=captures, fixtures=lf.NO_FIXTURES,
        pob_commit="0" * 40, clock=lambda: "2026-10-10T00:00:00Z"
    ).export(ExportRequest(**request))


def captures():
    capture = load_release_capture(lf.REPO_ROOT / "docs/evidence/P02/release/poe2-0.5.5e.json")
    newer = replace(capture, patch_id="new", patch_published_at="2026-10-01T00:00:00Z",
                    captured_at="2026-10-02T00:00:00Z")
    older = replace(capture, patch_id="old", patch_published_at="2026-09-01T00:00:00Z",
                    captured_at="2026-10-03T00:00:00Z")
    return newer, older


def test_recapturing_old_patch_does_not_change_live_resolution_or_historical_pin():
    newer, older = captures()
    for ordered in ([newer, older], [older, newer]):
        result = export_captures(ordered)
        assert result.profile.patch_id == "new"
        assert not result.validation_errors
        historical = export_captures(ordered, pinned_patch_id="old")
        assert historical.profile.patch_id == "old"
        assert historical.profile.compatibility.value == "stale"


@pytest.mark.parametrize("conflict", ["missing_date", "same_time", "same_patch"])
def test_ambiguous_release_chronology_is_a_gap(conflict):
    newer, older = captures()
    if conflict == "missing_date":
        older = replace(older, patch_published_at=None)
    elif conflict == "same_time":
        older = replace(older, patch_published_at=newer.patch_published_at)
    else:
        older = replace(older, patch_id=newer.patch_id)
    result = export_captures([newer, older])
    assert result.profile.patch_id == "unknown"
    assert result.profile.compatibility.value == "unknown"
    assert any("current-patch-unresolved" in gap.gap_id for gap in result.gaps)
    assert not result.validation_errors


def test_release_scope_and_duplicate_captures():
    newer, older = captures()
    result = export_captures([older, replace(newer, game="poe1"),
                             replace(newer, realm="other"), older])
    assert result.profile.patch_id == "old"
    assert not result.validation_errors


@pytest.mark.parametrize("record,engine,expected", [
    ({"level": 1, "str": 1}, {"level": 90, "str": 999}, "illegal"),
    ({"level": 90, "str": 999}, {"level": 1, "str": 1}, "illegal"),
    ({"level": 4, "str": 120}, {"level": 4, "str": 120}, "unknown"),
])
def test_imported_requirements_and_disagreements_are_checked(record, engine, expected):
    world = lf.load_world()
    cases = lf.load_cases()
    items = lf.make_items(cases, world.catalog.catalog_hash)
    items["ring"] = replace(items["ring"], requirements=record)
    spec = {**cases["base"], "equipment": {"Ring 1": {"item": "ring"}}}
    build = lf.make_build(spec, catalog_hash=world.catalog.catalog_hash)
    imported = copy.deepcopy(next(c for c in cases["cases"] if c["id"] == "minimal_legal_verified")["imported"])
    imported["items"] = {"Ring 1": {
        "name": "Invented Ring", "baseName": "Iron Ring", "rarity": "NORMAL",
        "requirements": engine, "sockets": 0}}
    report = LegalityValidator(catalog=world.catalog, items=items,
        imported=lf.make_imported(imported, build_hash=build.build_hash)).validate(build, world.profile)
    assert report.legality.value == expected
    codes = {v.code for v in report.violations}
    if record != engine:
        assert "import_item_requirement_mismatch" in codes
    else:
        assert not report.violations
    if engine["level"] > 4:
        assert "item_level_requirement_not_met" in codes
        assert "item_attribute_requirement_not_met" in codes
