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
  evidence and a summary can never support ``verified`` compatibility;
* treat a version label as compatibility. Resolving the patch says which
  patch is live, nothing about whether the engine models it.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..domain.enums import AccessMethod, Redistribution
from ..domain.identity import document_hash
from ..domain.records import SCHEMA_VERSION, SourceDocument

#: Format version of the capture file itself.
CAPTURE_VERSION = 1

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

    @property
    def is_verbatim(self) -> bool:
        return self.fidelity == "verbatim"

    def payload(self) -> bytes:
        """The stored bytes this capture is evidence of.

        The excerpt plus its attribution, which is what was actually read.
        Short, attributed and kept in the export bundle rather than
        republished.
        """
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
    if version != CAPTURE_VERSION:
        raise ReleaseCaptureError(
            "release capture %s declares capture_version %r; this build reads %d"
            % (path.name, version, CAPTURE_VERSION))
    missing = [key for key in _REQUIRED if not raw.get(key)]
    if missing:
        raise ReleaseCaptureError(
            "release capture %s is missing %s" % (path.name, ", ".join(missing)))
    fidelity = raw["fidelity"]
    if fidelity not in FIDELITIES:
        raise ReleaseCaptureError(
            "release capture %s declares fidelity %r; known values are %s"
            % (path.name, fidelity, ", ".join(FIDELITIES)))
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
        notes=raw.get("notes", ""))


def load_release_captures(directory: str | Path) -> list[ReleaseCapture]:
    """Every ``*.json`` capture in a directory, newest patch publication last.

    Ordering is by the captured timestamp, which is a fact about the capture;
    patch ids are not assumed to sort.
    """
    directory = Path(directory)
    if not directory.is_dir():
        return []
    captures = [load_release_capture(path)
                for path in sorted(directory.glob("*.json"))]
    return sorted(captures, key=lambda capture: capture.captured_at)


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
        media_type="text/plain; charset=utf-8",
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
