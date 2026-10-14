"""Deterministic mechanics claims from guide text, and their search (P04-T04).

Extraction is a fixed procedure: split the text into sections at headings,
split sections into sentences, and keep each sentence that names at least one
catalog entity by its exact name. Each kept sentence becomes one
``MechanicClaim`` with status ``unverified``, the entity IDs it names, a short
excerpt, and a locator holding the character offsets of the passage in the
original text, so a reviewer can retrieve it exactly.

What extraction never does:

* run, compile or interpret the text. A sentence that reads like an
  instruction ("ignore the policy", "run this") is stored as text and nothing
  else; this module imports no code-execution facility and no acquisition
  policy;
* grade a claim. Every claim is ``unverified`` however popular its source is.
  A guide's favourites are not gameplay evidence;
* pick between entities. A name shared by several catalog entities is left
  out of ``subject_ids``.

:class:`ClaimIndex` is an SQLite store with full-text search over section
headings and claim text, plus a filter by subject entity. Conflicting claims
are found by a fixed rule and kept side by side with a conflict mark; neither
replaces the other.
"""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from dataclasses import dataclass, replace
from typing import Iterable, Mapping, Sequence

from ..domain.enums import ClaimStatus
from ..domain.records import (SCHEMA_VERSION, CatalogEntity, MechanicClaim,
                              SourceDocument)

EXTRACTOR_VERSION = "p04-t04.1"

#: Longest excerpt kept. contracts.md: excerpts are short and attributed.
MAX_EXCERPT_CHARS = 300

#: Entity tables whose names count as explicit references. Ordinary passive
#: nodes are left out: thousands share names such as "Attribute".
REFERENCE_TABLES = ("classes", "ascendancies", "gems", "granted_skills",
                    "item_bases")
#: Passive nodes are references when they are notable or keystone.
NOTABLE_FLAGS = ("isNotable", "isKeystone")

#: A shorter name is too likely to be an ordinary word.
MIN_NAME_CHARS = 4

_HEADING = re.compile(r"^\s*(#{1,6}\s+.+|[^.!?\n]{2,60}:\s*|[A-Z0-9 '&-]{4,60})\s*$")
_SENTENCE_END = re.compile(r"(?<=[.!?])\s+|\n\s*[-*•]\s+|\n{2,}")
_PATCH = re.compile(r"\b(?:patch|version|v)\s*(\d+\.\d+(?:\.\d+)?[a-z]?)\b",
                    re.IGNORECASE)
_NUMBER = re.compile(r"\d+(?:\.\d+)?")
_NEGATION = re.compile(r"\b(?:not|no|never|cannot|can't|doesn't|don't|"
                       r"isn't|won't)\b", re.IGNORECASE)
_COLOUR = re.compile(r"\^(?:x[0-9A-Fa-f]{6}|\d)")


@dataclass(frozen=True)
class Passage:
    heading: str
    start: int
    end: int
    text: str


def _strip_colour(text: str) -> str:
    """PoB notes carry colour codes such as ``^7``; they are not prose."""
    return _COLOUR.sub("", text)


def passages(text: str) -> list[Passage]:
    """Sentences with their section heading and offsets into ``text``."""
    out: list[Passage] = []
    heading = ""
    position = 0
    for line in text.splitlines(keepends=True):
        stripped = line.strip()
        if stripped and _HEADING.match(stripped) and len(stripped) <= 60 \
                and not stripped.endswith("."):
            heading = stripped.lstrip("#").strip().rstrip(":").strip()
            position += len(line)
            continue
        if stripped:
            out.extend(_sentences(line, position, heading))
        position += len(line)
    return out


def _sentences(line: str, offset: int, heading: str) -> list[Passage]:
    out = []
    start = 0
    pieces = [m.end() for m in _SENTENCE_END.finditer(line)] + [len(line)]
    for end in pieces:
        chunk = line[start:end]
        lead = len(chunk) - len(chunk.lstrip(" \t-*•"))
        body = chunk.strip(" \t\r\n-*•")
        if body:
            begin = offset + start + lead
            out.append(Passage(heading, begin, begin + len(body), body))
        start = end
    return out


def _names(entities: Mapping[str, Sequence[CatalogEntity]]
           ) -> dict[str, list[list[str]]]:
    """Name to its candidate subjects. Each candidate is a list of IDs.

    A gem and the skill it grants share a name and are one subject, so they
    form one candidate. Any other repeat is a second candidate, which makes
    the name ambiguous.
    """
    granted = {}
    for gem in entities.get("gems", ()):
        raw = gem.raw_reference if isinstance(gem.raw_reference, dict) else {}
        if raw.get("grantedEffectId"):
            granted[raw["grantedEffectId"]] = gem.entity_id
    by_name: dict[str, list[list[str]]] = {}

    def add(name: str, ident: str, link: str | None = None) -> None:
        if len(name) < MIN_NAME_CHARS:
            return
        candidates = by_name.setdefault(name, [])
        for candidate in candidates:
            if ident in candidate:
                return
            if link is not None and link in candidate:
                candidate.append(ident)
                return
        candidates.append([ident])

    for table in REFERENCE_TABLES:
        for entity in entities.get(table, ()):
            raw = entity.raw_reference if isinstance(entity.raw_reference,
                                                     dict) else {}
            link = granted.get(raw.get("id")) if table == "granted_skills"                 else None
            for name in entity.display_names:
                add(name, entity.entity_id, link)
    for entity in entities.get("passive_nodes", ()):
        raw = entity.raw_reference if isinstance(entity.raw_reference, dict) \
            else {}
        if any(raw.get(flag) for flag in NOTABLE_FLAGS):
            for name in entity.display_names:
                add(name, entity.entity_id)
    return by_name


def _subjects(text: str, by_name: Mapping[str, list[list[str]]],
              pattern: re.Pattern[str] | None) -> list[str]:
    if pattern is None:
        return []
    subjects: set[str] = set()
    for match in pattern.finditer(text):
        candidates = by_name[match.group(0)]
        if len(candidates) == 1:
            subjects.update(candidates[0])
    return sorted(subjects)


def _pattern(by_name: Mapping[str, list[list[str]]]) -> re.Pattern[str] | None:
    if not by_name:
        return None
    names = sorted(by_name, key=lambda n: (-len(n), n))
    return re.compile(r"(?<!\w)(?:%s)(?!\w)" % "|".join(map(re.escape, names)))


def extract_claims(text: str, *, document: SourceDocument, created_at: str,
                   entities: Mapping[str, Sequence[CatalogEntity]],
                   locator_prefix: str = "",
                   record_prefix: str | None = None
                   ) -> tuple[MechanicClaim, ...]:
    """Unverified claims, one per sentence that names a catalog entity.

    ``locator_prefix`` names where ``text`` sits in the source document, for
    example ``/Notes``. Offsets in the locator index ``text`` itself.
    ``record_prefix`` names the claims; it defaults to the document's ID, and
    a parser passes its parse context so another catalog makes other IDs.
    """
    if record_prefix is None:
        record_prefix = document.record_id
    by_name = _names(entities)
    pattern = _pattern(by_name)
    declared = document.declared_patch
    claims: list[MechanicClaim] = []
    for passage in passages(text):
        clean = _strip_colour(passage.text)
        subjects = _subjects(clean, by_name, pattern)
        if not subjects:
            continue
        patch_match = _PATCH.search(clean) or _PATCH.search(passage.heading)
        locator = "%s#chars=%d-%d" % (locator_prefix, passage.start,
                                      passage.end)
        if passage.heading:
            locator += ";section=%s" % passage.heading
        excerpt = clean if len(clean) <= MAX_EXCERPT_CHARS else \
            clean[:MAX_EXCERPT_CHARS - 1].rstrip() + "…"
        digest = hashlib.sha256(("%s\0%s" % (locator, excerpt)).encode(
            "utf-8")).hexdigest()[:16]
        claims.append(MechanicClaim(
            schema_version=SCHEMA_VERSION,
            record_id="%s/claim/%s" % (record_prefix, digest),
            created_at=created_at, provenance_ids=[document.record_id],
            subject_ids=subjects, claim_text=excerpt,
            source_document_id=document.record_id, source_locator=locator,
            applies_to_patch=(patch_match.group(1) if patch_match
                              else declared),
            dependencies=[], status=ClaimStatus.UNVERIFIED,
            evidence_ids=[document.record_id]))
    return tuple(claims)


def passage_for(claim: MechanicClaim, text: str) -> str:
    """The original passage a claim's locator points at."""
    match = re.search(r"#chars=(\d+)-(\d+)", claim.source_locator)
    if match is None:
        raise ValueError("locator %r has no character offsets"
                         % claim.source_locator)
    return text[int(match.group(1)):int(match.group(2))]


# -------------------------------------------------------------- conflicts ---

def _shape(text: str) -> str:
    """Text with numbers and negations abstracted, for the conflict rule."""
    lowered = _NEGATION.sub(" ", text.lower())
    lowered = _NUMBER.sub("#", lowered)
    return " ".join(re.findall(r"[a-z#]+", lowered))


def _signature(text: str) -> tuple[tuple[str, ...], bool]:
    return (tuple(_NUMBER.findall(text)), bool(_NEGATION.search(text)))


def conflict_reason(a: MechanicClaim, b: MechanicClaim) -> str | None:
    """Why two claims conflict, or ``None``.

    The fixed rule: the same subjects and the same patch, the same sentence
    once numbers and negations are abstracted, and different numbers or a
    different negation. Anything looser would need judgement this module
    does not have.
    """
    if a.record_id == b.record_id or sorted(a.subject_ids) != sorted(
            b.subject_ids) or a.applies_to_patch != b.applies_to_patch:
        return None
    if _shape(a.claim_text) != _shape(b.claim_text):
        return None
    numbers_a, negated_a = _signature(a.claim_text)
    numbers_b, negated_b = _signature(b.claim_text)
    if negated_a != negated_b:
        return "one statement negates the other"
    if numbers_a != numbers_b:
        return "the statements give different numbers"
    return None


def with_conflicts(claims: Sequence[MechanicClaim]) -> tuple[MechanicClaim, ...]:
    """Claims with conflicting pairs marked ``contradicted``; none removed.

    Each contradicted claim lists the claims it conflicts with in
    ``dependencies`` and keeps its own source as evidence. Its record ID is
    unchanged: the claim is the same passage, now known to be disputed.
    """
    peers: dict[str, list[str]] = {}
    for i, a in enumerate(claims):
        for b in claims[i + 1:]:
            if conflict_reason(a, b) is not None:
                peers.setdefault(a.record_id, []).append(b.record_id)
                peers.setdefault(b.record_id, []).append(a.record_id)
    out = []
    for claim in claims:
        if claim.record_id in peers:
            claim = replace(claim, status=ClaimStatus.CONTRADICTED,
                            dependencies=sorted(set(claim.dependencies) | set(
                                peers[claim.record_id])),
                            evidence_ids=list(claim.evidence_ids)
                            or [claim.source_document_id])
        out.append(claim)
    return tuple(out)


# ------------------------------------------------------------------ index ---

@dataclass(frozen=True)
class ClaimHit:
    claim: MechanicClaim
    heading: str
    conflicts_with: tuple[str, ...]


class ClaimIndex:
    """SQLite full-text search over claims, with entity filters.

    Uses FTS5 when the SQLite build has it and a ``LIKE`` scan otherwise;
    ``full_text`` says which. No embedding service is involved.
    """

    def __init__(self, path: str = ":memory:") -> None:
        self.conn = sqlite3.connect(path)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript("""
            CREATE TABLE IF NOT EXISTS claim (
                claim_id TEXT PRIMARY KEY, heading TEXT NOT NULL,
                claim_text TEXT NOT NULL, applies_to_patch TEXT,
                source_document_id TEXT NOT NULL, json TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS claim_subject (
                claim_id TEXT NOT NULL, entity_id TEXT NOT NULL,
                PRIMARY KEY (claim_id, entity_id));
            CREATE TABLE IF NOT EXISTS claim_conflict (
                claim_id TEXT NOT NULL, other_id TEXT NOT NULL,
                reason TEXT NOT NULL, PRIMARY KEY (claim_id, other_id));
        """)
        try:
            self.conn.execute("CREATE VIRTUAL TABLE IF NOT EXISTS claim_fts "
                              "USING fts5(claim_id UNINDEXED, heading, "
                              "claim_text)")
            self.full_text = True
        except sqlite3.OperationalError:
            self.full_text = False

    def close(self) -> None:
        self.conn.close()

    def add(self, claims: Iterable[MechanicClaim]) -> int:
        """Store claims and record conflicts with what is already stored."""
        from ..domain.codec import to_jsonable
        added = 0
        with self.conn:
            for claim in claims:
                heading = _heading_of(claim)
                cursor = self.conn.execute(
                    "INSERT OR IGNORE INTO claim VALUES (?, ?, ?, ?, ?, ?)",
                    (claim.record_id, heading, claim.claim_text,
                     claim.applies_to_patch, claim.source_document_id,
                     json.dumps(to_jsonable(claim), sort_keys=True)))
                if cursor.rowcount == 0:
                    continue
                added += 1
                self.conn.executemany(
                    "INSERT OR IGNORE INTO claim_subject VALUES (?, ?)",
                    [(claim.record_id, s) for s in claim.subject_ids])
                if self.full_text:
                    self.conn.execute(
                        "INSERT INTO claim_fts VALUES (?, ?, ?)",
                        (claim.record_id, heading, claim.claim_text))
                for other in self._same_subjects(claim):
                    reason = conflict_reason(claim, other)
                    if reason is not None:
                        self.conn.executemany(
                            "INSERT OR IGNORE INTO claim_conflict VALUES "
                            "(?, ?, ?)", [(claim.record_id, other.record_id,
                                           reason),
                                          (other.record_id, claim.record_id,
                                           reason)])
        return added

    def _same_subjects(self, claim: MechanicClaim) -> list[MechanicClaim]:
        if not claim.subject_ids:
            return []
        rows = self.conn.execute(
            "SELECT DISTINCT c.json FROM claim c JOIN claim_subject s "
            "ON s.claim_id = c.claim_id WHERE s.entity_id = ? "
            "AND c.claim_id != ?", (claim.subject_ids[0], claim.record_id))
        return [_decode(row["json"]) for row in rows]

    def search(self, text: str | None = None, *,
               subject_id: str | None = None,
               patch: str | None = None, limit: int = 50) -> list[ClaimHit]:
        """Claims matching ``text`` (headings and claim text) and filters."""
        clauses, params = [], []
        if text:
            if self.full_text:
                clauses.append("c.claim_id IN (SELECT claim_id FROM claim_fts "
                               "WHERE claim_fts MATCH ?)")
                params.append(_fts_query(text))
            else:
                clauses.append("(c.claim_text LIKE ? OR c.heading LIKE ?)")
                params.extend(["%" + text + "%"] * 2)
        if subject_id:
            clauses.append("c.claim_id IN (SELECT claim_id FROM claim_subject "
                           "WHERE entity_id = ?)")
            params.append(subject_id)
        if patch:
            clauses.append("c.applies_to_patch = ?")
            params.append(patch)
        where = " WHERE " + " AND ".join(clauses) if clauses else ""
        rows = self.conn.execute(
            "SELECT c.claim_id, c.heading, c.json FROM claim c%s "
            "ORDER BY c.claim_id LIMIT ?" % where, (*params, limit))
        return [ClaimHit(claim=_decode(row["json"]), heading=row["heading"],
                         conflicts_with=self.conflicts(row["claim_id"]))
                for row in rows]

    def conflicts(self, claim_id: str) -> tuple[str, ...]:
        rows = self.conn.execute(
            "SELECT other_id FROM claim_conflict WHERE claim_id = ? "
            "ORDER BY other_id", (claim_id,))
        return tuple(row["other_id"] for row in rows)


def _heading_of(claim: MechanicClaim) -> str:
    match = re.search(r";section=(.*)$", claim.source_locator)
    return match.group(1) if match else ""


def _fts_query(text: str) -> str:
    """Quote every term, so user text is never read as FTS syntax."""
    terms = re.findall(r"\w+", text)
    return " ".join('"%s"' % term for term in terms) or '""'


def _decode(payload: str) -> MechanicClaim:
    from ..domain.codec import from_jsonable
    return from_jsonable(MechanicClaim, json.loads(payload))
