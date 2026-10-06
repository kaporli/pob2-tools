"""Engine boundary: lifecycle, typed failures and raw primitive reads (P02).

P02-T01 owns the lifecycle: one engine per process, bounded requests, worker
replacement, and the separation between loading someone's build exactly and
preparing a blank candidate. P02-T04 owns ``primitives``: the units, included
effects, excluded effects and single owner of every value P07 may consume,
plus the gap each value PoB does not supply becomes.

What is deliberately *not* here:

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
from .primitives import (BY_ID, BY_NATIVE_KEY, CATEGORIES, PRIMITIVES,
                         SEMANTICS_OWNER, SEMANTICS_VERSION, DeclaredPrimitive,
                         PrimitiveDefinition, PrimitiveGap, declare,
                         resolve_unit)
from .protocol import (ADAPTER_VERSION, PRIMITIVE_SEMANTICS_OWNER,
                       BuildDocument, DocumentProvenance, EngineIdentity,
                       EngineState, LoadedBuild, PrimitiveSnapshot,
                       timeout_for)

__all__ = [
    "ADAPTER_VERSION", "PRIMITIVE_SEMANTICS_OWNER", "DEFAULT_ENTRY",
    "BY_ID", "BY_NATIVE_KEY", "CATEGORIES", "PRIMITIVES", "SEMANTICS_OWNER",
    "SEMANTICS_VERSION",
    "BlobBuildDocuments", "BuildDocument", "BuildDocumentStore",
    "CheckoutIdentity", "DeclaredPrimitive", "DocumentProvenance",
    "EngineAdapter", "EngineCrash",
    "EngineError",
    "EngineIdentity", "EngineInternalError", "EngineInvalidInput",
    "EngineProfileMismatch", "EngineState", "EngineTimeout",
    "EngineUnsupported", "LoadedBuild", "MappingBuildDocuments",
    "PrimitiveDefinition", "PrimitiveGap",
    "PrimitiveSnapshot", "WorkerHandle", "WorkerSpec", "declare",
    "helper_digest", "kill_process_tree",
    "pob_worker_spec", "redact_diagnostic", "resolve_checkout", "resolve_unit",
    "timeout_for",
]
