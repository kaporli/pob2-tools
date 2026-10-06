"""One engine, one process (P02-T01).

A worker owns exactly one PoB Lua state. It never shares it, never hands a
pointer back, and never continues after the state has been declared unhealthy:
the parent replaces the whole process instead. Native crashes therefore cannot
be papered over by resetting Lua tables.

The worker is free to change its own working directory - that is the existing
engine's documented requirement (research F10). The parent's directory is the
one that must not move, which is why the engine may only be built in here.

``worker_main`` is the spawn entry point, so it must stay importable and
top-level. ``entry`` names the session factory as ``module:attribute``; the
offline tests point it at a synthetic session and never load PoB.
"""

from __future__ import annotations

import importlib
import os
import sys
import traceback
from typing import Any

from ..domain.enums import ResultStatus
from . import protocol
from .errors import redact_diagnostic

#: PoB's Lua writes progress text straight to the process stdout handle. The
#: parent's pipe is a separate object, so silencing this cannot corrupt framing.
_QUIET_DEFAULT = True


def resolve_session_factory(entry: str):
    """Import ``module:attribute``. Anything else is a coordinator defect."""
    if ":" not in entry:
        raise ValueError("worker entry must be 'module:attribute', got %r" % entry)
    module_name, _, attribute = entry.partition(":")
    module = importlib.import_module(module_name)
    try:
        return getattr(module, attribute)
    except AttributeError:
        raise ValueError("%s has no attribute %r" % (module_name, attribute)) from None


class SessionError(Exception):
    """Raised by a session to choose the reported status explicitly.

    ``fatal`` means the Lua state can no longer be trusted, so the parent must
    discard the process rather than send it another request.
    """

    def __init__(self, status: ResultStatus, diagnostic: str, *,
                 stage: str, fatal: bool = False) -> None:
        self.status = status
        self.diagnostic = diagnostic
        self.stage = stage
        self.fatal = fatal
        super().__init__(diagnostic)


class PobSession:
    """The real session: boots PoB and answers the typed operations."""

    def __init__(self, config: dict) -> None:
        self.pob_root = config["pob_root"]
        self.helper_lua = list(config.get("helper_lua") or ())
        self.default_stat_keys = config.get("default_stat_keys")
        self.healthy = True
        # Read before boot: the engine changes this process's directory, so a
        # relative helper path resolved afterwards would silently point into
        # someone else's checkout.
        self._helper_sources = [
            (os.path.basename(path), _read_text(path)) for path in self.helper_lua]
        self._cwd_before_boot = os.getcwd()

        from pob2mcp.engine import Pob2Engine, PobEngineError

        self._engine_error = PobEngineError
        self.engine = Pob2Engine(self.pob_root)
        self.cwd = os.getcwd()

    # -- operations -------------------------------------------------------

    def handle(self, op: str, args: dict) -> Any:
        if not self.healthy:
            raise SessionError(ResultStatus.ENGINE_CRASH,
                               "engine state was declared unhealthy", stage=op,
                               fatal=True)
        if op == protocol.OP_DESCRIBE:
            return self.describe()
        if op == protocol.OP_CREATE_BLANK_BUILD:
            return self.create_blank_build(**args)
        if op == protocol.OP_LOAD_EXACT_BUILD:
            return self.load_exact_build(**args)
        if op == protocol.OP_PRIMITIVES:
            return self.primitives(**args)
        if op == protocol.OP_CATALOG_PAGE:
            return self.catalog_page(**args)
        raise SessionError(ResultStatus.UNSUPPORTED,
                           "unknown operation %r" % op, stage="dispatch")

    def describe(self) -> dict:
        return {"pid": os.getpid(), "cwd": self.cwd, "pob_root": self.pob_root,
                "cwd_before_boot": self._cwd_before_boot,
                "helper_lua": [name for name, _ in self._helper_sources]}

    def create_blank_build(self, level: int, resist_penalty: int = 0) -> dict:
        """A clean optimization base. This one is *meant* to clear the build."""
        self._call("new_build", {}, stage=protocol.OP_CREATE_BLANK_BUILD)
        self._load_helpers(protocol.OP_CREATE_BLANK_BUILD)
        self._eval("return OPT_setup(%d, %d)" % (int(level), int(resist_penalty)),
                   stage=protocol.OP_CREATE_BLANK_BUILD)
        summary = self._call("get_build_info", {},
                             stage=protocol.OP_CREATE_BLANK_BUILD)
        summary["optSetupCalled"] = True
        return summary

    def load_exact_build(self, xml: str, name: str = "exact") -> dict:
        """Load a build document as it is. Never calls ``OPT_setup``.

        ``OPT_setup`` resets the tree, disables every socket group and empties
        every slot (research F11), which is the correct preparation for a blank
        candidate and completely wrong for evaluating someone's build.
        """
        if not isinstance(xml, str) or not xml.strip():
            raise SessionError(ResultStatus.INVALID_INPUT,
                               "build document is empty",
                               stage=protocol.OP_LOAD_EXACT_BUILD)
        try:
            summary = self.engine.call("load_build_xml", {"xml": xml, "name": name})
        except self._engine_error as exc:
            # The engine already replaced the build with whatever the failed
            # load left behind, so this state is not reusable.
            self.healthy = False
            raise SessionError(ResultStatus.INVALID_INPUT, str(exc),
                               stage=protocol.OP_LOAD_EXACT_BUILD,
                               fatal=True) from None
        self._load_helpers(protocol.OP_LOAD_EXACT_BUILD)
        summary["optSetupCalled"] = False
        return summary

    def primitives(self, config=None, main_skill=None, stat_keys=None) -> dict:
        stage = protocol.OP_PRIMITIVES
        for name, value in (config or []):
            self._call("set_config", {"name": name, "value": value}, stage=stage)
        if main_skill:
            group, skill = main_skill
            self._call("set_main_skill", {"group": group, "skill": skill}, stage=stage)
        keys = stat_keys or self.default_stat_keys
        args = {"all": True} if keys is None else {"keys": list(keys)}
        values = self._call("get_stats", args, stage=stage)
        summary = self._call("get_build_info", {}, stage=stage)
        return {"values": values, "summary": summary,
                "stat_keys": sorted(values) if keys is None else list(keys)}

    def catalog_page(self, table: str, offset: int = 0,
                     limit: int = protocol.CATALOG_PAGE_ROWS) -> dict:
        """Read one page of a catalog table (P02-T02).

        Read-only: the handlers behind this never touch the build, so a
        catalog read in the middle of an evaluation cannot change what the
        next primitive read returns. An unknown table is refused here rather
        than passed to the engine as a handler name.
        """
        stage = protocol.OP_CATALOG_PAGE
        if table == protocol.CATALOG_RULE_SOURCES:
            return self._call(protocol.CATALOG_RULE_SOURCES_HANDLER, {},
                              stage=stage)
        handler = protocol.CATALOG_HANDLERS.get(table)
        if handler is None:
            raise SessionError(
                ResultStatus.UNSUPPORTED,
                "unknown catalog table %r; known tables are %s"
                % (table, ", ".join(sorted(protocol.CATALOG_HANDLERS))),
                stage=stage)
        return self._call(handler, {"offset": int(offset), "limit": int(limit)},
                          stage=stage)

    def close(self) -> None:
        close = getattr(self.engine, "close", None)
        if close is not None:
            close()

    # -- plumbing ---------------------------------------------------------

    def _load_helpers(self, stage: str) -> None:
        for name, source in self._helper_sources:
            self._eval(source, stage="%s:%s" % (stage, name))

    def _call(self, fn: str, args: dict, *, stage: str):
        try:
            return self.engine.call(fn, args)
        except self._engine_error as exc:
            raise SessionError(ResultStatus.INTERNAL_ERROR, str(exc),
                               stage="%s:%s" % (stage, fn)) from None

    def _eval(self, code: str, *, stage: str):
        try:
            return self.engine.eval_lua(code)
        except self._engine_error as exc:
            raise SessionError(ResultStatus.INTERNAL_ERROR, str(exc),
                               stage=stage) from None


def _read_text(path: str) -> str:
    with open(path, "r", encoding="utf-8") as handle:
        return handle.read()


# -- spawn entry point --------------------------------------------------------

def _silence_stdout() -> None:
    """Point this process's stdout at the null device, file descriptor and all.

    Rebinding ``sys.stdout`` is not enough: PoB's Lua writes through the OS
    handle, so its startup text lands on the inherited descriptor and
    corrupts a parent that writes JSON to its own stdout. The worker never
    answers on stdout, so nothing is lost. Failure is not fatal: the engine
    still works, the parent's stdout is just noisy, and saying so on stderr
    is better than refusing to evaluate.
    """
    try:
        sys.stdout.flush()
    except (ValueError, OSError) as exc:
        # Nothing buffered is worth reporting: stdout is about to become the
        # null device, and a closed or detached stream here means there was
        # no output to lose. Named rather than swallowed (P02-T01-R09).
        del exc
    try:
        null = os.open(os.devnull, os.O_WRONLY)
        try:
            os.dup2(null, 1)
        finally:
            os.close(null)
    except OSError as exc:
        print("pob2opt worker: could not silence stdout (%s); engine output "
              "may reach the parent's stdout" % exc, file=sys.stderr)
    sys.stdout = open(os.devnull, "w")


def worker_main(entry: str, conn, config: dict) -> None:
    """Serve requests until shutdown, a fatal session error or a broken pipe."""
    if config.get("quiet", _QUIET_DEFAULT):
        _silence_stdout()

    try:
        session = resolve_session_factory(entry)(config)
    except BaseException as exc:  # startup failure is still a typed answer
        _send(conn, {"seq": 0, "ok": False,
                     "code": ResultStatus.INTERNAL_ERROR.value, "stage": "startup",
                     "diagnostic": redact_diagnostic(
                         "%s: %s" % (type(exc).__name__, exc)),
                     "traceback": redact_diagnostic(traceback.format_exc()),
                     "fatal": True})
        conn.close()
        return

    _send(conn, {"seq": 0, "ok": True, "result": {"ready": True, "pid": os.getpid()}})

    while True:
        try:
            request = conn.recv()
        except (EOFError, OSError):
            break
        seq = request.get("seq", -1)
        op = request.get("op")
        if op == protocol.OP_SHUTDOWN:
            _close_quietly(session)
            _send(conn, {"seq": seq, "ok": True, "result": {"closed": True}})
            break
        try:
            result = session.handle(op, request.get("args") or {})
        except SessionError as exc:
            _send(conn, {"seq": seq, "ok": False, "code": exc.status.value,
                         "stage": exc.stage,
                         "diagnostic": redact_diagnostic(exc.diagnostic),
                         "fatal": exc.fatal})
            if exc.fatal:
                break
        except BaseException as exc:
            _send(conn, {"seq": seq, "ok": False,
                         "code": ResultStatus.INTERNAL_ERROR.value,
                         "stage": str(op), "fatal": True,
                         "diagnostic": redact_diagnostic(
                             "%s: %s" % (type(exc).__name__, exc)),
                         "traceback": redact_diagnostic(traceback.format_exc())})
            break
        else:
            _send(conn, {"seq": seq, "ok": True, "result": result})

    _close_quietly(session)
    conn.close()


def _close_quietly(session) -> None:
    close = getattr(session, "close", None)
    if close is None:
        return
    try:
        close()
    except BaseException:
        # Reported nowhere else: the process is ending and the parent already
        # has its answer. Never silently swallowed on a live request path.
        traceback.print_exc(file=sys.stderr)


def _send(conn, payload: dict) -> None:
    """Answer the parent, or report to stderr if the pipe is already gone.

    A broken pipe here means the parent has terminated this worker, so it is
    not waiting for the answer and there is no channel left to raise on. The
    condition is named rather than swallowed, because architecture.md forbids
    an unexplained pass handler on a production boundary (P02-T01-R09).
    """
    try:
        conn.send(payload)
    except (BrokenPipeError, OSError) as exc:
        print("pob2opt worker: parent pipe closed before the reply was sent "
              "(%s: %s)" % (type(exc).__name__, exc), file=sys.stderr)
