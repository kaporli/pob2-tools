"""Independent offline review probes; argument is the checkout under review.

Catalog names and DPS below are synthetic, not gameplay evidence.
Print observations rather than asserting the buggy behavior as desirable.
"""
from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import tempfile

root = Path(sys.argv[1]).resolve()
sys.path[:0] = [str(root / "pob2-optimizer"), str(root / "tests")]

from objective_fixtures import v2_aggregate, v2_manifest, v2_request
from record_fixtures import seed_corpus
from pob2opt.catalog.scope import resolve_objective_scope
from pob2opt.domain import RECORD_TYPES, from_jsonable, validate_record
from pob2opt.domain.records import CatalogEntity
from pob2opt.domain.validation import aggregate_binding_errors
from pob2opt.storage import RunStore


def decode(kind, payload):
    return from_jsonable(RECORD_TYPES[kind], payload)


def entity(entity_id, name, raw=None):
    return CatalogEntity(entity_id=entity_id, display_names=[name], aliases=[],
                         raw_reference=raw or {}, rule_references=[])


flicker = "poe2/gems/fixture/Flicker"
other = "poe2/gems/fixture/UnrelatedSkill"
cls = "poe2/classes/fixture"
catalog = {
    "gems": [entity(flicker, "Flicker Strike"),
             entity(other, "Unrelated Skill")],
    "granted_skills": [],
    "classes": [entity(cls, "Fixture Class", {"classId": 1})],
    "ascendancies": [],
}
observations = {
    "python": sys.version,
    "checkout": str(root),
    "head": subprocess.check_output(
        ["git", "-C", str(root), "rev-parse", "HEAD"], text=True).strip(),
    "scope": [],
    "storage": [],
}
for ids in ([flicker], [other], [flicker, other]):
    payload = v2_request(target_skill_ids=ids)
    payload["class_scope"] = [{"class_id": cls, "ascendancy_ids": None}]
    validated = validate_record(payload, kind="run_request")
    scope = resolve_objective_scope(catalog, validated.raise_for_errors())
    observations["scope"].append({
        "target_skill_ids": ids, "request_valid": validated.ok,
        "scope_ok": scope.ok, "issues": [i.code for i in scope.issues],
    })

with tempfile.TemporaryDirectory(prefix="pr11-review-") as tmp:
    with RunStore.open(tmp) as store:
        seed_corpus(store)
        payload = v2_manifest()
        payload.update(record_id="review-run", run_id="review-run")
        manifest = decode("run_manifest", payload)
        store.put_run(manifest)
        for variant in ("wrong_hash", "wrong_objective", "legacy_aggregate"):
            data = v2_aggregate(record_id="review-" + variant,
                                aggregate_id="review-" + variant,
                                manifest_id=manifest.run_id)
            if variant == "wrong_hash":
                data["objective_hash"] = "d" * 64
            elif variant == "wrong_objective":
                data.update(objective_id="balanced_score", objective_metrics={},
                            objective_score=None, objective_gap_ids=["fixture-gap-1"])
            else:
                data["schema_version"] = 1
                for field in ("objective_version", "objective_hash",
                              "objective_metrics", "objective_score",
                              "objective_gap_ids"):
                    del data[field]
            agg = decode("aggregate_result", data)
            standalone = [e.code for e in aggregate_binding_errors(agg, manifest)]
            try:
                stored = store.put_normalized(agg)
                outcome = {"stored": stored,
                           "stored_validation_ok": store.validate_stored()[agg.record_id].ok}
            except Exception as exc:
                outcome = {"stored": False, "error": str(exc)}
            observations["storage"].append({
                "case": variant, "binding_errors": standalone, **outcome})

print(json.dumps(observations, indent=2))
