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
    kind_of,
    to_jsonable,
    validate_record,
)
from ..domain.cache import decide as decide_cache
from ..domain.enums import TaskState
from .blobs import BlobStore, BlobWrite
from .database import open_database, transaction, utcnow
from .errors import (
    CacheKeyConflict,
    DuplicateRecord,
    RecordNotFound,
    StorageError,
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
        self._require_valid(document, expected="source_document")
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
        self._require_valid(result, expected="acquisition_result")
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

    def put_normalized(self, record: Any) -> bool:
        kind = kind_of(record)
        if kind not in _NORMALIZED_HASHES:
            raise StorageError("%s is not a normalized record kind" % kind)
        self._require_valid(record)
        hash_field = _NORMALIZED_HASHES[kind]
        payload = canonical_text(to_jsonable(record))
        with transaction(self.conn) as conn:
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

    def get_normalized(self, record_id: str) -> Any:
        row = self.conn.execute(
            "SELECT kind, json FROM normalized_record WHERE record_id = ?",
            (record_id,)).fetchone()
        if row is None:
            raise RecordNotFound("normalized_record", record_id)
        return from_jsonable(RECORD_TYPES[row["kind"]], json.loads(row["json"]))

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

    def put_gap(self, gap: Any) -> bool:
        self._require_valid(gap, expected="data_gap")
        with transaction(self.conn) as conn:
            if conn.execute("SELECT 1 FROM data_gap WHERE gap_id = ?",
                            (gap.gap_id,)).fetchone():
                return False
            conn.execute(
                "INSERT INTO data_gap (gap_id, kind, severity, status,"
                " created_at, json) VALUES (?, ?, ?, ?, ?, ?)",
                (gap.gap_id, gap.kind.value, gap.severity.value,
                 gap.status.value, gap.created_at,
                 canonical_text(to_jsonable(gap))))
        return True

    def open_gaps(self, severity: str | None = None) -> list[Any]:
        sql = "SELECT json FROM data_gap WHERE status = 'open'"
        params: tuple[Any, ...] = ()
        if severity is not None:
            sql += " AND severity = ?"
            params = (severity,)
        return [from_jsonable(RECORD_TYPES["data_gap"], json.loads(r["json"]))
                for r in self.conn.execute(sql + " ORDER BY gap_id", params)]

    def put_observation(self, observation: Any) -> bool:
        self._require_valid(observation, expected="observation")
        with transaction(self.conn) as conn:
            if conn.execute(
                    "SELECT 1 FROM observation WHERE observation_id = ?",
                    (observation.observation_id,)).fetchone():
                return False
            conn.execute(
                "INSERT INTO observation (observation_id, build_hash,"
                " scenario_id, dataset_split, outcome, created_at, json)"
                " VALUES (?, ?, ?, ?, ?, ?, ?)",
                (observation.observation_id, observation.build_hash,
                 observation.scenario_id, observation.dataset_split.value,
                 observation.outcome.value, observation.created_at,
                 canonical_text(to_jsonable(observation))))
        return True

    def put_run(self, manifest: Any, manifest_hash: str) -> bool:
        self._require_valid(manifest, expected="run_manifest")
        with transaction(self.conn) as conn:
            if conn.execute("SELECT 1 FROM run WHERE run_id = ?",
                            (manifest.run_id,)).fetchone():
                return False
            conn.execute(
                "INSERT INTO run (run_id, manifest_hash, availability_mode,"
                " stop_status, created_at, json) VALUES (?, ?, ?, 'running', ?, ?)",
                (manifest.run_id, manifest_hash,
                 manifest.availability_mode.value, manifest.created_at,
                 canonical_text(to_jsonable(manifest))))
        return True

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
                          legacy: bool = False) -> Committed:
        """Write one result and close its task, in one transaction.

        Idempotent on purpose: a repeated completion message for the same
        task and the same evaluation is a no-op, so a duplicate delivery
        cannot create a second result or count one twice.
        """
        self._require_valid(result, expected="evaluation_result")
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
                self._close_task(conn, task_id, result.evaluation_id, now)
        return Committed(result.evaluation_id, created)

    @staticmethod
    def _close_task(conn: sqlite3.Connection, task_id: str,
                    evaluation_id: str, now: str) -> None:
        row = conn.execute(
            "SELECT state, attempt, evaluation_id FROM task WHERE task_id = ?",
            (task_id,)).fetchone()
        if row is None:
            raise RecordNotFound("task", task_id)
        if row["state"] == TaskState.COMPLETED.value:
            if row["evaluation_id"] != evaluation_id:
                raise StorageError(
                    "task %s already completed with evaluation %s; it cannot "
                    "also produce %s" % (task_id, row["evaluation_id"],
                                         evaluation_id))
            return
        conn.execute(
            "UPDATE task SET state = ?, evaluation_id = ?, finished_at = ?,"
            " error = NULL WHERE task_id = ?",
            (TaskState.COMPLETED.value, evaluation_id, now, task_id))
        conn.execute(
            "INSERT INTO task_event (task_id, attempt, from_state, to_state,"
            " reason, at) VALUES (?, ?, ?, ?, ?, ?)",
            (task_id, row["attempt"], row["state"], TaskState.COMPLETED.value,
             "result committed", now))

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

    def _require_valid(self, record: Any, *, expected: str | None = None) -> None:
        kind = kind_of(record)
        if expected is not None and kind != expected:
            raise StorageError("expected a %s, got a %s" % (expected, kind))
        validate_record(record).raise_for_errors()

    def index(self) -> RecordIndex:
        """Everything stored here, for the semantic reference pass."""
        index = RecordIndex()
        for row in self.conn.execute("SELECT blob_hash FROM blob"):
            index.add_blob(row["blob_hash"])
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

    def validate_stored(self, kinds: Sequence[str] | None = None
                        ) -> dict[str, Any]:
        """Re-validate stored records against the current corpus index."""
        index = self.index()
        reports: dict[str, Any] = {}
        for table, kind_column in (("source_record", "kind"),
                                   ("normalized_record", "kind")):
            for row in self.conn.execute(
                    "SELECT record_id, %s AS kind, json FROM %s"
                    % (kind_column, table)):
                if kinds is not None and row["kind"] not in kinds:
                    continue
                record = from_jsonable(RECORD_TYPES[row["kind"]],
                                       json.loads(row["json"]))
                reports[row["record_id"]] = validate_record(record, index=index)
        return reports


def _status_of(record: Any) -> str | None:
    for attribute in ("parse_status", "status", "compatibility",
                      "validation_status"):
        value = getattr(record, attribute, None)
        if value is not None and hasattr(value, "value"):
            return str(value.value)
    return None
