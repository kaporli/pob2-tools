"""The local market capture file (P05-T02).

D01 approves no provider route and no provider export representation, so the
only listing input is this file: what a user saw, typed or pasted by them.
It is labelled ``manual_capture`` and is never a provider export. A provider's
own JSON stays refused until a route and its representation are approved.

Format version 1::

    {
      "format": "pob2opt.market_capture",
      "format_version": 1,
      "provider": "<where the listings were seen>",
      "realm": "poe2",
      "league_id": "<league name>",
      "observed_at": "2026-10-16T18:00:00Z",
      "entries": [
        {"item_text": "<PoB or game clipboard item text>",
         "listing": {"listing_id": "<the provider's listing id>",
                     "price": {"amount": "1000", "currency": "divine"},
                     "quantity": 1,
                     "listed_at": null,
                     "listing_url": null,
                     "observed_at": "<optional override>"}},
        {"item_text": "...", "listing": null}
      ]
    }

``price`` null or absent is an unknown price, never zero. ``amount`` is a
decimal string in the original currency; a JSON number is refused because a
float cannot carry a price exactly. ``quantity`` null or absent is unknown. An
entry without ``listing`` has no listing evidence. Keys not listed here are
kept in the stored bytes and named in the result, not interpreted.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

from ..parsers.formats import MARKET_CAPTURE_FORMAT

FORMAT_VERSION = 1

_TIMESTAMP = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?Z$")
_DECIMAL = re.compile(r"^\d+(\.\d+)?$")

TOP_KEYS = frozenset({"format", "format_version", "provider", "realm",
                      "league_id", "observed_at", "entries"})
ENTRY_KEYS = frozenset({"item_text", "listing"})
LISTING_KEYS = frozenset({"listing_id", "price", "quantity", "listed_at",
                          "listing_url", "observed_at"})
PRICE_KEYS = frozenset({"amount", "currency"})


@dataclass(frozen=True)
class CaptureIssue:
    code: str
    field_path: str
    explanation: str


@dataclass(frozen=True)
class CaptureListing:
    listing_id: str
    price_amount: str | None
    price_currency: str | None
    quantity: int | None
    listed_at: str | None
    listing_url: str | None
    observed_at: str


@dataclass(frozen=True)
class CaptureEntry:
    index: int
    item_text: str
    listing: CaptureListing | None


@dataclass(frozen=True)
class Capture:
    provider: str
    realm: str
    league_id: str
    observed_at: str
    entries: tuple[CaptureEntry, ...]
    #: JSON Pointers of keys this version does not read.
    unknown_fields: tuple[str, ...]


class _Reader:
    def __init__(self) -> None:
        self.issues: list[CaptureIssue] = []
        self.unknown: list[str] = []

    def fail(self, code: str, path: str, explanation: str) -> None:
        self.issues.append(CaptureIssue(code, path, explanation))

    def known(self, value: dict, keys: frozenset, path: str) -> None:
        for key in sorted(set(value) - keys):
            self.unknown.append("%s/%s" % (path, key))

    def text(self, value: dict, key: str, path: str, *,
             nullable: bool = False) -> str | None:
        found = value.get(key)
        if found is None and nullable:
            return None
        if not isinstance(found, str) or not found.strip():
            self.fail("missing_field" if found is None else "invalid_field",
                      "%s/%s" % (path, key), "a non-empty string is required")
            return None
        return found

    def timestamp(self, value: dict, key: str, path: str, *,
                  nullable: bool = False) -> str | None:
        found = self.text(value, key, path, nullable=nullable)
        if found is not None and not _TIMESTAMP.match(found):
            self.fail("invalid_timestamp", "%s/%s" % (path, key),
                      "an RFC 3339 UTC timestamp ending in Z is required")
            return None
        return found


def read_capture(text: str) -> tuple[Capture | None, list[CaptureIssue]]:
    """The capture, or None with every issue found. Nothing is defaulted."""
    reader = _Reader()
    try:
        data = json.loads(text)
    except ValueError as error:
        return None, [CaptureIssue("json_syntax", "/", str(error))]
    if not isinstance(data, dict) or data.get("format") != MARKET_CAPTURE_FORMAT:
        return None, [CaptureIssue("not_a_capture", "/format",
                                   "format must be %r" % MARKET_CAPTURE_FORMAT)]
    if data.get("format_version") != FORMAT_VERSION:
        return None, [CaptureIssue(
            "unsupported_format_version", "/format_version",
            "this reader supports format_version %d" % FORMAT_VERSION)]
    reader.known(data, TOP_KEYS, "")
    provider = reader.text(data, "provider", "")
    realm = reader.text(data, "realm", "")
    league_id = reader.text(data, "league_id", "")
    observed_at = reader.timestamp(data, "observed_at", "")
    raw_entries = data.get("entries")
    if not isinstance(raw_entries, list) or not raw_entries:
        reader.fail("missing_field", "/entries",
                    "a non-empty list of entries is required")
        raw_entries = []

    entries: list[CaptureEntry] = []
    for index, raw in enumerate(raw_entries):
        path = "/entries/%d" % index
        if not isinstance(raw, dict):
            reader.fail("invalid_field", path, "an entry is an object")
            continue
        reader.known(raw, ENTRY_KEYS, path)
        item_text = reader.text(raw, "item_text", path)
        listing = None
        if raw.get("listing") is not None:
            listing = _listing(reader, raw["listing"], path + "/listing",
                               observed_at)
        if item_text is not None:
            entries.append(CaptureEntry(index, item_text, listing))
    if reader.issues:
        return None, reader.issues
    return Capture(provider, realm, league_id, observed_at, tuple(entries),
                   tuple(reader.unknown)), []


def _listing(reader: _Reader, raw: Any, path: str,
             observed_at: str | None) -> CaptureListing | None:
    if not isinstance(raw, dict):
        reader.fail("invalid_field", path, "a listing is an object or null")
        return None
    reader.known(raw, LISTING_KEYS, path)
    listing_id = reader.text(raw, "listing_id", path)
    amount = currency = None
    price = raw.get("price")
    if price is not None:
        if not isinstance(price, dict):
            reader.fail("invalid_field", path + "/price",
                        "a price is an object or null")
        else:
            reader.known(price, PRICE_KEYS, path + "/price")
            raw_amount = price.get("amount")
            if not isinstance(raw_amount, str) or not _DECIMAL.match(raw_amount):
                reader.fail("price_not_decimal_string", path + "/price/amount",
                            "a price amount is a non-negative decimal string "
                            "such as \"1000\" or \"2.5\"; a JSON number or "
                            "an empty amount is refused")
            else:
                amount = raw_amount
            currency = reader.text(price, "currency", path + "/price")
    quantity = raw.get("quantity")
    if quantity is not None and (isinstance(quantity, bool)
                                 or not isinstance(quantity, int)
                                 or quantity < 1):
        reader.fail("invalid_field", path + "/quantity",
                    "quantity is an integer of at least 1, or null")
        quantity = None
    listed_at = reader.timestamp(raw, "listed_at", path, nullable=True)
    listing_url = reader.text(raw, "listing_url", path, nullable=True)
    own = reader.timestamp(raw, "observed_at", path, nullable=True)
    if listing_id is None or (own or observed_at) is None:
        return None
    return CaptureListing(listing_id, amount, currency, quantity, listed_at,
                          listing_url, own or observed_at)
