"""Typed storage failures (P01-T03).

architecture.md forbids ``except: pass`` at a production boundary, so every
way storage can fail has a name here and carries the identifiers needed to
investigate it. A missing blob and a corrupt blob are different problems with
different repairs, and neither is "the record is gone".
"""

from __future__ import annotations


class StorageError(Exception):
    """Base class for every failure raised by ``pob2opt.storage``."""


class BlobNotFound(StorageError):
    def __init__(self, blob_hash: str, root: str) -> None:
        self.blob_hash = blob_hash
        self.root = root
        super().__init__("no blob %s under %s" % (blob_hash, root))


class BlobCorrupt(StorageError):
    """Content read back did not hash to the name it was stored under."""

    def __init__(self, expected: str, actual: str, path: str) -> None:
        self.expected = expected
        self.actual = actual
        self.path = path
        super().__init__(
            "blob %s hashes to %s on read; %s is corrupt or was replaced"
            % (expected, actual, path))


class RecordNotFound(StorageError):
    def __init__(self, kind: str, identifier: str) -> None:
        self.kind = kind
        self.identifier = identifier
        super().__init__("no %s with id %r" % (kind, identifier))


class DuplicateRecord(StorageError):
    def __init__(self, kind: str, identifier: str) -> None:
        self.kind = kind
        self.identifier = identifier
        super().__init__("%s %r already exists and records are immutable"
                         % (kind, identifier))


class CacheKeyConflict(StorageError):
    """Two different evaluations claim one cache key."""

    def __init__(self, cache_key: str, existing_id: str, incoming_id: str) -> None:
        self.cache_key = cache_key
        self.existing_id = existing_id
        self.incoming_id = incoming_id
        super().__init__(
            "cache key %s already holds evaluation %s; %s cannot take it"
            % (cache_key, existing_id, incoming_id))


class MigrationError(StorageError):
    pass


class SchemaTooNew(MigrationError):
    def __init__(self, found: int, supported: int) -> None:
        self.found = found
        self.supported = supported
        super().__init__(
            "database is at migration %d but this build implements %d; "
            "upgrade the software rather than downgrading the database"
            % (found, supported))


class MigrationHistoryChanged(MigrationError):
    def __init__(self, version: int, recorded: str, current: str) -> None:
        self.version = version
        super().__init__(
            "migration %d was applied as %s but now reads as %s; an applied "
            "migration may not be edited" % (version, recorded, current))


class TaskStateError(StorageError):
    def __init__(self, task_id: str, current: str, requested: str) -> None:
        self.task_id = task_id
        self.current = current
        self.requested = requested
        super().__init__("task %s is %s and cannot become %s"
                         % (task_id, current, requested))


class TaskResultMismatch(StorageError):
    """A result does not belong to the task being closed with it."""

    def __init__(self, task_id: str, detail: str) -> None:
        self.task_id = task_id
        super().__init__("task %s %s" % (task_id, detail))


class StaleAttempt(StorageError):
    """A result arrived from a dispatch that has since been superseded.

    This is what a worker that outlived a recovery delivers. Accepting it
    would attribute one attempt to another.
    """

    def __init__(self, task_id: str, reported: int, current: int) -> None:
        self.task_id = task_id
        self.reported = reported
        self.current = current
        super().__init__(
            "task %s is on attempt %d; a result from attempt %d is stale"
            % (task_id, current, reported))


class CheckpointMismatch(StorageError):
    """A checkpoint does not belong to the manifest it is being resumed with."""

    def __init__(self, expected: str, found: str) -> None:
        self.expected = expected
        self.found = found
        super().__init__(
            "checkpoint was written for manifest %s but this run's manifest "
            "is %s; resuming would mix two runs" % (found, expected))


class IncompleteBundle(StorageError):
    """A run bundle was asked to declare itself ready and could not.

    Carries the full ``self_check`` result, so the caller sees which blobs,
    records or references are missing rather than only that something is.
    """

    def __init__(self, run_id: str, check: dict) -> None:
        self.run_id = run_id
        self.check = check
        parts = []
        for key in ("missing_blobs", "corrupt_blobs", "missing_records"):
            if check.get(key):
                parts.append("%s=%s" % (key, check[key]))
        if check.get("unresolved_references"):
            parts.append("unresolved_references=%s"
                         % check["unresolved_references"])
        if check.get("validation_errors"):
            parts.append("validation_errors=%s" % check["validation_errors"])
        super().__init__("run bundle %s is not self-contained: %s"
                         % (run_id, "; ".join(parts) or "unknown"))


class LegacyArtifact(StorageError):
    """A historical phase output was offered where a real record is required."""

    def __init__(self, path: str) -> None:
        self.path = path
        super().__init__(
            "%s is a legacy phase output: readable as history, never a valid "
            "evaluation or checkpoint" % path)
