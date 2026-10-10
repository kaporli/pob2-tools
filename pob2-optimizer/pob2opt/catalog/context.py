"""Identity of an evaluation context (P02-T02).

``architecture.md`` puts the patch profile hash, the catalog hash, the PoB
commit, the dirty-tree hash and the adapter version in the evaluation cache
key. ``cache.py`` consumes a patch profile hash; this is where it comes from.

The projection holds what changes an answer and nothing else. Changing the
upstream commit changes the identity, so results produced by a different
engine cannot be reused. When the profile was resolved, and what it is
called, do not.
"""

from __future__ import annotations

from typing import Any

from ..domain.identity import content_hash
from ..domain.records import PatchProfile

#: Fields that identify a context. Everything else on a PatchProfile is
#: metadata about the export, not about what it will compute.
CONTEXT_FIELDS = (
    "game", "realm", "league_id", "patch_id", "catalog_hash", "pob_commit",
    "pob_dirty_hash", "adapter_version",
)


def context_identity(profile: PatchProfile) -> dict[str, Any]:
    """The projection hashed into an evaluation context identity.

    ``compatibility`` is included: a catalog accepted as verified and the
    same catalog accepted as partial are different claims, and a result
    cached under one must not be served for the other. ``resolved_at``,
    ``record_id``, the evidence lists and ``character_rules`` are excluded;
    the rules follow the catalog and the commit, which are both here.
    """
    identity = {name: getattr(profile, name) for name in CONTEXT_FIELDS}
    identity["compatibility"] = profile.compatibility.value
    return identity


def evaluation_context_hash(profile: PatchProfile) -> str:
    return content_hash(context_identity(profile))
