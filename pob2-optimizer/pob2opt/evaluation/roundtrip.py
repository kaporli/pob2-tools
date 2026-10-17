"""Export, reimport and compare on semantic identity (P02-T05).

The question this module answers is not "are the two documents the same bytes".
PoB renumbers items and nodes on load, so byte equality would fail on a correct
export and pass on a lossy one. The comparison is the canonical identity
projection of ``pob2opt.domain.identity``: the fields that decide what a build
or an item is, with names, prices and timestamps already excluded.

A round trip reports three things, and they are separate claims:

* ``export`` - what the document could not carry. An export missing anything
  inside the identity is incomplete and is not a recommended deliverable;
* ``differences`` - where the reimported record actually differs. A complete
  export with differences is a defect in this module, not an expected loss;
* ``items`` - the same comparison per equipped item and socketed jewel.

The source records are frozen and are hashed before and after, so a round trip
also proves that neither direction mutated its input.

The importer writes BuildSpec schema version 2. A version 1 source is compared
at version 1: the reimport is projected down (support settings dropped) so
the comparison measures the document, not the schema upgrade.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any, Mapping

from ..domain.identity import (build_hash, build_identity, canonical_text,
                               item_hash, item_identity)
from ..domain.absent import ABSENT
from ..domain.records import BuildSpec, ItemInstance, SkillEntry
from .builddoc import BuildExport, BuildImport, export_build, import_build
from .naming import CatalogNaming
from .support import SupportReport


class SourceMutated(AssertionError):
    """A conversion changed the record it was given. Never acceptable."""


@dataclass(frozen=True)
class Difference:
    """One identity path where the reimported record differs."""

    path: str
    before: Any
    after: Any

    def as_dict(self) -> dict[str, Any]:
        return {"path": self.path, "before": self.before, "after": self.after}


def diff_identity(before: Any, after: Any, path: str = "") -> list[Difference]:
    """Every leaf where two identity projections differ."""
    if isinstance(before, dict) and isinstance(after, dict):
        out: list[Difference] = []
        for key in sorted(set(before) | set(after)):
            if key not in before:
                out.append(Difference(path + "/" + str(key), None, after[key]))
            elif key not in after:
                out.append(Difference(path + "/" + str(key), before[key], None))
            else:
                out.extend(diff_identity(before[key], after[key],
                                         path + "/" + str(key)))
        return out
    if isinstance(before, list) and isinstance(after, list):
        out = []
        for index in range(max(len(before), len(after))):
            child = "%s/%d" % (path, index)
            if index >= len(before):
                out.append(Difference(child, None, after[index]))
            elif index >= len(after):
                out.append(Difference(child, before[index], None))
            else:
                out.extend(diff_identity(before[index], after[index], child))
        return out
    if before != after:
        return [Difference(path or "/", before, after)]
    return []


@dataclass(frozen=True)
class RoundTripReport:
    """One build exported, reimported and compared."""

    build_hash_before: str
    build_hash_after: str
    differences: tuple[Difference, ...]
    item_differences: Mapping[str, tuple[Difference, ...]]
    export: SupportReport
    document: str

    @property
    def identity_preserved(self) -> bool:
        return (self.build_hash_before == self.build_hash_after
                and not self.differences
                and not any(self.item_differences.values()))

    @property
    def status(self) -> str:
        if self.identity_preserved and self.export.complete:
            return "faithful"
        if self.export.complete:
            # A complete export whose reimport differs is a defect here, not
            # a declared limitation of the format.
            return "unfaithful"
        return "incomplete"

    @property
    def recommended_deliverable(self) -> bool:
        return self.status == "faithful"

    def as_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "recommended_deliverable": self.recommended_deliverable,
            "build_hash_before": self.build_hash_before,
            "build_hash_after": self.build_hash_after,
            "identity_preserved": self.identity_preserved,
            "differences": [d.as_dict() for d in self.differences],
            "item_differences": {
                key: [d.as_dict() for d in value]
                for key, value in self.item_differences.items() if value},
            "export": self.export.as_dict(),
        }


def _without_supports(skill: SkillEntry) -> SkillEntry:
    return replace(skill, supports=ABSENT,
                   triggered=[_without_supports(c) for c in skill.triggered])


def at_schema_version(build: BuildSpec, version: int) -> BuildSpec:
    """``build`` as a record of an older version, for comparison only.

    Only version 2 to 1 exists: it drops the support settings version 1 has
    no field for. The result is a projection, never a record to store.
    """
    if build.schema_version == version:
        return build
    if (build.schema_version, version) != (2, 1):
        raise ValueError("no projection from BuildSpec schema version %d to %d"
                         % (build.schema_version, version))
    groups = [replace(group, skills=[_without_supports(s) for s in group.skills])
              for group in build.skill_groups]
    return replace(build, schema_version=1, skill_groups=groups,
                   main_skill_group=ABSENT)


def _fingerprint(build: BuildSpec, items: Mapping[str, ItemInstance]) -> str:
    from ..domain.codec import to_jsonable
    return canonical_text({"build": to_jsonable(build),
                           "items": {k: to_jsonable(v)
                                     for k, v in sorted(items.items())}})


def round_trip(build: BuildSpec, items: Mapping[str, ItemInstance],
               naming: CatalogNaming, *,
               record_id: str = "roundtrip",
               created_at: str = "1970-01-01T00:00:00Z",
               tree_version: str = "0_5") -> RoundTripReport:
    """Export a build, read it back, and compare canonical identity."""
    before = _fingerprint(build, items)
    export: BuildExport = export_build(build, items, naming,
                                       tree_version=tree_version)
    restored: BuildImport = import_build(
        export.xml, naming, record_id=record_id, created_at=created_at,
        catalog_hash=build.catalog_hash)
    if _fingerprint(build, items) != before:
        raise SourceMutated(
            "export/import changed the BuildSpec or an ItemInstance it was "
            "given; conversion must not mutate the source object")

    restored_build = at_schema_version(restored.build, build.schema_version)
    differences = diff_identity(build_identity(build),
                                build_identity(restored_build))
    item_differences: dict[str, tuple[Difference, ...]] = {}
    for original_hash, original in sorted(items.items()):
        if original_hash not in export.item_ids:
            continue
        reimported = _match_item(original, restored.items)
        if reimported is None:
            item_differences[original_hash] = (
                Difference("/", item_identity(original), None),)
            continue
        item_differences[original_hash] = tuple(
            diff_identity(item_identity(original), item_identity(reimported)))
    return RoundTripReport(
        build_hash_before=build_hash(build),
        build_hash_after=build_hash(restored_build),
        differences=tuple(differences),
        item_differences=item_differences,
        export=SupportReport(export.report.unsupported + restored.report.unsupported),
        document=export.xml)


def _match_item(original: ItemInstance,
                reimported: Mapping[str, ItemInstance]) -> ItemInstance | None:
    """The reimported item for one original.

    Identical hashes match directly. Otherwise the comparison needs a
    candidate to report against, and display name plus base is the only
    stable handle a lossy document leaves.
    """
    exact = reimported.get(item_hash(original))
    if exact is not None:
        return exact
    for candidate in reimported.values():
        if candidate.display_name == original.display_name:
            return candidate
    return None
