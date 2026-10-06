"""Typed engine failures (P02-T01).

Every failure a worker or its coordinator can produce maps to exactly one
:class:`~pob2opt.domain.enums.ResultStatus`, so a caller never has to read
prose to decide whether a build was illegal, the engine died or the request ran
out of time. ``except: pass`` is not used anywhere on this boundary.

Diagnostics are redacted before they leave the process: absolute paths become
their basename, so a stored EvaluationResult cannot leak a checkout location.
"""

from __future__ import annotations

import re
from typing import Sequence

from ..domain.enums import ResultStatus
from ..domain.records import ErrorDetail

#: Longest diagnostic kept. Lua tracebacks are long and mostly repetition.
DIAGNOSTIC_LIMIT = 2000

_ABSOLUTE_PATH = re.compile(
    r"""(?:[A-Za-z]:[\/]|\\|(?<![\w.])/)[^\s'"<>|]*""")


def redact_diagnostic(text: str, limit: int = DIAGNOSTIC_LIMIT) -> str:
    """Collapse whitespace, strip absolute paths and bound the length."""
    collapsed = " ".join(str(text).split())

    def _basename(match: re.Match[str]) -> str:
        tail = re.split(r"[\/]", match.group(0))[-1]
        return "<path>/" + tail if tail else "<path>"

    redacted = _ABSOLUTE_PATH.sub(_basename, collapsed)
    if len(redacted) > limit:
        redacted = redacted[: limit - 3] + "..."
    return redacted


class EngineError(Exception):
    """Base class. ``status`` is the stored result status, never invented."""

    status: ResultStatus = ResultStatus.INTERNAL_ERROR

    def __init__(self, diagnostic: str, *, stage: str,
                 record_ids: Sequence[str] = ()) -> None:
        self.diagnostic = redact_diagnostic(diagnostic)
        self.stage = stage
        self.record_ids = list(record_ids)
        super().__init__("%s [%s] %s" % (self.status.value, stage, self.diagnostic))

    def as_error_detail(self) -> ErrorDetail:
        return ErrorDetail(code=self.status, stage=self.stage,
                           record_ids=list(self.record_ids),
                           diagnostic=self.diagnostic)


class EngineInvalidInput(EngineError):
    """The request could not describe a build the engine may evaluate."""

    status = ResultStatus.INVALID_INPUT


class EngineProfileMismatch(EngineInvalidInput):
    """The running checkout is not the one the PatchProfile pins."""


class EngineUnsupported(EngineError):
    """The operation is outside this adapter's declared capability."""

    status = ResultStatus.UNSUPPORTED


class EngineTimeout(EngineError):
    """The worker did not answer inside its bound; the process was replaced."""

    status = ResultStatus.TIMEOUT


class EngineCrash(EngineError):
    """The worker process died. Only a new process can continue."""

    status = ResultStatus.ENGINE_CRASH


class EngineInternalError(EngineError):
    """A coordinator-side defect: framing, protocol or path resolution."""

    status = ResultStatus.INTERNAL_ERROR


#: Wire code to exception. The worker sends the code; the parent raises.
ERROR_BY_CODE: dict[str, type[EngineError]] = {
    ResultStatus.INVALID_INPUT.value: EngineInvalidInput,
    ResultStatus.UNSUPPORTED.value: EngineUnsupported,
    ResultStatus.TIMEOUT.value: EngineTimeout,
    ResultStatus.ENGINE_CRASH.value: EngineCrash,
    ResultStatus.INTERNAL_ERROR.value: EngineInternalError,
}


def error_from_wire(payload: dict) -> EngineError:
    """Rebuild the typed error a worker reported. Unknown code is internal."""
    code = payload.get("code")
    cls = ERROR_BY_CODE.get(code)
    if cls is None:
        return EngineInternalError(
            "worker reported unknown error code %r: %s"
            % (code, payload.get("diagnostic", "")),
            stage=str(payload.get("stage", "unknown")))
    return cls(str(payload.get("diagnostic", "")),
               stage=str(payload.get("stage", "unknown")),
               record_ids=payload.get("record_ids") or ())
