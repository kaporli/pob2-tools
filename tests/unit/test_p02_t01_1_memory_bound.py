"""P02-T01.1 worker memory bound and replacement, offline (synthetic workers, no PoB).

Every worker is ``tests/synthetic_workers.py`` allocating Python memory on
request. Nothing here is engine output. The real-engine counterpart is
``tests/engine/test_p02_t01_1_memory_bound.py``.
"""

from __future__ import annotations

import dataclasses
import os

import pytest

from record_fixtures import records

from pob2opt.domain.enums import ResultStatus
from pob2opt.evaluation import (ADAPTER_VERSION, CheckoutIdentity, EngineAdapter,
                                EngineCrash, EngineMemoryLimit,
                                EngineReplacementExhausted, EngineState,
                                EngineUnsupported, MappingBuildDocuments,
                                WorkerSpec)
from pob2opt.evaluation import adapter as adapter_module
from pob2opt.evaluation.memory import probe_available, process_memory_bytes

ENTRY = "synthetic_workers:SyntheticSession"
COMMIT = "1" * 40
MB = 2**20

pytestmark = pytest.mark.skipif(not probe_available(),
                                reason="no worker memory probe on this platform")


def make_adapter(*, memory_limit_bytes=None, recycle_after_bytes=None,
                 max_requests_per_worker=None, max_consecutive_failures=None,
                 **config) -> EngineAdapter:
    spec = WorkerSpec(entry=ENTRY, quiet=True, extra=config)
    return EngineAdapter(
        spec, checkout=CheckoutIdentity(root="SYNTHETIC-NOT-POB", commit=COMMIT,
                                        dirty_hash=None, reason=None),
        screen_timeout_s=30.0, detailed_timeout_s=30.0, start_timeout_s=60.0,
        memory_limit_bytes=memory_limit_bytes,
        recycle_after_bytes=recycle_after_bytes,
        max_requests_per_worker=max_requests_per_worker,
        max_consecutive_failures=max_consecutive_failures)


@pytest.fixture()
def build():
    return records()["build_spec"]


@pytest.fixture()
def profile():
    return dataclasses.replace(records()["patch_profile"], pob_commit=COMMIT,
                               adapter_version=ADAPTER_VERSION)


@pytest.fixture()
def documents(build):
    return MappingBuildDocuments({build.build_hash: "<SyntheticBuild/>"})


PLAIN = EngineState(config={"setting": 7})
GROW = EngineState(config={"setting": 7, "grow": 1})


@pytest.fixture()
def reference(build, profile, documents):
    """What a fresh, never-limited worker answers for PLAIN."""
    with make_adapter() as fresh:
        fresh.documents = documents
        return fresh.primitives(build, PLAIN, profile).values


def test_the_probe_reads_this_process():
    assert process_memory_bytes(os.getpid()) > 10 * MB


def test_a_runaway_worker_is_killed_at_the_limit_with_a_typed_error(
        build, profile, documents, reference):
    with make_adapter(memory_limit_bytes=400 * MB, grow_on="primitives",
                      grow_key="grow", grow_forever=True, grow_mb=16) as adapter:
        adapter.documents = documents
        with pytest.raises(EngineMemoryLimit) as excinfo:
            adapter.primitives(build, GROW, profile)
        error = excinfo.value
        assert isinstance(error, EngineCrash)
        assert error.status is ResultStatus.ENGINE_CRASH
        assert error.observed_bytes > error.limit_bytes == 400 * MB
        assert "limit" in error.as_error_detail().diagnostic
        assert not adapter.worker_alive
        killed = adapter.worker_pids[0]

        after = adapter.primitives(build, PLAIN, profile)
        assert after.identity.worker_pid != killed
        assert after.values == reference
        assert adapter.replacements == 1
        assert "memory" in adapter.worker_history[0]["end"]
        assert adapter.worker_history[0]["peak_memory_bytes"] > 400 * MB


def test_a_worker_past_the_soft_limit_finishes_then_is_replaced(
        build, profile, documents, reference):
    with make_adapter(recycle_after_bytes=200 * MB, grow_on="primitives",
                      grow_key="grow", grow_mb=300) as adapter:
        adapter.documents = documents
        grown = adapter.primitives(build, GROW, profile)
        first = grown.identity.worker_pid
        assert adapter.worker_alive  # the answer was delivered, nothing killed

        after = adapter.primitives(build, PLAIN, profile)
        assert after.identity.worker_pid != first
        assert after.document.reloaded is True
        assert after.values == reference
        assert adapter.recycles == 1
        assert adapter.replacements == 0
        assert adapter.worker_history[0]["end"].startswith("recycled: memory")


def test_one_evaluation_never_spans_two_workers(build, profile, documents):
    """The load pushes the worker past the soft limit; the read still uses it."""
    with make_adapter(recycle_after_bytes=200 * MB, grow_on="load_exact_build",
                      grow_mb=300) as adapter:
        adapter.documents = documents
        snapshot = adapter.primitives(build, PLAIN, profile)
        assert adapter.worker_pids == [snapshot.identity.worker_pid]
        assert adapter.recycles == 0

        again = adapter.primitives(build, PLAIN, profile)
        assert again.identity.worker_pid != snapshot.identity.worker_pid
        assert again.values == snapshot.values
        assert adapter.recycles == 1


def test_a_request_budget_recycles_the_worker(build, profile, documents, reference):
    with make_adapter(max_requests_per_worker=3) as adapter:
        adapter.documents = documents
        first = adapter.primitives(build, PLAIN, profile)  # load, read, describe
        second = adapter.primitives(build, PLAIN, profile)
        assert second.identity.worker_pid != first.identity.worker_pid
        assert first.values == second.values == reference
        assert adapter.worker_history[0]["end"] == "recycled: 3 requests served"


def test_consecutive_losses_stop_further_replacement(build, profile, documents):
    with make_adapter(max_consecutive_failures=2, behavior="die",
                      die_on="primitives") as adapter:
        adapter.documents = documents
        for _ in range(2):
            with pytest.raises(EngineCrash) as excinfo:
                adapter.primitives(build, PLAIN, profile)
            assert not isinstance(excinfo.value, EngineReplacementExhausted)
        spawned = list(adapter.worker_pids)

        with pytest.raises(EngineReplacementExhausted) as excinfo:
            adapter.primitives(build, PLAIN, profile)
        assert excinfo.value.status is ResultStatus.ENGINE_CRASH
        assert adapter.worker_pids == spawned  # no third worker was started


def test_a_success_resets_the_loss_count(build, profile, documents):
    with make_adapter(max_consecutive_failures=2, memory_limit_bytes=300 * MB,
                      grow_on="primitives", grow_key="grow", grow_forever=True,
                      grow_mb=16) as adapter:
        adapter.documents = documents
        for state in (GROW, PLAIN, GROW, PLAIN):
            if state is GROW:
                with pytest.raises(EngineMemoryLimit):
                    adapter.primitives(build, state, profile)
            else:
                adapter.primitives(build, state, profile)
        assert adapter.consecutive_failures == 0
        assert len(adapter.worker_pids) == 3


def test_a_bound_without_a_probe_is_refused(monkeypatch):
    monkeypatch.setattr(adapter_module, "PROBE", None)
    with pytest.raises(EngineUnsupported):
        make_adapter(memory_limit_bytes=400 * MB)
    make_adapter().close()  # explicitly unbounded is still allowed


def test_the_defaults_bound_every_worker():
    adapter = EngineAdapter(WorkerSpec(entry=ENTRY),
                            checkout=CheckoutIdentity(root="x", commit=COMMIT,
                                                      dirty_hash=None, reason=None))
    assert adapter.memory_limit_bytes is not None
    assert adapter.recycle_after_bytes is not None
    assert adapter.recycle_after_bytes < adapter.memory_limit_bytes
    assert adapter.max_consecutive_failures is not None
