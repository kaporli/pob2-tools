"""Immutable storage, blobs and migrations (P01-T03).

The acceptance cases, each with its own test below:

* identical bytes ingested twice reuse one blob;
* the same external source acquired again creates a new record;
* a missing or corrupt blob raises a typed error, never wrong bytes;
* a duplicate completion message cannot create a second result;
* a fault injected between the blob write and the transaction leaves a
  recoverable orphan, not a record claiming a successful store.
"""

from __future__ import annotations

import hashlib
import sqlite3
from dataclasses import replace
from pathlib import Path

import pytest

from record_fixtures import blob_payloads, records, seed_corpus

from pob2opt.domain import document_hash, to_jsonable
from pob2opt.domain.enums import AcquisitionStatus
from pob2opt.storage import (
    BlobCorrupt,
    BlobNotFound,
    BlobStore,
    CacheKeyConflict,
    DuplicateRecord,
    MigrationHistoryChanged,
    RecordNotFound,
    RunStore,
    SchemaTooNew,
    StorageError,
    connect,
    migrate,
    open_database,
    schema_version,
)
from pob2opt.storage.migrations import (
    LATEST_VERSION,
    MIGRATIONS,
    Migration,
    applied,
)

R = records()
PAYLOADS = blob_payloads()
SOURCE_PAYLOAD = PAYLOADS[R["source_document"].blob_hash]


@pytest.fixture
def store(tmp_path: Path) -> RunStore:
    with RunStore.open(tmp_path / "corpus") as opened:
        yield opened


# ------------------------------------------------------------- migrations

def test_a_new_database_is_at_the_latest_migration(tmp_path: Path):
    conn = open_database(tmp_path / "x.sqlite")
    assert schema_version(conn) == LATEST_VERSION == 2
    assert set(applied(conn)) == {1, 2}


def test_migrating_twice_changes_nothing(tmp_path: Path):
    conn = open_database(tmp_path / "x.sqlite")
    before = applied(conn)
    assert migrate(conn, now="2026-10-04T00:00:00Z") == ()
    assert applied(conn) == before


def test_editing_an_applied_migration_is_refused(tmp_path: Path):
    conn = open_database(tmp_path / "x.sqlite")
    edited = (Migration(1, "initial", ("SELECT 1",)),) + MIGRATIONS[1:]
    with pytest.raises(MigrationHistoryChanged) as exc:
        migrate(conn, now="2026-10-04T00:00:00Z", migrations=edited)
    assert exc.value.version == 1


def test_a_v1_database_upgrades_to_v2_without_losing_tasks(tmp_path: Path):
    """Migration 2 relaxes the task index; it does not rewrite migration 1."""
    conn = connect(tmp_path / "x.sqlite")
    migrate(conn, now="2026-10-04T00:00:00Z", migrations=MIGRATIONS[:1])
    assert schema_version(conn) == 1
    conn.execute(
        "INSERT INTO task (task_id, run_id, generation_id, candidate_id,"
        " state, attempt, enqueued_at, payload) VALUES ('t1', 'r', 1, 'c',"
        " 'queued', 0, '2026-10-04T00:00:00Z', '{}')")

    assert migrate(conn, now="2026-10-05T00:00:00Z") == (2,)
    assert schema_version(conn) == 2
    row = conn.execute("SELECT task_id, context_key FROM task").fetchone()
    assert row["task_id"] == "t1"
    assert row["context_key"] == ""
    assert applied(conn)[1][1] == MIGRATIONS[0].checksum()


def test_a_database_from_a_newer_build_is_refused(tmp_path: Path):
    conn = open_database(tmp_path / "x.sqlite")  # noqa: F841
    conn.execute("INSERT INTO schema_migration (version, name, checksum,"
                 " applied_at) VALUES (99, 'future', 'x', '2030-01-01T00:00:00Z')")
    with pytest.raises(SchemaTooNew):
        migrate(conn, now="2026-10-04T00:00:00Z")


def test_foreign_keys_are_enforced(tmp_path: Path):
    conn = open_database(tmp_path / "x.sqlite")
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO source_record (record_id, kind, provider, blob_hash,"
            " created_at, json) VALUES ('r', 'source_document', 'p', ?,"
            " '2026-10-04T00:00:00Z', '{}')", ("0" * 64,))


def test_the_schema_has_no_column_per_game_stat(tmp_path: Path):
    """Payloads live in one json column; only identifiers are indexed."""
    conn = open_database(tmp_path / "x.sqlite")
    columns = {
        row["name"] for row in
        conn.execute("PRAGMA table_info(normalized_record)")
    }
    assert columns == {"record_id", "kind", "primary_hash", "catalog_hash",
                       "status", "created_at", "json"}


# ------------------------------------------------------------------ blobs

def test_identical_bytes_are_stored_once(tmp_path: Path):
    blobs = BlobStore(tmp_path / "blobs")
    first = blobs.put(SOURCE_PAYLOAD)
    mtime = first.path.stat().st_mtime_ns
    second = blobs.put(bytes(SOURCE_PAYLOAD))
    assert first.reused is False and second.reused is True
    assert second.blob_hash == first.blob_hash == document_hash(SOURCE_PAYLOAD)
    assert second.path.stat().st_mtime_ns == mtime, "the file was rewritten"
    assert list(blobs.iter_hashes()) == [first.blob_hash]


def test_a_missing_blob_is_a_typed_error(tmp_path: Path):
    blobs = BlobStore(tmp_path / "blobs")
    with pytest.raises(BlobNotFound) as exc:
        blobs.get("a" * 64)
    assert exc.value.blob_hash == "a" * 64


def test_a_corrupt_blob_is_a_typed_error_not_wrong_bytes(tmp_path: Path):
    blobs = BlobStore(tmp_path / "blobs")
    write = blobs.put(SOURCE_PAYLOAD)
    write.path.write_bytes(b"SYNTHETIC tampered content")
    with pytest.raises(BlobCorrupt) as exc:
        blobs.get(write.blob_hash)
    assert exc.value.expected == write.blob_hash
    assert exc.value.actual == hashlib.sha256(
        b"SYNTHETIC tampered content").hexdigest()


def test_blob_names_must_be_sha256(tmp_path: Path):
    blobs = BlobStore(tmp_path / "blobs")
    for bad in ("", "zz", "A" * 64, "g" * 64):
        with pytest.raises(ValueError):
            blobs.path_for(bad)


def test_an_interrupted_write_leaves_a_partial_file_not_a_blob(tmp_path: Path):
    blobs = BlobStore(tmp_path / "blobs")
    write = blobs.put(SOURCE_PAYLOAD)
    partial = write.path.with_name(write.path.name + ".partial")
    partial.write_bytes(b"half")
    assert list(blobs.iter_hashes()) == [write.blob_hash]
    assert [p.name for p in blobs.iter_incomplete()] == [partial.name]


# ---------------------------------------------------------- source records

def test_ingesting_a_source_stores_bytes_and_record(store: RunStore):
    result = store.ingest_source(SOURCE_PAYLOAD, R["source_document"])
    assert result.created is True and result.blob.reused is False
    assert store.read_payload(result.blob.blob_hash) == SOURCE_PAYLOAD
    assert store.get_source(result.record_id) == R["source_document"]


def test_ingesting_the_same_record_twice_is_a_no_op(store: RunStore):
    store.ingest_source(SOURCE_PAYLOAD, R["source_document"])
    again = store.ingest_source(SOURCE_PAYLOAD, R["source_document"])
    assert again.created is False and again.blob.reused is True
    assert store.conn.execute("SELECT COUNT(*) FROM source_record").fetchone()[0] == 1


def test_a_record_id_cannot_be_reused_for_different_content(store: RunStore):
    store.ingest_source(SOURCE_PAYLOAD, R["source_document"])
    altered = replace(R["source_document"], locale="en")
    with pytest.raises(DuplicateRecord):
        store.ingest_source(SOURCE_PAYLOAD, altered)


def test_the_same_external_source_acquired_later_is_a_new_record(store: RunStore):
    first = R["source_document"]
    store.ingest_source(SOURCE_PAYLOAD, first)

    updated_bytes = SOURCE_PAYLOAD + b"<!-- SYNTHETIC: the guide was edited -->\n"
    second = replace(
        first, record_id="fixture-source-1b",
        acquired_at="2026-10-05T12:00:00Z", created_at="2026-10-05T12:00:00Z",
        blob_hash=document_hash(updated_bytes), byte_count=len(updated_bytes))
    store.ingest_source(updated_bytes, second)

    history = store.source_history(first.provider, first.external_id)
    assert [d.record_id for d in history] == ["fixture-source-1", "fixture-source-1b"]
    assert history[0].blob_hash != history[1].blob_hash
    # The first version's bytes are still readable, unchanged.
    assert store.read_payload(history[0].blob_hash) == SOURCE_PAYLOAD


def test_a_declared_hash_that_does_not_match_the_payload_is_refused(store):
    with pytest.raises(StorageError, match="hashes to"):
        store.ingest_source(b"SYNTHETIC other bytes", R["source_document"])


def test_a_failed_acquisition_is_kept_and_stores_no_document(store: RunStore):
    failure = replace(R["acquisition_result"], record_id="fixture-acq-fail",
                      status=AcquisitionStatus.ACCESS_BLOCKED,
                      source_document_id=None, http_status=403,
                      retry_eligible=False,
                      diagnostic="SYNTHETIC: provider refused")
    assert store.put_acquisition_result(failure) is True
    assert store.get_source("fixture-acq-fail").status is \
        AcquisitionStatus.ACCESS_BLOCKED
    assert store.conn.execute(
        "SELECT COUNT(*) FROM source_record WHERE kind = 'source_document'"
    ).fetchone()[0] == 0


def test_reading_a_record_that_does_not_exist_is_typed(store: RunStore):
    with pytest.raises(RecordNotFound):
        store.get_source("fixture-missing")
    with pytest.raises(RecordNotFound):
        store.get_normalized("fixture-missing")


# ------------------------------------------------------- fault injection

def test_a_fault_between_blob_and_transaction_leaves_a_recoverable_orphan(
        store: RunStore, monkeypatch):
    """The bytes survive; nothing claims they were successfully stored."""
    def explode(*_args, **_kwargs):
        raise KeyboardInterrupt("SYNTHETIC interruption after the blob write")

    monkeypatch.setattr(store, "_insert_source_row", explode)
    with pytest.raises(KeyboardInterrupt):
        store.ingest_source(SOURCE_PAYLOAD, R["source_document"])

    blob_hash = document_hash(SOURCE_PAYLOAD)
    assert store.blobs.exists(blob_hash), "the written bytes were lost"
    assert store.blobs.get(blob_hash) == SOURCE_PAYLOAD
    assert store.orphan_blobs() == (blob_hash,)
    with pytest.raises(RecordNotFound):
        store.get_source("fixture-source-1")

    monkeypatch.undo()
    retried = store.ingest_source(SOURCE_PAYLOAD, R["source_document"])
    assert retried.created is True and retried.blob.reused is True
    assert store.orphan_blobs() == ()


def test_a_fault_inside_the_transaction_writes_no_partial_row(store: RunStore):
    """The blob row and the record row commit together or not at all."""
    store.conn.execute(
        "CREATE TRIGGER fixture_fail BEFORE INSERT ON source_record BEGIN"
        " SELECT RAISE(ABORT, 'SYNTHETIC failure mid-transaction'); END")
    with pytest.raises(sqlite3.IntegrityError, match="SYNTHETIC"):
        store.ingest_source(SOURCE_PAYLOAD, R["source_document"])
    store.conn.execute("DROP TRIGGER fixture_fail")

    assert store.conn.execute("SELECT COUNT(*) FROM blob").fetchone()[0] == 0
    assert store.conn.execute(
        "SELECT COUNT(*) FROM source_record").fetchone()[0] == 0
    assert store.orphan_blobs() == (document_hash(SOURCE_PAYLOAD),)


# ----------------------------------------------------- normalized records

def test_normalized_records_round_trip_through_sqlite(store: RunStore):
    seed_corpus(store)
    for kind in ("item_instance", "build_spec", "scenario_spec",
                 "rotation_policy", "mechanic_rule", "patch_profile"):
        assert store.get_normalized(R[kind].record_id) == R[kind]


def test_builds_are_findable_by_their_hash(store: RunStore):
    seed_corpus(store)
    found = store.find_normalized("build_spec", R["build_spec"].build_hash)
    assert [b.record_id for b in found] == ["fixture-build-1"]
    assert store.find_normalized("build_spec", "0" * 64) == []


def test_an_evaluation_result_is_not_a_normalized_record(store: RunStore):
    with pytest.raises(StorageError, match="not a normalized record kind"):
        store.put_normalized(R["evaluation_result"])


def test_an_invalid_record_never_reaches_storage(store: RunStore):
    from pob2opt.domain import RecordInvalid

    broken = replace(R["build_spec"], raw_blob_hashes=[])
    with pytest.raises(RecordInvalid):
        store.put_normalized(broken, require_references=False)
    assert store.conn.execute(
        "SELECT COUNT(*) FROM normalized_record").fetchone()[0] == 0


# ------------------------------------------------------------ evaluations

def test_evaluation_cache_keys_are_unique(store: RunStore):
    seed_corpus(store)
    clash = replace(R["evaluation_result"], record_id="fixture-evaluation-2",
                    evaluation_id="fixture-evaluation-2")
    with pytest.raises(CacheKeyConflict) as exc:
        store.commit_evaluation(None, clash)
    assert exc.value.existing_id == "fixture-evaluation-1"


def test_a_repeated_completion_message_creates_one_result(store: RunStore):
    seed_corpus(store, with_results=False)
    first = store.commit_evaluation(None, R["evaluation_result"])
    second = store.commit_evaluation(None, R["evaluation_result"])
    assert first.created is True and second.created is False
    assert store.conn.execute("SELECT COUNT(*) FROM evaluation").fetchone()[0] == 1


def test_evaluations_are_readable_by_cache_key(store: RunStore):
    seed_corpus(store)
    found = store.evaluation_by_cache_key(R["evaluation_result"].cache_key)
    assert found == R["evaluation_result"]
    assert store.evaluation_by_cache_key("0" * 64) is None


# ----------------------------------------------------- gaps, observations

def test_gaps_and_observations_are_stored_and_queryable(store: RunStore):
    seed_corpus(store)
    assert store.put_gap(R["data_gap"]) is False
    assert [g.gap_id for g in store.open_gaps("blocking")] == ["fixture-gap-1"]
    assert store.open_gaps("informational") == []

    assert store.put_observation(R["observation"]) is False
    assert store.conn.execute(
        "SELECT dataset_split FROM observation").fetchone()[0] == "holdout"


def test_the_store_index_resolves_its_own_references(store: RunStore):
    seed_corpus(store)
    index = store.record_index()
    assert R["item_instance"].item_hash in index.item_hashes
    assert R["source_document"].blob_hash in index.blob_hashes
    assert "fixture-source-1" in index.source_document_ids


def test_stored_records_can_be_revalidated_against_the_corpus(store: RunStore):
    seed_corpus(store)
    reports = store.validate_stored()
    assert len(reports) >= 15
    assert all(report.ok for report in reports.values()),         {rid: r.errors for rid, r in reports.items() if not r.ok}
    assert store.unresolved_references() == {}
