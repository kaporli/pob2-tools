"""Write the P04 fixture documents and catalog slice with the pinned PoB.

Usage (repository root, PoB checkout in POB2_ROOT):

    python scripts/p04_make_fixtures.py --out tests/fixtures/p04

Every build document here is composed by this script and then loaded and
saved by the pinned PoB, so the bytes are what PoB writes. The composition is
synthetic: classes, passives, gems and affixes are picked by fixed rules from
the catalog, item rolls take the low end of each range, and nothing describes
a played or recommended build. The catalog slice holds only the rows these
documents reference, plus every affix row whose text shape matches a fixture
item line, so offline tests see real tier and spawn-weight ambiguity.

The script needs PoB and is not part of any test run.
"""

from __future__ import annotations

import argparse
import copy
import json
import os
import re
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
for package in ("pob2-mcp", "pob2-optimizer"):
    sys.path.insert(0, str(REPO / package))

from pob2mcp.engine import Pob2Engine  # noqa: E402

#: Written into every document's Notes before PoB saves it, so the file says
#: what it is wherever it is copied. It names no catalog entity, so the notes
#: produce no claims.
NOTE = ("SYNTHETIC P04 fixture composed by scripts/p04_make_fixtures.py and "
        "saved by the pinned PoB. Not a played or recommended build.")

NUMBER = re.compile(r"\((\d+(?:\.\d+)?)-(\d+(?:\.\d+)?)\)")
SHAPE = re.compile(r"\(\d+(?:\.\d+)?-\d+(?:\.\d+)?\)|\d+(?:\.\d+)?")

#: Ten compositions. class/ascendancy are PoB class names; items are
#: (slot, base name, affix count); groups are (active index, supports) with
#: supports as (support index, level, quality, enabled). Indices pick from
#: the sorted active and support gem lists, so the choice is a rule, not taste.
#: A support level is capped at the gem's natural maximum, which PoB enforces
#: on load anyway; most supports in this catalog have a maximum of 1.
BUILDS = [
    dict(name="b01", cls="Ranger", asc=1, level=70, notables=3, asc_notables=1,
         items=[("Weapon 1", "Crude Bow", 3), ("Helmet", "Rusted Greathelm", 2)],
         groups=[(0, [(0, 3, 10, True), (1, 2, 0, False)])], main=1),
    dict(name="b02", cls="Huntress", asc=2, level=80, notables=4, asc_notables=2,
         items=[("Weapon 1", "Hunting Spear", 3), ("Body Armour", "Leather Vest", 2),
                ("Gloves", "Suede Bracers", 1)],
         groups=[(1, [(2, 4, 20, True)]), (2, [(3, 1, 5, True), (4, 3, 0, True)])],
         main=2),
    dict(name="b03", cls="Warrior", asc=1, level=60, notables=2, asc_notables=0,
         items=[("Weapon 1", "Wooden Club", 2), ("Weapon 1 Swap", "Crude Bow", 2)],
         groups=[(3, [(5, 2, 0, True)]), (4, [], "set2")], main=1),
    dict(name="b04", cls="Witch", asc=3, level=90, notables=5, asc_notables=2,
         items=[("Weapon 1", "Withered Wand", 3), ("Amulet", "Crimson Amulet", 2),
                ("Ring 1", "Iron Ring", 2)],
         groups=[(5, [(6, 5, 15, True), (7, 4, 0, False), (8, 1, 0, True)])],
         main=1, config=True),
    dict(name="b05", cls="Sorceress", asc=2, level=75, notables=3, asc_notables=1,
         items=[("Weapon 1", "Withered Wand", 2), ("Boots", "Rough Greaves", 2)],
         groups=[(6, [(9, 3, 0, True)]), (7, [(10, 2, 10, True)]),
                 (8, [])], main=3),
    dict(name="b06", cls="Mercenary", asc=1, level=55, notables=2, asc_notables=1,
         items=[("Weapon 1", "Makeshift Crossbow", 3), ("Belt", "Rawhide Belt", 2)],
         groups=[(9, [(11, 2, 5, True), (12, 1, 0, True)])], main=1, config=True),
    dict(name="b07", cls="Monk", asc=0, level=40, notables=2, asc_notables=0,
         items=[("Weapon 1", "Wrapped Quarterstaff", 2)],
         groups=[(10, [(13, 3, 0, False)])], main=1),
    dict(name="b08", cls="Druid", asc=1, level=85, notables=4, asc_notables=2,
         items=[("Weapon 1", "Wrapped Quarterstaff", 3), ("Gloves", "Suede Bracers", 2)],
         groups=[(11, [(14, 4, 20, True), (15, 2, 0, True)]), (12, [])], main=2),
    dict(name="b09", cls="Huntress", asc=3, level=65, notables=3, asc_notables=1,
         items=[("Weapon 1", "Hunting Spear", 2), ("Ring 2", "Iron Ring", 1)],
         groups=[(13, [(16, 1, 0, True)])], main=1, config=True),
    dict(name="b10", cls="Witch", asc=1, level=50, notables=2, asc_notables=1,
         items=[("Weapon 1", "Withered Wand", 1)],
         groups=[(14, [(17, 3, 5, True), (18, 2, 0, True)])], main=1),
    dict(name="b11", cls="Ranger", asc=2, level=68, notables=3, asc_notables=1,
         items=[("Weapon 1", "Crude Bow", 2), ("Body Armour", "Leather Vest", 1)],
         groups=[(15, [(19, 1, 10, True)]), (16, [(20, 1, 0, False)])], main=2),
    dict(name="b12", cls="Warrior", asc=2, level=72, notables=3, asc_notables=1,
         items=[("Weapon 1", "Wooden Club", 3), ("Helmet", "Rusted Greathelm", 1)],
         groups=[(17, [(21, 1, 20, True), (22, 1, 0, True)])], main=1, config=True),
]

#: The multi-loadout document is built on this composition.
VARIANT_BASE = "b09"


def write(path: Path, text: str) -> None:
    """UTF-8 with LF line ends. ``tests/fixtures`` is committed byte for byte
    (``.gitattributes``), so a CRLF written on Windows would be committed."""
    path.write_text(text, encoding="utf-8", newline="\n")


def rows(engine, table):
    out, offset = [], 0
    while offset is not None:
        page = engine.call("catalog_" + table, {"offset": offset, "limit": 5000})
        out += page["rows"]
        offset = page.get("next_offset")
    return out


def shape(line: str) -> str:
    return SHAPE.sub("#", line)


def spawns(mod, tags) -> bool:
    """Spawns on the base through a base-specific tag, not only ``default``."""
    for key, weight in zip(mod.get("weightKey") or (), mod.get("weightVal") or ()):
        if key in tags:
            return weight > 0 and key != "default"
    return False


def rolled(line: str) -> str:
    return NUMBER.sub(lambda m: m.group(1).rstrip("0").rstrip(".")
                      if "." in m.group(1) else m.group(1), line)


def make_item(name, base, affixes, mods, rarity="RARE"):
    tags = base.get("tags") or []
    pool = [m for m in mods if m.get("type") in ("Prefix", "Suffix")
            and spawns(m, tags) and len(m["lines"]) == 1]
    pool.sort(key=lambda m: (m.get("level", 0), m["id"]))
    picked, groups = [], set()
    for mod in pool:
        if mod["group"] in groups:
            continue
        picked.append(mod)
        groups.add(mod["group"])
        if len(picked) == affixes:
            break
    lines = ["Rarity: %s" % rarity, "FIXTURE P04 %s" % name, base["name"],
             "Item Level: 80", "Implicits: 0"]
    lines += [rolled(m["lines"][0]) for m in picked]
    return "\n".join(lines)


def build_one(engine, spec, catalog):
    cls = next(c for c in catalog["classes"] if c["name"] == spec["cls"])
    engine.call("new_build")
    engine.call("eval", {"code": "build.characterLevelAutoMode = false"})
    engine.call("set_level", {"level": spec["level"]})
    picked = engine.call("eval", {"code": """
local spec = build.spec
spec:SelectClass(%d)
spec:SelectAscendClass(%d)
spec:BuildAllDependsAndPaths()
local near, asc = {}, {}
for id, node in pairs(spec.nodes) do
  if node.type == 'Notable' and node.pathDist and node.pathDist <= 8 then
    if node.ascendancyName == nil then near[#near+1] = id
    elseif node.ascendancyName == spec.curAscendClassName then asc[#asc+1] = id end
  end
end
table.sort(near); table.sort(asc)
return {near = near, asc = asc}
""" % (cls["classId"], spec["asc"])})
    nodes = picked["near"][:spec["notables"]] + picked["asc"][:spec["asc_notables"]]
    if nodes:
        engine.call("alloc_nodes", {"ids": nodes})
    bases = {b["name"]: b for b in catalog["item_bases"]}
    for index, (slot, base, affixes) in enumerate(spec["items"]):
        if base not in bases:
            raise SystemExit("base %r is not in this catalog" % base)
        text = make_item("%s-%d" % (spec["name"], index), bases[base], affixes,
                         catalog["item_modifiers"])
        engine.call("equip_item", {"raw": text, "slot": slot})
    xml = engine.call("save_build_xml")["xml"]
    root = ET.fromstring(xml)

    actives = sorted((g for g in catalog["gems"] if not g["isSupport"]
                      and "attack" in (g.get("tags") or []) or
                      (not g["isSupport"] and "spell" in (g.get("tags") or []))),
                     key=lambda g: g["name"])
    supports = sorted((g for g in catalog["gems"] if g["isSupport"]),
                      key=lambda g: g["name"])
    skill_set = root.find("Skills/SkillSet")
    for child in list(skill_set):
        skill_set.remove(child)
    for gi, group in enumerate(spec["groups"]):
        active_index, support_list = group[0], group[1]
        bound = group[2] if len(group) > 2 else None
        attrib = {"enabled": "true", "label": "%s group %d" % (spec["name"], gi + 1),
                  "mainActiveSkill": "1",
                  "set1": "false" if bound == "set2" else "true",
                  "set2": "true" if bound == "set2" else ("false" if bound else "true")}
        if bound == "set2":
            attrib["set1"], attrib["set2"] = "false", "true"
        node = ET.SubElement(skill_set, "Skill", attrib)
        active = actives[active_index * 3 % len(actives)]
        ET.SubElement(node, "Gem", {"skillId": active["grantedEffectId"],
                                    "gemId": active["gameId"],
                                    "variantId": active.get("variantId") or "",
                                    "level": "15", "quality": "10",
                                    "enabled": "true"})
        for support_index, level, quality, enabled in support_list:
            support = supports[support_index * 5 % len(supports)]
            ET.SubElement(node, "Gem", {
                "skillId": support["grantedEffectId"], "gemId": support["gameId"],
                "variantId": support.get("variantId") or "",
                "level": str(min(level, support.get("naturalMaxLevel") or 1)),
                "quality": str(quality),
                "enabled": "true" if enabled else "false"})
    root.find("Build").set("mainSocketGroup", str(spec["main"]))
    root.find("Notes").text = NOTE
    if spec.get("config"):
        config_set = root.find("Config/ConfigSet")
        if config_set is None:
            config_set = root.find("Config")
        checks = sorted((v for v in catalog["config_variables"]
                         if v.get("type") == "check"), key=lambda v: v["var"])
        counts = sorted((v for v in catalog["config_variables"]
                         if v.get("type") == "count"), key=lambda v: v["var"])
        ET.SubElement(config_set, "Input", {"name": checks[len(spec["name"]) % len(checks)]["var"],
                                            "boolean": "true"})
        ET.SubElement(config_set, "Input", {"name": counts[0]["var"], "number": "3"})
    composed = ET.tostring(root, encoding="unicode")
    engine.call("load_build_xml", {"xml": composed})
    return engine.call("save_build_xml")["xml"]


def compose_variants(engine, leveling: str, endgame: str) -> str:
    """Endgame document plus the leveling sets, linked by PoB loadout titles."""
    base = ET.fromstring(endgame)
    other = ET.fromstring(leveling)
    items = base.find("Items")
    offset = max([int(i.get("id")) for i in items.findall("Item")] + [0])
    remap = {}
    for item in other.findall("Items/Item"):
        new = copy.deepcopy(item)
        remap[item.get("id")] = str(int(item.get("id")) + offset)
        new.set("id", remap[item.get("id")])
        items.insert(len(items.findall("Item")), new)
    titles = (("Tree", "Spec", None), ("Skills", "SkillSet", "id"),
              ("Items", "ItemSet", "id"), ("Config", "ConfigSet", "id"))
    for tag, child, key in titles:
        mine = base.find("%s/%s" % (tag, child))
        mine.set("title", "Endgame {2}")
        theirs = copy.deepcopy(other.find("%s/%s" % (tag, child)))
        theirs.set("title", "Leveling {1}")
        if key:
            theirs.set(key, "2")
        if tag == "Items":
            for slot in theirs.findall("Slot"):
                slot.set("itemId", remap.get(slot.get("itemId"), "0"))
        container = base.find(tag)
        container.insert(list(container).index(mine), theirs)
    # One more item set no loadout links: it must stay unlinked.
    spare = copy.deepcopy(base.find("Items/ItemSet[@id='2']"))
    spare.set("id", "3")
    spare.set("title", "Unlinked trade test")
    base.find("Items").append(spare)
    base.find("Tree").set("activeSpec", "2")
    base.find("Notes").text = NOTE
    engine.call("load_build_xml", {"xml": ET.tostring(base, encoding="unicode")})
    return engine.call("save_build_xml")["xml"]


def referenced(documents):
    refs = {"classes": set(), "nodes": set(), "gems": set(), "skills": set(),
            "bases": set(), "config": set(), "lines": set()}
    for xml in documents:
        root = ET.fromstring(xml)
        refs["classes"].add(root.find("Build").get("className"))
        for spec in root.iter("Spec"):
            for part in (spec.get("nodes") or "").split(","):
                if part.strip():
                    refs["nodes"].add(int(part))
        for gem in root.iter("Gem"):
            refs["gems"].add(gem.get("gemId"))
            refs["skills"].add(gem.get("skillId"))
        for item in root.iter("Item"):
            lines = [l.strip() for l in (item.text or "").split("\n") if l.strip()]
            if len(lines) > 2:
                refs["bases"].add(lines[2])
            after = False
            for line in lines:
                if after:
                    refs["lines"].add(shape(re.sub(r"^(\{[^}]*\})*", "", line)))
                if line.startswith("Implicits:"):
                    after = True
        for node in root.iter("Input"):
            refs["config"].add(node.get("name"))
    return refs


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    # Resolved before the engine starts: Pob2Engine changes the working
    # directory to the PoB source tree.
    out = Path(args.out).resolve()
    (out / "builds").mkdir(parents=True, exist_ok=True)
    pob_root = os.environ["POB2_ROOT"]
    engine = Pob2Engine(pob_root)
    engine.call("new_build")
    catalog = {t: rows(engine, t) for t in (
        "classes", "passive_nodes", "gems", "granted_skills", "item_bases",
        "item_modifiers", "slots", "config_variables")}

    documents = {}
    for spec in BUILDS:
        documents[spec["name"]] = build_one(engine, spec, catalog)
        write(out / "builds" / ("%s.xml" % spec["name"]),
              documents[spec["name"]])
    base = next(b for b in BUILDS if b["name"] == VARIANT_BASE)
    leveling = build_one(engine, dict(base, name=VARIANT_BASE + "-leveling",
                                      level=20, notables=1, asc_notables=0,
                                      items=[("Weapon 1", "Hunting Spear", 1)],
                                      groups=[(13, [(16, 1, 0, True)])], main=1),
                         catalog)
    variants = compose_variants(engine, leveling, documents[VARIANT_BASE])
    write(out / "variants.xml", variants)

    refs = referenced(list(documents.values()) + [variants])
    slice_rows = {
        "classes": catalog["classes"],
        "passive_nodes": [r for r in catalog["passive_nodes"] if r["id"] in refs["nodes"]],
        "gems": [r for r in catalog["gems"] if r["gameId"] in refs["gems"]],
        "granted_skills": [r for r in catalog["granted_skills"] if r["id"] in refs["skills"]],
        "item_bases": [r for r in catalog["item_bases"] if r["name"] in refs["bases"]],
        "item_modifiers": [r for r in catalog["item_modifiers"]
                           if any(shape(l) in refs["lines"] for l in r["lines"])],
        "slots": catalog["slots"],
        "config_variables": [r for r in catalog["config_variables"]
                             if r.get("var") in refs["config"]],
    }
    commit = subprocess.run(["git", "-C", pob_root, "rev-parse", "HEAD"],
                            capture_output=True, text=True).stdout.strip()
    write(out / "catalog-slice.json", json.dumps({
        "kind": "PoB-derived",
        "purpose": ("Offline catalog for the P04 parser, resolution, audit "
                    "and round-trip tests."),
        "not_a_claim": ("Rows of the pinned PoB catalog that the P04 fixture "
                        "documents reference, plus every affix row sharing a "
                        "text shape with a fixture item line. Not the "
                        "catalog."),
        "pob_commit": commit,
        "tree_version": ET.fromstring(variants).find("Tree/Spec").get("treeVersion"),
        "tables": slice_rows,
    }, indent=1, sort_keys=True) + "\n")
    write_manifest(out, commit)
    print(json.dumps({t: len(r) for t, r in slice_rows.items()}))
    return 0


def write_manifest(out: Path, commit: str) -> None:
    """Replace the P04 entries of ``tests/fixtures/manifest.json``."""
    import hashlib
    fixtures = out.parent
    path = fixtures / "manifest.json"
    manifest = json.loads(path.read_text(encoding="utf-8"))
    prefix = out.relative_to(fixtures).as_posix() + "/"
    kept = [e for e in manifest["fixtures"] if not e["path"].startswith(prefix)]
    caveat = ("Composed by scripts/p04_make_fixtures.py from fixed rules over "
              "the pinned catalog (PoB %s), then loaded and saved by that PoB. "
              "The bytes are PoB's; the build is synthetic: no played "
              "character, no recommendation and no gameplay measurement."
              % commit[:12])
    entries = []
    for file in sorted(out.rglob("*")):
        if not file.is_file():
            continue
        data = file.read_bytes()
        relative = file.relative_to(fixtures).as_posix()
        if file.name == "catalog-slice.json":
            description = ("Rows of the pinned PoB catalog the P04 documents "
                           "reference, plus every affix row sharing a text "
                           "shape with a fixture item line.")
        elif file.name == "variants.xml":
            description = ("Two loadouts linked by PoB's {id} title rule and "
                           "one item set no loadout links.")
        else:
            description = "One build: %s." % next(
                "%s, level %d, %d item(s), %d skill group(s)" % (
                    b["cls"], b["level"], len(b["items"]), len(b["groups"]))
                for b in BUILDS if b["name"] == file.stem)
        entries.append({
            "path": relative, "sha256": hashlib.sha256(data).hexdigest(),
            "bytes": len(data), "origin": "pob_derived", "author": "P04",
            "description": description,
            "used_by": ["tests/p04_fixtures.py"], "caveat": caveat})
    manifest["fixtures"] = kept + entries
    write(path, json.dumps(manifest, indent=2, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    raise SystemExit(main())
