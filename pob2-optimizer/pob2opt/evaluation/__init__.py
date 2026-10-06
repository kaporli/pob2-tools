"""Engine boundary: lifecycle, typed failures and raw primitive reads (P02).

P02-T01 owns the lifecycle: one engine per process, bounded requests, worker
replacement, and the separation between loading someone's build exactly and
preparing a blank candidate. P02-T04 owns ``primitives``: the units, included
effects, excluded effects and single owner of every value P07 may consume,
plus the gap each value PoB does not supply becomes.

P02-T05 owns the document half: writing a BuildSpec and its items back out as
a PoB document, reading one back, and comparing the two on canonical identity
rather than on XML bytes. Every field the format cannot carry is reported, and
an export that loses anything inside the identity is labelled incomplete.

What is deliberately *not* here:

* legality validation - P02-T03, in the ``legality`` subpackage, which is not
  imported here: it reads the catalog, and the catalog reads this module;
* the patch profile, catalog export and compatibility evidence - P02-T02, in
  ``pob2opt.catalog``. The catalog ID to PoB name tables the document exporter
  needs are still supplied by the caller through ``CatalogNaming``; building
  them from an exported catalog is integration work nobody has done yet.
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
from .primitives import (BY_ID, BY_NATIVE_KEY, CATEGORIES, PRIMITIVES,
                         SEMANTICS_OWNER, SEMANTICS_VERSION, DeclaredPrimitive,
                         PrimitiveDefinition, PrimitiveGap, declare,
                         resolve_unit)
from .protocol import (ADAPTER_VERSION, PRIMITIVE_SEMANTICS_OWNER,
                       BuildDocument, DocumentProvenance, EngineIdentity,
                       EngineState, LoadedBuild, PrimitiveSnapshot,
                       timeout_for)

__all__ = [
    "ADAPTER_VERSION", "AmbiguousNaming", "BlobBuildDocuments",
    "BuildDocument", "BuildDocumentStore", "BuildExport", "BuildImport",
    "BY_ID", "BY_NATIVE_KEY", "CatalogNaming", "CATEGORIES",
    "CheckoutIdentity", "DeclaredPrimitive", "DEFAULT_ENTRY", "Difference",
    "DocumentProvenance", "EngineAdapter", "EngineCrash", "EngineError",
    "EngineIdentity", "EngineInternalError", "EngineInvalidInput",
    "EngineProfileMismatch", "EngineState", "EngineTimeout",
    "EngineUnsupported", "LoadedBuild", "MappingBuildDocuments",
    "NOT_REPRESENTABLE", "PARTIAL", "PrimitiveDefinition", "PrimitiveGap",
    "PRIMITIVES", "PrimitiveSnapshot", "PRIMITIVE_SEMANTICS_OWNER",
    "RoundTripReport", "SEMANTICS_OWNER", "SEMANTICS_VERSION",
    "SourceMutated", "SupportReport", "UnresolvedName", "UNRESOLVED_NAME",
    "UnsupportedField", "WorkerHandle", "WorkerSpec", "declare",
    "diff_identity", "export_build", "export_item", "helper_digest",
    "import_build", "import_item", "kill_process_tree", "pob_worker_spec",
    "redact_diagnostic", "resolve_checkout", "resolve_unit", "round_trip",
    "timeout_for",
]
