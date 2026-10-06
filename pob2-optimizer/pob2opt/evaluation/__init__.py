"""Engine boundary: lifecycle, typed failures and raw primitive reads (P02).

P02-T01 owns what is here today: one engine per process, bounded requests,
worker replacement, and the separation between loading someone's build exactly
and preparing a blank candidate.

What is deliberately *not* here:

* primitive units, included and excluded effects - P02-T04;
* legality validation - P02-T03, in the ``legality`` subpackage, which is not
  imported here: it reads the catalog, and the catalog reads this module;
* writing a BuildSpec back out as a PoB document - P02-T05;
* the patch profile, catalog export and compatibility evidence - P02-T02.
"""

from __future__ import annotations

from .adapter import (DEFAULT_ENTRY, EngineAdapter, WorkerHandle, WorkerSpec,
                      helper_digest, kill_process_tree, pob_worker_spec)
from .checkout import CheckoutIdentity, resolve_checkout
from .documents import (BlobBuildDocuments, BuildDocumentStore,
                        MappingBuildDocuments)
from .errors import (EngineCrash, EngineError, EngineInternalError,
                     EngineInvalidInput, EngineProfileMismatch, EngineTimeout,
                     EngineUnsupported, redact_diagnostic)
from .protocol import (ADAPTER_VERSION, PRIMITIVE_SEMANTICS_OWNER,
                       BuildDocument, DocumentProvenance, EngineIdentity,
                       EngineState, LoadedBuild, PrimitiveSnapshot,
                       timeout_for)

__all__ = [
    "ADAPTER_VERSION", "PRIMITIVE_SEMANTICS_OWNER", "DEFAULT_ENTRY",
    "BlobBuildDocuments", "BuildDocument", "BuildDocumentStore",
    "CheckoutIdentity", "DocumentProvenance", "EngineAdapter", "EngineCrash",
    "EngineError",
    "EngineIdentity", "EngineInternalError", "EngineInvalidInput",
    "EngineProfileMismatch", "EngineState", "EngineTimeout",
    "EngineUnsupported", "LoadedBuild", "MappingBuildDocuments",
    "PrimitiveSnapshot", "WorkerHandle", "WorkerSpec", "helper_digest",
    "kill_process_tree",
    "pob_worker_spec", "redact_diagnostic", "resolve_checkout", "timeout_for",
]
