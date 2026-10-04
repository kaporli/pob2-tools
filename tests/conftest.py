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

import os
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
PKG_ROOTS = (REPO_ROOT / "pob2-mcp", REPO_ROOT / "pob2-optimizer")

# ``tests/testdoubles.py`` holds the synthetic doubles shared by the unit tests.
if str(Path(__file__).resolve().parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parent))

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
def engine(pob_root: Path):
    """One session-wide engine.

    ``Pob2Engine.__init__`` calls ``os.chdir`` into the PoB source tree and has
    no close/restart path (research F10), so the whole pytest process inherits
    that working directory for the rest of the session. The fixture restores it
    on teardown and records the leak for the F10 characterization tests.
    """
    from pob2mcp.engine import Pob2Engine

    before = os.getcwd()
    eng = Pob2Engine(str(pob_root))
    eng.cwd_before_boot = before  # type: ignore[attr-defined]
    eng.cwd_after_boot = os.getcwd()  # type: ignore[attr-defined]
    try:
        yield eng
    finally:
        os.chdir(before)
