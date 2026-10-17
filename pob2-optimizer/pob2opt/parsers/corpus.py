"""Deduplicate, group and audit parsed builds (P04-T05).

Exact duplicates share a canonical gameplay hash (``BuildSpec.build_hash``).
They are grouped, not dropped: every record, source and creator is kept, and
:func:`independent_builds` counts a hash once however many creators posted it.
Only builds of one schema version are comparable this way, because the
version is part of the identity projection.

Families start as engineer proposals from a fixed rule: the main skill, plus
the supports and triggered skills it is played with. A proposal carries no
family ID. A domain reviewer accepts it, possibly under another label, or
rejects it, and only an accepted label yields a family ID. Family IDs serve
sampling and holdout splits, never a correctness decision.

:func:`audit_variant` re-reads the source document independently of the
importer and compares it field by field with the normalized records: gear
modifier lines, skill and support levels, quality and enabled state, passive
allocations and set bindings. A mismatch fails the audit unless the record
declares that field unresolved.
"""

from __future__ import annotations

import hashlib
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, replace
from typing import Any, Iterable, Mapping, Sequence

from ..domain.absent import ABSENT
from ..domain.identity import build_hash
from ..domain.records import BuildSpec, ItemInstance, SourceDocument
from ..evaluation.itemtext import CATEGORY_MARKER
from ..evaluation.naming import CatalogNaming, UnresolvedName
from ..evaluation.variants import SET_TABLES

FAMILY_RULE = "p04-t05.main-skill-and-interactions.1"


# ------------------------------------------------------------ duplicates ---

@dataclass(frozen=True)
class CorpusEntry:
    build: BuildSpec
    #: The source documents behind this record, for creator and provider.
    sources: tuple[SourceDocument, ...]


@dataclass(frozen=True)
class DuplicateGroup:
    build_hash: str
    schema_version: int
    record_ids: tuple[str, ...]
    variant_ids: tuple[str | None, ...]
    source_document_ids: tuple[str, ...]
    creators: tuple[str | None, ...]
    providers: tuple[str, ...]


def exact_duplicates(entries: Iterable[CorpusEntry]) -> list[DuplicateGroup]:
    """Records grouped by gameplay hash; every member and its lineage kept."""
    groups: dict[tuple[int, str], list[CorpusEntry]] = {}
    for entry in entries:
        key = (entry.build.schema_version, entry.build.build_hash)
        groups.setdefault(key, []).append(entry)
    out = []
    for (version, digest), members in sorted(groups.items()):
        sources = [s for m in members for s in m.sources]
        out.append(DuplicateGroup(
            build_hash=digest, schema_version=version,
            record_ids=tuple(m.build.record_id for m in members),
            variant_ids=tuple(m.build.variant_id for m in members),
            source_document_ids=tuple(sorted({s.record_id for s in sources})),
            creators=tuple(sorted({s.author_id for s in sources},
                                  key=lambda a: (a is None, a or ""))),
            providers=tuple(sorted({s.provider for s in sources}))))
    return out


def independent_builds(entries: Iterable[CorpusEntry]) -> int:
    """Distinct gameplay hashes. Identical copies by other creators count once."""
    return len({(e.build.schema_version, e.build.build_hash) for e in entries})


# -------------------------------------------------------------- families ---

@dataclass(frozen=True)
class FamilyProposal:
    build_hash: str
    record_id: str
    mechanism: str | None
    interactions: tuple[str, ...]
    label: str
    rule: str = FAMILY_RULE
    status: str = "proposed"


@dataclass(frozen=True)
class FamilyLabel:
    """A reviewed proposal. Only an accepted one has a family ID."""

    proposal: FamilyProposal
    status: str  # "accepted" | "rejected"
    label: str
    reviewer: str
    reviewed_at: str
    note: str = ""

    @property
    def family_id(self) -> str | None:
        if self.status != "accepted":
            return None
        return "family/" + hashlib.sha256(
            self.label.encode("utf-8")).hexdigest()[:16]


def _main_skill(build: BuildSpec):
    group_index = build.main_skill_group
    if group_index is ABSENT:
        group_index = next((i for i, g in enumerate(build.skill_groups)
                            if g.main_skill_index is not None), None)
    if group_index is None or group_index >= len(build.skill_groups):
        return None
    group = build.skill_groups[group_index]
    if not group.skills:
        return None
    index = group.main_skill_index or 0
    return group.skills[min(index, len(group.skills) - 1)]


def propose_family(build: BuildSpec) -> FamilyProposal:
    """The fixed rule: main skill, then its supports and triggered skills."""
    skill = _main_skill(build)
    if skill is None:
        return FamilyProposal(build.build_hash, build.record_id, None, (),
                              "unlabelled: no main skill")
    interactions = tuple(sorted(set(skill.support_ids)
                                | {c.skill_id for c in skill.triggered}))
    label = skill.skill_id + (" + " + ", ".join(interactions)
                              if interactions else "")
    return FamilyProposal(build.build_hash, build.record_id, skill.skill_id,
                          interactions, label)


def review_family(proposal: FamilyProposal, *, accepted: bool, reviewer: str,
                  reviewed_at: str, label: str | None = None,
                  note: str = "") -> FamilyLabel:
    if not reviewer.strip():
        raise ValueError("a family label needs a named reviewer")
    return FamilyLabel(proposal=proposal,
                       status="accepted" if accepted else "rejected",
                       label=label or proposal.label, reviewer=reviewer,
                       reviewed_at=reviewed_at, note=note)


def with_family(build: BuildSpec, label: FamilyLabel, *, record_id: str,
                created_at: str) -> BuildSpec:
    """A new record carrying the accepted family; the original is unchanged."""
    if label.family_id is None:
        raise ValueError("only an accepted family label assigns a family")
    if label.proposal.build_hash != build.build_hash:
        raise ValueError("the label was reviewed for another build")
    out = replace(build, record_id=record_id, created_at=created_at,
                  family_id=label.family_id,
                  provenance_ids=list(build.provenance_ids) + [build.record_id])
    return replace(out, build_hash=build_hash(out))


def holdout_split(family_ids: Iterable[str], *, seed: str,
                  holdout_fraction: float) -> dict[str, str]:
    """Family to ``calibration`` or ``holdout``; a family is never split."""
    if not 0 < holdout_fraction < 1:
        raise ValueError("holdout_fraction must be between 0 and 1")
    out = {}
    for family in sorted(set(family_ids)):
        digest = hashlib.sha256(("%s\0%s" % (seed, family)).encode(
            "utf-8")).digest()
        position = int.from_bytes(digest[:8], "big") / 2 ** 64
        out[family] = "holdout" if position < holdout_fraction else \
            "calibration"
    return out


# ------------------------------------------------------------------ audit ---

@dataclass(frozen=True)
class FieldMismatch:
    domain: str
    field_path: str
    source: Any
    record: Any
    declared_partial: bool


@dataclass(frozen=True)
class AuditResult:
    variant_id: str | None
    compared: Mapping[str, int]
    agreed: Mapping[str, int]
    mismatches: tuple[FieldMismatch, ...]

    @property
    def passed(self) -> bool:
        """Every mismatch is a field the record declares unresolved."""
        return all(m.declared_partial for m in self.mismatches)

    def agreement(self, domain: str) -> float | None:
        compared = self.compared.get(domain, 0)
        return None if compared == 0 else self.agreed.get(domain, 0) / compared

    def as_dict(self) -> dict[str, Any]:
        return {
            "variant_id": self.variant_id, "passed": self.passed,
            "compared": dict(self.compared), "agreed": dict(self.agreed),
            "mismatches": [m.__dict__ for m in self.mismatches],
        }


class _Audit:
    def __init__(self, build: BuildSpec) -> None:
        self.compared: dict[str, int] = {}
        self.agreed: dict[str, int] = {}
        self.mismatches: list[FieldMismatch] = []
        self.declared = [ref.field_path for ref in build.unresolved_refs]

    def check(self, domain: str, path: str, source: Any, record: Any) -> None:
        self.compared[domain] = self.compared.get(domain, 0) + 1
        if source == record:
            self.agreed[domain] = self.agreed.get(domain, 0) + 1
            return
        declared = any(path.startswith(d) or d.startswith(path)
                       for d in self.declared)
        self.mismatches.append(FieldMismatch(domain, path, source, record,
                                             declared))


def _selected(root: ET.Element, selection: Mapping[str, str]
              ) -> dict[str, ET.Element | None]:
    out: dict[str, ET.Element | None] = {}
    for tag, child_tag, selector in SET_TABLES:
        container = root.find(tag)
        if container is None:
            out[tag] = None
            continue
        children = container.findall(child_tag)
        if not children:
            out[tag] = container
            continue
        wanted = selection.get(tag, container.get(selector, "1"))
        out[tag] = next((node for index, node in enumerate(children, 1)
                         if (str(index) if tag == "Tree" else node.get("id"))
                         == wanted), None)
    return out


def _item_lines(text: str) -> list[str]:
    """Modifier lines of PoB item text, with their category markers."""
    lines = [line.strip() for line in text.replace("\r\n", "\n").split("\n")]
    lines = [line for line in lines if line]
    for index, line in enumerate(lines):
        if line.startswith("Implicits:"):
            return lines[index + 1:]
    return []


_MARKER = re.compile(r"\{([^}]*)\}")
#: Markers that are not a category or line flag: variant membership, PoB's
#: crafting tags and roll ranges.
_IGNORED_MARKERS = ("variant:", "tags:", "range:")


def _line_key(line: str) -> tuple[tuple[str, ...], str]:
    """A modifier line as (sorted markers, text), so marker order is moot."""
    markers = []
    position = 0
    while True:
        match = _MARKER.match(line, position)
        if match is None:
            break
        if not match.group(1).startswith(_IGNORED_MARKERS):
            markers.append(match.group(1))
        position = match.end()
    return tuple(sorted(markers)), line[position:]


def _record_lines(item: ItemInstance) -> list[tuple[tuple[str, ...], str]]:
    out = []
    for modifier in item.modifiers:
        markers = [m.strip("{}") for m in
                   [CATEGORY_MARKER.get(modifier.category, "")] if m]
        markers += [name for name, on in modifier.flags.items()
                    if on and not name.startswith("variant:")]
        out.append((tuple(sorted(markers)), modifier.text))
    return out


def audit_variant(document: str, selection: Mapping[str, str],
                  build: BuildSpec, items: Mapping[str, ItemInstance],
                  naming: CatalogNaming) -> AuditResult:
    """Compare a variant's records with its source sets, field by field."""
    root = ET.fromstring(document)
    sets = _selected(root, selection)
    audit = _Audit(build)

    def reverse(table: str, value: Any) -> str | None:
        try:
            return naming.reverse(table, value)
        except UnresolvedName:
            return None

    # Passive allocations: the source node list against the record's union.
    spec = sets.get("Tree")
    if spec is not None:
        source_nodes = sorted(int(n) for n in (spec.get("nodes") or "")
                              .replace(" ", "").split(",") if n)
        record_nodes = sorted(
            naming.node_ids[p] for p in list(build.passives.allocated)
            + list(build.passives.ascendancy_allocated)
            + [n for ws in build.weapon_sets for n in ws.passive_allocations]
            if p in naming.node_ids)
        audit.check("allocations", "/passives/allocated", source_nodes,
                    sorted(set(record_nodes)))
        for child in spec:
            if child.tag.startswith("WeaponSet"):
                number = int(child.tag[len("WeaponSet"):])
                set_id = reverse("weapon_set_numbers", number)
                source = sorted(int(n) for n in (child.get("nodes") or "")
                                .replace(" ", "").split(",") if n)
                record = next((sorted(naming.node_ids[p]
                                      for p in ws.passive_allocations
                                      if p in naming.node_ids)
                               for ws in build.weapon_sets
                               if ws.set_id == set_id), [])
                audit.check("set_bindings", "/weapon_sets/%s" % set_id,
                            source, record)

    # Equipment: slot to item, then each item's modifier lines.
    item_set = sets.get("Items")
    item_text = {node.get("id"): node.text or ""
                 for node in root.findall("Items/Item")}
    if item_set is not None:
        for slot in item_set.findall("Slot"):
            slot_id = reverse("slot_names", slot.get("name", ""))
            path = "/equipment/%s" % slot_id
            source_text = item_text.get(slot.get("itemId", "0"))
            content = build.equipment.get(slot_id) if slot_id else None
            audit.check("set_bindings", path, source_text is not None,
                        content is not None)
            if source_text is None or content is None:
                continue
            item = items.get(content.item_hash)
            source_lines = [_line_key(l) for l in _item_lines(source_text)]
            record_lines = [] if item is None else _record_lines(item)
            for index in range(max(len(source_lines), len(record_lines))):
                audit.check(
                    "gear_rolls", "%s/modifiers/%d" % (path, index),
                    source_lines[index] if index < len(source_lines) else None,
                    record_lines[index] if index < len(record_lines) else None)

    def gem_id(gem: ET.Element) -> str | None:
        if gem.get("gemId") is None:
            return None
        try:
            return naming.reverse_gem(gem.get("gemId"), gem.get("variantId"))
        except UnresolvedName:
            return None

    # Skills: every gem, in order, against skills and their supports.
    # Groups PoB generates from gear, the tree or a mechanic are not part of
    # the record by design (``builddoc._import_skills``); the author's
    # groups are compared in order.
    skill_set = sets.get("Skills")
    every = [] if skill_set is None else skill_set.findall("Skill")
    groups = [g for g in every if not g.get("source")]

    # The main group, as PoB reads it: one-based over every group in the
    # document. A generated or missing group has no author position.
    build_element = root.find("Build")
    if every and build_element is not None:
        number = _int(build_element.get("mainSkillIndex")
                      or build_element.get("mainSocketGroup") or "1")
        target = (every[number - 1]
                  if number is not None and 1 <= number <= len(every)
                  else None)
        source_main = next((gi for gi, g in enumerate(groups)
                            if g is target), None)
        record_main = (None if build.main_skill_group is ABSENT
                       else build.main_skill_group)
        audit.check("skills_and_supports", "/main_skill_group", source_main,
                    record_main)
    for gi, group in enumerate(groups):
        record_group = (build.skill_groups[gi]
                        if gi < len(build.skill_groups) else None)
        path = "/skill_groups/%d" % gi
        set1 = group.get("set1", "true") == "true"
        set2 = group.get("set2", "true") == "true"
        source_set = (None if set1 == set2
                      else reverse("weapon_set_numbers", 1 if set1 else 2))
        audit.check("set_bindings", path + "/weapon_set_id", source_set,
                    None if record_group is None
                    else record_group.weapon_set_id)
        source_slot = (None if not group.get("slot")
                       else reverse("slot_names", group.get("slot")))
        audit.check("set_bindings", path + "/slot_id", source_slot,
                    None if record_group is None else record_group.slot_id)
        audit.check("skills_and_supports", path + "/enabled",
                    group.get("enabled", "false") == "true",
                    None if record_group is None else record_group.enabled)
        main_number = _int(group.get("mainActiveSkill"))
        audit.check("skills_and_supports", path + "/main_skill_index",
                    None if main_number is None else main_number - 1,
                    None if record_group is None
                    else record_group.main_skill_index)
        source_gems = []
        for gem in group.findall("Gem"):
            skill_id = reverse("skill_ids", gem.get("skillId", ""))
            source_gems.append((skill_id, gem_id(gem), _int(gem.get("level")),
                                _int(gem.get("quality")),
                                gem.get("enabled", "true") == "true"))
        record_gems = []
        if record_group is not None:
            for skill in record_group.skills:
                record_gems.append((skill.skill_id, skill.gem_id, skill.level,
                                    skill.quality, skill.enabled))
                supports = ([] if skill.supports is ABSENT
                            else list(skill.supports))
                for k, support_id in enumerate(skill.support_ids):
                    s = supports[k] if k < len(supports) else None
                    record_gems.append((support_id,
                                        None if s is None else s.gem_id,
                                        None if s is None else s.level,
                                        None if s is None else s.quality,
                                        None if s is None else s.enabled))
        for index in range(max(len(source_gems), len(record_gems))):
            audit.check(
                "skills_and_supports", "%s/gems/%d" % (path, index),
                source_gems[index] if index < len(source_gems) else None,
                record_gems[index] if index < len(record_gems) else None)

    return AuditResult(variant_id=build.variant_id,
                       compared=dict(audit.compared),
                       agreed=dict(audit.agreed),
                       mismatches=tuple(audit.mismatches))


def _int(text: str | None) -> int | None:
    try:
        return None if text is None else int(text)
    except ValueError:
        return None


def audit_summary(results: Sequence[AuditResult]) -> dict[str, Any]:
    """Field-level exact agreement per domain across audited variants."""
    compared: dict[str, int] = {}
    agreed: dict[str, int] = {}
    for result in results:
        for domain, count in result.compared.items():
            compared[domain] = compared.get(domain, 0) + count
        for domain, count in result.agreed.items():
            agreed[domain] = agreed.get(domain, 0) + count
    return {
        "variants": len(results),
        "passed": sum(1 for r in results if r.passed),
        "agreement": {d: {"compared": compared[d], "agreed": agreed.get(d, 0),
                          "exact": agreed.get(d, 0) / compared[d]}
                      for d in sorted(compared)},
        "undeclared_mismatches": [
            dict(m.__dict__, variant_id=r.variant_id)
            for r in results for m in r.mismatches if not m.declared_partial],
    }
