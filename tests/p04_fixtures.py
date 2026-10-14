"""Shared P04 fixtures: PoB-written documents and the catalog slice.

``tests/fixtures/p04`` is written by ``scripts/p04_make_fixtures.py``. Each
build document was composed by that script and then loaded and saved by the
pinned PoB, so the bytes are PoB's own; the compositions are synthetic and
describe no played build. ``catalog-slice.json`` holds the pinned catalog's
rows these documents reference. Each file is listed in
``tests/fixtures/manifest.json`` with origin ``pob_derived``.
"""

from __future__ import annotations

import hashlib
import json
from functools import lru_cache
from pathlib import Path

from pob2opt.catalog.entities import catalog_hash, entities_from_rows
from pob2opt.domain.enums import AccessMethod, Redistribution
from pob2opt.domain.records import (SCHEMA_VERSION, PopularitySignal,
                                    SourceDocument)
from pob2opt.parsers import ParseContext

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "p04"
CREATED_AT = "2026-10-14T00:00:00Z"

#: PoB documents whose every gameplay field the record holds.
COMPLETE_BUILDS = ("b01", "b03", "b04", "b05", "b07", "b08", "b09", "b10",
                   "b11", "b12")
#: PoB recorded a minion choice on a group it generated; the record cannot
#: hold it, so these parse as partial.
PARTIAL_BUILDS = ("b02", "b06")


@lru_cache(maxsize=1)
def slice_data() -> dict:
    return json.loads((FIXTURES / "catalog-slice.json").read_text(
        encoding="utf-8"))


@lru_cache(maxsize=1)
def entities() -> dict:
    tables = slice_data()["tables"]
    out = {table: entities_from_rows(table, rows)
           for table, rows in tables.items()}
    out["ascendancies"] = entities_from_rows("ascendancies", tables["classes"])
    out["passive_edges"] = entities_from_rows("passive_edges",
                                              tables["passive_nodes"])
    return out


def slice_catalog_hash() -> str:
    return catalog_hash(entities())


def context(**overrides) -> ParseContext:
    fields = dict(catalog_hash=slice_catalog_hash(), created_at=CREATED_AT,
                  entities=entities(),
                  current_tree_version=slice_data().get("tree_version"))
    fields.update(overrides)
    return ParseContext(**fields)


def document_bytes(name: str) -> bytes:
    if name == "variants":
        return (FIXTURES / "variants.xml").read_bytes()
    return (FIXTURES / "builds" / ("%s.xml" % name)).read_bytes()


def source(payload: bytes, *, record_id: str = "src/fixture",
           provider: str = "local", declared_patch: str | None = None,
           popularity: list[PopularitySignal] | None = None,
           author_id: str | None = None,
           media_type: str = "application/xml") -> SourceDocument:
    """A stored SourceDocument for ``payload``, as acquisition writes it."""
    return SourceDocument(
        schema_version=SCHEMA_VERSION, record_id=record_id,
        created_at=CREATED_AT, provenance_ids=[], provider=provider,
        source_url=None, external_id=None, acquired_at=CREATED_AT,
        published_at=None, updated_at=None,
        access_method=AccessMethod.LOCAL_FILE, media_type=media_type,
        blob_hash=hashlib.sha256(payload).hexdigest(),
        byte_count=len(payload), acquisition_version="p03.t02.1",
        source_manifest_id="local", declared_patch=declared_patch,
        author_id=author_id, locale=None, popularity=list(popularity or []),
        redistribution=Redistribution.UNKNOWN)
