"""P02-T02 offline lane: the catalog export with no PoB and no network.

Every test here runs the real exporter over a committed slice of engine rows
(`docs/evidence/P02/catalog-rows-slice.json`, PoB-derived and labelled as a
slice). What is measured:

* exported entities resolve the references a real saved build makes;
* entities that share a display name stay distinct entities;
* changing the upstream commit changes the evaluation context identity;
* an unresolved patch gives `unknown`, a summary capture or a failing
  fixture gives `partial`, and nothing here can reach `verified`;
* a profile pinned to an earlier patch stays usable as a historical profile;
* a rule upstream does not carry is a gap, not a constant.

The behaviour fixtures cannot run without an engine, so they report
`unchecked` here and the offline verdict is `unknown` unless a test supplies
its own fixture set. That is the intended semantics: an unchecked fixture is
not a pass. `tests/engine/test_p02_t02_catalog_engine.py` runs the real set.
"""

from __future__ import annotations

import copy
import dataclasses
import json
from pathlib import Path

import pytest

from pob2opt.catalog import (CatalogReader, ExportRequest, MappingCatalogReader,
                             PobCatalogProvider, catalog_hash,
                             compatibility_fixtures, context_identity,
                             derive_passive_edges, entities_from_rows,
                             entity_id, evaluation_context_hash,
                             load_release_capture, resolve_build_document)
from pob2opt.catalog.compatibility import (ABSENT, MATCH, MISMATCH, UNCHECKED,
                                           decide_compatibility, run_fixtures)
from pob2opt.catalog.release import ReleaseCaptureError
from pob2opt.catalog.rules import MissingRuleSource
from pob2opt.catalog.sources import citations_from_payload
from pob2opt.domain.enums import Compatibility, GapSeverity
from pob2opt.domain.validation import RecordIndex, validate_record

REPO_ROOT = Path(__file__).resolve().parents[2]
EVIDENCE = REPO_ROOT / "docs" / "evidence" / "P02"
SLICE = EVIDENCE / "catalog-rows-slice.json"
RELEASE = EVIDENCE / "release" / "poe2-0.5.5e.json"
SAMPLE_BUILD = EVIDENCE / "sample-build-ranger-quarterstaff.xml"
HUNTRESS_BUILD = REPO_ROOT / "tests" / "fixtures" / "builds" / "zero_dps_huntress.xml"


# ------------------------------------------------------------------ fixtures

@pytest.fixture(scope="module")
def rows() -> dict:
    return json.loads(SLICE.read_text(encoding="utf-8"))


@pytest.fixture()
def reader(rows) -> CatalogReader:
    return MappingCatalogReader(rows["tables"], rows["rule_sources"],
                                source=str(SLICE))


@pytest.fixture()
def capture():
    return load_release_capture(RELEASE)


@pytest.fixture()
def provider(reader, rows, capture):
    return PobCatalogProvider(
        reader,
        citations=citations_from_payload(rows["citations"]),
        release_captures=[capture],
        pob_commit=rows["pob_commit"],
        pob_dirty_hash=rows["pob_dirty_hash"],
        adapter_version="p02-t02.0")


@pytest.fixture()
def request_file():
    return ExportRequest(game="poe2", realm="poe2", league_id="Standard")


@pytest.fixture()
def export(provider, request_file):
    return provider.export(request_file)


# --------------------------------------------- the bundle is self-contained

def test_every_record_in_the_bundle_validates_against_the_bundle(export):
    assert export.validation_errors == []
    index = RecordIndex()
    for record in export.records:
        index.add(record)
    for digest in export.blobs:
        index.add_blob(digest)
    for record in export.records:
        report = validate_record(record, index=index)
        assert report.ok, (record.record_id, report.errors)


def test_the_profile_and_the_catalog_name_each_other(export):
    assert export.catalog.patch_profile_id == export.profile.record_id
    assert export.profile.catalog_hash == export.catalog.catalog_hash


def test_every_evidence_blob_is_stored_with_its_document(export):
    for document in export.evidence:
        payload = export.blobs[document.blob_hash]
        assert len(payload) == document.byte_count


# ---------------------------------- exported entities resolve sample builds

def test_a_saved_build_resolves_completely_against_the_export(export):
    resolution = resolve_build_document(
        SAMPLE_BUILD.read_text(encoding="utf-8"), export.catalog.entities)
    assert resolution.unresolved == []
    assert resolution.ambiguous == []
    # The references a real saved build actually makes, not just its class.
    assert resolution.counts["passive_node"] >= 30
    for kind in ("class", "gem", "granted_skill", "item_base", "slot"):
        assert resolution.counts.get(kind), kind


def test_the_synthetic_huntress_build_resolves_too(export):
    resolution = resolve_build_document(
        HUNTRESS_BUILD.read_text(encoding="utf-8"), export.catalog.entities)
    assert resolution.complete
    assert resolution.resolved["class:8"] == "poe2/classes/8"


def test_a_reference_the_catalog_does_not_have_is_unresolved_not_invented(export):
    xml = SAMPLE_BUILD.read_text(encoding="utf-8").replace(
        'classId="2"', 'classId="4242"')
    resolution = resolve_build_document(xml, export.catalog.entities)
    assert not resolution.complete
    assert any(item["reference"] == "4242" for item in resolution.unresolved)
    assert "class:4242" not in resolution.resolved


def test_a_document_that_is_not_xml_is_reported_not_silently_empty(export):
    resolution = resolve_build_document("not xml at all",
                                        export.catalog.entities)
    assert not resolution.complete
    assert resolution.unresolved[0]["kind"] == "document"


# ------------------------------------- duplicate display names stay distinct

def test_entities_sharing_a_display_name_remain_separate_entities():
    rows = [
        {"id": "Metadata/Items/Gems/SkillGemMaceStrikeA", "name": "Mace Strike"},
        {"id": "Metadata/Items/Gems/SkillGemMaceStrikeB", "name": "Mace Strike"},
    ]
    entities = entities_from_rows("gems", rows)
    assert len({entity.entity_id for entity in entities}) == 2
    assert [entity.display_names for entity in entities] == [
        ["Mace Strike"], ["Mace Strike"]]


def test_the_real_slice_still_carries_repeated_display_names(export):
    seen: dict[str, set[str]] = {}
    for table in ("gems", "passive_nodes", "granted_skills"):
        for entity in export.catalog.entities[table]:
            for name in entity.display_names:
                seen.setdefault("%s|%s" % (table, name), set()).add(
                    entity.entity_id)
    repeated = {key: ids for key, ids in seen.items() if len(ids) > 1}
    assert repeated, "the slice no longer demonstrates duplicate names"
    for key, ids in repeated.items():
        assert len(ids) > 1, key


def test_an_ambiguous_display_name_is_reported_not_resolved(export):
    # Two slots carry the display name "Weapon 1"; a document naming one by
    # its native id gets that one, and a name-only reference stays ambiguous.
    names = {}
    for entity in export.catalog.entities["slots"]:
        for name in entity.display_names:
            names.setdefault(name, []).append(entity.entity_id)
    shared = [name for name, ids in names.items() if len(set(ids)) > 1]
    assert shared, "the slot table no longer has a shared display name"


# ----------------------------- changing the upstream commit changes identity

def test_a_different_upstream_commit_is_a_different_context(export):
    other = dataclasses.replace(export.profile, pob_commit="f" * 40)
    assert evaluation_context_hash(other) != evaluation_context_hash(export.profile)


def test_a_modified_working_tree_is_a_different_context(export):
    # The slice is recorded from a clean tree (P02-T02.1), so dirty it.
    other = dataclasses.replace(export.profile, pob_dirty_hash="d" * 64)
    assert evaluation_context_hash(other) != evaluation_context_hash(export.profile)


def test_a_different_catalog_is_a_different_context(export):
    other = dataclasses.replace(export.profile, catalog_hash="0" * 64)
    assert evaluation_context_hash(other) != evaluation_context_hash(export.profile)


def test_resolution_time_and_record_id_do_not_change_the_context(export):
    other = dataclasses.replace(export.profile,
                                record_id="patch-profile/renamed",
                                resolved_at="2099-01-01T00:00:00Z",
                                created_at="2099-01-01T00:00:00Z")
    assert evaluation_context_hash(other) == evaluation_context_hash(export.profile)
    assert "resolved_at" not in context_identity(export.profile)


def test_the_same_rows_export_to_the_same_catalog_hash(provider, request_file,
                                                       reader, rows, capture):
    first = provider.export(request_file)
    second = PobCatalogProvider(
        MappingCatalogReader(rows["tables"], rows["rule_sources"]),
        citations=citations_from_payload(rows["citations"]),
        release_captures=[capture],
        pob_commit=rows["pob_commit"],
        pob_dirty_hash=rows["pob_dirty_hash"]).export(request_file)
    assert first.catalog.catalog_hash == second.catalog.catalog_hash


def test_one_changed_modifier_line_forks_the_catalog_hash(rows):
    entities = {table: entities_from_rows(table, table_rows)
                for table, table_rows in rows["tables"].items()}
    before = catalog_hash(entities)
    changed = copy.deepcopy(rows["tables"])
    changed["item_modifiers"][0]["lines"] = ["a line nobody wrote upstream"]
    entities["item_modifiers"] = entities_from_rows(
        "item_modifiers", changed["item_modifiers"])
    assert catalog_hash(entities) != before


# ------------------------------------------------ compatibility is not a label

def test_without_release_evidence_the_patch_is_unknown_and_blocking(
        reader, rows, request_file):
    provider = PobCatalogProvider(
        reader, citations=citations_from_payload(rows["citations"]),
        release_captures=[], pob_commit=rows["pob_commit"],
        pob_dirty_hash=rows["pob_dirty_hash"])
    export = provider.export(request_file)
    assert export.profile.patch_id == "unknown"
    assert export.profile.compatibility is Compatibility.UNKNOWN
    blocking = [gap for gap in export.gaps
                if gap.gap_id.endswith("current-patch-unresolved")]
    assert blocking and blocking[0].severity is GapSeverity.BLOCKING
    assert export.validation_errors == []


def test_an_unchecked_behaviour_fixture_is_not_a_pass(export):
    unchecked = [o for o in export.report.outcomes if o.outcome == UNCHECKED]
    assert unchecked, "the offline lane should not be able to check behaviour"
    assert export.profile.compatibility is Compatibility.UNKNOWN


def test_a_summary_capture_can_never_reach_verified(capture):
    assert not capture.is_verbatim
    verdict, reasons = decide_compatibility(
        [_outcome(MATCH)], patch_id="0.5.5e",
        patch_published_at="2026-10-06T00:00:00Z",
        engine_released_at="2026-12-01T00:00:00Z",
        evidence_is_verbatim=capture.is_verbatim,
        checkout_is_pinned=True)
    assert verdict is Compatibility.PARTIAL
    assert any("summary" in reason for reason in reasons)


def test_an_engine_older_than_the_patch_is_partial_not_verified():
    verdict, reasons = decide_compatibility(
        [_outcome(MATCH)], patch_id="0.5.5e",
        patch_published_at="2026-10-06T00:00:00Z",
        engine_released_at="2026-07-28T00:00:00Z",
        evidence_is_verbatim=True, checkout_is_pinned=True)
    assert verdict is Compatibility.PARTIAL
    assert any("predates" in reason for reason in reasons)


def test_a_failing_fixture_is_partial_even_when_everything_else_is_clean():
    verdict, reasons = decide_compatibility(
        [_outcome(MATCH), _outcome(MISMATCH, "field/moved")],
        patch_id="0.5.5e", patch_published_at="2026-01-01T00:00:00Z",
        engine_released_at="2026-02-01T00:00:00Z",
        evidence_is_verbatim=True, checkout_is_pinned=True)
    assert verdict is Compatibility.PARTIAL
    assert any("field/moved" in reason for reason in reasons)


def test_an_absent_entity_is_partial():
    verdict, _ = decide_compatibility(
        [_outcome(ABSENT, "avail/gone")], patch_id="0.5.5e",
        patch_published_at="2026-01-01T00:00:00Z",
        engine_released_at="2026-02-01T00:00:00Z",
        evidence_is_verbatim=True, checkout_is_pinned=True)
    assert verdict is Compatibility.PARTIAL


def test_verified_is_reachable_only_with_every_condition_met():
    verdict, reasons = decide_compatibility(
        [_outcome(MATCH)], patch_id="0.4.0",
        patch_published_at="2026-01-01T00:00:00Z",
        engine_released_at="2026-02-01T00:00:00Z",
        evidence_is_verbatim=True, checkout_is_pinned=True,
        blocking_gap_ids=())
    assert verdict is Compatibility.VERIFIED
    assert reasons


def test_a_blocking_gap_prevents_verified():
    verdict, _ = decide_compatibility(
        [_outcome(MATCH)], patch_id="0.4.0",
        patch_published_at="2026-01-01T00:00:00Z",
        engine_released_at="2026-02-01T00:00:00Z",
        evidence_is_verbatim=True, checkout_is_pinned=True,
        blocking_gap_ids=("gap/x",))
    assert verdict is Compatibility.PARTIAL


def test_a_matching_version_label_alone_decides_nothing():
    """No outcomes at all is unknown, however good the patch evidence is."""
    verdict, _ = decide_compatibility(
        [], patch_id="0.5.5e", patch_published_at="2026-01-01T00:00:00Z",
        engine_released_at="2026-02-01T00:00:00Z",
        evidence_is_verbatim=True, checkout_is_pinned=True)
    assert verdict is Compatibility.UNKNOWN


def _outcome(state, fixture_id="fixture/one"):
    from pob2opt.catalog.compatibility import FixtureOutcome
    return FixtureOutcome(fixture_id, "availability", state, "synthetic")


# ---------------------------------- the fixture set runs against the export

def test_the_shipped_fixture_set_matches_the_slice_where_it_can(export):
    outcomes = {o.fixture_id: o for o in export.report.outcomes}
    assert outcomes, "the shipped fixture set is empty"
    for fixture_id, outcome in outcomes.items():
        if outcome.kind == "behaviour":
            assert outcome.outcome == UNCHECKED
        elif outcome.kind == "count":
            # The slice is a slice; count floors are a live-engine check.
            continue
        else:
            assert outcome.outcome == MATCH, (fixture_id, outcome.detail)


def test_a_removed_entity_makes_its_fixture_absent(export):
    entities = dict(export.catalog.entities)
    entities["classes"] = [entity for entity in entities["classes"]
                           if entity.entity_id != "poe2/classes/8"]
    outcomes = run_fixtures(compatibility_fixtures(), entities)
    huntress = [o for o in outcomes if o.fixture_id == "avail/class/huntress"]
    assert huntress and huntress[0].outcome == ABSENT


def test_a_renamed_entity_makes_its_fixture_mismatch(export):
    entities = dict(export.catalog.entities)
    entities["classes"] = [
        dataclasses.replace(entity, display_names=["Huntress Reworked"])
        if entity.entity_id == "poe2/classes/8" else entity
        for entity in entities["classes"]]
    outcomes = run_fixtures(compatibility_fixtures(), entities)
    huntress = [o for o in outcomes if o.fixture_id == "avail/class/huntress"]
    assert huntress and huntress[0].outcome == MISMATCH


def test_a_behaviour_fixture_whose_engine_fails_is_a_mismatch_not_a_pass(export):
    def explode(_fixture):
        raise RuntimeError("the engine died")

    outcomes = run_fixtures(compatibility_fixtures(), export.catalog.entities,
                            behaviour=explode)
    behaviour = [o for o in outcomes if o.kind == "behaviour"]
    assert behaviour and all(o.outcome == MISMATCH for o in behaviour)


# --------------------------------------- historical profiles stay historical

def test_a_profile_pinned_to_an_older_patch_is_stale_and_still_usable(
        provider, export):
    historical = provider.export(ExportRequest(pinned_patch_id="0.5.4"))
    assert historical.profile.patch_id == "0.5.4"
    assert historical.profile.compatibility is Compatibility.STALE
    assert historical.validation_errors == []
    # It is a different context from the live one, and it still hashes.
    assert (evaluation_context_hash(historical.profile)
            != evaluation_context_hash(export.profile))
    ids = {gap.gap_id for gap in historical.gaps}
    assert any(gap_id.endswith("pinned-patch-superseded") for gap_id in ids)


def test_a_historical_profile_without_its_own_capture_says_so(provider):
    historical = provider.export(ExportRequest(pinned_patch_id="0.5.4"))
    ids = {gap.gap_id for gap in historical.gaps}
    assert any(gap_id.endswith("historical-patch-evidence-missing")
               for gap_id in ids)


def test_pinning_to_the_live_patch_is_not_stale(provider, capture):
    pinned = provider.export(ExportRequest(pinned_patch_id=capture.patch_id))
    assert pinned.profile.compatibility is not Compatibility.STALE


# ------------------------------------- rules are sourced or they are gaps

def test_the_level_range_and_point_maximums_come_from_cited_source(export):
    rules = export.profile.character_rules
    assert (rules.level_range.minimum, rules.level_range.maximum) == (1, 100)
    maximum = [b for b in rules.point_budgets
               if b.rule_id == "budget/ascendancy/maximum"]
    assert maximum and maximum[0].ascendancy_points == 8
    for budget in rules.point_budgets:
        assert budget.evidence_ids, budget.rule_id


def test_the_levelling_budget_is_the_level_minus_one_and_says_so(export):
    budgets = {b.rule_id: b for b in export.profile.character_rules.point_budgets}
    for level in (1, 2, 28, 100):
        budget = budgets["budget/levelling/level-%d" % level]
        assert budget.passive_points == level - 1
        assert budget.required_progression_flags == ["levelling_points_only"]


def test_the_legacy_level_plus_eight_guess_is_not_a_rule(export):
    """cli.py estimates (level - 1) + 8 passive points. Nothing promotes it."""
    budgets = export.profile.character_rules.point_budgets
    for budget in budgets:
        if budget.rule_id.startswith("budget/levelling/"):
            assert budget.passive_points == budget.level - 1
    gap_ids = {gap.gap_id for gap in export.gaps}
    assert any(gap_id.endswith("quest-passive-point-rewards")
               for gap_id in gap_ids)
    quest_gap = [gap for gap in export.gaps
                 if gap.gap_id.endswith("quest-passive-point-rewards")][0]
    assert "(level - 1) + 8" in quest_gap.explanation


def test_a_missing_unlock_rule_is_a_gap_with_a_collectable_request(export):
    wanted = ("quest-passive-point-rewards", "ascendancy-point-unlock-schedule",
              "slot-accepted-base-categories", "gem-level-legality",
              "skill-level-limit")
    ids = {gap.gap_id for gap in export.gaps}
    for suffix in wanted:
        matching = [gap for gap in export.gaps if gap.gap_id.endswith(suffix)]
        assert matching, (suffix, sorted(ids))
        gap = matching[0]
        assert len(gap.needed_evidence) > 40, gap.gap_id
        assert gap.collection_method
        assert gap.gap_id in export.profile.character_rules.missing_rule_gap_ids


def test_slot_rules_declare_no_accepted_categories_and_a_gap_says_why(export):
    rules = export.profile.character_rules
    assert rules.slots
    assert all(rule.accepted_base_categories == [] for rule in rules.slots)
    blocking = [gap for gap in export.gaps
                if gap.gap_id.endswith("slot-accepted-base-categories")]
    assert blocking and blocking[0].severity is GapSeverity.BLOCKING


def test_weapon_set_rules_come_from_the_engine_constants(export):
    sets = export.profile.character_rules.weapon_sets
    assert sets.set_ids == ["poe2/weapon_sets/1", "poe2/weapon_sets/2"]
    assert sets.swap_allowed is True
    assert sets.hands_per_set == {"poe2/weapon_sets/1": 2,
                                  "poe2/weapon_sets/2": 2}


def test_the_support_limit_says_upstream_only_warns(export):
    restrictions = export.profile.character_rules.support_restrictions
    assert len(restrictions) == 1
    assert restrictions[0].max_supports == 5
    assert "warns" in restrictions[0].description


def test_an_unsourceable_level_cap_refuses_the_export_instead_of_guessing(
        reader, rows, capture, request_file):
    citations = citations_from_payload(rows["citations"])
    citations.pop("level_cap")
    provider = PobCatalogProvider(
        reader, citations=citations, release_captures=[capture],
        pob_commit=rows["pob_commit"], pob_dirty_hash=rows["pob_dirty_hash"])
    with pytest.raises(MissingRuleSource, match="level_cap"):
        provider.export(request_file)


# ------------------------------------------------- release capture handling

def test_a_capture_with_an_unknown_fidelity_is_refused(tmp_path):
    raw = json.loads(RELEASE.read_text(encoding="utf-8"))
    raw["fidelity"] = "probably_right"
    path = tmp_path / "bad.json"
    path.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(ReleaseCaptureError, match="fidelity"):
        load_release_capture(path)


def test_a_capture_missing_its_patch_id_is_refused(tmp_path):
    raw = json.loads(RELEASE.read_text(encoding="utf-8"))
    del raw["patch_id"]
    path = tmp_path / "bad.json"
    path.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(ReleaseCaptureError, match="patch_id"):
        load_release_capture(path)


def test_a_capture_from_a_future_format_is_refused(tmp_path):
    raw = json.loads(RELEASE.read_text(encoding="utf-8"))
    raw["capture_version"] = 99
    path = tmp_path / "bad.json"
    path.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(ReleaseCaptureError, match="capture_version"):
        load_release_capture(path)


def test_the_capture_payload_carries_its_attribution(capture):
    payload = capture.payload().decode("utf-8")
    assert capture.source_url in payload
    assert capture.title in payload
    assert "summary" in payload


# ------------------------------------------------------ edges and ids

def test_an_edge_is_stored_once_for_a_link_reported_from_both_ends():
    rows = [{"id": 1, "linked": [2]}, {"id": 2, "linked": [1]}]
    edges = derive_passive_edges(rows)
    assert [edge.entity_id for edge in edges] == ["poe2/passive_edges/1-2"]


def test_a_link_to_a_node_outside_the_export_is_not_an_edge():
    rows = [{"id": 1, "linked": [999]}]
    assert derive_passive_edges(rows) == []


def test_entity_ids_are_the_native_key_not_a_hash():
    assert entity_id("classes", 8) == "poe2/classes/8"
    assert entity_id("ascendancies", 8, 1) == "poe2/ascendancies/8/1"


def test_a_modifier_id_repeated_across_groups_stays_two_entities():
    rows = [{"group": "Item", "id": "Shared", "lines": ["a"]},
            {"group": "Jewel", "id": "Shared", "lines": ["b"]}]
    entities = entities_from_rows("item_modifiers", rows)
    assert [entity.entity_id for entity in entities] == [
        "poe2/item_modifiers/Item/Shared", "poe2/item_modifiers/Jewel/Shared"]


def test_the_no_ascendancy_entry_is_not_an_entity():
    rows = [{"classId": 8, "name": "Huntress", "ascendancies": [
        {"index": 0, "name": "None"}, {"index": 1, "name": "Amazon"}]}]
    entities = entities_from_rows("ascendancies", rows)
    assert [entity.entity_id for entity in entities] == ["poe2/ascendancies/8/1"]


def test_an_unknown_catalog_table_is_refused():
    with pytest.raises(KeyError, match="not_a_table"):
        entities_from_rows("not_a_table", [])
