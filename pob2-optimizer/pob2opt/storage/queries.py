"""Documented read-only queries a reviewer can run by hand (P01-T05).

The acceptance case asks that a reviewer be able to inspect the database.
These are the queries, named, with no application code between the reviewer
and the rows. Paste any of them into ``sqlite3 runs/<run_id>/run.sqlite``, or
run them all with::

    python -m pob2opt.storage.queries runs/<run_id>/run.sqlite

Every statement is a SELECT. ``run_query`` refuses anything else.

``docs/evidence/P01/inspection-queries.md`` shows the output of each one
against the fixture run built by the P01 tests.
"""

from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path
from typing import Any

QUERIES: dict[str, str] = {
    "schema_version":
        "SELECT version, name, applied_at FROM schema_migration"
        " ORDER BY version",

    "task_counts_by_state":
        "SELECT run_id, state, COUNT(*) AS tasks FROM task"
        " GROUP BY run_id, state ORDER BY run_id, state",

    "unfinished_tasks":
        "SELECT task_id, generation_id, candidate_id, state, attempt,"
        " dispatched_at FROM task WHERE state IN ('queued', 'running')"
        " ORDER BY generation_id, task_id",

    "task_history":
        "SELECT task_id, attempt, from_state, to_state, reason, at"
        " FROM task_event ORDER BY event_id",

    "completed_results_once_each":
        "SELECT t.task_id, t.evaluation_id, COUNT(*) AS rows_per_task"
        " FROM task t WHERE t.state = 'completed' GROUP BY t.task_id"
        " ORDER BY t.task_id",

    "duplicate_evaluations_by_cache_key":
        "SELECT cache_key, COUNT(*) AS rows_with_this_key FROM evaluation"
        " GROUP BY cache_key HAVING COUNT(*) > 1",

    "cache_decisions":
        "SELECT reason, outcome, COUNT(*) AS decisions FROM cache_decision"
        " GROUP BY reason, outcome ORDER BY decisions DESC, reason",

    "cache_misses_in_detail":
        "SELECT cache_key, reason, rejected_cache_key, detail, decided_at"
        " FROM cache_decision WHERE outcome = 'miss' ORDER BY decision_id",

    "orphan_blob_rows":
        "SELECT b.blob_hash, b.byte_count FROM blob b"
        " LEFT JOIN source_record s ON s.blob_hash = b.blob_hash"
        " LEFT JOIN legacy_import l ON l.blob_hash = b.blob_hash"
        " WHERE s.record_id IS NULL AND l.import_id IS NULL",

    "source_versions_per_external_id":
        "SELECT provider, external_id, COUNT(*) AS versions,"
        " COUNT(DISTINCT blob_hash) AS distinct_payloads FROM source_record"
        " WHERE kind = 'source_document' GROUP BY provider, external_id"
        " ORDER BY provider, external_id",

    "open_blocking_gaps":
        "SELECT gap_id, kind, severity FROM data_gap WHERE status = 'open'"
        " AND severity = 'blocking' ORDER BY gap_id",

    "legacy_imports_are_labelled":
        "SELECT import_id, phase, source_path, imported_at FROM legacy_import"
        " ORDER BY import_id",

    "evaluations_marked_legacy":
        "SELECT evaluation_id, cache_key, legacy FROM evaluation"
        " WHERE legacy = 1 ORDER BY evaluation_id",

    "run_declared_references":
        "SELECT run_id, kind, COUNT(*) AS refs FROM run_reference"
        " GROUP BY run_id, kind ORDER BY run_id, kind",
}


def run_query(conn: sqlite3.Connection, name: str) -> list[dict[str, Any]]:
    sql = QUERIES[name]
    if not sql.lstrip().upper().startswith("SELECT"):  # pragma: no cover
        raise ValueError("inspection queries are read-only: %s" % name)
    conn.row_factory = sqlite3.Row
    return [dict(row) for row in conn.execute(sql)]


def run_all(conn: sqlite3.Connection) -> dict[str, list[dict[str, Any]]]:
    return {name: run_query(conn, name) for name in QUERIES}


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if len(args) != 1:
        print(__doc__, file=sys.stderr)
        return 2
    path = Path(args[0])
    if not path.is_file():
        print("no database at %s" % path, file=sys.stderr)
        return 3
    conn = sqlite3.connect("file:%s?mode=ro" % path.as_posix(), uri=True)
    try:
        print(json.dumps(run_all(conn), indent=2, ensure_ascii=False))
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
