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


def test_charged_staff_period_is_a_rotation_parameter_left_open(rules, gaps):
    assert _rule(rules, "charged-staff-period")["parameters"] == {"N": None}
    gap = gaps["gap-p09-t012-charged-staff-period"]
    assert gap["status"] == "open" and gap["severity"] == "blocking"


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
