"""Shared test configuration (P00-T02).

Two rules this file exists to enforce:

1. Tests import the monorepo working tree, never whatever ``pip`` happens to
   have installed. Both packages are commonly installed editable from older
   standalone checkouts; silently testing those is the failure mode this
   prepend prevents. ``tests/unit/test_import_provenance.py`` asserts it held.
2. Nothing boots PoB or touches the network at import/collection time. The
   engine is created lazily by a session fixture and only for ``engine`` tests.
"""

from __future__ import annotations

import faulthandler
import os
import sys
import threading
import time
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
PKG_ROOTS = (REPO_ROOT / "pob2-mcp", REPO_ROOT / "pob2-optimizer")

# ``tests/testdoubles.py`` holds the synthetic doubles shared by the unit tests,
# and ``scripts/`` holds the CI helper scripts that have their own tests.
for _helper_dir in (Path(__file__).resolve().parent, REPO_ROOT / "scripts"):
    if str(_helper_dir) not in sys.path:
        sys.path.insert(0, str(_helper_dir))

for _root in reversed(PKG_ROOTS):
    _p = str(_root)
    if _p in sys.path:
        sys.path.remove(_p)
    sys.path.insert(0, _p)


# --------------------------------------------------------------------- paths

@pytest.fixture(scope="session")
def repo_root() -> Path:
    return REPO_ROOT


@pytest.fixture(scope="session")
def fixtures_dir() -> Path:
    return Path(__file__).resolve().parent / "fixtures"


# --------------------------------------------------------------------- engine

def resolve_pob_root() -> Path | None:
    """The PoB checkout this machine is configured to use, or None.

    Priority matches ``pob2mcp.engine``: ``POB2_ROOT`` first, then the bundled
    submodule. Returns None instead of guessing when neither is usable, so the
    engine tests skip with a reason rather than failing obscurely.
    """
    env = os.environ.get("POB2_ROOT")
    candidates = [Path(env)] if env else []
    candidates.append(REPO_ROOT / "external" / "PathOfBuilding-PoE2")
    for cand in candidates:
        if (cand / "runtime" / "lua51.dll").is_file():
            return cand.resolve()
    return None


POB_ROOT = resolve_pob_root()

#: Set by the ``engine`` fixture so the terminal summary can point at the log.
FAULT_LOG: Path | None = None

#: Memory bound for the in-process session engine (P02-T01.1), in MB of the
#: pytest process's private bytes. A runaway inside a native call cannot be
#: interrupted, so above the bound the guard names the running test on stderr
#: and exits with ENGINE_MEMORY_EXIT. 0 disables it.
ENGINE_MEMORY_LIMIT_MB = int(os.environ.get("POB2_TEST_MEMORY_LIMIT_MB", "3072"))
ENGINE_MEMORY_EXIT = 87

#: The test pytest is running, for the guard's message.
CURRENT_TEST: str | None = None
#: pytest's capture manager, so the guard can reach the real stderr.
CAPTURE_MANAGER = None

SKIP_REASON = (
    "no usable PathOfBuilding-PoE2 runtime: set POB2_ROOT to a checkout whose "
    "runtime/lua51.dll exists, or restore the external/PathOfBuilding-PoE2 submodule"
)


@pytest.fixture(scope="session")
def pob_root() -> Path:
    if POB_ROOT is None:
        pytest.skip(SKIP_REASON)
    return POB_ROOT


@pytest.fixture(scope="session")
def engine(pob_root: Path, tmp_path_factory):
    """One session-wide engine.

    ``Pob2Engine.__init__`` calls ``os.chdir`` into the PoB source tree and has
    no close/restart path (research F10), so the whole pytest process inherits
    that working directory for the rest of the session. The fixture restores it
    on teardown and records the leak for the F10 characterization tests.

    Native-fault diagnostics are redirected to a file rather than switched off.
    PoB's LuaJIT raises an SEH exception (``0xe24c4a02``) as part of ordinary
    error unwinding, and ``faulthandler`` prints a full traceback each time: a
    measured 6984 banners and 286749 lines for one engine session, which buries
    the test report. The log keeps every one of them inspectable, and pytest's
    exit code still reports a real crash.
    """
    from pob2mcp.engine import Pob2Engine

    log_path = tmp_path_factory.mktemp("engine-faults") / "faulthandler.log"
    log = log_path.open("w", encoding="utf-8", errors="replace")
    was_enabled = faulthandler.is_enabled()
    faulthandler.enable(file=log, all_threads=True)

    before = os.getcwd()
    try:
        eng = Pob2Engine(str(pob_root))
    except BaseException:
        faulthandler.enable(file=sys.stderr, all_threads=True)
        log.close()
        print("native fault diagnostics: %s" % log_path, file=sys.stderr)
        raise
    _start_memory_guard(ENGINE_MEMORY_LIMIT_MB * 2**20)
    eng.cwd_before_boot = before  # type: ignore[attr-defined]
    eng.cwd_after_boot = os.getcwd()  # type: ignore[attr-defined]
    eng.fault_log = log_path  # type: ignore[attr-defined]
    global FAULT_LOG
    FAULT_LOG = log_path
    try:
        yield eng
    finally:
        os.chdir(before)
        if was_enabled:
            faulthandler.enable(file=sys.stderr, all_threads=True)
        else:  # pragma: no cover - pytest enables it by default
            faulthandler.disable()
        log.close()


def _start_memory_guard(limit_bytes: int) -> None:
    """Exit the session above ``limit_bytes``, naming the test (P02-T01.1).

    The engine runs in this process, so the bound cannot replace a worker the
    way ``EngineAdapter`` does. An explicit exit is the containment: without it
    the run grows until the machine stops it (observed 4 to 17.6 GB).
    """
    from pob2opt.evaluation.memory import probe_available, process_memory_bytes

    if limit_bytes <= 0 or not probe_available():
        return
    pid = os.getpid()

    def guard() -> None:
        while True:
            used = process_memory_bytes(pid)
            if used is not None and used > limit_bytes:
                # Capture redirects fd 2 to a temp file that os._exit drops.
                if CAPTURE_MANAGER is not None:
                    CAPTURE_MANAGER.suspend_global_capture(in_=False)
                os.write(2, ("\nengine memory guard: %d bytes above %d during %s; "
                             "exiting with %d (POB2_TEST_MEMORY_LIMIT_MB)\n"
                             % (used, limit_bytes, CURRENT_TEST, ENGINE_MEMORY_EXIT)
                             ).encode())
                os._exit(ENGINE_MEMORY_EXIT)
            time.sleep(0.5)

    threading.Thread(target=guard, name="engine-memory-guard", daemon=True).start()


def pytest_configure(config):
    global CAPTURE_MANAGER
    CAPTURE_MANAGER = config.pluginmanager.getplugin("capturemanager")


def pytest_runtest_logstart(nodeid, location):
    global CURRENT_TEST
    CURRENT_TEST = nodeid


def pytest_terminal_summary(terminalreporter):
    """Point at the native-fault log instead of printing it.

    A session-scoped fixture's teardown output is captured, so the path has to
    be reported here to be visible at all.
    """
    if FAULT_LOG is None or not FAULT_LOG.is_file():
        return
    size = FAULT_LOG.stat().st_size
    terminalreporter.write_line(
        "native fault diagnostics: %d bytes at %s" % (size, FAULT_LOG))
    terminalreporter.write_line(
        "  LuaJIT raises SEH 0xe24c4a02 during ordinary error unwinding, so this "
        "file is large and is not by itself a crash.")
