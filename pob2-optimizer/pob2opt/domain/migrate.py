"""Record migrations between schema versions.

BuildSpec version 1 to 2. Version 2 adds ``SkillEntry.supports``, the
settings of each support, and ``main_skill_group``.

Support settings: a version 1 record never recorded them, so the upgrade
cannot know them. Every setting becomes null (unknown), the record becomes
``partial`` when any skill has a support, and each unknown support is listed
in ``unresolved_refs``. Nothing is filled from PoB defaults.

Main skill group: the group the version 1 exporter wrote as PoB's main
socket group, that is the first group with a main skill index, else the
first group. This is the version 1 record's own export behaviour, not a
guess.

The upgrade returns a new record with its own ``record_id``; the version 1
record stays as stored. Its hash changes, because a version 2 identity is a
different projection (``identity.SUPPORT_IDENTITY_VERSION``).
"""

from __future__ import annotations

from dataclasses import replace

from .absent import ABSENT
from .enums import RecordParseStatus
from .identity import build_hash
from .records import (BUILD_SPEC_SCHEMA_VERSION, BuildSpec, SkillEntry,
                      SupportGem, UnresolvedRef)

#: Reason recorded for a support whose settings a version 1 record lacks.
UNKNOWN_SETTINGS_REASON = (
    "support settings unknown: BuildSpec schema version 1 did not record "
    "level, quality or enabled state")


def _upgrade_skill(skill: SkillEntry, path: str,
                   unknown: list[UnresolvedRef]) -> SkillEntry:
    supports = []
    for k, support_id in enumerate(skill.support_ids):
        supports.append(SupportGem(support_id=support_id, gem_id=None,
                                   level=None, quality=None, enabled=None))
        unknown.append(UnresolvedRef(field_path="%s/supports/%d" % (path, k),
                                     reference=support_id,
                                     reason=UNKNOWN_SETTINGS_REASON))
    triggered = [_upgrade_skill(child, "%s/triggered/%d" % (path, k), unknown)
                 for k, child in enumerate(skill.triggered)]
    return replace(skill, triggered=triggered, supports=supports)


def upgrade_build_spec(build: BuildSpec, *, record_id: str,
                       created_at: str) -> BuildSpec:
    """A version 2 copy of a version 1 BuildSpec, with support settings unknown."""
    if build.schema_version >= BUILD_SPEC_SCHEMA_VERSION:
        raise ValueError("BuildSpec %s is already schema version %d"
                         % (build.record_id, build.schema_version))
    unknown: list[UnresolvedRef] = []
    groups = []
    for i, group in enumerate(build.skill_groups):
        skills = [_upgrade_skill(skill, "/skill_groups/%d/skills/%d" % (i, j),
                                 unknown)
                  for j, skill in enumerate(group.skills)]
        groups.append(replace(group, skills=skills))
    # The version 1 exporter evaluated the first group with a main skill
    # index, or the first group; version 2 states that choice.
    main_group = None
    if groups:
        main_group = next((i for i, g in enumerate(groups)
                           if g.main_skill_index is not None), 0)
    status = build.parse_status
    if unknown and status is RecordParseStatus.COMPLETE:
        status = RecordParseStatus.PARTIAL
    upgraded = replace(
        build, schema_version=BUILD_SPEC_SCHEMA_VERSION, record_id=record_id,
        created_at=created_at,
        provenance_ids=list(build.provenance_ids) + [build.record_id],
        skill_groups=groups, main_skill_group=main_group,
        parse_status=status,
        unresolved_refs=list(build.unresolved_refs) + unknown)
    return replace(upgraded, build_hash=build_hash(upgraded))


def has_unknown_support_settings(build: BuildSpec) -> bool:
    """True when any support's settings are not fully known."""
    def unknown(skill: SkillEntry) -> bool:
        if skill.support_ids and skill.supports is ABSENT:
            return True
        if skill.supports is not ABSENT and any(
                s.level is None or s.quality is None or s.enabled is None
                for s in skill.supports):
            return True
        return any(unknown(child) for child in skill.triggered)
    return any(unknown(skill) for group in build.skill_groups
               for skill in group.skills)
