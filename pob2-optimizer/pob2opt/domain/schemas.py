"""Load and resolve the versioned JSON Schemas (P01-T01).

``schemas/v1`` lives inside the package (``pob2opt/schemas/v1``) so a record
can be validated from an installed wheel, not only from a source checkout.

Cross-file ``$ref`` values are plain relative names such as
``run_request.json``. They are resolved from a registry built out of the files
on disk, so validation never reaches the network: the ``$id`` host
``pob2-tools.invalid`` is reserved by RFC 2606 and can never resolve.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

import jsonschema
from referencing import Registry, Resource
from referencing.jsonschema import DRAFT202012

from .records import supported_schema_versions

SCHEMA_DIR = Path(__file__).resolve().parents[1] / "schemas" / "v1"


class UnknownSchemaVersion(ValueError):
    """A record declares a schema version this build does not implement."""

    def __init__(self, found: Any, kind: str | None = None) -> None:
        self.found = found
        self.supported = supported_schema_versions(kind)
        super().__init__(
            "unsupported schema_version %r; this build supports %s"
            % (found, ", ".join(str(v) for v in self.supported))
        )


class UnknownRecordKind(LookupError):
    def __init__(self, kind: str) -> None:
        self.kind = kind
        super().__init__("no schema for record kind %r in %s" % (kind, SCHEMA_DIR))


@lru_cache(maxsize=1)
def _documents() -> dict[str, Any]:
    if not SCHEMA_DIR.is_dir():  # pragma: no cover - packaging error
        raise FileNotFoundError("schema directory is missing: %s" % SCHEMA_DIR)
    return {
        path.name: json.loads(path.read_text(encoding="utf-8"))
        for path in sorted(SCHEMA_DIR.glob("*.json"))
    }


@lru_cache(maxsize=1)
def registry() -> Registry:
    """Every schema file, addressable by ``$id`` and by bare file name."""
    resources = []
    for name, doc in _documents().items():
        resource = Resource.from_contents(doc, default_specification=DRAFT202012)
        resources.append((name, resource))
        if "$id" in doc:
            resources.append((doc["$id"], resource))
    return Registry().with_resources(resources)


def schema_for(kind: str) -> dict[str, Any]:
    try:
        return _documents()["%s.json" % kind]
    except KeyError:
        raise UnknownRecordKind(kind) from None


@lru_cache(maxsize=None)
def validator_for(kind: str) -> jsonschema.protocols.Validator:
    schema = schema_for(kind)
    cls = jsonschema.validators.validator_for(schema)
    cls.check_schema(schema)
    return cls(schema, registry=registry())


def available_kinds() -> tuple[str, ...]:
    return tuple(sorted(name[: -len(".json")] for name in _documents()))


def check_schema_version(value: Any, kind: str | None = None) -> int:
    """Reject an unknown version with a message naming the supported ones.

    Versions are per record kind: BuildSpec reads 1 and 2, every other kind
    reads 1. Without a kind, any version some kind reads is accepted.
    """
    if value not in supported_schema_versions(kind) or isinstance(value, bool):
        raise UnknownSchemaVersion(value, kind)
    return int(value)
