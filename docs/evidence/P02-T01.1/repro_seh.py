"""Bounded reproduction: in-process engine, Lua errors, faulthandler, a Python thread.

Usage: python repro_seh.py CONDITION ITERATIONS
CONDITION is one of: plain, fh, thread, fh+thread.
  fh      faulthandler.enable(all_threads=True) to a file, as tests/conftest.py does
  thread  a background thread running Python continuously, as a sampler would

Each iteration makes one Lua call that raises inside pcall (LuaJIT throws an
SEH exception for it on Windows) and one call that succeeds. Prints one JSON
line: iterations completed, access violations seen, private bytes before/after.
Exits on the first OSError so a corrupted state is not exercised further.
"""
import faulthandler
import json
import os
import sys
import tempfile
import threading
import time

from pob2mcp.engine import Pob2Engine, PobEngineError
from pob2opt.evaluation.memory import process_memory_bytes


def main():
    condition, iterations = sys.argv[1], int(sys.argv[2])
    log = None
    if "fh" in condition:
        log = open(os.path.join(tempfile.gettempdir(), "repro-seh-%d.log" % os.getpid()), "w")
        faulthandler.enable(file=log, all_threads=True)
    else:
        faulthandler.disable()
    engine = Pob2Engine(os.environ["POB2_ROOT"])
    stop = False
    if "thread" in condition:
        def spin():
            n = 0
            while not stop:
                n = sum(range(200)) + n % 7
                time.sleep(0)
        threading.Thread(target=spin, daemon=True).start()
    before = process_memory_bytes(os.getpid())
    started = time.monotonic()
    done, failure = 0, None
    for _ in range(iterations):
        try:
            engine.call("eval", {"code": "error('repro')"})
        except PobEngineError:
            pass
        except OSError as exc:
            failure = str(exc)
            break
        try:
            engine.call("eval", {"code": "return 1"})
        except OSError as exc:
            failure = str(exc)
            break
        done += 1
    stop = True
    print(json.dumps({"condition": condition, "iterations": iterations, "completed": done,
                      "failure": failure, "private_before": before,
                      "private_after": process_memory_bytes(os.getpid()),
                      "seconds": round(time.monotonic() - started, 2),
                      "fault_log_bytes": (log.tell() if log else None)}))
    sys.stdout.flush()
    os._exit(0)


if __name__ == "__main__":
    main()
