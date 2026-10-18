"""Registry ``p06-flicker-v1``: every dependency of the P09-T01.1 Flicker seed
and of ``flicker_sustained_v1`` (P06-T01).

Statuses record what is established on 2026-10-18, not what the game does:

* ``owner: pob`` with ``implemented/untested``: PoB calculates the effect on
  the pinned engine. Parsing is not validation, so these stay untested.
* ``owner: simulator`` with ``unsupported``: the rule is known from the
  catalog but no code here calculates it yet (P07).
* ``support: unknown``: how the effect behaves is not established. Evidence
  resolves it through :mod:`pob2opt.coverage.resolution`, never an edit here.

Mechanic ids reuse the ``docs/evidence/P09-T01.1/mechanics.json`` ids where
that extract cites the mechanic, so P09 DataGaps link to these rules.
"""

from __future__ import annotations

from ..domain.enums import RuleOwner, RuleSupport, RuleValidation
from .registry import MechanicsRegistry, RuleEntry, make_rule

REGISTRY_ID = "p06-flicker-v1"
REGISTRY_VERSION = "1"

DPS = "flicker_sustained_v1"
ENCOUNTERS = ("p09-flk-clear-dense", "p09-flk-clear-spread",
              "p09-flk-boss-short", "p09-flk-boss-sustained")
ALL_SCENARIOS = (DPS,) + ENCOUNTERS

MECH = "docs/evidence/P09-T01.1/mechanics.json#"
CHARGE_TABLE = "docs/evidence/P09-T01.1/pob-charge-table.json"
PROBE = "docs/evidence/P06/seed-engine-mod-support.json"
PROTOCOL = "benchmarks/p09-flicker-v1/protocol.md"
GAP = "gap-p09-t011-"

POB, SIM, SCN = RuleOwner.POB, RuleOwner.SIMULATOR, RuleOwner.SCENARIO
IMPL, PART, UNSUP, UNK = (RuleSupport.IMPLEMENTED, RuleSupport.PARTIAL,
                          RuleSupport.UNSUPPORTED, RuleSupport.UNKNOWN)
UNTESTED, FIXTURE = RuleValidation.UNTESTED, RuleValidation.FIXTURE_CHECKED

ADAPTER = "pob2opt.evaluation.adapter"
ENGINE = "engine/pinned-checkout"
PATCH = "patch/profile-0.5.5e"
POB_MODS = "damage/pob-modifiers"


def _e(mechanic_id, title, domain, owner, support, validation=UNTESTED, *,
       subjects=(), deps=(), provides=(), critical=None, gaps=(), evidence=(),
       limitations=(), inputs=(), impl=None, damage_source=False,
       events=(), tests=()):
    if impl is None:
        impl = ADAPTER if owner is POB and support in (IMPL, PART) else "none"
    if owner is POB and mechanic_id not in (ENGINE, PATCH):
        deps = tuple(deps) + (ENGINE,)
    return RuleEntry(
        rule=make_rule(mechanic_id, owner=owner, support=support,
                       validation=validation, dependency_ids=sorted(set(deps)),
                       required_input_paths=inputs, implementation_ref=impl,
                       evidence_ids=evidence, limitations=limitations),
        title=title, domain=domain, subject_ids=tuple(subjects),
        provides_paths=tuple(provides), critical=critical,
        protocol_gap_ids=tuple(GAP + g for g in gaps),
        damage_source=damage_source, requires_events=tuple(events),
        tests=tuple(tests))


def _pob_support(skill_id, title, *, events=(), damage_source=False,
                 support=IMPL, limitations=(), deps=()):
    """A support whose effect PoB applies to the supported skill."""
    return _e("support/" + skill_id, title, "support", POB, support,
              subjects=("support:" + skill_id,), deps=(POB_MODS,) + tuple(deps),
              events=events, damage_source=damage_source,
              limitations=limitations or ("PoB parses the gem; correctness is not validated here.",))


def entries() -> list[RuleEntry]:
    flicker_evidence = (MECH + "skill/FlickerStrikePlayer",
                        MECH + "statdesc/flicker_strike_additional_flickers_from_power_charges",
                        MECH + "engine/removable-power-charges", CHARGE_TABLE)
    return [
        # ------------------------------------------------- engine and patch
        _e(ENGINE, "Pinned PoB checkout", "engine", POB, IMPL,
           subjects=("always",), gaps=("engine-checkout-state",),
           inputs=("/engine/pob_commit", "/engine/pob_dirty"),
           limitations=("Seed outputs were captured on an unchecked working tree.",)),
        _e(PATCH, "Patch profile 0.5.5e", "patch", SCN, PART,
           subjects=("always",), gaps=("patch-profile",),
           evidence=("docs/evidence/P02-T02.1/catalog-export.json",),
           limitations=("Compatibility is partial (P02-T02.1).",)),
        _e(POB_MODS, "Modifiers PoB parses from gems, tree and items", "damage",
           POB, PART, subjects=("passive:*", "item:*", "support:*"),
           limitations=("A parsed modifier is not a validated one.",
                        "Unparsed lines are reported per line by coverage analysis.")),

        # ------------------------------------------------- Flicker Strike
        _e("skill/FlickerStrikePlayer", "Flicker Strike damage per use", "damage",
           POB, IMPL, subjects=("skill:FlickerStrikePlayer",),
           deps=(POB_MODS, "resource/power-charges"), evidence=flicker_evidence,
           inputs=("/pob/FlickerStrikePlayer/AverageBurstDamage",
                   "/pob/FlickerStrikePlayer/AverageBurstHits",
                   "/pob/FlickerStrikePlayer/Speed"),
           provides=("skill.FlickerStrikePlayer.damage_per_use",),
           damage_source=True,
           limitations=("PoB reports AverageBurstDamage at forced charges; the charge "
                        "count must come from the rotation, not config.",)),
        _e("timing/flicker-strike-strike-duration", "Elapsed time of one Flicker use",
           "timing", SIM, PART, subjects=("skill:FlickerStrikePlayer",),
           deps=("skill/FlickerStrikePlayer",), gaps=("flicker-strike-timing",),
           limitations=("pob-cycle-v1 takes H(c) strikes of 1/S_F(c) each; unvalidated.",)),
        _e("activation/hit-and-run-reuse", "Hit and Run: usable after moving 10 m",
           "activation", SIM, UNK, subjects=("support:SupportHitAndRunPlayer",),
           critical="activation", gaps=("hit-and-run-movement", "spatial-unit"),
           evidence=(MECH + "support/SupportHitAndRunPlayer",
                     MECH + "statdesc/skill_unusable_until_moved_X_distance"),
           limitations=("Whether Flicker Strike's teleport counts as movement is an "
                        "owner statement only.",)),
        _e("support/SupportHitAndRunPlayer", "Hit and Run: 40% more skill speed",
           "timing", POB, IMPL, subjects=("support:SupportHitAndRunPlayer",),
           deps=("activation/hit-and-run-reuse", POB_MODS),
           evidence=(MECH + "support/SupportHitAndRunPlayer",)),
        _pob_support("SupportConcentratedAreaPlayer", "Concentrated Area"),
        _pob_support("SupportCloseCombatPlayerTwo", "Close Combat II",
                     limitations=("PoB uses its enemyDistance config for the distance.",)),
        _e("support/SupportPerpetualChargePlayer", "Perpetual Charge: 25% to keep a consumed charge",
           "resource", SIM, UNSUP, subjects=("support:SupportPerpetualChargePlayer",),
           deps=("resource/power-charges",), gaps=("charge-cycle-rules",),
           evidence=(MECH + "support/SupportPerpetualChargePlayer",
                     MECH + "statdesc/charge_skip_consume_chance_%")),
        _pob_support("SupportRakiatasFlowPlayer", "Rakiata's Flow"),

        # ------------------------------------------------- charges and Combo
        _e("resource/power-charges-max", "Maximum Power Charges", "resource", POB, IMPL,
           subjects=("always",), deps=(POB_MODS,), evidence=(MECH + "passive/65204",),
           inputs=("/pob/PowerChargesMax",),
           provides=("state.power_charges_max",)),
        _e("resource/power-charges", "Power Charge state over time", "resource", SIM, UNSUP,
           subjects=("skill:FlickerStrikePlayer", "skill:ChargedStaffPlayer"),
           deps=("resource/power-charges-max",), provides=("state.power_charges",),
           gaps=("charge-cycle-rules",),
           evidence=(MECH + "statdesc/cannot_gain_power_charges_during_skill",)),
        _e("resource/combo", "Combo state over time", "resource", SIM, UNSUP,
           subjects=("support:SupportCulminationPlayerTwo",), provides=("state.combo",),
           gaps=("charge-cycle-rules",),
           evidence=(MECH + "statdesc/skill_maximum_number_of_combo_stacks",)),
        _e("support/SupportCulminationPlayerTwo", "Culmination II: Combo from other melee strikes, expended on use",
           "resource", SIM, UNSUP, subjects=("support:SupportCulminationPlayerTwo",),
           deps=("resource/combo",), gaps=("charge-cycle-rules",),
           evidence=(MECH + "support/SupportCulminationPlayerTwo",)),
        _e("support/SupportAilithLineagePlayer", "Ailith's Chimes: Power Charge chance per Combo expended",
           "resource", SIM, UNSUP, subjects=("support:SupportAilithLineagePlayer",),
           deps=("resource/combo", "resource/power-charges"), gaps=("charge-cycle-rules",),
           evidence=(MECH + "support/SupportAilithLineagePlayer",
                     MECH + "statdesc/chance_%_to_gain_power_charges_per_combo_spent")),
        _e("passive/41751", "Martial Adept: additional Combo when gaining Combo", "resource",
           SIM, UNSUP, subjects=("passive:41751",), deps=("resource/combo",),
           gaps=("charge-cycle-rules",), evidence=(MECH + "passive/41751", PROBE),
           limitations=("PoB leaves both lines unparsed on the pin.",)),
        _e("passive/61586", "Martial Master: Combo from all Attack Hits", "resource",
           SIM, UNSUP, subjects=("passive:61586",), deps=("resource/combo",),
           gaps=("charge-cycle-rules",), evidence=(MECH + "passive/61586", PROBE),
           limitations=("PoB leaves both lines unparsed on the pin.",)),
        _e("passive/36643", "Additional Power Charge Chance (Martial Artist)", "resource",
           POB, IMPL, subjects=("passive:36643",), deps=(POB_MODS,),
           evidence=(MECH + "passive/36643",)),
        _e("resource/rage", "Rage state over time", "resource", SIM, UNSUP,
           subjects=("support:SupportRagePlayerTwo",), provides=("state.rage",),
           limitations=("Rage II grants Rage on hit; no simulator rule tracks Rage.",)),

        # ------------------------------------------------- Whirling Assault
        _e("skill/WhirlingAssaultPlayer", "Whirling Assault use time and damage", "timing",
           POB, IMPL, subjects=("skill:WhirlingAssaultPlayer",), deps=(POB_MODS,),
           inputs=("/pob/WhirlingAssaultPlayer/Time",),
           evidence=(MECH + "skill/WhirlingAssaultPlayer", CHARGE_TABLE),
           damage_source=True),
        _pob_support("SupportRagePlayerTwo", "Rage II", deps=("resource/rage",)),
        _pob_support("SupportOisinsOathPlayer", "Oisin's Oath: mana leech from elemental damage"),
        _e("support/SupportLivingLightningPlayerTwo", "Living Lightning II minions", "damage",
           SIM, UNK, subjects=("support:SupportLivingLightningPlayerTwo",),
           damage_source=True,
           limitations=("Minion creation and damage are not established.",)),

        # ------------------------------------------------- Charged Staff
        _e("skill/ChargedStaffPlayer", "Charged Staff buff damage and shockwave", "damage",
           POB, PART, subjects=("skill:ChargedStaffPlayer",), deps=(POB_MODS,),
           evidence=(MECH + "skill/ChargedStaffPlayer", CHARGE_TABLE),
           damage_source=True,
           limitations=("PoB reads the buff's per-charge damage from the same charges "
                        "Flicker Strike consumes.",)),
        _e("charges/charged-staff-consumption", "Charged Staff consumes all Power Charges; buff stacking",
           "resource", SIM, UNSUP, subjects=("skill:ChargedStaffPlayer",),
           deps=("resource/power-charges",),
           gaps=("charged-staff-shared-charges", "rotation-details")),
        _e("support/SupportInnervatePlayer", "Innervate: kill a Shocked enemy", "buff", POB, IMPL,
           subjects=("support:SupportInnervatePlayer",), deps=(POB_MODS,), events=("kill",)),
        _e("support/SupportBlazingCriticalPlayer", "Blazing Critical: crit imbues attacks with fire",
           "buff", SIM, UNK, subjects=("support:SupportBlazingCriticalPlayer",),
           limitations=("Buff uptime from critical hits is not established.",)),
        _pob_support("SupportEmbitterPlayer", "Embitter"),
        _e("support/SupportBhatairsVengeancePlayer", "Bhatair's Vengeance: freezing infuses cold",
           "buff", SIM, UNK, subjects=("support:SupportBhatairsVengeancePlayer",),
           limitations=("Freeze on the Pinnacle target and infusion uptime are not established.",)),
        _pob_support("SupportElementalArmamentPlayerTwo", "Elemental Armament II"),

        # ------------------------------------------------- persistent skills
        _e("skill/HeraldOfIcePlayer", "Herald of Ice explosions on shatter", "damage", POB, IMPL,
           subjects=("skill:HeraldOfIcePlayer",), deps=(POB_MODS,), damage_source=True,
           events=("kill",)),
        _e("skill/HeraldOfThunderPlayer", "Herald of Thunder bolts after killing a Shocked enemy",
           "damage", POB, IMPL, subjects=("skill:HeraldOfThunderPlayer",), deps=(POB_MODS,),
           damage_source=True, events=("kill",)),
        _e("skill/TrinityPlayer", "Trinity Affinity build-up", "buff", SIM, UNK,
           subjects=("skill:TrinityPlayer",),
           limitations=("Affinity is built by hits over time; PoB's assumed level is not "
                        "generated by the rotation.",)),
        _e("skill/MetaRemnantsOfKalguurPlayer", "Remnants of Kalguur on stun or kill", "buff",
           SIM, UNK, subjects=("skill:MetaRemnantsOfKalguurPlayer",), events=("stun_or_kill",),
           limitations=("Remnant creation and pickup are not modelled.",)),
        _e("skill/WindDancerPlayer", "Wind Dancer: evasion stages, released when hit", "buff",
           POB, IMPL, subjects=("skill:WindDancerPlayer",), deps=(POB_MODS,),
           events=("incoming_hit",), damage_source=True),
        _e("skill/GhostDancePlayer", "Ghost Dance: shrouds consumed when hit", "buff", POB, IMPL,
           subjects=("skill:GhostDancePlayer",), deps=(POB_MODS,), events=("incoming_hit",)),
        _e("skill/SanguineRevelryPlayer", "Sanguine Revelry: remnants from bleeding kills",
           "buff", SIM, UNK, subjects=("skill:SanguineRevelryPlayer",), events=("kill",)),
        _e("skill/WolfPouncePlayer", "Pounce", "damage", POB, IMPL,
           subjects=("skill:WolfPouncePlayer",), deps=(POB_MODS,), damage_source=True),
        _e("skill/MeleeQuarterstaffPlayer", "Quarterstaff default attack", "damage", POB, IMPL,
           subjects=("skill:MeleeQuarterstaffPlayer",), deps=(POB_MODS,), damage_source=True),
        _pob_support("SupportFireMasteryPlayer", "Fire Mastery"),
        _pob_support("SupportColdMasteryPlayer", "Cold Mastery"),
        _pob_support("SupportUhtredOmenPlayer", "Uhtred's Omen"),
        _pob_support("SupportFleetingRemnantsPlayerTwo", "Harmonic Remnants II", events=("stun_or_kill",)),
        _pob_support("SupportInterludePlayer", "Remnant Potency I", events=("stun_or_kill",)),
        _pob_support("SupportMarkForDeathPlayerTwo", "Mark for Death II"),
        _pob_support("SupportCooldownRecoveryPlayerTwo", "Cooldown Recovery II"),
        _pob_support("SupportRapidAttacksPlayerThree", "Rapid Attacks III"),
        _pob_support("SupportMagnifiedAreaPlayerTwo", "Magnified Area II"),
        _pob_support("SupportStunPlayerThree", "Stun III"),
        _pob_support("SupportFreezePlayer", "Freeze"),
        _pob_support("SupportBlindPlayerTwo", "Blind II"),
        _e("support/SupportConcussiveRunesPlayer", "Concussive Runes shockwave on heavy stun",
           "damage", SIM, UNK, subjects=("support:SupportConcussiveRunesPlayer",),
           damage_source=True, limitations=("Heavy stun on the target and Runic Ward are not modelled.",)),

        # ------------------------------------------------- mana and sustain
        _e("cost/mana-per-use", "Mana cost per skill use", "cost", POB, IMPL,
           subjects=("always",), deps=(POB_MODS,), evidence=(CHARGE_TABLE,),
           inputs=("/pob/FlickerStrikePlayer/ManaCost", "/pob/WhirlingAssaultPlayer/ManaCost")),
        _e("resource/mana-regeneration", "Mana regeneration and leech", "resource", POB, IMPL,
           subjects=("always",), deps=(POB_MODS,)),
        _e("resource/mana-flask", "Mana flask use and recovery", "resource", SIM, UNSUP,
           subjects=("always",), gaps=("sustain-cycle",)),
        _e("resource/mana-sustain", "Mana over the scenario window", "resource", SIM, UNSUP,
           subjects=tuple("scenario:" + s for s in ALL_SCENARIOS),
           deps=("cost/mana-per-use", "resource/mana-regeneration", "resource/mana-flask"),
           provides=("state.mana",), gaps=("sustain-cycle",)),

        # ------------------------------------------------- benchmark
        _e("attribution/flicker-sustained-v1", "Damage ownership for flicker_sustained_v1",
           "attribution", SIM, UNSUP, subjects=("scenario:" + DPS,),
           critical="attribution", gaps=("attribution-rules",),
           evidence=("docs/decisions/D07-flicker-strike-objective.md",),
           limitations=("No source is assigned until the attribution rule is accepted.",)),
        _e("initial-state/flicker-sustained-v1", "t = 0: 0 charges, 0 Combo, full mana and ES",
           "initial_state", SCN, IMPL, subjects=("scenario:" + DPS,),
           evidence=(PROTOCOL,),
           limitations=("A protocol choice awaiting reviewer acceptance.",)),
        _e("target/pinnacle-preset", "PoB Guardian/Pinnacle Boss enemy", "target", SCN, IMPL,
           FIXTURE, subjects=("scenario:" + DPS,),
           evidence=(MECH + "engine/pinnacle-enemy-preset", CHARGE_TABLE,
                     "docs/decisions/D07-flicker-strike-objective.md#amendment-2026-10-18")),
        _e("config/condition-sustain", "Config conditions must be generated by the build",
           "config", SIM, UNSUP, gaps=("config-conditions",),
           limitations=("D07: no free maximum-state toggles.",)),
        _e("config/enemyDistance", "Distance to the target used by PoB (placeholder 20)",
           "config", SCN, PART, subjects=("config:enemyDistance",),
           limitations=("PoB applies the placeholder; Close Combat II reads it. Flicker "
                        "Strike's own position relative to the target is not established.",)),
        _e("config/FlickerStrikeBypassCD", "PoB 'Bypass CD?' for Flicker Strike (default on)",
           "config", POB, UNK, subjects=("config:FlickerStrikeBypassCD",),
           evidence=(MECH + "engine/flicker-bypass-cd-config",),
           limitations=("Overrides Flicker Strike cooldown recovery; whether a cooldown "
                        "applies on the pin is not established.",)),
    ]


#: Each pob-cycle-v1 input (protocol.md) and the rule that owns it.
POB_CYCLE_INPUT_RULES = {
    "t_WA": "skill/WhirlingAssaultPlayer",
    "S_F(c)": "timing/flicker-strike-strike-duration",
    "H(c)": "skill/FlickerStrikePlayer",
    "D(c)": "skill/FlickerStrikePlayer",
    "C_max": "resource/power-charges-max",
    "p": "support/SupportAilithLineagePlayer",
    "K_max": "support/SupportCulminationPlayerTwo",
    "q": "support/SupportPerpetualChargePlayer",
    "g": "resource/combo",
    "m_F, m_WA": "cost/mana-per-use",
    "activation": "activation/hit-and-run-reuse",
    "attribution": "attribution/flicker-sustained-v1",
    "initial state": "initial-state/flicker-sustained-v1",
    "target": "target/pinnacle-preset",
    "mana sustain": "resource/mana-sustain",
    "Charged Staff": "charges/charged-staff-consumption",
}


def build_registry() -> MechanicsRegistry:
    return MechanicsRegistry(REGISTRY_ID, REGISTRY_VERSION, entries())
