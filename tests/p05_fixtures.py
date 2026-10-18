"""Shared P05 fixtures: synthetic item texts, the example 5 capture and a
catalog bundle for the CLI.

``tests/fixtures/p05`` is written by ``scripts/p05_make_fixtures.py`` and
listed in ``tests/fixtures/manifest.json`` with origin ``synthetic``. The
catalog bundle is exported by ``pob2opt catalog export`` from the P02 row
capture plus the P04 slice, as in ``test_p04_parse_cli.py``.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

import p04_fixtures as p04

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "p05"
REPO = Path(__file__).resolve().parents[1]
P02_EVIDENCE = REPO / "docs" / "evidence" / "P02"


@lru_cache(maxsize=1)
def game_items() -> dict[str, str]:
    return json.loads((FIXTURES / "game-items.json").read_text(
        encoding="utf-8"))["items"]


def capture_data() -> dict:
    return json.loads((FIXTURES / "capture-example5.json").read_text(
        encoding="utf-8"))


def capture_bytes(data: dict | None = None) -> bytes:
    if data is None:
        return (FIXTURES / "capture-example5.json").read_bytes()
    return json.dumps(data, indent=2).encode("utf-8")


def document(payload: bytes, record_id: str = "src/p05",
             media_type: str = "application/json"):
    return p04.source(payload, record_id=record_id, media_type=media_type)


def context(**overrides):
    return p04.context(**overrides)


def merged_rows(path: Path) -> Path:
    """The P02 row capture with the P04 slice's rows added to each table."""
    capture = json.loads((P02_EVIDENCE / "catalog-rows-slice.json").read_text(
        encoding="utf-8"))
    keys = {"classes": "classId", "passive_nodes": "id", "gems": "id",
            "granted_skills": "id", "item_bases": "name",
            "item_modifiers": ("group", "id"), "slots": "name",
            "config_variables": "var"}
    for table, rows in p04.slice_data()["tables"].items():
        key = keys[table]

        def ident(row):
            return tuple(row.get(k) for k in key) if isinstance(key, tuple) \
                else row.get(key)
        known = {ident(row) for row in capture["tables"].get(table, [])}
        capture["tables"].setdefault(table, []).extend(
            row for row in rows if ident(row) not in known)
    path.write_text(json.dumps(capture), encoding="utf-8")
    return path


def export_bundle(out: Path) -> Path:
    from pob2opt import cli

    rows = merged_rows(out / "rows.json")
    code = cli.main(["catalog", "export",
                     "--profile", str(P02_EVIDENCE / "catalog-profile-request.json"),
                     "--out", str(out / "bundle"), "--rows", str(rows),
                     "--release-evidence", str(P02_EVIDENCE / "release")])
    assert code == 0
    return out / "bundle"
