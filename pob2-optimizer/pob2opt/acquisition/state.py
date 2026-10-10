"""Conditional-request validators and resume cursors (P03-T02).

interfaces.md: "Resume cursors and cached unchanged pages avoid repeated
acquisition." Neither is a domain record, so neither belongs in the P01 schema
set. They live in one small JSON file beside the corpus database, written
atomically.

Keys are the provider plus the **redacted** URL, so a token in a query string
cannot reach this file either. Values hold only what a conditional request
needs: an ETag, a Last-Modified date and the document the last fetch produced.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from .http import Validators
from .redaction import redact_url

FILENAME = "acquisition-state.json"


class AcquisitionState:
    def __init__(self, path: Path | str | None) -> None:
        self.path = Path(path) if path is not None else None
        self._data: dict[str, Any] = {"pages": {}, "cursors": {}}
        self._load()

    @classmethod
    def in_corpus(cls, root: Path | str) -> "AcquisitionState":
        return cls(Path(root) / FILENAME)

    @classmethod
    def in_memory(cls) -> "AcquisitionState":
        return cls(None)

    # -- cached pages ------------------------------------------------------

    def validators(self, provider: str, url: str) -> Validators:
        entry = self._data["pages"].get(_key(provider, url))
        if not entry:
            return Validators()
        return Validators(etag=entry.get("etag"),
                          last_modified=entry.get("last_modified"))

    def document_for(self, provider: str, url: str) -> str | None:
        """The SourceDocument a previous fetch of this URL produced."""
        entry = self._data["pages"].get(_key(provider, url))
        return entry.get("source_document_id") if entry else None

    def remember(self, provider: str, url: str, *, etag: str | None,
                 last_modified: str | None, source_document_id: str | None,
                 acquired_at: str) -> None:
        self._data["pages"][_key(provider, url)] = {
            "etag": etag,
            "last_modified": last_modified,
            "source_document_id": source_document_id,
            "acquired_at": acquired_at,
        }
        self.save()

    # -- resume cursors ----------------------------------------------------

    def cursor(self, provider: str, name: str) -> str | None:
        return self._data["cursors"].get("%s|%s" % (provider, name))

    def set_cursor(self, provider: str, name: str, value: str | None) -> None:
        key = "%s|%s" % (provider, name)
        if value is None:
            self._data["cursors"].pop(key, None)
        else:
            self._data["cursors"][key] = value
        self.save()

    # -- persistence -------------------------------------------------------

    def _load(self) -> None:
        if self.path is None or not self.path.is_file():
            return
        try:
            loaded = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            # A damaged state file costs a re-acquisition. It never costs a
            # wrong answer, so it is discarded rather than raised.
            return
        if isinstance(loaded, dict):
            self._data["pages"] = dict(loaded.get("pages") or {})
            self._data["cursors"] = dict(loaded.get("cursors") or {})

    def save(self) -> None:
        if self.path is None:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temp = self.path.with_name(self.path.name + ".partial")
        text = json.dumps(self._data, indent=2, sort_keys=True)
        with open(temp, "w", encoding="utf-8") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp, self.path)


def _key(provider: str, url: str) -> str:
    return "%s|%s" % (provider, redact_url(url))
