"""P03-T01: `pob2opt source inspect` as a command, offline.

The command reports a recorded manifest. It has no fetch path and no flag that
makes it try one, so these tests run with the unit lane's socket guard in place
and nothing is skipped.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from pob2opt import cli
from pob2opt.sources import manifests

REPO_ROOT = Path(__file__).resolve().parents[2]
EVIDENCE = REPO_ROOT / "docs" / "evidence" / "P03"


def run(argv, capsys):
    code = cli.main(["source", *argv])
    captured = capsys.readouterr()
    return code, captured


def test_inspect_writes_the_manifest_and_a_report(tmp_path, capsys):
    code, out = run(["inspect", "--provider", "mobalytics",
                     "--out", str(tmp_path)], capsys)
    assert code == 0
    report = json.loads(out.out)
    assert report["provider"] == "mobalytics"
    assert report["acquisition_status"] == "access_blocked"
    assert report["support"] == {"listing_metadata": False,
                                 "full_build_data": False,
                                 "explanatory_prose": False}
    assert report["categories_inspected"] == []
    assert len(report["categories_not_inspected"]) == 5
    assert (tmp_path / "mobalytics-capabilities.json").is_file()
    assert (tmp_path / "mobalytics-inspect-report.json").is_file()
    # Status prose goes to stderr, machine output to stdout.
    assert "access_blocked" in out.err
    assert out.err.strip()


def test_every_recorded_provider_can_be_inspected(tmp_path, capsys):
    for name in ("mobalytics", "maxroll", "poe.ninja"):
        code, out = run(["inspect", "--provider", name,
                         "--out", str(tmp_path)], capsys)
        assert code == 0, name
        assert json.loads(out.out)["manifest_id"].startswith("p03-t01-")


def test_the_poe_ninja_report_names_its_one_reproducible_example(tmp_path, capsys):
    code, out = run(["inspect", "--provider", "poe-ninja",
                     "--out", str(tmp_path)], capsys)
    assert code == 0
    report = json.loads(out.out)
    assert report["has_reproducible_example"] is True
    assert report["acquisition_status"] == "unsupported_access"


def test_an_unknown_provider_is_a_missing_dependency_not_a_crash(tmp_path, capsys):
    code, out = run(["inspect", "--provider", "poe-vault",
                     "--out", str(tmp_path)], capsys)
    assert code == 3
    assert "unknown provider" in out.err
    assert list(tmp_path.iterdir()) == []


def test_a_missing_manifest_is_reported_as_missing(tmp_path, capsys):
    empty = tmp_path / "none"
    empty.mkdir()
    code, out = run(["inspect", "--provider", "maxroll", "--out", str(tmp_path),
                     "--manifest-dir", str(empty)], capsys)
    assert code == 3
    assert "no capability manifest" in out.err


def test_a_malformed_manifest_is_an_internal_failure_not_a_pass(tmp_path, capsys):
    broken_dir = tmp_path / "broken"
    broken_dir.mkdir()
    doc = json.loads((EVIDENCE / "maxroll-capabilities.json").read_text("utf-8"))
    del doc["support"]["full_build_data"]
    (broken_dir / "maxroll-capabilities.json").write_text(
        json.dumps(doc), encoding="utf-8")
    code, out = run(["inspect", "--provider", "maxroll", "--out", str(tmp_path),
                     "--manifest-dir", str(broken_dir)], capsys)
    assert code == 4
    assert "full_build_data" in out.err


def test_the_subcommand_refuses_anything_but_inspect(capsys):
    code, out = run(["crawl", "--provider", "mobalytics"], capsys)
    assert code == 2
    assert "source inspect" in out.err


# ------------------------------------------------------------ validation ---

@pytest.fixture
def good():
    return json.loads((EVIDENCE / "poe-ninja-capabilities.json").read_text("utf-8"))


def test_the_validator_accepts_the_recorded_manifest(good):
    assert manifests.validate_manifest(good, "poe-ninja") == []


def test_a_supported_flag_without_confirmation_is_rejected(good):
    doc = copy.deepcopy(good)
    doc["support"]["full_build_data"]["supported"] = True
    doc["support"]["full_build_data"]["confirmed"] = False
    problems = manifests.validate_manifest(doc, "poe-ninja")
    assert any("without confirmation" in p for p in problems)


def test_a_dropped_category_is_rejected(good):
    doc = copy.deepcopy(good)
    doc["representative_records"] = [r for r in doc["representative_records"]
                                     if r["category"] != "old_patch"]
    problems = manifests.validate_manifest(doc, "poe-ninja")
    assert any("omits old_patch" in p for p in problems)


def test_a_substituted_category_is_rejected(good):
    doc = copy.deepcopy(good)
    doc["representative_records"][2]["category"] = "whatever_was_handy"
    problems = manifests.validate_manifest(doc, "poe-ninja")
    assert any("unknown category" in p for p in problems)


def test_an_uninspected_category_without_a_reason_is_rejected(good):
    doc = copy.deepcopy(good)
    doc["representative_records"][0]["reason"] = ""
    problems = manifests.validate_manifest(doc, "poe-ninja")
    assert any("gives no reason" in p for p in problems)


def test_an_unresolvable_evidence_reference_is_rejected(good):
    doc = copy.deepcopy(good)
    doc["support"]["listing_metadata"]["evidence_ids"] = ["NINJ-E99"]
    problems = manifests.validate_manifest(doc, "poe-ninja")
    assert any("NINJ-E99" in p for p in problems)


def test_an_access_method_outside_the_contract_is_rejected(good):
    doc = copy.deepcopy(good)
    doc["access"]["permitted_access_method"] = "scraped_anyway"
    problems = manifests.validate_manifest(doc, "poe-ninja")
    assert any("not in the contract" in p for p in problems)


def test_a_looser_limit_than_the_interface_default_is_rejected(good):
    doc = copy.deepcopy(good)
    doc["limits"]["applied_defaults"]["max_attempts"] = 10
    problems = manifests.validate_manifest(doc, "poe-ninja")
    assert any("looser than" in p for p in problems)


def test_a_manifest_with_no_example_and_no_block_is_rejected(good):
    doc = copy.deepcopy(good)
    doc.pop("reproducible_acquisition_example")
    doc["blocked_cases"] = []
    problems = manifests.validate_manifest(doc, "poe-ninja")
    assert any("neither a reproducible example nor a blocked case" in p
               for p in problems)


def test_the_module_imports_no_http_client():
    """The capability reader must not be able to acquire anything."""
    source = (Path(manifests.__file__)).read_text("utf-8")
    for forbidden in ("import requests", "urllib.request", "http.client",
                      "import socket"):
        assert forbidden not in source, forbidden
