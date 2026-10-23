"""Item and listing import (P05-T02).

Input is a stored source document: item text (PoB or game clipboard format)
or a market capture file (``capture.py``). Output is ``ItemInstance`` and
``Listing`` records plus a ``ParseResult`` naming them.

Two identities, kept apart:

* An item is its canonical stats, ``item_hash`` (``domain/identity.py``). Its
  stored record ID is ``market-item/<catalog>/<item_hash>``, so equal stats are
  one item whatever their display names, and different rolls under one name
  are different items. A display name never merges or splits items.
* A listing is ``provider/realm/league/listing id``. Its ``listing_id`` (also
  its record ID) is that key, so two listings of equal-stat items are two
  listings sharing one ``item_hash``, and one listing seen twice is one.

Price is copied, never interpreted: the amount stays a decimal string in its
original currency, any currency is accepted, no amount is too high, and a
missing price is ``null``, not zero. Nothing here converts, caps or filters
by price. An item imported without a listing has no listing evidence; its
availability is ``unknown`` (``item_availability``).

A listing already stored with a different observation is a conflict: the
stored record is kept, the new one is not written, and the result is
partial. Replacing an observation is listing refresh (P05-T04), which D01
leaves without a route.

Pure: stored records are looked up through ``existing``; the caller writes.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any, Callable, Iterable, Sequence
from urllib.parse import quote

from ..domain.enums import Availability, ParseResultStatus, RecordParseStatus
from ..domain.identity import content_hash, listing_snapshot_hash
from ..domain.records import (SCHEMA_VERSION, CoverageCount, ItemInstance,
                              Listing, ParseIssue, ParseResult, SourceDocument)
from ..parsers import formats
from ..parsers.dispatch import read_item_text
from ..parsers.pob import ParseContext, parse_key
from .capture import Capture, CaptureEntry, read_capture

IMPORTER_ID = "pob2opt.market.import"
#: ``.2`` follows parser ``p04-t01.6`` (P02-T03.1).
IMPORTER_VERSION = "p05-t02.2"

#: Formats this importer reads. Provider JSON is refused (D01).
IMPORTABLE = (formats.ITEM_TEXT, formats.MARKET_CAPTURE)


def listing_key(provider: str, realm: str, league_id: str,
                external_id: str) -> str:
    """The listing identity: provider, realm, league and the provider's ID."""
    return "listing/" + "/".join(quote(part, safe="") for part in
                                 (provider, realm, league_id, external_id))


def item_record_id(catalog_hash: str, item_hash: str) -> str:
    return "market-item/%s/%s" % (catalog_hash[:16], item_hash)


def import_record_id(document: SourceDocument, context: ParseContext) -> str:
    """The ParseResult ID: source, importer version, catalog and options."""
    key = content_hash({"parse_key": parse_key(document, context),
                        "importer_version": IMPORTER_VERSION})[:16]
    return "%s/market-import/%s/%s" % (document.record_id, IMPORTER_VERSION,
                                       key)


@dataclass(frozen=True)
class EntryOutcome:
    """What one input entry became."""

    index: int
    item_hash: str | None
    listing_id: str | None
    #: ``created``, ``reused`` (already stored or earlier in this input) or
    #: ``conflict`` for the listing; None without one.
    listing_state: str | None


@dataclass(frozen=True)
class MarketImport:
    result: ParseResult
    #: Records to write. Items and listings already stored are not repeated.
    items: tuple[ItemInstance, ...] = ()
    listings: tuple[Listing, ...] = ()
    entries: tuple[EntryOutcome, ...] = ()
    #: Every item hash the input names, written now or already stored.
    item_hashes: tuple[str, ...] = ()

    @property
    def records(self) -> list[Any]:
        return [*self.items, *self.listings, self.result]


def import_market(document: SourceDocument, payload: bytes,
                  context: ParseContext, *,
                  existing: Callable[[str], Any | None] = lambda _id: None
                  ) -> MarketImport:
    """Read one stored document into item and listing records."""
    detected = formats.detect(payload)
    if detected.refused:
        return _refused(document, context, detected.reason,
                        detected.detail or detected.reason,
                        _status_for(detected.reason), detected.format)
    if detected.format == formats.PROVIDER_JSON:
        return _refused(
            document, context, "provider_export_blocked",
            "no provider export representation is approved: D01 records the "
            "public market route as unsupported_access. Use a "
            "pob2opt.market_capture file for listings you observed",
            ParseResultStatus.UNSUPPORTED_FORMAT, detected.format)
    if detected.format not in IMPORTABLE:
        return _refused(document, context, "unsupported_format",
                        "%s is not item text or a market capture"
                        % detected.format,
                        ParseResultStatus.UNSUPPORTED_FORMAT, detected.format)

    if detected.format == formats.ITEM_TEXT:
        capture = None
        entries = (CaptureEntry(0, detected.text or "", None),)
        extensions: dict[str, Any] = {"format": formats.ITEM_TEXT}
    else:
        capture, problems = read_capture(detected.text or "")
        if capture is None:
            issues = [ParseIssue(p.code, p.field_path, p.field_path,
                                 p.explanation) for p in problems]
            return MarketImport(_result(document, context,
                                        ParseResultStatus.INVALID, issues,
                                        extensions={"format": detected.format}))
        entries = capture.entries
        extensions = {"format": formats.MARKET_CAPTURE,
                      "unknown_fields": list(capture.unknown_fields)}
    return _import_entries(document, context, capture, entries, extensions,
                           existing)


def _import_entries(document, context, capture: Capture | None,
                    entries: Sequence[CaptureEntry], extensions, existing):
    issues: list[ParseIssue] = []
    invalid = False
    partial = False
    items: dict[str, ItemInstance] = {}
    item_hashes: list[str] = []
    listings: dict[str, Listing] = {}
    outcomes: list[EntryOutcome] = []
    present = resolved = 0

    for entry in entries:
        prefix = "/entries/%d" % entry.index
        read = read_item_text(entry.item_text, document, context,
                              record_id="pending")
        if read.item is None:
            invalid = True
            if read.refused is not None:
                issues.append(ParseIssue(read.refused.reason,
                                         prefix + "/item_text", prefix,
                                         read.refused.detail
                                         or read.refused.reason))
            for issue in read.issues:
                issues.append(replace(issue, field_path=prefix
                                      + "/item_text" + issue.field_path))
            outcomes.append(EntryOutcome(entry.index, None, None, None))
            continue
        for issue in read.issues:
            issues.append(replace(issue, source_locator=prefix + ":"
                                  + issue.source_locator))
        for count in read.coverage:
            present += count.present
            resolved += count.resolved
        item = replace(read.item, record_id=item_record_id(
            context.catalog_hash, read.item.item_hash))
        if item.parse_status is not RecordParseStatus.COMPLETE:
            partial = True
        if item.item_hash not in item_hashes:
            item_hashes.append(item.item_hash)
        if item.item_hash not in items and existing(item.record_id) is None:
            items[item.item_hash] = item

        if entry.listing is None:
            outcomes.append(EntryOutcome(entry.index, item.item_hash, None, None))
            continue
        assert capture is not None
        observed = entry.listing
        key = listing_key(capture.provider, capture.realm, capture.league_id,
                          observed.listing_id)
        listing = Listing(
            schema_version=SCHEMA_VERSION, record_id=key,
            created_at=context.created_at,
            provenance_ids=[document.record_id], listing_id=key,
            provider=capture.provider, realm=capture.realm,
            league_id=capture.league_id, item_hash=item.item_hash,
            price_amount=observed.price_amount,
            price_currency=observed.price_currency,
            listed_at=observed.listed_at, observed_at=observed.observed_at,
            last_checked_at=observed.observed_at,
            availability=Availability.OBSERVED,
            listing_url=observed.listing_url,
            source_document_id=document.record_id,
            quantity=observed.quantity)
        if key in listings:
            if _same(listings[key], listing):
                state = "reused"
            else:
                invalid = True
                state = "conflict"
                issues.append(ParseIssue(
                    "conflicting_listing", prefix + "/listing/listing_id",
                    prefix, "listing %r appears twice in this file with "
                    "different contents" % observed.listing_id))
        else:
            stored = existing(key)
            if stored is None:
                listings[key] = listing
                state = "created"
            elif _same(stored, listing):
                state = "reused"
            else:
                partial = True
                state = "conflict"
                issues.append(ParseIssue(
                    "listing_conflict", prefix + "/listing", prefix,
                    "listing %s is already stored with a different "
                    "observation; the stored record is kept. Replacing an "
                    "observation is listing refresh (P05-T04)" % key))
        outcomes.append(EntryOutcome(entry.index, item.item_hash, key, state))

    if invalid:
        result = _result(document, context, ParseResultStatus.INVALID, issues,
                         extensions=extensions)
        return MarketImport(result, entries=tuple(outcomes))
    coverage = [CoverageCount("items", len(entries), len(entries), 0)]
    if present:
        coverage.append(CoverageCount("item_affixes", present, resolved,
                                      present - resolved))
    record_ids = [item_record_id(context.catalog_hash, h) for h in item_hashes]
    record_ids += [o.listing_id for o in outcomes
                   if o.listing_id is not None and o.listing_state != "conflict"]
    status = ParseResultStatus.PARTIAL if partial else ParseResultStatus.COMPLETE
    result = _result(document, context, status, issues, coverage=coverage,
                     record_ids=list(dict.fromkeys(record_ids)),
                     extensions=extensions)
    return MarketImport(result, tuple(items.values()), tuple(listings.values()),
                        tuple(outcomes), tuple(item_hashes))


def _same(a: Listing, b: Listing) -> bool:
    return (listing_snapshot_hash(a) == listing_snapshot_hash(b)
            and a.listing_url == b.listing_url)


def _status_for(reason: str) -> ParseResultStatus:
    if reason in ("unknown_format", "pob1_document", "declared_format_mismatch"):
        return ParseResultStatus.UNSUPPORTED_FORMAT
    return ParseResultStatus.INVALID


def _refused(document, context, code, explanation, status, fmt) -> MarketImport:
    issue = ParseIssue(code, "/", "payload", explanation)
    return MarketImport(_result(document, context, status, [issue],
                                extensions={"format": fmt}))


def _result(document: SourceDocument, context: ParseContext,
            status: ParseResultStatus, issues: Sequence[ParseIssue],
            coverage: Sequence[CoverageCount] = (),
            record_ids: Sequence[str] = (),
            extensions: dict[str, Any] | None = None) -> ParseResult:
    return ParseResult(
        schema_version=SCHEMA_VERSION,
        record_id=import_record_id(document, context),
        created_at=context.created_at, provenance_ids=[document.record_id],
        status=status, parser_id=IMPORTER_ID, parser_version=IMPORTER_VERSION,
        source_document_id=document.record_id, record_ids=list(record_ids),
        field_coverage=list(coverage), issues=list(issues),
        raw_extensions=dict(extensions or {}))


def item_availability(listings: Iterable[Listing]) -> str:
    """An item's availability from the listings stored for its hash.

    No listing evidence is ``unknown``. Otherwise the best evidence held:
    ``rechecked`` over ``observed`` over ``unknown`` over ``unavailable``.
    """
    order = (Availability.RECHECKED, Availability.OBSERVED,
             Availability.UNKNOWN, Availability.UNAVAILABLE)
    seen = {listing.availability for listing in listings}
    for availability in order:
        if availability in seen:
            return availability.value
    return Availability.UNKNOWN.value
