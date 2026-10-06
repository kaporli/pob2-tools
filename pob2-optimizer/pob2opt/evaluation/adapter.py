"""The coordinator half of the engine boundary (P02-T01).

``EngineAdapter`` owns paths, bounds and process lifetime; the worker owns the
Lua state. The rules this module exists to keep:

* the parent's working directory never moves, whatever the worker does to its
  own (research F10);
* every path is resolved to an absolute path before the spawn, so nothing is
  interpreted relative to the worker's relocated directory;
* a request that outruns its bound, or a worker that dies, produces a typed
  error and a *new process*. Resetting Lua tables after a native crash is not
  a substitute and is not offered here;
* loading someone's build and building a blank candidate are different named
  operations, and only the second one clears the character (research F11).
"""

from __future__ import annotations

import hashlib
import os
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping, Sequence

import multiprocessing as mp

from ..domain.enums import Fidelity
from ..domain.records import BuildSpec, PatchProfile
from . import protocol
from .checkout import CheckoutIdentity, resolve_checkout
from .documents import BuildDocumentStore
from .errors import (EngineCrash, EngineError, EngineInternalError,
                     EngineInvalidInput, EngineProfileMismatch, EngineTimeout,
                     error_from_wire)
from .protocol import (ADAPTER_VERSION, BuildDocument, DocumentProvenance,
                       EngineIdentity, EngineState, LoadedBuild,
                       PrimitiveSnapshot)
from .worker import worker_main

#: The default session factory: the real PoB engine.
DEFAULT_ENTRY = "pob2opt.evaluation.worker:PobSession"

#: Helper Lua the optimizer ships. Resolved absolutely before every spawn.
_LUA_DIR = Path(__file__).resolve().parents[1] / "lua"
DEFAULT_HELPER_LUA = ("opt_helpers.lua", "tree_lib.lua")

#: Grace given to a worker asked to shut down before it is killed.
SHUTDOWN_GRACE_S = 10.0
#: Grace given to a killed worker before the parent stops waiting for it.
KILL_GRACE_S = 10.0


@dataclass(frozen=True, slots=True)
class WorkerSpec:
    """Everything the child needs, fully resolved by the parent."""

    entry: str = DEFAULT_ENTRY
    pob_root: str | None = None
    helper_lua: tuple[str, ...] = ()
    #: (basename, sha256) per helper, hashed in the parent before the spawn.
    #: The helpers run inside every engine, so a value produced with a
    #: different helper is a different value (P02-T01-R06).
    helper_lua_hashes: tuple[tuple[str, str], ...] = ()
    default_stat_keys: tuple[str, ...] | None = None
    quiet: bool = True
    extra: Mapping[str, Any] = field(default_factory=dict)

    def to_config(self) -> dict:
        config = {"pob_root": self.pob_root, "helper_lua": list(self.helper_lua),
                  "default_stat_keys": list(self.default_stat_keys)
                  if self.default_stat_keys else None,
                  "quiet": self.quiet}
        config.update(self.extra)
        return config


def helper_digest(path: Path) -> str:
    """SHA-256 of a helper script as the worker will hand it to Lua.

    Hashed after newline translation, not over the raw bytes: the worker reads
    these files as text, so a CRLF checkout and an LF checkout send the engine
    identical source and must produce identical identities. Hashing the bytes
    made the identity depend on how git checked the file out. This also agrees
    with the ``helper_lua_sha256`` values P00 recorded.
    """
    return hashlib.sha256(
        path.read_text(encoding="utf-8").encode("utf-8")).hexdigest()


def pob_worker_spec(pob_root: str | os.PathLike[str], *,
                    helper_lua: Sequence[str] = DEFAULT_HELPER_LUA,
                    **kwargs) -> WorkerSpec:
    """A spec for the real engine, with every path resolved here, not later."""
    root = Path(pob_root).resolve()
    if not root.is_dir():
        raise EngineInvalidInput("PoB checkout not found at %s" % root,
                                 stage="spawn")
    resolved: list[str] = []
    hashes: list[tuple[str, str]] = []
    for name in helper_lua:
        path = Path(name)
        path = path if path.is_absolute() else _LUA_DIR / path
        path = path.resolve()
        if not path.is_file():
            raise EngineInvalidInput("helper Lua not found at %s" % path,
                                     stage="spawn")
        resolved.append(str(path))
        hashes.append((path.name, helper_digest(path)))
    return WorkerSpec(entry=DEFAULT_ENTRY, pob_root=str(root),
                      helper_lua=tuple(resolved),
                      helper_lua_hashes=tuple(hashes), **kwargs)


# -- process handle -----------------------------------------------------------

def kill_process_tree(pid: int, process=None) -> list[str]:
    """Best effort, never raises. A leaked worker is worse than a noisy kill.

    Returns what went wrong instead of discarding it, so a worker that could
    not be killed is recorded on the handle rather than silently assumed dead
    (P02-T01-R09).
    """
    problems: list[str] = []
    if sys.platform == "win32":
        try:
            subprocess.run(["taskkill", "/F", "/T", "/PID", str(pid)],
                           capture_output=True, timeout=KILL_GRACE_S, check=False)
        except (OSError, subprocess.SubprocessError) as exc:
            problems.append("taskkill failed: %s: %s" % (type(exc).__name__, exc))
    if process is not None and process.is_alive():
        try:
            process.kill()
        except (OSError, ValueError) as exc:
            problems.append("kill failed: %s: %s" % (type(exc).__name__, exc))
        process.join(KILL_GRACE_S)
        if process.is_alive():
            problems.append("process %s is still alive after %.0fs"
                            % (pid, KILL_GRACE_S))
    return problems


class WorkerHandle:
    """One spawned process and the pipe to it."""

    def __init__(self, spec: WorkerSpec, generation: int,
                 start_timeout_s: float = protocol.START_TIMEOUT_S) -> None:
        self.spec = spec
        self.generation = generation
        self.start_timeout_s = start_timeout_s
        self._seq = 0
        self.dead = False
        self.death_reason: str | None = None
        #: True once a typed error has been raised for this handle's death, so
        #: the adapter knows the caller has already been told.
        self.reported = False

        context = mp.get_context("spawn")
        self._parent_conn, child_conn = context.Pipe(duplex=True)
        self.process = context.Process(
            target=worker_main,
            args=(spec.entry, child_conn, spec.to_config()),
            daemon=True, name="pob2opt-engine-%d" % generation)
        started = time.monotonic()
        self.process.start()
        child_conn.close()  # the parent must not hold the child's end open
        self.pid = self.process.pid
        ready = self._receive(self.start_timeout_s, stage="startup")
        self.boot_ms = int((time.monotonic() - started) * 1000)
        if not isinstance(ready, dict) or not ready.get("ready"):
            self.discard("worker did not report ready")
            raise EngineInternalError("worker sent %r instead of a ready frame"
                                      % (ready,), stage="startup")

    # -- requests ---------------------------------------------------------

    def request(self, op: str, args: dict | None, timeout_s: float):
        if self.dead:
            raise EngineCrash("worker %s was discarded: %s"
                              % (self.pid, self.death_reason or "unknown"),
                              stage=op)
        self._seq += 1
        frame = {"seq": self._seq, "op": op, "args": args or {}}
        try:
            self._parent_conn.send(frame)
        except (BrokenPipeError, OSError) as exc:
            self.discard("pipe broke while sending: %s" % exc)
            raise EngineCrash("worker %s died before it received %s"
                              % (self.pid, op), stage=op) from None
        return self._receive(timeout_s, stage=op)

    def _receive(self, timeout_s: float, *, stage: str):
        deadline_reached = not self._parent_conn.poll(timeout_s)
        if deadline_reached:
            self.discard("no answer within %.3fs" % timeout_s)
            raise EngineTimeout(
                "worker %s did not answer %s within %.3fs; the process was "
                "terminated" % (self.pid, stage, timeout_s), stage=stage)
        try:
            payload = self._parent_conn.recv()
        except (EOFError, OSError) as exc:
            # Give the dead child a moment to be reaped so the diagnostic can
            # name its exit code instead of "still running".
            self.process.join(KILL_GRACE_S if timeout_s > KILL_GRACE_S else timeout_s)
            exitcode = self._exit_state()
            self.discard("pipe closed: %s" % exc)
            raise EngineCrash("worker %s died during %s (%s)"
                              % (self.pid, stage, exitcode), stage=stage) from None
        if not isinstance(payload, dict):
            self.discard("worker sent a non-dict frame")
            raise EngineInternalError("worker sent %r" % (payload,), stage=stage)
        if payload.get("ok"):
            return payload.get("result")
        if payload.get("fatal"):
            self.discard("worker reported a fatal %s" % payload.get("code"))
        raise error_from_wire(payload)

    # -- lifetime ---------------------------------------------------------

    def _exit_state(self) -> str:
        code = self.process.exitcode
        return "still running" if code is None else "exit code %s" % code

    def discard(self, reason: str, *, reported: bool = True) -> None:
        """Terminate for good. A discarded handle is never reused."""
        if self.dead:
            self.reported = self.reported or reported
            return
        self.dead = True
        self.reported = reported
        problems: list[str] = []
        if self.pid is not None:
            problems.extend(kill_process_tree(self.pid, self.process))
        try:
            self._parent_conn.close()
        except OSError as exc:
            problems.append("closing the pipe failed: %s" % exc)
        self.death_reason = ("%s (%s)" % (reason, "; ".join(problems))
                             if problems else reason)

    def close(self) -> None:
        """Ask the worker to shut down; kill it if it will not.

        A shutdown that fails is recorded as the death reason rather than
        swallowed: the process is going away either way, but why it had to be
        killed is worth keeping.
        """
        if self.dead:
            return
        reason = "closed"
        try:
            self.request(protocol.OP_SHUTDOWN, {}, SHUTDOWN_GRACE_S)
        except EngineError as exc:
            reason = "closed after a failed shutdown: %s" % exc
        self.process.join(SHUTDOWN_GRACE_S)
        self.discard(reason)

    @property
    def alive(self) -> bool:
        return not self.dead and self.process.is_alive()


# -- adapter ------------------------------------------------------------------

class EngineAdapter:
    """Evaluate builds through exactly one worker process at a time."""

    def __init__(self, spec: WorkerSpec, *,
                 documents: BuildDocumentStore | None = None,
                 checkout: CheckoutIdentity | None = None,
                 screen_timeout_s: float = protocol.SCREEN_TIMEOUT_S,
                 detailed_timeout_s: float = protocol.DETAILED_TIMEOUT_S,
                 start_timeout_s: float = protocol.START_TIMEOUT_S,
                 require_pinned_checkout: bool = False) -> None:
        self.spec = spec
        self.documents = documents
        self.screen_timeout_s = screen_timeout_s
        self.detailed_timeout_s = detailed_timeout_s
        self.start_timeout_s = start_timeout_s
        self.require_pinned_checkout = require_pinned_checkout
        #: Recorded once. Every request asserts the parent has not moved.
        self.parent_cwd = os.getcwd()
        self.checkout = checkout if checkout is not None else resolve_checkout(
            spec.pob_root or ".")
        self._handle: WorkerHandle | None = None
        self._generation = 0
        #: What the worker's Lua state actually holds: the content key of the
        #: loaded document and the state applied on top of it. Keyed on
        #: content because ``build_hash`` is caller-supplied and two documents
        #: can share one (review finding P02-T01-R01).
        self._loaded_key: tuple[str, str] | None = None
        self._applied_state: dict | None = None
        self._loaded: LoadedBuild | None = None
        #: Which worker generation holds it. A later generation is a fresh
        #: engine with PoB's default blank build, however recently the
        #: previous one was loaded (P02-T01-R10).
        self._loaded_generation: int | None = None
        self._identity: EngineIdentity | None = None
        #: Every process this adapter has owned, oldest first.
        self.worker_pids: list[int] = []
        self.replacements = 0
        self.closed = False

    # -- context manager --------------------------------------------------

    def __enter__(self) -> "EngineAdapter":
        return self

    def __exit__(self, *exc_info) -> None:
        self.close()

    # -- worker lifetime --------------------------------------------------

    @property
    def generation(self) -> int:
        return self._generation

    @property
    def worker_pid(self) -> int | None:
        return self._handle.pid if self._handle is not None else None

    @property
    def worker_alive(self) -> bool:
        return self._handle is not None and self._handle.alive

    def _ensure_worker(self) -> WorkerHandle:
        if self.closed:
            raise EngineInternalError("adapter is closed", stage="worker")
        handle = self._handle
        if handle is not None and handle.alive:
            return handle
        if handle is not None:
            unreported = not handle.reported
            reason = handle.death_reason or (
                "worker process exited (%s)" % handle._exit_state())
            handle.discard(reason)
            self.replacements += 1
            self._forget_loaded_build()
            self._handle = None
            self._identity = None
            if unreported:
                # The worker died without anyone being told. Say so now; the
                # next request gets a fresh process. Restarting silently here
                # would turn a crash into a missing result nobody can see.
                raise EngineCrash("worker %s is gone: %s" % (handle.pid, reason),
                                  stage="worker")
        self._generation += 1
        self._identity = None
        self._handle = WorkerHandle(self.spec, self._generation,
                                    self.start_timeout_s)
        self.worker_pids.append(self._handle.pid)
        return self._handle

    def restart_worker(self) -> int:
        """Replace the process. Named so nothing can mistake it for a reset."""
        if self._handle is not None:
            self._handle.discard("restart requested")
            self.replacements += 1
            self._forget_loaded_build()
        return self._ensure_worker().pid

    def close(self) -> None:
        self.closed = True
        if self._handle is not None:
            self._handle.close()
            self._handle = None
        self._forget_loaded_build()
        self._identity = None

    # -- requests ---------------------------------------------------------

    def _request(self, op: str, args: dict | None, timeout_s: float):
        handle = self._ensure_worker()
        try:
            result = handle.request(op, args, timeout_s)
        except EngineError as exc:
            if handle.dead:
                # The handle terminated the process, for any reason: a
                # timeout, a crash, or a fatal error such as a malformed
                # document. The next request starts a fresh engine, which
                # holds nothing (P02-T01-R10).
                self._forget_loaded_build()
            # Annotate, never replace. Raising a directory error out of a
            # finally block would demote the failure that explains the missing
            # result to __context__ (P02-T01-R07).
            moved = self._parent_cwd_drift()
            if moved:
                exc.diagnostic = "%s; also %s" % (exc.diagnostic, moved)
            raise
        self._assert_parent_cwd(op)
        return result

    def _parent_cwd_drift(self) -> str | None:
        current = os.getcwd()
        if current == self.parent_cwd:
            return None
        return ("the coordinator working directory moved from %s to %s"
                % (self.parent_cwd, current))

    def _forget_loaded_build(self) -> None:
        self._loaded_key = None
        self._applied_state = None
        self._loaded = None
        self._loaded_generation = None

    def _worker_holds_state(self) -> bool:
        """True only if the process that did the loading is still serving.

        Checked before deciding to skip a load. Without it a worker replaced
        after a fatal error answers the next request from a blank character
        while the snapshot still carries the requested build's hash.
        """
        return (self._handle is not None and self._handle.alive
                and self._loaded_generation == self._generation
                and self._loaded is not None)

    def _assert_parent_cwd(self, stage: str) -> None:
        moved = self._parent_cwd_drift()
        if moved:
            raise EngineInternalError("%s during %s" % (moved, stage),
                                      stage=stage)

    # -- operations -------------------------------------------------------

    def identity(self) -> EngineIdentity:
        if self._identity is not None and self._handle is not None                 and self._handle.alive:
            return self._identity
        described = self._request(protocol.OP_DESCRIBE, {}, self.screen_timeout_s)
        self._identity = EngineIdentity(
            pob_root=described.get("pob_root") or (self.spec.pob_root or ""),
            pob_commit=self.checkout.commit,
            pob_dirty_hash=self.checkout.dirty_hash,
            adapter_version=ADAPTER_VERSION,
            helper_lua_hashes=self.spec.helper_lua_hashes,
            worker_pid=int(described.get("pid") or 0),
            worker_cwd=described.get("cwd") or "",
            generation=self._generation)
        return self._identity

    def create_blank_build(self, level: int, resist_penalty: int = 0) -> LoadedBuild:
        """Prepare an empty candidate. This clears tree, gear and groups."""
        payload = self._request(protocol.OP_CREATE_BLANK_BUILD,
                                {"level": int(level),
                                 "resist_penalty": int(resist_penalty)},
                                self.detailed_timeout_s)
        self._forget_loaded_build()
        return LoadedBuild.from_wire(payload)

    def load_exact_build(self, document: BuildDocument, name: str = "exact",
                         *, timeout_s: float | None = None) -> LoadedBuild:
        """Load a build document unchanged. Never clears the character.

        ``timeout_s`` lets an evaluation apply its own fidelity bound to the
        load it performs. Without that a screen-fidelity call declaring 30
        seconds could spend the detailed bound loading and still report
        success (P02-T01-R11).
        """
        payload = self._request(protocol.OP_LOAD_EXACT_BUILD,
                                {"xml": document.xml, "name": name},
                                self.detailed_timeout_s if timeout_s is None
                                else timeout_s)
        loaded = LoadedBuild.from_wire(payload)
        if loaded.opt_setup_called:
            raise EngineInternalError(
                "exact load reported OPT_setup; the imported build was cleared",
                stage=protocol.OP_LOAD_EXACT_BUILD)
        self._loaded_key = document.content_key
        # A fresh load carries no applied state; anything else would make the
        # next evaluation inherit the previous one's configuration.
        self._applied_state = EngineState().to_wire()
        self._loaded = loaded
        self._loaded_generation = self._generation
        return loaded

    def primitives(self, build: BuildSpec, state: EngineState,
                   profile: PatchProfile, *,
                   fidelity: Fidelity = Fidelity.SCREEN,
                   document: BuildDocument | None = None,
                   blob_hash: str | None = None) -> PrimitiveSnapshot:
        """Load ``build`` exactly, apply ``state``, read the engine outputs.

        The returned values carry no declared units: P02-T04 owns the primitive
        inventory, and this snapshot says so rather than implying otherwise.
        """
        self._check_profile(profile, build)
        if document is None:
            document = self._document_for(build, blob_hash)
        if document.build_hash != build.build_hash:
            raise EngineInvalidInput(
                "document %s does not belong to build %s"
                % (document.build_hash, build.build_hash), stage="document",
                record_ids=[build.record_id])

        timeout_s = protocol.timeout_for(fidelity, self.screen_timeout_s,
                                         self.detailed_timeout_s)
        wanted = state.to_wire()
        started = time.monotonic()
        # Reload unless the worker already holds exactly this document with
        # exactly this state. PoB keeps configuration in its own table and
        # nothing clears it, so a changed state needs a fresh document, not
        # just a different set_config call (P02-T01-R01).
        reloaded = (not self._worker_holds_state()
                    or self._loaded_key != document.content_key
                    or self._applied_state != wanted)
        if reloaded:
            loaded = self.load_exact_build(document, name=build.name or "exact",
                                           timeout_s=timeout_s)
        else:
            loaded = self._loaded
        payload = self._request(protocol.OP_PRIMITIVES, wanted, timeout_s)
        self._applied_state = wanted
        duration_ms = int((time.monotonic() - started) * 1000)

        summary = payload.get("summary") or {}
        summary.setdefault("optSetupCalled", loaded.opt_setup_called)
        return PrimitiveSnapshot(
            build_hash=build.build_hash,
            values=dict(payload.get("values") or {}),
            stat_keys=tuple(payload.get("stat_keys") or ()),
            identity=self.identity(),
            state_applied=wanted,
            loaded=LoadedBuild.from_wire(summary),
            document=DocumentProvenance.of(document, reloaded=reloaded),
            timeout_s=timeout_s,
            load_timeout_s=timeout_s if reloaded else None,
            duration_ms=duration_ms)

    # -- checks -----------------------------------------------------------

    def _document_for(self, build: BuildSpec,
                      blob_hash: str | None) -> BuildDocument:
        if self.documents is None:
            raise EngineInvalidInput(
                "no build document store is configured; pass document= or "
                "construct the adapter with documents=", stage="document",
                record_ids=[build.record_id])
        return self.documents.document_for(build, blob_hash)

    def _check_profile(self, profile: PatchProfile, build: BuildSpec) -> None:
        if self.checkout.commit is None:
            if self.require_pinned_checkout:
                raise EngineProfileMismatch(
                    "running checkout commit is unknown (%s)"
                    % (self.checkout.reason or "no reason recorded"),
                    stage="profile", record_ids=[profile.record_id])
            return
        if profile.pob_commit != self.checkout.commit:
            raise EngineProfileMismatch(
                "profile %s pins PoB %s but the running checkout is %s"
                % (profile.record_id, profile.pob_commit, self.checkout.commit),
                stage="profile", record_ids=[profile.record_id, build.record_id])
        if self.require_pinned_checkout and self.checkout.dirty_hash is not None:
            raise EngineProfileMismatch(
                "the running checkout has local modifications (%s)"
                % self.checkout.dirty_hash[:12], stage="profile",
                record_ids=[profile.record_id])
