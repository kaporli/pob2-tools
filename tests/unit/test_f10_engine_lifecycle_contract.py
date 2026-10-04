"""Research finding F10, characterized at the API surface (P00-T04).

This file records what ``pob2mcp.engine.Pob2Engine`` does today. As written it:

* changes the process working directory to the PoB source tree in ``__init__``
  and never changes it back;
* offers no close, shutdown or restart operation;
* offers no per-call timeout.

**These are legacy characterizations, not requirements.** The architecture
permits the existing cwd-dependent engine to keep working as long as it is
instantiated inside an isolated worker, with timeouts and path resolution owned
by the coordinator. A repair that leaves ``os.chdir`` inside the worker is a
valid repair. So the facts below are pinned only to detect silent drift in the
legacy module, and the repaired expectations at the bottom are written against
the boundary P02-T01 actually promises.

Importing the module is safe, because the DLL is only loaded in ``__init__``, so
this file needs no PoB runtime. ``tests/engine/test_f10_engine_state.py``
measures the real behaviour, including the A-B-A state check.
"""

from __future__ import annotations

import inspect

import pytest

from pob2mcp import engine as engine_module

SOURCE = inspect.getsource(engine_module)


# ------------------------------------------------------- current behaviour

def test_engine_constructor_changes_the_process_working_directory():
    """Legacy fact. Permitted inside a worker; the parent is what must not move."""
    init_source = inspect.getsource(engine_module.Pob2Engine.__init__)
    assert "os.chdir(self.src_dir)" in init_source


def test_engine_exposes_no_deterministic_teardown():
    for name in ("close", "shutdown", "restart", "__exit__", "__del__"):
        assert not hasattr(engine_module.Pob2Engine, name), (
            "Pob2Engine unexpectedly has %s; update this characterization" % name)


def test_engine_call_has_no_timeout_parameter():
    """Legacy fact. The bound belongs to the coordinator, not necessarily here."""
    params = inspect.signature(engine_module.Pob2Engine.call).parameters
    assert set(params) == {"self", "fn", "args"}


def test_engine_serializes_calls_with_a_thread_lock_only():
    """A lock makes concurrent calls safe; it does not isolate processes."""
    assert "self._lock = threading.Lock()" in SOURCE
    assert "multiprocessing" not in SOURCE


def test_engine_error_type_is_undifferentiated():
    """Every failure - load, runtime, handler - is the same exception class."""
    assert issubclass(engine_module.PobEngineError, RuntimeError)
    assert SOURCE.count("raise PobEngineError") >= 3
    assert "timeout" not in SOURCE.lower()


def test_missing_runtime_is_reported_with_an_actionable_message(tmp_path):
    with pytest.raises(engine_module.PobEngineError) as excinfo:
        engine_module.Pob2Engine(str(tmp_path))
    message = str(excinfo.value)
    assert "lua51.dll" in message
    assert "POB2_ROOT" in message


# ------------------------------------------------------- repaired behaviour
#
# P02-T01 promises an `EngineAdapter` with one engine per worker process, a
# parent working directory that never moves, bounded requests, and worker
# replacement after a timeout or crash. These expectations are written against
# that boundary, so a repair that keeps the legacy engine inside an isolated
# worker satisfies them, and a repair that only adds an unused parameter or
# method does not.
#
# They currently fail because `pob2opt.evaluation` does not exist yet.


def load_adapter():
    """The future engine adapter, or a failure that keeps the xfail honest."""
    from pob2opt.evaluation import EngineAdapter  # noqa: F401  (does not exist yet)

    return EngineAdapter


@pytest.mark.xfail(
    strict=True,
    reason="F10 repair is P02-T01: evaluating through the adapter must leave the "
           "calling process working directory unchanged. The worker may still "
           "chdir internally; that is explicitly permitted.",
)
def test_repaired_adapter_leaves_the_parent_working_directory_alone(tmp_path):
    import os

    adapter = load_adapter()
    before = os.getcwd()
    adapter().primitives(build=None, state=None, profile=None)
    assert os.getcwd() == before


@pytest.mark.xfail(
    strict=True,
    reason="F10 repair is P02-T01: a wedged request must return a typed timeout "
           "within its bound. A timeout parameter that is never enforced does "
           "not satisfy this.",
)
def test_repaired_adapter_enforces_the_timeout_it_advertises():
    import time

    adapter = load_adapter()
    instance = adapter()
    started = time.perf_counter()
    result = instance.evaluate_raw("while true do end", timeout_s=1.0)
    elapsed = time.perf_counter() - started

    assert result.status == "timeout"
    assert elapsed < 10.0, "the call must be bounded, not merely annotated"


@pytest.mark.xfail(
    strict=True,
    reason="F10 repair is P02-T01: after a forced worker failure the adapter must "
           "replace the process and complete the next request. Resetting Lua "
           "tables does not count as replacing a crashed native state.",
)
def test_repaired_adapter_replaces_a_worker_after_failure():
    adapter = load_adapter()
    instance = adapter()
    first = instance.evaluate_raw("os.exit(1)", timeout_s=5.0)
    assert first.status in {"engine_crash", "timeout"}

    second = instance.evaluate_raw("return 1 + 1", timeout_s=5.0)
    assert second.status == "ok"
    assert second.worker_id != first.worker_id
