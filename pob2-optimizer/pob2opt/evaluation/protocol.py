"""The parent/worker wire contract and the records it carries (P02-T01).

The wire itself is plain JSON-able dicts. The parent turns them into the frozen
dataclasses below; a synthetic worker therefore needs no import of this module
and no PoB runtime, which is what keeps the offline lane offline.

Units and semantic ownership live in ``primitives.py`` (P02-T04). A snapshot
reports them through ``declared()`` and reports everything the engine did not
supply through ``gaps()``; a raw value is still available, but reading one
without its declaration is now a choice the caller makes explicitly.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Any, Mapping

from ..domain.enums import Fidelity
from .primitives import (SEMANTICS_OWNER, SEMANTICS_VERSION, DeclaredPrimitive,
                         PrimitiveGap, declare)

#: Bumped whenever the adapter changes what it asks the engine for, or how it
#: interprets the answer. Part of the evaluation cache identity.
#:
#: Not named after one task. P02-T02, T03 and T04 each bumped it on their own
#: branch, so no single task's string describes the integrated adapter; a
#: cached result stamped "p02-t03.0" would claim an adapter that never ran.
#: Bump this whenever any of them changes again.
#: p02-t02.0 added the read-only catalog operation. p02-t03.0 adds the
#: read-only legality-state operation. The primitive path is unchanged in
#: both, but the adapter can ask the engine for something new, which is what
#: this string is for. p02.2 (P02-T02.1) widens the gem and granted-skill
#: catalog rows: weapon restrictions, skill type names, support type
#: expressions, costs, stat sets and PoB's own static support matches.
ADAPTER_VERSION = "p02.2"

#: Owner of primitive units, included effects and excluded effects.
PRIMITIVE_SEMANTICS_OWNER = SEMANTICS_OWNER

#: Default hard memory limit per worker (P02-T01.1). A worker above it is
#: killed and the request fails with ``EngineMemoryLimit``.
MEMORY_LIMIT_BYTES = 3 * 2**30
#: Default planned-replacement threshold, checked between requests. A worker
#: above it finishes its current request and is then replaced.
RECYCLE_AFTER_BYTES = 2 * 2**30
#: Unplanned worker losses in a row before the adapter stops replacing.
MAX_CONSECUTIVE_FAILURES = 3
#: How often a busy worker's memory is sampled.
MEMORY_POLL_S = 0.1

OP_DESCRIBE = "describe"
OP_CREATE_BLANK_BUILD = "create_blank_build"
OP_LOAD_EXACT_BUILD = "load_exact_build"
OP_PRIMITIVES = "primitives"
OP_CATALOG_PAGE = "catalog_page"
OP_LEGALITY_STATE = "legality_state"
OP_CYCLE_INPUTS = "cycle_inputs"
OP_PARSE_SUPPORT = "parse_support"
OP_SHUTDOWN = "shutdown"

OPERATIONS = (OP_DESCRIBE, OP_CREATE_BLANK_BUILD, OP_LOAD_EXACT_BUILD,
              OP_PRIMITIVES, OP_CATALOG_PAGE, OP_LEGALITY_STATE, OP_CYCLE_INPUTS,
              OP_PARSE_SUPPORT, OP_SHUTDOWN)

#: The bootstrap handler behind ``OP_LEGALITY_STATE``. Read-only: it reports
#: the allocation, equipment, skills and calculated pools the engine holds and
#: decides nothing (P02-T03).
LEGALITY_STATE_HANDLER = "legality_state"

#: Fixed, read-only Lua behind ``OP_CYCLE_INPUTS`` (P07-T01). After the same
#: config and main skill handling as ``OP_PRIMITIVES`` it reports values the
#: output table does not carry: each equipped flask's ``flaskData`` scalars
#: and the main skill's duration modifiers with the Charged Staff per-stack
#: base. Callers cannot supply code; it never changes the build.
CYCLE_INPUTS_LUA = r"""
local env = build.calcsTab.mainEnv
local skill = env.player.mainSkill
local cfg = skill.skillCfg
local flasks = {}
for slotName, slot in pairs(build.itemsTab.slots) do
  local item = slot.selItemId and build.itemsTab.items[slot.selItemId]
  if item and item.flaskData and not slot.nodeId then
    local fd = {}
    for k, v in pairs(item.flaskData) do if type(v) ~= "table" then fd[k] = v end end
    flasks[slotName] = { name = item.name, base = item.baseName, flaskData = fd,
                         active = slot.active and true or false }
  end
end
return {
  main_skill = skill.activeEffect.grantedEffect.id,
  flasks = flasks,
  duration = {
    per_stack_ms_base = skill.skillModList:Sum("BASE", cfg, "ChargedStaffBuffDuration"),
    inc = skill.skillModList:Sum("INC", cfg, "Duration"),
    more = skill.skillModList:More(cfg, "Duration"),
  },
}
"""

#: Catalog tables the engine can enumerate, and the bootstrap handler for
#: each. ``passive_edges`` is absent on purpose: edges are derived from the
#: node rows rather than read twice from the tree (P02-T02).
CATALOG_HANDLERS = {
    "classes": "catalog_classes",
    "passive_nodes": "catalog_passive_nodes",
    "gems": "catalog_gems",
    "granted_skills": "catalog_granted_skills",
    "item_bases": "catalog_item_bases",
    "item_modifiers": "catalog_item_modifiers",
    "slots": "catalog_slots",
    "config_variables": "catalog_config_variables",
}

#: Not a paged table: one structured read of the upstream facts the character
#: rules are derived from.
CATALOG_RULE_SOURCES = "rule_sources"
CATALOG_RULE_SOURCES_HANDLER = "catalog_rule_sources"

#: Rows per engine request. Measured at ~80 ms and ~1.8 MB for 5000 passive
#: nodes on the pinned checkout, so this is a comfort margin, not a limit.
CATALOG_PAGE_ROWS = 2000

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

    ``source`` says where the bytes came from. ``stored_blob`` is the build's
    own immutable payload; ``caller_supplied`` is a document handed in
    directly, which nothing can trace back to the build.
    """

    build_hash: str
    xml: str
    blob_hash: str | None = None
    source: str = "caller_supplied"

    @property
    def content_hash(self) -> str:
        """SHA-256 of the document itself, which is what the engine loads."""
        return hashlib.sha256(self.xml.encode("utf-8")).hexdigest()

    @property
    def content_key(self) -> tuple[str, str]:
        """What identifies a loaded state. ``build_hash`` alone does not.

        ``build_hash`` is caller-supplied and two different documents can
        carry the same one, so caching a load on it returns the first
        document's numbers for the second document (P02-T01-R01).
        """
        return (self.build_hash, self.content_hash)


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
    #: (basename, sha256) for each helper script loaded into the Lua state.
    #: adapter_version is hand-maintained; these are the code that ran.
    helper_lua_hashes: tuple[tuple[str, str], ...]
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
    #: PoB's ``skillData.showAverage`` for the main skill, or None when the
    #: engine did not report it. It decides the unit of ``CombinedDPS``
    #: (damage per use when true, damage per second when false), so None keeps
    #: that primitive unresolved instead of guessing a factor of the use rate.
    main_skill_show_average: bool | None = None
    #: Which skill the outputs belong to, as PoB names it.
    main_skill: str | None = None

    @classmethod
    def from_wire(cls, payload: Mapping[str, Any]) -> "LoadedBuild":
        show_average = payload.get("mainSkillShowAverage")
        return cls(
            name=payload.get("buildName"),
            class_name=payload.get("class"),
            ascendancy=payload.get("ascendancy"),
            level=payload.get("level"),
            allocated_nodes=int(payload.get("allocatedNodes") or 0),
            equipped_items=int(payload.get("equippedItems") or 0),
            socket_groups=int(payload.get("socketGroups") or 0),
            opt_setup_called=bool(payload.get("optSetupCalled")),
            main_skill_show_average=(None if show_average is None
                                     else bool(show_average)),
            main_skill=payload.get("mainSkill"),
        )


@dataclass(frozen=True, slots=True)
class DocumentProvenance:
    """Which document produced a snapshot, and how far it can be trusted.

    ``build_matches_document`` is deliberately absent: comparing PoB's class
    name to ``BuildSpec.class_id`` needs the catalog mapping, which is
    P02-T02. Recording what was *not* verified is the honest alternative to
    implying a check that does not exist.
    """

    build_hash: str
    content_hash: str
    blob_hash: str | None
    source: str
    #: False when the worker already held this exact document and state.
    reloaded: bool
    unverified: tuple[str, ...] = (
        "the loaded character was not cross-checked against the BuildSpec; "
        "that needs the catalog mapping owned by P02-T02",)

    @classmethod
    def of(cls, document: BuildDocument, *, reloaded: bool) -> "DocumentProvenance":
        return cls(build_hash=document.build_hash,
                   content_hash=document.content_hash,
                   blob_hash=document.blob_hash, source=document.source,
                   reloaded=reloaded)


@dataclass(frozen=True, slots=True)
class PrimitiveSnapshot:
    """Raw engine outputs plus the provenance needed to trust or discard them."""

    build_hash: str
    values: Mapping[str, Any]
    stat_keys: tuple[str, ...]
    identity: EngineIdentity
    state_applied: Mapping[str, Any]
    loaded: LoadedBuild
    document: DocumentProvenance
    #: Total evaluation allowance, excluding separately bounded worker startup
    #: and timeout cleanup. Loading, primitives and identity share this budget.
    timeout_s: float
    #: Remaining evaluation budget when loading began, or None without a load.
    #: This is part of timeout_s, not an additional allowance.
    load_timeout_s: float | None
    duration_ms: int
    #: Units, included effects and excluded effects come from
    #: ``pob2opt.evaluation.primitives``; this names its owner and version.
    semantics_owner: str = PRIMITIVE_SEMANTICS_OWNER
    semantics_status: str = "declared"
    semantics_version: str = SEMANTICS_VERSION

    def numeric(self) -> dict[str, float]:
        return {k: float(v) for k, v in self.values.items()
                if isinstance(v, (int, float)) and not isinstance(v, bool)}

    def declared(self) -> dict[str, DeclaredPrimitive]:
        """Every primitive this snapshot can supply, with its unit."""
        return self._split()[0]

    def gaps(self) -> tuple[PrimitiveGap, ...]:
        """Every primitive it cannot. A gap is never replaced by a constant."""
        return self._split()[1]

    def primitive(self, primitive_id: str) -> DeclaredPrimitive | None:
        """One declared primitive, or None. None means missing, not zero."""
        return self.declared().get(primitive_id)

    def _split(self):
        return declare(self.values,
                       show_average=self.loaded.main_skill_show_average)
