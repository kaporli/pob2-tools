"""The fixture inventory is accurate and honestly labelled (P00-T02).

Fixtures are the easiest place for a synthetic number to be mistaken later for a
measurement. The manifest records what each file is and where it came from; this
test keeps it true.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest


@pytest.fixture(scope="module")
def manifest(fixtures_dir: Path) -> dict:
    return json.loads((fixtures_dir / "manifest.json").read_text(encoding="utf-8"))


def test_every_fixture_file_is_listed(fixtures_dir: Path, manifest: dict):
    on_disk = {
        str(p.relative_to(fixtures_dir)).replace("\\", "/")
        for p in fixtures_dir.rglob("*")
        if p.is_file() and p.name != "manifest.json"
    }
    listed = {entry["path"] for entry in manifest["fixtures"]}
    assert listed == on_disk


def test_recorded_hashes_match_the_files(fixtures_dir: Path, manifest: dict):
    for entry in manifest["fixtures"]:
        data = (fixtures_dir / entry["path"]).read_bytes()
        assert hashlib.sha256(data).hexdigest() == entry["sha256"], entry["path"]
        assert len(data) == entry["bytes"], entry["path"]


def test_every_fixture_is_declared_synthetic(manifest: dict):
    assert "SYNTHETIC" in manifest["statement"]
    for entry in manifest["fixtures"]:
        assert entry["origin"] == "synthetic", entry["path"]
        assert entry["caveat"].strip(), entry["path"]


def test_json_fixtures_carry_their_own_synthetic_marker(fixtures_dir: Path, manifest: dict):
    for entry in manifest["fixtures"]:
        path = fixtures_dir / entry["path"]
        if path.suffix != ".json":
            continue
        payload = json.loads(path.read_text(encoding="utf-8"))
        assert payload["kind"] == "synthetic", entry["path"]
        assert payload["purpose"].strip(), entry["path"]
        assert payload.get("not_a_claim", "").strip(), entry["path"]


def test_xml_fixtures_carry_a_synthetic_comment(fixtures_dir: Path, manifest: dict):
    for entry in manifest["fixtures"]:
        path = fixtures_dir / entry["path"]
        if path.suffix != ".xml":
            continue
        assert "SYNTHETIC" in path.read_text(encoding="utf-8"), entry["path"]
