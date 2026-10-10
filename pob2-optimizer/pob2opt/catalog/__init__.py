"""Patch-specific entities and compatibility profiles (P02-T02).

What this package owns:

* reading the pinned engine's catalog tables through the typed Lua bridge
  operations and turning them into P01 ``CatalogEntity`` rows;
* the ``CharacterRules`` that upstream data actually supports, and a
  ``DataGap`` for every rule it does not;
* resolving the current game patch from stored official release evidence,
  and recording ``unknown`` when there is none;
* comparing the catalog against a fixed compatibility fixture set, so a
  matching version label alone never produces ``verified``;
* the identity of an evaluation context, which changes when the upstream
  commit changes.

What it does not do: approve a new patch automatically, invent an unlock or
reward rule that upstream does not carry, or reach the network. Release
evidence is captured out of band and read from disk.
"""

from __future__ import annotations

from .compatibility import (CompatibilityReport, FixtureOutcome,
                            compatibility_fixtures, decide_compatibility,
                            run_fixtures)
from .context import context_identity, evaluation_context_hash
from .entities import (CATALOG_TABLE_ORDER, CatalogTables, catalog_hash,
                       derive_passive_edges, entities_from_rows, entity_id)
from .export import (CatalogExport, CatalogProvider, ExportRequest,
                     PobCatalogProvider, write_bundle)
from .reader import CatalogReader, EngineCatalogReader, MappingCatalogReader
from .release import (ReleaseCapture, load_release_capture,
                      release_evidence_document)
from .resolve import BuildResolution, resolve_build_document
from .rules import RuleBuild, build_character_rules

__all__ = [
    "BuildResolution", "CATALOG_TABLE_ORDER", "CatalogExport",
    "CatalogProvider", "CatalogReader", "CatalogTables",
    "CompatibilityReport", "EngineCatalogReader", "ExportRequest",
    "FixtureOutcome", "MappingCatalogReader", "PobCatalogProvider",
    "ReleaseCapture", "RuleBuild", "build_character_rules", "catalog_hash",
    "compatibility_fixtures", "context_identity", "decide_compatibility",
    "derive_passive_edges", "entities_from_rows", "entity_id",
    "evaluation_context_hash", "load_release_capture",
    "release_evidence_document", "resolve_build_document", "run_fixtures",
    "write_bundle",
]
