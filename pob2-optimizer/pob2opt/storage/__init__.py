"""SQLite repositories, immutable blobs and migrations (P01).

Per architecture.md this layer stores and retrieves records. It does not rank
builds, call PoB or reach the network.

* ``blobs`` - content-addressed original bytes, verified on read.
* ``migrations`` / ``database`` - numbered schema versions and the connection.
* ``repositories`` - ``RunStore``, the coordinator's single writer.
* ``tasks`` - task state, recovery and atomic checkpoints.
* ``runbundle`` - the immutable run directory and corpus copy-in.
* ``index`` - reference resolution against the database.
* ``legacy`` - historical phase outputs, labelled and never cache-eligible.
* ``queries`` - the documented read-only inspection queries.
"""

from __future__ import annotations

from .blobs import BlobStore, BlobWrite
from .database import connect, open_database, schema_version, transaction, utcnow
from .errors import (
    BlobCorrupt,
    BlobNotFound,
    CacheKeyConflict,
    CheckpointMismatch,
    DuplicateRecord,
    IncompleteBundle,
    LegacyArtifact,
    MigrationError,
    MigrationHistoryChanged,
    RecordNotFound,
    SchemaTooNew,
    StaleAttempt,
    StorageError,
    TaskResultMismatch,
    TaskStateError,
)
from .legacy import (
    LegacyPhaseImport,
    import_legacy_run,
    iter_legacy_imports,
    load_legacy_phase,
    reject_as_checkpoint,
)
from .index import StoreIndex
from .migrations import LATEST_VERSION, MIGRATIONS, Migration, migrate
from .queries import QUERIES, run_all, run_query
from .repositories import (
    BLOB_DIRECTORY,
    CORPUS_DATABASE,
    RUN_DATABASE,
    Committed,
    Ingested,
    RunStore,
)
from .runbundle import CopyReport, RunBundle
from .tasks import (
    TaskRow,
    TaskStore,
    read_checkpoint,
    resume_plan,
    validate_checkpoint,
    write_checkpoint,
)

__all__ = [
    "BLOB_DIRECTORY", "BlobCorrupt", "BlobNotFound", "BlobStore", "BlobWrite",
    "CORPUS_DATABASE", "CacheKeyConflict", "CheckpointMismatch", "Committed",
    "CopyReport", "DuplicateRecord", "IncompleteBundle", "Ingested",
    "LATEST_VERSION",
    "LegacyArtifact", "LegacyPhaseImport", "MIGRATIONS", "Migration",
    "MigrationError", "MigrationHistoryChanged", "QUERIES", "RUN_DATABASE",
    "RecordNotFound", "RunBundle", "RunStore", "SchemaTooNew",
    "StaleAttempt", "StorageError", "StoreIndex", "TaskResultMismatch",
    "TaskRow", "TaskStateError", "TaskStore", "connect", "import_legacy_run",
    "iter_legacy_imports", "load_legacy_phase", "migrate", "open_database",
    "read_checkpoint", "reject_as_checkpoint", "resume_plan", "run_all",
    "run_query", "schema_version", "transaction", "utcnow",
    "validate_checkpoint", "write_checkpoint",
]
