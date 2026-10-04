"""Engine-test fixtures (P00-T02/T04).

Everything under ``tests/engine`` is marked ``engine`` and needs a real PoB
checkout. When none is configured the tests skip with the reason from
``tests/conftest.py``; a skip is never an engine pass.
"""

from __future__ import annotations

from pathlib import Path

import pytest

pytestmark = pytest.mark.engine


@pytest.fixture(scope="session")
def opt_helpers_source(repo_root: Path) -> str:
    return (repo_root / "pob2-optimizer" / "pob2opt" / "lua" / "opt_helpers.lua").read_text(
        encoding="utf-8")


@pytest.fixture()
def blank_build(engine):
    """A freshly created build; isolates each test from the previous one."""
    engine.call("new_build")
    return engine
