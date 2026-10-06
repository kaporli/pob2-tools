"""Independent review probes for PR #3 at ae4303e, not production tests.

Run from the repo root with a configured development interpreter:
    python docs/evidence/P01/review-ae4303e-probes.py

All writes are inside a newly created temporary directory. The script prints
observed behavior; the accompanying review states the required behavior.
"""
from __future__ import annotations

import json
import sys
import tempfile
from dataclasses import replace
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
sys.path[:0] = [str(REPO / "pob2-optimizer"), str(REPO / "tests")]

from record_fixtures import records
from pob2opt.domain import (
    AggregateKey, EvaluationKey, RecordIndex, validate_record,
)
from pob2opt.domain.enums import Fidelity
from pob2opt.storage import RunBundle, RunStore


def probe():
    examples = records()
    result = {}
    with tempfile.TemporaryDirectory(prefix="p01-review-") as temporary:
        root = Path(temporary)
        with RunBundle.create(root / "tasks", examples["run_manifest"]) as bundle:
            tasks = bundle.store.tasks
            tasks.enqueue(task_id="cancelled-task", run_id=bundle.run_id,
                          generation_id=1, candidate_id="candidate-a", payload={})
            tasks.dispatch("cancelled-task", worker_id="old-worker")
            tasks.cancel("cancelled-task")
            before = tasks.get("cancelled-task").state.value
            bundle.store.commit_evaluation("cancelled-task", examples["evaluation_result"])
            result["cancelled_completion"] = {
                "before": before, "after": tasks.get("cancelled-task").state.value,
            }
            tasks.enqueue(task_id="clear-task", run_id=bundle.run_id,
                          generation_id=2, candidate_id="same-build",
                          payload={"scenario_id": "clear"})
            try:
                tasks.enqueue(task_id="boss-task", run_id=bundle.run_id,
                              generation_id=2, candidate_id="same-build",
                              payload={"scenario_id": "boss"})
                result["second_scenario_task"] = {"accepted": True}
            except Exception as exc:
                result["second_scenario_task"] = {
                    "accepted": False, "error": type(exc).__name__, "message": str(exc),
                }

        with RunStore.open_corpus(root / "corpus") as corpus:
            build = examples["build_spec"]
            inserted = corpus.put_normalized(build)
            errors = corpus.validate_stored()[build.record_id]
            result["dangling_normalized_build"] = {
                "inserted": inserted, "unresolved_paths": list(errors.paths()),
            }
            with RunBundle.create(root / "bundle", examples["run_manifest"]) as bundle:
                bundle.copy_references(corpus, normalized_ids=[build.record_id])
                result["incomplete_bundle"] = bundle.self_check()

        item = examples["item_instance"]
        unknown = replace(item, properties={**item.properties, "unknown_property": None})
        result["nullable_item"] = {"validation_ok": validate_record(unknown).ok}
        with RunStore.open_corpus(root / "nullable") as corpus:
            result["nullable_item"]["stored"] = corpus.put_normalized(unknown)
            try:
                corpus.get_normalized(unknown.record_id)
                result["nullable_item"]["read_ok"] = True
            except Exception as exc:
                result["nullable_item"].update(
                    read_ok=False, error=type(exc).__name__, message=str(exc))

    index = RecordIndex.from_records(examples.values())
    missing_references = {
        "patch_evidence": replace(examples["patch_profile"],
                                  patch_evidence_ids=["missing-evidence"]),
        "mechanic_dependency": replace(examples["mechanic_rule"],
                                       dependency_ids=["missing-mechanic"]),
        "manifest_snapshot": replace(examples["run_manifest"],
                                     source_snapshot_ids=["missing-snapshot"]),
    }
    result["unchecked_reference_fields"] = {
        label: {"validation_ok": (report := validate_record(record, index=index)).ok,
                "paths": list(report.paths())}
        for label, record in missing_references.items()
    }
    try:
        validate_record(replace(examples["evaluation_result"], status="ok"))
        result["string_enum_instance"] = {"raised": False}
    except Exception as exc:
        result["string_enum_instance"] = {
            "raised": True, "error": type(exc).__name__, "message": str(exc),
        }

    manifest = examples["run_manifest"]
    other_seed = replace(manifest, rng_seed=manifest.rng_seed + 1)
    arguments = {"build_hash": examples["build_spec"].build_hash,
                 "rotation_hash": examples["evaluation_result"].rotation_hash}
    aggregate_a = AggregateKey.from_manifest(manifest, **arguments).cache_key()
    aggregate_b = AggregateKey.from_manifest(other_seed, **arguments).cache_key()
    evaluation_a = EvaluationKey.from_manifest(
        manifest, **arguments, scenario_hash="1" * 64, fidelity=Fidelity.DETAILED).cache_key()
    evaluation_b = EvaluationKey.from_manifest(
        other_seed, **arguments, scenario_hash="1" * 64, fidelity=Fidelity.DETAILED).cache_key()
    result["aggregate_seed_collision"] = {
        "aggregate_keys_equal": aggregate_a == aggregate_b,
        "evaluation_keys_differ": evaluation_a != evaluation_b,
    }
    return result


if __name__ == "__main__":
    print(json.dumps(probe(), indent=2))
