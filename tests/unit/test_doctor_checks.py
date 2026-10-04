"""P00-T03 acceptance: `pob2opt doctor` fixture scenarios.

Covers the four required environments (missing directory, missing DLL,
incompatible profile, valid offline environment) plus the behavioural
guarantees: no secrets in the output, no working-directory change, and a
working invocation from a directory whose path contains spaces.

Every scenario is built from a temporary directory. No check in this file
inspects the real machine's PoB checkout.
"""

from __future__ import annotations

import json
import os
import struct
import subprocess
import sys
from pathlib import Path

import pytest

from pob2opt import doctor

SECRET_COOKIE = "FAKE-POESESSID-VALUE-ac9f12"


# ----------------------------------------------------------------- scenarios

def _write_pe(path: Path, machine: int = 0x8664) -> None:
    """A minimal file with a readable PE COFF header, for the bitness check."""
    path.parent.mkdir(parents=True, exist_ok=True)
    header = bytearray(0x50)
    header[0:2] = b"MZ"
    header[0x3C:0x40] = struct.pack("<I", 0x40)
    header[0x40:0x44] = b"PE\0\0"
    header[0x44:0x46] = struct.pack("<H", machine)
    path.write_bytes(bytes(header))


def make_pob_checkout(root: Path, *, dll: bool = True, dll_machine: int = 0x8664,
                      complete_layout: bool = True) -> Path:
    """A fake PoB2 checkout with just the entries doctor looks for."""
    root.mkdir(parents=True, exist_ok=True)
    if dll:
        _write_pe(root / "runtime" / "lua51.dll", dll_machine)
    (root / "src").mkdir(parents=True, exist_ok=True)
    (root / "src" / "HeadlessWrapper.lua").write_text("-- fixture\n", encoding="utf-8")
    if complete_layout:
        (root / "src" / "Launch.lua").write_text("-- fixture\n", encoding="utf-8")
    (root / "src" / "Data").mkdir(exist_ok=True)
    (root / "src" / "Data" / "Gems.lua").write_text("return {}\n", encoding="utf-8")
    (root / "src" / "TreeData" / "0_5").mkdir(parents=True, exist_ok=True)
    (root / "manifest.xml").write_text("<Manifest><Version number='0.0.0'/></Manifest>\n",
                                       encoding="utf-8")
    return root


@pytest.fixture()
def repo_like(tmp_path: Path) -> Path:
    """A directory standing in for the repository root."""
    root = tmp_path / "repo"
    (root / "pob2-optimizer" / "pob2opt").mkdir(parents=True)
    (root / "pob2-mcp" / "pob2mcp").mkdir(parents=True)
    return root


def collect(repo_like: Path, tmp_path: Path, **over):
    kwargs = dict(env={}, repo_root=repo_like, cwd=tmp_path, home=tmp_path / "home")
    kwargs.update(over)
    return doctor.collect(**kwargs)


# ------------------------------------------------------------------ scenario 1

def test_missing_pob_directory_blocks_engine_but_not_offline_work(repo_like, tmp_path):
    report = collect(repo_like, tmp_path, pob_root=str(tmp_path / "nowhere"))

    assert report.by_name("pob_directory").status == doctor.MISSING
    assert report.by_name("pob_runtime_dll").status == doctor.MISSING
    assert "engine" in report.blocked_capabilities
    # Offline capability is reported separately and is not blocked by the engine.
    assert report.by_name("python_runtime").status == doctor.OK
    assert report.by_name("run_location").status == doctor.OK
    assert "offline_pipeline" not in report.blocked_capabilities
    # Exit code 3 = a missing dependency prevents the requested operation.
    assert report.exit_code == doctor.EXIT_MISSING_DEPENDENCY


# ------------------------------------------------------------------ scenario 2

def test_missing_dll_is_reported_separately_from_a_missing_directory(repo_like, tmp_path):
    root = make_pob_checkout(tmp_path / "pob", dll=False)
    report = collect(repo_like, tmp_path, pob_root=str(root))

    assert report.by_name("pob_directory").status == doctor.OK
    assert report.by_name("pob_runtime_dll").status == doctor.MISSING
    assert "lua51.dll" in report.by_name("pob_runtime_dll").summary
    # The checkout exists but cannot run, so the profile is incompatible too.
    assert report.by_name("pob_profile").status == doctor.INCOMPATIBLE
    assert report.by_name("pob_catalog").status == doctor.OK
    assert report.exit_code == doctor.EXIT_MISSING_DEPENDENCY


# ------------------------------------------------------------------ scenario 3

def test_incompatible_profile_names_the_absent_layout_entries(repo_like, tmp_path):
    root = make_pob_checkout(tmp_path / "pob", complete_layout=False)
    report = collect(repo_like, tmp_path, pob_root=str(root))

    profile = report.by_name("pob_profile")
    assert profile.status == doctor.INCOMPATIBLE
    assert "src/Launch.lua" in profile.summary
    assert profile.data["markers"]["src/Launch.lua"] is False
    assert profile.data["markers"]["src/HeadlessWrapper.lua"] is True
    # Layout evidence is never a patch approval.
    assert profile.data["patch_profile_approved"] is False
    assert profile.data["patch_profile_owner"] == "P02-T02"


def test_architecture_mismatch_is_incompatible_not_missing(repo_like, tmp_path):
    root = make_pob_checkout(tmp_path / "pob", dll_machine=0x014C)  # x86
    report = collect(repo_like, tmp_path, pob_root=str(root))

    runtime = report.by_name("pob_runtime_dll")
    if struct.calcsize("P") * 8 == 64:
        assert runtime.status == doctor.INCOMPATIBLE
        assert runtime.data["architecture"] == "x86"
    else:  # pragma: no cover - this suite is specified for 64-bit hosts
        assert runtime.status == doctor.OK


# ------------------------------------------------------------------ scenario 4

def test_valid_offline_environment_passes_every_blocking_check(repo_like, tmp_path):
    root = make_pob_checkout(tmp_path / "pob")
    # Make the repo-root check pass by pointing it at the real working tree.
    real_repo = Path(doctor.__file__).resolve().parents[2]
    report = doctor.collect(pob_root=str(root), env={}, repo_root=real_repo,
                            cwd=tmp_path, home=tmp_path / "home")

    assert report.failed_blocking == ()
    assert report.exit_code == doctor.EXIT_OK
    # Provider access stays unresolved; that is informational, never blocking.
    providers = report.by_name("providers")
    assert providers.status == doctor.UNKNOWN
    assert providers.blocking is False
    assert "live_market" in report.blocked_capabilities


# ---------------------------------------------------------------- no secrets

def test_configured_credentials_are_reported_as_booleans_only(repo_like, tmp_path):
    home = tmp_path / "home"
    (home / ".pob2-mcp").mkdir(parents=True)
    (home / ".pob2-mcp" / "token.json").write_text(
        json.dumps({"access_token": "FAKE-TOKEN-7731", "refresh_token": "FAKE-REFRESH"}),
        encoding="utf-8")

    report = collect(repo_like, tmp_path, env={"POESESSID": SECRET_COOKIE}, home=home)
    providers = report.by_name("providers")

    assert providers.data["providers"]["poe_trade"]["credential_present"] is True
    assert providers.data["providers"]["poe_oauth"]["credential_present"] is True
    assert providers.data["contacted_any_provider"] is False
    assert providers.data["started_oauth"] is False

    serialized = json.dumps(report.to_dict())
    assert SECRET_COOKIE not in serialized
    assert "FAKE-TOKEN-7731" not in serialized
    assert "FAKE-REFRESH" not in serialized
    assert "POESESSID=" not in serialized


# ------------------------------------------------------------- no side effects

def test_doctor_does_not_create_the_run_directory(repo_like, tmp_path):
    runs = tmp_path / "workspace" / "runs"
    report = doctor.collect(pob_root=str(tmp_path / "nowhere"), run_root=str(runs),
                            env={}, repo_root=repo_like, cwd=tmp_path, home=tmp_path)

    assert not runs.exists(), "doctor must inspect, not create, the run location"
    assert report.by_name("run_location").status == doctor.OK
    assert report.by_name("run_location").data["exists"] is False


def test_collect_does_not_change_the_working_directory(repo_like, tmp_path):
    before = os.getcwd()
    root = make_pob_checkout(tmp_path / "pob")
    doctor.collect(pob_root=str(root), env={}, repo_root=repo_like, cwd=tmp_path, home=tmp_path)
    assert os.getcwd() == before


# ------------------------------------------------------------------- the CLI

def _run_cli(cwd: Path, repo_root: Path, *args: str, env_extra=None):
    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join(
        [str(repo_root / "pob2-optimizer"), str(repo_root / "pob2-mcp")])
    env.pop("POB2_ROOT", None)
    env.update(env_extra or {})
    return subprocess.run(
        [sys.executable, "-m", "pob2opt.cli", "doctor", *args],
        cwd=str(cwd), env=env, capture_output=True, text=True, timeout=120,
    )


def test_cli_json_goes_to_stdout_and_prose_to_stderr(tmp_path, repo_root):
    root = make_pob_checkout(tmp_path / "pob")
    proc = _run_cli(tmp_path, repo_root, "--json", "--pob-root", str(root))

    payload = json.loads(proc.stdout)
    assert payload["schema_version"] == doctor.SCHEMA_VERSION
    assert payload["tool"] == "pob2opt doctor"
    assert {c["name"] for c in payload["checks"]} >= {
        "python_runtime", "packages", "pob_directory", "pob_runtime_dll",
        "pob_profile", "pob_catalog", "providers", "run_location"}
    assert "pob2opt doctor" in proc.stderr
    assert proc.returncode == payload["exit_code"]


def test_cli_reports_missing_engine_with_exit_code_3(tmp_path, repo_root):
    proc = _run_cli(tmp_path, repo_root, "--json", "--pob-root", str(tmp_path / "absent"))

    payload = json.loads(proc.stdout)
    assert proc.returncode == doctor.EXIT_MISSING_DEPENDENCY
    assert "engine" in payload["summary"]["blocked_capabilities"]
    # Offline checks still pass and say so.
    statuses = {c["name"]: c["status"] for c in payload["checks"]}
    assert statuses["python_runtime"] == doctor.OK
    assert statuses["run_location"] == doctor.OK


def test_cli_works_from_a_directory_containing_spaces(tmp_path, repo_root):
    workdir = tmp_path / "a directory with spaces"
    workdir.mkdir()
    pob = make_pob_checkout(tmp_path / "pob root with spaces")

    proc = _run_cli(workdir, repo_root, "--json", "--pob-root", str(pob))

    payload = json.loads(proc.stdout)
    assert payload["exit_code"] == proc.returncode
    directory = next(c for c in payload["checks"] if c["name"] == "pob_directory")
    assert directory["status"] == doctor.OK
    assert "spaces" in directory["data"]["path"]
    run_location = next(c for c in payload["checks"] if c["name"] == "run_location")
    assert str(workdir) in run_location["data"]["run_root"]


def test_cli_rejects_an_unknown_option_with_exit_code_2(tmp_path, repo_root):
    proc = _run_cli(tmp_path, repo_root, "--not-a-real-option")
    assert proc.returncode == doctor.EXIT_INVALID_REQUEST


def test_doctor_subcommand_does_not_reach_the_legacy_phase_pipeline(tmp_path, repo_root):
    """`doctor` must not inherit the legacy parser's required --level/--out."""
    proc = _run_cli(tmp_path, repo_root, "--pob-root", str(tmp_path / "absent"))
    assert "--level" not in proc.stderr
    assert "phase" not in proc.stderr.lower().split("blocked")[0]
    assert proc.returncode == doctor.EXIT_MISSING_DEPENDENCY
