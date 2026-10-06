"""Where the exact build document for a BuildSpec comes from (P02-T01).

A BuildSpec is a normalized record; it is not a PoB file. Writing one back out
is P02-T05. Until that exists, the only faithful document is the original the
build was parsed from, which P01 stored as an immutable blob. A BuildSpec that
carries no raw blob is a metadata-only import, and asking the engine to
evaluate it is invalid input, not an occasion to reconstruct something.
"""

from __future__ import annotations

from typing import Mapping, Protocol

from ..domain.records import BuildSpec
from .errors import EngineInvalidInput
from .protocol import BuildDocument


class BuildDocumentStore(Protocol):
    def document_for(self, build: BuildSpec) -> BuildDocument: ...


class BlobBuildDocuments:
    """Reads the first raw blob a BuildSpec references from a P01 BlobStore."""

    def __init__(self, blobs, encoding: str = "utf-8") -> None:
        self.blobs = blobs
        self.encoding = encoding

    def document_for(self, build: BuildSpec) -> BuildDocument:
        if not build.raw_blob_hashes:
            raise EngineInvalidInput(
                "build %s has no raw document blob; a metadata-only import "
                "cannot be evaluated as an exact build" % build.build_hash,
                stage="document", record_ids=[build.record_id])
        blob_hash = build.raw_blob_hashes[0]
        try:
            payload = self.blobs.get(blob_hash)
        except Exception as exc:
            raise EngineInvalidInput(
                "raw document blob %s is unavailable: %s" % (blob_hash, exc),
                stage="document", record_ids=[build.record_id]) from None
        try:
            xml = payload.decode(self.encoding)
        except UnicodeDecodeError as exc:
            raise EngineInvalidInput(
                "raw document blob %s is not %s text: %s"
                % (blob_hash, self.encoding, exc),
                stage="document", record_ids=[build.record_id]) from None
        return BuildDocument(build_hash=build.build_hash, xml=xml,
                             blob_hash=blob_hash)


class MappingBuildDocuments:
    """An explicit build_hash to document mapping, for fixtures and tests."""

    def __init__(self, documents: Mapping[str, str]) -> None:
        self.documents = dict(documents)

    def document_for(self, build: BuildSpec) -> BuildDocument:
        try:
            xml = self.documents[build.build_hash]
        except KeyError:
            raise EngineInvalidInput(
                "no build document registered for %s" % build.build_hash,
                stage="document", record_ids=[build.record_id]) from None
        return BuildDocument(build_hash=build.build_hash, xml=xml)
