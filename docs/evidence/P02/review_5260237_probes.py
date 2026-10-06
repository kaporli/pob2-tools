"""Independent follow-up probes. Set POB2_ROOT and run this file.

Real-engine cases use synthetic fixture inputs; no gameplay claim is made.
"""
from __future__ import annotations

import json
import os
import sys
import time
from dataclasses import asdict, replace
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
sys.path[:0] = [str(REPO / p) for p in
               ("pob2-optimizer", "pob2-mcp", "tests", "scripts")]
sys.path.insert(0, str(Path(__file__).resolve().parent))

from record_fixtures import records
from p02_t01_evidence import populated_xml
from synthetic_workers import SyntheticSession
from pob2opt.evaluation import (BuildDocument, CheckoutIdentity, EngineAdapter,
                                EngineError, EngineState, WorkerSpec,
                                pob_worker_spec, resolve_checkout)


class TwoSlowStages(SyntheticSession):
    def handle(self, op, args):
        if op in ("load_exact_build", "primitives"):
            time.sleep(0.6)
        return super().handle(op, args)


def real_probe():
    root = Path(os.environ["POB2_ROOT"]).resolve()
    checkout = resolve_checkout(root)
    xml = populated_xml(root)
    build = records()["build_spec"]
    profile = replace(records()["patch_profile"], pob_commit=checkout.commit)
    document = BuildDocument(build.build_hash, xml)
    out = {"checkout": asdict(checkout)}
    with EngineAdapter(pob_worker_spec(root), start_timeout_s=300,
                       screen_timeout_s=120, detailed_timeout_s=120) as adapter:
        def evaluate(state=EngineState()):
            return adapter.primitives(build, state, profile, document=document)

        baseline = evaluate()
        overridden = evaluate(EngineState(config={"enemyLevel": 120}))
        restored = evaluate()
        out["successful_state_aba"] = {
            "b_differs": baseline.values != overridden.values,
            "a_restored": baseline.values == restored.values}

        before_pid = adapter.worker_pid
        try:
            adapter.load_exact_build(BuildDocument("bad", "<broken>"))
        except EngineError as exc:
            out["malformed_load_error"] = exc.status.value
        recovered = evaluate()
        out["fatal_load_recovery"] = {
            "pid_changed": before_pid != adapter.worker_pid,
            "a_restored": baseline.values == recovered.values,
            "loaded": asdict(recovered.loaded)}

        try:
            evaluate(EngineState(config={"enemyLevel": 120}, main_skill=(999999, 1)))
            failure = None
        except EngineError as exc:
            failure = {"status": exc.status.value, "stage": exc.stage}
        after_failure = evaluate()
        adapter.load_exact_build(document)
        after_reload = evaluate()
        out["partial_state_failure"] = {
            "error": failure,
            "baseline_dps": baseline.values.get("TotalDPS"),
            "next_empty_state_dps": after_failure.values.get("TotalDPS"),
            "explicit_reload_dps": after_reload.values.get("TotalDPS"),
            "reloaded_after_failure": after_failure.document.reloaded,
            "reported_state": after_failure.state_applied,
            "changed_keys": sum(baseline.values.get(k) != v
                                for k, v in after_failure.values.items()),
        }
    return out


def deadline_probe():
    build = records()["build_spec"]
    profile = records()["patch_profile"]
    checkout = CheckoutIdentity("SYNTHETIC", profile.pob_commit, None)
    spec = WorkerSpec(entry="review_5260237_probes:TwoSlowStages")
    with EngineAdapter(spec, checkout=checkout, screen_timeout_s=1.0,
                       detailed_timeout_s=3, start_timeout_s=30) as adapter:
        adapter.identity()  # Startup does not consume the measured budget.
        started = time.monotonic()
        try:
            result = adapter.primitives(build, EngineState(), profile,
                                        document=BuildDocument(build.build_hash, "synthetic"))
            return {"returned_success": True, "elapsed_s": time.monotonic() - started,
                    "timeout_s": result.timeout_s, "load_timeout_s": result.load_timeout_s,
                    "duration_ms": result.duration_ms}
        except EngineError as exc:
            return {"returned_success": False, "error": exc.status.value,
                    "elapsed_s": time.monotonic() - started}


if __name__ == "__main__":
    report = {"real_engine": real_probe(), "synthetic_deadline": deadline_probe()}
    Path(__file__).with_suffix(".json").write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
