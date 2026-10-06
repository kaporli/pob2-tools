"""Record what the P02-T01 engine boundary actually did (not a test).

Writes `docs/evidence/P02/lifecycle.json`. Two sections:

``synthetic``   the offline lane: wedged worker, dead worker, replacement.
                No PoB, no network. Nothing here is a game value.
``pob``         the real engine, when a checkout is configured. Identity,
                exact load versus blank build, A-B-A agreement and forced
                termination. PoB-derived, still not a gameplay measurement.

Usage:
    python scripts/p02_t01_evidence.py [--out PATH]
    POB2_ROOT must be set (or the submodule present) for the ``pob`` section.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
for path in (REPO / "pob2-optimizer", REPO / "pob2-mcp", REPO / "tests"):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from engine_helpers import FIXTURE_WEAPON  # noqa: E402
from pob2opt.evaluation import (ADAPTER_VERSION, BuildDocument, EngineAdapter,  # noqa: E402
                                EngineCrash, EngineError, EngineState,
                                kill_process_tree, pob_worker_spec,
                                resolve_checkout)

DEFAULT_OUT = REPO / "docs" / "evidence" / "P02" / "lifecycle.json"
PROBE = REPO / "scripts" / "p02_t01_timeout_probe.py"
PROBE_DEADLINE_S = 90.0
REL_TOLERANCE = 1e-6
ABS_TOLERANCE = 1e-9


def run_probe(mode: str) -> dict:
    completed = subprocess.run(
        [sys.executable, str(PROBE), "--mode", mode, "--timeout", "2.0"],
        cwd=str(REPO), capture_output=True, text=True, timeout=PROBE_DEADLINE_S)
    report = json.loads(completed.stdout.strip().splitlines()[-1])
    report["exit_code"] = completed.returncode
    return report


def synthetic_section() -> dict:
    return {
        "what_this_is": "Synthetic workers from tests/synthetic_workers.py. No "
                        "PoB, no network, no game value.",
        "hard_outer_deadline_s": PROBE_DEADLINE_S,
        "probes": {mode: run_probe(mode) for mode in ("wedge", "crash", "revive")},
    }


def resolve_pob_root() -> Path | None:
    env = os.environ.get("POB2_ROOT")
    candidates = [Path(env)] if env else []
    candidates.append(REPO / "external" / "PathOfBuilding-PoE2")
    for candidate in candidates:
        if (candidate / "runtime" / "lua51.dll").is_file():
            return candidate.resolve()
    return None


def populated_xml(pob_root: Path) -> str:
    """A build with tree, gear and a socket group, saved by PoB itself."""
    from pob2mcp.engine import Pob2Engine

    before = os.getcwd()
    engine = Pob2Engine(str(pob_root))
    try:
        engine.call("new_build")
        nodes = engine.call("search_nodes", {"text": "projectile damage", "limit": 5})
        engine.call("alloc_nodes", {"ids": [n["id"] for n in nodes[:2]]})
        engine.call("equip_item", {"raw": FIXTURE_WEAPON, "slot": "Weapon 1"})
        return engine.call("save_build_xml")["xml"]
    finally:
        engine.close()
        os.chdir(before)


def compare(first: dict, second: dict) -> dict:
    worst_rel, worst_abs, worst_key = 0.0, 0.0, None
    mismatched = []
    for key, value in first.items():
        other = second.get(key)
        if isinstance(value, (int, float)) and not isinstance(value, bool) \
                and isinstance(other, (int, float)):
            delta = abs(float(other) - float(value))
            rel = delta / abs(float(value)) if value else 0.0
            if delta > worst_abs or rel > worst_rel:
                worst_abs, worst_rel, worst_key = max(worst_abs, delta), \
                    max(worst_rel, rel), key
            if delta > ABS_TOLERANCE and rel > REL_TOLERANCE:
                mismatched.append(key)
        elif other != value:
            mismatched.append(key)
    return {"compared_keys": len(first), "worst_key": worst_key,
            "worst_absolute_delta": worst_abs, "worst_relative_delta": worst_rel,
            "keys_outside_tolerance": mismatched,
            "within_tolerance": not mismatched}


def pob_section(pob_root: Path) -> dict:
    import dataclasses

    from record_fixtures import records

    checkout = resolve_checkout(pob_root)
    xml = populated_xml(pob_root)
    stronger = xml.replace("60 to 90", "120 to 180")
    build_hash = "p02t01-evidence-build"
    build = dataclasses.replace(records()["build_spec"], build_hash=build_hash)
    profile = dataclasses.replace(records()["patch_profile"],
                                  pob_commit=checkout.commit)

    parent_cwd_before = os.getcwd()
    adapter = EngineAdapter(pob_worker_spec(pob_root), start_timeout_s=600.0,
                            screen_timeout_s=300.0, detailed_timeout_s=300.0)
    out: dict = {"what_this_is": "PoB-derived engine behaviour. Deterministic "
                                 "primitive agreement only; not a gameplay "
                                 "measurement and not a performance claim.",
                 "parent_cwd_before": parent_cwd_before}
    try:
        identity = adapter.identity()
        out["identity"] = {
            "pob_root": identity.pob_root, "pob_commit": identity.pob_commit,
            "pob_dirty_hash": identity.pob_dirty_hash,
            "dirty_reason": checkout.reason,
            "adapter_version": identity.adapter_version,
            "worker_cwd": identity.worker_cwd, "is_pinned": identity.is_pinned}
        out["worker_cwd_differs_from_parent"] = (
            identity.worker_cwd != parent_cwd_before)

        document = BuildDocument(build_hash, xml)
        exact = adapter.load_exact_build(document)
        out["load_exact_build"] = dataclasses.asdict(exact)
        blank = adapter.create_blank_build(level=28)
        out["create_blank_build"] = dataclasses.asdict(blank)

        first = adapter.primitives(build, EngineState(), profile, document=document)
        adapter.load_exact_build(BuildDocument("p02t01-evidence-b", stronger))
        second = adapter.primitives(build, EngineState(), profile, document=document)
        out["aba"] = {
            "b_document": "the same build with a stronger fixture weapon",
            "tolerance": {"relative": REL_TOLERANCE, "absolute": ABS_TOLERANCE},
            "agreement": compare(dict(first.values), dict(second.values)),
            "semantics_status": first.semantics_status,
            "semantics_owner": first.semantics_owner,
        }

        first_pid = adapter.identity().worker_pid
        kill_process_tree(first_pid, adapter._handle.process)
        killed: dict = {"killed_pid": first_pid}
        try:
            adapter.load_exact_build(document)
        except EngineCrash as exc:
            killed["observed"] = exc.status.value
            killed["diagnostic"] = exc.diagnostic
        except EngineError as exc:  # pragma: no cover - would be a defect
            killed["observed"] = exc.status.value
            killed["diagnostic"] = exc.diagnostic
        else:
            killed["observed"] = "no_error"
        revived = adapter.load_exact_build(document)
        killed["replacement_pid"] = adapter.identity().worker_pid
        killed["new_process"] = killed["replacement_pid"] != first_pid
        killed["replacement_completed_the_task"] = dataclasses.asdict(revived)
        out["forced_termination"] = killed
        out["worker_pids"] = list(adapter.worker_pids)
        out["replacements"] = adapter.replacements
    finally:
        adapter.close()
    out["parent_cwd_after"] = os.getcwd()
    out["parent_cwd_unchanged"] = out["parent_cwd_after"] == parent_cwd_before
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args(argv)

    report = {
        "schema_version": 1,
        "task": "P02-T01",
        "specification_version": "1.0",
        "adapter_version": ADAPTER_VERSION,
        "recorded_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "synthetic": synthetic_section(),
    }
    pob_root = resolve_pob_root()
    if pob_root is None:
        report["pob"] = {"status": "unavailable",
                         "reason": "no usable PathOfBuilding-PoE2 runtime; set "
                                   "POB2_ROOT or restore the submodule"}
    else:
        report["pob"] = pob_section(pob_root)
        report["pob"]["status"] = "recorded"

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=1, sort_keys=True) + "\n",
                        encoding="utf-8")
    print("wrote %s" % args.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
