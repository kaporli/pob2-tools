"""Independent synthetic PR13 boundary probes. No PoB or game output.

The fast-reply and unreadable-probe cases inject coordinator measurements;
the startup failures use real spawned synthetic workers. JSON is observation,
not a claim that the observed behavior is correct.
"""
from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import time
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[3]
CHECKOUT = ROOT / ".venv/pr13-review"
sys.path[:0] = [str(CHECKOUT / "pob2-optimizer"), str(CHECKOUT / "tests"),
                str(Path(__file__).resolve().parent)]

from pob2opt.evaluation import (BuildDocument, CheckoutIdentity, EngineAdapter,
                                EngineError, WorkerSpec)
from pob2opt.evaluation import adapter as module
from synthetic_workers import SyntheticSession

MB = 2**20


class SlowStartup(SyntheticSession):
    def __init__(self, config):
        time.sleep(0.4)
        super().__init__(config)


def adapter(entry="synthetic_workers:SyntheticSession", **kwargs):
    extra = kwargs.pop("extra", {})
    return EngineAdapter(
        WorkerSpec(entry=entry, quiet=True, extra=extra),
        checkout=CheckoutIdentity(root="SYNTHETIC", commit="1" * 40,
                                  dirty_hash=None, reason=None),
        start_timeout_s=5, screen_timeout_s=3, recycle_after_bytes=None,
        **kwargs)


def run():
    out = {"head": subprocess.check_output(
        ["git", "-C", str(CHECKOUT), "rev-parse", "HEAD"], text=True).strip(),
           "python": sys.version, "cases": {}}
    with adapter(memory_limit_bytes=80 * MB,
                 extra={"grow_on": "primitives", "grow_mb": 80}) as engine:
        try:
            engine.identity()
            engine.probe(BuildDocument("synthetic", "<SyntheticBuild/>"))
            outcome = {"returned_result": True,
                       "measured_bytes": engine._handle.sample_memory()}
        except EngineError as exc:
            outcome = {"error": type(exc).__name__}
        outcome.update(alive=engine.worker_alive, hard_limit_bytes=80 * MB)
        out["cases"]["actual_allocation_fast_reply"] = outcome
    for name, measured in (("fast_over_limit_reply", 500 * MB),
                           ("unreadable_probe", None)):
        with adapter(memory_limit_bytes=400 * MB) as engine:
            engine.identity()  # Warm the real synthetic worker.
            with patch.object(module, "process_memory_bytes", return_value=measured):
                try:
                    result = engine.probe(BuildDocument("synthetic", "<SyntheticBuild/>"))
                    outcome = {"returned_result": bool(result), "error": None}
                except EngineError as exc:
                    outcome = {"error": type(exc).__name__}
                outcome.update(alive=engine.worker_alive,
                               last_memory_bytes=engine._handle.last_memory_bytes,
                               hard_limit_bytes=400 * MB)
            out["cases"][name] = outcome

    with adapter(memory_limit_bytes=400 * MB,
                 extra={"slow_on": "describe", "slow_s": 0.3}) as engine:
        with patch.object(module, "process_memory_bytes", return_value=None) as sample:
            try:
                engine.identity()
                result = {"returned_result": True}
            except EngineError as exc:
                result = {"error": type(exc).__name__}
            result.update(samples=sample.call_count, alive=engine.worker_alive)
        out["cases"]["unreadable_during_wait"] = result

    with adapter(memory_limit_bytes=None, max_consecutive_failures=2,
                 extra={"behavior": "startup_fail"}) as engine:
        errors = []
        for _ in range(5):
            try:
                engine.identity()
            except EngineError as exc:
                errors.append(type(exc).__name__)
        out["cases"]["repeated_startup_failure"] = {
            "errors": errors, "generation": engine.generation,
            "failures": engine.consecutive_failures,
            "history": list(engine.worker_history)}

    with adapter(memory_limit_bytes=None, max_consecutive_failures=2,
                 extra={"values": 3}) as engine:
        errors = []
        for _ in range(5):
            try:
                # The synthetic handler raises TypeError converting values
                # to a dict; worker_main sends a fatal INTERNAL_ERROR reply.
                engine.probe(BuildDocument("synthetic", "<SyntheticBuild/>"))
            except EngineError as exc:
                errors.append(type(exc).__name__)
        out["cases"]["repeated_fatal_reply"] = {
            "errors": errors, "generation": engine.generation,
            "failures": engine.consecutive_failures,
            "history": list(engine.worker_history)}

    with adapter(entry="review_probes:SlowStartup", memory_limit_bytes=1,
                 max_consecutive_failures=2) as engine:
        errors = []
        for _ in range(3):
            try:
                engine.identity()
            except EngineError as exc:
                errors.append({"type": type(exc).__name__, "message": str(exc)})
        out["cases"]["startup_memory_history"] = {
            "errors": errors, "generation": engine.generation,
            "failures": engine.consecutive_failures,
            "history": list(engine.worker_history), "pids": list(engine.worker_pids)}
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    run()
