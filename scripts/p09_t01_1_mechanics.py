"""Extract the Flicker Strike charge mechanics from the pinned PoB data (P09-T01.1).

    POB2_ROOT=<PathOfBuilding-PoE2 checkout> python scripts/p09_t01_1_mechanics.py

Without ``POB2_ROOT`` it reads ``external/PathOfBuilding-PoE2``. It refuses a
checkout whose HEAD is not the pin or whose working tree is dirty.

It writes ``docs/evidence/P09-T01.1/mechanics.json``: verbatim lines from the
skill, support and stat-description data files, the passive nodes and class
list from the 0_5 tree, and the engine lines that turn power charges into
Flicker Strike strikes. Every entry carries its file path, file SHA-256 and
line numbers so a reviewer can open the same lines. Everything here is
PoB-derived: it says what the pinned engine data contains, not how the game
behaves.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
OUT = REPO_ROOT / "docs" / "evidence" / "P09-T01.1" / "mechanics.json"
PIN = "ce566eac45ea8a86477f513c7ee65a1ebe60014e"
WRITTEN_AT = "2026-10-17T00:00:00Z"

#: Lines kept from a skill or support block. Everything else (per-level
#: tables, icons, flavour text) is dropped; the line numbers say where to look.
SKILL_LINE_PATTERNS = [
    r'^\tname = ',
    r'^\tdescription = ',
    r'^\tskillTypes = ',
    r'^\tsupport = true',
    r'^\t(require|add|exclude)SkillTypes = ',
    r'^\t\t\["Staff"\] = true',
    r'^\t\t\[1\] = \{ .*(cost|manaMultiplier)',
    r'^\t\t\[20\] = \{ .*cost',
    r'^\t\t\{ "charge_skip_consume_chance_%"',
    r'^\t\t\{ "chance_to_gain_1_more_charge_%"',
    r'^\t\t\t\t\{ "[^"]+", -?[0-9.]+ \},',
    r'^\t\t\t\t"[a-z0-9_%+]+",$',
    r'AdditionalFlickersPerPowerCharge|averageBurstHits',
]

#: (mechanic_id, file under src/, skill key).
SKILLS = [
    ("skill/FlickerStrikePlayer", "Data/Skills/act_int.lua", "FlickerStrikePlayer"),
    ("skill/WhirlingAssaultPlayer", "Data/Skills/act_int.lua", "WhirlingAssaultPlayer"),
    ("skill/ChargedStaffPlayer", "Data/Skills/act_int.lua", "ChargedStaffPlayer"),
    ("skill/SiphoningStrikePlayer", "Data/Skills/act_int.lua", "SiphoningStrikePlayer"),
    ("skill/KillingPalmPlayer", "Data/Skills/act_int.lua", "KillingPalmPlayer"),
    ("support/SupportCulminationPlayerTwo", "Data/Skills/sup_dex.lua", "SupportCulminationPlayerTwo"),
    ("support/SupportAilithLineagePlayer", "Data/Skills/sup_dex.lua", "SupportAilithLineagePlayer"),
    ("support/SupportHitAndRunPlayer", "Data/Skills/sup_dex.lua", "SupportHitAndRunPlayer"),
    ("support/SupportPerpetualChargePlayer", "Data/Skills/sup_int.lua", "SupportPerpetualChargePlayer"),
]

#: (mechanic_id, file under src/, stat id).
STAT_DESCRIPTIONS = [
    ("statdesc/flicker_strike_additional_flickers_from_power_charges",
     "Data/StatDescriptions/skill_stat_descriptions.lua",
     "flicker_strike_additional_flickers_from_power_charges"),
    ("statdesc/cannot_gain_power_charges_during_skill",
     "Data/StatDescriptions/skill_stat_descriptions.lua",
     "cannot_gain_power_charges_during_skill"),
    ("statdesc/chance_%_to_gain_power_charges_per_combo_spent",
     "Data/StatDescriptions/gem_stat_descriptions.lua",
     "chance_%_to_gain_power_charges_per_combo_spent"),
    ("statdesc/skill_maximum_number_of_combo_stacks",
     "Data/StatDescriptions/gem_stat_descriptions.lua",
     "skill_maximum_number_of_combo_stacks"),
    ("statdesc/skill_unusable_until_moved_X_distance",
     "Data/StatDescriptions/gem_stat_descriptions.lua",
     "skill_unusable_until_moved_X_distance"),
    ("statdesc/charge_skip_consume_chance_%",
     "Data/StatDescriptions/gem_stat_descriptions.lua",
     "charge_skip_consume_chance_%"),
]

#: (mechanic_id, file under src/, regex of the lines to keep).
ENGINE_LINES = [
    ("engine/removable-power-charges", "Modules/CalcPerform.lua",
     r'local removablePowerCharges = |output\.RemovablePowerCharges = removable'
     r'|modDB\.multipliers\["RemovablePowerCharge"\] = '),
    ("engine/flicker-bypass-cd-config", "Modules/ConfigOptions.lua",
     r'FlickerStrikeBypassCD|skillName = "Flicker Strike", includeTransfigured = true \}\)'),
]

#: Passive nodes cited by the proposal: seed allocations and the ascendancy
#: nodes whose text names charges, Combo or melee triggers.
PASSIVE_NODE_IDS = ["65204", "41751", "61586", "36643", "7979", "42441", "52448", "2516"]


def _git(root: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(root), *args], check=True,
                          capture_output=True, text=True).stdout.strip()


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _lines(path: Path) -> list[str]:
    return path.read_text(encoding="utf-8").split("\n")


def _entry(mechanic_id, kind, root, rel, picked):
    path = root / "src" / rel
    return {
        "mechanic_id": mechanic_id,
        "kind": kind,
        "path": "src/" + rel,
        "file_sha256": _sha(path),
        "lines": [{"n": n, "text": t} for n, t in picked],
    }


def skill_entry(root, mechanic_id, rel, key):
    lines = _lines(root / "src" / rel)
    start = next(i for i, l in enumerate(lines) if l.startswith('skills["%s"]' % key))
    end = start + 1
    while end < len(lines) and not lines[end].startswith('skills["'):
        end += 1
    pats = [re.compile(p) for p in SKILL_LINE_PATTERNS]
    picked = [(start + 1, lines[start])]
    for i in range(start + 1, end):
        if any(p.search(lines[i]) for p in pats):
            picked.append((i + 1, lines[i]))
    kind = "support" if mechanic_id.startswith("support/") else "skill"
    return _entry(mechanic_id, kind, root, rel, picked)


def statdesc_entry(root, mechanic_id, rel, stat):
    lines = _lines(root / "src" / rel)
    target = '[1]="%s"' % stat
    idx = next(i for i, l in enumerate(lines)
               if l.strip() == target and lines[i - 1].strip() == "stats={")
    start = idx
    while not re.match(r'^\t\[\d+\]=\{$', lines[start]):
        start -= 1
    picked = [(i + 1, lines[i]) for i in range(start, idx + 1)
              if 'text=' in lines[i] or 'k="' in lines[i] or i == idx]
    return _entry(mechanic_id, "stat_description", root, rel, picked)


def engine_entry(root, mechanic_id, rel, pattern):
    lines = _lines(root / "src" / rel)
    pat = re.compile(pattern)
    picked = [(i + 1, l) for i, l in enumerate(lines) if pat.search(l)]
    if not picked:
        raise SystemExit("no engine lines for %s" % mechanic_id)
    return _entry(mechanic_id, "engine", root, rel, picked)


def tree_entries(root):
    rel = "TreeData/0_5/tree.json"
    path = root / "src" / rel
    tree = json.loads(path.read_text(encoding="utf-8"))
    nodes = []
    for nid in PASSIVE_NODE_IDS:
        n = tree["nodes"][nid]
        nodes.append({
            "mechanic_id": "passive/%s" % nid,
            "kind": "passive_node",
            "path": "src/" + rel,
            "file_sha256": _sha(path),
            "node_id": int(nid),
            "name": n.get("name"),
            "ascendancy": n.get("ascendancyName"),
            "notable": bool(n.get("isNotable")),
            "stats": n.get("stats", []),
        })
    classes = [{"class": c["name"],
                "ascendancies": [a["id"] for a in c.get("ascendancies", [])]}
               for c in tree["classes"]]
    return nodes, {"path": "src/" + rel, "file_sha256": _sha(path), "classes": classes}


def main() -> int:
    root = Path(os.environ.get("POB2_ROOT") or REPO_ROOT / "external" / "PathOfBuilding-PoE2")
    head = _git(root, "rev-parse", "HEAD")
    if head != PIN:
        raise SystemExit("PoB HEAD %s is not the pin %s" % (head, PIN))
    if _git(root, "status", "--porcelain"):
        raise SystemExit("PoB working tree at %s is dirty; use a clean checkout" % root)

    entries = [skill_entry(root, *s) for s in SKILLS]
    entries += [statdesc_entry(root, *s) for s in STAT_DESCRIPTIONS]
    entries += [engine_entry(root, *s) for s in ENGINE_LINES]
    nodes, classes = tree_entries(root)
    entries += nodes

    payload = {
        "task": "P09-T01.1",
        "kind": "PoB-derived",
        "not_a_claim": (
            "Verbatim lines from the pinned Path of Building data. They say "
            "what the engine data holds for patch data exported before "
            "0.5.5e, not how the game behaves. Engine agreement is not "
            "gameplay evidence."),
        "pob_commit": head,
        "pob_dirty": False,
        "written_at": WRITTEN_AT,
        "generated_by": "scripts/p09_t01_1_mechanics.py",
        "entries": entries,
        "classes": classes,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, indent=2, ensure_ascii=False) + "\n"
    OUT.write_text(text, encoding="utf-8", newline="\n")
    print("wrote %s, %d entries, sha256 %s" % (OUT.relative_to(REPO_ROOT), len(entries),
                                               hashlib.sha256(text.encode()).hexdigest()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
