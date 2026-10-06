"""Adversarial probes against P02-T01 as committed at eca7afe.

Kept as the review evidence for that commit. Run against a later
revision, probes 1, 2, 4, 5, 6 and 7 should report the repaired
behaviour; the pre-repair answers are in
review-eca7afe-adversarial.json.

    POB2_ROOT=... python docs/evidence/P02/review-eca7afe-adversarial-probes.py
"""
from __future__ import annotations

import dataclasses
import json
import os
import sys
import pathlib
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
for p in (REPO / "pob2-optimizer", REPO / "pob2-mcp", REPO / "tests"):
    sys.path.insert(0, str(p))

from engine_helpers import FIXTURE_WEAPON
from record_fixtures import records
from pob2opt.evaluation import (BlobBuildDocuments, BuildDocument, EngineAdapter,
                                EngineState, MappingBuildDocuments,
                                pob_worker_spec, resolve_checkout)

POB = Path(os.environ["POB2_ROOT"])
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
    XML = populated_xml()
    STRONGER = XML.replace("60 to 90", "120 to 180")
    assert STRONGER != XML
    H = "probe-build"
    build = dataclasses.replace(records()["build_spec"], build_hash=H)
    profile = dataclasses.replace(records()["patch_profile"],
                                  pob_commit=resolve_checkout(POB).commit)
    docs = MappingBuildDocuments({H: XML})

    adapter = EngineAdapter(pob_worker_spec(POB), documents=docs,
                            start_timeout_s=600, screen_timeout_s=300,
                            detailed_timeout_s=300)
    try:
        # ---- PROBE 1: does the B document actually change the numbers? -------
        a1 = adapter.primitives(build, EngineState(), profile)
        b = adapter.primitives(build, EngineState(), profile,
                               document=BuildDocument(H, STRONGER))
        a2 = adapter.primitives(build, EngineState(), profile,
                                document=BuildDocument(H, XML))
        OUT["probe1_b_differs"] = {
            "a1_TotalDPS": a1.values.get("TotalDPS"),
            "b_TotalDPS": b.values.get("TotalDPS"),
            "a2_TotalDPS": a2.values.get("TotalDPS"),
            "b_actually_differs": b.values.get("TotalDPS") != a1.values.get("TotalDPS"),
            "a1_equals_a2": a1.values == a2.values,
            "note": "the committed A-B-A test never reads B's values at all",
        }

        # ---- PROBE 2: does engine configuration leak between evaluations? ----
        adapter.load_exact_build(BuildDocument(H, XML))
        base = adapter.primitives(build, EngineState(), profile,
                                  document=BuildDocument(H, XML))
        cfg = adapter.primitives(build, EngineState(config={"enemyIsBoss": "Boss"}),
                                 profile, document=BuildDocument(H, XML))
        after = adapter.primitives(build, EngineState(), profile,
                                   document=BuildDocument(H, XML))
        changed = {k: (base.values.get(k), cfg.values.get(k))
                   for k in base.values
                   if base.values.get(k) != cfg.values.get(k)}
        leaked = {k: (base.values.get(k), after.values.get(k))
                  for k in base.values
                  if base.values.get(k) != after.values.get(k)}
        OUT["probe2_config_leak"] = {
            "keys_changed_by_config": len(changed),
            "sample_changed": dict(list(changed.items())[:5]),
            "keys_still_changed_after_empty_state": len(leaked),
            "sample_leaked": dict(list(leaked.items())[:5]),
            "leaks": bool(leaked),
        }

        # ---- PROBE 3: does an unrelated document get evaluated as the build? -
        other = XML.replace('level="28"', 'level="60"') if 'level="28"' in XML else XML
        snap = adapter.primitives(build, EngineState(), profile,
                                  document=BuildDocument(H, STRONGER))
        OUT["probe3_document_identity"] = {
            "build_hash": build.build_hash,
            "document_hash_used": H,
            "note": "BlobBuildDocuments sets document.build_hash from the same "
                    "BuildSpec, so the equality check can never fail for the "
                    "production store",
            "loaded_class": snap.loaded.class_name,
            "spec_class_id": build.class_id,
            "classes_agree": snap.loaded.class_name == build.class_id,
        }
    finally:
        adapter.close()

    # ---- PROBE 4: several raw blobs, silently index 0 --------------------------
    from pob2opt.storage.blobs import BlobStore
    import tempfile
    tmp = Path(tempfile.mkdtemp())
    store = BlobStore(tmp)
    first = store.put(b"<PathOfBuilding2>FIRST</PathOfBuilding2>")
    second = store.put(b"<PathOfBuilding2>SECOND</PathOfBuilding2>")
    multi = dataclasses.replace(records()["build_spec"],
                                raw_blob_hashes=[first.blob_hash, second.blob_hash])
    doc = BlobBuildDocuments(store).document_for(multi)
    OUT["probe4_multiple_blobs"] = {
        "blob_count": 2,
        "chosen": doc.blob_hash == first.blob_hash and "first",
        "xml": doc.xml,
        "note": "no rule declared; index 0 wins silently",
    }

    # ---- PROBE 5: a storage defect reported as invalid_input -------------------
    class BrokenStore:
        def get(self, h):
            raise TypeError("a defect in the caller, not a bad document")

    try:
        BlobBuildDocuments(BrokenStore()).document_for(records()["build_spec"])
    except Exception as exc:
        OUT["probe5_broken_store"] = {
            "raised": type(exc).__name__,
            "status": getattr(exc, "status", None) and exc.status.value,
            "diagnostic": getattr(exc, "diagnostic", str(exc)),
            "note": "a TypeError inside the store is reported as invalid_input",
        }

    # ---- PROBE 6: stale checkout cache ----------------------------------------
    import subprocess, shutil
    repo = tmp / "chk"
    repo.mkdir()
    (repo / "a.txt").write_text("x")
    git = shutil.which("git")
    env = dict(os.environ, GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@e.invalid",
               GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@e.invalid")
    for argv in (["init", "-q"], ["add", "a.txt"], ["commit", "-qm", "x"]):
        subprocess.run([git, "-C", str(repo), *argv], check=True, capture_output=True, env=env)
    clean = resolve_checkout(repo)
    (repo / "b.txt").write_text("appeared mid-run")
    again = resolve_checkout(repo)
    OUT["probe6_stale_cache"] = {
        "clean_dirty_hash": clean.dirty_hash,
        "after_modification_dirty_hash": again.dirty_hash,
        "still_reports_clean": again.dirty_hash is None,
        "uncached": resolve_checkout(repo, use_cache=False).dirty_hash is not None,
    }

    # ---- PROBE 7: helper Lua is not part of the engine identity ---------------
    spec_a = pob_worker_spec(POB)
    OUT["probe7_identity_inputs"] = {
        "helper_lua_in_spec": [Path(p).name for p in spec_a.helper_lua],
        "identity_fields": [f.name for f in dataclasses.fields(
            __import__("pob2opt.evaluation.protocol", fromlist=["x"]).EngineIdentity)],
        "note": "helper Lua is injected into every engine but appears in no identity field",
    }

    print(json.dumps(OUT, indent=1, default=str))


if __name__ == '__main__':
    run()
