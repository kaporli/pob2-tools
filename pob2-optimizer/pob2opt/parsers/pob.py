"""PoB documents and sharing codes into BuildSpec records (P04-T01/T03).

One stored source document in, one :class:`ParseOutcome` out: a
``ParseResult``, one ``BuildSpec`` per variant, the items those variants use,
and unverified claims from the document's notes.

What makes a parse complete is narrow on purpose. Every variant must import
with no blocking loss, the document must have its tree, items and skills
sections, and every affix line the catalog can vouch for must match exactly
one catalog modifier. Anything else is ``partial`` with an issue naming the
field. A document that is not a recognizable PoE 2 PoB build is ``invalid``
or ``unsupported_format``, never a complete build with nothing in it.

Catalog modifier matching is reported, not written into the items. PoB item
text cannot carry catalog modifier IDs (P02-T05), so writing them would turn
every export incomplete. Unique, implicit, enchant, rune and crafted lines are
not in the catalog's affix table; they are counted as unchecked rather than
called unresolved.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from dataclasses import dataclass, replace
from typing import Any, Mapping, Sequence

from ..domain.enums import (ModifierCategory, ParseResultStatus,
                            RecordParseStatus)
from ..domain.identity import build_hash, item_hash
from ..domain.records import (SCHEMA_VERSION, BuildSpec, CatalogEntity,
                              CoverageCount, ItemInstance, MechanicClaim,
                              ParseIssue, ParseResult, SourceDocument,
                              UnresolvedRef)
from ..domain.validation import validate_record
from ..evaluation.naming import CatalogNaming, UnresolvedName
from ..evaluation.support import NOT_REPRESENTABLE, UnsupportedField
from ..evaluation.variants import VariantSplit, split_variants
from . import formats
from .claims import extract_claims
from .resolve import (TEMPLATE_CLAIM, class_for_document_name, item_readiness,
                      naming_from_catalog, resolve_item_modifiers)

PARSER_ID = "pob2opt.parsers.pob"
PARSER_VERSION = "p04-t01.1"

#: Elements a PoE 2 PoB document is known to contain. Others are kept in
#: ``raw_extensions`` and named there.
KNOWN_ELEMENTS = frozenset({"Build", "Import", "Calcs", "Skills", "Tree",
                            "Items", "Config", "Notes", "TreeView",
                            "Party", "PartyMembers"})

#: Item modifier categories drawn from the affix pool the catalog exports.
AFFIX_CATEGORIES = (ModifierCategory.EXPLICIT, ModifierCategory.FRACTURED,
                    ModifierCategory.DESECRATED)
AFFIX_RARITIES = ("magic", "rare")


@dataclass(frozen=True)
class ParseContext:
    """Everything a parse depends on besides the bytes."""

    catalog_hash: str
    created_at: str
    #: The catalog's entity tables. Required unless ``naming`` is supplied.
    entities: Mapping[str, Sequence[CatalogEntity]] | None = None
    #: An explicit naming table, for synthetic fixtures.
    naming: CatalogNaming | None = None
    #: The tree version the catalog was exported from; older ones are named.
    current_tree_version: str | None = None


@dataclass(frozen=True)
class ParseOutcome:
    result: ParseResult
    builds: tuple[BuildSpec, ...] = ()
    items: tuple[ItemInstance, ...] = ()
    claims: tuple[MechanicClaim, ...] = ()
    split: VariantSplit | None = None

    @property
    def records(self) -> list[Any]:
        return [*self.items, *self.builds, *self.claims, self.result]


class _Issues:
    def __init__(self) -> None:
        self.items: list[ParseIssue] = []

    def add(self, code: str, field_path: str, locator: str,
            explanation: str) -> None:
        issue = ParseIssue(code=code, field_path=field_path or "/",
                           source_locator=locator or "document",
                           explanation=explanation)
        if issue not in self.items:
            self.items.append(issue)


def _result(document: SourceDocument, context: ParseContext,
            status: ParseResultStatus, issues: Sequence[ParseIssue],
            coverage: Sequence[CoverageCount] = (),
            record_ids: Sequence[str] = (),
            extensions: Mapping[str, Any] | None = None) -> ParseResult:
    return ParseResult(
        schema_version=SCHEMA_VERSION,
        record_id="%s/parse/%s" % (document.record_id, PARSER_VERSION),
        created_at=context.created_at, provenance_ids=[document.record_id],
        status=status, parser_id=PARSER_ID, parser_version=PARSER_VERSION,
        source_document_id=document.record_id, record_ids=list(record_ids),
        field_coverage=list(coverage), issues=list(issues),
        raw_extensions=dict(extensions or {}))


def refused(document: SourceDocument, context: ParseContext,
            detected: formats.Detected) -> ParseOutcome:
    """A payload no parser accepts, as a ParseResult with its reason."""
    unsupported = detected.reason in ("pob1_document", "unknown_format",
                                      "unknown_declared_format",
                                      "declared_format_mismatch")
    status = (ParseResultStatus.UNSUPPORTED_FORMAT if unsupported
              else ParseResultStatus.INVALID)
    issue = ParseIssue(code=detected.reason, field_path="/",
                       source_locator="payload",
                       explanation=detected.detail or detected.reason)
    return ParseOutcome(_result(document, context, status, [issue],
                                extensions={"format": detected.format}))


def parse_pob(document: SourceDocument, payload: bytes,
              context: ParseContext) -> ParseOutcome:
    """Parse a stored PoB XML document or sharing code."""
    detected = formats.detect(payload)
    if detected.refused or detected.format not in (formats.POB_XML,
                                                   formats.POB_CODE):
        if not detected.refused:
            detected = formats.Detected(
                detected.format, True, "unsupported_format",
                "%s is not a PoB document" % detected.format)
        return refused(document, context, detected)
    return parse_pob_xml(document, detected.xml or "", context,
                         source_format=detected.format)


def _naming(root: ET.Element, context: ParseContext,
            issues: _Issues) -> CatalogNaming:
    if context.naming is not None:
        return context.naming
    if context.entities is None:
        raise ValueError("ParseContext needs entities or naming")
    build = root.find("Build")
    class_name = "" if build is None else build.get("className", "")
    class_id = class_for_document_name(context.entities, class_name)
    report = naming_from_catalog(context.entities, class_id=class_id)
    for entry in report.ambiguous:
        issues.add("ambiguous_catalog_name", "/catalog/%s" % entry["table"],
                   "catalog", "PoB value %r names %d catalog entities (%s); "
                   "references to it stay unresolved"
                   % (entry["value"], len(entry["candidates"]),
                      ", ".join(entry["candidates"])))
    return report.naming


def parse_pob_xml(document: SourceDocument, xml: str, context: ParseContext,
                  *, source_format: str = formats.POB_XML) -> ParseOutcome:
    issues = _Issues()
    try:
        root = ET.fromstring(xml)
    except ET.ParseError as error:
        return ParseOutcome(_result(document, context,
                                    ParseResultStatus.INVALID,
                                    [ParseIssue("xml_syntax", "/", "payload",
                                                str(error))]))
    if root.tag != formats.POB2_ROOT or root.find("Build") is None:
        return ParseOutcome(_result(
            document, context, ParseResultStatus.INVALID,
            [ParseIssue("layout_unrecognized", "/Build", "payload",
                        "no Build element under %s; this is not a layout the "
                        "parser recognizes, so no build is produced"
                        % formats.POB2_ROOT)]))

    extensions: dict[str, Any] = {"format": source_format}
    unknown = sorted({child.tag for child in root} - KNOWN_ELEMENTS)
    if unknown:
        extensions["unknown_elements"] = {
            tag: [ET.tostring(node, encoding="unicode")
                  for node in root.findall(tag)] for tag in unknown}

    naming = _naming(root, context, issues)
    split = split_variants(
        xml, naming, record_id="%s/build" % document.record_id,
        created_at=context.created_at, catalog_hash=context.catalog_hash,
        provenance_ids=[document.record_id],
        source_document_ids=[document.record_id])

    missing = _missing_sections(root)
    for section, (field_path, reason) in missing.items():
        issues.add("missing_" + section, field_path, "/" + section.title(),
                   reason)
    tree_version = _tree_version(root)
    if tree_version is not None:
        extensions["tree_version"] = tree_version
        if (context.current_tree_version is not None
                and tree_version != context.current_tree_version):
            issues.add("old_tree_version", "/passives", "/Tree/Spec/@treeVersion",
                       "the document's tree version %s is not the catalog's "
                       "%s; its node IDs are checked against the catalog, "
                       "not migrated" % (tree_version,
                                         context.current_tree_version))
    extensions["target_version"] = root.find("Build").get("targetVersion")

    builds: list[BuildSpec] = []
    items: dict[str, ItemInstance] = {}
    unrepresented: list[dict[str, Any]] = []
    for index, variant in enumerate(split.variants):
        prefix = "/variants/%d" % index
        locator = "variant %s (%s)" % (variant.label, variant.variant_id)
        for loss in variant.imported.report.unsupported:
            if _blocking(loss):
                issues.add(loss.kind, prefix + loss.field_path, locator,
                           loss.reason)
            else:
                unrepresented.append({"variant": variant.variant_id,
                                      **loss.as_dict()})
        build = variant.imported.build
        if not build.class_id:
            issues.add("unresolved_class", prefix + "/class_id", locator,
                       "the class does not resolve, and a BuildSpec without "
                       "a class cannot be evaluated; no record is produced "
                       "for this variant")
            continue
        build = _finish_build(build, document, missing)
        report = validate_record(build)
        if not report.ok:
            issues.add("record_invalid", prefix, locator,
                       "; ".join("%s %s" % (e.code, e.field_path)
                                 for e in report.errors))
            continue
        builds.append(build)
        for item in variant.imported.items.values():
            items.setdefault(item.item_hash, _finish_item(item, document))

    for loss in split.unlinked.unsupported:
        issues.add("unlinked_variant_set", loss.field_path, "document",
                   loss.reason)
    extensions["unlinked_sets"] = [u.as_dict()
                                   for u in split.unlinked.unsupported]
    if unrepresented:
        extensions["unrepresented"] = unrepresented

    coverage = list(_coverage(root, naming))
    modifier_coverage = _modifier_checks(items.values(), context, issues)
    if modifier_coverage is not None:
        coverage.append(modifier_coverage)
    for item in items.values():
        if item_readiness(item) == TEMPLATE_CLAIM:
            issues.add(TEMPLATE_CLAIM, "/items/%s" % item.item_hash,
                       item.display_name,
                       "an item name without stats is a claim about which "
                       "item is meant, not an item ready for calculation")

    notes = root.find("Notes")
    claims: tuple[MechanicClaim, ...] = ()
    if notes is not None and (notes.text or "").strip():
        extensions["notes"] = notes.text
        claims = extract_claims(notes.text or "", document=document,
                                created_at=context.created_at,
                                entities=context.entities or {},
                                locator_prefix="/Notes")

    status = _status(builds, issues.items)
    for build in builds:
        if build.parse_status is not RecordParseStatus.COMPLETE:
            status = ParseResultStatus.PARTIAL
    if status is ParseResultStatus.COMPLETE and issues.items:
        status = ParseResultStatus.PARTIAL
    record_ids = [b.record_id for b in builds] + [
        i.record_id for i in items.values()] + [c.record_id for c in claims]
    result = _result(document, context, status, issues.items, coverage,
                     record_ids, extensions)
    return ParseOutcome(result=result, builds=tuple(builds),
                        items=tuple(items.values()), claims=claims,
                        split=split)


def _status(builds, issues) -> ParseResultStatus:
    if not builds:
        return ParseResultStatus.INVALID
    return ParseResultStatus.PARTIAL if issues else ParseResultStatus.COMPLETE


def _blocking(loss: UnsupportedField) -> bool:
    return loss.affects_identity or loss.kind != NOT_REPRESENTABLE


def _missing_sections(root: ET.Element) -> dict[str, tuple[str, str]]:
    missing: dict[str, tuple[str, str]] = {}
    if root.find("Tree/Spec") is None:
        missing["tree"] = (
            "/passives", "the source has no passive tree; the allocation is "
            "unknown, which blocks legal evaluation")
    if root.find("Items") is None:
        missing["items"] = (
            "/equipment", "the source has no items section; the equipment is "
            "unknown, not empty")
    if root.find("Skills") is None:
        missing["skills"] = (
            "/skill_groups", "the source has no skills section; the skill "
            "groups are unknown, not empty")
    return missing


def _tree_version(root: ET.Element) -> str | None:
    spec = root.find("Tree/Spec")
    return None if spec is None else spec.get("treeVersion")


def _finish_build(build: BuildSpec, document: SourceDocument,
                  missing: Mapping[str, tuple[str, str]]) -> BuildSpec:
    refs = list(build.unresolved_refs)
    for section, (field_path, reason) in missing.items():
        refs.append(UnresolvedRef(field_path=field_path,
                                  reference=section, reason=reason))
    status = build.parse_status
    if refs:
        status = RecordParseStatus.PARTIAL
    out = replace(build, raw_blob_hashes=[document.blob_hash],
                  declared_patch=document.declared_patch,
                  unresolved_refs=refs, parse_status=status)
    return replace(out, build_hash=build_hash(out))


def _finish_item(item: ItemInstance, document: SourceDocument) -> ItemInstance:
    out = replace(item, source_document_id=document.record_id,
                  provenance_ids=[document.record_id])
    return replace(out, item_hash=item_hash(out))


def _coverage(root: ET.Element, naming: CatalogNaming):
    """Present, resolved and missing references by domain, from the source."""
    def count(domain, refs, missing=0):
        refs = list(refs)
        resolved = sum(1 for ok in refs if ok)
        return CoverageCount(domain=domain, present=len(refs),
                             resolved=resolved,
                             missing=missing + len(refs) - resolved)

    def reverse(table, value) -> bool:
        try:
            naming.reverse(table, value)
            return True
        except UnresolvedName:
            return False

    build = root.find("Build")
    class_name = build.get("className") if build is not None else None
    yield count("class", [reverse("class_names", class_name)]
                if class_name else [], 0 if class_name else 1)
    nodes: list[bool] = []
    for spec in root.findall("Tree/Spec"):
        for part in (spec.get("nodes") or "").replace(" ", "").split(","):
            if part:
                nodes.append(part.isdigit() and reverse("node_ids", int(part)))
    yield count("passives", nodes, 1 if root.find("Tree/Spec") is None else 0)
    item_ids = {node.get("id") for node in root.findall("Items/Item")}
    slots = [reverse("slot_names", slot.get("name", ""))
             and slot.get("itemId") in item_ids
             for slot in root.findall("Items/ItemSet/Slot")
             if slot.get("itemId", "0") != "0"]
    yield count("equipment", slots, 1 if root.find("Items") is None else 0)
    actives: list[bool] = []
    supports: list[bool] = []
    for gem in root.iter("Gem"):
        ok = reverse("skill_ids", gem.get("skillId", ""))
        if ok and naming.reverse("skill_ids", gem.get("skillId", "")) \
                in naming.support_skill_ids:
            supports.append(_settings_stated(gem))
        else:
            actives.append(ok)
    missing_skills = 1 if root.find("Skills") is None else 0
    yield count("skills", actives, missing_skills)
    yield count("supports", supports)
    config = root.find("Config")
    yield count("config", [] if config is None else [
        node.get("name") is not None for node in config.iter("Input")])


def _settings_stated(gem: ET.Element) -> bool:
    return all(gem.get(name) is not None
               for name in ("level", "quality", "enabled"))


def _modifier_checks(items, context: ParseContext,
                     issues: _Issues) -> CoverageCount | None:
    """Affix lines of magic and rare items against the catalog's modifiers."""
    if not context.entities or not context.entities.get("item_modifiers"):
        return None
    present = resolved = 0
    for item in items:
        if item.rarity not in AFFIX_RARITIES:
            continue
        _, matches = resolve_item_modifiers(item, context.entities)
        for match, modifier in zip(matches, item.modifiers):
            if modifier.category not in AFFIX_CATEGORIES:
                continue
            present += 1
            if match.status == "resolved":
                resolved += 1
                continue
            explanation = (
                "affix line matches %d catalog modifiers (%s); no automatic "
                "choice" % (len(match.candidates), ", ".join(match.candidates))
                if match.candidates else
                "affix line matches no catalog modifier of this patch")
            issues.add("%s_affix" % match.status,
                       "/items/%s/modifiers/%d" % (item.item_hash,
                                                   match.source_position),
                       item.display_name + ": " + match.text, explanation)
    return CoverageCount(domain="item_affixes", present=present,
                         resolved=resolved, missing=present - resolved)
