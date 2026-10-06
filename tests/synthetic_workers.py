"""Synthetic engine sessions for the offline P02-T01 lane.

These stand in for ``pob2opt.evaluation.worker.PobSession``. They answer the
same operations over the same pipe, so the adapter under test is the real one;
only the Lua state is absent. Nothing here loads PoB, touches the network or
pretends to produce engine values: every number is declared synthetic.

The module must stay importable by name, because a spawned worker imports it
from ``sys.path`` in the child process.
"""

from __future__ import annotations

import os
import sys
import time

SYNTHETIC_MARKER = "SYNTHETIC-NOT-POB"

#: Returned by ``primitives``. Invented, deterministic, and not a game value.
SYNTHETIC_VALUES = {"SyntheticTotal": 1234.5, "SyntheticSpeed": 2.0}


class SyntheticSession:
    """One configurable fake engine.

    ``behavior`` selects what it does instead of calculating:

    ``ok``            answer every operation
    ``wedge``         block forever on ``wedge_on``
    ``die``           leave the process immediately on ``die_on``
    ``startup_fail``  raise while being constructed

    ``slow_on``/``slow_s`` delay one operation without wedging it, which is
    how a bound that does not cover that operation becomes visible.
    """

    def __init__(self, config: dict) -> None:
        self.config = config
        self.behavior = config.get("behavior", "ok")
        self.wedge_on = config.get("wedge_on")
        self.die_on = config.get("die_on")
        self.slow_on = config.get("slow_on")
        self.slow_s = float(config.get("slow_s", 0.0))
        self.loaded_xml: str | None = None
        self.opt_setup_calls = 0
        self.closed = False

        if self.behavior == "startup_fail":
            raise RuntimeError(config.get("startup_message", "synthetic startup failure"))

        # A worker may relocate itself; the parent's directory is the one that
        # must not move. Doing it here makes that difference testable offline.
        chdir_to = config.get("chdir_to")
        if chdir_to:
            os.chdir(chdir_to)
        self.cwd = os.getcwd()

    # -- operations -------------------------------------------------------

    def handle(self, op: str, args: dict):
        self._maybe_wedge(op)
        self._maybe_die(op)
        if self.slow_on == op and self.slow_s:
            time.sleep(self.slow_s)
        if op == "describe":
            return {"pid": os.getpid(), "cwd": self.cwd,
                    "pob_root": self.config.get("pob_root") or SYNTHETIC_MARKER,
                    "synthetic": True}
        if op == "create_blank_build":
            self.opt_setup_calls += 1
            self.loaded_xml = None
            return self._summary(allocated=1, items=0, groups=0,
                                 opt_setup=True, level=args.get("level"))
        if op == "load_exact_build":
            xml = args.get("xml")
            if not isinstance(xml, str) or not xml.strip():
                from pob2opt.domain.enums import ResultStatus
                from pob2opt.evaluation.worker import SessionError
                raise SessionError(ResultStatus.INVALID_INPUT,
                                   "synthetic: build document is empty",
                                   stage="load_exact_build")
            self.loaded_xml = xml
            counts = self.config.get("loaded_counts") or {}
            return self._summary(allocated=counts.get("allocated", 7),
                                 items=counts.get("items", 2),
                                 groups=counts.get("groups", 3),
                                 opt_setup=False,
                                 level=counts.get("level", 28))
        if op == "primitives":
            values = dict(self.config.get("values") or SYNTHETIC_VALUES)
            for name, value in args.get("config") or []:
                values["config:" + name] = value
            keys = args.get("stat_keys")
            if keys:
                values = {k: values[k] for k in keys if k in values}
            return {"values": values, "stat_keys": sorted(values),
                    "summary": self._summary(
                        allocated=7, items=2, groups=3, opt_setup=False,
                        level=28)}
        from pob2opt.domain.enums import ResultStatus
        from pob2opt.evaluation.worker import SessionError
        raise SessionError(ResultStatus.UNSUPPORTED,
                           "synthetic session has no operation %r" % op,
                           stage="dispatch")

    def close(self) -> None:
        self.closed = True

    # -- plumbing ---------------------------------------------------------

    def _summary(self, *, allocated, items, groups, opt_setup, level):
        return {"buildName": SYNTHETIC_MARKER, "class": "SyntheticClass",
                "ascendancy": None, "level": level,
                "allocatedNodes": allocated, "equippedItems": items,
                "socketGroups": groups, "optSetupCalled": opt_setup}

    def _maybe_wedge(self, op: str) -> None:
        if self.behavior != "wedge" or op != self.wedge_on:
            return
        # No answer, ever. The parent's bound is the only thing that ends it,
        # which is exactly what the acceptance case measures.
        while True:
            time.sleep(3600)

    def _maybe_die(self, op: str) -> None:
        if self.behavior != "die" or op != self.die_on:
            return
        # Leave without unwinding: the closest offline stand-in for a native
        # crash, and the parent must notice through the pipe, not a message.
        sys.stdout.flush()
        os._exit(int(self.config.get("exit_code", 70)))


class StatefulFailureSession(SyntheticSession):
    """Mutates before nonfatal failure, so cached state must be invalidated."""

    def __init__(self, config):
        super().__init__(config)
        self.applied = {"setting": 7, "skill": 1}

    def handle(self, op, args):
        from pob2opt.domain.enums import ResultStatus
        from pob2opt.evaluation.worker import SessionError

        if op == "primitives":
            self.applied.update(dict(args.get("config") or []))
            if args.get("main_skill"):
                self.applied["skill"] = args["main_skill"][0]
                raise SessionError(ResultStatus.INTERNAL_ERROR, "partial mutation",
                                   stage=op)
            result = super().handle(op, args)
            result["values"] = dict(self.applied)
            return result
        result = super().handle(op, args)
        if op == "load_exact_build":
            self.applied = {"setting": 7, "skill": 1}
        if op == "create_blank_build" or args.get("name") == "fail_load":
            self.applied = {"setting": 999, "skill": 999}
            raise SessionError(ResultStatus.INTERNAL_ERROR, "partial mutation", stage=op)
        return result


class TimedStagesSession(SyntheticSession):
    """Independent delays per operation, reset on a new healthy worker."""

    def handle(self, op, args):
        time.sleep(self.config.get("stage_delays", {}).get(op, 0))
        return super().handle(op, args)
