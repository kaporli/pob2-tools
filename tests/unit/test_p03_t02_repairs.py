"""Regressions for the eight P03-T02 review findings (docs/reviews/P03-T02.md).

Offline. The transport is injected or faked, and the one test that touches
``RequestsTransport`` hands it a session object that opens nothing. Each test
is written so that reverting its repair fails it: the reproduction, not the
configured value, is the assertion.

The findings, in the review's order:

* R1 credentials are not forwarded across origins.
* R2 unsafe XML is refused whatever the document is encoded in.
* R3 cache identity is the request, not its redacted display form.
* R4 a response closes without the body being iterated.
* R5 a provider cooldown outlives the request that earned it.
* R6 a 304 after a redirect resolves against the URL that was asked for.
* R7 the approved path is the path that is sent.
* R8 JSON depth is a typed refusal on every supported interpreter.
"""

from __future__ import annotations

import base64
import json
import zlib
from datetime import datetime, timedelta, timezone

import pytest

from pob2opt.acquisition import (
    AcquisitionService,
    AcquisitionState,
    HostPolicy,
    HostRule,
    HttpAcquirer,
    Limits,
    MalformedContent,
    PolicyRefusal,
    ProviderLimits,
    ProviderScheduler,
    Request,
    RequestsTransport,
    Response,
    Validators,
    inspect as inspect_content,
)
from pob2opt.acquisition.content import MAX_JSON_DEPTH
from pob2opt.domain.enums import AcquisitionStatus
from pob2opt.storage import RunStore

HOST_A = "a.example.invalid"
HOST_B = "b.example.invalid"
URL_A = "https://%s/build/42" % HOST_A
URL_B = "https://%s/build/42" % HOST_B
BUILD_JSON = json.dumps({"id": "42", "class": "Ranger"}).encode("utf-8")
SECRET = "s3cr3t-token-value"


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


class ScriptedTransport:
    """Answers by URL, and keeps every request it was handed."""

    def __init__(self, routes) -> None:
        self.routes = dict(routes)
        self.requests: list[Request] = []

    def send(self, request: Request) -> Response:
        self.requests.append(request)
        item = self.routes[request.url]
        if callable(item):
            item = item(request)
        if isinstance(item, BaseException):
            raise item
        return item


def ok(body: bytes = BUILD_JSON, **headers) -> Response:
    merged = {"Content-Type": "application/json"}
    merged.update(headers)
    return Response(status=200, headers=merged, chunks=[body])


def redirect_to(location: str, code: int = 302) -> Response:
    return Response(status=code, headers={"Location": location},
                    chunks=[b"moved"])


def policy(*hosts) -> HostPolicy:
    return HostPolicy.of(HostRule(host=host) for host in hosts)


@pytest.fixture()
def corpus(tmp_path):
    store = RunStore.open_corpus(tmp_path / "corpus")
    yield store
    store.close()


def service_for(transport, corpus, tmp_path, *, hosts=(HOST_A, HOST_B),
                clock=None, limits=None, provider_limits=None):
    clock = clock or ManualClock()
    acquirer = HttpAcquirer(transport=transport, policy=policy(*hosts),
                            limits=limits or Limits(), clock=clock,
                            scheduler=ProviderScheduler(clock),
                            provider_limits=provider_limits)
    return AcquisitionService(corpus, acquirer=acquirer, clock=clock,
                              state=AcquisitionState.in_corpus(tmp_path))


# ------------------------------------------------ R1 cross-origin creds ===

def test_a_cross_origin_redirect_does_not_forward_the_caller_credentials():
    transport = ScriptedTransport({URL_A: redirect_to(URL_B), URL_B: ok()})
    clock = ManualClock()
    acquirer = HttpAcquirer(transport=transport, policy=policy(HOST_A, HOST_B),
                            clock=clock, scheduler=ProviderScheduler(clock))

    outcome = acquirer.fetch("fixture", URL_A, headers={
        "Authorization": "Bearer %s" % SECRET,
        "Cookie": "session=%s" % SECRET,
        "Accept": "application/json",
    })

    assert outcome.status is AcquisitionStatus.OK
    first, second = transport.requests
    assert first.headers["Authorization"].endswith(SECRET)
    # Approving B to serve build data does not authorize it to receive A's
    # secrets. Both named headers are gone; the safe one survives.
    assert "Authorization" not in second.headers
    assert "Cookie" not in second.headers
    assert second.headers["Accept"] == "application/json"
    assert outcome.credentials_dropped is True


def test_a_same_origin_redirect_still_carries_them():
    moved = "https://%s/build/42/final" % HOST_A
    transport = ScriptedTransport({URL_A: redirect_to(moved), moved: ok()})
    clock = ManualClock()
    acquirer = HttpAcquirer(transport=transport, policy=policy(HOST_A),
                            clock=clock, scheduler=ProviderScheduler(clock))

    outcome = acquirer.fetch("fixture", URL_A,
                             headers={"Authorization": "Bearer %s" % SECRET})

    assert outcome.status is AcquisitionStatus.OK
    assert transport.requests[1].headers["Authorization"].endswith(SECRET)
    assert outcome.credentials_dropped is False


def test_a_validator_does_not_follow_a_cross_origin_redirect():
    """An ETag names a representation on the server that issued it."""
    transport = ScriptedTransport({URL_A: redirect_to(URL_B), URL_B: ok()})
    clock = ManualClock()
    acquirer = HttpAcquirer(transport=transport, policy=policy(HOST_A, HOST_B),
                            clock=clock, scheduler=ProviderScheduler(clock))

    acquirer.fetch("fixture", URL_A, validators=Validators(etag='"v1"'))

    assert transport.requests[0].headers["If-None-Match"] == '"v1"'
    assert "If-None-Match" not in transport.requests[1].headers


# ---------------------------------------------------- R2 unsafe XML ===

UNSAFE_XML = ('<?xml version="1.0" encoding="%s"?>'
              '<!DOCTYPE build [<!ENTITY x SYSTEM "file:///etc/passwd">]>'
              '<PathOfBuilding><Build/></PathOfBuilding>')
SAFE_XML = ('<?xml version="1.0" encoding="%s"?>'
            '<PathOfBuilding><Build level="1"/></PathOfBuilding>')


@pytest.mark.parametrize("declared,encoding", [
    ("utf-8", "utf-8"),
    ("utf-16", "utf-16"),
    ("utf-16", "utf-16-le"),
])
def test_unsafe_xml_is_refused_whatever_it_is_encoded_in(declared, encoding):
    payload = (UNSAFE_XML % declared).encode(encoding)
    with pytest.raises(MalformedContent) as refused:
        inspect_content(payload, "xml")
    assert refused.value.reason == "unsafe_xml"


@pytest.mark.parametrize("declared,encoding", [
    ("utf-8", "utf-8"), ("utf-16", "utf-16")])
def test_a_compressed_unsafe_document_is_refused_too(declared, encoding):
    code = base64.urlsafe_b64encode(
        zlib.compress((UNSAFE_XML % declared).encode(encoding)))
    with pytest.raises(MalformedContent) as refused:
        inspect_content(code, "build_code")
    assert refused.value.reason == "unsafe_xml"


def test_an_unsafe_document_creates_no_record_and_no_blob(corpus, tmp_path):
    transport = ScriptedTransport({
        URL_A: ok((UNSAFE_XML % "utf-16").encode("utf-16"),
                  **{"Content-Type": "application/xml"})})
    service = service_for(transport, corpus, tmp_path)

    outcome = service.ingest_url(URL_A, provider="fixture")

    assert outcome.status is AcquisitionStatus.INVALID_RESPONSE
    assert outcome.document is None
    assert outcome.result.source_document_id is None
    assert corpus.source_history("fixture", None) == []


@pytest.mark.parametrize("declared,encoding", [
    ("utf-8", "utf-8"), ("utf-16", "utf-16")])
def test_ordinary_supported_xml_still_imports(corpus, tmp_path, declared,
                                              encoding):
    payload = (SAFE_XML % declared).encode(encoding)
    transport = ScriptedTransport({
        URL_A: ok(payload, **{"Content-Type": "application/xml"})})
    service = service_for(transport, corpus, tmp_path)

    outcome = service.ingest_url(URL_A, provider="fixture")

    assert outcome.status is AcquisitionStatus.OK
    assert outcome.document.byte_count == len(payload)


def test_an_unsupported_encoding_is_refused_rather_than_guessed_at():
    with pytest.raises(MalformedContent) as refused:
        inspect_content(
            (SAFE_XML % "utf-32").encode("utf-32"), "xml")
    assert refused.value.reason == "xml_encoding"


# ------------------------------------------------- R3 cache identity ===

def test_two_resources_differing_only_in_a_redacted_value_do_not_share_a_cache(
        corpus, tmp_path):
    """``variant`` is not an address parameter, so redaction replaces it. Two
    different builds used to arrive at one cache key, and the second request
    sent the first's ETag."""
    first = URL_A + "?variant=first"
    second = URL_A + "?variant=second"
    transport = ScriptedTransport({
        first: ok(b'{"id": "first"}', **{"ETag": '"v1"'}),
        second: ok(b'{"id": "second"}', **{"ETag": '"v2"'}),
    })
    service = service_for(transport, corpus, tmp_path)

    one = service.ingest_url(first, provider="fixture")
    two = service.ingest_url(second, provider="fixture")

    assert one.status is two.status is AcquisitionStatus.OK
    assert "If-None-Match" not in transport.requests[1].headers
    assert one.source_document_id != two.source_document_id
    assert corpus.read_payload(two.document.blob_hash) == b'{"id": "second"}'


def test_the_same_public_input_still_reuses_its_cache(corpus, tmp_path):
    transport = ScriptedTransport({
        URL_A: [ok(**{"ETag": '"v1"'}), Response(status=304, headers={})]})

    class Sequential(ScriptedTransport):
        def send(self, request: Request) -> Response:
            self.requests.append(request)
            queue = self.routes[request.url]
            return queue[min(len(self.requests) - 1, len(queue) - 1)]

    transport = Sequential({
        URL_A: [ok(**{"ETag": '"v1"'}), Response(status=304, headers={})]})
    service = service_for(transport, corpus, tmp_path)

    first = service.ingest_url(URL_A, provider="fixture")
    second = service.ingest_url(URL_A, provider="fixture")

    assert transport.requests[1].headers["If-None-Match"] == '"v1"'
    assert second.unchanged is True
    assert second.source_document_id == first.source_document_id


def test_distinct_authorization_contexts_do_not_share_a_cache_entry(tmp_path):
    state = AcquisitionState.in_corpus(tmp_path)
    state.remember("fixture", URL_A, etag='"v1"', last_modified=None,
                   source_document_id="doc-1",
                   acquired_at="2026-10-10T00:00:00.000Z",
                   credential_partition="account-one")

    assert state.document_for("fixture", URL_A,
                              credential_partition="account-one") == "doc-1"
    assert state.document_for("fixture", URL_A,
                              credential_partition="account-two") is None
    assert state.document_for("fixture", URL_A) is None
    assert not state.validators("fixture", URL_A)


# ------------------------------------------------ R4 response closure ===

class FakeRawResponse:
    """Stands in for a ``requests.Response``. Opens nothing."""

    def __init__(self, status: int, headers=None, body: bytes = b"") -> None:
        self.status_code = status
        self.headers = dict(headers or {})
        self.body = body
        self.closed = False
        self.iterated = False

    def iter_content(self, chunk_size: int = 0):
        self.iterated = True
        yield self.body

    def close(self) -> None:
        self.closed = True


class FakeSession:
    def __init__(self, raw: FakeRawResponse) -> None:
        self.raw = raw
        self.calls: list[dict] = []

    def request(self, method, url, **kwargs):
        self.calls.append(dict(kwargs, method=method, url=url))
        return self.raw


@pytest.mark.parametrize("status,headers", [
    (403, {}),
    (304, {}),
    (302, {"Location": URL_B}),
    (200, {"Content-Length": str(64 * 1024 * 1024)}),
])
def test_the_real_transport_closes_a_response_nobody_iterated(status, headers):
    """Closing an unstarted generator never runs its ``finally``, so the body
    guard cannot be the connection's only owner."""
    raw = FakeRawResponse(status, headers)
    transport = RequestsTransport(session=FakeSession(raw))

    response = transport.send(Request(url=URL_A))
    response.close()

    assert raw.iterated is False
    assert raw.closed is True


def test_closing_a_response_twice_is_harmless():
    raw = FakeRawResponse(200, {}, b"body")
    transport = RequestsTransport(session=FakeSession(raw))

    response = transport.send(Request(url=URL_A))
    response.close()
    response.close()

    assert raw.closed is True
    assert response.closed is True


def test_a_partially_read_body_still_closes():
    raw = FakeRawResponse(200, {}, b"body")
    transport = RequestsTransport(session=FakeSession(raw))

    response = transport.send(Request(url=URL_A))
    next(iter(response.chunks))
    response.close()

    assert raw.closed is True


# -------------------------------------------------- R5 provider cooldown ===

def test_a_cooldown_survives_moving_to_another_url(corpus, tmp_path):
    """A 429 constrains the provider, not the one URL that received it."""
    clock = ManualClock()
    transport = ScriptedTransport({
        URL_A: Response(status=429, headers={"Retry-After": "120"},
                        chunks=[b""]),
        URL_B: ok(),
    })
    service = service_for(transport, corpus, tmp_path, clock=clock)

    first = service.ingest_url(URL_A, provider="fixture")
    second = service.ingest_url(URL_B, provider="fixture")

    assert first.status is AcquisitionStatus.RATE_LIMITED
    assert first.deferral.delay_s == 120.0
    # The second URL never reached the transport.
    assert [request.url for request in transport.requests] == [URL_A]
    assert second.status is AcquisitionStatus.RATE_LIMITED
    assert second.deferral.not_before == "2026-10-10T00:02:00.000Z"
    assert clock.slept == []

    clock.seconds = 120.0
    third = service.ingest_url(URL_B, provider="fixture")
    assert third.status is AcquisitionStatus.OK
    assert [request.url for request in transport.requests] == [URL_A, URL_B]


def test_another_provider_is_not_held_by_the_first_providers_cooldown(
        corpus, tmp_path):
    clock = ManualClock()
    transport = ScriptedTransport({
        URL_A: Response(status=429, headers={"Retry-After": "120"},
                        chunks=[b""]),
        URL_B: ok(),
    })
    service = service_for(transport, corpus, tmp_path, clock=clock)

    service.ingest_url(URL_A, provider="first")
    other = service.ingest_url(URL_B, provider="second")

    assert other.status is AcquisitionStatus.OK


def test_a_pending_cooldown_is_restored_for_a_resumed_run(corpus, tmp_path):
    clock = ManualClock()
    transport = ScriptedTransport({
        URL_A: Response(status=429, headers={"Retry-After": "120"},
                        chunks=[b""]),
        URL_B: ok(),
    })
    service = service_for(transport, corpus, tmp_path, clock=clock)
    service.ingest_url(URL_A, provider="fixture")

    saved = AcquisitionState.in_corpus(tmp_path).cooldowns()
    assert saved == {"fixture": "2026-10-10T00:02:00.000Z"}

    resumed = service_for(transport, corpus, tmp_path, clock=clock)
    outcome = resumed.ingest_url(URL_B, provider="fixture")

    assert outcome.status is AcquisitionStatus.RATE_LIMITED
    assert [request.url for request in transport.requests] == [URL_A]


def test_a_long_pacing_interval_defers_instead_of_blocking(corpus, tmp_path):
    clock = ManualClock()
    transport = ScriptedTransport({URL_A: ok(), URL_B: ok()})
    service = service_for(transport, corpus, tmp_path, clock=clock,
                          provider_limits={"fixture": ProviderLimits(
                              min_interval_s=600.0)})

    service.ingest_url(URL_A, provider="fixture")
    second = service.ingest_url(URL_B, provider="fixture")

    assert second.status is AcquisitionStatus.RATE_LIMITED
    assert second.deferral.delay_s == 600.0
    assert clock.slept == []


# --------------------------------------------------- R6 redirected 304 ===

def test_a_304_after_a_redirect_resolves_against_the_url_that_was_asked_for(
        corpus, tmp_path):
    calls = {"n": 0}

    class Chain(ScriptedTransport):
        def send(self, request: Request) -> Response:
            self.requests.append(request)
            if request.url == URL_A:
                return redirect_to(URL_B)
            calls["n"] += 1
            if calls["n"] == 1:
                return ok(**{"ETag": '"v1"'})
            return Response(status=304, headers={})

    transport = Chain({})
    service = service_for(transport, corpus, tmp_path)

    first = service.ingest_url(URL_A, provider="fixture")
    second = service.ingest_url(URL_A, provider="fixture")

    assert first.status is AcquisitionStatus.OK
    assert second.status is AcquisitionStatus.OK
    assert second.unchanged is True
    assert second.source_document_id == first.source_document_id
    assert len(corpus.source_history("fixture", None)) == 1
    assert _attempt_count(corpus) == 2


def test_a_changed_redirect_target_does_not_reuse_the_cached_representation(
        corpus, tmp_path):
    third = "https://%s/build/99" % HOST_B
    state = {"target": URL_B, "served": 0}

    class Moving(ScriptedTransport):
        def send(self, request: Request) -> Response:
            self.requests.append(request)
            if request.url == URL_A:
                return redirect_to(state["target"])
            if request.url == URL_B:
                state["served"] += 1
                return ok(**{"ETag": '"v1"'})
            return Response(status=304, headers={})

    transport = Moving({})
    service = service_for(transport, corpus, tmp_path)

    service.ingest_url(URL_A, provider="fixture")
    state["target"] = third
    outcome = service.ingest_url(URL_A, provider="fixture")

    # The validator describes B's representation. A 304 from somewhere else
    # says nothing about the document we hold.
    assert outcome.status is AcquisitionStatus.INVALID_RESPONSE
    assert outcome.document is None


def test_a_validator_is_not_offered_to_an_origin_that_did_not_issue_it():
    """The cached representation came from B, so A never sees its ETag."""
    transport = ScriptedTransport({URL_A: redirect_to(URL_B), URL_B: ok()})
    clock = ManualClock()
    acquirer = HttpAcquirer(transport=transport, policy=policy(HOST_A, HOST_B),
                            clock=clock, scheduler=ProviderScheduler(clock))

    acquirer.fetch("fixture", URL_A, validators=Validators(etag='"v1"'),
                   validator_url=URL_B)

    assert "If-None-Match" not in transport.requests[0].headers
    assert transport.requests[1].headers["If-None-Match"] == '"v1"'


# ----------------------------------------- follow-up exact resource keys ===

@pytest.mark.parametrize("first_path,second_path", [
    ("/export?variant=first", "/export?variant=second"),
    ("/export?id=1&id=2", "/export?id=2&id=1"),
    ("/old", "/new"),
])
@pytest.mark.parametrize("unexpected_304", [False, True])
def test_changed_redirect_resource_never_reuses_old_build(
        corpus, tmp_path, first_path, second_path, unexpected_304):
    start = "https://%s/start" % HOST_A
    destination = {"path": first_path}

    def respond(request):
        if request.url == start:
            # Even on the same origin, the redirect endpoint must not get
            # a validator issued by its destination.
            assert "If-None-Match" not in request.headers
            return redirect_to("https://%s%s" % (HOST_A, destination["path"]))
        if request.headers.get("If-None-Match") == '"v1"' or unexpected_304 and destination["path"] == second_path:
            return Response(304)
        return ok(json.dumps({"path": destination["path"]}).encode(), ETag='"v1"')

    class Transport:
        def send(self, request):
            return respond(request)

    service = service_for(Transport(), corpus, tmp_path)
    original = service.ingest_url(start, provider="fixture")
    unchanged = service.ingest_url(start, provider="fixture")
    assert unchanged.unchanged
    assert unchanged.source_document_id == original.source_document_id
    destination["path"] = second_path
    changed = service.ingest_url(start, provider="fixture")
    if unexpected_304:
        assert changed.status is AcquisitionStatus.INVALID_RESPONSE
        assert changed.document is None
    else:
        assert changed.ok and not changed.unchanged
        assert changed.source_document_id != original.source_document_id
        assert json.loads(corpus.read_payload(changed.blob_hash))["path"] == second_path


def test_duplicate_query_order_survives_direct_cache_lookup(corpus, tmp_path):
    first = URL_A + "?id=1&id=2"
    second = URL_A + "?id=2&id=1"

    def response(request):
        assert "If-None-Match" not in request.headers
        return ok(json.dumps({"url": request.url}).encode(), ETag='"v1"')

    service = service_for(ScriptedTransport({first: response, second: response}),
                          corpus, tmp_path)
    one = service.ingest_url(first, provider="fixture")
    two = service.ingest_url(second, provider="fixture")
    assert one.source_document_id != two.source_document_id


def test_final_resource_cache_key_survives_restart_without_storing_secret(corpus, tmp_path):
    final = URL_B + "?access_token=" + SECRET
    transport = ScriptedTransport({URL_A: redirect_to(final), final: ok(ETag='"v1"')})
    service_for(transport, corpus, tmp_path).ingest_url(URL_A, provider="fixture")
    saved = (tmp_path / "acquisition-state.json").read_text()
    assert SECRET not in saved
    assert '"final_key"' in saved

    def cached(request):
        assert request.headers["If-None-Match"] == '"v1"'
        return Response(304)

    transport.routes[final] = cached
    resumed = service_for(transport, corpus, tmp_path)
    assert resumed.ingest_url(URL_A, provider="fixture").unchanged


def test_legacy_cache_without_exact_final_key_is_refetched(corpus, tmp_path):
    transport = ScriptedTransport({URL_A: ok(ETag='"v1"')})
    service_for(transport, corpus, tmp_path).ingest_url(URL_A, provider="fixture")
    path = tmp_path / "acquisition-state.json"
    saved = json.loads(path.read_text())
    for entry in saved["pages"].values():
        entry.pop("final_key")
    path.write_text(json.dumps(saved))
    resumed = service_for(transport, corpus, tmp_path)
    assert resumed.ingest_url(URL_A, provider="fixture").ok
    assert "If-None-Match" not in transport.requests[-1].headers


@pytest.mark.parametrize("attempt_budget", [1, 3])
def test_restart_honors_cooldown_until_deadline(corpus, tmp_path, attempt_budget):
    clock = ManualClock()
    transport = ScriptedTransport({URL_A: Response(429, {"Retry-After": "120"}), URL_B: ok()})
    first = service_for(transport, corpus, tmp_path, clock=clock,
                        limits=Limits(max_attempts=attempt_budget))
    first.ingest_url(URL_A, provider="fixture")
    resumed = service_for(transport, corpus, tmp_path, clock=clock)
    result = resumed.ingest_url(URL_B, provider="fixture")
    assert result.status is AcquisitionStatus.RATE_LIMITED
    assert len(transport.requests) == 1
    assert AcquisitionState.in_corpus(tmp_path).cooldowns()["fixture"] == "2026-10-10T00:02:00.000Z"
    assert resumed.ingest_url(URL_B, provider="other").ok
    clock.seconds = 120
    assert resumed.ingest_url(URL_B, provider="fixture").ok


def test_restoration_preserves_stricter_live_cooldown(corpus, tmp_path):
    clock = ManualClock()
    state = AcquisitionState.in_corpus(tmp_path)
    state.set_cooldowns({"fixture": "2026-10-10T00:02:00.000Z"})
    transport = ScriptedTransport({URL_A: ok()})
    acquirer = HttpAcquirer(transport=transport, policy=policy(HOST_A), clock=clock)
    acquirer.scheduler.defer_provider("fixture", 300)
    service = AcquisitionService(corpus, acquirer=acquirer, state=state, clock=clock)
    result = service.ingest_url(URL_A, provider="fixture")
    assert result.deferral.delay_s == 300
    assert transport.requests == []


@pytest.mark.parametrize("encoding,note", [
    ("ISO-8859-1", "caf\u00e9"), ("windows-1252", "price \u20ac"),
    ("utf-16-le", "caf\u00e9"), ("utf-16-be", "price \u20ac"),
])
@pytest.mark.parametrize("compressed", [False, True])
def test_declared_non_ascii_xml_preserves_raw_payload(corpus, encoding, note, compressed):
    xml = ('<?xml version="1.0" encoding="%s"?><PathOfBuilding><Notes>%s</Notes></PathOfBuilding>'
           % (encoding, note)).encode(encoding)
    payload = base64.urlsafe_b64encode(zlib.compress(xml)) if compressed else xml
    kind = "build_code" if compressed else "xml"
    result = AcquisitionService(corpus).ingest_bytes(payload, kind=kind, provider="fixture")
    assert result.ok
    assert corpus.read_payload(result.blob_hash) == payload


@pytest.mark.parametrize("payload", [
    b'<?xml version="1.0" encoding="UTF-8"?><PathOfBuilding>\xff</PathOfBuilding>',
    ('<?xml version="1.0" encoding="ISO-8859-1"?><PathOfBuilding/>').encode("utf-16"),
])
def test_invalid_encoding_remains_typed_refusal(corpus, payload):
    result = AcquisitionService(corpus).ingest_bytes(payload, kind="xml", provider="fixture")
    assert result.status is AcquisitionStatus.INVALID_RESPONSE
    assert result.document is None


# ------------------------------------------------------- R7 dot segments ===

def test_a_dot_segment_cannot_leave_the_approved_path():
    allowed = HostPolicy.of([HostRule(host=HOST_A,
                                      path_prefixes=("/approved/",))])

    assert allowed.check("https://%s/approved/build" % HOST_A) == (
        "https://%s/approved/build" % HOST_A)
    with pytest.raises(PolicyRefusal):
        allowed.check("https://%s/approved/../blocked" % HOST_A)
    with pytest.raises(PolicyRefusal):
        allowed.check("https://%s/approved/%%2e%%2e/blocked" % HOST_A)


def test_the_approved_url_is_the_one_the_client_will_send():
    """The policy and the HTTP client must agree on the path. ``requests``
    resolves dot segments when it prepares a request; this asserts there is
    nothing left for it to resolve. No request is made."""
    import requests

    allowed = HostPolicy.of([HostRule(host=HOST_A)])
    for spelling in ("https://%s/a/./b" % HOST_A,
                     "https://%s/a/c/../b" % HOST_A,
                     "https://%s/a/b?id=7" % HOST_A):
        approved = allowed.check(spelling)
        prepared = requests.Request("GET", approved).prepare()
        assert prepared.url == approved


def test_a_redirect_into_a_dot_segment_is_refused(corpus, tmp_path):
    escape = "https://%s/approved/../blocked" % HOST_A
    start = "https://%s/approved/x" % HOST_A
    transport = ScriptedTransport({start: redirect_to(escape)})
    clock = ManualClock()
    acquirer = HttpAcquirer(
        transport=transport,
        policy=HostPolicy.of([HostRule(host=HOST_A,
                                       path_prefixes=("/approved/",))]),
        clock=clock, scheduler=ProviderScheduler(clock))

    outcome = acquirer.fetch("fixture", start)

    assert outcome.status is AcquisitionStatus.UNSUPPORTED_ACCESS


# ----------------------------------------------------------- R8 JSON depth ===

def _attempt_count(corpus) -> int:
    return corpus.conn.execute(
        "SELECT COUNT(*) FROM source_record WHERE kind = 'acquisition_result'"
    ).fetchone()[0]


def _deep_json(levels: int) -> bytes:
    return ("[" * levels + "]" * levels).encode("utf-8")


def test_deeply_nested_json_is_a_typed_refusal_not_a_recursion_error():
    with pytest.raises(MalformedContent) as refused:
        inspect_content(_deep_json(2000), "json")
    assert refused.value.reason == "json_too_deep"


def test_the_depth_bound_is_the_same_on_every_interpreter():
    inspect_content(_deep_json(MAX_JSON_DEPTH), "json")
    with pytest.raises(MalformedContent):
        inspect_content(_deep_json(MAX_JSON_DEPTH + 1), "json")


def test_a_deep_document_through_the_service_stores_nothing(corpus, tmp_path):
    transport = ScriptedTransport({URL_A: ok(_deep_json(2000))})
    service = service_for(transport, corpus, tmp_path)

    outcome = service.ingest_url(URL_A, provider="fixture")

    assert outcome.status is AcquisitionStatus.INVALID_RESPONSE
    assert outcome.document is None
    assert corpus.source_history("fixture", None) == []


def test_a_deep_document_through_the_cli_reports_a_typed_failure(tmp_path,
                                                                 capsys):
    from pob2opt.acquisition import cli as acquisition_cli

    payload = tmp_path / "deep.json"
    payload.write_bytes(_deep_json(2000))
    code = acquisition_cli.main([
        "--corpus", str(tmp_path / "corpus"), "--provider", "fixture",
        "--input", str(payload)])

    assert code != 0
    printed = capsys.readouterr()
    assert "json_too_deep" in printed.out + printed.err

def test_ordinary_json_still_works():
    report = inspect_content(json.dumps({"a": [1, 2, {"b": 3}]}).encode(),
                             "json")
    assert report.kind == "json"
