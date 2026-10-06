"""Declared primitive semantics (P02-T04).

One table. Every value the encounter model (P07) is allowed to consume appears
here once, with a unit, an owner and the effects the number already contains.
A field name is not a semantic: ``TotalDPS`` says nothing about whether it
counts projectile overlap, trigger cadence or damage over time, so each entry
cites the controlled fixture that settled it. The fixtures and their measured
numbers are in ``docs/evidence/P02/primitives.md``.

Three rules this module exists to keep:

* one owner per primitive. ``pob`` means the pinned engine computes it and
  nothing downstream may recompute it; ``simulator`` means P07 computes it and
  the engine supplies no value at all.
* a missing native output is a gap, never a substituted constant. Reading a
  primitive whose native key is absent returns ``None`` and produces a
  ``PrimitiveGap``.
* a native output whose unit depends on engine state is ``conditional`` and
  stays unresolved until that state is known. ``CombinedDPS`` is damage per
  second for most skills and damage *per use* for skills PoB flags
  ``showAverage``; a consumer that cannot see the flag gets a gap.

Nothing here is gameplay evidence. Engine agreement is not practical accuracy.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

#: Bumped whenever a declaration below changes meaning. Part of what a caller
#: records next to a value, so an old evaluation is not read under new units.
SEMANTICS_VERSION = "p02-t04.1"

#: The task that owns this table.
SEMANTICS_OWNER = "P02-T04"

STATUS_DECLARED = "declared"
STATUS_CONDITIONAL = "conditional"
STATUS_GAP = "gap"

OWNER_POB = "pob"
OWNER_SIMULATOR = "simulator"

#: Evidence labels. Nothing in this repository is gameplay evidence.
FIXTURE_LABEL = "PoB-derived, controlled fixture"


@dataclass(frozen=True, slots=True)
class PrimitiveDefinition:
    """What one primitive means, in enough detail to use or refuse it."""

    primitive_id: str
    #: The PoB output key, or None when no native output exists.
    native_key: str | None
    unit: str
    owner: str
    includes: tuple[str, ...]
    excludes: tuple[str, ...]
    status: str
    #: The fixture in docs/evidence/P02/primitives.md that established this,
    #: or the reason no fixture could.
    evidence: str
    #: Set for ``conditional``: the engine fact that decides the unit.
    resolved_by: str | None = None

    @property
    def declared(self) -> bool:
        return self.status in (STATUS_DECLARED, STATUS_CONDITIONAL)


@dataclass(frozen=True, slots=True)
class DeclaredPrimitive:
    """One primitive's value together with the declaration it was read under."""

    definition: PrimitiveDefinition
    value: Any
    unit: str

    @property
    def primitive_id(self) -> str:
        return self.definition.primitive_id


@dataclass(frozen=True, slots=True)
class PrimitiveGap:
    """A primitive that could not be supplied. Never a default value.

    ``kind`` uses the ``DataGap`` vocabulary from ``docs/specs/contracts.md``.
    """

    primitive_id: str
    native_key: str | None
    kind: str
    explanation: str
    needed_evidence: str
    owner: str


def _p(primitive_id, native_key, unit, owner, includes, excludes, status,
       evidence, resolved_by=None) -> PrimitiveDefinition:
    return PrimitiveDefinition(primitive_id=primitive_id, native_key=native_key,
                               unit=unit, owner=owner, includes=tuple(includes),
                               excludes=tuple(excludes), status=status,
                               evidence=evidence, resolved_by=resolved_by)


# --------------------------------------------------------------- damage per use

_DAMAGE = (
    _p("damage_per_use", "AverageDamage", "damage per use", OWNER_POB,
       includes=("hit probability", "critical strike chance and multiplier",
                 "enemy resistances and the configured enemy level"),
       excludes=("damage over time", "ailment damage", "projectile overlap",
                 "other socket groups", "rotation and setup time"),
       status=STATUS_DECLARED, evidence="F-ACC, F-PROJ"),
    _p("hit_damage_per_second", "TotalDPS", "damage per second", OWNER_POB,
       includes=("everything damage_per_use includes",
                 "the use rate in use_rate_per_second"),
       excludes=("damage over time", "ailment damage", "projectile overlap",
                 "other socket groups", "rotation and setup time",
                 "trigger cadence unless the skill declares one"),
       status=STATUS_DECLARED, evidence="F-DPS, F-PROJ, F-TRIG"),
    _p("combined_damage", "CombinedDPS",
       "damage per second, or damage per use when the skill declares showAverage",
       OWNER_POB,
       includes=("hit damage", "damage over time when the unit is per second",
                 "culling and reservation multipliers"),
       excludes=("other socket groups",),
       status=STATUS_CONDITIONAL, evidence="F-UNIT",
       resolved_by="LoadedBuild.main_skill_show_average"),
    _p("aggregate_damage_per_second", "FullDPS", "damage per second", OWNER_POB,
       includes=("every socket group flagged includeInFullDPS",
                 "damage over time"),
       excludes=("projectile overlap", "rotation and setup time"),
       status=STATUS_DECLARED, evidence="F-FULL"),
)

# ------------------------------------------------------------- damage over time

_DOT = (
    _p("dot_damage_per_second", "TotalDotDPS",
       "damage per second while the effect is active", OWNER_POB,
       includes=("ailment chance and stack potential for ailment damage over time",
                 "the damage-over-time cap PoB applies"),
       excludes=("the effect duration", "the cost of reapplying the effect",
                 "total damage per application"),
       status=STATUS_DECLARED, evidence="F-DOT"),
    _p("dot_instance_damage_per_second", "TotalDot",
       "damage per second while one instance is active", OWNER_POB,
       includes=("one application of the skill's own damage over time",),
       excludes=("the effect duration", "ailments", "stacking"),
       status=STATUS_DECLARED, evidence="F-DOT"),
    _p("skill_effect_duration_s", "Duration", "seconds", OWNER_POB,
       includes=("duration modifiers from gems, supports and the tree",),
       excludes=("ailment durations, which have their own outputs",),
       status=STATUS_DECLARED, evidence="F-DOT"),
)

# -------------------------------------------------------------------- timing

_TIMING = (
    _p("use_rate_per_second", "Speed", "uses per second", OWNER_POB,
       includes=("attack or cast speed modifiers",
                 "the cooldown, when the skill has one: the rate becomes 1/cooldown",
                 "a declared trigger rate, when the skill data has one"),
       excludes=("rotation composition", "enabler casts", "reload downtime",
                 "movement and targeting"),
       status=STATUS_DECLARED, evidence="F-CD, F-TRIG"),
    _p("use_time_s", "Time", "seconds per use", OWNER_POB,
       includes=("the reciprocal of use_rate_per_second",),
       excludes=("rotation composition", "enabler casts"),
       status=STATUS_DECLARED, evidence="F-CD"),
    _p("cooldown_s", "Cooldown", "seconds", OWNER_POB,
       includes=("cooldown recovery modifiers",),
       excludes=("extra charges from supports, which PoB folds into the rate",),
       status=STATUS_DECLARED, evidence="F-CD"),
)

# ------------------------------------------------------------- resource cost

_COST = (
    _p("mana_cost_per_use", "ManaCost", "mana per use", OWNER_POB,
       includes=("cost modifiers from gems, supports and the tree",),
       excludes=("mana regeneration", "sustainability over an encounter"),
       status=STATUS_DECLARED, evidence="F-COST"),
    _p("mana_cost_per_second", "ManaPerSecondCost", "mana per second", OWNER_POB,
       includes=("mana_cost_per_use multiplied by use_rate_per_second",),
       excludes=("mana regeneration", "rotation composition"),
       status=STATUS_DECLARED, evidence="F-COST"),
    _p("life_cost_per_use", "LifeCost", "life per use", OWNER_POB,
       includes=("cost modifiers",), excludes=("life regeneration",),
       status=STATUS_DECLARED, evidence="F-COST"),
    _p("spirit_total", "Spirit", "spirit points", OWNER_POB,
       includes=("spirit granted by gear and the tree",),
       excludes=("what is currently reserved",),
       status=STATUS_DECLARED, evidence="F-COST"),
    _p("spirit_unreserved", "SpiritUnreserved", "spirit points", OWNER_POB,
       includes=("every active reservation",), excludes=(),
       status=STATUS_DECLARED, evidence="F-COST"),
)

# ----------------------------------------------------------- hit probability

_HIT = (
    _p("hit_probability_pct", "HitChance", "percent", OWNER_POB,
       includes=("accuracy against the configured enemy level",),
       excludes=("block, evasion-on-the-defender and other avoidance the enemy "
                 "model would add"),
       status=STATUS_DECLARED, evidence="F-ACC"),
    _p("crit_chance_pct", "CritChance", "percent", OWNER_POB,
       includes=("hit probability: PoB reports the effective crit chance",),
       excludes=(),
       status=STATUS_DECLARED, evidence="F-ACC"),
)

# --------------------------------------------------------------- target count

_TARGETS = (
    _p("projectiles_per_use", "ProjectileCount",
       "projectiles per use, expected value and not always an integer", OWNER_POB,
       includes=("additional projectiles from gear, gems and supports",
                 "chance-based extra projectiles, as an expected value"),
       excludes=("how many of them reach one target: see "
                 "projectile_overlap_multiplier"),
       status=STATUS_DECLARED, evidence="F-PROJ"),
    _p("pierce_count", "PierceCount", "enemies pierced per projectile", OWNER_POB,
       includes=(), excludes=("whether enemies are positioned to be pierced",),
       status=STATUS_DECLARED, evidence="F-PROJ"),
    _p("chain_count", "ChainCount", "chains per projectile", OWNER_POB,
       includes=(), excludes=("whether other enemies are in chain range",),
       status=STATUS_DECLARED, evidence="F-PROJ"),
    _p("area_of_effect_radius_pob", "AreaOfEffectRadius",
       "PoB area units; PoB's own conversion is 10 units per metre", OWNER_POB,
       includes=("area of effect modifiers",), excludes=(),
       status=STATUS_DECLARED, evidence="F-AREA"),
    _p("area_of_effect_radius_m", "AreaOfEffectRadiusMetres", "metres", OWNER_POB,
       includes=("area of effect modifiers",), excludes=(),
       status=STATUS_DECLARED, evidence="F-AREA"),
)

# ------------------------------------------------------------------ defences

_DEFENCE = (
    _p("life", "Life", "life points", OWNER_POB, includes=(), excludes=(),
       status=STATUS_DECLARED, evidence="F-DEF"),
    _p("energy_shield", "EnergyShield", "energy shield points", OWNER_POB,
       includes=(), excludes=(), status=STATUS_DECLARED, evidence="F-DEF"),
    _p("mana", "Mana", "mana points", OWNER_POB, includes=(), excludes=(),
       status=STATUS_DECLARED, evidence="F-DEF"),
    _p("armour", "Armour", "armour points", OWNER_POB, includes=(),
       excludes=("the hit size it is evaluated against",),
       status=STATUS_DECLARED, evidence="F-DEF"),
    _p("evasion", "Evasion", "evasion points", OWNER_POB, includes=(),
       excludes=("the attacker accuracy it is evaluated against",),
       status=STATUS_DECLARED, evidence="F-DEF"),
    _p("fire_resist_pct", "FireResist", "percent", OWNER_POB, includes=(),
       excludes=(), status=STATUS_DECLARED, evidence="F-DEF"),
    _p("cold_resist_pct", "ColdResist", "percent", OWNER_POB, includes=(),
       excludes=(), status=STATUS_DECLARED, evidence="F-DEF"),
    _p("lightning_resist_pct", "LightningResist", "percent", OWNER_POB,
       includes=(), excludes=(), status=STATUS_DECLARED, evidence="F-DEF"),
    _p("chaos_resist_pct", "ChaosResist", "percent", OWNER_POB, includes=(),
       excludes=(), status=STATUS_DECLARED, evidence="F-DEF"),
    _p("effective_hit_pool", "TotalEHP", "damage absorbed before death",
       OWNER_POB,
       includes=("the configured incoming damage composition PoB assumes",),
       excludes=("an encounter's actual damage schedule", "recovery over time"),
       status=STATUS_DECLARED, evidence="F-DEF"),
    _p("max_physical_hit_taken", "PhysicalMaximumHitTaken", "damage", OWNER_POB,
       includes=(), excludes=("repeated hits", "damage over time"),
       status=STATUS_DECLARED, evidence="F-DEF"),
    _p("block_chance_pct", "BlockChance", "percent", OWNER_POB, includes=(),
       excludes=(), status=STATUS_DECLARED, evidence="F-DEF"),
    _p("movement_speed_mod", "EffectiveMovementSpeedMod",
       "multiplier, 1.0 is base", OWNER_POB, includes=(),
       excludes=("the route an encounter requires",),
       status=STATUS_DECLARED, evidence="F-DEF"),
)

# ------------------------------------------- what PoB does not supply at all

_SIMULATOR = (
    _p("targets_hit_per_use", None, "enemies hit per use", OWNER_SIMULATOR,
       includes=(), excludes=(),
       status=STATUS_GAP, evidence="no native output; PoB calculates against one "
       "configured enemy. F-PROJ shows extra projectiles change nothing."),
    _p("projectile_overlap_multiplier", None,
       "fraction of projectiles per use that reach one target", OWNER_SIMULATOR,
       includes=(), excludes=(),
       status=STATUS_GAP, evidence="F-PROJ: tripling ProjectileCount left "
       "AverageDamage and TotalDPS unchanged, and the per-skill overlap configs "
       "PoB ships name no skill in the pinned PoE2 catalog."),
    _p("trigger_rate_per_second", None, "triggers per second", OWNER_SIMULATOR,
       includes=(), excludes=(),
       status=STATUS_GAP, evidence="F-TRIG: PoB uses a declared trigger rate "
       "when the skill data carries one; no meta gem in the pinned catalog "
       "marked a socketed spell triggered, so the spell was scored at its own "
       "cast rate."),
    _p("dot_reapplication_cost_s", None, "seconds per application",
       OWNER_SIMULATOR, includes=(), excludes=(),
       status=STATUS_GAP, evidence="F-DOT: the reported rate is unchanged by "
       "duration, so nothing charges for reapplying the effect."),
    _p("sustained_damage_per_second", None,
       "damage per second over a complete rotation", OWNER_SIMULATOR,
       includes=(), excludes=(),
       status=STATUS_GAP, evidence="no native output. The legacy estimate in "
       "pob2opt.legacy_estimates is a heuristic, not this primitive."),
    _p("setup_time_s", None, "seconds spent before sustained damage begins",
       OWNER_SIMULATOR, includes=(), excludes=(),
       status=STATUS_GAP, evidence="no native output."),
)

PRIMITIVES: tuple[PrimitiveDefinition, ...] = (
    _DAMAGE + _DOT + _TIMING + _COST + _HIT + _TARGETS + _DEFENCE + _SIMULATOR)

BY_ID: Mapping[str, PrimitiveDefinition] = {d.primitive_id: d for d in PRIMITIVES}
BY_NATIVE_KEY: Mapping[str, PrimitiveDefinition] = {
    d.native_key: d for d in PRIMITIVES if d.native_key is not None}

#: The categories P02-T04 was told to inventory, mapped to the primitives that
#: cover each one. A P07 consumer looks here, not at raw output keys.
CATEGORIES: Mapping[str, tuple[str, ...]] = {
    "damage_per_hit_or_use": ("damage_per_use", "hit_damage_per_second",
                              "combined_damage", "aggregate_damage_per_second"),
    "damage_over_time": ("dot_damage_per_second", "dot_instance_damage_per_second",
                         "skill_effect_duration_s", "dot_reapplication_cost_s"),
    "attack_or_cast_time": ("use_rate_per_second", "use_time_s",
                            "trigger_rate_per_second", "setup_time_s"),
    "resource_cost": ("mana_cost_per_use", "mana_cost_per_second",
                      "life_cost_per_use", "spirit_total", "spirit_unreserved"),
    "cooldown": ("cooldown_s",),
    "hit_probability": ("hit_probability_pct", "crit_chance_pct"),
    "target_count": ("projectiles_per_use", "pierce_count", "chain_count",
                     "area_of_effect_radius_pob", "area_of_effect_radius_m",
                     "targets_hit_per_use", "projectile_overlap_multiplier"),
    "defences": ("life", "energy_shield", "mana", "armour", "evasion",
                 "fire_resist_pct", "cold_resist_pct", "lightning_resist_pct",
                 "chaos_resist_pct", "effective_hit_pool",
                 "max_physical_hit_taken", "block_chance_pct",
                 "movement_speed_mod"),
    "sustained_performance": ("sustained_damage_per_second",),
}


def resolve_unit(definition: PrimitiveDefinition,
                 show_average: bool | None) -> str | None:
    """The unit a value may be read under, or None when it is unresolved.

    Only ``combined_damage`` is conditional today: PoB writes ``AverageDamage``
    into ``CombinedDPS`` for skills whose data sets ``showAverage``, so the
    same key is damage per use for those skills and damage per second for the
    rest. Guessing costs a factor of the skill's use rate.
    """
    if definition.status != STATUS_CONDITIONAL:
        return definition.unit
    if definition.primitive_id != "combined_damage":
        return None
    if show_average is None:
        return None
    return "damage per use" if show_average else "damage per second"


def declare(values: Mapping[str, Any], *, show_average: bool | None = None
            ) -> tuple[dict[str, DeclaredPrimitive], tuple[PrimitiveGap, ...]]:
    """Split raw engine outputs into declared primitives and gaps.

    A primitive whose native key is absent from ``values`` is a gap. It is not
    zero, not a neutral multiplier and not the previous build's number.
    """
    declared: dict[str, DeclaredPrimitive] = {}
    gaps: list[PrimitiveGap] = []
    for definition in PRIMITIVES:
        if definition.native_key is None:
            gaps.append(PrimitiveGap(
                primitive_id=definition.primitive_id, native_key=None,
                kind="unsupported_rule",
                explanation="the pinned engine supplies no output for this "
                            "primitive; %s" % definition.evidence,
                needed_evidence="an encounter model that computes it, or an "
                                "engine extension reviewed as such",
                owner=definition.owner))
            continue
        if definition.native_key not in values:
            gaps.append(PrimitiveGap(
                primitive_id=definition.primitive_id,
                native_key=definition.native_key, kind="missing_input",
                explanation="the engine did not report %s for this build and "
                            "state" % definition.native_key,
                needed_evidence="an evaluation whose main skill produces %s"
                                % definition.native_key,
                owner=definition.owner))
            continue
        unit = resolve_unit(definition, show_average)
        if unit is None:
            gaps.append(PrimitiveGap(
                primitive_id=definition.primitive_id,
                native_key=definition.native_key, kind="missing_input",
                explanation="the unit of %s depends on %s, which this snapshot "
                            "does not carry" % (definition.native_key,
                                                definition.resolved_by),
                needed_evidence="the engine fact named in resolved_by",
                owner=definition.owner))
            continue
        declared[definition.primitive_id] = DeclaredPrimitive(
            definition=definition, value=values[definition.native_key], unit=unit)
    return declared, tuple(gaps)
