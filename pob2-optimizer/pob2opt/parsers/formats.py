"""Format dispatch by signature (P04-T01).

The parser is chosen from the bytes, not the file name. A declared format is
honoured only when the bytes agree with it; a mismatch is reported rather
than parsed as the declared kind.

Signatures, checked in this order:

* ``pob_xml``: an XML document whose root element is ``PathOfBuilding2``.
  A ``PathOfBuilding`` root is the Path of Exile 1 format and is
  ``unsupported_format`` here.
* ``saved_html``: a document starting with a doctype or ``<html``.
* ``provider_json``: a JSON object or array. No P03 provider representation
  is approved (D02 is unresolved), so these have no parser yet.
* ``item_text``: PoB or game clipboard item text, starting ``Rarity:`` or
  ``Item Class:``.
* ``pob_code``: a PoB sharing code, which decodes to ``pob_xml``.

Decoding reuses the acquisition layer's bounded checks, so a truncated code,
an expansion past the cap, a doctype or entity declaration and malformed XML
are refused with a typed reason. Nothing is executed.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from dataclasses import dataclass

from ..acquisition import content as content_rules

POB_XML = "pob_xml"
POB_CODE = "pob_code"
ITEM_TEXT = "item_text"
SAVED_HTML = "saved_html"
PROVIDER_JSON = "provider_json"
UNKNOWN = "unknown"

FORMATS = (POB_XML, POB_CODE, ITEM_TEXT, SAVED_HTML, PROVIDER_JSON)

POB2_ROOT = "PathOfBuilding2"
POB1_ROOT = "PathOfBuilding"


@dataclass(frozen=True)
class Detected:
    """What the bytes are, and the XML text when they hold a PoB document."""

    format: str
    #: Set when the payload is refused; ``reason`` is a short code.
    refused: bool = False
    reason: str = ""
    detail: str = ""
    #: Decoded PoB XML for ``pob_xml`` and ``pob_code``.
    xml: str | None = None
    #: Decoded text for ``item_text``, ``saved_html`` and ``provider_json``.
    text: str | None = None


def _xml_root_tag(text: str) -> str | None:
    try:
        return ET.fromstring(text).tag
    except ET.ParseError:
        return None


def detect(payload: bytes, *, declared: str | None = None) -> Detected:
    """The format of ``payload``. ``declared`` must agree with the bytes."""
    if declared is not None and declared not in FORMATS:
        return Detected(UNKNOWN, True, "unknown_declared_format",
                        "%r is not a parseable format" % declared)
    found = _detect(payload)
    if declared is not None and not found.refused and found.format != declared:
        return Detected(found.format, True, "declared_format_mismatch",
                        "declared %s but the bytes are %s"
                        % (declared, found.format))
    return found


def _detect(payload: bytes) -> Detected:
    if not payload or not payload.strip():
        return Detected(UNKNOWN, True, "empty_payload", "the payload has no bytes")
    head = payload.lstrip()[:512]
    lowered = head.lower()

    if head.startswith(b"<?xml") or head.startswith(b"<PathOfBuilding") \
            or head.startswith(b"\xef\xbb\xbf") or payload[:2] in (b"<\x00", b"\x00<"):
        return _pob_xml(payload)
    if lowered.startswith(b"<!doctype html") or lowered.startswith(b"<html"):
        return Detected(SAVED_HTML, text=payload.decode("utf-8", "replace"))
    if head.startswith(b"{") or head.startswith(b"["):
        try:
            text = payload.decode("utf-8")
        except UnicodeDecodeError as error:
            return Detected(PROVIDER_JSON, True, "json_encoding", str(error))
        return Detected(PROVIDER_JSON, text=text)
    if head.startswith(b"Rarity:") or head.startswith(b"Item Class:"):
        try:
            return Detected(ITEM_TEXT, text=payload.decode("utf-8"))
        except UnicodeDecodeError as error:
            return Detected(ITEM_TEXT, True, "text_encoding", str(error))
    if content_rules._looks_like_build_code(payload):
        try:
            xml_bytes = content_rules.decode_build_code(payload)
        except content_rules.ContentRefused as refused:
            return Detected(POB_CODE, True, refused.reason, refused.detail)
        inner = _pob_xml(xml_bytes)
        if inner.refused:
            return Detected(POB_CODE, True, inner.reason, inner.detail)
        return Detected(POB_CODE, xml=inner.xml)
    return Detected(UNKNOWN, True, "unknown_format",
                    "no supported format signature matches these bytes")


def _pob_xml(payload: bytes) -> Detected:
    try:
        content_rules.check_xml(payload)
        text = content_rules.xml_text(payload)
    except content_rules.ContentRefused as refused:
        return Detected(POB_XML, True, refused.reason, refused.detail)
    tag = _xml_root_tag(text.lstrip("﻿"))
    if tag == POB1_ROOT:
        return Detected(POB_XML, True, "pob1_document",
                        "a Path of Exile 1 PoB document, not a PoE 2 build")
    if tag != POB2_ROOT:
        return Detected(POB_XML, True, "layout_unrecognized",
                        "root element %r is not %s" % (tag, POB2_ROOT))
    return Detected(POB_XML, xml=text.lstrip("﻿"))
