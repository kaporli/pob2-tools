"""P02-T01 adapter lifecycle, offline (synthetic workers, no PoB).

This file replaces the P00 missing-service placeholder for
``pob2opt.evaluation``. It covers acceptance cases 1 and 3 of the P02-T01 list
in ``tests/MANIFEST.md``; case 2 needs an outer process supervisor and lives in
``test_p02_t01_timeout_supervisor.py``; case 4 is the real engine, under
``tests/engine``.

Every worker here is ``tests/synthetic_workers.py``. No value produced by this
file is a game value or engine output.
"""

from __future__ import annotations

import dataclasses
import os
import shutil
from pathlib import Path

import pytest

from record_fixtures import blob_payloads, records

from pob2opt.domain.enums import Fidelity, ResultStatus
from pob2opt.evaluation import (ADAPTER_VERSION, BlobBuildDocuments,
                                BuildDocument, CheckoutIdentity, EngineAdapter,
                                EngineCrash, EngineInvalidInput,
                                EngineProfileMismatch, EngineState,
                                EngineUnsupported, MappingBuildDocuments,
                                WorkerSpec, pob_worker_spec, redact_diagnostic,
                                resolve_checkout, timeout_for)
from pob2opt.evaluation.protocol import (DETAILED_TIMEOUT_S, OP_CREATE_BLANK_BUILD,
                                         SCREEN_TIMEOUT_S)
from pob2opt.storage.blobs import BlobStore

ENTRY = "synthetic_workers:SyntheticSession"
SYNTHETIC_COMMIT = "1" * 40

#: Short enough to keep the suite quick, long enough to survive a cold spawn.
START_TIMEOUT_S = 60.0
REQUEST_TIMEOUT_S = 20.0


# ------------------------------------------------------------------ helpers

def synthetic_checkout(commit: str = SYNTHETIC_COMMIT,
                       dirty: str | None = None) -> CheckoutIdentity:
    return CheckoutIdentity(root="SYNTHETIC-NOT-POB", commit=commit,
                            dirty_hash=dirty, reason=None)


def make_adapter(**extra_config) -> EngineAdapter:
    spec = WorkerSpec(entry=ENTRY, pob_root=None, quiet=True, extra=extra_config)
    return EngineAdapter(spec, checkout=synthetic_checkout(),
                         screen_timeout_s=REQUEST_TIMEOUT_S,
                         detailed_timeout_s=REQUEST_TIMEOUT_S,
                         start_timeout_s=START_TIMEOUT_S)


@pytest.fixture()
def adapter():
    with make_adapter() as live:
        yield live


@pytest.fixture()
def fixture_build():
    return records()["build_spec"]


@pytest.fixture()
def fixture_profile():
    """The P01 profile, repinned to the commit the synthetic checkout reports."""
    return dataclasses.replace(records()["patch_profile"],
                               pob_commit=SYNTHETIC_COMMIT)


@pytest.fixture()
def documents(fixture_build):
    return MappingBuildDocuments({fixture_build.build_hash: "<SyntheticBuild/>"})


# ------------------------------------------------- case 1: parent stays put

def test_the_parent_working_directory_survives_a_worker_that_moves_its_own(
        tmp_path: Path, fixture_build, fixture_profile):
    """The worker chdirs into a directory the parent has never been in."""
    elsewhere = tmp_path / "worker-cwd"
    elsewhere.mkdir()
    before = os.getcwd()

    spec = WorkerSpec(entry=ENTRY, pob_root=None,
                      extra={"chdir_to": str(elsewhere)})
    adapter = EngineAdapter(spec, checkout=synthetic_checkout(),
                            documents=MappingBuildDocuments(
                                {fixture_build.build_hash: "<SyntheticBuild/>"}),
                            screen_timeout_s=REQUEST_TIMEOUT_S,
                            detailed_timeout_s=REQUEST_TIMEOUT_S,
                            start_timeout_s=START_TIMEOUT_S)
    try:
        snapshot = adapter.primitives(fixture_build, EngineState(), fixture_profile)
        assert Path(snapshot.identity.worker_cwd).resolve() == elsewhere.resolve()
        assert os.getcwd() == before
    finally:
        adapter.close()
    assert os.getcwd() == before


def test_evaluating_a_fixture_build_returns_a_snapshot_with_provenance(
        adapter, documents, fixture_build, fixture_profile):
    adapter.documents = documents
    snapshot = adapter.primitives(fixture_build, EngineState(), fixture_profile)

    assert snapshot.build_hash == fixture_build.build_hash
    assert snapshot.identity.adapter_version == ADAPTER_VERSION
    assert snapshot.identity.pob_commit == SYNTHETIC_COMMIT
    assert snapshot.identity.worker_pid == adapter.worker_pid
    assert snapshot.values
    assert snapshot.timeout_s == SCREEN_TIMEOUT_S or snapshot.timeout_s == REQUEST_TIMEOUT_S


def test_a_snapshot_never_claims_declared_primitive_semantics(
        adapter, documents, fixture_build, fixture_profile):
    """Units and ownership are P02-T04; nothing here may imply they exist."""
    adapter.documents = documents
    snapshot = adapter.primitives(fixture_build, EngineState(), fixture_profile)

    assert snapshot.semantics_status == "undeclared"
    assert snapshot.semantics_owner == "P02-T04"


def test_engine_state_configuration_actually_reaches_the_worker(
        adapter, documents, fixture_build, fixture_profile):
    adapter.documents = documents
    state = EngineState(config={"syntheticCondition": True})
    snapshot = adapter.primitives(fixture_build, state, fixture_profile)

    assert snapshot.values["config:syntheticCondition"] is True
    assert snapshot.state_applied["config"] == [["syntheticCondition", True]]


def test_fidelity_selects_the_declared_request_bound():
    assert timeout_for(Fidelity.SCREEN) == SCREEN_TIMEOUT_S
    assert timeout_for(Fidelity.DETAILED) == DETAILED_TIMEOUT_S


# ------------------------------------------- exact loading versus blank build

def test_load_exact_build_keeps_the_character_and_never_runs_opt_setup(adapter):
    loaded = adapter.load_exact_build(BuildDocument("h", "<SyntheticBuild/>"))

    assert loaded.opt_setup_called is False
    assert (loaded.allocated_nodes, loaded.equipped_items, loaded.socket_groups) \
        == (7, 2, 3)


def test_create_blank_build_is_the_only_operation_that_clears_the_character(adapter):
    blank = adapter.create_blank_build(level=28)

    assert blank.opt_setup_called is True
    assert (blank.equipped_items, blank.socket_groups) == (0, 0)


def test_an_empty_document_is_invalid_input_not_an_empty_character(adapter):
    with pytest.raises(EngineInvalidInput) as excinfo:
        adapter.load_exact_build(BuildDocument("h", "   "))

    assert excinfo.value.status is ResultStatus.INVALID_INPUT


# --------------------------------------------------------- document sourcing

def test_a_metadata_only_build_cannot_be_evaluated(fixture_build, fixture_profile,
                                                   tmp_path):
    """No raw blob means nothing faithful to load. Reconstruction is P02-T05."""
    adapter = make_adapter()
    adapter.documents = BlobBuildDocuments(BlobStore(tmp_path / "blobs"))
    metadata_only = dataclasses.replace(fixture_build, raw_blob_hashes=[])
    try:
        with pytest.raises(EngineInvalidInput, match="metadata-only"):
            adapter.primitives(metadata_only, EngineState(), fixture_profile)
    finally:
        adapter.close()


def test_the_stored_original_document_is_what_gets_loaded(tmp_path, fixture_build):
    store = BlobStore(tmp_path / "blobs")
    payload = blob_payloads()[fixture_build.raw_blob_hashes[0]]
    store.put(payload)

    document = BlobBuildDocuments(store).document_for(fixture_build)

    assert document.xml == payload.decode("utf-8")
    assert document.blob_hash == fixture_build.raw_blob_hashes[0]


def test_a_document_from_another_build_is_refused(adapter, fixture_build,
                                                  fixture_profile):
    other = BuildDocument(build_hash="some-other-build", xml="<SyntheticBuild/>")
    with pytest.raises(EngineInvalidInput, match="does not belong"):
        adapter.primitives(fixture_build, EngineState(), fixture_profile,
                           document=other)


def test_no_document_store_is_an_error_not_an_invented_build(adapter, fixture_build,
                                                             fixture_profile):
    with pytest.raises(EngineInvalidInput, match="document store"):
        adapter.primitives(fixture_build, EngineState(), fixture_profile)


# -------------------------------------------------------------- patch profile

def test_a_profile_pinning_a_different_commit_is_refused(adapter, documents,
                                                         fixture_build):
    adapter.documents = documents
    elsewhere = dataclasses.replace(records()["patch_profile"], pob_commit="f" * 40)

    with pytest.raises(EngineProfileMismatch) as excinfo:
        adapter.primitives(fixture_build, EngineState(), elsewhere)

    assert excinfo.value.status is ResultStatus.INVALID_INPUT


def test_a_modified_checkout_is_refused_when_pinning_is_required(
        documents, fixture_build, fixture_profile):
    spec = WorkerSpec(entry=ENTRY, pob_root=None)
    adapter = EngineAdapter(spec, documents=documents,
                            checkout=synthetic_checkout(dirty="d" * 64),
                            require_pinned_checkout=True,
                            start_timeout_s=START_TIMEOUT_S)
    try:
        with pytest.raises(EngineProfileMismatch, match="local modifications"):
            adapter.primitives(fixture_build, EngineState(), fixture_profile)
    finally:
        adapter.close()


def test_an_unknown_commit_is_refused_when_pinning_is_required(
        documents, fixture_build, fixture_profile):
    spec = WorkerSpec(entry=ENTRY, pob_root=None)
    unknown = CheckoutIdentity("SYNTHETIC-NOT-POB", None, None, "git is not on PATH")
    adapter = EngineAdapter(spec, documents=documents, checkout=unknown,
                            require_pinned_checkout=True,
                            start_timeout_s=START_TIMEOUT_S)
    try:
        with pytest.raises(EngineProfileMismatch, match="unknown"):
            adapter.primitives(fixture_build, EngineState(), fixture_profile)
    finally:
        adapter.close()


# ------------------------------------------------- case 3: process replacement

def test_a_dead_worker_is_replaced_by_a_new_process_not_a_reset():
    adapter = make_adapter(behavior="die", die_on=OP_CREATE_BLANK_BUILD,
                           exit_code=70)
    try:
        first = adapter.identity().worker_pid

        with pytest.raises(EngineCrash) as excinfo:
            adapter.create_blank_build(level=28)
        assert excinfo.value.status is ResultStatus.ENGINE_CRASH
        assert not adapter.worker_alive

        second = adapter.load_exact_build(BuildDocument("h", "<SyntheticBuild/>"))
        assert second.opt_setup_called is False
        assert adapter.identity().worker_pid != first
        assert adapter.replacements == 1
        assert adapter.worker_pids[0] == first
    finally:
        adapter.close()


def test_restart_worker_is_the_only_recovery_and_it_changes_the_process(adapter):
    first = adapter.identity().worker_pid
    second = adapter.restart_worker()

    assert second != first
    assert adapter.identity().worker_pid == second
    assert adapter.generation == 2


def test_the_adapter_offers_no_reset_that_reuses_a_crashed_process():
    """A reset after a native crash is exactly the thing P02-T01 forbids."""
    assert not hasattr(EngineAdapter, "reset")


def test_closing_the_adapter_terminates_its_worker():
    adapter = make_adapter()
    adapter.identity()
    handle = adapter._handle
    adapter.close()

    assert handle.dead
    assert not handle.process.is_alive()


# --------------------------------------------------------------- typed errors

def test_an_unknown_operation_is_unsupported_not_a_crash(adapter):
    with pytest.raises(EngineUnsupported) as excinfo:
        adapter._request("not_an_operation", {}, REQUEST_TIMEOUT_S)

    assert excinfo.value.status is ResultStatus.UNSUPPORTED
    assert adapter.worker_alive, "a rejected operation must not kill the worker"


def test_a_worker_that_cannot_start_reports_a_typed_internal_error():
    adapter = make_adapter(behavior="startup_fail",
                           startup_message="synthetic startup failure")
    try:
        with pytest.raises(Exception) as excinfo:
            adapter.identity()
        assert excinfo.value.status is ResultStatus.INTERNAL_ERROR
        assert "synthetic startup failure" in excinfo.value.diagnostic
    finally:
        adapter.close()


def test_every_error_converts_to_a_storable_error_detail(adapter):
    try:
        adapter.load_exact_build(BuildDocument("h", ""))
    except EngineInvalidInput as exc:
        detail = exc.as_error_detail()

    assert detail.code is ResultStatus.INVALID_INPUT
    assert detail.stage
    assert detail.diagnostic


def test_diagnostics_do_not_carry_absolute_paths():
    text = redact_diagnostic(
        r"failed loading C:\Users\someone\PathOfBuilding-PoE2\src\Modules\Build.lua")

    assert "C:\\Users" not in text
    assert "Build.lua" in text


# --------------------------------------------------- paths resolved pre-spawn

def test_pob_worker_spec_resolves_every_path_before_a_spawn_can_happen(tmp_path):
    root = tmp_path / "checkout"
    (root / "runtime").mkdir(parents=True)
    spec = pob_worker_spec(root)

    assert Path(spec.pob_root).is_absolute()
    assert spec.helper_lua
    for path in spec.helper_lua:
        assert Path(path).is_absolute()
        assert Path(path).is_file()


def test_a_missing_checkout_is_refused_before_a_process_is_started(tmp_path):
    with pytest.raises(EngineInvalidInput, match="checkout not found"):
        pob_worker_spec(tmp_path / "absent")


def test_a_missing_helper_script_is_refused_before_a_process_is_started(tmp_path):
    root = tmp_path / "checkout"
    (root / "runtime").mkdir(parents=True)
    with pytest.raises(EngineInvalidInput, match="helper Lua not found"):
        pob_worker_spec(root, helper_lua=("no_such_helper.lua",))


# ------------------------------------------------------- checkout resolution

def test_an_unversioned_directory_reports_an_unknown_commit(tmp_path):
    identity = resolve_checkout(tmp_path, use_cache=False)

    assert identity.commit is None
    assert identity.is_pinned is False
    assert identity.reason


def test_a_missing_directory_is_unknown_not_an_exception(tmp_path):
    identity = resolve_checkout(tmp_path / "absent", use_cache=False)

    assert identity.commit is None
    assert "not found" in identity.reason


def test_a_clean_checkout_reports_a_bare_commit_and_no_dirty_hash(tmp_path):
    root = make_git_repo(tmp_path / "clean")
    identity = resolve_checkout(root, use_cache=False)

    assert identity.commit and identity.commit.strip() == identity.commit
    assert len(identity.commit) == 40
    assert identity.dirty_hash is None
    assert identity.is_pinned is True


def test_an_untracked_file_makes_the_checkout_unpinned(tmp_path):
    root = make_git_repo(tmp_path / "dirty")
    (root / "scratch.txt").write_text("left behind by an earlier session\n")
    identity = resolve_checkout(root, use_cache=False)

    assert identity.dirty_hash is not None
    assert identity.is_pinned is False
    assert "differs" in identity.reason


def make_git_repo(root: Path) -> Path:
    import subprocess

    git = shutil.which("git")
    if git is None:  # pragma: no cover - git is a documented prerequisite
        pytest.skip("git is not on PATH")
    root.mkdir(parents=True)
    (root / "README.md").write_text("synthetic checkout\n", encoding="utf-8")
    env = dict(os.environ, GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@example.invalid",
               GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@example.invalid")
    for argv in (["init", "-q"], ["add", "README.md"],
                 ["commit", "-qm", "synthetic"]):
        subprocess.run([git, "-C", str(root), *argv], check=True,
                       capture_output=True, env=env)
    return root
