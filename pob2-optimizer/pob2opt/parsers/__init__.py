"""Parsing and build normalization (P04).

Stored source bytes in, canonical records out: ``ParseResult``, one
``BuildSpec`` per build variant, ``ItemInstance`` records and unverified
``MechanicClaim`` records. Offline and deterministic; nothing in an input is
executed.

* ``formats`` and ``dispatch`` - format detection by signature and parser
  choice (P04-T01, T02);
* ``pob`` - PoB documents and sharing codes (P04-T01);
* ``resolve`` - catalog naming, exact name resolution, patch migration and
  item modifier matching (P04-T03);
* ``claims`` - claim extraction and the SQLite claim index (P04-T04);
* ``corpus`` - exact deduplication, family proposals and the field audit
  (P04-T05).
"""

from .claims import (ClaimHit, ClaimIndex, conflict_reason, extract_claims,
                     passage_for, with_conflicts)
from .corpus import (AuditResult, CorpusEntry, DuplicateGroup, FamilyLabel,
                     FamilyProposal, audit_summary, audit_variant,
                     exact_duplicates, holdout_split, independent_builds,
                     propose_family, review_family, with_family)
from .dispatch import parse_document, visible_text
from .formats import Detected, detect
from .pob import PARSER_ID, PARSER_VERSION, ParseContext, ParseOutcome
from .resolve import (Migration, NameResolution, NamingReport, item_readiness,
                      migrate_build, naming_from_catalog, resolve_item_modifiers,
                      resolve_name)

__all__ = [
    "AuditResult", "ClaimHit", "ClaimIndex", "CorpusEntry", "Detected",
    "DuplicateGroup", "FamilyLabel", "FamilyProposal", "Migration",
    "NameResolution", "NamingReport", "PARSER_ID", "PARSER_VERSION",
    "ParseContext", "ParseOutcome", "audit_summary", "audit_variant",
    "conflict_reason", "detect", "exact_duplicates", "extract_claims",
    "holdout_split", "independent_builds", "item_readiness", "migrate_build",
    "naming_from_catalog", "parse_document", "passage_for", "propose_family",
    "resolve_item_modifiers", "resolve_name", "review_family", "visible_text",
    "with_conflicts", "with_family",
]
