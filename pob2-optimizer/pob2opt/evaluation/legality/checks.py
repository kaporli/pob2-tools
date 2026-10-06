"""The checks themselves (P02-T03).

One function per declared check. Each one records what it found and nothing
else: it never edits the build, never substitutes a default for a missing
rule, and never reports a decision it did not make. Three habits run through
all of them.

**Illegal and unknown are different answers.** A broken rule is a violation
naming the rule, the field and the two numbers. A rule the profile does not
carry, or an input nobody supplied, is an unknown citing the gap that says
what to collect.

**A bound that is only a lower bound decides only one way.** The exported
passive budget counts levelling points and leaves quest points out, so a
build inside it is inside the real budget, and a build outside it is not
thereby illegal: that is an unknown, and the gap says so.

**Nothing is inferred from a name.** Equipment legality needs the base
categories each slot accepts. P02-T02 exported every slot rule with an empty
category list and a blocking gap, so the slot check answers ``unknown`` and
cites it. Reading the categories off an item's name would be inventing the
rule the gap exists to request.
"""

from __future__ import annotations

from collections import deque
from typing import Iterable, Sequence

from ...domain.enums import Legality, ModifierParseStatus, RecordParseStatus
from ...domain.records import SkillEntry
from . import gaps as gapdefs
from .context import Context, numeric_class, numeric_node
from .inputs import ATTRIBUTES, POOLS, normalize_id
from .report import (CHECK_ASCENDANCY, CHECK_ASCENDANCY_BUDGET, CHECK_CHOICES,
                     CHECK_CLASS, CHECK_CONNECTIVITY, CHECK_GEM_LEVELS,
                     CHECK_HANDS, CHECK_IMPORT, CHECK_ITEM_CONSTRUCTION,
                     CHECK_ITEM_REQUIREMENTS, CHECK_LEVEL,
                     CHECK_PASSIVE_BUDGET, CHECK_RESERVATION, CHECK_SKILLS,
                     CHECK_SLOTS, CHECK_SOCKETED, CHECK_SUPPORTS,
                     CHECK_WEAPON_SETS, Constraint, ReportBuilder)

#: Attribute name to the requirement key an item declares it under.
_ATTRIBUTE_REQUIREMENT = {"strength": "str", "dexterity": "dex",
                          "intelligence": "int"}


# ------------------------------------------------------------ class, level ---

def check_class(ctx: Context, out: ReportBuilder) -> None:
    class_id = normalize_id("classes", ctx.build.class_id)
    known = ctx.rules.class_ascendancies
    if not known:
        out.unknown(CHECK_CLASS, "class_rules_absent",
                    "the profile lists no classes, so class membership was "
                    "not decided",
                    field_paths=("/class_id",),
                    gaps=[ctx.gaps.gap(_gap("catalog-not-supplied"))])
        return
    if class_id not in known:
        out.violation(
            CHECK_CLASS, "unknown_class",
            "class %s is not one of the %d classes the profile's rules carry"
            % (class_id, len(known)),
            rule_id="character_rules/class_ascendancies",
            field_paths=("/class_id",), subject_ids=(class_id,),
            evidence_ids=tuple(ctx.profile.character_rules.evidence_ids))
        return
    if ctx.catalog.has_table("classes") and not ctx.catalog.has("classes", class_id):
        out.unknown(CHECK_CLASS, "class_not_in_catalog",
                    "the profile's rules carry class %s but the supplied "
                    "catalog does not" % class_id,
                    field_paths=("/class_id",), subject_ids=(class_id,),
                    gaps=[ctx.gaps.gap(_gap("unresolved-catalog-entity"),
                                       references=(class_id,))])
        return
    out.ran(CHECK_CLASS, "class %s is one of the profile's classes" % class_id)


def check_ascendancy(ctx: Context, out: ReportBuilder) -> None:
    class_id = normalize_id("classes", ctx.build.class_id)
    allowed = ctx.rules.class_ascendancies.get(class_id)
    if ctx.build.ascendancy_id is None:
        if ctx.ascendancy_allocated:
            out.violation(
                CHECK_ASCENDANCY, "ascendancy_nodes_without_ascendancy",
                "%d ascendancy passives are allocated while the build "
                "declares no ascendancy"
                % len(ctx.ascendancy_allocated),
                rule_id="character_rules/class_ascendancies",
                field_paths=("/ascendancy_id", "/passives/ascendancy_allocated"),
                subject_ids=tuple(ctx.ascendancy_allocated[:8]))
            return
        out.ran(CHECK_ASCENDANCY,
                "the build declares no ascendancy and allocates none")
        return
    ascendancy_id = normalize_id("ascendancies", ctx.build.ascendancy_id)
    if allowed is None:
        out.unknown(CHECK_ASCENDANCY, "class_rules_absent",
                    "the profile carries no ascendancy list for class %s"
                    % class_id, field_paths=("/ascendancy_id",),
                    subject_ids=(class_id,),
                    gaps=[ctx.gaps.gap(_gap("catalog-not-supplied"))])
        return
    if ascendancy_id not in allowed:
        owner = _ascendancy_owner(ctx, ascendancy_id)
        detail = (" it belongs to %s" % owner) if owner else \
            " no class in the profile carries it"
        out.violation(
            CHECK_ASCENDANCY, "ascendancy_not_on_class",
            "ascendancy %s is not available to class %s;%s"
            % (ascendancy_id, class_id, detail),
            rule_id="character_rules/class_ascendancies",
            field_paths=("/ascendancy_id",),
            subject_ids=(ascendancy_id, class_id),
            evidence_ids=tuple(ctx.profile.character_rules.evidence_ids))
        return
    out.ran(CHECK_ASCENDANCY,
            "ascendancy %s is available to class %s" % (ascendancy_id, class_id))


def _ascendancy_owner(ctx: Context, ascendancy_id: str) -> str | None:
    for class_id, ascendancies in ctx.rules.class_ascendancies.items():
        if ascendancy_id in ascendancies:
            return class_id
    return None


def check_level(ctx: Context, out: ReportBuilder) -> None:
    level = ctx.level
    low, high = ctx.rules.level_minimum, ctx.rules.level_maximum
    out.constraint(Constraint(
        name="character_level", used=float(level), allowed=float(high),
        decision=Legality.LEGAL if low <= level <= high else Legality.ILLEGAL,
        basis="character_rules/level_range",
        rule_ids=("character_rules/level_range",)))
    if level < low or level > high:
        out.violation(
            CHECK_LEVEL, "level_out_of_range",
            "level %d is outside the legal range %d to %d" % (level, low, high),
            rule_id="character_rules/level_range", field_paths=("/level",),
            evidence_ids=tuple(ctx.profile.character_rules.evidence_ids))
        return
    out.ran(CHECK_LEVEL,
            "level %d is inside the legal range %d to %d" % (level, low, high))


# ----------------------------------------------------------------- budgets ---

def check_passive_budget(ctx: Context, out: ReportBuilder) -> None:
    duplicates = _duplicates([normalize_id("passive_nodes", node)
                              for node in ctx.build.passives.allocated])
    if duplicates:
        out.violation(
            CHECK_PASSIVE_BUDGET, "duplicate_passive_allocation",
            "%d passive node id(s) are allocated more than once: %s"
            % (len(duplicates), ", ".join(duplicates[:8])),
            rule_id="contracts/duplicate_allocation_ids",
            field_paths=("/passives/allocated",),
            subject_ids=tuple(duplicates[:8]))
    used = ctx.points_used
    maximum_rule = ctx.rules.maximum_budget()
    declared = ctx.build.progression.normal_point_budget
    levelling = ctx.rules.levelling_budget(ctx.level)

    if maximum_rule is not None and used > maximum_rule.passive_points:
        out.constraint(Constraint(
            name="passive_points", used=float(used),
            allowed=float(maximum_rule.passive_points),
            decision=Legality.ILLEGAL,
            basis="character_rules/point_budgets/%s" % maximum_rule.rule_id,
            rule_ids=(maximum_rule.rule_id,)))
        out.violation(
            CHECK_PASSIVE_BUDGET, "passive_points_exceed_maximum",
            "%d ordinary passives are allocated and the profile's maximum is "
            "%d" % (used, maximum_rule.passive_points),
            rule_id=maximum_rule.rule_id,
            field_paths=("/passives/allocated",),
            evidence_ids=tuple(maximum_rule.evidence_ids))
        return

    if declared is not None:
        decision = Legality.LEGAL if used <= declared else Legality.ILLEGAL
        out.constraint(Constraint(
            name="passive_points", used=float(used), allowed=float(declared),
            decision=decision, basis="build/progression/normal_point_budget"))
        if used > declared:
            out.violation(
                CHECK_PASSIVE_BUDGET, "passive_points_exceed_declared_budget",
                "%d ordinary passives are allocated and the build's own "
                "progression declares a budget of %d" % (used, declared),
                rule_id="build/progression/normal_point_budget",
                field_paths=("/passives/allocated", "/progression/normal_point_budget"),
                evidence_ids=tuple(ctx.build.progression.evidence_ids))
            return
        out.ran(CHECK_PASSIVE_BUDGET,
                "%d of the %d points the build's progression declares" % (used, declared))
        return

    if levelling is None:
        out.constraint(Constraint(
            name="passive_points", used=float(used), allowed=None,
            decision=Legality.UNKNOWN,
            basis="no levelling budget rule for level %d" % ctx.level))
        out.unknown(
            CHECK_PASSIVE_BUDGET, "no_passive_budget_rule",
            "the profile carries no levelling point budget for level %d, so "
            "the %d allocated passives were not compared with anything"
            % (ctx.level, used),
            field_paths=("/passives/allocated",),
            gaps=[ctx.gaps.gap(_gap("missing-point-budget-rule"),
                               field_paths=("/character_rules/point_budgets",))])
        return

    lower_bound = levelling.passive_points
    if used <= lower_bound:
        out.constraint(Constraint(
            name="passive_points", used=float(used), allowed=float(lower_bound),
            decision=Legality.LEGAL,
            basis="character_rules/point_budgets/%s (levelling points only, a "
                  "lower bound on the real budget)" % levelling.rule_id,
            rule_ids=(levelling.rule_id,)))
        out.ran(CHECK_PASSIVE_BUDGET,
                "%d of the %d levelling points a level %d character has; quest "
                "points would only add to that"
                % (used, lower_bound, ctx.level))
        return
    out.constraint(Constraint(
        name="passive_points", used=float(used), allowed=None,
        decision=Legality.UNKNOWN,
        basis="character_rules/point_budgets/%s counts levelling points only; "
              "the quest reward total is a gap" % levelling.rule_id,
        rule_ids=(levelling.rule_id,),
        gap_ids=(gapdefs.T02_QUEST_PASSIVE_POINTS,)))
    out.unknown(
        CHECK_PASSIVE_BUDGET, "passive_points_above_levelling_budget",
        "%d ordinary passives are allocated and a level %d character earns %d "
        "from levelling. Quest rewards add an unknown number on top, so this "
        "is over the sourced lower bound and not over a known budget"
        % (used, ctx.level, lower_bound),
        rule_id=levelling.rule_id, field_paths=("/passives/allocated",),
        gap_ids=(gapdefs.T02_QUEST_PASSIVE_POINTS,))


def check_ascendancy_budget(ctx: Context, out: ReportBuilder) -> None:
    used = ctx.ascendancy_points_used
    maximum_rule = ctx.rules.maximum_budget()
    declared = ctx.build.progression.ascendancy_point_budget

    if maximum_rule is not None and used > maximum_rule.ascendancy_points:
        out.constraint(Constraint(
            name="ascendancy_points", used=float(used),
            allowed=float(maximum_rule.ascendancy_points),
            decision=Legality.ILLEGAL,
            basis="character_rules/point_budgets/%s" % maximum_rule.rule_id,
            rule_ids=(maximum_rule.rule_id,)))
        out.violation(
            CHECK_ASCENDANCY_BUDGET, "ascendancy_points_exceed_maximum",
            "%d ascendancy passives are allocated and the profile's maximum "
            "is %d" % (used, maximum_rule.ascendancy_points),
            rule_id=maximum_rule.rule_id,
            field_paths=("/passives/ascendancy_allocated",),
            evidence_ids=tuple(maximum_rule.evidence_ids))
        return

    if declared is not None:
        decision = Legality.LEGAL if used <= declared else Legality.ILLEGAL
        out.constraint(Constraint(
            name="ascendancy_points", used=float(used), allowed=float(declared),
            decision=decision,
            basis="build/progression/ascendancy_point_budget"))
        if used > declared:
            out.violation(
                CHECK_ASCENDANCY_BUDGET,
                "ascendancy_points_exceed_declared_budget",
                "%d ascendancy passives are allocated and the build's own "
                "progression declares a budget of %d" % (used, declared),
                rule_id="build/progression/ascendancy_point_budget",
                field_paths=("/passives/ascendancy_allocated",
                             "/progression/ascendancy_point_budget"),
                evidence_ids=tuple(ctx.build.progression.evidence_ids))
            return
        out.ran(CHECK_ASCENDANCY_BUDGET,
                "%d of the %d ascendancy points the build's progression "
                "declares" % (used, declared))
        return

    if used == 0:
        out.constraint(Constraint(
            name="ascendancy_points", used=0.0,
            allowed=float(maximum_rule.ascendancy_points)
            if maximum_rule is not None else None,
            decision=Legality.LEGAL, basis="nothing is allocated"))
        out.ran(CHECK_ASCENDANCY_BUDGET, "no ascendancy passive is allocated")
        return

    out.constraint(Constraint(
        name="ascendancy_points", used=float(used),
        allowed=float(maximum_rule.ascendancy_points)
        if maximum_rule is not None else None,
        decision=Legality.UNKNOWN,
        basis="the profile carries the ascendancy maximum but no unlock "
              "schedule, so how many points a level %d character has earned is "
              "unknown" % ctx.level,
        gap_ids=(gapdefs.T02_ASCENDANCY_SCHEDULE,)))
    out.unknown(
        CHECK_ASCENDANCY_BUDGET, "ascendancy_unlock_schedule_unknown",
        "%d ascendancy passives are allocated, which is within the profile's "
        "maximum, but the profile has no rule for when each point is earned, "
        "so whether a level %d character has them is undecided"
        % (used, ctx.level),
        field_paths=("/passives/ascendancy_allocated",),
        gap_ids=(gapdefs.T02_ASCENDANCY_SCHEDULE,))


# ---------------------------------------------------------------- the tree ---

def check_connectivity(ctx: Context, out: ReportBuilder) -> None:
    if not ctx.catalog.has_table("passive_nodes"):
        out.unknown(CHECK_CONNECTIVITY, "no_passive_tree",
                    "no passive node table was supplied, so connectivity was "
                    "not decided for %d allocated nodes" % len(ctx.allocated),
                    field_paths=("/passives/allocated",),
                    gaps=[ctx.gaps.gap(_gap("catalog-not-supplied"))])
        return
    allocated = tuple(dict.fromkeys(ctx.allocated))
    missing = tuple(node for node in allocated
                    if not ctx.catalog.has("passive_nodes", node))
    if missing:
        out.unknown(
            CHECK_CONNECTIVITY, "allocated_node_not_in_catalog",
            "%d allocated node(s) are not in the supplied catalog, so the "
            "allocation could not be walked: %s"
            % (len(missing), ", ".join(missing[:8])),
            field_paths=("/passives/allocated",), subject_ids=missing[:8],
            gaps=[ctx.gaps.gap(_gap("unresolved-catalog-entity"),
                               references=missing[:8],
                               field_paths=("/passives/allocated",))])
        return

    start = ctx.catalog.class_start_node(ctx.build.class_id)
    if start is None:
        out.unknown(
            CHECK_CONNECTIVITY, "class_start_node_unknown",
            "the catalog does not say which node class %s starts from, so the "
            "allocation could not be walked" % ctx.build.class_id,
            field_paths=("/class_id",),
            gaps=[ctx.gaps.gap(_gap("unresolved-catalog-entity"),
                               references=(normalize_id("classes",
                                                         ctx.build.class_id),))])
        return

    reachable = _reachable(ctx, start, set(allocated) | {start})
    stranded = tuple(node for node in allocated if node not in reachable)
    if stranded:
        out.violation(
            CHECK_CONNECTIVITY, "disconnected_passive_allocation",
            "%d allocated node(s) have no path to the class start node %s "
            "through other allocated nodes: %s"
            % (len(stranded), start, ", ".join(stranded[:8])),
            rule_id="passive_tree/connected_allocation",
            field_paths=("/passives/allocated",), subject_ids=stranded[:8])
    else:
        out.ran(CHECK_CONNECTIVITY,
                "all %d allocated nodes reach the class start node %s"
                % (len(allocated), start))
    _check_ascendancy_connectivity(ctx, out)


def _check_ascendancy_connectivity(ctx: Context, out: ReportBuilder) -> None:
    allocated = tuple(dict.fromkeys(ctx.ascendancy_allocated))
    if not allocated:
        return
    missing = tuple(node for node in allocated
                    if not ctx.catalog.has("passive_nodes", node))
    if missing:
        out.unknown(
            CHECK_CONNECTIVITY, "ascendancy_node_not_in_catalog",
            "%d allocated ascendancy node(s) are not in the supplied catalog: "
            "%s" % (len(missing), ", ".join(missing[:8])),
            field_paths=("/passives/ascendancy_allocated",),
            subject_ids=missing[:8],
            gaps=[ctx.gaps.gap(_gap("unresolved-catalog-entity"),
                               references=missing[:8])])
        return
    names = {str(ctx.catalog.node_raw(node).get("ascendancyName") or "")
             for node in allocated}
    names.discard("")
    if len(names) > 1:
        out.violation(
            CHECK_CONNECTIVITY, "ascendancy_nodes_from_several_ascendancies",
            "allocated ascendancy nodes belong to more than one ascendancy: %s"
            % ", ".join(sorted(names)),
            rule_id="passive_tree/connected_allocation",
            field_paths=("/passives/ascendancy_allocated",))
        return
    starts = ctx.catalog.ascendancy_start_nodes()
    name = next(iter(names), None)
    start = starts.get(name) if name else None
    if start is None:
        out.unknown(
            CHECK_CONNECTIVITY, "ascendancy_start_node_unknown",
            "the catalog carries no start node for ascendancy %r, so its "
            "allocation could not be walked" % (name or "unnamed"),
            field_paths=("/passives/ascendancy_allocated",),
            gaps=[ctx.gaps.gap(_gap("unresolved-catalog-entity"),
                               references=tuple(allocated[:8]))])
        return
    reachable = _reachable(ctx, start, set(allocated) | {start})
    stranded = tuple(node for node in allocated if node not in reachable)
    if stranded:
        out.violation(
            CHECK_CONNECTIVITY, "disconnected_ascendancy_allocation",
            "%d allocated ascendancy node(s) have no path to the %s start "
            "node: %s" % (len(stranded), name, ", ".join(stranded[:8])),
            rule_id="passive_tree/connected_allocation",
            field_paths=("/passives/ascendancy_allocated",),
            subject_ids=stranded[:8])


def _reachable(ctx: Context, start: str, permitted: set[str]) -> set[str]:
    adjacency = ctx.catalog.adjacency
    seen = {start}
    queue = deque([start])
    while queue:
        node = queue.popleft()
        for neighbour in sorted(adjacency.get(node, ())):
            if neighbour in permitted and neighbour not in seen:
                seen.add(neighbour)
                queue.append(neighbour)
    return seen


def check_choices(ctx: Context, out: ReportBuilder) -> None:
    choices = ctx.build.passives.choices
    if not choices:
        out.ran(CHECK_CHOICES, "the build makes no passive choice")
        return
    allocated = set(ctx.allocated) | set(ctx.ascendancy_allocated)
    for raw_node, option in sorted(choices.items()):
        node_id = normalize_id("passive_nodes", raw_node)
        path = "/passives/choices/%s" % raw_node
        if node_id not in allocated:
            out.violation(
                CHECK_CHOICES, "choice_on_unallocated_node",
                "a choice (%s) is recorded for node %s, which is not allocated"
                % (option, node_id),
                rule_id="passive_tree/choice_requires_allocation",
                field_paths=(path,), subject_ids=(node_id,))
            continue
        raw = ctx.catalog.node_raw(node_id)
        if not raw:
            out.unknown(
                CHECK_CHOICES, "choice_node_not_in_catalog",
                "node %s is not in the supplied catalog, so its options are "
                "unavailable" % node_id, field_paths=(path,),
                subject_ids=(node_id,),
                gaps=[ctx.gaps.gap(_gap("unresolved-catalog-entity"),
                                   references=(node_id,))])
            continue
        options = raw.get("options")
        if not options:
            out.unknown(
                CHECK_CHOICES, "choice_options_not_exported",
                "node %s records the chosen option %r and the catalog carries "
                "no option list for it, so the choice was not checked"
                % (node_id, option), field_paths=(path,),
                subject_ids=(node_id,),
                gaps=[ctx.gaps.gap(_gap("attribute-choice-options"),
                                   references=(node_id,),
                                   field_paths=(path,))])
            continue
        names = {str(value) for value in _option_names(options)}
        if str(option) not in names:
            out.violation(
                CHECK_CHOICES, "choice_not_offered_by_node",
                "node %s offers %s and the build chose %r"
                % (node_id, ", ".join(sorted(names)), option),
                rule_id="passive_tree/node_options", field_paths=(path,),
                subject_ids=(node_id,))
    out.ran(CHECK_CHOICES, "%d passive choice(s) examined" % len(choices))


def _option_names(options) -> Iterable[str]:
    if isinstance(options, dict):
        for key, value in options.items():
            if isinstance(value, dict) and value.get("name"):
                yield str(value["name"])
            else:
                yield str(key)
    elif isinstance(options, (list, tuple)):
        for value in options:
            if isinstance(value, dict) and value.get("name"):
                yield str(value["name"])
            else:
                yield str(value)


def check_socketed(ctx: Context, out: ReportBuilder) -> None:
    socketed = ctx.build.passives.socketed
    if not socketed:
        out.ran(CHECK_SOCKETED, "nothing is socketed into the tree")
        return
    allocated = set(ctx.allocated) | set(ctx.ascendancy_allocated)
    seen: set[str] = set()
    for entry in socketed:
        node_id = normalize_id("passive_nodes", entry.node_id)
        path = "/passives/socketed/%s" % entry.node_id
        if node_id in seen:
            out.violation(
                CHECK_SOCKETED, "two_entities_in_one_socket",
                "node %s holds more than one socketed entity" % node_id,
                rule_id="passive_tree/one_entity_per_socket",
                field_paths=(path,), subject_ids=(node_id,))
            continue
        seen.add(node_id)
        if node_id not in allocated:
            out.violation(
                CHECK_SOCKETED, "socket_on_unallocated_node",
                "entity %s is socketed into node %s, which is not allocated"
                % (entry.entity_id, node_id),
                rule_id="passive_tree/socket_requires_allocation",
                field_paths=(path,), subject_ids=(node_id, entry.entity_id))
            continue
        raw = ctx.catalog.node_raw(node_id)
        if not raw:
            out.unknown(
                CHECK_SOCKETED, "socket_node_not_in_catalog",
                "node %s is not in the supplied catalog, so whether it is a "
                "socket is unknown" % node_id, field_paths=(path,),
                subject_ids=(node_id,),
                gaps=[ctx.gaps.gap(_gap("unresolved-catalog-entity"),
                                   references=(node_id,))])
            continue
        if not raw.get("isJewelSocket"):
            out.violation(
                CHECK_SOCKETED, "socketed_into_non_socket_node",
                "entity %s is socketed into node %s, which the catalog reports "
                "as type %r and not a socket"
                % (entry.entity_id, node_id, raw.get("type")),
                rule_id="passive_tree/socket_node_type", field_paths=(path,),
                subject_ids=(node_id,))
            continue
        if entry.entity_id in ctx.items:
            continue
        if not _entity_anywhere(ctx, entry.entity_id):
            out.unknown(
                CHECK_SOCKETED, "socketed_entity_unresolved",
                "node %s holds %s, which is neither a supplied item record nor "
                "an entity in the catalog" % (node_id, entry.entity_id),
                field_paths=(path,), subject_ids=(entry.entity_id,),
                gaps=[ctx.gaps.gap(_gap("item-record-not-supplied"),
                                   references=(entry.entity_id,))])
    out.ran(CHECK_SOCKETED, "%d socketed entit(ies) examined" % len(socketed))


def _entity_anywhere(ctx: Context, entity_id: str) -> bool:
    for table in ctx.catalog.tables.values():
        if entity_id in table:
            return True
    return False


# ---------------------------------------------------------------- equipment ---

def check_slots(ctx: Context, out: ReportBuilder) -> None:
    if not ctx.equipped:
        out.ran(CHECK_SLOTS, "the build equips nothing, so no slot had to "
                             "accept anything")
        return
    by_item: dict[str, list[str]] = {}
    by_listing: dict[str, list[str]] = {}
    for entry in ctx.equipped:
        rule = ctx.rules.slot(entry.slot_id)
        if rule is None:
            out.violation(
                CHECK_SLOTS, "unknown_slot",
                "slot %s is not one of the %d slots the profile declares"
                % (entry.slot_id, len(ctx.rules.slots_by_id)),
                rule_id="character_rules/slots",
                field_paths=("/equipment/%s" % entry.slot_id,),
                subject_ids=(entry.slot_id,))
            continue
        if entry.item_hash:
            by_item.setdefault(entry.item_hash, []).append(entry.slot_id)
        if entry.listing_id:
            by_listing.setdefault(entry.listing_id, []).append(entry.slot_id)
        _check_slot_categories(ctx, out, entry, rule)

    for item_hash, slots in sorted(by_item.items()):
        if len(slots) > 1:
            out.violation(
                CHECK_SLOTS, "item_in_two_slots",
                "item %s is equipped in %d slots at once: %s"
                % (item_hash, len(slots), ", ".join(slots)),
                rule_id="contracts/one_item_one_slot",
                field_paths=tuple("/equipment/%s" % slot for slot in slots),
                subject_ids=(item_hash,))
    for listing_id, slots in sorted(by_listing.items()):
        if len(slots) > 1:
            out.violation(
                CHECK_SLOTS, "listing_fills_two_slots",
                "listing %s fills %d slots at once: %s. One listing cannot "
                "fill two slots unless an explicit quantity supports it"
                % (listing_id, len(slots), ", ".join(slots)),
                rule_id="contracts/listing_quantity",
                field_paths=tuple("/equipment/%s" % slot for slot in slots),
                subject_ids=(listing_id,))
    out.ran(CHECK_SLOTS, "%d occupied slot(s) examined" % len(ctx.equipped))


def _check_slot_categories(ctx: Context, out: ReportBuilder, entry, rule) -> None:
    """Does this slot accept this item's base category?

    The rule decides. P02-T02 exported every ``SlotRule`` with an empty
    category list and a blocking gap, so today this is always ``unknown``.
    The branch above it is not dead code: a profile that carries the
    categories is checked against them, which is what closing the gap means.
    """
    if not rule.accepted_base_categories:
        out.unknown(
            CHECK_SLOTS, "slot_base_category_undecidable",
            "slot %s declares no accepted base categories, so whether it "
            "accepts %s was not decided" % (entry.slot_id, entry.label),
            rule_id=rule.slot_id,
            field_paths=("/equipment/%s" % entry.slot_id,),
            subject_ids=(entry.slot_id,),
            gap_ids=(gapdefs.T02_SLOT_CATEGORIES,))
        return
    category = _base_category(ctx, entry)
    if category is None:
        out.unknown(
            CHECK_SLOTS, "item_base_unresolved",
            "the base category of %s in slot %s could not be resolved from the "
            "catalog" % (entry.label, entry.slot_id),
            field_paths=("/equipment/%s" % entry.slot_id,),
            subject_ids=(entry.slot_id,),
            gaps=[ctx.gaps.gap(_gap("unresolved-catalog-entity"),
                               references=(entry.item_hash or entry.slot_id,))])
        return
    if category not in rule.accepted_base_categories:
        out.violation(
            CHECK_SLOTS, "base_category_not_accepted",
            "slot %s accepts %s and %s is a %s"
            % (entry.slot_id, ", ".join(rule.accepted_base_categories),
               entry.label, category),
            rule_id=rule.slot_id,
            field_paths=("/equipment/%s" % entry.slot_id,),
            subject_ids=(entry.slot_id,),
            evidence_ids=tuple(rule.evidence_ids))


def _base_category(ctx: Context, entry) -> str | None:
    base_id = None
    if entry.record is not None:
        base_id = entry.record.base_id
    if base_id is None and entry.imported is not None:
        base_id = entry.imported.base_name
    if base_id is None:
        return None
    raw = ctx.catalog.base_raw(base_id)
    if not raw:
        return None
    return raw.get("type")


def check_hands(ctx: Context, out: ReportBuilder) -> None:
    weapon_slots = [entry for entry in ctx.equipped
                    if (ctx.rules.slot(entry.slot_id) is not None
                        and ctx.rules.slot(entry.slot_id).weapon_set_id is not None)]
    declared_hands: dict[str, list[str]] = {}
    for weapon_set in ctx.build.weapon_sets:
        for hand, slot_ref in weapon_set.hand_slots.items():
            if slot_ref is None:
                continue
            slot_id = normalize_id("slots", slot_ref)
            declared_hands.setdefault(weapon_set.set_id, []).append(slot_id)
            rule = ctx.rules.slot(slot_id)
            path = "/weapon_sets/%s/hand_slots/%s" % (weapon_set.set_id, hand)
            if rule is None:
                out.violation(
                    CHECK_HANDS, "unknown_hand_slot",
                    "weapon set %s binds hand %s to slot %s, which the profile "
                    "does not declare" % (weapon_set.set_id, hand, slot_id),
                    rule_id="character_rules/slots", field_paths=(path,),
                    subject_ids=(slot_id,))
                continue
            if rule.weapon_set_id is None:
                out.violation(
                    CHECK_HANDS, "hand_slot_is_not_a_weapon_slot",
                    "weapon set %s binds hand %s to slot %s, which belongs to "
                    "no weapon set" % (weapon_set.set_id, hand, slot_id),
                    rule_id=rule.slot_id, field_paths=(path,),
                    subject_ids=(slot_id,),
                    evidence_ids=tuple(rule.evidence_ids))
            elif rule.weapon_set_id != weapon_set.set_id:
                out.violation(
                    CHECK_HANDS, "hand_slot_belongs_to_another_set",
                    "weapon set %s binds hand %s to slot %s, which belongs to "
                    "%s" % (weapon_set.set_id, hand, slot_id,
                            rule.weapon_set_id),
                    rule_id=rule.slot_id, field_paths=(path,),
                    subject_ids=(slot_id, rule.weapon_set_id),
                    evidence_ids=tuple(rule.evidence_ids))

    hands_per_set = ctx.rules.weapon_sets.hands_per_set
    for set_id, slots in sorted(declared_hands.items()):
        allowed = hands_per_set.get(set_id)
        if allowed is None:
            continue
        if len(slots) > allowed:
            out.violation(
                CHECK_HANDS, "too_many_hands_in_weapon_set",
                "weapon set %s binds %d hand slots and the profile allows %d"
                % (set_id, len(slots), allowed),
                rule_id="character_rules/weapon_sets",
                field_paths=("/weapon_sets/%s/hand_slots" % set_id,),
                evidence_ids=tuple(ctx.rules.weapon_sets.evidence_ids))

    if weapon_slots:
        out.unknown(
            CHECK_HANDS, "hand_conflict_undecidable",
            "%d weapon slot(s) are occupied and the profile carries no rule "
            "for which bases occupy both hands, so two-handed and off-hand "
            "conflicts were not decided: %s"
            % (len(weapon_slots),
               ", ".join(entry.slot_id for entry in weapon_slots[:8])),
            field_paths=tuple("/equipment/%s" % entry.slot_id
                              for entry in weapon_slots[:8]),
            subject_ids=tuple(entry.slot_id for entry in weapon_slots[:8]),
            gap_ids=(gapdefs.T02_SLOT_CATEGORIES,))
    else:
        out.ran(CHECK_HANDS, "no weapon slot is occupied and %d hand binding(s) "
                             "were examined"
                             % sum(len(v) for v in declared_hands.values()))


def check_item_requirements(ctx: Context, out: ReportBuilder) -> None:
    if not ctx.equipped:
        out.ran(CHECK_ITEM_REQUIREMENTS, "the build equips nothing")
        return
    level = ctx.level
    for entry in ctx.equipped:
        path = "/equipment/%s" % entry.slot_id
        required = entry.requirement("level")
        if required is None:
            required = _base_requirement(ctx, entry, "level")
        if required is None:
            out.unknown(
                CHECK_ITEM_REQUIREMENTS, "item_level_requirement_unknown",
                "neither %s nor its base declares a level requirement"
                % entry.label, field_paths=(path,),
                subject_ids=(entry.item_hash or entry.slot_id,),
                gaps=[ctx.gaps.gap(_gap("unresolved-catalog-entity"),
                                   references=(entry.item_hash or entry.slot_id,))])
        elif level < required:
            out.violation(
                CHECK_ITEM_REQUIREMENTS, "item_level_requirement_not_met",
                "%s in slot %s requires level %g and the character is level %d"
                % (entry.label, entry.slot_id, required, level),
                rule_id="item/requirements/level", field_paths=(path,),
                subject_ids=(entry.item_hash or entry.slot_id,))

        for attribute in ATTRIBUTES:
            key = _ATTRIBUTE_REQUIREMENT[attribute]
            needed = entry.requirement(key)
            if needed is None:
                needed = _base_requirement(ctx, entry, key)
            if not needed:
                continue
            have = ctx.measured.attribute(attribute) if ctx.measured else None
            if have is None:
                out.unknown(
                    CHECK_ITEM_REQUIREMENTS, "attribute_total_unmeasured",
                    "%s in slot %s requires %g %s and the character's total "
                    "was not measured" % (entry.label, entry.slot_id, needed,
                                          attribute),
                    field_paths=(path,),
                    subject_ids=(entry.item_hash or entry.slot_id,),
                    gaps=[ctx.gaps.gap(_gap("character-attribute-totals"),
                                       references=(entry.item_hash
                                                    or entry.slot_id,))])
            elif have < needed:
                out.violation(
                    CHECK_ITEM_REQUIREMENTS, "item_attribute_requirement_not_met",
                    "%s in slot %s requires %g %s and the character has %g"
                    % (entry.label, entry.slot_id, needed, attribute, have),
                    rule_id="item/requirements/%s" % key, field_paths=(path,),
                    subject_ids=(entry.item_hash or entry.slot_id,))
    out.ran(CHECK_ITEM_REQUIREMENTS,
            "%d equipped item(s) checked against level %d"
            % (len(ctx.equipped), level))


def _base_requirement(ctx: Context, entry, key: str) -> float | None:
    base_id = None
    if entry.record is not None:
        base_id = entry.record.base_id
    if base_id is None and entry.imported is not None:
        base_id = entry.imported.base_name
    if base_id is None:
        return None
    req = ctx.catalog.base_raw(base_id).get("req")
    if not isinstance(req, dict):
        return None
    value = req.get(key)
    return float(value) if isinstance(value, (int, float)) else None


def check_item_construction(ctx: Context, out: ReportBuilder) -> None:
    if not ctx.equipped:
        out.ran(CHECK_ITEM_CONSTRUCTION, "the build equips nothing")
        return
    for entry in ctx.equipped:
        path = "/equipment/%s" % entry.slot_id
        subject = entry.item_hash or entry.slot_id
        if entry.record is None:
            if entry.item_hash is None:
                # The engine holds an item the record does not mention. The
                # import check reports that; there is nothing to construct.
                continue
            out.unknown(
                CHECK_ITEM_CONSTRUCTION, "item_record_not_supplied",
                "slot %s equips %s and no ItemInstance for it was supplied"
                % (entry.slot_id, entry.item_hash), field_paths=(path,),
                subject_ids=(subject,),
                gaps=[ctx.gaps.gap(_gap("item-record-not-supplied"),
                                   references=(subject,), field_paths=(path,))])
            continue
        record = entry.record
        if record.parse_status == RecordParseStatus.INVALID:
            out.violation(
                CHECK_ITEM_CONSTRUCTION, "item_parse_invalid",
                "%s in slot %s has parse_status invalid, so it does not "
                "describe an item" % (entry.label, entry.slot_id),
                rule_id="item/parse_status", field_paths=(path,),
                subject_ids=(subject,))
            continue
        unresolved = [mod for mod in record.modifiers
                      if mod.parse_status != ModifierParseStatus.RESOLVED]
        if record.parse_status == RecordParseStatus.PARTIAL or unresolved:
            out.unknown(
                CHECK_ITEM_CONSTRUCTION, "item_modifiers_unresolved",
                "%s in slot %s is parse_status %s with %d unresolved or "
                "ambiguous modifier(s)"
                % (entry.label, entry.slot_id, record.parse_status.value,
                   len(unresolved)), field_paths=(path,), subject_ids=(subject,),
                gaps=[ctx.gaps.gap(_gap("unresolved-item-modifier"),
                                   references=(subject,), field_paths=(path,))])
        if not entry.sourced:
            out.unknown(
                CHECK_ITEM_CONSTRUCTION, "theoretical_item_construction",
                "%s in slot %s traces to no source document and no listing, so "
                "it is a constructed item and no rule in this profile says "
                "whether it can exist" % (entry.label, entry.slot_id),
                field_paths=(path,), subject_ids=(subject,),
                gaps=[ctx.gaps.gap(_gap("theoretical-item-construction"),
                                   references=(subject,), field_paths=(path,))])
        _check_socket_count(ctx, out, entry)
    out.ran(CHECK_ITEM_CONSTRUCTION,
            "%d equipped item(s) examined for construction" % len(ctx.equipped))


def _check_socket_count(ctx: Context, out: ReportBuilder, entry) -> None:
    sockets = len(entry.record.sockets) if entry.record is not None else 0
    if entry.imported is not None:
        sockets = max(sockets, entry.imported.sockets)
    if not sockets:
        return
    base_id = entry.record.base_id if entry.record is not None else None
    if base_id is None and entry.imported is not None:
        base_id = entry.imported.base_name
    raw = ctx.catalog.base_raw(base_id) if base_id else {}
    limit = raw.get("socketLimit")
    if not isinstance(limit, (int, float)):
        return
    if sockets > limit:
        out.violation(
            CHECK_ITEM_CONSTRUCTION, "too_many_sockets",
            "%s in slot %s carries %d sockets and its base allows %g"
            % (entry.label, entry.slot_id, sockets, limit),
            rule_id="item_base/socketLimit",
            field_paths=("/equipment/%s" % entry.slot_id,),
            subject_ids=(entry.item_hash or entry.slot_id,))


# ------------------------------------------------------------------- skills ---

def _walk(entries: Sequence[SkillEntry]):
    for entry in entries:
        yield entry
        for nested in entry.triggered:
            yield from _walk([nested])


def check_skills(ctx: Context, out: ReportBuilder) -> None:
    groups = ctx.build.skill_groups
    if not groups:
        out.ran(CHECK_SKILLS, "the build has no skill group")
        return
    equipped_hashes = {entry.item_hash for entry in ctx.equipped
                       if entry.item_hash}
    for index, group in enumerate(groups):
        path = "/skill_groups/%d" % index
        if group.slot_id is not None:
            slot_id = normalize_id("slots", group.slot_id)
            if ctx.rules.slot(slot_id) is None:
                out.violation(
                    CHECK_SKILLS, "unknown_group_slot",
                    "skill group %s is bound to slot %s, which the profile "
                    "does not declare" % (group.group_id, slot_id),
                    rule_id="character_rules/slots",
                    field_paths=("%s/slot_id" % path,), subject_ids=(slot_id,))
        if group.main_skill_index is not None and not (
                0 <= group.main_skill_index < len(group.skills)):
            out.violation(
                CHECK_SKILLS, "main_skill_index_out_of_range",
                "skill group %s names main skill index %d and holds %d skills"
                % (group.group_id, group.main_skill_index, len(group.skills)),
                rule_id="build/skill_groups/main_skill_index",
                field_paths=("%s/main_skill_index" % path,))
        if group.source_item_hash is not None:
            _check_item_granted(ctx, out, group, path, equipped_hashes)
        for entry in _walk(group.skills):
            _check_skill_entry(ctx, out, group, entry, path)
    out.ran(CHECK_SKILLS, "%d skill group(s) examined" % len(groups))


def _check_item_granted(ctx: Context, out: ReportBuilder, group, path: str,
                        equipped_hashes: set[str]) -> None:
    item_hash = group.source_item_hash
    if item_hash not in equipped_hashes:
        out.violation(
            CHECK_SKILLS, "item_granted_skill_without_item",
            "skill group %s is granted by item %s, which is not equipped"
            % (group.group_id, item_hash),
            rule_id="build/skill_groups/source_item_hash",
            field_paths=("%s/source_item_hash" % path,),
            subject_ids=(item_hash,))
        return
    record = ctx.item_for(item_hash)
    if record is None:
        out.unknown(
            CHECK_SKILLS, "item_granted_skill_source_not_supplied",
            "skill group %s is granted by item %s and no record for it was "
            "supplied" % (group.group_id, item_hash),
            field_paths=("%s/source_item_hash" % path,),
            subject_ids=(item_hash,),
            gaps=[ctx.gaps.gap(_gap("item-record-not-supplied"),
                               references=(item_hash,))])
        return
    granted = {effect for modifier in record.modifiers
               for effect in modifier.resolved_effect_ids}
    wanted = {entry.skill_id for entry in _walk(group.skills)}
    if granted & wanted or granted & {normalize_id("granted_skills", skill)
                                      for skill in wanted}:
        return
    out.unknown(
        CHECK_SKILLS, "item_granted_skill_unresolved",
        "skill group %s names item %s as its source and none of that item's "
        "modifiers resolves to %s"
        % (group.group_id, item_hash, ", ".join(sorted(wanted)) or "any skill"),
        field_paths=("%s/source_item_hash" % path,), subject_ids=(item_hash,),
        gaps=[ctx.gaps.gap(_gap("item-granted-skill-resolution"),
                           references=(item_hash,))])


def _check_skill_entry(ctx: Context, out: ReportBuilder, group, entry: SkillEntry,
                       path: str) -> None:
    if entry.gem_id is not None and ctx.catalog.has_table("gems"):
        raw = ctx.catalog.gem_raw(entry.gem_id)
        if not raw:
            out.unknown(
                CHECK_SKILLS, "gem_not_in_catalog",
                "skill group %s uses gem %s, which the supplied catalog does "
                "not carry" % (group.group_id, entry.gem_id),
                field_paths=("%s/skills" % path,), subject_ids=(entry.gem_id,),
                gaps=[ctx.gaps.gap(_gap("unresolved-catalog-entity"),
                                   references=(normalize_id("gems", entry.gem_id),))])
        elif raw.get("isSupport"):
            out.violation(
                CHECK_SKILLS, "support_gem_used_as_active_skill",
                "skill group %s uses support gem %s as an active skill"
                % (group.group_id, entry.gem_id),
                rule_id="gem/isSupport", field_paths=("%s/skills" % path,),
                subject_ids=(normalize_id("gems", entry.gem_id),))
    for support_id in entry.support_ids:
        if not ctx.catalog.has_table("gems"):
            break
        raw = ctx.catalog.gem_raw(support_id)
        if not raw:
            out.unknown(
                CHECK_SKILLS, "support_not_in_catalog",
                "skill group %s uses support %s, which the supplied catalog "
                "does not carry" % (group.group_id, support_id),
                field_paths=("%s/skills" % path,), subject_ids=(support_id,),
                gaps=[ctx.gaps.gap(_gap("unresolved-catalog-entity"),
                                   references=(normalize_id("gems", support_id),))])
        elif not raw.get("isSupport"):
            out.violation(
                CHECK_SKILLS, "active_gem_used_as_support",
                "skill group %s supports %s with %s, which the catalog reports "
                "as an active skill gem"
                % (group.group_id, entry.skill_id, support_id),
                rule_id="gem/isSupport", field_paths=("%s/skills" % path,),
                subject_ids=(normalize_id("gems", support_id),))


def check_supports(ctx: Context, out: ReportBuilder) -> None:
    per_group: dict[str, list[str]] = {}
    for group in ctx.build.skill_groups:
        supports: list[str] = []
        for entry in _walk(group.skills):
            supports.extend(entry.support_ids)
        if supports:
            per_group[group.group_id] = supports
    if not per_group:
        out.constraint(Constraint(name="supports_per_group", used=0.0,
                                  allowed=_support_max(ctx),
                                  decision=Legality.LEGAL,
                                  basis="no socket group carries a support"))
        out.ran(CHECK_SUPPORTS, "no socket group carries a support")
        return

    restriction = ctx.rules.support_limit()
    most = max(len(set(values)) for values in per_group.values())
    if restriction is None:
        out.constraint(Constraint(name="supports_per_group", used=float(most),
                                  allowed=None, decision=Legality.UNKNOWN,
                                  basis="the profile carries no support "
                                        "restriction"))
        out.unknown(
            CHECK_SUPPORTS, "no_support_restriction",
            "%d socket group(s) carry supports and the profile declares no "
            "limit" % len(per_group),
            field_paths=("/skill_groups",),
            gaps=[ctx.gaps.gap(_gap("missing-support-restriction"))])
        return

    limit = restriction.max_supports
    out.constraint(Constraint(
        name="supports_per_group", used=float(most), allowed=float(limit),
        decision=Legality.LEGAL if most <= limit else Legality.ILLEGAL,
        basis="character_rules/support_restrictions/%s" % restriction.restriction_id,
        rule_ids=(restriction.restriction_id,)))
    for group_id, supports in sorted(per_group.items()):
        distinct = list(dict.fromkeys(supports))
        if len(distinct) > limit:
            out.violation(
                CHECK_SUPPORTS, "too_many_supports",
                "socket group %s carries %d distinct supports and the "
                "profile's limit is %d. The profile records that limit as the "
                "engine's declared one"
                % (group_id, len(distinct), limit),
                rule_id=restriction.restriction_id,
                field_paths=("/skill_groups/%s/support_ids" % group_id,),
                evidence_ids=tuple(restriction.evidence_ids))
        if len(distinct) != len(supports):
            repeated = sorted({s for s in supports if supports.count(s) > 1})
            out.unknown(
                CHECK_SUPPORTS, "duplicate_support_in_group",
                "socket group %s lists %s more than once and the profile has "
                "no rule about repetition" % (group_id, ", ".join(repeated)),
                field_paths=("/skill_groups/%s/support_ids" % group_id,),
                subject_ids=tuple(repeated),
                gaps=[ctx.gaps.gap(_gap("duplicate-support-rule"),
                                   references=tuple(repeated))])
    out.ran(CHECK_SUPPORTS,
            "%d socket group(s) with supports, most %d, limit %d"
            % (len(per_group), most, limit))


def _support_max(ctx: Context) -> float | None:
    restriction = ctx.rules.support_limit()
    return float(restriction.max_supports) if restriction is not None else None


def check_gem_levels(ctx: Context, out: ReportBuilder) -> None:
    entries = [(group, entry) for group in ctx.build.skill_groups
               for entry in _walk(group.skills)]
    if not entries:
        out.ran(CHECK_GEM_LEVELS, "the build has no skill entry")
        return
    for group, entry in entries:
        path = "/skill_groups/%s" % group.group_id
        if entry.level < 1:
            out.violation(
                CHECK_GEM_LEVELS, "gem_level_below_one",
                "%s in group %s is level %d" % (entry.skill_id, group.group_id,
                                                entry.level),
                rule_id="gem/level", field_paths=(path,),
                subject_ids=(entry.skill_id,))
            continue
        if entry.quality < 0:
            out.violation(
                CHECK_GEM_LEVELS, "negative_quality",
                "%s in group %s has quality %d" % (entry.skill_id,
                                                   group.group_id, entry.quality),
                rule_id="gem/quality", field_paths=(path,),
                subject_ids=(entry.skill_id,))
        if entry.gem_id is None:
            out.unknown(
                CHECK_GEM_LEVELS, "skill_level_limit_unknown",
                "%s in group %s is level %d and has no gem, and the profile "
                "carries no character-facing skill level limit"
                % (entry.skill_id, group.group_id, entry.level),
                field_paths=(path,), subject_ids=(entry.skill_id,),
                gap_ids=(gapdefs.T02_SKILL_LEVEL_LIMIT,))
            continue
        raw = ctx.catalog.gem_raw(entry.gem_id)
        natural = raw.get("naturalMaxLevel") if raw else None
        if not isinstance(natural, (int, float)):
            out.unknown(
                CHECK_GEM_LEVELS, "gem_natural_maximum_unknown",
                "gem %s declares no natural maximum level in the supplied "
                "catalog, so level %d was not checked"
                % (entry.gem_id, entry.level), field_paths=(path,),
                subject_ids=(normalize_id("gems", entry.gem_id),),
                gaps=[ctx.gaps.gap(_gap("unresolved-catalog-entity"),
                                   references=(normalize_id("gems", entry.gem_id),))])
            continue
        if entry.level > natural:
            out.unknown(
                CHECK_GEM_LEVELS, "gem_above_natural_maximum",
                "%s is level %d and its natural maximum is %g. Items and "
                "passives grant levels above a natural maximum and the profile "
                "carries no rule for the highest legal level"
                % (entry.gem_id, entry.level, natural),
                field_paths=(path,),
                subject_ids=(normalize_id("gems", entry.gem_id),),
                gap_ids=(gapdefs.T02_GEM_LEVEL_LEGALITY,))
    out.ran(CHECK_GEM_LEVELS, "%d skill entr(ies) examined" % len(entries))


# ------------------------------------------------------------- reservations ---

def check_reservation(ctx: Context, out: ReportBuilder) -> None:
    measured = ctx.measured
    if measured is None or not measured.pools:
        out.unknown(
            CHECK_RESERVATION, "reservation_not_measured",
            "no measurement of the character's pools was supplied, so "
            "reservation was not checked",
            field_paths=("/skill_groups",),
            gaps=[ctx.gaps.gap(_gap("reservation-measurement"))])
        return
    decided = 0
    for name in POOLS:
        pool = measured.pool(name)
        if pool is None:
            continue
        if pool.total is None or pool.unreserved is None:
            out.constraint(Constraint(
                name="%s_reservation" % name, used=pool.reserved,
                allowed=pool.total, decision=Legality.UNKNOWN,
                basis="the engine did not report both the %s total and its "
                      "unreserved remainder" % name))
            out.unknown(
                CHECK_RESERVATION, "%s_not_calculated" % name,
                "the engine reported no %s total or no unreserved remainder, "
                "so %s reservation was not decided" % (name, name),
                field_paths=("/skill_groups",),
                gaps=[ctx.gaps.gap(_gap("reservation-measurement"))])
            continue
        decided += 1
        out.constraint(Constraint(
            name="%s_reservation" % name,
            used=(pool.total - pool.unreserved), allowed=pool.total,
            decision=Legality.ILLEGAL if pool.unreserved < 0 else Legality.LEGAL,
            basis="engine measurement (%s)" % measured.source))
        if pool.unreserved < 0:
            out.violation(
                CHECK_RESERVATION, "reservation_exceeds_pool",
                "the build reserves %g %s and has %g: the engine reports %g "
                "unreserved" % (pool.total - pool.unreserved, name, pool.total,
                                pool.unreserved),
                rule_id="engine/%sUnreserved" % name.capitalize(),
                field_paths=("/skill_groups",))
    if decided:
        out.ran(CHECK_RESERVATION,
                "%d pool(s) decided from a %s measurement"
                % (decided, measured.source))


# ------------------------------------------------------------- weapon sets ---

def check_weapon_sets(ctx: Context, out: ReportBuilder) -> None:
    rules = ctx.rules.weapon_sets
    declared = ctx.build.weapon_sets
    group_sets = {group.weapon_set_id for group in ctx.build.skill_groups
                  if group.weapon_set_id is not None}
    if not declared and not group_sets:
        out.ran(CHECK_WEAPON_SETS, "the build declares no weapon set")
        return
    if not rules.set_ids:
        out.unknown(
            CHECK_WEAPON_SETS, "weapon_set_rules_absent",
            "the build declares %d weapon set(s) and the profile declares "
            "none" % len(declared), field_paths=("/weapon_sets",),
            gaps=[ctx.gaps.gap(_gap("missing-weapon-set-rules"))])
        return

    seen: set[str] = set()
    for weapon_set in declared:
        if weapon_set.set_id in seen:
            out.violation(
                CHECK_WEAPON_SETS, "duplicate_weapon_set",
                "weapon set %s is declared twice" % weapon_set.set_id,
                rule_id="character_rules/weapon_sets",
                field_paths=("/weapon_sets",), subject_ids=(weapon_set.set_id,))
        seen.add(weapon_set.set_id)
        if weapon_set.set_id not in rules.set_ids:
            out.violation(
                CHECK_WEAPON_SETS, "unknown_weapon_set",
                "weapon set %s is not one of %s"
                % (weapon_set.set_id, ", ".join(rules.set_ids)),
                rule_id="character_rules/weapon_sets",
                field_paths=("/weapon_sets",), subject_ids=(weapon_set.set_id,),
                evidence_ids=tuple(rules.evidence_ids))
    for set_id in sorted(group_sets):
        if set_id not in rules.set_ids:
            out.violation(
                CHECK_WEAPON_SETS, "skill_group_in_unknown_weapon_set",
                "a skill group is bound to weapon set %s, which is not one of "
                "%s" % (set_id, ", ".join(rules.set_ids)),
                rule_id="character_rules/weapon_sets",
                field_paths=("/skill_groups",), subject_ids=(set_id,),
                evidence_ids=tuple(rules.evidence_ids))
    if len(seen) > 1 and not rules.swap_allowed:
        out.violation(
            CHECK_WEAPON_SETS, "weapon_swap_not_allowed",
            "the build declares %d weapon sets and the profile says swapping "
            "is not allowed" % len(seen),
            rule_id="character_rules/weapon_sets",
            field_paths=("/weapon_sets",),
            evidence_ids=tuple(rules.evidence_ids))

    _check_weapon_set_points(ctx, out)
    out.ran(CHECK_WEAPON_SETS, "%d declared weapon set(s) examined" % len(declared))


def _check_weapon_set_points(ctx: Context, out: ReportBuilder) -> None:
    used = len({node for weapon_set in ctx.build.weapon_sets
                for node in weapon_set.passive_allocations})
    budget = ctx.rules.weapon_set_budget()
    if used == 0:
        out.constraint(Constraint(
            name="weapon_set_points", used=0.0,
            allowed=float(budget.passive_points) if budget else None,
            decision=Legality.LEGAL,
            basis="no weapon-set passive is allocated"))
        return
    if budget is None:
        out.constraint(Constraint(name="weapon_set_points", used=float(used),
                                  allowed=None, decision=Legality.UNKNOWN,
                                  basis="the profile carries no weapon-set "
                                        "point budget"))
        out.unknown(
            CHECK_WEAPON_SETS, "no_weapon_set_point_budget",
            "%d weapon-set passives are allocated and the profile carries no "
            "weapon-set point budget" % used,
            field_paths=("/weapon_sets",),
            gaps=[ctx.gaps.gap(_gap("missing-point-budget-rule"),
                               field_paths=("/character_rules/point_budgets",))])
        return
    allowed = budget.passive_points
    out.constraint(Constraint(
        name="weapon_set_points", used=float(used), allowed=float(allowed),
        decision=Legality.ILLEGAL if used > allowed else Legality.UNKNOWN,
        basis="character_rules/point_budgets/%s is the total across every "
              "quest reward; when each is earned is a gap" % budget.rule_id,
        rule_ids=(budget.rule_id,), gap_ids=(gapdefs.T02_WEAPON_SET_UNLOCK,)))
    if used > allowed:
        out.violation(
            CHECK_WEAPON_SETS, "weapon_set_points_exceed_budget",
            "%d weapon-set passives are allocated and every quest reward "
            "together grants %d" % (used, allowed),
            rule_id=budget.rule_id, field_paths=("/weapon_sets",),
            evidence_ids=tuple(budget.evidence_ids))
        return
    out.unknown(
        CHECK_WEAPON_SETS, "weapon_set_point_unlock_unknown",
        "%d of the %d weapon-set passive points are allocated, and the profile "
        "records no level at which each is earned, so whether a level %d "
        "character has them is undecided" % (used, allowed, ctx.level),
        field_paths=("/weapon_sets",), gap_ids=(gapdefs.T02_WEAPON_SET_UNLOCK,))


# ------------------------------------------------------------ after import ---

def check_import(ctx: Context, out: ReportBuilder) -> None:
    imported = ctx.imported
    if imported is None:
        out.unknown(
            CHECK_IMPORT, "not_verified_after_import",
            "the build was not loaded into the pinned engine, so this verdict "
            "rests on the record's own claims about its allocation and "
            "equipment",
            gaps=[ctx.gaps.gap(_gap("unverified-import"))])
        return
    if imported.unreadable_node_keys:
        out.unknown(
            CHECK_IMPORT, "unreadable_allocation_keys",
            "the engine holds %d allocated node key(s) that are not numeric: "
            "%s" % (len(imported.unreadable_node_keys),
                    ", ".join(imported.unreadable_node_keys[:8])),
            subject_ids=tuple(imported.unreadable_node_keys[:8]),
            gaps=[ctx.gaps.gap(_gap("unresolved-catalog-entity"),
                               references=tuple(imported.unreadable_node_keys[:8]))])

    if imported.level is not None and imported.level != ctx.build.level:
        out.violation(
            CHECK_IMPORT, "import_level_mismatch",
            "the record says level %d and the engine holds level %d after "
            "loading its document" % (ctx.build.level, imported.level),
            rule_id="post_import/level", field_paths=("/level",))

    declared_class = numeric_class(ctx.build.class_id)
    if (declared_class is not None and imported.class_id is not None
            and declared_class != imported.class_id):
        out.violation(
            CHECK_IMPORT, "import_class_mismatch",
            "the record says class %s and the engine holds class %s (%s)"
            % (ctx.build.class_id, imported.class_id, imported.class_name),
            rule_id="post_import/class", field_paths=("/class_id",))

    record_nodes = {numeric_node(node) for node in ctx.build.passives.allocated}
    if None not in record_nodes:
        engine_nodes = set(imported.allocated_nodes)
        only_record = sorted(n for n in record_nodes if n not in engine_nodes)
        only_engine = sorted(n for n in engine_nodes if n not in record_nodes)
        if only_record or only_engine:
            out.violation(
                CHECK_IMPORT, "import_allocation_mismatch",
                "the engine's allocation after loading the document differs "
                "from the record: %d node(s) only in the record (%s), %d only "
                "in the engine (%s)"
                % (len(only_record),
                   ", ".join(str(n) for n in only_record[:8]) or "none",
                   len(only_engine),
                   ", ".join(str(n) for n in only_engine[:8]) or "none"),
                rule_id="post_import/allocation",
                field_paths=("/passives/allocated",))

    record_slots = {normalize_id("slots", slot)
                    for slot, entry in ctx.build.equipment.items()
                    if entry is not None}
    engine_slots = {item.slot_id for item in imported.items.values()}
    if record_slots != engine_slots:
        only_record = sorted(record_slots - engine_slots)
        only_engine = sorted(engine_slots - record_slots)
        out.violation(
            CHECK_IMPORT, "import_equipment_mismatch",
            "the engine's equipment after loading the document differs from "
            "the record: %s only in the record, %s only in the engine"
            % (", ".join(only_record) or "none",
               ", ".join(only_engine) or "none"),
            rule_id="post_import/equipment", field_paths=("/equipment",))

    out.ran(CHECK_IMPORT,
            "verified against the engine after an exact load of document %s: "
            "%d allocated nodes, %d ascendancy nodes, %d equipped items"
            % (imported.document_hash[:12], len(imported.allocated_nodes),
               len(imported.ascendancy_nodes), len(imported.items)))


# ----------------------------------------------------------------- helpers ---

def _gap(name: str) -> str:
    return "%s/%s" % (gapdefs.GAP_PREFIX, name)


def _duplicates(values: Sequence[str]) -> list[str]:
    seen: set[str] = set()
    repeated: list[str] = []
    for value in values:
        if value in seen and value not in repeated:
            repeated.append(value)
        seen.add(value)
    return repeated


#: The order checks run in. Order does not change a verdict; it decides the
#: order findings are reported in.
CHECKS = (
    check_class,
    check_ascendancy,
    check_level,
    check_passive_budget,
    check_ascendancy_budget,
    check_connectivity,
    check_choices,
    check_socketed,
    check_slots,
    check_hands,
    check_item_requirements,
    check_item_construction,
    check_skills,
    check_supports,
    check_gem_levels,
    check_reservation,
    check_weapon_sets,
    check_import,
)
