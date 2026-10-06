"""A reference index backed by the database (P01-T03, review finding P01-R03).

``RecordIndex`` holds every known identifier in memory, which is fine for a
fixture set and wrong for a corpus: validating one record would read the whole
store. ``StoreIndex`` answers the same question, ``contains(namespace, value)``,
with one indexed SELECT.

Two deliberate differences from the in-memory index:

* ``blob_hashes`` is true only when the **bytes are present**, not when a row
  claims the hash. A record naming a blob is not evidence that the payload was
  copied into this run, which is exactly the gap a run bundle has to close.
* ``pending`` holds records that are being written in the current transaction,
  so a batch whose members reference each other validates as a unit instead of
  each row failing against the state before the batch.
"""

from __future__ import annotations

import sqlite3
from typing import Any, Iterable

from ..domain.validation import ANY_RECORD, NAMESPACES, RecordIndex

#: ``namespace -> (table, column)`` for the single-column lookups.
_SQL_SOURCES: dict[str, tuple[str, str]] = {
    "record_ids": ("", ""),  # spans several tables; handled explicitly
    "catalog_hashes": ("normalized_record", "catalog_hash"),
    "item_hashes": ("normalized_record", "primary_hash"),
    "build_hashes": ("normalized_record", "primary_hash"),
    "listing_ids": ("normalized_record", "record_id"),
    "source_document_ids": ("source_record", "record_id"),
    "patch_profile_ids": ("normalized_record", "record_id"),
    "scenario_ids": ("normalized_record", "record_id"),
    "rotation_ids": ("normalized_record", "record_id"),
    "evaluation_ids": ("evaluation", "evaluation_id"),
    "manifest_ids": ("run", "run_id"),
    "gap_ids": ("data_gap", "gap_id"),
}

#: Namespaces restricted to particular record kinds in
#: ``normalized_record``. ``catalog_hashes`` matters most: the column is also
#: set on items and builds, which *cite* a catalog rather than provide one,
#: and letting a citation answer the lookup is how a bundle believed it held
#: a catalog it had never copied (review finding P01-R03).
_KIND_FILTER: dict[str, tuple[str, ...]] = {
    "source_document_ids": ("source_document",),
    "item_hashes": ("item_instance",),
    "build_hashes": ("build_spec",),
    "listing_ids": ("listing",),
    "patch_profile_ids": ("patch_profile",),
    "scenario_ids": ("scenario_spec",),
    "rotation_ids": ("rotation_policy",),
    "catalog_hashes": ("game_catalog",),
}

#: Tables whose primary key is a record id, for the ``record_ids`` union.
_RECORD_TABLES = (
    ("source_record", "record_id"),
    ("normalized_record", "record_id"),
    ("evaluation", "evaluation_id"),
    ("data_gap", "gap_id"),
    ("observation", "observation_id"),
    ("run", "run_id"),
)


def _is_sha256(value: str) -> bool:
    return (len(value) == 64
            and all(c in "0123456789abcdef" for c in value))


class StoreIndex:
    """Reference resolution against a live store, plus an optional batch."""

    def __init__(self, store: Any, *, pending: RecordIndex | None = None) -> None:
        self.store = store
        self.pending = pending if pending is not None else RecordIndex()

    # -- construction ------------------------------------------------------

    @classmethod
    def with_pending(cls, store: Any, records: Iterable[Any],
                     blob_hashes: Iterable[str] = ()) -> "StoreIndex":
        """An index that also sees records not yet committed."""
        return cls(store, pending=RecordIndex.from_records(records, blob_hashes))

    # -- lookup ------------------------------------------------------------

    def contains(self, namespace: str, value: str) -> bool:
        if self.pending.contains(namespace, value):
            return True
        if namespace == ANY_RECORD:
            return any(self._lookup(name, value) for name in NAMESPACES)
        return self._lookup(namespace, value)

    def _lookup(self, namespace: str, value: str) -> bool:
        if namespace == "blob_hashes":
            # The bytes, not the row: a claim is not a payload. A union
            # lookup reaches here with record ids too, which are not hashes.
            return _is_sha256(value) and self.store.blobs.exists(value)
        if namespace == "record_ids":
            return any(self._exists(table, column, value)
                       for table, column in _RECORD_TABLES)
        if namespace == "rotation_hashes":
            return self._derived_hash("rotation_policy", value)
        if namespace == "manifest_hashes":
            return self._exists("run", "manifest_hash", value)
        if namespace == "mechanic_ids":
            return bool(self._query(
                "SELECT 1 FROM normalized_record WHERE kind = 'mechanic_rule'"
                " AND json_extract(json, '$.mechanic_id') = ? LIMIT 1", value))
        table, column = _SQL_SOURCES[namespace]
        return self._exists(table, column, value,
                            kinds=_KIND_FILTER.get(namespace))

    def _exists(self, table: str, column: str, value: str,
                kinds: tuple[str, ...] | None = None) -> bool:
        sql = "SELECT 1 FROM %s WHERE %s = ?" % (table, column)
        params: tuple[Any, ...] = (value,)
        if kinds:
            sql += " AND kind IN (%s)" % ", ".join("?" * len(kinds))
            params += kinds
        return bool(self._query(sql + " LIMIT 1", *params))

    def _derived_hash(self, kind: str, value: str) -> bool:
        """Hashes that are computed, not stored, need the record itself."""
        from ..domain import identity

        for record in self.store.iter_normalized(kind):
            if identity.rotation_hash(record) == value:
                return True
        return False

    def _query(self, sql: str, *params: Any) -> sqlite3.Row | None:
        try:
            return self.store.conn.execute(sql, params).fetchone()
        except sqlite3.OperationalError:  # pragma: no cover - missing table
            return None

    # -- reporting ---------------------------------------------------------

    def snapshot(self) -> RecordIndex:
        """Materialize the whole corpus. For reporting, never for a lookup."""
        return self.store.record_index()
