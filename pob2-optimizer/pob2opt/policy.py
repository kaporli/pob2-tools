"""Assumption policy: how to floor/ceiling conditional configs, and how to
pair enabler skills with payoff skills.

The generic rule: any config var PoB scopes to an active skill (ifSkill) is a
build mechanic. Ceiling = checks on + counts at their curated cap; floor = all
off. Counts without a curated cap are left at floor (conservative ceiling).
"""

# curated caps for count-type skill configs (PoB clamps most of these anyway)
COUNT_CAPS = {
    "whirlwindStages": 4,
    "twisterWhirlwindsConsumed": 4,
    "windDancerStacks": 3,
    "multiplierGatheringStorm": 4,
    "frenzyChargeCount": 3,
    "powerChargeCount": 3,
    "enduranceChargeCount": 3,
}

# config vars that are never part of a ceiling (enemy stats, distances, etc.)
EXCLUDE_PREFIXES = ("enemy", "multiplierEnemy", "quest")

# ---------------------------------------------------------------------------
# Enabler/payoff pairing by description keywords. A payoff gem is paired with
# every provider of a mechanic its description says it consumes/needs.
# ---------------------------------------------------------------------------
MECHANICS = {
    "whirlwind": {
        "provides": ["kicks up a whirlwind", "whirlwind around"],
        "consumes": ["consumes the whirlwind", "touches a whirlwind", "consume a whirlwind"],
    },
    "empower_next": {
        "provides": ["empowering your next"],
        # payoff side resolved structurally: any Repeatable attack sharing a
        # weapon type with the enabler (see combos driver)
        "consumes": [],
    },
    "curse": {
        "provides": ["curse", "hex"],           # gem tagString match, see driver
        "consumes": ["cursed enemies", "consume a curse", "consumes a curse", "removing the curse",
                     "against cursed", "if the enemy is cursed", "hexed"],
    },
    "corpse": {
        "provides": ["creates a corpse", "corpses you create"],
        "consumes": ["consumes a corpse", "consume corpses", "detonating a corpse", "corpse"],
    },
    "freeze": {
        "provides": ["freeze buildup", "freezes enemies"],
        "consumes": ["frozen enemies", "consume freeze", "against frozen", "if the enemy is frozen"],
    },
    "ignite": {
        "provides": ["ignite", "ignites"],
        "consumes": ["ignited enemies", "against ignited", "consumes ignite", "if the enemy is ignited"],
    },
    "shock": {
        "provides": ["shock"],
        "consumes": ["shocked enemies", "against shocked", "consumes shock"],
    },
    "poison": {
        "provides": ["poison"],
        "consumes": ["poisoned enemies", "against poisoned", "per poison"],
    },
    "frenzy": {
        "provides": ["grants a frenzy charge", "gain a frenzy charge", "generate frenzy"],
        "consumes": ["consumes your frenzy charges", "consumes a frenzy charge"],
    },
    "mark": {
        "provides": ["mark"],
        "consumes": ["marked enemy", "against marked"],
    },
    # warcries empowering slams: providers matched by keyword, consumers matched
    # structurally in the combos builder (gem tagString contains "Slam")
    "empower_slam": {
        "provides": ["empower", "exert"],
        "consumes": [],
    },
}


# label/var keywords -> default ceiling for count configs not explicitly capped.
# PoB clamps most of these internally (m_min in the config apply functions), so
# a generous cap is safe where clamped and flagged as an assumption either way.
COUNT_KEYWORD_CAPS = (
    ("stage", 10),      # channelling ramps: Flameblast stages, whirlwinds, ...
    ("charge", 3),
    ("stack", 5),
    ("intensity", 4),
)


def ceiling_values(scoped_configs):
    """Map scoped config entries to their ceiling values."""
    out = {}
    for entry in scoped_configs:
        var, typ = entry["var"], entry["type"]
        if var.startswith(EXCLUDE_PREFIXES):
            continue
        if typ == "check":
            out[var] = True
        elif var in COUNT_CAPS:
            out[var] = COUNT_CAPS[var]
        else:
            hay = (var + " " + entry.get("label", "")).lower()
            for kw, cap in COUNT_KEYWORD_CAPS:
                if kw in hay:
                    out[var] = cap
                    break
    return out


# ---------------------------------------------------------------------------
# Rotation model: classify how a payoff skill's casts are gated, so effective
# DPS = damage per cycle / cycle time instead of PoB's spam assumption.
# Patterns are matched against gem descriptions.
# ---------------------------------------------------------------------------
ROTATION_PATTERNS = [
    # (kind, payoff-description keywords)
    ("curse_detonate", ("detonate a curse", "detonates a curse")),   # wait half curse duration
    ("consume_stack", ("consumes the whirlwind", "touches a whirlwind")),  # K builder casts per use
    ("gauge", ("maximum heat", "reaching maximum", "prevent you from firing")),  # burst + lockout
    ("channel", ("channel",)),                                        # own attack time: spam-honest
]
STACK_BUILD_CASTS = 4  # whirlwind stages assumed per consumption

# measured gauge constants: skill -> (burst seconds until cap, lockout seconds).
# Field-measured in game; skills detected as gauges without an entry are scored
# with the conservative default and flagged unmeasured.
GAUGE_CONSTANTS = {
    "Rapid Shot": (2.6, 10.0),   # measured 2026-09-22 (user stopwatch)
}
GAUGE_DEFAULT = (3.0, 6.0)

# Skill unlock gates the PoB data does not carry: minimum CHARACTER level at
# which the skill can be engraved (uncut gem tier system). Wiki/field-sourced;
# grows as gaps are discovered. Checked wherever skills are proposed.
SKILL_UNLOCK_LEVELS = {
    "Plasma Blast": 52,   # user-verified in game 2026-09-22 (wiki listed 41; trust in-game)
}


def unlock_ok(gem_name: str, char_level: int) -> bool:
    return char_level >= SKILL_UNLOCK_LEVELS.get(gem_name, 0)


# Support-gem TIER gates (the "I/II/III" suffix = required Uncut Support Gem
# level). Tier maps to the character/area level where that uncut tier first
# drops. PoB carries no requirement for these. (poe-vault/stratlore, 2026-09.)
SUPPORT_TIER_LEVELS = {"I": 1, "II": 35, "III": 54}


def support_tier_ok(support_name: str, char_level: int) -> bool:
    for suffix, lvl in SUPPORT_TIER_LEVELS.items():
        if support_name.endswith(" " + suffix):
            return char_level >= lvl
    return True  # untiered supports (Hit and Run, Lightning Penetration) always fine

def classify_rotation(description: str) -> str:
    d = (description or "").lower()
    for kind, kws in ROTATION_PATTERNS:
        if any(k in d for k in kws):
            return kind
    return "spam"


def rotation_dps(primitives: list, classification: dict) -> dict:
    """primitives: [{skill, avgUse, castTime, speed, combined, duration, cooldown,
    persistent, role}] where role in main|enabler|persistent|spirit.
    Returns {dps, cycle, detail}. First-order model:
    - persistent/spirit skills contribute their full DPS (they act while you rotate)
    - enablers cost amortized cast time (per duration, per cooldown, or per cycle)
    - main skill casts fill the remaining time; special gates change the period.
    """
    main = next((p for p in primitives if p["role"] == "main"), None)
    if not main or not main.get("combined"):
        return {"dps": 0, "cycle": 0, "detail": "no main"}
    t_main = main.get("castTime") or (1.0 / main["speed"] if main.get("speed") else 1.0)
    kind = classification.get("kind", "spam")
    detail = [f"main {main['skill']} cast {t_main:.2f}s, kind={kind}"]
    passive_dps = 0.0
    overhead = 0.0
    builders_time = 0.0
    for p in primitives:
        if p["role"] in ("persistent", "spirit"):
            passive_dps += p.get("combined") or 0
            continue
        if p["role"] != "enabler":
            continue
        t = p.get("castTime") or 1.0
        period = p.get("cooldown") or p.get("duration") or 0
        if classification.get("stack_builder") == p["skill"]:
            builders_time += STACK_BUILD_CASTS * t
            detail.append(f"builder {p['skill']}: {STACK_BUILD_CASTS}x{t:.2f}s per payoff")
        elif period and period > 0:
            overhead += t / period
            detail.append(f"enabler {p['skill']}: {t:.2f}s per {period:.1f}s")
        else:
            overhead += t / 6.0  # assume recast every ~6s when no duration known
            detail.append(f"enabler {p['skill']}: {t:.2f}s per ~6s (assumed)")
    overhead = min(overhead, 0.6)
    if kind == "curse_detonate":
        curse = next((p for p in primitives if p["role"] == "enabler" and p.get("duration")), None)
        cd = (curse.get("duration") or 7.5) if curse else 7.5
        tc = (curse.get("castTime") or 0.7) if curse else 0.7
        period = max(cd / 2 + tc + t_main, t_main / (1 - overhead) if overhead < 1 else t_main)
        per_cycle = (main.get("avgUse") or 0) + (main.get("dot_per_use") or 0)
        dps = per_cycle / period * (1) + passive_dps
        detail.append(f"curse gate: period {period:.2f}s, {per_cycle:.0f}/cycle")
    elif kind == "consume_stack":
        period = builders_time + t_main
        per_cycle = (main.get("avgUse") or 0) + (main.get("dot_per_use") or 0)
        dps = per_cycle / max(period, t_main) + passive_dps
        detail.append(f"stack gate: period {period:.2f}s, {per_cycle:.0f}/cycle")
    else:
        uptime = max(0.4, 1.0 - overhead - (builders_time / (builders_time + 4 * t_main) if builders_time else 0))
        dps = (main.get("combined") or 0) * uptime + passive_dps
        detail.append(f"uptime {uptime:.2f}")
    return {"dps": dps, "cycle": kind, "detail": "; ".join(detail)}


def clear_score(m: dict, pack_cap: int = 9):
    """Clear-speed proxy = single-target DPS x how many pack members you hit at
    once. AoE coverage (area x mob density) and projectile/pierce/chain reach
    each add effective targets, capped at a white-pack size. Movement speed is a
    small multiplier (less standing still). This is a first-order proxy, not a
    simulator — it ranks 'deletes packs' vs 'hits one thing', which raw DPS can't."""
    dps = m.get("dps") or 0
    if dps <= 0:
        return 0.0
    MOB_DENSITY = 1.3          # white mobs per square metre in a leveling pack
    targets = 1.0
    r = m.get("aoeRadius") or 0
    if r > 0:
        import math
        targets += min(math.pi * r * r * MOB_DENSITY, pack_cap - 1)
    proj = max(1, m.get("projectiles") or 1)
    reach = 1 + (m.get("pierce") or 0) + (m.get("chain") or 0)
    if proj > 1 or reach > 1:
        # projectiles that pierce/chain sweep a line through a pack
        targets += min(proj * reach - 1, pack_cap - targets)
    targets = min(targets, pack_cap)
    move = 0.85 + 0.15 * (m.get("moveSpeed") or 1)   # mobility eases clear, mildly
    return dps * targets * move


def skill_category(gem) -> str:
    """Classify a gem by how it's used, from its tags — so marks (active casts)
    are never confused with heralds (spirit reservations) again."""
    tags = (gem.get("tagString") or "").lower()
    name = gem["name"].lower()
    ge_support = False  # callers pass active gems here
    if gem.get("minion") or "minion" in tags:
        return "minion"
    if "herald" in tags or "herald" in name:
        return "herald"        # spirit-reserved, on-kill clear
    if gem.get("isMark") or "mark" in name:
        return "mark"          # ACTIVE cast on enemy, no reservation
    if "banner" in tags or "banner" in name:
        return "banner"        # spirit-reserved (Glory)
    if "aura" in tags or "persistent" in tags:
        return "aura"
    if "curse" in tags:
        return "curse"         # active cast
    return "active"


# Enemy conditions a build self-applies in real combat, each gated by the
# damage/tool that produces it. Enabling the ones a build qualifies for turns
# the pessimistic bare-dummy DPS into a realistic-combat number.
COMBAT_CONDITIONS = [
    ("conditionEnemyShocked",      "lightning"),
    ("conditionEnemyIgnited",      "fire"),
    ("conditionEnemyChilled",      "cold"),
    ("conditionEnemyArmourBroken", "physical"),
    ("conditionEnemyMaimed",       "physical"),
    ("conditionEnemyPoisoned",     "poison"),
    ("conditionEnemyBleeding",     "bleed"),
]


# spirit skill identification (persistent reservation buffs)
def is_spirit_skill(gem) -> bool:
    tags = (gem.get("tagString") or "").lower()
    d = (gem.get("description") or "").lower()
    return ("buff" in tags and ("reserve" in d or "herald" in tags or "banner" in tags
            or "aura" in tags)) or "herald" in gem["name"].lower() or "banner" in gem["name"].lower()


# combo seeds that keyword matching cannot derive (named-buff dependencies,
# ground-effect pairs) — curated from live meta build guides
CURATED_COMBOS = [
    ("Hollow Form", "Whirling Assault"),
    ("Oil Grenade", "Flameblast"),
    ("Whirling Slash", "Twister"),
    ("Smash to Smithereens", "Sunder"),
]


def floor_values(scoped_configs):
    out = {}
    for entry in scoped_configs:
        var, typ = entry["var"], entry["type"]
        if var.startswith(EXCLUDE_PREFIXES):
            continue
        out[var] = False if typ == "check" else 0
    return out


# Skills gated behind a resource PoB does not model as a cast-rate limit.
# Their screened DPS assumes free casting and is fiction as a main skill.
GATED_PATTERNS = (
    "glory",                  # the whole Glory family: ultimates and warcries whose
                              # uptime PoB does not model (Hammer of the Gods,
                              # Skyfall, Ancestral Cry, ...)
    "you may call down",
)


def is_gated(description: str) -> bool:
    d = (description or "").lower()
    return any(p in d for p in GATED_PATTERNS)


def find_mechanics(description: str, tag_string: str):
    """Return (provides, consumes) mechanic sets for one gem."""
    d = (description or "").lower()
    tags = (tag_string or "").lower()
    provides, consumes = set(), set()
    for mech, spec in MECHANICS.items():
        for kw in spec["provides"]:
            if kw in d or (mech in ("curse", "mark") and kw in tags):
                provides.add(mech)
                break
        for kw in spec["consumes"]:
            if kw in d:
                consumes.add(mech)
                break
    return provides, consumes
