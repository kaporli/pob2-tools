"""Storage and snapshot regressions for review findings R06–R08."""
from dataclasses import replace

import pytest

import record_fixtures as fixtures
from pob2opt.domain import validate_record
from pob2opt.domain.cache import decide
from pob2opt.domain.enums import CacheReason
from pob2opt.domain.validation import NAMESPACES, RecordInvalid
from pob2opt.storage import RunBundle, RunStore
from pob2opt.storage.errors import CacheKeyConflict, DuplicateRecord
from pob2opt.storage.runbundle import _CorpusLookup


def test_wrong_source_kind_is_rejected_and_staged_bundle_is_not_ready(tmp_path):
    manifest = fixtures.records()["run_manifest"]
    with RunBundle.create(tmp_path, manifest) as bundle:
        records = fixtures.seed_corpus(bundle.store, with_results=False)
        wrong = replace(records["build_spec"], record_id="wrong-source-kind",
                        source_document_ids=[records["acquisition_result"].record_id])
        with pytest.raises(RecordInvalid) as error:
            bundle.store.put_normalized(wrong)
        assert "/source_document_ids/0" in error.value.report.paths()
        assert not bundle.store.has_record(wrong.record_id)
        bundle.store.put_normalized(wrong, require_references=False)
        check = bundle.self_check()
        assert not check["readable"]
        assert "/source_document_ids/0" in check["unresolved_references"][wrong.record_id]


def test_namespace_agreement_across_memory_sql_pending_and_copy(tmp_path):
    with RunStore.open(tmp_path) as store:
        fixtures.seed_corpus(store)
        memory = store.record_index()
        sql = store.reference_index()
        pending = store.reference_index([r for _, _, r in store.iter_stored()])
        lookup = _CorpusLookup(store)
        values = {v for name in NAMESPACES for v in getattr(memory, name)}
        values.add("missing-id")
        for namespace in (*NAMESPACES, "any_record"):
            for value in values:
                expected = memory.contains(namespace, value)
                assert sql.contains(namespace, value) == expected, (namespace, value)
                assert pending.contains(namespace, value) == expected, (namespace, value)
                # The walker handles actual blob bytes separately from rows.
                if namespace == "blob_hashes" or value in memory.blob_hashes:
                    continue
                assert (lookup.locate(namespace, value) is not None) == expected, (namespace, value)


@pytest.mark.parametrize("listing_first", [False, True])
def test_snapshot_is_independent_of_batch_order_and_corpus(tmp_path, monkeypatch, listing_first):
    if listing_first:
        monkeypatch.setattr(fixtures, "CORE_BATCH", ("listing",) + tuple(
            kind for kind in fixtures.CORE_BATCH if kind != "listing"))
    corpus_path = tmp_path / "corpus"
    bundle_path = tmp_path / "bundle"
    with RunStore.open(corpus_path) as corpus:
        records = fixtures.seed_corpus(corpus, with_results=False)
        with RunBundle.create(bundle_path, records["run_manifest"]) as bundle:
            report = bundle.copy_references(corpus, normalized_ids=[
                records["build_spec"].record_id, records["scenario_spec"].record_id])
            assert report.complete
            assert bundle.store.has_record(records["item_instance"].record_id)
            bundle.require_readable()
    corpus_path.rename(tmp_path / "disconnected-corpus")
    with RunBundle.open(bundle_path) as bundle:
        bundle.require_readable()
        assert bundle.store.get_normalized(records["item_instance"].record_id) == records["item_instance"]


def test_missing_transitive_target_is_reported(tmp_path):
    with RunStore.open(tmp_path / "corpus") as corpus:
        records = fixtures.seed_corpus(corpus, with_results=False)
        wrong = replace(records["build_spec"], record_id="missing-source",
                        source_document_ids=["source-not-acquired"])
        corpus.put_normalized(wrong, require_references=False)
        with RunBundle.create(tmp_path / "bundle", records["run_manifest"]) as bundle:
            report = bundle.copy_references(corpus, normalized_ids=[wrong.record_id])
            assert not report.complete
            assert "source-not-acquired" in report.unresolved["source_document_ids"]
            assert not bundle.self_check()["readable"]


def test_evidence_union_can_reference_blob_bytes_directly(tmp_path):
    with RunStore.open(tmp_path / "corpus") as corpus:
        records = fixtures.seed_corpus(corpus, with_results=False)
        blob = corpus.blobs.put(b"independent synthetic evidence")
        build = replace(records["build_spec"], record_id="blob-evidence-build",
                        provenance_ids=[blob.blob_hash])
        corpus.put_normalized(build)
        with RunBundle.create(tmp_path / "bundle", records["run_manifest"]) as bundle:
            report = bundle.copy_references(corpus, normalized_ids=[
                build.record_id, records["scenario_spec"].record_id])
            assert report.complete
            assert bundle.store.read_payload(blob.blob_hash) == b"independent synthetic evidence"
            bundle.require_readable()


@pytest.mark.parametrize("seed_kind", ["aggregate_result", "scenario_spec"])
@pytest.mark.parametrize("legacy", [False, True])
def test_evaluation_dependencies_copy_idempotently_without_tasks(tmp_path, seed_kind, legacy):
    corpus_path = tmp_path / "corpus"
    bundle_path = tmp_path / "bundle"
    with RunStore.open(corpus_path) as corpus:
        records = fixtures.seed_corpus(corpus, with_results=False)
        evaluation = records["evaluation_result"]
        corpus.commit_evaluation(None, evaluation, legacy=legacy)
        if seed_kind == "scenario_spec":
            seed = replace(records[seed_kind], record_id="reference-scenario",
                           scenario_id="reference-scenario",
                           reference_result_id=evaluation.evaluation_id)
        else:
            seed = records[seed_kind]
        corpus.put_normalized(seed)
        with RunBundle.create(bundle_path, records["run_manifest"]) as bundle:
            for _ in range(2):
                report = bundle.copy_references(corpus, normalized_ids=[seed.record_id])
                assert report.complete
                bundle.require_readable()
            assert bundle.store.conn.execute("SELECT COUNT(*) FROM evaluation").fetchone()[0] == 1
            assert bundle.store.conn.execute("SELECT COUNT(*) FROM task").fetchone()[0] == 0
            assert bundle.store.get_record(evaluation.evaluation_id) == evaluation
    corpus_path.rename(tmp_path / "disconnected-corpus")
    with RunBundle.open(bundle_path) as bundle:
        bundle.require_readable()
        assert bundle.store.is_legacy_evaluation(evaluation.cache_key) == legacy

        class RequestKey:
            def cache_key(self):
                return evaluation.cache_key

        decision = decide(RequestKey(), bundle.store.evaluation_by_cache_key,
                          legacy=bundle.store.is_legacy_evaluation)
        assert decision.is_hit == (not legacy)
        if legacy:
            assert decision.reason is CacheReason.LEGACY_IMPORT


@pytest.mark.parametrize("conflict", ["cache_key", "payload", "identity", "legacy"])
def test_batch_evaluation_conflicts_roll_back_other_records(tmp_path, conflict):
    with RunStore.open(tmp_path) as store:
        records = fixtures.seed_corpus(store)
        evaluation = records["evaluation_result"]
        options = {}
        if conflict == "cache_key":
            incoming = replace(evaluation, record_id="other-evaluation",
                               evaluation_id="other-evaluation")
            expected = CacheKeyConflict
        elif conflict == "payload":
            incoming = replace(evaluation, seed=evaluation.seed + 1)
            expected = DuplicateRecord
        elif conflict == "identity":
            incoming = replace(evaluation, cache_key="a" * 64)
            expected = DuplicateRecord
        else:
            incoming = evaluation
            options["legacy_evaluation_ids"] = [evaluation.evaluation_id]
            expected = DuplicateRecord
        extra = replace(records["item_instance"], record_id="rolled-back-item")
        with pytest.raises(expected):
            store.import_batch([extra, incoming], **options)
        assert not store.has_record(extra.record_id)
        assert store.get_record(evaluation.evaluation_id) == evaluation
        assert not store.is_legacy_evaluation(evaluation.cache_key)


def test_cyclic_gap_and_evaluation_import_as_one_batch(tmp_path):
    with RunStore.open(tmp_path) as store:
        records = fixtures.seed_corpus(store, with_results=False)
        evaluation = records["evaluation_result"]
        gap = replace(records["data_gap"], record_id="evaluation-gap", gap_id="evaluation-gap",
                      affected_evaluation_ids=[evaluation.evaluation_id])
        evaluation = replace(evaluation, gap_ids=[gap.gap_id])
        store.import_batch([evaluation, gap])
        assert not store.unresolved_references()
