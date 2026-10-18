"""P07-T01 first slice: the flicker_sustained_v1 cycle evaluator.

Hand-computed timelines check the event loop, mana and attribution; the
coverage-gated evaluator is checked on a fully settled synthetic build and on
the real seed from the frozen P09-T01.2 bundle. Nothing here starts the
engine; tests/engine/test_p07_t01_flicker_cycle_engine.py does.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from pathlib import Path

import pytest

from pob2opt.combat import (AttributionTable, DoubleAttribution, MissingValue, PolicyError,
                            evaluate_flicker, from_replay, load_p09_resolutions,
                            proposed_table, seed_rotation)
from pob2opt.combat.attribution import FLICKER_HIT, WHIRLING_HIT
from pob2opt.combat.events import (DECIDE, EXPIRE, IMPACT, STATE, EventLimitExceeded,
                                   EventLoop)
from pob2opt.combat.policy import compare, use
from pob2opt.combat.timeline import simulate, summary
from pob2opt.combat.values import (CycleValues, FlaskValues, benchmark_document,
                                   seed_replay_values)
from pob2opt.coverage.capture import bind_capture
from pob2opt.coverage.flicker_v1 import build_registry
from pob2opt.coverage.inputs import build_facts_from_pob_xml
from pob2opt.coverage.registry import MechanicsRegistry
from pob2opt.domain.enums import RuleSupport, RuleValidation

REPO = Path(__file__).resolve().parents[2]
SEED = REPO / "docs/evidence/P09-T01.1/seed/export-flicker-main.xml"
REPLAY = REPO / "docs/evidence/P09-T01.2/replay.json"
EVIDENCE = REPO / "docs/evidence/P07-T01/seed-evaluation.json"


PIN = "ce566eac45ea8a86477f513c7ee65a1ebe60014e"


def engine_result(scored_xml: str, **changes) -> dict:
    """What PARSE_SUPPORT_LUA returns for a document with no items or passives."""
    facts = build_facts_from_pob_xml(scored_xml)
    out = {"items": [], "nodes": [],
           "config": [{"var": k, "shown": True, "input": v, "placeholder": None}
                      for k, v in sorted(facts.config_explicit.items())],
           "selection": dict(facts.selection)}
    out.update(changes)
    return out


def identity(xml: str, *, pob_commit: str = PIN, pob_dirty: bool = False) -> dict:
    """What a clean pinned capture of ``xml``'s scoring document records."""
    scored = benchmark_document(xml)
    return {"head": PIN, "dirty_hash": None,
            "document_sha256": hashlib.sha256(scored.encode("utf-8")).hexdigest(),
            "state": {"forced_power_charges": 5, "document": "benchmark"},
            "parse_capture": bind_capture(scored, engine_result(scored),
                                          pob_commit=pob_commit, pob_dirty=pob_dirty)}


def values(**kw) -> CycleValues:
    base = dict(document="benchmark", charges=5, whirling_time_s=1.0, whirling_mana=0.0,
                whirling_damage_per_use=0.0, charged_staff_time_s=0.5, charged_staff_mana=0.0,
                flicker_strikes_per_use=3, flicker_strike_rate=3.0, flicker_mana=0.0,
                flicker_damage_per_strike_buffed=100.0, flicker_damage_per_strike_unbuffed=50.0,
                flicker_ignite_dps=None, buff_duration_s=10.0, mana_pool=1e9,
                mana_regen_per_s=0.0, flasks=(), pob_total_dps=None,
                pob_burst_damage_per_use=300.0, engine=identity(SYNTH_XML % ""))
    base.update(kw)
    return CycleValues(**base)


def run(v, **kw):
    t = simulate(v, seed_rotation(), proposed_table(), **kw)
    return t, summary(t, v, proposed_table())


# ------------------------------------------------------------ event loop ===

def test_event_order_is_time_then_phase_then_insertion():
    loop, seen = EventLoop(10), []
    for phase, kind in ((DECIDE, "d"), (IMPACT, "i"), (EXPIRE, "e"), (STATE, "s"), (IMPACT, "i2")):
        loop.schedule(5, phase, kind)
    loop.schedule(3, DECIDE, "early")
    loop.run(lambda e: seen.append(e.kind))
    assert seen == ["early", "e", "s", "i", "i2", "d"]


def test_no_event_in_the_past_and_no_decision_at_the_limit():
    loop, seen = EventLoop(10), []
    loop.schedule(10, IMPACT, "impact-at-limit")
    loop.schedule(10, DECIDE, "decide-at-limit")
    loop.schedule(11, IMPACT, "after")
    loop.run(lambda e: seen.append(e.kind))
    assert seen == ["impact-at-limit"]
    with pytest.raises(ValueError):
        loop.schedule(9, DECIDE, "past")


def test_event_bound_is_an_error_not_a_result():
    with pytest.raises(EventLimitExceeded):
        run(values(), max_events=10)


# ------------------------------------------------------ hand computation ===

def test_hand_computed_timeline_with_half_open_buff_and_windows():
    # WA [0,1), CS [1,1.5) buff [1.5,11.5), then (WA, F) pairs of 2 s; Flicker
    # uses start at 2.5, 4.5, 6.5, 8.5, 10.5 with impacts 1/3 s apart. The
    # last impact of the 10.5 use lands at exactly 11.5: unbuffed.
    t, s = run(values(), window_s=12.0, burst_s=5.0)
    flicker = [a["start_s"] for a in t.actions if a["skill"] == "FlickerStrikePlayer"]
    assert flicker == [2.5, 4.5, 6.5, 8.5, 10.5]
    assert s["attributed_damage_0_120"] == 14 * 100 + 50
    assert s["flicker_sustained_dps"] == pytest.approx(1450 / 12)
    # Burst [0,5): three strikes of the 2.5 use and the first of the 4.5 use.
    assert s["flicker_burst_dps"] == pytest.approx(400 / 5)
    assert t.buff_windows[0] == {"start_s": 1.5, "end_s": 11.5, "stacks": 5}
    assert all(a["start_s"] < 12.0 for a in t.actions)
    assert all(i["t_us"] <= 12_000_000 for i in t.impacts)


def test_expired_buff_is_refreshed_before_the_next_flicker_strike():
    t, _ = run(values(), window_s=20.0)
    seq = [a["skill"] for a in t.actions]
    i = seq.index("FlickerStrikePlayer", 4 * 2)
    assert seq[:4] == ["WhirlingAssaultPlayer", "ChargedStaffPlayer",
                       "WhirlingAssaultPlayer", "FlickerStrikePlayer"]
    # After the 10.5 use the buff has expired at 11.5: WA, then CS again.
    after = [a for a in t.actions if a["start_s"] >= 11.5]
    assert [a["skill"] for a in after[:3]] == ["WhirlingAssaultPlayer", "ChargedStaffPlayer",
                                              "WhirlingAssaultPlayer"]
    assert i > 0


def test_same_input_gives_identical_trace():
    a, _ = run(values())
    b, _ = run(values())
    assert a.to_json() == b.to_json()


# ------------------------------------------------- D07 adversarial cases ===

def test_doubling_an_off_skill_action_time_costs_time_once():
    long_buff = dict(buff_duration_s=10_000.0, flicker_damage_per_strike_unbuffed=100.0)
    _, one = run(values(**long_buff))
    _, two = run(values(whirling_time_s=2.0, **long_buff))
    ratio = two["flicker_sustained_dps"] / one["flicker_sustained_dps"]
    # Cycle 2 s -> 3 s: about 2/3, never the 1/2 a double penalty would give.
    assert 0.62 < ratio < 0.70
    assert two["time_in_window_s"]["Whirling Assault"] > one["time_in_window_s"]["Whirling Assault"]


def test_waiting_for_mana_reduces_dps_and_is_counted():
    starved = dict(mana_pool=300.0, mana_regen_per_s=20.0, flicker_mana=200.0, whirling_mana=50.0)
    t, limited = run(values(**starved))
    _, free = run(values(**starved), enforce_mana=False)
    assert limited["flicker_sustained_dps"] < free["flicker_sustained_dps"]
    assert limited["mana"]["waited_s"] > 0
    assert any(a["action"] == "wait for mana" for a in t.actions)
    assert limited["mana"]["lowest_balance"] >= -1e-6
    assert free["mana"]["first_deficit_s"] is not None


def test_flask_restores_mana_by_its_data_and_policy():
    flask = FlaskValues(slot="Flask 2", name="f", mana_total=300.0, instant_percent=30.0,
                        duration_s=3.0, charges_used=10.0, charges_max=20.0, charges_per_s=1.0)
    starved = dict(mana_pool=300.0, mana_regen_per_s=20.0, flicker_mana=200.0, whirling_mana=50.0)
    _, without = run(values(**starved))
    _, with_flask = run(values(flasks=(flask,), **starved))
    assert with_flask["mana"]["flask_uses"] > 0
    assert with_flask["flicker_sustained_dps"] > without["flicker_sustained_dps"]


def test_higher_burst_loses_to_higher_sustained():
    bursty = values(flicker_damage_per_strike_buffed=300.0, flicker_damage_per_strike_unbuffed=300.0,
                    mana_pool=1000.0, mana_regen_per_s=5.0, flicker_mana=500.0)
    steady = values(flicker_damage_per_strike_buffed=150.0, flicker_damage_per_strike_unbuffed=150.0)
    _, a = run(bursty)
    _, b = run(steady)
    assert a["flicker_burst_dps"] > b["flicker_burst_dps"]
    assert a["flicker_sustained_dps"] < b["flicker_sustained_dps"]
    ranked = sorted([("bursty", a), ("steady", b)], key=lambda r: -r[1]["flicker_sustained_dps"])
    assert ranked[0][0] == "steady"


def test_unrelated_skill_damage_cannot_win():
    _, quiet = run(values())
    _, loud = run(values(whirling_damage_per_use=1e12))
    assert loud["flicker_sustained_dps"] == quiet["flicker_sustained_dps"]
    assert loud["contributions"]["by_source"][WHIRLING_HIT]["owner"] == "unrelated"


def test_double_attribution_is_refused():
    with pytest.raises(DoubleAttribution):
        AttributionTable.from_rows("t", [(FLICKER_HIT, "flicker_direct"),
                                         (FLICKER_HIT, "flicker_secondary")])
    with pytest.raises(DoubleAttribution):
        AttributionTable.from_rows("t", [(FLICKER_HIT, "flicker_direct"),
                                         (FLICKER_HIT, "flicker_direct")])


def test_unassigned_source_is_never_scored():
    table = AttributionTable.from_rows("t", [(WHIRLING_HIT, "unrelated")])
    t = simulate(values(), seed_rotation(), table)
    assert summary(t, values(), table)["attributed_damage_0_120"] == 0.0


def test_on_kill_predicate_is_refused_not_satisfied():
    policy = seed_rotation()
    policy = replace(policy, rules=[use(0, "on-kill", "FlickerStrikePlayer",
                                        compare("state.kills_recent", "gte", 1))])
    with pytest.raises(PolicyError, match="unreachable"):
        simulate(values(), policy, proposed_table())


# --------------------------------------------- coverage-gated evaluation ===

SYNTH_XML = """<?xml version="1.0" encoding="UTF-8"?>
<PathOfBuilding2>
 <Build className="Monk" ascendClassName="Martial Artist" level="90" mainSocketGroup="1"/>
 <Skills><SkillSet id="1">
  <Skill enabled="true" set1="true" set2="true">
   <Gem skillId="FlickerStrikePlayer" nameSpec="Flicker Strike" enabled="true"/>
   <Gem skillId="SupportHitAndRunPlayer" nameSpec="Hit and Run" enabled="true"/>
  </Skill>
  <Skill enabled="true" set1="true" set2="true">
   <Gem skillId="WhirlingAssaultPlayer" nameSpec="Whirling Assault" enabled="true"/>%s
  </Skill>
  <Skill enabled="true" set1="true" set2="true">
   <Gem skillId="ChargedStaffPlayer" nameSpec="Charged Staff" enabled="true"/>
  </Skill>
 </SkillSet></Skills>
 <Tree><Spec nodes=""/></Tree>
</PathOfBuilding2>
"""
LIVING_LIGHTNING = ('\n   <Gem skillId="SupportLivingLightningPlayerTwo" '
                    'nameSpec="Living Lightning II" enabled="true"/>')
PROPOSED = proposed_table()


def settled(table=None, **changes) -> MechanicsRegistry:
    """Every seeded rule implemented, fixture-checked, evidenced and reviewed."""
    entries = []
    for e in build_registry():
        rule = replace(e.rule, support=RuleSupport.IMPLEMENTED,
                       validation=RuleValidation.FIXTURE_CHECKED,
                       evidence_ids=list(e.rule.evidence_ids) or ["fixture"])
        e = replace(e, rule=rule, reviewed_by="fixture reviewer")
        if e.mechanic_id == "activation/hit-and-run-reuse":
            e = replace(e, satisfied_by=("skill:FlickerStrikePlayer",))
        if e.mechanic_id == "attribution/flicker-sustained-v1":
            # Settled on exactly the scored table: its classes and its hash.
            bound = table or PROPOSED
            e = replace(e, assignments=dict(bound.classes), rule=replace(
                e.rule, evidence_ids=list(e.rule.evidence_ids) + [bound.binding_id()]))
        if e.mechanic_id == "charges/charged-staff-consumption":
            e = replace(e, provides_paths=("buff.charged_staff.active",))
        if e.mechanic_id == "support/SupportLivingLightningPlayerTwo":
            e = replace(e, damage_source=True)
        fix = changes.get(e.mechanic_id)
        if fix:
            e = fix(e)
        entries.append(e)
    return MechanicsRegistry("p06-flicker-v1", "1", entries)


@pytest.fixture()
def bench(tmp_path):
    path = tmp_path / "scenarios.json"
    path.write_text(json.dumps({"data_gaps": [], "scenarios": [
        {"scenario_id": "flicker_sustained_v1", "category": "dps_benchmark", "fields": {}}]}),
        encoding="utf-8")
    return path


def evaluate(bench, registry, *, xml=SYNTH_XML % "", source=None, **kw):
    return evaluate_flicker(xml, source or values(engine=identity(xml)), scenarios_path=bench,
                            config_options={}, registry=registry, patch_compatibility="verified",
                            **kw)


def test_settled_build_fills_the_objective(bench):
    result = evaluate(bench, settled())
    assert result.status == "eligible", result.decision
    assert result.objective["score"] == result.diagnostic["flicker_sustained_dps"]
    assert result.objective["metrics"]["flicker_burst_dps"] == result.diagnostic["flicker_burst_dps"]


def test_unsettled_attribution_blocks_with_everything_else_settled(bench):
    result = evaluate(bench, settled(**{
        "attribution/flicker-sustained-v1": lambda e: replace(e, reviewed_by=None)}))
    assert result.status == "blocked"
    assert "attribution/flicker-sustained-v1" in result.decision["unsettled_critical"]
    assert result.objective["metrics"] == {"flicker_sustained_dps": None, "flicker_burst_dps": None}
    assert result.objective["score"] is None
    assert result.diagnostic["label"].startswith("NOT ELIGIBLE")


def test_attribution_acceptance_must_be_explicit(bench):
    unsettled = {"attribution/flicker-sustained-v1": lambda e: replace(
        e, reviewed_by=None, rule=replace(e.rule, support=RuleSupport.UNSUPPORTED))}
    assert evaluate(bench, settled(**unsettled)).status == "blocked"
    accepted = evaluate(bench, settled(**unsettled), attribution_acceptance={
        "reviewer": "fixture reviewer", "evidence_ids": ["fixture"],
        "table_id": PROPOSED.table_id, "table_hash": PROPOSED.table_hash()})
    assert accepted.status == "eligible", accepted.decision


def test_unresolved_activation_is_defined_only_by_the_owners_method(bench):
    unknown = {"activation/hit-and-run-reuse": lambda e: replace(
        e, satisfied_by=None, reviewed_by=None,
        rule=replace(e.rule, support=RuleSupport.UNKNOWN, validation=RuleValidation.UNTESTED))}
    # pob-cycle-v1 has no implementation, so it never runs (review R7).
    assert evaluate(bench, settled(**unknown), method="pob-cycle-v1").status == "unsupported_method"
    owner = evaluate(bench, settled(**unknown), method="pob-community-v2")
    assert owner.status == "eligible", owner.decision
    applied = {a["resolution_id"]: a for a in owner.coverage["applied_resolutions"]}
    assert applied["pob-community-v2/hit-and-run"]["result"] == "applied"
    assert applied["pob-community-v2/hit-and-run"]["detail"].endswith("teleport-satisfies")


def test_movement_that_never_happens_blocks(bench):
    move_only = {"activation/hit-and-run-reuse": lambda e: replace(e, satisfied_by=("move",))}
    # Settled evidence that only movement re-enables the skill is not
    # overruled by the owner's method definition.
    result = evaluate(bench, settled(**move_only), method="pob-community-v2")
    assert result.status == "blocked"
    assert any(b["class"] == "activation_unmet" for b in result.decision["blocking"])


def test_unassigned_secondary_damage_blocks(bench):
    # A table, accepted and bound, that has no class for Living Lightning II.
    table = AttributionTable.from_rows("no-living-lightning", [
        (src, cls) for src, cls in PROPOSED.classes.items()
        if src != "support/SupportLivingLightningPlayerTwo"])
    xml = SYNTH_XML % LIVING_LIGHTNING
    result = evaluate(bench, settled(table=table), xml=xml, attribution=table)
    assert result.status == "blocked"
    assert any(b["class"] == "unassigned_damage" and
               "support/SupportLivingLightningPlayerTwo" in b["mechanics"]
               for b in result.decision["blocking"])


def test_missing_engine_value_keeps_metrics_null(bench):
    def source():
        raise MissingValue("/flicker/AverageDamage", "not in the engine output")
    result = evaluate(bench, settled(), source=source)
    assert result.status == "missing_inputs"
    assert result.objective["metrics"] == {"flicker_sustained_dps": None, "flicker_burst_dps": None}
    assert result.decision["blocking"][0]["fields"] == ["/flicker/AverageDamage"]
    with pytest.raises(MissingValue):
        replay = json.loads(REPLAY.read_text(encoding="utf-8"))
        replay["whirling_assault"] = {k: v for k, v in replay["whirling_assault"].items()
                                      if k != "Time"}
        from_replay(replay, source_xml=SEED.read_text(encoding="utf-8"),
                    source_sha256=hashlib.sha256(SEED.read_bytes()).hexdigest())


def test_invalid_rotation_returns_a_typed_refusal(bench):
    policy = replace(seed_rotation(), rules=[use(0, "x", "FlickerStrikePlayer",
                                                 compare("state.kills_recent", "gte", 1))])
    result = evaluate(bench, settled(), policy=policy)
    assert result.status == "invalid_rotation"
    assert result.objective["score"] is None


def test_evaluation_is_deterministic(bench):
    a, b = evaluate(bench, settled()), evaluate(bench, settled())
    assert a.to_json() == b.to_json()


# ------------------------------------------------------------ real seed ===

@pytest.fixture(scope="module")
def seed_result():
    replay = json.loads(REPLAY.read_text(encoding="utf-8"))
    return evaluate_flicker(SEED.read_text(encoding="utf-8"),
                            seed_replay_values(REPO),
                            p09_resolutions=load_p09_resolutions())


def test_seed_is_blocked_with_typed_gaps_and_a_labelled_diagnostic(seed_result):
    r = seed_result
    assert r.status == "blocked"
    assert r.objective["score"] is None
    assert r.decision["unsettled_critical"] == ["attribution/flicker-sustained-v1"]
    ids = set(r.decision["blocking_gap_ids"])
    assert {"gap-p09-t011-attribution-rules", "gap-p09-t011-patch-profile"} <= ids
    assert "gap-p09-t011-hit-and-run-movement" not in ids
    assert r.diagnostic["label"].startswith("NOT ELIGIBLE")
    assert 2.0e5 < r.diagnostic["flicker_sustained_dps"] < 2.6e5
    assert r.mana_ignored["flicker_sustained_dps"] > r.diagnostic["flicker_sustained_dps"]


def test_seed_matches_p09_t012_community_cycle_within_one_percent(seed_result):
    cycle = json.loads((REPO / "docs/evidence/P09-T01.2/community-cycle.json")
                       .read_text(encoding="utf-8"))
    theirs = cycle["pounce_off"]["flicker_sustained_dps"]
    assert seed_result.diagnostic["flicker_sustained_dps"] == pytest.approx(theirs, rel=0.01)
    assert seed_result.diagnostic["flicker_burst_dps"] == pytest.approx(
        cycle["pounce_off"]["flicker_burst_dps"], rel=1e-9)


def test_frozen_bundle_carries_the_capture_identity():
    v = seed_replay_values(REPO)
    seed = SEED.read_bytes().decode("utf-8")
    assert v.engine["head"] == PIN and v.engine["dirty_hash"] is None
    assert v.engine["document_sha256"] == hashlib.sha256(
        benchmark_document(seed).encode("utf-8")).hexdigest()
    with pytest.raises(MissingValue, match="hashes to"):
        from_replay(json.loads(REPLAY.read_text(encoding="utf-8")), source_xml=seed + " ",
                    source_sha256=v.engine["source_document_sha256"])


def test_seed_evidence_file_matches(seed_result):
    stored = json.loads(EVIDENCE.read_text(encoding="utf-8"))
    for key in ("evaluation_id", "status", "objective", "decision", "diagnostic"):
        assert stored[key] == json.loads(json.dumps(seed_result.to_json()[key])), key
