"""Local and HTTP acquisition into immutable records (P03-T02).

The service turns an input - a file, a build code or a URL - into exactly two
kinds of P01 record: the ``SourceDocument`` that describes the stored bytes,
and the ``AcquisitionResult`` that describes the attempt. It owns no store of
its own: blobs and rows belong to ``pob2opt.storage``.

Three properties this module exists to guarantee:

* **A failure is typed and empty.** Every refusal path builds an
  ``AcquisitionResult`` with a contracts.md status, ``source_document_id``
  null, and no blob written. There is no path from a 403, a 404, a 429, an
  oversized payload, a timeout or malformed content to a stored document.
* **Repeated input is idempotent.** A document's ``record_id`` is a UUID5 over
  its content identity (provider, access method, blob hash, redacted URL,
  external ID), so the same bytes from the same place are the same record. The
  second ingestion writes no second row and no second blob. The attempt is
  still recorded: attempts are events and both are kept.
* **No credential is persisted.** URLs are redacted before they reach a record,
  a log line or the state file, and request headers never leave the HTTP layer.
  A request that carries a credential is not cached at all unless the caller
  names the authorization context it belongs to, because a shared cache entry
  is a way for one caller's authenticated copy to be served to another.

Nothing here imports the engine. Acquisition runs with no PoB checkout.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from ..domain.enums import AccessMethod, AcquisitionStatus, Redistribution
from ..domain.identity import canonical_text, document_hash
from ..domain.records import SCHEMA_VERSION, AcquisitionResult, SourceDocument
from . import content as content_rules
from .content import ContentRefused, MalformedContent, OversizedContent, UnsupportedContent
from .http import FetchOutcome, HttpAcquirer
from .limits import Limits
from .redaction import SAFE_HEADERS, redact_diagnostic, redact_url
from .scheduling import Clock, Deferral, SystemClock
from .state import AcquisitionState

LOGGER = logging.getLogger("pob2opt.acquisition")

#: This acquisition implementation. P03-T03 adapters stamp their own.
ACQUISITION_VERSION = "p03.t02.1"
#: ``source_manifest_id`` for input that arrived without a provider manifest.
LOCAL_MANIFEST_ID = "local-input"

#: Namespace for the deterministic document identity.
SOURCE_NAMESPACE = uuid.uuid5(uuid.NAMESPACE_URL,
                              "https://pob2-tools.invalid/p03/source-document")


@dataclass(frozen=True)
class AcquisitionOutcome:
    """What one acquisition attempt produced. Not a persisted record."""

    status: AcquisitionStatus
    result: AcquisitionResult
    document: SourceDocument | None = None
    #: False when the document already existed, so nothing new was written.
    created: bool = False
    #: True for a 304: the stored copy is current and nothing was downloaded.
    unchanged: bool = False
    attempts: int = 1
    deferral: Deferral | None = None

    @property
    def ok(self) -> bool:
        return self.status is AcquisitionStatus.OK

    @property
    def source_document_id(self) -> str | None:
        return self.result.source_document_id

    @property
    def blob_hash(self) -> str | None:
        return self.document.blob_hash if self.document is not None else None


def source_document_id(*, provider: str, access_method: AccessMethod,
                       blob_hash: str, source_url: str | None,
                       external_id: str | None) -> str:
    """Deterministic identity for one acquired payload.

    Acquisition time is deliberately not part of it: re-acquiring the same
    bytes from the same place is the same document, and a second row claiming
    otherwise would be a duplicate, not a new fact.
    """
    identity = {
        "access_method": AccessMethod(access_method).value,
        "blob_hash": blob_hash,
        "external_id": external_id,
        "provider": provider,
        "source_url": source_url,
    }
    return str(uuid.uuid5(SOURCE_NAMESPACE, canonical_text(identity)))


class AcquisitionService:
    def __init__(self, store: Any, *, acquirer: HttpAcquirer | None = None,
                 clock: Clock | None = None,
                 state: AcquisitionState | None = None,
                 limits: Limits | None = None,
                 acquisition_version: str = ACQUISITION_VERSION) -> None:
        self.store = store
        self.acquirer = acquirer
        self.clock = clock or SystemClock()
        self.state = state if state is not None else AcquisitionState.in_memory()
        self.limits = limits or (acquirer.limits if acquirer is not None else Limits())
        self.acquisition_version = acquisition_version
        if self.acquirer is not None:
            # Merge with any stricter deadline already held by this scheduler.
            # The normal service/CLI path must restore before its first send.
            self.acquirer.scheduler.restore_cooldowns(self.state.cooldowns())

    # -- local inputs ------------------------------------------------------

    def ingest_file(self, path: Path | str, *, provider: str,
                    kind: str | None = None,
                    access_method: AccessMethod = AccessMethod.LOCAL_FILE,
                    **document_fields: Any) -> AcquisitionOutcome:
        """Read a saved file and store it unchanged.

        The size limit applies here too: a local file past the cap is refused
        rather than loaded, for the same reason a response is.
        """
        path = Path(path)
        source_ref = str(path)
        try:
            size = path.stat().st_size
        except OSError as error:
            return self._failed(provider, source_ref, access_method,
                                AcquisitionStatus.NOT_FOUND,
                                "cannot read %s (%s)" % (path.name,
                                                         type(error).__name__))
        if size > self.limits.max_bytes:
            return self._failed(
                provider, source_ref, access_method,
                AcquisitionStatus.INVALID_RESPONSE,
                "the file is %d bytes, past the %d byte limit"
                % (size, self.limits.max_bytes))
        try:
            payload = path.read_bytes()
        except OSError as error:
            return self._failed(provider, source_ref, access_method,
                                AcquisitionStatus.INVALID_RESPONSE,
                                "cannot read %s (%s)" % (path.name,
                                                         type(error).__name__))
        return self.ingest_bytes(payload, provider=provider, kind=kind,
                                 filename=path.name, source_ref=source_ref,
                                 access_method=access_method, **document_fields)

    def ingest_build_code(self, code: str | bytes, *, provider: str,
                          access_method: AccessMethod = AccessMethod.MANUAL_CAPTURE,
                          source_ref: str | None = None,
                          **document_fields: Any) -> AcquisitionOutcome:
        """Store a PoB build code after checking that it expands safely.

        The stored bytes are the code as supplied. The expanded XML is checked
        and discarded: normalizing it is P04's work, and keeping two copies of
        the same build would make the raw record ambiguous.
        """
        payload = code.encode("utf-8") if isinstance(code, str) else bytes(code)
        return self.ingest_bytes(payload, provider=provider,
                                 kind=content_rules.BUILD_CODE,
                                 source_ref=source_ref or "build-code",
                                 access_method=access_method, **document_fields)

    def ingest_bytes(self, payload: bytes, *, provider: str,
                     kind: str | None = None,
                     filename: str | None = None,
                     source_ref: str = "bytes",
                     source_url: str | None = None,
                     external_id: str | None = None,
                     access_method: AccessMethod = AccessMethod.LOCAL_FILE,
                     media_type: str | None = None,
                     redistribution: Redistribution = Redistribution.UNKNOWN,
                     source_manifest_id: str = LOCAL_MANIFEST_ID,
                     declared_patch: str | None = None,
                     author_id: str | None = None,
                     locale: str | None = None,
                     published_at: str | None = None,
                     updated_at: str | None = None,
                     popularity: list | None = None,
                     provenance_ids: list[str] | None = None,
                     http_status: int | None = None,
                     attempts: int = 1) -> AcquisitionOutcome:
        """Validate, store once, and record the attempt."""
        if len(payload) > self.limits.max_bytes:
            return self._failed(provider, source_ref, access_method,
                                AcquisitionStatus.INVALID_RESPONSE,
                                "the payload is %d bytes, past the %d byte limit"
                                % (len(payload), self.limits.max_bytes),
                                http_status=http_status, attempts=attempts)
        try:
            resolved = kind or content_rules.detect_kind(
                payload, filename=filename, media_type=media_type)
            report = content_rules.inspect(
                payload, resolved, max_expanded_bytes=self.limits.max_bytes)
        except ContentRefused as refusal:
            return self._failed(provider, source_ref, access_method,
                                _status_for(refusal),
                                "%s: %s" % (refusal.reason, refusal.detail),
                                http_status=http_status, attempts=attempts)

        safe_url = redact_url(source_url) if source_url else None
        blob_hash = document_hash(payload)
        record_id = source_document_id(provider=provider,
                                       access_method=access_method,
                                       blob_hash=blob_hash,
                                       source_url=safe_url,
                                       external_id=external_id)
        existing = self._existing(record_id)
        if existing is not None:
            LOGGER.info("acquisition reused document=%s provider=%s",
                        record_id, provider)
            result = self._result(provider, source_ref, access_method,
                                  AcquisitionStatus.OK,
                                  source_document_id=record_id,
                                  http_status=http_status,
                                  retry_eligible=False,
                                  diagnostic="already acquired; bytes unchanged",
                                  attempts=attempts)
            return AcquisitionOutcome(AcquisitionStatus.OK, result, existing,
                                      created=False, attempts=attempts)

        # The attempt and the document cite each other. contracts.md requires
        # every record to trace back to something, and these two are each
        # other's root: the attempt produced the document, the document records
        # what the attempt read. The catalog evidence bundle uses the same pair.
        result_id = str(uuid.uuid4())
        now = self.clock.utcnow()
        document = SourceDocument(
            schema_version=SCHEMA_VERSION,
            record_id=record_id,
            created_at=now,
            provenance_ids=list(provenance_ids or [result_id]),
            provider=provider,
            source_url=safe_url,
            external_id=external_id,
            acquired_at=now,
            published_at=published_at,
            updated_at=updated_at,
            access_method=AccessMethod(access_method),
            media_type=media_type or report.media_type,
            blob_hash=blob_hash,
            byte_count=report.byte_count,
            acquisition_version=self.acquisition_version,
            source_manifest_id=source_manifest_id,
            declared_patch=declared_patch,
            author_id=author_id,
            locale=locale,
            popularity=list(popularity or []),
            redistribution=Redistribution(redistribution))

        ingested = self.store.ingest_source(payload, document)
        stored = self.store.get_source(ingested.record_id)
        result = self._result(provider, source_ref, access_method,
                              AcquisitionStatus.OK,
                              source_document_id=stored.record_id,
                              http_status=http_status, retry_eligible=False,
                              diagnostic=None, attempts=attempts,
                              record_id=result_id)
        LOGGER.info("acquisition stored document=%s provider=%s kind=%s bytes=%d",
                    stored.record_id, provider, report.kind, report.byte_count)
        return AcquisitionOutcome(AcquisitionStatus.OK, result, stored,
                                  created=ingested.created, attempts=attempts)

    # -- network input -----------------------------------------------------

    def ingest_url(self, url: str, *, provider: str,
                   headers: Mapping[str, str] | None = None,
                   kind: str | None = None,
                   external_id: str | None = None,
                   access_method: AccessMethod = AccessMethod.PUBLIC_PAGE,
                   use_cache: bool = True,
                   credential_partition: str | None = None,
                   **document_fields: Any) -> AcquisitionOutcome:
        """Fetch through the shared HTTP layer and store what came back.

        A conditional request is sent whenever a validator for this request is
        known. A 304 is a success that stores nothing: the document already
        held is returned unchanged.

        ``credential_partition`` names the authorization context a request's
        headers belong to. Without it, a request carrying a credential is not
        cached and sends no validator: the stored representation would depend
        on who asked, and the cache has no way to tell.
        """
        safe_url = redact_url(url)
        if self.acquirer is None:
            return self._failed(provider, safe_url, access_method,
                                AcquisitionStatus.UNSUPPORTED_ACCESS,
                                "this service was built without an HTTP "
                                "acquirer; URL input is not available")
        cacheable = use_cache and (credential_partition is not None
                                   or not carries_credentials(headers))
        if use_cache and not cacheable:
            LOGGER.info("acquisition cache bypassed for an authenticated "
                        "request provider=%s url=%s", provider, safe_url)
        validators = (self.state.validators(
            provider, url, credential_partition=credential_partition)
            if cacheable else None)
        validator_key = (self.state.final_key_for(
            provider, url, credential_partition=credential_partition)
            if cacheable else None)
        fetched = self.acquirer.fetch(provider, url, headers=headers,
                                      validators=validators,
                                      validator_key=validator_key,
                                      resource_key=lambda target: self.state.key_for(
                                          provider, target,
                                          credential_partition=credential_partition))
        self._save_cooldowns()

        if fetched.status is not AcquisitionStatus.OK:
            return self._failed(provider, fetched.url, access_method,
                                fetched.status, fetched.diagnostic,
                                http_status=fetched.http_status,
                                retry_eligible=fetched.retry_eligible,
                                attempts=fetched.attempts,
                                deferral=fetched.deferral)

        if fetched.unchanged:
            return self._unchanged(provider, url, fetched, access_method,
                                   credential_partition)

        outcome = self.ingest_bytes(
            fetched.body or b"", provider=provider, kind=kind,
            filename=_filename_of(url), source_ref=fetched.url,
            source_url=url, external_id=external_id,
            access_method=access_method,
            media_type=_media_type_of(fetched),
            http_status=fetched.http_status, attempts=fetched.attempts,
            **document_fields)
        if outcome.ok and cacheable:
            self.state.remember(provider, url, etag=fetched.etag,
                                last_modified=fetched.last_modified,
                                source_document_id=outcome.source_document_id,
                                acquired_at=self.clock.utcnow(),
                                final_url=fetched.url,
                                final_key=fetched.resource_key,
                                credential_partition=credential_partition)
        return outcome

    def _save_cooldowns(self) -> None:
        """Persist pending provider deadlines, so a resumed run honours them."""
        scheduler = getattr(self.acquirer, "scheduler", None)
        if scheduler is None:
            return
        self.state.set_cooldowns(scheduler.pending_cooldowns())

    def ingest(self, reference: str, *, provider: str,
               **fields: Any) -> AcquisitionOutcome:
        """Dispatch one reference: a URL, an existing path, or a build code."""
        text = reference.strip()
        if "://" in text.split("?", 1)[0][:12]:
            return self.ingest_url(text, provider=provider, **fields)
        if Path(text).exists():
            return self.ingest_file(text, provider=provider, **fields)
        return self.ingest_build_code(text, provider=provider, **fields)

    # -- record construction -----------------------------------------------

    def _existing(self, record_id: str):
        from ..storage.errors import RecordNotFound

        try:
            return self.store.get_source(record_id)
        except RecordNotFound:
            return None

    def _unchanged(self, provider: str, url: str, fetched: FetchOutcome,
                   access_method: AccessMethod,
                   credential_partition: str | None) -> AcquisitionOutcome:
        # Keyed by the URL that was asked for, not by the one the redirect
        # chain ended at: the validator was stored against the former, so a
        # 304 has to be resolved against the former.
        known = self.state.document_for(
            provider, url, credential_partition=credential_partition)
        cached_final = self.state.final_key_for(
            provider, url, credential_partition=credential_partition)
        if not cached_final or cached_final != fetched.resource_key:
            # The starting URL now leads somewhere else. The validator we sent
            # describes the old target's representation, so this 304 says
            # nothing about the document we hold.
            return self._failed(provider, fetched.url, access_method,
                                AcquisitionStatus.INVALID_RESPONSE,
                                "304 from a location other than the one the "
                                "cached representation came from",
                                http_status=fetched.http_status,
                                attempts=fetched.attempts)
        document = self._existing(known) if known else None
        if document is None:
            # The validator was ours but the document is gone. That is not a
            # successful acquisition of anything.
            return self._failed(provider, fetched.url, access_method,
                                AcquisitionStatus.INVALID_RESPONSE,
                                "304 for a document this corpus no longer holds",
                                http_status=fetched.http_status,
                                attempts=fetched.attempts)
        result = self._result(provider, fetched.url, access_method,
                              AcquisitionStatus.OK,
                              source_document_id=document.record_id,
                              http_status=fetched.http_status,
                              retry_eligible=False,
                              diagnostic="not modified; stored copy is current",
                              attempts=fetched.attempts)
        return AcquisitionOutcome(AcquisitionStatus.OK, result, document,
                                  created=False, unchanged=True,
                                  attempts=fetched.attempts)

    def _failed(self, provider: str, source_ref: str,
                access_method: AccessMethod, status: AcquisitionStatus,
                diagnostic: str | None, *, http_status: int | None = None,
                retry_eligible: bool = False, attempts: int = 1,
                deferral: Deferral | None = None) -> AcquisitionOutcome:
        if status is AcquisitionStatus.OK:
            raise ValueError("a failure cannot carry status ok")
        detail = diagnostic
        if deferral is not None and detail and deferral.describe() not in detail:
            detail = "%s %s" % (detail, deferral.describe())
        result = self._result(provider, source_ref, access_method, status,
                              source_document_id=None, http_status=http_status,
                              retry_eligible=retry_eligible, diagnostic=detail,
                              attempts=attempts)
        LOGGER.info("acquisition failed provider=%s ref=%s status=%s",
                    provider, redact_url(source_ref) if "://" in source_ref
                    else source_ref, status.value)
        return AcquisitionOutcome(status, result, None, created=False,
                                  attempts=attempts, deferral=deferral)

    def _result(self, provider: str, source_ref: str,
                access_method: AccessMethod, status: AcquisitionStatus, *,
                source_document_id: str | None, http_status: int | None,
                retry_eligible: bool, diagnostic: str | None,
                attempts: int,
                record_id: str | None = None) -> AcquisitionResult:
        now = self.clock.utcnow()
        record_id = record_id or str(uuid.uuid4())
        detail = diagnostic
        if detail is not None:
            detail = redact_diagnostic("%s (attempts=%d)" % (detail, attempts))
        result = AcquisitionResult(
            schema_version=SCHEMA_VERSION,
            record_id=record_id,
            created_at=now,
            # A successful attempt cites what it produced. A failed one has
            # nothing else to cite, and inventing a document for it is the one
            # thing this module must never do, so it is its own root.
            provenance_ids=[source_document_id or record_id],
            provider=provider,
            source_ref=_safe_ref(source_ref),
            access_method=AccessMethod(access_method),
            status=status,
            source_document_id=source_document_id,
            http_status=http_status,
            retry_eligible=retry_eligible,
            diagnostic=detail,
            attempted_at=now)
        self.store.put_acquisition_result(result)
        return result


def carries_credentials(headers: Mapping[str, str] | None) -> bool:
    """True when a caller header could be a credential.

    The same allow list the HTTP layer strips a cross-origin redirect with:
    anything not known to be safe is treated as a secret.
    """
    return any(str(name).lower() not in SAFE_HEADERS
               for name in (headers or {}))


def _status_for(refusal: ContentRefused) -> AcquisitionStatus:
    if isinstance(refusal, UnsupportedContent):
        return AcquisitionStatus.UNSUPPORTED_ACCESS
    if isinstance(refusal, (MalformedContent, OversizedContent)):
        return AcquisitionStatus.INVALID_RESPONSE
    return AcquisitionStatus.INVALID_RESPONSE


def _safe_ref(source_ref: str) -> str:
    return redact_url(source_ref) if "://" in source_ref else source_ref


def _media_type_of(fetched: FetchOutcome) -> str | None:
    declared = (fetched.media_type or "").strip()
    return declared[:200] or None


def _filename_of(url: str) -> str | None:
    path = redact_url(url).split("?", 1)[0]
    name = path.rsplit("/", 1)[-1]
    return name or None
