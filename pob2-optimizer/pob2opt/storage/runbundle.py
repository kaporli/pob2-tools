"""Immutable run bundles (P01-T04).

The layout is the one in architecture.md:

    runs/<run_id>/
      manifest.json
      run.sqlite
      blobs/<sha256>
      artifacts/candidates/<build_hash>.json
      artifacts/exports/<build_hash>.xml
      artifacts/traces/<evaluation_id>.jsonl
      checkpoint.json
      report.json
      report.md
      events.jsonl

A run copies the corpus content it needs into its own database and blob store
before execution. That is the whole point of a bundle: the corpus is mutable
and may be moved, pruned or disconnected, and a finished run still has to be
readable and reproducible afterwards. :meth:`RunBundle.copy_references` does
the copying and records every copied reference in ``run_reference``, so the
bundle also states what it depended on.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Sequence

from ..domain import RECORD_TYPES, from_jsonable, manifest_hash, to_jsonable
from .errors import CheckpointMismatch, RecordNotFound, StorageError
from .repositories import BLOB_DIRECTORY, RunStore

MANIFEST_NAME = "manifest.json"
ARTIFACT_DIRS = ("artifacts/candidates", "artifacts/exports", "artifacts/traces")


@dataclass(frozen=True, slots=True)
class CopyReport:
    sources: tuple[str, ...]
    normalized: tuple[str, ...]
    blobs: tuple[str, ...]
    reused_blobs: tuple[str, ...]

    @property
    def total(self) -> int:
        return len(self.sources) + len(self.normalized) + len(self.blobs)


class RunBundle:
    """One run directory and the store inside it."""

    def __init__(self, root: Path, store: RunStore, manifest: Any) -> None:
        self.root = root
        self.store = store
        self.manifest = manifest

    # -- lifecycle ---------------------------------------------------------

    @classmethod
    def create(cls, root: Path | str, manifest: Any, **kwargs: Any) -> "RunBundle":
        root = Path(root)
        if (root / MANIFEST_NAME).exists():
            raise StorageError("%s already holds a run bundle" % root)
        for directory in (BLOB_DIRECTORY,) + ARTIFACT_DIRS:
            (root / directory).mkdir(parents=True, exist_ok=True)
        store = RunStore.open(root, **kwargs)
        digest = manifest_hash(manifest)
        store.put_run(manifest, digest)
        (root / MANIFEST_NAME).write_text(
            json.dumps(to_jsonable(manifest), indent=2, ensure_ascii=False,
                       sort_keys=True) + "\n",
            encoding="utf-8", newline="\n")
        return cls(root, store, manifest)

    @classmethod
    def open(cls, root: Path | str, **kwargs: Any) -> "RunBundle":
        root = Path(root)
        path = root / MANIFEST_NAME
        if not path.is_file():
            raise RecordNotFound("run bundle", str(root))
        manifest = from_jsonable(RECORD_TYPES["run_manifest"],
                                 json.loads(path.read_text(encoding="utf-8")))
        store = RunStore.open(root, **kwargs)
        recorded = store.run_manifest_hash(manifest.run_id)
        current = manifest_hash(manifest)
        if recorded != current:
            raise CheckpointMismatch(recorded, current)
        return cls(root, store, manifest)

    def close(self) -> None:
        self.store.close()

    def __enter__(self) -> "RunBundle":
        return self

    def __exit__(self, *exc: Any) -> None:
        self.close()

    @property
    def run_id(self) -> str:
        return str(self.manifest.run_id)

    @property
    def manifest_hash(self) -> str:
        return manifest_hash(self.manifest)

    # -- paths -------------------------------------------------------------

    def candidate_path(self, build_hash: str) -> Path:
        return self.root / "artifacts" / "candidates" / ("%s.json" % build_hash)

    def export_path(self, build_hash: str) -> Path:
        return self.root / "artifacts" / "exports" / ("%s.xml" % build_hash)

    def trace_path(self, evaluation_id: str) -> Path:
        return self.root / "artifacts" / "traces" / ("%s.jsonl" % evaluation_id)

    @property
    def events_path(self) -> Path:
        return self.root / "events.jsonl"

    # -- copying the corpus in ---------------------------------------------

    def copy_references(self, corpus: RunStore, *,
                        source_ids: Sequence[str] = (),
                        normalized_ids: Sequence[str] = (),
                        blob_hashes: Iterable[str] = ()) -> CopyReport:
        """Copy the records and payloads this run needs into its own bundle.

        Every blob referenced by a copied source document comes with it, so
        the bundle can still produce the original bytes after the corpus is
        gone.
        """
        wanted_blobs = set(blob_hashes)
        copied_sources: list[str] = []
        copied_normalized: list[str] = []
        new_blobs: list[str] = []
        reused: list[str] = []

        for record_id in source_ids:
            record = corpus.get_source(record_id)
            blob_hash = getattr(record, "blob_hash", None)
            if blob_hash is None:
                # An acquisition attempt has no payload of its own.
                self.store.put_acquisition_result(record)
            else:
                written = self.store.ingest_source(
                    corpus.read_payload(blob_hash), record).blob
                (reused if written.reused else new_blobs).append(blob_hash)
                wanted_blobs.add(blob_hash)
            copied_sources.append(record_id)

        for blob_hash in sorted(wanted_blobs - set(new_blobs) - set(reused)):
            written = self.store.blobs.put(corpus.read_payload(blob_hash))
            (reused if written.reused else new_blobs).append(blob_hash)

        for record_id in normalized_ids:
            self.store.put_normalized(corpus.get_normalized(record_id))
            copied_normalized.append(record_id)

        self.store.add_run_references(self.run_id, "source", copied_sources)
        self.store.add_run_references(self.run_id, "normalized", copied_normalized)
        self.store.add_run_references(self.run_id, "blob", sorted(wanted_blobs))
        return CopyReport(tuple(copied_sources), tuple(copied_normalized),
                          tuple(new_blobs), tuple(reused))

    def declared_references(self) -> dict[str, list[str]]:
        return {kind: self.store.run_references(self.run_id, kind)
                for kind in ("source", "normalized", "blob")}

    def self_check(self) -> dict[str, Any]:
        """Confirm the bundle can be read without its corpus.

        Verifies every declared blob against its hash and every declared
        record against the bundle's own database.
        """
        refs = self.declared_references()
        missing_blobs = [h for h in refs["blob"] if not self.store.blobs.exists(h)]
        for blob_hash in refs["blob"]:
            if blob_hash not in missing_blobs:
                self.store.read_payload(blob_hash)  # raises on corruption
        missing_records: list[str] = []
        for record_id in refs["source"]:
            try:
                self.store.get_source(record_id)
            except RecordNotFound:
                missing_records.append(record_id)
        for record_id in refs["normalized"]:
            try:
                self.store.get_normalized(record_id)
            except RecordNotFound:
                missing_records.append(record_id)
        return {
            "run_id": self.run_id,
            "manifest_hash": self.manifest_hash,
            "blobs_declared": len(refs["blob"]),
            "records_declared": len(refs["source"]) + len(refs["normalized"]),
            "missing_blobs": missing_blobs,
            "missing_records": missing_records,
            "readable": not missing_blobs and not missing_records,
        }
