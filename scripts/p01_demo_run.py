"""End-to-end P01 example: corpus, run bundle, tasks, interruption, resume.

    python scripts/p01_demo_run.py --out docs/evidence/P01/demo-run.json

Everything it touches is the synthetic record fixtures in
``tests/fixtures/records``. Nothing here contacts PoB, a provider or the
network, and no number it prints is a measurement.

What it demonstrates, in order:

1. a corpus ingests a source document; the same bytes a second time reuse
   the blob;
2. a run bundle is created and copies the records it needs into itself;
3. the corpus is deleted and the bundle is still fully readable;
4. three tasks are queued, one completes, one is interrupted mid-flight;
5. a checkpoint is written, then goes stale when the newer result commits;
6. resume recovers the interrupted task, keeps the completed one once, and a
   duplicate completion message changes nothing;
7. every documented inspection query is run and saved.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import tempfile
from dataclasses import replace
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "pob2-optimizer"))
sys.path.insert(0, str(REPO / "tests"))

from record_fixtures import blob_payloads, records  # noqa: E402

from pob2opt.domain import EvaluationKey, rotation_hash, scenario_hash  # noqa: E402
from pob2opt.domain.enums import Fidelity, TaskState  # noqa: E402
from pob2opt.storage import (  # noqa: E402
    RunBundle,
    RunStore,
    load_legacy_phase,
    read_checkpoint,
    resume_plan,
    run_all,
    validate_checkpoint,
    write_checkpoint,
)


def build(out: Path) -> dict:
    R = records()
    payload = blob_payloads()[R["source_document"].blob_hash]
    manifest = R["run_manifest"]
    steps: list[dict] = []

    corpus_root = out / "corpus"
    run_root = out / "runs" / manifest.run_id
    for path in (corpus_root, out / "runs"):
        if path.exists():
            shutil.rmtree(path)

    # 1. corpus ingestion -------------------------------------------------
    with RunStore.open_corpus(corpus_root) as corpus:
        first = corpus.ingest_source(payload, R["source_document"])
        second = corpus.ingest_source(payload, R["source_document"])
        for kind in ("game_catalog", "item_instance", "build_spec",
                     "scenario_spec", "rotation_policy", "mechanic_rule"):
            corpus.put_normalized(R[kind])
        corpus.put_gap(R["data_gap"])
        steps.append({
            "step": "ingest",
            "blob_hash": first.blob.blob_hash,
            "first_write_reused_an_existing_blob": first.blob.reused,
            "second_write_reused_an_existing_blob": second.blob.reused,
            "source_records": len(corpus.source_history("fixture_provider",
                                                        "FX-1")),
        })

    # 2. run bundle copies what it needs ----------------------------------
    with RunStore.open_corpus(corpus_root) as corpus, \
            RunBundle.create(run_root, manifest) as bundle:
        report = bundle.copy_references(
            corpus, source_ids=["fixture-source-1"],
            normalized_ids=["fixture-catalog-1", "fixture-item-1",
                            "fixture-build-1", "fixture-clear-dense",
                            "fixture-rotation-clear"])
        steps.append({"step": "copy_references", "sources": list(report.sources),
                      "normalized": list(report.normalized),
                      "blobs": list(report.blobs)})

    # 3. the corpus goes away ---------------------------------------------
    shutil.rmtree(corpus_root)

    with RunBundle.open(run_root) as bundle:
        steps.append({"step": "corpus_disconnected",
                      "self_check": bundle.self_check()})

        store, tasks = bundle.store, bundle.store.tasks
        key = EvaluationKey.from_manifest(
            manifest, build_hash=R["build_spec"].build_hash,
            rotation_hash=rotation_hash(R["rotation_policy"]),
            scenario_hash=scenario_hash(R["scenario_spec"]),
            fidelity=Fidelity.DETAILED)

        miss = store.lookup(key, run_id=manifest.run_id)
        steps.append({"step": "cold_cache", "outcome": miss.outcome.value,
                      "reason": miss.reason.value})

        # 4. three tasks, one completed, one interrupted -------------------
        for index in range(3):
            tasks.enqueue(task_id="demo-task-%d" % (index + 1),
                          run_id=manifest.run_id, generation_id=1,
                          candidate_id="demo-candidate-%d" % (index + 1),
                          payload={"build_hash": R["build_spec"].build_hash})

        checkpoint = replace(
            R["checkpoint"], manifest_hash=bundle.manifest_hash,
            completed_generation=0, next_generation_id=1,
            completed_task_ids=[],
            queued_task_ids=["demo-task-1", "demo-task-2", "demo-task-3"])
        write_checkpoint(bundle.root, checkpoint)
        validate_checkpoint(checkpoint, manifest_hash=bundle.manifest_hash,
                            run_id=manifest.run_id)

        tasks.dispatch("demo-task-1", worker_id="demo-worker-1")
        result = replace(R["evaluation_result"], cache_key=key.cache_key())
        store.commit_evaluation("demo-task-1", result, run_id=manifest.run_id)
        tasks.dispatch("demo-task-2", worker_id="demo-worker-2")
        # The coordinator is interrupted here: demo-task-2 is still running
        # and the checkpoint on disk still says nothing has completed.

        stale = read_checkpoint(bundle.root)
        steps.append({"step": "checkpoint_is_stale",
                      "checkpoint_completed_task_ids": stale.completed_task_ids,
                      "database_completed_task_ids":
                          [t.task_id for t in tasks.by_state(
                              manifest.run_id, TaskState.COMPLETED)]})

        # 5. resume ---------------------------------------------------------
        plan = resume_plan(tasks, manifest.run_id)
        repeat = store.commit_evaluation("demo-task-1", result,
                                         run_id=manifest.run_id)
        steps.append({"step": "resume",
                      "recovered_from_running": list(plan["recovered_from_running"]),
                      "to_dispatch": list(plan["to_dispatch"]),
                      "already_completed": list(plan["already_completed"]),
                      "duplicate_message_created_a_second_result": repeat.created,
                      "evaluation_rows": store.conn.execute(
                          "SELECT COUNT(*) FROM evaluation").fetchone()[0]})

        # 6. a historical phase output is readable but never reusable -----
        legacy_dir = out / "legacy"
        legacy_dir.mkdir(parents=True, exist_ok=True)
        legacy_file = legacy_dir / "gems.json"
        legacy_file.write_text(json.dumps(
            [{"gem": "SYNTHETIC Gem", "dps": 1234.0}], indent=1),
            encoding="utf-8")
        imported = load_legacy_phase(store, legacy_file)
        store.put_gap(R["data_gap"])
        steps.append({"step": "legacy_import", "phase": imported.phase,
                      "cache_eligible": imported.cache_eligible,
                      "blob_hash": imported.blob_hash})

        warm = store.lookup(key, run_id=manifest.run_id)
        screen = store.lookup(key.at_fidelity(Fidelity.SCREEN),
                              run_id=manifest.run_id)
        steps.append({"step": "warm_cache",
                      "detailed": [warm.outcome.value, warm.reason.value],
                      "screen": [screen.outcome.value, screen.reason.value]})

        queries = run_all(store.conn)

    return {"steps": steps, "inspection_queries": queries}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default="docs/evidence/P01/demo-run.json",
                        help="JSON file to write the recorded result to")
    parser.add_argument("--work", default=None,
                        help="where to build the demo corpus and run bundle; "
                             "a temporary directory by default, because the "
                             "databases themselves are not the evidence")
    args = parser.parse_args(argv)

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    if args.work:
        result = build(Path(args.work))
    else:
        with tempfile.TemporaryDirectory(prefix="pob2opt-p01-") as work:
            result = build(Path(work))
    out.write_text(
        json.dumps(result, indent=2, ensure_ascii=False, sort_keys=False) + "\n",
        encoding="utf-8", newline="\n")
    for step in result["steps"]:
        print("%-22s %s" % (step["step"],
                            json.dumps({k: v for k, v in step.items()
                                        if k != "step"})[:140]))
    print("\nwrote %s" % out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
