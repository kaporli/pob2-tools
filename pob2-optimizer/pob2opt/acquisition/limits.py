"""Request, size and attempt limits (P03-T02).

The defaults are the ones interfaces.md fixes: 10-second connect, 30-second
read, 20 MiB, at most three attempts for classified transient failures. The
same 20 MiB bound caps an expanded build code.

"Provider-imposed stricter limits take precedence" is implemented as
:meth:`Limits.tightened_by`, which takes the minimum of each bound and the
maximum of the pacing interval. A provider override can therefore only make
acquisition more cautious: asking for a 60-second read or a fourth attempt
changes nothing.
"""

from __future__ import annotations

from dataclasses import dataclass, replace

CONNECT_TIMEOUT_S = 10.0
READ_TIMEOUT_S = 30.0
MAX_BYTES = 20 * 1024 * 1024
MAX_ATTEMPTS = 3
MAX_REDIRECTS = 3
#: The longest advertised delay this process will wait out inline. A longer one
#: is scheduled, not truncated (see scheduling.py).
MAX_INLINE_WAIT_S = 30.0


@dataclass(frozen=True)
class Limits:
    connect_timeout_s: float = CONNECT_TIMEOUT_S
    read_timeout_s: float = READ_TIMEOUT_S
    max_bytes: int = MAX_BYTES
    max_attempts: int = MAX_ATTEMPTS
    max_redirects: int = MAX_REDIRECTS
    max_inline_wait_s: float = MAX_INLINE_WAIT_S
    #: Minimum spacing between two requests to the same provider.
    min_interval_s: float = 0.0

    def __post_init__(self) -> None:
        for name in ("connect_timeout_s", "read_timeout_s"):
            if getattr(self, name) <= 0:
                raise ValueError("%s must be positive" % name)
        if self.max_bytes <= 0:
            raise ValueError("max_bytes must be positive")
        if self.max_attempts < 1:
            raise ValueError("max_attempts must be at least 1")
        if self.max_redirects < 0:
            raise ValueError("max_redirects cannot be negative")
        if self.min_interval_s < 0:
            raise ValueError("min_interval_s cannot be negative")

    def tightened_by(self, other: "ProviderLimits | None") -> "Limits":
        if other is None:
            return self
        return replace(
            self,
            connect_timeout_s=_min(self.connect_timeout_s, other.connect_timeout_s),
            read_timeout_s=_min(self.read_timeout_s, other.read_timeout_s),
            max_bytes=int(_min(self.max_bytes, other.max_bytes)),
            max_attempts=int(_min(self.max_attempts, other.max_attempts)),
            max_redirects=int(_min(self.max_redirects, other.max_redirects)),
            max_inline_wait_s=_min(self.max_inline_wait_s, other.max_inline_wait_s),
            min_interval_s=max(self.min_interval_s, other.min_interval_s or 0.0),
        )


@dataclass(frozen=True)
class ProviderLimits:
    """What one provider's manifest says about its own limits.

    Every bound is optional and can only tighten. ``min_interval_s`` is the
    exception by direction, not by kind: a longer gap between requests is the
    more cautious choice, so the larger value wins.
    """

    connect_timeout_s: float | None = None
    read_timeout_s: float | None = None
    max_bytes: int | None = None
    max_attempts: int | None = None
    max_redirects: int | None = None
    max_inline_wait_s: float | None = None
    min_interval_s: float = 0.0
    #: Free text: which manifest stated these.
    evidence: str = ""


def _min(default: float, override: float | None) -> float:
    if override is None:
        return default
    return min(default, override)
