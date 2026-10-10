"""Source capability manifests (P03-T01).

This package reads the recorded per-provider capability manifests. It does not
acquire anything and it never contacts a provider. Acquisition is P03-T02.
"""

from .manifests import (CATEGORIES, MANIFEST_DIR_ENV, ManifestError,
                        ManifestNotFound, SUPPORT_FLAGS, default_manifest_dir,
                        known_providers, load_manifest, resolve_provider,
                        summarize, validate_manifest)

__all__ = [
    "CATEGORIES",
    "MANIFEST_DIR_ENV",
    "ManifestError",
    "ManifestNotFound",
    "SUPPORT_FLAGS",
    "default_manifest_dir",
    "known_providers",
    "load_manifest",
    "resolve_provider",
    "summarize",
    "validate_manifest",
]
