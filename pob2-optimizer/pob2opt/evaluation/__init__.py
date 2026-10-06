"""Engine boundary: lifecycle, typed failures and raw primitive reads (P02).

P02-T01 owns the lifecycle half: one engine per process, bounded requests,
worker replacement, and the separation between loading someone's build exactly
and preparing a blank candidate.

P02-T05 owns the document half: writing a BuildSpec and its items back out as
a PoB document, reading one back, and comparing the two on canonical identity
rather than on XML bytes. Every field the format cannot carry is reported, and
an export that loses anything inside the identity is labelled incomplete.

What is deliberately *not* here:

* primitive units, included and excluded effects - P02-T04;
* legality validation - P02-T03;
* the patch profile, catalog export and compatibility evidence - P02-T02. The
  catalog ID to PoB name tables the exporter needs are supplied by the caller
  through ``CatalogNaming`` until then.
"""

from __future__ import annotations

from .adapter import (DEFAULT_ENTRY, EngineAdapter, WorkerHandle, WorkerSpec,
                      helper_digest, kill_process_tree, pob_worker_spec)
from .builddoc import BuildExport, BuildImport, export_build, import_build
from .checkout import CheckoutIdentity, resolve_checkout
from .documents import (BlobBuildDocuments, BuildDocumentStore,
                        MappingBuildDocuments)
from .itemtext import export_item, import_item
from .naming import AmbiguousNaming, CatalogNaming, UnresolvedName
from .roundtrip import (Difference, RoundTripReport, SourceMutated,
                        diff_identity, round_trip)
from .support import (NOT_REPRESENTABLE, PARTIAL, UNRESOLVED_NAME,
                      SupportReport, UnsupportedField)
from .errors import (EngineCrash, EngineError, EngineInternalError,
                     EngineInvalidInput, EngineProfileMismatch, EngineTimeout,
                     EngineUnsupported, redact_diagnostic)
from .protocol import (ADAPTER_VERSION, PRIMITIVE_SEMANTICS_OWNER,
                       BuildDocument, DocumentProvenance, EngineIdentity,
                       EngineState, LoadedBuild, PrimitiveSnapshot,
                       timeout_for)

__all__ = [
    "ADAPTER_VERSION", "PRIMITIVE_SEMANTICS_OWNER", "DEFAULT_ENTRY",
    "NOT_REPRESENTABLE", "PARTIAL", "UNRESOLVED_NAME",
    "AmbiguousNaming", "BlobBuildDocuments", "BuildDocument",
    "BuildDocumentStore", "BuildExport", "BuildImport", "CatalogNaming",
    "CheckoutIdentity", "Difference", "DocumentProvenance", "EngineAdapter",
    "EngineCrash", "EngineError",
    "EngineIdentity", "EngineInternalError", "EngineInvalidInput",
    "EngineProfileMismatch", "EngineState", "EngineTimeout",
    "EngineUnsupported", "LoadedBuild", "MappingBuildDocuments",
    "PrimitiveSnapshot", "RoundTripReport", "SourceMutated", "SupportReport",
    "UnresolvedName", "UnsupportedField", "WorkerHandle", "WorkerSpec",
    "diff_identity", "export_build", "export_item", "helper_digest",
    "import_build", "import_item", "kill_process_tree",
    "pob_worker_spec", "redact_diagnostic", "resolve_checkout", "round_trip",
    "timeout_for",
]
