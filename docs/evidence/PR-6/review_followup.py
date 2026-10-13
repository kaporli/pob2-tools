"""Offline follow-up probes. Usage: python THIS.py PR6_CHECKOUT.

No live service, game engine, or credentials are used.
"""
import json
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from xml.etree import ElementTree

root = Path(sys.argv[1]).resolve()
sys.path.insert(0, str(root / "pob2-optimizer"))
from pob2opt.acquisition import AcquisitionService, AcquisitionState, HostPolicy, HostRule, HttpAcquirer, Response
from pob2opt.storage import RunStore

class Clock:
    seconds = 0.0
    def monotonic(self): return self.seconds
    def sleep(self, seconds): self.seconds += seconds
    def utcnow(self):
        return (datetime(2026, 10, 12, tzinfo=timezone.utc) + timedelta(seconds=self.seconds)).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"

class Transport:
    def __init__(self, send): self.callback, self.sent = send, []
    def send(self, request):
        self.sent.append(request)
        return self.callback(request)

def service(store, state, transport, clock):
    client = HttpAcquirer(transport=transport, policy=HostPolicy.of([HostRule("fixture.invalid")]), clock=clock)
    return AcquisitionService(store, acquirer=client, state=state, clock=clock)

def ok(body):
    return Response(200, {"Content-Type": "application/json", "ETag": '"v1"'}, chunks=[body])

observed = {}
with tempfile.TemporaryDirectory() as tmp:
    folder = Path(tmp)
    clock = Clock()
    with RunStore.open_corpus(folder) as store:
        first_transport = Transport(lambda r: Response(429, {"Retry-After": "120"}))
        first = service(store, AcquisitionState.in_corpus(folder), first_transport, clock)
        first.ingest_url("https://fixture.invalid/one", provider="fixture")
        saved = AcquisitionState.in_corpus(folder).cooldowns()
        second_transport = Transport(lambda r: ok(b"{}"))
        resumed = service(store, AcquisitionState.in_corpus(folder), second_transport, clock)
        result = resumed.ingest_url("https://fixture.invalid/two", provider="fixture")
        observed["restart"] = {"saved_deadline": saved, "status": result.status.value,
            "requests_sent": len(second_transport.sent), "seconds_elapsed": clock.seconds,
            "deadline_after_request": AcquisitionState.in_corpus(folder).cooldowns()}

with tempfile.TemporaryDirectory() as tmp:
    with RunStore.open_corpus(Path(tmp)) as store:
        target = {"variant": "first"}
        def fetch(request):
            if request.url.endswith("/start"):
                return Response(302, {"Location": "https://fixture.invalid/export?variant=" + target["variant"]})
            if request.headers.get("If-None-Match") == '"v1"':
                return Response(304)
            return ok(json.dumps(target).encode())
        transport = Transport(fetch)
        ingest = service(store, AcquisitionState.in_memory(), transport, Clock())
        first = ingest.ingest_url("https://fixture.invalid/start", provider="fixture")
        target["variant"] = "second"
        second = ingest.ingest_url("https://fixture.invalid/start", provider="fixture")
        observed["changed_redirect_query"] = {"status": second.status.value,
            "same_document": first.source_document_id == second.source_document_id,
            "returned_payload": store.read_payload(second.blob_hash).decode(),
            "requests": [{"url": r.url, "validator": r.headers.get("If-None-Match")} for r in transport.sent]}

state = AcquisitionState.in_memory()
observed["repeated_query_order_keys_equal"] = state.key_for("fixture", "https://fixture.invalid/export?id=1&id=2") == state.key_for("fixture", "https://fixture.invalid/export?id=2&id=1")

with tempfile.TemporaryDirectory() as tmp:
    with RunStore.open_corpus(Path(tmp)) as store:
        ingest = AcquisitionService(store)
        xml = '<?xml version="1.0" encoding="ISO-8859-1"?><PathOfBuilding><Notes>caf\u00e9</Notes></PathOfBuilding>'.encode("iso-8859-1")
        ElementTree.fromstring(xml)  # independent baseline: this document is well formed
        result = ingest.ingest_bytes(xml, kind="xml", provider="fixture")
        observed["declared_latin1"] = {"status": result.status.value, "diagnostic": result.result.diagnostic}

print(json.dumps(observed, indent=2, sort_keys=True))
