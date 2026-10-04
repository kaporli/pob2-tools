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


# ------------------------------------------------------- future repair binding
# P01 records and P02 worker fixtures do not exist yet. Passing None records or
# inventing evaluate_raw() would prescribe an invalid production contract.
# P02 must replace this binding check with actual adapter evaluations. See the
# explicit cases and hard outer-timeout requirement in tests/MANIFEST.md.

from repair_contracts import MissingFutureService, require_production_binding


@pytest.mark.xfail(strict=True, raises=MissingFutureService,
                   reason="P02-T01: engine adapter and production contract binding are not implemented")
def test_production_engine_contract_binding_is_pending():
    require_production_binding("pob2opt.evaluation", "P02-T01")
