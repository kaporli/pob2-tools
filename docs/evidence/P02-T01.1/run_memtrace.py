"""Run engine tests under memtrace with a pinned PYTHONHASHSEED and a hard guard.

Usage: python run_memtrace.py RUN_NAME SEED [pytest args...]
Every run keeps its own directory under runs/, failed or not.
POB2_RUN_REPO picks the checkout under test (default: this one).
POB2_PLUGIN=0 runs without the in-process plugin: the parent samples memory
and the -vv progress line every 0.5 s instead. The parent guard
kills the whole tree at limit + 1 GiB or the time limit, in case the in-process
watchdog cannot.
"""
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import psutil

HERE = Path(__file__).resolve().parent
REPO = Path(os.environ.get("POB2_RUN_REPO") or HERE.parents[2]).resolve()
PLUGIN = os.environ.get("POB2_PLUGIN", "1") != "0"
POB = os.environ.get("POB2_ROOT", "C:/Users/Elias/PycharmProjects/PathOfBuilding-PoE2")
LIMIT_MB = int(os.environ.get("POB2_MEM_LIMIT_MB", "3072"))
TIME_LIMIT_S = float(os.environ.get("POB2_TIME_LIMIT_S", "600"))


def main():
    name, seed, *pytest_args = sys.argv[1:]
    out = HERE / "runs" / name
    if out.exists():
        sys.exit("run %s already exists; pick a new name" % name)
    out.mkdir(parents=True)
    env = dict(os.environ, POB2_ROOT=POB, PYTHONHASHSEED=seed,
               POB2_MEMTRACE_DIR=str(out), POB2_MEM_LIMIT_MB=str(LIMIT_MB),
               PYTHONPATH=os.pathsep.join([str(REPO / "pob2-mcp"),
                                           str(REPO / "pob2-optimizer"), str(HERE)]))
    args = [sys.executable, "-m", "pytest", "-vv", "-p", "no:cacheprovider"] \
        + (["-p", "memtrace"] if PLUGIN else []) + (pytest_args or ["tests/engine"])
    samples = (out / "samples.jsonl").open("w")
    started = time.monotonic()
    with (out / "stdout.txt").open("w") as so, (out / "stderr.txt").open("w") as se:
        proc = subprocess.Popen(args, cwd=REPO, env=env, stdout=so, stderr=se)
        root = psutil.Process(proc.pid)
        peak, guard = 0, None
        while proc.poll() is None:
            try:
                total = root.memory_info().rss + sum(
                    c.memory_info().rss for c in root.children(recursive=True))
            except psutil.Error:
                total = 0
            peak = max(peak, total)
            elapsed = time.monotonic() - started
            lines = (out / "stdout.txt").read_text(errors="replace").splitlines()
            samples.write(json.dumps({"t": round(elapsed, 2), "tree_rss": total,
                                      "progress": lines[-1][:200] if lines else ""})
                          + "\n")
            samples.flush()
            if total > (LIMIT_MB + 1024) * 2**20 or elapsed > TIME_LIMIT_S:
                guard = "memory" if total > (LIMIT_MB + 1024) * 2**20 else "time"
                for p in [root] + root.children(recursive=True):
                    try:
                        p.kill()
                    except psutil.Error:
                        pass
                break
            time.sleep(0.5)
        proc.wait()
    samples.close()
    summary = {"run": name, "repo": str(REPO), "plugin": PLUGIN,
               "head": subprocess.run(["git", "-C", str(REPO), "rev-parse", "HEAD"],
                                      capture_output=True, text=True).stdout.strip(),
               "seed": seed, "args": args[1:], "exit_code": proc.returncode,
               "parent_guard": guard, "limit_mb": LIMIT_MB, "peak_tree_rss": peak,
               "elapsed_s": round(time.monotonic() - started, 1),
               "python": sys.version.split()[0]}
    tail = (out / "stdout.txt").read_text(errors="replace").strip().splitlines()[-1:]
    summary["last_line"] = tail[0] if tail else ""
    (out / "summary.json").write_text(json.dumps(summary, indent=2))
    print(json.dumps(summary))


if __name__ == "__main__":
    main()
