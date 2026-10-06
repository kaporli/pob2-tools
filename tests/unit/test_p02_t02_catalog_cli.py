"""P02-T02 offline lane: `pob2opt catalog export` as a command.

Runs the real dispatcher in-process over the committed row slice, so the
argument handling, the exit codes from interfaces.md and the bundle layout
are exercised without PoB and without the network.
"""

from __future__ import annotations

import json
from pathlib import Path

from pob2opt import cli
from pob2opt.catalog import cli as catalog_cli

REPO_ROOT = Path(__file__).resolve().parents[2]
EVIDENCE = REPO_ROOT / "docs" / "evidence" / "P02"
SLICE = EVIDENCE / "catalog-rows-slice.json"
RELEASE_DIR = EVIDENCE / "release"
REQUEST = EVIDENCE / "catalog-profile-request.json"
SAMPLE_BUILD = EVIDENCE / "sample-build-ranger-quarterstaff.xml"


def run(argv, capsys):
    code = cli.main(["catalog", *argv])
    captured = capsys.readouterr()
    return code, captured


def test_an_export_from_a_row_capture_writes_a_complete_bundle(tmp_path, capsys):
    out = tmp_path / "bundle"
    code, captured = run(["export", "--profile", str(REQUEST),
                          "--out", str(out), "--rows", str(SLICE),
                          "--release-evidence", str(RELEASE_DIR),
                          "--resolve-build", str(SAMPLE_BUILD)], capsys)
    assert code == catalog_cli.EXIT_OK, captured.err
    summary = json.loads(captured.out)
    assert summary["patch_id"] == "0.5.5e"
    assert summary["validation_errors"] == []
    assert (out / "catalog.json").is_file()
    assert (out / "patch_profile.json").is_file()
    assert (out / "gaps.json").is_file()
    assert list((out / "blobs").iterdir())
    # The machine-readable half is stdout; the prose half is stderr.
    assert captured.err.strip()
    assert "compatibility" in captured.err
    resolution = summary["resolutions"]["sample-build-ranger-quarterstaff.xml"]
    assert resolution["complete"] is True


def test_every_evidence_blob_named_by_a_document_is_on_disk(tmp_path, capsys):
    out = tmp_path / "bundle"
    run(["export", "--profile", str(REQUEST), "--out", str(out),
         "--rows", str(SLICE), "--release-evidence", str(RELEASE_DIR)], capsys)
    for path in (out / "evidence").iterdir():
        document = json.loads(path.read_text(encoding="utf-8"))
        blob = out / "blobs" / document["blob_hash"]
        assert blob.is_file(), document["record_id"]
        assert blob.stat().st_size == document["byte_count"]


def test_a_missing_request_file_is_exit_two(tmp_path, capsys):
    code, captured = run(["export", "--profile", str(tmp_path / "nope.json"),
                          "--out", str(tmp_path / "out"),
                          "--rows", str(SLICE)], capsys)
    assert code == catalog_cli.EXIT_INVALID_REQUEST
    assert "not usable" in captured.err


def test_an_unknown_request_key_is_exit_two(tmp_path, capsys):
    request = tmp_path / "request.json"
    request.write_text(json.dumps({"schema_version": 1, "game": "poe2",
                                   "secret_mode": True}), encoding="utf-8")
    code, captured = run(["export", "--profile", str(request),
                          "--out", str(tmp_path / "out"),
                          "--rows", str(SLICE)], capsys)
    assert code == catalog_cli.EXIT_INVALID_REQUEST
    assert "secret_mode" in captured.err


def test_a_future_request_schema_is_exit_two(tmp_path, capsys):
    request = tmp_path / "request.json"
    request.write_text(json.dumps({"schema_version": 99}), encoding="utf-8")
    code, captured = run(["export", "--profile", str(request),
                          "--out", str(tmp_path / "out"),
                          "--rows", str(SLICE)], capsys)
    assert code == catalog_cli.EXIT_INVALID_REQUEST
    assert "schema_version" in captured.err


def test_no_engine_and_no_capture_is_exit_three(tmp_path, capsys, monkeypatch):
    monkeypatch.delenv("POB2_ROOT", raising=False)
    code, captured = run(["export", "--profile", str(REQUEST),
                          "--out", str(tmp_path / "out")], capsys)
    assert code == catalog_cli.EXIT_MISSING_DEPENDENCY
    assert "no PoB checkout" in captured.err


def test_without_release_evidence_the_bundle_says_unknown(tmp_path, capsys):
    out = tmp_path / "bundle"
    code, captured = run(["export", "--profile", str(REQUEST),
                          "--out", str(out), "--rows", str(SLICE),
                          "--release-evidence", str(tmp_path / "empty")], capsys)
    assert code == catalog_cli.EXIT_OK
    summary = json.loads(captured.out)
    assert summary["patch_id"] == "unknown"
    assert summary["compatibility"] == "unknown"


def test_catalog_without_a_subcommand_is_exit_two(capsys):
    code, captured = run([], capsys)
    assert code == 2
    assert "catalog export" in captured.err


def test_the_command_is_dispatched_before_the_legacy_phase_parser():
    assert "catalog" in cli.NEW_COMMANDS
    assert "catalog" not in cli.PHASES


def test_the_doctors_patch_profile_owner_now_names_a_command_that_exists(tmp_path):
    """`tests/unit/test_doctor_checks.py` asserts the owner is P02-T02.

    That claim was a forward reference. It is only true while the command
    the doctor names can actually be run, so this pins the two together.
    """
    from pob2opt import doctor

    check = doctor.check_pob_profile(tmp_path)
    assert check.data["patch_profile_owner"] == "P02-T02"
    assert check.data["patch_profile_approved"] is False
    command = check.data.get("patch_profile_command", "")
    assert command.startswith("pob2opt catalog export")
    assert "catalog" in cli.NEW_COMMANDS
