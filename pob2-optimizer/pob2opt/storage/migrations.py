"""Numbered SQLite migrations and their runner (P01-T03).

Rules this module enforces:

* Migrations are numbered, ordered and applied inside one transaction each.
* An applied migration is recorded with a checksum of its statements. Editing
  a migration that has already run is rejected (``MigrationHistoryChanged``),
  because the database no longer matches the code that claims to describe it.
* A database written by a newer build is refused, not downgraded.

Payload tables store the whole canonical JSON record in one ``json`` column
and index only identifiers, hashes and statuses. There is deliberately no
column per game stat: a new modifier must not require a schema migration.
"""

from __future__ import annotations

import hashlib
import sqlite3
from dataclasses import dataclass
from typing import Sequence

from .errors import MigrationHistoryChanged, SchemaTooNew

MIGRATION_TABLE = """
CREATE TABLE IF NOT EXISTS schema_migration (
    version    INTEGER PRIMARY KEY,
    name       TEXT NOT NULL,
    checksum   TEXT NOT NULL,
    applied_at TEXT NOT NULL
)
"""


@dataclass(frozen=True, slots=True)
class Migration:
    version: int
    name: str
    statements: tuple[str, ...]

    def checksum(self) -> str:
        joined = "\n".join(s.strip() for s in self.statements)
        return hashlib.sha256(joined.encode("utf-8")).hexdigest()


_V1 = (
    # ---------------------------------------------------------- immutable bytes
    """
    CREATE TABLE blob (
        blob_hash     TEXT PRIMARY KEY,
        byte_count    INTEGER NOT NULL CHECK (byte_count >= 0),
        media_type    TEXT,
        first_seen_at TEXT NOT NULL
    )
    """,
    # ------------------------------------------------------------ raw sources
    """
    CREATE TABLE source_record (
        record_id   TEXT PRIMARY KEY,
        kind        TEXT NOT NULL,
        provider    TEXT NOT NULL,
        external_id TEXT,
        source_url  TEXT,
        blob_hash   TEXT REFERENCES blob(blob_hash),
        acquired_at TEXT,
        created_at  TEXT NOT NULL,
        json        TEXT NOT NULL
    )
    """,
    "CREATE INDEX source_record_external ON source_record "
    "(provider, external_id, acquired_at)",
    "CREATE INDEX source_record_blob ON source_record (blob_hash)",
    # ------------------------------------------------------ normalized records
    """
    CREATE TABLE normalized_record (
        record_id    TEXT PRIMARY KEY,
        kind         TEXT NOT NULL,
        primary_hash TEXT,
        catalog_hash TEXT,
        status       TEXT,
        created_at   TEXT NOT NULL,
        json         TEXT NOT NULL
    )
    """,
    "CREATE INDEX normalized_record_kind ON normalized_record "
    "(kind, primary_hash)",
    "CREATE INDEX normalized_record_catalog ON normalized_record (catalog_hash)",
    # ------------------------------------------------------------------- runs
    """
    CREATE TABLE run (
        run_id            TEXT PRIMARY KEY,
        manifest_hash     TEXT NOT NULL,
        availability_mode TEXT NOT NULL,
        stop_status       TEXT NOT NULL,
        created_at        TEXT NOT NULL,
        json              TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE run_reference (
        run_id    TEXT NOT NULL REFERENCES run(run_id),
        kind      TEXT NOT NULL,
        ref       TEXT NOT NULL,
        copied_at TEXT NOT NULL,
        PRIMARY KEY (run_id, kind, ref)
    )
    """,
    # ------------------------------------------------------------ evaluations
    """
    CREATE TABLE evaluation (
        evaluation_id TEXT PRIMARY KEY,
        cache_key     TEXT NOT NULL UNIQUE,
        run_id        TEXT,
        build_hash    TEXT NOT NULL,
        rotation_hash TEXT NOT NULL,
        scenario_id   TEXT NOT NULL,
        manifest_id   TEXT NOT NULL,
        fidelity      TEXT NOT NULL,
        seed          INTEGER NOT NULL,
        status        TEXT NOT NULL,
        legacy        INTEGER NOT NULL DEFAULT 0 CHECK (legacy IN (0, 1)),
        created_at    TEXT NOT NULL,
        json          TEXT NOT NULL
    )
    """,
    "CREATE INDEX evaluation_build ON evaluation (build_hash, scenario_id)",
    "CREATE INDEX evaluation_run ON evaluation (run_id)",
    """
    CREATE TABLE cache_decision (
        decision_id        INTEGER PRIMARY KEY AUTOINCREMENT,
        run_id             TEXT,
        cache_key          TEXT NOT NULL,
        outcome            TEXT NOT NULL,
        reason             TEXT NOT NULL,
        evaluation_id      TEXT,
        rejected_cache_key TEXT,
        detail             TEXT,
        decided_at         TEXT NOT NULL
    )
    """,
    "CREATE INDEX cache_decision_key ON cache_decision (cache_key)",
    # ------------------------------------------------------- gaps and evidence
    """
    CREATE TABLE data_gap (
        gap_id     TEXT PRIMARY KEY,
        kind       TEXT NOT NULL,
        severity   TEXT NOT NULL,
        status     TEXT NOT NULL,
        created_at TEXT NOT NULL,
        json       TEXT NOT NULL
    )
    """,
    "CREATE INDEX data_gap_status ON data_gap (status, severity)",
    """
    CREATE TABLE observation (
        observation_id TEXT PRIMARY KEY,
        build_hash     TEXT NOT NULL,
        scenario_id    TEXT NOT NULL,
        dataset_split  TEXT NOT NULL,
        outcome        TEXT NOT NULL,
        created_at     TEXT NOT NULL,
        json           TEXT NOT NULL
    )
    """,
    "CREATE INDEX observation_split ON observation (dataset_split, build_hash)",
    # -------------------------------------------------------------- task state
    """
    CREATE TABLE task (
        task_id       TEXT PRIMARY KEY,
        run_id        TEXT NOT NULL,
        generation_id INTEGER NOT NULL,
        candidate_id  TEXT NOT NULL,
        state         TEXT NOT NULL,
        attempt       INTEGER NOT NULL DEFAULT 0,
        evaluation_id TEXT REFERENCES evaluation(evaluation_id),
        worker_id     TEXT,
        error         TEXT,
        enqueued_at   TEXT NOT NULL,
        dispatched_at TEXT,
        finished_at   TEXT,
        payload       TEXT NOT NULL
    )
    """,
    "CREATE UNIQUE INDEX task_candidate ON task "
    "(run_id, generation_id, candidate_id)",
    "CREATE INDEX task_state ON task (run_id, state, generation_id)",
    """
    CREATE TABLE task_event (
        event_id   INTEGER PRIMARY KEY AUTOINCREMENT,
        task_id    TEXT NOT NULL REFERENCES task(task_id),
        attempt    INTEGER NOT NULL,
        from_state TEXT,
        to_state   TEXT NOT NULL,
        reason     TEXT,
        at         TEXT NOT NULL
    )
    """,
    "CREATE INDEX task_event_task ON task_event (task_id, event_id)",
    # ------------------------------------------------------- legacy artifacts
    """
    CREATE TABLE legacy_import (
        import_id   TEXT PRIMARY KEY,
        phase       TEXT NOT NULL,
        source_path TEXT NOT NULL,
        blob_hash   TEXT NOT NULL REFERENCES blob(blob_hash),
        imported_at TEXT NOT NULL,
        note        TEXT NOT NULL
    )
    """,
)

MIGRATIONS: tuple[Migration, ...] = (
    Migration(1, "initial records, evaluations, gaps, runs and task state", _V1),
)

LATEST_VERSION = max(m.version for m in MIGRATIONS)


def current_version(conn: sqlite3.Connection) -> int:
    conn.execute(MIGRATION_TABLE)
    row = conn.execute("SELECT MAX(version) FROM schema_migration").fetchone()
    return int(row[0]) if row and row[0] is not None else 0


def applied(conn: sqlite3.Connection) -> dict[int, tuple[str, str]]:
    conn.execute(MIGRATION_TABLE)
    return {
        int(version): (name, checksum)
        for version, name, checksum in conn.execute(
            "SELECT version, name, checksum FROM schema_migration ORDER BY version")
    }


def migrate(conn: sqlite3.Connection, *, now: str,
            migrations: Sequence[Migration] = MIGRATIONS) -> tuple[int, ...]:
    """Apply every outstanding migration. Returns the versions applied."""
    history = applied(conn)
    highest = max(history) if history else 0
    known = {m.version for m in migrations}
    if highest > max(known | {0}):
        raise SchemaTooNew(highest, LATEST_VERSION)

    for migration in sorted(migrations, key=lambda m: m.version):
        recorded = history.get(migration.version)
        if recorded is not None:
            if recorded[1] != migration.checksum():
                raise MigrationHistoryChanged(
                    migration.version, recorded[1], migration.checksum())
            continue

    newly_applied: list[int] = []
    for migration in sorted(migrations, key=lambda m: m.version):
        if migration.version in history:
            continue
        with conn:  # one transaction per migration
            for statement in migration.statements:
                conn.execute(statement)
            conn.execute(
                "INSERT INTO schema_migration (version, name, checksum, applied_at)"
                " VALUES (?, ?, ?, ?)",
                (migration.version, migration.name, migration.checksum(), now))
        newly_applied.append(migration.version)
    return tuple(newly_applied)
