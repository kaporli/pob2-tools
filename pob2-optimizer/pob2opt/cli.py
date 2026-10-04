"""pob2opt CLI — orchestrates the phases with a worker pool and resumable state.

Usage examples:
  pob2opt all --level 28 --out runs/l28
  pob2opt all --level 60 --budget 5 --league "Forbidden Rites" --workers 6 --out runs/l60
  pob2opt screen --level 45 --limit 50 --out runs/test   (quick slice)

Each phase writes <out>/<phase>.json; finished phases are skipped on rerun
(delete the file or pass --force to redo).
"""

from __future__ import annotations

import argparse
import json
import multiprocessing as mp
import os
import sys
import time

_REPO_ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))

def _resolve(env_var, *candidates):
    val = os.environ.get(env_var)
    if val:
        return val
    for c in candidates:
        if c and os.path.isdir(c):
            return c
    return ""  # empty -> Pob2Engine raises a clear error / installed package is used

# PoB checkout: env POB2_ROOT, else the bundled git submodule.
DEFAULT_POB_ROOT = _resolve("POB2_ROOT", os.path.join(_REPO_ROOT, "external", "PathOfBuilding-PoE2"))
# pob2-mcp source: env POB2_MCP_PATH, else the sibling package (if not pip-installed).
DEFAULT_MCP_PATH = _resolve("POB2_MCP_PATH", os.path.join(_REPO_ROOT, "pob2-mcp"))
DEFAULT_BUILD = os.environ.get(
    "POB2_BUILD_XML",
    os.path.join(os.path.expanduser("~"), "Documents", "Path of Building (PoE2)", "Builds", "My Character.xml"),
)


def log(*a):
    print(*a, file=sys.stderr, flush=True)


def load_phase(out_dir, name):
    p = os.path.join(out_dir, f"{name}.json")
    if os.path.exists(p):
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    return None


def save_phase(out_dir, name, data):
    os.makedirs(out_dir, exist_ok=True)
    with open(os.path.join(out_dir, f"{name}.json"), "w", encoding="utf-8") as f:
        json.dump(data, f, indent=1)


def run_pool(args, tasks, label):
    from pob2opt import engine_worker
    results = []
    t0 = time.time()
    resist = -20 if args.level < 45 else -30
    if args.workers <= 1:
        engine_worker.init_worker(args.pob_root, args.mcp_path, args.build_xml, args.level, resist)
        for i, task in enumerate(tasks):
            results.append(engine_worker.run_task(task))
            if (i + 1) % 10 == 0:
                log(f"{label}: {i + 1}/{len(tasks)} ({time.time() - t0:.0f}s)")
    else:
        with mp.Pool(args.workers, initializer=engine_worker.init_worker,
                     initargs=(args.pob_root, args.mcp_path, args.build_xml, args.level, resist)) as pool:
            for i, r in enumerate(pool.imap_unordered(engine_worker.run_task, tasks, chunksize=4)):
                results.append(r)
                if (i + 1) % 20 == 0:
                    log(f"{label}: {i + 1}/{len(tasks)} ({time.time() - t0:.0f}s)")
    errors = [r for r in results if isinstance(r, dict) and r.get("error")]
    if errors:
        log(f"{label}: {len(errors)} task errors (first: {errors[0]['error']})")
    return results


def get_gems(args):
    from pob2opt import engine_worker
    cached = load_phase(args.out, "gems")
    if cached and not args.force:
        return cached
    resist = -20 if args.level < 45 else -30
    w = engine_worker.Worker(args.pob_root, args.mcp_path, args.build_xml, args.level, resist)
    gems = w.gems()
    save_phase(args.out, "gems", gems)
    return gems


def phase_harvest(args):
    if load_phase(args.out, "harvest") and not args.force:
        return load_phase(args.out, "harvest")
    from pob2opt import engine_worker, harvest
    resist = -20 if args.level < 45 else -30
    w = engine_worker.Worker(args.pob_root, args.mcp_path, args.build_xml, args.level, resist)
    data = harvest.harvest_all(args.mcp_path, w, args.league, args.level, args.budget, log=log)
    save_phase(args.out, "harvest", data)
    return data


def phase_screen(args):
    if load_phase(args.out, "screen") and not args.force:
        return load_phase(args.out, "screen")
    from pob2opt import phases
    gems = get_gems(args)
    uniques = load_phase(args.out, "harvest") if not args.no_trade else None
    tasks = phases.build_screen_tasks(gems, uniques, limit=args.limit, char_level=args.level)
    log(f"screen: {len(tasks)} tasks")
    results = [r for r in run_pool(args, tasks, "screen") if r and not r.get("skip") and not r.get("error")]
    results.sort(key=lambda r: -r["ceiling"])
    save_phase(args.out, "screen", results)
    return results


def phase_combos(args):
    if load_phase(args.out, "combos") and not args.force:
        return load_phase(args.out, "combos")
    from pob2opt import phases
    gems = get_gems(args)
    screen = load_phase(args.out, "screen") or []
    tasks = phases.build_combo_tasks(gems, screen, limit=args.limit)
    log(f"combos: {len(tasks)} tasks")
    results = [r for r in run_pool(args, tasks, "combos") if r and not r.get("skip") and not r.get("error")]
    results.sort(key=lambda r: -r["ceiling"])
    save_phase(args.out, "combos", results)
    return results


def phase_triggers(args):
    if load_phase(args.out, "triggers") and not args.force:
        return load_phase(args.out, "triggers")
    from pob2opt import phases
    gems = get_gems(args)
    screen = load_phase(args.out, "screen") or []
    tasks = phases.build_trigger_tasks(gems, screen, limit=args.limit)
    log(f"triggers: {len(tasks)} tasks")
    results = [r for r in run_pool(args, tasks, "triggers") if r and not r.get("skip") and not r.get("error")]
    results.sort(key=lambda r: -r["ceiling"])
    save_phase(args.out, "triggers", results)
    return results


def phase_stack(args):
    if load_phase(args.out, "stack") and not args.force:
        return load_phase(args.out, "stack")
    from pob2opt import phases
    gems = get_gems(args)
    screen = load_phase(args.out, "screen") or []
    combos = load_phase(args.out, "combos") or []
    top = sorted(screen + combos, key=lambda r: -r["ceiling"])
    tasks = phases.build_stack_tasks(top, gems, limit=args.limit)
    log(f"stack: {len(tasks)} tasks")
    results = [r for r in run_pool(args, tasks, "stack") if r and not r.get("skip") and not r.get("error")]
    results.sort(key=lambda r: -(r["gain"] if r.get("spirit_ok") else -1))
    save_phase(args.out, "stack", results)
    return results


def phase_finals(args):
    if load_phase(args.out, "finals") and not args.force:
        return load_phase(args.out, "finals")
    from pob2opt import phases
    screen = load_phase(args.out, "screen") or []
    combos = load_phase(args.out, "combos") or []
    stack = load_phase(args.out, "stack") or []
    # tier-normalized, medium-weighted skill ranking + best combos
    rank = phases.rank_tiered(screen, args.tier_weights)
    top, seen = [], set()
    for row in rank:
        if len(top) >= args.top:
            break
        top.append(row["best"])
        seen.add(row["gem"])
    for r in sorted(combos, key=lambda r: -r["ceiling"]):
        if len(top) >= args.top + max(2, args.top // 2):
            break
        if r["payoff"] not in seen:
            top.append(r)
            seen.add(r["payoff"])
    triggers = load_phase(args.out, "triggers") or []
    for r in sorted(triggers, key=lambda r: -r["ceiling"])[:2]:
        key = (r["meta"], r["inner"])
        if key not in seen:
            top.append(r)
            seen.add(key)
    # attach profitable spirit-feasible stack additions to each finalist
    stack_for = {}
    for s in stack:
        if s.get("spirit_ok") and s["gain"] > s["full_before"] * 0.05:
            lst = stack_for.setdefault(s["main"], [])
            if s["candidate"] not in lst:
                lst.append(s["candidate"])
    points = (args.level - 1) + (6 if args.level <= 30 else 12)
    asc = 2 if args.level < 40 else 4
    tasks = []
    for r in top:
        main = r.get("inner") or r.get("payoff") or r.get("gem")
        enablers = list(r.get("enablers", []))
        if r.get("activator"):
            enablers.append(r["activator"])
        tasks.append(("final", {
            "main": main, "meta": r.get("meta"), "enablers": enablers,
            "stack": stack_for.get(main, [])[:3], "weapon": r.get("weapon_spec"),
            "points": points, "asc_points": asc,
        }))
    log(f"finals: {len(tasks)} candidates")
    results = [r for r in run_pool(args, tasks, "finals") if r and not r.get("error")]
    results.sort(key=lambda r: -r["ceiling"])
    for i, r in enumerate(results):
        xml = r.pop("xml", None)
        if xml:
            path = os.path.join(args.out, f"build_{i+1:02d}_{r['main'].replace(' ', '_')}.xml")
            with open(path, "w", encoding="utf-8") as f:
                f.write(xml)
            r["xml_file"] = path
    save_phase(args.out, "finals", results)
    return results


def phase_report(args):
    from pob2opt import phases
    finals = load_phase(args.out, "finals") or []
    screen = load_phase(args.out, "screen") or []
    combos = load_phase(args.out, "combos") or []
    lines = [f"# pob2opt report — level {args.level}, league {args.league}", ""]
    rank = phases.rank_tiered(screen, args.tier_weights)
    if rank:
        w = args.tier_weights
        lines.append(f"## Gear-tier ranking (normalized; weights min {w[0]}, medium {w[1]}, BiS {w[2]})")
        lines.append("| # | Skill | Minimal | Medium | BiS | Score |")
        lines.append("|---|---|---|---|---|---|")
        for i, r in enumerate(rank[:20]):
            lines.append(f"| {i+1} | {r['gem']} | {r['min']:.0f} | {r['med']:.0f} | {r['bis']:.0f} | {r['score']:.3f} |")
        lines.append("")
    lines.append("## Finalists (fully optimized: supports + tree + attributes)")
    lines.append("| # | Build | Floor DPS | Ceiling DPS | Assumptions | File |")
    lines.append("|---|---|---|---|---|---|")
    for i, r in enumerate(finals):
        name = r["main"] + ((" + " + "+".join(r["enablers"])) if r.get("enablers") else "")
        if r.get("stack"):
            name += " & " + ", ".join(r["stack"])
        lines.append(f"| {i+1} | {name} @ {r['weapon']} | {r['floor']:.0f} | {r['ceiling']:.0f} | "
                     f"{', '.join(r['assumptions']) or '-'} | {os.path.basename(r.get('xml_file', ''))} |")
    def dedupe(rows, key):
        seen, out = set(), []
        for r in rows:
            k = key(r)
            if k in seen:
                continue
            seen.add(k)
            out.append(r)
        return out

    lines.append("")
    lines.append("## Top raw screens (single skill)")
    for r in dedupe(screen, lambda r: r["gem"])[:15]:
        lines.append(f"- {r['ceiling']:.0f} (floor {r['floor']:.0f}) {r['gem']} @ {r['weapon']}")
    lines.append("")
    lines.append("## Top combos (enabler -> payoff)")
    for r in dedupe(combos, lambda r: (r["payoff"], tuple(r["enablers"])))[:15]:
        lines.append(f"- {r['ceiling']:.0f} (floor {r['floor']:.0f}) {'+'.join(r['enablers'])} -> {r['payoff']} [{r['mechanic']}]")
    triggers = load_phase(args.out, "triggers") or []
    if triggers:
        lines.append("")
        lines.append("## Top trigger wraps (meta-gem > socketed spell)")
        for r in dedupe(triggers, lambda r: (r["meta"], r["inner"]))[:10]:
            act = f" (+{r['activator']})" if r.get("activator") else ""
            lines.append(f"- {r['ceiling']:.0f} (floor {r['floor']:.0f}) {r['meta']} > {r['inner']}{act}")
    gated = [r for r in screen if r.get("gated")]
    if gated:
        lines.append("")
        lines.append("## Burst-rotation payoffs (Glory/stun-gated — per-window numbers, NOT sustained DPS)")
        for r in dedupe(sorted(gated, key=lambda x: -x["ceiling"]), lambda r: r["gem"])[:6]:
            lines.append(f"- {r['ceiling']:.0f} per window: {r['gem']} @ {r['weapon']} — needs its resource loop "
                         f"(heavy stuns/ignites); pair with a generator and judge by rotation, not this number")
    text = "\n".join(lines)
    with open(os.path.join(args.out, "report.md"), "w", encoding="utf-8") as f:
        f.write(text)
    print(text)
    return text


def phase_buildarounds(args):
    """Axis-creating uniques as first-class build candidates: scan the unique DB
    for scaling-conversion mods, force-equip each weapon-type unique, and run the
    full tier pipeline on its best compatible skill."""
    if load_phase(args.out, "buildarounds") and not args.force:
        return load_phase(args.out, "buildarounds")
    from pob2opt import engine_worker, phases, policy
    gems = get_gems(args)
    screen = load_phase(args.out, "screen") or []
    rank_order = [r["gem"] for r in phases.rank_tiered(screen, args.tier_weights)]
    resist = -20 if args.level < 45 else -30
    w = engine_worker.Worker(args.pob_root, args.mcp_path, args.build_xml, args.level, resist)
    found = w.lua(r"""
    local out = {}
    for utype, list in pairs(build.data.uniques) do
      if type(list) == "table" then
        for _, text in ipairs(list) do
          local name = text:match("^([^\r\n]+)")
          local hit = false
          for line in text:gmatch("[^\r\n]+") do
            local ll = line:lower()
            if (ll:find("equal to") and ll:find("maximum")) or ll:find("per %d+ maximum")
               or (ll:find("gain") and ll:find("per")) then hit = true end
          end
          if hit then out[#out+1] = { name = name, utype = utype, text = text } end
        end
      end
    end
    return out
    """)
    WEAPON_TYPES = {"mace": ("Two Hand Mace", True), "bow": ("Bow", True), "crossbow": ("Crossbow", True),
                    "spear": ("Spear", False), "staff": ("Staff", True), "wand": ("Wand", False),
                    "sceptre": ("Sceptre", False), "quarterstaff": ("Quarterstaff", True)}
    spirit_pool = [g["name"] for g in gems if policy.is_spirit_skill(g)][:20]
    points = (args.level - 1) + 8
    tasks = []
    wt_map = {"Two Hand Mace": ["Two Hand Mace"], "Bow": ["Bow"], "Crossbow": ["Crossbow"],
              "Spear": ["Spear"], "Staff": ["Staff"], "Wand": ["Wand"], "Sceptre": ["Sceptre"],
              "Quarterstaff": ["Quarterstaff"]}
    for u in found:
        m = WEAPON_TYPES.get(u["utype"])
        if not m:
            continue
        type_name, two_h = m
        mains = [g["name"] for g in gems
                 if set(g.get("weaponTypes") or []) & set(wt_map[type_name])
                 and not policy.is_gated(g["description"])]
        mains.sort(key=lambda n: rank_order.index(n) if n in rank_order else 999)
        if not mains:
            continue
        g = next((x for x in gems if x["name"] == mains[0]), {})
        tasks.append(("tier", {
            "main": mains[0], "enablers": [], "minion": False,
            "weapon": {"type": type_name, "two_handed": two_h, "kind": "attack",
                       "raw": "Rarity: Unique\n" + u["text"]},
            "offhand": None, "main_desc": g.get("description", ""),
            "spirit_pool": spirit_pool, "filler_pool": [],
            "points": points, "asc_points": 2 if args.level < 40 else 4, "max_act": 2,
            "buildaround": u["name"],
        }))
    log(f"buildarounds: {len(tasks)} unique-anchored candidates")
    results = [r for r in run_pool(args, tasks, "buildarounds") if r and not r.get("skip") and not r.get("error")]
    for r, t in zip(results, tasks):
        r["buildaround"] = t[1]["buildaround"]
        r.pop("xml", None)
    results.sort(key=lambda r: -(r.get("rotation_dps") or 0))
    save_phase(args.out, "buildarounds", results)
    for r in results[:10]:
        if not r.get("illegal"):
            log(f"  {r.get('rotation_dps', 0):7.0f}  {r.get('buildaround')} -> {r['main']}")
    return results


def phase_tierlist(args):
    """Rotation-scored tier list of the top N candidate builds (v2 model)."""
    if load_phase(args.out, "tierlist") and not args.force:
        return load_phase(args.out, "tierlist")
    from pob2opt import phases, policy
    gems = get_gems(args)
    gem_by_name = {g["name"]: g for g in gems}
    screen = load_phase(args.out, "screen") or []
    combos = load_phase(args.out, "combos") or []
    rank = phases.rank_tiered(screen, args.tier_weights)
    spirit_pool = [g["name"] for g in gems if policy.is_spirit_skill(g)][:20]
    ONE_HANDED_CASTER = {"Wand", "Sceptre"}
    points = (args.level - 1) + 8  # act 1-2 quest passives (user-verified)
    tasks, seen = [], set()

    def offhand_for(spec, main_gem):
        if not spec:
            return None
        if spec["type"] in ONE_HANDED_CASTER:
            return "focus"
        if spec["type"] == "Spear":
            return "buckler"
        return None

    rank_order = [row["gem"] for row in rank]

    def filler_pool_for(main):
        g = gem_by_name.get(main, {})
        if policy.classify_rotation(g.get("description", "")) != "gauge":
            return []
        wts = set(g.get("weaponTypes") or [])
        pool = [c["name"] for c in gems
                if c["name"] != main and set(c.get("weaponTypes") or []) & wts
                and not policy.is_gated(c["description"])
                and policy.unlock_ok(c["name"], args.level)]
        pool.sort(key=lambda n: rank_order.index(n) if n in rank_order else 999)
        return pool[:8]

    def add(main, enablers, spec, minion):
        if main in seen or len(tasks) >= args.top:
            return
        seen.add(main)
        g = gem_by_name.get(main, {})
        tasks.append(("tier", {
            "main": main, "enablers": enablers, "weapon": spec,
            "offhand": offhand_for(spec, main), "minion": minion,
            "main_desc": g.get("description", ""), "spirit_pool": spirit_pool,
            "filler_pool": filler_pool_for(main),
            "points": points, "asc_points": 2, "max_act": 2,
        }))

    combo_best = {}
    for r in sorted(combos, key=lambda x: -x["ceiling"]):
        combo_best.setdefault(r["payoff"], r)
    # multi-skill archetypes enter as first-class rows (fix #4): top combos first
    for r in sorted(combos, key=lambda x: -x["ceiling"])[:8]:
        g = gem_by_name.get(r["payoff"], {})
        add(r["payoff"], r["enablers"], r.get("weapon_spec"), bool(g.get("minion")))
    for row in rank:
        main = row["gem"]
        g = gem_by_name.get(main, {})
        combo = combo_best.get(main)
        enablers = combo["enablers"] if combo and combo["ceiling"] > row["med"] * 1.1 else []
        spec = (combo or {}).get("weapon_spec") or (row["best"] or {}).get("weapon_spec")
        add(main, enablers, spec, bool(g.get("minion")))
    log(f"tierlist: {len(tasks)} builds")
    results = [r for r in run_pool(args, tasks, "tierlist") if r and not r.get("skip") and not r.get("error")]
    legal = [r for r in results if not r.get("illegal")]
    legal.sort(key=lambda r: -r["rotation_dps"])
    for i, r in enumerate(legal):
        xml = r.pop("xml", None)
        if xml:
            path = os.path.join(args.out, f"tier_{i+1:02d}_{r['main'].replace(' ', '_')}.xml")
            with open(path, "w", encoding="utf-8") as f:
                f.write(xml)
            r["xml_file"] = os.path.basename(path)
    save_phase(args.out, "tierlist", {"legal": legal, "illegal": [r for r in results if r.get("illegal")]})
    def tbl(rows, key, label):
        out = [f"## {label}",
               "| # | Build | Archetype | Boss (honest) | Clear | PoB (raw) | File |",
               "|---|---|---|---|---|---|---|"]
        for i, r in enumerate(sorted(rows, key=lambda r: -(r.get(key) or 0))[:15]):
            name = r["main"] + ((" + " + "+".join(r["enablers"])) if r["enablers"] else "")
            honest = r.get("honest_single_target")
            if honest is None:
                honest = r.get("realistic_dps") or r.get("rotation_dps") or 0
            out.append(f"| {i+1} | {name} @ {r['weapon']} | {r.get('archetype','?')} | {honest:.0f} | "
                       f"{r.get('clear_score', 0):.0f} | {r['rotation_dps']:.0f} | {r.get('xml_file','')} |")
        return out
    def honest_of(r):
        h = r.get("honest_single_target")
        return h if h is not None else (r.get("realistic_dps") or r.get("rotation_dps") or 0)
    st_best = max(legal, key=honest_of) if legal else None
    cl_best = max(legal, key=lambda r: r.get("clear_score") or 0) if legal else None
    lines = [f"# Tier list — level {args.level}, ~1ex gear, concentration-corrected dual-axis", ""]
    if st_best and cl_best:
        lines += [f"**Recommended pair — bosser: `{st_best['main']}` ({honest_of(st_best):.0f} honest single-target) "
                  f"· mapper: `{cl_best['main']}` ({cl_best.get('clear_score',0):.0f} clear)**",
                  "*Boss (honest) = PoB raw × concentration model (scatter/hit-rate). PoB (raw) shown for reference.*", ""]
    lines += tbl(legal, "honest_single_target", "By SINGLE-TARGET (bossing, honest)") + [""] + tbl(legal, "clear_score", "By CLEAR (mapping)")
    if len(results) > len(legal):
        lines.append("")
        lines.append(f"Excluded as illegal (requirements unmet): "
                     + ", ".join(r["main"] for r in results if r.get("illegal")))
    text = "\n".join(lines)
    with open(os.path.join(args.out, "tierlist.md"), "w", encoding="utf-8") as f:
        f.write(text)
    print(text)
    return legal


PHASES = {"harvest": phase_harvest, "screen": phase_screen, "combos": phase_combos,
          "triggers": phase_triggers, "stack": phase_stack, "finals": phase_finals,
          "tierlist": phase_tierlist, "report": phase_report}


def phase_feedback(args):
    """Log a real play observation and re-fit the concentration model.
    Usage: pob2opt feedback --level 37 --out . --skill "Rain of Arrows"
           --axis single --predicted 6245 --observed 1000"""
    from pob2opt import calibration, concentration
    if not args.skill:
        print(json.dumps(calibration.status(), indent=1)); return
    # --predicted is the model's HONEST prediction (what the tier list showed),
    # --observed is effective DPS you actually experienced.
    arch = args.archetype or "unknown"
    n = calibration.add_observation(args.skill, arch, args.axis, args.predicted or 0,
                                    args.observed or 0, args.note or "")
    fit = calibration.fit()
    log(f"logged observation #{n} ({args.skill} {args.axis}); fitted {fit.get('fitted')} archetype fudges")
    print(json.dumps(calibration.status(), indent=1))


def phase_calibrate(args):
    from pob2opt import calibration, ladder
    entries = ladder.fetch_ladder(args.mcp_path, args.league, limit=100, log=log)
    log(f"ladder: {len(entries)} characters fetched")
    obs = ladder.observations_from_ladder(entries)
    for o in obs:
        calibration.add_observation(**o)
    fit = calibration.fit()
    print(json.dumps({"ladder_chars": len(entries), "ladder_observations": len(obs), **fit}, indent=1))


PHASES["feedback"] = phase_feedback
PHASES["calibrate"] = phase_calibrate


def _doctor(argv):
    """`pob2opt doctor` (P00-T03). Imported lazily: diagnostics must stay usable
    even when something in the legacy phase pipeline is broken."""
    from . import doctor
    return doctor.main(argv)


#: Subcommands from docs/specs/interfaces.md. These never touch PHASES; the
#: legacy phase pipeline keeps its own parser and its existing behavior.
NEW_COMMANDS = {"doctor": _doctor}


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    # New-contract subcommands are dispatched before the legacy phase parser so
    # they cannot inherit its required --level/--out or reach the phase pipeline.
    if argv and argv[0] in NEW_COMMANDS:
        return NEW_COMMANDS[argv[0]](argv[1:])
    ap = argparse.ArgumentParser(prog="pob2opt")
    ap.add_argument("phase", choices=list(PHASES) + ["all"])
    ap.add_argument("--level", type=int, required=True)
    ap.add_argument("--budget", type=float, default=5.0, help="trade budget in exalts")
    ap.add_argument("--league", default="Forbidden Rites")
    ap.add_argument("--workers", type=int, default=max(1, (os.cpu_count() or 4) - 2))
    ap.add_argument("--out", required=True)
    ap.add_argument("--top", type=int, default=8, help="finalists to fully optimize")
    ap.add_argument("--limit", type=int, default=None, help="cap task count (testing)")
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--no-trade", action="store_true", help="skip trade (crafted minimal items only)")
    ap.add_argument("--tier-weights", default="0.25,0.5,0.25",
                    help="weights for minimal,medium,BiS gear tiers in the normalized ranking")
    ap.add_argument("--skill", help="feedback: skill name")
    ap.add_argument("--axis", default="single", choices=["single", "clear"], help="feedback axis")
    ap.add_argument("--archetype", help="feedback: skill archetype (optional)")
    ap.add_argument("--predicted", type=float, default=0, help="feedback: predicted DPS")
    ap.add_argument("--observed", type=float, default=0, help="feedback: observed effective DPS")
    ap.add_argument("--ratio", type=float, default=1.0, help="feedback: observed/predicted if not giving both")
    ap.add_argument("--note", help="feedback: free note")
    ap.add_argument("--pob-root", default=DEFAULT_POB_ROOT)
    ap.add_argument("--mcp-path", default=DEFAULT_MCP_PATH)
    ap.add_argument("--build-xml", default=DEFAULT_BUILD,
                    help="character XML (class/level source)")
    args = ap.parse_args(argv)
    args.tier_weights = tuple(float(x) for x in args.tier_weights.split(","))
    # engine workers chdir into the PoB source tree; every path must be absolute
    args.out = os.path.abspath(args.out)
    args.pob_root = os.path.abspath(args.pob_root) if args.pob_root else ""
    args.mcp_path = os.path.abspath(args.mcp_path) if args.mcp_path else ""
    args.build_xml = open(os.path.abspath(args.build_xml), encoding="utf-8").read()

    if args.phase == "all":
        order = ["screen", "combos", "triggers", "stack", "finals", "report"]
        if not args.no_trade:
            order.insert(0, "harvest")
        for name in order:
            log(f"=== phase {name} ===")
            PHASES[name](args)
    else:
        PHASES[args.phase](args)
    return 0


if __name__ == "__main__":
    mp.freeze_support()
    sys.exit(main())
