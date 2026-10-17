"""Bounded real-engine soak of the P02-T01.1 worker bound.

Usage: python soak_adapter.py NAME EVALUATIONS [LIMIT_MB RECYCLE_MB]

1. A fresh, unbounded worker probes f11-populated.xml once: the reference.
2. A bounded adapter repeats EVALUATIONS times: create_blank_build (OPT_setup
   on a fresh build), then probe the same document. This is the path that ran
   away in repro_f11 and base-noplugin-s11/s13.
3. Every successful probe is compared with the reference (1e-6 relative or
   1e-9 absolute). Every failure is recorded with its class and diagnostic.

No retries: a failed evaluation stays failed; the next evaluation gets a fresh
worker. One JSON line per evaluation and a summary go to soak/NAME.jsonl.
"""
import json
import math
import os
import sys
import time
from pathlib import Path

from pob2opt.evaluation import (BuildDocument, EngineAdapter, EngineError,
                                pob_worker_spec)

HERE = Path(__file__).resolve().parent
POB = os.environ.get("POB2_ROOT", "C:/Users/Elias/PycharmProjects/PathOfBuilding-PoE2")


def same(a, b):
    if a.keys() != b.keys():
        return False
    for key in a:
        x, y = a[key], b[key]
        if isinstance(x, (int, float)) and isinstance(y, (int, float)):
            if not (x == y or abs(x - y) <= max(1e-9, 1e-6 * max(abs(x), abs(y)))):
                return False
            if math.isnan(x) != math.isnan(y):
                return False
        elif x != y:
            return False
    return True


def main():
    name, evaluations = sys.argv[1], int(sys.argv[2])
    limit_mb = int(sys.argv[3]) if len(sys.argv) > 3 else 2048
    recycle_mb = int(sys.argv[4]) if len(sys.argv) > 4 else 1280
    out = HERE / "soak" / ("%s.jsonl" % name)
    out.parent.mkdir(exist_ok=True)
    if out.exists():
        sys.exit("soak %s exists; pick a new name" % name)
    document = BuildDocument("f11-populated",
                             (HERE / "f11-populated.xml").read_text(encoding="utf-8"))
    spec = pob_worker_spec(POB)

    def write(record):
        with out.open("a") as stream:
            stream.write(json.dumps(record) + "\n")

    with EngineAdapter(spec, memory_limit_bytes=None, recycle_after_bytes=None) as fresh:
        reference = fresh.probe(document)
        write({"event": "reference", "pid": fresh.worker_pid, "keys": len(reference)})

    started = time.monotonic()
    counts = {"ok": 0, "mismatch": 0}
    with EngineAdapter(spec, memory_limit_bytes=limit_mb * 2**20,
                       recycle_after_bytes=recycle_mb * 2**20) as adapter:
        for i in range(evaluations):
            t0 = time.monotonic()
            record = {"event": "evaluation", "i": i}
            try:
                adapter.create_blank_build(level=28)
                values = adapter.probe(document)
            except EngineError as exc:
                record.update(outcome=type(exc).__name__, status=exc.status.value,
                              stage=exc.stage, diagnostic=exc.diagnostic[:300])
                counts[type(exc).__name__] = counts.get(type(exc).__name__, 0) + 1
            else:
                match = same(values, reference)
                record.update(outcome="ok" if match else "mismatch")
                counts["ok" if match else "mismatch"] += 1
            record.update(pid=adapter.worker_pid, generation=adapter.generation,
                          seconds=round(time.monotonic() - t0, 2),
                          worker_memory=(adapter._handle.last_memory_bytes
                                         if adapter._handle is not None else None))
            write(record)
            if record["outcome"] == "EngineReplacementExhausted":
                break
        summary = {"event": "summary", "evaluations": evaluations, "counts": counts,
                   "limit_mb": limit_mb, "recycle_mb": recycle_mb,
                   "workers": len(adapter.worker_pids), "recycles": adapter.recycles,
                   "replacements": adapter.replacements,
                   "seconds": round(time.monotonic() - started, 1),
                   "history": adapter.worker_history}
    summary["history"] = adapter.worker_history
    write(summary)
    print(json.dumps({k: v for k, v in summary.items() if k != "history"}))


if __name__ == "__main__":
    main()
