"""Character rules the pinned engine's data actually supports (P02-T02).

Every rule here is read from upstream and carries the citation it came from.
Where upstream has nothing, this module produces a ``DataGap`` naming the
evidence someone has to collect, and leaves the rule out.

Three rules upstream does not carry, recorded as gaps rather than filled in:

* which quests grant ordinary passive skill points. ``data.questRewards``
  grants weapon-set passive points and stat rewards, and nothing else. The
  legacy ``(level - 1) + 8`` constant in ``cli.py`` is not promoted here;
* when each ascendancy point is earned. Upstream carries the maximum, 8, and
  a beginner's labyrinth hint that is a recommendation, not a rule;
* which item base categories each equipment slot accepts. The slot table
  names slots; it does not say what fits in them. Since P02-T03.1 the engine
  is asked instead (``slotrules.py``); a capture without that probe keeps the
  original gap.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

from ..domain.absent import ABSENT
from ..domain.enums import GapKind, GapSeverity, GapStatus
from ..domain.records import (SCHEMA_VERSION, CatalogEntity, CharacterRules,
                              DataGap, LevelRange, OffHandRule,
                              PointBudgetRule, SlotRule, SupportRestriction,
                              WeaponSetRules)
from .entities import entity_id
from .evidence import (EXPORT_ROOT_ID, EvidenceBundle, json_payload,
                       pob_source_url)
from .slotrules import NO_FLAG, SlotAcceptance, read_acceptance
from .sources import Citation

GAP_PREFIX = "gap/p02-t02"
GAP_PREFIX_T031 = "gap/p02-t03.1"


class MissingRuleSource(RuntimeError):
    """A rule the ``CharacterRules`` record requires has no upstream source.

    Raised rather than defaulted: ``level_range`` and the point maximums are
    not nullable, so an export that cannot source them must fail loudly
    instead of shipping a remembered constant.
    """


@dataclass
class RuleBuild:
    rules: CharacterRules
    gaps: list[DataGap] = field(default_factory=list)


def make_gap(gap_id: str, *, kind: GapKind, severity: GapSeverity,
         explanation: str, needed_evidence: str, collection_method: str,
         created_at: str, subject_ids: Sequence[str] = (),
         field_paths: Sequence[str] = (),
         provenance_ids: Sequence[str] = (EXPORT_ROOT_ID,)) -> DataGap:
    return DataGap(
        schema_version=SCHEMA_VERSION,
        record_id=gap_id,
        created_at=created_at,
        provenance_ids=list(provenance_ids),
        gap_id=gap_id,
        kind=kind,
        subject_ids=list(subject_ids),
        field_paths=list(field_paths),
        mechanic_ids=[],
        severity=severity,
        explanation=explanation,
        needed_evidence=needed_evidence,
        collection_method=collection_method,
        affected_evaluation_ids=[],
        sensitivity_result_id=None,
        status=GapStatus.OPEN,
        resolution_evidence_ids=[])


def _cite(bundle: EvidenceBundle, citation: Citation, commit: str | None) -> str:
    return bundle.add(
        "evidence/pob/source/%s" % citation.name,
        citation.payload(),
        provider="path-of-building-poe2",
        source_url=pob_source_url(commit, citation.relative_path, citation.line),
        media_type="text/x-lua")


def _cite_data(bundle: EvidenceBundle, name: str, value: Any,
               commit: str | None) -> str:
    return bundle.add(
        "evidence/pob/data/%s" % name,
        json_payload(value),
        provider="path-of-building-poe2",
        source_url=pob_source_url(commit, "src/Data"),
        media_type="application/json")


def build_character_rules(
        *, rule_sources: Mapping[str, Any],
        classes: Sequence[CatalogEntity],
        ascendancies: Sequence[CatalogEntity],
        slots: Sequence[CatalogEntity],
        gems: Sequence[CatalogEntity],
        citations: Mapping[str, Citation],
        evidence: EvidenceBundle,
        pob_commit: str | None,
        created_at: str) -> RuleBuild:
    """Assemble ``CharacterRules`` and the gaps around them."""
    gaps: list[DataGap] = []
    rule_evidence: list[str] = []

    point_maximums = citations.get("point_maximums")
    level_cap = citations.get("level_cap")
    if point_maximums is None or level_cap is None:
        missing = [name for name, found in
                   (("point_maximums", point_maximums), ("level_cap", level_cap))
                   if found is None]
        raise MissingRuleSource(
            "the pinned checkout no longer matches the patterns for %s; the "
            "level range and point maximums cannot be sourced, so no patch "
            "profile is produced. Update pob2opt/catalog/sources.py against "
            "the new upstream and re-read the numbers."
            % ", ".join(missing))

    maximum_level = level_cap.value(0)
    passive_maximum = point_maximums.value(0)
    ascendancy_maximum = point_maximums.value(1)
    point_evidence = _cite(evidence, point_maximums, pob_commit)
    level_evidence = _cite(evidence, level_cap, pob_commit)
    rule_evidence += [point_evidence, level_evidence]

    # -- classes and ascendancies ----------------------------------------
    by_class: dict[str, list[str]] = {
        entity.entity_id: [] for entity in classes}
    for ascendancy in ascendancies:
        owner = entity_id("classes", ascendancy.raw_reference.get("classId"))
        by_class.setdefault(owner, []).append(ascendancy.entity_id)
    class_ascendancies = {key: sorted(value) for key, value in sorted(by_class.items())}
    class_evidence = _cite_data(
        evidence, "class-ascendancies",
        {key: list(value) for key, value in class_ascendancies.items()},
        pob_commit)
    rule_evidence.append(class_evidence)

    # -- point budgets ----------------------------------------------------
    budgets: list[PointBudgetRule] = []
    for level in range(1, maximum_level + 1):
        budgets.append(PointBudgetRule(
            rule_id="budget/levelling/level-%d" % level,
            level=level,
            # The flag says what this row counts. It excludes quest rewards
            # and ascendancy trials, so the zero below is the flag's meaning
            # and not a claim that a real character has no ascendancy points.
            required_progression_flags=["levelling_points_only"],
            passive_points=level - 1,
            ascendancy_points=0,
            evidence_ids=[point_evidence, level_evidence]))
    budgets.append(PointBudgetRule(
        rule_id="budget/ascendancy/maximum",
        level=maximum_level,
        required_progression_flags=["ascendancy_points_maximum"],
        passive_points=passive_maximum,
        ascendancy_points=ascendancy_maximum,
        evidence_ids=[point_evidence]))

    weapon_set_points = rule_sources.get("maxWeaponSetPoints")
    quest_point_rewards = list(rule_sources.get("questPointRewards") or ())
    if isinstance(weapon_set_points, (int, float)) and quest_point_rewards:
        quest_evidence = _cite_data(evidence, "weapon-set-quest-points",
                                    quest_point_rewards, pob_commit)
        rule_evidence.append(quest_evidence)
        budgets.append(PointBudgetRule(
            rule_id="budget/weapon-set/all-quest-rewards",
            level=maximum_level,
            required_progression_flags=["weapon_set_points",
                                        "all_weapon_set_quest_rewards_taken"],
            passive_points=int(weapon_set_points),
            ascendancy_points=0,
            evidence_ids=[quest_evidence]))
        gaps.append(make_gap(
            "%s/weapon-set-point-unlock-levels" % GAP_PREFIX,
            kind=GapKind.UNSUPPORTED_RULE,
            severity=GapSeverity.INFORMATIONAL,
            explanation=(
                "Upstream records %d weapon-set passive points across %d quest "
                "rewards, each with the level of the area the quest is in. An "
                "area level is not the character level at which the reward is "
                "obtainable, so the budget is exported as a total and not as a "
                "schedule." % (int(weapon_set_points), len(quest_point_rewards))),
            needed_evidence=(
                "for each quest that grants weapon-set passive skill points in "
                "the resolved patch, the quest name, the act and the minimum "
                "character level at which a character can complete it, from the "
                "official patch notes or the in-game quest list"),
            collection_method="source lookup",
            created_at=created_at,
            field_paths=["/character_rules/point_budgets"]))
    else:
        gaps.append(make_gap(
            "%s/weapon-set-point-budget" % GAP_PREFIX,
            kind=GapKind.MISSING_INPUT,
            severity=GapSeverity.RANKING_SENSITIVE,
            explanation=(
                "The engine reported no weapon-set passive point total, so the "
                "weapon-set budget is absent from this profile."),
            needed_evidence=(
                "the total number of weapon-set passive skill points a "
                "character can obtain in the resolved patch, and the quests "
                "that grant them, from the official patch notes"),
            collection_method="source lookup",
            created_at=created_at,
            field_paths=["/character_rules/point_budgets"]))

    gaps.append(make_gap(
        "%s/quest-passive-point-rewards" % GAP_PREFIX,
        kind=GapKind.UNSUPPORTED_RULE,
        severity=GapSeverity.RANKING_SENSITIVE,
        explanation=(
            "No entry in the engine's quest reward data grants ordinary passive "
            "skill points: the point-granting entries all grant weapon-set "
            "passive points. The exported budget therefore counts levelling "
            "points only, and a character's real passive total is higher by an "
            "unknown amount. The legacy pob2opt/cli.py estimate of "
            "(level - 1) + 8 is not sourced from anything and is deliberately "
            "not promoted to a rule here."),
        needed_evidence=(
            "the list of quests granting ordinary passive skill points in the "
            "resolved patch, each with its act, the quest name and the number "
            "of points granted, from the official patch notes or the in-game "
            "quest reward screen"),
        collection_method="source lookup",
        created_at=created_at,
        field_paths=["/character_rules/point_budgets"]))

    gaps.append(make_gap(
        "%s/ascendancy-point-unlock-schedule" % GAP_PREFIX,
        kind=GapKind.UNSUPPORTED_RULE,
        severity=GapSeverity.RANKING_SENSITIVE,
        explanation=(
            "Upstream carries the ascendancy point maximum (%d) but no rule for "
            "when each point is earned. The only progression hint in the engine "
            "is a labyrinth suggestion its own comment calls a recommendation "
            "for beginners. A build below the maximum therefore has no sourced "
            "budget." % ascendancy_maximum),
        needed_evidence=(
            "for the resolved patch, each trial or quest that grants ascendancy "
            "points, the number granted and the minimum character level at "
            "which it can be completed, from the official patch notes"),
        collection_method="source lookup",
        created_at=created_at,
        field_paths=["/character_rules/point_budgets"]))

    # -- slots -------------------------------------------------------------
    acceptance = read_acceptance(rule_sources.get("slotAcceptance"))
    slot_rules, off_hand_rules, slot_gaps, slot_evidence_ids = _slot_rules(
        slots, acceptance, citations, evidence, pob_commit, created_at)
    gaps.extend(slot_gaps)
    rule_evidence.extend(slot_evidence_ids)

    # -- supports ----------------------------------------------------------
    support_restrictions: list[SupportRestriction] = []
    support_citation = citations.get("support_socket_limit")
    if support_citation is not None:
        support_evidence = _cite(evidence, support_citation, pob_commit)
        rule_evidence.append(support_evidence)
        support_restrictions.append(SupportRestriction(
            restriction_id="support/socket-group-limit",
            applies_to=["poe2/skill_groups"],
            max_supports=support_citation.value(0),
            description=(
                "At most %d non-hidden support gems in one socket group. "
                "Upstream warns above this number and still calculates the "
                "build, so this is the engine's declared limit and not proof "
                "that the game rejects a sixth support."
                % support_citation.value(0)),
            evidence_ids=[support_evidence]))
    else:
        gaps.append(make_gap(
            "%s/support-socket-limit" % GAP_PREFIX,
            kind=GapKind.MISSING_INPUT,
            severity=GapSeverity.RANKING_SENSITIVE,
            explanation=(
                "The pinned pattern for the engine's support socket limit no "
                "longer matches, so no support restriction was exported."),
            needed_evidence=(
                "the maximum number of support gems a single skill may be "
                "supported by in the resolved patch, from the official patch "
                "notes or the in-game skill screen"),
            collection_method="source lookup",
            created_at=created_at,
            field_paths=["/character_rules/support_restrictions"]))

    # -- weapon sets -------------------------------------------------------
    constants = dict(rule_sources.get("characterConstants") or {})
    set_count = constants.get("base_number_of_weapon_sets")
    hands: dict[str, int] = {}
    for slot in slots:
        weapon_set = slot.raw_reference.get("weaponSet")
        if weapon_set is None:
            continue
        name = str(slot.raw_reference.get("slotName") or "")
        if not name.startswith("Weapon ") or "Jewel" in name:
            continue
        key = entity_id("weapon_sets", weapon_set)
        hands[key] = hands.get(key, 0) + 1
    if isinstance(set_count, (int, float)) and int(set_count) > 0:
        weapon_set_evidence = _cite_data(
            evidence, "weapon-set-constants",
            {"base_number_of_weapon_sets": set_count,
             "enable_weapon_sets": constants.get("enable_weapon_sets"),
             "base_weapon_swap_duration_ms":
                 constants.get("base_weapon_swap_duration_ms"),
             "hands_per_set": dict(sorted(hands.items()))},
            pob_commit)
        rule_evidence.append(weapon_set_evidence)
        set_ids = [entity_id("weapon_sets", index)
                   for index in range(1, int(set_count) + 1)]
        for key in set_ids:
            hands.setdefault(key, 0)
        weapon_sets = WeaponSetRules(
            set_ids=set_ids,
            hands_per_set={key: hands[key] for key in sorted(hands)},
            swap_allowed=bool(constants.get("enable_weapon_sets")),
            evidence_ids=[weapon_set_evidence],
            off_hand_rules=off_hand_rules if acceptance is not None else ABSENT)
    else:
        weapon_set_evidence = _cite_data(evidence, "weapon-set-constants",
                                         constants, pob_commit)
        rule_evidence.append(weapon_set_evidence)
        weapon_sets = WeaponSetRules(
            set_ids=[], hands_per_set={}, swap_allowed=False,
            evidence_ids=[weapon_set_evidence],
            off_hand_rules=off_hand_rules if acceptance is not None else ABSENT)
        gaps.append(make_gap(
            "%s/weapon-set-count" % GAP_PREFIX,
            kind=GapKind.MISSING_INPUT,
            severity=GapSeverity.BLOCKING,
            explanation=(
                "The engine reported no weapon-set count, so the profile "
                "declares no weapon sets at all. Nothing may read that as "
                "'weapon swapping is disallowed'."),
            needed_evidence=(
                "the number of weapon sets a character has in the resolved "
                "patch and whether swapping between them is unrestricted, from "
                "the official patch notes"),
            collection_method="source lookup",
            created_at=created_at,
            field_paths=["/character_rules/weapon_sets"]))

    # -- gem and skill levels ---------------------------------------------
    natural_levels = [gem.raw_reference.get("naturalMaxLevel") for gem in gems]
    natural_levels = [int(level) for level in natural_levels
                      if isinstance(level, (int, float))]
    gem_level_limit = max(natural_levels) if natural_levels else None
    if gem_level_limit is not None:
        gem_evidence = _cite_data(
            evidence, "gem-natural-max-levels",
            {"observed_maximum": gem_level_limit, "gems": len(gems)},
            pob_commit)
        rule_evidence.append(gem_evidence)
    gaps.append(make_gap(
        "%s/gem-level-legality" % GAP_PREFIX,
        kind=GapKind.UNSUPPORTED_RULE,
        severity=GapSeverity.INFORMATIONAL,
        explanation=(
            "gem_level_limit is the highest natural maximum level in the "
            "engine's gem data (%s). It is not a legality cap: items and "
            "passives grant levels above a gem's natural maximum, and upstream "
            "carries no single number for the highest legal level."
            % (gem_level_limit if gem_level_limit is not None else "unknown")),
        needed_evidence=(
            "the rule relating a gem's natural maximum level to the highest "
            "level it can reach with item and passive grants in the resolved "
            "patch, confirmed with one fixture build per grant source"),
        collection_method="engine implementation",
        created_at=created_at,
        field_paths=["/character_rules/gem_level_limit"]))
    gaps.append(make_gap(
        "%s/skill-level-limit" % GAP_PREFIX,
        kind=GapKind.MISSING_INPUT,
        severity=GapSeverity.INFORMATIONAL,
        explanation=(
            "The engine carries per-skill level tables but no character-facing "
            "limit on a skill's level that is separate from its gem, so "
            "skill_level_limit is exported as unknown."),
        needed_evidence=(
            "whether the resolved patch caps an active skill's level "
            "independently of its gem level, and the cap if it does, from the "
            "official patch notes"),
        collection_method="source lookup",
        created_at=created_at,
        field_paths=["/character_rules/skill_level_limit"]))

    rules = CharacterRules(
        level_range=LevelRange(minimum=1, maximum=maximum_level),
        class_ascendancies=class_ascendancies,
        gem_level_limit=gem_level_limit,
        skill_level_limit=None,
        point_budgets=budgets,
        slots=slot_rules,
        support_restrictions=support_restrictions,
        weapon_sets=weapon_sets,
        missing_rule_gap_ids=[gap.gap_id for gap in gaps],
        evidence_ids=sorted(set(rule_evidence)))
    return RuleBuild(rules=rules, gaps=gaps)


def _slot_rules(slots: Sequence[CatalogEntity],
                acceptance: SlotAcceptance | None,
                citations: Mapping[str, Citation], evidence: EvidenceBundle,
                pob_commit: str | None, created_at: str):
    """Slot rules, off-hand rules, their gaps and their evidence ids."""
    gaps: list[DataGap] = []
    slot_evidence = _cite_data(
        evidence, "slots",
        [{"entity_id": slot.entity_id,
          "weaponSet": slot.raw_reference.get("weaponSet")} for slot in slots],
        pob_commit)
    evidence_ids = [slot_evidence]

    def weapon_set_of(slot: CatalogEntity) -> str | None:
        weapon_set = slot.raw_reference.get("weaponSet")
        return (entity_id("weapon_sets", weapon_set)
                if weapon_set is not None else None)

    if acceptance is None:
        rules = [SlotRule(
            slot_id=slot.entity_id,
            # Empty because upstream's slot table does not carry it, not
            # because the slot accepts nothing. See the gap below.
            accepted_base_categories=[],
            weapon_set_id=weapon_set_of(slot),
            evidence_ids=[slot_evidence]) for slot in slots]
        gaps.append(make_gap(
            "%s/slot-accepted-base-categories" % GAP_PREFIX,
            kind=GapKind.MISSING_INPUT,
            severity=GapSeverity.BLOCKING,
            explanation=(
                "The engine's slot table names %d slots and which of them "
                "belong to a weapon set. It does not say which item base "
                "categories each slot accepts, so every exported slot rule has "
                "an empty category list and equipment legality cannot be "
                "decided from this profile." % len(rules)),
            needed_evidence=(
                "for each equipment slot, the set of item base types it "
                "accepts and the hand or slot conflicts it creates, read from "
                "the engine's own item-to-slot matching code and confirmed "
                "against one fixture item per base type"),
            collection_method="engine implementation",
            created_at=created_at,
            field_paths=["/character_rules/slots"]))
        return rules, [], gaps, evidence_ids

    probe_evidence = _cite_data(evidence, "slot-acceptance-probe", {
        "probe_count": acceptance.probe_count,
        "probe_failures": acceptance.probe_failures,
        "accepted": acceptance.accepted,
        "partial": acceptance.partial,
        "refused_rarities": acceptance.refused_rarities,
        "rarity_undecided": acceptance.rarity_undecided,
        "off_hand": [{"off_slot": c.off_slot, "main_slot": c.main_slot,
                      "flag": c.flag, "main_category": c.main_category,
                      "accepted": list(c.accepted), "partial": list(c.partial),
                      "uniform": c.uniform,
                      "refused_rarities": list(c.refused_rarities),
                      "rarity_undecided": {r: list(v) for r, v
                                           in c.rarity_undecided.items()}}
                     for c in acceptance.off_hand],
    }, pob_commit)
    evidence_ids.append(probe_evidence)
    rule_evidence = [slot_evidence, probe_evidence]
    citation = citations.get("slot_validity")
    if citation is not None:
        source_evidence = _cite(evidence, citation, pob_commit)
        evidence_ids.append(source_evidence)
        rule_evidence.append(source_evidence)

    off_slots = acceptance.off_hand_slots
    failed = acceptance.failed_bases
    gap_partial = "%s/slot-partial-categories" % GAP_PREFIX_T031
    gap_rarity = "%s/slot-rarity-partial" % GAP_PREFIX_T031
    gap_mixed = "%s/off-hand-mixed-main-hand" % GAP_PREFIX_T031
    gap_failed = "%s/slot-probe-failures" % GAP_PREFIX_T031

    def rule_gap_ids(undecided, rarities, mixed=False):
        out = []
        if undecided:
            out.append(gap_mixed if mixed or "*" in undecided else gap_partial)
        if rarities:
            out.append(gap_rarity)
        if failed:
            out.append(gap_failed)
        return sorted(set(out))

    rules: list[SlotRule] = []
    unprobed, empty, socketed = [], [], []
    for slot in slots:
        name = str(slot.raw_reference.get("name") or "")
        refused = acceptance.refused_rarities.get(name, [])
        rarities = acceptance.rarity_undecided.get(name, {})
        undecided = list(acceptance.partial.get(name, []))
        if name in off_slots:
            accepted = acceptance.off_hand_union(name)
            refused = acceptance.off_hand_refused(name)
            undecided = acceptance.off_hand_undecided(name)
            # A rarity a context leaves undecided stays undecided for the slot.
            merged: dict[str, set] = {}
            for c in acceptance.off_hand:
                if c.off_slot == name:
                    for rarity, cats in c.rarity_undecided.items():
                        merged.setdefault(rarity, set()).update(cats)
            rarities = {r: sorted(c) for r, c in sorted(merged.items())}
        elif name in acceptance.accepted:
            accepted = acceptance.accepted[name]
        else:
            accepted = []
            unprobed.append(slot.entity_id)
        if not accepted and not undecided and name in acceptance.accepted:
            (socketed if slot.raw_reference.get("parentSlot") else empty
             ).append(slot.entity_id)
        rules.append(SlotRule(
            slot_id=slot.entity_id, accepted_base_categories=list(accepted),
            weapon_set_id=weapon_set_of(slot),
            evidence_ids=list(rule_evidence),
            refused_rarities=list(refused),
            undecided_categories=list(undecided),
            undecided_rarities={r: list(c) for r, c in rarities.items()},
            undecided_bases=list(failed),
            gap_ids=rule_gap_ids(undecided, rarities)))

    by_name = {str(slot.raw_reference.get("name") or ""): slot.entity_id
               for slot in slots}
    off_hand_rules = [OffHandRule(
        off_hand_slot_id=by_name.get(c.off_slot,
                                     entity_id("slots", c.off_slot)),
        main_hand_slot_id=by_name.get(c.main_slot,
                                      entity_id("slots", c.main_slot)),
        main_hand_category=c.main_category, required_flag=c.flag,
        accepted_base_categories=list(c.accepted),
        evidence_ids=list(rule_evidence),
        refused_rarities=list(c.refused_rarities),
        undecided=not c.uniform,
        undecided_categories=list(c.partial),
        undecided_rarities={r: list(v) for r, v in c.rarity_undecided.items()},
        undecided_bases=list(failed),
        gap_ids=rule_gap_ids(c.partial, c.rarity_undecided,
                             mixed=not c.uniform)
        if c.uniform else sorted({gap_mixed, *([gap_failed] if failed else [])}))
        for c in acceptance.off_hand]

    def gap(suffix, subjects, explanation, needed,
            kind=GapKind.UNSUPPORTED_RULE, severity=GapSeverity.BLOCKING,
            field_path="/character_rules/slots"):
        # Slot ids are catalog entity ids, not records, so they are named in
        # the explanation rather than in subject_ids.
        if subjects:
            explanation = "%s. Slots: %s" % (explanation,
                                             ", ".join(sorted(subjects)))
        gaps.append(make_gap(
            "%s/%s" % (GAP_PREFIX_T031, suffix), kind=kind, severity=severity,
            explanation=explanation, needed_evidence=needed,
            collection_method="engine implementation", created_at=created_at,
            field_paths=[field_path]))

    if acceptance.probe_failures:
        gap("slot-probe-failures", [],
            "%d item base(s) could not be built as probe items, so every slot "
            "answers undecided for them: %s"
            % (len(acceptance.probe_failures),
               ", ".join(acceptance.probe_failures[:20])),
            "an item text the engine parses for each listed base",
            kind=GapKind.MISSING_INPUT)
    partial = dict(acceptance.partial)
    for c in acceptance.off_hand:
        if c.partial:
            partial["%s with %s, %s" % (c.off_slot, c.main_category,
                                         c.flag)] = list(c.partial)
    if partial:
        gap("slot-partial-categories", [],
            "The engine accepts only some bases of these categories in these "
            "slots, so a category list cannot express the rule: %s"
            % "; ".join("%s: %s" % (k, ", ".join(v))
                        for k, v in sorted(partial.items())),
            "the base-level condition the engine applies to each listed "
            "category, read from ItemsTab:IsItemValidForSlot")
    mixed = sorted("%s with %s, %s" % (c.off_slot, c.main_category, c.flag)
                   for c in acceptance.off_hand if not c.uniform)
    if mixed:
        gap("off-hand-mixed-main-hand", [],
            "Bases of one main-hand category give different off-hand results, "
            "so no off-hand rule was exported for: %s" % "; ".join(mixed),
            "the main-hand property the engine's off-hand check reads for "
            "each listed category")
    if unprobed:
        gap("slot-unprobed", unprobed,
            "%d slot(s) of the slot table were not in the acceptance probe, "
            "so they accept nothing in this profile" % len(unprobed),
            "an acceptance probe row for each listed slot",
            kind=GapKind.MISSING_INPUT)
    if socketed:
        gap("socketed-item-jewel-slots", socketed,
            "%d jewel socket slot(s) belong to an equipment item. The engine "
            "accepts a jewel there only when the parent item has jewel "
            "sockets and, for some items, only certain jewel bases. The probe "
            "runs with empty parents, so these slots accept nothing in this "
            "profile and imported jewels in them stay unplaced"
            % len(socketed),
            "the parent-item condition (canSocketJewelBase) per "
            "socket-granting item, read from ItemsTab:IsItemValidForSlot and "
            "the item data",
            severity=GapSeverity.RANKING_SENSITIVE)
    if empty:
        gap("slot-accepts-nothing", empty,
            "%d slot(s) accepted no probe base at all" % len(empty),
            "the condition under which the engine accepts an item in each "
            "listed slot")
    rarity_partial = {"%s at %s" % (slot, rarity): list(cats)
                      for slot, by in acceptance.rarity_undecided.items()
                      for rarity, cats in by.items()}
    for c in acceptance.off_hand:
        for rarity, cats in c.rarity_undecided.items():
            rarity_partial["%s with %s, %s at %s" % (
                c.off_slot, c.main_category, c.flag, rarity)] = list(cats)
    if rarity_partial:
        gap("slot-rarity-partial", [],
            "At these rarities the engine's answer for these categories "
            "differs from normal rarity while the slot does not refuse the "
            "rarity outright. Probe items are not real uniques, so these "
            "combinations are undecided: %s"
            % "; ".join("%s: %s" % (k, ", ".join(v))
                        for k, v in sorted(rarity_partial.items())),
            "the category and rarity condition the engine applies in each "
            "listed slot, read from ItemsTab:IsItemValidForSlot")
    flagged = sorted({c.flag for c in acceptance.off_hand if c.flag != NO_FLAG})
    if flagged:
        gap("off-hand-keystone-flags", [],
            "Off-hand rules for %s assume the flag is set. Whether a build has "
            "it is calculated engine state, which the legality check does not "
            "read, so a pairing allowed only under one of them is reported as "
            "unknown" % ", ".join(flagged),
            "the build's calculated flag state from the engine's modDB",
            severity=GapSeverity.RANKING_SENSITIVE,
            field_path="/character_rules/weapon_sets/off_hand_rules")
    return rules, off_hand_rules, gaps, evidence_ids
