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
                "proposed_first_campaign": asc == "Martial Artist",
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
            "benchmark_applicability": "Needs a benchmark target that can be Shocked; unknown until gap-p09-t011-benchmark-target closes. No kill event in the cited text.",
            "gap_ids": ["gap-p09-t011-variant-exports", "gap-p09-t011-benchmark-target"],
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
        "status": "proposed, not accepted. Product scope is the owner's decision.",
        "kind": "PoB-derived proposal",
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
            "unusable for any of them. Proposed for the first campaign: Monk / "
            "Martial Artist only, because it is the only one with an export. "
            "Adding others is the owner's call."),
        "variants": variants,
        "variant_distinctness": (
            "The three variants differ in the event that grants the Power "
            "Charges Flicker Strike consumes: Combo expenditure, Shock "
            "consumption, enemy kill or cull. Each needs a different skill. "
            "Only the first has an export."),
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
         needed_evidence, collection_method, mechanic_ids=()):
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
        status=GapStatus.OPEN,
        resolution_evidence_ids=[],
    )


B, R, I = GapSeverity.BLOCKING, GapSeverity.RANKING_SENSITIVE, GapSeverity.INFORMATIONAL
MI, UE, UR = GapKind.MISSING_INPUT, GapKind.UNRESOLVED_ENTITY, GapKind.UNSUPPORTED_RULE


def build_gaps():
    return [
        _gap("gap-p09-t011-encounter-selection", MI, B, ENC_IDS, ["/encounter"],
             "No named area or boss is selected for any of the four shapes. The "
             "owner's rotation names no encounter.",
             "For each shape, one named area or boss the owner runs with this "
             "character: area name, area level or waystone tier, map "
             "modifiers, and for the boss shapes the boss name. One per shape.",
             "Owner answer to Q7 in benchmarks/p09-flicker-v1/protocol.md; a "
             "reviewer checks each against its shape in docs/specs/scenarios.md."),
        _gap("gap-p09-t011-enemy-health", MI, B, ALL_IDS, ["/target_entities/*/health"],
             "No PoE 2 monster life is held. A recording's health bar is a "
             "fraction of an unknown maximum.",
             "Maximum life of each named monster and boss at a stated area "
             "level, rarity and patch, with the catalog row or experiment it "
             "came from. One value per entity.",
             "An identified catalog row from an accepted patch profile, or a "
             "controlled experiment with a known damage figure. A health bar "
             "alone does not close this."),
        _gap("gap-p09-t011-enemy-defenses", MI, B, ALL_IDS,
             ["/target_entities/*/defenses", "/target_entities/*/level"],
             "No monster level, resistance, armour or evasion is held. "
             "Mitigation is not visible in a recording.",
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
        _gap("gap-p09-t011-spatial-unit", UE, B, ALL_IDS,
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
        _gap("gap-p09-t011-movement-model", UR, B, CLEAR_IDS + [DPS_ID],
             ["/movement_model_id"],
             "No pathfinding is implemented. Clear routes and the movement "
             "Hit and Run needs before each Flicker Strike have no model.",
             "Per-leg route times for each named clear area, and the time the "
             "owner spends moving between Flicker Strike uses, read off a "
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
             "needs an observed result on the scenario; an export holds none.",
             "For each scenario, an accepted configuration (the seed is the "
             "candidate) and an accepted observation of it on that scenario: "
             "completion time for the four workloads, attributed damage in "
             "[0, 120) for flicker_sustained_v1.",
             "P09-T02 observation import of owner recordings after this "
             "protocol is accepted; reviewer acceptance freezes the reference."),
        _gap("gap-p09-t011-benchmark-target", MI, B, [DPS_ID],
             ["/target_entities/0/identity", "/target_entities/0/level",
              "/target_entities/0/defenses", "/target_entities/0/health",
              "/incoming_damage_model_id"],
             "D07 needs one non-dying, continuously targetable enemy with "
             "evidenced level and defenses. No such in-game target is "
             "identified; whether one exists is unverified. Whether it can be "
             "Shocked, how it avoids dying and whether it deals damage are "
             "unknown.",
             "Identity of an in-game enemy that stays alive and targetable for "
             "120 s, its level, resistances, armour, evasion, life handling, "
             "whether it can be Shocked, and whether it deals damage, each with "
             "its source. Or a reviewer-approved substitute target.",
             "Owner answer to Q8, then catalog rows for that monster from an "
             "accepted patch profile."),
        _gap("gap-p09-t011-benchmark-measurement", UR, B, [DPS_ID],
             ["/measurement_method"],
             "P09-T02 needs a feasible way to measure attributed damage in "
             "[0, 120) in game. The game shows no damage total. Kill time "
             "without evidenced enemy health cannot become DPS.",
             "A measurement method that yields damage dealt by Flicker Strike "
             "over [0, 120) on the benchmark target, with its uncertainty, "
             "accepted by a reviewer before collection.",
             "Method study once the benchmark target is known, for example a "
             "target with catalog-evidenced life and a recorded life fraction "
             "per second; reviewer acceptance required."),
        _gap("gap-p09-t011-attribution-rules", UR, B, [DPS_ID],
             ["/attribution_rules"],
             "The seed has damage sources whose ownership relative to Flicker "
             "Strike is not reviewed: Herald of Ice and Herald of Thunder, "
             "Living Lightning minions from the Whirling Assault group, "
             "Charged Staff's added lightning and shockwave on Quarterstaff "
             "attacks, Wind Dancer's Gale Force, Trinity, Remnants of Kalguur.",
             "A reviewed rule per seed damage source: counted as Flicker "
             "Strike damage, reported separately, or excluded, with the "
             "catalog or mechanic evidence for each.",
             "P07-T02 attribution rule review against the catalog; the owner's "
             "answer to Q4 limits which sources are active.",
             ["skill/ChargedStaffPlayer"]),
        _gap("gap-p09-t011-rotation-details", MI, B, ALL_IDS, ["/rotation_id"],
             "The owner's rotation is one sentence. It does not state how many "
             "Whirling Assault uses produce 5 charges, what happens at 0 charges "
             "and 0 Combo, when Charged Staff is used, which buffs are pressed, "
             "how the Hit and Run movement is supplied, or flask use.",
             "Owner answers to Q1 to Q6, and one recording of the cycle on a "
             "boss with the charge counter legible.",
             "Owner answers in writing plus a recording; a reviewer checks the "
             "rotation record against both."),
        _gap("gap-p09-t011-charge-cycle-rules", UR, B, [DPS_ID] + BOSS_IDS,
             ["/rotation_id", "/sustain_report"],
             "Catalog text gives the parts, not the game semantics: what "
             "'Surpassing chance' yields for 25% per Combo, whether Whirling "
             "Assault gains Combo from its own hits under Martial Master, "
             "whether Martial Adept's extra Combo counts against the 10 Combo "
             "cap, whether Flicker Strike consumes all charges per use, how "
             "Perpetual Charge interacts with the strike count, and when the "
             "'cannot gain Power Charges' window ends.",
             "For each question, game evidence: a recording with the Combo and "
             "Power Charge counters legible over at least 20 cycles, or an "
             "official statement.",
             "Owner recordings, counted frame by frame; a reviewer accepts the "
             "count before any rule is implemented.",
             ["support/SupportAilithLineagePlayer", "support/SupportCulminationPlayerTwo",
              "passive/41751", "passive/61586", "support/SupportPerpetualChargePlayer",
              "statdesc/cannot_gain_power_charges_during_skill"]),
        _gap("gap-p09-t011-hit-and-run-movement", UR, B, ALL_IDS, ["/movement_model_id"],
             "Hit and Run makes Flicker Strike usable after moving 10 metres "
             "and unusable again after use. Whether Flicker Strike's teleport "
             "or Whirling Assault's advance counts as moving is not stated.",
             "Recorded evidence of which movement re-enables Flicker Strike "
             "with Hit and Run: walking, dodge roll, Whirling Assault, the "
             "Flicker teleport itself.",
             "Owner answer to Q5 and a recording of the cycle.",
             ["support/SupportHitAndRunPlayer", "statdesc/skill_unusable_until_moved_X_distance"]),
        _gap("gap-p09-t011-sustain-cycle", MI, B, [DPS_ID], ["/sustain_report"],
             "D07 needs resource depletion and whether the cycle repeats. PoB "
             "shows 248 mana per Flicker Strike use against 887 maximum mana "
             "(proxy_only); mana recovery during the cycle is not evidenced.",
             "Mana and Power Charge readings across at least ten consecutive "
             "cycles on one target, with flask uses marked.",
             "Owner recording with mana and charge counters legible."),
        _gap("gap-p09-t011-patch-profile", GapKind.STALE_PATCH, B, ALL_IDS,
             ["/patch_profile_id"],
             "The catalog verdict is partial: the engine data release predates "
             "0.5.5e and slot-accepted-base-categories is open (P02-T02.1).",
             "An accepted patch profile with compatibility verified for 0.5.5e "
             "or the patch the measurements are taken on.",
             "P02-T02 re-export after an engine data release for the live "
             "patch, plus the D03 decision."),
        _gap("gap-p09-t011-engine-checkout-state", MI, I, [DPS_ID], ["/pob_proxy"],
             "The seed's PoB stats came from the operator's checkout at the "
             "pinned HEAD with an unchecked working tree. They are proxy_only "
             "either way.",
             "A rerun of the stored export in a clean checkout of the pin, "
             "comparing TotalDPS, ManaCost and PowerChargesMax.",
             "Load docs/evidence/P09-T01.1/seed/export-flicker-main.xml in a "
             "clean pinned engine and compare."),
        _gap("gap-p09-t011-variant-exports", MI, B, ["flk-var-shock-consume", "flk-var-cull-kill"],
             ["/variants/*/status"],
             "Only the combo-expenditure variant has an export. P09-T02 needs "
             "complete configurations for every reviewed variant.",
             "One complete export per variant (Siphoning Strike with a Shock "
             "source; Killing Palm) with the rotation played, then enough "
             "configurations for the P09-T02 split.",
             "Owner or independently sourced exports, imported as account "
             "characters or local share codes; no provider scraping."),
        _gap("gap-p09-t011-class-scope-decision", MI, B, ["scope-proposal"],
             ["/ascendancies/*/proposed_first_campaign", "/variants"],
             "The class list and variants are proposals. D07 makes scope the "
             "owner's decision.",
             "The owner's approved ascendancy list for the first campaign and "
             "the approved variants.",
             "Owner answer to Q9, recorded in a review."),
        _gap("gap-p09-t011-survival-threshold", MI, R, ENC_IDS + [DPS_ID],
             ["/survival_gates/1/threshold"],
             "The seed runs Chaos Inoculation (maximum life 1), so its "
             "survivable pool is energy shield. Any margin stricter than "
             "deaths equal zero would be a fitted threshold.",
             "A minimum energy shield fraction per encounter, set from "
             "recorded incoming damage, or an explicit decision to keep "
             "deaths equal zero as the only gate.",
             "Reviewer decision after gap-p09-t011-incoming-damage has data."),
        _gap("gap-p09-t011-initial-resources", MI, R, ALL_IDS, ["/initial_state/resources"],
             "The state at encounter start is not recorded, and whether Power "
             "Charges and Combo persist across area transitions is unknown.",
             "Energy shield, mana, Power Charges and Combo at the start event "
             "of each recorded trial, and whether charges persist after an "
             "area transition.",
             "Owner recordings, read at the start event."),
        _gap("gap-p09-t011-preparation-allowance", MI, R, ALL_IDS, ["/allowed_preparation"],
             "Which pre-encounter actions persist into an encounter (heralds, "
             "Trinity, Wind Dancer, Ghost Dance, weapon swap buffs) is not "
             "recorded.",
             "For each seed buff skill: whether it is active at the start "
             "event and how long it lasts, from recordings.",
             "Owner answer to Q4 plus recordings."),
    ]


# ------------------------------------------------------------- scenarios ===

def F(basis, source, value=None, gaps=()):
    return {"basis": basis, "source": source, "value": value, "gap_ids": list(gaps)}


SHAPES = {
    "p09-flk-clear-dense": ("clear", "clear_dense",
                            "One named area whose packs stand close together; measures time to clear a fixed enemy workload with little travel."),
    "p09-flk-clear-spread": ("clear", "clear_spread",
                             "One named area whose packs are spread along a route; measures time including travel between packs."),
    "p09-flk-boss-short": ("boss", "boss_short",
                           "One named boss that stays targetable; measures time from encounter start to kill."),
    "p09-flk-boss-sustained": ("boss", "boss_sustained",
                               "One named boss with phases or untargetable windows; measures start to kill including the windows that elapse before the kill."),
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
        "reference_result_id": F("unresolved", "No observation exists", None,
                                 ["gap-p09-t011-reference-result"]),
        "rotation_id": F("owner_statement", "Owner rotation, verbatim in scenarios.json rotation",
                         ROTATION_ID, ["gap-p09-t011-rotation-details", "gap-p09-t011-hit-and-run-movement"]),
        "resource_gates": F("specification", "docs/specs/scenarios.md and the seed export", RESOURCE_GATES),
        "evidence_ids": F("seed_export", "Seed manifest, mechanics extract, P02-T02.1 catalog export", [
            "docs/evidence/P09-T01.1/seed/manifest.json",
            "docs/evidence/P09-T01.1/mechanics.json",
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
        "selection_criterion": F("specification", "docs/specs/scenarios.md", criterion),
        "encounter": F("unresolved", "Owner has named no encounter", None, ["gap-p09-t011-encounter-selection"]),
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
                                 "docs/specs/product.md: one configuration across scenarios, no party buffs, no outside resource generation, weapon-set changes allowed when represented and timed",
                                 {"party_buffs": False, "outside_resource_generation": False,
                                  "weapon_set_changes": "allowed when represented and timed"},
                                 ["gap-p09-t011-preparation-allowance"]),
        "capability_floor_ratio": F("specification", "docs/specs/scenarios.md provisional floor", 0.5),
        "survival_gates": F("specification", "docs/specs/scenarios.md (deaths); threshold of the energy shield gate unresolved",
                            [SURVIVAL_DEATHS, SURVIVAL_ES], ["gap-p09-t011-survival-threshold"]),
    }
    f.update(common_fields(sid))
    return {"scenario_id": sid, "version": "1", "category": category, "shape": shape, "fields": f}


def dps_scenario(mechanics_ids):
    obj = FLICKER_SUSTAINED_DPS_V1
    windows = {w.name: [w.start_s, w.end_s] for w in obj.windows}
    f = {
        "scenario_id": F("decision_D07", "docs/decisions/D07-flicker-strike-objective.md item 1", DPS_ID),
        "version": F("decision_D07", "D07: separately versioned benchmark", "1"),
        "category": F("decision_D07", "D07: controlled damage benchmark alongside the four scenarios", "dps_benchmark"),
        "kind": F("specification", "docs/specs/scenarios.md", "representative"),
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
        "target_entities.dies": F("decision_D07", "D07 item 1: non-dying", False),
        "target_entities.targetable_windows": F("decision_D07", "D07 item 1: continuously targetable", [[0.0, 120.0]]),
        "target_entities.identity": F("unresolved", "No in-game target identified", None, ["gap-p09-t011-benchmark-target"]),
        "target_entities.level": F("unresolved", "D07 requires evidenced level", None, ["gap-p09-t011-benchmark-target"]),
        "target_entities.defenses": F("unresolved", "D07 requires evidenced defenses", None,
                                      ["gap-p09-t011-benchmark-target", "gap-p09-t011-enemy-defenses"]),
        "target_entities.health": F("unresolved", "Life handling of a non-dying target and life-threshold conditions unknown", None,
                                    ["gap-p09-t011-benchmark-target", "gap-p09-t011-enemy-health"]),
        "adds": F("decision_D07", "D07 item 4: no adds", []),
        "kill_events": F("decision_D07", "D07 item 4: no kill events; on-kill dependencies are unavailable", []),
        "initial_state.resources": F("protocol_choice",
                                     "D07 item 2: stated, obtainable state, no free maximum-state toggles. Proposed: 0 Power Charges, 0 Combo, energy shield and mana full. Needs reviewer acceptance",
                                     {"power_charges": 0, "combo": 0, "energy_shield": "full", "mana": "full"},
                                     ["gap-p09-t011-initial-resources"]),
        "allowed_preparation": F("decision_D07", "D07 item 2: preparation, support actions and movement count inside the window",
                                 {"inside_window": True, "party_buffs": False},
                                 ["gap-p09-t011-preparation-allowance"]),
        "movement_model_id": F("unresolved", "Hit and Run movement before each Flicker Strike has no model", None,
                               ["gap-p09-t011-movement-model", "gap-p09-t011-hit-and-run-movement", "gap-p09-t011-spatial-unit"]),
        "spatial_model_id": F("unresolved", "No unit conversion", None, ["gap-p09-t011-spatial-unit"]),
        "incoming_damage_model_id": F("unresolved", "Whether the target deals damage is unknown", None,
                                      ["gap-p09-t011-benchmark-target"]),
        "duration_limit_s": F("decision_D07", "D07 item 2: fixed window", 120.0),
        "completion_condition": F("decision_D07", "D07 items 2 and 4", {
            "type": "fixed_window",
            "start_event": "Scenario time zero: first frame of the trial with the stated initial state.",
            "completion_event": "t = 120 s. No kill or completion event exists.",
            "failure_events": ["character death"],
        }),
        "attribution_rules": F("unresolved", "D07 item 3: ambiguous ownership blocks", None,
                               ["gap-p09-t011-attribution-rules"]),
        "measurement_method": F("unresolved", "No in-game damage total", None, ["gap-p09-t011-benchmark-measurement"]),
        "sustain_report": F("decision_D07", "D07 item 6: report depletion and whether the cycle repeats",
                            {"required": True, "repeatable_cycle": None},
                            ["gap-p09-t011-sustain-cycle", "gap-p09-t011-charge-cycle-rules"]),
        "survival_gates": F("specification", "docs/specs/scenarios.md (deaths); energy shield threshold unresolved",
                            [SURVIVAL_DEATHS, SURVIVAL_ES],
                            ["gap-p09-t011-survival-threshold", "gap-p09-t011-benchmark-target"]),
        "pob_proxy": F("seed_export", "docs/evidence/P09-T01.1/seed/manifest.json pob_proxy_flicker_main",
                       {"label": "proxy_only", "path": "docs/evidence/P09-T01.1/seed/stats-flicker-main.json"},
                       ["gap-p09-t011-engine-checkout-state"]),
    }
    f.update(common_fields(DPS_ID))
    return {"scenario_id": DPS_ID, "version": "1", "category": "dps_benchmark",
            "shape": "flicker_sustained_v1", "fields": f}


def build_rotation(facts):
    return {
        "rotation_id": ROTATION_ID,
        "version": "1",
        "owner_statement_verbatim": OWNER_ROTATION,
        "received": "2026-10-17",
        "source": "Owner (Elias), P09-T01.1 assignment",
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
            {"claim": "Flicker Strike consumes Power Charges for 2 additional teleporting strikes per charge and cannot gain Power Charges while used. PoB models the extra strikes as 2 x removable Power Charges.",
             "mechanic_ids": ["skill/FlickerStrikePlayer", "statdesc/flicker_strike_additional_flickers_from_power_charges",
                              "statdesc/cannot_gain_power_charges_during_skill", "engine/removable-power-charges"]},
            {"claim": "Perpetual Charge on Flicker Strike: 25% chance to not remove Charges but still count as consuming them.",
             "mechanic_ids": ["support/SupportPerpetualChargePlayer", "statdesc/charge_skip_consume_chance_%"]},
            {"claim": "Hit and Run on Flicker Strike: usable after moving 10 metres, unusable again after use, 40% more skill speed.",
             "mechanic_ids": ["support/SupportHitAndRunPlayer", "statdesc/skill_unusable_until_moved_X_distance"]},
            {"claim": "Charged Staff, also in the seed, consumes all Power Charges and requires 1: it draws on the same pool.",
             "mechanic_ids": ["skill/ChargedStaffPlayer"]},
            {"claim": "Mana: Flicker Strike 85 base cost at gem level 20; PoB shows %d per use against %d maximum mana (proxy_only)." % (
                facts["flicker_mana_cost_per_use"], facts["mana"]),
             "mechanic_ids": ["skill/FlickerStrikePlayer"], "source": "docs/evidence/P09-T01.1/seed/stats-flicker-main.json"},
        ],
        "unresolved": [
            {"question_id": "Q1", "gap_ids": ["gap-p09-t011-rotation-details", "gap-p09-t011-charge-cycle-rules"]},
            {"question_id": "Q2", "gap_ids": ["gap-p09-t011-rotation-details", "gap-p09-t011-charge-cycle-rules", "gap-p09-t011-initial-resources"]},
            {"question_id": "Q3", "gap_ids": ["gap-p09-t011-rotation-details", "gap-p09-t011-attribution-rules"]},
            {"question_id": "Q4", "gap_ids": ["gap-p09-t011-rotation-details", "gap-p09-t011-preparation-allowance", "gap-p09-t011-attribution-rules"]},
            {"question_id": "Q5", "gap_ids": ["gap-p09-t011-hit-and-run-movement", "gap-p09-t011-movement-model"]},
            {"question_id": "Q6", "gap_ids": ["gap-p09-t011-sustain-cycle"]},
        ],
        "not_a_rotation_policy": (
            "Not a RotationPolicy record: the predicates (charge threshold, "
            "movement condition, buff upkeep) are unresolved, and writing "
            "them would invent the details the owner has not stated."),
    }


QUESTIONS = [
    ("Q1", "After a Flicker Strike, how many Whirling Assault uses do you make before the next Flicker Strike? Do you watch the Power Charge counter reach 5, and what do you do if it shows fewer?"),
    ("Q2", "At the start of a fight, with no charges and no Combo, what do you press first? Does your first Whirling Assault already give Power Charges?"),
    ("Q3", "When do you press Charged Staff? It consumes all Power Charges, the same pool Flicker Strike uses."),
    ("Q4", "Which of Herald of Ice, Herald of Thunder, Wind Dancer, Ghost Dance, Pounce, Trinity, Remnants of Kalguur, Sanguine Revelry (weapon swap) and Quarterstaff Strike do you press during a boss fight, which stay on without pressing, and which do you not use?"),
    ("Q5", "Flicker Strike has Hit and Run (usable after moving 10 metres). What supplies that movement between your Flicker Strikes: Whirling Assault's advance, walking, dodge roll?"),
    ("Q6", "Do you use the mana flask during the cycle, and do you run out of mana?"),
    ("Q7", "Name two maps you run (one with packs close together, one spread out) and two bosses (one you kill without breaks, one with phases or untargetable time), with waystone tier or area level and map modifiers."),
    ("Q8", "Do you know an in-game enemy that does not die and stays targetable for 2 minutes? If not, D07's DPS benchmark stays blocked unless you approve a substitute."),
    ("Q9", "Approve or change the proposed scope: first campaign Monk / Martial Artist only, and the three variants (Combo expenditure, Shock consumption, kill and cull)."),
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
            "note": "An export carries no trial. A reference result needs an accepted observation of this configuration on each scenario.",
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
            "owner_statement": "The owner's verbatim rotation.",
            "protocol_choice": "Proposed by this protocol; needs reviewer acceptance.",
            "unresolved": "Unknown. Value null; gap_ids say what closes it.",
        },
        "seed_facts": facts,
        "scenarios": scenarios,
        "rotation": rotation,
        "owner_questions": [{"question_id": q, "question": t} for q, t in QUESTIONS],
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
        "open_gaps": [g["gap_id"] for g in bundle["data_gaps"]],
        "usable_for": [
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
