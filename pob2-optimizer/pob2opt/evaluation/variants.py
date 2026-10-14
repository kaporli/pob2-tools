"""Split one PoB document into its build variants (P04-T01, P02-T05 follow-up).

A PoB document can hold several tree specs, skill sets, item sets and config
sets. ``import_build`` reads only the active selection and reports every other
set as a loss. This module turns the document into one BuildSpec per variant
instead, and never combines sets the document does not link.

A variant is one of:

* the **active selection**: the sets the document's own selectors pick, which
  is exactly what PoB evaluates when it opens the file;
* a **loadout**, linked by the rule the pinned PoB uses for its loadout list
  (``buildMode:SyncLoadouts`` in ``src/Modules/Build.lua``). A tree spec
  titled ``Name {id}`` links the item, skill and config sets whose titles
  carry the same ``{id}``; a spec without braces links sets with exactly its
  title. A tab with a single set links to every spec. A title naming two sets
  in one tab is ambiguous and links nothing.

Deviation from PoB: PoB prefixes a spec's title with its tree version when
the version is not the latest one, which then rarely matches a set title.
The latest tree version is not part of a document, so titles are compared
without that prefix here. The difference can only add a loadout PoB would not
list; the linked sets are still the author's own.

A set that belongs to no variant is never merged into one. It is reported on
the split as ``unlinked``, so a leveling tree is never paired with endgame gear
because both sit in one file.

Each variant's BuildSpec keeps the original document as its raw blob, so all
variants of one guide share the same source evidence, and ``variant_id``
names the selected sets.
"""

from __future__ import annotations

import copy
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, replace
from typing import Mapping, Sequence

from ..domain.identity import build_hash, document_hash
from ..domain.records import ItemInstance
from .builddoc import BuildImport, import_build
from .naming import CatalogNaming
from .support import PARTIAL, LossCollector, SupportReport

#: (container tag, set tag, active selector). Tree specs are selected by
#: one-based position, the others by ``id``, as the upstream loaders do.
SET_TABLES = (
    ("Tree", "Spec", "activeSpec"),
    ("Skills", "SkillSet", "activeSkillSet"),
    ("Items", "ItemSet", "activeItemSet"),
    ("Config", "ConfigSet", "activeConfigSet"),
)

_LINK = re.compile(r"\{([A-Za-z0-9,]+)\}")


@dataclass(frozen=True)
class SetRef:
    """One set in the document: its tab, selector key and title."""

    tag: str
    key: str
    title: str

    @property
    def link_ids(self) -> tuple[str, ...]:
        match = _LINK.search(self.title)
        return tuple(part for part in match.group(1).split(",") if part) \
            if match else ()

    @property
    def plain_title(self) -> str:
        stripped = _LINK.sub("", self.title).strip()
        return stripped or "Default"


@dataclass(frozen=True)
class BuildVariant:
    variant_id: str
    #: Loadout name, or ``active`` for the document's own selection.
    label: str
    #: Container tag to the selected set key (spec position or set id).
    selection: Mapping[str, str]
    is_active: bool
    imported: BuildImport


@dataclass(frozen=True)
class VariantSplit:
    """Every variant of one document and the sets no variant uses."""

    source_document: str
    source_hash: str
    variants: tuple[BuildVariant, ...]
    #: Sets outside every variant and ambiguous links, kept with their XML.
    unlinked: SupportReport

    @property
    def active(self) -> BuildVariant | None:
        return next((v for v in self.variants if v.is_active), None)


def _sets(root: ET.Element) -> dict[str, list[tuple[SetRef, ET.Element]]]:
    out: dict[str, list[tuple[SetRef, ET.Element]]] = {}
    for tag, child_tag, _ in SET_TABLES:
        container = root.find(tag)
        if container is None:
            continue
        children = container.findall(child_tag)
        if not children:
            continue  # a legacy flat container is its own single set
        refs = []
        for index, node in enumerate(children, 1):
            key = str(index) if tag == "Tree" else node.get("id", "")
            refs.append((SetRef(tag, key, node.get("title") or "Default"), node))
        out[tag] = refs
    return out


def _active_selection(root: ET.Element,
                      sets: Mapping[str, Sequence[tuple[SetRef, ET.Element]]]
                      ) -> dict[str, str] | None:
    selection: dict[str, str] = {}
    for tag, _, selector in SET_TABLES:
        if tag not in sets:
            continue
        wanted = root.find(tag).get(selector, "1")
        matches = [ref.key for ref, _ in sets[tag] if ref.key == wanted]
        if len(matches) != 1:
            return None
        selection[tag] = matches[0]
    return selection


def _loadouts(sets: Mapping[str, Sequence[tuple[SetRef, ET.Element]]],
              losses: LossCollector) -> list[tuple[str, dict[str, str]]]:
    """PoB's loadout rule; ambiguous links are reported, never chosen."""
    specs = [ref for ref, _ in sets.get("Tree", ())]
    others = [tag for tag, _, _ in SET_TABLES[1:] if tag in sets]
    if not specs:
        return []
    found: list[tuple[str, dict[str, str]]] = []
    for spec in specs:
        if spec.link_ids:
            keys = [(link, "%s {%s}" % (spec.plain_title, link))
                    for link in spec.link_ids]
        else:
            keys = [(None, spec.title)]
        for link, label in keys:
            selection = {"Tree": spec.key}
            for tag in others:
                refs = [ref for ref, _ in sets[tag]]
                if len(refs) == 1:
                    selection[tag] = refs[0].key
                    continue
                if link is not None:
                    matches = [r for r in refs if link in r.link_ids]
                else:
                    matches = [r for r in refs
                               if not r.link_ids and r.title == spec.title]
                if len(matches) == 1:
                    selection[tag] = matches[0].key
                elif len(matches) > 1:
                    losses.add("/%s" % tag, PARTIAL,
                               "loadout %r matches %d %s sets; the link is "
                               "ambiguous and no variant is formed"
                               % (label, len(matches), tag),
                               [r.key for r in matches], True)
                    break
                else:
                    break
            else:
                found.append((label, selection))
    return found


def _reduced_document(root: ET.Element, selection: Mapping[str, str]) -> str:
    """The document with only the selected sets, each one made active."""
    reduced = copy.deepcopy(root)
    for tag, child_tag, selector in SET_TABLES:
        container = reduced.find(tag)
        if container is None or tag not in selection:
            continue
        children = container.findall(child_tag)
        for index, node in enumerate(children, 1):
            key = str(index) if tag == "Tree" else node.get("id", "")
            if key != selection[tag]:
                container.remove(node)
        container.set(selector, "1" if tag == "Tree" else selection[tag])
    return ET.tostring(reduced, encoding="unicode")


def _variant_id(source_hash: str, selection: Mapping[str, str]) -> str:
    parts = ["%s=%s" % (tag, selection[tag]) for tag, _, _ in SET_TABLES
             if tag in selection]
    return "pob-variant/%s/%s" % (source_hash[:16], ";".join(parts))


def _used_items(imported: BuildImport) -> dict[str, ItemInstance]:
    wanted = {slot.item_hash for slot in imported.build.equipment.values()
              if slot is not None}
    wanted |= {s.entity_id for s in imported.build.passives.socketed}
    return {key: item for key, item in imported.items.items() if key in wanted}


def split_variants(document: str, naming: CatalogNaming, *, record_id: str,
                   created_at: str, catalog_hash: str,
                   provenance_ids: Sequence[str] = (),
                   source_document_ids: Sequence[str] = ()) -> VariantSplit:
    """One BuildImport per variant of ``document``; unlinked sets reported.

    Record IDs are ``<record_id>/<n>`` in variant order: the active selection
    first, then loadouts in document order. A loadout equal to the active
    selection is the same variant and appears once, labelled with its name.
    """
    root = ET.fromstring(document)
    source_hash = document_hash(document.encode("utf-8"))
    sets = _sets(root)
    losses = LossCollector()

    active = _active_selection(root, sets)
    candidates: list[tuple[str, dict[str, str], bool]] = []
    if active is not None:
        candidates.append(("active", active, True))
    for label, selection in _loadouts(sets, losses):
        if active is not None and selection == active:
            candidates[0] = (label, active, True)
            continue
        if any(selection == known for _, known, _ in candidates):
            continue
        candidates.append((label, selection, False))
    if active is None and sets:
        losses.add("/", PARTIAL,
                   "the document's active selectors do not each name one set, "
                   "so PoB's own selection cannot be reproduced", None, True)

    variants: list[BuildVariant] = []
    for index, (label, selection, is_active) in enumerate(candidates):
        reduced = _reduced_document(root, selection)
        imported = import_build(reduced, naming,
                                record_id="%s/%d" % (record_id, index),
                                created_at=created_at,
                                catalog_hash=catalog_hash,
                                provenance_ids=provenance_ids)
        variant_id = _variant_id(source_hash, selection)
        build = replace(imported.build, variant_id=variant_id,
                        raw_blob_hashes=[source_hash],
                        source_document_ids=list(source_document_ids))
        build = replace(build, build_hash=build_hash(build))
        imported = BuildImport(build=build, items=_used_items(imported),
                               report=imported.report,
                               source_document=document)
        variants.append(BuildVariant(variant_id=variant_id, label=label,
                                     selection=dict(selection),
                                     is_active=is_active, imported=imported))

    used = {(tag, selection[tag]) for _, selection, _ in candidates
            for tag in selection}
    for tag, refs in sets.items():
        for ref, node in refs:
            if (tag, ref.key) not in used:
                losses.add("/%s/%s" % (tag, node.tag), PARTIAL,
                           "set %r belongs to no variant: no loadout links "
                           "it and the document does not select it"
                           % ref.title, ET.tostring(node, encoding="unicode"),
                           False)
    return VariantSplit(source_document=document, source_hash=source_hash,
                        variants=tuple(variants), unlinked=losses.report())
