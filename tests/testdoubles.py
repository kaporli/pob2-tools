"""A synthetic double for ``pob2opt.engine_worker.Worker`` (P00-T04).

It answers every call ``pob2opt.phases`` makes with canned values so the real
production control flow can be exercised without PoB. It is NOT a model of the
engine: the numbers it returns are chosen to make one data path observable, and
nothing it produces is evidence about PoE 2 mechanics or about PoB's output.

Lua is dispatched by matching a distinctive substring of the snippet the caller
sends, so a change to those snippets surfaces here as a KeyError rather than as
a silently wrong default.
"""

from __future__ import annotations

from typing import Any


class FakeWorkerError(LookupError):
    pass


class FakeWorker:
    def __init__(
        self,
        *,
        char_level: int = 60,
        metrics: dict[str, Any] | None = None,
        primitives: list[dict[str, Any]] | None = None,
        geometry: dict[str, Any] | None = None,
        damage_profile: dict[str, Any] | None = None,
        clip_duty: float = 1.0,
        scoped_configs: list[dict[str, Any]] | None = None,
        ascendancy: str = "FIXTURE-ASC",
        known_gems: set[str] | None = None,
    ) -> None:
        self.char_level = char_level
        self._metrics = metrics or {
            "dps": 1000.0, "full": 1000.0, "life": 2000.0,
            "str": 100, "dex": 100, "int": 100,
            "reqStr": 0, "reqDex": 0, "reqInt": 0,
            "spiritUnreserved": 0,
        }
        self._primitives = primitives or []
        self._geometry = geometry or {"tags": "attack", "proj": 1, "aoe": 0}
        self._damage_profile = damage_profile or {}
        self._clip_duty = clip_duty
        self._scoped = scoped_configs or []
        self._ascendancy = ascendancy
        self._known_gems = known_gems
        self._next_group = 1

        # Observable history, for assertions about ordering and side effects.
        self.calls: list[tuple[str, Any]] = []
        self.configs_set: dict[str, Any] = {}
        self.groups: dict[int, str] = {}

    # -- recording ----------------------------------------------------------

    def _record(self, name: str, payload: Any = None):
        self.calls.append((name, payload))

    @property
    def call_names(self) -> list[str]:
        return [name for name, _ in self.calls]

    # -- worker surface -----------------------------------------------------

    def reset(self):
        self._record("reset")

    def lua(self, code: str):
        self._record("lua", code)
        if "OPT_quest_bonuses" in code:
            return True
        if "OPT_primitives" in code:
            return [dict(p) for p in self._primitives]
        if "boltCount" in code:
            return {"duty": self._clip_duty}
        if "OPT_damage_profile" in code:
            return dict(self._damage_profile)
        if "OPT_geometry" in code:
            return dict(self._geometry)
        if "socketGroupList" in code and "enabled = false" in code:
            return True
        raise FakeWorkerError("FakeWorker has no canned answer for: " + code.strip()[:120])

    def clear_slot(self, slot: str):
        self._record("clear_slot", slot)
        return True

    def equip(self, raw: str, slot: str):
        self._record("equip", (slot, raw.splitlines()[1] if "\n" in raw else raw))
        return {"ok": True, "id": 1}

    def best_base(self, type_name: str):
        self._record("best_base", type_name)
        return "FIXTURE " + type_name

    def add_group(self, gem: str, quality: int = 0, full_dps: bool = True):
        self._record("add_group", gem)
        if self._known_gems is not None and gem not in self._known_gems:
            return None
        index = self._next_group
        self._next_group += 1
        self.groups[index] = gem
        return index

    def remove_group(self, gi: int):
        self._record("remove_group", gi)
        self.groups.pop(gi, None)
        return True

    def set_main(self, gi: int, skill: int = 1):
        self._record("set_main", gi)
        return True

    def scoped_configs(self):
        self._record("scoped_configs")
        return [dict(e) for e in self._scoped]

    def set_config(self, var: str, value):
        self._record("set_config", (var, value))
        self.configs_set[var] = value
        return True

    def support_greedy(self, gi: int, sockets: int):
        self._record("support_greedy", (gi, sockets))
        return []

    def optimize_tree(self, points: int, asc_points: int, swap_rounds: int = 12):
        self._record("optimize_tree", (points, asc_points, swap_rounds))
        return {"ascendancy": self._ascendancy, "points": points}

    def metrics(self):
        self._record("metrics")
        return dict(self._metrics)

    def save_xml(self):
        self._record("save_xml")
        return "<PathOfBuilding2><!-- fixture --></PathOfBuilding2>"
