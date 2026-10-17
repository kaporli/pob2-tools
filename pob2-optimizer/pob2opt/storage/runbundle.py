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
from dataclasses import dataclass, field as dc_field
from pathlib import Path
from typing import Any, Iterable, Sequence

from ..domain import (
    RECORD_TYPES,
    from_jsonable,
    manifest_hash,
    to_jsonable,
)
from ..domain.records import kind_of
from ..domain.validation import ANY_RECORD, NAMESPACES, _references, provided_identifiers
from .errors import (
    BlobCorrupt,
    BlobNotFound,
    CheckpointMismatch,
    IncompleteBundle,
    RecordNotFound,
    StorageError,
)
from .repositories import BLOB_DIRECTORY, RunStore

MANIFEST_NAME = "manifest.json"
ARTIFACT_DIRS = ("artifacts/candidates", "artifacts/exports", "artifacts/traces")


@dataclass(frozen=True, slots=True)
class CopyReport:
    sources: tuple[str, ...]
    normalized: tuple[str, ...]
    blobs: tuple[str, ...]
    reused_blobs: tuple[str, ...]
    #: Dependencies the corpus could not supply, by bucket. Non-empty means
    #: the bundle is incomplete and self_check will say so.
    unresolved: dict[str, tuple[str, ...]] = dc_field(default_factory=dict)

    @property
    def total(self) -> int:
        return len(self.sources) + len(self.normalized) + len(self.blobs)

    @property
    def complete(self) -> bool:
        return not self.unresolved


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
        # The manifest is written before the content it describes is copied
        # in, so its own references cannot resolve yet. ``self_check`` is
        # where the bundle has to prove closure, and it validates the
        # manifest with everything else.
        store.put_run(manifest, digest, require_references=False)
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
                        blob_hashes: Iterable[str] = (),
                        transitive: bool = True) -> CopyReport:
        """Copy the records and payloads this run needs into its own bundle.

        With ``transitive`` (the default) the seeds are closed over their
        reference graph: asking for a build brings its catalog, its equipped
        items and their listings, the rotation, the gaps it depends on, the
        source documents and the raw payload blobs. Copying only the seeds
        produced a bundle that called itself readable while none of the
        build dependencies were present (review finding P01-R03).

        A dependency the corpus cannot supply is reported in
        ``CopyReport.unresolved`` rather than silently dropped, and
        :meth:`self_check` then refuses to call the bundle readable.
        """
        if transitive:
            seeds, blobs, unresolved = self._closure(
                corpus, source_ids, normalized_ids, blob_hashes)
        else:
            seeds, unresolved = {}, {}
            blobs = set(blob_hashes)
            for bucket, ids in (("source", source_ids),
                                ("record", normalized_ids)):
                for identifier in ids:
                    record = _fetch(corpus, bucket, identifier)
                    if record is None:
                        unresolved.setdefault(bucket, []).append(identifier)
                    else:
                        seeds[(bucket, identifier)] = record

        new_blobs: list[str] = []
        reused: list[str] = []
        copied_sources: list[str] = []
        other_records: list[Any] = []

        for (bucket, identifier), record in seeds.items():
            if bucket != "source":
                other_records.append(record)
                continue
            blob_hash = getattr(record, "blob_hash", None)
            if blob_hash is None:
                # An acquisition attempt has no payload of its own.
                self.store.put_acquisition_result(record)
                copied_sources.append(identifier)
                continue
            payload = _read_payload(corpus, blob_hash)
            if payload is None:
                unresolved.setdefault("blob", []).append(blob_hash)
                continue
            written = self.store.ingest_source(payload, record).blob
            (reused if written.reused else new_blobs).append(blob_hash)
            blobs.add(blob_hash)
            copied_sources.append(identifier)

        for blob_hash in sorted(blobs - set(new_blobs) - set(reused)):
            payload = _read_payload(corpus, blob_hash)
            if payload is None:
                unresolved.setdefault("blob", []).append(blob_hash)
                continue
            written = self.store.blobs.put(payload)
            (reused if written.reused else new_blobs).append(blob_hash)

        # One batch, so records that reference each other resolve together.
        copied_records: list[str] = []
        if other_records:
            self.store.import_batch(
                other_records, require_references=False,
                legacy_evaluation_ids={
                    r.evaluation_id for r in other_records
                    if kind_of(r) == "evaluation_result"
                    and corpus.is_legacy_evaluation(r.cache_key)})
            copied_records = [_record_id(r) for r in other_records]

        self.store.add_run_references(self.run_id, "source", copied_sources)
        self.store.add_run_references(self.run_id, "normalized", copied_records)
        self.store.add_run_references(self.run_id, "blob", sorted(blobs))
        return CopyReport(tuple(copied_sources), tuple(copied_records),
                          tuple(new_blobs), tuple(reused),
                          {k: tuple(v) for k, v in sorted(unresolved.items())})

    def _closure(self, corpus: RunStore, source_ids, normalized_ids,
                 blob_hashes):
        """Walk the reference graph from the seeds through the corpus."""
        blobs = set(blob_hashes)
        unresolved: dict[str, list[str]] = {}
        found: dict[tuple[str, str], Any] = {}

        lookup = _CorpusLookup(corpus)
        queue: list[tuple[str, str]] = (
            [("source", rid) for rid in source_ids]
            + [("record", rid) for rid in normalized_ids])
        seen: set[tuple[str, str]] = set()

        while queue:
            key = queue.pop(0)
            if key in seen:
                continue
            seen.add(key)
            bucket, identifier = key

            record = _fetch(corpus, bucket, identifier)
            if record is None:
                unresolved.setdefault(bucket, []).append(identifier)
                continue
            found[key] = record

            for _path, value, namespace in _references(kind_of(record), record):
                if value is None:
                    continue
                if namespace == "blob_hashes":
                    blobs.add(value)
                    continue
                target = lookup.locate(namespace, value)
                if target is None:
                    if namespace == ANY_RECORD and corpus.reference_index().contains(
                            "blob_hashes", value):
                        blobs.add(value)
                    else:
                        unresolved.setdefault(namespace, []).append(value)
                elif target not in seen:
                    queue.append(target)
        return found, blobs, unresolved

    def declared_references(self) -> dict[str, list[str]]:
        return {kind: self.store.run_references(self.run_id, kind)
                for kind in ("source", "normalized", "blob")}

    def self_check(self) -> dict[str, Any]:
        """Can this bundle be read, and does everything in it resolve?

        Four separate questions, reported separately:

        * are the declared blobs present, and do their bytes still hash to
          their names;
        * are the declared records present;
        * does every reference in every stored record, the manifest
          included, resolve inside this bundle;
        * do the records satisfy semantic validation, including binding each
          aggregate to its manifest's objective.

        A bundle is ``readable`` only when all four hold. Before the review
        it answered the first two and called that readable, so a snapshot
        missing its entire dependency graph passed (P01-R03).
        """
        refs = self.declared_references()
        missing_blobs: list[str] = []
        corrupt_blobs: list[str] = []
        for blob_hash in refs["blob"]:
            if not self.store.blobs.exists(blob_hash):
                missing_blobs.append(blob_hash)
                continue
            try:
                self.store.read_payload(blob_hash)
            except BlobCorrupt:
                corrupt_blobs.append(blob_hash)

        missing_records: list[str] = []
        for record_id in refs["source"]:
            try:
                self.store.get_source(record_id)
            except RecordNotFound:
                missing_records.append(record_id)
        for record_id in refs["normalized"]:
            if not self.store.has_record(record_id):
                missing_records.append(record_id)

        reports = self.store.validate_stored()
        invalid = {rid: [str(e) for e in report.errors]
                   for rid, report in reports.items() if not report.ok}
        unresolved = {rid: [e.field_path for e in report.errors
                            if e.code == "unresolved_reference"]
                      for rid, report in reports.items()
                      if any(e.code == "unresolved_reference" for e in report.errors)}
        check = {
            "run_id": self.run_id,
            "manifest_hash": self.manifest_hash,
            "blobs_declared": len(refs["blob"]),
            "records_declared": len(refs["source"]) + len(refs["normalized"]),
            "missing_blobs": missing_blobs,
            "corrupt_blobs": corrupt_blobs,
            "missing_records": missing_records,
            "unresolved_references": unresolved,
            "readable": not (missing_blobs or corrupt_blobs or missing_records
                             or invalid),
        }
        # Preserve the successful v1 check's wire shape and recorded evidence.
        if invalid:
            check["validation_errors"] = invalid
        return check

    def require_readable(self) -> dict[str, Any]:
        """Raise unless the bundle is complete.

        Use before declaring a run ready to execute: a bundle that cannot
        resolve its own graph cannot reproduce its results later.
        """
        check = self.self_check()
        if not check["readable"]:
            raise IncompleteBundle(self.run_id, check)
        return check


def _fetch(store: RunStore, bucket: str, identifier: str) -> Any:
    try:
        return (store.get_source(identifier) if bucket == "source"
                else store.get_record(identifier))
    except RecordNotFound:
        return None


def _read_payload(store: RunStore, blob_hash: str) -> bytes | None:
    try:
        return store.read_payload(blob_hash)
    except BlobNotFound:
        return None


def _record_id(record: Any) -> str:
    for attribute in ("record_id", "evaluation_id", "gap_id", "observation_id", "run_id"):
        value = getattr(record, attribute, None)
        if value is not None:
            return str(value)
    raise StorageError("%s has no identifier" % kind_of(record))


class _CorpusLookup:
    """Resolve a reference to the corpus row that satisfies it."""

    def __init__(self, corpus: RunStore) -> None:
        self.corpus = corpus
        self._table: dict[tuple[str, str], tuple[str, str]] | None = None

    def locate(self, namespace: str, value: str) -> tuple[str, str] | None:
        if self._table is None:
            self._table = self._build()
        if namespace == ANY_RECORD:
            for name in NAMESPACES:
                target = self._table.get((name, value))
                if target is not None:
                    return target
            return None
        return self._table.get((namespace, value))

    def _build(self) -> dict[tuple[str, str], tuple[str, str]]:
        table: dict[tuple[str, str], tuple[str, str]] = {}
        for rid, kind, record in self.corpus.iter_stored():
            bucket = ("source" if kind in ("source_document", "acquisition_result")
                      else "record")
            for key in provided_identifiers(record):
                table.setdefault(key, (bucket, rid))
        return table
