"""Explicit host policy (P03-T02).

interfaces.md says to "follow only approved provider/link hosts". That is an
allow list, so the default here is :meth:`HostPolicy.deny_all`: no host is
approved until a capability manifest for it has been accepted (P03-T01 has not
chosen a provider yet). An unapproved host is ``unsupported_access``, never a
quiet attempt.

The policy is re-applied to every redirect target, so an approved host cannot
hand acquisition off to an unapproved one.
"""

from __future__ import annotations

import ipaddress
from dataclasses import dataclass, field
from typing import Iterable
from urllib.parse import urlsplit, urlunsplit

from .redaction import redact_url

#: Only these schemes can ever be approved. ``http`` has to be requested
#: explicitly per rule, and exists for a loopback stub, not for a provider.
SUPPORTED_SCHEMES = ("https", "http")

DEFAULT_PORTS = {"https": 443, "http": 80}

#: Percent-encoded dot segments. A path spelling one is refused rather than
#: guessed at: the policy and the HTTP client would otherwise disagree about
#: which path was approved.
ENCODED_DOT_SEGMENTS = ("%2e", "%2E")


class PolicyRefusal(Exception):
    """A URL the policy refuses. Carries the reason, already redacted."""

    def __init__(self, reason: str, url: str) -> None:
        self.reason = reason
        self.url = redact_url(url)
        super().__init__("%s: %s" % (reason, self.url))


@dataclass(frozen=True)
class HostRule:
    """One approved host.

    ``path_prefixes`` empty means any path on that host. A rule naming
    ``scheme="http"`` is accepted only because an offline loopback stub needs
    it; a provider rule must be https.
    """

    host: str
    scheme: str = "https"
    port: int | None = None
    path_prefixes: tuple[str, ...] = ()
    include_subdomains: bool = False
    #: Free text for the worklog: which manifest approved this host.
    approved_by: str = ""

    def __post_init__(self) -> None:
        if self.scheme not in SUPPORTED_SCHEMES:
            raise ValueError("unsupported scheme %r" % (self.scheme,))
        if not self.host:
            raise ValueError("a host rule needs a host")
        object.__setattr__(self, "host", self.host.lower().rstrip("."))

    def matches_host(self, host: str) -> bool:
        if host == self.host:
            return True
        return self.include_subdomains and host.endswith("." + self.host)

    def matches_path(self, path: str) -> bool:
        if not self.path_prefixes:
            return True
        return any(path.startswith(prefix) for prefix in self.path_prefixes)


@dataclass(frozen=True)
class HostPolicy:
    rules: tuple[HostRule, ...] = field(default_factory=tuple)

    @classmethod
    def deny_all(cls) -> "HostPolicy":
        """The shipped default: nothing is approved."""
        return cls(())

    @classmethod
    def of(cls, rules: Iterable[HostRule]) -> "HostPolicy":
        return cls(tuple(rules))

    @property
    def allowed_hosts(self) -> tuple[str, ...]:
        return tuple(sorted(rule.host for rule in self.rules))

    def check(self, url: str) -> str:
        """Return the normalized URL, or raise :class:`PolicyRefusal`.

        Refused: a URL carrying credentials, an unsupported scheme, a bare IP
        literal, a host that is not approved, a non-default port the rule did
        not declare, a percent-encoded dot segment, and a path outside the
        rule's prefixes.

        The returned URL is the one the caller must send. Dot segments are
        removed here, so the path the policy approved is the path that travels:
        a rule allowing ``/approved/`` used to accept ``/approved/../blocked``,
        which any HTTP client then resolves to ``/blocked``.
        """
        if not isinstance(url, str) or not url.strip():
            raise PolicyRefusal("empty url", url or "")
        parts = urlsplit(url.strip())
        if parts.scheme.lower() not in SUPPORTED_SCHEMES:
            raise PolicyRefusal("scheme %r is not supported" % parts.scheme, url)
        if parts.username or parts.password:
            raise PolicyRefusal("url carries credentials", url)
        host = (parts.hostname or "").lower().rstrip(".")
        if not host:
            raise PolicyRefusal("url has no host", url)
        try:
            port = parts.port
        except ValueError:
            raise PolicyRefusal("url has an invalid port", url) from None

        raw_path = parts.path or "/"
        if any(token in raw_path for token in ENCODED_DOT_SEGMENTS):
            raise PolicyRefusal(
                "path carries a percent-encoded dot segment", url)
        path = remove_dot_segments(raw_path)

        if not self.rules:
            raise PolicyRefusal(
                "no host is approved for acquisition; the host allow list is "
                "empty until a capability manifest is accepted", url)

        host_matched = False
        for rule in self.rules:
            if not rule.matches_host(host):
                continue
            host_matched = True
            if parts.scheme.lower() != rule.scheme:
                continue
            expected = rule.port or DEFAULT_PORTS[rule.scheme]
            if (port or DEFAULT_PORTS[rule.scheme]) != expected:
                raise PolicyRefusal(
                    "port %s is not approved for %s"
                    % (port, host), url)
            if not rule.matches_path(path):
                raise PolicyRefusal(
                    "path is outside the approved prefixes for %s" % host, url)
            return _canonical_url(parts.scheme.lower(), host, port, path,
                                  parts.query)

        if host_matched:
            raise PolicyRefusal(
                "scheme %r is not approved for %s" % (parts.scheme, host), url)

        if _is_ip_literal(host):
            raise PolicyRefusal("bare IP literal is not an approved host", url)
        raise PolicyRefusal("host %s is not on the allow list" % host, url)

    def allows(self, url: str) -> bool:
        try:
            self.check(url)
        except PolicyRefusal:
            return False
        return True


def remove_dot_segments(path: str) -> str:
    """RFC 3986 5.2.4, so the approved path is the resolved one."""
    segments = path.split("/")
    out: list[str] = []
    for index, segment in enumerate(segments):
        last = index == len(segments) - 1
        if segment == ".":
            if last:
                out.append("")
            continue
        if segment == "..":
            if len(out) > 1:
                out.pop()
            if last:
                out.append("")
            continue
        out.append(segment)
    return "/".join(out) or "/"


def _canonical_url(scheme: str, host: str, port: int | None, path: str,
                   query: str) -> str:
    netloc = "[%s]" % host if ":" in host else host
    if port is not None and port != DEFAULT_PORTS[scheme]:
        netloc = "%s:%d" % (netloc, port)
    # The fragment is dropped: it is never sent, and keeping it in the
    # approved URL would mean approving something other than the request.
    return urlunsplit((scheme, netloc, path, query, ""))


def _is_ip_literal(host: str) -> bool:
    try:
        ipaddress.ip_address(host.strip("[]"))
    except ValueError:
        return False
    return True
