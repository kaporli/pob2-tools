"""BuildSpec schema version 2: support settings and the main skill group.

The P02 follow-up. Version 2 adds ``SkillEntry.supports`` (each support's
gem, level, quality and enabled state) and ``BuildSpec.main_skill_group``.
These tests pin the version rules, the versioned identity, the migration
from version 1, and that an unknown setting still blocks a recommended
export: the PR #5 guard is kept, not relaxed.

Offline; the synthetic naming table from ``p02_t05_fixtures``.
"""

from __future__ import annotations

from dataclasses import replace

import pytest
from p02_t05_fixtures import SYNTHETIC_NAMING, supported_build

from pob2opt.domain.absent import ABSENT
from pob2opt.domain.enums import RecordParseStatus
from pob2opt.domain.identity import build_hash, build_identity
from pob2opt.domain.migrate import (UNKNOWN_SETTINGS_REASON,
                                    has_unknown_support_settings,
                                    upgrade_build_spec)
from pob2opt.domain.records import SupportGem
from pob2opt.domain.schemas import UnknownSchemaVersion, check_schema_version
from pob2opt.domain.validation import validate_record
from pob2opt.evaluation import (AmbiguousNaming, CatalogNaming, export_build,
                                import_build, round_trip)
from pob2opt.evaluation.naming import UnresolvedName

CREATED = "2026-10-14T00:00:00Z"
#: Stand-in raw payload hash; the P02 fixture carries none.
RAW = "a" * 64


def v2_build(**settings):
    """The supported fixture as a complete version 2 record."""
    build, items = supported_build()
    build = replace(build, raw_blob_hashes=[RAW])
    upgraded = upgrade_build_spec(build, record_id="v2", created_at=CREATED)
    level = settings.get("level", 3)
    quality = settings.get("quality", 7)
    enabled = settings.get("enabled", True)

    def fill(skill):
        return replace(skill, supports=[
            SupportGem(support_id=s.support_id, gem_id=None, level=level,
                       quality=quality, enabled=enabled)
            for s in skill.supports],
            triggered=[fill(c) for c in skill.triggered])

    groups = [replace(g, skills=[fill(s) for s in g.skills])
              for g in upgraded.skill_groups]
    refs = [r for r in upgraded.unresolved_refs
            if r.reason != UNKNOWN_SETTINGS_REASON]
    out = replace(upgraded, skill_groups=groups, unresolved_refs=refs,
                  parse_status=build.parse_status)
    return replace(out, build_hash=build_hash(out)), items


# ------------------------------------------------------------ versions ---

def test_build_spec_reads_versions_one_and_two_and_others_only_one():
    assert check_schema_version(2, "build_spec") == 2
    assert check_schema_version(1, "build_spec") == 1
    with pytest.raises(UnknownSchemaVersion) as error:
        check_schema_version(2, "item_instance")
    assert "1" in str(error.value)
    with pytest.raises(UnknownSchemaVersion):
        check_schema_version(3, "build_spec")


def test_a_version_two_record_validates():
    build, _ = v2_build()
    report = validate_record(build)
    assert report.ok, report.errors


def test_version_one_cannot_carry_support_settings():
    build, _ = v2_build()
    as_v1 = replace(build, schema_version=1, main_skill_group=ABSENT)
    codes = validate_record(as_v1).codes()
    assert "support_settings_need_v2" in codes


def test_version_two_must_list_every_support_in_order():
    build, _ = v2_build()
    group = build.skill_groups[0]
    skill = group.skills[0]
    swapped = replace(skill, supports=list(reversed(skill.supports)))
    broken = replace(build, skill_groups=[replace(group, skills=[swapped])]
                     + build.skill_groups[1:])
    assert "support_settings_mismatch" in validate_record(broken).codes()
    missing = replace(build, skill_groups=[replace(group, skills=[
        replace(skill, supports=ABSENT)])] + build.skill_groups[1:])
    assert "missing_support_settings" in validate_record(missing).codes()


def test_a_complete_record_cannot_have_an_unknown_support_setting():
    build, _ = v2_build(level=None)
    codes = validate_record(build).codes()
    assert "inconsistent_parse_status" in codes


def test_the_main_group_must_exist_and_belong_to_version_two():
    build, _ = v2_build()
    assert "main_group_out_of_range" in validate_record(
        replace(build, main_skill_group=len(build.skill_groups))).codes()
    assert validate_record(replace(build, main_skill_group=ABSENT)).codes()
    assert "inconsistent_parse_status" in validate_record(
        replace(build, main_skill_group=None)).codes()
    original, _ = supported_build()
    report = validate_record(replace(original, main_skill_group=0,
                                     raw_blob_hashes=[RAW]))
    # The schema forbids the field below version 2 before semantics run.
    assert set(report.codes()) & {"schema_violation", "main_group_needs_v2"}


# ------------------------------------------------------------ identity ---

def test_a_version_one_hash_is_unchanged_by_the_extension():
    build, _ = supported_build()
    assert "identity_version" not in build_identity(build)
    assert "supports" not in build_identity(build)["skill_groups"][0]["skills"][0]
    assert build.build_hash == build_hash(build)


@pytest.mark.parametrize("setting,value", [("level", 4), ("quality", 8),
                                           ("enabled", False)])
def test_every_support_setting_is_part_of_the_identity(setting, value):
    base, _ = v2_build()
    other, _ = v2_build(**{setting: value})
    assert build_hash(base) != build_hash(other)


def test_the_main_group_is_part_of_the_identity():
    build, _ = v2_build()
    assert build_hash(build) != build_hash(replace(build, main_skill_group=1))


def test_versions_never_collide():
    build, _ = supported_build()
    upgraded = upgrade_build_spec(build, record_id="u", created_at=CREATED)
    assert build_identity(upgraded)["identity_version"] == 2
    assert build.build_hash != upgraded.build_hash


# ----------------------------------------------------------- migration ---

def test_an_upgrade_never_invents_support_settings():
    build, _ = supported_build()
    build = replace(build, raw_blob_hashes=[RAW])
    upgraded = upgrade_build_spec(build, record_id="u", created_at=CREATED)
    supports = upgraded.skill_groups[0].skills[0].supports
    assert supports and all(s.level is None and s.quality is None
                            and s.enabled is None for s in supports)
    assert upgraded.parse_status is RecordParseStatus.PARTIAL
    paths = [r.field_path for r in upgraded.unresolved_refs]
    assert "/skill_groups/0/skills/0/supports/0" in paths
    assert has_unknown_support_settings(upgraded)
    assert validate_record(upgraded).ok, validate_record(upgraded).errors


def test_an_upgrade_keeps_the_main_group_the_version_one_export_used():
    build, items = supported_build()
    upgraded = upgrade_build_spec(build, record_id="u", created_at=CREATED)
    expected = next(i for i, g in enumerate(build.skill_groups)
                    if g.main_skill_index is not None)
    assert upgraded.main_skill_group == expected
    old = export_build(build, items, SYNTHETIC_NAMING).xml
    new = export_build(upgraded, items, SYNTHETIC_NAMING).xml
    marker = 'mainSocketGroup="%d"' % (expected + 1)
    assert marker in old and marker in new


def test_an_upgrade_returns_a_new_record_and_leaves_the_old_one():
    build, _ = supported_build()
    before = build_identity(build)
    upgraded = upgrade_build_spec(build, record_id="u", created_at=CREATED)
    assert build_identity(build) == before
    assert upgraded.record_id == "u"
    assert build.record_id in upgraded.provenance_ids
    with pytest.raises(ValueError):
        upgrade_build_spec(upgraded, record_id="again", created_at=CREATED)


def test_a_build_without_supports_upgrades_complete():
    build, _ = supported_build()
    bare = replace(build, skill_groups=[replace(g, skills=[
        replace(s, support_ids=[]) for s in g.skills])
        for g in build.skill_groups])
    upgraded = upgrade_build_spec(bare, record_id="u", created_at=CREATED)
    assert not has_unknown_support_settings(upgraded)


# ------------------------------------------------------- documents ---

def test_a_known_support_state_round_trips_faithfully():
    build, items = v2_build(level=5, quality=13, enabled=False)
    build = replace(build, skill_groups=[replace(g, skills=[
        replace(s, triggered=[]) for s in g.skills])
        for g in build.skill_groups])
    build = replace(build, build_hash=build_hash(build))
    trip = round_trip(build, items, SYNTHETIC_NAMING)
    support_losses = [u for u in trip.export.unsupported
                      if "/support" in u.field_path]
    assert support_losses == []
    assert trip.identity_preserved, [d.as_dict() for d in trip.differences]
    reread = import_build(trip.document, SYNTHETIC_NAMING, record_id="r",
                          created_at=CREATED,
                          catalog_hash=build.catalog_hash).build
    support = reread.skill_groups[0].skills[0].supports[0]
    assert (support.level, support.quality, support.enabled) == (5, 13, False)


@pytest.mark.parametrize("unknown", ["level", "quality", "enabled"])
def test_an_unknown_setting_blocks_the_deliverable(unknown):
    build, items = v2_build(**{unknown: None})
    build = replace(build, parse_status=RecordParseStatus.PARTIAL)
    export = export_build(build, items, SYNTHETIC_NAMING)
    assert not export.recommended_deliverable
    reasons = [u.reason for u in export.report.unsupported
               if "/supports/" in u.field_path]
    assert any(unknown in reason for reason in reasons)


def test_a_main_group_after_the_first_round_trips():
    build, items = v2_build()
    moved = replace(build, main_skill_group=1)
    moved = replace(moved, build_hash=build_hash(moved))
    document = export_build(moved, items, SYNTHETIC_NAMING).xml
    assert 'mainSocketGroup="2"' in document
    reread = import_build(document, SYNTHETIC_NAMING, record_id="r",
                          created_at=CREATED, catalog_hash=build.catalog_hash)
    assert reread.build.main_skill_group == 1


def test_a_main_group_naming_no_group_is_reported():
    build, items = v2_build()
    document = export_build(build, items, SYNTHETIC_NAMING).xml
    document = document.replace('mainSocketGroup="1"', 'mainSocketGroup="9"')
    reread = import_build(document, SYNTHETIC_NAMING, record_id="r",
                          created_at=CREATED, catalog_hash=build.catalog_hash)
    assert reread.build.main_skill_group is None
    assert reread.build.parse_status is RecordParseStatus.PARTIAL


# ------------------------------------------------------- gem naming ---

def test_gems_resolve_on_the_gem_and_variant_pair():
    naming = CatalogNaming(gem_ids={"gem-a": "Metadata/G", "gem-b": "Metadata/G"},
                           gem_variant_ids={"gem-a": "A", "gem-b": "B"})
    naming.check_invertible()
    assert naming.reverse_gem("Metadata/G", "B") == "gem-b"
    with pytest.raises(UnresolvedName):
        naming.reverse_gem("Metadata/G", None)  # two gems share it
    with pytest.raises(UnresolvedName):
        naming.reverse_gem("Metadata/G", "C")


def test_a_gem_pair_shared_by_two_ids_is_refused():
    naming = CatalogNaming(gem_ids={"gem-a": "Metadata/G", "gem-b": "Metadata/G"})
    with pytest.raises(AmbiguousNaming):
        naming.check_invertible()
