"""Research finding F10, characterized at the API surface (P00-T04).

This file records what ``pob2mcp.engine.Pob2Engine`` does today. As written it:

* changes the process working directory to the PoB source tree in ``__init__``
  and never changes it back;
* offers no per-call timeout.

Two of the original characterizations were migrated by P02-T01, which is a
behaviour change, not a drifting test: the engine now has a deterministic
``close`` and a distinct closed-state error. The sections below say so where
they apply.

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
from pathlib import Path

import pytest

from pob2mcp import engine as engine_module

SOURCE = inspect.getsource(engine_module)
REPO_ROOT = Path(__file__).resolve().parents[2]


# ------------------------------------------------------- current behaviour

def test_engine_constructor_changes_the_process_working_directory():
    """Legacy fact. Permitted inside a worker; the parent is what must not move."""
    init_source = inspect.getsource(engine_module.Pob2Engine.__init__)
    assert "os.chdir(self.src_dir)" in init_source


def test_engine_now_has_a_deterministic_teardown():
    """Migrated by P02-T01. It previously had no close path at all."""
    assert hasattr(engine_module.Pob2Engine, "close")
    assert hasattr(engine_module.Pob2Engine, "__exit__")
    assert "lua.lua_close(state)" in SOURCE


def test_a_closed_engine_refuses_calls_instead_of_touching_a_freed_pointer():
    assert issubclass(engine_module.PobEngineClosed, engine_module.PobEngineError)
    call_source = inspect.getsource(engine_module.Pob2Engine.call)
    assert "raise PobEngineClosed" in call_source


def test_the_engine_still_has_no_restart_of_its_own():
    """Replacing a dead engine is the adapter's job, by replacing the process."""
    for name in ("shutdown", "restart", "reset"):
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


def test_engine_errors_are_still_undifferentiated_apart_from_closure():
    """Load, runtime and handler failures remain one class.

    P02-T01 classifies failures in ``pob2opt.evaluation.errors`` instead, at
    the boundary that owns the result status. Only the closed state is
    distinguished here, because only the engine can know it.
    """
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
# P02-T01 implemented ``pob2opt.evaluation``, so the P00 missing-service
# placeholder is gone. Its four acceptance cases live in
# ``tests/unit/test_p02_t01_adapter.py`` (parent cwd, exact versus blank
# loading, process replacement), ``tests/unit/test_p02_t01_timeout_supervisor.py``
# (the bounded request, under an outer deadline) and
# ``tests/engine/test_p02_t01_engine_adapter.py`` (the real engine).


def test_the_production_engine_boundary_exists_and_is_covered():
    import importlib.util

    assert importlib.util.find_spec("pob2opt.evaluation") is not None
    covered = [
        REPO_ROOT / "tests" / "unit" / "test_p02_t01_adapter.py",
        REPO_ROOT / "tests" / "unit" / "test_p02_t01_timeout_supervisor.py",
        REPO_ROOT / "tests" / "engine" / "test_p02_t01_engine_adapter.py",
    ]
    assert all(path.is_file() for path in covered)
