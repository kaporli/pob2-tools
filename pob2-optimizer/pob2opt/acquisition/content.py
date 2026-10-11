"""Payload kinds and the checks that refuse one (P03-T02).

Four input kinds are handled: a saved PoB XML build, a PoB build code, a guide
page as HTML, and a structured export as JSON. Acquisition stores the original
bytes of all four. It does not normalize them, and per architecture.md it does
not touch the engine.

What it does do is refuse. interfaces.md requires that a build code's expanded
payload is capped at 20 MiB and that malformed encoding and unsafe XML
constructs are rejected. A refusal is a typed failure, never an empty success,
so nothing downstream can mistake a rejected payload for a build with no gear.

Nothing here executes anything. HTML is never parsed, and a ``<script>`` body
is bytes like any other. ``tests/unit/test_p03_t02_local.py`` checks that this
package contains no ``eval``, ``exec`` or subprocess call at all.
"""

from __future__ import annotations

import base64
import binascii
import codecs
import json
import re
import zlib
from dataclasses import dataclass
from xml.etree import ElementTree

#: Expanded size cap for a compressed build code (interfaces.md).
MAX_EXPANDED_BYTES = 20 * 1024 * 1024
#: Nesting depth we refuse to parse past. Entity expansion is refused outright
#: below; this bounds the other way to exhaust a parser.
MAX_XML_DEPTH = 100
#: The same bound for JSON. CPython's scanner recurses, and on 3.10 a few
#: thousand levels raise ``RecursionError``, which is not a typed refusal. The
#: depth is therefore bounded before the parser is handed the document, so the
#: answer is the same on every supported interpreter.
MAX_JSON_DEPTH = 100

XML = "xml"
HTML = "html"
JSON = "json"
BUILD_CODE = "build_code"
KINDS = (XML, HTML, JSON, BUILD_CODE)

MEDIA_TYPES = {
    XML: "application/xml",
    HTML: "text/html",
    JSON: "application/json",
    BUILD_CODE: "text/vnd.pathofbuilding.code",
}

#: Constructs that make an XML document a resource request or an expansion
#: bomb. Matched on the decoded text, case-insensitively: a byte search finds
#: ``<!DOCTYPE`` in a UTF-8 document and misses it in a UTF-16 one, where
#: every character is two bytes.
UNSAFE_XML_MARKERS = ("<!doctype", "<!entity")

#: Encodings an XML payload may be in. Anything else is refused before
#: parsing. The alternative, decoding on a guess, is how the check above ends
#: up looking at different characters from the ones the parser will see.
#: Compared after :func:`_canonical_encoding`, so each spelling of a name is
#: one entry.
SUPPORTED_XML_ENCODINGS = frozenset({
    "utf8", "ascii", "usascii", "utf16", "utf16le", "utf16be", "iso88591",
    "latin1", "windows1252", "cp1252",
})

_XML_BOMS = (
    (codecs.BOM_UTF32_LE, "utf-32-le"),
    (codecs.BOM_UTF32_BE, "utf-32-be"),
    (codecs.BOM_UTF8, "utf-8-sig"),
    (codecs.BOM_UTF16_LE, "utf-16-le"),
    (codecs.BOM_UTF16_BE, "utf-16-be"),
)

_XML_DECLARED_ENCODING = re.compile(
    r"""^\s*<\?xml[^>]*?encoding\s*=\s*["']([A-Za-z0-9._-]+)["']""")


class ContentRefused(Exception):
    """A payload this layer will not store. ``reason`` is a short code."""

    def __init__(self, reason: str, detail: str) -> None:
        self.reason = reason
        self.detail = detail
        super().__init__("%s: %s" % (reason, detail))


class MalformedContent(ContentRefused):
    pass


class OversizedContent(ContentRefused):
    pass


class UnsupportedContent(ContentRefused):
    pass


@dataclass(frozen=True)
class ContentReport:
    kind: str
    media_type: str
    byte_count: int
    #: Set for a build code: how large it expands to. None for the rest.
    expanded_bytes: int | None = None


def detect_kind(payload: bytes, *, filename: str | None = None,
                media_type: str | None = None) -> str:
    """Guess the kind. An explicit kind always beats this."""
    if media_type:
        lowered = media_type.split(";")[0].strip().lower()
        if lowered in ("application/json", "text/json"):
            return JSON
        if lowered in ("application/xml", "text/xml"):
            return XML
        if lowered == "text/html":
            return HTML
        if lowered == MEDIA_TYPES[BUILD_CODE]:
            return BUILD_CODE
    if filename:
        suffix = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
        if suffix in ("xml", "pobbuild"):
            return XML
        if suffix in ("html", "htm"):
            return HTML
        if suffix == "json":
            return JSON
        if suffix in ("txt", "code", "pob"):
            return BUILD_CODE

    head = payload.lstrip()[:512]
    if head.startswith(b"<?xml") or head.startswith(b"<PathOfBuilding"):
        return XML
    lowered_head = head.lower()
    if lowered_head.startswith(b"<!doctype html") or lowered_head.startswith(b"<html"):
        return HTML
    if head.startswith(b"{") or head.startswith(b"["):
        return JSON
    if head and _looks_like_build_code(payload):
        return BUILD_CODE
    raise UnsupportedContent(
        "unknown_kind",
        "cannot tell what this payload is; pass the kind explicitly")


def inspect(payload: bytes, kind: str, *,
            max_expanded_bytes: int = MAX_EXPANDED_BYTES) -> ContentReport:
    """Check a payload of a declared kind. Raises :class:`ContentRefused`."""
    if kind not in KINDS:
        raise UnsupportedContent("unknown_kind", "%r is not an input kind" % (kind,))
    if not payload:
        raise MalformedContent("empty_payload", "the payload has no bytes")

    expanded = None
    if kind == JSON:
        _check_json(payload)
    elif kind == XML:
        check_xml(payload)
    elif kind == BUILD_CODE:
        expanded = len(decode_build_code(payload,
                                         max_expanded_bytes=max_expanded_bytes))
    # HTML is stored verbatim and never parsed. There is nothing to validate
    # that would not amount to interpreting it.
    return ContentReport(kind=kind, media_type=MEDIA_TYPES[kind],
                         byte_count=len(payload), expanded_bytes=expanded)


def _check_json(payload: bytes) -> None:
    try:
        text = payload.decode("utf-8")
    except UnicodeDecodeError as error:
        raise MalformedContent("json_encoding", str(error)) from None
    _check_json_depth(text)
    try:
        json.loads(text, parse_constant=_reject_constant)
    except ValueError as error:
        raise MalformedContent("json_syntax", str(error)) from None
    except RecursionError:
        # Belt and braces. The scan above bounds depth, but the interpreter's
        # own limit must still produce a refusal rather than an exception that
        # escapes the typed-failure boundary.
        raise MalformedContent(
            "json_too_deep",
            "the parser ran out of stack on this document") from None


def _check_json_depth(text: str) -> None:
    """Refuse past :data:`MAX_JSON_DEPTH` without parsing.

    A scan, not a parse: counting brackets outside string literals is enough
    to answer the question and cannot itself recurse.
    """
    depth = 0
    in_string = False
    escaped = False
    for char in text:
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char in "[{":
            depth += 1
            if depth > MAX_JSON_DEPTH:
                raise MalformedContent(
                    "json_too_deep",
                    "nesting deeper than %d levels" % MAX_JSON_DEPTH)
        elif char in "]}":
            depth -= 1


def _reject_constant(name: str):
    # contracts.md rejects NaN and Infinity outright, and json.loads accepts
    # them by default.
    raise ValueError("%s is not a permitted JSON value" % name)


def xml_text(payload: bytes) -> str:
    """Decode an XML payload, or refuse it. Never with ignored errors.

    The encoding is taken from a byte-order mark, then from the declaration,
    and defaults to UTF-8 as XML requires. An encoding outside
    :data:`SUPPORTED_XML_ENCODINGS` is refused rather than decoded on a guess.
    """
    encoding = _bom_encoding(payload)
    from_bom = encoding is not None
    if encoding is None:
        encoding = _nul_pattern_encoding(payload) or "utf-8"
    _require_supported_encoding(encoding)
    text = _decode_strictly(payload, encoding)

    declared = _declared_encoding(text)
    if declared is not None:
        _require_supported_encoding(declared)
        if not from_bom and _canonical_encoding(declared) != _canonical_encoding(encoding):
            text = _decode_strictly(payload, declared)
    return text


def _bom_encoding(payload: bytes) -> str | None:
    for bom, encoding in _XML_BOMS:
        if payload.startswith(bom):
            return encoding
    return None


def _nul_pattern_encoding(payload: bytes) -> str | None:
    """UTF-16 without a byte-order mark, which some exporters still write."""
    if payload[:2] == b"<\x00":
        return "utf-16-le"
    if payload[:2] == b"\x00<":
        return "utf-16-be"
    return None


def _canonical_encoding(name: str) -> str:
    lowered = name.strip().lower().replace("_", "-")
    if lowered.endswith("-sig"):
        lowered = lowered[:-4]
    return lowered.replace("-", "")


def _require_supported_encoding(name: str) -> None:
    if _canonical_encoding(name) not in SUPPORTED_XML_ENCODINGS:
        raise MalformedContent(
            "xml_encoding", "%s is not a supported XML encoding" % name)


def _decode_strictly(payload: bytes, encoding: str) -> str:
    try:
        return payload.decode(encoding)
    except (UnicodeDecodeError, LookupError) as error:
        raise MalformedContent("xml_encoding", str(error)) from None


def _declared_encoding(text: str) -> str | None:
    match = _XML_DECLARED_ENCODING.match(text.lstrip("\ufeff"))
    return match.group(1) if match else None


def check_xml(payload: bytes) -> None:
    """Refuse unsafe constructs, then confirm the document is well formed."""
    text = xml_text(payload)
    lowered = text.lower()
    for marker in UNSAFE_XML_MARKERS:
        if marker in lowered:
            raise MalformedContent(
                "unsafe_xml",
                "the document declares %s; a doctype or entity declaration is "
                "refused" % marker.upper())
    depth = 0
    try:
        parser = ElementTree.XMLPullParser(events=("start", "end"))
        parser.feed(text)
        parser.close()
        for event, _ in parser.read_events():
            if event == "start":
                depth += 1
                if depth > MAX_XML_DEPTH:
                    raise MalformedContent(
                        "xml_too_deep",
                        "nesting deeper than %d elements" % MAX_XML_DEPTH)
            else:
                depth -= 1
    except ElementTree.ParseError as error:
        raise MalformedContent("xml_syntax", str(error)) from None


def decode_build_code(payload: bytes, *,
                      max_expanded_bytes: int = MAX_EXPANDED_BYTES) -> bytes:
    """Expand a PoB build code and return the XML it contains.

    The result is checked, not stored: acquisition keeps the code the user
    supplied, byte for byte. Expansion is bounded as it happens, so a payload
    that inflates past the cap is refused without ever being held in memory.
    """
    if max_expanded_bytes <= 0:
        raise ValueError("max_expanded_bytes must be positive")
    text = b"".join(payload.split())
    if not text:
        raise MalformedContent("empty_payload", "the build code has no bytes")
    padded = text + b"=" * (-len(text) % 4)
    try:
        compressed = base64.urlsafe_b64decode(padded)
    except (binascii.Error, ValueError) as error:
        raise MalformedContent("base64", str(error)) from None
    if not compressed:
        raise MalformedContent("base64", "the build code decodes to no bytes")

    decompressor = zlib.decompressobj()
    out = bytearray()
    pending = compressed
    # One byte of headroom over the cap, so "exactly at the cap" and "over it"
    # are distinguishable without expanding the whole payload first.
    budget = max_expanded_bytes + 1
    try:
        while pending and len(out) < budget:
            out += decompressor.decompress(pending, budget - len(out))
            pending = decompressor.unconsumed_tail
        if len(out) < budget:
            out += decompressor.flush(budget - len(out))
    except zlib.error as error:
        raise MalformedContent("deflate", str(error)) from None
    if len(out) > max_expanded_bytes:
        raise OversizedContent(
            "expanded_too_large",
            "the build code expands past the %d byte cap" % max_expanded_bytes)
    if not decompressor.eof:
        raise MalformedContent("deflate", "the compressed stream is truncated")
    check_xml(bytes(out))
    return bytes(out)


_CODE_ALPHABET = frozenset(
    b"ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_=+/")


def _looks_like_build_code(payload: bytes) -> bool:
    body = b"".join(payload.split())
    return bool(body) and all(byte in _CODE_ALPHABET for byte in body)
