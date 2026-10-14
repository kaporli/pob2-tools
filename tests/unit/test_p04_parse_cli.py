"""`pob2opt parse --source ID --corpus DIR --catalog DIR` end to end. Offline.

A local PoB document is ingested by the P03 acquisition service, a catalog
bundle is exported by `pob2opt catalog export` from committed rows (the P02
slice with the P04 slice's tables added), and the parse command stores the
records in the corpus, where they resolve against each other.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

import p04_fixtures as fx
from pob2opt import cli
from pob2opt.acquisition.service import AcquisitionService
from pob2opt.parsers import cli as parse_cli
from pob2opt.storage import RunStore

REPO = Path(__file__).resolve().parents[2]
EVIDENCE = REPO / "docs" / "evidence" / "P02"


def merged_rows(path: Path) -> Path:
    """The P02 row capture with the P04 slice's rows added to each table."""
    capture = json.loads((EVIDENCE / "catalog-rows-slice.json").read_text(
        encoding="utf-8"))
    keys = {"classes": "classId", "passive_nodes": "id", "gems": "id",
            "granted_skills": "id", "item_bases": "name",
            "item_modifiers": ("group", "id"), "slots": "name",
            "config_variables": "var"}
    for table, rows in fx.slice_data()["tables"].items():
        key = keys[table]

        def ident(row):
            return tuple(row.get(k) for k in key) if isinstance(key, tuple) \
                else row.get(key)
        known = {ident(row) for row in capture["tables"].get(table, [])}
        capture["tables"].setdefault(table, []).extend(
            row for row in rows if ident(row) not in known)
    path.write_text(json.dumps(capture), encoding="utf-8")
    return path


@pytest.fixture(scope="module")
def bundle(tmp_path_factory):
    out = tmp_path_factory.mktemp("catalog")
    rows = merged_rows(out / "rows.json")
    code = cli.main(["catalog", "export",
                     "--profile", str(EVIDENCE / "catalog-profile-request.json"),
                     "--out", str(out / "bundle"), "--rows", str(rows),
                     "--release-evidence", str(EVIDENCE / "release")])
    assert code == 0
    return out / "bundle"


def ingest(corpus: Path, name: str) -> str:
    path = corpus.parent / ("%s.xml" % name)
    path.write_bytes(fx.document_bytes(name))
    with RunStore.open_corpus(corpus) as store:
        outcome = AcquisitionService(store).ingest_file(path, provider="local")
    assert outcome.ok
    return outcome.source_document_id


def run(argv, capsys):
    code = cli.main(["parse", *argv])
    captured = capsys.readouterr()
    return code, captured


def test_a_stored_document_parses_into_stored_records(tmp_path, bundle,
                                                      capsys):
    corpus = tmp_path / "corpus"
    source_id = ingest(corpus, "variants")
    code, captured = run(["--source", source_id, "--corpus", str(corpus),
                          "--catalog", str(bundle),
                          "--tree-version", fx.slice_data()["tree_version"]],
                         capsys)
    assert code == parse_cli.EXIT_OK, captured.err
    report = json.loads(captured.out)
    assert report["status"] == "partial"  # the unlinked item set
    assert len(report["builds"]) == 2
    assert {b["parse_status"] for b in report["builds"]} == {"complete"}
    with RunStore.open_corpus(corpus) as store:
        for record_id in report["record_ids"]:
            assert store.has_record(record_id), record_id
        assert store.has_record(report["parse_result_id"])
        reports = store.validate_stored(["build_spec", "item_instance",
                                         "parse_result"])
        assert reports and all(r.ok for r in reports.values()), {
            rid: r.errors for rid, r in reports.items() if not r.ok}
        assert store.unresolved_references() == {}


def test_parsing_twice_reports_the_stored_result(tmp_path, bundle, capsys):
    corpus = tmp_path / "corpus"
    source_id = ingest(corpus, "b03")
    argv = ["--source", source_id, "--corpus", str(corpus),
            "--catalog", str(bundle)]
    first_code, first = run(argv, capsys)
    second_code, second = run(argv, capsys)
    assert (first_code, second_code) == (parse_cli.EXIT_OK, parse_cli.EXIT_OK)
    assert json.loads(second.out)["unchanged"] is True
    assert json.loads(first.out)["record_ids"] == \
        json.loads(second.out)["record_ids"]


def test_an_unknown_source_is_an_invalid_request(tmp_path, bundle, capsys):
    code, captured = run(["--source", "nope", "--corpus",
                          str(tmp_path / "corpus"), "--catalog", str(bundle)],
                         capsys)
    assert code == parse_cli.EXIT_INVALID_REQUEST
    assert "nope" in captured.err


def test_a_missing_catalog_bundle_blocks(tmp_path, capsys):
    code, captured = run(["--source", "x", "--corpus", str(tmp_path / "c"),
                          "--catalog", str(tmp_path / "none")], capsys)
    assert code == parse_cli.EXIT_BLOCKED
    assert "catalog export" in captured.err


def test_an_unsupported_document_exits_three(tmp_path, bundle, capsys):
    corpus = tmp_path / "corpus"
    path = tmp_path / "export.json"
    path.write_text('{"build": {"skills": ["Arc"]}}', encoding="utf-8")
    with RunStore.open_corpus(corpus) as store:
        outcome = AcquisitionService(store).ingest_file(path,
                                                        provider="maxroll")
    code, captured = run(["--source", outcome.source_document_id,
                          "--corpus", str(corpus), "--catalog", str(bundle)],
                         capsys)
    assert code == parse_cli.EXIT_BLOCKED
    report = json.loads(captured.out)
    assert report["status"] == "unsupported_format"
    assert report["issues"][0]["code"] == "provider_parser_blocked"
