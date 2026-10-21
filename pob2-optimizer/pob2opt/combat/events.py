"""Deterministic event loop (P07-T01).

Time is integer microseconds. The queue orders events by
``(time, phase, insertion_id)``; at one timestamp expirations run first, then
scheduled state changes, completed actions and impacts, periodic effects,
and policy decisions last. Buff intervals are half-open ``[start, end)``.
Events at exactly the duration limit are processed, then the loop stops
without another policy decision. The loop refuses more than ``max_events``
events: hitting the bound is a resource-limit error, never a result.
"""

from __future__ import annotations

import heapq
from dataclasses import dataclass, field
from typing import Any, Callable

EXPIRE, STATE, IMPACT, PERIODIC, DECIDE = range(5)
PHASE_NAMES = ("expire", "state", "impact", "periodic", "decide")

US_PER_S = 1_000_000
DEFAULT_MAX_EVENTS = 500_000


def to_us(seconds: float) -> int:
    if seconds < 0:
        raise ValueError("negative duration %r" % seconds)
    return int(round(seconds * US_PER_S))


class EventLimitExceeded(RuntimeError):
    """The scenario produced more events than its bound. Not a result."""


@dataclass(order=True)
class Event:
    time_us: int
    phase: int
    insertion_id: int
    kind: str = field(compare=False)
    payload: Any = field(compare=False, default=None)


class EventLoop:
    def __init__(self, limit_us: int, *, max_events: int = DEFAULT_MAX_EVENTS):
        self.limit_us = limit_us
        self.max_events = max_events
        self.now_us = 0
        self._queue: list[Event] = []
        self._next_id = 0
        self.processed = 0

    def schedule(self, time_us: int, phase: int, kind: str, payload: Any = None) -> Event:
        if time_us < self.now_us:
            raise ValueError("event %s at %d us is before now %d us" % (kind, time_us, self.now_us))
        event = Event(time_us, phase, self._next_id, kind, payload)
        self._next_id += 1
        heapq.heappush(self._queue, event)
        return event

    def run(self, handle: Callable[[Event], None]) -> None:
        while self._queue:
            event = heapq.heappop(self._queue)
            if event.time_us > self.limit_us:
                break
            if event.time_us == self.limit_us and event.phase == DECIDE:
                # Terminate at the limit without another policy decision.
                continue
            self.processed += 1
            if self.processed > self.max_events:
                raise EventLimitExceeded("more than %d events before %d us"
                                         % (self.max_events, self.limit_us))
            self.now_us = event.time_us
            handle(event)
