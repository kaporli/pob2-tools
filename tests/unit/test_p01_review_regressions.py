"""The five defects the P01 review found, each with the probe that found it.

`docs/reviews/P01.md` and `docs/evidence/P01/review-ae4303e.json`. Every test
here fails against the reviewed revision `ae4303e` and passes now. The probes
go through the public API, not through the helper that produced the original
value.
"""

from __future__ import annotations

import math
import sqlite3
from dataclasses import replace
from pathlib import Path

import pytest

from record_fixtures import blob_payloads, records, seed_corpus

from pob2opt.domain import (
    AggregateComponent,
    AggregateKey,
    EvaluationKey,
    RECORD_TYPES,
    RecordIndex,
    from_jsonable,
    rotation_hash,
    scenario_hash,
    to_jsonable,
    validate_record,
)
from pob2opt.domain.enums import Fidelity, TaskState
from pob2opt.storage import (
    IncompleteBundle,
    RunBundle,
    RunStore,
    StaleAttempt,
    TaskResultMismatch,
    TaskStateError,
)

R = records()
MANIFEST = R["run_manifest"]
RUN_ID = MANIFEST.run_id


@pytest.fixture
def bundle(tmp_path: Path) -> RunBundle:
    with RunBundle.create(tmp_path / RUN_ID, MANIFEST) as created:
        seed_corpus(created.store, with_results=False)
        yield created


def evaluation_key(fidelity: Fidelity = Fidelity.DETAILED) -> EvaluationKey:
    return EvaluationKey.from_manifest(
        MANIFEST, build_hash=R["build_spec"].build_hash,
        rotation_hash=rotation_hash(R["rotation_policy"]),
        scenario_hash=scenario_hash(R["scenario_spec"]), fidelity=fidelity)


# ===================================================================== R01

def test_a_cancelled_task_is_not_completed_by_a_late_result(bundle: RunBundle):
    """The reviewer cancelled a task, delivered its result, and watched the
    state change from cancelled to completed."""
    store, tasks = bundle.store, bundle.store.tasks
    tasks.enqueue(task_id="cancelled-task", run_id=RUN_ID, generation_id=1,
                  candidate_id="candidate-a", payload={})
    tasks.dispatch("cancelled-task", worker_id="old-worker")
    tasks.cancel("cancelled-task")

    with pytest.raises(TaskStateError):
        store.commit_evaluation("cancelled-task", R["evaluation_result"])

    assert tasks.get("cancelled-task").state is TaskState.CANCELLED
    # Refused atomically: no evaluation row was left behind.
    assert store.conn.execute(
        "SELECT COUNT(*) FROM evaluation").fetchone()[0] == 0


@pytest.mark.parametrize("state", ["queued", "failed", "cancelled"])
def test_only_a_running_task_may_complete(bundle: RunBundle, state: str):
    store, tasks = bundle.store, bundle.store.tasks
    tasks.enqueue(task_id="t", run_id=RUN_ID, generation_id=1,
                  candidate_id="c", payload={})
    if state != "queued":
        tasks.dispatch("t", worker_id="w")
        tasks.fail("t", error="x") if state == "failed" else tasks.cancel("t")

    with pytest.raises(TaskStateError) as exc:
        store.commit_evaluation("t", R["evaluation_result"])
    assert exc.value.current == state
    assert tasks.get("t").state is TaskState(state)
    assert store.conn.execute(
        "SELECT COUNT(*) FROM evaluation").fetchone()[0] == 0


def test_a_running_task_completes_and_an_exact_retry_is_a_no_op(bundle):
    store, tasks = bundle.store, bundle.store.tasks
    tasks.enqueue(task_id="t", run_id=RUN_ID, generation_id=1,
                  candidate_id="c", payload={})
    tasks.dispatch("t", worker_id="w")
    first = store.commit_evaluation("t", R["evaluation_result"])
    second = store.commit_evaluation("t", R["evaluation_result"])
    assert first.created is True and second.created is False
    assert tasks.get("t").state is TaskState.COMPLETED
    assert store.conn.execute(
        "SELECT COUNT(*) FROM evaluation").fetchone()[0] == 1


def test_a_different_result_for_a_completed_task_is_refused(bundle):
    store, tasks = bundle.store, bundle.store.tasks
    tasks.enqueue(task_id="t", run_id=RUN_ID, generation_id=1,
                  candidate_id="c", payload={})
    tasks.dispatch("t", worker_id="w")
    store.commit_evaluation("t", R["evaluation_result"])

    other = replace(R["evaluation_result"], record_id="fixture-evaluation-2",
                    evaluation_id="fixture-evaluation-2", cache_key="b" * 64)
    with pytest.raises(TaskResultMismatch, match="already completed"):
        store.commit_evaluation("t", other)
    assert store.conn.execute(
        "SELECT COUNT(*) FROM evaluation").fetchone()[0] == 1


def test_a_task_bound_to_a_context_refuses_an_unrelated_result(bundle):
    """"Validate the task/result association", not merely that the id exists."""
    store, tasks = bundle.store, bundle.store.tasks
    boss_key = replace(evaluation_key(), scenario_hash="c" * 64)
    tasks.enqueue(task_id="boss", run_id=RUN_ID, generation_id=1,
                  candidate_id="c", payload={},
                  context_key=boss_key.cache_key())
    tasks.dispatch("boss", worker_id="w")

    with pytest.raises(TaskResultMismatch, match="cache key"):
        store.commit_evaluation("boss", R["evaluation_result"])
    assert tasks.get("boss").state is TaskState.RUNNING
    assert store.conn.execute(
        "SELECT COUNT(*) FROM evaluation").fetchone()[0] == 0

    matching = replace(R["evaluation_result"], cache_key=boss_key.cache_key())
    assert store.commit_evaluation("boss", matching).created is True


def test_a_result_from_a_superseded_attempt_is_rejected(bundle: RunBundle):
    """What a worker that outlived a recovery delivers."""
    store, tasks = bundle.store, bundle.store.tasks
    tasks.enqueue(task_id="t", run_id=RUN_ID, generation_id=1,
                  candidate_id="c", payload={})
    tasks.dispatch("t", worker_id="worker-1")
    tasks.recover(RUN_ID)
    tasks.dispatch("t", worker_id="worker-2")
    assert tasks.get("t").attempt == 2

    with pytest.raises(StaleAttempt) as exc:
        store.commit_evaluation("t", R["evaluation_result"], attempt=1)
    assert (exc.value.reported, exc.value.current) == (1, 2)
    assert tasks.get("t").state is TaskState.RUNNING

    assert store.commit_evaluation(
        "t", R["evaluation_result"], attempt=2).created is True


# ===================================================================== R02

def test_a_null_in_a_free_form_field_survives_the_round_trip(tmp_path: Path):
    """The reviewer stored an item it could then not read back."""
    item = R["item_instance"]
    unknown = replace(item, record_id="fixture-item-null",
                      properties={**item.properties, "unknown_property": None})
    assert validate_record(unknown).ok

    with RunStore.open_corpus(tmp_path / "corpus") as corpus:
        seed_corpus(corpus, with_results=False)
        corpus.put_normalized(unknown)
        read_back = corpus.get_normalized(unknown.record_id)
    assert read_back.properties["unknown_property"] is None
    assert read_back == unknown


@pytest.mark.parametrize("value", [None, 0, False, "", [], {}])
def test_every_json_value_survives_a_free_form_field(value):
    item = R["item_instance"]
    stored = replace(item, properties={**item.properties, "probe": value})
    payload = to_jsonable(stored)
    assert payload["properties"]["probe"] == value
    decoded = from_jsonable(RECORD_TYPES["item_instance"], payload)
    assert decoded.properties["probe"] == value
    assert type(decoded.properties["probe"]) is type(value)


def test_a_non_nullable_field_still_rejects_null():
    payload = to_jsonable(R["item_instance"])
    payload["rarity"] = None
    report = validate_record(payload, kind="item_instance")
    assert not report.ok
    assert "/rarity" in report.paths()


def test_nan_in_a_free_form_field_is_still_refused():
    item = R["item_instance"]
    stored = replace(item, properties={**item.properties, "probe": math.nan})
    report = validate_record(stored)
    assert "not_a_number" in report.codes()
    assert report.paths() == ("/properties/probe",)


def test_a_wire_value_in_a_dataclass_does_not_escape_as_an_attribute_error():
    """``status="ok"`` used to reach the semantic pass and raise."""
    broken = replace(R["evaluation_result"], status="ok")
    report = validate_record(broken)
    assert report.ok
    # Semantics ran against a decoded record, and the report hands back the
    # properly typed instance rather than the hand-built one.
    assert report.record.status is R["evaluation_result"].status
    assert report.record == R["evaluation_result"]


def test_an_undecodable_value_is_a_report_not_an_exception():
    broken = replace(R["evaluation_result"], status="not_a_status")
    report = validate_record(broken)
    assert not report.ok
    assert "/status" in report.paths()
    assert all(error.field_path.startswith("/") for error in report.errors)


def test_storage_persists_the_decoded_record(tmp_path: Path):
    with RunStore.open_corpus(tmp_path / "corpus") as corpus:
        seed_corpus(corpus, with_results=False)
        loose = replace(R["evaluation_result"], status="ok")
        corpus.commit_evaluation(None, loose)
        stored = corpus.evaluation_by_cache_key(loose.cache_key)
    assert stored == R["evaluation_result"]
    assert stored.status is R["evaluation_result"].status


# ===================================================================== R03

def test_an_incomplete_bundle_is_not_readable(tmp_path: Path):
    with RunStore.open_corpus(tmp_path / "corpus") as corpus:
        corpus.put_normalized(R["build_spec"], require_references=False)
        with RunBundle.create(tmp_path / "run", MANIFEST) as made:
            made.copy_references(corpus, normalized_ids=["fixture-build-1"],
                                 transitive=False)
            check = made.self_check()
            assert check["readable"] is False
            assert check["unresolved_references"]
            with pytest.raises(IncompleteBundle):
                made.require_readable()


# ===================================================================== R04

def test_one_candidate_can_carry_a_clear_and_a_boss_task(bundle: RunBundle):
    """The reviewer queued two scenarios for one candidate and hit UNIQUE."""
    tasks = bundle.store.tasks
    clear = evaluation_key()
    boss = replace(clear, scenario_hash="c" * 64)

    assert tasks.enqueue(task_id="clear-task", run_id=RUN_ID, generation_id=2,
                         candidate_id="same-build", payload={},
                         context_key=clear.cache_key())
    assert tasks.enqueue(task_id="boss-task", run_id=RUN_ID, generation_id=2,
                         candidate_id="same-build", payload={},
                         context_key=boss.cache_key())
    assert len(tasks.by_state(RUN_ID, TaskState.QUEUED)) == 2


def test_one_candidate_can_carry_a_screen_and_a_detailed_task(bundle):
    tasks = bundle.store.tasks
    for name, fidelity in (("screen", Fidelity.SCREEN),
                           ("detailed", Fidelity.DETAILED)):
        assert tasks.enqueue(
            task_id="%s-task" % name, run_id=RUN_ID, generation_id=2,
            candidate_id="same-build", payload={},
            context_key=evaluation_key(fidelity).cache_key())
    assert len(tasks.by_state(RUN_ID, TaskState.QUEUED)) == 2


def test_one_candidate_can_carry_several_seeds(bundle: RunBundle):
    tasks = bundle.store.tasks
    for seed in (1, 2, 3):
        assert tasks.enqueue(
            task_id="seed-%d" % seed, run_id=RUN_ID, generation_id=2,
            candidate_id="same-build", payload={},
            context_key=replace(evaluation_key(), seed=seed).cache_key())
    assert len(tasks.by_state(RUN_ID, TaskState.QUEUED)) == 3


def test_the_same_context_for_one_candidate_is_still_refused(bundle):
    """Relaxing the index must not let one evaluation be queued twice."""
    tasks = bundle.store.tasks
    context = evaluation_key().cache_key()
    tasks.enqueue(task_id="first", run_id=RUN_ID, generation_id=2,
                  candidate_id="same-build", payload={}, context_key=context)
    with pytest.raises(sqlite3.IntegrityError):
        tasks.enqueue(task_id="second", run_id=RUN_ID, generation_id=2,
                      candidate_id="same-build", payload={},
                      context_key=context)


def test_repeating_a_task_id_is_still_idempotent(bundle: RunBundle):
    tasks = bundle.store.tasks
    assert tasks.enqueue(task_id="t", run_id=RUN_ID, generation_id=1,
                         candidate_id="c", payload={}) is True
    assert tasks.enqueue(task_id="t", run_id=RUN_ID, generation_id=1,
                         candidate_id="c", payload={}) is False


def test_recovery_preserves_every_completed_evaluation(bundle: RunBundle):
    """Several tasks for one candidate, one finished, the rest recovered."""
    store, tasks = bundle.store, bundle.store.tasks
    clear = evaluation_key()
    boss = replace(clear, scenario_hash="c" * 64)
    tasks.enqueue(task_id="clear-task", run_id=RUN_ID, generation_id=2,
                  candidate_id="same-build", payload={},
                  context_key=clear.cache_key())
    tasks.enqueue(task_id="boss-task", run_id=RUN_ID, generation_id=2,
                  candidate_id="same-build", payload={},
                  context_key=boss.cache_key())

    tasks.dispatch("clear-task", worker_id="w1")
    store.commit_evaluation("clear-task",
                            replace(R["evaluation_result"],
                                    cache_key=clear.cache_key()))
    tasks.dispatch("boss-task", worker_id="w2")

    assert tasks.recover(RUN_ID) == ("boss-task",)
    assert tasks.get("clear-task").state is TaskState.COMPLETED
    assert tasks.get("boss-task").state is TaskState.QUEUED
    assert tasks.completed_evaluation_ids(RUN_ID) == ("fixture-evaluation-1",)


# ===================================================================== R05

def components(manifest=MANIFEST, **overrides):
    return [AggregateComponent.of(
        "fixture-clear-dense",
        replace(EvaluationKey.from_manifest(
            manifest, build_hash=R["build_spec"].build_hash,
            rotation_hash=rotation_hash(R["rotation_policy"]),
            scenario_hash=scenario_hash(R["scenario_spec"]),
            fidelity=Fidelity.DETAILED), **overrides))]


def aggregate_key(manifest=MANIFEST, **overrides) -> str:
    return AggregateKey.from_components(
        manifest, build_hash=R["build_spec"].build_hash,
        rotation_hash=rotation_hash(R["rotation_policy"]),
        components=components(manifest, **overrides)).cache_key()


def test_the_run_seed_collision_the_reviewer_found_is_gone():
    other = replace(MANIFEST, rng_seed=MANIFEST.rng_seed + 1)
    assert aggregate_key(other) != aggregate_key()


@pytest.mark.parametrize("overrides", [
    {"scenario_hash": "c" * 64},
    {"rotation_hash": "d" * 64},
    {"fidelity": Fidelity.SCREEN},
    {"seed": 99},
    {"calibration_hash": "e" * 64},
    {"catalog_hash": "f" * 64},
    {"pob_commit": "1" * 40},
    {"mechanics_registry_hash": "9" * 64},
    {"evaluator_version": "other"},
], ids=lambda o: ",".join(o))
def test_any_evaluation_dependency_moves_the_aggregate_key(overrides):
    assert aggregate_key(**overrides) != aggregate_key()
