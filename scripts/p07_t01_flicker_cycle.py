"""flicker_sustained_v1 for the seed through the P07 evaluator (P07-T01).

    python scripts/p07_t01_flicker_cycle.py            # offline, frozen bundle
    python scripts/p07_t01_flicker_cycle.py --live     # two fresh engine workers

Offline: values from ``docs/evidence/P09-T01.2/replay.json``; writes
``docs/evidence/P07-T01/seed-evaluation.json`` (scoring document, Pounce
disabled) and ``seed-as-imported-evaluation.json`` (Pounce on, diagnostic).

``--live``: captures the values twice, each through its own ``EngineAdapter``
and therefore its own worker processes, on the clean pinned checkout;
evaluates both; requires identical results; compares them with the frozen
bundle. Writes ``docs/evidence/P07-T01/fresh-worker-agreement.json``.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
for _pkg in (REPO / "pob2-mcp", REPO / "pob2-optimizer"):
    if str(_pkg) not in sys.path:
        sys.path.insert(0, str(_pkg))

from pob2opt.combat import evaluate_flicker, from_replay, load_p09_resolutions  # noqa: E402
from pob2opt.combat.values import capture  # noqa: E402

SEED = REPO / "docs/evidence/P09-T01.1/seed/export-flicker-main.xml"
REPLAY = REPO / "docs/evidence/P09-T01.2/replay.json"
REPLAY_REF = "docs/evidence/P09-T01.2/replay.json"
OUT = REPO / "docs/evidence/P07-T01"
PIN = "ce566eac45ea8a86477f513c7ee65a1ebe60014e"


def write(name: str, payload: dict) -> Path:
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / name
    path.write_text(json.dumps(payload, indent=1, sort_keys=True, ensure_ascii=False) + "\n",
                    encoding="utf-8", newline="\n")
    return path


def header(kind: str, live: bool = False) -> dict:
    return {"task": "P07-T01", "kind": kind,
            "not_a_claim": "PoB-derived computation by method pob-community-v2 (owner decision, "
                           "D07 amendment 2026-10-18 (2)). Not a gameplay measurement and not "
                           "a best-build recommendation.",
            "command": "python scripts/p07_t01_flicker_cycle.py" + (" --live" if live else ""),
            "build": str(SEED.relative_to(REPO)).replace("\\", "/")}


def offline() -> int:
    xml = SEED.read_text(encoding="utf-8")
    replay = json.loads(REPLAY.read_text(encoding="utf-8"))
    p09 = load_p09_resolutions()
    for name, document in (("seed-evaluation.json", "benchmark"),
                           ("seed-as-imported-evaluation.json", "seed")):
        values = from_replay(replay, document=document, replay_ref=REPLAY_REF)
        result = evaluate_flicker(xml, values, p09_resolutions=p09)
        payload = {**header("evaluation from frozen engine bundle"), "document": document,
                   **result.to_json()}
        path = write(name, payload)
        d = result.diagnostic
        print("%s: %s; diagnostic sustained %.0f burst %.0f; %d blocking"
              % (path.relative_to(REPO).as_posix(), result.status, d["flicker_sustained_dps"],
                 d["flicker_burst_dps"], len(result.decision["blocking"])))
    return 0


def _strip(values: dict) -> dict:
    out = dict(values)
    out["engine"] = {k: v for k, v in values["engine"].items() if k != "worker_pids"}
    out["trace"] = {}
    return out


def _rel(a, b):
    if isinstance(a, (int, float)) and isinstance(b, (int, float)) and not isinstance(a, bool):
        return 0.0 if a == b else abs(a - b) / max(abs(a), abs(b), 1e-300)
    return 0.0 if a == b else math.inf


def live() -> int:
    from pob2opt.evaluation import EngineAdapter, pob_worker_spec, resolve_checkout

    root = Path(os.environ.get("POB2_ROOT") or REPO / "external" / "PathOfBuilding-PoE2").resolve()
    checkout = resolve_checkout(root)
    if checkout.commit != PIN or checkout.dirty_hash is not None or checkout.reason is not None:
        raise SystemExit("refusing: %s is not a clean checkout of %s" % (root, PIN))
    xml = SEED.read_text(encoding="utf-8")
    p09 = load_p09_resolutions()
    runs = []
    for label in ("A", "B"):
        adapter = EngineAdapter(pob_worker_spec(root), start_timeout_s=600.0,
                                screen_timeout_s=300.0, detailed_timeout_s=300.0,
                                require_pinned_checkout=True, max_requests_per_worker=4)
        try:
            values = capture(adapter, xml, document="benchmark", build_hash="p07-t01/" + label)
        finally:
            adapter.close()
            history = list(adapter.worker_history)
            pids = list(adapter.worker_pids)
        result = evaluate_flicker(xml, values, p09_resolutions=p09)
        runs.append({"label": label, "worker_pids": pids, "worker_history": history,
                     "values": values.to_json(), "evaluation": result.to_json()})
    a, b = runs
    same_values = _strip(a["values"]) == _strip(b["values"])
    ea, eb = dict(a["evaluation"]), dict(b["evaluation"])
    for e in (ea, eb):
        e["values"] = _strip(e["values"])
    same_eval = ea == eb
    disjoint = not set(a["worker_pids"]) & set(b["worker_pids"])
    frozen = from_replay(json.loads(REPLAY.read_text(encoding="utf-8")), document="benchmark",
                         replay_ref=REPLAY_REF).to_json()
    keys = [k for k in frozen if k not in ("trace", "engine", "flasks", "document")
            and frozen[k] is not None]
    vs_frozen = {k: {"live": a["values"][k], "frozen": frozen[k],
                     "rel_diff": _rel(a["values"][k], frozen[k])} for k in keys}
    flasks_equal = a["values"]["flasks"] == frozen["flasks"]
    agreement = {"values_identical": same_values, "evaluations_identical": same_eval,
                 "worker_pid_sets_disjoint": disjoint,
                 "evaluation_ids": [a["evaluation"]["evaluation_id"],
                                    b["evaluation"]["evaluation_id"]],
                 "flasks_equal_frozen_bundle": flasks_equal,
                 "max_rel_diff_vs_frozen_bundle": max(v["rel_diff"] for v in vs_frozen.values())}
    after = resolve_checkout(root)
    payload = {**header("live fresh-worker agreement", live=True),
               "engine_root": "external/PathOfBuilding-PoE2", "engine_head": checkout.commit,
               "working_tree_before": "clean",
               "working_tree_after": "clean" if after.dirty_hash is None and after.reason is None
               else "DIRTY",
               "agreement": agreement, "vs_frozen_bundle": vs_frozen,
               "runs": [{"label": r["label"], "worker_pids": r["worker_pids"],
                         "worker_history": r["worker_history"], "values": r["values"],
                         "status": r["evaluation"]["status"],
                         "diagnostic_sustained": r["evaluation"]["diagnostic"]["flicker_sustained_dps"],
                         "diagnostic_burst": r["evaluation"]["diagnostic"]["flicker_burst_dps"],
                         "evaluation_id": r["evaluation"]["evaluation_id"]} for r in runs]}
    path = write("fresh-worker-agreement.json", payload)
    print("%s: values identical %s, evaluations identical %s, pids disjoint %s, max rel diff "
          "vs frozen %.3g" % (path.relative_to(REPO).as_posix(), same_values, same_eval,
                              disjoint, agreement["max_rel_diff_vs_frozen_bundle"]))
    return 0 if same_values and same_eval and disjoint else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--live", action="store_true")
    sys.exit(live() if parser.parse_args().live else offline())
