"""Evidence records for the export bundle (P02-T02).

Every rule, every compatibility decision and the patch id itself cite a
``SourceDocument`` whose bytes are stored next to it, so a reviewer can read
what a rule was derived from without the engine. Nothing here is a gameplay
measurement: these documents are either PoB-derived (read out of the pinned
checkout) or a capture of an official page.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ..domain.enums import AccessMethod, AcquisitionStatus, Redistribution
from ..domain.identity import document_hash
from ..domain.records import (SCHEMA_VERSION, AcquisitionResult,
                              SourceDocument)


#: Record id of the acquisition every record in a bundle traces back to.
EXPORT_ROOT_ID = "acquisition/catalog-export"


@dataclass
class EvidenceBundle:
    """The evidence documents an export produced, and their payloads.

    Every record in the bundle must trace back to something, so the bundle
    has a root: an ``AcquisitionResult`` for the engine read and the
    invocation document it produced, each citing the other. That two-record
    cycle is the shape the P01 fixture corpus uses for the same problem; the
    alternative root would be a ``RunManifest``, and a catalog export is not
    a run.
    """

    acquisition_version: str
    created_at: str
    root_id: str = EXPORT_ROOT_ID
    documents: list[SourceDocument] = field(default_factory=list)
    payloads: dict[str, bytes] = field(default_factory=dict)

    def add(self, record_id: str, payload: bytes, *, provider: str,
            source_url: str | None, media_type: str,
            access_method: AccessMethod = AccessMethod.LOCAL_FILE,
            redistribution: Redistribution = Redistribution.RESTRICTED,
            declared_patch: str | None = None,
            external_id: str | None = None,
            provenance_ids: list[str] | None = None) -> str:
        """Store one payload and its descriptor. Returns the record id."""
        digest = document_hash(payload)
        self.documents.append(SourceDocument(
            schema_version=SCHEMA_VERSION,
            record_id=record_id,
            created_at=self.created_at,
            provenance_ids=(list(provenance_ids) if provenance_ids is not None
                            else [self.root_id]),
            provider=provider,
            source_url=source_url,
            external_id=external_id,
            acquired_at=self.created_at,
            published_at=None,
            updated_at=None,
            access_method=access_method,
            media_type=media_type,
            blob_hash=digest,
            byte_count=len(payload),
            acquisition_version=self.acquisition_version,
            source_manifest_id="pob2opt.catalog/%s" % self.acquisition_version,
            declared_patch=declared_patch,
            author_id=None,
            locale=None,
            popularity=[],
            redistribution=redistribution))
        self.payloads[digest] = payload
        return record_id

    def adopt(self, document: SourceDocument, payload: bytes) -> str:
        import dataclasses
        if not document.provenance_ids:
            document = dataclasses.replace(document,
                                           provenance_ids=[self.root_id])
        self.documents.append(document)
        self.payloads[document.blob_hash] = payload
        return document.record_id

    def root_records(self, *, invocation_id: str, provider: str,
                     source_ref: str, payload: bytes) -> AcquisitionResult:
        """The bundle's root pair: the invocation document and its read."""
        self.add(invocation_id, payload, provider=provider, source_url=None,
                 media_type="application/json",
                 redistribution=Redistribution.ALLOWED)
        return AcquisitionResult(
            schema_version=SCHEMA_VERSION,
            record_id=self.root_id,
            created_at=self.created_at,
            provenance_ids=[invocation_id],
            provider=provider,
            source_ref=source_ref,
            access_method=AccessMethod.LOCAL_FILE,
            status=AcquisitionStatus.OK,
            source_document_id=invocation_id,
            http_status=None,
            retry_eligible=False,
            diagnostic=None,
            attempted_at=self.created_at)

    @property
    def record_ids(self) -> list[str]:
        return [document.record_id for document in self.documents]


def pob_source_url(commit: str | None, relative_path: str,
                   line: int | None = None) -> str | None:
    """A permanent link to the cited line, when the commit is known."""
    if not commit:
        return None
    anchor = "#L%d" % line if line else ""
    return ("https://github.com/PathOfBuildingCommunity/PathOfBuilding-PoE2/"
            "blob/%s/%s%s" % (commit, relative_path, anchor))


def json_payload(value: Any) -> bytes:
    """Canonical bytes for a derived evidence document."""
    from ..domain.identity import canonical_json
    return canonical_json(value)
