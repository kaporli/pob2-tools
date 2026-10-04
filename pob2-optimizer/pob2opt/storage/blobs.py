"""Content-addressed immutable payload storage (P01-T03).

Original bytes are stored once, named by their SHA-256, and never rewritten.
Re-ingesting the same bytes reuses the file: identical content is one blob,
however many documents reference it.

Reads verify. A file whose content no longer hashes to its name raises
:class:`BlobCorrupt` instead of returning the wrong bytes, because a silently
wrong payload would be indistinguishable from a real source.

Writes are atomic: a temporary file in the same directory is written, flushed,
fsynced and then ``os.replace``d into place. A crash mid-write leaves the
temporary file, never a short blob under a correct-looking name.
"""

from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

from .errors import BlobCorrupt, BlobNotFound

#: Blobs are sharded by the first two hex characters, so one directory does
#: not accumulate hundreds of thousands of entries.
SHARD_WIDTH = 2
TEMP_SUFFIX = ".partial"


@dataclass(frozen=True, slots=True)
class BlobWrite:
    blob_hash: str
    byte_count: int
    path: Path
    #: True when the bytes were already stored and nothing was written.
    reused: bool


class BlobStore:
    def __init__(self, root: Path | str) -> None:
        self.root = Path(root)

    def __repr__(self) -> str:  # pragma: no cover - diagnostics
        return "BlobStore(%r)" % str(self.root)

    def path_for(self, blob_hash: str) -> Path:
        _check_hash(blob_hash)
        return self.root / blob_hash[:SHARD_WIDTH] / blob_hash

    def exists(self, blob_hash: str) -> bool:
        return self.path_for(blob_hash).is_file()

    def put(self, payload: bytes) -> BlobWrite:
        if not isinstance(payload, (bytes, bytearray, memoryview)):
            raise TypeError("blobs hold raw bytes, not %s"
                            % type(payload).__name__)
        payload = bytes(payload)
        blob_hash = hashlib.sha256(payload).hexdigest()
        target = self.path_for(blob_hash)
        if target.is_file():
            return BlobWrite(blob_hash, len(payload), target, reused=True)

        target.parent.mkdir(parents=True, exist_ok=True)
        temp = target.with_name(target.name + TEMP_SUFFIX)
        with open(temp, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp, target)
        return BlobWrite(blob_hash, len(payload), target, reused=False)

    def get(self, blob_hash: str) -> bytes:
        path = self.path_for(blob_hash)
        try:
            payload = path.read_bytes()
        except FileNotFoundError:
            raise BlobNotFound(blob_hash, str(self.root)) from None
        actual = hashlib.sha256(payload).hexdigest()
        if actual != blob_hash:
            raise BlobCorrupt(blob_hash, actual, str(path))
        return payload

    def copy_to(self, other: "BlobStore", blob_hash: str) -> BlobWrite:
        """Copy one verified blob into another store (used by run bundles)."""
        return other.put(self.get(blob_hash))

    def iter_hashes(self) -> Iterator[str]:
        if not self.root.is_dir():
            return
        for shard in sorted(self.root.iterdir()):
            if not shard.is_dir():
                continue
            for path in sorted(shard.iterdir()):
                if path.name.endswith(TEMP_SUFFIX) or not path.is_file():
                    continue
                yield path.name

    def iter_incomplete(self) -> Iterator[Path]:
        """Temporary files left by an interrupted write."""
        if not self.root.is_dir():
            return
        for shard in sorted(self.root.iterdir()):
            if shard.is_dir():
                yield from sorted(shard.glob("*" + TEMP_SUFFIX))


def _check_hash(blob_hash: str) -> None:
    if (not isinstance(blob_hash, str) or len(blob_hash) != 64
            or any(c not in "0123456789abcdef" for c in blob_hash)):
        raise ValueError("%r is not a lower-case SHA-256 hex digest"
                         % (blob_hash,))
