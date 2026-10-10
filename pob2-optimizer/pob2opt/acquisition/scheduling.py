"""Provider pacing and retry scheduling (P03-T02).

interfaces.md: "Respect full advertised retry delays by scheduling work later;
do not truncate them." So this module never shortens a delay. It does one of
two things:

* the delay fits inside :attr:`Limits.max_inline_wait_s`, so the full delay is
  slept and the attempt is repeated; or
* it does not fit, so nothing is slept, the attempt stops, and the result
  carries a :class:`Deferral` with the full delay and the earliest time the
  work may be retried.

Pacing is per provider: a request waits out the remainder of
``min_interval_s`` since that provider's last request.

The clock is injected. Tests use a manual clock, so an unslept wait and a
truncated wait are both visible instead of being hidden by wall time.
"""

from __future__ import annotations

import email.utils
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Protocol


class Clock(Protocol):
    def monotonic(self) -> float: ...  # pragma: no cover - protocol
    def utcnow(self) -> str: ...  # pragma: no cover - protocol
    def sleep(self, seconds: float) -> None: ...  # pragma: no cover - protocol


class SystemClock:
    def monotonic(self) -> float:
        return time.monotonic()

    def utcnow(self) -> str:
        return (datetime.now(timezone.utc)
                .strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z")

    def sleep(self, seconds: float) -> None:
        if seconds > 0:
            time.sleep(seconds)


@dataclass(frozen=True)
class Deferral:
    """Work that must be retried later, with the delay kept whole."""

    delay_s: float
    not_before: str
    reason: str

    def describe(self) -> str:
        return "retry_after=%gs not_before=%s (%s)" % (
            self.delay_s, self.not_before, self.reason)


def parse_retry_after(value: str | None, *, clock: Clock | None = None) -> float | None:
    """Seconds from a ``Retry-After`` header, or None when it is unusable.

    Both forms are accepted: delta-seconds and an HTTP date. A date in the past
    is zero, never negative.
    """
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        seconds = float(text)
    except ValueError:
        pass
    else:
        return max(0.0, seconds)
    try:
        when = email.utils.parsedate_to_datetime(text)
    except (TypeError, ValueError):
        return None
    if when is None:
        return None
    if when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)
    now = datetime.now(timezone.utc)
    if clock is not None:
        try:
            now = datetime.strptime(clock.utcnow(), "%Y-%m-%dT%H:%M:%S.%fZ").replace(
                tzinfo=timezone.utc)
        except ValueError:
            pass
    return max(0.0, (when - now).total_seconds())


class ProviderScheduler:
    """Per-provider pacing and the inline-wait decision."""

    def __init__(self, clock: Clock | None = None) -> None:
        self.clock = clock or SystemClock()
        self._last_request: dict[str, float] = {}

    def wait_for_slot(self, provider: str, min_interval_s: float) -> float:
        """Sleep out the remaining pacing interval. Returns what it slept."""
        slept = 0.0
        if min_interval_s > 0:
            previous = self._last_request.get(provider)
            if previous is not None:
                remaining = min_interval_s - (self.clock.monotonic() - previous)
                if remaining > 0:
                    self.clock.sleep(remaining)
                    slept = remaining
        self._last_request[provider] = self.clock.monotonic()
        return slept

    def plan_retry(self, *, attempt: int, advertised_delay_s: float | None,
                   max_inline_wait_s: float, reason: str) -> Deferral | None:
        """Wait the full delay inline, or return the deferral that replaces it.

        ``None`` means the wait happened and the caller should try again.
        """
        delay = (advertised_delay_s if advertised_delay_s is not None
                 else backoff_delay(attempt))
        if delay <= max_inline_wait_s:
            self.clock.sleep(delay)
            return None
        return Deferral(delay_s=delay,
                        not_before=self.plus(delay),
                        reason=reason)

    def plus(self, seconds: float) -> str:
        """``clock.utcnow()`` moved forward, in the contracts.md timestamp form."""
        try:
            now = datetime.strptime(self.clock.utcnow(), "%Y-%m-%dT%H:%M:%S.%fZ")
        except ValueError:
            now = datetime.strptime(self.clock.utcnow(), "%Y-%m-%dT%H:%M:%SZ")
        moved = now.replace(tzinfo=timezone.utc) + timedelta(seconds=seconds)
        return moved.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def backoff_delay(attempt: int) -> float:
    """1s, 2s, 4s ... for a transient failure that advertised no delay."""
    return float(2 ** max(0, attempt - 1))
