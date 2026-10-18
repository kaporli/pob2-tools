"""Build the P09-T01.1 Flicker Strike suite artefacts.

    python scripts/p09_t01_1_flicker_suite.py

Deterministic and offline. Reads the stored seed export
(``docs/evidence/P09-T01.1/seed/``) and the pinned engine data extract
(``docs/evidence/P09-T01.1/mechanics.json``, written by
``scripts/p09_t01_1_mechanics.py``) and writes:

* ``docs/evidence/P09-T01.1/seed/manifest.json`` - provenance and SHA-256 of
  every seed file, the owner's rotation verbatim, and the share code check.
* ``docs/evidence/P09-T01.1/scope-proposal.json`` - proposed class and
  ascendancy list and three interaction variants, each citing its evidence.
* ``benchmarks/p09-flicker-v1/scenarios.json`` - the four clear/boss workloads
  and ``flicker_sustained_v1``, every field with a source or its DataGap ids,
  the owner rotation record and the DataGap records.
* ``benchmarks/p09-flicker-v1/references.json`` - the reference manifest.
* ``benchmarks/p09-flicker-v1/suite.json`` - frozen file and definition hashes.

Nothing here is a measurement of gameplay performance. Unknown enemy
statistics, encounter numbers and thresholds stay null with a DataGap.
"""

from __future__ import annotations

import base64
import hashlib
import json
import sys
import zlib
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
for _pkg in (REPO_ROOT / "pob2-mcp", REPO_ROOT / "pob2-optimizer"):
    if str(_pkg) not in sys.path:
        sys.path.insert(0, str(_pkg))

from pob2opt.domain.codec import to_jsonable  # noqa: E402
from pob2opt.domain.enums import GapKind, GapSeverity, GapStatus  # noqa: E402
from pob2opt.domain.identity import content_hash  # noqa: E402
from pob2opt.domain.objectives import FLICKER_SUSTAINED_DPS_V1  # noqa: E402
from pob2opt.domain.records import SCHEMA_VERSION, DataGap  # noqa: E402
from pob2opt.domain.validation import validate_record  # noqa: E402

TASK = "P09-T01.1"
SUITE_ID = "p09-flicker-v1"
PROTOCOL_ID = "p09-flk-protocol-v1"
CREATED_AT = "2026-10-17T00:00:00Z"

EVIDENCE = REPO_ROOT / "docs" / "evidence" / "P09-T01.1"
SEED_DIR = EVIDENCE / "seed"
MECHANICS_PATH = EVIDENCE / "mechanics.json"
SCOPE_PATH = EVIDENCE / "scope-proposal.json"
SEED_MANIFEST_PATH = SEED_DIR / "manifest.json"
BENCH = REPO_ROOT / "benchmarks" / SUITE_ID
SCENARIOS_PATH = BENCH / "scenarios.json"
REFERENCES_PATH = BENCH / "references.json"
SUITE_PATH = BENCH / "suite.json"
FLICKER_COVERAGE = "docs/evidence/P02-T02.1/flicker-coverage.json"
CATALOG_EXPORT = "docs/evidence/P02-T02.1/catalog-export.json"
PATCH_PROFILE_ID = "patch-profile/0.5.5e/ac0e930898cb3951"

#: The owner's rotation, exactly as supplied on 2026-10-17. The only rotation
#: evidence. Spelling kept.
OWNER_ROTATION = ("whirling assault to get 5 power charges & then flicker "
                  "strike, rince and repeat")

CHARGE_TABLE_PATH = EVIDENCE / "pob-charge-table.json"
NINJA_DIR = EVIDENCE / "reference-ninja-25c49"
D07_AMENDMENT = "docs/decisions/D07-flicker-strike-objective.md#amendment-2026-10-18"
OWNER_ANSWERS_REF = "docs/evidence/P09-T01.1/seed/manifest.json#owner_answers"

#: Owner answers of 2026-10-18 to Q1 to Q9. ``verbatim`` is the owner's text
#: where it was relayed verbatim, otherwise None; ``recorded`` is what this
#: protocol takes from it.
OWNER_ANSWERS = [
    ("Q1", "just 1", "One Whirling Assault use per Flicker Strike use."),
    ("Q2", "whirling assault", "The opener at 0 Power Charges and 0 Combo is Whirling Assault."),
    ("Q3", "when i have a charge",
     "Charged Staff is pressed when at least one Power Charge is held. Its place in the cycle relative to Flicker Strike is not stated."),
    ("Q4", "I press pounce, but only for mobility",
     "Herald of Ice, Herald of Thunder, Wind Dancer, Ghost Dance, Trinity, Remnants of Kalguur and the other Spirit skills are persistent and always active, not pressed (relayed summary). Pounce is movement only, not part of the damage rotation."),
    ("Q5", "the dash from flicker itself",
     "Flicker Strike's own teleport supplies Hit and Run's 10 metres. Owner statement; the catalog does not confirm it."),
    ("Q6", "yes when i'm on a boss & my refund 2% mana on kill jewel doesnt see use",
     "Mana flask used on bosses; the mana-on-kill jewel does nothing on a boss."),
    ("Q7", None,
     "Runs T16 (maximum tier) maps comfortably. Struggles on maps with the 'monsters have increased ailment threshold' modifier: chill does not apply and Polcirkeln does not shatter. Bosses not named (relayed summary)."),
    ("Q8", "we damage calc with PoB, not ingame testing",
     "Decision 1: PoB is the accepted damage source. Recorded as the D07 amendment of 2026-10-18."),
    ("Q9", "any class, any ascendancy, any variant",
     "Decision 2: all 23 ascendancies and all three variants are approved scope."),
    ("Q10", "Once per N cycles",
     "Charged Staff is pressed only periodically, once per N Whirling Assault to Flicker Strike cycles, to refresh its buff (owner's chosen option, relayed by the coordinator 2026-10-18). Owner decision 2026-10-18 (2) then gave the full rotation: the press repeats when the buff expires, so N follows from the buff duration (gap-p09-t012-charged-staff-period resolved)."),
]

#: Owner decision 2026-10-18 (2), verbatim, and where D07 records it.
OWNER_DECISION_2 = (
    "it's obvious, whirling assault to generate charges, charged staff, "
    "whirling assault to generate charges, flicker, whirling, flicker, "
    "whirling, flicker, etc until charged runs out & repeat? but again, look "
    "at how those other PoBs did DPS calcs, don't stray from their methods, "
    "match them. Assume we have charges for flicker for the dps calcs")
D07_AMENDMENT_2 = "docs/decisions/D07-flicker-strike-objective.md#amendment-2026-10-18-2"

#: P09-T01.2 evidence: the clean pinned replay and the rule table.
T012 = "docs/evidence/P09-T01.2"
REPLAY_REF = T012 + "/replay.json"
RULES_REF = T012 + "/mechanics-rules.json"
COMMUNITY_REF = T012 + "/community-cycle.json"

NOT_A_CLAIM = (
    "PROTOCOL, NOT A MEASUREMENT. No enemy statistic, encounter timing, "
    "threshold or performance value in this suite was measured. Null fields "
    "are unresolved inputs with DataGap records. The seed export supplies a "
    "configuration, not a trial. PoB values are proxy_only.")

SEED_FILES = [
    "export-as-imported.xml",
    "export-flicker-main.xml",
    "export-as-imported.code.txt",
    "items-raw.json",
    "skill-groups.json",
    "passive-nodes.json",
    "config-input.json",
    "stats-flicker-main.json",
]

CLEAR_IDS = ["p09-flk-clear-dense", "p09-flk-clear-spread"]
BOSS_IDS = ["p09-flk-boss-short", "p09-flk-boss-sustained"]
ENC_IDS = CLEAR_IDS + BOSS_IDS
DPS_ID = "flicker_sustained_v1"
ALL_IDS = ENC_IDS + [DPS_ID]
ROTATION_ID = "p09-flk-rotation-owner-v1"
SEED_REF_ID = "p09-flk-ref-candidate-seed-v1"


# ------------------------------------------------------------------- seed ===

def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def share_code(xml: bytes) -> str:
    """The encoding ``pob2mcp.server.export_build_code`` applies."""
    code = base64.b64encode(zlib.compress(xml, 9)).decode()
    return code.replace("+", "-").replace("/", "_")


def decode_share_code(code: str) -> bytes:
    """The decoding ``pob2mcp.server.import_build_code`` applies."""
    return zlib.decompress(base64.b64decode(
        code.strip().replace("-", "+").replace("_", "/")))


def write_share_code() -> None:
    xml = (SEED_DIR / "export-as-imported.xml").read_bytes()
    (SEED_DIR / "export-as-imported.code.txt").write_text(
        share_code(xml) + "\n", encoding="ascii", newline="\n")


def _seed_json(name):
    return json.loads((SEED_DIR / name).read_text(encoding="utf-8"))


def seed_facts():
    """Configuration facts read from the stored export. No performance."""
    groups = _seed_json("skill-groups.json")
    stats = _seed_json("stats-flicker-main.json")
    nodes = {n["id"]: n for n in _seed_json("passive-nodes.json")}
    items = _seed_json("items-raw.json")

    def group(label):
        g = next(g for g in groups if g["gems"][0]["name"] == label)
        return [{"name": x["name"], "level": x["level"], "quality": x["quality"],
                 "granted_effect_id": x["grantedEffectId"]} for x in g["gems"]]

    return {
        "class": "Monk",
        "ascendancy": "Martial Artist",
        "level": 93,
        "passive_points_used": 116,
        "flicker_group": group("Flicker Strike"),
        "whirling_assault_group": group("Whirling Assault"),
        "other_active_skills": sorted({g["gems"][0]["name"] for g in groups
                                       if g["gems"][0]["name"] not in (
                                           "Flicker Strike", "Whirling Assault")}),
        "weapon_1_base": items["Weapon 1"].split("\n")[2],
        "weapon_1_swap_base": items["Weapon 1 Swap"].split("\n")[2],
        "belt": items["Belt"].split("\n")[1],
        "power_charges_max": stats["PowerChargesMax"],
        "power_charges_max_sources": [
            {"source": "Base", "value": 3},
            {"source": "passive 65204 Overflowing Power", "value": 2,
             "allocated": 65204 in nodes},
        ],
        "chaos_inoculation_allocated": 56349 in nodes,
        "life": stats["Life"],
        "energy_shield": stats["EnergyShield"],
        "mana": stats["Mana"],
        "flicker_mana_cost_per_use": stats["ManaCost"],
        "mana_regen_per_s": stats["ManaRegenRecovery"],
        "req_dex": stats["ReqDex"],
        "req_int": stats["ReqInt"],
        "martial_artist_nodes": sorted(n["name"] for n in nodes.values()
                                       if n.get("ascendancy") == "Martial Artist"
                                       and n["type"] == "Notable"),
    }


def build_seed_manifest():
    xml = (SEED_DIR / "export-as-imported.xml").read_bytes()
    code = (SEED_DIR / "export-as-imported.code.txt").read_text(encoding="ascii").strip()
    if decode_share_code(code) != xml:
        raise SystemExit("share code does not decode to export-as-imported.xml")
    stats = _seed_json("stats-flicker-main.json")
    files = []
    for name in SEED_FILES:
        data = (SEED_DIR / name).read_bytes()
        files.append({"path": "docs/evidence/P09-T01.1/seed/" + name,
                      "sha256": _sha(data), "bytes": len(data)})
    return {
        "task": TASK,
        "kind": "account_character_import",
        "evidence_class": "PoB-derived configuration",
        "not_a_claim": (
            "A configuration exported from the owner's character. It is not a "
            "trial, a completion time or a damage measurement, and it closes "
            "no performance gap. PoB stats in this folder are proxy_only."),
        "provenance": {
            "captured_on": "2026-10-17",
            "operator": "implementation agent for the owner (Elias)",
            "access_path": (
                "Account-character import through the operator's pob2 MCP "
                "server (import_character, account already authenticated). "
                "D01 separates this from market access; it is not a provider "
                "build source and no provider was contacted."),
            "character_name": "JewsOfPalestine",
            "character_name_note": "Recorded here for provenance only.",
            "league": "Forbidden Rites",
            "class": "Monk",
            "ascendancy": "Martial Artist",
            "level": 93,
            "passive_points_used": 116,
            "mcp_server": "python -m pob2mcp.server, package at C:/Users/Elias/PycharmProjects/pob2-mcp",
            "engine_checkout": "C:/Users/Elias/PycharmProjects/PathOfBuilding-PoE2",
            "engine_head": "ce566eac45ea8a86477f513c7ee65a1ebe60014e",
            "engine_working_tree": "not checked by this task (P02-T02.1 records it as carrying user scratch files)",
            "engine_version_reported": "0.23.1",
            "calls": [
                "import_character(JewsOfPalestine): Monk, Martial Artist, level 93, 116 points, main skill Herald of Ice (group 5)",
                "get_build_info, get_skills, get_items(include_raw=true), get_config",
                "export_build_code: share code of the as-imported state",
                "eval_lua build:SaveDB('code') written to export-as-imported.xml (the same call the server's save_build_xml handler makes)",
                "eval_lua: socket groups with gem ids and passive nodes written to skill-groups.json and passive-nodes.json",
                "set_main_skill(group=6): Flicker Strike",
                "get_stats; eval_lua: build:SaveDB('code') to export-flicker-main.xml, mainOutput scalars to stats-flicker-main.json, item raw text to items-raw.json, config input to config-input.json",
            ],
            "share_code_check": (
                "export-as-imported.code.txt is regenerated from "
                "export-as-imported.xml with the server's encoding (zlib level "
                "9, base64, URL-safe). Its length, first 80 and last 40 "
                "characters equal the export_build_code output of the same "
                "session, and it decodes back to the XML bytes."),
        },
        "owner_rotation": {
            "verbatim": OWNER_ROTATION,
            "received": "2026-10-17",
            "status": "the only rotation evidence; details not stated are unresolved inputs",
        },
        "owner_answers": {
            "received": "2026-10-18",
            "relayed_by": "coordinator",
            "answers": [{"question_id": q, "verbatim": v, "recorded": r}
                        for q, v, r in OWNER_ANSWERS],
        },
        "owner_decisions": [
            {"decision": "PoB is the accepted damage source; the flicker_sustained_v1 target is a fixed, versioned PoB enemy configuration; gameplay recordings are optional validation for the DPS benchmark.",
             "authority": "Elias", "date": "2026-10-18", "recorded_in": D07_AMENDMENT},
            {"decision": "Class scope: any class, any ascendancy (all 23); all three variants approved.",
             "authority": "Elias", "date": "2026-10-18",
             "recorded_in": "docs/evidence/P09-T01.1/scope-proposal.json approval"},
            {"decision": "Rotation and DPS method: Whirling Assault, Charged Staff, then Whirling Assault and Flicker Strike until the Charged Staff buff expires, repeated; per-use Flicker Strike damage as community PoB builds compute it, with charges assumed (method pob-community-v2).",
             "verbatim": OWNER_DECISION_2,
             "authority": "Elias", "date": "2026-10-18", "relayed_by": "coordinator",
             "recorded_in": D07_AMENDMENT_2},
        ],
        "pob_main_skill_as_imported": "Herald of Ice (group 5)",
        "pob_proxy_flicker_main": {
            "label": "proxy_only",
            "main_skill_group": 6,
            "TotalDPS": stats["TotalDPS"],
            "AverageDamage": stats["AverageDamage"],
            "Speed": stats["Speed"],
            "ManaCost": stats["ManaCost"],
            "PowerCharges": stats["PowerCharges"],
            "PowerChargesMax": stats["PowerChargesMax"],
            "conditions": (
                "Imported PoB config: enemyIsBoss Pinnacle, enemy level 82, "
                "enemy elemental resistances 50, power charges 0 in the "
                "calculation, so one Flicker strike per use. PoB's displayed "
                "value, not D07's time-accounted benchmark."),
        },
        "files": files,
    }


# ------------------------------------------------------------- mechanics ===

def load_mechanics():
    data = json.loads(MECHANICS_PATH.read_text(encoding="utf-8"))
    return data, {e["mechanic_id"] for e in data["entries"]}


# ------------------------------------------------------------------ scope ===

#: Ascendancy -> passive mechanic ids whose text names charges, Combo or a
#: melee trigger (from mechanics.json). An empty list means no such node was
#: found by the keyword pass; it does not mean the ascendancy cannot use
#: Flicker Strike.
ASCENDANCY_NODES = {
    "Martial Artist": ["passive/41751", "passive/61586", "passive/36643"],
    "Amazon": ["passive/7979", "passive/42441"],
    "Invoker": ["passive/52448"],
    "Lich": ["passive/2516"],
}

ASCENDANCY_NOTES = {
    "Martial Artist": "Seed character. Martial Adept and Martial Master are allocated in the seed; Additional Power Charge Chance is not.",
    "Amazon": "Consuming a Charge triggers Elemental Surge; Flicker Strike consumes Power Charges.",
    "Invoker": "Triggers Elemental Expression on Melee Critical Hit; Flicker Strike is a Melee Attack.",
    "Lich": "Its power charge node applies to Spells only; Flicker Strike is an Attack.",
}


def build_scope(mechanics):
    data, ids = mechanics
    rows = []
    for cls in data["classes"]["classes"]:
        for asc in cls["ascendancies"]:
            nodes = ASCENDANCY_NODES.get(asc, [])
            for m in nodes:
                assert m in ids, m
            if asc == "Martial Artist":
                status, reason = "evidenced_by_seed", (
                    "The seed export is a Monk / Martial Artist using Flicker "
                    "Strike on a Quarterstaff.")
            else:
                status, reason = "catalog_possible", (
                    "No catalog row restricts Flicker Strike or a Quarterstaff "
                    "to a class. No export of this ascendancy using Flicker "
                    "Strike exists.")
            rows.append({
                "class": cls["class"],
                "ascendancy": asc,
                "status": status,
                "reason": reason,
                "relevant_nodes": nodes,
                "note": ASCENDANCY_NOTES.get(asc, ""),
                "in_approved_scope": True,
            })

    variants = [
        {
            "variant_id": "flk-var-combo-expend",
            "name": "Combo expenditure power charges",
            "status": "evidenced_by_seed",
            "charge_source_event": "A Culmination-supported melee attack expends Combo; Ailith's Chimes grants Power Charges per Combo expended.",
            "required_mechanics": [
                {"requirement": "Flicker Strike on a Quarterstaff", "mechanic_ids": ["skill/FlickerStrikePlayer"]},
                {"requirement": "A melee attack other than Flicker Strike supported by Culmination (adds ComboStacking; up to 10 Combo; Combo gained from other melee strikes; all Combo expended on use; 6000 ms decay delay). Seed: Whirling Assault", "mechanic_ids": ["support/SupportCulminationPlayerTwo", "statdesc/skill_maximum_number_of_combo_stacks", "skill/WhirlingAssaultPlayer"]},
                {"requirement": "Ailith's Chimes on that attack (requires ComboStacking): 25% Surpassing chance per Combo expended to gain a Power Charge", "mechanic_ids": ["support/SupportAilithLineagePlayer", "statdesc/chance_%_to_gain_power_charges_per_combo_spent"]},
                {"requirement": "Flicker Strike consumes the Power Charges: 2 additional teleporting strikes per Power Charge; no Power Charges gained while using it", "mechanic_ids": ["statdesc/flicker_strike_additional_flickers_from_power_charges", "statdesc/cannot_gain_power_charges_during_skill", "engine/removable-power-charges"]},
            ],
            "seed_amplifiers": [
                {"what": "Overflowing Power, +2 maximum Power Charges (5 in the seed)", "mechanic_ids": ["passive/65204"]},
                {"what": "Martial Adept (additional Combo) and Martial Master (Combo from all Attack Hits), Martial Artist only", "mechanic_ids": ["passive/41751", "passive/61586"]},
                {"what": "Perpetual Charge on Flicker Strike, 25% chance to not remove Charges but still count as consuming them", "mechanic_ids": ["support/SupportPerpetualChargePlayer", "statdesc/charge_skip_consume_chance_%"]},
            ],
            "benchmark_applicability": "No kill or add event appears in the cited text, so flicker_sustained_v1 can supply this cycle, subject to gap-p09-t011-charge-cycle-rules.",
            "gap_ids": ["gap-p09-t011-charge-cycle-rules", "gap-p09-t011-rotation-details"],
        },
        {
            "variant_id": "flk-var-shock-consume",
            "name": "Shock consumption power charges",
            "status": "catalog_only",
            "charge_source_event": "Siphoning Strike hits a Shocked target, consumes its Shock and grants a Power Charge.",
            "required_mechanics": [
                {"requirement": "Flicker Strike on a Quarterstaff", "mechanic_ids": ["skill/FlickerStrikePlayer"]},
                {"requirement": "Siphoning Strike (Quarterstaff; base_consume_enemy_shock_on_hit; grants a Power Charge when it consumes Shock)", "mechanic_ids": ["skill/SiphoningStrikePlayer"]},
                {"requirement": "A separate source of Shock on the target: Siphoning Strike has never_shock", "mechanic_ids": ["skill/SiphoningStrikePlayer"]},
                {"requirement": "Flicker Strike consumes the Power Charges: 2 additional strikes per Power Charge", "mechanic_ids": ["statdesc/flicker_strike_additional_flickers_from_power_charges", "statdesc/cannot_gain_power_charges_during_skill"]},
            ],
            "seed_amplifiers": [],
            "benchmark_applicability": "Needs the PoB benchmark enemy to be Shocked, and the Shock to be sustained by the build under the rotation rather than toggled in config (gap-p09-t011-config-conditions). No kill event in the cited text.",
            "gap_ids": ["gap-p09-t011-variant-exports", "gap-p09-t011-config-conditions"],
        },
        {
            "variant_id": "flk-var-cull-kill",
            "name": "Kill and cull power charges",
            "status": "catalog_only",
            "charge_source_event": "Killing Palm kills or culls an enemy (cull below 10% life) and grants Power Charges by rarity: 1 normal or magic, 2 rare, 3 unique.",
            "required_mechanics": [
                {"requirement": "Flicker Strike on a Quarterstaff", "mechanic_ids": ["skill/FlickerStrikePlayer"]},
                {"requirement": "Killing Palm (Quarterstaff; kill_enemy_on_hit_if_under_10%_life; skill_grant_X_power_charges_against_* 1/2/3)", "mechanic_ids": ["skill/KillingPalmPlayer"]},
                {"requirement": "Flicker Strike consumes the Power Charges: 2 additional strikes per Power Charge", "mechanic_ids": ["statdesc/flicker_strike_additional_flickers_from_power_charges", "statdesc/cannot_gain_power_charges_during_skill"]},
            ],
            "seed_amplifiers": [],
            "benchmark_applicability": "Kill-dependent. D07 item 4 allows no adds or kill events in flicker_sustained_v1, so this source supplies no Power Charges there; only the clear and boss workloads supply kills.",
            "gap_ids": ["gap-p09-t011-variant-exports"],
        },
    ]
    for v in variants:
        for req in v["required_mechanics"] + v["seed_amplifiers"]:
            for m in req["mechanic_ids"]:
                assert m in ids, m

    return {
        "task": TASK,
        "status": "approved scope (owner decision 2026-10-18). Evidence statuses below are unchanged by the approval.",
        "kind": "PoB-derived proposal, approved by the owner",
        "approval": {
            "authority": "Elias",
            "date": "2026-10-18",
            "verbatim": "any class, any ascendancy, any variant",
            "ascendancies": "all 23",
            "variants": [v["variant_id"] for v in variants],
            "source": OWNER_ANSWERS_REF,
        },
        "flicker_strike_requirements": {
            "weapon": "Quarterstaff (gem weaponRequirements) / Staff (granted skill weaponTypes)",
            "req_dex_base": 50,
            "req_int_base": 50,
            "source": FLICKER_COVERAGE + " coverage.gem",
            "seed_level_20_requirement": {"ReqDex": 137, "ReqInt": 115,
                                          "source": "docs/evidence/P09-T01.1/seed/stats-flicker-main.json (PoB-derived)"},
        },
        "class_restriction_evidence": (
            "The Flicker Strike gem row carries gemType, naturalMaxLevel, "
            "reqDex, reqInt, reqStr, tagString, tags, tier and "
            "weaponRequirements; none names a class. The catalog character "
            "rules (" + CATALOG_EXPORT + " character_rules) hold class to "
            "ascendancy links, levels, point budgets, weapon sets and the "
            "support limit; none binds a gem or a weapon to a class. Absence "
            "of a rule in PoB data is not proof the game has none."),
        "class_source": "docs/evidence/P09-T01.1/mechanics.json classes (pinned tree 0_5)",
        "ascendancies": rows,
        "excluded": [],
        "excluded_note": (
            "No ascendancy is excluded: no evidence found makes Flicker Strike "
            "unusable for any of them. The owner approved all 23. Only Monk / "
            "Martial Artist has an export."),
        "variants": variants,
        "variant_distinctness": (
            "The three variants differ in the event that grants the Power "
            "Charges Flicker Strike consumes: Combo expenditure, Shock "
            "consumption, enemy kill or cull. Each needs a different skill. "
            "Only the first has an export. All three approved by the owner."),
        "candidates_not_proposed": [
            {"candidate": "Perpetual Charge", "reason": "Changes charge consumption, not the charge source. Shared amplifier."},
            {"candidate": "Charged Staff", "reason": "Consumes all Power Charges (requires 1): competes with Flicker Strike for charges, grants none.", "mechanic_ids": ["skill/ChargedStaffPlayer"]},
            {"candidate": "Power Siphon (item-granted)", "reason": "Same kill/cull event as flk-var-cull-kill: a near-duplicate."},
            {"candidate": "Lingering Illusion", "reason": "Power Charge from a Remnant dropped when an enemy destroys the copy: depends on enemy damage. Not checked further."},
            {"candidate": "Devour, Wing Blast", "reason": "Wyvern shapeshift skills; compatibility with a Quarterstaff Flicker Strike not checked."},
        ],
    }


# ------------------------------------------------------------------- gaps ===

def _gap(gap_id, kind, severity, subjects, field_paths, explanation,
         needed_evidence, collection_method, mechanic_ids=(), resolved_by=()):
    return DataGap(
        schema_version=SCHEMA_VERSION,
        record_id=gap_id,
        created_at=CREATED_AT,
        provenance_ids=[PROTOCOL_ID],
        gap_id=gap_id,
        kind=kind,
        subject_ids=list(subjects),
        field_paths=list(field_paths),
        mechanic_ids=list(mechanic_ids),
        severity=severity,
        explanation=explanation,
        needed_evidence=needed_evidence,
        collection_method=collection_method,
        affected_evaluation_ids=[],
        sensitivity_result_id=None,
        status=GapStatus.RESOLVED if resolved_by else GapStatus.OPEN,
        resolution_evidence_ids=list(resolved_by),
    )


B, R, I = GapSeverity.BLOCKING, GapSeverity.RANKING_SENSITIVE, GapSeverity.INFORMATIONAL
MI, UE, UR = GapKind.MISSING_INPUT, GapKind.UNRESOLVED_ENTITY, GapKind.UNSUPPORTED_RULE
UP = GapKind.UNVALIDATED_PREDICTION


def build_gaps():
    return [
        _gap("gap-p09-t011-encounter-selection", MI, B, ENC_IDS, ["/encounter"],
             "Owner Q7: T16 maps for clearing, one with the 'monsters have "
             "increased ailment threshold' modifier (the owner's evidenced weak "
             "case). No map name or layout and no boss is named. PoB has no "
             "named PoE 2 boss preset: its boss skill presets are Atziri, "
             "Shaper, Sirus, Cortex, Exarch, Eater and Maven, and its enemy "
             "tiers are Standard Boss, Guardian/Pinnacle Boss and Uber "
             "Pinnacle Boss.",
             "For each clear shape, the T16 map name and layout the owner "
             "runs, with its modifiers; for each boss shape, the boss name "
             "and area level. The proposed PoB tiers for the boss shapes "
             "accepted or replaced.",
             "Owner answer to Q11 in benchmarks/p09-flicker-v1/protocol.md; a "
             "reviewer checks each against its shape in docs/specs/scenarios.md.",
             ["engine/boss-skill-presets", "engine/enemy-is-boss-option"]),
        _gap("gap-p09-t011-enemy-health", MI, B, ENC_IDS, ["/target_entities/*/health"],
             "No PoE 2 monster life is held for the clear and boss "
             "encounters. A recording's health bar is a fraction of an "
             "unknown maximum.",
             "Maximum life of each named monster and boss at a stated area "
             "level, rarity and patch, with the catalog row or experiment it "
             "came from. One value per entity.",
             "An identified catalog row from an accepted patch profile, or a "
             "controlled experiment with a known damage figure. A health bar "
             "alone does not close this."),
        _gap("gap-p09-t011-enemy-defenses", MI, B, ENC_IDS,
             ["/target_entities/*/defenses", "/target_entities/*/level"],
             "No monster level, resistance, armour or evasion is held for the "
             "named clear and boss encounters. flicker_sustained_v1 uses the "
             "PoB preset instead (D07 amendment).",
             "Per named monster at a stated area level and patch: level, "
             "elemental and chaos resistances, armour, evasion, with the "
             "catalog row or capture each came from.",
             "Catalog export from an accepted patch profile, or a measured "
             "damage-taken comparison against a known hit."),
        _gap("gap-p09-t011-encounter-density", MI, B, CLEAR_IDS,
             ["/target_entities/*/count", "/target_entities/*/position"],
             "Dense and spread differ by pack size and spacing; neither is held "
             "for any area.",
             "For each named clear area: monsters per pack, packs per run, and "
             "distance between successive packs along the walked route, with "
             "the distance unit.",
             "Owner recordings of full runs of the named area with route and "
             "pack positions marked, five runs or more so a spread is stated."),
        _gap("gap-p09-t011-spatial-unit", UE, B, ENC_IDS,
             ["/spatial_model_id", "/target_entities/*/position"],
             "PoB's stat description formatter prints "
             "skill_unusable_until_moved_X_distance 100 as 10 metres "
             "(divide_by_ten), which ties catalog distance values to metres "
             "in description text. Recorded positions are in screen or "
             "minimap space and no conversion to either exists.",
             "The conversion between recorded screen or minimap distance and "
             "catalog distance units, with the two measurements that fix it.",
             "A controlled measurement: a skill of known catalog radius used "
             "on a target at measured distances, at two distances.",
             ["statdesc/skill_unusable_until_moved_X_distance"]),
        _gap("gap-p09-t011-movement-model", UR, B, CLEAR_IDS,
             ["/movement_model_id"],
             "No pathfinding is implemented. Clear routes have no model.",
             "Per-leg route times for each named clear area, read off a "
             "recording's clock in seconds.",
             "Owner recordings; per-leg times read frame by frame with the "
             "frame rate stated."),
        _gap("gap-p09-t011-incoming-damage", MI, B, ENC_IDS,
             ["/incoming_damage_model_id", "/event_schedule"],
             "No timestamped damage event is held for any encounter.",
             "Timestamped damage events for each named encounter and patch "
             "with the character's maximum and current energy shield, "
             "mitigation and recovery at each event.",
             "Owner recordings with the resource globes legible, plus a "
             "reviewer-accepted method separating damage from recovery."),
        _gap("gap-p09-t011-boss-windows", MI, B, BOSS_IDS,
             ["/target_entities/*/targetable_windows", "/event_schedule"],
             "No phase or invulnerability timing is held for any boss.",
             "Start and end of every phase and untargetable window of each "
             "named boss in seconds from encounter start, at a stated area "
             "level and patch, over at least five attempts.",
             "Owner recordings; times read off the recording clock with frame "
             "rate and reaction precision stated."),
        _gap("gap-p09-t011-duration-limit", MI, B, ENC_IDS, ["/duration_limit_s"],
             "A limit decides which builds fail; setting it needs observed "
             "completion times.",
             "Completion time of every attempt, failures included, for each "
             "named encounter with the seed configuration.",
             "Owner recordings, start and completion events per the protocol, "
             "at least five attempts per encounter."),
        _gap("gap-p09-t011-success-fraction", MI, B, ENC_IDS, ["/minimum_success_fraction"],
             "Recorded gameplay trials are stochastic. scenarios.md requires a "
             "stochastic suite to state its minimum success fraction before "
             "data collection. None is set.",
             "A minimum fraction of successful trials per encounter, fixed by "
             "the owner or reviewer before collection starts.",
             "Product decision recorded in a review before P09-T02 collection."),
        _gap("gap-p09-t011-reference-result", MI, B, ALL_IDS,
             ["/reference_build_id", "/reference_result_id"],
             "The seed export begins reference selection. A reference also "
             "needs a result on the scenario: an observed completion time for "
             "the four workloads, and for flicker_sustained_v1 a pob-cycle-v1 "
             "computation, which cannot run until its blocking gaps close.",
             "For each workload an accepted observation of the seed; for "
             "flicker_sustained_v1 a pob-cycle-v1 result of the seed in a "
             "clean pinned engine, accepted by a reviewer.",
             "P09-T02 observation import for the workloads; the P07 evaluator "
             "or a scripted PoB computation for the benchmark."),
        _gap("gap-p09-t011-benchmark-target", MI, B, [DPS_ID],
             ["/target_entities/0/identity", "/target_entities/0/level",
              "/target_entities/0/defenses"],
             "D07 needed one non-dying, continuously targetable in-game enemy "
             "with evidenced level and defenses.",
             "A fixed, versioned enemy configuration with level and defenses.",
             "Owner decision 2026-10-18: the target is a fixed PoB enemy "
             "configuration (D07 amendment); the Guardian/Pinnacle Boss "
             "preset is used.",
             ["engine/pinnacle-enemy-preset"],
             resolved_by=[D07_AMENDMENT, OWNER_ANSWERS_REF]),
        _gap("gap-p09-t011-benchmark-measurement", UR, B, [DPS_ID],
             ["/measurement_method"],
             "P09-T02 needed a way to measure attributed damage in [0, 120) in "
             "game.",
             "A damage source and computation method for flicker_sustained_v1.",
             "Owner decision 2026-10-18: PoB is the damage source (D07 "
             "amendment); method pob-cycle-v1 defined in the protocol.",
             resolved_by=[D07_AMENDMENT, OWNER_ANSWERS_REF]),
        _gap("gap-p09-t011-attribution-rules", UR, B, [DPS_ID],
             ["/attribution_rules"],
             "Proposed rule: only Flicker Strike's own PoB AverageBurstDamage "
             "counts; Whirling Assault, Living Lightning, the heralds, Wind "
             "Dancer, Trinity and Remnants of Kalguur are reported "
             "separately. Not yet accepted by a reviewer. Charged Staff's "
             "buff share is gap-p09-t011-charged-staff-shared-charges.",
             "Reviewer acceptance of the proposed rule, or a replacement rule "
             "per seed damage source with catalog evidence.",
             "P07-T02 attribution rule review against the catalog. P09-T01.2 "
             "proposes an ownership table: Flicker Strike hits including the "
             "Charged Staff buff's added lightning counted; ignite, Charged "
             "Shockwave, Whirling Assault, Living Lightning and the heralds "
             "reported separately (" + RULES_REF + " attribution)."),
        _gap("gap-p09-t011-rotation-details", MI, B, ALL_IDS, ["/rotation_id"],
             "Owner Q1 to Q6 fix the cycle (one Whirling Assault, one Flicker "
             "Strike, Whirling Assault opener). Q10: Charged Staff is pressed "
             "once per N cycles to refresh its buff, consuming all held "
             "charges. Open: N (gap-p09-t012-charged-staff-period) and the "
             "press's position inside its cycle (after Whirling Assault and "
             "before Flicker Strike is the only point with a charge held, "
             "unless Perpetual Charge kept one).",
             "N, and whether the refresh press follows Whirling Assault or "
             "follows a Flicker Strike that kept a charge.",
             "Owner follow-up to Q10; a reviewer checks the rotation record. "
             "Rule table: " + RULES_REF + " charged-staff-period. Owner "
             "decision 2026-10-18 (2) gives the full rotation: Whirling "
             "Assault, Charged Staff, then Whirling Assault and Flicker Strike "
             "until the buff expires, repeated.",
             ["skill/ChargedStaffPlayer"],
             resolved_by=[D07_AMENDMENT_2, OWNER_ANSWERS_REF]),
        _gap("gap-p09-t011-charge-cycle-rules", UR, B, [DPS_ID] + BOSS_IDS,
             ["/measurement_method", "/sustain_report"],
             "pob-cycle-v1 needs the Combo Whirling Assault holds at each use. "
             "Catalog text gives the parts, not the game semantics: whether "
             "Flicker Strike strikes are 'other Melee Attacks' that grant "
             "Combo to the Culmination-supported Whirling Assault, how many "
             "per strike with Martial Adept (one extra per gain) and Martial "
             "Master (Combo from all Attack Hits), whether Whirling Assault's "
             "own hits grant it Combo, whether the 10 Combo cap applies "
             "before or after Martial Adept's extra, what distribution "
             "'25% Surpassing chance per Combo expended' gives, and how "
             "Perpetual Charge's kept charges carry into the next cycle.",
             "For each question, evidence: an official statement, a catalog "
             "or engine implementation that settles it, or a recording with "
             "the Combo and Power Charge counters legible over at least 20 "
             "cycles.",
             "Engine or catalog lookup first; recordings as optional "
             "validation; a reviewer accepts each rule before any "
             "pob-cycle-v1 value is computed. P09-T01.2 settled the Surpassing "
             "distribution and Perpetual Charge's per-charge rule, and left "
             "Combo per strike and Whirling Assault's own Combo open with "
             "both alternatives and their conflict with the owner's '5 power "
             "charges' written out (" + RULES_REF + ").",
             ["support/SupportAilithLineagePlayer", "support/SupportCulminationPlayerTwo",
              "passive/41751", "passive/61586", "support/SupportPerpetualChargePlayer",
              "statdesc/cannot_gain_power_charges_during_skill"]),
        _gap("gap-p09-t011-charged-staff-shared-charges", UR, B, [DPS_ID],
             ["/measurement_method", "/attribution_rules"],
             "PoB applies Charged Staff's per-charge added lightning and Flicker "
             "Strike's per-charge strikes from the same RemovablePowerCharges: "
             "with Charged Staff enabled, per-strike AverageDamage is 136232 at "
             "5 forced charges, with it disabled 124231. Both skills consume "
             "all Power Charges, so in game the same charges cannot feed both "
             "on one use.",
             "Which D(c) table pob-cycle-v1 uses: Charged Staff buff stacks "
             "from charges actually consumed by Charged Staff under the "
             "rotation (needs Q10), or Charged Staff disabled.",
             "Owner answer to Q10 (once per N cycles) and N, then a reviewer "
             "rule. P09-T01.2 proposes buff stacks from the charges Charged "
             "Staff consumed, captures A_CS(s) and the no-buff values on the "
             "benchmark document, and states the open refresh rule ("
             + RULES_REF + " charged-staff-buff-ownership).",
             ["skill/ChargedStaffPlayer", "engine/removable-power-charges"]),
        _gap("gap-p09-t011-flicker-strike-timing", UP, R, [DPS_ID],
             ["/measurement_method"],
             "pob-cycle-v1 times every Flicker Strike strike, including the "
             "extra teleporting strikes, at 1 / PoB Speed, with no travel or "
             "Hit and Run movement time. PoB's TotalDPS makes the same "
             "assumption for a single strike. Not validated.",
             "Recorded duration of Flicker Strike uses at known charge counts, "
             "or an engine or official statement of the extra strikes' timing.",
             "Optional owner recording of Flicker Strike uses at 1 and 5 "
             "charges, read frame by frame."),
        _gap("gap-p09-t011-hit-and-run-movement", UR, B, ALL_IDS,
             ["/movement_model_id", "/measurement_method"],
             "Hit and Run makes Flicker Strike usable after moving 10 metres. "
             "Owner Q5: 'the dash from flicker itself' supplies it. The "
             "catalog does not confirm that Flicker Strike's teleport counts "
             "as moving.",
             "Engine, official or recorded evidence that Flicker Strike's "
             "teleport re-enables Hit and Run, including the first-use "
             "activation condition; otherwise a legal movement action with "
             "its time charged to the cycle, or a supported replacement setup.",
             "Engine or official rule lookup; a recording of consecutive uses "
             "is an optional evidence route, not a waiver of activation. "
             "P09-T01.2 found no pinned or retrieved evidence either way and "
             "wrote three labelled variants: teleport re-enables (owner Q5), "
             "no Hit and Run (S_F 6.6588 captured), and a timed 10 m movement "
             "(needs movement speed in metres per second) (" + RULES_REF + ").",
             ["support/SupportHitAndRunPlayer", "statdesc/skill_unusable_until_moved_X_distance"]),
        _gap("gap-p09-t011-sustain-cycle", MI, B, [DPS_ID], ["/sustain_report"],
             "D07 item 6 needs resource depletion and whether the cycle "
             "repeats. PoB: Flicker Strike 248 mana per use, Whirling Assault "
             "160, 887 maximum mana, 47.9 mana regeneration per second. Owner "
             "Q6: mana flask used on bosses; mana on kill does nothing there. "
             "Flask recovery and charge gain are not in the method yet.",
             "PoB's mana flask recovery and charge gain for the seed's flask, "
             "or a reviewer rule for flask use in the 120 s window.",
             "P09-T01.2 captured the mana flask from PoB (356.5 mana per use, "
             "10 of 75 charges, 0.25 charges per second, no kill charges on "
             "the benchmark). Still open: flask charges at t = 0, when the "
             "flask is used, and per-use versus per-strike Flicker Strike "
             "mana (gap-p09-t012-flicker-mana-charging); reviewer rule. "
             "Then resolved: Mageblood in the pinned PoB grants Mage's Legacy "
             "stat bonuses only and leaves flasks unchanged; the seed's one "
             "mana flask is modelled from PoB flaskData; the timeline waits "
             "for mana inside the window (" + COMMUNITY_REF + ", " + RULES_REF
             + " mana-sustain). Flask charges full at t = 0 and the flask use "
             "policy are protocol choices for review.",
             resolved_by=[RULES_REF, COMMUNITY_REF, REPLAY_REF]),
        _gap("gap-p09-t011-config-conditions", UR, B, [DPS_ID],
             ["/target_entities/0/conditions", "/initial_state"],
             "D07 forbids free maximum-state toggles. The seed's imported PoB "
             "config carries condition inputs (for example "
             "conditionChampionIntimidate, inDemonForm, touchedDebuffsCount "
             "10, purpleFlameStacks 10, targetBrandedEnemy, "
             "SecondsSinceInevitableCrit 10, multiplierCurrentManaPercentage "
             "100) whose effect on Flicker Strike and whose sustain under the "
             "rotation are not checked.",
             "For each condition input that changes a Flicker Strike output: "
             "evidence the build sustains it under the rotation, or the input "
             "switched off in the benchmark configuration.",
             "PoB comparison with each input toggled; reviewer rule. P09-T01.2 "
             "swept every socket group and listed every Config-sourced, "
             "conditional and enemy modifier: one forced state found "
             "(Pounce's Predator's Mark, 24% increased damage taken from "
             "eight Living Lightning minions), switched off in the benchmark "
             "documents; no imported config input feeds a Flicker Strike "
             "modifier (" + RULES_REF + " pounce-predators-mark, "
             "pob-default-states). Awaiting reviewer acceptance.",
             ["engine/pinnacle-enemy-preset"]),
        _gap("gap-p09-t011-patch-profile", GapKind.STALE_PATCH, B, ALL_IDS,
             ["/patch_profile_id"],
             "The catalog verdict is partial: the engine data release predates "
             "0.5.5e and slot-accepted-base-categories is open (P02-T02.1).",
             "An accepted patch profile with compatibility verified for 0.5.5e "
             "or the patch the measurements are taken on.",
             "P02-T02 re-export after an engine data release for the live "
             "patch, plus the D03 decision."),
        _gap("gap-p09-t011-engine-checkout-state", MI, B, [DPS_ID], ["/pob_proxy", "/measurement_method"],
             "With PoB as the damage source, benchmark numbers must come from "
             "a clean checkout of the pin. The seed's stats and the charge "
             "table came from the operator's checkout at the pinned HEAD with "
             "an unchecked working tree.",
             "The charge table and Whirling Assault outputs recomputed from "
             "the stored export in a clean checkout of ce566ea.",
             "Load docs/evidence/P09-T01.1/seed/export-flicker-main.xml in a "
             "clean pinned engine and repeat the pob-charge-table.json "
             "procedure. Done by scripts/p09_t01_2_seed_replay.py: all 734 "
             "imported outputs, the charge table, Whirling Assault and the "
             "enemy agree exactly on a clean checkout of the pin.",
             resolved_by=[REPLAY_REF]),
        _gap("gap-p09-t011-variant-exports", MI, B, ["flk-var-shock-consume", "flk-var-cull-kill"],
             ["/variants/*/status"],
             "Only the combo-expenditure variant has an export. Each approved "
             "variant needs complete configurations.",
             "One complete export per variant (Siphoning Strike with a Shock "
             "source; Killing Palm) with the rotation played, then enough "
             "configurations for the P09-T02 split.",
             "Owner or independently sourced exports, imported as account "
             "characters or local share codes; no provider scraping."),
        _gap("gap-p09-t012-charged-staff-period", MI, B, [DPS_ID] + BOSS_IDS,
             ["/rotation_id", "/measurement_method"],
             "Owner Q10: Charged Staff is pressed once per N Whirling Assault "
             "to Flicker Strike cycles to refresh its buff. N decides how "
             "many charges Charged Staff takes from Flicker Strike, how much "
             "of the window its buff covers, and its time and mana.",
             "The number N, and the press's position inside its cycle.",
             "Owner answer relayed by the coordinator; a reviewer records it "
             "in the rotation. Owner decision 2026-10-18 (2): the press repeats "
             "when the buff expires, so N follows from the buff duration "
             "(6 s per stack, 25% increased duration on the seed, from PoB) and "
             "PoB's use times.",
             ["skill/ChargedStaffPlayer"],
             resolved_by=[D07_AMENDMENT_2, REPLAY_REF]),
        _gap("gap-p09-t012-flicker-mana-charging", UR, B, [DPS_ID] + BOSS_IDS,
             ["/sustain_report", "/measurement_method"],
             "Flicker Strike costs 248 mana in PoB. Its text describes one use "
             "with additional teleporting strikes (one payment), while PoB's "
             "ManaPerSecondCost multiplies the cost by the strike rate (one "
             "payment per strike). At 5 charges the two differ elevenfold.",
             "An official statement, a pinned engine rule, or a recording of "
             "the mana globe across Flicker Strike uses at known charges.",
             "Engine or official lookup; optional owner recording read frame "
             "by frame. Resolved by the owner's community-PoB method (D07 "
             "amendment 2): PoB's ManaCost is the upfront cost of one use, "
             "paid once per use (" + RULES_REF + " flicker-mana-charging).",
             ["skill/FlickerStrikePlayer"],
             resolved_by=[D07_AMENDMENT_2, RULES_REF]),
        _gap("gap-p09-t011-class-scope-decision", MI, B, ["scope-proposal"],
             ["/ascendancies/*/in_approved_scope", "/variants"],
             "The class list and variants were proposals; D07 makes scope the "
             "owner's decision.",
             "The owner's approved ascendancy list and variants.",
             "Owner answer to Q9: 'any class, any ascendancy, any variant'.",
             resolved_by=[OWNER_ANSWERS_REF]),
        _gap("gap-p09-t011-survival-threshold", MI, R, ENC_IDS,
             ["/survival_gates/1/threshold"],
             "The seed runs Chaos Inoculation (maximum life 1), so its "
             "survivable pool is energy shield. Any margin stricter than "
             "deaths equal zero would be a fitted threshold.",
             "A minimum energy shield fraction per encounter, set from "
             "recorded incoming damage, or an explicit decision to keep "
             "deaths equal zero as the only gate.",
             "Reviewer decision after gap-p09-t011-incoming-damage has data."),
        _gap("gap-p09-t011-initial-resources", MI, R, ENC_IDS, ["/initial_state/resources"],
             "The state at encounter start is not recorded, and whether Power "
             "Charges and Combo persist across area transitions is unknown.",
             "Energy shield, mana, Power Charges and Combo at the start event "
             "of each recorded trial, and whether charges persist after an "
             "area transition.",
             "Owner recordings, read at the start event."),
        _gap("gap-p09-t011-preparation-allowance", MI, R, ALL_IDS, ["/allowed_preparation"],
             "Which pre-encounter actions persist into an encounter was not "
             "recorded.",
             "For each seed buff skill: whether it is active at the start "
             "event.",
             "Owner answer to Q4: Spirit skills are persistent and always "
             "active; Pounce is movement only.",
             resolved_by=[OWNER_ANSWERS_REF]),
    ]


# ------------------------------------------------------------- scenarios ===

def F(basis, source, value=None, gaps=()):
    return {"basis": basis, "source": source, "value": value, "gap_ids": list(gaps)}


SHAPES = {
    "p09-flk-clear-dense": ("clear", "clear_dense",
                            "One named T16 area whose packs stand close together; measures time to clear a fixed enemy workload with little travel."),
    "p09-flk-clear-spread": ("clear", "clear_spread",
                             "One named T16 area whose packs are spread along a route; measures time including travel between packs."),
    "p09-flk-boss-short": ("boss", "boss_short",
                           "One named boss that stays targetable; measures time from encounter start to kill."),
    "p09-flk-boss-sustained": ("boss", "boss_sustained",
                               "One named boss with phases or untargetable windows; measures start to kill including the windows that elapse before the kill."),
}

ENCOUNTER_VALUES = {
    "p09-flk-clear-dense": F(
        "owner_statement",
        "Owner Q7: runs T16 maps comfortably, struggles with 'monsters have increased ailment threshold' (chill does not apply, Polcirkeln does not shatter). Placing that modifier on the dense shape is this protocol's choice",
        {"waystone_tier": 16, "map": None,
         "required_modifiers": ["monsters have increased ailment threshold"],
         "why": "the owner's evidenced weak case"},
        ["gap-p09-t011-encounter-selection"]),
    "p09-flk-clear-spread": F(
        "owner_statement", "Owner Q7: runs T16 maps comfortably",
        {"waystone_tier": 16, "map": None, "required_modifiers": []},
        ["gap-p09-t011-encounter-selection"]),
    "p09-flk-boss-short": F(
        "protocol_choice",
        "Owner named no boss. PoB has no named PoE 2 boss preset (engine/boss-skill-presets lists PoE 1 bosses); proposed: PoB tier Guardian/Pinnacle Boss as the enemy configuration, boss name open",
        {"boss": None, "proposed_pob_enemy_tier": "Pinnacle", "status": "proposed"},
        ["gap-p09-t011-encounter-selection"]),
    "p09-flk-boss-sustained": F(
        "protocol_choice",
        "Owner named no boss. Proposed: PoB tier Uber Pinnacle Boss as the enemy configuration, boss name open",
        {"boss": None, "proposed_pob_enemy_tier": "Uber", "status": "proposed"},
        ["gap-p09-t011-encounter-selection"]),
}

SURVIVAL_DEATHS = {
    "gate_id": "deaths",
    "definition": "event",
    "path": "/metrics/survival/deaths",
    "operator": "eq",
    "threshold": 0.0,
    "event": "Character death during the trial (death screen in a recording; death event in an evaluator).",
    "threshold_basis": "docs/specs/scenarios.md: death is a failure, not a missing trial.",
}
SURVIVAL_ES = {
    "gate_id": "minimum-energy-shield",
    "definition": "numeric",
    "path": "/metrics/minimum_resources/energy_shield_fraction",
    "operator": "gte",
    "threshold": None,
    "threshold_gap": "gap-p09-t011-survival-threshold",
    "why_energy_shield": "Seed allocates Chaos Inoculation (passive 56349): maximum life 1, so a life margin is meaningless for it.",
}
RESOURCE_GATES = [
    {"path": "/metrics/minimum_resources/mana", "operator": "gte", "threshold": 0.0,
     "basis": "docs/specs/scenarios.md: an empty pool is downtime, not illegality; a pool never goes negative."},
    {"path": "/metrics/maximum_resources/power_charges", "operator": "lte", "threshold": 5,
     "basis": "Seed PowerChargesMax 5: base 3 plus Overflowing Power +2 (passive 65204). A count above it is an evaluator error."},
]

PERSISTENT_SKILLS = ["Herald of Ice", "Herald of Thunder", "Wind Dancer", "Ghost Dance",
                     "Trinity", "Remnants of Kalguur"]


def common_fields(sid):
    return {
        "patch_profile_id": F("catalog", CATALOG_EXPORT + " patch_profile_id (verdict partial)",
                              PATCH_PROFILE_ID, ["gap-p09-t011-patch-profile"]),
        "initial_state.configuration": F(
            "seed_export", "docs/evidence/P09-T01.1/seed/export-as-imported.xml (sha256 in seed/manifest.json)",
            "seed export, Monk / Martial Artist level 93"),
        "rng_seeds": F("product_default",
                       "Recorded gameplay is not seeded; docs/specs/scenarios.md requires a stochastic suite to fix its minimum success fraction instead",
                       []),
        "reference_build_id": F("unresolved", "Seed is a candidate configuration only; see references.json",
                                None, ["gap-p09-t011-reference-result"]),
        "reference_result_id": F("unresolved", "No result exists", None,
                                 ["gap-p09-t011-reference-result"]),
        "rotation_id": F("owner_statement", "Owner rotation and answers Q1 to Q6, in scenarios.json rotation",
                         ROTATION_ID, ["gap-p09-t011-rotation-details", "gap-p09-t011-hit-and-run-movement"]),
        "resource_gates": F("specification", "docs/specs/scenarios.md and the seed export", RESOURCE_GATES),
        "evidence_ids": F("seed_export", "Seed manifest, mechanics extract, PoB charge table, P02-T02.1 catalog export", [
            "docs/evidence/P09-T01.1/seed/manifest.json",
            "docs/evidence/P09-T01.1/mechanics.json",
            "docs/evidence/P09-T01.1/pob-charge-table.json",
            CATALOG_EXPORT]),
        "validation_status": F("specification", "docs/specs/contracts.md RuleValidation; no evaluator has run these", "untested"),
    }


def encounter_scenario(sid):
    category, shape, criterion = SHAPES[sid]
    clear = category == "clear"
    f = {
        "scenario_id": F("specification", "docs/specs/scenarios.md four shapes", sid),
        "version": F("product_default", "docs/specs/scenarios.md: a version change starts a new aggregate identity", "1"),
        "category": F("specification", "docs/specs/scenarios.md", category),
        "kind": F("specification", "docs/specs/scenarios.md: representative scenarios are a separate dataset", "representative"),
        "shape": F("specification", "docs/specs/scenarios.md", shape),
        "selection_criterion": F("specification", "docs/specs/scenarios.md; T16 from owner Q7", criterion),
        "encounter": ENCOUNTER_VALUES[sid],
        "target_entities.count": F("unresolved", "Depends on the named encounter", None,
                                   ["gap-p09-t011-encounter-density"] if clear else ["gap-p09-t011-encounter-selection"]),
        "target_entities.health": F("unresolved", "No monster life held", None, ["gap-p09-t011-enemy-health"]),
        "target_entities.level": F("unresolved", "No monster level held", None,
                                   ["gap-p09-t011-enemy-defenses", "gap-p09-t011-encounter-selection"]),
        "target_entities.defenses": F("unresolved", "No mitigation held", None, ["gap-p09-t011-enemy-defenses"]),
        "target_entities.position": F("unresolved", "No positions or unit conversion", None,
                                      (["gap-p09-t011-encounter-density"] if clear else []) + ["gap-p09-t011-spatial-unit"]),
        "target_entities.targetable_windows": F("unresolved", "No timings held", None,
                                                ["gap-p09-t011-encounter-selection"] if clear else ["gap-p09-t011-boss-windows"]),
        "initial_state.resources": F("unresolved", "Start state not recorded", None, ["gap-p09-t011-initial-resources"]),
        "event_schedule": F("unresolved", "No spawn, phase or damage timings held", None,
                            ["gap-p09-t011-encounter-density", "gap-p09-t011-incoming-damage"] if clear
                            else ["gap-p09-t011-boss-windows", "gap-p09-t011-incoming-damage"]),
        "spatial_model_id": F("unresolved", "No unit conversion", None, ["gap-p09-t011-spatial-unit"]),
        "movement_model_id": F("unresolved", "No route or movement model", None,
                               (["gap-p09-t011-movement-model"] if clear else []) + ["gap-p09-t011-hit-and-run-movement"]),
        "duration_limit_s": F("unresolved", "Needs observed completion times", None, ["gap-p09-t011-duration-limit"]),
        "minimum_success_fraction": F("unresolved", "docs/specs/scenarios.md requires it before collection", None,
                                      ["gap-p09-t011-success-fraction"]),
        "completion_condition": F("specification", "docs/specs/scenarios.md", {
            "type": "all_targets_dead" if clear else "target_dead",
            "start_event": "First frame the character is in the named area (clear) or the boss arena with the encounter started (boss).",
            "completion_event": ("The last declared target of the fixed workload dies; the clock includes movement, targeting, preparation and cleanup."
                                 if clear else
                                 "The named boss dies; the clock stops at the kill and includes only the untargetable windows that elapsed before it."),
            "failure_events": ["character death", "duration limit reached"],
        }),
        "incoming_damage_model_id": F("unresolved", "No damage events held", None, ["gap-p09-t011-incoming-damage"]),
        "allowed_preparation": F("product_default",
                                 "docs/specs/product.md (one configuration, no party buffs, no outside resource generation, timed weapon-set changes); owner Q4 (Spirit skills persistent, Pounce movement only)",
                                 {"party_buffs": False, "outside_resource_generation": False,
                                  "weapon_set_changes": "allowed when represented and timed",
                                  "persistent_skills": PERSISTENT_SKILLS,
                                  "movement_only_skills": ["Pounce"]}),
        "capability_floor_ratio": F("specification", "docs/specs/scenarios.md provisional floor", 0.5),
        "survival_gates": F("specification", "docs/specs/scenarios.md (deaths); threshold of the energy shield gate unresolved",
                            [SURVIVAL_DEATHS, SURVIVAL_ES], ["gap-p09-t011-survival-threshold"]),
    }
    f.update(common_fields(sid))
    return {"scenario_id": sid, "version": "1", "category": category, "shape": shape, "fields": f}


def _charge_table():
    return json.loads(CHARGE_TABLE_PATH.read_text(encoding="utf-8"))


POB_CYCLE_REQUIRED_GAPS = (
    "gap-p09-t011-charge-cycle-rules",
    "gap-p09-t011-rotation-details",
    "gap-p09-t011-charged-staff-shared-charges",
    "gap-p09-t011-config-conditions",
    "gap-p09-t011-engine-checkout-state",
    "gap-p09-t011-sustain-cycle",
    "gap-p09-t011-hit-and-run-movement",
    "gap-p09-t011-attribution-rules",
    "gap-p09-t012-charged-staff-period",
    "gap-p09-t012-flicker-mana-charging",
)

#: Prerequisites closed with evidence. They stay in required_gap_ids.
RESOLVED_PREREQUISITES = frozenset({"gap-p09-t011-engine-checkout-state",
                                    "gap-p09-t011-rotation-details",
                                    "gap-p09-t012-charged-staff-period",
                                    "gap-p09-t011-sustain-cycle",
                                    "gap-p09-t012-flicker-mana-charging"})

#: pob-community-v2 (D07 amendment 2): what the owner's method waives, and
#: what still stands between its value and a supported score.
COMMUNITY_WAIVED = (
    ("gap-p09-t011-charge-cycle-rules", "charges assumed for Flicker Strike"),
    ("gap-p09-t011-charged-staff-shared-charges", "Charged Staff and Flicker Strike each at maximum charges as PoB applies them"),
    ("gap-p09-t011-hit-and-run-movement", "Hit and Run as PoB applies it; owner's method, not a verified mechanic"),
)
COMMUNITY_STILL_BLOCKING = (
    "gap-p09-t011-attribution-rules",
    "gap-p09-t011-config-conditions",
)


def community_method():
    """pob-community-v2: the owner's method, computed in COMMUNITY_REF."""
    return {
        "method_id": "pob-community-v2",
        "decision": D07_AMENDMENT_2,
        "owner_verbatim": OWNER_DECISION_2,
        "per_use_damage": "PoB AverageBurstDamage of Flicker Strike at the build's maximum Power Charges with the Charged Staff buff as PoB applies it (charges assumed); per strike = AverageDamage, credited at each strike's end",
        "rotation": ["Whirling Assault", "Charged Staff", "repeat (Whirling Assault, Flicker Strike) until the Charged Staff buff expires", "repeat from Whirling Assault, Charged Staff"],
        "time": "PoB Time of Whirling Assault and Charged Staff; Flicker Strike H / Speed; all inside [0, 120)",
        "buff_duration": "6 s per stack (ChargedStaffBuffDuration) x (1 + increased duration) x stacks consumed, from PoB",
        "reported_beside": "plain PoB AverageBurstDamage and TotalDPS at maximum charges; the community reference's condition inputs on the seed",
        "not_a_verified_mechanic": "Hit and Run reuse and charge availability are the owner's chosen method.",
        "waived_by_decision": [{"gap_id": g, "evidence": D07_AMENDMENT_2, "why": w} for g, w in COMMUNITY_WAIVED],
        "still_blocking_a_supported_score": list(COMMUNITY_STILL_BLOCKING),
        "computation": COMMUNITY_REF,
    }


def pob_cycle_method():
    """pob-cycle-v1: the flicker_sustained_v1 computation, defined, not run."""
    t = _charge_table()
    rows = t["flicker_by_charges"]
    table = "docs/evidence/P09-T01.1/pob-charge-table.json"
    return {
        "method_id": "pob-cycle-v1",
        "required_gap_ids": list(POB_CYCLE_REQUIRED_GAPS),
        "damage_source": "Path of Building on the pinned engine (D07 amendment 2026-10-18)",
        "target": "flicker_sustained_v1 PoB enemy configuration (target_entities fields)",
        "inputs": [
            {"name": "t_WA", "meaning": "seconds per Whirling Assault use",
             "source": "PoB output Time (= 1 / Speed) with socket group 8 as main skill; " + table + " whirling_assault",
             "seed_value": t["whirling_assault"]["Time"]},
            {"name": "S_F(c)", "meaning": "Flicker Strike strikes per second at c Power Charges",
             "source": "PoB output Speed with Flicker Strike as main skill (includes the skill's 285% more attack speed and Hit and Run's 40% more skill speed); " + table,
             "seed_values": {str(r["power_charges"]): r["Speed"] for r in rows}},
            {"name": "H(c)", "meaning": "strikes per Flicker Strike use",
             "source": "PoB AverageBurstHits = 1 + AdditionalFlickersPerPowerCharge (2 per removable charge); skill/FlickerStrikePlayer preDamageFunc, statdesc/flicker_strike_additional_flickers_from_power_charges",
             "seed_values": {str(r["power_charges"]): r["AverageBurstHits"] for r in rows}},
            {"name": "D(c)", "meaning": "damage per Flicker Strike use at c Power Charges",
             "source": "PoB AverageBurstDamage at c forced charges (0: usePowerCharges unset); " + table + ". Which table (Charged Staff enabled or disabled) is gap-p09-t011-charged-staff-shared-charges",
             "seed_values_charged_staff_enabled": {str(r["power_charges"]): r["AverageBurstDamage"] for r in rows}},
            {"name": "C_max", "meaning": "maximum Power Charges", "source": "PoB PowerChargesMax", "seed_value": 5},
            {"name": "p", "meaning": "Power Charge chance per Combo expended",
             "source": "Ailith's Chimes chance_%_to_gain_power_charges_per_combo_spent 25, 'Surpassing' (support/SupportAilithLineagePlayer)", "value": 0.25},
            {"name": "K_max", "meaning": "Combo cap of the Culmination-supported skill",
             "source": "Culmination II skill_maximum_number_of_combo_stacks 10", "value": 10},
            {"name": "q", "meaning": "chance a consumed charge is not removed",
             "source": "Perpetual Charge charge_skip_consume_chance_% 25 (support/SupportPerpetualChargePlayer)", "value": 0.25},
            {"name": "g", "meaning": "Combo Whirling Assault gains per Flicker Strike strike and per own hit",
             "source": "unknown", "value": None, "gap_id": "gap-p09-t011-charge-cycle-rules"},
            {"name": "m_F, m_WA", "meaning": "mana per use",
             "source": "PoB ManaCost, groups 6 and 8", "seed_values": {"m_F": rows[0]["ManaCost"], "m_WA": t["whirling_assault"]["ManaCost"]}},
        ],
        "procedure": [
            "Prerequisites: every required_gap_id must be resolved with evidence. Before the first and each subsequent Flicker Strike use, establish Hit and Run activation. If teleport does not re-enable it, account for an evidenced movement action and its elapsed time, or stop with a blocking gap. Unassigned secondary damage cannot enter D(c) or the score; attribution must be accepted before computation.",
            "1. t = 0: 0 Power Charges, 0 Combo, persistent Spirit skills active (owner Q4), energy shield and mana full.",
            "2. Cycle k = 1, 2, ...: one Whirling Assault use lasting t_WA, then one Flicker Strike use (owner Q1, Q2). Charged Staff's place is gap-p09-t011-rotation-details; no value is computed until it closes.",
            "3. At Whirling Assault use k, Combo K_k = min(K_max, Combo gained since the previous Whirling Assault use, per g). It is expended; the Power Charges gained follow Ailith's Chimes, expected p x K_k, with the distribution the Surpassing rule gives (gap-p09-t011-charge-cycle-rules). Charges held C_k = min(C_max, carried_k + gained_k). Flicker Strike's 'cannot gain Power Charges while using this Skill' means no charge is gained during step 4.",
            "4. Flicker Strike use k performs H(C_k) strikes, each lasting 1 / S_F(C_k) (gap-p09-t011-flicker-strike-timing). D(C_k) is credited in equal parts D(C_k) / H(C_k) at each strike's end. Over a charge distribution, use E[D] = sum over c of P(C_k = c) x D(c); never interpolate D between charge counts.",
            "5. Charges carried into cycle k + 1: each consumed charge is kept with probability q (Perpetual Charge), capped at C_max.",
            "6. flicker_sustained_dps = credited damage whose strike ends in [0, 120) divided by 120. flicker_burst_dps = credited damage whose strike ends in [0, 5) divided by 5, from the same t = 0 state. Only completed strikes count at a window end.",
            "7. Report mana: m_WA per Whirling Assault use and m_F per Flicker Strike use against maximum mana and regeneration; flask use is gap-p09-t011-sustain-cycle. Report whether the cycle reaches a repeating charge state (D07 item 6).",
            "8. Whirling Assault's own damage and every other skill's damage are reported separately and never enter the score (D07 item 3).",
        ],
        "community_method_difference": (
            "The community reference (poe.ninja 25c49) reads AverageBurstDamage "
            "at forced charges (7, above its maximum of 6) with forced Combo, "
            "Rage, Onslaught and enemy conditions: burst per use, no charge "
            "generation time. pob-cycle-v1 uses the same PoB outputs but only "
            "charges the rotation generates, and divides by elapsed time "
            "including each Whirling Assault use. PoB TotalDPS (AverageDamage "
            "x Speed) also ignores charge generation time."),
        "status": "Defined, not computed. Blocking: " + ", ".join(
            g for g in POB_CYCLE_REQUIRED_GAPS if g not in RESOLVED_PREREQUISITES) + ".",
        "resolved_prerequisites": sorted(RESOLVED_PREREQUISITES),
        "rule_table": RULES_REF,
    }


def dps_scenario(mechanics_ids):
    obj = FLICKER_SUSTAINED_DPS_V1
    windows = {w.name: [w.start_s, w.end_s] for w in obj.windows}
    enemy = _charge_table()["enemy"]
    for m in ("engine/pinnacle-enemy-preset", "engine/enemy-is-boss-option"):
        assert m in mechanics_ids, m
    f = {
        "scenario_id": F("decision_D07", "docs/decisions/D07-flicker-strike-objective.md item 1", DPS_ID),
        "version": F("decision_D07", "D07: separately versioned benchmark", "1"),
        "category": F("decision_D07", "D07: controlled damage benchmark alongside the four scenarios", "dps_benchmark"),
        "kind": F("decision_D07", "D07 amendment 2026-10-18: PoB calculation benchmark", "pob_calculation"),
        "objective": F("decision_D07", "pob2opt/domain/objectives.py FLICKER_SUSTAINED_DPS_V1",
                       {"objective_id": obj.objective_id, "version": obj.version,
                        "target_skill": {"gem_id": obj.target_skill.gem_id,
                                         "granted_skill_id": obj.target_skill.granted_skill_id}}),
        "window_s": F("decision_D07", "D07 item 2; objectives.py sustained window", windows["sustained"]),
        "burst_window_s": F("decision_D07", "D07 item 5; objectives.py burst window", windows["burst"]),
        "metric_definition": F("decision_D07", "D07 items 3 and 5", {
            "flicker_sustained_dps": "attributed_damage_in_[0,120) / 120",
            "flicker_burst_dps": "attributed_damage_in_[0,5) / 5, same initial conditions, never the most favourable segment",
        }),
        "target_entities.count": F("decision_D07", "D07 item 1: one enemy", 1),
        "target_entities.dies": F("decision_D07", "D07 item 1: non-dying; a PoB calculation has no death", False),
        "target_entities.targetable_windows": F("decision_D07", "D07 item 1: continuously targetable", [[0.0, 120.0]]),
        "target_entities.identity": F("decision_D07", "D07 amendment 2026-10-18; engine/enemy-is-boss-option, engine/pinnacle-enemy-preset",
                                      {"pob_config": {"enemyIsBoss": "Pinnacle", "presetBossSkills": "None"},
                                       "label": "Guardian/Pinnacle Boss", "engine_commit": "ce566eac45ea8a86477f513c7ee65a1ebe60014e"}),
        "target_entities.level": F("catalog", "engine/pinnacle-enemy-preset: defaultLevel 82; read back by PoB (pob-charge-table.json enemy)",
                                   enemy["enemyLevel"]),
        "target_entities.defenses": F("catalog", "engine/pinnacle-enemy-preset: elemental resist 50, chaos 0, armour and evasion from the monster tables at level 82; values read back by PoB (pob-charge-table.json enemy)",
                                      {"resist": enemy["resist"], "armour": enemy["Armour"], "evasion": enemy["Evasion"]}),
        "target_entities.conditions": F("unresolved", "Enemy and player condition inputs must be sustained by the build, not toggled (D07 item 2)", None,
                                        ["gap-p09-t011-config-conditions"]),
        "target_entities.health": F("decision_D07", "D07 amendment: the PoB calculation does not model target life or death", "not modelled"),
        "adds": F("decision_D07", "D07 item 4: no adds", []),
        "kill_events": F("decision_D07", "D07 item 4: no kill events; on-kill dependencies are unavailable", []),
        "initial_state.resources": F("protocol_choice",
                                     "D07 item 2: stated, obtainable state, no free maximum-state toggles. Proposed: 0 Power Charges, 0 Combo, energy shield and mana full. Needs reviewer acceptance",
                                     {"power_charges": 0, "combo": 0, "energy_shield": "full", "mana": "full"}),
        "allowed_preparation": F("owner_statement", "D07 item 2 (preparation inside the window); owner Q4: Spirit skills persistent and active from t = 0, Pounce movement only",
                                 {"inside_window": True, "party_buffs": False,
                                  "persistent_skills": PERSISTENT_SKILLS, "excluded_from_rotation": ["Pounce"]}),
        "movement_model_id": F("owner_statement", "Owner Q5: the Flicker Strike dash supplies Hit and Run's movement; no separate movement action",
                               "none", ["gap-p09-t011-hit-and-run-movement", "gap-p09-t011-flicker-strike-timing"]),
        "spatial_model_id": F("decision_D07", "D07 amendment: PoB calculation, no positions", "none"),
        "incoming_damage_model_id": F("decision_D07", "D07 amendment: PoB calculation, no incoming damage", "none"),
        "duration_limit_s": F("decision_D07", "D07 item 2: fixed window", 120.0),
        "completion_condition": F("decision_D07", "D07 items 2 and 4", {
            "type": "fixed_window",
            "start_event": "Scenario time zero with the stated initial state.",
            "completion_event": "t = 120 s. No kill or completion event exists.",
            "failure_events": ["character death"],
        }),
        "attribution_rules": F("protocol_choice",
                               "D07 item 3. Proposed: only Flicker Strike's own PoB AverageBurstDamage counts; other skills reported separately",
                               {"counted": "Flicker Strike main skill AverageBurstDamage",
                                "reported_separately": ["Whirling Assault", "Living Lightning", "Herald of Ice",
                                                        "Herald of Thunder", "Wind Dancer", "Trinity",
                                                        "Remnants of Kalguur", "Charged Staff"]},
                               ["gap-p09-t011-attribution-rules", "gap-p09-t011-charged-staff-shared-charges"]),
        "measurement_method": F("decision_D07", "D07 amendment 2026-10-18; method defined in benchmarks/p09-flicker-v1/protocol.md",
                                pob_cycle_method(),
                                [*POB_CYCLE_REQUIRED_GAPS, "gap-p09-t011-flicker-strike-timing"]),
        "gameplay_recordings": F("decision_D07", "D07 amendment: optional validation, not a prerequisite", "optional"),
        "benchmark_method": F("decision_D07", "D07 amendment 2026-10-18 (2): the owner's community-PoB method is the benchmark's method; pob-cycle-v1 stays defined for a generated-charge evaluation",
                              {"primary": "pob-community-v2", "generated_charges": "pob-cycle-v1"}),
        "community_method": F("decision_D07", "D07 amendment 2026-10-18 (2)", community_method(),
                              list(COMMUNITY_STILL_BLOCKING)),
        "sustain_report": F("decision_D07", "D07 item 6: report depletion and whether the cycle repeats",
                            {"required": True, "repeatable_cycle": None},
                            ["gap-p09-t011-sustain-cycle", "gap-p09-t011-charge-cycle-rules"]),
        "survival_gates": F("specification", "docs/specs/scenarios.md (deaths). No incoming damage in the PoB calculation, so no energy shield gate applies",
                            [SURVIVAL_DEATHS]),
        "pob_proxy": F("seed_export", "docs/evidence/P09-T01.1/seed/manifest.json pob_proxy_flicker_main",
                       {"label": "proxy_only", "path": "docs/evidence/P09-T01.1/seed/stats-flicker-main.json"},
                       ["gap-p09-t011-engine-checkout-state"]),
        "pob_inputs": F("seed_export", "PoB outputs at 0 to 5 charges and Whirling Assault; PoB-derived",
                        {"path": "docs/evidence/P09-T01.1/pob-charge-table.json"},
                        ["gap-p09-t011-engine-checkout-state"]),
    }
    f.update(common_fields(DPS_ID))
    return {"scenario_id": DPS_ID, "version": "1", "category": "dps_benchmark",
            "shape": "flicker_sustained_v1", "fields": f}


def build_rotation(facts):
    return {
        "rotation_id": ROTATION_ID,
        "version": "3",
        "owner_statement_verbatim": OWNER_ROTATION,
        "owner_decision_2_verbatim": OWNER_DECISION_2,
        "received": "2026-10-17",
        "answers_received": "2026-10-18",
        "source": "Owner (Elias), P09-T01.1 assignment and answers Q1 to Q9",
        "cycle": {
            "opener": "Whirling Assault (Q2: 'whirling assault')",
            "repeat": ["Whirling Assault x1 (Q1: 'just 1')", "Flicker Strike x1"],
            "charged_staff": "Pressed after a Whirling Assault, then again when its buff expires (owner decision 2026-10-18 (2)); period from the buff duration",
            "persistent_buffs_not_pressed": PERSISTENT_SKILLS,
            "movement_only": ["Pounce (Q4: 'I press pounce, but only for mobility')"],
            "hit_and_run_movement": "Flicker Strike's dash (Q5: 'the dash from flicker itself'); unverified by the catalog",
            "mana": "Mana flask on bosses; mana on kill does nothing there (Q6)",
        },
        "derived_from_evidence": [
            {"claim": "Whirling Assault in the seed carries Culmination II and Ailith's Chimes (skill group 8).",
             "source": "docs/evidence/P09-T01.1/seed/skill-groups.json"},
            {"claim": "Culmination II adds ComboStacking, holds up to 10 Combo gained from strikes with other melee attacks, expends all Combo on use, decay delay 6000 ms.",
             "mechanic_ids": ["support/SupportCulminationPlayerTwo", "statdesc/skill_maximum_number_of_combo_stacks"]},
            {"claim": "Ailith's Chimes requires ComboStacking and gives a 25% Surpassing chance per Combo expended to gain a Power Charge. This is the seed's only cited Power Charge source.",
             "mechanic_ids": ["support/SupportAilithLineagePlayer", "statdesc/chance_%_to_gain_power_charges_per_combo_spent"]},
            {"claim": "Seed ascendancy: Martial Adept (additional Combo when gaining Combo) and Martial Master (Combo from all Attack Hits) are allocated.",
             "mechanic_ids": ["passive/41751", "passive/61586"], "source": "docs/evidence/P09-T01.1/seed/passive-nodes.json"},
            {"claim": "Maximum Power Charges 5: base 3 plus Overflowing Power +2, matching the owner's 5.",
             "mechanic_ids": ["passive/65204"], "source": "docs/evidence/P09-T01.1/seed/stats-flicker-main.json"},
            {"claim": "Flicker Strike consumes Power Charges for 2 additional teleporting strikes per charge and cannot gain Power Charges while used. PoB models the extra strikes as 2 x removable Power Charges (AverageBurstHits 1, 3, 5, 7, 9, 11 at 0 to 5 charges).",
             "mechanic_ids": ["skill/FlickerStrikePlayer", "statdesc/flicker_strike_additional_flickers_from_power_charges",
                              "statdesc/cannot_gain_power_charges_during_skill", "engine/removable-power-charges"],
             "source": "docs/evidence/P09-T01.1/pob-charge-table.json"},
            {"claim": "Perpetual Charge on Flicker Strike: 25% chance to not remove Charges but still count as consuming them.",
             "mechanic_ids": ["support/SupportPerpetualChargePlayer", "statdesc/charge_skip_consume_chance_%"]},
            {"claim": "Hit and Run on Flicker Strike: usable after moving 10 metres, unusable again after use, 40% more skill speed.",
             "mechanic_ids": ["support/SupportHitAndRunPlayer", "statdesc/skill_unusable_until_moved_X_distance"]},
            {"claim": "Charged Staff consumes all Power Charges and requires 1; in PoB its per-charge buff reads the same charges Flicker Strike's strikes do.",
             "mechanic_ids": ["skill/ChargedStaffPlayer"], "source": "docs/evidence/P09-T01.1/pob-charge-table.json"},
            {"claim": "Mana: Flicker Strike 85 base cost at gem level 20; PoB shows %d per use, Whirling Assault 160, against %d maximum mana (proxy_only)." % (
                facts["flicker_mana_cost_per_use"], facts["mana"]),
             "mechanic_ids": ["skill/FlickerStrikePlayer"], "source": "docs/evidence/P09-T01.1/pob-charge-table.json"},
        ],
        "unresolved": [
            {"question_id": "Q10", "gap_ids": ["gap-p09-t011-rotation-details", "gap-p09-t011-charged-staff-shared-charges",
                                               "gap-p09-t012-charged-staff-period"]},
            {"question_id": "Q5", "gap_ids": ["gap-p09-t011-hit-and-run-movement"]},
            {"question_id": "Q6", "gap_ids": ["gap-p09-t011-sustain-cycle"]},
            {"question_id": "Q1", "gap_ids": ["gap-p09-t011-charge-cycle-rules"]},
        ],
        "not_a_rotation_policy": (
            "Not a RotationPolicy record: Charged Staff's predicate and place "
            "are unresolved, and writing them would invent what the owner "
            "has not stated."),
    }


#: (id, question, status). Q1 to Q9 answered 2026-10-18; answers in the seed
#: manifest. Q10 and Q11 follow from the answers.
QUESTIONS = [
    ("Q1", "Whirling Assault uses per Flicker Strike.", "answered"),
    ("Q2", "Opener at 0 charges and 0 Combo.", "answered"),
    ("Q3", "When Charged Staff is pressed.", "answered"),
    ("Q4", "Which buff and utility skills are pressed.", "answered"),
    ("Q5", "What supplies Hit and Run's 10 metres.", "answered"),
    ("Q6", "Mana flask use.", "answered"),
    ("Q7", "Maps and bosses.", "answered in part: T16 maps, ailment threshold weak case; no map or boss named"),
    ("Q8", "Benchmark target.", "answered: decision 1, PoB is the damage source"),
    ("Q9", "Class and variant scope.", "answered: decision 2, all approved"),
    ("Q10", "Charged Staff consumes all Power Charges. In the cycle, do you press it after Whirling Assault and before Flicker Strike (taking the charges Flicker Strike would use), after Flicker Strike on a charge Perpetual Charge kept, or at another point? About how often?", "answered: once per N cycles (Q10), then the full rotation in owner decision 2026-10-18 (2)"),
    ("Q11", "Which T16 maps (one with packs close together, one spread out) and which two bosses (one you kill without breaks, one with phases or untargetable time) do you run? Are PoB's Pinnacle and Uber tiers acceptable enemy configurations for them?", "open"),
]


# ------------------------------------------------------------ references ===

def build_references(seed_manifest):
    as_imported = next(f for f in seed_manifest["files"] if f["path"].endswith("export-as-imported.xml"))
    return {
        "suite_id": SUITE_ID,
        "task": TASK,
        "reference_policy": (
            "docs/specs/scenarios.md: one approved reference build and result "
            "per scenario, legal and complete, evaluated under identical "
            "rules, frozen before a comparison campaign."),
        "candidates": [{
            "reference_candidate_id": SEED_REF_ID,
            "source": "docs/evidence/P09-T01.1/seed/manifest.json",
            "configuration_document": as_imported["path"],
            "configuration_sha256": as_imported["sha256"],
            "status": "candidate_configuration_only",
            "scenario_ids": ALL_IDS,
            "closes": [],
            "begins": ["gap-p09-t011-reference-result"],
            "note": "An export carries no trial. A reference result needs an accepted observation of this configuration on each workload, and an accepted pob-cycle-v1 result for flicker_sustained_v1.",
        }],
        "scenarios": [{
            "scenario_id": sid,
            "reference_build_id": None,
            "reference_result_id": None,
            "reference_status": "unresolved",
            "candidate_ids": [SEED_REF_ID],
            "gap_ids": ["gap-p09-t011-reference-result"],
        } for sid in ALL_IDS],
    }


# ---------------------------------------------------------------- output ===

def _dump(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, indent=2, ensure_ascii=False) + "\n"
    data = text.encode("utf-8")
    path.write_text(text, encoding="utf-8", newline="\n")
    return {"path": path.relative_to(REPO_ROOT).as_posix(), "sha256": _sha(data), "bytes": len(data)}


def _file_ref(path):
    data = path.read_bytes()
    return {"path": path.relative_to(REPO_ROOT).as_posix(), "sha256": _sha(data), "bytes": len(data)}


def suite_identity(scenarios, references):
    """What the suite hash freezes: each definition hash and its reference slots."""
    refs = {r["scenario_id"]: r for r in references["scenarios"]}
    return {"scenarios": sorted((
        {"scenario_id": s["scenario_id"], "version": s["version"],
         "definition_hash": content_hash(s),
         "reference_build_id": refs[s["scenario_id"]]["reference_build_id"],
         "reference_result_id": refs[s["scenario_id"]]["reference_result_id"]}
        for s in scenarios), key=lambda x: (x["scenario_id"], x["version"]))}


def build_all():
    mechanics = load_mechanics()
    facts = seed_facts()
    seed_manifest = build_seed_manifest()
    scope = build_scope(mechanics)
    gaps = build_gaps()
    failures = [(g.record_id, [str(e) for e in validate_record(g).errors]) for g in gaps]
    failures = [f for f in failures if f[1]]
    if failures:
        raise SystemExit("invalid gaps: %s" % failures)
    gap_ids = {g.gap_id for g in gaps}
    scenarios = [encounter_scenario(s) for s in ENC_IDS] + [dps_scenario(mechanics[1])]
    for s in scenarios:
        for name, field in s["fields"].items():
            for g in field["gap_ids"]:
                if g not in gap_ids:
                    raise SystemExit("%s.%s names unknown gap %s" % (s["scenario_id"], name, g))
    rotation = build_rotation(facts)
    references = build_references(seed_manifest)
    bundle = {
        "suite_id": SUITE_ID,
        "task": TASK,
        "kind": "representative_protocol",
        "status": "proposed, not accepted",
        "not_a_claim": NOT_A_CLAIM,
        "schema_version": 1,
        "generated_by": "scripts/p09_t01_1_flicker_suite.py",
        "protocol": "benchmarks/%s/protocol.md" % SUITE_ID,
        "field_bases": {
            "specification": "Stated by docs/specs (scenarios.md, contracts.md, product.md).",
            "decision_D07": "Fixed by docs/decisions/D07-flicker-strike-objective.md.",
            "product_default": "A product default from docs/specs.",
            "seed_export": "Read from the stored seed export (configuration, not performance).",
            "catalog": "Read from the pinned catalog export or engine data.",
            "owner_statement": "The owner's verbatim rotation or answers (seed/manifest.json owner_answers).",
            "protocol_choice": "Proposed by this protocol; needs reviewer acceptance.",
            "unresolved": "Unknown. Value null; gap_ids say what closes it.",
        },
        "seed_facts": facts,
        "scenarios": scenarios,
        "rotation": rotation,
        "owner_questions": [{"question_id": q, "question": t, "status": st}
                            for q, t, st in QUESTIONS],
        "data_gaps": [to_jsonable(g) for g in gaps],
    }
    return seed_manifest, scope, bundle, references, scenarios


def main() -> int:
    write_share_code()
    seed_manifest, scope, bundle, references, scenarios = build_all()
    seed_ref = _dump(SEED_MANIFEST_PATH, seed_manifest)
    scope_ref = _dump(SCOPE_PATH, scope)
    scen_ref = _dump(SCENARIOS_PATH, bundle)
    refs_ref = _dump(REFERENCES_PATH, references)
    mech_bytes = MECHANICS_PATH.read_bytes()
    identity = suite_identity(scenarios, references)
    suite = {
        "suite_id": SUITE_ID,
        "task": TASK,
        "kind": "representative_protocol",
        "status": "proposed, not accepted",
        "not_a_claim": NOT_A_CLAIM,
        "protocol": "benchmarks/%s/protocol.md" % SUITE_ID,
        "hashing": (
            "File entries: SHA-256 of the raw bytes (identity.document_hash). "
            "definition_hash: identity.content_hash (canonical JSON SHA-256) "
            "of each scenario object in scenarios.json. suite_hash: "
            "content_hash of suite_identity, the sorted definition hashes with "
            "their reference slots. Representative ScenarioSpec records cannot "
            "be written while required fields are unknown, so scenario_hash "
            "over ScenarioSpec does not apply yet."),
        "sources": {
            "scenarios": scen_ref,
            "references": refs_ref,
            "seed_manifest": seed_ref,
            "scope_proposal": scope_ref,
            "mechanics": {"path": MECHANICS_PATH.relative_to(REPO_ROOT).as_posix(),
                          "sha256": _sha(mech_bytes), "bytes": len(mech_bytes)},
            "pob_charge_table": _file_ref(CHARGE_TABLE_PATH),
            "reference_ninja_share_code": _file_ref(NINJA_DIR / "share-code.txt"),
            "reference_ninja_decoded": _file_ref(NINJA_DIR / "decoded.xml"),
            "reference_ninja_evaluation": _file_ref(NINJA_DIR / "evaluation.json"),
        },
        "scenarios": [
            {"scenario_id": x["scenario_id"], "version": x["version"],
             "definition_hash": x["definition_hash"],
             "reference_build_id": x["reference_build_id"],
             "reference_result_id": x["reference_result_id"],
             "reference_status": "unresolved"}
            for x in identity["scenarios"]],
        "suite_hash": content_hash(identity),
        "suite_hash_note": (
            "Both reference slots are null for every scenario. Freezing a "
            "reference later changes this hash and starts a separate "
            "leaderboard."),
        "open_gaps": [g["gap_id"] for g in bundle["data_gaps"] if g["status"] == "open"],
        "resolved_gaps": [g["gap_id"] for g in bundle["data_gaps"] if g["status"] == "resolved"],
        "usable_for": [
            "computing flicker_sustained_v1 with pob-cycle-v1 once its blocking gaps close",
            "the owner's answers and recordings that P09-T02 collection needs",
            "reviewer acceptance of scope, variants and protocol before any constant is fitted",
        ],
        "not_usable_for": [
            "any statement about clear speed, kill time or DPS",
            "calibrating or fitting any constant",
            "ranking real builds",
            "a D04 practical claim",
        ],
    }
    _dump(SUITE_PATH, suite)
    print("suite %s" % SUITE_ID)
    print("  scenarios.json  sha256 %s" % scen_ref["sha256"])
    print("  references.json sha256 %s" % refs_ref["sha256"])
    print("  suite_hash      %s" % suite["suite_hash"])
    print("  gaps %d" % len(bundle["data_gaps"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
