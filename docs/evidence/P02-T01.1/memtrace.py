"""Diagnostic pytest plugin for P02-T01.1. Evidence only, never a production hook.

Per test: process-tree memory at start, end and peak, plus the engine call in
flight. A watchdog thread samples every 0.25 s; above POB2_MEM_LIMIT_MB it
writes the in-flight call and every thread's Python stack, then exits 97.
ctypes releases the GIL during the native call, so the watchdog still runs
while Lua is busy.
"""
import faulthandler
import hashlib
import json
import os
import threading
import time
from pathlib import Path

import psutil
import pytest
from pob2mcp.engine import Pob2Engine

OUT = Path(os.environ["POB2_MEMTRACE_DIR"])
OUT.mkdir(parents=True, exist_ok=True)
LIMIT = int(os.environ.get("POB2_MEM_LIMIT_MB", "3072")) * 2**20
LOG = (OUT / "tests.jsonl").open("a", encoding="utf-8")
SELF = psutil.Process()

state = {"test": None, "call": None, "calls": 0, "peak": 0}
lock = threading.Lock()


def tree_rss():
    total, own = 0, 0
    try:
        own = SELF.memory_info().rss
        total = own
        for child in SELF.children(recursive=True):
            try:
                total += child.memory_info().rss
            except psutil.Error:
                pass
    except psutil.Error:
        pass
    return total, own


def log(**values):
    with lock:
        LOG.write(json.dumps(dict(t=round(time.monotonic(), 3), **values)) + "\n")
        LOG.flush()


def describe(args):
    out = {}
    for key, value in (args or {}).items():
        text = value if isinstance(value, str) else json.dumps(value, default=str)
        out[key] = ("sha256:" + hashlib.sha256(text.encode()).hexdigest()[:16]
                    if len(text) > 120 else text)
    return out


CALL = Pob2Engine.call


def traced_call(self, name, args=None):
    state["calls"] += 1
    state["call"] = {"fn": name, "args": describe(args), "since": time.monotonic(),
                     "n": state["calls"], "where": "in-process"}
    try:
        return CALL(self, name, args)
    finally:
        state["call"] = None


Pob2Engine.call = traced_call

try:
    from pob2opt.evaluation.adapter import WorkerHandle
    REQUEST = WorkerHandle.request

    def traced_request(self, op, args, timeout_s):
        state["call"] = {"fn": op, "args": describe(args), "since": time.monotonic(),
                         "where": "worker pid %s" % self.pid}
        try:
            return REQUEST(self, op, args, timeout_s)
        finally:
            state["call"] = None

    WorkerHandle.request = traced_request
except ImportError:
    pass


def watchdog():
    while True:
        total, own = tree_rss()
        state["peak"] = max(state["peak"], total)
        if total > LIMIT:
            call = state["call"]
            age = None if call is None else round(time.monotonic() - call["since"], 3)
            log(event="limit", test=state["test"], tree_rss=total, own_rss=own,
                call=call, call_age_s=age)
            with (OUT / "stacks.txt").open("w", encoding="utf-8") as stream:
                stream.write("test: %s\ncall: %s\nage: %s\n\n" % (state["test"], call, age))
                stream.flush()
                faulthandler.dump_traceback(file=stream, all_threads=True)
            LOG.close()
            for child in SELF.children(recursive=True):
                try:
                    child.kill()
                except psutil.Error:
                    pass
            os._exit(97)
        time.sleep(0.25)


threading.Thread(target=watchdog, name="memtrace-watchdog", daemon=True).start()


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_protocol(item, nextitem):
    total, own = tree_rss()
    state["test"] = item.nodeid
    state["peak"] = total
    log(event="start", test=item.nodeid, tree_rss=total, own_rss=own)
    started = time.monotonic()
    yield
    total, own = tree_rss()
    log(event="end", test=item.nodeid, tree_rss=total, own_rss=own,
        peak=state["peak"], seconds=round(time.monotonic() - started, 3))
