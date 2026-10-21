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
    #: SHA-256 of the item's document text. None: identity unknown, so no
    #: parse verdict can be bound to it.
    text_sha256: str | None = None


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
    #: ``Input`` entries of the selected config set, plus any calculation
    #: overrides the caller applies. Placeholders are not inputs.
    config_explicit: Mapping[str, Any]
    #: The engine's effective config input when captured; None otherwise.
    config_effective: Mapping[str, Any] | None = None
    engine: EngineState | None = None
    #: SHA-256 of the whole document the facts were read from.
    document_hash: str | None = None
    #: Selected set per tab (``Tree`` by position, others by id).
    selection: Mapping[str, str] = field(default_factory=dict)
    #: Why a tab's set could not be selected. Each one blocks coverage.
    loadout_problems: tuple[str, ...] = ()
    #: Custom modifier blocks of the selected config set as PoB holds them
    #: after loading: ``(title, enabled, text)``, legacy ``customMods``
    #: migrated, and one empty enabled ``Default`` block when there is none.
    custom_mods: tuple[tuple[str, bool, str], ...] = ()


def active_custom_mods(blocks) -> list[tuple[str, bool, str]]:
    """Blocks PoB applies in BuildModList: enabled with nonempty text."""
    return [b for b in blocks if b[1] and b[2].strip()]


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


def item_text_hash(text: str) -> str:
    """Identity of an item's document text, line endings normalised."""
    lines = [line.rstrip() for line in text.strip().splitlines()]
    return hashlib.sha256("\n".join(lines).encode("utf-8")).hexdigest()


def select_loadout(root: ET.Element, loadout: str | None = None
                   ) -> tuple[dict[str, ET.Element], dict[str, str], list[str]]:
    """The selected set element per tab, its key, and selection problems.

    Uses the P04 rules (``evaluation/variants.py``): with ``loadout`` None the
    document's own selectors (``Tree`` by one-based position, the others by
    id, a missing selector meaning 1); otherwise the named loadout under
    PoB's linking rule. A selector naming no set or several sets, an
    ambiguous link and an unknown loadout are problems; nothing falls back
    to the first set.
    """
    from ..evaluation.support import LossCollector
    from ..evaluation.variants import (SET_TABLES, _active_selection, _loadouts,
                                       _sets)
    sets = _sets(root)
    losses = LossCollector()
    problems: list[str] = []
    if loadout is None:
        selection: dict[str, str] = {}
        for tag, _, _ in SET_TABLES:
            if tag not in sets:
                continue
            one = _active_selection(root, {tag: sets[tag]}, losses)
            if one is not None:
                selection.update(one)
    else:
        found = [sel for label, sel in _loadouts(sets, losses) if label == loadout]
        if len(found) != 1:
            problems.append("/loadout: %d loadouts are labelled %r" % (len(found), loadout))
            selection = {}
        else:
            selection = found[0]
    problems.extend("%s: %s" % (u.field_path, u.reason) for u in losses.report().unsupported)
    chosen: dict[str, ET.Element] = {}
    for tag, child_tag, _ in SET_TABLES:
        container = root.find(tag)
        if container is None:
            continue
        if tag not in sets:
            chosen[tag] = container  # a legacy flat container is its own set
            continue
        if tag not in selection:
            if not any(p.startswith("/%s" % tag) for p in problems):
                problems.append("/%s: no %s is selected" % (tag, child_tag))
            continue
        chosen[tag] = next(node for ref, node in sets[tag] if ref.key == selection[tag])
    return chosen, selection, problems


def build_facts_from_pob_xml(xml: str | bytes, *, loadout: str | None = None,
                             config_effective: Mapping[str, Any] | None = None,
                             engine: EngineState | None = None) -> BuildFacts:
    raw = xml.encode("utf-8") if isinstance(xml, str) else xml
    root = ET.fromstring(raw)
    build = root.find("Build")
    chosen, selection, problems = select_loadout(root, loadout)
    groups = []
    container = chosen.get("Skills")
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
    spec = chosen.get("Tree")
    if spec is not None and spec.tag == "Tree":
        spec = spec.find("Spec")
    nodes = spec.get("nodes", "") if spec is not None else ""
    passive_ids = tuple(sorted({n for n in nodes.split(",") if n}, key=int))
    items_by_id = {i.get("id"): i for i in root.iter("Item")}
    items = []
    item_set = chosen.get("Items")
    for slot in (item_set.iter("Slot") if item_set is not None else ()):
        item_id = slot.get("itemId", "0")
        if item_id in ("0", ""):
            continue
        if item_id not in items_by_id:
            problems.append("/Items/Slot[%s]: item %s is not in the document"
                            % (slot.get("name", ""), item_id))
            continue
        text = items_by_id[item_id].text or ""
        lines = text.strip().splitlines()
        name = ", ".join(line.strip() for line in lines[1:3]) if len(lines) > 2 else ""
        items.append(ItemFacts(slot=slot.get("name", ""), item_id=item_id, name=name,
                               text_sha256=item_text_hash(text)))
    # Jewels socketed in allocated tree nodes are equipped items too; PoB
    # names their slot "Jewel <node id>".
    sockets = spec.findall("Sockets/Socket") if spec is not None else []
    for socket in sockets:
        item_id, node_id = socket.get("itemId", "0"), socket.get("nodeId", "")
        if item_id in ("0", "") or node_id not in passive_ids:
            continue
        if item_id not in items_by_id:
            problems.append("/Tree/Spec/Sockets[%s]: item %s is not in the document"
                            % (node_id, item_id))
            continue
        text = items_by_id[item_id].text or ""
        lines = text.strip().splitlines()
        name = ", ".join(line.strip() for line in lines[1:3]) if len(lines) > 2 else ""
        items.append(ItemFacts(slot="Jewel " + node_id, item_id=item_id, name=name,
                               text_sha256=item_text_hash(text)))
    config_set = chosen.get("Config")
    explicit = {}
    blocks: list[tuple[str, bool, str]] = []
    if config_set is not None:
        for node in config_set.findall("Input"):
            explicit[node.get("name")] = _input_value(node)
        # ConfigTab:Load (src/Classes/ConfigTab.lua ~927): enabled unless the
        # attribute says otherwise, text is the element's first text node.
        for node in config_set.findall("CustomModifierBlock"):
            enabled = node.get("enabled") in ("true", None)
            text = node.text or ""
            # PoB's XML reader keeps no whitespace-only text node.
            blocks.append((node.get("title") or "Default", enabled,
                           text if text.strip() else ""))
    # PoB's legacy migration (~962): a nonempty customMods input becomes the
    # Default block when there is no block or one empty block; the input is
    # then dropped either way.
    legacy = explicit.pop("customMods", None)
    legacy = legacy if isinstance(legacy, str) else ""
    if legacy and (not blocks or (len(blocks) == 1 and not blocks[0][2])):
        blocks = [("Default", True, legacy)]
    elif not blocks:
        blocks = [("Default", True, "")]
    main = build.get("mainSocketGroup") if build is not None else None
    level = build.get("level") if build is not None else None
    digest = hashlib.sha256(raw).hexdigest()
    return BuildFacts(
        build_id="sha256:%s/%s" % (digest, ";".join(
            "%s=%s" % kv for kv in sorted(selection.items()))),
        class_name=build.get("className") if build is not None else None,
        ascendancy=build.get("ascendClassName") if build is not None else None,
        level=int(level) if level else None,
        declared_patch=build.get("targetVersion") if build is not None else None,
        main_group=int(main) if main else None,
        groups=tuple(groups), passive_ids=passive_ids, items=tuple(items),
        config_explicit=explicit, config_effective=config_effective, engine=engine,
        document_hash=digest, selection=dict(selection),
        loadout_problems=tuple(problems), custom_mods=tuple(blocks))


# ------------------------------------------------------- engine parse data ===

@dataclass(frozen=True)
class LineSupport:
    line: str
    parsed: bool
    extra: str | None
    block: str | None = None


@dataclass(frozen=True)
class CaptureBinding:
    """What a parse capture was taken from. Verified before any verdict is used.

    ``items`` maps slot to ``(item_id, text_sha256)`` as the engine had it
    equipped; ``nodes`` are the engine's allocated nodes; ``config`` the
    selected set's inputs the engine held, overrides included.
    """

    document_hash: str
    selection: Mapping[str, str]
    pob_commit: str
    pob_dirty: bool | None
    items: Mapping[str, tuple[str, str]]
    nodes: tuple[str, ...]
    config: Mapping[str, Any]
    #: The engine's custom modifier blocks for the selected set; None when
    #: the capture did not record them.
    custom_mods: tuple[tuple[str, bool, str], ...] | None = None

    def identity(self) -> dict:
        return {"document_hash": self.document_hash,
                "selection": dict(sorted(self.selection.items())),
                "pob_commit": self.pob_commit, "pob_dirty": self.pob_dirty,
                "items": {k: list(v) for k, v in sorted(self.items.items())},
                "nodes": sorted(self.nodes, key=str),
                "config": dict(sorted(self.config.items())),
                "custom_mods": None if self.custom_mods is None
                else [list(b) for b in self.custom_mods]}


@dataclass(frozen=True)
class ModSupport:
    """PoB's per-line parse verdicts for one build (see the probe script).

    A key present with an empty tuple is a verified empty line set; an
    absent key is no evidence.
    """

    source: str
    pob_commit: str
    items: Mapping[str, tuple[LineSupport, ...]]
    nodes: Mapping[str, tuple[LineSupport, ...]]
    #: Config rows ``{var, shown, input, placeholder}``; None when not captured.
    config: tuple[Mapping[str, Any], ...] | None = None
    #: None: the capture is not bound to any document, so it proves nothing.
    binding: CaptureBinding | None = None


def load_mod_support(path: str | Path) -> ModSupport:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return mod_support_from_json(data, str(path).replace("\\", "/"))


def mod_support_from_json(data: Mapping[str, Any], source: str) -> ModSupport:
    """A capture payload (``scripts/p06_seed_engine_mod_support.py`` format)."""

    def rows(lines):
        return tuple(LineSupport(line=r["line"], parsed=bool(r["parsed"]),
                                 extra=r.get("extra"), block=r.get("block"))
                     for r in lines)

    return ModSupport(
        source=source,
        pob_commit=data["pob_commit"],
        items={e["slot"]: rows(e["lines"]) for e in data["items"]},
        nodes={str(e["id"]): rows(e["lines"]) for e in data["nodes"]},
        config=tuple(data["config"]) if "config" in data else None,
        binding=_binding(data.get("binding")),
    )


def _binding(data) -> CaptureBinding | None:
    if not data:
        return None
    return CaptureBinding(
        document_hash=data["document_hash"], selection=dict(data["selection"]),
        pob_commit=data["pob_commit"], pob_dirty=data["pob_dirty"],
        items={k: tuple(v) for k, v in data["items"].items()},
        nodes=tuple(str(n) for n in data["nodes"]), config=dict(data["config"]),
        custom_mods=None if data.get("custom_mods") is None
        else tuple((t, bool(e), x) for t, e, x in data["custom_mods"]))


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

#: Scenario field to PoB config variable, for the fields that fix a target.
_RESIST_VARS = {"Fire": "enemyFireResist", "Cold": "enemyColdResist",
                "Lightning": "enemyLightningResist", "Chaos": "enemyChaosResist"}


def target_config(fields: Mapping[str, Any]) -> dict[str, Any]:
    """The PoB config values a scenario's target fields fix, exactly.

    Reads ``target_entities.identity.pob_config``, ``target_entities.level``
    and ``target_entities.defenses``. A null field fixes nothing.
    """
    def value(name):
        spec = fields.get(name)
        return spec.get("value") if isinstance(spec, dict) else None

    out: dict[str, Any] = {}
    identity = value("target_entities.identity")
    if isinstance(identity, dict):
        out.update(identity.get("pob_config") or {})
    level = value("target_entities.level")
    if isinstance(level, (int, float)) and not isinstance(level, bool):
        out["enemyLevel"] = level
    defenses = value("target_entities.defenses")
    if isinstance(defenses, dict):
        for kind, var in _RESIST_VARS.items():
            if kind in (defenses.get("resist") or {}):
                out[var] = defenses["resist"][kind]
        if "armour" in defenses:
            out["enemyArmour"] = defenses["armour"]
        if "evasion" in defenses:
            out["enemyEvasion"] = defenses["evasion"]
    return out


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
    #: PoB config variable to the exact value the scenario fixes. Only these
    #: are scenario-owned; every other applied value needs its own rule.
    target_config: Mapping[str, Any] = field(default_factory=dict)


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
            protocol_gaps=tuple(g for g in gaps if sid in g.subject_ids),
            target_config=target_config(scenario["fields"]))
    return out
