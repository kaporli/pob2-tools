"""Offline inputs to coverage analysis (P06-T02).

Everything here reads files; nothing starts the engine. The engine's own
parse verdicts arrive as a JSON file written by
``scripts/p06_seed_engine_mod_support.py`` and are optional: without them,
item and passive parse support is reported as missing data, never assumed.
"""

from __future__ import annotations

import hashlib
import json
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping

from ..domain.codec import from_jsonable
from ..domain.records import DataGap


@dataclass(frozen=True)
class GemFacts:
    skill_id: str
    name: str
    enabled: bool
    support: bool


@dataclass(frozen=True)
class GroupFacts:
    index: int
    enabled: bool
    slot: str | None
    #: Weapon sets the group is bound to (PoB ``set1``/``set2``).
    sets: frozenset[int]
    gems: tuple[GemFacts, ...]

    @property
    def active_skills(self) -> tuple[GemFacts, ...]:
        return tuple(g for g in self.gems if not g.support and g.enabled)

    @property
    def supports(self) -> tuple[GemFacts, ...]:
        return tuple(g for g in self.gems if g.support and g.enabled)


@dataclass(frozen=True)
class ItemFacts:
    slot: str
    item_id: str
    name: str


@dataclass(frozen=True)
class EngineState:
    pob_commit: str | None
    pob_dirty: bool | None


@dataclass(frozen=True)
class BuildFacts:
    build_id: str
    class_name: str | None
    ascendancy: str | None
    level: int | None
    declared_patch: str | None
    main_group: int | None
    groups: tuple[GroupFacts, ...]
    passive_ids: tuple[str, ...]
    items: tuple[ItemFacts, ...]
    #: ``Input`` entries the document states. Placeholders are not inputs.
    config_explicit: Mapping[str, Any]
    #: The engine's effective config input when captured; None otherwise.
    config_effective: Mapping[str, Any] | None = None
    engine: EngineState | None = None


def _bool(value: str | None) -> bool:
    return value == "true"


def _input_value(node: ET.Element) -> Any:
    for key in ("boolean", "number", "string"):
        if key in node.attrib:
            raw = node.attrib[key]
            if key == "boolean":
                return raw == "true"
            if key == "number":
                return float(raw) if "." in raw else int(raw)
            return raw
    return None


def build_facts_from_pob_xml(xml: str | bytes, *,
                             config_effective: Mapping[str, Any] | None = None,
                             engine: EngineState | None = None) -> BuildFacts:
    raw = xml.encode("utf-8") if isinstance(xml, str) else xml
    root = ET.fromstring(raw)
    build = root.find("Build")
    skills = root.find("Skills")
    groups = []
    skill_set = skills.find("SkillSet") if skills is not None else None
    container = skill_set if skill_set is not None else skills
    for index, skill in enumerate(container.iter("Skill") if container is not None else (), 1):
        sets = frozenset(n for n in (1, 2) if skill.get("set%d" % n, "true") == "true")
        gems = tuple(GemFacts(
            skill_id=g.get("skillId") or "",
            name=g.get("nameSpec") or "",
            enabled=_bool(g.get("enabled")),
            support=(g.get("skillId") or "").startswith("Support"))
            for g in skill.iter("Gem"))
        groups.append(GroupFacts(index=index, enabled=_bool(skill.get("enabled")),
                                 slot=skill.get("slot"), sets=sets, gems=gems))
    spec = root.find("Tree/Spec")
    nodes = spec.get("nodes", "") if spec is not None else ""
    passive_ids = tuple(sorted({n for n in nodes.split(",") if n}, key=int))
    items_by_id = {i.get("id"): i for i in root.iter("Item")}
    items = []
    item_set = root.find("Items/ItemSet")
    for slot in (item_set.iter("Slot") if item_set is not None else ()):
        item_id = slot.get("itemId", "0")
        if item_id in ("0", "") or item_id not in items_by_id:
            continue
        text = (items_by_id[item_id].text or "").strip().splitlines()
        name = ", ".join(line.strip() for line in text[1:3]) if len(text) > 2 else ""
        items.append(ItemFacts(slot=slot.get("name", ""), item_id=item_id, name=name))
    config_set = root.find("Config/ConfigSet")
    if config_set is None:
        config_set = root.find("Config")
    explicit = {}
    if config_set is not None:
        for node in config_set.findall("Input"):
            explicit[node.get("name")] = _input_value(node)
    main = build.get("mainSocketGroup") if build is not None else None
    level = build.get("level") if build is not None else None
    return BuildFacts(
        build_id="sha256:" + hashlib.sha256(raw).hexdigest(),
        class_name=build.get("className") if build is not None else None,
        ascendancy=build.get("ascendClassName") if build is not None else None,
        level=int(level) if level else None,
        declared_patch=build.get("targetVersion") if build is not None else None,
        main_group=int(main) if main else None,
        groups=tuple(groups), passive_ids=passive_ids, items=tuple(items),
        config_explicit=explicit, config_effective=config_effective, engine=engine)


# ------------------------------------------------------- engine parse data ===

@dataclass(frozen=True)
class LineSupport:
    line: str
    parsed: bool
    extra: str | None
    block: str | None = None


@dataclass(frozen=True)
class ModSupport:
    """PoB's per-line parse verdicts for one build (see the probe script)."""

    source: str
    pob_commit: str
    items: Mapping[str, tuple[LineSupport, ...]]
    nodes: Mapping[str, tuple[LineSupport, ...]]
    #: Config rows ``{var, shown, input, placeholder}``; None when not captured.
    config: tuple[Mapping[str, Any], ...] | None = None


def load_mod_support(path: str | Path) -> ModSupport:
    data = json.loads(Path(path).read_text(encoding="utf-8"))

    def rows(lines):
        return tuple(LineSupport(line=r["line"], parsed=bool(r["parsed"]),
                                 extra=r.get("extra"), block=r.get("block"))
                     for r in lines)

    return ModSupport(
        source=str(path).replace("\\", "/"),
        pob_commit=data["pob_commit"],
        items={e["slot"]: rows(e["lines"]) for e in data["items"]},
        nodes={str(e["id"]): rows(e["lines"]) for e in data["nodes"]},
        config=tuple(data["config"]) if "config" in data else None,
    )


# ------------------------------------------------------- PoB config options ===

@dataclass(frozen=True)
class ConfigOption:
    var: str
    type: str
    #: ``ifSkill`` and friends: key to the names or symbols it lists.
    gates: Mapping[str, tuple[str, ...]]
    default: Any = None


_VAR = re.compile(r'^\s*\{\s*var\s*=\s*"([^"]+)"\s*,\s*type\s*=\s*"([^"]+)"(.*)$')
_GATE = re.compile(r'\b(if[A-Za-z]+)\s*=\s*(\{[^}]*\}|"[^"]*"|[A-Za-z_.]+)')
_DEFAULT = re.compile(r'\bdefault(State|Index)\s*=\s*(true|false|-?[0-9.]+|"[^"]*")')


def _strings(raw: str) -> tuple[str, ...]:
    found = re.findall(r'"([^"]*)"', raw)
    if found:
        return tuple(found)
    return tuple(p.strip() for p in raw.strip("{} ").split(",") if p.strip())


def parse_config_options(source: str) -> dict[str, ConfigOption]:
    """Read option definitions from PoB's ``ConfigOptions.lua`` text.

    Only the one-line header of each option is read: its variable, type,
    gating conditions and default. ``apply`` bodies are not interpreted.
    """
    options = {}
    for line in source.splitlines():
        match = _VAR.match(line)
        if not match:
            continue
        var, kind, rest = match.groups()
        rest = rest.split("apply = function", 1)[0]
        gates = {key: _strings(value) for key, value in _GATE.findall(rest)}
        default = None
        dm = _DEFAULT.search(rest)
        if dm:
            raw = dm.group(2)
            default = (raw == "true" if raw in ("true", "false")
                       else raw.strip('"') if raw.startswith('"')
                       else float(raw) if "." in raw else int(raw))
            if dm.group(1) == "Index":
                default = ("index", default)
        options[var] = ConfigOption(var=var, type=kind, gates=gates, default=default)
    return options


def load_config_options(pob_root: str | Path) -> dict[str, ConfigOption]:
    path = Path(pob_root) / "src" / "Modules" / "ConfigOptions.lua"
    return parse_config_options(path.read_text(encoding="utf-8"))


# ------------------------------------------------------------- scenarios ===

#: Events each scenario category can supply. ``flicker_sustained_v1`` has one
#: non-dying target, no incoming damage and no kills (D07 item 4).
CATEGORY_EVENTS = {
    "dps_benchmark": frozenset(),
    "clear": frozenset({"kill", "incoming_hit", "stun_or_kill"}),
    "boss": frozenset({"incoming_hit", "stun_or_kill"}),
}


@dataclass(frozen=True)
class ScenarioFacts:
    scenario_id: str
    category: str
    events: frozenset[str]
    #: JSON pointer to the gap ids of a field whose value is unknown.
    missing_fields: Mapping[str, tuple[str, ...]]
    #: Protocol DataGaps naming this scenario, any status.
    protocol_gaps: tuple[DataGap, ...] = field(default_factory=tuple)


def load_scenarios(path: str | Path) -> dict[str, ScenarioFacts]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    gaps = [from_jsonable(DataGap, g) for g in data["data_gaps"]]
    out = {}
    for scenario in data["scenarios"]:
        sid = scenario["scenario_id"]
        category = scenario["category"]
        missing = {}
        for name, spec in scenario["fields"].items():
            if isinstance(spec, dict) and spec.get("value") is None and spec.get("gap_ids"):
                missing["/" + name] = tuple(spec["gap_ids"])
        out[sid] = ScenarioFacts(
            scenario_id=sid, category=category,
            events=CATEGORY_EVENTS.get(category, frozenset()),
            missing_fields=missing,
            protocol_gaps=tuple(g for g in gaps if sid in g.subject_ids))
    return out
