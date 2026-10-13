"""Build source acquisition (P03-T02).

Local input and the shared HTTP layer. This package turns a file, a build code
or an approved URL into the two P01 records that describe it, and refuses
everything else with a typed status.

Read in this order:

* ``redaction`` - what is removed from a URL, a header and a diagnostic.
* ``hosts`` - the allow list. Nothing is approved by default.
* ``limits`` - the interfaces.md defaults, and how a provider tightens them.
* ``transport`` - the one seam a test replaces; no policy lives there.
* ``scheduling`` - pacing, and why an advertised delay is never truncated.
* ``content`` - the four input kinds and the checks that refuse one.
* ``http`` - the fetch loop: policy, limits, statuses, conditional requests.
* ``state`` - cached validators and resume cursors.
* ``service`` - immutable writes through ``pob2opt.storage``.

Per architecture.md the coordinator owns network acquisition; a worker never
calls this. Nothing here imports the engine, so acquisition runs with no PoB
checkout at all.
"""

from __future__ import annotations

from .content import (
    BUILD_CODE,
    HTML,
    JSON,
    KINDS,
    MEDIA_TYPES,
    XML,
    ContentRefused,
    ContentReport,
    MalformedContent,
    OversizedContent,
    UnsupportedContent,
    decode_build_code,
    detect_kind,
    inspect,
)
from .hosts import HostPolicy, HostRule, PolicyRefusal
from .http import HttpAcquirer, FetchOutcome, Validators, classify
from .limits import Limits, ProviderLimits
from .redaction import REDACTED, redact_headers, redact_url
from .scheduling import Clock, Deferral, ProviderScheduler, SystemClock, parse_retry_after
from .service import (
    ACQUISITION_VERSION,
    LOCAL_MANIFEST_ID,
    AcquisitionOutcome,
    AcquisitionService,
    source_document_id,
)
from .state import AcquisitionState
from .transport import (
    Request,
    RequestsTransport,
    Response,
    Transport,
    TransportConnectionError,
    TransportError,
    TransportTimeout,
)

__all__ = [
    "ACQUISITION_VERSION", "AcquisitionOutcome", "AcquisitionService",
    "AcquisitionState", "BUILD_CODE", "Clock", "ContentRefused",
    "ContentReport", "Deferral", "FetchOutcome", "HTML", "HostPolicy",
    "HostRule", "HttpAcquirer", "JSON", "KINDS", "LOCAL_MANIFEST_ID",
    "Limits", "MEDIA_TYPES", "MalformedContent", "OversizedContent",
    "PolicyRefusal", "ProviderLimits", "ProviderScheduler", "REDACTED",
    "Request", "RequestsTransport", "Response", "SystemClock", "Transport",
    "TransportConnectionError", "TransportError", "TransportTimeout",
    "UnsupportedContent", "Validators", "XML", "classify",
    "decode_build_code", "detect_kind", "inspect", "parse_retry_after",
    "redact_headers", "redact_url", "source_document_id",
]
