"""Reading historical phase outputs without trusting them (P01-T04).

The legacy pipeline (``pob2opt.cli.save_phase``) wrote ``<out>/<phase>.json``
with no manifest, no dependency hashes and no record of the inputs it was
produced for. P00 characterized that: a cached ``gems.json`` was reused for
any level, league, budget or PoB revision.

So these files are readable history and nothing else. Everything loaded here
is labelled ``legacy``, is stored with the payload bytes preserved, and can
never satisfy a cache lookup or stand in for a checkpoint. The API has no
switch that would allow it: ``cache_eligible`` is a constant.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator

from .database import transaction
from .errors import LegacyArtifact

#: Phase names the legacy CLI wrote. A file outside this list is still
#: importable; the name is recorded as given.
KNOWN_PHASES = ("gems", "supports", "combos", "summoners", "items", "finals")

LEGACY_NOTE = (
    "Imported from a pre-specification phase pipeline run. No manifest, no "
    "dependency hashes and no recorded inputs. Historical evidence only: not "
    "a baseline, not cache-eligible, and no number in it is a measurement."
)


@dataclass(frozen=True, slots=True)
class LegacyPhaseImport:
    import_id: str
    phase: str
    source_path: str
    blob_hash: str
    byte_count: int
    payload: Any
    imported_at: str
    note: str = LEGACY_NOTE

    #: Not a field and not a parameter. A legacy import is never reusable as
    #: an evaluation, whatever its content looks like.
    @property
    def cache_eligible(self) -> bool:
        return False


def is_legacy_phase_file(path: Path | str) -> bool:
    path = Path(path)
    return path.suffix == ".json" and path.stem in KNOWN_PHASES


def reject_as_checkpoint(path: Path | str) -> None:
    """Guard for anywhere a checkpoint path is accepted from a user."""
    if is_legacy_phase_file(path):
        raise LegacyArtifact(str(path))


def load_legacy_phase(store: Any, path: Path | str, *,
                      phase: str | None = None) -> LegacyPhaseImport:
    """Store one phase file's bytes and register it as legacy history."""
    path = Path(path)
    payload_bytes = path.read_bytes()
    blob = store.blobs.put(payload_bytes)
    phase = phase or path.stem
    import_id = "legacy:%s:%s" % (phase, blob.blob_hash[:16])
    now = store.clock()
    with transaction(store.conn) as conn:
        conn.execute(
            "INSERT OR IGNORE INTO blob (blob_hash, byte_count, media_type,"
            " first_seen_at) VALUES (?, ?, 'application/json', ?)",
            (blob.blob_hash, blob.byte_count, now))
        conn.execute(
            "INSERT OR IGNORE INTO legacy_import (import_id, phase,"
            " source_path, blob_hash, imported_at, note)"
            " VALUES (?, ?, ?, ?, ?, ?)",
            (import_id, phase, str(path), blob.blob_hash, now, LEGACY_NOTE))
    return LegacyPhaseImport(
        import_id=import_id, phase=phase, source_path=str(path),
        blob_hash=blob.blob_hash, byte_count=blob.byte_count,
        payload=json.loads(payload_bytes.decode("utf-8")), imported_at=now,
    )


def import_legacy_run(store: Any, directory: Path | str
                      ) -> list[LegacyPhaseImport]:
    """Import every phase file in one legacy run directory."""
    directory = Path(directory)
    return [load_legacy_phase(store, path)
            for path in sorted(directory.glob("*.json"))
            if is_legacy_phase_file(path)]


def iter_legacy_imports(store: Any) -> Iterator[dict[str, Any]]:
    for row in store.conn.execute(
            "SELECT import_id, phase, source_path, blob_hash, imported_at,"
            " note FROM legacy_import ORDER BY import_id"):
        yield dict(row)
