"""The flicker_sustained_v1 timeline (P07-T01/T02, first slice).

Runs one ``RotationPolicy`` over the benchmark window with values from
``CycleValues``. Every action, every wait for mana and every strike is an
event; damage is credited at each strike's impact time, and only impacts in
the half-open windows count. Charges follow method ``pob-community-v2``:
Whirling Assault supplies the build's maximum, Charged Staff and Flicker
Strike each consume all held charges.

Action timing (PoB ``Time`` for Whirling Assault and Charged Staff; Flicker
Strike lasts strikes / ``Speed``) is the method's, not a measurement.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Mapping

from ..domain.records import RotationPolicy
from .attribution import AttributionTable, FLICKER_HIT, WHIRLING_HIT
from .events import (DECIDE, DEFAULT_MAX_EVENTS, EXPIRE, IMPACT, STATE, US_PER_S,
                     EventLoop, to_us)
from .mana import ManaState
from .policy import FLICKER_ID, STAFF_ID, WHIRLING_ID, choose, validate_policy
from .values import CycleValues

SKILL_NAMES = {FLICKER_ID: "Flicker Strike", WHIRLING_ID: "Whirling Assault",
               STAFF_ID: "Charged Staff"}


@dataclass
class TimelineResult:
    window_s: float
    burst_s: float
    mana_enforced: bool
    actions: list[dict] = field(default_factory=list)
    impacts: list[dict] = field(default_factory=list)
    flask_uses_s: list[float] = field(default_factory=list)
    buff_windows: list[dict] = field(default_factory=list)
    mana: dict = field(default_factory=dict)
    events_processed: int = 0
    stopped: str | None = None

    def credited(self, end_s: float) -> list[dict]:
        return [i for i in self.impacts if i["t_us"] < end_s * US_PER_S]

    def to_json(self) -> dict:
        return {"window_s": self.window_s, "burst_s": self.burst_s,
                "mana_enforced": self.mana_enforced, "events_processed": self.events_processed,
                "stopped": self.stopped, "mana": self.mana, "buff_windows": self.buff_windows,
                "flask_uses_s": self.flask_uses_s, "actions": self.actions,
                "impacts": self.impacts}


def simulate(values: CycleValues, policy: RotationPolicy, attribution: AttributionTable, *,
             window_s: float = 120.0, burst_s: float = 5.0,
             enforce_mana: bool = True, max_events: int = DEFAULT_MAX_EVENTS) -> TimelineResult:
    skills = {
        WHIRLING_ID: (to_us(values.whirling_time_s), values.whirling_mana),
        STAFF_ID: (to_us(values.charged_staff_time_s), values.charged_staff_mana),
    }
    step_s = 1.0 / values.flicker_strike_rate
    flicker_us = to_us(values.flicker_strikes_per_use * step_s)
    skills[FLICKER_ID] = (flicker_us, values.flicker_mana)
    validate_policy(policy, set(skills))

    limit_us = to_us(window_s)
    loop = EventLoop(limit_us, max_events=max_events)
    mana = ManaState.start(values.mana_pool, values.mana_regen_per_s, values.mana_flask())
    out = TimelineResult(window_s=window_s, burst_s=burst_s, mana_enforced=enforce_mana)
    state: dict[str, Any] = {"state.power_charges": 0, "buff.charged_staff.active": False}
    buff = {"start_us": None, "end_us": None, "stacks": 0}
    wait = {"start_us": None}
    uses = {"flicker": 0}

    def close_wait(now_us: int) -> None:
        if wait["start_us"] is not None and now_us > wait["start_us"]:
            out.actions.append({"action": "wait for mana", "skill": None,
                                "start_s": wait["start_us"] / US_PER_S, "end_s": now_us / US_PER_S,
                                "mana_cost": 0.0})
        wait["start_us"] = None

    def buffed(t_us: int) -> bool:
        return (buff["end_us"] is not None and buff["start_us"] <= t_us < buff["end_us"])

    def handle(event) -> None:
        now = event.time_us
        if event.kind == "buff_expire":
            if buff["end_us"] == now:
                state["buff.charged_staff.active"] = False
            return
        if event.kind == "impact":
            out.impacts.append(event.payload)
            return
        if event.kind == "action_end":
            payload = event.payload
            if payload["skill"] == WHIRLING_ID:
                state["state.power_charges"] = values.charges
            elif payload["skill"] == STAFF_ID:
                stacks = payload["charges_consumed"]
                buff.update(start_us=now, end_us=now + to_us(values.buff_duration_s / values.charges
                                                             * stacks), stacks=stacks)
                state["buff.charged_staff.active"] = True
                out.buff_windows.append({"start_s": now / US_PER_S, "end_s": buff["end_us"] / US_PER_S,
                                         "stacks": stacks})
                loop.schedule(buff["end_us"], EXPIRE, "buff_expire")
            return
        if event.kind != "decide":
            raise AssertionError(event.kind)
        mana.advance(now)
        rule = choose(policy, state)
        if rule is None:
            out.stopped = "no rule applies at %.6f s" % (now / US_PER_S)
            return
        duration_us, cost = skills[rule.skill_id]
        if enforce_mana:
            if mana.maybe_flask(cost):
                out.flask_uses_s.append(now / US_PER_S)
            if mana.mana < cost:
                if wait["start_us"] is None:
                    wait["start_us"] = now
                candidates = []
                afford = mana.time_to_afford_us(cost)
                if afford is not None:
                    candidates.append(now + max(1, afford))
                ready = mana.flask_ready_us()
                if ready is not None and ready > now:
                    candidates.append(ready)
                if not candidates:
                    out.stopped = "mana for %s is never affordable" % rule.skill_id
                    close_wait(limit_us)
                    return
                loop.schedule(min(candidates), DECIDE, "decide")
                return
        else:
            if mana.maybe_flask(cost):
                out.flask_uses_s.append(now / US_PER_S)
        close_wait(now)
        before = mana.mana
        mana.pay(cost)
        charges = state["state.power_charges"]
        record = {"action": rule.action_id, "skill": rule.skill_id,
                  "start_s": now / US_PER_S, "end_s": (now + duration_us) / US_PER_S,
                  "mana_cost": cost, "mana_before": before, "mana_after": mana.mana,
                  "charges_before": charges}
        end = now + duration_us
        if rule.skill_id == FLICKER_ID:
            uses["flicker"] += 1
            record["charges_consumed"] = charges
            record["strikes"] = values.flicker_strikes_per_use
            state["state.power_charges"] = 0
            for k in range(1, values.flicker_strikes_per_use + 1):
                t = now + to_us(k * step_s)
                hit = buffed(t)
                loop.schedule(t, IMPACT, "impact", {
                    "t_us": t, "t_s": t / US_PER_S, "source": FLICKER_HIT,
                    "owner": attribution.owner(FLICKER_HIT), "use": uses["flicker"], "strike": k,
                    "charged_staff_buff": hit,
                    "damage": (values.flicker_damage_per_strike_buffed if hit
                               else values.flicker_damage_per_strike_unbuffed)})
        elif rule.skill_id == STAFF_ID:
            record["charges_consumed"] = charges
            state["state.power_charges"] = 0
        elif rule.skill_id == WHIRLING_ID:
            record["charges_after"] = values.charges
            record["charges_note"] = "assumed by method pob-community-v2"
            if values.whirling_damage_per_use is not None:
                loop.schedule(end, IMPACT, "impact", {
                    "t_us": end, "t_s": end / US_PER_S, "source": WHIRLING_HIT,
                    "owner": attribution.owner(WHIRLING_HIT), "use": None, "strike": None,
                    "charged_staff_buff": False, "damage": values.whirling_damage_per_use})
        out.actions.append(record)
        loop.schedule(end, STATE, "action_end", {"skill": rule.skill_id,
                                                 "charges_consumed": charges})
        loop.schedule(end, DECIDE, "decide")

    loop.schedule(0, DECIDE, "decide")
    loop.run(handle)
    if wait["start_us"] is not None:
        close_wait(limit_us)
    mana.advance(max(mana.t_us, limit_us))
    out.events_processed = loop.processed
    out.mana = {
        "pool": mana.pool, "regen_per_s": mana.regen_per_s,
        "spent_in_window": math.fsum(a["mana_cost"] for a in out.actions if a["start_s"] < window_s),
        "flask_uses": mana.flask_uses, "flask_mana_recovered_raw": mana.flask_mana_raw,
        "lowest_balance": mana.lowest, "end_balance": mana.mana,
        "first_deficit_s": None if mana.first_deficit_us is None else mana.first_deficit_us / US_PER_S,
        "waited_s": math.fsum(min(a["end_s"], window_s) - a["start_s"] for a in out.actions
                        if a["skill"] is None),
        "flask": None if mana.flask is None else {
            "slot": mana.flask.slot, "name": mana.flask.name, "mana_total": mana.flask.mana_total,
            "instant_percent": mana.flask.instant_percent, "duration_s": mana.flask.duration_s,
            "charges_used": mana.flask.charges_used, "charges_max": mana.flask.charges_max,
            "charges_per_s": mana.flask.charges_per_s},
        "policy": "flask: start full; not while recovering; when its recovery fits under the "
                  "pool or the next cost is unaffordable" + (
                      "; actions wait for mana" if enforce_mana
                      else "; no waiting, balance may go negative (comparison only)"),
    }
    return out


def time_in_window(result: TimelineResult) -> dict[str, float]:
    spent: dict[str, float] = {}
    for a in result.actions:
        span = max(0.0, min(a["end_s"], result.window_s) - a["start_s"])
        name = SKILL_NAMES.get(a["skill"], a["action"])
        spent[name] = spent.get(name, 0.0) + span
    return spent


def repeatable_cycle(result: TimelineResult, values: CycleValues) -> dict:
    """Whether the rotation reaches a repeating state, and whether its mana
    balances per Charged Staff period without waiting."""
    presses = [a["start_s"] for a in result.actions if a["skill"] == STAFF_ID]
    periods = []
    for a, b in zip(presses, presses[1:]):
        seq = [x["skill"] or "wait" for x in result.actions if a <= x["start_s"] < b]
        waited = math.fsum(x["end_s"] - x["start_s"] for x in result.actions
                     if x["skill"] is None and a <= x["start_s"] < b)
        periods.append({"start_s": a, "end_s": b, "sequence": seq, "waited_s": waited})
    repeating = len(periods) >= 2 and periods[-1]["sequence"] == periods[-2]["sequence"]
    # Long-run balance of one no-wait period: the demand of its actions
    # against regeneration and the flask's charge-limited recovery.
    flask = values.mana_flask()
    step_s = 1.0 / values.flicker_strike_rate
    flicker_s = values.flicker_strikes_per_use * step_s
    pair_s = values.whirling_time_s + flicker_s
    head_s = values.whirling_time_s + values.charged_staff_time_s
    pairs = max(0, int((values.buff_duration_s) // pair_s) + 1)
    period_s = head_s + pairs * pair_s
    demand = (values.whirling_mana + values.charged_staff_mana
              + pairs * (values.whirling_mana + values.flicker_mana))
    supply = values.mana_regen_per_s * period_s
    if flask is not None and flask.charges_used > 0:
        supply += flask.charges_per_s * period_s / flask.charges_used * flask.mana_total
    return {
        "charged_staff_periods": periods,
        "repeating_sequence": repeating,
        "no_wait_period": {"pairs": pairs, "period_s": period_s, "mana_demand": demand,
                           "mana_supply_regen_plus_flask": supply,
                           "sustainable_without_waiting": supply >= demand},
        "note": "The mana-limited timeline repeats by waiting; indefinite sustain without "
                "waiting needs supply >= demand per period.",
    }


def contributions(result: TimelineResult, end_s: float) -> dict[str, Any]:
    rows: dict[str, dict] = {}
    parts: dict[str, list[float]] = {}
    for i in result.credited(end_s):
        key = i["source"]
        row = rows.setdefault(key, {"owner": i["owner"], "impacts": 0, "damage": 0.0})
        row["impacts"] += 1
        parts.setdefault(key, []).append(i["damage"])
    for key, values_ in parts.items():
        # fsum: Python 3.12 changed float sum(); results must not depend on it.
        rows[key]["damage"] = math.fsum(values_)
    flicker = [i for i in result.credited(end_s) if i["source"] == FLICKER_HIT]
    return {"by_source": rows,
            "flicker_with_charged_staff_buff": math.fsum(i["damage"] for i in flicker if i["charged_staff_buff"]),
            "flicker_without_buff": math.fsum(i["damage"] for i in flicker if not i["charged_staff_buff"]),
            "flicker_strikes_counted": len(flicker)}


def scored_damage(result: TimelineResult, attribution: AttributionTable, end_s: float) -> float:
    return math.fsum(i["damage"] for i in result.credited(end_s) if attribution.scores(i["source"]))


def summary(result: TimelineResult, values: CycleValues,
            attribution: AttributionTable) -> Mapping[str, Any]:
    sustained = scored_damage(result, attribution, result.window_s)
    burst = scored_damage(result, attribution, result.burst_s)
    return {
        "flicker_sustained_dps": sustained / result.window_s,
        "flicker_burst_dps": burst / result.burst_s,
        "attributed_damage_0_120": sustained,
        "attributed_damage_0_5": burst,
        "contributions": contributions(result, result.window_s),
        "time_in_window_s": time_in_window(result),
        "flicker_uses_started": sum(1 for a in result.actions if a["skill"] == FLICKER_ID),
        "preparation_time_s": math.fsum(min(a["end_s"], result.window_s) - a["start_s"]
                                  for a in result.actions if a["skill"] in (WHIRLING_ID, STAFF_ID)),
        "mana": result.mana,
    }
