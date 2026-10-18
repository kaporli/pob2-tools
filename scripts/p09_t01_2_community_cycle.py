"""flicker_sustained_v1 by the owner's community-PoB method (P09-T01.2).

    python scripts/p09_t01_2_community_cycle.py

Method ``pob-community-v2`` (D07 amendment 2026-10-18 (2)): per-use Flicker
Strike damage is PoB's own output at the build's maximum Power Charges with
the Charged Staff buff as PoB applies it; charges for Flicker Strike are
assumed. The rotation is Whirling Assault, Charged Staff, then Whirling
Assault and Flicker Strike repeated until the buff expires, then again. Every
action's PoB time counts inside [0, 120); burst is [0, 5) from the same start.

Offline: reads ``docs/evidence/P09-T01.2/replay.json`` and writes
``docs/evidence/P09-T01.2/community-cycle.json`` with the full timeline, the
damage breakdown, a mana ledger and the plain PoB numbers beside it.
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
EVID = REPO_ROOT / "docs" / "evidence" / "P09-T01.2"
REPLAY = EVID / "replay.json"
OUT = EVID / "community-cycle.json"
REPLAY_REF = "docs/evidence/P09-T01.2/replay.json"
DECISION = "docs/decisions/D07-flicker-strike-objective.md#amendment-2026-10-18-2"

METHOD_ID = "pob-community-v2"
WINDOW_S = 120.0
BURST_S = 5.0
#: Charges assumed for every Flicker Strike use and consumed by each Charged
#: Staff press (amendment 2 item 2): the build's maximum.
CHARGES = 5


def inputs(replay: dict, variant: str) -> dict:
    """Per-use values for one document variant, each traced to replay.json."""
    if variant == "seed":
        on, off = replay["flicker_seed"], replay["flicker_charged_staff_disabled"]
        on_ref, off_ref = "/flicker_seed", "/flicker_charged_staff_disabled"
    else:
        docs = replay["benchmark_documents"]
        on, off = docs["flicker_benchmark"], docs["flicker_benchmark_charged_staff_disabled"]
        on_ref = "/benchmark_documents/flicker_benchmark"
        off_ref = "/benchmark_documents/flicker_benchmark_charged_staff_disabled"
    buffed = next(r for r in on if r["forced_power_charges"] == CHARGES)
    plain = next(r for r in off if r["forced_power_charges"] == CHARGES)
    duration = replay["diagnostics"]["charged_staff_duration"]
    per_stack_s = duration["per_stack_ms_base"] / 1000 * (1 + duration["duration_inc"] / 100) \
        * duration["duration_more"]
    return {
        "t_WA_s": replay["whirling_assault"]["Time"],
        "t_CS_s": replay["charged_staff"]["Time"],
        "strikes_per_flicker": buffed["AverageBurstHits"],
        "strike_rate_per_s": buffed["Speed"],
        "per_strike_buffed": buffed["AverageDamage"],
        "per_strike_unbuffed": plain["AverageDamage"],
        "buff_duration_s": per_stack_s * CHARGES,
        "mana_WA": replay["whirling_assault"]["ManaCost"],
        "mana_CS": replay["charged_staff"]["ManaCost"],
        "mana_F": buffed["ManaCost"],
        "trace": {
            "t_WA_s": REPLAY_REF + "#/whirling_assault/Time",
            "t_CS_s": REPLAY_REF + "#/charged_staff/Time",
            "strikes_per_flicker": REPLAY_REF + "#" + on_ref + "/%d/AverageBurstHits" % CHARGES,
            "strike_rate_per_s": REPLAY_REF + "#" + on_ref + "/%d/Speed" % CHARGES,
            "per_strike_buffed": REPLAY_REF + "#" + on_ref + "/%d/AverageDamage" % CHARGES,
            "per_strike_unbuffed": REPLAY_REF + "#" + off_ref + "/%d/AverageDamage" % CHARGES,
            "buff_duration_s": REPLAY_REF + "#/diagnostics/charged_staff_duration "
                               "(6000 ms per stack x (1 + increased duration) x more, x %d stacks)" % CHARGES,
            "mana": REPLAY_REF + "#/whirling_assault/ManaCost, /charged_staff/ManaCost, "
                    + on_ref + "/%d/ManaCost" % CHARGES,
        },
    }


def timeline(v: dict) -> tuple[list[dict], list[dict]]:
    """Actions and Flicker Strike strikes in [0, WINDOW_S)."""
    actions: list[dict] = []
    strikes: list[dict] = []
    t = 0.0
    buff_end = None  # no buff before the first Charged Staff press

    def act(name, duration, **extra):
        nonlocal t
        actions.append({"action": name, "start_s": t, "end_s": t + duration, **extra})
        t += duration

    while t < WINDOW_S:
        if buff_end is None or buff_end <= t:
            act("Whirling Assault", v["t_WA_s"], mana=v["mana_WA"], purpose="charges for Charged Staff (assumed)")
            if t >= WINDOW_S:
                break
            act("Charged Staff", v["t_CS_s"], mana=v["mana_CS"], charges_consumed=CHARGES)
            buff_end = t + v["buff_duration_s"]
            actions[-1]["buff_until_s"] = buff_end
            if t >= WINDOW_S:
                break
        act("Whirling Assault", v["t_WA_s"], mana=v["mana_WA"], purpose="charges for Flicker Strike (assumed)")
        if t >= WINDOW_S:
            break
        start = t
        step = 1 / v["strike_rate_per_s"]
        use = len([a for a in actions if a["action"] == "Flicker Strike"]) + 1
        for k in range(1, v["strikes_per_flicker"] + 1):
            end = start + k * step
            buffed = buff_end is not None and end <= buff_end
            strikes.append({"use": use, "strike": k, "end_s": end, "buffed": buffed,
                            "damage": v["per_strike_buffed"] if buffed else v["per_strike_unbuffed"]})
        act("Flicker Strike", v["strikes_per_flicker"] * step, mana=v["mana_F"],
            charges_consumed=CHARGES, strikes=v["strikes_per_flicker"])
    return actions, strikes


def mana_ledger(actions: list[dict], pool: float, regen: float) -> dict:
    """Mana with continuous regeneration and costs paid at action start, no
    flask and no waiting: how far the schedule outruns the pool."""
    mana, t, lowest, first_short = pool, 0.0, pool, None
    spent = 0.0
    for a in actions:
        if a["start_s"] >= WINDOW_S:
            break
        mana = min(pool, mana + (a["start_s"] - t) * regen)
        t = a["start_s"]
        mana -= a["mana"]
        spent += a["mana"]
        if mana < 0 and first_short is None:
            first_short = a["start_s"]
        lowest = min(lowest, mana)
    return {"pool": pool, "regen_per_s": regen, "spent_in_window": spent,
            "regenerated_at_most": regen * WINDOW_S, "lowest_balance": lowest,
            "first_unaffordable_action_s": first_short,
            "assumptions": "Flicker Strike mana paid once per use; no mana flask; no waiting for mana. "
                           "The flask (356.5 per use, 10 of 75 charges, 0.25 charges per second) is not scheduled."}


def evaluate(replay: dict, variant: str) -> dict:
    v = inputs(replay, variant)
    actions, strikes = timeline(v)
    sustained = [s for s in strikes if s["end_s"] < WINDOW_S]
    burst = [s for s in strikes if s["end_s"] < BURST_S]
    total = sum(s["damage"] for s in sustained)
    out = replay["diagnostics"]["imported"]["outputs"]
    time_on = {}
    for a in actions:
        span = max(0.0, min(a["end_s"], WINDOW_S) - a["start_s"])
        time_on[a["action"]] = time_on.get(a["action"], 0.0) + span
    return {
        "document": variant,
        "inputs": v,
        "flicker_sustained_dps": total / WINDOW_S,
        "flicker_burst_dps": sum(s["damage"] for s in burst) / BURST_S,
        "attributed_damage_0_120": total,
        "breakdown": {
            "flicker_hits_with_charged_staff_buff": sum(s["damage"] for s in sustained if s["buffed"]),
            "flicker_hits_without_buff": sum(s["damage"] for s in sustained if not s["buffed"]),
            "strikes_counted": len(sustained),
            "flicker_uses_started": sum(1 for a in actions if a["action"] == "Flicker Strike"),
            "reported_not_scored": "Whirling Assault, Charged Shockwave, ignite, Living Lightning, heralds",
        },
        "time_in_window_s": time_on,
        "mana": mana_ledger(actions, out["Mana"], out["ManaRegenRecovery"]),
        "actions": actions,
        "strikes": strikes,
    }


def main() -> int:
    replay = json.loads(REPLAY.read_text(encoding="utf-8"))
    seed5 = next(r for r in replay["flicker_seed"] if r["forced_power_charges"] == CHARGES)
    bench5 = next(r for r in replay["benchmark_documents"]["flicker_benchmark"]
                  if r["forced_power_charges"] == CHARGES)
    ref = replay["reference_conditions"]["seed"]
    record = {
        "task": "P09-T01.2",
        "kind": "PoB-derived computation",
        "method_id": METHOD_ID,
        "decision": DECISION,
        "not_a_claim": "The owner's chosen method (community PoB per-use damage, charges assumed), with "
                       "rotation time counted. Not a verified game mechanic and not a gameplay measurement. "
                       "Not frozen as a reference result.",
        "command": "python scripts/p09_t01_2_community_cycle.py",
        "replay_sha256": hashlib.sha256(REPLAY.read_bytes()).hexdigest(),
        "rotation": "Whirling Assault, Charged Staff, then (Whirling Assault, Flicker Strike) until the "
                    "Charged Staff buff expires, then again (owner, amendment 2 item 1).",
        "primary": evaluate(replay, "seed"),
        "pounce_off": evaluate(replay, "benchmark"),
        "plain_pob": {
            "note": "PoB's own numbers at 5 forced charges with Charged Staff enabled; no rotation time.",
            "seed": {"AverageBurstDamage": seed5["AverageBurstDamage"], "TotalDPS": seed5["TotalDPS"]},
            "pounce_off": {"AverageBurstDamage": bench5["AverageBurstDamage"], "TotalDPS": bench5["TotalDPS"]},
            "reference_conditions_on_seed": {
                "config": replay["reference_conditions"]["config"],
                "AverageBurstDamage": ref["AverageBurstDamage"], "TotalDPS": ref["TotalDPS"],
                "note": "The community reference's condition inputs on the seed. Not adopted by amendment 2; reported only."},
        },
        "still_blocking_a_supported_score": [
            {"gap_id": "gap-p09-t011-sustain-cycle", "why": "the schedule spends more mana than the pool and regeneration supply; flask use is not scheduled"},
            {"gap_id": "gap-p09-t012-flicker-mana-charging", "why": "per-use or per-strike mana"},
            {"gap_id": "gap-p09-t011-attribution-rules", "why": "ownership table proposed, not accepted by a reviewer"},
            {"gap_id": "gap-p09-t011-config-conditions", "why": "the seed's PoB applies Pounce's Predator's Mark (x1.24); primary keeps it as the owner's PoB does, pounce_off drops it"},
        ],
        "resolved_by_decision": ["gap-p09-t011-rotation-details", "gap-p09-t012-charged-staff-period"],
        "waived_by_decision": [
            {"gap_id": g, "evidence": DECISION, "why": why} for g, why in (
                ("gap-p09-t011-charge-cycle-rules", "charges assumed for Flicker Strike"),
                ("gap-p09-t011-charged-staff-shared-charges", "Charged Staff and Flicker Strike each at maximum charges as PoB applies them"),
                ("gap-p09-t011-hit-and-run-movement", "Hit and Run as PoB applies it; owner's method, not a verified mechanic"),
            )],
    }
    OUT.write_text(json.dumps(record, indent=1, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    p = record["primary"]
    print("wrote %s: sustained %.0f, burst %.0f (seed); plain PoB TotalDPS %.0f"
          % (OUT.relative_to(REPO_ROOT), p["flicker_sustained_dps"], p["flicker_burst_dps"],
             seed5["TotalDPS"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
