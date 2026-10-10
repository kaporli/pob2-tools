"""Where catalog rows come from (P02-T02).

Two readers, one interface. ``EngineCatalogReader`` asks the pinned PoB
engine through the P02-T01 adapter. ``MappingCatalogReader`` replays rows
already captured to disk, which is how the offline lane runs the same export
code without PoB.

A reader never edits a row. Interpreting one is ``entities.py``'s job and
deciding what it means for a rule is ``rules.py``'s.
"""

from __future__ import annotations

from typing import Any, Iterable, Mapping, Protocol

from ..evaluation import protocol
from ..evaluation.adapter import EngineAdapter


class CatalogReader(Protocol):
    """Read a whole catalog table, or the structured rule sources."""

    def rows(self, table: str) -> list[dict]:
        ...  # pragma: no cover - protocol

    def rule_sources(self) -> dict:
        ...  # pragma: no cover - protocol

    def describe(self) -> dict:
        """Where these rows came from. Recorded on the export."""
        ...  # pragma: no cover - protocol


class EngineCatalogReader:
    """Rows read from a live engine through the bounded P02-T01 adapter."""

    def __init__(self, adapter: EngineAdapter, *,
                 page_rows: int = protocol.CATALOG_PAGE_ROWS,
                 timeout_s: float | None = None) -> None:
        self.adapter = adapter
        self.page_rows = page_rows
        self.timeout_s = timeout_s

    def rows(self, table: str) -> list[dict]:
        return self.adapter.catalog_rows(table, page_rows=self.page_rows,
                                         timeout_s=self.timeout_s)

    def rule_sources(self) -> dict:
        page = self.adapter.catalog_page(protocol.CATALOG_RULE_SOURCES,
                                         timeout_s=self.timeout_s)
        return dict(page)

    def describe(self) -> dict:
        identity = self.adapter.identity()
        return {
            "kind": "pob_engine",
            "pob_root": identity.pob_root,
            "pob_commit": identity.pob_commit,
            "pob_dirty_hash": identity.pob_dirty_hash,
            "adapter_version": identity.adapter_version,
            "helper_lua_hashes": [list(pair)
                                  for pair in identity.helper_lua_hashes],
        }


class MappingCatalogReader:
    """Rows replayed from a captured export.

    ``source`` says where the capture came from, so an export built this way
    can never be mistaken for one read from a live engine.
    """

    def __init__(self, tables: Mapping[str, Iterable[Mapping[str, Any]]],
                 rule_sources: Mapping[str, Any] | None = None,
                 *, source: str = "captured_rows") -> None:
        self._tables = {name: [dict(row) for row in rows]
                        for name, rows in tables.items()}
        self._rule_sources = dict(rule_sources or {})
        self.source = source

    def rows(self, table: str) -> list[dict]:
        if table not in self._tables:
            raise KeyError("no captured rows for catalog table %r" % table)
        return [dict(row) for row in self._tables[table]]

    def rule_sources(self) -> dict:
        return dict(self._rule_sources)

    def describe(self) -> dict:
        return {"kind": "captured_rows", "source": self.source,
                "tables": sorted(self._tables)}
