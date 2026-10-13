"""Read and check the recorded source capability manifests (P03-T01).

The manifests live in ``docs/evidence/P03`` as ``<slug>-capabilities.json``.
They are evidence files written by hand from a bounded inspection, so the
checks here are structural: every required section present, every enum value
inside the contract, every evidence reference resolving, every one of the five
representative categories answered.

Nothing in this module opens a socket. A manifest records what a provider was
observed to permit; it is not a client.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from ..domain.enums import AccessMethod, AcquisitionStatus, Redistribution

#: Point the loader somewhere else, which is how the tests read fixtures.
MANIFEST_DIR_ENV = "POB2_SOURCE_MANIFESTS"

#: The five representative record categories P03-T01 requires. A manifest must
#: answer all five. "Not inspected, and here is why" is an answer; silently
#: dropping a category or substituting another record is not.
CATEGORIES = (
    "current_endgame",
    "multiple_variants",
    "old_patch",
    "sparse_incomplete",
    "unusual_build",
)

#: Listing metadata, full build data and explanatory prose are separate claims
#: and carry separate flags. A provider that exposes titles but not trees says
#: so here instead of reporting one blended "supported".
SUPPORT_FLAGS = ("listing_metadata", "full_build_data", "explanatory_prose")

#: Top-level sections every manifest carries.
REQUIRED_KEYS = (
    "schema_version",
    "record_kind",
    "manifest_id",
    "task",
    "specification_version",
    "provider",
    "provider_slug",
    "inspected_at",
    "evidence_class",
    "inspection",
    "bounds",
    "robots",
    "terms",
    "access",
    "support",
    "fields_visible",
    "structured_export_formats",
    "pagination",
    "authentication",
    "limits",
    "blocked_cases",
    "representative_records",
    "redistribution",
    "local_handling",
    "recommended_adapter_path",
    "evidence",
)

#: Aliases a caller may type for --provider.
_ALIASES = {
    "mobalytics": "mobalytics",
    "maxroll": "maxroll",
    "poe-ninja": "poe-ninja",
    "poe.ninja": "poe-ninja",
    "poeninja": "poe-ninja",
    "poe_ninja": "poe-ninja",
    "ninja": "poe-ninja",
}


class ManifestError(ValueError):
    """A manifest is present but does not satisfy the P03-T01 structure."""


class ManifestNotFound(LookupError):
    """No manifest file exists for the requested provider."""


def default_manifest_dir() -> Path:
    """``docs/evidence/P03`` in this checkout, or the env override."""
    override = os.environ.get(MANIFEST_DIR_ENV)
    if override:
        return Path(override)
    return Path(__file__).resolve().parents[3] / "docs" / "evidence" / "P03"


def resolve_provider(name: str) -> str:
    """Map a provider name a caller typed onto a manifest slug."""
    slug = _ALIASES.get(str(name).strip().lower())
    if slug is None:
        raise ManifestNotFound(
            "unknown provider %r; known providers are %s"
            % (name, ", ".join(sorted(set(_ALIASES.values())))))
    return slug


def known_providers() -> list[str]:
    return sorted(set(_ALIASES.values()))


def manifest_path(slug: str, directory: Path | None = None) -> Path:
    base = default_manifest_dir() if directory is None else Path(directory)
    return base / ("%s-capabilities.json" % slug)


def load_manifest(name: str, directory: Path | None = None) -> dict[str, Any]:
    """Read one provider's manifest and validate it. No network access."""
    slug = resolve_provider(name)
    path = manifest_path(slug, directory)
    if not path.is_file():
        raise ManifestNotFound("no capability manifest at %s" % path)
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ManifestError("%s is unreadable: %s" % (path, exc)) from exc
    problems = validate_manifest(manifest, slug)
    if problems:
        raise ManifestError("%s: %s" % (path, "; ".join(problems)))
    return manifest


def validate_manifest(manifest: Any, slug: str | None = None) -> list[str]:
    """Return every structural problem found. An empty list means usable."""
    problems: list[str] = []
    if not isinstance(manifest, dict):
        return ["manifest is not an object"]

    for key in REQUIRED_KEYS:
        if key not in manifest:
            problems.append("missing %s" % key)
    if problems:
        return problems

    if manifest["record_kind"] != "source_capability_manifest":
        problems.append("record_kind is %r" % manifest["record_kind"])
    if slug is not None and manifest["provider_slug"] != slug:
        problems.append("provider_slug %r does not match file %r"
                        % (manifest["provider_slug"], slug))

    evidence_ids = _evidence_ids(manifest, problems)
    _check_access(manifest, problems)
    _check_support(manifest, problems)
    _check_categories(manifest, problems)
    _check_limits(manifest, problems)

    if manifest["redistribution"] not in set(Redistribution):
        problems.append("redistribution %r is not in the contract"
                        % manifest["redistribution"])

    for path, value in _referenced_evidence(manifest):
        if value not in evidence_ids:
            problems.append("%s references unknown evidence %r" % (path, value))

    return problems


def summarize(manifest: dict[str, Any]) -> dict[str, Any]:
    """The short answer a reviewer reads before opening the manifest."""
    access = manifest["access"]
    support = manifest["support"]
    records = manifest["representative_records"]
    inspected = [r["category"] for r in records if r.get("inspected")]
    return {
        "provider": manifest["provider"],
        "provider_slug": manifest["provider_slug"],
        "manifest_id": manifest["manifest_id"],
        "inspected_at": manifest["inspected_at"],
        "permitted_access_method": access["permitted_access_method"],
        "acquisition_status": access["acquisition_status"],
        "support": {flag: bool(support[flag]["supported"]) for flag in SUPPORT_FLAGS},
        "support_confirmed": {flag: bool(support[flag].get("confirmed"))
                              for flag in SUPPORT_FLAGS},
        "categories_inspected": inspected,
        "categories_not_inspected": [r["category"] for r in records
                                     if not r.get("inspected")],
        "blocked_case_count": len(manifest["blocked_cases"]),
        "has_reproducible_example": "reproducible_acquisition_example" in manifest,
        "redistribution": manifest["redistribution"],
        "local_handling": manifest["local_handling"],
        "recommended_access_methods": manifest["recommended_adapter_path"]["access_methods"],
        "blocks": manifest["recommended_adapter_path"]["blocks"],
    }


# ------------------------------------------------------------------ checks ---

def _evidence_ids(manifest: dict[str, Any], problems: list[str]) -> set[str]:
    ids: set[str] = set()
    evidence = manifest["evidence"]
    if not isinstance(evidence, list) or not evidence:
        problems.append("evidence is empty")
        return ids
    for entry in evidence:
        for field in ("id", "method", "observed_at", "observation"):
            if field not in entry:
                problems.append("evidence entry missing %s" % field)
        entry_id = entry.get("id")
        if entry_id in ids:
            problems.append("duplicate evidence id %r" % entry_id)
        ids.add(entry_id)
    return ids


def _check_access(manifest: dict[str, Any], problems: list[str]) -> None:
    access = manifest["access"]
    method = access.get("permitted_access_method")
    if method is not None and method not in set(AccessMethod):
        problems.append("permitted_access_method %r is not in the contract" % method)
    status = access.get("acquisition_status")
    if status not in set(AcquisitionStatus):
        problems.append("acquisition_status %r is not in the contract" % status)
    if not access.get("rationale"):
        problems.append("access.rationale is empty")

    # Acceptance: a provider is either reproducible or specifically blocked.
    example = manifest.get("reproducible_acquisition_example")
    blocked = manifest["blocked_cases"]
    if example is None and not blocked:
        problems.append("neither a reproducible example nor a blocked case")


def _check_support(manifest: dict[str, Any], problems: list[str]) -> None:
    support = manifest["support"]
    for flag in SUPPORT_FLAGS:
        entry = support.get(flag)
        if not isinstance(entry, dict):
            problems.append("support.%s is missing" % flag)
            continue
        if not isinstance(entry.get("supported"), bool):
            problems.append("support.%s.supported is not a boolean" % flag)
        if not isinstance(entry.get("confirmed"), bool):
            problems.append("support.%s.confirmed is not a boolean" % flag)
        if entry.get("supported") and not entry.get("confirmed"):
            problems.append("support.%s claims supported without confirmation" % flag)
        method = entry.get("access_method")
        if method is not None and method not in set(AccessMethod):
            problems.append("support.%s.access_method %r is not in the contract"
                            % (flag, method))
        if not entry.get("note"):
            problems.append("support.%s has no note" % flag)
        if not entry.get("evidence_ids"):
            problems.append("support.%s cites no evidence" % flag)


def _check_categories(manifest: dict[str, Any], problems: list[str]) -> None:
    records = manifest["representative_records"]
    if not isinstance(records, list):
        problems.append("representative_records is not a list")
        return
    seen = [r.get("category") for r in records]
    for category in CATEGORIES:
        if category not in seen:
            problems.append("representative_records omits %s" % category)
    for extra in seen:
        if extra not in CATEGORIES:
            problems.append("representative_records has unknown category %r" % extra)
    for record in records:
        if not isinstance(record.get("inspected"), bool):
            problems.append("%s has no inspected flag" % record.get("category"))
            continue
        if not record.get("inspected") and not record.get("reason"):
            problems.append("%s was not inspected and gives no reason"
                            % record.get("category"))
        status = record.get("status")
        if status not in set(AcquisitionStatus) and status != "not_applicable":
            problems.append("%s has status %r" % (record.get("category"), status))


def _check_limits(manifest: dict[str, Any], problems: list[str]) -> None:
    applied = manifest["limits"].get("applied_defaults")
    if not isinstance(applied, dict):
        problems.append("limits.applied_defaults is missing")
        return
    expected = {"connect_timeout_s": 10, "read_timeout_s": 30,
                "max_response_bytes": 20 * 1024 * 1024, "max_attempts": 3}
    for key, want in expected.items():
        got = applied.get(key)
        if got is None:
            problems.append("limits.applied_defaults missing %s" % key)
        elif got > want:
            problems.append("limits.applied_defaults.%s is %r, looser than the "
                            "interfaces.md default %r" % (key, got, want))


def _referenced_evidence(manifest: dict[str, Any]):
    """Yield (path, evidence_id) for every evidence reference in the file."""
    def walk(node: Any, path: str):
        if isinstance(node, dict):
            for key, value in node.items():
                here = "%s.%s" % (path, key) if path else key
                if key in ("evidence_ids", "evidence_id"):
                    if isinstance(value, str):
                        yield here, value
                    elif isinstance(value, list):
                        for item in value:
                            yield here, item
                else:
                    yield from walk(value, here)
        elif isinstance(node, list):
            for index, item in enumerate(node):
                yield from walk(item, "%s[%d]" % (path, index))

    # The evidence list itself holds ids, not references to them.
    for key, value in manifest.items():
        if key == "evidence":
            continue
        yield from walk(value, key)
