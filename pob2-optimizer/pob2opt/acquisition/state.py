"""Conditional-request validators, cooldowns and resume cursors (P03-T02).

interfaces.md: "Resume cursors and cached unchanged pages avoid repeated
acquisition." None of these is a domain record, so none belongs in the P01
schema set. They live in one small JSON file beside the corpus database,
written atomically.

A cached page is keyed by the identity of the request that produced it, not by
its display form. The two have to be separate: redaction replaces every query
value it cannot vouch for, so ``?variant=first`` and ``?variant=second`` share
a redacted spelling, and keying on that spelling sends one resource's ETag on
the other's request. A 304 then answers with the wrong build.

The key is therefore an HMAC over the real request identity under a salt
generated for this corpus. It is not reversible, so no credential is stored,
and it does not collide, so no two resources share a validator. The redacted
URL is still written beside it for a reader.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
from pathlib import Path
from typing import Any, Mapping
from urllib.parse import urlsplit

from .http import Validators
from .hosts import DEFAULT_PORTS, remove_dot_segments
from .redaction import redact_url

FILENAME = "acquisition-state.json"


class AcquisitionState:
    def __init__(self, path: Path | str | None) -> None:
        self.path = Path(path) if path is not None else None
        self._data: dict[str, Any] = {"pages": {}, "cursors": {},
                                      "cooldowns": {}, "salt": ""}
        self._load()

    @classmethod
    def in_corpus(cls, root: Path | str) -> "AcquisitionState":
        return cls(Path(root) / FILENAME)

    @classmethod
    def in_memory(cls) -> "AcquisitionState":
        return cls(None)

    # -- cached pages ------------------------------------------------------

    def key_for(self, provider: str, url: str, *,
                credential_partition: str | None = None) -> str:
        """The cache key for one request. See the module docstring."""
        return request_key(provider, url, salt=self._salt(),
                           credential_partition=credential_partition)

    def validators(self, provider: str, url: str, *,
                   credential_partition: str | None = None) -> Validators:
        entry = self._entry(provider, url, credential_partition)
        if not entry or not entry.get("final_key"):
            return Validators()
        return Validators(etag=entry.get("etag"),
                          last_modified=entry.get("last_modified"))

    def document_for(self, provider: str, url: str, *,
                     credential_partition: str | None = None) -> str | None:
        """The SourceDocument a previous fetch of this request produced."""
        entry = self._entry(provider, url, credential_partition)
        return entry.get("source_document_id") if entry else None

    def final_url_for(self, provider: str, url: str, *,
                      credential_partition: str | None = None) -> str | None:
        """Display location only; final_key_for binds conditional requests."""
        entry = self._entry(provider, url, credential_partition)
        return entry.get("final_url") if entry else None

    def final_key_for(self, provider: str, url: str, *,
                      credential_partition: str | None = None) -> str | None:
        """Opaque identity of the final resource, never its redacted spelling."""
        entry = self._entry(provider, url, credential_partition)
        return entry.get("final_key") if entry else None

    def remember(self, provider: str, url: str, *, etag: str | None,
                 last_modified: str | None, source_document_id: str | None,
                 acquired_at: str, final_url: str | None = None,
                 final_key: str | None = None,
                 credential_partition: str | None = None) -> None:
        self._data["pages"][self.key_for(
            provider, url, credential_partition=credential_partition)] = {
            "etag": etag,
            "last_modified": last_modified,
            "source_document_id": source_document_id,
            "acquired_at": acquired_at,
            "final_url": redact_url(final_url or url),
            "final_key": final_key or self.key_for(
                provider, final_url or url,
                credential_partition=credential_partition),
            "provider": provider,
            # For a reader only. Never the key: see the module docstring.
            "url": redact_url(url),
        }
        self.save()

    def _entry(self, provider: str, url: str,
               credential_partition: str | None) -> dict[str, Any] | None:
        return self._data["pages"].get(
            self.key_for(provider, url,
                         credential_partition=credential_partition))

    # -- provider cooldowns ------------------------------------------------

    def cooldowns(self) -> dict[str, str]:
        return dict(self._data.get("cooldowns") or {})

    def set_cooldowns(self, deadlines: Mapping[str, str]) -> None:
        """Replace the pending retry deadlines, so a resumed run honours them."""
        current = dict(self._data.get("cooldowns") or {})
        if dict(deadlines) == current:
            return
        self._data["cooldowns"] = dict(deadlines)
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

    def _salt(self) -> str:
        salt = self._data.get("salt")
        if not salt:
            salt = secrets.token_hex(16)
            self._data["salt"] = salt
        return salt

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
            self._data["cooldowns"] = dict(loaded.get("cooldowns") or {})
            self._data["salt"] = str(loaded.get("salt") or "")

    def save(self) -> None:
        if self.path is None:
            return
        self._salt()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temp = self.path.with_name(self.path.name + ".partial")
        text = json.dumps(self._data, indent=2, sort_keys=True)
        with open(temp, "w", encoding="utf-8") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp, self.path)


def request_key(provider: str, url: str, *, salt: str,
                credential_partition: str | None = None) -> str:
    """A stable, non-reversible identity for one request.

    Built from the provider, the origin, the path and the exact query,
    values and order included: these distinguish two representations,
    and dropping the ones redaction cannot vouch for is what made two
    different resources share a cache entry. ``credential_partition`` names
    the authorization context, so one caller's authenticated copy is never
    served to another.
    """
    parts = urlsplit(url.strip())
    try:
        port = parts.port
    except ValueError:
        port = None
    scheme = (parts.scheme or "").lower()
    # Structured fields cannot collide through delimiters. Keep the complete
    # query spelling/order: duplicate keys can be order-sensitive, and even
    # decoding query values would assume semantics the provider never promised.
    identity = json.dumps({
        "version": 2,
        "provider": provider,
        "scheme": scheme,
        "host": (parts.hostname or "").lower().rstrip("."),
        "port": port if port is not None else DEFAULT_PORTS.get(scheme),
        "path": remove_dot_segments(parts.path or "/"),
        "partition": credential_partition,
        "query": parts.query,
    }, sort_keys=True, separators=(",", ":"))
    return hmac.new(salt.encode("utf-8"), identity.encode("utf-8"),
                    hashlib.sha256).hexdigest()
