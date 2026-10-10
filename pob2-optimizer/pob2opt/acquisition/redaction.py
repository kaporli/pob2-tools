"""Credential redaction for stored URLs, logs and diagnostics (P03-T02).

contracts.md requires that a failed acquisition keeps "redacted diagnostics",
and the task requires that no credential material reaches a blob, a log line or
a stored URL. Two rules make that checkable instead of aspirational:

* A URL loses its userinfo and its fragment, and every query value is replaced
  unless its parameter name is on :data:`SAFE_QUERY_KEYS`. An allow list is the
  only workable direction here: a deny list cannot keep up with whatever a
  provider decides to call its token this year.
* A header value is replaced unless its name is on :data:`SAFE_HEADERS`. Only
  the name survives, so a diagnostic can still say which header was sent.

The redacted URL is what gets stored and logged. The request still travels with
whatever the caller supplied, so redaction never weakens the actual call.
"""

from __future__ import annotations

from typing import Iterable, Mapping
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

#: The replacement text. Deliberately not empty: a reader must be able to see
#: that a value existed and was removed.
REDACTED = "REDACTED"

#: Query parameters kept verbatim. These address a document; none of them
#: authenticates anything.
SAFE_QUERY_KEYS = frozenset({
    "after", "before", "build", "class", "cursor", "format", "id", "lang",
    "league", "limit", "locale", "offset", "order", "page", "page_size",
    "per_page", "realm", "size", "slug", "sort", "start", "version",
})

#: Request headers kept verbatim. Everything else keeps its name only.
SAFE_HEADERS = frozenset({
    "accept", "accept-encoding", "accept-language", "cache-control",
    "content-length", "content-type", "etag", "if-modified-since",
    "if-none-match", "last-modified", "retry-after", "user-agent",
})


def redact_url(url: str) -> str:
    """Return ``url`` with userinfo, fragment and unsafe query values removed.

    A value that cannot be parsed as a URL is returned as the literal
    ``REDACTED``: an unparseable string is exactly the case where we cannot
    tell whether it carries a secret.
    """
    if not isinstance(url, str) or not url:
        return REDACTED
    try:
        parts = urlsplit(url)
    except ValueError:
        return REDACTED

    netloc = parts.hostname or ""
    if ":" in netloc:  # IPv6 literal
        netloc = "[%s]" % netloc
    try:
        port = parts.port
    except ValueError:
        return REDACTED
    if port is not None:
        netloc = "%s:%d" % (netloc, port)
    if parts.username or parts.password:
        # The credential is gone, but the fact that one was supplied is not.
        netloc = "%s@%s" % (REDACTED, netloc)

    query = urlencode([
        (key, value if key.lower() in SAFE_QUERY_KEYS else REDACTED)
        for key, value in parse_qsl(parts.query, keep_blank_values=True)
    ])
    return urlunsplit((parts.scheme, netloc, parts.path, query, ""))


def has_credentials(url: str) -> bool:
    """True when the URL itself carries userinfo."""
    try:
        parts = urlsplit(url)
    except ValueError:
        return False
    return bool(parts.username or parts.password)


def redact_headers(headers: Mapping[str, str] | None) -> dict[str, str]:
    """Keep every header name; keep a value only when the name is safe."""
    if not headers:
        return {}
    return {
        str(name): (str(value) if str(name).lower() in SAFE_HEADERS else REDACTED)
        for name, value in headers.items()
    }


def header_names(headers: Mapping[str, str] | None) -> list[str]:
    return sorted(str(name) for name in (headers or {}))


def redact_diagnostic(text: str, *, secrets: Iterable[str] = ()) -> str:
    """Last line of defence for a free-form message.

    Diagnostics are assembled from redacted parts already. This removes any
    literal secret a caller knows about and bounds the length, so a response
    body can never be smuggled into a record through an error message.
    """
    out = text
    for secret in secrets:
        if secret:
            out = out.replace(secret, REDACTED)
    out = " ".join(out.split())
    return out[:500]
