"""The shared HTTP layer (P03-T02).

One class, :class:`HttpAcquirer`, applies everything interfaces.md fixes about
acquisition: host policy, the 10/30 second timeouts, the 20 MiB size limit, at
most three attempts for classified transient failures, full advertised retry
delays, conditional requests and per-provider pacing. It returns a typed
outcome; it never returns a body for anything but a 200.

No provider knowledge lives here. There is no adapter, no pagination and no
field extraction: P03-T03 owns those and will call this.

The two rules worth stating plainly, because they are the ones a downstream
project depends on:

* A failure returns ``body=None``. A refused, blocked, missing, rate-limited,
  timed-out, oversized or malformed response never produces bytes to store, so
  it cannot become a successful empty build further down.
* Nothing that could carry a credential is logged or returned. The URL in an
  outcome is the redacted one, and header values never leave this module.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Mapping
from urllib.parse import urljoin

from ..domain.enums import AcquisitionStatus
from .hosts import HostPolicy, PolicyRefusal
from .limits import Limits, ProviderLimits
from .redaction import redact_diagnostic, redact_url
from .scheduling import Clock, Deferral, ProviderScheduler, SystemClock, parse_retry_after
from .transport import (
    Request,
    Response,
    Transport,
    TransportConnectionError,
    TransportError,
    TransportTimeout,
)

LOGGER = logging.getLogger("pob2opt.acquisition")

USER_AGENT = "pob2opt-acquisition/1 (+local research tool)"

REDIRECT_STATUSES = (301, 302, 303, 307, 308)

#: Status codes whose failure is classified transient, so an attempt may be
#: repeated. Everything else is answered once and kept.
TRANSIENT_STATUSES = (408, 425, 429, 500, 502, 503, 504)


@dataclass(frozen=True)
class Validators:
    """What a previous acquisition of the same URL returned."""

    etag: str | None = None
    last_modified: str | None = None

    def headers(self) -> dict[str, str]:
        out: dict[str, str] = {}
        if self.etag:
            out["If-None-Match"] = self.etag
        if self.last_modified:
            out["If-Modified-Since"] = self.last_modified
        return out

    def __bool__(self) -> bool:
        return bool(self.etag or self.last_modified)


@dataclass(frozen=True)
class FetchOutcome:
    status: AcquisitionStatus
    #: Redacted. This is the only URL form that leaves the module.
    url: str
    http_status: int | None = None
    body: bytes | None = None
    media_type: str | None = None
    etag: str | None = None
    last_modified: str | None = None
    attempts: int = 0
    retry_eligible: bool = False
    deferral: Deferral | None = None
    #: Seconds the provider advertised through ``Retry-After``, kept whole.
    retry_after_s: float | None = None
    diagnostic: str | None = None
    #: True for a 304: the stored copy is current and nothing was downloaded.
    unchanged: bool = False
    #: The limits actually applied, after provider tightening.
    limits: Limits = field(default_factory=Limits)

    @property
    def ok(self) -> bool:
        return self.status is AcquisitionStatus.OK


class HttpAcquirer:
    """Policy, limits and scheduling around one injected transport."""

    def __init__(self, *, transport: Transport,
                 policy: HostPolicy | None = None,
                 limits: Limits | None = None,
                 provider_limits: Mapping[str, ProviderLimits] | None = None,
                 clock: Clock | None = None,
                 scheduler: ProviderScheduler | None = None,
                 user_agent: str = USER_AGENT) -> None:
        self.transport = transport
        # Deny by default: a caller that wants a host must name it.
        self.policy = policy if policy is not None else HostPolicy.deny_all()
        self.limits = limits or Limits()
        self.provider_limits = dict(provider_limits or {})
        self.clock = clock or SystemClock()
        self.scheduler = scheduler or ProviderScheduler(self.clock)
        self.user_agent = user_agent

    def limits_for(self, provider: str) -> Limits:
        return self.limits.tightened_by(self.provider_limits.get(provider))

    def fetch(self, provider: str, url: str, *,
              headers: Mapping[str, str] | None = None,
              validators: Validators | None = None) -> FetchOutcome:
        limits = self.limits_for(provider)
        try:
            target = self.policy.check(url)
        except PolicyRefusal as refusal:
            return self._refused(refusal, limits)

        validators = validators or Validators()
        attempts = 0
        redirects = 0
        last: FetchOutcome | None = None

        while attempts < limits.max_attempts:
            attempts += 1
            self.scheduler.wait_for_slot(provider, limits.min_interval_s)
            try:
                response = self.transport.send(self._request(target, limits, headers,
                                                             validators))
            except TransportError as error:
                last = self._transport_failure(error, target, attempts, limits)
            else:
                with _closing(response):
                    if response.status in REDIRECT_STATUSES:
                        location = response.header("Location")
                        moved = self._redirect(target, location, limits, redirects)
                        if isinstance(moved, FetchOutcome):
                            return _with_attempts(moved, attempts)
                        target, redirects = moved, redirects + 1
                        attempts -= 1  # a redirect is not a retry
                        continue
                    last = self._handle(response, target, attempts, limits,
                                        validators)

            if not last.retry_eligible:
                return last
            if attempts >= limits.max_attempts:
                break
            deferral = self.scheduler.plan_retry(
                attempt=attempts,
                advertised_delay_s=_advertised_delay(last),
                max_inline_wait_s=limits.max_inline_wait_s,
                reason=last.status.value)
            if deferral is not None:
                # The advertised delay is longer than we will hold a process
                # open for. It is kept whole and handed back as a schedule.
                return _with_deferral(last, deferral)

        assert last is not None
        LOGGER.info("acquisition exhausted attempts provider=%s url=%s status=%s",
                    provider, redact_url(target), last.status.value)
        return last

    # -- internals ---------------------------------------------------------

    def _request(self, url: str, limits: Limits,
                 headers: Mapping[str, str] | None,
                 validators: Validators) -> Request:
        sent = {"User-Agent": self.user_agent, "Accept-Encoding": "identity"}
        sent.update({str(k): str(v) for k, v in (headers or {}).items()})
        sent.update(validators.headers())
        return Request(url=url, headers=sent,
                       connect_timeout_s=limits.connect_timeout_s,
                       read_timeout_s=limits.read_timeout_s,
                       max_bytes=limits.max_bytes)

    def _refused(self, refusal: PolicyRefusal, limits: Limits) -> FetchOutcome:
        LOGGER.info("acquisition refused url=%s reason=%s",
                    refusal.url, refusal.reason)
        return FetchOutcome(
            status=AcquisitionStatus.UNSUPPORTED_ACCESS,
            url=refusal.url,
            retry_eligible=False,
            diagnostic=redact_diagnostic(refusal.reason),
            limits=limits)

    def _transport_failure(self, error: TransportError, url: str, attempts: int,
                           limits: Limits) -> FetchOutcome:
        if isinstance(error, TransportTimeout):
            status = AcquisitionStatus.TIMEOUT
        elif isinstance(error, TransportConnectionError):
            status = AcquisitionStatus.INVALID_RESPONSE
        else:
            status = AcquisitionStatus.INVALID_RESPONSE
        LOGGER.info("acquisition transport failure url=%s status=%s attempt=%d",
                    redact_url(url), status.value, attempts)
        return FetchOutcome(status=status, url=redact_url(url),
                            attempts=attempts, retry_eligible=True,
                            diagnostic=redact_diagnostic(str(error)),
                            limits=limits)

    def _redirect(self, url: str, location: str | None, limits: Limits,
                  redirects: int):
        if not location:
            return FetchOutcome(
                status=AcquisitionStatus.INVALID_RESPONSE, url=redact_url(url),
                retry_eligible=False, limits=limits,
                diagnostic="redirect without a Location header")
        if redirects >= limits.max_redirects:
            return FetchOutcome(
                status=AcquisitionStatus.INVALID_RESPONSE, url=redact_url(url),
                retry_eligible=False, limits=limits,
                diagnostic="more than %d redirects" % limits.max_redirects)
        target = urljoin(url, location)
        try:
            return self.policy.check(target)
        except PolicyRefusal as refusal:
            # An approved host cannot delegate to an unapproved one.
            return self._refused(refusal, limits)

    def _handle(self, response: Response, url: str, attempts: int,
                limits: Limits, validators: Validators) -> FetchOutcome:
        status_code = response.status
        base = dict(url=redact_url(url), http_status=status_code,
                    attempts=attempts, limits=limits)

        if status_code == 304:
            if not validators:
                return FetchOutcome(
                    status=AcquisitionStatus.INVALID_RESPONSE,
                    retry_eligible=False,
                    diagnostic="304 for a request that carried no validator",
                    **base)
            return FetchOutcome(status=AcquisitionStatus.OK, unchanged=True,
                                etag=response.header("ETag") or validators.etag,
                                last_modified=(response.header("Last-Modified")
                                               or validators.last_modified),
                                **base)

        if status_code == 200:
            return self._read_body(response, limits, base)

        status, transient = classify(status_code)
        diagnostic = "HTTP %d" % status_code
        retry_after = parse_retry_after(response.header("Retry-After"),
                                        clock=self.clock)
        if retry_after is not None:
            diagnostic += " retry-after=%gs" % retry_after
        LOGGER.info("acquisition failed url=%s http=%d status=%s attempt=%d",
                    redact_url(url), status_code, status.value, attempts)
        return FetchOutcome(status=status, retry_eligible=transient,
                            diagnostic=redact_diagnostic(diagnostic),
                            retry_after_s=retry_after, **base)

    def _read_body(self, response: Response, limits: Limits,
                   base: dict) -> FetchOutcome:
        declared = response.header("Content-Length")
        if declared is not None:
            try:
                if int(declared) > limits.max_bytes:
                    return _too_large(limits, base,
                                      "declared %s bytes" % declared)
            except ValueError:
                pass

        body = bytearray()
        try:
            for chunk in response.chunks:
                body += chunk
                if len(body) > limits.max_bytes:
                    # Stop reading here. Waiting for the end would mean holding
                    # exactly the payload the limit exists to refuse.
                    response.close()
                    return _too_large(limits, base,
                                      "read past %d bytes" % limits.max_bytes)
        except TransportTimeout as error:
            return FetchOutcome(status=AcquisitionStatus.TIMEOUT,
                                retry_eligible=True,
                                diagnostic=redact_diagnostic(str(error)), **base)
        except TransportError as error:
            return FetchOutcome(status=AcquisitionStatus.INVALID_RESPONSE,
                                retry_eligible=True,
                                diagnostic=redact_diagnostic(str(error)), **base)

        if not body:
            return FetchOutcome(status=AcquisitionStatus.INVALID_RESPONSE,
                                retry_eligible=False,
                                diagnostic="200 with an empty body", **base)
        return FetchOutcome(status=AcquisitionStatus.OK, body=bytes(body),
                            media_type=response.header("Content-Type"),
                            etag=response.header("ETag"),
                            last_modified=response.header("Last-Modified"),
                            retry_eligible=False, **base)


def classify(http_status: int) -> tuple[AcquisitionStatus, bool]:
    """Map an HTTP status to the contracts.md vocabulary and transience."""
    if http_status in (401, 403, 451):
        return AcquisitionStatus.ACCESS_BLOCKED, False
    if http_status in (404, 410):
        return AcquisitionStatus.NOT_FOUND, False
    if http_status == 429:
        return AcquisitionStatus.RATE_LIMITED, True
    if http_status in (408, 425):
        return AcquisitionStatus.TIMEOUT, True
    if http_status >= 500:
        return AcquisitionStatus.INVALID_RESPONSE, http_status in TRANSIENT_STATUSES
    return AcquisitionStatus.INVALID_RESPONSE, False


def _too_large(limits: Limits, base: dict, detail: str) -> FetchOutcome:
    LOGGER.info("acquisition refused oversized payload url=%s limit=%d",
                base.get("url"), limits.max_bytes)
    return FetchOutcome(
        status=AcquisitionStatus.INVALID_RESPONSE, retry_eligible=False,
        diagnostic="payload exceeds the %d byte limit (%s)"
                   % (limits.max_bytes, detail), **base)


def _advertised_delay(outcome: FetchOutcome) -> float | None:
    return outcome.retry_after_s


def _with_attempts(outcome: FetchOutcome, attempts: int) -> FetchOutcome:
    import dataclasses

    return dataclasses.replace(outcome, attempts=attempts)


def _with_deferral(outcome: FetchOutcome, deferral: Deferral) -> FetchOutcome:
    import dataclasses

    diagnostic = " ".join(filter(None, [outcome.diagnostic, deferral.describe()]))
    return dataclasses.replace(outcome, deferral=deferral,
                               diagnostic=redact_diagnostic(diagnostic))


class _closing:
    def __init__(self, response: Response) -> None:
        self.response = response

    def __enter__(self) -> Response:
        return self.response

    def __exit__(self, *exc: object) -> None:
        self.response.close()
