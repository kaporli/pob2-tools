"""The gaps the validator raises itself (P02-T03).

P02-T02 recorded the rules upstream does not carry. These are the ones the
*validator* runs into: an input it was not given, or a catalog field that was
never exported. Each one is declared once, with the measurement that would
close it, so an unknown verdict always points at a specific collection task
rather than at "needs more data".

Nothing here fills a rule in. A gap is the honest answer when a check cannot
be decided, and `report.ReportBuilder.unknown` refuses an unknown that cites
none.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable, Sequence

from ...domain.enums import GapKind, GapSeverity, GapStatus
from ...domain.records import SCHEMA_VERSION, DataGap

GAP_PREFIX = "gap/p02-t03"

#: Gaps P02-T02 recorded that this validator cites rather than raises. Named
#: here so a reader can see which unknowns belong to the catalog export.
T02_SLOT_CATEGORIES = "gap/p02-t02/slot-accepted-base-categories"
T02_QUEST_PASSIVE_POINTS = "gap/p02-t02/quest-passive-point-rewards"
T02_ASCENDANCY_SCHEDULE = "gap/p02-t02/ascendancy-point-unlock-schedule"
T02_WEAPON_SET_UNLOCK = "gap/p02-t02/weapon-set-point-unlock-levels"
T02_GEM_LEVEL_LEGALITY = "gap/p02-t02/gem-level-legality"
T02_SKILL_LEVEL_LIMIT = "gap/p02-t02/skill-level-limit"


@dataclass(frozen=True, slots=True)
class GapTemplate:
    gap_id: str
    kind: GapKind
    severity: GapSeverity
    explanation: str
    needed_evidence: str
    collection_method: str


#: Every gap this validator can raise. One entry, one undecidable question.
TEMPLATES: dict[str, GapTemplate] = {
    template.gap_id: template
    for template in (
        GapTemplate(
            gap_id="%s/attribute-choice-options" % GAP_PREFIX,
            kind=GapKind.MISSING_INPUT,
            severity=GapSeverity.RANKING_SENSITIVE,
            explanation=(
                "The exported passive node rows carry no attribute flag and no "
                "option list, so the set of choices a node offers is not in the "
                "catalog. Whether a chosen option is one of that node's options "
                "cannot be decided from this profile. Upstream does carry it: "
                "the node has isAttribute and an options table."),
            needed_evidence=(
                "for each passive node that offers a choice in the resolved "
                "patch, the node id and the identifier of every option it "
                "offers, read from the engine's own node data (node.isAttribute "
                "and the keys of node.options) and exported into the catalog's "
                "passive_nodes rows"),
            collection_method="engine implementation"),
        GapTemplate(
            gap_id="%s/character-attribute-totals" % GAP_PREFIX,
            kind=GapKind.MISSING_INPUT,
            severity=GapSeverity.RANKING_SENSITIVE,
            explanation=(
                "An item's attribute requirement is compared against the "
                "character's totals, which come from the class base, the "
                "allocated tree and every equipped item at once. No measurement "
                "of those totals was supplied, so the comparison was not made. "
                "The item's level requirement is a separate check and was."),
            needed_evidence=(
                "the character's Strength, Dexterity and Intelligence totals "
                "for this exact build, read from the pinned engine after an "
                "exact import of this build document"),
            collection_method="engine implementation"),
        GapTemplate(
            gap_id="%s/reservation-measurement" % GAP_PREFIX,
            kind=GapKind.MISSING_INPUT,
            severity=GapSeverity.RANKING_SENSITIVE,
            explanation=(
                "Whether a build reserves more Spirit, Mana or Life than it has "
                "depends on every reserving skill, its level, its supports and "
                "every reservation modifier on the tree and on gear. Nothing "
                "here recomputes that, and no engine measurement was supplied, "
                "so the resource constraint was not decided."),
            needed_evidence=(
                "the engine's Spirit, SpiritReserved and SpiritUnreserved "
                "outputs, and the same three for Mana and Life, for this exact "
                "build, read from the pinned engine after an exact import. "
                "SpiritUnreserved is the unclamped difference and is the value "
                "that shows over-reservation"),
            collection_method="engine implementation"),
        GapTemplate(
            gap_id="%s/theoretical-item-construction" % GAP_PREFIX,
            kind=GapKind.UNSUPPORTED_RULE,
            severity=GapSeverity.BLOCKING,
            explanation=(
                "The item is not traced to a source document or a listing, so "
                "it is a constructed item. No item-generation legality rules "
                "exist in this profile: which modifiers can appear together on "
                "a base, at which item level, and in which quantity is not "
                "recorded anywhere. Its constructability is therefore "
                "undecidable and cannot be accepted. interfaces.md disables "
                "theoretical mode until those rules exist."),
            needed_evidence=(
                "for the resolved patch, the modifier pool each item base can "
                "roll, the affix count limits by rarity, the item level each "
                "modifier requires and the groups that exclude each other, read "
                "from the engine's own item modifier data and confirmed against "
                "one fixture item per base category"),
            collection_method="engine implementation"),
        GapTemplate(
            gap_id="%s/unverified-import" % GAP_PREFIX,
            kind=GapKind.MISSING_INPUT,
            severity=GapSeverity.BLOCKING,
            explanation=(
                "The build was not loaded into the pinned engine, so the "
                "allocation and equipment this verdict used are the ones the "
                "record claims rather than the ones the engine holds. A "
                "permissive import is not proof of legality, and a record that "
                "was never imported is not proof of anything the engine would "
                "do with it."),
            needed_evidence=(
                "an exact load of this build's own document in the pinned "
                "engine followed by the legality_state read, so the allocated "
                "node ids, the equipped items and the calculated pools come "
                "from the engine rather than from the record"),
            collection_method="engine implementation"),
        GapTemplate(
            gap_id="%s/unresolved-catalog-entity" % GAP_PREFIX,
            kind=GapKind.UNRESOLVED_ENTITY,
            severity=GapSeverity.BLOCKING,
            explanation=(
                "The build refers to entities this catalog does not carry. A "
                "reference the catalog cannot resolve is not thereby illegal: "
                "the catalog may be incomplete for this patch. It is also not "
                "legal. The checks that needed those entities are undecided."),
            needed_evidence=(
                "a catalog export from the engine the build was authored "
                "against, containing the entity ids listed in this gap's "
                "subject_ids, or the confirmation that those ids do not exist "
                "in the resolved patch"),
            collection_method="source lookup"),
        GapTemplate(
            gap_id="%s/duplicate-support-rule" % GAP_PREFIX,
            kind=GapKind.UNSUPPORTED_RULE,
            severity=GapSeverity.RANKING_SENSITIVE,
            explanation=(
                "A socket group lists the same support twice. The profile's "
                "support restriction carries a maximum count and nothing about "
                "repetition, so whether one skill may be supported twice by the "
                "same support is not a rule this profile has."),
            needed_evidence=(
                "whether the resolved patch permits the same support gem twice "
                "in one socket group, from the official patch notes or the "
                "in-game skill screen"),
            collection_method="source lookup"),
        GapTemplate(
            gap_id="%s/item-granted-skill-resolution" % GAP_PREFIX,
            kind=GapKind.MISSING_INPUT,
            severity=GapSeverity.RANKING_SENSITIVE,
            explanation=(
                "A socket group names an equipped item as its source, but none "
                "of that item's modifiers resolves to a granted skill, so "
                "whether the item actually grants that skill is undecided. The "
                "item is equipped; that much was checked."),
            needed_evidence=(
                "the resolved granted-skill effect ids for the modifiers of the "
                "named item, produced by the item parser that owns "
                "ItemModifier.resolved_effect_ids"),
            collection_method="parser implementation"),
        GapTemplate(
            gap_id="%s/catalog-not-supplied" % GAP_PREFIX,
            kind=GapKind.MISSING_INPUT,
            severity=GapSeverity.BLOCKING,
            explanation=(
                "No GameCatalog was supplied, so nothing could be looked up: "
                "not a class, not a passive node, not a gem and not an item "
                "base. The checks that need the catalog did not run. A profile "
                "without its catalog decides membership and connectivity for "
                "nothing."),
            needed_evidence=(
                "the GameCatalog whose catalog_hash the patch profile pins, "
                "produced by `pob2opt catalog export` against the pinned "
                "engine"),
            collection_method="engine implementation"),
        GapTemplate(
            gap_id="%s/missing-point-budget-rule" % GAP_PREFIX,
            kind=GapKind.MISSING_INPUT,
            severity=GapSeverity.BLOCKING,
            explanation=(
                "The profile carries no point budget rule for what this check "
                "needed, so the number of points available was not derived. An "
                "absent budget is not an unlimited one."),
            needed_evidence=(
                "the point budget rule the message names, as a PointBudgetRule "
                "with explicit progression flags and its own evidence, added to "
                "the patch profile's character rules"),
            collection_method="source lookup"),
        GapTemplate(
            gap_id="%s/unresolved-item-modifier" % GAP_PREFIX,
            kind=GapKind.UNRESOLVED_ENTITY,
            severity=GapSeverity.RANKING_SENSITIVE,
            explanation=(
                "An equipped item carries modifiers the parser could not "
                "resolve or found ambiguous, or the item record itself is "
                "partial. What the item actually does is therefore not fully "
                "known, and neither is whether it is a legal item."),
            needed_evidence=(
                "a resolved parse of the named item's modifier lines against "
                "the pinned catalog's item_modifiers table, or the statement "
                "that those lines do not exist in the resolved patch"),
            collection_method="parser implementation"),
        GapTemplate(
            gap_id="%s/item-record-not-supplied" % GAP_PREFIX,
            kind=GapKind.MISSING_INPUT,
            severity=GapSeverity.BLOCKING,
            explanation=(
                "The build equips an item whose ItemInstance record was not "
                "supplied, so its requirements, its modifiers, its sockets and "
                "its provenance are all unavailable. An item nobody can read "
                "is not an item that passed a check."),
            needed_evidence=(
                "the ItemInstance records for the item hashes listed in this "
                "gap's subject_ids, from the corpus the build was resolved "
                "against"),
            collection_method="import request"),
        GapTemplate(
            gap_id="%s/missing-support-restriction" % GAP_PREFIX,
            kind=GapKind.MISSING_INPUT,
            severity=GapSeverity.RANKING_SENSITIVE,
            explanation=(
                "The build uses supports and the profile carries no support "
                "restriction, so the number allowed in one socket group is not "
                "a rule this profile has."),
            needed_evidence=(
                "the maximum number of support gems one skill may be supported "
                "by in the resolved patch, from the official patch notes or the "
                "in-game skill screen"),
            collection_method="source lookup"),
        GapTemplate(
            gap_id="%s/missing-weapon-set-rules" % GAP_PREFIX,
            kind=GapKind.MISSING_INPUT,
            severity=GapSeverity.BLOCKING,
            explanation=(
                "The build declares weapon sets and the profile declares none, "
                "so which sets exist, how many hands each has and whether "
                "swapping is allowed are all unknown. An empty set list is not "
                "a statement that weapon sets do not exist."),
            needed_evidence=(
                "the number of weapon sets a character has in the resolved "
                "patch, the hand slots belonging to each, and whether swapping "
                "between them is unrestricted, from the official patch notes"),
            collection_method="source lookup"),
    )
}


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def raise_gap(gap_id: str, *, created_at: str,
              provenance_ids: Sequence[str],
              subject_ids: Sequence[str] = (),
              references: Sequence[str] = (),
              field_paths: Sequence[str] = (),
              explanation_suffix: str = "") -> DataGap:
    """Build one ``DataGap`` from its template.

    ``subject_ids`` are the records this gap is about, and they have to
    resolve in whatever corpus the gap is stored in: contracts.md requires
    every cross-record reference to resolve. The identifiers the validator
    could *not* resolve are exactly the ones that would not, so they go in
    ``references`` and are named in the explanation as text. The report's own
    findings carry them as fields; the persisted record does not pretend they
    are resolvable references.
    """
    try:
        template = TEMPLATES[gap_id]
    except KeyError:
        raise LookupError("no gap template %r" % gap_id) from None
    explanation = template.explanation
    if references:
        explanation = "%s Ran into: %s." % (explanation, ", ".join(references))
    if explanation_suffix:
        explanation = "%s %s" % (explanation, explanation_suffix)
    return DataGap(
        schema_version=SCHEMA_VERSION,
        record_id=template.gap_id,
        created_at=created_at,
        provenance_ids=list(provenance_ids),
        gap_id=template.gap_id,
        kind=template.kind,
        subject_ids=list(subject_ids),
        field_paths=list(field_paths),
        mechanic_ids=[],
        severity=template.severity,
        explanation=explanation,
        needed_evidence=template.needed_evidence,
        collection_method=template.collection_method,
        affected_evaluation_ids=[],
        sensitivity_result_id=None,
        status=GapStatus.OPEN,
        resolution_evidence_ids=[])


class GapFactory:
    """Raises each gap at most once per report, accumulating what it hit.

    ``subject_ids`` is fixed for the whole report: the build and the profile
    this validation was about, which are the two records a stored gap can
    always resolve against.
    """

    def __init__(self, *, provenance_ids: Sequence[str],
                 subject_ids: Sequence[str] = (),
                 clock: Callable[[], str] = utc_now) -> None:
        self.provenance_ids = list(provenance_ids)
        self.subject_ids = list(subject_ids)
        self.clock = clock
        self._created_at = clock()
        self._references: dict[str, list[str]] = {}
        self._paths: dict[str, list[str]] = {}

    def gap(self, gap_id: str, *, references: Sequence[str] = (),
            field_paths: Sequence[str] = (),
            explanation_suffix: str = "") -> DataGap:
        seen = self._references.setdefault(gap_id, [])
        paths = self._paths.setdefault(gap_id, [])
        for reference in references:
            if reference not in seen:
                seen.append(reference)
        for path in field_paths:
            if path not in paths:
                paths.append(path)
        return raise_gap(gap_id, created_at=self._created_at,
                         provenance_ids=self.provenance_ids,
                         subject_ids=tuple(self.subject_ids),
                         references=tuple(seen), field_paths=tuple(paths),
                         explanation_suffix=explanation_suffix)
