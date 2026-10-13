"""Offline reviewer probes; pass the PR6 checkout path as the first argument.

Outputs observations, not a passing regression suite. All tokens are invented.
No sockets, auth clients, PoB, or actual credentials are used.
"""
import base64
import json
import sys
import tempfile
import zlib
from datetime import datetime, timedelta, timezone
from pathlib import Path

root = Path(sys.argv[1]).resolve()
sys.path.insert(0, str(root / "pob2-optimizer"))
from pob2opt.acquisition import (AcquisitionService, HostPolicy, HostRule,
    HttpAcquirer, Limits, Response)
from pob2opt.acquisition.transport import RequestsTransport
from pob2opt.storage import RunStore
import requests


class Clock:
    seconds = 0.0
    def monotonic(self): return self.seconds
    def sleep(self, seconds): self.seconds += seconds
    def utcnow(self):
        dt = datetime(2026, 10, 11, tzinfo=timezone.utc) + timedelta(seconds=self.seconds)
        return dt.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


class Transport:
    def __init__(self, *responses):
        self.responses = iter(responses)
        self.sent = []
    def send(self, request):
        self.sent.append(request)
        return next(self.responses)


def policy(*hosts):
    return HostPolicy.of(HostRule(h) for h in hosts)


a = "https://a.example.invalid/start"
b = "https://b.example.invalid/raw"
observed = {}
transport = Transport(Response(302, {"Location": b}), Response(200, chunks=[b"{} "]))
client = HttpAcquirer(transport=transport, policy=policy("a.example.invalid", "b.example.invalid"))
client.fetch("test", a, headers={"Authorization": "Bearer invented-review-token", "Cookie": "session=invented"})
observed["cross_origin_headers"] = dict(transport.sent[1].headers)


class RawResponse:
    status_code = 403
    headers = {}
    closed = False
    def iter_content(self, chunk_size):
        yield b"discard this response"
    def close(self): self.closed = True


class Session:
    def __init__(self, response): self.response = response
    def request(self, *args, **kwargs): return self.response


raw = RawResponse()
client = HttpAcquirer(transport=RequestsTransport(Session(raw)), policy=policy("a.example.invalid"))
client.fetch("test", a)
observed["discarded_403_response_closed"] = raw.closed

with tempfile.TemporaryDirectory() as tmp:
    with RunStore.open_corpus(Path(tmp)) as store:
        service = AcquisitionService(store)
        xml = '<?xml version="1.0" encoding="UTF-16"?><!DOCTYPE PathOfBuilding [<!ENTITY x "ENTITY_EXPANDED">]><PathOfBuilding>&x;</PathOfBuilding>'.encode("utf-16")
        result = service.ingest_bytes(xml, kind="xml", provider="test")
        observed["utf16_doctype_status"] = result.status.value
        code = base64.urlsafe_b64encode(zlib.compress(xml))
        observed["utf16_doctype_build_code_status"] = service.ingest_build_code(code, provider="test").status.value
        try:
            result = service.ingest_bytes(b"[" * 2000 + b"0" + b"]" * 2000, kind="json", provider="test")
            observed["deep_json"] = result.status.value
        except Exception as error:
            observed["deep_json"] = type(error).__name__

clock = Clock()
transport = Transport(Response(429, {"Retry-After": "120"}), Response(200, chunks=[b"{}"]))
client = HttpAcquirer(transport=transport, policy=policy("a.example.invalid"), clock=clock)
first = client.fetch("test", a)
second = client.fetch("test", a + "?page=2")
observed["provider_retry_delay"] = {"not_before": first.deferral.not_before,
    "next_request_at": clock.utcnow(), "second_status": second.status.value}

with tempfile.TemporaryDirectory() as tmp:
    with RunStore.open_corpus(Path(tmp)) as store:
        transport = Transport(Response(302, {"Location": b}),
            Response(200, {"Content-Type": "application/json", "ETag": '"v1"'}, chunks=[b"{}"]),
            Response(302, {"Location": b}), Response(304))
        client = HttpAcquirer(transport=transport, policy=policy("a.example.invalid", "b.example.invalid"))
        service = AcquisitionService(store, acquirer=client)
        first = service.ingest_url(a, provider="test")
        second = service.ingest_url(a, provider="test")
        observed["redirect_304"] = {"first_status": first.status.value, "second_status": second.status.value,
            "diagnostic": second.result.diagnostic}

restricted = HostPolicy.of([HostRule("a.example.invalid", path_prefixes=("/approved/",))])
url = restricted.check("https://a.example.invalid/approved/../blocked")
prepared_url = requests.Request("GET", url).prepare().url
observed["approved_path_after_transport_preparation"] = prepared_url

with tempfile.TemporaryDirectory() as tmp:
    with RunStore.open_corpus(Path(tmp)) as store:
        transport = Transport(Response(200, {"Content-Type": "application/json", "ETag": '"v1"'}, chunks=[b'{"variant":1}']), Response(304))
        client = HttpAcquirer(transport=transport, policy=policy("a.example.invalid"))
        service = AcquisitionService(store, acquirer=client)
        first = service.ingest_url(a + "?variant=first", provider="test")
        second = service.ingest_url(a + "?variant=second", provider="test")
        observed["redacted_url_cache_collision"] = {
            "second_request_sent_first_etag": transport.sent[1].headers.get("If-None-Match"),
            "second_status": second.status.value,
            "returned_first_document": second.source_document_id == first.source_document_id,
        }
print(json.dumps(observed, indent=2, sort_keys=True))
