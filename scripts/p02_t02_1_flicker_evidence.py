"""Flicker Strike catalog coverage evidence (P02-T02.1).

Builds three Flicker Strike documents in a throwaway engine (alone, with one
support the catalog lists as compatible, with one it lists as incompatible),
reads their engine values through ``EngineAdapter.probe``, and compares the
catalog's static support list with PoB's own answer for the live main skill
of the first document.

Run it to regenerate the evidence:

    python scripts/p02_t02_1_flicker_evidence.py

It writes ``docs/evidence/P02-T02.1/flicker-coverage.json``. Without a PoB
checkout it records ``unavailable``. Everything here is PoB-derived. Engine
agreement is not gameplay evidence, and the weapon's rolls are invented.
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
for _pkg in (REPO_ROOT / "pob2-mcp", REPO_ROOT / "pob2-optimizer",
             REPO_ROOT / "scripts"):
    if str(_pkg) not in sys.path:
        sys.path.insert(0, str(_pkg))

OUT = REPO_ROOT / "docs" / "evidence" / "P02-T02.1" / "flicker-coverage.json"

GEM_ID = "Metadata/Items/Gems/SkillGemFlickerStrike"
SKILL_ID = "FlickerStrikePlayer"
CHAR_LEVEL = 90
RESIST_PENALTY = -60
#: The gem row's ``naturalMaxLevel``.
GEM_LEVEL = 20

SET_GEM_LEVEL_LUA = """
local g = build.skillsTab.socketGroupList[%d]
g.gemList[1].level = %d
build.skillsTab:ProcessSocketGroup(g)
build.buildFlag = true
runCallback("OnFrame")
return g.gemList[1].level
"""

#: Same synthetic quarterstaff as ``tests/engine_helpers.FIXTURE_WEAPON``.
WEAPON = "\n".join(["Rarity: Rare", "Fixture Stave", "Long Quarterstaff",
                    "Quality: 20", "Item Level: 82",
                    "Adds 60 to 90 Physical Damage",
                    "30% increased Attack Speed"])

#: (document name, support gem name or None). The two supports were chosen
#: from the catalog rows: Rapid Attacks I requires Attack, which Flicker
#: Strike has; Fork requires Projectile, which it lacks.
DOCUMENTS = (("flicker_alone", None),
             ("flicker_rapid_attacks", "Rapid Attacks I"),
             ("flicker_fork", "Fork"))

#: Engine outputs each behaviour fixture records.
STAT_KEYS = ("AverageDamage", "Speed", "ManaCost", "CritChance")

#: PoB's own support check against the live main skill, over every support
#: granted effect, plus the skill types the live skill actually carries.
LIVE_SUPPORTS_LUA = """
local skill = build.calcsTab.mainEnv.player.mainSkill
local accepted = {}
for id, effect in pairs(data.skills) do
  if effect.support then
    local ok, yes = pcall(calcLib.canGrantedEffectSupportActiveSkill, effect, skill)
    if ok and yes then accepted[#accepted + 1] = tostring(id) end
  end
end
table.sort(accepted)
local names = {}
for name, number in pairs(SkillType) do
  if skill.skillTypes[number] then names[#names + 1] = name end
end
table.sort(names)
return { skill = skill.activeEffect.grantedEffect.id, accepted = accepted,
         liveSkillTypes = names }
"""


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def build_documents(pob_root) -> tuple[dict[str, str], dict]:
    """The three documents, and PoB's live support answer for the first."""
    from p02_t04_primitive_fixtures import _ADD_SUPPORT_LUA, FixtureBuilder

    builder = FixtureBuilder(pob_root)
    docs: dict[str, str] = {}
    live: dict = {}
    try:
        engine = builder.engine
        for name, support in DOCUMENTS:
            engine.call("new_build")
            for source in builder._helpers:
                engine.eval_lua(source)
            engine.eval_lua(_ADD_SUPPORT_LUA)
            engine.eval_lua("return OPT_setup(%d, %d)"
                            % (CHAR_LEVEL, RESIST_PENALTY))
            engine.eval_lua("return OPT_equip(%s, %s)"
                            % (json.dumps(WEAPON), json.dumps("Weapon 1")))
            index = engine.eval_lua('return OPT_add_group("Flicker Strike", %d, 0, true)'
                                    % CHAR_LEVEL)
            if not index:
                raise LookupError("the pinned catalog has no usable Flicker Strike")
            # OPT_add_group takes the highest level the character meets, which
            # is 40 at level 90. Use the gem's natural maximum instead.
            engine.eval_lua(SET_GEM_LEVEL_LUA % (index, GEM_LEVEL))
            if support is not None:
                if not engine.eval_lua("return OPT_T04_add_support(%d, %s, %d)"
                                       % (index, json.dumps(support), CHAR_LEVEL)):
                    raise LookupError("the pinned catalog has no %r" % support)
            engine.eval_lua("return OPT_set_main(%d, 1)" % index)
            if name == "flicker_alone":
                live = engine.eval_lua(LIVE_SUPPORTS_LUA)
            docs[name] = engine.call("save_build_xml")["xml"]
    finally:
        builder.close()
    return docs, live


def probe_documents(pob_root, docs: dict[str, str]) -> dict[str, dict]:
    from pob2opt.evaluation import (BuildDocument, EngineAdapter, EngineState,
                                    pob_worker_spec)

    adapter = EngineAdapter(pob_worker_spec(pob_root), start_timeout_s=600.0,
                            screen_timeout_s=300.0, detailed_timeout_s=300.0)
    try:
        return {name: adapter.probe(
                    BuildDocument(build_hash="p02-t02.1/%s" % name, xml=xml),
                    EngineState(stat_keys=STAT_KEYS), timeout_s=300.0)
                for name, xml in docs.items()}
    finally:
        adapter.close()


def catalog_rows(pob_root) -> tuple[dict, dict]:
    from pob2opt.evaluation import EngineAdapter, pob_worker_spec

    adapter = EngineAdapter(pob_worker_spec(pob_root), start_timeout_s=600.0,
                            screen_timeout_s=300.0, detailed_timeout_s=300.0)
    try:
        gems = adapter.catalog_rows("gems", timeout_s=600.0)
        skills = adapter.catalog_rows("granted_skills", timeout_s=600.0)
    finally:
        adapter.close()
    return gems, skills


def main() -> int:
    pob_root = os.environ.get("POB2_ROOT")
    OUT.parent.mkdir(parents=True, exist_ok=True)
    if not pob_root or not Path(pob_root).is_dir():
        OUT.write_text(json.dumps(
            {"kind": "PoB-derived", "status": "unavailable",
             "reason": "POB2_ROOT is not set to a PoB checkout",
             "written_at": _now()}, indent=1) + "\n", encoding="utf-8")
        return 0

    from pob2opt.catalog.supports import flicker_coverage
    from pob2opt.evaluation import resolve_checkout

    checkout = resolve_checkout(pob_root)
    gems, skills = catalog_rows(pob_root)
    coverage = flicker_coverage(gems, skills)
    docs, live = build_documents(pob_root)
    values = probe_documents(pob_root, docs)

    static = set(coverage["supported_by_effect_ids"])
    accepted = set(live.get("accepted") or ())
    payload = {
        "kind": "PoB-derived",
        "not_a_claim": (
            "Read out of the pinned Path of Building checkout. Not gameplay "
            "evidence. The support list is PoB's static answer on base skill "
            "types; the weapon in the documents has invented rolls."),
        "written_at": _now(),
        "pob_commit": checkout.commit,
        "pob_dirty_hash": checkout.dirty_hash,
        "coverage": coverage,
        "live_main_skill": {
            "skill": live.get("skill"),
            "live_skill_types": live.get("liveSkillTypes"),
            "accepted_count": len(accepted),
            "accepted_only_live": sorted(accepted - static),
            "accepted_only_static": sorted(static - accepted),
        },
        "behaviour": {name: {"support": support, "values": values[name],
                             "document": docs[name]}
                      for name, support in DOCUMENTS},
    }
    OUT.write_text(json.dumps(payload, indent=1, sort_keys=True,
                              ensure_ascii=False) + "\n", encoding="utf-8")
    print("wrote %s" % OUT, file=sys.stderr)
    return 0


if __name__ == "__main__":
    import multiprocessing as mp

    mp.freeze_support()
    sys.exit(main())
