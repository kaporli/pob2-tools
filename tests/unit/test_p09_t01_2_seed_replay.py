"""P09-T01.2: the clean seed replay and the cycle rule table are consistent.

Offline. Checks the committed evidence, not the engine:

* the replay ran on a clean checkout of the pin and agrees with every value
  P09-T01.1 captured,
* the benchmark documents differ from the seed only by the stated changes,
  and those changes move the numbers the way the rules say,
* every rule cites evidence that exists, and every rule that is not
  resolved names an open blocking or ranking gap in the suite,
* activation and attribution stay blocking, and no unassigned damage is
  counted.
"""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path

import pytest

import p09_t01_2_seed_replay as replay_script

EVID = Path("docs") / "evidence" / "P09-T01.2"
SEED_XML = Path("docs") / "evidence" / "P09-T01.1" / "seed" / "export-flicker-main.xml"
SCENARIOS = Path("benchmarks") / "p09-flicker-v1" / "scenarios.json"
PIN = "ce566eac45ea8a86477f513c7ee65a1ebe60014e"


def _load(repo_root: Path, rel) -> dict:
    return json.loads((repo_root / rel).read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def replay(repo_root: Path) -> dict:
    return _load(repo_root, EVID / "replay.json")


@pytest.fixture(scope="module")
def rules(repo_root: Path) -> dict:
    return _load(repo_root, EVID / "mechanics-rules.json")


@pytest.fixture(scope="module")
def web(repo_root: Path) -> dict:
    return _load(repo_root, EVID / "web-evidence.json")


@pytest.fixture(scope="module")
def gaps(repo_root: Path) -> dict:
    return {g["gap_id"]: g for g in _load(repo_root, SCENARIOS)["data_gaps"]}


def _pointer(doc, pointer: str):
    node = doc
    for part in [p for p in pointer.split("/") if p]:
        node = node[int(part)] if isinstance(node, list) else node[part]
    return node


def _rule(rules, rule_id):
    return next(r for r in rules["rules"] if r["rule_id"] == rule_id)


# ------------------------------------------------------------------ replay

def test_replay_ran_on_the_clean_pin(replay):
    assert replay["engine"]["head"] == PIN
    identity = replay["engine"]["adapter_identity"]
    assert identity["pob_commit"] == PIN and identity["pob_dirty_hash"] is None


def test_replay_agrees_with_every_earlier_value(replay):
    agreement = replay["agreement_with_p09_t01_1"]
    assert replay["agreement_summary"]["values_differing"] == 0
    stats = agreement["stats_flicker_main"]
    assert stats["compared"] == 734 and not stats["only_old"] and not stats["differ"]
    assert sorted(agreement["flicker_by_charges"]) == [str(c) for c in range(6)]
    assert all(row["compared"] == 6 and not row["differ"]
               for row in agreement["flicker_by_charges"].values())
    assert sorted(agreement["flicker_charged_staff_disabled"]) == ["1", "5"]
    assert agreement["whirling_assault"]["compared"] == 5
    assert agreement["enemy"]["compared"] == 7 and not agreement["enemy"]["differ"]


def test_every_probe_loaded_a_fresh_document(replay):
    names = [s["name"] for s in replay["states"]]
    assert len(names) == len(set(names))
    assert any(n.startswith("benchmark/flicker/") for n in names)


def test_document_edits_touch_only_the_named_element(repo_root: Path):
    xml = (repo_root / SEED_XML).read_text(encoding="utf-8")
    off = replay_script.disable_group(xml, replay_script.GROUP_POUNCE)
    assert len(off) == len(xml) + 1  # "true" -> "false"
    assert replay_script.group_gem(xml, replay_script.GROUP_POUNCE) == "Pounce"
    no_hr = replay_script.disable_gem(xml, replay_script.GROUP_FLICKER, "Hit and Run")
    assert no_hr.count('enabled="false"') == xml.count('enabled="false"') + 1
    with pytest.raises(LookupError):
        replay_script.disable_group(off, replay_script.GROUP_POUNCE)
    with pytest.raises(LookupError):
        replay_script.disable_gem(xml, replay_script.GROUP_WHIRLING, "Hit and Run")


def test_pounce_mark_is_the_only_seed_state_the_benchmark_drops(replay):
    seed = {r["forced_power_charges"]: r for r in replay["flicker_seed"]}
    bench = {r["forced_power_charges"]: r
             for r in replay["benchmark_documents"]["flicker_benchmark"]}
    for c in range(6):
        assert math.isclose(seed[c]["AverageDamage"] / bench[c]["AverageDamage"], 1.24, rel_tol=1e-6)
        assert bench[c]["Speed"] == seed[c]["Speed"]
        assert bench[c]["AverageBurstHits"] == 1 + 2 * c


def test_hit_and_run_only_changes_speed(replay):
    docs = replay["benchmark_documents"]
    with_hr = {r["forced_power_charges"]: r for r in docs["flicker_benchmark"]}
    without = {r["forced_power_charges"]: r for r in docs["flicker_benchmark_no_hit_and_run"]}
    for c in range(6):
        assert without[c]["AverageDamage"] == with_hr[c]["AverageDamage"]
        assert without[c]["ManaCost"] == with_hr[c]["ManaCost"]
        # PoB rounds Speed to four decimals.
        assert math.isclose(with_hr[c]["Speed"] / without[c]["Speed"], 1.4, rel_tol=1e-3)


def test_charged_staff_buff_is_the_only_charge_dependent_per_strike_term(replay):
    off = replay["benchmark_documents"]["flicker_benchmark_charged_staff_disabled"]
    per_strike = {r["forced_power_charges"]: r["AverageDamage"] for r in off}
    assert len({per_strike[c] for c in range(1, 6)}) == 1
    assert per_strike[0] < per_strike[1]  # 'consumed a Power Charge Recently'


# ------------------------------------------------------------------- rules

def test_rule_table_is_built_from_the_committed_replay_and_web_files(repo_root: Path, rules):
    for key, rel in (("replay_sha256", EVID / "replay.json"),
                     ("web_evidence_sha256", EVID / "web-evidence.json")):
        assert rules[key] == hashlib.sha256((repo_root / rel).read_bytes()).hexdigest()
    assert rules["engine_head"] == PIN


def test_every_rule_cites_evidence_that_exists(repo_root: Path, rules, replay, web):
    web_ids = {i["evidence_id"] for i in web["items"]}
    for rule in rules["rules"]:
        assert rule["evidence"], rule["rule_id"]
        for ref in rule["evidence"]:
            if ref.startswith("pob/"):
                assert ref in rules["citations"], ref
            elif ref.startswith("web/"):
                assert ref in web_ids, ref
            elif ref.startswith("docs/evidence/P09-T01.2/replay.json#"):
                _pointer(replay, ref.split("#", 1)[1])
            else:
                assert (repo_root / ref.split("#", 1)[0]).is_file(), ref


def test_unresolved_rules_name_an_open_gap(rules, gaps):
    for rule in rules["rules"]:
        if rule["status"] == "resolved":
            continue
        gap = gaps[rule["gap_id"]]
        assert gap["status"] == "open", rule["rule_id"]
        if rule["status"] == "blocking":
            assert gap["severity"] == "blocking", rule["rule_id"]


def test_activation_stays_blocking_with_written_variants(rules, gaps):
    rule = _rule(rules, "hit-and-run-reuse")
    assert rule["status"] == "blocking"
    assert {a["variant"] for a in rule["alternatives"]} == {
        "teleport_reenables", "no_hit_and_run", "timed_movement"}
    timed = next(a for a in rule["alternatives"] if a["variant"] == "timed_movement")
    assert timed["extra_time_s"] is None and timed["missing"]
    assert gaps["gap-p09-t011-hit-and-run-movement"]["status"] == "open"


def test_charged_staff_period_follows_the_owner_rotation(rules, gaps):
    rule = _rule(rules, "charged-staff-period")
    assert rule["status"] == "resolved"
    assert rule["parameters"]["buff_s_per_stack"] == pytest.approx(7.5)
    gap = gaps["gap-p09-t012-charged-staff-period"]
    assert gap["status"] == "resolved"
    assert any("amendment-2026-10-18-2" in e for e in gap["resolution_evidence_ids"])


def test_attribution_counts_only_flicker_hits_and_stays_open(rules, gaps):
    table = rules["attribution"]
    counted = " ".join(row["source"] for row in table["score_counts"])
    assert "Flicker Strike direct hits" in counted
    separate = " ".join(row["source"] for row in table["reported_separately"])
    for source in ("ignite", "Charged Shockwave", "Whirling Assault", "Living Lightning", "Herald"):
        assert source in separate
    assert gaps["gap-p09-t011-attribution-rules"]["status"] == "open"


def test_engine_checkout_gap_is_resolved_by_the_replay(gaps):
    gap = gaps["gap-p09-t011-engine-checkout-state"]
    assert gap["status"] == "resolved"
    assert gap["resolution_evidence_ids"] == ["docs/evidence/P09-T01.2/replay.json"]


def test_owner_q10_answer_is_recorded(repo_root: Path):
    seed = _load(repo_root, Path("docs") / "evidence" / "P09-T01.1" / "seed" / "manifest.json")
    answers = {a["question_id"]: a for a in seed["owner_answers"]["answers"]}
    assert answers["Q10"]["verbatim"] == "Once per N cycles"
    assert "gap-p09-t012-charged-staff-period" in answers["Q10"]["recorded"]


# ------------------------------------------------- PoB defaults and P06 shape

def test_bypass_cd_default_changes_nothing_and_distance_is_reported(replay, rules):
    probes = {p["probe"]: p for p in replay["config_probes"]}
    default, off = probes["default"], probes["FlickerStrikeBypassCD_off"]
    for key in ("AverageDamage", "AverageBurstDamage", "Speed", "ManaCost"):
        assert default[key] == off[key], key
    assert probes["enemyDistance_10"]["AverageDamage"] > default["AverageDamage"] \
        > probes["enemyDistance_35"]["AverageDamage"]
    assert _rule(rules, "flicker-bypass-cd-default")["status"] == "resolved"
    assert _rule(rules, "enemy-distance")["status"] == "conditional"


def test_unparsed_seed_nodes_are_covered(rules):
    text = _rule(rules, "way-of-the-stonefist")["rule"]
    assert "Martial Adept" in text and "Martial Master" in text
    assert _rule(rules, "consumed-power-charge-recently")["status"] == "conditional"


#: Mirrors pob2opt.coverage.resolution (branch p06-coverage, 3cc334d).
RESOLUTION_FIELDS = {"resolution_id", "gap_id", "mechanic_id", "evidence_ids", "author",
                     "resolved_at", "reviewer", "rule_changes", "input_values", "outcome"}
RULE_FIELDS = {"support", "validation", "limitations", "tolerances", "required_input_paths",
               "dependency_ids", "implementation_ref", "owner"}


def test_ledger_resolutions_fit_the_coverage_ledger(rules):
    resolutions = rules["p06_ledger_resolutions"]
    for res in resolutions:
        assert RESOLUTION_FIELDS <= set(res), res["resolution_id"]
        assert res["evidence_ids"] and res["reviewer"] is None
        assert set(res["rule_changes"]) <= RULE_FIELDS
        assert res["rule_changes"] or res["input_values"]
    ready = [r["resolution_id"] for r in resolutions if r["ready"]]
    assert ready == ["p09-t012/engine-checkout"]
    mechanics = [r["mechanic_id"] for r in resolutions]
    assert len(mechanics) == len(set(mechanics))  # no self-contradicting outcomes


# ----------------------------------------- pob-community-v2 (D07 amendment 2)

@pytest.fixture(scope="module")
def community(repo_root: Path) -> dict:
    return _load(repo_root, EVID / "community-cycle.json")


def test_community_cycle_is_built_from_the_committed_replay(repo_root: Path, community):
    assert community["replay_sha256"] == hashlib.sha256(
        (repo_root / EVID / "replay.json").read_bytes()).hexdigest()
    assert community["method_id"] == "pob-community-v2"


@pytest.mark.parametrize("variant", ["primary", "pounce_off"])
def test_timeline_follows_the_owner_rotation_and_counts_all_time(community, variant):
    run = community[variant]
    actions = run["actions"]
    assert [a["action"] for a in actions[:4]] == [
        "Whirling Assault", "Charged Staff", "Whirling Assault", "Flicker Strike"]
    for before, after in zip(actions, actions[1:]):
        assert after["start_s"] == pytest.approx(before["end_s"])
    # Charged Staff is pressed again only once its buff has run out.
    presses = [a for a in actions if a["action"] == "Charged Staff"]
    for prev, nxt in zip(presses, presses[1:]):
        assert nxt["start_s"] >= prev["buff_until_s"]
    assert sum(run["time_in_window_s"].values()) == pytest.approx(120.0)


@pytest.mark.parametrize("variant", ["primary", "pounce_off"])
def test_sustained_and_burst_come_from_completed_strikes(community, variant):
    run = community[variant]
    v = run["inputs"]
    counted = [s for s in run["strikes"] if s["end_s"] < 120.0]
    assert run["attributed_damage_0_120"] == pytest.approx(sum(s["damage"] for s in counted))
    assert run["flicker_sustained_dps"] == pytest.approx(run["attributed_damage_0_120"] / 120.0)
    burst = [s for s in run["strikes"] if s["end_s"] < 5.0]
    assert run["flicker_burst_dps"] == pytest.approx(sum(s["damage"] for s in burst) / 5.0)
    for s in counted:
        assert s["damage"] == (v["per_strike_buffed"] if s["buffed"] else v["per_strike_unbuffed"])
    # Rotation time lowers the value below PoB's plain per-use rate.
    assert run["flicker_sustained_dps"] < v["per_strike_buffed"] * v["strike_rate_per_s"]


def test_plain_pob_numbers_are_reported_beside(community, replay):
    seed5 = next(r for r in replay["flicker_seed"] if r["forced_power_charges"] == 5)
    plain = community["plain_pob"]
    assert plain["seed"] == {"AverageBurstDamage": seed5["AverageBurstDamage"],
                             "TotalDPS": seed5["TotalDPS"]}
    assert plain["reference_conditions_on_seed"]["config"] == replay["reference_conditions"]["config"]


def test_waivers_cite_the_decision_and_blockers_stay_open(community, rules, gaps):
    decision = "docs/decisions/D07-flicker-strike-objective.md#amendment-2026-10-18-2"
    waived = {w["gap_id"] for w in community["waived_by_decision"]}
    assert all(w["evidence"] == decision for w in community["waived_by_decision"])
    assert "gap-p09-t011-hit-and-run-movement" in waived
    for row in community["still_blocking_a_supported_score"]:
        assert gaps[row["gap_id"]]["status"] == "open"
    assert community["unsustained_schedule"]["seed"]["mana"]["first_unaffordable_action_s"] is not None
    assert _rule(rules, "hit-and-run-reuse")["pob_community_v2"] == "waived"
    assert _rule(rules, "mana-sustain")["pob_community_v2"] == "applies"


def test_mana_is_modelled_with_the_seed_flask_and_waiting_counts(community, replay, gaps):
    flask = replay["diagnostics"]["imported"]["flasks"]["Flask 2"]["flaskData"]
    for run in (community["primary"], community["pounce_off"]):
        mana = run["mana"]
        assert mana["lowest_balance"] >= -1e-9 and mana["first_unaffordable_action_s"] is None
        possible = (flask["chargesMax"] + flask["gainBase"] * 120.0) // flask["chargesUsed"]
        assert mana["flask_uses"] <= possible
        assert mana["flask_mana_recovered"] <= mana["flask_uses"] * flask["manaTotal"] + 1e-6
        assert run["time_in_window_s"]["wait for mana"] == pytest.approx(mana["waited_s"], abs=0.02)
    nowait = community["unsustained_schedule"]["seed"]
    assert nowait["flicker_sustained_dps"] > community["primary"]["flicker_sustained_dps"]
    for gid in ("gap-p09-t011-sustain-cycle", "gap-p09-t012-flicker-mana-charging"):
        assert gaps[gid]["status"] == "resolved" and gaps[gid]["resolution_evidence_ids"]
