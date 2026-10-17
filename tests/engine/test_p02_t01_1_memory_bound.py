"""P02-T01.1: the worker memory bound against the real PoB engine.

Each bound is set where a real worker always crosses it, so every case is
deterministic: a hard limit below PoB's boot footprint, a one-byte recycle
threshold and a small request budget. The intermittent runaway itself is
reproduced by ``docs/evidence/P02-T01.1``; it is not reliable enough to be a
test.
"""

from __future__ import annotations

import math
import os
import subprocess
import sys
from pathlib import Path

import pytest

from pob2opt.domain.enums import ResultStatus
from pob2opt.evaluation import (BuildDocument, EngineAdapter, EngineMemoryLimit,
                                EngineReplacementExhausted, pob_worker_spec)
from pob2opt.evaluation.memory import probe_available

pytestmark = [pytest.mark.engine,
              pytest.mark.skipif(not probe_available(),
                                 reason="no worker memory probe on this platform")]

START_TIMEOUT_S = 600.0
REQUEST_TIMEOUT_S = 300.0
MB = 2**20


def assert_same(a: dict, b: dict) -> None:
    """P02-T01 tolerance: 1e-6 relative or 1e-9 absolute; NaN equals NaN."""
    assert a.keys() == b.keys()
    for key in a:
        x, y = a[key], b[key]
        if isinstance(x, float) and isinstance(y, float):
            if math.isnan(x) or math.isnan(y):
                assert math.isnan(x) and math.isnan(y), key
                continue
            assert x == pytest.approx(y, rel=1e-6, abs=1e-9), key
        else:
            assert x == y, key


def make_adapter(pob_root, **bounds) -> EngineAdapter:
    return EngineAdapter(pob_worker_spec(pob_root), screen_timeout_s=REQUEST_TIMEOUT_S,
                         detailed_timeout_s=REQUEST_TIMEOUT_S,
                         start_timeout_s=START_TIMEOUT_S, **bounds)


@pytest.fixture(scope="module")
def document(pob_root: Path, tmp_path_factory) -> BuildDocument:
    """A PoB-saved build, made out of process (see test_p02_t01_engine_adapter)."""
    out = tmp_path_factory.mktemp("p02t011-fixture") / "populated.xml"
    script = Path(__file__).resolve().parents[2] / "scripts" / \
        "p02_t01_build_fixture_document.py"
    completed = subprocess.run(
        [sys.executable, str(script), str(out)],
        cwd=str(script.parent.parent), capture_output=True, text=True,
        env=dict(os.environ, POB2_ROOT=str(pob_root)), timeout=600)
    assert completed.returncode == 0 and out.is_file(), completed.stderr[-2000:]
    return BuildDocument("p02t011-engine-fixture", out.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def reference(pob_root, document) -> dict:
    with make_adapter(pob_root, memory_limit_bytes=None,
                      recycle_after_bytes=None) as fresh:
        return fresh.probe(document)


def test_a_worker_over_the_hard_limit_is_killed_and_reported(pob_root, document,
                                                              reference):
    """PoB needs far more than 64 MB to boot, so the limit trips at startup."""
    with make_adapter(pob_root, memory_limit_bytes=64 * MB,
                      recycle_after_bytes=None) as adapter:
        with pytest.raises(EngineMemoryLimit) as excinfo:
            adapter.probe(document)
        assert excinfo.value.status is ResultStatus.ENGINE_CRASH
        assert excinfo.value.stage == "startup"
        assert excinfo.value.observed_bytes > 64 * MB
        assert adapter.consecutive_failures == 1
    # A worker under a realistic bound evaluates the same build normally.
    with make_adapter(pob_root) as adapter:
        assert_same(adapter.probe(document), reference)


def test_repeated_losses_stop_without_unlimited_replacement(pob_root):
    with make_adapter(pob_root, memory_limit_bytes=64 * MB, recycle_after_bytes=None,
                      max_consecutive_failures=2) as adapter:
        for _ in range(2):
            with pytest.raises(EngineMemoryLimit):
                adapter.identity()
        with pytest.raises(EngineReplacementExhausted):
            adapter.identity()


def test_a_recycled_worker_gives_identical_results(pob_root, document, reference):
    with make_adapter(pob_root, recycle_after_bytes=1) as adapter:
        first = adapter.probe(document)
        first_pid = adapter.worker_pid
        second = adapter.probe(document)
        assert adapter.worker_pid != first_pid
        assert adapter.recycles == 1 and adapter.replacements == 0
        assert_same(first, reference)
        assert_same(second, reference)
        assert adapter.worker_history[0]["end"].startswith("recycled: memory")
        assert adapter.worker_history[0]["peak_memory_bytes"] > 64 * MB


def test_a_request_budget_recycles_between_operations_only(pob_root, document,
                                                           reference):
    """probe is a load and a read: two requests, never split across workers."""
    with make_adapter(pob_root, max_requests_per_worker=2) as adapter:
        values = [adapter.probe(document) for _ in range(3)]
        assert len(adapter.worker_pids) == 3
        assert all(entry["requests"] == 2 for entry in adapter.worker_history)
        for value in values:
            assert_same(value, reference)
