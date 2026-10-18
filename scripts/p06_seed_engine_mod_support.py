"""Ask the pinned PoB engine which seed modifier lines it parses (P06-T02).

Loads the P09-T01.1 seed export exactly as stored and records, per equipped
item modifier line and per allocated passive line, whether PoB's parser
produced a modifier list and whether text was left over. PoB marks
unparsed text as ``extra`` (Classes/Item.lua, Classes/PassiveTree.lua).
A parsed line is not proof of a correct implementation; an unparsed line is
proof that PoB does not calculate it.

The capture is bound to the document hash, the selected sets, the clean
engine identity, each equipped item's id and text hash, the allocated nodes
and the selected config inputs. It refuses to write when the engine's loaded
state differs from the document's.

Also records every config variable holding an input or placeholder value and
whether PoB's own config tab shows it for this build (``control.shown``).
PoB applies count-type placeholders when no input is set
(ConfigTab:BuildModList), so placeholders are assumptions too.

Refuses a dirty or unpinned checkout. Needs the engine; run it alone:

    POB2_ROOT=external/PathOfBuilding-PoE2 python scripts/p06_seed_engine_mod_support.py
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SEED = REPO / "docs/evidence/P09-T01.1/seed/export-flicker-main.xml"
OUT = REPO / "docs/evidence/P06/seed-engine-mod-support.json"
PIN = "ce566eac45ea8a86477f513c7ee65a1ebe60014e"

PROBE = r"""
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
out.selection = {
  Tree = tostring(build.treeTab.activeSpec),
  Skills = tostring(build.skillsTab.activeSkillSetId),
  Items = tostring(build.itemsTab.activeItemSetId),
  Config = tostring(cfg.activeConfigSetId),
}
return out
"""


def _git(root: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(root), *args], check=True,
                          capture_output=True, text=True).stdout.strip()


def main() -> int:
    root = Path(os.environ.get("POB2_ROOT") or REPO / "external/PathOfBuilding-PoE2").resolve()
    head = _git(root, "rev-parse", "HEAD")
    dirty = _git(root, "status", "--porcelain")
    if head != PIN or dirty:
        print("refused: checkout %s at %s, dirty=%s" % (root, head, bool(dirty)))
        return 2
    sys.path.insert(0, str(REPO / "pob2-mcp"))
    from pob2mcp.engine import Pob2Engine

    xml = SEED.read_bytes()
    sys.path.insert(0, str(REPO / "pob2-optimizer"))
    from pob2opt.coverage.inputs import build_facts_from_pob_xml
    facts = build_facts_from_pob_xml(xml)
    if facts.loadout_problems:
        print("refused: %s" % "; ".join(facts.loadout_problems))
        return 2
    with Pob2Engine(str(root)) as engine:
        engine.call("load_build_xml", {"xml": xml.decode("utf-8"), "name": "seed"})
        result = engine.eval_lua(PROBE)
    # Bind the verdicts to what the engine actually held, and refuse when that
    # differs from the document's own selection, items, nodes or inputs.
    by_slot = {i.slot: i for i in facts.items}
    engine_items = {e["slot"]: e["item_id"] for e in result["items"]}
    problems = []
    if result["selection"] != dict(facts.selection):
        problems.append("selection %s != %s" % (result["selection"], dict(facts.selection)))
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
    if problems:
        print("refused: " + "; ".join(problems))
        return 2
    binding = {
        "document_hash": facts.document_hash,
        "selection": dict(facts.selection),
        "pob_commit": head,
        "pob_dirty": False,
        "items": {slot: [i.item_id, i.text_sha256] for slot, i in sorted(by_slot.items())},
        "nodes": list(facts.passive_ids),
        "config": dict(sorted(facts.config_explicit.items())),
    }
    result["items"].sort(key=lambda e: e["slot"])
    result["nodes"].sort(key=lambda e: int(e["id"]))
    result["config"].sort(key=lambda e: e["var"])
    payload = {
        "task": "P06-T02",
        "kind": "engine_parse_support",
        "not_a_claim": ("Parsed means PoB produced a modifier list; it does not "
                        "mean the modifier is implemented correctly."),
        "pob_commit": head,
        "pob_dirty": False,
        "seed_xml": str(SEED.relative_to(REPO)).replace("\\", "/"),
        "seed_sha256": hashlib.sha256(xml).hexdigest(),
        "generated_by": "scripts/p06_seed_engine_mod_support.py",
        "binding": binding,
        **result,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    unparsed = sum(1 for e in result["items"] for r in e["lines"] if not r["parsed"] or r.get("extra"))
    print("items %d, nodes %d, unparsed item lines %d" % (
        len(result["items"]), len(result["nodes"]), unparsed))
    return 0


if __name__ == "__main__":
    sys.exit(main())
