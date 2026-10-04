"""Snapshot and cache boundaries (P01-T04).

The acceptance cases:

* each of patch, catalog, engine, calibration, rotation, scenario, registry,
  fidelity and seed forces a miss;
* source popularity alone does not change a combat result;
* a run stays readable after its corpus is changed or disconnected;
* legacy phase output is readable history and never cache-eligible.
"""

from __future__ import annotations

import json
import shutil
from dataclasses import replace
from pathlib import Path

import pytest

from record_fixtures import blob_payloads, records

from pob2opt.domain import (
    DEPENDENCY_FIELDS,
    EvaluationKey,
    build_hash,
    document_hash,
    manifest_hash,
    rotation_hash,
    scenario_hash,
)
from pob2opt.domain.cache import AggregateKey
from pob2opt.domain.enums import CacheOutcome, CacheReason, Fidelity
from pob2opt.storage import (
    BlobNotFound,
    LegacyArtifact,
    RunBundle,
    RunStore,
    import_legacy_run,
    iter_legacy_imports,
    load_legacy_phase,
    reject_as_checkpoint,
)

R = records()
PAYLOADS = blob_payloads()
SOURCE_PAYLOAD = PAYLOADS[R["source_document"].blob_hash]
MANIFEST = R["run_manifest"]


def key(**overrides) -> EvaluationKey:
    base = EvaluationKey.from_manifest(
        MANIFEST,
        build_hash=R["build_spec"].build_hash,
        rotation_hash=rotation_hash(R["rotation_policy"]),
        scenario_hash=scenario_hash(R["scenario_spec"]),
        fidelity=Fidelity.DETAILED,
    )
    return replace(base, **overrides) if overrides else base


@pytest.fixture
def store(tmp_path: Path) -> RunStore:
    with RunStore.open(tmp_path / "run") as opened:
        yield opened


# ---------------------------------------------------- every dependency counts

def test_the_key_lists_every_dependency_architecture_names():
    named = {field for fields in DEPENDENCY_FIELDS.values() for field in fields}
    assert named <= set(key().identity())
    assert set(key().identity()) == {
        "build_hash", "rotation_hash", "scenario_hash", "patch_profile_hash",
        "catalog_hash", "pob_commit", "pob_dirty_hash", "adapter_version",
        "mechanics_registry_hash", "calibration_hash", "evaluator_version",
        "fidelity", "seed",
    }


CHANGES = {
    "patch": {"patch_profile_hash": "f" * 64},
    "catalog": {"catalog_hash": "e" * 64},
    "engine": {"pob_commit": "1" * 40},
    "engine_dirty_tree": {"pob_dirty_hash": "d" * 64},
    "calibration": {"calibration_hash": "c" * 64},
    "rotation": {"rotation_hash": "b" * 64},
    "scenario": {"scenario_hash": "a" * 64},
    "registry": {"mechanics_registry_hash": "9" * 64},
    "fidelity": {"fidelity": Fidelity.SCREEN},
    "seed": {"seed": 7},
    "adapter": {"adapter_version": "fixture-adapter-0.2"},
    "evaluator": {"evaluator_version": "fixture-evaluator-0.2"},
    "build": {"build_hash": "8" * 64},
}


@pytest.mark.parametrize("dependency", sorted(CHANGES))
def test_changing_any_dependency_changes_the_cache_key(dependency: str):
    assert key(**CHANGES[dependency]).cache_key() != key().cache_key()


def test_every_named_dependency_has_a_change_case():
    assert set(DEPENDENCY_FIELDS) <= set(CHANGES)


def test_the_same_inputs_always_produce_the_same_key():
    assert key().cache_key() == key().cache_key()
    assert len(key().cache_key()) == 64


def test_the_aggregate_key_adds_objective_and_baselines():
    base = AggregateKey.from_manifest(
        MANIFEST, build_hash=R["build_spec"].build_hash,
        rotation_hash=rotation_hash(R["rotation_policy"]))
    assert "objective_hash" in base.identity()
    assert "baseline_suite_hash" in base.identity()
    assert replace(base, objective_hash="7" * 64).cache_key() != base.cache_key()
    assert replace(base, baseline_suite_hash="6" * 64).cache_key() != \
        base.cache_key()
    # Seed and fidelity are not aggregate inputs; the evaluations carry them.
    assert "seed" not in base.identity()


# ------------------------------------------------------- lookups and reasons

def test_an_empty_cache_misses_with_a_recorded_reason(store: RunStore):
    decision = store.lookup(key(), run_id="fixture-run-1")
    assert decision.outcome is CacheOutcome.MISS
    assert decision.reason is CacheReason.NO_ENTRY
    recorded = store.cache_decisions(decision.cache_key)
    assert [d["reason"] for d in recorded] == ["no_entry"]


def test_a_stored_result_hits_and_the_reason_is_recorded(store: RunStore):
    result = replace(R["evaluation_result"], cache_key=key().cache_key())
    store.commit_evaluation(None, result)
    decision = store.lookup(key())
    assert decision.is_hit
    assert decision.reason is CacheReason.EXACT_MATCH
    assert decision.evaluation_id == "fixture-evaluation-1"


def test_a_screen_result_cannot_answer_a_detailed_request(store: RunStore):
    screen = key(fidelity=Fidelity.SCREEN)
    stored = replace(R["evaluation_result"], cache_key=screen.cache_key(),
                     fidelity=Fidelity.SCREEN,
                     metrics=replace(R["evaluation_result"].metrics,
                                     completion_time_s=None))
    store.commit_evaluation(None, stored)

    decision = store.lookup(key())
    assert decision.outcome is CacheOutcome.MISS
    assert decision.reason is CacheReason.FIDELITY_INSUFFICIENT
    assert decision.rejected_cache_key == screen.cache_key()
    assert "detailed" in decision.detail

    # The screen request itself still hits its own entry.
    assert store.lookup(screen).is_hit


def test_a_legacy_entry_is_never_cache_eligible(store: RunStore):
    result = replace(R["evaluation_result"], cache_key=key().cache_key())
    store.commit_evaluation(None, result, legacy=True)
    decision = store.lookup(key())
    assert decision.outcome is CacheOutcome.MISS
    assert decision.reason is CacheReason.LEGACY_IMPORT


def test_popularity_alone_does_not_change_a_combat_result(store: RunStore):
    """Acceptance: the acquisition record changes, the evaluation does not."""
    from pob2opt.domain.records import PopularitySignal

    before = key().cache_key()
    popular = replace(R["source_document"], record_id="fixture-source-1p",
                      popularity=[PopularitySignal(kind="favourites",
                                                   value=4200.0,
                                                   observed_at="2026-10-05T00:00:00Z")])
    store.ingest_source(SOURCE_PAYLOAD, R["source_document"])
    store.ingest_source(SOURCE_PAYLOAD, popular)
    assert build_hash(R["build_spec"]) == R["build_spec"].build_hash
    assert key().cache_key() == before
    # Two acquisition records, one payload.
    assert len(store.source_history("fixture_provider", "FX-1")) == 2
    assert store.conn.execute("SELECT COUNT(*) FROM blob").fetchone()[0] == 1


def test_listing_price_changes_the_snapshot_not_the_combat_key(store: RunStore):
    from pob2opt.domain import listing_snapshot_hash

    cheap = R["listing"]
    expensive = replace(cheap, record_id="fixture-listing-2",
                        listing_id="fixture-listing-2", price_amount="1000",
                        price_currency="fixture-divine")
    assert listing_snapshot_hash(cheap) != listing_snapshot_hash(expensive)
    assert key().cache_key() == key().cache_key()


# ------------------------------------------------------------- run bundles

def _bundle(tmp_path: Path) -> RunBundle:
    return RunBundle.create(tmp_path / "runs" / MANIFEST.run_id, MANIFEST)


def test_a_bundle_has_the_layout_architecture_specifies(tmp_path: Path):
    with _bundle(tmp_path) as bundle:
        root = bundle.root
        for relative in ("manifest.json", "run.sqlite", "blobs",
                         "artifacts/candidates", "artifacts/exports",
                         "artifacts/traces"):
            assert (root / relative).exists(), relative
        assert bundle.manifest_hash == manifest_hash(MANIFEST)
        assert bundle.candidate_path("abc").parent.name == "candidates"
        assert bundle.trace_path("e1").suffix == ".jsonl"


def test_creating_a_bundle_twice_in_one_directory_is_refused(tmp_path: Path):
    from pob2opt.storage import StorageError

    with _bundle(tmp_path):
        pass
    with pytest.raises(StorageError, match="already holds"):
        _bundle(tmp_path)


def test_a_run_stays_readable_after_its_corpus_is_disconnected(tmp_path: Path):
    corpus_root = tmp_path / "corpus"
    with RunStore.open_corpus(corpus_root) as corpus:
        corpus.ingest_source(SOURCE_PAYLOAD, R["source_document"])
        corpus.put_normalized(R["game_catalog"])
        corpus.put_normalized(R["item_instance"])
        corpus.put_normalized(R["build_spec"])

    with RunStore.open_corpus(corpus_root) as corpus, _bundle(tmp_path) as bundle:
        report = bundle.copy_references(
            corpus,
            source_ids=["fixture-source-1"],
            normalized_ids=["fixture-catalog-1", "fixture-item-1",
                            "fixture-build-1"])
        assert report.sources == ("fixture-source-1",)
        assert len(report.normalized) == 3
        assert report.blobs == (R["source_document"].blob_hash,)

    # The corpus is deleted entirely.
    shutil.rmtree(corpus_root)

    with RunBundle.open(tmp_path / "runs" / MANIFEST.run_id) as reopened:
        check = reopened.self_check()
        assert check["readable"] is True
        assert check["missing_blobs"] == [] and check["missing_records"] == []
        assert reopened.store.read_payload(
            R["source_document"].blob_hash) == SOURCE_PAYLOAD
        assert reopened.store.get_normalized("fixture-build-1") == R["build_spec"]
        assert reopened.declared_references()["normalized"] == [
            "fixture-build-1", "fixture-catalog-1", "fixture-item-1"]


def test_a_bundle_reports_what_it_is_missing_rather_than_guessing(tmp_path: Path):
    with _bundle(tmp_path) as bundle:
        bundle.store.add_run_references(bundle.run_id, "blob", ["0" * 64])
        bundle.store.add_run_references(bundle.run_id, "source", ["fixture-gone"])
        check = bundle.self_check()
        assert check["readable"] is False
        assert check["missing_blobs"] == ["0" * 64]
        assert check["missing_records"] == ["fixture-gone"]


def test_reading_a_payload_the_bundle_never_copied_is_a_typed_error(tmp_path):
    with _bundle(tmp_path) as bundle:
        with pytest.raises(BlobNotFound):
            bundle.store.read_payload("0" * 64)


# ----------------------------------------------------------------- legacy

def _legacy_run(tmp_path: Path) -> Path:
    """A directory shaped like the pre-specification phase pipeline's output."""
    root = tmp_path / "legacy" / "l28"
    root.mkdir(parents=True)
    (root / "gems.json").write_text(json.dumps(
        [{"gem": "SYNTHETIC Gem", "dps": 1234.0}], indent=1), encoding="utf-8")
    (root / "finals.json").write_text(json.dumps(
        [{"build": "SYNTHETIC", "dps": 5678.0}], indent=1), encoding="utf-8")
    (root / "notes.txt").write_text("not a phase file", encoding="utf-8")
    return root


def test_legacy_phase_output_is_imported_labelled_and_not_cache_eligible(
        store: RunStore, tmp_path: Path):
    imports = import_legacy_run(store, _legacy_run(tmp_path))
    assert sorted(i.phase for i in imports) == ["finals", "gems"]
    for item in imports:
        assert item.cache_eligible is False
        assert "not cache-eligible" in item.note
        assert store.read_payload(item.blob_hash)

    rows = list(iter_legacy_imports(store))
    assert len(rows) == 2
    assert all(row["note"] == imports[0].note for row in rows)


def test_a_legacy_import_has_no_switch_that_makes_it_eligible(
        store: RunStore, tmp_path: Path):
    from pob2opt.storage.legacy import LegacyPhaseImport

    item = load_legacy_phase(store, _legacy_run(tmp_path) / "gems.json")
    # A read-only property, not a field: there is no constructor argument and
    # no assignment that turns a legacy import into a reusable evaluation.
    attribute = LegacyPhaseImport.cache_eligible
    assert isinstance(attribute, property) and attribute.fset is None
    assert "cache_eligible" not in LegacyPhaseImport.__dataclass_fields__
    with pytest.raises((AttributeError, TypeError)):
        item.cache_eligible = True  # type: ignore[misc]


def test_a_phase_file_is_refused_where_a_checkpoint_is_expected(tmp_path: Path):
    root = _legacy_run(tmp_path)
    with pytest.raises(LegacyArtifact):
        reject_as_checkpoint(root / "gems.json")
    # A real checkpoint path passes the guard untouched.
    assert reject_as_checkpoint(root.parent / "checkpoint.json") is None


def test_importing_the_same_legacy_file_twice_reuses_its_blob(
        store: RunStore, tmp_path: Path):
    root = _legacy_run(tmp_path)
    first = load_legacy_phase(store, root / "gems.json")
    second = load_legacy_phase(store, root / "gems.json")
    assert first.blob_hash == second.blob_hash == document_hash(
        (root / "gems.json").read_bytes())
    assert len(list(iter_legacy_imports(store))) == 1
