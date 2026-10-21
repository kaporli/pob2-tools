"""Clean pinned replay of the Flicker Strike seed (P09-T01.2).

    python scripts/p09_t01_2_seed_replay.py

Loads ``docs/evidence/P09-T01.1/seed/export-flicker-main.xml`` through
``EngineAdapter`` on ``external/PathOfBuilding-PoE2`` (or ``POB2_ROOT``) and
re-reads every value the P09-T01.1 capture took through the operator's MCP
server: the imported Flicker Strike outputs, the 0 to 5 Power Charge table
with Charged Staff enabled and disabled, Whirling Assault and the Pinnacle
enemy. It refuses a checkout whose HEAD is not the pin or whose working tree
is not clean.

A second, direct engine session reads diagnostics the adapter has no typed
operation for: enemy values, every Config-sourced modifier, the conditions and
multipliers PoB holds after the calculation, and the per-source modifiers
behind Flicker Strike's speed and added damage. These are read-only.

It writes ``docs/evidence/P09-T01.2/replay.json``. Everything in it is
PoB-derived: it says what the pinned engine computes, not how the game
behaves.
"""

from __future__ import annotations

import json
import math
import os
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
for _pkg in (REPO_ROOT / "pob2-mcp", REPO_ROOT / "pob2-optimizer"):
    if str(_pkg) not in sys.path:
        sys.path.insert(0, str(_pkg))

SEED_DIR = REPO_ROOT / "docs" / "evidence" / "P09-T01.1" / "seed"
OLD_TABLE = REPO_ROOT / "docs" / "evidence" / "P09-T01.1" / "pob-charge-table.json"
OLD_STATS = SEED_DIR / "stats-flicker-main.json"
SEED_XML = SEED_DIR / "export-flicker-main.xml"
OUT = REPO_ROOT / "docs" / "evidence" / "P09-T01.2" / "replay.json"

PIN = "ce566eac45ea8a86477f513c7ee65a1ebe60014e"
TIMEOUT_S = 300.0
#: Relative tolerance for "agrees with the earlier capture". The earlier values
#: were JSON numbers printed by the same engine; anything above float noise is
#: a real difference and is reported as one.
REL_TOL = 1e-9
MAX_REQUESTS_PER_WORKER = 6

#: Condition inputs the community reference build sets in its PoB config.
REFERENCE_CONDITIONS = {
    "buffOnslaught": True, "conditionCritInPast8Sec": True, "conditionCritRecently": True,
    "conditionEnemyBlinded": True, "conditionEnemyBurning": True, "conditionEnemyChilled": True,
    "conditionEnemyDazed": True, "conditionEnemyFrozen": True, "conditionEnemyIntimidated": True,
    "conditionEnemyShocked": True, "conditionGainedPowerChargeRecently": True,
    "conditionHaveEnergyShield": True, "conditionNonCritRecently": True, "multiplierCombo": 10,
    "multiplierRage": 30, "useEnduranceCharges": True, "useFrenzyCharges": True,
    "windDancerStacks": 3,
}

#: Socket groups in the seed document, 1-based as PoB numbers them.
GROUP_FLICKER = 6
GROUP_WHIRLING = 8
GROUP_CHARGED_STAFF = 11
#: Pounce: movement only (owner Q4). Its Predator's Mark raises the enemy's
#: damage taken in PoB; the benchmark documents switch it off.
GROUP_POUNCE = 4

FLICKER_KEYS = ("AverageBurstHits", "AverageDamage", "AverageBurstDamage",
                "Speed", "TotalDPS", "ManaCost", "PowerCharges",
                "PowerChargesMax", "RemovablePowerCharges")
SKILL_KEYS = ("Speed", "Time", "AverageDamage", "TotalDPS", "ManaCost",
              "AverageBurstHits", "AverageBurstDamage")

DIAGNOSTIC_LUA = r"""
local env = build.calcsTab.mainEnv
local out = build.calcsTab.mainOutput
local skill = env.player.mainSkill
local function mods(list)
  local rows = {}
  for _, m in ipairs(list) do
    local tags = {}
    for _, t in ipairs(m) do
      local parts = {}
      for k, v in pairs(t) do parts[#parts + 1] = tostring(k) .. "=" .. tostring(v) end
      table.sort(parts)
      tags[#tags + 1] = table.concat(parts, ",")
    end
    rows[#rows + 1] = { name = m.name, type = m.type, value = type(m.value) == "table" and "<table>" or m.value,
                        source = tostring(m.source), tags = tags }
  end
  return rows
end
local function tab(store, modType, cfg, name)
  local rows = {}
  for _, r in ipairs(store:Tabulate(modType, cfg, name)) do
    local v = r.value
    rows[#rows + 1] = { value = type(v) == "table" and "<table>" or v, source = tostring(r.mod.source),
                        name = r.mod.name, type = r.mod.type }
  end
  table.sort(rows, function(a, b) return (a.source .. tostring(a.value)) < (b.source .. tostring(b.value)) end)
  return rows
end
local function truthy(t)
  local keys = {}
  for k, v in pairs(t or {}) do if v == true then keys[#keys + 1] = k end end
  table.sort(keys)
  return keys
end
local function numbers(t)
  local res = {}
  for k, v in pairs(t or {}) do if type(v) == "number" and v ~= 0 then res[k] = v end end
  return res
end
local enemy = {}
for _, s in ipairs({ "FireResist", "ColdResist", "LightningResist", "ChaosResist", "Armour", "Evasion" }) do
  enemy[s] = env.enemyDB:Sum("BASE", nil, s)
end
local hit = {}
for _, t in ipairs({ "Physical", "Lightning", "Cold", "Fire", "Chaos" }) do
  hit[t .. "HitAverage"] = out[t .. "HitAverage"]
end
for _, k in ipairs({ "CritChance", "HitChance", "IgniteDPS", "BleedDPS", "PoisonDPS", "TotalDot",
                     "TotalDotDPS", "WithDotDPS", "CombinedDPS", "ShockEffectMod", "Mana", "ManaRegenRecovery",
                     "ManaRegen", "ManaRecoveryRateMod", "ManaCost", "ManaUnreserved", "EnergyShield",
                     "PowerCharges", "PowerChargesMax", "RemovablePowerCharges" }) do
  hit[k] = out[k]
end
local conditional = {}
local function scan(store, scope)
  for name, list in pairs(store.mods or {}) do
    for _, m in ipairs(list) do
      for _, t in ipairs(m) do
        if t.type == "Condition" or t.type == "ActorCondition" or t.type == "Multiplier"
            or t.type == "MultiplierThreshold" or t.type == "PerStat" then
          local vars = t.var or (t.varList and table.concat(t.varList, "|")) or t.stat or "?"
          conditional[#conditional + 1] = { scope = scope, mod = name, type = m.type,
            value = type(m.value) == "table" and "<table>" or m.value, source = tostring(m.source),
            tag = t.type, var = tostring(vars), neg = t.neg and true or false,
            actor = t.actor and tostring(t.actor) or nil }
        end
      end
    end
  end
end
scan(env.player.modDB, "player")
local enemy_mods = {}
for name, list in pairs(env.enemyDB.mods or {}) do
  for _, m in ipairs(list) do
    local src = tostring(m.source)
    if src ~= "Base" and src ~= "Config" then
      local tags = {}
      for _, t in ipairs(m) do tags[#tags + 1] = tostring(t.type) .. ":" .. tostring(t.var or t.effectName or t.effectType or "") end
      enemy_mods[#enemy_mods + 1] = { mod = name, type = m.type, source = src, tags = tags,
        value = type(m.value) == "table" and "<table>" or m.value }
    end
  end
end
table.sort(enemy_mods, function(a, b) return (a.source .. a.mod .. tostring(a.value)) < (b.source .. b.mod .. tostring(b.value)) end)
scan(skill.skillModList, "main_skill")
table.sort(conditional, function(a, b)
  return (a.var .. a.mod .. a.source .. tostring(a.value)) < (b.var .. b.mod .. b.source .. tostring(b.value)) end)
for _, k in ipairs({ "Rage", "MaximumRage", "Onslaught", "OnslaughtEffect" }) do hit[k] = out[k] end
local flasks = {}
for _, slotName in ipairs({ "Flask 1", "Flask 2" }) do
  local slot = build.itemsTab.slots[slotName]
  local item = slot and build.itemsTab.items[slot.selItemId]
  if item and item.flaskData then
    local fd = {}
    for k, v in pairs(item.flaskData) do if type(v) ~= "table" then fd[k] = v end end
    flasks[slotName] = { name = item.name, flaskData = fd, active = slot.active and true or false }
  end
end
local flask_mods = {}
for _, n in ipairs({ "FlaskManaRecovery", "FlaskRecoveryRate", "FlaskManaRecoveryRate", "FlaskDuration",
                     "FlaskChargesGenerated", "ManaFlaskChargesGenerated", "FlaskChargesGained",
                     "ManaFlaskChargesGained", "FlaskChargesUsed", "ManaFlaskChargesUsed", "FlaskEffect" }) do
  flask_mods[n] = { BASE = env.player.modDB:Sum("BASE", nil, n), INC = env.player.modDB:Sum("INC", nil, n),
                    MORE = env.player.modDB:More(nil, n) }
end
return {
  flasks = flasks,
  flask_mods = flask_mods,
  mana_recovery_flask = out.ManaRecoveryRateMod,
  conditional_mods = conditional,
  enemy_mods = enemy_mods,
  main_skill = skill.activeEffect.grantedEffect.id,
  enemy_level = env.enemyLevel,
  enemy = enemy,
  outputs = hit,
  config_mods = mods(build.configTab.modList),
  config_enemy_mods = mods(build.configTab.enemyModList),
  player_conditions = truthy(env.player.modDB.conditions),
  player_multipliers = numbers(env.player.modDB.multipliers),
  enemy_conditions = truthy(env.enemyDB.conditions),
  enemy_multipliers = numbers(env.enemyDB.multipliers),
  speed_more = tab(skill.skillModList, "MORE", skill.skillCfg, "Speed"),
  speed_inc = tab(skill.skillModList, "INC", skill.skillCfg, "Speed"),
  lightning_min = tab(skill.skillModList, "BASE", skill.skillCfg, "LightningMin"),
  lightning_max = tab(skill.skillModList, "BASE", skill.skillCfg, "LightningMax"),
  damage_more = tab(skill.skillModList, "MORE", skill.skillCfg, "Damage"),
  flicker_strikes = tab(skill.skillModList, "BASE", skill.skillCfg, "AdditionalFlickersPerPowerCharge"),
}
"""


CHARGED_STAFF_DURATION_LUA = r"""
local skill = build.calcsTab.mainEnv.player.mainSkill
local cfg = skill.skillCfg
local rows = {}
for _, r in ipairs(skill.skillModList:Tabulate("INC", cfg, "Duration")) do
  rows[#rows + 1] = { value = r.value, source = tostring(r.mod.source) }
end
for _, r in ipairs(skill.skillModList:Tabulate("MORE", cfg, "Duration")) do
  rows[#rows + 1] = { value = r.value, source = tostring(r.mod.source), more = true }
end
return {
  skill = skill.activeEffect.grantedEffect.id,
  per_stack_ms_base = skill.skillModList:Sum("BASE", cfg, "ChargedStaffBuffDuration"),
  duration_inc = skill.skillModList:Sum("INC", cfg, "Duration"),
  duration_more = skill.skillModList:More(cfg, "Duration"),
  duration_mods = rows,
}
"""


def check_checkout(root: Path):
    from pob2opt.evaluation import resolve_checkout

    checkout = resolve_checkout(root)
    if checkout.commit != PIN:
        raise SystemExit("refusing: %s is at %s, not the pin %s"
                         % (root, checkout.commit, PIN))
    if checkout.dirty_hash is not None or checkout.reason is not None:
        raise SystemExit("refusing: %s is not a clean pinned tree (%s)"
                         % (root, checkout.reason or checkout.dirty_hash))
    return checkout


def disable_group(xml: str, index: int) -> str:
    """The document with socket group ``index`` (1-based) disabled."""
    starts = [m.start() for m in re.finditer(r"<Skill ", xml)]
    if index > len(starts):
        raise LookupError("the document has %d socket groups" % len(starts))
    start = starts[index - 1]
    head = xml[start:xml.index(">", start)]
    if 'enabled="true"' not in head:
        raise LookupError("socket group %d is not enabled" % index)
    return xml[:start] + head.replace('enabled="true"', 'enabled="false"', 1) + xml[start + len(head):]


def disable_gem(xml: str, index: int, name: str) -> str:
    """The document with gem ``name`` in socket group ``index`` disabled."""
    starts = [m.start() for m in re.finditer(r"<Skill ", xml)] + [len(xml)]
    start, end = starts[index - 1], starts[index]
    block = xml[start:end]
    match = re.search(r'<Gem [^>]*nameSpec="%s"[^>]*>' % re.escape(name), block)
    if match is None or ' enabled="true"' not in match.group(0):
        raise LookupError("no enabled %r in socket group %d" % (name, index))
    gem = match.group(0).replace(' enabled="true"', ' enabled="false"', 1)
    return xml[:start] + block[:match.start()] + gem + block[match.end():] + xml[end:]


def group_gem(xml: str, index: int) -> str:
    start = [m.start() for m in re.finditer(r"<Skill ", xml)][index - 1]
    return re.search(r'nameSpec="([^"]+)"', xml[start:]).group(1)


def close(a, b) -> bool:
    if isinstance(a, bool) or isinstance(b, bool) or not isinstance(a, (int, float)) \
            or not isinstance(b, (int, float)):
        return a == b
    return math.isclose(a, b, rel_tol=REL_TOL, abs_tol=1e-9)


def compare(new: dict, old: dict) -> dict:
    keys = sorted(set(new) | set(old))
    differ = {k: {"old": old.get(k), "new": new.get(k)} for k in keys
              if k in new and k in old and not close(new[k], old[k])}
    return {"compared": sum(1 for k in keys if k in new and k in old),
            "only_old": sorted(k for k in keys if k not in new),
            "only_new": sorted(k for k in keys if k not in old),
            "differ": differ}


def run_adapter(root: Path, xml: str) -> dict:
    from pob2opt.evaluation import (BuildDocument, EngineAdapter, EngineState,
                                    pob_worker_spec)

    bench = disable_group(xml, GROUP_POUNCE)
    variants = {"seed": xml,
                "charged_staff_disabled": disable_group(xml, GROUP_CHARGED_STAFF),
                "benchmark": bench,
                "benchmark_charged_staff_disabled": disable_group(bench, GROUP_CHARGED_STAFF),
                "benchmark_no_hit_and_run": disable_gem(bench, GROUP_FLICKER, "Hit and Run"),
                "benchmark_no_hit_and_run_charged_staff_disabled": disable_gem(
                    disable_group(bench, GROUP_CHARGED_STAFF), GROUP_FLICKER, "Hit and Run")}
    adapter = EngineAdapter(pob_worker_spec(root), start_timeout_s=600.0,
                            screen_timeout_s=TIMEOUT_S, detailed_timeout_s=TIMEOUT_S,
                            require_pinned_checkout=True,
                            # Each seed load grows the worker (P02-T01.1); a
                            # fresh worker every few probes keeps it bounded.
                            max_requests_per_worker=MAX_REQUESTS_PER_WORKER)
    out: dict = {"states": []}
    try:
        def probe(name, doc_xml, state):
            values = adapter.probe(BuildDocument(build_hash="p09-t01.2/" + name, xml=doc_xml),
                                   state, timeout_s=TIMEOUT_S)
            out["states"].append({"name": name, "state": state.to_wire()})
            return values

        out["imported_all"] = probe("imported", xml, EngineState(main_skill=(GROUP_FLICKER, 1)))
        for variant, doc in variants.items():
            rows = []
            for charges in range(0, 6):
                config = {} if charges == 0 else {"usePowerCharges": True,
                                                  "overridePowerCharges": charges}
                values = probe("%s/flicker/%d" % (variant, charges), doc,
                               EngineState(config=config, main_skill=(GROUP_FLICKER, 1),
                                           stat_keys=FLICKER_KEYS))
                rows.append({"forced_power_charges": charges, **values})
            out["flicker_" + variant] = rows
        # Which other socket group feeds Flicker Strike's numbers: disable one
        # group at a time, at 0 and 5 forced charges.
        sweep = []
        for index in range(1, xml.count("<Skill ") + 1):
            if index == GROUP_FLICKER:
                continue
            try:
                doc = disable_group(xml, index)
            except LookupError:
                continue
            for charges in (0, 5):
                config = {} if charges == 0 else {"usePowerCharges": True,
                                                  "overridePowerCharges": charges}
                values = probe("sweep/%d/%d" % (index, charges), doc,
                               EngineState(config=config, main_skill=(GROUP_FLICKER, 1),
                                           stat_keys=FLICKER_KEYS + ("CritChance", "CombinedDPS",
                                                                     "IgniteDPS")))
                sweep.append({"disabled_group": index, "gem": group_gem(xml, index),
                              "forced_power_charges": charges, **values})
        out["group_sweep"] = sweep
        # PoB defaults the import did not write: Flicker Strike's "Bypass CD?"
        # (on by default) and the enemy distance placeholder (20 units = 2 m),
        # which Close Combat II reads. Benchmark document, 5 forced charges.
        probes = []
        for name, extra in (("default", {}),
                            ("FlickerStrikeBypassCD_off", {"FlickerStrikeBypassCD": False}),
                            ("enemyDistance_10", {"enemyDistance": 10}),
                            ("enemyDistance_35", {"enemyDistance": 35})):
            values = probe("config/%s" % name, bench,
                           EngineState(config={"usePowerCharges": True, "overridePowerCharges": 5, **extra},
                                       main_skill=(GROUP_FLICKER, 1),
                                       stat_keys=FLICKER_KEYS + ("CritChance", "HitChance")))
            probes.append({"probe": name, "config": extra, **values})
        out["config_probes"] = probes
        # The community reference's condition inputs (reference-ninja-25c49
        # decoded.xml), applied to the seed at its maximum of 5 charges. Its
        # enemy resistance and above-maximum charge inputs are left out: the
        # target is the fixed Pinnacle preset.
        out["reference_conditions"] = {
            "config": REFERENCE_CONDITIONS,
            "seed": probe("reference_conditions/seed", xml, EngineState(
                config={"usePowerCharges": True, "overridePowerCharges": 5, **REFERENCE_CONDITIONS},
                main_skill=(GROUP_FLICKER, 1), stat_keys=FLICKER_KEYS)),
        }
        out["whirling_assault"] = probe(
            "whirling_assault", xml,
            EngineState(main_skill=(GROUP_WHIRLING, 1), stat_keys=SKILL_KEYS))
        out["charged_staff"] = probe(
            "charged_staff", xml,
            EngineState(main_skill=(GROUP_CHARGED_STAFF, 1), stat_keys=SKILL_KEYS))
        identity = adapter.identity()
        out["identity"] = {"pob_root": identity.pob_root, "pob_commit": identity.pob_commit,
                           "pob_dirty_hash": identity.pob_dirty_hash,
                           "adapter_version": identity.adapter_version,
                           "helper_lua_hashes": [list(h) for h in identity.helper_lua_hashes]}
    finally:
        adapter.close()
    return out


def run_diagnostics(root: Path, xml: str) -> dict:
    from pob2mcp.engine import Pob2Engine

    cs_off = disable_group(xml, GROUP_CHARGED_STAFF)
    plans = [("imported", xml, []),
             ("charges_1", xml, [("usePowerCharges", True), ("overridePowerCharges", 1)]),
             ("charges_5", xml, [("usePowerCharges", True), ("overridePowerCharges", 5)]),
             ("charged_staff_disabled/charges_5", cs_off,
              [("usePowerCharges", True), ("overridePowerCharges", 5)])]
    result = {}
    cwd = os.getcwd()
    engine = Pob2Engine(str(root))
    try:
        for name, doc, config in plans:
            engine.call("load_build_xml", {"xml": doc, "name": "p09-t01.2 " + name})
            for key, value in config:
                engine.call("set_config", {"name": key, "value": value})
            engine.call("set_main_skill", {"group": GROUP_FLICKER, "skill": 1})
            result[name] = engine.eval_lua(DIAGNOSTIC_LUA)
        engine.call("load_build_xml", {"xml": xml, "name": "p09-t01.2 config"})
        result["config_input"] = engine.call("get_config", {})
        # Charged Staff's buff duration: PoB carries ChargedStaffBuffDuration
        # (6000 ms per stack) but no module reads it, so read the duration
        # modifiers that apply to the skill instead.
        engine.call("set_config", {"name": "usePowerCharges", "value": True})
        engine.call("set_config", {"name": "overridePowerCharges", "value": 1})
        engine.call("set_main_skill", {"group": GROUP_CHARGED_STAFF, "skill": 1})
        result["charged_staff_duration"] = engine.eval_lua(CHARGED_STAFF_DURATION_LUA)
    finally:
        engine.close()
        os.chdir(cwd)
    return result


def main() -> int:
    root = Path(os.environ.get("POB2_ROOT") or REPO_ROOT / "external" / "PathOfBuilding-PoE2").resolve()
    checkout = check_checkout(root)
    xml = SEED_XML.read_text(encoding="utf-8")
    groups = {GROUP_FLICKER: "Flicker Strike", GROUP_WHIRLING: "Whirling Assault",
              GROUP_CHARGED_STAFF: "Charged Staff"}
    for index, name in groups.items():
        if group_gem(xml, index) != name:
            raise SystemExit("socket group %d is %r, expected %r"
                             % (index, group_gem(xml, index), name))

    adapter_out = run_adapter(root, xml)
    diagnostics = run_diagnostics(root, xml)
    check_checkout(root)  # still clean after both sessions

    old_table = json.loads(OLD_TABLE.read_text(encoding="utf-8"))
    old_stats = json.loads(OLD_STATS.read_text(encoding="utf-8"))
    agreement = {"stats_flicker_main": compare(adapter_out["imported_all"], old_stats)}
    old_rows = {r["power_charges"]: r for r in old_table["flicker_by_charges"]}
    agreement["flicker_by_charges"] = {
        str(r["forced_power_charges"]): compare(
            {k: r[k] for k in old_rows[r["forced_power_charges"]] if k in r and k != "power_charges"},
            {k: v for k, v in old_rows[r["forced_power_charges"]].items() if k != "power_charges"})
        for r in adapter_out["flicker_seed"]}
    old_off = {r["power_charges"]: r for r in old_table["flicker_charged_staff_disabled"]}
    agreement["flicker_charged_staff_disabled"] = {
        str(c): compare({k: r[k] for k in old_off[c] if k in r and k != "power_charges"},
                        {k: v for k, v in old_off[c].items() if k != "power_charges"})
        for r in adapter_out["flicker_charged_staff_disabled"]
        for c in [r["forced_power_charges"]] if c in old_off}
    agreement["whirling_assault"] = compare(
        {k: adapter_out["whirling_assault"].get(k) for k in old_table["whirling_assault"]
         if k != "socket_group"},
        {k: v for k, v in old_table["whirling_assault"].items() if k != "socket_group"})
    enemy_old = old_table["enemy"]
    imported_diag = diagnostics["imported"]
    agreement["enemy"] = compare(
        {"enemyLevel": imported_diag["enemy_level"], **{
            k: imported_diag["enemy"][k] for k in ("Armour", "Evasion")},
         **{k + "Resist": imported_diag["enemy"][k + "Resist"]
            for k in ("Fire", "Cold", "Lightning", "Chaos")}},
        {"enemyLevel": enemy_old["enemyLevel"], "Armour": enemy_old["Armour"],
         "Evasion": enemy_old["Evasion"],
         **{k + "Resist": v for k, v in enemy_old["resist"].items()}})

    def diffs(node):
        if "differ" in node:
            return len(node["differ"])
        return sum(diffs(v) for v in node.values())

    record = {
        "task": "P09-T01.2",
        "kind": "PoB-derived",
        "not_a_claim": "Engine outputs for the seed on the clean pinned checkout. Not a benchmark "
                       "result and not a measurement. PoB DPS values stay proxy_only.",
        "command": "python scripts/p09_t01_2_seed_replay.py",
        "build": "docs/evidence/P09-T01.1/seed/export-flicker-main.xml",
        "engine": {"checkout": "external/PathOfBuilding-PoE2", "head": checkout.commit,
                   "working_tree": "clean (git status --porcelain --untracked-files=all empty, "
                                   "checked before and after the run)",
                   "adapter_identity": adapter_out.pop("identity")},
        "procedure": [
            "EngineAdapter.probe loads the document unchanged for every state; no state leaks between rows.",
            "power charges 0: imported config; 1 to 5: config usePowerCharges = true, overridePowerCharges = n.",
            "Charged Staff disabled: socket group %d set enabled=\"false\" in the document." % GROUP_CHARGED_STAFF,
            "Whirling Assault: main skill group %d; Charged Staff: main skill group %d."
            % (GROUP_WHIRLING, GROUP_CHARGED_STAFF),
            "Diagnostics: a direct Pob2Engine session on the same checkout, read-only Lua after the same loads.",
        ],
        "states": adapter_out.pop("states"),
        "agreement_with_p09_t01_1": agreement,
        "agreement_summary": {"values_differing": diffs(agreement),
                              "rel_tol": REL_TOL},
        "flicker_seed": adapter_out["flicker_seed"],
        "flicker_charged_staff_disabled": adapter_out["flicker_charged_staff_disabled"],
        "benchmark_documents": {
            "change": "Pounce (socket group %d) disabled: owner Q4 keeps it out of the rotation, and its "
                      "Predator's Mark is a state the benchmark does not generate." % GROUP_POUNCE,
            "flicker_benchmark": adapter_out["flicker_benchmark"],
            "flicker_benchmark_charged_staff_disabled": adapter_out["flicker_benchmark_charged_staff_disabled"],
            "flicker_benchmark_no_hit_and_run": adapter_out["flicker_benchmark_no_hit_and_run"],
            "flicker_benchmark_no_hit_and_run_charged_staff_disabled":
                adapter_out["flicker_benchmark_no_hit_and_run_charged_staff_disabled"]},
        "whirling_assault": adapter_out["whirling_assault"],
        "charged_staff": adapter_out["charged_staff"],
        "group_sweep": adapter_out["group_sweep"],
        "config_probes": adapter_out["config_probes"],
        "reference_conditions": adapter_out["reference_conditions"],
        "diagnostics": diagnostics,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(record, indent=1, sort_keys=True, ensure_ascii=False) + "\n",
                   encoding="utf-8", newline="\n")
    print("wrote %s; %d values differ from the P09-T01.1 capture"
          % (OUT.relative_to(REPO_ROOT), record["agreement_summary"]["values_differing"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
