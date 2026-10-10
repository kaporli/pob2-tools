"""P03-T02 local acquisition: the four input kinds, idempotency and refusals.

Offline by construction. Nothing in this file opens a socket, and the engine is
never imported: acquisition has to work with no PoB checkout at all.
"""

from __future__ import annotations

import base64
import json

import sys
import zlib
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from pob2opt.acquisition import (
    AcquisitionService,
    AcquisitionState,
    MalformedContent,
    OversizedContent,
    UnsupportedContent,
    content,
    decode_build_code,
    detect_kind,
    source_document_id,
)
from pob2opt.acquisition.cli import main as ingest_main
from pob2opt.domain.enums import AccessMethod, AcquisitionStatus, Redistribution
from pob2opt.domain.identity import document_hash
from pob2opt.storage import RunStore

BUILD_XML = (b'<?xml version="1.0" encoding="UTF-8"?>\n'
             b'<PathOfBuilding><Build level="92" className="Ranger"'
             b' ascendClassName="Deadeye"/><Skills/><Tree/><Items/>'
             b'</PathOfBuilding>')
GUIDE_HTML = (b'<!doctype html><html><head><title>A guide</title></head>'
              b'<body><h1>Lightning Arrow</h1><script>alert(1)</script>'
              b'</body></html>')
EXPORT_JSON = json.dumps({"id": "abc123", "class": "Ranger",
                          "skills": ["Lightning Arrow"]}).encode("utf-8")


def build_code(xml: bytes = BUILD_XML) -> bytes:
    return base64.urlsafe_b64encode(zlib.compress(xml))


class ManualClock:
    """A clock a test can read. Wall time would hide an unslept wait."""

    def __init__(self) -> None:
        self.seconds = 0.0
        self.slept: list[float] = []

    def monotonic(self) -> float:
        return self.seconds

    def utcnow(self) -> str:
        moment = (datetime(2026, 10, 10, tzinfo=timezone.utc)
                  + timedelta(seconds=self.seconds))
        return moment.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"

    def sleep(self, seconds: float) -> None:
        self.slept.append(seconds)
        self.seconds += seconds


@pytest.fixture()
def service(tmp_path):
    store = RunStore.open_corpus(tmp_path / "corpus")
    yield AcquisitionService(store, clock=ManualClock(),
                             state=AcquisitionState.in_memory())
    store.close()


def _write(tmp_path: Path, name: str, payload: bytes) -> Path:
    path = tmp_path / name
    path.write_bytes(payload)
    return path


# ------------------------------------------------- the four input kinds ===

@pytest.mark.parametrize("name,payload,kind,media_type", [
    ("build.xml", BUILD_XML, "xml", "application/xml"),
    ("guide.html", GUIDE_HTML, "html", "text/html"),
    ("export.json", EXPORT_JSON, "json", "application/json"),
])
def test_saved_file_round_trips_to_a_raw_record(service, tmp_path, name,
                                                payload, kind, media_type):
    path = _write(tmp_path, name, payload)

    outcome = service.ingest_file(path, provider="fixture")

    assert outcome.status is AcquisitionStatus.OK
    assert outcome.created is True
    document = outcome.document
    assert document.media_type == media_type
    assert document.blob_hash == document_hash(payload)
    assert document.byte_count == len(payload)
    assert document.access_method is AccessMethod.LOCAL_FILE
    # The bytes come back out of the store unchanged, hash verified on read.
    assert service.store.read_payload(document.blob_hash) == payload
    assert detect_kind(payload, filename=name) == kind
    assert service.store.get_source(outcome.result.record_id).status is (
        AcquisitionStatus.OK)


def test_build_code_round_trips_and_keeps_the_code_it_was_given(service):
    code = build_code()

    outcome = service.ingest_build_code(code, provider="fixture")

    assert outcome.status is AcquisitionStatus.OK
    assert outcome.document.media_type == "text/vnd.pathofbuilding.code"
    assert outcome.document.blob_hash == document_hash(code)
    # The raw record is the code, not the XML inside it. P04 expands it.
    assert service.store.read_payload(outcome.document.blob_hash) == code
    assert decode_build_code(code) == BUILD_XML


def test_popularity_and_patch_stay_absent_rather_than_invented(service, tmp_path):
    outcome = service.ingest_file(_write(tmp_path, "b.xml", BUILD_XML),
                                  provider="fixture")

    document = outcome.document
    assert document.popularity == []          # empty means no signal observed
    assert document.declared_patch is None    # unknown, not a guess
    assert document.published_at is None
    assert document.updated_at is None
    assert document.redistribution is Redistribution.UNKNOWN
    assert document.source_url is None        # null for a local file


# ------------------------------------------------------------ idempotency ===

def test_repeated_input_writes_one_blob_and_one_record(service, tmp_path):
    first_path = _write(tmp_path, "build.xml", BUILD_XML)
    second_path = _write(tmp_path, "copy-of-build.xml", BUILD_XML)

    first = service.ingest_file(first_path, provider="fixture")
    second = service.ingest_file(first_path, provider="fixture")
    third = service.ingest_file(second_path, provider="fixture")

    assert first.created is True
    assert second.created is False and third.created is False
    assert first.source_document_id == second.source_document_id
    # Same bytes from another path are the same document: identity is content.
    assert third.source_document_id == first.source_document_id
    assert len(list(service.store.blobs.iter_hashes())) == 1
    assert len(service.store.source_history("fixture", None)) == 1
    # The attempts are still three separate events; failures must stay visible.
    rows = service.store.conn.execute(
        "SELECT COUNT(*) FROM source_record WHERE kind = 'acquisition_result'"
    ).fetchone()[0]
    assert rows == 3


def test_different_bytes_are_a_different_document(service, tmp_path):
    first = service.ingest_file(_write(tmp_path, "a.xml", BUILD_XML),
                                provider="fixture")
    other = BUILD_XML.replace(b'level="92"', b'level="93"')
    second = service.ingest_file(_write(tmp_path, "b.xml", other),
                                 provider="fixture")

    assert first.source_document_id != second.source_document_id
    assert len(list(service.store.blobs.iter_hashes())) == 2


def test_document_identity_ignores_acquisition_time_only(service):
    identity = dict(provider="p", access_method=AccessMethod.LOCAL_FILE,
                    blob_hash="0" * 64, source_url=None, external_id=None)
    assert source_document_id(**identity) == source_document_id(**identity)
    for field, value in [("provider", "q"), ("blob_hash", "1" * 64),
                         ("source_url", "https://example.invalid/a"),
                         ("external_id", "x"),
                         ("access_method", AccessMethod.PUBLIC_PAGE)]:
        changed = dict(identity)
        changed[field] = value
        assert source_document_id(**changed) != source_document_id(**identity)


# ----------------------------------------------------------- refusals ===

def test_malformed_content_is_typed_and_stores_nothing(service, tmp_path):
    path = _write(tmp_path, "export.json", b'{"skills": [1, 2,}')

    outcome = service.ingest_file(path, provider="fixture")

    assert outcome.status is AcquisitionStatus.INVALID_RESPONSE
    assert outcome.document is None
    assert outcome.result.source_document_id is None
    assert outcome.result.retry_eligible is False
    assert list(service.store.blobs.iter_hashes()) == []
    assert service.store.source_history("fixture", None) == []


def test_oversized_local_file_is_refused_before_it_is_stored(tmp_path):
    from pob2opt.acquisition import Limits

    store = RunStore.open_corpus(tmp_path / "corpus")
    service = AcquisitionService(store, clock=ManualClock(),
                                 limits=Limits(max_bytes=1024))
    payload = b"<r>" + b"x" * 4096 + b"</r>"

    outcome = service.ingest_file(_write(tmp_path, "big.xml", payload),
                                  provider="fixture")

    assert outcome.status is AcquisitionStatus.INVALID_RESPONSE
    assert "past the 1024 byte limit" in outcome.result.diagnostic
    assert list(store.blobs.iter_hashes()) == []
    store.close()


def test_a_missing_file_is_not_found_not_an_empty_document(service, tmp_path):
    outcome = service.ingest_file(tmp_path / "absent.xml", provider="fixture")

    assert outcome.status is AcquisitionStatus.NOT_FOUND
    assert outcome.document is None
    assert list(service.store.blobs.iter_hashes()) == []


def test_unrecognised_input_is_unsupported_access(service, tmp_path):
    outcome = service.ingest_file(_write(tmp_path, "thing.bin", b"\x00\x01\x02"),
                                  provider="fixture")

    assert outcome.status is AcquisitionStatus.UNSUPPORTED_ACCESS
    assert outcome.document is None


# ------------------------------------------------- build code expansion ===

def test_a_build_code_that_expands_past_the_cap_is_refused(service):
    bomb = base64.urlsafe_b64encode(zlib.compress(b"\0" * (1 << 20)))

    with pytest.raises(OversizedContent):
        decode_build_code(bomb, max_expanded_bytes=1024)

    # And the cap is enforced, not merely accepted: a cap it fits under works.
    assert len(decode_build_code(
        base64.urlsafe_b64encode(zlib.compress(BUILD_XML)),
        max_expanded_bytes=1024)) == len(BUILD_XML)


def test_the_shipped_default_cap_is_the_interfaces_md_one():
    assert content.MAX_EXPANDED_BYTES == 20 * 1024 * 1024
    oversized = base64.urlsafe_b64encode(
        zlib.compress(b"\0" * (content.MAX_EXPANDED_BYTES + 4096)))

    with pytest.raises(OversizedContent):
        decode_build_code(oversized)


def test_an_oversized_build_code_never_reaches_a_blob(tmp_path):
    from pob2opt.acquisition import Limits

    store = RunStore.open_corpus(tmp_path / "corpus")
    service = AcquisitionService(store, clock=ManualClock(),
                                 limits=Limits(max_bytes=2048))
    bomb = base64.urlsafe_b64encode(zlib.compress(b"\0" * (1 << 20)))

    outcome = service.ingest_build_code(bomb, provider="fixture")

    assert outcome.status is AcquisitionStatus.INVALID_RESPONSE
    assert outcome.document is None
    assert list(store.blobs.iter_hashes()) == []
    store.close()


@pytest.mark.parametrize("payload", [
    b"not base64 at all !!!",
    base64.urlsafe_b64encode(b"this is not a deflate stream"),
    base64.urlsafe_b64encode(zlib.compress(BUILD_XML))[:12],
])
def test_malformed_build_codes_are_refused(payload):
    with pytest.raises(MalformedContent):
        decode_build_code(payload)


def test_a_truncated_deflate_stream_is_not_a_partial_build():
    compressed = zlib.compress(BUILD_XML)
    with pytest.raises(MalformedContent):
        decode_build_code(base64.urlsafe_b64encode(compressed[:-5]))


# --------------------------------------------------------- unsafe XML ===

@pytest.mark.parametrize("payload", [
    b'<?xml version="1.0"?><!DOCTYPE r [<!ENTITY a "b">]><r>&a;</r>',
    b'<?xml version="1.0"?><!DOCTYPE r SYSTEM "http://evil.invalid/x.dtd"><r/>',
])
def test_unsafe_xml_constructs_are_refused(service, tmp_path, payload):
    with pytest.raises(MalformedContent):
        content.check_xml(payload)

    outcome = service.ingest_file(_write(tmp_path, "evil.xml", payload),
                                  provider="fixture", kind="xml")
    assert outcome.status is AcquisitionStatus.INVALID_RESPONSE
    assert list(service.store.blobs.iter_hashes()) == []


def test_a_build_code_hiding_unsafe_xml_is_refused():
    payload = base64.urlsafe_b64encode(zlib.compress(
        b'<!DOCTYPE r [<!ENTITY a "b">]><r>&a;</r>'))
    with pytest.raises(MalformedContent):
        decode_build_code(payload)


def test_deeply_nested_xml_is_refused():
    depth = content.MAX_XML_DEPTH + 10
    payload = b"<r>" * depth + b"</r>" * depth
    with pytest.raises(MalformedContent):
        content.check_xml(payload)


def test_html_is_stored_verbatim_and_never_interpreted(service, tmp_path):
    outcome = service.ingest_file(_write(tmp_path, "guide.html", GUIDE_HTML),
                                  provider="fixture")

    stored = service.store.read_payload(outcome.document.blob_hash)
    assert stored == GUIDE_HTML
    assert b"<script>alert(1)</script>" in stored  # kept, not run, not stripped


# ------------------------------------------------- independence and hygiene ===

def test_acquisition_imports_no_engine():
    """Acquisition runs with no PoB runtime, so it must not pull the engine in.

    Asked in a fresh interpreter: this suite has already imported the engine
    boundary by the time it gets here, so an in-process check would prove
    nothing. The child makes no network call; it imports and reports.
    """
    import subprocess

    probe = (
        "import sys, pob2opt.acquisition;"
        "bad=[n for n in sys.modules if n.startswith('pob2opt.evaluation')"
        " or n.startswith('pob2opt.engine') or n=='pob2opt.phases'];"
        "print('LOADED' if bad else 'CLEAN')")
    import os

    import pob2opt

    package_root = str(Path(pob2opt.__file__).resolve().parents[1])
    environment = dict(os.environ)
    environment["PYTHONPATH"] = os.pathsep.join(
        [package_root, environment.get("PYTHONPATH", "")]).rstrip(os.pathsep)
    done = subprocess.run([sys.executable, "-c", probe], capture_output=True,
                          text=True, timeout=120, env=environment)

    assert done.returncode == 0, done.stderr
    assert done.stdout.strip() == "CLEAN", done.stdout


def test_the_package_executes_no_downloaded_content():
    """Nothing acquired is run. Checked on the syntax tree, not on prose."""
    import ast

    package = Path(__import__("pob2opt.acquisition",
                              fromlist=["__file__"]).__file__).parent
    banned_calls = {"eval", "exec", "compile", "__import__"}
    banned_modules = {"subprocess", "pickle", "marshal", "shutil", "ctypes"}
    for module in sorted(package.glob("*.py")):
        tree = ast.parse(module.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                assert node.func.id not in banned_calls, (
                    "%s calls %s" % (module.name, node.func.id))
            if isinstance(node, ast.Attribute):
                assert node.attr not in ("system", "popen", "spawnv"), (
                    "%s calls os.%s" % (module.name, node.attr))
            if isinstance(node, ast.Import):
                for alias in node.names:
                    assert alias.name.split(".")[0] not in banned_modules, (
                        "%s imports %s" % (module.name, alias.name))
            if isinstance(node, ast.ImportFrom) and node.module:
                assert node.module.split(".")[0] not in banned_modules, (
                    "%s imports from %s" % (module.name, node.module))


# ---------------------------------------------------------------- the CLI ===

def test_ingest_command_stores_a_file_and_reports_json(tmp_path, capsys):
    path = _write(tmp_path, "build.xml", BUILD_XML)
    corpus = tmp_path / "corpus"

    code = ingest_main(["--provider", "fixture", "--input", str(path),
                        "--corpus", str(corpus)])

    assert code == 0
    report = json.loads(capsys.readouterr().out)
    assert report["status"] == "ok"
    assert report["blob_hash"] == document_hash(BUILD_XML)
    assert report["created"] is True

    again = ingest_main(["--provider", "fixture", "--input", str(path),
                         "--corpus", str(corpus)])
    assert again == 0
    assert json.loads(capsys.readouterr().out)["created"] is False


def test_ingest_command_refuses_a_url_with_no_approved_host(tmp_path, capsys):
    code = ingest_main(["--provider", "fixture", "--corpus", str(tmp_path),
                        "--input", "https://example.invalid/build"])

    assert code == 3
    assert "no host is approved" in capsys.readouterr().err


def test_ingest_command_exit_code_for_malformed_input(tmp_path, capsys):
    path = _write(tmp_path, "export.json", b"{oops")

    code = ingest_main(["--provider", "fixture", "--input", str(path),
                        "--corpus", str(tmp_path / "corpus")])

    assert code == 4
    assert json.loads(capsys.readouterr().out)["source_document_id"] is None


def test_unknown_kind_is_rejected_by_the_parser(tmp_path):
    with pytest.raises(SystemExit):
        ingest_main(["--provider", "p", "--input", "x", "--corpus",
                     str(tmp_path), "--kind", "sqlite"])


def test_detect_kind_refuses_to_guess(service):
    with pytest.raises(UnsupportedContent):
        detect_kind(b"\x7fELF\x02\x01")


# ------------------------------------------------------------- evidence ===

def test_the_committed_evidence_states_what_the_code_does():
    """The committed artifact is checked, not trusted.

    `python scripts/p03_t02_evidence.py` rewrites it. These are the claims a
    reviewer reads first, so a stale file fails here instead of in review.
    """
    path = (Path(__file__).resolve().parents[2] / "docs" / "evidence" / "P03"
            / "acquisition.json")
    report = json.loads(path.read_text(encoding="utf-8"))

    assert report["evidence_kind"] == "synthetic"
    assert set(report["input_kinds"]) == {"xml", "html", "json", "build_code"}
    assert report["idempotency"]["blobs"] == 1
    assert report["idempotency"]["source_documents"] == 1
    assert len(report["idempotency"]["document_ids"]) == 1

    cases = {row["case"]: row for row in report["failures"]}
    assert {"http_403", "http_404", "http_429", "oversized_payload", "timeout",
            "malformed_content"} <= set(cases)
    for case in cases.values():
        assert case["status"] != "ok"
        assert case["source_document_id"] is None
        assert case["documents_written"] == 0
        assert case["blobs_written"] == 0

    secrets = report["credentials"]
    assert secrets["status"] == "ok"
    assert not any(value for key, value in secrets.items()
                   if key.startswith("secret_in_"))
    assert report["host_policy"]["default_allowed_hosts"] == []
