"""P02-T01 acceptance case 4: the adapter against the real PoB engine.

Everything here runs a spawned worker that boots the pinned checkout, so each
test costs a real engine boot. The module therefore uses one adapter for the
whole module and only restarts the worker where a test is about process
replacement.

What is measured:

* A-B-A agreement for deterministic primitives within the task's tolerance;
* an imported build keeps its tree, gear and socket groups through the adapter
  (research F11), while ``create_blank_build`` still clears them;
* the coordinator's working directory never moves, although the worker's does;
* a killed worker gives a typed error and the next request runs in a new
  process, with no reset of the dead one.
"""

from __future__ import annotations

import dataclasses
import faulthandler
import os
import sys
from pathlib import Path

import pytest

from engine_helpers import FIXTURE_WEAPON
from record_fixtures import records

from pob2opt.domain.enums import ResultStatus
from pob2opt.evaluation import (BuildDocument, EngineAdapter, EngineCrash,
                                EngineInvalidInput, EngineState,
                                MappingBuildDocuments, kill_process_tree,
                                pob_worker_spec, resolve_checkout)

pytestmark = pytest.mark.engine

#: P02-T01 acceptance tolerance for deterministic primitives.
REL_TOLERANCE = 1e-6
ABS_TOLERANCE = 1e-9

#: A PoB boot measured in minutes on the P00 environment; these bounds are the
#: adapter's, not the engine's, and are deliberately generous here.
START_TIMEOUT_S = 600.0
REQUEST_TIMEOUT_S = 300.0

BUILD_HASH = "p02t01-engine-fixture"


# ------------------------------------------------------------------ fixtures

@pytest.fixture(scope="module")
def populated_xml(pob_root: Path, tmp_path_factory) -> str:
    """A build with a tree, an item and a socket group, saved by PoB itself.

    Built in a throwaway engine of its own, then closed, so the adapter under
    test never sees a document this suite did not create and the coordinator's
    working directory is back where it started before any worker is spawned.

    Native-fault diagnostics are redirected for the duration for the reason
    tests/conftest.py gives: LuaJIT raises SEH 0xe24c4a02 during ordinary error
    unwinding and faulthandler prints a traceback for every one.
    """
    from pob2mcp.engine import Pob2Engine

    log_path = tmp_path_factory.mktemp("p02t01-faults") / "faulthandler.log"
    log = log_path.open("w", encoding="utf-8", errors="replace")
    was_enabled = faulthandler.is_enabled()
    faulthandler.enable(file=log, all_threads=True)
    before = os.getcwd()
    engine = None
    try:
        engine = Pob2Engine(str(pob_root))
        engine.call("new_build")
        nodes = engine.call("search_nodes", {"text": "projectile damage",
                                             "limit": 5})
        engine.call("alloc_nodes", {"ids": [n["id"] for n in nodes[:2]]})
        engine.call("equip_item", {"raw": FIXTURE_WEAPON, "slot": "Weapon 1"})
        return engine.call("save_build_xml")["xml"]
    finally:
        if engine is not None:
            engine.close()
        os.chdir(before)
        if was_enabled:
            faulthandler.enable(file=sys.stderr, all_threads=True)
        else:  # pragma: no cover - pytest enables it by default
            faulthandler.disable()
        log.close()


@pytest.fixture(scope="module")
def adapter(pob_root: Path):
    spec = pob_worker_spec(pob_root)
    live = EngineAdapter(spec, screen_timeout_s=REQUEST_TIMEOUT_S,
                         detailed_timeout_s=REQUEST_TIMEOUT_S,
                         start_timeout_s=START_TIMEOUT_S)
    try:
        yield live
    finally:
        live.close()


@pytest.fixture(scope="module")
def document(populated_xml: str) -> BuildDocument:
    return BuildDocument(build_hash=BUILD_HASH, xml=populated_xml)


@pytest.fixture(scope="module")
def build_and_profile(pob_root: Path):
    """P01 fixture records, repinned to the checkout actually running."""
    checkout = resolve_checkout(pob_root)
    build = dataclasses.replace(records()["build_spec"], build_hash=BUILD_HASH)
    profile = dataclasses.replace(records()["patch_profile"],
                                  pob_commit=checkout.commit)
    return build, profile


# ------------------------------------------------- the coordinator stays put

def test_the_worker_moves_into_the_pob_tree_and_the_parent_does_not(
        adapter, pob_root: Path):
    before = os.getcwd()
    identity = adapter.identity()

    assert Path(identity.worker_cwd).resolve() == (pob_root / "src").resolve()
    assert os.getcwd() == before
    assert os.getcwd() == adapter.parent_cwd


def test_the_identity_names_the_running_checkout(adapter, pob_root: Path):
    identity = adapter.identity()
    checkout = resolve_checkout(pob_root)

    assert identity.pob_commit == checkout.commit
    assert identity.pob_dirty_hash == checkout.dirty_hash
    assert identity.is_pinned == checkout.is_pinned
    assert Path(identity.pob_root).resolve() == pob_root.resolve()


# --------------------------------------------------- exact load keeps the build

def test_an_exact_load_keeps_the_tree_the_gear_and_the_socket_groups(
        adapter, document):
    loaded = adapter.load_exact_build(document)

    assert loaded.opt_setup_called is False
    assert loaded.allocated_nodes > 1, "only the class root would mean a wipe"
    assert loaded.equipped_items == 1


def test_create_blank_build_still_clears_the_character(adapter, document):
    adapter.load_exact_build(document)
    blank = adapter.create_blank_build(level=28)

    assert blank.opt_setup_called is True
    assert blank.equipped_items == 0
    assert blank.socket_groups == 0
    assert blank.allocated_nodes <= 1


def test_a_malformed_document_is_invalid_input_not_a_default_character(
        adapter, fixtures_dir: Path):
    malformed = (fixtures_dir / "builds" / "malformed_build.xml").read_text(
        encoding="utf-8")

    with pytest.raises(EngineInvalidInput) as excinfo:
        adapter.load_exact_build(BuildDocument("malformed", malformed))

    assert excinfo.value.status is ResultStatus.INVALID_INPUT
    # The state after a failed load is not reusable, so the worker is gone.
    assert not adapter.worker_alive


# ----------------------------------------------------------- A-B-A stability

def assert_values_match(first: dict, second: dict) -> None:
    assert set(first) == set(second)
    for key, value in first.items():
        other = second[key]
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            assert other == pytest.approx(value, rel=REL_TOLERANCE,
                                          abs=ABS_TOLERANCE), key
        else:
            assert other == value, key


def test_aba_through_the_adapter_returns_identical_primitives(
        adapter, document, build_and_profile, populated_xml):
    build, profile = build_and_profile
    documents = MappingBuildDocuments({BUILD_HASH: populated_xml})
    adapter.documents = documents
    state = EngineState()

    first = adapter.primitives(build, state, profile)

    stronger = populated_xml.replace("60 to 90", "120 to 180")
    assert stronger != populated_xml, "B must differ, or A-B-A proves nothing"
    adapter.load_exact_build(BuildDocument("p02t01-engine-b", stronger))
    middle = adapter.primitives(build, state, profile,
                                document=BuildDocument(BUILD_HASH, populated_xml))

    adapter.load_exact_build(BuildDocument("p02t01-engine-b", stronger))
    adapter.load_exact_build(document)
    second = adapter.primitives(build, state, profile)

    assert_values_match(first.values, second.values)
    assert_values_match(first.values, middle.values)


def test_repeating_one_request_is_stable(adapter, document, build_and_profile,
                                         populated_xml):
    build, profile = build_and_profile
    adapter.documents = MappingBuildDocuments({BUILD_HASH: populated_xml})
    first = adapter.primitives(build, EngineState(), profile)
    for _ in range(3):
        assert_values_match(first.values,
                            adapter.primitives(build, EngineState(), profile).values)


def test_a_snapshot_declares_no_primitive_semantics(adapter, build_and_profile,
                                                    populated_xml):
    build, profile = build_and_profile
    adapter.documents = MappingBuildDocuments({BUILD_HASH: populated_xml})
    snapshot = adapter.primitives(build, EngineState(), profile)

    assert snapshot.semantics_status == "undeclared"
    assert snapshot.values, "the engine did answer; only the units are missing"


# ------------------------------------------------------- forced termination

def test_a_killed_worker_is_replaced_and_the_next_request_succeeds(
        adapter, document, pob_root: Path):
    adapter.load_exact_build(document)
    first = adapter.identity().worker_pid
    replacements = adapter.replacements

    kill_process_tree(first, adapter._handle.process)

    with pytest.raises(EngineCrash) as excinfo:
        adapter.load_exact_build(document)
    assert excinfo.value.status is ResultStatus.ENGINE_CRASH

    loaded = adapter.load_exact_build(document)
    second = adapter.identity().worker_pid

    assert second != first, "a reset of the dead process would not change the pid"
    assert adapter.replacements == replacements + 1
    assert loaded.allocated_nodes > 1
    assert os.getcwd() == adapter.parent_cwd
