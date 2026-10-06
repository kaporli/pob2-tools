"""The four distinct "no value" states required by contracts.md (P01-T01).

A persisted record has to keep these apart:

===========  =====================================  ========================
State        Python                                 JSON
===========  =====================================  ========================
unknown      ``None``                               ``null``
absent       ``ABSENT``                             key omitted entirely
zero         ``0`` / ``0.0`` / ``""`` / ``[]``      ``0`` / ``""`` / ``[]``
false        ``False``                              ``false``
===========  =====================================  ========================

``None`` means the fact is unknown or was not supplied and, per contracts.md,
also obliges the producer to raise a :class:`DataGap`. ``ABSENT`` means the
field does not apply to this record at all, so it never reaches JSON and never
reaches a hash. Neither is a substitute for ``0`` or ``False``.

``ABSENT`` deliberately has no truth value. ``if x:`` cannot tell it apart from
``False``, ``0`` or ``None``, and that confusion is exactly what this module
exists to prevent, so the comparison must be written ``x is ABSENT``.
"""

from __future__ import annotations

from typing import Any


class Absent:
    """Singleton marker for a field that does not apply to this record."""

    __slots__ = ()
    _instance: Absent | None = None

    def __new__(cls) -> Absent:
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __repr__(self) -> str:
        return "ABSENT"

    def __bool__(self) -> bool:
        raise TypeError(
            "ABSENT has no truth value: it is not None, not False and not 0. "
            "Write `x is ABSENT` or `x is not ABSENT`."
        )

    def __copy__(self) -> Absent:
        return self

    def __deepcopy__(self, memo: dict[int, Any]) -> Absent:
        return self

    def __reduce__(self) -> tuple[Any, ...]:
        return (Absent, ())


ABSENT = Absent()


def is_present(value: Any) -> bool:
    """True when the field applies, including when its value is unknown."""
    return value is not ABSENT


def present_items(mapping: dict[str, Any]) -> dict[str, Any]:
    """Drop absent entries; keep ``None``, ``0``, ``False`` and ``[]``."""
    return {k: v for k, v in mapping.items() if v is not ABSENT}
