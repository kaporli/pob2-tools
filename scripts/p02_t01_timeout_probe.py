"""Drive one adapter failure case and report what happened as JSON (P02-T01).

This runs as its own process so a supervisor can impose a hard outer deadline
on it. If the adapter's bound does not work, this process hangs, the supervisor
kills the tree and the test fails. A test that only called the adapter
in-process would hang the whole suite instead of failing it, which is what the
acceptance case is written to prevent.

Usage:
    python scripts/p02_t01_timeout_probe.py --mode wedge --timeout 2.0

Modes:
    wedge   the worker never answers; expect a typed ``timeout``
    crash   the worker leaves without answering; expect a typed ``engine_crash``
    revive  crash, then prove the next request completes in a different process

Exit code 0 means the expected typed outcome was observed. Nothing here needs
PoB, the network or pytest. Only the public adapter API is used.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
for path in (REPO / "pob2-optimizer", REPO / "pob2-mcp", REPO / "tests"):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from pob2opt.evaluation import (BuildDocument, EngineAdapter, EngineCrash,  # noqa: E402
                                EngineTimeout, EngineState, CheckoutIdentity, WorkerSpec)
from pob2opt.evaluation.protocol import OP_CREATE_BLANK_BUILD  # noqa: E402

ENTRY = "synthetic_workers:SyntheticSession"
DOCUMENT = BuildDocument(build_hash="probe-build", xml="<SyntheticBuild/>")
EVALUATION_MODES = ("combined", "slow_load", "slow_primitives", "slow_identity",
                    "within_budget", "wedged_load")


def evaluation_probe(mode: str, bound: float) -> dict:
    """One evaluation budget, with an independent outer supervisor in pytest."""
    from record_fixtures import records

    examples = records()
    build, profile = examples["build_spec"], examples["patch_profile"]
    delays = {
        "combined": {"load_exact_build": 0.7, "primitives": 0.7},
        "slow_load": {"load_exact_build": 2},
        "slow_primitives": {"primitives": 2},
        "slow_identity": {"load_exact_build": 0.7, "describe": 0.7},
        "within_budget": {"load_exact_build": 0.1, "primitives": 0.1},
        "wedged_load": {},
    }[mode]
    extra = {"stage_delays": {op: seconds * bound for op, seconds in delays.items()}}
    if mode == "wedged_load":
        extra.update(behavior="wedge", wedge_on="load_exact_build")
    spec = WorkerSpec(entry="synthetic_workers:TimedStagesSession", extra=extra)
    checkout = CheckoutIdentity("SYNTHETIC", profile.pob_commit, None)
    document = BuildDocument(build.build_hash, "<SyntheticBuild/>")
    with EngineAdapter(spec, checkout=checkout, screen_timeout_s=bound,
                       detailed_timeout_s=bound * 4, start_timeout_s=60) as adapter:
        first_pid = adapter.restart_worker()  # Startup is separately bounded.
        start = time.monotonic()
        try:
            snapshot = adapter.primitives(build, EngineState(), profile, document=document)
            observed, stage = "success", None
        except EngineTimeout as exc:
            observed, stage = exc.status.value, exc.stage
        report = {"mode": mode, "observed": observed, "stage": stage,
                  "elapsed_s": time.monotonic() - start,
                  "worker_alive_after": adapter.worker_alive}
        if mode == "within_budget":
            report["ok"] = observed == "success" and report["elapsed_s"] < bound
            if observed == "success":
                report["timeout_s"] = snapshot.timeout_s
        else:
            report["ok"] = observed == "timeout" and not adapter.worker_alive
            adapter.spec = WorkerSpec(entry=ENTRY)
            recovered = adapter.primitives(build, EngineState(), profile, document=document)
            report["new_process"] = first_pid != recovered.identity.worker_pid
            report["reloaded"] = recovered.document.reloaded
            report["ok"] = report["ok"] and report["new_process"] and report["reloaded"]
        return report


def spec_for(mode: str) -> WorkerSpec:
    """Both failures are triggered by the same public call, not by a private one."""
    if mode == "wedge":
        extra = {"behavior": "wedge", "wedge_on": OP_CREATE_BLANK_BUILD}
    else:
        extra = {"behavior": "die", "die_on": OP_CREATE_BLANK_BUILD,
                 "exit_code": 70}
    return WorkerSpec(entry=ENTRY, pob_root=None, quiet=False, extra=extra)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=("wedge", "crash", "revive") + EVALUATION_MODES,
                        required=True)
    parser.add_argument("--timeout", type=float, default=2.0,
                        help="per-request bound the adapter must enforce")
    args = parser.parse_args(argv)

    if args.mode in EVALUATION_MODES:
        report = evaluation_probe(args.mode, args.timeout)
        print(json.dumps(report, sort_keys=True))
        return 0 if report["ok"] else 1

    expected = "timeout" if args.mode == "wedge" else "engine_crash"
    report = {"mode": args.mode, "timeout_s": args.timeout, "expected": expected,
              "parent_cwd_before": os.getcwd()}

    adapter = EngineAdapter(spec_for(args.mode),
                            screen_timeout_s=args.timeout,
                            detailed_timeout_s=args.timeout,
                            start_timeout_s=60.0)
    try:
        first_pid = adapter.identity().worker_pid
        report["first_worker_pid"] = first_pid
        try:
            adapter.create_blank_build(level=28)
        except (EngineTimeout, EngineCrash) as exc:
            report["observed"] = exc.status.value
            report["stage"] = exc.stage
            report["diagnostic"] = exc.diagnostic
        else:
            report["observed"] = "no_error"

        report["worker_alive_after"] = adapter.worker_alive
        report["parent_cwd_after"] = os.getcwd()

        if args.mode == "revive":
            loaded = adapter.load_exact_build(DOCUMENT)
            identity = adapter.identity()
            report["second_worker_pid"] = identity.worker_pid
            report["generation"] = identity.generation
            report["replacements"] = adapter.replacements
            report["new_process"] = identity.worker_pid != first_pid
            report["revived_load"] = {
                "allocated_nodes": loaded.allocated_nodes,
                "equipped_items": loaded.equipped_items,
                "socket_groups": loaded.socket_groups,
                "opt_setup_called": loaded.opt_setup_called,
            }
        report["worker_pids"] = list(adapter.worker_pids)
    finally:
        adapter.close()

    ok = (report.get("observed") == expected
          and not report["worker_alive_after"]
          and report["parent_cwd_after"] == report["parent_cwd_before"])
    if args.mode == "revive":
        ok = ok and bool(report.get("new_process"))
    report["ok"] = ok
    print(json.dumps(report, sort_keys=True))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
