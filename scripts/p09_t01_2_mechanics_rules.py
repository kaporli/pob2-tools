"""Flicker seed cycle mechanics and damage ownership rules (P09-T01.2).

    python scripts/p09_t01_2_mechanics_rules.py

Writes ``docs/evidence/P09-T01.2/mechanics-rules.json``: one record per rule
the pob-cycle-v1 computation needs, with its status, the rule text, its
parameters and the evidence behind it. Engine citations are resolved against
``external/PathOfBuilding-PoE2`` (or ``POB2_ROOT``) at the pin: file path,
file SHA-256 and the line numbers of the cited text. Values read from the
engine come from ``replay.json`` by JSON pointer. Web evidence is in
``web-evidence.json``.

Status meanings:

* ``resolved``: the pinned data, engine or replay settles the rule. A
  reviewer still accepts it before a score counts.
* ``conditional``: the rule needs one evidenced choice; each alternative is
  written out so the evaluator can run it as a separately labelled variant.
* ``blocking``: no evidenced rule exists; the named gap blocks a score.

Nothing here is a gameplay measurement.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
EVID = REPO_ROOT / "docs" / "evidence" / "P09-T01.2"
REPLAY = EVID / "replay.json"
WEB = EVID / "web-evidence.json"
OUT = EVID / "mechanics-rules.json"
PIN = "ce566eac45ea8a86477f513c7ee65a1ebe60014e"
REPLAY_REF = "docs/evidence/P09-T01.2/replay.json"
WEB_REF = "docs/evidence/P09-T01.2/web-evidence.json"
OWNER_REF = "docs/evidence/P09-T01.1/seed/manifest.json#owner_answers"
DECISION_2 = "docs/decisions/D07-flicker-strike-objective.md#amendment-2026-10-18-2"

#: How each rule stands under pob-community-v2 (D07 amendment 2): "waived"
#: rules only exist to generate charges or schedule activation in-model.
UNDER_COMMUNITY_METHOD = {
    "combo-gain-per-strike": "waived", "whirling-assault-own-combo": "waived",
    "ailith-surpassing-distribution": "waived", "perpetual-charge": "waived",
    "charged-staff-buff-ownership": "waived", "consumed-power-charge-recently": "waived",
    "hit-and-run-reuse": "waived",
}

#: (citation id, file under src/, exact text, optional anchor). Without an
#: anchor the text must occur once in the file; with one, the first
#: occurrence inside the block that starts at the anchor line is cited.
CITATIONS = [
    ("pob/flicker-description", "Data/Skills/act_int.lua",
     'description = "Teleport to an enemy and Strike them. Consumes Power Charges to perform additional teleporting Strikes on nearby enemies.",', 'skills["FlickerStrikePlayer"]'),
    ("pob/flicker-prediamage", "Data/Skills/act_int.lua",
     'activeSkill.skillData.averageBurstHits = 1 + strikesPerCharge', 'skills["FlickerStrikePlayer"]'),
    ("pob/flicker-strikes-per-charge", "Data/Skills/act_int.lua",
     '{ "flicker_strike_additional_flickers_from_power_charges", 2 },', 'skills["FlickerStrikePlayer"]'),
    ("pob/flicker-speed-more", "Data/Skills/act_int.lua",
     'mod("Speed", "MORE", 285, ModFlag.Attack),', 'skills["FlickerStrikePlayer"]'),
    ("pob/statdesc-no-charge-gain", "Data/StatDescriptions/skill_stat_descriptions.lua",
     'text="You cannot gain Power Charges while using this Skill"'),
    ("pob/charged-staff-description", "Data/Skills/act_int.lua",
     'description = "Consume all Power Charges to charge your Quarterstaff with electricity, adding Lightning damage and a Lightning shockwave to your Quarterstaff Attacks. Reusing this skill while the Buff is active adds to the Buff\'s duration and damage.",', 'skills["ChargedStaffPlayer"]'),
    ("pob/charged-staff-duration", "Data/Skills/act_int.lua",
     '{ "charged_staff_buff_duration_per_stack_ms", 6000 },', 'skills["ChargedStaffPlayer"]'),
    ("pob/charged-staff-requires", "Data/Skills/act_int.lua",
     '{ "active_skill_requires_X_power_charges", 1 },', 'skills["ChargedStaffPlayer"]'),
    ("pob/charged-shockwave-skill", "Data/Skills/act_int.lua",
     'skills["ChargedStaffShockwavePlayer"] = {'),
    ("pob/removable-power-charges", "Modules/CalcPerform.lua",
     'local removablePowerCharges = m_max(output.PowerCharges - output.PowerChargesMin, 0)'),
    ("pob/consumed-recently-parse", "Modules/ModParser.lua",
     '["if you\'ve consumed an? (%D+) charge recently"] = function(charge) return { tag = { type = "Multiplier", var = "Removable" .. firstToUpper(charge) .. "Charge", limit = 1 }} end,'),
    ("pob/perpetual-charge-description", "Data/Skills/sup_int.lua",
     'description = "Supports skills that consume Power, Frenzy or Endurance Charges on use, giving them a chance not to remove each Charge while still gaining the benefits of consuming them.",', 'skills["SupportPerpetualChargePlayer"]'),
    ("pob/perpetual-charge-chance", "Data/Skills/sup_int.lua",
     '{ "charge_skip_consume_chance_%", 25 },', 'skills["SupportPerpetualChargePlayer"]'),
    ("pob/ailith-description", "Data/Skills/sup_dex.lua",
     'description = "Supports Skills which can expend Combo. On expending Combo with Supported Skills, you have a chance to gain Power Charges based on the amount of Combo expended.",', 'skills["SupportAilithLineagePlayer"]'),
    ("pob/statdesc-ailith-surpassing", "Data/StatDescriptions/gem_stat_descriptions.lua",
     'text="{0}% Surpassing chance to gain a Power Charge when expending Combo with Supported Skills per Combo expended"'),
    ("pob/culmination-description", "Data/Skills/sup_dex.lua",
     'description = "Supports Melee Attack Skills. Supported Skills gain Combo when you successfully Strike Enemies with other Melee Attacks. Supported Skills reset their Combo on use, dealing more Damage the higher Combo you had on use. Cannot support skills which already gain Combo. Cannot modify the Skills of Minions.",', 'skills["SupportCulminationPlayerTwo"]'),
    ("pob/culmination-cap", "Data/Skills/sup_dex.lua",
     '{ "skill_maximum_number_of_combo_stacks", 10 },', 'skills["SupportCulminationPlayerTwo"]'),
    ("pob/culmination-decay", "Data/Skills/sup_dex.lua",
     '{ "base_combo_stacks_decay_delay_ms", 6000 },', 'skills["SupportCulminationPlayerTwo"]'),
    ("pob/hit-and-run-description", "Data/Skills/sup_dex.lua",
     'description = "Supports Attack Skills you use yourself which do not already have some Condition for use. Supported Skills can only be used after you have moved a certain distance, but have massively increased Skill Speed. Cannot support Skills which have a cooldown.",', 'skills["SupportHitAndRunPlayer"]'),
    ("pob/hit-and-run-distance", "Data/Skills/sup_dex.lua",
     '{ "skill_unusable_until_moved_X_distance", 100 },', 'skills["SupportHitAndRunPlayer"]'),
    ("pob/whirling-assault-description", "Data/Skills/act_int.lua",
     'description = "Advance while hitting enemies around you with a series of spinning Strikes.",', 'skills["WhirlingAssaultPlayer"]'),
    ("pob/predators-mark-description", "Data/Skills/act_str.lua",
     'description = "Mark a target, causing it to take increased damage based on how many of the target\'s enemies are near to it. If the target dies, the Mark will Activate to Trigger the Summon Wolf skill and Consume the Mark.",', 'skills["WolfPounceMarkPlayer"]'),
    ("pob/predators-mark-minion-count", "Modules/CalcPerform.lua",
     'env.player.modDB:NewMod("Multiplier:MinionPresenceCount", "BASE", output[activeSkill.minion.minionData.limit], "Config", { type = "Condition", var = "Combat" })'),
    ("pob/flicker-bypass-cd", "Modules/ConfigOptions.lua",
     'modList:NewMod("CooldownRecovery", "OVERRIDE", 0, "Config", { type = "SkillName", skillName = "Flicker Strike", includeTransfigured = true })'),
    ("pob/close-combat-ramp", "Data/Skills/sup_dex.lua",
     'mod("Damage", "MORE", nil, 0, 0, { type = "DistanceRamp", ramp = {{10,1},{35,0}} }),',
     'skills["SupportCloseCombatPlayerTwo"]'),
    ("pob/enemy-distance-placeholder", "Modules/ConfigOptions.lua",
     '{ var = "enemyDistance", type = "count", label = "Distance to enemy:", tooltip = "10 units equals 1 metre'),
    ("pob/mana-cost-upfront", "Modules/CalcOffence.lua",
     '["Mana"] = { type = "Mana", upfront = true, percent = false, text = "mana", baseCost = 0, baseCostRaw = 0, totalCost = 0, baseCostNoMult = 0, finalBaseCost = 0 },'),
    ("pob/mana-cost-output", "Modules/CalcOffence.lua", 'local costName = resource.."Cost"'),
    ("pob/mana-per-second-cost", "Modules/CalcOffence.lua",
     'output[usedResource.."PerSecondCost"] = (output[usedResource.."PerSecondCost"] or 0)+ output[resource.."Cost"] * useSpeed'),
    ("pob/mageblood-legacies", "Modules/CalcPerform.lua", 'if modDB:Flag(nil, "MagebloodEquipped") then'),
    ("pob/mageblood-parse", "Modules/ModParser.lua", '["legacy of (%w+)"] = function (_, flask) return {'),
    ("pob/ultimate-mana-flask", "Data/Bases/flask.lua",
     'flask = { mana = 310, duration = 3, chargesUsed = 10, chargesMax = 75, },'),
]

#: Passive node text from the seed (docs/evidence/P09-T01.1/mechanics.json).
T011_MECHANICS = "docs/evidence/P09-T01.1/mechanics.json"


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def resolve_citations(root: Path) -> dict:
    head = subprocess.run(["git", "-C", str(root), "rev-parse", "HEAD"], check=True,
                          capture_output=True, text=True).stdout.strip()
    status = subprocess.run(["git", "-C", str(root), "status", "--porcelain=v1",
                             "--untracked-files=all"], check=True, capture_output=True,
                            text=True).stdout.strip()
    if head != PIN or status:
        raise SystemExit("refusing: %s is not a clean checkout of %s" % (root, PIN))
    out = {}
    for cid, rel, text, *anchor in CITATIONS:
        path = root / "src" / rel
        lines = path.read_text(encoding="utf-8").splitlines()
        if anchor:
            starts = [i for i, line in enumerate(lines) if line.startswith(anchor[0])]
            if len(starts) != 1:
                raise SystemExit("citation %s: anchor %s found %d times" % (cid, anchor[0], len(starts)))
            block = []
            for i in range(starts[0], len(lines)):
                if i > starts[0] and lines[i].startswith("skills["):
                    break
                block.append(i)
            hits = [i + 1 for i in block if text in lines[i]][:1]
        else:
            hits = [i + 1 for i, line in enumerate(lines) if text in line]
        if len(hits) != 1:
            raise SystemExit("citation %s: %d matches in %s" % (cid, len(hits), rel))
        out[cid] = {"path": "src/" + rel, "file_sha256": _sha(path), "line": hits[0], "text": text}
        if anchor:
            out[cid]["block"] = anchor[0]
    return out


def ptr(path: str) -> str:
    return REPLAY_REF + "#" + path


def rules(replay: dict) -> list[dict]:
    seed = {r["forced_power_charges"]: r for r in replay["flicker_seed"]}
    bench = {r["forced_power_charges"]: r for r in replay["benchmark_documents"]["flicker_benchmark"]}
    bench_off = {r["forced_power_charges"]: r
                 for r in replay["benchmark_documents"]["flicker_benchmark_charged_staff_disabled"]}
    no_hr = replay["benchmark_documents"]["flicker_benchmark_no_hit_and_run"][0]
    wa = replay["whirling_assault"]
    cs = replay["charged_staff"]
    diag = replay["diagnostics"]["imported"]
    probes = {p["probe"]: p for p in replay["config_probes"]}
    cs_duration = replay["diagnostics"]["charged_staff_duration"]
    flask = diag["flasks"]["Flask 2"]["flaskData"]
    return [
        {"rule_id": "flicker-extra-strikes", "status": "resolved",
         "question": "Strikes per Flicker Strike use at c Power Charges.",
         "rule": "H(c) = 1 + 2c, c = Power Charges held at use (removable charges).",
         "parameters": {"H": {str(c): seed[c]["AverageBurstHits"] for c in seed}},
         "evidence": ["pob/flicker-description", "pob/flicker-strikes-per-charge",
                      "pob/flicker-prediamage", "pob/removable-power-charges",
                      "web/fextralife-flicker-strike", ptr("/flicker_seed")]},
        {"rule_id": "flicker-no-charge-gain", "status": "resolved",
         "question": "Can Power Charges be gained while Flicker Strike is in use?",
         "rule": "No. Charges gained by Whirling Assault arrive before the Flicker Strike use starts.",
         "evidence": ["pob/statdesc-no-charge-gain", "web/fextralife-flicker-strike"]},
        {"rule_id": "flicker-strike-timing", "status": "conditional",
         "gap_id": "gap-p09-t011-flicker-strike-timing",
         "question": "Elapsed time of one Flicker Strike use with H strikes.",
         "rule": "Proposed: H(c) / S_F seconds, strikes evenly spaced at 1 / S_F; S_F is PoB Speed (strikes per second). Unvalidated: no evidence on teleport travel time.",
         "parameters": {"S_F_with_hit_and_run": bench[0]["Speed"], "S_F_without_hit_and_run": no_hr["Speed"]},
         "evidence": ["pob/flicker-speed-more", ptr("/benchmark_documents/flicker_benchmark"),
                      ptr("/diagnostics/charges_5/speed_more")]},
        {"rule_id": "flicker-mana-charging", "status": "resolved",
         "question": "Is Flicker Strike's mana cost paid once per use or once per strike?",
         "rule": "Once per use, by the owner's community-PoB method: PoB's ManaCost is the upfront cost of one skill use (pob/mana-cost-upfront, pob/mana-cost-output), and the skill text describes one use with additional strikes. PoB's ManaPerSecondCost multiplies that cost by the attack speed (pob/mana-per-second-cost), which for Flicker Strike is the strike rate, so it is not used. Not verified in game.",
         "parameters": {"mana_per_use": seed[0]["ManaCost"]},
         "evidence": ["pob/mana-cost-upfront", "pob/mana-cost-output", "pob/mana-per-second-cost",
                      "pob/flicker-description", DECISION_2, ptr("/flicker_seed/0/ManaCost")]},
        {"rule_id": "perpetual-charge", "status": "resolved",
         "question": "How many consumed Power Charges stay after a Flicker Strike use?",
         "rule": "Each consumed charge independently stays with probability q = 0.25 and still counts as consumed (Flicker Strike's extra strikes and 'consumed recently' effects use the full count). Carry = Binomial(c, 0.25). Applies to Flicker Strike only: Perpetual Charge is socketed in its group, not with Charged Staff.",
         "parameters": {"q": 0.25},
         "evidence": ["pob/perpetual-charge-description", "pob/perpetual-charge-chance",
                      "docs/evidence/P09-T01.1/seed/skill-groups.json"]},
        {"rule_id": "ailith-surpassing-distribution", "status": "resolved",
         "question": "Power Charges gained when Whirling Assault expends K Combo.",
         "rule": "Surpassing chance P = 25% x K. Gain floor(P / 100) charges, plus one more with probability (P mod 100) / 100, then cap at maximum Power Charges. At K = 10: 2 charges, plus a third with probability 0.5.",
         "parameters": {"p_per_combo": 0.25},
         "evidence": ["pob/ailith-description", "pob/statdesc-ailith-surpassing",
                      "web/poe2wiki-surpassing-chance"],
         "limitation": "The Surpassing definition comes from a search summary of the community wiki, which refused automated access. A reviewer may require the page itself or an in-game tooltip capture."},
        {"rule_id": "combo-gain-per-strike", "status": "blocking",
         "gap_id": "gap-p09-t011-charge-cycle-rules",
         "question": "Combo the Culmination-supported Whirling Assault gains from one Flicker Strike use.",
         "rule": "Unresolved. Culmination II: Combo is gained when you successfully Strike with other Melee Attacks; Martial Adept: one additional Combo when Combo is gained. Whether each teleporting strike is a separate gain event, or the use is one, is not established.",
         "alternatives": [
             {"variant": "per_strike", "combo_per_flicker_use": "min(10, 2 x H(c))",
              "consequence": "10 Combo at every use with c >= 2; at c = 0 a use gives 2 Combo."},
             {"variant": "per_use", "combo_per_flicker_use": 2,
              "consequence": "Whirling Assault expends at most 2 Combo (plus its own hits, see whirling-assault-own-combo): 50% chance of 1 charge per cycle."}],
         "conflict": "The owner's rotation reads 'whirling assault to get 5 power charges'. Under per_strike, one Whirling Assault expending 10 Combo gives 2 or 3 charges; 5 needs carried charges from Perpetual Charge. Under per_use, far fewer. Neither alternative explains 5 from one Whirling Assault use, so at least one rule here differs from the game or the statement describes a typical, not a guaranteed, state.",
         "evidence": ["pob/culmination-description", "pob/culmination-cap",
                      T011_MECHANICS + "#passive/41751", T011_MECHANICS + "#passive/61586", OWNER_REF,
                      "web/forum-3591721-combo", "web/game8-combo"]},
        {"rule_id": "whirling-assault-own-combo", "status": "blocking",
         "gap_id": "gap-p09-t011-charge-cycle-rules",
         "question": "Does Whirling Assault gain Combo from its own hits?",
         "rule": "Unresolved. Culmination II grants Combo for strikes with other Melee Attacks; Martial Master grants Combo from all Attack Hits. Which wins for the supported skill itself, and how many hits one Whirling Assault use performs (PoB gives damage per use, not a hit count), is not established.",
         "alternatives": [{"variant": "no_own_combo"},
                          {"variant": "own_hits_count", "missing": "hits per Whirling Assault use"}],
         "evidence": ["pob/culmination-description", "pob/whirling-assault-description",
                      T011_MECHANICS + "#passive/61586", ptr("/whirling_assault")]},
        {"rule_id": "combo-cap-and-decay", "status": "resolved",
         "question": "Combo cap and decay for the supported Whirling Assault.",
         "rule": "Cap 10 on the stored count; all Combo is expended on use; decay starts 6.0 s after the last gain. A cycle that waits (for mana, Hit and Run or Charged Staff) longer than 6.0 s after the last Flicker strike loses its Combo.",
         "parameters": {"K_max": 10, "decay_delay_s": 6.0},
         "evidence": ["pob/culmination-cap", "pob/culmination-decay"]},
        {"rule_id": "whirling-assault-use", "status": "resolved",
         "question": "Whirling Assault time and mana per use.",
         "rule": "t_WA = PoB Time with group 8 as main skill; mana per use = PoB ManaCost.",
         "parameters": {"t_WA_s": wa["Time"], "mana": wa["ManaCost"]},
         "evidence": [ptr("/whirling_assault")]},
        {"rule_id": "charged-staff-use", "status": "resolved",
         "question": "Charged Staff time, mana and charge use per press.",
         "rule": "One press takes PoB Time, costs PoB ManaCost, needs at least 1 Power Charge and consumes all held charges (s = charges held). Perpetual Charge does not apply (not in its group).",
         "parameters": {"t_CS_s": cs["Time"], "mana": cs["ManaCost"]},
         "evidence": ["pob/charged-staff-description", "pob/charged-staff-requires", ptr("/charged_staff")]},
        {"rule_id": "charged-staff-buff-ownership", "status": "conditional",
         "gap_id": "gap-p09-t011-charged-staff-shared-charges",
         "question": "How much added lightning the Charged Staff buff gives Flicker Strike's strikes, and for how long.",
         "rule": "Proposed: the buff's stacks equal the charges Charged Staff consumed at its press (s), independent of the charges Flicker Strike later consumes; it lasts 6 s per stack. A Flicker strike under a buff of s stacks deals per-strike damage A_CS(s) = PoB AverageDamage at s forced charges with Charged Staff enabled; with no buff, A_0 = the Charged Staff disabled value. PoB itself reads both from the current charge count, so its AverageBurstDamage with Charged Staff enabled is not used directly.",
         "parameters": {"A_CS(s)_benchmark": {str(s): bench[s]["AverageDamage"] for s in bench if s >= 1},
                        "A_no_buff_consumed_recently": bench_off[1]["AverageDamage"],
                        "A_no_buff_not_consumed_recently": bench_off[0]["AverageDamage"],
                        "buff_duration_s_per_stack": 6.0},
         "open": ["Refresh rule: 'Reusing this skill while the Buff is active adds to the Buff's duration and damage' gives no cap or formula.",
                  "Press period N (owner Q10 answer: once per N cycles; N not yet given) -> gap-p09-t012-charged-staff-period.",
                  "A_CS(s) also includes the 'consumed a Power Charge recently' effects, which PoB ties to the same charge count; for a strike with 0 charges consumed recently this mixes two states (pob/consumed-recently-parse)."],
         "evidence": ["pob/charged-staff-description", "pob/charged-staff-duration",
                      "pob/removable-power-charges", "pob/consumed-recently-parse",
                      ptr("/benchmark_documents"), ptr("/diagnostics/charges_5/lightning_min")]},
        {"rule_id": "consumed-power-charge-recently", "status": "conditional",
         "gap_id": "gap-p09-t011-charged-staff-shared-charges",
         "question": "When do the seed's three 'if you've consumed a Power Charge Recently' passives apply?",
         "rule": "PoB applies them whenever the current skill has a removable charge (pob/consumed-recently-parse), i.e. at c >= 1. Proposed for the cycle: they apply to a strike when any Power Charge was consumed in the previous 4 s (by Flicker Strike or Charged Staff); the A values with and without them are both captured. 'Recently' = 4 s is the game's general definition and is not in the pinned data.",
         "parameters": {"A_without": bench_off[0]["AverageDamage"], "A_with": bench_off[1]["AverageDamage"]},
         "evidence": ["pob/consumed-recently-parse", ptr("/diagnostics/charges_5/conditional_mods")]},
        {"rule_id": "hit-and-run-reuse", "status": "blocking",
         "gap_id": "gap-p09-t011-hit-and-run-movement",
         "question": "Is Flicker Strike usable again after each use, and at what speed?",
         "rule": "Unresolved. The supported skill becomes usable after moving 10 metres and unusable again after use. Nothing pinned or retrieved says whether Flicker Strike's teleport, or Whirling Assault's advance, counts as moving. Owner statement (Q5) only.",
         "alternatives": [
             {"variant": "teleport_reenables", "basis": "owner Q5, unconfirmed", "S_F": bench[0]["Speed"],
              "extra_time_s": 0},
             {"variant": "no_hit_and_run", "basis": "the support removed: no activation condition, no 40% more skill speed",
              "S_F": no_hr["Speed"], "extra_time_s": 0,
              "note": "A different build from the seed; evaluated as a labelled variant."},
             {"variant": "timed_movement", "basis": "an explicit 10 m movement action before each Flicker Strike use",
              "S_F": bench[0]["Speed"], "extra_time_s": None,
              "missing": "movement speed in metres per second for the seed; PoB has no metre-based movement output (gap-p09-t011-spatial-unit)"}],
         "evidence": ["pob/hit-and-run-description", "pob/hit-and-run-distance",
                      "web/fextralife-hit-and-run", OWNER_REF,
                      ptr("/benchmark_documents/flicker_benchmark_no_hit_and_run")]},
        {"rule_id": "pounce-predators-mark", "status": "resolved",
         "question": "Does the benchmark keep Pounce's Predator's Mark?",
         "rule": "No. PoB applies the mark as 3% increased damage taken per minion in presence and counts Whirling Assault's eight Living Lightning minions, giving the enemy 24% increased damage taken. Owner Q4 keeps Pounce out of the rotation, and the mark needs a Pounce use the benchmark does not schedule. Benchmark documents disable Pounce (group 4); Flicker Strike per-strike damage falls by the factor 1 / 1.24.",
         "parameters": {"seed_to_benchmark_damage_ratio": bench[5]["AverageDamage"] / seed[5]["AverageDamage"]},
         "evidence": ["pob/predators-mark-description", "pob/predators-mark-minion-count", OWNER_REF,
                      ptr("/group_sweep"), ptr("/diagnostics/charges_5/enemy_mods")]},
        {"rule_id": "persistent-buffs", "status": "resolved",
         "question": "Which buff states feeding Flicker Strike are legitimate at t = 0?",
         "rule": "Herald of Ice and Herald of Thunder (their 'affected by a Herald' passives), Wind Dancer, Ghost Dance, Trinity, Remnants of Kalguur are persistent Spirit skills (owner Q4) and stay. Disabling them one at a time changes Flicker Strike damage only for the two heralds. Full Life holds: Chaos Inoculation sets maximum life to 1 and the benchmark has no incoming damage.",
         "evidence": [OWNER_REF, ptr("/group_sweep"), ptr("/diagnostics/imported/player_conditions")]},
        {"rule_id": "pob-default-states", "status": "resolved",
         "question": "Which PoB defaults raise Flicker Strike damage without the rotation generating them?",
         "rule": "After the Pounce change, none found among conditional modifiers and enemy modifiers. Rage is 0, Onslaught off, Shock off, Trinity resonance 0, Combo not used by Flicker Strike: these understate damage the build may generate and are not counted. Mageblood's 42% increased Speed is an item modifier PoB applies without a condition; it stays as PoB's model under the D07 amendment. The imported config inputs (inDemonForm, touchedDebuffsCount, purpleFlameStacks, targetBrandedEnemy, SecondsSinceInevitableCrit, companionInPresence and similar) feed no Flicker Strike modifier on this build.",
         "evidence": [ptr("/diagnostics/imported/config_mods"), ptr("/diagnostics/imported/config_enemy_mods"),
                      ptr("/diagnostics/charges_5/conditional_mods"), ptr("/diagnostics/charges_5/enemy_mods"),
                      ptr("/diagnostics/charges_5/outputs")]},
        {"rule_id": "mana-sustain", "status": "resolved",
         "question": "Mana available over the 120 s window.",
         "rule": "Pool and regeneration from PoB; the seed's one mana flask (Flask 2) from PoB flaskData: its recovery per use, instant part, duration, charges per use, maximum and 0.25 charges per second; no kill charges or mana on kill on one non-dying target. Mageblood in the pinned PoB grants Mage's Legacy stat bonuses (here Jade x2, Silver, Diamond) and does not make flasks permanent or change their charges (pob/mageblood-parse, pob/mageblood-legacies). Protocol choices for review: flask charges full at t = 0, the flask used whenever its recovery fits or a cost is unaffordable, never overlapping, no action time. The evaluation waits for mana before an unaffordable action; that waiting counts inside the window.",
         "parameters": {"mana_max": diag["outputs"]["Mana"], "mana_regen_per_s": diag["outputs"]["ManaRegenRecovery"],
                        "flask_mana_per_use": flask["manaTotal"], "flask_instant_fraction": flask["instantPerc"] / 100,
                        "flask_duration_s": flask["duration"], "flask_charges_per_use": flask["chargesUsed"],
                        "flask_charges_max": flask["chargesMax"], "flask_charges_per_s": flask["gainBase"]},
         "implication": "At 5 charges one Whirling Assault plus one Flicker Strike costs %d mana per cycle against %.1f mana per second of regeneration plus the flask; the rotation cannot run back to back and the evaluation waits for mana." % (wa["ManaCost"] + seed[0]["ManaCost"], diag["outputs"]["ManaRegenRecovery"]),
         "evidence": ["pob/ultimate-mana-flask", "pob/mageblood-parse", "pob/mageblood-legacies",
                      ptr("/diagnostics/imported/flasks"), ptr("/diagnostics/imported/flask_mods"),
                      ptr("/diagnostics/imported/outputs"), OWNER_REF,
                      "docs/evidence/P09-T01.2/community-cycle.json"]},
        {"rule_id": "charged-staff-period", "status": "resolved",
         "question": "How often Charged Staff is pressed.",
         "rule": "Owner Q10: once per N cycles; owner decision 2026-10-18 (2): Whirling Assault, Charged Staff, then Whirling Assault and Flicker Strike until the buff expires, repeated. The period follows from the buff duration: 6 s per stack (ChargedStaffBuffDuration) x (1 + 25% increased duration on the seed) x stacks consumed. Each press costs its own time and mana.",
         "parameters": {"buff_s_per_stack": cs_duration["per_stack_ms_base"] / 1000 * (1 + cs_duration["duration_inc"] / 100) * cs_duration["duration_more"],
                        "N": "derived per timeline"},
         "evidence": [OWNER_REF, DECISION_2, "pob/charged-staff-duration", ptr("/diagnostics/charged_staff_duration")]},
        {"rule_id": "flicker-bypass-cd-default", "status": "resolved",
         "question": "Does PoB's default 'Bypass CD?' for Flicker Strike change the seed's numbers?",
         "rule": "No. The import does not write FlickerStrikeBypassCD; PoB defaults it on and adds CooldownRecovery OVERRIDE 0 for Flicker Strike. The pinned Flicker Strike has no cooldown, and switching the option off leaves every captured output unchanged. The benchmark may leave it at the default.",
         "evidence": ["pob/flicker-bypass-cd", ptr("/config_probes"),
                      ptr("/diagnostics/imported/config_mods")]},
        {"rule_id": "enemy-distance", "status": "conditional",
         "gap_id": "gap-p09-t011-config-conditions",
         "question": "Distance between the character and the target for Close Combat II.",
         "rule": "PoB uses its placeholder enemyDistance 20 (2 m) when the document sets none; Close Combat II gives 30% more damage at 1 m or less, falling to 0 at 3.5 m, so 18% at 2 m. Flicker Strike teleports to its target, but the resulting distance is not established. Proposed: keep the placeholder (the value the seed was imported with) and report the sensitivity.",
         "parameters": {"per_strike_at_1m": probes["enemyDistance_10"]["AverageDamage"],
                        "per_strike_at_2m_default": probes["default"]["AverageDamage"],
                        "per_strike_at_3_5m": probes["enemyDistance_35"]["AverageDamage"]},
         "evidence": ["pob/close-combat-ramp", "pob/enemy-distance-placeholder", ptr("/config_probes")]},
        {"rule_id": "way-of-the-stonefist", "status": "conditional",
         "gap_id": "gap-p09-t011-config-conditions",
         "question": "PoB leaves Way of the Stonefist unparsed. Does the seed lose its effect?",
         "rule": "Not for the base type: the imported gloves already are 'Runeforged Fists of Stone', so the account API returned the transformed item. Whether their explicit modifiers are the transformed, stronger versions is not established; PoB evaluates the text as imported. Martial Adept and Martial Master are also unparsed by PoB; their Combo effects belong to the cycle rules (combo-gain-per-strike, whirling-assault-own-combo), not to PoB damage.",
         "evidence": ["docs/evidence/P09-T01.1/seed/items-raw.json",
                      "docs/evidence/P09-T01.1/seed/passive-nodes.json"]},
    ]


#: Which mechanic of the P06 registry (p06-flicker-v1, branch p06-coverage
#: 3cc334d) each rule informs. None: no P06 entry names it yet.
P06_MECHANICS = {
    "flicker-extra-strikes": ["skill/FlickerStrikePlayer"],
    "flicker-no-charge-gain": ["resource/power-charges"],
    "flicker-strike-timing": ["timing/flicker-strike-strike-duration"],
    "flicker-mana-charging": ["cost/mana-per-use"],
    "perpetual-charge": ["support/SupportPerpetualChargePlayer"],
    "ailith-surpassing-distribution": ["support/SupportAilithLineagePlayer"],
    "combo-gain-per-strike": ["support/SupportCulminationPlayerTwo", "passive/41751", "resource/combo"],
    "whirling-assault-own-combo": ["passive/61586", "support/SupportCulminationPlayerTwo"],
    "combo-cap-and-decay": ["resource/combo"],
    "whirling-assault-use": ["skill/WhirlingAssaultPlayer"],
    "charged-staff-use": ["charges/charged-staff-consumption"],
    "charged-staff-buff-ownership": ["skill/ChargedStaffPlayer", "charges/charged-staff-consumption"],
    "consumed-power-charge-recently": None,
    "hit-and-run-reuse": ["activation/hit-and-run-reuse", "support/SupportHitAndRunPlayer"],
    "pounce-predators-mark": ["skill/WolfPouncePlayer", "config/condition-sustain"],
    "persistent-buffs": ["skill/HeraldOfIcePlayer", "skill/HeraldOfThunderPlayer"],
    "pob-default-states": ["config/condition-sustain"],
    "mana-sustain": ["resource/mana-sustain", "resource/mana-flask", "resource/mana-regeneration"],
    "charged-staff-period": ["charges/charged-staff-consumption"],
    "flicker-bypass-cd-default": ["config/FlickerStrikeBypassCD"],
    "enemy-distance": ["config/enemyDistance"],
    "way-of-the-stonefist": None,
}

#: Corrected rule fields for the P06 registry when the rule's evidence is
#: accepted. Shaped as pob2opt.coverage.resolution.Resolution.rule_changes.
P06_RULE_CHANGES = {
    "flicker-extra-strikes": {"validation": "fixture_checked"},
    "perpetual-charge": {"limitations": ["Each consumed charge stays with probability 0.25, independently; the use still counts all of them as consumed."]},
    "ailith-surpassing-distribution": {"limitations": ["Surpassing: floor(25% x K / 100) charges plus one with the remaining chance; definition from a search summary of the community wiki."]},
    "combo-cap-and-decay": {"limitations": ["Cap 10 on the stored count, all expended on use, decay 6.0 s after the last gain."]},
    "whirling-assault-use": {"validation": "fixture_checked"},
    "charged-staff-use": {"limitations": ["Consumes all held charges, needs 1; not covered by Perpetual Charge in the seed."]},
    "pounce-predators-mark": {"limitations": ["Off in flicker_sustained_v1 documents: Pounce is movement only (owner Q4) and the mark is not generated by the rotation."]},
    "flicker-bypass-cd-default": {"support": "implemented", "validation": "fixture_checked",
                                  "limitations": ["No effect on the pin: Flicker Strike has no cooldown; outputs identical with the option off."]},
}


def ledger_resolutions(rule_list: list[dict]) -> list[dict]:
    """Each rule as a pob2opt.coverage Resolution. ``ready`` is true only
    when feeding it to CoverageLedger.resolve would close a gap that this
    evidence fully settles; a rule that settles part of a gap is a rule
    change only, so the gap stays open."""
    out = []
    for rule in rule_list:
        mechanics = P06_MECHANICS.get(rule["rule_id"])
        changes = P06_RULE_CHANGES.get(rule["rule_id"])
        if not mechanics or changes is None or rule["status"] != "resolved":
            continue
        out.append({
            "resolution_id": "p09-t012/" + rule["rule_id"],
            "gap_id": rule.get("gap_id"),
            "mechanic_id": mechanics[0],
            "evidence_ids": rule["evidence"],
            "author": "P09-T01.2",
            "resolved_at": "2026-10-18T00:00:00Z",
            "reviewer": None,
            "rule_changes": changes,
            "input_values": {},
            "outcome": "p09-t012:" + rule["rule_id"],
            "ready": False,
            "why_not_ready": "awaiting reviewer; the rule settles part of its mechanic, not a whole gap",
        })
    out.append({
        "resolution_id": "p09-t012/engine-checkout",
        "gap_id": "gap-p09-t011-engine-checkout-state",
        "mechanic_id": "engine/pinned-checkout",
        "evidence_ids": [REPLAY_REF],
        "author": "P09-T01.2",
        "resolved_at": "2026-10-18T00:00:00Z",
        "reviewer": None,
        "rule_changes": {"validation": "fixture_checked"},
        "input_values": {"/pob_inputs": REPLAY_REF},
        "outcome": "clean pinned replay agrees with every earlier value",
        "ready": True,
        "why_not_ready": None,
    })
    return out


def attribution(replay: dict) -> dict:
    diag = replay["diagnostics"]["charges_5"]["outputs"]
    return {
        "status": "proposed; needs reviewer acceptance (gap-p09-t011-attribution-rules stays open)",
        "score_counts": [
            {"source": "Flicker Strike direct hits", "rule": "Counted: H(c) strikes x per-strike PoB AverageDamage on the benchmark document (Pounce off)."},
            {"source": "Charged Staff buff added lightning on Flicker Strike hits",
             "rule": "Counted as part of the Flicker Strike hit, with stacks from charges Charged Staff consumed (rule charged-staff-buff-ownership). Never from charges Flicker Strike consumes."},
        ],
        "reported_separately": [
            {"source": "Flicker Strike ignite (PoB IgniteDPS)", "rule": "Excluded from the v1 score: its uptime depends on hit timing the cycle does not model. Reported. At 5 forced charges PoB shows %.1f per second, about 0.1%% of the hit damage rate." % diag["IgniteDPS"]},
            {"source": "Charged Shockwave", "rule": "A separate hidden attack (pob/charged-shockwave-skill) triggered while the buff is active. Not in Flicker Strike's outputs; owned by Charged Staff."},
            {"source": "Whirling Assault hits", "rule": "Separate skill."},
            {"source": "Living Lightning minions (Living Lightning II on Whirling Assault)", "rule": "Separate; minion damage."},
            {"source": "Herald of Ice explosions, Herald of Thunder bolts", "rule": "Separate skills. Herald of Ice explosions need shattered or killed enemies, which the benchmark does not have."},
            {"source": "Remnants of Kalguur, Trinity, Wind Dancer, Ghost Dance, Sanguine Revelry", "rule": "Separate; buffs only where they change Flicker Strike's PoB numbers."},
        ],
        "never_counted": [
            {"source": "Pounce and Predator's Mark", "rule": "Not used in the benchmark (rule pounce-predators-mark)."},
            {"source": "Any damage counted in two places", "rule": "Each damage instance has exactly one owner row above; a row may not be added without removing it elsewhere."},
        ],
        "evidence": [REPLAY_REF + "#/diagnostics", REPLAY_REF + "#/group_sweep"],
    }


def main() -> int:
    root = Path(os.environ.get("POB2_ROOT") or REPO_ROOT / "external" / "PathOfBuilding-PoE2").resolve()
    citations = resolve_citations(root)
    replay = json.loads(REPLAY.read_text(encoding="utf-8"))
    web = {i["evidence_id"]: i["url"] for i in json.loads(WEB.read_text(encoding="utf-8"))["items"]}
    rule_list = rules(replay)
    for rule in rule_list:
        for ref in rule["evidence"]:
            if ref.startswith("pob/") and ref not in citations:
                raise SystemExit("unknown citation %s" % ref)
            if ref.startswith("web/") and ref not in web:
                raise SystemExit("unknown web evidence %s" % ref)
    record = {
        "task": "P09-T01.2",
        "kind": "rule_table",
        "not_a_claim": "Rules for computing pob-cycle-v1 from PoB outputs. Status 'resolved' means the pinned "
                       "data, engine or replay settles it, pending reviewer acceptance. No gameplay measurement.",
        "command": "python scripts/p09_t01_2_mechanics_rules.py",
        "engine_head": PIN,
        "replay": REPLAY_REF,
        "replay_sha256": _sha(REPLAY),
        "web_evidence": WEB_REF,
        "web_evidence_sha256": _sha(WEB),
        "citations": citations,
        "rules": [dict(r, p06_mechanic_ids=P06_MECHANICS[r["rule_id"]],
                       pob_community_v2=UNDER_COMMUNITY_METHOD.get(r["rule_id"], "applies"))
                  for r in rule_list],
        "pob_community_v2_decision": DECISION_2,
        "p06_ledger_resolutions": ledger_resolutions(rule_list),
        "status_counts": {s: sum(1 for r in rule_list if r["status"] == s)
                          for s in ("resolved", "conditional", "blocking")},
        "attribution": attribution(replay),
    }
    OUT.write_text(json.dumps(record, indent=1, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    print("wrote %s: %s" % (OUT.relative_to(REPO_ROOT), record["status_counts"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
