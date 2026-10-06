"""Worker task implementations + driver-side task list builders.

Task functions (task_*) run INSIDE worker processes and receive (worker, payload).
Builder functions (build_*_tasks) run in the driver and produce task lists.
"""

from __future__ import annotations

import json

from . import legacy_estimates, policy

WT_TO_CAT = {
    "Spear": ("Spear", False), "Bow": ("Bow", True), "Crossbow": ("Crossbow", True),
    "Quarterstaff": ("Quarterstaff", True), "Warstaff": ("Quarterstaff", True),
    "Staff": ("Staff", True),
    "One Hand Mace": ("One Hand Mace", False), "One Handed Mace": ("One Hand Mace", False),
    "Two Hand Mace": ("Two Hand Mace", True), "Two Handed Mace": ("Two Hand Mace", True),
    "Wand": ("Wand", False), "Sceptre": ("Sceptre", False),
}
CASTER_TYPES = [("Wand", False), ("Staff", True)]
MINION_TYPES = [("Sceptre", False)]


def craft_weapon(worker, type_name: str, plus_levels: int, kind: str) -> str:
    base = worker.best_base(type_name)
    if not base:
        raise LookupError(f"no base exists for weapon type {type_name!r}")
    mods = []
    if plus_levels and kind == "spell":
        mods.append(f"+{plus_levels} to Level of all Spell Skills")
    elif plus_levels and kind == "minion":
        mods.append(f"+{plus_levels} to Level of all Minion Skills")
    lines = ["Rarity: Rare", "Optimizer Weapon", base, f"Item Level: {worker.char_level}",
             "Implicits: 0"] + mods
    return "\n".join(lines)


def _equip_for(worker, weapon_spec):
    """weapon_spec: {"type": ..., "kind": attack|spell|minion, "raw": optional trade text}"""
    if weapon_spec is None:
        worker.clear_slot("Weapon 1")
        worker.clear_slot("Weapon 2")
        return "unarmed"
    raw = weapon_spec.get("raw")
    if not raw:
        plus = 3 if worker.char_level >= 45 else 2
        raw = craft_weapon(worker, weapon_spec["type"], plus, weapon_spec["kind"])
    r = worker.equip(raw, "Weapon 1")
    if not r.get("ok"):
        raise RuntimeError(f"equip failed: {r.get('err')}")
    if weapon_spec.get("two_handed"):
        worker.clear_slot("Weapon 2")
    lines = raw.splitlines()
    # rares: line 3 is the base; uniques keep their name (line 2)
    label = lines[2] if lines[1] in ("Optimizer Weapon",) else lines[1]
    if not weapon_spec.get("raw"):
        label += " (minimal)"
    return label


def _condition_off_on(worker):
    """Measure with every scoped condition on, then with every one off.

    These were called "ceiling" and "floor". They are not bounds: they are two
    measurements under two declared configurations, which is what the current
    names say (P02-T04).
    """
    scoped = worker.scoped_configs()
    on_vals = policy.ceiling_values(scoped)
    off_vals = policy.floor_values(scoped)
    for var, val in on_vals.items():
        worker.set_config(var, val)
    m_on = worker.metrics()
    for var, val in off_vals.items():
        worker.set_config(var, val)
    m_off = worker.metrics()
    # the worker is left in the condition-off state
    return legacy_estimates.condition_estimates(
        _score(m_off), _score(m_on), sorted(on_vals))


def _score(m):
    """The legacy screening number, with its units checked (P02-T04)."""
    return legacy_estimates.screen_score(m)


# ---------------------------------------------------------------- worker tasks

def task_screen(worker, p):
    """Single skill on a minimal weapon: floor/ceiling metrics."""
    worker.maybe_reset()
    weapon = _equip_for(worker, p.get("weapon"))
    gi = worker.add_group(p["gem"], quality=20, full_dps=True)
    if gi is None:
        return {"gem": p["gem"], "skip": "gem not found"}
    worker.set_main(gi)
    try:
        estimates = _condition_off_on(worker)
    finally:
        worker.remove_group(gi)
    return {"gem": p["gem"], "weapon": weapon, "weapon_spec": p.get("weapon"),
            "tier": p.get("tier", "min"), "gated": p.get("gated", False),
            "minion": p.get("minion", False), **estimates}


def task_combo(worker, p):
    """Payoff skill + enabler skills active together."""
    worker.maybe_reset()
    weapon = _equip_for(worker, p.get("weapon"))
    gis = []
    for en in p["enablers"]:
        gi = worker.add_group(en, quality=0, full_dps=True)
        if gi:
            gis.append(gi)
    gi = worker.add_group(p["payoff"], quality=20, full_dps=True)
    if gi is None:
        for g in reversed(gis):
            worker.remove_group(g)
        return {"payoff": p["payoff"], "skip": "gem not found"}
    worker.set_main(gi)
    try:
        estimates = _condition_off_on(worker)
    finally:
        for g in reversed(gis + [gi]):
            worker.remove_group(g)
    return {"payoff": p["payoff"], "enablers": p["enablers"], "mechanic": p.get("mechanic"),
            "weapon": weapon, "weapon_spec": p.get("weapon"), **estimates}


def task_trigger(worker, p):
    """Meta-gem wrapper combo: inner spell socketed inside a trigger gem, with
    an optional activator skill (e.g. a freezing spell for Cast on Freeze)."""
    worker.maybe_reset()
    weapon = _equip_for(worker, p.get("weapon"))
    gis = []
    if p.get("activator"):
        gi = worker.add_group(p["activator"], quality=20, full_dps=True)
        if gi:
            gis.append(gi)
    gi = worker.lua(f"return OPT_add_wrapped_group({json.dumps(p['meta'])}, {json.dumps(p['inner'])}, {worker.char_level}, 20)")
    if gi is None:
        for g in reversed(gis):
            worker.remove_group(g)
        return {"meta": p["meta"], "inner": p["inner"], "skip": "gem not found"}
    # main skill = the triggered inner spell (skill index 2 in a wrapped group)
    worker.set_main(gi, 2)
    try:
        estimates = _condition_off_on(worker)
    finally:
        for g in reversed(gis + [gi]):
            worker.remove_group(g)
    # P02-T04 fixture F-TRIG: no meta gem in the pinned catalog marked the
    # socketed spell triggered, so these numbers are the spell cast directly.
    estimates["estimate_gaps"] = ["trigger_cadence_not_modelled"]
    return {"meta": p["meta"], "inner": p["inner"], "activator": p.get("activator"),
            "weapon": weapon, "weapon_spec": p.get("weapon"), "mechanic": "trigger_wrap",
            **estimates}


def task_stack(worker, p):
    """Multi-entity aggregation: enable base skill set, measure FullDPS with and
    without the candidate added. Spirit feasibility enforced. Uses a full reset
    (many groups) — stack task lists are short."""
    worker.reset()
    _equip_for(worker, p.get("weapon"))
    for gem in p["base"]:
        worker.add_group(gem, quality=20, full_dps=True)
    main_gi = worker.add_group(p["main"], quality=20, full_dps=True)
    worker.set_main(main_gi)
    scoped = worker.scoped_configs()
    for var, val in policy.ceiling_values(scoped).items():
        worker.set_config(var, val)
    before = worker.metrics()
    gi = worker.add_group(p["candidate"], quality=20, full_dps=True)
    if gi is None:
        return {"candidate": p["candidate"], "skip": "gem not found"}
    scoped = worker.scoped_configs()
    for var, val in policy.ceiling_values(scoped).items():
        worker.set_config(var, val)
    after = worker.metrics()
    feasible = (after.get("spiritUnreserved") or 0) >= 0
    return {"candidate": p["candidate"], "base": p["base"], "main": p["main"],
            "full_before": before["full"], "full_after": after["full"],
            "gain": after["full"] - before["full"], "spirit_ok": feasible}


def task_final(worker, p):
    """Full pipeline for one finalist: groups, supports, tree, attrs. Returns
    metrics + build XML. Supports plain mains and trigger-wrapped mains."""
    worker.reset()
    weapon = _equip_for(worker, p.get("weapon"))
    for en in p.get("enablers", []):
        worker.add_group(en, quality=0, full_dps=True)
    stack_gis = []
    for extra in p.get("stack", []):
        sgi = worker.add_group(extra, quality=20, full_dps=True)
        if sgi:
            stack_gis.append(sgi)
    if p.get("meta"):
        gi = worker.lua(f"return OPT_add_wrapped_group({json.dumps(p['meta'])}, {json.dumps(p['main'])}, {worker.char_level}, 20)")
        worker.set_main(gi, 2)
    else:
        gi = worker.add_group(p["main"], quality=20, full_dps=True)
        worker.set_main(gi)
    scoped = worker.scoped_configs()
    assumption_vars = policy.ceiling_values(scoped)
    for var, val in assumption_vars.items():
        worker.set_config(var, val)
    sockets = p.get("sockets", 3 if worker.char_level < 40 else 4)
    sup = worker.support_greedy(gi, sockets)
    # real builds support their secondary damage sources too
    for sgi in stack_gis:
        try:
            worker.support_greedy(sgi, 2)
        except Exception:
            pass
    tree = worker.optimize_tree(p["points"], p["asc_points"], p.get("swap_rounds", 12))
    m_on = worker.metrics()
    for entry in scoped:
        var = entry["var"]
        if var in assumption_vars:
            worker.set_config(var, False if entry["type"] == "check" else 0)
    m_off = worker.metrics()
    for var, val in assumption_vars.items():
        worker.set_config(var, val)
    xml = worker.save_xml()
    estimates = legacy_estimates.condition_estimates(
        _score(m_off), _score(m_on), sorted(assumption_vars))
    return {"main": p["main"], "enablers": p.get("enablers", []), "stack": p.get("stack", []),
            "weapon": weapon, "supports": sup["chosen"], "ascendancy": tree["ascendancy"],
            "tree_points": tree["points"],
            "life": m_on.get("life"), "requirements": {k: m_on.get(k) for k in
                ("str", "dex", "int", "reqStr", "reqDex", "reqInt")},
            "xml": xml, **estimates}


def task_tier(worker, p):
    """v2 build evaluation: quest bonuses, multi-slot 1ex gear, supports, tree,
    HARD legality gate, spirit-gem greedy, rotation-scored DPS."""
    worker.reset()
    worker.lua("return OPT_quest_bonuses(%d)" % p.get("max_act", 2))
    weapon = _equip_for(worker, p.get("weapon"))
    # crafted spirit source so heralds/summons are actually payable (fix #1)
    body = worker.best_base("Body Armour")
    if body:
        worker.equip(f"Rarity: Rare\nSpirit Body\n{body}\nItem Level: {worker.char_level}\nImplicits: 0\n+60 to Spirit", "Body Armour")
    # offhand: crafted minimal focus for one-handed casters; white buckler for spears
    off = p.get("offhand")
    if off == "focus":
        base = worker.best_base("Focus")
        if base:
            worker.equip(f"Rarity: Rare\nMinimal Focus\n{base}\nItem Level: {worker.char_level}\nImplicits: 0\n+1 to Level of all Spell Skills", "Weapon 2")
    elif off == "buckler":
        base = worker.best_base("Buckler")
        if base:
            worker.equip(f"Rarity: Normal\nWhite Buckler\n{base}\nItem Level: {worker.char_level}\nImplicits: 0", "Weapon 2")
    gis = []
    for en in p.get("enablers", []):
        gi = worker.add_group(en, quality=0, full_dps=True)
        if gi:
            gis.append(gi)
    gi = worker.add_group(p["main"], quality=20, full_dps=True)
    if gi is None:
        return {"main": p["main"], "skip": "gem not found"}
    worker.set_main(gi)
    scoped = worker.scoped_configs()
    for var, val in policy.ceiling_values(scoped).items():
        worker.set_config(var, val)
    worker.support_greedy(gi, 3)
    tree = worker.optimize_tree(p["points"], p["asc_points"], p.get("swap_rounds", 8))
    m = worker.metrics()
    legal = all((m.get(a) or 0) >= (m.get("req" + a.capitalize()) or 0) for a in ("str", "dex", "int"))
    if not legal:
        return {"main": p["main"], "enablers": p.get("enablers", []), "illegal": True,
                "requirements": {k: m.get(k) for k in ("str", "dex", "int", "reqStr", "reqDex", "reqInt")}}
    # spirit greedy: up to 2 reservation buffs that fit the Spirit budget
    spirit_added = []
    for sname in p.get("spirit_pool", []):
        if len(spirit_added) >= 2:
            break
        before = worker.metrics()
        sgi = worker.add_group(sname, quality=0, full_dps=False)
        if not sgi:
            continue
        after = worker.metrics()
        gain = max(after["dps"], after["full"]) - max(before["dps"], before["full"])
        if (after.get("spiritUnreserved") or 0) >= 0 and gain > max(before["dps"], 1) * 0.01:
            spirit_added.append(sname)
        else:
            worker.remove_group(sgi)
    prims = worker.lua("return OPT_primitives()")
    enabler_names = set(p.get("enablers", []))
    for pr in prims:
        label = pr.get("label") or ""
        if pr["skill"] == p["main"] or p["main"] in label:
            pr["role"] = "main"
            if pr.get("poison") and pr.get("speed"):
                pr["dot_per_use"] = pr["poison"] / pr["speed"]
        elif pr["skill"] in enabler_names or any(e in label for e in enabler_names):
            pr["role"] = "enabler"
        elif pr["skill"] in spirit_added or any(s in label for s in spirit_added):
            pr["role"] = "spirit"
        elif not label.startswith("OPT:"):
            # item-granted / leftover groups: real skills, but you are not
            # casting them while executing the rotation (fix #2)
            pr["role"] = "item_granted"
        else:
            pr["role"] = "persistent"
    rotation_gaps: list[str] = []
    if p.get("minion"):
        for pr in prims:
            if pr["role"] == "main":
                pr["role"] = "persistent"  # minions attack continuously
        classification = {"kind": "persistent"}
        rot = {"dps": sum((pr.get("combined") or 0) for pr in prims if pr["role"] in ("persistent", "spirit")),
               "cycle": "persistent", "detail": "minions act continuously"}
    else:
        kind = policy.classify_rotation(p.get("main_desc", ""))
        classification = {"kind": kind}
        if kind == "consume_stack" and p.get("enablers"):
            classification["stack_builder"] = p["enablers"][0]
        rot = policy.rotation_dps(prims, classification)
        # reload duty for clip weapons (data-driven: boltCount/reloadTime).
        # A clip weapon whose attack rate the engine did not report has an
        # unknown duty, and 1.0 would be the most favourable answer, so the
        # Lua returns nothing and the row records a gap (P02-T04).
        clip = worker.lua("""
        local s = build.calcsTab.mainEnv.player.mainSkill
        local sd = s and s.skillData or {}
        local o = build.calcsTab.mainOutput
        if sd.boltCount and sd.reloadTime then
          if o.Speed and o.Speed > 0 then
            local fire = sd.boltCount / o.Speed
            return { duty = fire / (fire + sd.reloadTime), reason = "clip weapon" }
          end
          return { reason = "clip weapon with no reported attack rate" }
        end
        return { duty = 1, reason = "not a clip weapon" }
        """)
        duty = clip.get("duty")
        if duty is None:
            rotation_gaps.append("reload_duty_unknown: %s"
                                 % clip.get("reason", "no reason reported"))
            rot["dps"] = None
        else:
            rot["dps"] *= duty
        # gauge skills: burst window + lockout, filled by the best same-weapon skill
        if kind == "gauge" and rot["dps"] is not None:
            t_up, t_lock = policy.GAUGE_CONSTANTS.get(p["main"], policy.GAUGE_DEFAULT)
            measured = p["main"] in policy.GAUGE_CONSTANTS
            burst_dps = rot["dps"]
            # filler search: quick pass over same-weapon attack gems
            filler_best = (0, None)
            for cand in p.get("filler_pool", []):
                fgi = worker.add_group(cand, quality=20, full_dps=False)
                if not fgi:
                    continue
                worker.set_main(fgi)
                try:
                    worker.support_greedy(fgi, 2)
                except Exception:
                    pass
                fm = worker.metrics()
                if fm["dps"] > filler_best[0]:
                    filler_best = (fm["dps"], cand)
                worker.lua(f"build.skillsTab.socketGroupList[{fgi}].enabled = false; build.buildFlag=true; runCallback('OnFrame'); return true")
            worker.set_main(gi)
            comp = (burst_dps * t_up + filler_best[0] * t_lock) / (t_up + t_lock)
            rot = {"dps": comp, "cycle": "gauge" + ("" if measured else " (unmeasured)"),
                   "detail": f"burst {burst_dps:.0f} for {t_up}s, filler "
                             f"{filler_best[1] or 'none'} {filler_best[0]:.0f} for {t_lock}s lockout"}
            if filler_best[1]:
                rot["filler"] = filler_best[1]
    # Enemy conditions the build self-applies. Measured as a ratio of the same
    # engine output read twice, so the unit cancels, and applied as a
    # multiplier on the rotation rather than as a replacement for it. Replacing
    # it is research finding F02: the rotation correction was thrown away here.
    realistic = None
    uplift = None
    uplift_gap = None
    enabled_conditions: list[str] = []
    try:
        prof = worker.lua("return OPT_damage_profile()")
        bare = worker.metrics().get("dps")
        for var, gate in policy.COMBAT_CONDITIONS:
            if prof.get(gate):
                worker.set_config(var, True)
                enabled_conditions.append(var)
        realistic = worker.metrics().get("dps")
        uplift, uplift_gap = legacy_estimates.condition_uplift(
            bare, realistic, enabled_conditions)
        # the conditions stay on for the saved file; the rotation and the
        # condition-off numbers above were measured without them
    except Exception as exc:
        uplift_gap = "%s: %s: %s" % (legacy_estimates.GAP_NO_UPLIFT,
                                     type(exc).__name__, exc)
    xml = worker.save_xml()
    geom = None
    geometry_gap = None
    try:
        geom = worker.lua("return OPT_geometry()")
    except Exception as exc:
        geometry_gap = "%s: %s: %s" % (legacy_estimates.GAP_NO_GEOMETRY,
                                       type(exc).__name__, exc)
    estimates = legacy_estimates.sustained_estimates(
        rot["dps"], geom, uplift, uplift_gap=uplift_gap,
        geometry_gap=geometry_gap)
    estimates["estimate_gaps"] = (rotation_gaps + rot.get("assumptions", [])
                                  + estimates["estimate_gaps"])
    return {"main": p["main"], "enablers": p.get("enablers", []), "weapon": weapon,
            "offhand": off, "spirit": spirit_added, "ascendancy": tree["ascendancy"],
            "pob_dps": _score(m), "realistic_dps": realistic,
            "conditions_enabled": enabled_conditions,
            "rotation_kind": rot["cycle"], "rotation_detail": rot["detail"],
            "rotation_saturated": bool(rot.get("saturated")),
            "life": m.get("life"), "minion": p.get("minion", False),
            "requirements": {k: m.get(k) for k in ("str", "dex", "int", "reqStr", "reqDex", "reqInt")},
            "xml": xml, **estimates}


# ---------------------------------------------------------------- task builders

def base_specs_for(gem):
    """Weapon (type, two_handed, kind) specs for one gem, tierless."""
    specs = []
    if gem["weaponTypes"]:
        seen = set()
        for wt in gem["weaponTypes"]:
            if wt in ("Unarmed", "None"):
                specs.append(None)
                continue
            m = WT_TO_CAT.get(wt)
            if m and m[0] not in seen:
                seen.add(m[0])
                specs.append({"type": m[0], "two_handed": m[1], "kind": "attack"})
    else:
        kind = "minion" if gem["minion"] else "spell"
        types = MINION_TYPES if gem["minion"] else CASTER_TYPES
        for t, two in types:
            specs.append({"type": t, "two_handed": two, "kind": kind})
    return specs


def weapon_specs_for(gem, harvest=None):
    """Gear-tier weapon specs per gem: 'min' = crafted minimal; 'med'/'bis' =
    harvested trade items when available; plus top uniques (tagged 'bis')."""
    specs = []
    for spec in base_specs_for(gem):
        if spec is None:
            specs.append(None)
            continue
        specs.append({**spec, "tier": "min"})
        h = (harvest or {}).get(spec["type"])
        if h:
            if h.get("medium"):
                specs.append({**spec, "tier": "med", "raw": h["medium"]["item_text"]})
            if h.get("bis"):
                specs.append({**spec, "tier": "bis", "raw": h["bis"]["item_text"]})
            for u in h.get("items", [])[:2]:
                if u["item_text"] not in (x.get("raw") for x in specs if x):
                    specs.append({**spec, "tier": "bis", "raw": u["item_text"]})
    return specs


def build_screen_tasks(gems, harvest=None, limit=None, char_level=99):
    tasks = []
    for g in gems:
        if not policy.unlock_ok(g["name"], char_level):
            continue
        gated = policy.is_gated(g["description"])
        for spec in weapon_specs_for(g, harvest):
            tasks.append(("screen", {"gem": g["name"], "weapon": spec, "minion": g["minion"],
                                     "tier": (spec or {}).get("tier", "min"), "gated": gated}))
    return tasks[:limit] if limit else tasks


def rank_tiered(screen, weights=(0.25, 0.5, 0.25)):
    """Aggregate screen results per gem across gear tiers, normalize each tier
    by its column max, and score with (min, med, bis) weights. Gems missing a
    tier fall back to the next-lower tier's value."""
    per_gem = {}
    for r in screen:
        on = legacy_estimates.legacy_value(r, legacy_estimates.CONDITION_ON_KEY)
        if on is None or r.get("gated"):
            continue
        g = per_gem.setdefault(r["gem"], {})
        t = r.get("tier", "min")
        if on >= g.get(t, (-1, None))[0]:
            g[t] = (on, r)
    rows = []
    for gem, tiers in per_gem.items():
        v_min = tiers.get("min", (0, None))[0]
        v_med = tiers.get("med", tiers.get("min", (0, None)))[0]
        v_bis = tiers.get("bis", tiers.get("med", tiers.get("min", (0, None))))[0]
        best = max(tiers.values(), key=lambda x: x[0])[1]
        rows.append({"gem": gem, "min": v_min, "med": v_med, "bis": v_bis, "best": best})
    if not rows:
        return []
    maxes = {t: max(r[t] for r in rows) or 1 for t in ("min", "med", "bis")}
    for r in rows:
        r["score"] = sum(w * (r[t] / maxes[t]) for w, t in zip(weights, ("min", "med", "bis")))
    rows.sort(key=lambda r: -r["score"])
    return rows


def build_combo_tasks(gems, top_screen, limit=None):
    """Pair mechanic providers with consumers. Weapon = the payoff's best
    MEDIUM-tier spec from the screen phase (medium-weighted headline)."""
    best_weapon = {}
    for r in top_screen:
        on = legacy_estimates.legacy_value(r, legacy_estimates.CONDITION_ON_KEY)
        if "gem" in r and on is not None:
            # prefer med tier; fall back to whatever exists
            pref = {"med": 2, "bis": 1, "min": 0}.get(r.get("tier", "min"), 0)
            cur = best_weapon.get(r["gem"])
            key = (pref, on)
            if cur is None or key > cur[0]:
                best_weapon[r["gem"]] = (key, r.get("weapon_spec"))
    provides, consumes = {}, {}
    for g in gems:
        p, c = policy.find_mechanics(g["description"], g["tagString"])
        for mech in p:
            provides.setdefault(mech, []).append(g)
        for mech in c:
            consumes.setdefault(mech, []).append(g)
    # empower_next: providers empower any Repeatable attack sharing a weapon type
    empowerers = provides.get("empower_next", [])
    tasks, seen = [], set()
    for mech, payoffs in consumes.items():
        for payoff in payoffs:
            for provider in provides.get(mech, []):
                if provider["name"] == payoff["name"]:
                    continue
                key = (payoff["name"], provider["name"])
                if key in seen:
                    continue
                seen.add(key)
                spec = best_weapon.get(payoff["name"], (0, None))[1]
                tasks.append(("combo", {"payoff": payoff["name"], "enablers": [provider["name"]],
                                        "mechanic": mech, "weapon": spec}))
    for payoff in gems:
        if not payoff["weaponTypes"]:
            continue
        for emp in empowerers:
            if payoff["name"] == emp["name"]:
                continue
            if set(payoff["weaponTypes"]) & set(emp["weaponTypes"]):
                key = (payoff["name"], emp["name"])
                if key in seen:
                    continue
                seen.add(key)
                spec = best_weapon.get(payoff["name"], (0, None))[1]
                tasks.append(("combo", {"payoff": payoff["name"], "enablers": [emp["name"]],
                                        "mechanic": "empower_next", "weapon": spec}))
    # curated seeds from meta research (named-buff/ground dependencies)
    names = {g["name"] for g in gems}
    for enabler, payoff in policy.CURATED_COMBOS:
        if enabler in names and payoff in names and (payoff, enabler) not in seen:
            seen.add((payoff, enabler))
            spec = best_weapon.get(payoff, (0, None))[1]
            tasks.append(("combo", {"payoff": payoff, "enablers": [enabler],
                                    "mechanic": "curated", "weapon": spec}))
    # warcries empower slams (structural: Warcry tag -> Slam tag)
    warcries = [g for g in gems if "warcry" in g["tagString"].lower()]
    slams = [g for g in gems if "slam" in g["tagString"].lower()]
    for payoff in slams:
        for wc in warcries:
            key = (payoff["name"], wc["name"])
            if key in seen:
                continue
            seen.add(key)
            spec = best_weapon.get(payoff["name"], (0, None))[1]
            tasks.append(("combo", {"payoff": payoff["name"], "enablers": [wc["name"]],
                                    "mechanic": "empower_slam", "weapon": spec}))
    return tasks[:limit] if limit else tasks


# activator element for trigger meta-gems: what the wrapped setup needs to proc
TRIGGER_ACTIVATORS = {
    "freeze": ("cold",), "ignite": ("fire",), "shock": ("lightning",),
    "crit": (), "dodge": (), "block": (), "minion death": (),
}


def build_trigger_tasks(gems, top_screen, limit=None):
    """Meta trigger gems ('Cast on X', Invocations) wrapping the best spells,
    with a matching activator skill enabled."""
    metas = [g for g in gems if g["name"].lower().startswith("cast on")
             or "invocation" in g["name"].lower()]
    # inner candidates: top un-gated spells (no weapon requirement)
    rank = rank_tiered(top_screen)
    spells = [r["gem"] for r in rank
              if next((g for g in gems if g["name"] == r["gem"] and not g["weaponTypes"]), None)][:10]
    # activators by element keyword in description
    def best_activator(mech_words):
        for r in rank:
            g = next((x for x in gems if x["name"] == r["gem"]), None)
            if g and any(w in g["description"].lower() or w in g["tagString"].lower()
                         for w in mech_words):
                return r["gem"]
        return None
    tasks = []
    for meta in metas:
        mech = meta["name"].lower().replace("cast on ", "")
        acts = TRIGGER_ACTIVATORS.get(mech, ())
        activator = best_activator(acts) if acts else None
        spec = None
        for r in top_screen:
            if r.get("gem") in spells and r.get("tier") == "med":
                spec = r.get("weapon_spec")
                break
        for inner in spells:
            if inner == meta["name"] or inner == activator:
                continue
            tasks.append(("trigger", {"meta": meta["name"], "inner": inner,
                                      "activator": activator, "weapon": spec}))
    return tasks[:limit] if limit else tasks


def build_stack_tasks(top_results, gems, limit=None):
    """For each of the best mains: try adding each independent damage source
    (minions, triggered/persistent skills) as an extra FullDPS group."""
    persistent = [g["name"] for g in gems
                  if (g["minion"] or "Companion" in g["name"] or "Summon" in g["name"]
                      or "totem" in g["description"].lower() or "trigger" in g["description"].lower())
                  and not policy.is_gated(g["description"])]
    tasks = []
    for r in top_results[:8]:
        main = r.get("payoff") or r.get("gem")
        enablers = r.get("enablers", [])
        for cand in persistent:
            if cand == main or cand in enablers:
                continue
            tasks.append(("stack", {"main": main, "base": enablers,
                                    "candidate": cand, "weapon": r.get("weapon_spec")}))
    return tasks[:limit] if limit else tasks
