"""P02-T02.1 offline lane: verbatim patch evidence and Flicker Strike coverage.

What is measured, with no PoB and no network:

* a ``verbatim`` release capture carries the fetched bytes, their recorded
  hash and an excerpt that occurs in them, or it is refused;
* the verbatim capture is chosen over the summary of the same patch, and the
  export drops the not-verbatim and unpinned-checkout gaps for the clean slice;
* Flicker Strike resolves to exactly the D07 gem and granted-skill rows in the
  slice exported from the clean pinned checkout, with its catalog facts;
* the ``members`` fixture kind catches a support moving to the wrong side and
  ignores an unrelated addition;
* every Flicker Strike catalog fixture matches the slice.

The behaviour fixtures need an engine; `tests/engine/test_p02_t02_1_flicker_engine.py`
runs them.
"""

from __future__ import annotations

import copy
import dataclasses
import hashlib
import json
import shutil
from pathlib import Path

import pytest

from objective_fixtures import resolved_selection

from pob2opt.catalog import (ExportRequest, MappingCatalogReader,
                             PobCatalogProvider, compatibility_fixtures,
                             entities_from_rows, load_release_capture)
from pob2opt.catalog.compatibility import ABSENT, MATCH, MISMATCH, run_fixtures
from pob2opt.catalog.release import (ReleaseCaptureError, current_release,
                                     load_release_captures,
                                     release_evidence_document)
from pob2opt.catalog.scope import resolve_target_skills
from pob2opt.catalog.sources import citations_from_payload
from pob2opt.catalog.supports import flicker_coverage, skill_coverage
from pob2opt.domain.objectives import FLICKER_SUSTAINED_DPS_V1

REPO_ROOT = Path(__file__).resolve().parents[2]
EVIDENCE = REPO_ROOT / "docs" / "evidence" / "P02"
RELEASE_DIR = EVIDENCE / "release"
VERBATIM = RELEASE_DIR / "poe2-0.5.5e-verbatim.json"
SUMMARY = RELEASE_DIR / "poe2-0.5.5e.json"
SLICE = EVIDENCE / "catalog-rows-slice.json"

FLICKER = FLICKER_SUSTAINED_DPS_V1.target_skill
GEM = "poe2/gems/" + FLICKER.gem_id
GRANTED = "poe2/granted_skills/" + FLICKER.granted_skill_id


@pytest.fixture(scope="module")
def rows() -> dict:
    return json.loads(SLICE.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def entities(rows) -> dict:
    return {table: entities_from_rows(table, rows["tables"][table])
            for table in ("gems", "granted_skills")}


def _copy_capture(tmp_path: Path, **changes) -> Path:
    raw = json.loads(VERBATIM.read_text(encoding="utf-8"))
    shutil.copyfile(RELEASE_DIR / raw["raw_file"], tmp_path / raw["raw_file"])
    raw.update(changes)
    path = tmp_path / "capture.json"
    path.write_text(json.dumps(raw), encoding="utf-8")
    return path


# ------------------------------------------------------- verbatim captures

def test_the_verbatim_capture_carries_the_bytes_it_hashes():
    capture = load_release_capture(VERBATIM)
    assert capture.is_verbatim
    raw = json.loads(VERBATIM.read_text(encoding="utf-8"))
    assert hashlib.sha256(capture.payload()).hexdigest() == raw["raw_sha256"]
    assert b"0.5.5e Patch Notes" in capture.payload()


def test_the_bundle_document_addresses_the_fetched_page():
    capture = load_release_capture(VERBATIM)
    document, payload = release_evidence_document(
        capture, record_id="evidence/release/x", created_at="2026-10-17T00:00:00Z",
        acquisition_version="test")
    assert payload == capture.raw
    assert document.byte_count == len(capture.raw)
    assert document.media_type.startswith("text/html")


def test_verbatim_wins_over_a_summary_of_the_same_patch():
    captures = load_release_captures(RELEASE_DIR)
    assert {c.fidelity for c in captures} == {"summary", "verbatim"}
    chosen, problem = current_release(captures, "poe2", "poe2")
    assert problem is None
    assert chosen.patch_id == "0.5.5e" and chosen.is_verbatim


def test_both_captures_agree_on_when_the_patch_went_live():
    summary = load_release_capture(SUMMARY)
    verbatim = load_release_capture(VERBATIM)
    assert summary.patch_published_at == verbatim.patch_published_at


def test_altered_bytes_are_refused(tmp_path):
    path = _copy_capture(tmp_path)
    page = tmp_path / json.loads(path.read_text(encoding="utf-8"))["raw_file"]
    page.write_bytes(page.read_bytes() + b" ")
    with pytest.raises(ReleaseCaptureError, match="hashes to"):
        load_release_capture(path)


def test_verbatim_without_bytes_is_refused(tmp_path):
    path = _copy_capture(tmp_path, raw_file=None, raw_sha256=None)
    with pytest.raises(ReleaseCaptureError, match="without the fetched bytes"):
        load_release_capture(path)


def test_a_version_1_capture_cannot_name_raw_bytes(tmp_path):
    path = _copy_capture(tmp_path, capture_version=1)
    with pytest.raises(ReleaseCaptureError, match="capture_version 1"):
        load_release_capture(path)


def test_an_excerpt_the_page_does_not_contain_is_refused(tmp_path):
    path = _copy_capture(tmp_path, excerpt="Flicker Strike now deals 500% more damage.")
    with pytest.raises(ReleaseCaptureError, match="not in raw_file"):
        load_release_capture(path)


def test_a_summary_capture_still_loads_unchanged():
    capture = load_release_capture(SUMMARY)
    assert not capture.is_verbatim and capture.raw is None
    assert b"summary" in capture.payload()


def test_the_clean_slice_export_drops_the_fidelity_and_checkout_gaps(rows):
    assert rows["pob_dirty_hash"] is None
    provider = PobCatalogProvider(
        MappingCatalogReader(rows["tables"], rows["rule_sources"]),
        citations=citations_from_payload(rows["citations"]),
        release_captures=load_release_captures(RELEASE_DIR),
        pob_commit=rows["pob_commit"], pob_dirty_hash=rows["pob_dirty_hash"])
    export = provider.export(ExportRequest())
    gap_ids = {gap.gap_id for gap in export.gaps}
    assert "gap/p02-t02/release-evidence-not-verbatim" not in gap_ids
    assert "gap/p02-t02/unpinned-checkout" not in gap_ids
    # Still retained: the engine release date and the slot rule.
    assert "gap/p02-t02/catalog-predates-current-patch" in gap_ids
    assert "gap/p02-t02/slot-accepted-base-categories" in gap_ids
    assert export.validation_errors == []


# --------------------------------------------------------- Flicker Strike

def test_flicker_strike_resolves_to_exactly_the_registered_pair(entities):
    coverage = skill_coverage(entities, FLICKER)
    assert coverage["issues"] == []
    assert coverage["gem_entity_id"] == GEM
    assert coverage["granted_skill_entity_id"] == GRANTED


def test_the_objective_scope_accepts_the_exported_ids(entities):
    selection = resolved_selection(target_skill_ids=[GEM, GRANTED])
    assert resolve_target_skills(entities, selection) == []


def test_flicker_strike_catalog_facts(entities):
    coverage = skill_coverage(entities, FLICKER)
    assert coverage["gem"]["weaponRequirements"] == "Quarterstaff"
    granted = coverage["granted_skill"]
    assert granted["weaponTypes"] == ["Staff"]
    assert set(granted["skillTypeNames"]) >= {
        "Attack", "Melee", "ConsumesCharges", "SkillConsumesPowerChargesOnUse"}
    assert {c["resource"] for c in granted["costs"]} == {"Mana"}
    constants = granted["statSets"][0]["constantStats"]
    assert ["flicker_strike_additional_flickers_from_power_charges", 2] in constants
    assert "cannot_gain_power_charges_during_skill" in granted["statSets"][0]["stats"]


def test_support_compatibility_comes_from_the_engine_row(entities):
    coverage = skill_coverage(entities, FLICKER)
    supported = set(coverage["supported_by_effect_ids"])
    assert "SupportRapidAttacksPlayer" in supported
    assert "SupportForkPlayer" not in supported
    for entry in coverage["compatible_support_gems"]:
        assert entry["granted_effect_id"] in supported


def test_a_missing_row_is_an_issue_not_a_substitute(entities):
    trimmed = {"gems": [e for e in entities["gems"] if e.entity_id != GEM],
               "granted_skills": entities["granted_skills"]}
    coverage = skill_coverage(trimmed, FLICKER)
    assert coverage["issues"] and GEM in coverage["issues"][0]
    assert "supported_by_effect_ids" not in coverage


def test_a_second_gem_with_the_same_name_is_ambiguous(entities):
    original = next(e for e in entities["gems"] if e.entity_id == GEM)
    twin = dataclasses.replace(original, entity_id="poe2/gems/Twin",
                               raw_reference={**original.raw_reference, "id": "Twin"})
    crowded = {**entities, "gems": [*entities["gems"], twin]}
    issues = skill_coverage(crowded, FLICKER)["issues"]
    assert any("shares the name" in issue and "poe2/gems/Twin" in issue
               for issue in issues)


def test_rows_from_an_older_adapter_say_so(rows):
    skills = copy.deepcopy(rows["tables"]["granted_skills"])
    for row in skills:
        row.pop("supportedBy", None)
    issues = flicker_coverage(rows["tables"]["gems"], skills)["issues"]
    assert any("supportedBy" in issue for issue in issues)


def test_a_support_marker_on_the_target_is_an_issue(rows):
    gems = copy.deepcopy(rows["tables"]["gems"])
    for row in gems:
        if row["id"] == FLICKER.gem_id:
            row["isSupport"] = True
    issues = flicker_coverage(gems, rows["tables"]["granted_skills"])["issues"]
    assert any("support" in issue for issue in issues)


# ------------------------------------------------------- fixtures on Flicker

def _flicker_fixtures() -> list[dict]:
    return [f for f in compatibility_fixtures()["fixtures"]
            if "flicker" in f["fixture_id"]]


def test_every_flicker_catalog_fixture_matches_the_slice(entities):
    fixtures = [f for f in _flicker_fixtures() if f["kind"] != "behaviour"]
    assert len(fixtures) >= 10
    outcomes = run_fixtures({"fixtures": fixtures}, entities)
    assert [o.fixture_id for o in outcomes if o.outcome != MATCH] == []


def test_the_flicker_behaviour_fixtures_pin_the_support_contrast():
    behaviour = {f["fixture_id"]: f["expected"] for f in _flicker_fixtures()
                 if f["kind"] == "behaviour"}
    alone = behaviour["behaviour/flicker-strike-alone"]
    assert behaviour["behaviour/flicker-strike-fork"] == alone
    assert (behaviour["behaviour/flicker-strike-rapid-attacks"]["Speed"]
            != alone["Speed"])


def _members_fixture() -> dict:
    return next(f for f in _flicker_fixtures() if f["kind"] == "members")


def _with_supported_by(entities, supported):
    skills = []
    for entity in entities["granted_skills"]:
        if entity.entity_id == GRANTED:
            raw = {**entity.raw_reference, "supportedBy": supported}
            entity = dataclasses.replace(entity, raw_reference=raw)
        skills.append(entity)
    return {**entities, "granted_skills": skills}


def _supported(entities) -> list[str]:
    return next(e for e in entities["granted_skills"]
                if e.entity_id == GRANTED).raw_reference["supportedBy"]


def test_a_dropped_support_is_a_mismatch_naming_it(entities):
    supported = [s for s in _supported(entities) if s != "SupportRapidAttacksPlayer"]
    outcome = run_fixtures({"fixtures": [_members_fixture()]},
                           _with_supported_by(entities, supported))[0]
    assert outcome.outcome == MISMATCH
    assert "SupportRapidAttacksPlayer" in outcome.detail


def test_an_excluded_support_appearing_is_a_mismatch(entities):
    supported = [*_supported(entities), "SupportForkPlayer"]
    outcome = run_fixtures({"fixtures": [_members_fixture()]},
                           _with_supported_by(entities, supported))[0]
    assert outcome.outcome == MISMATCH
    assert "SupportForkPlayer" in outcome.detail


def test_an_unrelated_new_support_is_not_a_mismatch(entities):
    supported = [*_supported(entities), "SupportSomethingNewPlayer"]
    outcome = run_fixtures({"fixtures": [_members_fixture()]},
                           _with_supported_by(entities, supported))[0]
    assert outcome.outcome == MATCH


def test_a_members_path_that_is_not_a_list_is_a_mismatch(entities):
    outcome = run_fixtures({"fixtures": [_members_fixture()]},
                           _with_supported_by(entities, None))[0]
    assert outcome.outcome == MISMATCH


def test_a_members_fixture_on_a_missing_entity_is_absent(entities):
    outcome = run_fixtures({"fixtures": [_members_fixture()]},
                           {"gems": entities["gems"], "granted_skills": []})[0]
    assert outcome.outcome == ABSENT
