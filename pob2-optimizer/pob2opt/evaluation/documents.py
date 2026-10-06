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
from ..storage.errors import BlobCorrupt, BlobNotFound
from .errors import EngineInternalError, EngineInvalidInput
from .protocol import BuildDocument


class BuildDocumentStore(Protocol):
    def document_for(self, build: BuildSpec,
                     blob_hash: str | None = None) -> BuildDocument: ...


class BlobBuildDocuments:
    """Reads a BuildSpec's own stored document from a P01 BlobStore."""

    def __init__(self, blobs, encoding: str = "utf-8") -> None:
        self.blobs = blobs
        self.encoding = encoding

    def document_for(self, build: BuildSpec,
                     blob_hash: str | None = None) -> BuildDocument:
        """The build's own stored document.

        With several raw blobs the caller must say which one. Nothing in the
        contracts makes the first entry the PoB document, and P04 has not
        defined the ordering, so guessing would be an undeclared rule
        (P02-T01-R04).
        """
        chosen = self._choose(build, blob_hash)
        try:
            payload = self.blobs.get(chosen)
        except (BlobNotFound, BlobCorrupt, OSError) as exc:
            raise EngineInvalidInput(
                "raw document blob %s is unavailable: %s" % (chosen, exc),
                stage="document", record_ids=[build.record_id]) from None
        except Exception as exc:
            # Anything else is a defect in the store, not a build that cannot
            # be described. Calling it invalid_input would hide it.
            raise EngineInternalError(
                "blob store failed reading %s: %s: %s"
                % (chosen, type(exc).__name__, exc), stage="document",
                record_ids=[build.record_id]) from None
        try:
            xml = payload.decode(self.encoding)
        except UnicodeDecodeError as exc:
            raise EngineInvalidInput(
                "raw document blob %s is not %s text: %s"
                % (chosen, self.encoding, exc),
                stage="document", record_ids=[build.record_id]) from None
        return BuildDocument(build_hash=build.build_hash, xml=xml,
                             blob_hash=chosen, source="stored_blob")

    @staticmethod
    def _choose(build: BuildSpec, blob_hash: str | None) -> str:
        available = list(build.raw_blob_hashes)
        if not available:
            raise EngineInvalidInput(
                "build %s has no raw document blob; a metadata-only import "
                "cannot be evaluated as an exact build" % build.build_hash,
                stage="document", record_ids=[build.record_id])
        if blob_hash is not None:
            if blob_hash not in available:
                raise EngineInvalidInput(
                    "build %s does not reference blob %s; it references %s"
                    % (build.build_hash, blob_hash, ", ".join(available)),
                    stage="document", record_ids=[build.record_id])
            return blob_hash
        if len(available) > 1:
            raise EngineInvalidInput(
                "build %s references %d raw blobs (%s); say which one is the "
                "build document. Position does not decide it."
                % (build.build_hash, len(available), ", ".join(available)),
                stage="document", record_ids=[build.record_id])
        return available[0]


class MappingBuildDocuments:
    """An explicit build_hash to document mapping, for fixtures and tests."""

    def __init__(self, documents: Mapping[str, str]) -> None:
        self.documents = dict(documents)

    def document_for(self, build: BuildSpec,
                     blob_hash: str | None = None) -> BuildDocument:
        try:
            xml = self.documents[build.build_hash]
        except KeyError:
            raise EngineInvalidInput(
                "no build document registered for %s" % build.build_hash,
                stage="document", record_ids=[build.record_id]) from None
        return BuildDocument(build_hash=build.build_hash, xml=xml,
                             source="caller_supplied")
