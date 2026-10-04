"""Research finding F10, characterized at the API surface (P00-T04).

``pob2mcp.engine.Pob2Engine`` owns a native Lua state and, as written:

* changes the process working directory to the PoB source tree in ``__init__``
  and never changes it back, so every path resolved afterwards by the hosting
  process is relative to somebody else's checkout;
* offers no close, shutdown or restart operation, so a crashed or leaked native
  state cannot be disposed of deterministically;
* offers no per-call timeout, so a wedged evaluation blocks its caller.

Importing the module is safe - the DLL is only loaded in ``__init__`` - so this
file needs no PoB runtime. ``tests/engine/test_f10_engine_state.py`` measures the
real behaviour, including the A-B-A state check.

The repair is P02-T01 ("Keep the parent's working directory unchanged", plus
deterministic close/error handling and worker replacement after timeout/crash).
"""

from __future__ import annotations

import inspect

import pytest

from pob2mcp import engine as engine_module

SOURCE = inspect.getsource(engine_module)


# ------------------------------------------------------- current behaviour

def test_engine_constructor_changes_the_process_working_directory():
    init_source = inspect.getsource(engine_module.Pob2Engine.__init__)
    assert "os.chdir(self.src_dir)" in init_source


def test_engine_exposes_no_deterministic_teardown():
    for name in ("close", "shutdown", "restart", "__exit__", "__del__"):
        assert not hasattr(engine_module.Pob2Engine, name), (
            "Pob2Engine unexpectedly has %s; update this characterization" % name)


def test_engine_call_has_no_timeout_parameter():
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

@pytest.mark.xfail(
    strict=True,
    reason="F10 repair is P02-T01: the engine must expose deterministic close "
           "and restart so a crashed native state is replaced, not reset.",
)
def test_repaired_engine_exposes_close_and_restart():
    assert hasattr(engine_module.Pob2Engine, "close")
    assert hasattr(engine_module.Pob2Engine, "restart")


@pytest.mark.xfail(
    strict=True,
    reason="F10 repair is P02-T01: the hosting process working directory must "
           "stay unchanged; path resolution belongs to the coordinator.",
)
def test_repaired_engine_does_not_chdir_the_host_process():
    assert "os.chdir" not in SOURCE


@pytest.mark.xfail(
    strict=True,
    reason="F10 repair is P02-T01: evaluation needs a bounded timeout so a "
           "wedged call cannot block cancellation or progress reporting.",
)
def test_repaired_engine_accepts_a_call_timeout():
    assert "timeout" in inspect.signature(engine_module.Pob2Engine.call).parameters
