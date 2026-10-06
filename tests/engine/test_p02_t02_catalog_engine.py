"""P02-T02 against the real PoB engine.

What only the engine can establish:

* the typed Lua catalog operations enumerate the live tables, page stably,
  and refuse an unknown table instead of guessing a handler;
* a catalog read does not disturb an evaluation sharing the same worker;
* the behaviour half of the compatibility fixture set actually runs, so the
  verdict is not `unknown` for want of an engine;
* a build PoB itself saved resolves completely against the export;
* replaying the captured rows offline reproduces the live catalog hash, so
  the offline lane is the same export and not a second implementation.

One adapter serves the whole module: a boot costs real time.
"""

from __future__ import annotations

import dataclasses
import json
import os
from pathlib import Path

import pytest

from record_fixtures import records

from pob2opt.catalog import (EngineCatalogReader, ExportRequest,
                             MappingCatalogReader, PobCatalogProvider,
                             catalog_hash, compatibility_fixtures,
                             evaluation_context_hash, load_release_capture,
                             resolve_build_document)
from pob2opt.catalog.compatibility import MATCH, UNCHECKED
from pob2opt.catalog.sources import (citations_from_payload,
                                     citations_to_payload, read_citations)
from pob2opt.domain.enums import Compatibility, Fidelity
from pob2opt.evaluation import (ADAPTER_VERSION, BuildDocument, EngineAdapter,
                                EngineState, EngineUnsupported, protocol,
                                pob_worker_spec, resolve_checkout)
from pob2opt.domain.validation import RecordIndex, validate_record

pytestmark = pytest.mark.engine

REPO_ROOT = Path(__file__).resolve().parents[2]
EVIDENCE = REPO_ROOT / "docs" / "evidence" / "P02"
RELEASE = EVIDENCE / "release" / "poe2-0.5.5e.json"
SAMPLE_BUILD = EVIDENCE / "sample-build-ranger-quarterstaff.xml"

START_TIMEOUT_S = 600.0
REQUEST_TIMEOUT_S = 300.0


@pytest.fixture(scope="module")
def adapter(pob_root: Path):
    live = EngineAdapter(pob_worker_spec(pob_root),
                         screen_timeout_s=REQUEST_TIMEOUT_S,
                         detailed_timeout_s=REQUEST_TIMEOUT_S,
                         start_timeout_s=START_TIMEOUT_S)
    try:
        yield live
    finally:
        live.close()


@pytest.fixture(scope="module")
def reader(adapter):
    return EngineCatalogReader(adapter, timeout_s=REQUEST_TIMEOUT_S)


@pytest.fixture(scope="module")
def checkout(pob_root: Path):
    return resolve_checkout(pob_root)


@pytest.fixture(scope="module")
def cwd_before_export():
    """Where the coordinator was before any catalog read.

    Not the repository root: other engine modules in the same session use
    the raw ``Pob2Engine``, which relocates this process. The claim under
    test is that the catalog read does not move it, so the baseline is
    wherever this module found it.
    """
    return os.getcwd()


@pytest.fixture(scope="module")
def live_export(adapter, reader, pob_root: Path, checkout, cwd_before_export):
    def behaviour(fixture):
        document = BuildDocument(build_hash="compat/%s" % fixture["fixture_id"],
                                 xml=fixture["document"])
        state = EngineState(stat_keys=tuple(sorted(fixture.get("expected") or {})))
        return adapter.probe(document, state, timeout_s=REQUEST_TIMEOUT_S)

    provider = PobCatalogProvider(
        reader, citations=read_citations(pob_root),
        release_captures=[load_release_capture(RELEASE)],
        pob_commit=checkout.commit, pob_dirty_hash=checkout.dirty_hash,
        behaviour=behaviour)
    return provider.export(ExportRequest())


# --------------------------------------------------- the bridge operations

def test_every_catalog_table_pages_to_a_stable_total(reader, adapter):
    for table in protocol.CATALOG_HANDLERS:
        first = adapter.catalog_page(table, 0, 5, timeout_s=REQUEST_TIMEOUT_S)
        again = adapter.catalog_page(table, 0, 5, timeout_s=REQUEST_TIMEOUT_S)
        assert first["rows"] == again["rows"], table
        assert first["total"] >= len(first["rows"])
        rows = reader.rows(table)
        assert len(rows) == first["total"], table
        assert rows[:5] == first["rows"], table


def test_paging_covers_every_row_exactly_once(adapter):
    whole = adapter.catalog_rows("classes", page_rows=3,
                                 timeout_s=REQUEST_TIMEOUT_S)
    single = adapter.catalog_page("classes", 0, 1000,
                                  timeout_s=REQUEST_TIMEOUT_S)["rows"]
    assert whole == single
    assert len({row["classId"] for row in whole}) == len(whole)


def test_an_unknown_catalog_table_is_unsupported_not_a_guess(adapter):
    with pytest.raises(EngineUnsupported, match="unknown catalog table"):
        adapter.catalog_page("not_a_table", timeout_s=REQUEST_TIMEOUT_S)
    # The worker survives an unsupported request.
    assert adapter.catalog_page("classes", 0, 1,
                                timeout_s=REQUEST_TIMEOUT_S)["total"] == 8


def test_a_catalog_read_does_not_disturb_a_loaded_build(adapter, pob_root):
    build = dataclasses.replace(records()["build_spec"],
                                build_hash="p02t02-engine-fixture")
    profile = dataclasses.replace(records()["patch_profile"],
                                  pob_commit=resolve_checkout(pob_root).commit,
                                  adapter_version=ADAPTER_VERSION)
    document = BuildDocument(build_hash=build.build_hash,
                             xml=SAMPLE_BUILD.read_text(encoding="utf-8"))
    before = adapter.primitives(build, EngineState(), profile,
                                fidelity=Fidelity.DETAILED, document=document)
    adapter.catalog_page("gems", 0, 10, timeout_s=REQUEST_TIMEOUT_S)
    after = adapter.primitives(build, EngineState(), profile,
                               fidelity=Fidelity.DETAILED, document=document)
    assert after.document.reloaded is False
    assert after.loaded == before.loaded
    assert after.values == before.values


# ------------------------------------------------------ the export itself

def test_the_live_export_validates_and_names_its_catalog(live_export):
    assert live_export.validation_errors == []
    index = RecordIndex()
    for record in live_export.records:
        index.add(record)
    for digest in live_export.blobs:
        index.add_blob(digest)
    for record in live_export.records:
        assert validate_record(record, index=index).ok, record.record_id
    counts = {table: len(rows)
              for table, rows in live_export.catalog.entities.items()}
    assert counts["classes"] == 8
    assert counts["passive_nodes"] > 4000
    assert counts["passive_edges"] > 4000
    assert counts["gems"] > 800
    assert counts["item_modifiers"] > 7000
    assert counts["config_variables"] > 450


def test_the_behaviour_fixtures_actually_ran(live_export):
    behaviour = [o for o in live_export.report.outcomes if o.kind == "behaviour"]
    assert behaviour
    for outcome in behaviour:
        assert outcome.outcome == MATCH, outcome.detail
        assert outcome.observed


def test_no_fixture_is_unchecked_against_a_real_engine(live_export):
    unchecked = [o.fixture_id for o in live_export.report.outcomes
                 if o.outcome == UNCHECKED]
    assert unchecked == []


def test_the_live_verdict_is_never_verified_on_this_checkout(live_export):
    """A summary capture and an engine older than the live patch."""
    assert live_export.profile.compatibility is Compatibility.PARTIAL
    reasons = " ".join(live_export.report.reasons)
    assert "predates" in reasons
    assert "summary" in reasons


def test_a_build_pob_saved_resolves_completely(live_export):
    resolution = resolve_build_document(
        SAMPLE_BUILD.read_text(encoding="utf-8"),
        live_export.catalog.entities)
    assert resolution.unresolved == []
    assert resolution.ambiguous == []
    assert resolution.counts["passive_node"] >= 30


def test_duplicate_display_names_survive_as_distinct_entities(live_export):
    for table in ("gems", "passive_nodes"):
        by_name: dict[str, set[str]] = {}
        for entity in live_export.catalog.entities[table]:
            for name in entity.display_names:
                by_name.setdefault(name, set()).add(entity.entity_id)
        repeated = {name: ids for name, ids in by_name.items() if len(ids) > 1}
        assert repeated, table
        for name, ids in repeated.items():
            assert len(ids) > 1, (table, name)


def test_a_replay_of_the_captured_rows_reproduces_the_live_catalog_hash(
        reader, live_export, checkout, pob_root):
    rows = {table: reader.rows(table) for table in protocol.CATALOG_HANDLERS}
    payload = json.loads(json.dumps({
        "tables": rows,
        "rule_sources": reader.rule_sources(),
        "citations": citations_to_payload(read_citations(pob_root)),
    }))
    replay = PobCatalogProvider(
        MappingCatalogReader(payload["tables"], payload["rule_sources"]),
        citations=citations_from_payload(payload["citations"]),
        release_captures=[load_release_capture(RELEASE)],
        pob_commit=checkout.commit, pob_dirty_hash=checkout.dirty_hash,
        adapter_version=ADAPTER_VERSION).export(ExportRequest())
    assert replay.catalog.catalog_hash == live_export.catalog.catalog_hash
    # The replay has no engine, so the behaviour half is unchecked and the
    # verdict falls back to unknown rather than inheriting the live one.
    assert replay.profile.compatibility is Compatibility.UNKNOWN
    # Same catalog, same commit, and still a different context: the verdict
    # is part of the identity, so a result cached under a partial profile is
    # not served for an unknown one.
    assert (evaluation_context_hash(replay.profile)
            != evaluation_context_hash(live_export.profile))
    assert (dataclasses.replace(replay.profile,
                                compatibility=live_export.profile.compatibility)
            .catalog_hash == live_export.profile.catalog_hash)
    assert (evaluation_context_hash(dataclasses.replace(
        replay.profile, compatibility=live_export.profile.compatibility))
        == evaluation_context_hash(live_export.profile))


def test_changing_the_upstream_commit_changes_the_context(live_export):
    moved = dataclasses.replace(live_export.profile, pob_commit="0" * 40)
    assert (evaluation_context_hash(moved)
            != evaluation_context_hash(live_export.profile))


def test_the_catalog_hash_covers_the_whole_entity_set(live_export):
    entities = dict(live_export.catalog.entities)
    assert catalog_hash(entities) == live_export.catalog.catalog_hash
    entities["classes"] = entities["classes"][:-1]
    assert catalog_hash(entities) != live_export.catalog.catalog_hash


def test_the_shipped_fixture_set_was_recorded_from_this_checkout(checkout):
    recorded = compatibility_fixtures()["recorded_from"]
    assert recorded["pob_commit"] == checkout.commit, (
        "the fixture set was recorded from a different checkout; re-record it "
        "deliberately rather than editing expectations to match")


def test_the_parent_working_directory_did_not_move(live_export,
                                                   cwd_before_export):
    assert os.getcwd() == cwd_before_export
