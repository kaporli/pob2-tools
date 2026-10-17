"""The P09-T01.1 Flicker Strike suite is complete, honest and frozen.

Offline. Checks the committed artefacts against the generator and against
the rules of the task:

* every field has a source or names a DataGap that exists, and a null value
  always names one,
* no field claims a performance measurement,
* survival gates carry a numeric or event definition,
* flicker_sustained_v1 matches D07 and the registered objective,
* the seed export is stored whole, its share code decodes to it, and the
  owner's rotation is verbatim,
* the scope proposal lists every ascendancy once and three distinct variants
  whose mechanics cite the pinned engine extract,
* the suite and reference hashes match the files.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

import p09_t01_1_flicker_suite as gen
from pob2opt.domain.identity import content_hash
from pob2opt.domain.objectives import FLICKER_SUSTAINED_DPS_V1

BENCH = Path("benchmarks") / "p09-flicker-v1"
EVID = Path("docs") / "evidence" / "P09-T01.1"


def _load(repo_root: Path, rel) -> dict:
    return json.loads((repo_root / rel).read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def bundle(repo_root: Path) -> dict:
    return _load(repo_root, BENCH / "scenarios.json")


@pytest.fixture(scope="module")
def suite(repo_root: Path) -> dict:
    return _load(repo_root, BENCH / "suite.json")


@pytest.fixture(scope="module")
def references(repo_root: Path) -> dict:
    return _load(repo_root, BENCH / "references.json")


@pytest.fixture(scope="module")
def scope(repo_root: Path) -> dict:
    return _load(repo_root, EVID / "scope-proposal.json")


@pytest.fixture(scope="module")
def seed(repo_root: Path) -> dict:
    return _load(repo_root, EVID / "seed" / "manifest.json")


@pytest.fixture(scope="module")
def mechanics(repo_root: Path) -> dict:
    return _load(repo_root, EVID / "mechanics.json")


@pytest.fixture(scope="module")
def gap_ids(bundle: dict) -> set:
    return {g["gap_id"] for g in bundle["data_gaps"]}


def _scenario(bundle, sid):
    return next(s for s in bundle["scenarios"] if s["scenario_id"] == sid)


# ------------------------------------------------------------ generator

def test_committed_artefacts_are_what_the_generator_produces(
        bundle, references, scope, seed):
    seed_manifest, scope_g, bundle_g, references_g, _ = gen.build_all()
    assert seed == seed_manifest
    assert scope == scope_g
    assert bundle == bundle_g
    assert references == references_g


# --------------------------------------------------------------- hashes

def test_every_source_file_matches_its_frozen_hash(repo_root: Path, suite: dict):
    for name, ref in suite["sources"].items():
        data = (repo_root / ref["path"]).read_bytes()
        assert hashlib.sha256(data).hexdigest() == ref["sha256"], name
        assert len(data) == ref["bytes"], name


def test_definition_and_suite_hashes_recompute(bundle, references, suite):
    identity = gen.suite_identity(bundle["scenarios"], references)
    assert content_hash(identity) == suite["suite_hash"]
    by_id = {s["scenario_id"]: s for s in bundle["scenarios"]}
    for row in suite["scenarios"]:
        assert content_hash(by_id[row["scenario_id"]]) == row["definition_hash"]


def test_seed_files_match_their_manifest(repo_root: Path, seed: dict):
    assert len(seed["files"]) == len(gen.SEED_FILES)
    for f in seed["files"]:
        data = (repo_root / f["path"]).read_bytes()
        assert hashlib.sha256(data).hexdigest() == f["sha256"], f["path"]


# ----------------------------------------------------------------- seed

def test_share_code_decodes_to_the_stored_export(repo_root: Path):
    seed_dir = repo_root / EVID / "seed"
    code = (seed_dir / "export-as-imported.code.txt").read_text(encoding="ascii").strip()
    xml = (seed_dir / "export-as-imported.xml").read_bytes()
    assert gen.decode_share_code(code) == xml
    assert b'className="Monk"' in xml and b'ascendClassName="Martial Artist"' in xml


def test_the_export_is_complete(repo_root: Path):
    seed_dir = repo_root / EVID / "seed"
    xml = (seed_dir / "export-as-imported.xml").read_text(encoding="utf-8")
    for part in ("<Build ", "<Tree ", "<Skills", "<Items", "<Config"):
        assert part in xml, part
    items = json.loads((seed_dir / "items-raw.json").read_text(encoding="utf-8"))
    assert "Sinister Quarterstaff" in items["Weapon 1"]
    assert "Mageblood" in items["Belt"]
    groups = json.loads((seed_dir / "skill-groups.json").read_text(encoding="utf-8"))
    flicker = next(g for g in groups if g["gems"][0]["name"] == "Flicker Strike")
    assert [g["name"] for g in flicker["gems"]] == [
        "Flicker Strike", "Hit and Run", "Concentrated Area", "Close Combat II",
        "Perpetual Charge", "Rakiata's Flow"]
    assert (flicker["gems"][0]["level"], flicker["gems"][0]["quality"]) == (20, 23)


def test_owner_rotation_is_verbatim_everywhere(seed, bundle):
    text = "whirling assault to get 5 power charges & then flicker strike, rince and repeat"
    assert gen.OWNER_ROTATION == text
    assert seed["owner_rotation"]["verbatim"] == text
    assert bundle["rotation"]["owner_statement_verbatim"] == text


def test_character_name_only_in_provenance(repo_root: Path):
    name = "JewsOfPalestine"
    hits = []
    for path in list((repo_root / EVID).rglob("*")) + list((repo_root / BENCH).rglob("*")):
        if path.is_file() and name in path.read_text(encoding="utf-8", errors="ignore"):
            hits.append(path.relative_to(repo_root).as_posix())
    assert hits == ["docs/evidence/P09-T01.1/seed/manifest.json"]


def test_pob_dps_is_labelled_proxy_only(seed, bundle):
    assert seed["pob_proxy_flicker_main"]["label"] == "proxy_only"
    proxy = _scenario(bundle, gen.DPS_ID)["fields"]["pob_proxy"]
    assert proxy["value"]["label"] == "proxy_only"


# --------------------------------------------------------------- fields

def test_every_field_is_sourced_or_names_a_gap(bundle, gap_ids):
    allowed = set(bundle["field_bases"])
    for s in bundle["scenarios"]:
        for name, f in s["fields"].items():
            assert f["basis"] in allowed, (s["scenario_id"], name)
            assert f["source"].strip(), (s["scenario_id"], name)
            for g in f["gap_ids"]:
                assert g in gap_ids, (s["scenario_id"], name, g)
            if f["value"] is None or f["basis"] == "unresolved":
                assert f["gap_ids"], (s["scenario_id"], name)
            if f["basis"] == "unresolved":
                assert f["value"] is None, (s["scenario_id"], name)


def test_no_field_claims_a_performance_measurement(bundle):
    bases = {f["basis"] for s in bundle["scenarios"] for f in s["fields"].values()}
    assert not bases & {"measured", "gameplay", "observation"}


def test_unknown_enemy_and_encounter_numbers_stay_null(bundle):
    for sid in gen.ENC_IDS:
        f = _scenario(bundle, sid)["fields"]
        assert f["encounter"]["gap_ids"] == ["gap-p09-t011-encounter-selection"]
        enc = f["encounter"]["value"]
        assert enc.get("map", enc.get("boss")) is None, sid
        for name in ("target_entities.count", "target_entities.health",
                     "target_entities.level", "target_entities.defenses",
                     "duration_limit_s", "minimum_success_fraction",
                     "incoming_damage_model_id", "reference_result_id"):
            assert f[name]["value"] is None, (sid, name)


def test_four_shapes_two_clear_two_boss(bundle):
    shapes = {s["scenario_id"]: (s["category"], s["shape"]) for s in bundle["scenarios"]}
    assert shapes == {
        "p09-flk-clear-dense": ("clear", "clear_dense"),
        "p09-flk-clear-spread": ("clear", "clear_spread"),
        "p09-flk-boss-short": ("boss", "boss_short"),
        "p09-flk-boss-sustained": ("boss", "boss_sustained"),
        "flicker_sustained_v1": ("dps_benchmark", "flicker_sustained_v1"),
    }


def test_every_survival_gate_has_a_numeric_or_event_definition(bundle):
    for s in bundle["scenarios"]:
        gates = s["fields"]["survival_gates"]["value"]
        assert gates, s["scenario_id"]
        for g in gates:
            assert g["definition"] in ("numeric", "event"), g
            assert g["path"].startswith("/metrics/") and g["operator"]
            if g["definition"] == "event":
                assert g["event"].strip() and g["threshold"] == 0.0
            if g["threshold"] is None:
                assert g["threshold_gap"] in s["fields"]["survival_gates"]["gap_ids"]


def test_completion_events_are_stated(bundle):
    for s in bundle["scenarios"]:
        c = s["fields"]["completion_condition"]["value"]
        assert c["start_event"].strip() and c["completion_event"].strip()
        assert "character death" in c["failure_events"]


# -------------------------------------------------------- D07 benchmark

def test_benchmark_matches_d07_and_the_registered_objective(bundle):
    f = _scenario(bundle, gen.DPS_ID)["fields"]
    windows = {w.name: [w.start_s, w.end_s] for w in FLICKER_SUSTAINED_DPS_V1.windows}
    assert f["window_s"]["value"] == windows["sustained"] == [0.0, 120.0]
    assert f["burst_window_s"]["value"] == windows["burst"] == [0.0, 5.0]
    assert f["adds"]["value"] == [] and f["kill_events"]["value"] == []
    assert f["target_entities.count"]["value"] == 1
    assert f["target_entities.dies"]["value"] is False
    assert f["objective"]["value"]["target_skill"]["granted_skill_id"] == "FlickerStrikePlayer"


def test_benchmark_target_is_the_fixed_pob_pinnacle_preset(bundle, repo_root: Path):
    f = _scenario(bundle, gen.DPS_ID)["fields"]
    table = _load(repo_root, EVID / "pob-charge-table.json")
    assert f["target_entities.identity"]["value"]["pob_config"] == {
        "enemyIsBoss": "Pinnacle", "presetBossSkills": "None"}
    assert f["target_entities.level"]["value"] == table["enemy"]["enemyLevel"] == 82
    d = f["target_entities.defenses"]["value"]
    assert d["resist"] == {"Fire": 50, "Cold": 50, "Lightning": 50, "Chaos": 0}
    assert f["kind"]["value"] == "pob_calculation"
    assert f["gameplay_recordings"]["value"] == "optional"


def test_in_game_target_and_measurement_gaps_resolved_by_the_d07_amendment(bundle):
    gaps = {g["gap_id"]: g for g in bundle["data_gaps"]}
    for gid in ("gap-p09-t011-benchmark-target", "gap-p09-t011-benchmark-measurement"):
        assert gaps[gid]["status"] == "resolved"
        assert gen.D07_AMENDMENT in gaps[gid]["resolution_evidence_ids"]


def test_method_is_defined_but_blocked_until_its_rules_are_known(bundle):
    f = _scenario(bundle, gen.DPS_ID)["fields"]["measurement_method"]
    sev = {g["gap_id"]: (g["severity"], g["status"]) for g in bundle["data_gaps"]}
    assert f["value"]["method_id"] == "pob-cycle-v1"
    assert any(sev[g] == ("blocking", "open") for g in f["gap_ids"])
    g_input = next(i for i in f["value"]["inputs"] if i["name"] == "g")
    assert g_input["value"] is None and g_input["gap_id"] == "gap-p09-t011-charge-cycle-rules"


def test_method_inputs_trace_to_the_pob_charge_table(bundle, repo_root: Path):
    table = _load(repo_root, EVID / "pob-charge-table.json")
    inputs = {i["name"]: i for i in _scenario(bundle, gen.DPS_ID)["fields"]["measurement_method"]["value"]["inputs"]}
    assert inputs["t_WA"]["seed_value"] == table["whirling_assault"]["Time"]
    for row in table["flicker_by_charges"]:
        c = str(row["power_charges"])
        assert inputs["H(c)"]["seed_values"][c] == row["AverageBurstHits"] == 1 + 2 * row["power_charges"]
        assert inputs["D(c)"]["seed_values_charged_staff_enabled"][c] == row["AverageBurstDamage"]
        assert inputs["S_F(c)"]["seed_values"][c] == row["Speed"]


def test_benchmark_initial_state_is_a_proposal_not_a_free_maximum(bundle):
    f = _scenario(bundle, gen.DPS_ID)["fields"]["initial_state.resources"]
    assert f["basis"] == "protocol_choice"
    assert f["value"]["power_charges"] == 0 and f["value"]["combo"] == 0


# ----------------------------------------------------------------- gaps

def test_gaps_are_open_specific_and_valid(bundle):
    from pob2opt.domain.validation import validate_record
    vacuous = {"need more data", "more data", "unknown", "tbd", "todo"}
    for g in gen.build_gaps():
        assert not validate_record(g).errors, g.gap_id
    for g in bundle["data_gaps"]:
        assert g["status"] in ("open", "resolved")
        if g["status"] == "resolved":
            assert g["resolution_evidence_ids"], g["gap_id"]
        assert g["needed_evidence"].strip().lower().rstrip(".") not in vacuous
        assert g["collection_method"].strip() and g["field_paths"] and g["subject_ids"]


def test_rotation_questions_each_name_gaps(bundle, gap_ids):
    qids = {q["question_id"] for q in bundle["owner_questions"]}
    for u in bundle["rotation"]["unresolved"]:
        assert u["question_id"] in qids
        assert u["gap_ids"] and set(u["gap_ids"]) <= gap_ids


def test_rotation_claims_cite_evidence(bundle, mechanics):
    ids = {e["mechanic_id"] for e in mechanics["entries"]}
    for c in bundle["rotation"]["derived_from_evidence"]:
        assert c.get("mechanic_ids") or c.get("source"), c["claim"]
        assert set(c.get("mechanic_ids", [])) <= ids, c["claim"]


# ---------------------------------------------------------------- scope

def test_every_ascendancy_appears_once_with_an_allowed_status(scope, repo_root: Path):
    catalog = _load(repo_root, gen.CATALOG_EXPORT)
    expected = sum(len(v) for v in catalog["character_rules"]["class_ascendancies"].values())
    rows = scope["ascendancies"]
    assert len(rows) == expected == 23
    assert len({r["ascendancy"] for r in rows}) == 23
    for r in rows:
        assert r["status"] in ("evidenced_by_seed", "catalog_possible", "excluded")
        assert r["reason"].strip()
    seeded = [r for r in rows if r["status"] == "evidenced_by_seed"]
    assert [(r["class"], r["ascendancy"]) for r in seeded] == [("Monk", "Martial Artist")]


def test_three_variants_with_distinct_charge_sources(scope, mechanics):
    ids = {e["mechanic_id"] for e in mechanics["entries"]}
    variants = scope["variants"]
    assert len(variants) == 3
    sources = [v["charge_source_event"] for v in variants]
    assert len(set(sources)) == 3
    generators = []
    for v in variants:
        reqs = v["required_mechanics"]
        assert reqs[0]["mechanic_ids"] == ["skill/FlickerStrikePlayer"]
        for r in reqs + v["seed_amplifiers"]:
            assert set(r["mechanic_ids"]) <= ids
        generators.append(reqs[1]["mechanic_ids"][0])
    assert len(set(generators)) == 3
    assert [v["status"] for v in variants] == ["evidenced_by_seed", "catalog_only", "catalog_only"]


def test_mechanics_extract_is_from_the_clean_pin(mechanics):
    assert mechanics["pob_commit"] == "ce566eac45ea8a86477f513c7ee65a1ebe60014e"
    assert mechanics["pob_dirty"] is False
    for e in mechanics["entries"]:
        assert e["file_sha256"] and e["path"].startswith("src/")


# ----------------------------------------------------------- references

def test_no_reference_is_frozen(references, suite):
    for r in references["scenarios"]:
        assert r["reference_build_id"] is None and r["reference_result_id"] is None
    for r in suite["scenarios"]:
        assert r["reference_status"] == "unresolved"
    cand = references["candidates"][0]
    assert cand["status"] == "candidate_configuration_only" and cand["closes"] == []


def test_protocol_document_refuses_practical_claims(repo_root: Path):
    text = (repo_root / BENCH / "protocol.md").read_text(encoding="utf-8")
    assert "not accepted" in text
    assert "proxy_only" in text
    assert chr(0x2014) not in text
    for q in ("Q1", "Q9"):
        assert q in text


# -------------------------------------------------- owner answers 2026-10-18

def test_owner_answers_are_recorded_verbatim(seed):
    answers = {a["question_id"]: a for a in seed["owner_answers"]["answers"]}
    assert answers["Q1"]["verbatim"] == "just 1"
    assert answers["Q2"]["verbatim"] == "whirling assault"
    assert answers["Q3"]["verbatim"] == "when i have a charge"
    assert answers["Q5"]["verbatim"] == "the dash from flicker itself"
    assert answers["Q8"]["verbatim"] == "we damage calc with PoB, not ingame testing"
    assert answers["Q9"]["verbatim"] == "any class, any ascendancy, any variant"
    assert len(seed["owner_decisions"]) == 2


def test_scope_is_approved_for_all_ascendancies_and_variants(scope, bundle):
    assert scope["approval"]["verbatim"] == "any class, any ascendancy, any variant"
    assert all(r["in_approved_scope"] for r in scope["ascendancies"])
    assert scope["approval"]["variants"] == [v["variant_id"] for v in scope["variants"]]
    gap = next(g for g in bundle["data_gaps"] if g["gap_id"] == "gap-p09-t011-class-scope-decision")
    assert gap["status"] == "resolved"


def test_hit_and_run_movement_is_non_blocking(bundle):
    gap = next(g for g in bundle["data_gaps"] if g["gap_id"] == "gap-p09-t011-hit-and-run-movement")
    assert gap["severity"] == "informational" and gap["status"] == "open"


def test_suite_lists_open_and_resolved_gaps(bundle, suite):
    status = {g["gap_id"]: g["status"] for g in bundle["data_gaps"]}
    assert set(suite["open_gaps"]) == {g for g, s in status.items() if s == "open"}
    assert set(suite["resolved_gaps"]) == {g for g, s in status.items() if s == "resolved"}


def test_reference_ninja_build_is_stored_and_decodes(repo_root: Path):
    d = repo_root / EVID / "reference-ninja-25c49"
    code = (d / "share-code.txt").read_text(encoding="ascii").strip()
    assert gen.decode_share_code(code) == (d / "decoded.xml").read_bytes()
    ev = json.loads((d / "evaluation.json").read_text(encoding="utf-8"))
    assert ev["source_url"] == "https://poe.ninja/poe2/pob/25c49"
    assert ev["kind"].startswith("community build")
    assert ev["flicker_selected"]["AverageBurstHits"] == 17


def test_d07_carries_a_dated_amendment_and_keeps_its_original_text(repo_root: Path):
    text = (repo_root / "docs" / "decisions" / "D07-flicker-strike-objective.md").read_text(encoding="utf-8")
    assert "## Amendment 2026-10-18" in text
    assert "Use one non-dying, continuously targetable enemy with explicit, evidenced level and defenses." in text
