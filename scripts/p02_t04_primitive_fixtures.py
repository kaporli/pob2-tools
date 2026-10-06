"""Controlled fixtures for the P02-T04 primitive inventory.

Each fixture is a complete PoB build document that differs from its pair in
exactly one declared way, so a semantic can be settled by comparison instead of
by reading a field name. The documents are built once in a throwaway engine and
then evaluated through ``pob2opt.evaluation.EngineAdapter``, which is the only
engine path this repository has.

Run it to regenerate the evidence:

    python scripts/p02_t04_primitive_fixtures.py

It writes ``docs/evidence/P02/primitives.json``. Without a PoB checkout the
file records ``unavailable`` rather than inventing numbers.

Everything here is PoB-derived. Engine agreement is not practical accuracy and
nothing in this file is gameplay evidence.
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
for _pkg in (REPO_ROOT / "pob2-mcp", REPO_ROOT / "pob2-optimizer"):
    if str(_pkg) not in sys.path:
        sys.path.insert(0, str(_pkg))

CHAR_LEVEL = 60
RESIST_PENALTY = -30

#: A synthetic rare bow. Invented values; it exists to give the engine
#: something deterministic to calculate.
BOW_HEADER = ("Rarity: Rare", "P02-T04 Fixture Bow", "%(base)s",
              "Item Level: 60", "Implicits: 0")

#: Added to the weapon in the accuracy fixture. The hit chance it buys is the
#: point; the number is invented.
ACCURACY_MOD = "+2000 to Accuracy Rating"
#: Added to the weapon in the projectile fixture.
PROJECTILE_MOD = "Bow Attacks fire 2 additional Arrows"

#: Every meta gem in the pinned catalog that can wrap a spell. One fixture
#: each, so the trigger-cadence finding is not a claim about one gem.
META_GEMS = ("Cast on Critical", "Cast on Block", "Cast on Dodge",
             "Cast on Minion Death", "Cast on Elemental Ailment")

#: The spell every trigger fixture wraps, and casts directly for comparison.
WRAPPED_SPELL = "Fireball"


def wrapped_name(meta: str) -> str:
    return "cast_wrapped_" + meta.lower().replace(" ", "_")


#: Fixture names in the order they are built. Each returns a saved build XML.
FIXTURE_ORDER = (("baseline", "accuracy", "projectiles", "dot", "dot_longer",
                  "cast_direct", "cast_wrapped", "cooldown", "show_average")
                 + tuple(wrapped_name(meta) for meta in META_GEMS))

_ADD_SUPPORT_LUA = """
function OPT_T04_add_support(gi, name, charLevel)
  local g = build.skillsTab.socketGroupList[gi]
  if not g then return nil end
  local lvl = 0
  for _, gem in pairs(build.data.gems) do
    if gem.name == name and gem.grantedEffect and gem.grantedEffect.levels then
      for l, info in ipairs(gem.grantedEffect.levels) do
        if (info.levelRequirement or 0) <= charLevel then lvl = l end
      end
    end
  end
  if lvl == 0 then return nil end
  table.insert(g.gemList, { nameSpec = name, level = lvl, quality = 0,
                            enabled = true, count = 1, enableGlobal1 = true,
                            enableGlobal2 = true })
  build.skillsTab:ProcessSocketGroup(g)
  build.buildFlag = true
  runCallback("OnFrame")
  return #g.gemList
end
"""


class FixtureBuilder:
    """A throwaway engine that produces the fixture documents and closes."""

    def __init__(self, pob_root: str | os.PathLike[str]) -> None:
        from pob2mcp.engine import Pob2Engine

        lua_dir = REPO_ROOT / "pob2-optimizer" / "pob2opt" / "lua"
        self._helpers = [(lua_dir / name).read_text(encoding="utf-8")
                         for name in ("opt_helpers.lua", "tree_lib.lua")]
        self._cwd = os.getcwd()
        self.engine = Pob2Engine(str(pob_root))

    def close(self) -> None:
        close = getattr(self.engine, "close", None)
        if close is not None:
            close()
        os.chdir(self._cwd)

    # -- plumbing ---------------------------------------------------------

    def _fresh(self):
        self.engine.call("new_build")
        for source in self._helpers:
            self.engine.eval_lua(source)
        self.engine.eval_lua(_ADD_SUPPORT_LUA)
        self.engine.eval_lua("return OPT_setup(%d, %d)"
                             % (CHAR_LEVEL, RESIST_PENALTY))

    def _equip_bow(self, extra_mods=()):
        base = self.engine.eval_lua('return OPT_best_base("Bow", %d)' % CHAR_LEVEL)
        lines = [line % {"base": base} for line in BOW_HEADER]
        lines.extend(extra_mods)
        raw = "\n".join(lines)
        self.engine.eval_lua("return OPT_equip(%s, %s)"
                             % (json.dumps(raw), json.dumps("Weapon 1")))
        return base

    def _group(self, gem: str, quality: int = 20):
        index = self.engine.eval_lua('return OPT_add_group(%s, %d, %d, true)'
                                     % (json.dumps(gem), CHAR_LEVEL, quality))
        if not index:
            raise LookupError("the pinned catalog has no usable gem %r" % gem)
        self.engine.eval_lua("return OPT_set_main(%d, 1)" % index)
        return index

    def _save(self) -> str:
        return self.engine.call("save_build_xml")["xml"]

    # -- fixtures ---------------------------------------------------------

    def baseline(self) -> str:
        self._fresh()
        self._equip_bow()
        self._group("Lightning Arrow")
        return self._save()

    def accuracy(self) -> str:
        self._fresh()
        self._equip_bow([ACCURACY_MOD])
        self._group("Lightning Arrow")
        return self._save()

    def projectiles(self) -> str:
        self._fresh()
        self._equip_bow([PROJECTILE_MOD])
        self._group("Lightning Arrow")
        return self._save()

    def dot(self) -> str:
        self._fresh()
        self._group("Contagion")
        return self._save()

    def dot_longer(self) -> str:
        self._fresh()
        index = self._group("Contagion")
        added = None
        for support in ("Prolonged Duration II", "Prolonged Duration I"):
            added = self.engine.eval_lua('return OPT_T04_add_support(%d, %s, %d)'
                                         % (index, json.dumps(support), CHAR_LEVEL))
            if added:
                break
        if not added:
            raise LookupError("the pinned catalog has no duration support")
        self.engine.eval_lua("return OPT_set_main(%d, 1)" % index)
        return self._save()

    def cast_direct(self) -> str:
        self._fresh()
        self._group(WRAPPED_SPELL)
        return self._save()

    def wrapped(self, meta: str) -> str:
        self._fresh()
        index = self.engine.eval_lua(
            'return OPT_add_wrapped_group(%s, %s, %d, 20)'
            % (json.dumps(meta), json.dumps(WRAPPED_SPELL), CHAR_LEVEL))
        if not index:
            raise LookupError("the pinned catalog has no %s wrap" % meta)
        # skill 2 is the socketed spell inside the meta gem
        self.engine.eval_lua("return OPT_set_main(%d, 2)" % index)
        return self._save()

    def cast_wrapped(self) -> str:
        return self.wrapped("Cast on Critical")

    def cooldown(self) -> str:
        self._fresh()
        self._group("Frost Bomb")
        return self._save()

    def show_average(self) -> str:
        self._fresh()
        self._group("Incinerate")
        return self._save()


def build_fixture_documents(pob_root) -> dict[str, str]:
    """Every fixture document, keyed by name. One engine, then closed."""
    builder = FixtureBuilder(pob_root)
    by_wrapped_name = {wrapped_name(meta): meta for meta in META_GEMS}
    try:
        return {name: (builder.wrapped(by_wrapped_name[name])
                       if name in by_wrapped_name else getattr(builder, name)())
                for name in FIXTURE_ORDER}
    finally:
        builder.close()


# ----------------------------------------------------------------- evidence

def read_fixtures(pob_root, documents: dict[str, str]) -> dict:
    """Evaluate every fixture through the adapter and collect the outputs."""
    from pob2opt.domain.enums import Fidelity
    from pob2opt.evaluation import (ADAPTER_VERSION, BuildDocument, EngineAdapter, EngineState,
                                    pob_worker_spec, resolve_checkout)

    from record_fixtures import records

    checkout = resolve_checkout(pob_root)
    build = dataclasses.replace(records()["build_spec"],
                                build_hash="p02t04-primitive-fixture")
    # adapter_version is repinned for the same reason pob_commit is: P02-T02
    # made the adapter refuse a profile pinned to a different adapter, and the
    # shared fixture profile names neither this commit nor this adapter.
    profile = dataclasses.replace(records()["patch_profile"],
                                  pob_commit=checkout.commit,
                                  adapter_version=ADAPTER_VERSION)
    out: dict[str, dict] = {}
    adapter = EngineAdapter(pob_worker_spec(pob_root),
                            screen_timeout_s=600.0, detailed_timeout_s=600.0,
                            start_timeout_s=900.0)
    try:
        for name in FIXTURE_ORDER:
            document = BuildDocument(build.build_hash, documents[name])
            snapshot = adapter.primitives(build, EngineState(), profile,
                                          document=document,
                                          fidelity=Fidelity.DETAILED)
            out[name] = {
                "values": dict(snapshot.values),
                "show_average": snapshot.loaded.main_skill_show_average,
                "main_skill": snapshot.loaded.main_skill,
                "socket_groups": snapshot.loaded.socket_groups,
                "declared": {pid: {"value": d.value, "unit": d.unit}
                             for pid, d in sorted(snapshot.declared().items())},
                "gaps": sorted(g.primitive_id for g in snapshot.gaps()),
            }
        identity = adapter.identity()
    finally:
        adapter.close()
    return {"identity": {"pob_commit": identity.pob_commit,
                         "pob_dirty_hash": identity.pob_dirty_hash,
                         "adapter_version": identity.adapter_version,
                         "helper_lua_hashes": dict(identity.helper_lua_hashes)},
            "fixtures": out}


KEYS_OF_INTEREST = (
    "AverageDamage", "TotalDPS", "CombinedDPS", "FullDPS", "Speed", "Time",
    "Cooldown", "Duration", "TotalDot", "TotalDotDPS", "WithDotDPS",
    "HitChance", "CritChance", "ProjectileCount", "ManaCost",
    "ManaPerSecondCost", "AreaOfEffectRadius", "AreaOfEffectRadiusMetres",
    "Life", "TotalEHP")


def summarize(payload: dict) -> dict:
    """The comparisons the inventory actually rests on."""
    fixtures = payload["fixtures"]

    def value(name, key):
        return fixtures[name]["values"].get(key)

    base = fixtures["baseline"]["values"]
    return {
        "F-DPS": {
            "claim": "TotalDPS is AverageDamage multiplied by Speed",
            "AverageDamage": base.get("AverageDamage"),
            "Speed": base.get("Speed"),
            "product": (base.get("AverageDamage") or 0) * (base.get("Speed") or 0),
            "TotalDPS": base.get("TotalDPS"),
        },
        "F-ACC": {
            "claim": "AverageDamage already contains hit probability and crit",
            "baseline": {k: value("baseline", k)
                         for k in ("HitChance", "CritChance", "AverageDamage")},
            "accuracy": {k: value("accuracy", k)
                         for k in ("HitChance", "CritChance", "AverageDamage")},
        },
        "F-PROJ": {
            "claim": "projectile count does not multiply single-target damage",
            "baseline": {k: value("baseline", k)
                         for k in ("ProjectileCount", "AverageDamage", "TotalDPS")},
            "projectiles": {k: value("projectiles", k)
                            for k in ("ProjectileCount", "AverageDamage", "TotalDPS")},
        },
        "F-DOT": {
            "claim": "damage over time is a rate; duration does not change it",
            "dot": {k: value("dot", k)
                    for k in ("Duration", "TotalDot", "TotalDotDPS", "CombinedDPS")},
            "dot_longer": {k: value("dot_longer", k)
                           for k in ("Duration", "TotalDot", "TotalDotDPS", "CombinedDPS")},
        },
        "F-TRIG": {
            "claim": "a meta gem does not change the socketed spell's cadence",
            "cast_direct": {k: value("cast_direct", k)
                            for k in ("Speed", "Time", "TotalDPS", "AverageDamage")},
            "cast_wrapped": {k: value("cast_wrapped", k)
                             for k in ("Speed", "Time", "TotalDPS", "AverageDamage")},
            "cast_direct_main_skill": fixtures["cast_direct"]["main_skill"],
            "cast_wrapped_main_skill": fixtures["cast_wrapped"]["main_skill"],
            "every_meta_gem": {
                meta: {"main_skill": fixtures[wrapped_name(meta)]["main_skill"],
                       **{k: value(wrapped_name(meta), k)
                          for k in ("Speed", "TotalDPS", "AverageDamage")}}
                for meta in META_GEMS},
        },
        "F-CD": {
            "claim": "a cooldown becomes the use rate: Speed is 1/Cooldown",
            "cooldown": {k: value("cooldown", k)
                         for k in ("Cooldown", "Speed", "Time", "AverageDamage",
                                   "TotalDPS")},
        },
        "F-UNIT": {
            "claim": "CombinedDPS is damage per use when the skill sets showAverage",
            "show_average_flag": fixtures["show_average"]["show_average"],
            "show_average": {k: value("show_average", k)
                             for k in ("AverageDamage", "TotalDPS", "CombinedDPS",
                                       "FullDPS", "Speed")},
            "baseline_flag": fixtures["baseline"]["show_average"],
        },
        "F-COST": {
            "claim": "ManaPerSecondCost is ManaCost multiplied by Speed",
            "baseline": {k: value("baseline", k)
                         for k in ("ManaCost", "ManaPerSecondCost", "Speed")},
        },
        "F-AREA": {
            "claim": "PoB publishes both the raw radius and its own metre conversion",
            "baseline": {k: value("baseline", k)
                         for k in ("AreaOfEffectRadius", "AreaOfEffectRadiusMetres")},
        },
        "F-FULL": {
            "claim": "FullDPS aggregates groups and includes damage over time",
            "show_average": {k: value("show_average", k)
                             for k in ("TotalDPS", "TotalDotDPS", "FullDPS")},
        },
        "F-DEF": {
            "claim": "defensive outputs are present and named",
            "baseline": {k: value("baseline", k) for k in ("Life", "TotalEHP")},
        },
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default=str(
        REPO_ROOT / "docs" / "evidence" / "P02" / "primitives.json"))
    parser.add_argument("--pob-root", default=os.environ.get("POB2_ROOT"))
    args = parser.parse_args(argv)

    sys.path.insert(0, str(REPO_ROOT / "tests"))
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    root = Path(args.pob_root) if args.pob_root else (
        REPO_ROOT / "external" / "PathOfBuilding-PoE2")
    if not (root / "runtime" / "lua51.dll").is_file():
        out_path.write_text(json.dumps(
            {"status": "unavailable",
             "reason": "no PoB runtime at %s; set POB2_ROOT" % root,
             "kind": "PoB-derived, controlled fixture"}, indent=1) + "\n",
            encoding="utf-8")
        print("no PoB runtime at %s; wrote an unavailable record" % root,
              file=sys.stderr)
        return 3

    documents = build_fixture_documents(root)
    payload = read_fixtures(root, documents)
    payload["status"] = "ok"
    payload["kind"] = "PoB-derived, controlled fixture"
    payload["caveat"] = ("Engine agreement, not practical accuracy. No value "
                         "here is a gameplay measurement.")
    payload["summary"] = summarize(payload)
    payload["keys_of_interest"] = list(KEYS_OF_INTEREST)
    out_path.write_text(json.dumps(payload, indent=1, sort_keys=True) + "\n",
                        encoding="utf-8")
    print("wrote %s" % out_path, file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
