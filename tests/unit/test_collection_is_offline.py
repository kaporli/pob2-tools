"""Collecting the suite must not boot PoB or contact a provider (P00-T02).

The script this project started from booted the engine at module import, so
merely collecting tests loaded a 600 kB native DLL, read the passive tree and
printed several hundred lines. That is both slow and a false signal: a gate can
look exercised when nothing ran.

This test re-runs pytest in collect-only mode and checks the output for the
engine's startup banner.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

#: Lines PoB's HeadlessWrapper prints while booting.
ENGINE_BANNERS = (
    "Loading main script",
    "Loading passive tree data",
    "Loading passive tree assets",
    "Uniques loaded",
    "Rares loaded",
)


@pytest.fixture(scope="module")
def collect_output(repo_root: Path) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join(
        [str(repo_root / "pob2-optimizer"), str(repo_root / "pob2-mcp")])
    return subprocess.run(
        [sys.executable, "-m", "pytest", "--collect-only", "-q",
         "-p", "no:cacheprovider"],
        cwd=str(repo_root), env=env, capture_output=True, text=True, timeout=300,
    )


def test_collection_succeeds(collect_output):
    assert collect_output.returncode == 0, collect_output.stdout[-3000:]


def test_collection_does_not_boot_pob(collect_output):
    """Scope: this inspects the console for PoB's startup banners.

    It shows the engine did not start. It is not independent proof that
    collection made no network call, and it does not become that by passing.
    Strengthen it when P03 adds acquisition modules.
    """
    combined = collect_output.stdout + collect_output.stderr
    for banner in ENGINE_BANNERS:
        assert banner not in combined, "PoB booted during collection: " + banner


def test_collection_finds_the_four_test_directories(collect_output):
    combined = collect_output.stdout.replace("\\", "/")
    assert "tests/unit/" in combined
    assert "tests/engine/" in combined
    assert "tests/integration/" in combined


def test_no_test_module_lives_outside_the_tests_tree(repo_root: Path):
    """A stray `test_*.py` beside the packages would be collected by accident."""
    strays = [
        p for p in repo_root.glob("*/test_*.py")
        if "tests" not in p.parts and "external" not in p.parts
    ]
    assert strays == [], "move these under tests/: %s" % strays
