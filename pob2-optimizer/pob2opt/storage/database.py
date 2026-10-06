"""SQLite connection, clock and transaction helpers (P01-T03).

One coordinator process owns the writer. ``transaction()`` opens
``BEGIN IMMEDIATE`` so a second writer fails fast with ``database is locked``
instead of interleaving.

Foreign keys are on. SQLite ignores them by default, and a task row pointing
at an evaluation that was never written is exactly the inconsistency the task
acceptance cases are about.
"""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Iterator

from .migrations import current_version, migrate


def utcnow() -> str:
    """RFC 3339 UTC with a literal Z, matching the contracts.md pattern."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def connect(path: Path | str) -> sqlite3.Connection:
    """Open (or create) a database with the settings this project needs."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), isolation_level=None,
                           detect_types=0, timeout=30.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA synchronous = FULL")
    return conn


def open_database(path: Path | str, *,
                  clock: Callable[[], str] = utcnow) -> sqlite3.Connection:
    """Connect and bring the schema up to date."""
    conn = connect(path)
    migrate(conn, now=clock())
    return conn


@contextmanager
def transaction(conn: sqlite3.Connection) -> Iterator[sqlite3.Connection]:
    """One all-or-nothing unit of work.

    ``isolation_level=None`` turns off the sqlite3 module's implicit
    transaction handling, so the statements are explicit and a raised
    exception inside the block rolls back everything in it.
    """
    conn.execute("BEGIN IMMEDIATE")
    try:
        yield conn
    except BaseException:
        conn.execute("ROLLBACK")
        raise
    conn.execute("COMMIT")


def schema_version(conn: sqlite3.Connection) -> int:
    return current_version(conn)
