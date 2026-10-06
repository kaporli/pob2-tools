"""Re-run the two defects the parallel probe file found, against HEAD."""
from __future__ import annotations

import dataclasses, json, os, pathlib, sys, time

REPO = pathlib.Path(__file__).resolve().parents[3]
for p in (REPO / "pob2-optimizer", REPO / "pob2-mcp", REPO / "tests",
          REPO / "docs" / "evidence" / "P02"):
    sys.path.insert(0, str(p))

from engine_helpers import FIXTURE_WEAPON
from record_fixtures import records
from pob2opt.domain.enums import Fidelity
from pob2opt.evaluation import (BuildDocument, EngineAdapter, EngineError,
                                EngineState, MappingBuildDocuments,
                                WorkerSpec, pob_worker_spec, resolve_checkout)

POB = pathlib.Path(os.environ["POB2_ROOT"])
H = "probe-b-build"
OUT = {}


def populated_xml():
    from pob2mcp.engine import Pob2Engine
    before = os.getcwd()
    e = Pob2Engine(str(POB))
    try:
        e.call("new_build")
        nodes = e.call("search_nodes", {"text": "projectile damage", "limit": 5})
        e.call("alloc_nodes", {"ids": [n["id"] for n in nodes[:2]]})
        e.call("equip_item", {"raw": FIXTURE_WEAPON, "slot": "Weapon 1"})
        return e.call("save_build_xml")["xml"]
    finally:
        e.close(); os.chdir(before)


def run():
    xml = populated_xml()
    malformed = (REPO / "tests/fixtures/builds/malformed_build.xml").read_text(
        encoding="utf-8")
    build = dataclasses.replace(records()["build_spec"], build_hash=H)
    profile = dataclasses.replace(records()["patch_profile"],
                                  pob_commit=resolve_checkout(POB).commit)

    # ---- A: state after a fatal load replaced the worker -----------------
    adapter = EngineAdapter(pob_worker_spec(POB),
                            documents=MappingBuildDocuments({H: xml}),
                            start_timeout_s=600, screen_timeout_s=300,
                            detailed_timeout_s=300)
    try:
        before = adapter.primitives(build, EngineState(), profile)
        try:
            adapter.load_exact_build(BuildDocument("bad", malformed))
        except EngineError as exc:
            failure = {"status": exc.status.value, "stage": exc.stage}
        after = adapter.primitives(build, EngineState(), profile)
        OUT["fatal_load_recovery"] = {
            "failure": failure,
            "before_loaded": dataclasses.asdict(before.loaded),
            "after_loaded": dataclasses.asdict(after.loaded),
            "after_reloaded": after.document.reloaded,
            "values_changed": before.values != after.values,
            "blank_after_recovery":
                (after.loaded.allocated_nodes <= 1
                 and after.loaded.equipped_items == 0),
        }
    finally:
        adapter.close()

    # ---- B: does the screen bound cover the load in the same call? -------
    spec = WorkerSpec(entry="review_eca7afe_workers:SlowLoadSession",
                      pob_root=None, extra={"behavior": "ok"})
    adapter = EngineAdapter(spec, documents=MappingBuildDocuments({H: xml}),
                            checkout=resolve_checkout(POB),
                            screen_timeout_s=0.1, detailed_timeout_s=300,
                            start_timeout_s=120)
    profile2 = dataclasses.replace(records()["patch_profile"],
                                   pob_commit=resolve_checkout(POB).commit)
    started = time.monotonic()
    try:
        snap = adapter.primitives(build, EngineState(), profile2,
                                  fidelity=Fidelity.SCREEN)
        OUT["synthetic_screen_deadline"] = {
            "returned_success": True,
            "elapsed_s": round(time.monotonic() - started, 3),
            "declared_screen_timeout_s": 0.1,
            "snapshot_timeout_s": snap.timeout_s,
            "snapshot_load_timeout_s": snap.load_timeout_s,
            "reported_duration_ms": snap.duration_ms,
        }
    except EngineError as exc:
        OUT["synthetic_screen_deadline"] = {
            "returned_success": False,
            "elapsed_s": round(time.monotonic() - started, 3),
            "declared_screen_timeout_s": 0.1,
            "status": exc.status.value, "stage": exc.stage,
        }
    finally:
        adapter.close()

    print(json.dumps(OUT, indent=1, default=str))


if __name__ == "__main__":
    run()
