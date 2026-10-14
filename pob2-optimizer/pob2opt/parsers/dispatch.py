"""Choose a parser for a stored source document (P04-T01/T02).

The registry maps a detected format to a parser. Provider pages and provider
JSON exports have no parser: P04-T02 requires one per P03-approved provider
representation, and D02 has approved none (``docs/decisions/D02``). Such a
document gets ``unsupported_format`` with the reason, and a saved guide page
still yields its prose as unverified claims, never a build.

Item text is parsed into one ``ItemInstance``. A name without stats stays a
template claim and the parse is partial.
"""

from __future__ import annotations

import html.parser
from dataclasses import replace
from typing import Callable

from ..domain.enums import ParseResultStatus, RecordParseStatus
from ..domain.identity import item_hash
from ..domain.records import ParseIssue, SourceDocument
from ..evaluation.itemtext import import_item
from . import formats
from .claims import extract_claims
from .pob import (ParseContext, ParseOutcome, _result, parse_pob_xml,
                  record_base, refused)
from .resolve import (TEMPLATE_CLAIM, item_readiness, naming_from_catalog)

ITEM_PARSER_ID = "pob2opt.parsers.itemtext"

#: Provider names from the P03 capability manifests. None has an approved
#: build-data representation.
BLOCKED_PROVIDERS = ("mobalytics", "maxroll", "poe-ninja")


def parse_document(document: SourceDocument, payload: bytes,
                   context: ParseContext, *,
                   declared_format: str | None = None) -> ParseOutcome:
    """Parse one stored document. Deterministic, offline, never executes."""
    if declared_format is not None:
        context = replace(context, declared_format=declared_format)
    detected = formats.detect(payload, declared=context.declared_format)
    if detected.refused:
        return refused(document, context, detected)
    handler = _HANDLERS.get(detected.format)
    if handler is None:
        return refused(document, context, formats.Detected(
            detected.format, True, "unsupported_format",
            "no parser for %s" % detected.format))
    return handler(document, detected, context)


def _pob(document, detected, context) -> ParseOutcome:
    return parse_pob_xml(document, detected.xml or "", context,
                         source_format=detected.format)


def _item(document, detected, context) -> ParseOutcome:
    naming = context.naming
    if naming is None:
        naming = naming_from_catalog(context.entities or {}).naming
    try:
        item = import_item(detected.text or "", naming,
                           record_id=record_base(document, context)
                           + "/item",
                           created_at=context.created_at,
                           catalog_hash=context.catalog_hash,
                           provenance_ids=[document.record_id],
                           source_document_id=document.record_id)
    except ValueError as error:
        return refused(document, context, formats.Detected(
            formats.ITEM_TEXT, True, "malformed_item_text", str(error)))
    issues = []
    if item.base_id is None:
        issues.append(ParseIssue("unresolved_base", "/base_id",
                                 item.display_name,
                                 "the base type is not in this catalog"))
    if item_readiness(item) == TEMPLATE_CLAIM:
        issues.append(ParseIssue(TEMPLATE_CLAIM, "/modifiers",
                                 item.display_name,
                                 "an item name without stats is a claim "
                                 "about which item is meant, not an item "
                                 "ready for calculation"))
    if issues and item.parse_status is RecordParseStatus.COMPLETE:
        item = replace(item, parse_status=RecordParseStatus.PARTIAL)
        item = replace(item, item_hash=item_hash(item))
    status = ParseResultStatus.PARTIAL if issues else ParseResultStatus.COMPLETE
    result = _result(document, context, status, issues,
                     record_ids=[item.record_id],
                     extensions={"format": formats.ITEM_TEXT})
    result = _with_parser(result, ITEM_PARSER_ID)
    return ParseOutcome(result=result, items=(item,))


def _with_parser(result, parser_id: str):
    return replace(result, parser_id=parser_id)


class _VisibleText(html.parser.HTMLParser):
    """Visible text of a saved page. Script and style bodies are dropped."""

    SKIP = frozenset({"script", "style", "noscript", "template"})
    BLOCK = frozenset({"p", "div", "li", "br", "h1", "h2", "h3", "h4", "h5",
                       "h6", "section", "article", "tr"})

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self._skip = 0

    def handle_starttag(self, tag, attrs):
        if tag in self.SKIP:
            self._skip += 1
        elif tag in self.BLOCK:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in self.SKIP and self._skip:
            self._skip -= 1
        elif tag in self.BLOCK:
            self.parts.append("\n")

    def handle_data(self, data):
        if not self._skip:
            self.parts.append(data)

    def text(self) -> str:
        lines = [" ".join(line.split()) for line in "".join(self.parts).split("\n")]
        return "\n".join(line for line in lines if line)


def visible_text(page: str) -> str:
    parser = _VisibleText()
    parser.feed(page)
    parser.close()
    return parser.text()


def _guide_page(document, detected, context) -> ParseOutcome:
    text = visible_text(detected.text or "")
    claims = extract_claims(text, document=document,
                            created_at=context.created_at,
                            entities=context.entities or {},
                            locator_prefix="/visible_text",
                            record_prefix=record_base(document, context))
    issue = _blocked_issue(document, "a saved guide page")
    result = _result(document, context, ParseResultStatus.PARTIAL, [issue],
                     record_ids=[c.record_id for c in claims],
                     extensions={"format": formats.SAVED_HTML,
                                 "visible_text": text})
    return ParseOutcome(result=result, claims=claims)


def _provider_json(document, detected, context) -> ParseOutcome:
    issue = _blocked_issue(document, "a provider JSON export")
    result = _result(document, context, ParseResultStatus.UNSUPPORTED_FORMAT,
                     [issue], extensions={"format": formats.PROVIDER_JSON})
    return ParseOutcome(result=result)


def _blocked_issue(document: SourceDocument, what: str) -> ParseIssue:
    return ParseIssue(
        "provider_parser_blocked", "/", document.provider,
        "%s from %r has no build-data parser: P04-T02 parses only "
        "P03-approved provider representations, and D02 has approved none. "
        "No build is produced; a title or a list of skill names is not a "
        "build" % (what, document.provider))


_HANDLERS: dict[str, Callable[..., ParseOutcome]] = {
    formats.POB_XML: _pob,
    formats.POB_CODE: _pob,
    formats.ITEM_TEXT: _item,
    formats.SAVED_HTML: _guide_page,
    formats.PROVIDER_JSON: _provider_json,
}
