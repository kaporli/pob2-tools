"""Which PoB checkout is actually running (P02-T01).

Only what the adapter needs to refuse a mismatched engine: the commit and
whether the tree is modified. The full patch profile, its release evidence and
the compatibility fixture set are P02-T02.

A modified tree is reported as a hash of the ``git status`` listing, not of the
modified file contents. It detects that the checkout is not the pinned commit;
it does not identify what changed. P02-T02 owns content-level hashing.
"""

from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

GIT_TIMEOUT_S = 60.0


@dataclass(frozen=True, slots=True)
class CheckoutIdentity:
    root: str
    commit: str | None
    dirty_hash: str | None
    #: Why commit or dirty_hash is None, when they are.
    reason: str | None = None

    @property
    def is_pinned(self) -> bool:
        return bool(self.commit) and self.dirty_hash is None


def resolve_checkout(root: str | os.PathLike[str]) -> CheckoutIdentity:
    """Resolve the checkout at ``root``. Unknown stays unknown.

    Deliberately not cached across calls. A process-wide cache kept reporting
    a clean tree after the checkout was edited mid-run, so every snapshot
    taken afterwards carried an identity that was no longer true
    (P02-T01-R05). ``EngineAdapter`` resolves once and keeps the result on the
    instance, which is the right scope; one ``git`` call per adapter is not
    worth that hazard.
    """
    return _resolve(str(Path(root).resolve()))


def _resolve(root: str) -> CheckoutIdentity:
    if not Path(root).is_dir():
        return CheckoutIdentity(root, None, None, "checkout directory not found")
    git = shutil.which("git")
    if git is None:
        return CheckoutIdentity(root, None, None, "git is not on PATH")

    commit = _git(git, root, "rev-parse", "HEAD")
    commit = commit.strip() if commit else None
    if not commit:
        return CheckoutIdentity(root, None, None, "not a git checkout")

    status = _git(git, root, "status", "--porcelain=v1", "--untracked-files=all")
    if status is None:
        return CheckoutIdentity(root, commit, None, "working-tree status unavailable")
    if not status.strip():
        return CheckoutIdentity(root, commit, None, None)
    listing = "\n".join(sorted(line.strip() for line in status.splitlines()
                               if line.strip()))
    return CheckoutIdentity(root, commit,
                            hashlib.sha256(listing.encode("utf-8")).hexdigest(),
                            "working tree differs from the pinned commit")


def _git(git: str, root: str, *args: str) -> str | None:
    try:
        completed = subprocess.run(
            [git, "-C", root, *args], capture_output=True, text=True,
            timeout=GIT_TIMEOUT_S, check=False)
    except (OSError, subprocess.SubprocessError):
        return None
    if completed.returncode != 0:
        return None
    return completed.stdout
