"""The transport seam (P03-T02).

Everything above this module is offline-testable: the HTTP rules live in
``http.py`` and a test supplies its own :class:`Transport`. A transport does
one thing, sends one request and returns a streaming response. It does not
retry, does not follow redirects and does not decide what a status means.

``RequestsTransport`` is the real one. ``requests`` is imported inside the
call, so importing ``pob2opt.acquisition`` neither needs it nor opens a socket.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, Iterator, Mapping, Protocol

#: Read size for the streaming body. Small enough that the size limit is hit
#: shortly after it is exceeded, not after the whole payload has arrived.
CHUNK_BYTES = 64 * 1024


class TransportError(Exception):
    """A transport-level failure. The URL in the message is already redacted."""


class TransportTimeout(TransportError):
    """Connect or read timeout. Classified transient."""


class TransportConnectionError(TransportError):
    """DNS, TLS or connection failure. Classified transient."""


@dataclass(frozen=True)
class Request:
    url: str
    method: str = "GET"
    headers: Mapping[str, str] = field(default_factory=dict)
    connect_timeout_s: float = 10.0
    read_timeout_s: float = 30.0
    #: The caller stops reading past this. A transport may use it to refuse
    #: early, but enforcement is the caller's and is checked as such.
    max_bytes: int = 20 * 1024 * 1024


@dataclass
class Response:
    status: int
    headers: Mapping[str, str] = field(default_factory=dict)
    #: Body chunks. Not read at all for a status whose body we discard.
    chunks: Iterable[bytes] = ()
    url: str = ""

    def close(self) -> None:
        close = getattr(self.chunks, "close", None)
        if callable(close):
            close()

    def header(self, name: str) -> str | None:
        lowered = name.lower()
        for key, value in self.headers.items():
            if str(key).lower() == lowered:
                return str(value)
        return None


class Transport(Protocol):
    def send(self, request: Request) -> Response:  # pragma: no cover - protocol
        ...


class RequestsTransport:
    """The real transport. Never follows a redirect: host policy decides that."""

    def __init__(self, session: object | None = None) -> None:
        self._session = session

    def send(self, request: Request) -> Response:
        import requests
        from requests import exceptions as requests_exceptions

        from .redaction import redact_url

        session = self._session
        if session is None:
            session = requests.Session()
            self._session = session
        try:
            response = session.request(
                request.method,
                request.url,
                headers=dict(request.headers),
                timeout=(request.connect_timeout_s, request.read_timeout_s),
                allow_redirects=False,
                stream=True,
            )
        except requests_exceptions.Timeout as error:
            raise TransportTimeout("timeout for %s (%s)" % (
                redact_url(request.url), type(error).__name__)) from None
        except requests_exceptions.RequestException as error:
            raise TransportConnectionError("connection failed for %s (%s)" % (
                redact_url(request.url), type(error).__name__)) from None

        return Response(
            status=int(response.status_code),
            headers=dict(response.headers),
            chunks=_guarded_chunks(response),
            url=request.url,
        )


def _guarded_chunks(response: object) -> Iterator[bytes]:
    from requests import exceptions as requests_exceptions

    try:
        for chunk in response.iter_content(chunk_size=CHUNK_BYTES):  # type: ignore[attr-defined]
            if chunk:
                yield chunk
    except requests_exceptions.Timeout:
        raise TransportTimeout("timeout while reading the response body") from None
    except requests_exceptions.RequestException as error:
        raise TransportConnectionError(
            "connection lost while reading the response body (%s)"
            % type(error).__name__) from None
    finally:
        close = getattr(response, "close", None)
        if callable(close):
            close()
