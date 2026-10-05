"""The coordinator's record store (P01-T03, P01-T04).

One class owns every write, because architecture.md gives the coordinator the
single writer. The same schema backs a corpus and a run bundle; a run is just
a store that also has a manifest, tasks and copied references.

Immutability is the rule. A record is inserted once under its ``record_id``
and never updated: re-ingesting the same external source later creates a new
record that references the same or a new blob, so the history of what a
source said and when stays readable. Re-ingesting *identical bytes* reuses
the blob rather than storing a second copy.

Payloads are stored as canonical JSON in one column with identifiers and
statuses indexed beside them. There is no column per game stat, so a new
modifier never needs a migration.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterable, Iterator, Sequence

from ..domain import (
    RECORD_TYPES,
    CacheDecision,
    EvaluationKey,
    RecordIndex,
    canonical_text,
    from_jsonable,
    manifest_hash,
    kind_of,
    to_jsonable,
    validate_record,
)
from ..domain.cache import decide as decide_cache
from ..domain.enums import TASK_TRANSITIONS, TaskState
from .blobs import BlobStore, BlobWrite
from .index import StoreIndex
from .database import open_database, transaction, utcnow
from .errors import (
    CacheKeyConflict,
    DuplicateRecord,
    RecordNotFound,
    StaleAttempt,
    StorageError,
    TaskResultMismatch,
    TaskStateError,
)

RUN_DATABASE = "run.sqlite"
CORPUS_DATABASE = "corpus.sqlite"
BLOB_DIRECTORY = "blobs"

#: Record kinds the normalized table accepts, with the column each one's
#: indexed hash comes from.
_NORMALIZED_HASHES: dict[str, str | None] = {
    "patch_profile": "catalog_hash",
    "game_catalog": "catalog_hash",
    "item_instance": "item_hash",
    "listing": "item_hash",
    "build_spec": "build_hash",
    "parse_result": None,
    "mechanic_claim": None,
    "mechanic_rule": None,
    "scenario_spec": None,
    "rotation_policy": None,
    "aggregate_result": "build_hash",
    "review_record": None,
}

_SOURCE_KINDS = ("source_document", "acquisition_result")


@dataclass(frozen=True, slots=True)
class Ingested:
    record_id: str
    blob: BlobWrite
    #: False when this record already existed, so ingestion was a no-op.
    created: bool


@dataclass(frozen=True, slots=True)
class Committed:
    evaluation_id: str
    #: False when the result was already stored, so this was a repeat message.
    created: bool


class RunStore:
    """Transactional, idempotent writes. Coordinator only."""

    def __init__(self, conn: sqlite3.Connection, blobs: BlobStore, *,
                 root: Path | None = None,
                 clock: Callable[[], str] = utcnow) -> None:
        self.conn = conn
        self.blobs = blobs
        self.root = root
        self.clock = clock

    # -- lifecycle ---------------------------------------------------------

    @classmethod
    def open(cls, root: Path | str, *, database: str = RUN_DATABASE,
             clock: Callable[[], str] = utcnow) -> "RunStore":
        root = Path(root)
        root.mkdir(parents=True, exist_ok=True)
        conn = open_database(root / database, clock=clock)
        return cls(conn, BlobStore(root / BLOB_DIRECTORY), root=root, clock=clock)

    @classmethod
    def open_corpus(cls, root: Path | str, *,
                    clock: Callable[[], str] = utcnow) -> "RunStore":
        return cls.open(root, database=CORPUS_DATABASE, clock=clock)

    def close(self) -> None:
        self.conn.close()

    def __enter__(self) -> "RunStore":
        return self

    def __exit__(self, *exc: Any) -> None:
        self.close()

    @property
    def tasks(self) -> "Any":
        from .tasks import TaskStore

        return TaskStore(self.conn, clock=self.clock)

    # -- raw sources -------------------------------------------------------

    def ingest_source(self, payload: bytes, document: Any) -> Ingested:
        """Store original bytes once and the SourceDocument that describes them.

        The blob is written first and the row second. A crash between the two
        leaves an orphan blob, which :meth:`orphan_blobs` finds and the next
        ingestion of the same bytes reuses. The reverse order would leave a
        record pointing at bytes that were never stored.
        """
        # Raw acquisition precedes normalization (contracts.md), so a source
        # document is stored without resolving its references.
        document = self._require_valid(document, expected="source_document")
        blob = self.blobs.put(payload)
        if document.blob_hash != blob.blob_hash:
            raise StorageError(
                "document declares blob %s but the payload hashes to %s"
                % (document.blob_hash, blob.blob_hash))
        if document.byte_count != blob.byte_count:
            raise StorageError(
                "document declares %d bytes but the payload is %d"
                % (document.byte_count, blob.byte_count))

        created = self._insert_source_row(document, blob)
        return Ingested(document.record_id, blob, created)

    def _insert_source_row(self, document: Any, blob: BlobWrite) -> bool:
        now = self.clock()
        with transaction(self.conn) as conn:
            existing = conn.execute(
                "SELECT json FROM source_record WHERE record_id = ?",
                (document.record_id,)).fetchone()
            if existing is not None:
                if existing["json"] != canonical_text(to_jsonable(document)):
                    raise DuplicateRecord("source_document", document.record_id)
                return False
            conn.execute(
                "INSERT OR IGNORE INTO blob (blob_hash, byte_count, media_type,"
                " first_seen_at) VALUES (?, ?, ?, ?)",
                (blob.blob_hash, blob.byte_count, document.media_type, now))
            conn.execute(
                "INSERT INTO source_record (record_id, kind, provider,"
                " external_id, source_url, blob_hash, acquired_at, created_at,"
                " json) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (document.record_id, "source_document", document.provider,
                 document.external_id, document.source_url, blob.blob_hash,
                 document.acquired_at, document.created_at,
                 canonical_text(to_jsonable(document))))
        return True

    def put_acquisition_result(self, result: Any) -> bool:
        """Record an attempt, successful or not. Failures are kept."""
        result = self._require_valid(result, expected="acquisition_result")
        with transaction(self.conn) as conn:
            if conn.execute("SELECT 1 FROM source_record WHERE record_id = ?",
                            (result.record_id,)).fetchone():
                return False
            conn.execute(
                "INSERT INTO source_record (record_id, kind, provider,"
                " external_id, source_url, blob_hash, acquired_at, created_at,"
                " json) VALUES (?, 'acquisition_result', ?, NULL, ?, NULL,"
                " ?, ?, ?)",
                (result.record_id, result.provider, result.source_ref,
                 result.attempted_at, result.created_at,
                 canonical_text(to_jsonable(result))))
        return True

    def get_source(self, record_id: str) -> Any:
        row = self.conn.execute(
            "SELECT kind, json FROM source_record WHERE record_id = ?",
            (record_id,)).fetchone()
        if row is None:
            raise RecordNotFound("source_record", record_id)
        return from_jsonable(RECORD_TYPES[row["kind"]], json.loads(row["json"]))

    def source_history(self, provider: str, external_id: str | None) -> list[Any]:
        """Every version of one external source, oldest acquisition first."""
        rows = self.conn.execute(
            "SELECT json FROM source_record WHERE kind = 'source_document'"
            " AND provider = ? AND external_id IS ?"
            " ORDER BY acquired_at, record_id", (provider, external_id)).fetchall()
        return [from_jsonable(RECORD_TYPES["source_document"],
                              json.loads(row["json"])) for row in rows]

    def read_payload(self, blob_hash: str) -> bytes:
        return self.blobs.get(blob_hash)

    def orphan_blobs(self) -> tuple[str, ...]:
        """Blobs on disk that no row references.

        The recoverable half of an interrupted ingestion: the bytes are safe
        and verifiable, and no record claims they were successfully stored.
        """
        known = {row[0] for row in self.conn.execute("SELECT blob_hash FROM blob")}
        return tuple(h for h in self.blobs.iter_hashes() if h not in known)

    # -- normalized records -------------------------------------------------

    def put_normalized(self, record: Any, *,
                       require_references: bool = True) -> bool:
        """Accept one normalized record.

        References are resolved against this store by default. A record whose
        catalog, equipment, rotation or raw payload is not here is not
        normalized data, it is a dangling fragment, and admitting it was how
        an incomplete bundle came to call itself readable (P01-R03).

        ``require_references=False`` is the explicit staging escape hatch for
        an import that will be completed in a later call; prefer
        :meth:`put_normalized_batch`, which resolves within the batch.
        """
        return self.put_normalized_batch(
            [record], require_references=require_references)[record.record_id]

    def put_normalized_batch(self, records: Sequence[Any], *,
                             require_references: bool = True) -> dict[str, bool]:
        """Accept several normalized records as one unit."""
        for record in records:
            kind = kind_of(record)
            if kind not in _NORMALIZED_HASHES:
                raise StorageError("%s is not a normalized record kind" % kind)
        return self.import_batch(records,
                                 require_references=require_references)

    def import_batch(self, records: Sequence[Any], *,
                     require_references: bool = True,
                     run_id: str | None = None) -> dict[str, bool]:
        """Accept a set of records of any kind as one validated unit.

        References are resolved against the store **plus the batch**, and
        everything is written in one transaction. This is what cyclic
        references need: a patch profile cites the catalog that cites it, and
        it also cites a gap that lives in another table, so neither an
        ordering nor a normalized-only batch can import them
        (review finding P01-R03, point 2).
        """
        index = self.reference_index(records) if require_references else None
        decoded = [self._require_valid(record, index=index)
                   for record in records]

        created: dict[str, bool] = {}
        with transaction(self.conn) as conn:
            for record in decoded:
                kind = kind_of(record)
                writer = self._WRITERS.get(kind)
                if writer is None:
                    raise StorageError("%s cannot be imported in a batch" % kind)
                created[_identity_of(record)] = writer(self, conn, record,
                                                       run_id)
        return created

    # -- single-record writers, each usable inside a shared transaction ----

    def _write_normalized(self, conn: sqlite3.Connection, record: Any,
                          _run_id: str | None = None) -> bool:
        kind = kind_of(record)
        hash_field = _NORMALIZED_HASHES[kind]
        payload = canonical_text(to_jsonable(record))
        existing = conn.execute(
            "SELECT json FROM normalized_record WHERE record_id = ?",
            (record.record_id,)).fetchone()
        if existing is not None:
            if existing["json"] != payload:
                raise DuplicateRecord(kind, record.record_id)
            return False
        conn.execute(
            "INSERT INTO normalized_record (record_id, kind, primary_hash,"
            " catalog_hash, status, created_at, json)"
            " VALUES (?, ?, ?, ?, ?, ?, ?)",
            (record.record_id, kind,
             getattr(record, hash_field) if hash_field else None,
             getattr(record, "catalog_hash", None),
             _status_of(record), record.created_at, payload))
        return True

    def _write_gap(self, conn: sqlite3.Connection, gap: Any,
                   _run_id: str | None = None) -> bool:
        if conn.execute("SELECT 1 FROM data_gap WHERE gap_id = ?",
                        (gap.gap_id,)).fetchone():
            return False
        conn.execute(
            "INSERT INTO data_gap (gap_id, kind, severity, status,"
            " created_at, json) VALUES (?, ?, ?, ?, ?, ?)",
            (gap.gap_id, gap.kind.value, gap.severity.value, gap.status.value,
             gap.created_at, canonical_text(to_jsonable(gap))))
        return True

    def _write_observation(self, conn: sqlite3.Connection, observation: Any,
                           _run_id: str | None = None) -> bool:
        if conn.execute("SELECT 1 FROM observation WHERE observation_id = ?",
                        (observation.observation_id,)).fetchone():
            return False
        conn.execute(
            "INSERT INTO observation (observation_id, build_hash, scenario_id,"
            " dataset_split, outcome, created_at, json)"
            " VALUES (?, ?, ?, ?, ?, ?, ?)",
            (observation.observation_id, observation.build_hash,
             observation.scenario_id, observation.dataset_split.value,
             observation.outcome.value, observation.created_at,
             canonical_text(to_jsonable(observation))))
        return True

    def _write_run(self, conn: sqlite3.Connection, manifest: Any,
                   _run_id: str | None = None) -> bool:
        if conn.execute("SELECT 1 FROM run WHERE run_id = ?",
                        (manifest.run_id,)).fetchone():
            return False
        conn.execute(
            "INSERT INTO run (run_id, manifest_hash, availability_mode,"
            " stop_status, created_at, json) VALUES (?, ?, ?, 'running', ?, ?)",
            (manifest.run_id, manifest_hash(manifest),
             manifest.availability_mode.value, manifest.created_at,
             canonical_text(to_jsonable(manifest))))
        return True

    #: Filled in below, once the methods exist.
    _WRITERS: dict[str, Any] = {}

    def get_normalized(self, record_id: str) -> Any:
        row = self.conn.execute(
            "SELECT kind, json FROM normalized_record WHERE record_id = ?",
            (record_id,)).fetchone()
        if row is None:
            raise RecordNotFound("normalized_record", record_id)
        return from_jsonable(RECORD_TYPES[row["kind"]], json.loads(row["json"]))

    def get_record(self, record_id: str) -> Any:
        """Any persisted record by id, whichever table it lives in."""
        for _rid, _kind, record in self.iter_stored():
            if _rid == record_id:
                return record
        raise RecordNotFound("record", record_id)

    def has_record(self, record_id: str) -> bool:
        try:
            self.get_record(record_id)
        except RecordNotFound:
            return False
        return True

    def find_normalized(self, kind: str, primary_hash: str) -> list[Any]:
        rows = self.conn.execute(
            "SELECT json FROM normalized_record WHERE kind = ? AND"
            " primary_hash = ? ORDER BY created_at, record_id",
            (kind, primary_hash)).fetchall()
        return [from_jsonable(RECORD_TYPES[kind], json.loads(r["json"]))
                for r in rows]

    def iter_normalized(self, kind: str) -> Iterator[Any]:
        for row in self.conn.execute(
                "SELECT json FROM normalized_record WHERE kind = ?"
                " ORDER BY created_at, record_id", (kind,)):
            yield from_jsonable(RECORD_TYPES[kind], json.loads(row["json"]))

    # -- gaps, observations, runs ------------------------------------------

    def put_gap(self, gap: Any, *, require_references: bool = True) -> bool:
        gap = self._require_valid(
            gap, expected="data_gap",
            index=self.reference_index([gap]) if require_references else None)
        with transaction(self.conn) as conn:
            return self._write_gap(conn, gap)

    def open_gaps(self, severity: str | None = None) -> list[Any]:
        sql = "SELECT json FROM data_gap WHERE status = 'open'"
        params: tuple[Any, ...] = ()
        if severity is not None:
            sql += " AND severity = ?"
            params = (severity,)
        return [from_jsonable(RECORD_TYPES["data_gap"], json.loads(r["json"]))
                for r in self.conn.execute(sql + " ORDER BY gap_id", params)]

    def put_observation(self, observation: Any, *,
                        require_references: bool = True) -> bool:
        observation = self._require_valid(
            observation, expected="observation",
            index=self.reference_index([observation])
            if require_references else None)
        with transaction(self.conn) as conn:
            return self._write_observation(conn, observation)

    def put_run(self, manifest: Any, expected_hash: str | None = None, *,
                require_references: bool = True) -> bool:
        """Store a run manifest.

        The stored digest is recomputed from the manifest, never taken on
        trust. ``expected_hash``, when given, is checked against it, so a
        caller that already computed one finds out here if they disagree.
        """
        manifest = self._require_valid(
            manifest, expected="run_manifest",
            index=self.reference_index([manifest])
            if require_references else None)
        digest = manifest_hash(manifest)
        if expected_hash is not None and expected_hash != digest:
            raise StorageError(
                "manifest %s hashes to %s, not the %s the caller expected"
                % (manifest.run_id, digest, expected_hash))
        with transaction(self.conn) as conn:
            return self._write_run(conn, manifest)

    def get_run(self, run_id: str) -> Any:
        row = self.conn.execute("SELECT json FROM run WHERE run_id = ?",
                                (run_id,)).fetchone()
        if row is None:
            raise RecordNotFound("run", run_id)
        return from_jsonable(RECORD_TYPES["run_manifest"], json.loads(row["json"]))

    def run_manifest_hash(self, run_id: str) -> str:
        row = self.conn.execute("SELECT manifest_hash FROM run WHERE run_id = ?",
                                (run_id,)).fetchone()
        if row is None:
            raise RecordNotFound("run", run_id)
        return str(row["manifest_hash"])

    def add_run_references(self, run_id: str, kind: str,
                           refs: Iterable[str]) -> int:
        """Record which corpus content this run copied into its own scope."""
        now = self.clock()
        added = 0
        with transaction(self.conn) as conn:
            for ref in refs:
                cursor = conn.execute(
                    "INSERT OR IGNORE INTO run_reference (run_id, kind, ref,"
                    " copied_at) VALUES (?, ?, ?, ?)", (run_id, kind, ref, now))
                added += cursor.rowcount or 0
        return added

    def run_references(self, run_id: str, kind: str | None = None) -> list[str]:
        sql = "SELECT ref FROM run_reference WHERE run_id = ?"
        params: tuple[Any, ...] = (run_id,)
        if kind is not None:
            sql += " AND kind = ?"
            params += (kind,)
        return [row["ref"] for row in self.conn.execute(sql + " ORDER BY ref",
                                                        params)]

    # -- evaluations and cache ---------------------------------------------

    def commit_evaluation(self, task_id: str | None, result: Any, *,
                          run_id: str | None = None,
                          legacy: bool = False,
                          require_references: bool = True,
                          attempt: int | None = None) -> Committed:
        """Write one result and close its task, in one transaction.

        Idempotent on purpose: a repeated completion message for the same
        task and the same evaluation is a no-op, so a duplicate delivery
        cannot create a second result or count one twice.

        Everything else is refused, and refused atomically, so a rejected
        completion leaves no evaluation row behind:

        * only a ``running`` task may complete. A cancelled, queued or failed
          task stays as it is; before the review a late result silently
          revived cancelled work (P01-R01).
        * when the task carries a ``context_key``, the result must be the
          evaluation that key names. A worker cannot close a boss task with a
          clear result.
        * ``attempt`` says which dispatch produced this result. A result from
          a superseded attempt, which is what arrives when a worker outlives
          a recovery, is rejected rather than attributed to the attempt now
          running. Omit it only when the caller genuinely does not know.
        """
        result = self._require_valid(
            result, expected="evaluation_result",
            index=self.reference_index([result]) if require_references else None)
        payload = canonical_text(to_jsonable(result))
        now = self.clock()
        with transaction(self.conn) as conn:
            by_key = conn.execute(
                "SELECT evaluation_id, json FROM evaluation WHERE cache_key = ?",
                (result.cache_key,)).fetchone()
            if by_key is not None:
                if by_key["evaluation_id"] != result.evaluation_id:
                    raise CacheKeyConflict(result.cache_key,
                                           by_key["evaluation_id"],
                                           result.evaluation_id)
                if by_key["json"] != payload:
                    raise DuplicateRecord("evaluation_result",
                                          result.evaluation_id)
                created = False
            else:
                conn.execute(
                    "INSERT INTO evaluation (evaluation_id, cache_key, run_id,"
                    " build_hash, rotation_hash, scenario_id, manifest_id,"
                    " fidelity, seed, status, legacy, created_at, json)"
                    " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (result.evaluation_id, result.cache_key, run_id,
                     result.build_hash, result.rotation_hash,
                     result.scenario_id, result.manifest_id,
                     result.fidelity.value, result.seed, result.status.value,
                     1 if legacy else 0, result.created_at, payload))
                created = True

            if task_id is not None:
                self._close_task(conn, task_id, result, now, attempt)
        return Committed(result.evaluation_id, created)

    @staticmethod
    def _close_task(conn: sqlite3.Connection, task_id: str, result: Any,
                    now: str, attempt: int | None) -> None:
        row = conn.execute(
            "SELECT state, attempt, context_key, evaluation_id FROM task"
            " WHERE task_id = ?", (task_id,)).fetchone()
        if row is None:
            raise RecordNotFound("task", task_id)
        state = TaskState(row["state"])
        evaluation_id = result.evaluation_id

        # An exact repeat of a completed task is the duplicate-delivery case
        # and stays a no-op. A different result for it is a bug.
        if state is TaskState.COMPLETED:
            if row["evaluation_id"] != evaluation_id:
                raise TaskResultMismatch(
                    task_id, "already completed with evaluation %s; it cannot "
                    "also produce %s" % (row["evaluation_id"], evaluation_id))
            return

        if TaskState.COMPLETED not in TASK_TRANSITIONS[state]:
            raise TaskStateError(task_id, state.value,
                                 TaskState.COMPLETED.value)

        if row["context_key"] and row["context_key"] != result.cache_key:
            raise TaskResultMismatch(
                task_id, "expects the evaluation with cache key %s, but %s "
                "has cache key %s" % (row["context_key"], evaluation_id,
                                      result.cache_key))

        if attempt is not None and attempt != row["attempt"]:
            raise StaleAttempt(task_id, attempt, row["attempt"])

        conn.execute(
            "UPDATE task SET state = ?, evaluation_id = ?, finished_at = ?,"
            " error = NULL WHERE task_id = ?",
            (TaskState.COMPLETED.value, evaluation_id, now, task_id))
        conn.execute(
            "INSERT INTO task_event (task_id, attempt, from_state, to_state,"
            " reason, at) VALUES (?, ?, ?, ?, ?, ?)",
            (task_id, row["attempt"], state.value, TaskState.COMPLETED.value,
             "result %s committed" % evaluation_id, now))

    def evaluation_by_cache_key(self, cache_key: str) -> Any | None:
        row = self.conn.execute(
            "SELECT json FROM evaluation WHERE cache_key = ?",
            (cache_key,)).fetchone()
        if row is None:
            return None
        return from_jsonable(RECORD_TYPES["evaluation_result"],
                             json.loads(row["json"]))

    def is_legacy_evaluation(self, cache_key: str) -> bool:
        row = self.conn.execute(
            "SELECT legacy FROM evaluation WHERE cache_key = ?",
            (cache_key,)).fetchone()
        return bool(row and row["legacy"])

    def lookup(self, key: EvaluationKey, *,
               run_id: str | None = None) -> CacheDecision:
        """Resolve a cache lookup and persist why it hit or missed."""
        decision = decide_cache(key, self.evaluation_by_cache_key,
                                legacy=self.is_legacy_evaluation)
        self.record_cache_decision(decision, run_id=run_id)
        return decision

    def record_cache_decision(self, decision: CacheDecision, *,
                              run_id: str | None = None) -> None:
        with transaction(self.conn) as conn:
            conn.execute(
                "INSERT INTO cache_decision (run_id, cache_key, outcome,"
                " reason, evaluation_id, rejected_cache_key, detail, decided_at)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (run_id, decision.cache_key, decision.outcome.value,
                 decision.reason.value, decision.evaluation_id,
                 decision.rejected_cache_key, decision.detail, self.clock()))

    def cache_decisions(self, cache_key: str | None = None) -> list[dict[str, Any]]:
        sql = ("SELECT run_id, cache_key, outcome, reason, evaluation_id,"
               " rejected_cache_key, detail, decided_at FROM cache_decision")
        params: tuple[Any, ...] = ()
        if cache_key is not None:
            sql += " WHERE cache_key = ?"
            params = (cache_key,)
        return [dict(row) for row in
                self.conn.execute(sql + " ORDER BY decision_id", params)]

    # -- validation --------------------------------------------------------

    def _require_valid(self, record: Any, *, expected: str | None = None,
                       index: Any = None, pending: Sequence[Any] = ()) -> Any:
        """Validate and return the **decoded** record to persist.

        Returning the decoded instance matters: a hand-built dataclass can
        hold a wire value where a typed one belongs, and only the decoded
        record is guaranteed to be the one the schema accepted
        (review finding P01-R02).
        """
        kind = kind_of(record)
        if expected is not None and kind != expected:
            raise StorageError("expected a %s, got a %s" % (expected, kind))
        if index is None and pending:
            index = StoreIndex.with_pending(self, pending)
        return validate_record(record, index=index).raise_for_errors()

    def reference_index(self, pending: Sequence[Any] = (),
                        blob_hashes: Iterable[str] = ()) -> StoreIndex:
        """Resolve references against this store, plus any pending batch."""
        return StoreIndex.with_pending(self, pending, blob_hashes)

    def record_index(self) -> RecordIndex:
        """Materialize every identifier. For reporting, not for a lookup."""
        index = RecordIndex()
        for blob_hash in self.blobs.iter_hashes():
            index.add_blob(blob_hash)
        for table, kind_column in (("source_record", "kind"),
                                   ("normalized_record", "kind")):
            for row in self.conn.execute(
                    "SELECT %s AS kind, json FROM %s" % (kind_column, table)):
                index.add(from_jsonable(RECORD_TYPES[row["kind"]],
                                        json.loads(row["json"])))
        for table, kind in (("data_gap", "data_gap"),
                            ("observation", "observation"),
                            ("run", "run_manifest"),
                            ("evaluation", "evaluation_result")):
            for row in self.conn.execute("SELECT json FROM %s" % table):
                index.add(from_jsonable(RECORD_TYPES[kind],
                                        json.loads(row["json"])))
        return index

    def iter_stored(self, kinds: Sequence[str] | None = None
                    ) -> Iterator[tuple[str, str, Any]]:
        """Every persisted record, as ``(record_id, kind, record)``.

        All of them, not only the source and normalized tables: evaluations,
        gaps, observations and manifests carry references too.
        """
        tables = (("source_record", None), ("normalized_record", None),
                  ("evaluation", "evaluation_result"), ("data_gap", "data_gap"),
                  ("observation", "observation"), ("run", "run_manifest"))
        for table, fixed_kind in tables:
            column = "kind" if fixed_kind is None else "'%s' AS kind" % fixed_kind
            id_column = {"evaluation": "evaluation_id", "data_gap": "gap_id",
                         "observation": "observation_id", "run": "run_id",
                         }.get(table, "record_id")
            for row in self.conn.execute(
                    "SELECT %s AS rid, %s, json FROM %s"
                    % (id_column, column, table)):
                if kinds is not None and row["kind"] not in kinds:
                    continue
                yield (row["rid"], row["kind"],
                       from_jsonable(RECORD_TYPES[row["kind"]],
                                     json.loads(row["json"])))

    def validate_stored(self, kinds: Sequence[str] | None = None
                        ) -> dict[str, Any]:
        """Re-validate every stored record against this store as a corpus."""
        index = self.reference_index()
        return {rid: validate_record(record, index=index)
                for rid, _kind, record in self.iter_stored(kinds)}

    def unresolved_references(self) -> dict[str, list[str]]:
        """``record_id -> unresolved field paths``, empty when closed."""
        out: dict[str, list[str]] = {}
        for rid, report in self.validate_stored().items():
            paths = [e.field_path for e in report.errors
                     if e.code == "unresolved_reference"]
            if paths:
                out[rid] = paths
        return out


def _identity_of(record: Any) -> str:
    """The id a batch result is keyed by."""
    for attribute in ("record_id", "gap_id", "observation_id", "run_id"):
        value = getattr(record, attribute, None)
        if value is not None:
            return str(value)
    raise StorageError("%s has no identifier" % kind_of(record))


RunStore._WRITERS = dict(
    {kind: RunStore._write_normalized for kind in _NORMALIZED_HASHES},
    data_gap=RunStore._write_gap,
    observation=RunStore._write_observation,
    run_manifest=RunStore._write_run,
)


def _status_of(record: Any) -> str | None:
    for attribute in ("parse_status", "status", "compatibility",
                      "validation_status"):
        value = getattr(record, attribute, None)
        if value is not None and hasattr(value, "value"):
            return str(value.value)
    return None
