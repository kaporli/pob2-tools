"""`pob2opt ingest --provider NAME --input PATH_OR_URL --corpus DIR` (P03-T02).

JSON on stdout, prose on stderr, as interfaces.md requires. Exit codes are the
shared ones:

* ``0`` the payload was acquired, or the stored copy is already current.
* ``2`` the request itself is wrong: an unknown kind, a missing argument.
* ``3`` access or coverage prevented it: ``unsupported_access``,
  ``access_blocked``, ``rate_limited``, ``not_found``.
* ``4`` an operational failure: ``invalid_response``, ``timeout``.

A URL needs ``--allow-host``. No host is approved by default: P03-T01 has not
chosen a provider, and this command will not invent one.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Sequence

from ..domain.enums import AccessMethod, AcquisitionStatus, Redistribution
from ..storage import RunStore
from . import content as content_rules
from .hosts import HostPolicy, HostRule
from .http import HttpAcquirer
from .limits import Limits
from .service import LOCAL_MANIFEST_ID, AcquisitionService
from .state import AcquisitionState
from .transport import RequestsTransport

EXIT_OK = 0
EXIT_INVALID_REQUEST = 2
EXIT_ACCESS = 3
EXIT_INTERNAL = 4

_EXIT_FOR = {
    AcquisitionStatus.OK: EXIT_OK,
    AcquisitionStatus.UNSUPPORTED_ACCESS: EXIT_ACCESS,
    AcquisitionStatus.ACCESS_BLOCKED: EXIT_ACCESS,
    AcquisitionStatus.RATE_LIMITED: EXIT_ACCESS,
    AcquisitionStatus.NOT_FOUND: EXIT_ACCESS,
    AcquisitionStatus.INVALID_RESPONSE: EXIT_INTERNAL,
    AcquisitionStatus.TIMEOUT: EXIT_INTERNAL,
}


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="pob2opt ingest",
        description="Acquire permitted input and preserve the raw payload.")
    parser.add_argument("--provider", required=True)
    parser.add_argument("--input", required=True,
                        help="a file path, a build code, or an approved URL")
    parser.add_argument("--corpus", required=True, help="corpus directory")
    parser.add_argument("--kind", choices=list(content_rules.KINDS), default=None,
                        help="declare the input kind instead of detecting it")
    parser.add_argument("--access-method", default=None,
                        choices=[m.value for m in AccessMethod])
    parser.add_argument("--redistribution", default=Redistribution.UNKNOWN.value,
                        choices=[r.value for r in Redistribution])
    parser.add_argument("--manifest-id", default=LOCAL_MANIFEST_ID,
                        help="capability manifest that approved this access")
    parser.add_argument("--external-id", default=None)
    parser.add_argument("--allow-host", action="append", default=[],
                        metavar="HOST",
                        help="approve one https host for this invocation; "
                             "repeatable. Without it no URL is fetched")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(list(sys.argv[2:] if argv is None else argv))
    reference = args.input.strip()
    is_url = "://" in reference.split("?", 1)[0][:12]

    if is_url and not args.allow_host:
        print("refusing to fetch a URL: no host is approved. Pass --allow-host "
              "HOST for a host whose capability manifest you have accepted.",
              file=sys.stderr)
        return EXIT_ACCESS

    acquirer = None
    if is_url:
        policy = HostPolicy.of(HostRule(host=host, approved_by="--allow-host")
                               for host in args.allow_host)
        acquirer = HttpAcquirer(transport=RequestsTransport(), policy=policy,
                                limits=Limits())

    corpus = Path(args.corpus).resolve()
    fields = {
        "redistribution": Redistribution(args.redistribution),
        "source_manifest_id": args.manifest_id,
    }
    if args.kind:
        fields["kind"] = args.kind
    if args.external_id:
        fields["external_id"] = args.external_id
    if args.access_method:
        fields["access_method"] = AccessMethod(args.access_method)

    with RunStore.open_corpus(corpus) as store:
        service = AcquisitionService(store, acquirer=acquirer,
                                     state=AcquisitionState.in_corpus(corpus))
        try:
            outcome = service.ingest(reference, provider=args.provider, **fields)
        except TypeError as error:
            print("invalid request: %s" % error, file=sys.stderr)
            return EXIT_INVALID_REQUEST

    document = outcome.document
    report = {
        "status": outcome.status.value,
        "provider": args.provider,
        "acquisition_result_id": outcome.result.record_id,
        "source_document_id": outcome.source_document_id,
        "blob_hash": outcome.blob_hash,
        "byte_count": document.byte_count if document is not None else None,
        "media_type": document.media_type if document is not None else None,
        "source_url": document.source_url if document is not None else None,
        "created": outcome.created,
        "unchanged": outcome.unchanged,
        "attempts": outcome.attempts,
        "http_status": outcome.result.http_status,
        "retry_eligible": outcome.result.retry_eligible,
        "retry_not_before": (outcome.deferral.not_before
                             if outcome.deferral is not None else None),
        "diagnostic": outcome.result.diagnostic,
    }
    print(json.dumps(report, indent=2, sort_keys=True))
    if outcome.ok:
        print("acquired %s as %s" % (args.provider, outcome.source_document_id),
              file=sys.stderr)
    else:
        print("acquisition %s: %s" % (outcome.status.value,
                                      outcome.result.diagnostic or ""),
              file=sys.stderr)
    return _EXIT_FOR[outcome.status]
