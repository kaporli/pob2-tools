"""Bound parse captures: which modifier lines the pinned engine parses (P06-T02).

``PARSE_SUPPORT_LUA`` reads, after a document is loaded, every equipped item
modifier line and every allocated passive line with PoB's parse verdict, the
applied config rows with PoB's visibility test, the selected config set's
custom modifier blocks, and the selected set ids.
``bind_capture`` checks that what the engine held equals the document's own
selection, items, nodes and inputs, and returns the capture payload with its
``binding`` (document hash, selection, engine commit and clean state, item id
and text hash per slot, nodes, config, custom modifier blocks). Coverage
verifies that binding before using any verdict.

Shared by ``scripts/p06_seed_engine_mod_support.py`` and the P07 cycle
capture, which runs the same Lua through ``EngineAdapter.parse_support``.
"""

from __future__ import annotations

from typing import Any, Mapping

from .inputs import build_facts_from_pob_xml

PARSE_SUPPORT_LUA = r"""
local out = { items = {}, nodes = {} }
local function lines(item, field)
  local rows = {}
  for _, ml in ipairs(item[field] or {}) do
    rows[#rows + 1] = {
      line = ml.line,
      parsed = (ml.modList ~= nil and #ml.modList > 0),
      extra = ml.extra and tostring(ml.extra) or nil,
    }
  end
  return rows
end
local fields = { "enchantModLines", "runeModLines", "implicitModLines",
                 "explicitModLines", "buffModLines" }
for slotName, slot in pairs(build.itemsTab.slots) do
  local item = build.itemsTab.items[slot.selItemId]
  if item then
    local entry = { slot = slotName, item_id = tostring(slot.selItemId), name = item.name,
                    base = item.baseName, lines = {} }
    for _, f in ipairs(fields) do
      for _, row in ipairs(lines(item, f)) do
        row.block = f
        entry.lines[#entry.lines + 1] = row
      end
    end
    out.items[#out.items + 1] = entry
  end
end
for id, node in pairs(build.spec.allocNodes) do
  local rows = {}
  for i, text in ipairs(node.sd or {}) do
    local mod = node.mods and node.mods[i] or nil
    rows[#rows + 1] = {
      line = text,
      parsed = (mod ~= nil and mod.list ~= nil),
      extra = (mod ~= nil and mod.extra) and tostring(mod.extra) or nil,
    }
  end
  out.nodes[#out.nodes + 1] = { id = tostring(id), name = node.dn, lines = rows }
end
local cfg = build.configTab
local set = cfg.configSets[cfg.activeConfigSetId]
out.config = {}
for var, control in pairs(cfg.varControls) do
  local shown = control.shown
  if type(shown) == "function" then shown = shown() end
  local input, placeholder = set.input[var], set.placeholder[var]
  if input ~= nil or placeholder ~= nil then
    out.config[#out.config + 1] = { var = var, shown = shown and true or false,
      input = input, placeholder = placeholder }
  end
end
out.custom_mods = {}
for _, block in ipairs(set.customModsList or {}) do
  out.custom_mods[#out.custom_mods + 1] = { title = block.title or "Default",
    enabled = block.enabled ~= false, text = block.text or "" }
end
out.selection = {
  Tree = tostring(build.treeTab.activeSpec),
  Skills = tostring(build.skillsTab.activeSkillSetId),
  Items = tostring(build.itemsTab.activeItemSetId),
  Config = tostring(cfg.activeConfigSetId),
}
return out
"""


class CaptureRefused(ValueError):
    def __init__(self, problems: list[str]):
        self.problems = problems
        super().__init__("; ".join(problems))


def _lua_list(value) -> list:
    """Lua returns an empty table as an empty mapping."""
    if isinstance(value, Mapping):
        return list(value.values())
    return list(value or [])


def bind_capture(xml: str | bytes, result: Mapping[str, Any], *, pob_commit: str | None,
                 pob_dirty: bool | None) -> dict:
    """The capture payload bound to ``xml``; refuses when the engine's state differs."""
    raw = xml.encode("utf-8") if isinstance(xml, str) else xml
    facts = build_facts_from_pob_xml(raw)
    if facts.loadout_problems:
        raise CaptureRefused(list(facts.loadout_problems))
    result = dict(result)
    for key in ("items", "nodes", "config", "custom_mods"):
        result[key] = _lua_list(result.get(key))
    by_slot = {i.slot: i for i in facts.items}
    engine_items = {e["slot"]: e["item_id"] for e in result["items"]}
    problems = []
    if dict(result.get("selection") or {}) != dict(facts.selection):
        problems.append("selection %s != %s" % (result.get("selection"), dict(facts.selection)))
    if set(engine_items) != set(by_slot) or any(
            by_slot[k].item_id != v for k, v in engine_items.items() if k in by_slot):
        problems.append("equipped items differ: engine %s, document %s" % (
            engine_items, {k: v.item_id for k, v in by_slot.items()}))
    engine_nodes = sorted((str(n["id"]) for n in result["nodes"]), key=int)
    if engine_nodes != list(facts.passive_ids):
        problems.append("allocated nodes differ")
    inputs = {r["var"]: r.get("input") for r in result["config"]}
    for var, value in facts.config_explicit.items():
        engine_value = inputs.get(var)
        same = (engine_value.split() == value.split()
                if isinstance(engine_value, str) and isinstance(value, str)
                else engine_value == value)
        if not same:
            problems.append("config %s: engine %r, document %r" % (var, inputs.get(var), value))
    # Custom modifier blocks of the selected config set as the engine holds
    # them (legacy customMods migrated by PoB); review PR-19-22 F1.
    engine_blocks = [(b["title"], bool(b["enabled"]), b["text"])
                     for b in result.pop("custom_mods")]
    if engine_blocks != list(facts.custom_mods):
        problems.append("custom modifier blocks: engine %r, document %r" % (
            engine_blocks, list(facts.custom_mods)))
    if problems:
        raise CaptureRefused(problems)
    result["items"].sort(key=lambda e: e["slot"])
    result["nodes"].sort(key=lambda e: int(e["id"]))
    result["config"].sort(key=lambda e: e["var"])
    return {
        "pob_commit": pob_commit,
        "pob_dirty": pob_dirty,
        "binding": {
            "document_hash": facts.document_hash,
            "selection": dict(facts.selection),
            "pob_commit": pob_commit,
            "pob_dirty": pob_dirty,
            "items": {slot: [i.item_id, i.text_sha256] for slot, i in sorted(by_slot.items())},
            "nodes": list(facts.passive_ids),
            "config": dict(sorted(facts.config_explicit.items())),
            "custom_mods": [list(b) for b in facts.custom_mods],
        },
        **result,
    }
