"""Official release evidence, read from disk (P02-T02).

The current game patch is a fact about the game, not about Path of Building,
so it cannot be read out of the engine. It is captured out of band into a
small JSON file and read here. The export never reaches the network: an
export that could silently fetch a patch id would also silently fetch it
wrong, and `tests/unit` must run with no sockets at all.

Three things this module refuses to do:

* invent a patch id. No capture means ``patch_id`` is unknown, the profile is
  ``unknown``, and a ``DataGap`` says what is missing;
* treat a summary as a verbatim capture. ``fidelity`` travels with the
  evidence and a summary can never support ``verified`` compatibility. A
  ``verbatim`` capture must carry the fetched bytes, their hash must match,
  and every excerpt line must occur in them;
* treat a version label as compatibility. Resolving the patch says which
  patch is live, nothing about whether the engine models it.
"""

from __future__ import annotations

import hashlib
import html
import json
from datetime import datetime
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..domain.enums import AccessMethod, Redistribution
from ..domain.identity import document_hash
from ..domain.records import SCHEMA_VERSION, SourceDocument

#: Format version of the capture file itself. Version 2 adds ``raw_file``,
#: ``raw_sha256`` and ``raw_media_type``: the fetched page, stored beside the
#: capture. Version 1 files are still read.
CAPTURE_VERSION = 2
CAPTURE_VERSIONS = (1, 2)

#: ``verbatim`` is a byte capture of the official page. ``summary`` is a
#: machine or human reading of it: enough to name the patch, not enough to
#: certify anything.
FIDELITIES = ("verbatim", "summary")


class ReleaseCaptureError(ValueError):
    """The capture file cannot be read as release evidence."""


@dataclass(frozen=True, slots=True)
class ReleaseCapture:
    """One captured official release page."""

    path: str
    provider: str
    source_url: str
    captured_at: str
    fidelity: str
    game: str
    realm: str | None
    patch_id: str
    patch_published_at: str | None
    title: str
    author: str | None
    excerpt: str
    redistribution: str
    capture_method: str
    notes: str
    raw: bytes | None = None
    raw_media_type: str | None = None

    @property
    def is_verbatim(self) -> bool:
        return self.fidelity == "verbatim"

    def payload(self) -> bytes:
        """The stored bytes this capture is evidence of.

        For a verbatim capture, the fetched page itself. Otherwise the excerpt
        plus its attribution, which is what was actually read. Either way it
        is kept in the export bundle rather than republished.
        """
        if self.raw is not None:
            return self.raw
        header = ("source: %s\ntitle: %s\nauthor: %s\npublished: %s\n"
                  "captured: %s (%s, %s)\n\n"
                  % (self.source_url, self.title, self.author or "unknown",
                     self.patch_published_at or "unknown", self.captured_at,
                     self.capture_method, self.fidelity))
        return (header + self.excerpt).encode("utf-8")


_REQUIRED = ("provider", "source_url", "captured_at", "fidelity", "game",
             "patch_id", "title", "excerpt", "capture_method")


def load_release_capture(path: str | Path) -> ReleaseCapture:
    """Read one capture file. A malformed capture is an error, not a guess."""
    path = Path(path)
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ReleaseCaptureError(
            "release capture %s could not be read: %s" % (path.name, exc)) from None
    if not isinstance(raw, dict):
        raise ReleaseCaptureError(
            "release capture %s is not a JSON object" % path.name)
    version = raw.get("capture_version")
    if version not in CAPTURE_VERSIONS:
        raise ReleaseCaptureError(
            "release capture %s declares capture_version %r; this build reads %s"
            % (path.name, version, ", ".join(map(str, CAPTURE_VERSIONS))))
    missing = [key for key in _REQUIRED if not raw.get(key)]
    if missing:
        raise ReleaseCaptureError(
            "release capture %s is missing %s" % (path.name, ", ".join(missing)))
    fidelity = raw["fidelity"]
    if fidelity not in FIDELITIES:
        raise ReleaseCaptureError(
            "release capture %s declares fidelity %r; known values are %s"
            % (path.name, fidelity, ", ".join(FIDELITIES)))
    page = _raw_page(path, raw, version)
    if fidelity == "verbatim" and page is None:
        raise ReleaseCaptureError(
            "release capture %s claims verbatim fidelity without the fetched "
            "bytes; capture_version 2 needs raw_file and raw_sha256" % path.name)
    if page is not None:
        _check_excerpt(path, raw["excerpt"], page)
    return ReleaseCapture(
        path=str(path),
        provider=raw["provider"],
        source_url=raw["source_url"],
        captured_at=raw["captured_at"],
        fidelity=fidelity,
        game=raw["game"],
        realm=raw.get("realm"),
        patch_id=raw["patch_id"],
        patch_published_at=raw.get("patch_published_at"),
        title=raw["title"],
        author=raw.get("author"),
        excerpt=raw["excerpt"],
        redistribution=raw.get("redistribution", Redistribution.UNKNOWN.value),
        capture_method=raw["capture_method"],
        notes=raw.get("notes", ""),
        raw=page,
        raw_media_type=raw.get("raw_media_type") if page is not None else None)


def _raw_page(path: Path, raw: dict, version: int) -> bytes | None:
    """The fetched bytes named by ``raw_file``, checked against ``raw_sha256``."""
    name, digest = raw.get("raw_file"), raw.get("raw_sha256")
    if name is None and digest is None:
        return None
    if version < 2:
        raise ReleaseCaptureError(
            "release capture %s names raw bytes, which capture_version 1 "
            "cannot carry" % path.name)
    if not name or not digest:
        raise ReleaseCaptureError(
            "release capture %s needs both raw_file and raw_sha256" % path.name)
    page_path = path.parent / name
    try:
        page = page_path.read_bytes()
    except OSError as exc:
        raise ReleaseCaptureError(
            "release capture %s: raw_file could not be read: %s"
            % (path.name, exc)) from None
    observed = hashlib.sha256(page).hexdigest()
    if observed != digest:
        raise ReleaseCaptureError(
            "release capture %s: raw_file %s hashes to %s, recorded %s"
            % (path.name, name, observed, digest))
    return page


def _check_excerpt(path: Path, excerpt: str, page: bytes) -> None:
    """Every excerpt line must occur in the page's unescaped text."""
    text = html.unescape(page.decode("utf-8", errors="replace"))
    missing = [line for line in excerpt.splitlines()
               if line.strip() and line.strip() not in text]
    if missing:
        raise ReleaseCaptureError(
            "release capture %s: excerpt line(s) not in raw_file: %s"
            % (path.name, "; ".join(missing)))


def load_release_captures(directory: str | Path) -> list[ReleaseCapture]:
    """Read evidence deterministically; acquisition order does not imply release order."""
    directory = Path(directory)
    if not directory.is_dir():
        return []
    captures = [load_release_capture(path)
                for path in sorted(directory.glob("*.json"))]
    return captures


def current_release(captures: list[ReleaseCapture], game: str,
                    realm: str) -> tuple[ReleaseCapture | None, str | None]:
    """Resolve applicable publication chronology, or explain its uncertainty."""
    applicable = [c for c in captures if c.game == game and c.realm in (None, realm)]
    if not applicable:
        return None, "No applicable official release evidence was supplied."
    dated = []
    for capture in applicable:
        try:
            published = datetime.fromisoformat(capture.patch_published_at.replace("Z", "+00:00"))
            if published.utcoffset() is None:
                raise ValueError("publication date must include a timezone")
        except (AttributeError, ValueError):
            return None, "Release evidence has missing or invalid publication chronology."
        dated.append((published, capture))
    by_patch = {}
    for published, capture in dated:
        previous = by_patch.setdefault(capture.patch_id, published)
        if previous != published:
            return None, "Captures disagree on the publication date of the same patch."
    latest_date = max(date for date, _ in dated)
    latest = [c for date, c in dated if date == latest_date]
    if len({c.patch_id for c in latest}) != 1:
        return None, "Different patches have the same latest publication timestamp."
    # Acquisition time breaks ties only between captures of the SAME release.
    return max(latest, key=lambda c: (c.is_verbatim, c.captured_at, c.source_url)), None


def release_evidence_document(capture: ReleaseCapture, *, record_id: str,
                              created_at: str,
                              acquisition_version: str) -> tuple[SourceDocument, bytes]:
    """A ``SourceDocument`` for one capture, plus the bytes it addresses.

    ``declared_patch`` carries the patch the page names. contracts.md is
    explicit that a declared patch is not verified compatibility, which is
    why deciding that is ``compatibility.py``'s job and not this one's.
    """
    payload = capture.payload()
    return SourceDocument(
        schema_version=SCHEMA_VERSION,
        record_id=record_id,
        created_at=created_at,
        provenance_ids=[],
        provider=capture.provider,
        source_url=capture.source_url,
        external_id=None,
        acquired_at=capture.captured_at,
        published_at=capture.patch_published_at,
        updated_at=None,
        access_method=AccessMethod.MANUAL_CAPTURE,
        media_type=capture.raw_media_type or "text/plain; charset=utf-8",
        blob_hash=document_hash(payload),
        byte_count=len(payload),
        acquisition_version=acquisition_version,
        source_manifest_id="pob2opt.catalog.release/%d" % CAPTURE_VERSION,
        declared_patch=capture.patch_id,
        author_id=capture.author,
        locale=None,
        popularity=[],
        redistribution=_redistribution(capture.redistribution),
    ), payload


def _redistribution(value: Any) -> Redistribution:
    try:
        return Redistribution(value)
    except ValueError:
        return Redistribution.UNKNOWN
