"""Re-run of the P01 review probes against the repaired revision.

    python docs/evidence/P01/review-repair-probes.py

The reviewer's original script is kept unchanged at `review-ae4303e-probes.py`
as evidence about commit `ae4303e`. This one asks the same questions of the
fixed code, keeping the observation keys identical so the two JSON files can
be read side by side.

Three probes had to change shape, because the behaviour they exercised is
what was repaired:

* `cancelled_completion` and the task probes need a bundle that holds the
  records an EvaluationResult references. On the reviewed revision any
  bundle accepted any result; now an empty one accepts none, which is the
  P01-R03 fix.
* `dangling_normalized_build` now expects `put_normalized` to refuse, so the
  insert is attempted and the refusal recorded.
* `aggregate_seed_collision` uses `AggregateKey.from_components`, since
  `from_manifest` was removed: an aggregate has no identity without the
  evaluations it was computed from (P01-R05).

All writes go to a new temporary directory. Nothing here is a measurement.
"""
from __future__ import annotations

import json
import sys
import tempfile
from dataclasses import replace
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
sys.path[:0] = [str(REPO / "pob2-optimizer"), str(REPO / "tests")]

from record_fixtures import records, seed_corpus  # noqa: E402

from pob2opt.domain import (  # noqa: E402
    AggregateComponent,
    AggregateKey,
    EvaluationKey,
    RecordIndex,
    rotation_hash,
    scenario_hash,
    validate_record,
)
from pob2opt.domain.enums import Fidelity  # noqa: E402
from pob2opt.storage import RunBundle, RunStore  # noqa: E402


def probe() -> dict:
    examples = records()
    manifest = examples["run_manifest"]
    result: dict = {}

    with tempfile.TemporaryDirectory(prefix="p01-repair-") as temporary:
        root = Path(temporary)

        with RunBundle.create(root / "tasks", manifest) as bundle:
            seed_corpus(bundle.store, with_results=False)
            tasks = bundle.store.tasks

            # P01-R01: a late result must not revive a cancelled task.
            tasks.enqueue(task_id="cancelled-task", run_id=bundle.run_id,
                          generation_id=1, candidate_id="candidate-a",
                          payload={})
            tasks.dispatch("cancelled-task", worker_id="old-worker")
            tasks.cancel("cancelled-task")
            before = tasks.get("cancelled-task").state.value
            try:
                bundle.store.commit_evaluation("cancelled-task",
                                               examples["evaluation_result"])
                refusal = None
            except Exception as exc:
                refusal = type(exc).__name__
            result["cancelled_completion"] = {
                "before": before,
                "after": tasks.get("cancelled-task").state.value,
                "refused_with": refusal,
                "evaluation_rows": bundle.store.conn.execute(
                    "SELECT COUNT(*) FROM evaluation").fetchone()[0],
            }

            # P01-R04: one candidate, two evaluation contexts.
            clear = EvaluationKey.from_manifest(
                manifest, build_hash=examples["build_spec"].build_hash,
                rotation_hash=rotation_hash(examples["rotation_policy"]),
                scenario_hash=scenario_hash(examples["scenario_spec"]),
                fidelity=Fidelity.DETAILED)
            boss = replace(clear, scenario_hash="c" * 64)
            tasks.enqueue(task_id="clear-task", run_id=bundle.run_id,
                          generation_id=2, candidate_id="same-build",
                          payload={"scenario_id": "clear"},
                          context_key=clear.cache_key())
            try:
                tasks.enqueue(task_id="boss-task", run_id=bundle.run_id,
                              generation_id=2, candidate_id="same-build",
                              payload={"scenario_id": "boss"},
                              context_key=boss.cache_key())
                result["second_scenario_task"] = {"accepted": True}
            except Exception as exc:
                result["second_scenario_task"] = {
                    "accepted": False, "error": type(exc).__name__,
                    "message": str(exc)}

        # P01-R03: a dangling build is refused, and an incomplete bundle is
        # not readable.
        with RunStore.open_corpus(root / "corpus") as corpus:
            build = examples["build_spec"]
            try:
                corpus.put_normalized(build)
                refused_paths = None
            except Exception as exc:
                refused_paths = sorted({e.field_path
                                        for e in exc.report.errors})
            result["dangling_normalized_build"] = {
                "inserted": corpus.conn.execute(
                    "SELECT COUNT(*) FROM normalized_record").fetchone()[0] > 0,
                "unresolved_paths": refused_paths,
            }

            corpus.put_normalized(build, require_references=False)
            with RunBundle.create(root / "bundle", manifest) as bundle:
                bundle.copy_references(corpus, normalized_ids=[build.record_id],
                                       transitive=False)
                check = bundle.self_check()
                result["incomplete_bundle"] = {
                    k: check[k] for k in
                    ("blobs_declared", "records_declared", "missing_blobs",
                     "missing_records", "readable")}
                result["incomplete_bundle"]["unresolved_reference_count"] = sum(
                    len(v) for v in check["unresolved_references"].values())

        # A complete bundle, by contrast, is readable without its corpus.
        with RunStore.open_corpus(root / "full") as corpus:
            seed_corpus(corpus, with_results=False)
            with RunBundle.create(root / "full-bundle", manifest) as bundle:
                report = bundle.copy_references(
                    corpus, normalized_ids=["fixture-build-1",
                                            "fixture-clear-dense"])
                result["transitive_copy"] = {
                    "asked_for": ["fixture-build-1", "fixture-clear-dense"],
                    "normalized_copied": len(report.normalized),
                    "sources_copied": len(report.sources),
                    "unresolved": report.unresolved,
                    "readable": bundle.self_check()["readable"],
                }

        # P01-R02: a null in a free-form field round trips through storage.
        item = examples["item_instance"]
        unknown = replace(item, record_id="fixture-item-null",
                          properties={**item.properties,
                                      "unknown_property": None})
        result["nullable_item"] = {"validation_ok": validate_record(unknown).ok}
        with RunStore.open_corpus(root / "nullable") as corpus:
            seed_corpus(corpus, with_results=False)
            result["nullable_item"]["stored"] = corpus.put_normalized(unknown)
            try:
                read_back = corpus.get_normalized(unknown.record_id)
                result["nullable_item"]["read_ok"] = True
                result["nullable_item"]["null_preserved"] = (
                    read_back.properties["unknown_property"] is None)
            except Exception as exc:
                result["nullable_item"].update(
                    read_ok=False, error=type(exc).__name__, message=str(exc))

    # P01-R03: reference fields the reviewer found unchecked.
    index = RecordIndex.from_records(examples.values())
    missing_references = {
        "patch_evidence": replace(examples["patch_profile"],
                                  patch_evidence_ids=["missing-evidence"]),
        "mechanic_dependency": replace(examples["mechanic_rule"],
                                       dependency_ids=["missing-mechanic"]),
        "manifest_snapshot": replace(examples["run_manifest"],
                                     source_snapshot_ids=["missing-snapshot"]),
    }
    result["unchecked_reference_fields"] = {}
    for label, record in missing_references.items():
        report = validate_record(record, index=index)
        result["unchecked_reference_fields"][label] = {
            "validation_ok": report.ok,
            "paths": [e.field_path for e in report.errors
                      if e.code == "unresolved_reference"],
        }

    # P01-R02: a wire value inside a dataclass is a report, not a crash.
    try:
        report = validate_record(replace(examples["evaluation_result"],
                                         status="ok"))
        result["string_enum_instance"] = {
            "raised": False, "ok": report.ok,
            "decoded_to_enum": report.record.status
            is examples["evaluation_result"].status}
    except Exception as exc:
        result["string_enum_instance"] = {
            "raised": True, "error": type(exc).__name__, "message": str(exc)}

    # P01-R05: the aggregate key moves with its constituent evaluations.
    other_seed = replace(manifest, rng_seed=manifest.rng_seed + 1)
    arguments = {"build_hash": examples["build_spec"].build_hash,
                 "rotation_hash": examples["evaluation_result"].rotation_hash}

    def aggregate(source_manifest):
        evaluation = EvaluationKey.from_manifest(
            source_manifest, **arguments, scenario_hash="1" * 64,
            fidelity=Fidelity.DETAILED)
        return AggregateKey.from_components(
            source_manifest, **arguments,
            components=[AggregateComponent.of("fixture-clear-dense",
                                              evaluation)]).cache_key()

    evaluation_a = EvaluationKey.from_manifest(
        manifest, **arguments, scenario_hash="1" * 64,
        fidelity=Fidelity.DETAILED).cache_key()
    evaluation_b = EvaluationKey.from_manifest(
        other_seed, **arguments, scenario_hash="1" * 64,
        fidelity=Fidelity.DETAILED).cache_key()
    result["aggregate_seed_collision"] = {
        "aggregate_keys_equal": aggregate(manifest) == aggregate(other_seed),
        "evaluation_keys_differ": evaluation_a != evaluation_b,
    }
    return result


if __name__ == "__main__":
    print(json.dumps(probe(), indent=2))
