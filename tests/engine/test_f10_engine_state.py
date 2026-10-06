"""Research finding F10 against the real engine (P00-T04).

Two things are checked here:

* the working-directory side effect is real and permanent for the hosting
  process, which is why the engine may only be instantiated inside a worker;
* an A-B-A evaluation sequence returns to its original numbers, i.e. the
  deterministic primitives used by these tests do not leak state between
  evaluations. That is evidence about *these* operations only.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from engine_helpers import FIXTURE_WEAPON, STRONGER_WEAPON, allocated_count

pytestmark = pytest.mark.engine

#: P02-T01 acceptance tolerance for deterministic primitives.
REL_TOLERANCE = 1e-6
ABS_TOLERANCE = 1e-9


# ------------------------------------------------- working-directory leak

def test_engine_boot_moved_the_process_into_the_pob_source_tree(engine, pob_root: Path):
    assert Path(engine.cwd_after_boot) == (pob_root / "src").resolve()
    assert Path(engine.cwd_before_boot) != Path(engine.cwd_after_boot)


def test_the_working_directory_stays_changed_for_the_whole_session(engine, pob_root: Path):
    """Nothing restores it; the test session's own fixture has to."""
    assert Path(os.getcwd()).resolve() == (pob_root / "src").resolve()


def test_relative_paths_now_resolve_inside_someone_elses_checkout(engine, pob_root: Path):
    resolved = Path("HeadlessWrapper.lua").resolve()
    assert resolved == (pob_root / "src" / "HeadlessWrapper.lua").resolve()
    assert resolved.is_file()


# --------------------------------------------------------- A-B-A stability

def assert_stats_match(first: dict, second: dict) -> None:
    assert set(first) == set(second)
    for key, value in first.items():
        other = second[key]
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            assert other == pytest.approx(value, rel=REL_TOLERANCE, abs=ABS_TOLERANCE), key
        else:
            assert other == value, key


def test_aba_weapon_swap_returns_identical_stats(blank_build):
    blank_build.call("equip_item", {"raw": FIXTURE_WEAPON, "slot": "Weapon 1"})
    state_a1 = blank_build.call("get_stats", {"all": True})

    blank_build.call("equip_item", {"raw": STRONGER_WEAPON, "slot": "Weapon 1"})
    state_b = blank_build.call("get_stats", {"all": True})

    blank_build.call("equip_item", {"raw": FIXTURE_WEAPON, "slot": "Weapon 1"})
    state_a2 = blank_build.call("get_stats", {"all": True})

    assert state_b["TotalDPS"] > state_a1["TotalDPS"], "B must differ, or A-B-A proves nothing"
    assert_stats_match(state_a1, state_a2)


def test_aba_build_reload_returns_identical_stats(blank_build):
    nodes = blank_build.call("search_nodes", {"text": "projectile damage", "limit": 5})
    blank_build.call("alloc_nodes", {"ids": [nodes[0]["id"]]})
    blank_build.call("equip_item", {"raw": FIXTURE_WEAPON, "slot": "Weapon 1"})
    xml = blank_build.call("save_build_xml")["xml"]
    state_a1 = blank_build.call("get_stats", {"all": True})
    nodes_a1 = allocated_count(blank_build)

    blank_build.call("new_build")
    blank_build.call("equip_item", {"raw": STRONGER_WEAPON, "slot": "Weapon 1"})

    blank_build.call("load_build_xml", {"xml": xml, "name": "aba"})
    assert_stats_match(state_a1, blank_build.call("get_stats", {"all": True}))
    assert allocated_count(blank_build) == nodes_a1


def test_repeated_evaluation_of_the_same_state_is_stable(blank_build):
    blank_build.call("equip_item", {"raw": FIXTURE_WEAPON, "slot": "Weapon 1"})
    first = blank_build.call("get_stats", {"all": True})
    for _ in range(9):
        assert_stats_match(first, blank_build.call("get_stats", {"all": True}))


# ------------------------------------------------------- repaired behaviour
# The original expectation here was that ``Pob2Engine`` itself would stop
# changing the directory. The architecture permits the opposite: the engine
# loads its data relative to ``src/``, so the worker is allowed to move and the
# *coordinator* is what must not. P02-T01 kept the engine as it is and put the
# boundary one level up, so this assertion was migrated to that boundary.
# tests/engine/test_p02_t01_engine_adapter.py measures the same property
# against a spawned worker.


def test_the_engine_still_moves_the_process_it_is_built_in(engine):
    """Which is why a worker is the only place it may be built.

    The coordinator-side guarantee this replaced is measured in
    tests/engine/test_p02_t01_engine_adapter.py, against a spawned worker.
    """
    assert Path(os.getcwd()) != Path(engine.cwd_before_boot)
