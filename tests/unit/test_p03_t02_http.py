"""P03-T02 shared HTTP layer: policy, limits, statuses, scheduling, secrets.

Offline. The transport is injected, so no socket is opened and no provider is
contacted. `tests/unit/conftest.py` blocks outbound sockets for this directory
and nothing here works around that.

Every limit is checked by behaviour. A test that only read the configured value
back would pass against an implementation that accepts the parameter and
ignores it, so each one is written so that ignoring the parameter changes the
outcome.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone

import pytest

from pob2opt.acquisition import (
    AcquisitionService,
    AcquisitionState,
    HostPolicy,
    HostRule,
    HttpAcquirer,
    Limits,
    PolicyRefusal,
    ProviderLimits,
    ProviderScheduler,
    Request,
    Response,
    TransportConnectionError,
    TransportTimeout,
    Validators,
    classify,
    parse_retry_after,
    redact_url,
)
from pob2opt.domain.enums import AccessMethod, AcquisitionStatus
from pob2opt.storage import RunStore

HOST = "builds.example.invalid"
URL = "https://%s/build/42" % HOST
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


class CountingChunks:
    """A body that records how much of it the client actually pulled."""

    def __init__(self, chunk: bytes, count: int) -> None:
        self.chunk = chunk
        self.count = count
        self.served = 0
        self.closed = False

    def __iter__(self):
        for _ in range(self.count):
            self.served += 1
            yield self.chunk

    def close(self) -> None:
        self.closed = True


class StubTransport:
    """Replays scripted responses and keeps every request it was handed."""

    def __init__(self, *script) -> None:
        self.script = list(script)
        self.requests: list[Request] = []

    def send(self, request: Request) -> Response:
        self.requests.append(request)
        item = self.script[min(len(self.requests) - 1, len(self.script) - 1)]
        if callable(item) and not isinstance(item, Response):
            item = item(request)
        if isinstance(item, BaseException):
            raise item
        return item


def ok_response(body: bytes = BUILD_JSON, **headers) -> Response:
    merged = {"Content-Type": "application/json"}
    merged.update(headers)
    return Response(status=200, headers=merged, chunks=[body], url=URL)


def status_response(code: int, **headers) -> Response:
    return Response(status=code, headers=headers, chunks=[b"error page"], url=URL)


def policy(*hosts) -> HostPolicy:
    return HostPolicy.of(HostRule(host=host) for host in (hosts or (HOST,)))


def acquirer(transport, *, clock=None, limits=None, provider_limits=None,
             host_policy=None) -> HttpAcquirer:
    clock = clock or ManualClock()
    return HttpAcquirer(transport=transport, policy=host_policy or policy(),
                        limits=limits or Limits(), clock=clock,
                        scheduler=ProviderScheduler(clock),
                        provider_limits=provider_limits)


@pytest.fixture()
def corpus(tmp_path):
    store = RunStore.open_corpus(tmp_path / "corpus")
    yield store
    store.close()


def service_with(transport, corpus, tmp_path, **kwargs) -> AcquisitionService:
    client = acquirer(transport, **kwargs)
    return AcquisitionService(corpus, acquirer=client, clock=client.clock,
                              state=AcquisitionState.in_corpus(tmp_path),
                              limits=client.limits)


# ----------------------------------------------------------- host policy ===

def test_nothing_is_approved_by_default():
    assert HostPolicy.deny_all().allowed_hosts == ()
    with pytest.raises(PolicyRefusal) as refusal:
        HostPolicy.deny_all().check(URL)
    assert "allow list is empty" in refusal.value.reason


@pytest.mark.parametrize("url,fragment", [
    ("http://%s/build/42" % HOST, "scheme"),
    ("ftp://%s/build/42" % HOST, "scheme"),
    ("https://user:pw@%s/build/42" % HOST, "credentials"),
    ("https://other.invalid/build/42", "allow list"),
    ("https://sub.%s/build/42" % HOST, "allow list"),
    ("https://%s:8443/build/42" % HOST, "port"),
    ("https://127.0.0.1/build/42", "IP literal"),
])
def test_refused_urls(url, fragment):
    with pytest.raises(PolicyRefusal) as refusal:
        policy().check(url)
    assert fragment in refusal.value.reason


def test_a_refusal_never_repeats_the_credential():
    with pytest.raises(PolicyRefusal) as refusal:
        policy().check("https://user:%s@%s/x" % (SECRET, HOST))
    assert SECRET not in str(refusal.value)


def test_path_prefixes_and_subdomains_are_opt_in():
    rule = HostPolicy.of([HostRule(host=HOST, path_prefixes=("/build/",),
                                   include_subdomains=True)])
    assert rule.allows(URL)
    assert rule.allows("https://cdn.%s/build/7" % HOST)
    with pytest.raises(PolicyRefusal):
        rule.check("https://%s/admin" % HOST)


def test_an_unapproved_host_is_unsupported_access_not_a_failed_fetch(corpus, tmp_path):
    transport = StubTransport(ok_response())
    service = service_with(transport, corpus, tmp_path,
                           host_policy=HostPolicy.deny_all())

    outcome = service.ingest_url(URL, provider="fixture")

    assert outcome.status is AcquisitionStatus.UNSUPPORTED_ACCESS
    assert transport.requests == []        # nothing was sent at all
    assert outcome.document is None
    assert list(corpus.blobs.iter_hashes()) == []


# ------------------------------------------------- the six failure cases ===

FAILURES = [
    (403, AcquisitionStatus.ACCESS_BLOCKED, False, 1),
    (404, AcquisitionStatus.NOT_FOUND, False, 1),
    (429, AcquisitionStatus.RATE_LIMITED, True, 3),
]


@pytest.mark.parametrize("code,status,retryable,attempts", FAILURES)
def test_http_failures_are_typed_and_store_nothing(corpus, tmp_path, code,
                                                   status, retryable, attempts):
    transport = StubTransport(status_response(code))
    service = service_with(transport, corpus, tmp_path)

    outcome = service.ingest_url(URL, provider="fixture")

    assert outcome.status is status
    assert outcome.document is None
    assert outcome.result.source_document_id is None
    assert outcome.result.http_status == code
    assert outcome.result.retry_eligible is retryable
    assert len(transport.requests) == attempts
    assert list(corpus.blobs.iter_hashes()) == []
    assert corpus.source_history("fixture", None) == []


def test_an_oversized_response_is_refused_mid_stream(corpus, tmp_path):
    body = CountingChunks(b"x" * 1024, 4096)          # 4 MiB offered
    transport = StubTransport(Response(200, {"Content-Type": "application/json"},
                                       chunks=body))
    service = service_with(transport, corpus, tmp_path,
                           limits=Limits(max_bytes=8 * 1024))

    outcome = service.ingest_url(URL, provider="fixture")

    assert outcome.status is AcquisitionStatus.INVALID_RESPONSE
    assert outcome.document is None
    # Enforced while streaming: an implementation that buffered the whole body
    # and then compared sizes would have pulled all 4096 chunks.
    assert body.served <= 9
    assert body.closed is True
    assert list(corpus.blobs.iter_hashes()) == []


def test_a_declared_oversized_length_is_refused_before_the_body(corpus, tmp_path):
    body = CountingChunks(b"x" * 1024, 4096)
    transport = StubTransport(Response(
        200, {"Content-Type": "application/json", "Content-Length": "4194304"},
        chunks=body))
    service = service_with(transport, corpus, tmp_path,
                           limits=Limits(max_bytes=8 * 1024))

    outcome = service.ingest_url(URL, provider="fixture")

    assert outcome.status is AcquisitionStatus.INVALID_RESPONSE
    assert body.served == 0


def test_a_timeout_is_a_timeout_not_an_empty_build(corpus, tmp_path):
    transport = StubTransport(TransportTimeout("read timed out"))
    service = service_with(transport, corpus, tmp_path)

    outcome = service.ingest_url(URL, provider="fixture")

    assert outcome.status is AcquisitionStatus.TIMEOUT
    assert outcome.document is None
    assert outcome.result.retry_eligible is True
    assert len(transport.requests) == 3
    assert list(corpus.blobs.iter_hashes()) == []


def test_malformed_content_from_a_200_is_invalid_response(corpus, tmp_path):
    transport = StubTransport(ok_response(b'{"skills": [1,'))
    service = service_with(transport, corpus, tmp_path)

    outcome = service.ingest_url(URL, provider="fixture")

    assert outcome.status is AcquisitionStatus.INVALID_RESPONSE
    assert outcome.result.http_status == 200
    assert outcome.document is None
    assert list(corpus.blobs.iter_hashes()) == []


def test_an_empty_200_is_not_a_successful_acquisition(corpus, tmp_path):
    transport = StubTransport(Response(200, {"Content-Type": "application/json"},
                                       chunks=[b""]))
    service = service_with(transport, corpus, tmp_path)

    outcome = service.ingest_url(URL, provider="fixture")

    assert outcome.status is AcquisitionStatus.INVALID_RESPONSE
    assert outcome.document is None


def test_every_failure_status_maps_to_the_contract_vocabulary():
    assert classify(401)[0] is AcquisitionStatus.ACCESS_BLOCKED
    assert classify(410)[0] is AcquisitionStatus.NOT_FOUND
    assert classify(503) == (AcquisitionStatus.INVALID_RESPONSE, True)
    assert classify(418) == (AcquisitionStatus.INVALID_RESPONSE, False)
    assert classify(408) == (AcquisitionStatus.TIMEOUT, True)


# ------------------------------------------------------- limits enforced ===

def test_the_interfaces_md_timeouts_reach_the_transport(corpus, tmp_path):
    transport = StubTransport(ok_response())
    service = service_with(transport, corpus, tmp_path)

    service.ingest_url(URL, provider="fixture")

    sent = transport.requests[0]
    assert (sent.connect_timeout_s, sent.read_timeout_s) == (10.0, 30.0)
    assert sent.max_bytes == 20 * 1024 * 1024


def test_a_provider_may_tighten_a_timeout_but_not_loosen_it(corpus, tmp_path):
    def slow(request):
        # Honours the timeout it was given, so an ignored parameter shows up as
        # a successful fetch instead of a timeout.
        if request.read_timeout_s < 20.0:
            raise TransportTimeout("read timed out")
        return ok_response()

    strict = service_with(StubTransport(slow), corpus, tmp_path,
                          provider_limits={"fixture": ProviderLimits(
                              read_timeout_s=5.0)})
    assert strict.ingest_url(URL, provider="fixture").status is (
        AcquisitionStatus.TIMEOUT)

    store = RunStore.open_corpus(tmp_path / "other")
    relaxed = service_with(StubTransport(slow), store, tmp_path / "other",
                           provider_limits={"fixture": ProviderLimits(
                               read_timeout_s=600.0, max_bytes=1 << 30,
                               max_attempts=99)})
    outcome = relaxed.ingest_url(URL, provider="fixture")
    assert outcome.status is AcquisitionStatus.OK
    effective = relaxed.acquirer.limits_for("fixture")
    assert effective.read_timeout_s == 30.0
    assert effective.max_bytes == 20 * 1024 * 1024
    assert effective.max_attempts == 3
    store.close()


def test_a_provider_attempt_cap_is_obeyed(corpus, tmp_path):
    transport = StubTransport(status_response(429))
    service = service_with(transport, corpus, tmp_path,
                           provider_limits={"fixture": ProviderLimits(
                               max_attempts=2)})

    service.ingest_url(URL, provider="fixture")

    assert len(transport.requests) == 2


def test_a_non_transient_failure_is_attempted_once(corpus, tmp_path):
    transport = StubTransport(status_response(403))
    service = service_with(transport, corpus, tmp_path)

    service.ingest_url(URL, provider="fixture")

    assert len(transport.requests) == 1


def test_a_transient_failure_that_recovers_is_a_success(corpus, tmp_path):
    transport = StubTransport(status_response(503), ok_response())
    service = service_with(transport, corpus, tmp_path)

    outcome = service.ingest_url(URL, provider="fixture")

    assert outcome.status is AcquisitionStatus.OK
    assert outcome.attempts == 2
    assert outcome.document.byte_count == len(BUILD_JSON)


# ---------------------------------------------------------- scheduling ===

def test_a_short_advertised_delay_is_waited_out_in_full(corpus, tmp_path):
    clock = ManualClock()
    transport = StubTransport(status_response(429, **{"Retry-After": "5"}))
    service = service_with(transport, corpus, tmp_path, clock=clock)

    outcome = service.ingest_url(URL, provider="fixture")

    assert outcome.status is AcquisitionStatus.RATE_LIMITED
    assert clock.slept == [5.0, 5.0]      # the full delay, both times, not less
    assert len(transport.requests) == 3


def test_a_long_advertised_delay_is_scheduled_not_truncated(corpus, tmp_path):
    clock = ManualClock()
    transport = StubTransport(status_response(429, **{"Retry-After": "120"}))
    service = service_with(transport, corpus, tmp_path, clock=clock)

    outcome = service.ingest_url(URL, provider="fixture")

    assert outcome.status is AcquisitionStatus.RATE_LIMITED
    assert clock.slept == []              # nothing was slept, nothing was cut
    assert len(transport.requests) == 1
    assert outcome.deferral.delay_s == 120.0
    assert outcome.deferral.not_before == "2026-10-10T00:02:00.000Z"
    assert "not_before" in outcome.result.diagnostic
    assert outcome.result.retry_eligible is True


def test_an_http_date_retry_after_is_understood():
    clock = ManualClock()
    assert parse_retry_after("Sat, 10 Oct 2026 00:00:30 GMT", clock=clock) == 30.0
    assert parse_retry_after("Sat, 10 Oct 2020 00:00:00 GMT", clock=clock) == 0.0
    assert parse_retry_after("whenever") is None
    assert parse_retry_after(None) is None


def test_backoff_applies_when_nothing_is_advertised(corpus, tmp_path):
    clock = ManualClock()
    transport = StubTransport(TransportConnectionError("reset"))
    service = service_with(transport, corpus, tmp_path, clock=clock)

    service.ingest_url(URL, provider="fixture")

    assert clock.slept == [1.0, 2.0]


def test_provider_pacing_spaces_consecutive_requests(corpus, tmp_path):
    clock = ManualClock()
    transport = StubTransport(ok_response(), ok_response(b'{"id": "43"}'))
    service = service_with(transport, corpus, tmp_path, clock=clock,
                           provider_limits={"fixture": ProviderLimits(
                               min_interval_s=2.5)})

    service.ingest_url(URL, provider="fixture")
    service.ingest_url(URL + "b", provider="fixture")

    assert clock.slept == [2.5]           # the second request waited its turn


# ----------------------------------------------- conditional requests ===

def test_a_conditional_request_is_sent_and_304_stores_nothing_new(corpus, tmp_path):
    transport = StubTransport(
        ok_response(ETag='"v1"', **{"Last-Modified": "Sat, 10 Oct 2026 00:00:00 GMT"}),
        Response(304, {"ETag": '"v1"'}, chunks=[]))
    service = service_with(transport, corpus, tmp_path)

    first = service.ingest_url(URL, provider="fixture")
    second = service.ingest_url(URL, provider="fixture")

    assert first.created is True
    assert second.status is AcquisitionStatus.OK
    assert second.unchanged is True
    assert second.created is False
    assert second.source_document_id == first.source_document_id
    assert transport.requests[1].headers["If-None-Match"] == '"v1"'
    assert transport.requests[1].headers["If-Modified-Since"].startswith("Sat,")
    assert len(list(corpus.blobs.iter_hashes())) == 1
    assert len(corpus.source_history("fixture", None)) == 1


def test_a_304_without_a_validator_is_not_a_success(corpus, tmp_path):
    transport = StubTransport(Response(304, {}, chunks=[]))
    service = service_with(transport, corpus, tmp_path)

    outcome = service.ingest_url(URL, provider="fixture")

    assert outcome.status is AcquisitionStatus.INVALID_RESPONSE
    assert outcome.document is None


def test_the_same_url_fetched_twice_writes_one_record(corpus, tmp_path):
    transport = StubTransport(ok_response(), ok_response())
    service = service_with(transport, corpus, tmp_path)

    first = service.ingest_url(URL, provider="fixture")
    second = service.ingest_url(URL, provider="fixture")

    assert first.source_document_id == second.source_document_id
    assert second.created is False
    assert len(list(corpus.blobs.iter_hashes())) == 1


def test_resume_cursors_survive_a_new_process(tmp_path):
    state = AcquisitionState.in_corpus(tmp_path)
    state.set_cursor("fixture", "listing", "page-7")

    assert AcquisitionState.in_corpus(tmp_path).cursor("fixture", "listing") == (
        "page-7")
    AcquisitionState.in_corpus(tmp_path).set_cursor("fixture", "listing", None)
    assert AcquisitionState.in_corpus(tmp_path).cursor("fixture", "listing") is None


# ------------------------------------------------------------ redirects ===

def test_a_redirect_inside_the_allow_list_is_followed(corpus, tmp_path):
    transport = StubTransport(
        Response(302, {"Location": "https://%s/build/42/v2" % HOST}, chunks=[]),
        ok_response())
    service = service_with(transport, corpus, tmp_path)

    outcome = service.ingest_url(URL, provider="fixture")

    assert outcome.status is AcquisitionStatus.OK
    assert transport.requests[1].url.endswith("/v2")


def test_a_redirect_off_the_allow_list_is_refused(corpus, tmp_path):
    transport = StubTransport(
        Response(301, {"Location": "https://elsewhere.invalid/build/42"},
                 chunks=[]),
        ok_response())
    service = service_with(transport, corpus, tmp_path)

    outcome = service.ingest_url(URL, provider="fixture")

    assert outcome.status is AcquisitionStatus.UNSUPPORTED_ACCESS
    assert len(transport.requests) == 1
    assert list(corpus.blobs.iter_hashes()) == []


def test_a_redirect_loop_is_bounded(corpus, tmp_path):
    transport = StubTransport(Response(302, {"Location": URL}, chunks=[]))
    service = service_with(transport, corpus, tmp_path,
                           limits=Limits(max_redirects=2))

    outcome = service.ingest_url(URL, provider="fixture")

    assert outcome.status is AcquisitionStatus.INVALID_RESPONSE
    assert len(transport.requests) == 3


# ----------------------------------------------------------- credentials ===

def test_no_credential_reaches_a_blob_a_record_a_log_or_the_state(
        corpus, tmp_path, caplog):
    secret_url = "https://%s/build/42?access_token=%s&page=3" % (HOST, SECRET)
    transport = StubTransport(ok_response())
    service = service_with(transport, corpus, tmp_path)

    with caplog.at_level(logging.DEBUG, logger="pob2opt.acquisition"):
        outcome = service.ingest_url(
            secret_url, provider="fixture",
            headers={"Authorization": "Bearer %s" % SECRET,
                     "Cookie": "session=%s" % SECRET})

    assert outcome.status is AcquisitionStatus.OK
    # The real request still carried them; only what we keep is redacted.
    assert transport.requests[0].headers["Authorization"].endswith(SECRET)

    document = outcome.document
    assert SECRET not in (document.source_url or "")
    assert document.source_url.endswith("?access_token=REDACTED&page=3")
    assert SECRET not in json.dumps(_as_json(corpus, document.record_id))
    assert SECRET not in json.dumps(_as_json(corpus, outcome.result.record_id))
    assert SECRET not in corpus.read_payload(document.blob_hash).decode("utf-8")
    assert SECRET not in caplog.text
    assert SECRET not in (tmp_path / "acquisition-state.json").read_text(
        encoding="utf-8")


def test_a_failed_fetch_keeps_no_credential_either(corpus, tmp_path, caplog):
    secret_url = "https://%s/build/42?api_key=%s" % (HOST, SECRET)
    transport = StubTransport(status_response(403))
    service = service_with(transport, corpus, tmp_path)

    with caplog.at_level(logging.DEBUG, logger="pob2opt.acquisition"):
        outcome = service.ingest_url(secret_url, provider="fixture")

    assert outcome.status is AcquisitionStatus.ACCESS_BLOCKED
    assert SECRET not in outcome.result.source_ref
    assert SECRET not in json.dumps(_as_json(corpus, outcome.result.record_id))
    assert SECRET not in caplog.text


def test_redact_url_keeps_the_address_and_drops_the_rest():
    assert redact_url("https://h.invalid/a?token=x&page=2") == (
        "https://h.invalid/a?token=REDACTED&page=2")
    assert redact_url("https://user:pw@h.invalid/a#frag") == (
        "https://REDACTED@h.invalid/a")
    assert redact_url("not a url at all") == "not a url at all"
    assert redact_url("") == "REDACTED"


def test_the_stored_url_is_the_redacted_one_in_the_access_method(corpus, tmp_path):
    transport = StubTransport(ok_response())
    service = service_with(transport, corpus, tmp_path)

    outcome = service.ingest_url(URL, provider="fixture",
                                 access_method=AccessMethod.DOCUMENTED_API)

    assert outcome.document.access_method is AccessMethod.DOCUMENTED_API
    assert outcome.document.source_url == URL


def _as_json(store, record_id):
    row = store.conn.execute("SELECT json FROM source_record WHERE record_id = ?",
                             (record_id,)).fetchone()
    return json.loads(row["json"])


# ---------------------------------------------------- no acquirer at all ===

def test_a_service_without_an_acquirer_refuses_urls(corpus, tmp_path):
    service = AcquisitionService(corpus, state=AcquisitionState.in_memory())

    outcome = service.ingest_url(URL, provider="fixture")

    assert outcome.status is AcquisitionStatus.UNSUPPORTED_ACCESS
    assert outcome.document is None


def test_validators_are_absent_until_a_page_is_cached(tmp_path):
    state = AcquisitionState.in_corpus(tmp_path)
    assert bool(state.validators("fixture", URL)) is False
    assert Validators(etag='"v"').headers() == {"If-None-Match": '"v"'}
