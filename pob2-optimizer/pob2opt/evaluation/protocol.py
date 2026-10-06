"""The parent/worker wire contract and the records it carries (P02-T01).

The wire itself is plain JSON-able dicts. The parent turns them into the frozen
dataclasses below; a synthetic worker therefore needs no import of this module
and no PoB runtime, which is what keeps the offline lane offline.

Nothing here declares units or semantic ownership for a primitive value. That
inventory is P02-T04; until it exists every snapshot says so, so a caller
cannot mistake a raw PoB field for a defined primitive.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

from ..domain.enums import Fidelity

#: Bumped whenever the adapter changes what it asks the engine for, or how it
#: interprets the answer. Part of the evaluation cache identity.
ADAPTER_VERSION = "p02-t01.1"

#: Owner of primitive units, included effects and excluded effects.
PRIMITIVE_SEMANTICS_OWNER = "P02-T04"

OP_DESCRIBE = "describe"
OP_CREATE_BLANK_BUILD = "create_blank_build"
OP_LOAD_EXACT_BUILD = "load_exact_build"
OP_PRIMITIVES = "primitives"
OP_SHUTDOWN = "shutdown"

OPERATIONS = (OP_DESCRIBE, OP_CREATE_BLANK_BUILD, OP_LOAD_EXACT_BUILD,
              OP_PRIMITIVES, OP_SHUTDOWN)

#: Defaults from `docs/specs/interfaces.md`. Both are configurable per adapter
#: and the value actually used is recorded on the snapshot.
SCREEN_TIMEOUT_S = 30.0
DETAILED_TIMEOUT_S = 120.0

#: A fresh PoB boot measured minutes, not seconds, on the P00 environment.
START_TIMEOUT_S = 300.0


def timeout_for(fidelity: Fidelity, screen: float = SCREEN_TIMEOUT_S,
                detailed: float = DETAILED_TIMEOUT_S) -> float:
    return screen if fidelity == Fidelity.SCREEN else detailed


@dataclass(frozen=True, slots=True)
class BuildDocument:
    """The exact build document a BuildSpec was parsed from.

    ``xml`` is the stored original, not a regeneration: P02-T05 owns writing a
    BuildSpec back out, and nothing here may pretend to do it.
    """

    build_hash: str
    xml: str
    blob_hash: str | None = None


@dataclass(frozen=True, slots=True)
class EngineState:
    """What the adapter applies to a loaded build before reading primitives.

    Deliberately small: anything that is not one of these is not applied, so a
    caller cannot believe a configuration took effect that never left Python.
    """

    config: Mapping[str, Any] = field(default_factory=dict)
    #: ``(socket group index, skill index)``, both 1-based as PoB numbers them.
    main_skill: tuple[int, int] | None = None
    stat_keys: tuple[str, ...] | None = None

    def to_wire(self) -> dict:
        return {
            "config": [[k, self.config[k]] for k in sorted(self.config)],
            "main_skill": list(self.main_skill) if self.main_skill else None,
            "stat_keys": list(self.stat_keys) if self.stat_keys else None,
        }


@dataclass(frozen=True, slots=True)
class EngineIdentity:
    """Which engine produced a value, in enough detail to invalidate a cache."""

    pob_root: str
    pob_commit: str | None
    pob_dirty_hash: str | None
    adapter_version: str
    worker_pid: int
    worker_cwd: str
    #: Incremented every time the adapter had to replace the worker process.
    generation: int

    @property
    def is_pinned(self) -> bool:
        """False when the commit is unknown or the tree is modified."""
        return bool(self.pob_commit) and self.pob_dirty_hash is None


@dataclass(frozen=True, slots=True)
class LoadedBuild:
    """What actually survived a load, counted in the engine, not assumed."""

    name: str | None
    class_name: str | None
    ascendancy: str | None
    level: int | None
    allocated_nodes: int
    equipped_items: int
    socket_groups: int
    #: True only for ``create_blank_build``. An exact load that reports True is
    #: a defect, not a configuration choice.
    opt_setup_called: bool

    @classmethod
    def from_wire(cls, payload: Mapping[str, Any]) -> "LoadedBuild":
        return cls(
            name=payload.get("buildName"),
            class_name=payload.get("class"),
            ascendancy=payload.get("ascendancy"),
            level=payload.get("level"),
            allocated_nodes=int(payload.get("allocatedNodes") or 0),
            equipped_items=int(payload.get("equippedItems") or 0),
            socket_groups=int(payload.get("socketGroups") or 0),
            opt_setup_called=bool(payload.get("optSetupCalled")),
        )


@dataclass(frozen=True, slots=True)
class PrimitiveSnapshot:
    """Raw engine outputs plus the provenance needed to trust or discard them."""

    build_hash: str
    values: Mapping[str, Any]
    stat_keys: tuple[str, ...]
    identity: EngineIdentity
    state_applied: Mapping[str, Any]
    loaded: LoadedBuild
    timeout_s: float
    duration_ms: int
    #: Until P02-T04 publishes the inventory, no value here has declared units.
    semantics_owner: str = PRIMITIVE_SEMANTICS_OWNER
    semantics_status: str = "undeclared"

    def numeric(self) -> dict[str, float]:
        return {k: float(v) for k, v in self.values.items()
                if isinstance(v, (int, float)) and not isinstance(v, bool)}
