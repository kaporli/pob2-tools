"""What an export could not carry, and whether that changes the build (P02-T05).

An export that drops a field and says nothing is the defect this task exists to
repair, so every conversion here returns its losses alongside its output. A
loss is one :class:`UnsupportedField` carrying the field path, the reason and
the value itself, so a caller can keep the value out of band instead of
discovering later that it is gone.

Two severities, because they mean different things:

* ``affects_identity`` true - the field is inside the canonical identity
  projection of ``pob2opt.domain.identity``. The document cannot reproduce the
  build or item, so the export is **incomplete** and must not be offered as the
  deliverable;
* ``affects_identity`` false - the current identity excludes the field.
  Ordinary metadata does not block delivery. A ``partial`` loss still blocks
  it: missing gameplay fields in the schema cannot be certified by comparing
  that schema's reduced identity.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

#: Why a value could not be written.
NOT_REPRESENTABLE = "not_representable"
UNRESOLVED_NAME = "unresolved_name"
PARTIAL = "partial"

KINDS = (NOT_REPRESENTABLE, UNRESOLVED_NAME, PARTIAL)


@dataclass(frozen=True)
class UnsupportedField:
    """One value the document could not carry, kept rather than dropped."""

    field_path: str
    kind: str
    reason: str
    #: The value itself. Reporting without preserving would still lose it.
    preserved: Any
    affects_identity: bool

    def __post_init__(self) -> None:
        if self.kind not in KINDS:
            raise ValueError("unknown unsupported kind %r" % (self.kind,))

    def as_dict(self) -> dict[str, Any]:
        return {
            "field_path": self.field_path,
            "kind": self.kind,
            "reason": self.reason,
            "preserved": _plain(self.preserved),
            "affects_identity": self.affects_identity,
        }


def _plain(value: Any) -> Any:
    """A JSON-safe echo of a preserved value, without importing the codec."""
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if isinstance(value, dict):
        return {str(k): _plain(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set, frozenset)):
        return [_plain(v) for v in value]
    return repr(value)


@dataclass(frozen=True)
class SupportReport:
    """The losses of one conversion, and what they mean for the result."""

    unsupported: tuple[UnsupportedField, ...] = ()

    @property
    def identity_losses(self) -> tuple[UnsupportedField, ...]:
        return tuple(u for u in self.unsupported if u.affects_identity)

    @property
    def completeness(self) -> str:
        return "complete" if self.complete else "incomplete"

    @property
    def complete(self) -> bool:
        # The canonical schema may itself lack gameplay fields (support
        # settings, for example). Equal reduced identities cannot certify them.
        return not any(u.affects_identity or u.kind == PARTIAL
                       for u in self.unsupported)

    @property
    def recommended_deliverable(self) -> bool:
        """An incomplete export is never the recommended deliverable."""
        return self.complete

    def paths(self) -> tuple[str, ...]:
        return tuple(u.field_path for u in self.unsupported)

    def as_dict(self) -> dict[str, Any]:
        return {
            "completeness": self.completeness,
            "recommended_deliverable": self.recommended_deliverable,
            "unsupported": [u.as_dict() for u in self.unsupported],
        }


class LossCollector:
    """Accumulates losses under a field-path prefix."""

    def __init__(self, prefix: str = "") -> None:
        self.prefix = prefix
        self._items: list[UnsupportedField] = []

    def at(self, suffix: str) -> "LossCollector":
        child = LossCollector(self.prefix + suffix)
        child._items = self._items
        return child

    def add(self, path: str, kind: str, reason: str, preserved: Any,
            affects_identity: bool) -> None:
        self._items.append(UnsupportedField(
            field_path=self.prefix + path, kind=kind, reason=reason,
            preserved=preserved, affects_identity=affects_identity))

    def extend(self, items: Iterable[UnsupportedField], path: str = "") -> None:
        for item in items:
            self._items.append(UnsupportedField(
                field_path=self.prefix + path + item.field_path,
                kind=item.kind, reason=item.reason, preserved=item.preserved,
                affects_identity=item.affects_identity))

    def report(self) -> SupportReport:
        return SupportReport(tuple(self._items))

    def __len__(self) -> int:
        return len(self._items)
