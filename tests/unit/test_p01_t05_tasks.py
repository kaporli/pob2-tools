"""Atomic task persistence and recovery (P01-T05).

The acceptance case names four interruption points: before dispatch, after
dispatch, after the result is written, and before the checkpoint is replaced.
Each has a test here, and each asserts the same two properties afterwards:
resume loses no completed result and counts none of them twice.

The last section runs the documented inspection queries, so the queries a
reviewer is told to use are known to work against a real database.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import replace
from pathlib import Path

import pytest

from record_fixtures import records, seed_corpus

from pob2opt.domain import manifest_hash
from pob2opt.domain.enums import StopStatus, TaskState
from pob2opt.storage import (
    CheckpointMismatch,
    RecordNotFound,
    RunBundle,
    TaskStateError,
    read_checkpoint,
    resume_plan,
    validate_checkpoint,
    write_checkpoint,
)
from pob2opt.storage.queries import QUERIES, run_all, run_query
from pob2opt.storage.tasks import CHECKPOINT_NAME

R = records()
MANIFEST = R["run_manifest"]
RUN_ID = MANIFEST.run_id
RESULT = R["evaluation_result"]


@pytest.fixture
def bundle(tmp_path: Path) -> RunBundle:
    """A bundle holding the whole fixture corpus, so results can be committed.

    An EvaluationResult names a build, a rotation, a scenario, a gap and a
    rule; a bundle that holds none of them cannot accept one.
    """
    with RunBundle.create(tmp_path / RUN_ID, MANIFEST) as created:
        seed_corpus(created.store, with_results=False)
        yield created


def seed_tasks(bundle: RunBundle, count: int = 3) -> list[str]:
    ids = []
    for i in range(count):
        task_id = "fixture-task-%d" % (i + 1)
        bundle.store.tasks.enqueue(
            task_id=task_id, run_id=RUN_ID, generation_id=1,
            candidate_id="fixture-candidate-%d" % (i + 1),
            payload={"build_hash": RESULT.build_hash,
                     "scenario_id": RESULT.scenario_id})
        ids.append(task_id)
    return ids


def result_for(task_id: str):
    """One distinct evaluation per task; cache keys must stay unique."""
    suffix = task_id.rsplit("-", 1)[-1]
    return replace(RESULT, record_id="fixture-evaluation-%s" % suffix,
                   evaluation_id="fixture-evaluation-%s" % suffix,
                   cache_key=(suffix * 64)[:64])


# ------------------------------------------------------------- state machine

def test_the_five_states_and_their_legal_transitions(bundle: RunBundle):
    tasks = bundle.store.tasks
    [task_id, *_] = seed_tasks(bundle, 1)
    assert tasks.get(task_id).state is TaskState.QUEUED

    tasks.dispatch(task_id, worker_id="worker-1")
    assert tasks.get(task_id).state is TaskState.RUNNING
    assert tasks.get(task_id).attempt == 1

    tasks.fail(task_id, error="SYNTHETIC engine crash")
    assert tasks.get(task_id).state is TaskState.FAILED
    tasks.requeue(task_id, reason="fresh worker attempt")
    assert tasks.get(task_id).state is TaskState.QUEUED

    tasks.dispatch(task_id, worker_id="worker-2")
    assert tasks.get(task_id).attempt == 2
    bundle.store.commit_evaluation(task_id, result_for(task_id))
    assert tasks.get(task_id).state is TaskState.COMPLETED


def test_a_completed_task_cannot_be_moved_again(bundle: RunBundle):
    tasks = bundle.store.tasks
    [task_id] = seed_tasks(bundle, 1)
    tasks.dispatch(task_id, worker_id="worker-1")
    bundle.store.commit_evaluation(task_id, result_for(task_id))
    for move in (lambda: tasks.cancel(task_id),
                 lambda: tasks.fail(task_id, error="late"),
                 lambda: tasks.requeue(task_id, reason="late")):
        with pytest.raises(TaskStateError):
            move()


def test_dispatching_a_task_that_is_already_running_is_refused(bundle):
    tasks = bundle.store.tasks
    [task_id] = seed_tasks(bundle, 1)
    tasks.dispatch(task_id, worker_id="worker-1")
    with pytest.raises(TaskStateError):
        tasks.dispatch(task_id, worker_id="worker-2")


def test_task_identity_is_the_candidate_plus_its_evaluation_context(bundle):
    """Revised after review finding P01-R04.

    This test used to assert that one candidate in one generation could only
    ever have one task, which refused a boss scenario after a clear one.
    Identity is the candidate *and* the context it is evaluated under.
    """
    tasks = bundle.store.tasks
    seed_tasks(bundle, 1)

    # The same task id is still a no-op.
    assert tasks.enqueue(task_id="fixture-task-1", run_id=RUN_ID,
                         generation_id=1, candidate_id="other",
                         payload={}) is False

    # The same candidate with no context key is still one task.
    with pytest.raises(sqlite3.IntegrityError):
        tasks.enqueue(task_id="fixture-task-9", run_id=RUN_ID,
                      generation_id=1, candidate_id="fixture-candidate-1",
                      payload={})

    # The same candidate under a different context is a different task.
    assert tasks.enqueue(task_id="fixture-task-9", run_id=RUN_ID,
                         generation_id=1, candidate_id="fixture-candidate-1",
                         payload={}, context_key="a" * 64) is True
    assert tasks.get("fixture-task-9").context_key == "a" * 64


def test_claim_next_takes_one_task_at_a_time(bundle: RunBundle):
    tasks = bundle.store.tasks
    seed_tasks(bundle, 2)
    first = tasks.claim_next(RUN_ID, worker_id="worker-1")
    second = tasks.claim_next(RUN_ID, worker_id="worker-2")
    assert {first.task_id, second.task_id} == {"fixture-task-1", "fixture-task-2"}
    assert tasks.claim_next(RUN_ID, worker_id="worker-3") is None


# ------------------------------------------------- the four interruptions

def test_interrupted_before_dispatch_the_task_is_dispatched_once(bundle):
    tasks = bundle.store.tasks
    seed_tasks(bundle, 2)
    # The coordinator dies here, having written only the queue.
    plan = resume_plan(tasks, RUN_ID)
    assert plan["recovered_from_running"] == ()
    assert plan["to_dispatch"] == ("fixture-task-1", "fixture-task-2")
    assert plan["already_completed"] == ()


def test_interrupted_after_dispatch_the_attempt_is_recorded_and_requeued(bundle):
    tasks = bundle.store.tasks
    seed_tasks(bundle, 2)
    tasks.dispatch("fixture-task-1", worker_id="worker-1")
    # The coordinator dies with the worker still holding the task.
    plan = resume_plan(tasks, RUN_ID)
    assert plan["recovered_from_running"] == ("fixture-task-1",)
    assert plan["to_dispatch"] == ("fixture-task-1", "fixture-task-2")

    restored = tasks.get("fixture-task-1")
    assert restored.state is TaskState.QUEUED
    assert restored.attempt == 1, "the lost attempt must stay counted"
    assert restored.worker_id is None
    reasons = [e["reason"] for e in tasks.history("fixture-task-1")]
    assert "interrupted attempt 1 returned to the queue" in reasons

    tasks.dispatch("fixture-task-1", worker_id="worker-2")
    assert tasks.get("fixture-task-1").attempt == 2


def test_interrupted_after_the_result_is_written_keeps_it_exactly_once(bundle):
    store, tasks = bundle.store, bundle.store.tasks
    seed_tasks(bundle, 2)
    tasks.dispatch("fixture-task-1", worker_id="worker-1")
    store.commit_evaluation("fixture-task-1", result_for("fixture-task-1"))
    tasks.dispatch("fixture-task-2", worker_id="worker-2")
    # The coordinator dies after task 1's commit and before task 2 finishes.

    plan = resume_plan(tasks, RUN_ID)
    assert plan["already_completed"] == ("fixture-task-1",)
    assert plan["recovered_from_running"] == ("fixture-task-2",)
    assert plan["to_dispatch"] == ("fixture-task-2",)

    # The worker's completion message is delivered again after the restart.
    repeat = store.commit_evaluation("fixture-task-1",
                                     result_for("fixture-task-1"))
    assert repeat.created is False
    assert store.conn.execute(
        "SELECT COUNT(*) FROM evaluation").fetchone()[0] == 1
    assert tasks.completed_evaluation_ids(RUN_ID) == ("fixture-evaluation-1",)


def test_a_task_cannot_claim_two_different_results(bundle: RunBundle):
    from pob2opt.storage import StorageError

    store, tasks = bundle.store, bundle.store.tasks
    seed_tasks(bundle, 1)
    tasks.dispatch("fixture-task-1", worker_id="worker-1")
    store.commit_evaluation("fixture-task-1", result_for("fixture-task-1"))
    with pytest.raises(StorageError, match="already completed"):
        store.commit_evaluation("fixture-task-1", result_for("fixture-task-2"))


def test_an_engine_timeout_is_a_failed_attempt_not_a_zero_score(bundle):
    store, tasks = bundle.store, bundle.store.tasks
    seed_tasks(bundle, 1)
    tasks.dispatch("fixture-task-1", worker_id="worker-1")
    tasks.fail("fixture-task-1", error="timeout after 120s")
    assert tasks.get("fixture-task-1").state is TaskState.FAILED
    assert store.conn.execute(
        "SELECT COUNT(*) FROM evaluation").fetchone()[0] == 0
    assert tasks.counts(RUN_ID)["completed"] == 0


def test_interrupted_before_the_checkpoint_is_replaced(bundle: RunBundle):
    """The database is authoritative; the stale checkpoint is not a second
    opinion."""
    store, tasks = bundle.store, bundle.store.tasks
    seed_tasks(bundle, 2)

    stale = replace(R["checkpoint"], manifest_hash=bundle.manifest_hash,
                    completed_generation=0, completed_task_ids=[],
                    queued_task_ids=["fixture-task-1", "fixture-task-2"],
                    next_generation_id=1)
    write_checkpoint(bundle.root, stale)

    tasks.dispatch("fixture-task-1", worker_id="worker-1")
    store.commit_evaluation("fixture-task-1", result_for("fixture-task-1"))
    # The newer checkpoint is never written.

    on_disk = read_checkpoint(bundle.root)
    assert on_disk.completed_task_ids == []
    plan = resume_plan(tasks, RUN_ID)
    assert plan["already_completed"] == ("fixture-task-1",)
    assert "fixture-task-1" not in plan["to_dispatch"]


# ------------------------------------------------------------- checkpoints

def test_a_checkpoint_is_replaced_atomically(bundle: RunBundle):
    checkpoint = replace(R["checkpoint"], manifest_hash=bundle.manifest_hash)
    path = write_checkpoint(bundle.root, checkpoint)
    assert path.name == CHECKPOINT_NAME
    assert list(bundle.root.glob("*.writing")) == []

    newer = replace(checkpoint, completed_generation=2, next_generation_id=3,
                    stop_status=StopStatus.CONVERGED)
    write_checkpoint(bundle.root, newer)
    assert read_checkpoint(bundle.root).completed_generation == 2
    assert list(bundle.root.glob("*.writing")) == []


def test_a_checkpoint_from_another_manifest_is_rejected(bundle: RunBundle):
    foreign = replace(R["checkpoint"], manifest_hash="f" * 64)
    with pytest.raises(CheckpointMismatch) as exc:
        validate_checkpoint(foreign, manifest_hash=bundle.manifest_hash)
    assert exc.value.found == "f" * 64

    right = replace(R["checkpoint"], manifest_hash=bundle.manifest_hash)
    assert validate_checkpoint(right, manifest_hash=bundle.manifest_hash,
                               run_id=RUN_ID) is None

    with pytest.raises(CheckpointMismatch):
        validate_checkpoint(right, manifest_hash=bundle.manifest_hash,
                            run_id="some-other-run")


def test_changing_the_manifest_invalidates_its_checkpoints(bundle: RunBundle):
    checkpoint = replace(R["checkpoint"], manifest_hash=bundle.manifest_hash)
    edited = replace(MANIFEST, rng_seed=7)
    with pytest.raises(CheckpointMismatch):
        validate_checkpoint(checkpoint, manifest_hash=manifest_hash(edited))


def test_a_missing_checkpoint_is_a_typed_error(bundle: RunBundle):
    with pytest.raises(RecordNotFound):
        read_checkpoint(bundle.root)


def test_a_reopened_bundle_refuses_an_edited_manifest_file(bundle: RunBundle):
    root = bundle.root
    bundle.close()
    payload = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    payload["rng_seed"] = 999
    (root / "manifest.json").write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(CheckpointMismatch):
        RunBundle.open(root)


# -------------------------------------------------- reviewer inspection

def test_every_documented_query_runs_against_a_real_run(bundle: RunBundle):
    store, tasks = bundle.store, bundle.store.tasks
    seed_tasks(bundle, 3)
    tasks.dispatch("fixture-task-1", worker_id="worker-1")
    store.commit_evaluation("fixture-task-1", result_for("fixture-task-1"))
    tasks.dispatch("fixture-task-2", worker_id="worker-2")
    tasks.fail("fixture-task-2", error="SYNTHETIC engine crash")
    store.put_gap(R["data_gap"])

    results = run_all(store.conn)
    assert set(results) == set(QUERIES)
    counts = {row["state"]: row["tasks"]
              for row in results["task_counts_by_state"]}
    assert counts == {"completed": 1, "failed": 1, "queued": 1}
    assert results["duplicate_evaluations_by_cache_key"] == []
    assert results["orphan_blob_rows"] == []
    assert [r["gap_id"] for r in results["open_blocking_gaps"]] == ["fixture-gap-1"]
    assert len(results["task_history"]) >= 6


def test_the_inspection_queries_are_read_only():
    for name, sql in QUERIES.items():
        assert sql.lstrip().upper().startswith("SELECT"), name


def test_duplicate_results_are_impossible_at_the_schema_level(bundle):
    """The duplicate query is a check, not the defence: the index is."""
    store = bundle.store
    store.commit_evaluation(None, result_for("fixture-task-1"))
    assert run_query(store.conn, "duplicate_evaluations_by_cache_key") == []

    cache_key = result_for("fixture-task-1").cache_key
    with pytest.raises(sqlite3.IntegrityError, match="cache_key"):
        store.conn.execute(
            "INSERT INTO evaluation (evaluation_id, cache_key, build_hash,"
            " rotation_hash, scenario_id, manifest_id, fidelity, seed, status,"
            " created_at, json) VALUES ('other', ?, 'b', 'r', 's', 'm',"
            " 'detailed', 1, 'ok', '2026-10-04T00:00:00Z', '{}')", (cache_key,))
