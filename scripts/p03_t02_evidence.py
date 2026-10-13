"""Record what P03-T02 acquisition actually does. Writes the evidence file.

Everything here is **synthetic**: invented payloads and a scripted transport.
No provider is contacted, no PoB runtime is used and no socket is opened. The
file this writes is a record of our own code's behaviour, not a measurement of
any provider.

    python scripts/p03_t02_evidence.py [--out docs/evidence/P03/acquisition.json]
"""

from __future__ import annotations

import argparse
import base64
import io
import json
import logging
import platform
import sys
import tempfile
import zlib
from datetime import datetime, timedelta, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "pob2-optimizer"))

from pob2opt.acquisition import (  # noqa: E402
    ACQUISITION_VERSION,
    AcquisitionService,
    AcquisitionState,
    HostPolicy,
    HostRule,
    HttpAcquirer,
    Limits,
    PolicyRefusal,
    ProviderLimits,
    ProviderScheduler,
    Response,
    TransportTimeout,
)
from pob2opt.domain.enums import AcquisitionStatus  # noqa: E402
from pob2opt.storage import RunStore  # noqa: E402

HOST = "builds.example.invalid"
URL = "https://%s/build/42" % HOST
SECRET = "s3cr3t-token-value"

BUILD_XML = (b'<?xml version="1.0" encoding="UTF-8"?>\n<PathOfBuilding>'
             b'<Build level="92" className="Ranger"/><Skills/><Tree/><Items/>'
             b'</PathOfBuilding>')
GUIDE_HTML = b'<!doctype html><html><body><h1>Lightning Arrow</h1></body></html>'
EXPORT_JSON = b'{"id": "42", "class": "Ranger"}'
BUILD_CODE = base64.urlsafe_b64encode(zlib.compress(BUILD_XML))


class ManualClock:
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


class CountingChunks:
    def __init__(self, chunk: bytes, count: int) -> None:
        self.chunk, self.count, self.served = chunk, count, 0

    def __iter__(self):
        for _ in range(self.count):
            self.served += 1
            yield self.chunk

    def close(self) -> None:
        pass


class StubTransport:
    def __init__(self, *script) -> None:
        self.script = list(script)
        self.requests = []

    def send(self, request):
        self.requests.append(request)
        item = self.script[min(len(self.requests) - 1, len(self.script) - 1)]
        if isinstance(item, BaseException):
            raise item
        return item


def _service(root: Path, transport=None, clock=None, limits=None,
             provider_limits=None, host_policy=None) -> AcquisitionService:
    clock = clock or ManualClock()
    store = RunStore.open_corpus(root)
    acquirer = None
    if transport is not None:
        acquirer = HttpAcquirer(
            transport=transport,
            policy=host_policy or HostPolicy.of([HostRule(host=HOST)]),
            limits=limits or Limits(), clock=clock,
            scheduler=ProviderScheduler(clock),
            provider_limits=provider_limits)
    return AcquisitionService(store, acquirer=acquirer, clock=clock,
                              state=AcquisitionState.in_corpus(root),
                              limits=limits or Limits())


def _ok(body: bytes, **headers) -> Response:
    merged = {"Content-Type": "application/json"}
    merged.update(headers)
    return Response(200, merged, chunks=[body], url=URL)


def _status(code: int, **headers) -> Response:
    return Response(code, headers, chunks=[b"error page"], url=URL)


def input_kinds(workspace: Path) -> dict:
    service = _service(workspace / "kinds")
    out = {}
    cases = [("xml", "build.xml", BUILD_XML), ("html", "guide.html", GUIDE_HTML),
             ("json", "export.json", EXPORT_JSON)]
    for kind, name, payload in cases:
        path = workspace / name
        path.write_bytes(payload)
        outcome = service.ingest_file(path, provider="synthetic")
        out[kind] = _document_row(service, outcome)
    outcome = service.ingest_build_code(BUILD_CODE, provider="synthetic")
    out["build_code"] = _document_row(service, outcome)
    out["build_code"]["expanded_bytes"] = len(BUILD_XML)
    service.store.close()
    return out


def _document_row(service, outcome) -> dict:
    document = outcome.document
    stored = service.store.read_payload(document.blob_hash)
    return {
        "status": outcome.status.value,
        "record_id": document.record_id,
        "media_type": document.media_type,
        "blob_hash": document.blob_hash,
        "byte_count": document.byte_count,
        "created": outcome.created,
        "stored_bytes_match": len(stored) == document.byte_count,
        "source_url": document.source_url,
        "popularity": list(document.popularity),
        "declared_patch": document.declared_patch,
        "redistribution": document.redistribution.value,
    }


def idempotency(workspace: Path) -> dict:
    service = _service(workspace / "idem")
    path = workspace / "idem-build.xml"
    path.write_bytes(BUILD_XML)
    copy = workspace / "idem-copy.xml"
    copy.write_bytes(BUILD_XML)
    first = service.ingest_file(path, provider="synthetic")
    second = service.ingest_file(path, provider="synthetic")
    third = service.ingest_file(copy, provider="synthetic")
    attempts = service.store.conn.execute(
        "SELECT COUNT(*) FROM source_record WHERE kind = 'acquisition_result'"
    ).fetchone()[0]
    result = {
        "document_ids": sorted({first.source_document_id,
                                second.source_document_id,
                                third.source_document_id}),
        "created_flags": [first.created, second.created, third.created],
        "blobs": len(list(service.store.blobs.iter_hashes())),
        "source_documents": len(service.store.source_history("synthetic", None)),
        "acquisition_results": attempts,
    }
    service.store.close()
    return result


def failures(workspace: Path) -> list[dict]:
    rows = []
    for name, transport, limits in [
        ("http_403", StubTransport(_status(403)), None),
        ("http_404", StubTransport(_status(404)), None),
        ("http_429", StubTransport(_status(429, **{"Retry-After": "5"})), None),
        ("oversized_payload",
         StubTransport(Response(200, {"Content-Type": "application/json"},
                                chunks=CountingChunks(b"x" * 1024, 4096))),
         Limits(max_bytes=8 * 1024)),
        ("timeout", StubTransport(TransportTimeout("read timed out")), None),
        ("malformed_content", StubTransport(_ok(b'{"skills": [1,')), None),
    ]:
        clock = ManualClock()
        service = _service(workspace / name, transport, clock=clock,
                           limits=limits)
        outcome = service.ingest_url(URL, provider="synthetic")
        rows.append({
            "case": name,
            "status": outcome.status.value,
            "http_status": outcome.result.http_status,
            "retry_eligible": outcome.result.retry_eligible,
            "attempts": len(transport.requests),
            "source_document_id": outcome.result.source_document_id,
            "documents_written": len(
                service.store.source_history("synthetic", None)),
            "blobs_written": len(list(service.store.blobs.iter_hashes())),
            "slept_s": list(clock.slept),
            "diagnostic": outcome.result.diagnostic,
        })
        service.store.close()

    # Local refusals, same rule: a refused payload is never a stored one.
    service = _service(workspace / "local-refusals")
    bad = workspace / "bad.json"
    bad.write_bytes(b'{"skills": [1,')
    outcome = service.ingest_file(bad, provider="synthetic")
    rows.append({
        "case": "local_malformed_json",
        "status": outcome.status.value,
        "http_status": None,
        "retry_eligible": outcome.result.retry_eligible,
        "attempts": 1,
        "source_document_id": outcome.result.source_document_id,
        "documents_written": len(service.store.source_history("synthetic", None)),
        "blobs_written": len(list(service.store.blobs.iter_hashes())),
        "slept_s": [],
        "diagnostic": outcome.result.diagnostic,
    })
    service.store.close()
    return rows


def credentials(workspace: Path) -> dict:
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    logger = logging.getLogger("pob2opt.acquisition")
    logger.addHandler(handler)
    logger.setLevel(logging.DEBUG)
    try:
        root = workspace / "secrets"
        service = _service(root, StubTransport(_ok(EXPORT_JSON)))
        outcome = service.ingest_url(
            "%s?access_token=%s&page=3" % (URL, SECRET), provider="synthetic",
            headers={"Authorization": "Bearer %s" % SECRET,
                     "Cookie": "session=%s" % SECRET})
        document = outcome.document
        row = service.store.conn.execute(
            "SELECT json FROM source_record WHERE record_id = ?",
            (document.record_id,)).fetchone()["json"]
        attempt = service.store.conn.execute(
            "SELECT json FROM source_record WHERE record_id = ?",
            (outcome.result.record_id,)).fetchone()["json"]
        state_text = (root / "acquisition-state.json").read_text(encoding="utf-8")
        blob = service.store.read_payload(document.blob_hash).decode("utf-8")
        service.store.close()
        return {
            "status": outcome.status.value,
            "stored_source_url": document.source_url,
            "secret_in_stored_url": SECRET in (document.source_url or ""),
            "secret_in_source_document_row": SECRET in row,
            "secret_in_acquisition_result_row": SECRET in attempt,
            "secret_in_blob": SECRET in blob,
            "secret_in_log": SECRET in stream.getvalue(),
            "secret_in_state_file": SECRET in state_text,
            "log_lines": stream.getvalue().strip().splitlines(),
        }
    finally:
        logger.removeHandler(handler)


def limits_enforced(workspace: Path) -> dict:
    transport = StubTransport(_ok(EXPORT_JSON))
    service = _service(workspace / "limits", transport)
    service.ingest_url(URL, provider="synthetic")
    sent = transport.requests[0]
    service.store.close()

    body = CountingChunks(b"x" * 1024, 4096)
    sized = StubTransport(Response(200, {"Content-Type": "application/json"},
                                   chunks=body))
    service = _service(workspace / "limits-size", sized,
                       limits=Limits(max_bytes=8 * 1024))
    oversized = service.ingest_url(URL, provider="synthetic")
    service.store.close()

    loose = ProviderLimits(read_timeout_s=600.0, max_bytes=1 << 30,
                           max_attempts=99, min_interval_s=2.5)
    tight = ProviderLimits(read_timeout_s=5.0, max_attempts=2)
    effective_loose = Limits().tightened_by(loose)
    effective_tight = Limits().tightened_by(tight)
    return {
        "defaults_sent_to_transport": {
            "connect_timeout_s": sent.connect_timeout_s,
            "read_timeout_s": sent.read_timeout_s,
            "max_bytes": sent.max_bytes,
        },
        "size_limit": {
            "limit_bytes": 8 * 1024,
            "offered_bytes": 4096 * 1024,
            "chunks_pulled_before_refusal": body.served,
            "status": oversized.status.value,
        },
        "provider_cannot_loosen": {
            "requested": {"read_timeout_s": 600.0, "max_bytes": 1 << 30,
                          "max_attempts": 99, "min_interval_s": 2.5},
            "effective": {"read_timeout_s": effective_loose.read_timeout_s,
                          "max_bytes": effective_loose.max_bytes,
                          "max_attempts": effective_loose.max_attempts,
                          "min_interval_s": effective_loose.min_interval_s},
        },
        "provider_can_tighten": {
            "requested": {"read_timeout_s": 5.0, "max_attempts": 2},
            "effective": {"read_timeout_s": effective_tight.read_timeout_s,
                          "max_attempts": effective_tight.max_attempts},
        },
    }


def scheduling(workspace: Path) -> dict:
    short_clock = ManualClock()
    short = StubTransport(_status(429, **{"Retry-After": "5"}))
    service = _service(workspace / "sched-short", short, clock=short_clock)
    short_outcome = service.ingest_url(URL, provider="synthetic")
    service.store.close()

    long_clock = ManualClock()
    long = StubTransport(_status(429, **{"Retry-After": "120"}))
    service = _service(workspace / "sched-long", long, clock=long_clock)
    long_outcome = service.ingest_url(URL, provider="synthetic")
    service.store.close()

    pace_clock = ManualClock()
    paced = StubTransport(_ok(EXPORT_JSON), _ok(b'{"id": "43"}'))
    service = _service(workspace / "sched-pace", paced, clock=pace_clock,
                       provider_limits={"synthetic": ProviderLimits(
                           min_interval_s=2.5)})
    service.ingest_url(URL, provider="synthetic")
    service.ingest_url(URL + "b", provider="synthetic")
    service.store.close()
    return {
        "short_delay_is_waited_in_full": {
            "retry_after_s": 5.0, "slept_s": short_clock.slept,
            "attempts": len(short.requests),
            "status": short_outcome.status.value},
        "long_delay_is_scheduled_not_truncated": {
            "retry_after_s": 120.0, "slept_s": long_clock.slept,
            "attempts": len(long.requests),
            "status": long_outcome.status.value,
            "not_before": (long_outcome.deferral.not_before
                           if long_outcome.deferral else None),
            "retry_eligible": long_outcome.result.retry_eligible},
        "provider_pacing": {"min_interval_s": 2.5,
                            "slept_s": pace_clock.slept,
                            "requests": len(paced.requests)},
    }


def conditional(workspace: Path) -> dict:
    transport = StubTransport(_ok(EXPORT_JSON, ETag='"v1"'),
                              Response(304, {"ETag": '"v1"'}, chunks=[]))
    root = workspace / "conditional"
    service = _service(root, transport)
    first = service.ingest_url(URL, provider="synthetic")
    second = service.ingest_url(URL, provider="synthetic")
    report = {
        "second_request_headers": sorted(transport.requests[1].headers),
        "if_none_match_sent": transport.requests[1].headers.get("If-None-Match"),
        "second_status": second.status.value,
        "second_unchanged": second.unchanged,
        "same_document": first.source_document_id == second.source_document_id,
        "blobs": len(list(service.store.blobs.iter_hashes())),
        "source_documents": len(service.store.source_history("synthetic", None)),
    }
    service.store.close()
    return report


def host_policy() -> dict:
    refusals = {}
    allowed = HostPolicy.of([HostRule(host=HOST)])
    for label, url in [
        ("default_deny", URL),
        ("plain_http", "http://%s/x" % HOST),
        ("other_host", "https://elsewhere.invalid/x"),
        ("credentials_in_url", "https://user:pw@%s/x" % HOST),
        ("ip_literal", "https://127.0.0.1/x"),
    ]:
        policy = HostPolicy.deny_all() if label == "default_deny" else allowed
        try:
            policy.check(url)
        except PolicyRefusal as refusal:
            refusals[label] = refusal.reason
        else:
            refusals[label] = "ALLOWED"
    return {
        "default_allowed_hosts": list(HostPolicy.deny_all().allowed_hosts),
        "refusals": refusals,
    }


def build(workspace: Path) -> dict:
    return {
        "task": "P03-T02",
        "specification_version": "1.0",
        "evidence_kind": "synthetic",
        "caveat": ("Invented payloads and a scripted transport. No provider "
                   "was contacted, no socket was opened and no PoB runtime "
                   "was used. This records our code's behaviour, nothing "
                   "about any provider."),
        "acquisition_version": ACQUISITION_VERSION,
        "python": platform.python_version(),
        "platform": platform.platform(),
        "input_kinds": input_kinds(workspace),
        "idempotency": idempotency(workspace),
        "failures": failures(workspace),
        "credentials": credentials(workspace),
        "limits": limits_enforced(workspace),
        "scheduling": scheduling(workspace),
        "conditional_requests": conditional(workspace),
        "host_policy": host_policy(),
        "statuses_in_use": [status.value for status in AcquisitionStatus],
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default=str(
        REPO_ROOT / "docs" / "evidence" / "P03" / "acquisition.json"))
    args = parser.parse_args(argv)
    with tempfile.TemporaryDirectory() as temporary:
        report = build(Path(temporary))
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n",
                   encoding="utf-8")
    print("wrote %s" % out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
