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
                                BuildDocument, EngineCrash, EngineInternalError,
                                EngineInvalidInput, EngineMemoryLimit,
                                EngineReplacementExhausted, EngineState,
                                EngineTimeout, EngineUnsupported, MappingBuildDocuments,
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


def test_fast_allocation_reply_cannot_bypass_the_hard_limit(monkeypatch):
    # Force the wait to see the reply before its periodic memory sample.
    monkeypatch.setattr(adapter_module.protocol, "MEMORY_POLL_S", 30.0)
    with make_adapter(memory_limit_bytes=200 * MB, grow_on="describe",
                      grow_mb=200) as adapter:
        with pytest.raises(EngineMemoryLimit) as error:
            adapter.identity()
        assert error.value.stage == "describe"
        assert not adapter.worker_alive
        assert adapter.worker_history[0]["peak_memory_bytes"] > 200 * MB


@pytest.mark.parametrize("stage", ["startup", "describe", "load_exact_build"])
def test_ready_and_error_replies_are_checked(monkeypatch, stage):
    original = adapter_module.WorkerHandle._wait

    def wait(handle, timeout_s, *, stage):
        ready = original(handle, timeout_s, stage=stage)
        if ready and stage == target_stage:
            monkeypatch.setattr(adapter_module, "process_memory_bytes",
                                lambda pid: 500 * MB)
        return ready

    target_stage = stage
    monkeypatch.setattr(adapter_module.WorkerHandle, "_wait", wait)
    with make_adapter(memory_limit_bytes=400 * MB) as adapter:
        with pytest.raises(EngineMemoryLimit) as error:
            if stage == "load_exact_build":
                adapter.load_exact_build(BuildDocument("synthetic", ""))
            else:
                adapter.identity()
        assert error.value.stage == stage
        assert adapter.consecutive_failures == 1
        assert len(adapter.worker_history) == len(adapter.worker_pids) == 1


def test_cached_identity_does_not_bypass_memory_check(monkeypatch):
    with make_adapter(memory_limit_bytes=400 * MB) as adapter:
        adapter.identity()
        monkeypatch.setattr(adapter_module, "process_memory_bytes", lambda pid: 500 * MB)
        with pytest.raises(EngineMemoryLimit):
            adapter.identity()
        assert not adapter.worker_alive
        assert adapter.consecutive_failures == 1


@pytest.mark.parametrize("behavior", ["startup", "handler"])
def test_all_fatal_losses_exhaust_budget_and_retain_history(behavior):
    config = {"behavior": "startup_fail"} if behavior == "startup" else {"values": 3}
    with make_adapter(max_consecutive_failures=2, **config) as adapter:
        for count in (1, 2):
            with pytest.raises(EngineInternalError):
                adapter.probe(BuildDocument("synthetic", "<SyntheticBuild/>"))
            assert adapter.consecutive_failures == count
            assert len(adapter.worker_history) == len(adapter.worker_pids) == count
            assert adapter.worker_history[-1]["pid"] == adapter.worker_pids[-1]
            assert "fatal" in adapter.worker_history[-1]["end"]
        for _ in range(2):
            with pytest.raises(EngineReplacementExhausted, match="fatal"):
                adapter.identity()
        assert len(adapter.worker_pids) == 2
        assert len(adapter.worker_history) == 2
    assert len(adapter.worker_history) == 2  # closing cannot duplicate history


def test_startup_memory_losses_retain_peak_and_reason(monkeypatch):
    monkeypatch.setattr(adapter_module, "process_memory_bytes", lambda pid: 500 * MB)
    with make_adapter(memory_limit_bytes=400 * MB, max_consecutive_failures=2) as adapter:
        for count in (1, 2):
            with pytest.raises(EngineMemoryLimit):
                adapter.identity()
            assert adapter.consecutive_failures == count
            assert len(adapter.worker_history) == count
            assert adapter.worker_history[-1]["peak_memory_bytes"] == 500 * MB
        with pytest.raises(EngineReplacementExhausted, match="memory"):
            adapter.identity()
        assert len(adapter.worker_pids) == 2


@pytest.mark.parametrize("bound", ["memory_limit_bytes", "recycle_after_bytes"])
@pytest.mark.parametrize("stage", ["startup", "reuse", "wait", "reply"])
def test_missing_memory_observation_fails_closed(monkeypatch, bound, stage):
    # Import locally so this regression can also run against the reviewed head.
    with make_adapter(**{bound: 400 * MB}, slow_on="describe", slow_s=0.3,
                      max_consecutive_failures=1) as adapter:
        if stage != "startup":
            adapter.identity()
            handle = adapter._handle
            old_peak = handle.peak_memory_bytes
        if stage in ("startup", "reuse"):
            monkeypatch.setattr(adapter_module, "process_memory_bytes", lambda pid: None)
        else:
            original = adapter_module.WorkerHandle._wait

            def wait(handle, timeout_s, *, stage):
                if target == "wait":
                    monkeypatch.setattr(adapter_module, "process_memory_bytes", lambda pid: None)
                ready = original(handle, timeout_s, stage=stage)
                if target == "reply":
                    monkeypatch.setattr(adapter_module, "process_memory_bytes", lambda pid: None)
                return ready

            target = stage
            monkeypatch.setattr(adapter_module.WorkerHandle, "_wait", wait)
        with pytest.raises(EngineCrash) as error:
            if stage in ("wait", "reply"):
                adapter._request("describe", {}, 3.0)
            else:
                adapter.identity()
        assert type(error.value).__name__ == "EngineMemoryProbeError"
        assert error.value.status is ResultStatus.ENGINE_CRASH
        assert not adapter.worker_alive
        assert adapter._handle.last_memory_bytes is None
        if stage != "startup":
            assert adapter._handle.peak_memory_bytes >= old_peak
        assert adapter.consecutive_failures == 1
        assert len(adapter.worker_history) == 1
        with pytest.raises(EngineReplacementExhausted, match="probe unavailable"):
            adapter.identity()


def test_explicitly_unbounded_worker_tolerates_missing_probe(monkeypatch):
    monkeypatch.setattr(adapter_module, "process_memory_bytes", lambda pid: None)
    with make_adapter() as adapter:
        assert adapter.probe(BuildDocument("synthetic", "<SyntheticBuild/>"))
        assert adapter.worker_alive


def test_shutdown_does_not_require_a_memory_sample(monkeypatch):
    adapter = make_adapter(memory_limit_bytes=400 * MB)
    adapter.identity()
    monkeypatch.setattr(adapter_module, "process_memory_bytes", lambda pid: None)
    adapter.close()
    assert adapter.worker_history[0]["end"] == "closed"
    assert adapter.consecutive_failures == 0


def test_live_nonfatal_errors_do_not_exhaust_failure_budget():
    with make_adapter(max_consecutive_failures=1) as adapter:
        for _ in range(3):
            with pytest.raises(EngineInvalidInput):
                adapter.load_exact_build(BuildDocument("synthetic", ""))
        assert adapter.worker_alive
        assert adapter.consecutive_failures == 0
        assert adapter.worker_history == []
        assert len(adapter.worker_pids) == 1


def test_startup_timeouts_are_counted_and_recorded():
    with make_adapter(startup_s=5.0, max_consecutive_failures=2) as adapter:
        adapter.start_timeout_s = 0.2
        for count in (1, 2):
            with pytest.raises(EngineTimeout):
                adapter.identity()
            assert adapter.consecutive_failures == count
            assert len(adapter.worker_history) == len(adapter.worker_pids) == count
        with pytest.raises(EngineReplacementExhausted, match="no answer"):
            adapter.identity()


def test_dead_process_is_not_reported_as_a_live_probe_failure(monkeypatch):
    with make_adapter(memory_limit_bytes=400 * MB) as adapter:
        adapter.identity()
        handle = adapter._handle
        handle.process.kill()
        handle.process.join(5)
        monkeypatch.setattr(adapter_module, "process_memory_bytes", lambda pid: None)
        with pytest.raises(EngineCrash) as error:
            adapter._request("describe", {}, 3.0)
        assert type(error.value) is EngineCrash
        assert adapter.consecutive_failures == 1
        assert len(adapter.worker_history) == 1
