"""Mana pool, regeneration and one mana flask (P07-T02).

Mana regenerates continuously at PoB's ``ManaRegenRecovery`` and is capped at
the pool. A flask use restores ``instantPerc`` of its total at once and the
rest evenly over its duration; it costs ``chargesUsed`` charges, which return
at ``gainBase`` per second up to ``chargesMax``. A flask use takes no action
time. There are no kill charges on the benchmark.

Flask policy (protocol choice, P09-T01.2): start with full charges; never use
the flask while it is still recovering; use it when its whole recovery fits
under the pool or the next cost is unaffordable.

Values are piecewise linear between events, so they are computed exactly
rather than stepped.
"""

from __future__ import annotations

from dataclasses import dataclass

from .events import US_PER_S
from .values import FlaskValues


@dataclass
class ManaState:
    pool: float
    regen_per_s: float
    flask: FlaskValues | None
    mana: float = 0.0
    charges: float = 0.0
    flask_until_us: int = 0
    flask_rate_per_s: float = 0.0
    t_us: int = 0
    spent: float = 0.0
    flask_mana_raw: float = 0.0
    flask_uses: int = 0
    lowest: float = 0.0
    first_deficit_us: int | None = None

    @classmethod
    def start(cls, pool: float, regen_per_s: float, flask: FlaskValues | None) -> "ManaState":
        return cls(pool=pool, regen_per_s=regen_per_s, flask=flask, mana=pool,
                   charges=flask.charges_max if flask else 0.0, lowest=pool)

    # -- time ---------------------------------------------------------------

    def advance(self, to_us: int) -> None:
        if to_us < self.t_us:
            raise ValueError("mana cannot move back in time")
        while self.t_us < to_us:
            end = to_us
            if self.t_us < self.flask_until_us < end:
                end = self.flask_until_us
            dt = (end - self.t_us) / US_PER_S
            rate = self.regen_per_s
            if self.t_us < self.flask_until_us:
                rate += self.flask_rate_per_s
                self.flask_mana_raw += self.flask_rate_per_s * dt
            if self.mana < self.pool:
                self.mana = min(self.pool, self.mana + rate * dt)
            if self.flask is not None:
                self.charges = min(self.flask.charges_max,
                                   self.charges + self.flask.charges_per_s * dt)
            self.t_us = end

    def flask_ready_us(self) -> int | None:
        """Earliest time the flask can be used, or None without a flask."""
        f = self.flask
        if f is None or f.charges_used <= 0:
            return None
        ready = max(self.t_us, self.flask_until_us)
        missing = f.charges_used - self.charges
        if missing > 1e-12:
            if f.charges_per_s <= 0:
                return None
            ready = max(ready, self.t_us + _ceil_us(missing / f.charges_per_s))
        return ready

    def maybe_flask(self, next_cost: float) -> bool:
        f = self.flask
        if f is None or self.t_us < self.flask_until_us or self.charges + 1e-9 < f.charges_used:
            return False
        if self.mana + f.mana_total <= self.pool or self.mana < next_cost:
            self.charges -= f.charges_used
            instant = f.mana_total * f.instant_percent / 100.0
            self.mana = min(self.pool, self.mana + instant)
            self.flask_mana_raw += instant
            rest = f.mana_total - instant
            if f.duration_s > 0 and rest > 0:
                self.flask_rate_per_s = rest / f.duration_s
                self.flask_until_us = self.t_us + int(round(f.duration_s * US_PER_S))
            self.flask_uses += 1
            return True
        return False

    def time_to_afford_us(self, cost: float) -> int | None:
        """Microseconds until ``cost`` is affordable at current rates, ignoring
        a future flask use. None if it never is (pool below cost, no regen)."""
        if self.mana >= cost:
            return 0
        if cost > self.pool:
            return None
        mana, t = self.mana, self.t_us
        if t < self.flask_until_us:
            rate = self.regen_per_s + self.flask_rate_per_s
            span = (self.flask_until_us - t) / US_PER_S
            if rate > 0 and mana + rate * span >= cost:
                return _ceil_us((cost - mana) / rate)
            mana += rate * span
            t = self.flask_until_us
        if self.regen_per_s <= 0:
            return None
        return (t - self.t_us) + _ceil_us((cost - mana) / self.regen_per_s)

    def pay(self, cost: float) -> None:
        self.mana -= cost
        self.spent += cost
        if self.mana < self.lowest:
            self.lowest = self.mana
        if self.mana < -1e-9 and self.first_deficit_us is None:
            self.first_deficit_us = self.t_us


def _ceil_us(seconds: float) -> int:
    us = seconds * US_PER_S
    whole = int(us)
    return whole if us - whole < 1e-6 else whole + 1
