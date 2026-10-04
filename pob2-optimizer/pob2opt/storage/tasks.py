"""Atomic task state and checkpoints (P01-T05).

States are ``queued``, ``running``, ``completed``, ``failed`` and
``cancelled``. Every transition is one transaction that updates ``task`` and
appends to ``task_event``, so the database and its audit trail cannot
disagree after a crash.

What recovery guarantees, in the words of the acceptance case:

* An interruption **before dispatch** leaves the task queued. It is dispatched
  once on resume.
* An interruption **after dispatch** leaves it running. ``recover`` returns it
  to queued with a new attempt recorded; the lost attempt stays visible.
* An interruption **after the result is written** leaves it completed.
  ``recover`` does not touch it, and a repeated completion message is a no-op
  (``RunStore.commit_evaluation``), so the result is neither lost nor counted
  twice.
* An interruption **before the checkpoint is replaced** leaves the old
  checkpoint and the newer database. The database is authoritative: resume
  rebuilds the queue from task rows, so completed work in the newer
  generation is not re-run.

Checkpoints are written to a sibling temporary file, flushed, fsynced and
``os.replace``d, so a reader never sees a half-written checkpoint. A
checkpoint whose ``manifest_hash`` does not match the run's manifest is
rejected: resuming would mix two runs.
"""

from __future__ import annotations

import json
import os
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Sequence

from ..domain import RECORD_TYPES, canonical_text, from_jsonable, to_jsonable
from ..domain.enums import TASK_TRANSITIONS, TaskState
from .database import transaction, utcnow
from .errors import CheckpointMismatch, RecordNotFound, TaskStateError

CHECKPOINT_NAME = "checkpoint.json"
TEMP_SUFFIX = ".writing"


@dataclass(frozen=True, slots=True)
class TaskRow:
    task_id: str
    run_id: str
    generation_id: int
    candidate_id: str
    state: TaskState
    attempt: int
    evaluation_id: str | None
    worker_id: str | None
    error: str | None
    enqueued_at: str
    dispatched_at: str | None
    finished_at: str | None
    payload: dict[str, Any]

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> "TaskRow":
        return cls(
            task_id=row["task_id"], run_id=row["run_id"],
            generation_id=row["generation_id"], candidate_id=row["candidate_id"],
            state=TaskState(row["state"]), attempt=row["attempt"],
            evaluation_id=row["evaluation_id"], worker_id=row["worker_id"],
            error=row["error"], enqueued_at=row["enqueued_at"],
            dispatched_at=row["dispatched_at"], finished_at=row["finished_at"],
            payload=json.loads(row["payload"]),
        )


class TaskStore:
    def __init__(self, conn: sqlite3.Connection, *,
                 clock: Callable[[], str] = utcnow) -> None:
        self.conn = conn
        self.clock = clock

    # -- queue -------------------------------------------------------------

    def enqueue(self, *, task_id: str, run_id: str, generation_id: int,
                candidate_id: str, payload: dict[str, Any]) -> bool:
        """Add one task. Re-enqueueing the same task id is a no-op."""
        now = self.clock()
        with transaction(self.conn) as conn:
            if conn.execute("SELECT 1 FROM task WHERE task_id = ?",
                            (task_id,)).fetchone():
                return False
            conn.execute(
                "INSERT INTO task (task_id, run_id, generation_id,"
                " candidate_id, state, attempt, enqueued_at, payload)"
                " VALUES (?, ?, ?, ?, ?, 0, ?, ?)",
                (task_id, run_id, generation_id, candidate_id,
                 TaskState.QUEUED.value, now, canonical_text(payload)))
            self._event(conn, task_id, 0, None, TaskState.QUEUED, "enqueued", now)
        return True

    def dispatch(self, task_id: str, *, worker_id: str) -> TaskRow:
        """Mark a queued task running and count the attempt, atomically."""
        now = self.clock()
        with transaction(self.conn) as conn:
            row = self._locked(conn, task_id)
            state = TaskState(row["state"])
            self._require_transition(task_id, state, TaskState.RUNNING)
            attempt = row["attempt"] + 1
            conn.execute(
                "UPDATE task SET state = ?, attempt = ?, worker_id = ?,"
                " dispatched_at = ?, error = NULL WHERE task_id = ?",
                (TaskState.RUNNING.value, attempt, worker_id, now, task_id))
            self._event(conn, task_id, attempt, state, TaskState.RUNNING,
                        "dispatched to %s" % worker_id, now)
        return self.get(task_id)

    def claim_next(self, run_id: str, *, worker_id: str) -> TaskRow | None:
        """Dispatch the lowest-generation queued task, or return None."""
        with transaction(self.conn) as conn:
            row = conn.execute(
                "SELECT task_id FROM task WHERE run_id = ? AND state = ?"
                " ORDER BY generation_id, task_id LIMIT 1",
                (run_id, TaskState.QUEUED.value)).fetchone()
        if row is None:
            return None
        return self.dispatch(row["task_id"], worker_id=worker_id)

    def fail(self, task_id: str, *, error: str) -> TaskRow:
        return self._finish(task_id, TaskState.FAILED, error=error)

    def cancel(self, task_id: str, *, reason: str = "cancelled") -> TaskRow:
        return self._finish(task_id, TaskState.CANCELLED, error=reason)

    def requeue(self, task_id: str, *, reason: str) -> TaskRow:
        """Give a failed task another attempt. Completed tasks are refused."""
        return self._finish(task_id, TaskState.QUEUED, error=None, reason=reason)

    def _finish(self, task_id: str, target: TaskState, *, error: str | None,
                reason: str | None = None) -> TaskRow:
        now = self.clock()
        with transaction(self.conn) as conn:
            row = self._locked(conn, task_id)
            state = TaskState(row["state"])
            self._require_transition(task_id, state, target)
            finished = None if target is TaskState.QUEUED else now
            conn.execute(
                "UPDATE task SET state = ?, error = ?, finished_at = ?"
                " WHERE task_id = ?", (target.value, error, finished, task_id))
            self._event(conn, task_id, row["attempt"], state, target,
                        reason or error, now)
        return self.get(task_id)

    # -- recovery ----------------------------------------------------------

    def recover(self, run_id: str) -> tuple[str, ...]:
        """Return unfinished running tasks to the queue after a restart.

        Completed, failed and cancelled tasks are left exactly as they are.
        The attempt counter is not reset: the interrupted attempt stays in
        ``task_event`` so a repeatedly crashing candidate remains visible.
        """
        now = self.clock()
        recovered: list[str] = []
        with transaction(self.conn) as conn:
            rows = conn.execute(
                "SELECT task_id, attempt FROM task WHERE run_id = ? AND"
                " state = ? ORDER BY task_id",
                (run_id, TaskState.RUNNING.value)).fetchall()
            for row in rows:
                conn.execute(
                    "UPDATE task SET state = ?, worker_id = NULL,"
                    " dispatched_at = NULL WHERE task_id = ?",
                    (TaskState.QUEUED.value, row["task_id"]))
                self._event(conn, row["task_id"], row["attempt"],
                            TaskState.RUNNING, TaskState.QUEUED,
                            "interrupted attempt %d returned to the queue"
                            % row["attempt"], now)
                recovered.append(row["task_id"])
        return tuple(recovered)

    # -- reading -----------------------------------------------------------

    def get(self, task_id: str) -> TaskRow:
        row = self.conn.execute("SELECT * FROM task WHERE task_id = ?",
                                (task_id,)).fetchone()
        if row is None:
            raise RecordNotFound("task", task_id)
        return TaskRow.from_row(row)

    def by_state(self, run_id: str, state: TaskState) -> list[TaskRow]:
        rows = self.conn.execute(
            "SELECT * FROM task WHERE run_id = ? AND state = ?"
            " ORDER BY generation_id, task_id", (run_id, state.value)).fetchall()
        return [TaskRow.from_row(row) for row in rows]

    def counts(self, run_id: str) -> dict[str, int]:
        rows = self.conn.execute(
            "SELECT state, COUNT(*) AS n FROM task WHERE run_id = ?"
            " GROUP BY state", (run_id,)).fetchall()
        counts = {state.value: 0 for state in TaskState}
        counts.update({row["state"]: row["n"] for row in rows})
        return counts

    def history(self, task_id: str) -> list[dict[str, Any]]:
        return [dict(row) for row in self.conn.execute(
            "SELECT attempt, from_state, to_state, reason, at FROM task_event"
            " WHERE task_id = ? ORDER BY event_id", (task_id,))]

    def completed_evaluation_ids(self, run_id: str) -> tuple[str, ...]:
        rows = self.conn.execute(
            "SELECT evaluation_id FROM task WHERE run_id = ? AND state = ?"
            " AND evaluation_id IS NOT NULL ORDER BY task_id",
            (run_id, TaskState.COMPLETED.value)).fetchall()
        return tuple(row["evaluation_id"] for row in rows)

    # -- internals ---------------------------------------------------------

    @staticmethod
    def _locked(conn: sqlite3.Connection, task_id: str) -> sqlite3.Row:
        row = conn.execute("SELECT * FROM task WHERE task_id = ?",
                           (task_id,)).fetchone()
        if row is None:
            raise RecordNotFound("task", task_id)
        return row

    @staticmethod
    def _require_transition(task_id: str, current: TaskState,
                            target: TaskState) -> None:
        if target not in TASK_TRANSITIONS[current]:
            raise TaskStateError(task_id, current.value, target.value)

    @staticmethod
    def _event(conn: sqlite3.Connection, task_id: str, attempt: int,
               from_state: TaskState | None, to_state: TaskState,
               reason: str | None, now: str) -> None:
        conn.execute(
            "INSERT INTO task_event (task_id, attempt, from_state, to_state,"
            " reason, at) VALUES (?, ?, ?, ?, ?, ?)",
            (task_id, attempt, from_state.value if from_state else None,
             to_state.value, reason, now))


# ------------------------------------------------------------- checkpoints

def write_checkpoint(run_root: Path | str, checkpoint: Any) -> Path:
    """Write ``checkpoint.json`` atomically next to the run bundle."""
    run_root = Path(run_root)
    run_root.mkdir(parents=True, exist_ok=True)
    target = run_root / CHECKPOINT_NAME
    temp = target.with_name(target.name + TEMP_SUFFIX)
    payload = json.dumps(to_jsonable(checkpoint), indent=2,
                         ensure_ascii=False, sort_keys=True) + "\n"
    with open(temp, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(payload)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temp, target)
    return target


def read_checkpoint(run_root: Path | str) -> Any:
    path = Path(run_root) / CHECKPOINT_NAME
    if not path.is_file():
        raise RecordNotFound("checkpoint", str(path))
    return from_jsonable(RECORD_TYPES["checkpoint"],
                         json.loads(path.read_text(encoding="utf-8")))


def validate_checkpoint(checkpoint: Any, *, manifest_hash: str,
                        run_id: str | None = None) -> None:
    """Refuse a checkpoint that belongs to a different manifest or run."""
    if checkpoint.manifest_hash != manifest_hash:
        raise CheckpointMismatch(manifest_hash, checkpoint.manifest_hash)
    if run_id is not None and checkpoint.run_id != run_id:
        raise CheckpointMismatch(run_id, checkpoint.run_id)


def resume_plan(tasks: TaskStore, run_id: str) -> dict[str, Sequence[str]]:
    """What a resume will do, from the database rather than the checkpoint.

    The database is authoritative after a crash, so this is derived from task
    rows. A checkpoint that disagrees is stale, not a second opinion.
    """
    recovered = tasks.recover(run_id)
    return {
        "recovered_from_running": recovered,
        "to_dispatch": tuple(t.task_id for t in
                             tasks.by_state(run_id, TaskState.QUEUED)),
        "already_completed": tuple(t.task_id for t in
                                   tasks.by_state(run_id, TaskState.COMPLETED)),
    }
