"""Diagnostic pytest plugin: per-test/per-call evidence, never a production hook."""
import hashlib
import json
import os
import time
from pathlib import Path

import pytest
from pob2mcp.engine import Pob2Engine

OUT = Path(os.environ["POB2_TRACE_FILE"])
CALL = Pob2Engine.call


def log(**values):
    with OUT.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(dict(seconds=time.monotonic(), **values)) + "\n")


def traced_call(self, name, args=None):
    args = args or {}
    description = {k: (hashlib.sha256(v.encode()).hexdigest() if k == "xml"
                        else str(v)[:100]) for k, v in args.items()}
    log(event="call", name=name, args=description)
    result = CALL(self, name, args)
    heap = CALL(self, "eval", {"code": "return collectgarbage('count')"})
    log(event="return", name=name, lua_heap_kib=heap)
    return result


Pob2Engine.call = traced_call


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_protocol(item, nextitem):
    log(event="test_start", test=item.nodeid)
    yield
    log(event="test_end", test=item.nodeid)
