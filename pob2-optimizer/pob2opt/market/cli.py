"""`pob2opt market import --input FILE --corpus DIR --catalog DIR` (P05-T02).

Stores the file's bytes as a source document, then writes the items,
listings and the ParseResult naming them. Offline: no provider, no PoB.
JSON on stdout, prose on stderr.

``--catalog`` is the bundle from ``pob2opt catalog export``, as for
``pob2opt parse``: affix lines are checked against it and item records name
it. Item text is ``local_file``; a market capture file is
``manual_capture``.

Exit codes: ``0`` imported (``status`` may be ``partial``), ``2`` the file is
invalid, ``3`` the format, catalog or acquisition prevents the import (a
provider export is refused here, D01), ``4`` operational failure. Importing
the same bytes again under the same catalog reports the stored result.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Sequence

from ..acquisition import content as content_rules
from ..acquisition.service import AcquisitionService
from ..domain.enums import AccessMethod, ParseResultStatus
from ..parsers import formats
from ..parsers.cli import _load_catalog, import_catalog_bundle
from ..parsers.pob import ParseContext
from ..storage import RunStore
from .importer import import_market, import_record_id, item_availability

EXIT_OK = 0
EXIT_INVALID_REQUEST = 2
EXIT_BLOCKED = 3
EXIT_INTERNAL = 4


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="pob2opt market import",
        description="Import item text or a market capture file.")
    parser.add_argument("--input", required=True, help="item text or capture")
    parser.add_argument("--corpus", required=True, help="corpus directory")
    parser.add_argument("--catalog", required=True,
                        help="catalog bundle directory from `catalog export`")
    parser.add_argument("--provider", default="local",
                        help="source label for the stored document")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(list(sys.argv[3:] if argv is None else argv))
    path = Path(args.input).resolve()
    corpus = Path(args.corpus).resolve()
    bundle = Path(args.catalog).resolve()
    if not (bundle / "catalog.json").is_file():
        print("no catalog bundle at %s; run `pob2opt catalog export` first"
              % bundle, file=sys.stderr)
        return EXIT_BLOCKED
    try:
        catalog, profile, gaps, evidence, blobs, acquisition = \
            _load_catalog(bundle)
    except (OSError, ValueError, KeyError) as error:
        print("unreadable catalog bundle: %s" % error, file=sys.stderr)
        return EXIT_BLOCKED
    try:
        head = path.read_bytes()
    except OSError as error:
        print("cannot read %s: %s" % (path, error), file=sys.stderr)
        return EXIT_INVALID_REQUEST

    detected = formats.detect(head)
    kind = None
    access = AccessMethod.LOCAL_FILE
    if detected.format == formats.ITEM_TEXT:
        kind = content_rules.ITEM_TEXT
    elif detected.format in (formats.MARKET_CAPTURE, formats.PROVIDER_JSON):
        kind = content_rules.JSON
        if detected.format == formats.MARKET_CAPTURE:
            access = AccessMethod.MANUAL_CAPTURE

    with RunStore.open_corpus(corpus) as store:
        outcome = AcquisitionService(store).ingest_file(
            path, provider=args.provider, kind=kind, access_method=access)
        if not outcome.ok:
            print(json.dumps({"status": outcome.status.value,
                              "diagnostic": outcome.result.diagnostic},
                             indent=2, sort_keys=True))
            print("not stored: %s" % (outcome.result.diagnostic or ""),
                  file=sys.stderr)
            return EXIT_BLOCKED
        document = outcome.document
        context = ParseContext(
            catalog_hash=catalog.catalog_hash,
            created_at=datetime.now(timezone.utc).strftime(
                "%Y-%m-%dT%H:%M:%SZ"),
            entities=catalog.entities)
        result_id = import_record_id(document, context)
        if store.has_record(result_id):
            stored = store.get_record(result_id)
            print(json.dumps(_report(store, stored, None, unchanged=True),
                             indent=2, sort_keys=True))
            print("already imported: %s" % result_id, file=sys.stderr)
            return _exit_code(stored.status)
        if not import_catalog_bundle(store, catalog, profile, gaps, evidence,
                                     blobs, acquisition):
            return EXIT_BLOCKED

        def existing(record_id: str):
            return store.get_record(record_id) if store.has_record(record_id) \
                else None

        imported = import_market(document, store.read_payload(document.blob_hash),
                                 context, existing=existing)
        store.import_batch(imported.records)
        report = _report(store, imported.result, imported, unchanged=False)

    print(json.dumps(report, indent=2, sort_keys=True))
    print("market import %s: %d item(s), %d listing(s), %d issue(s)"
          % (report["status"], len(report["items"]), len(report["listings"]),
             len(report["issues"])), file=sys.stderr)
    return _exit_code(imported.result.status)


def _exit_code(status: ParseResultStatus) -> int:
    if status is ParseResultStatus.INVALID:
        return EXIT_INVALID_REQUEST
    if status is ParseResultStatus.UNSUPPORTED_FORMAT:
        return EXIT_BLOCKED
    return EXIT_OK


def _report(store, result, imported, *, unchanged: bool) -> dict:
    items = []
    listings = []
    for record_id in result.record_ids:
        record = store.get_record(record_id)
        if record_id.startswith("listing/"):
            listings.append({
                "listing_id": record.listing_id, "item_hash": record.item_hash,
                "price_amount": record.price_amount,
                "price_currency": record.price_currency,
                "quantity": record.quantity,
                "availability": record.availability.value,
                "observed_at": record.observed_at})
        else:
            items.append({
                "record_id": record.record_id, "item_hash": record.item_hash,
                "display_name": record.display_name,
                "parse_status": record.parse_status.value,
                "availability": item_availability(
                    store.find_normalized("listing", record.item_hash))})
    report = {
        "parse_result_id": result.record_id,
        "status": result.status.value,
        "source_document_id": result.source_document_id,
        "items": items,
        "listings": listings,
        "issues": [{"code": i.code, "field_path": i.field_path,
                    "source_locator": i.source_locator,
                    "explanation": i.explanation} for i in result.issues],
        "unchanged": unchanged,
    }
    if imported is not None:
        report["entries"] = [{"index": e.index, "item_hash": e.item_hash,
                              "listing_id": e.listing_id,
                              "listing_state": e.listing_state}
                             for e in imported.entries]
    return report
