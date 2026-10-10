"""Catalog names a PoB document needs and a BuildSpec does not carry (P02-T05).

A BuildSpec holds catalog IDs. A PoB document holds PoB's own display names and
native numeric IDs. Translating between them is catalog data, and P02-T02 owns
the catalog, so nothing here invents a mapping: the caller supplies the tables
and an ID that is not in them is reported as unresolved.

Two rules make the tables usable in both directions:

* a table must be injective. Two catalog IDs sharing one PoB name cannot be
  told apart on the way back, so the inverse is refused rather than guessed;
* lookups never fall back. ``resolve`` raises :class:`UnresolvedName`, which
  the exporter turns into a reported unsupported field.

Nothing here is a claim about PoE 2 content. The tables are data supplied by a
caller, and the test tables are synthetic.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping


class UnresolvedName(LookupError):
    """A catalog ID with no entry in the supplied table."""

    def __init__(self, table: str, key: str) -> None:
        super().__init__("%s has no entry for %r" % (table, key))
        self.table = table
        self.key = key


class AmbiguousNaming(ValueError):
    """Two catalog IDs share one PoB name, so the reverse read is undecidable."""


def _invert(table: Mapping[str, object], name: str) -> dict[object, str]:
    out: dict[object, str] = {}
    for key, value in table.items():
        if value in out:
            raise AmbiguousNaming(
                "%s maps %r and %r to the same PoB name %r; a document written "
                "with it cannot be read back" % (name, out[value], key, value))
        out[value] = key
    return out


@dataclass(frozen=True)
class CatalogNaming:
    """Catalog ID to PoB name, in both directions.

    Every field is a plain mapping the caller owns. The empty default means
    "no entry", which produces an unresolved report, not a silent default.
    """

    #: class_id -> PoB ``className`` (``Build@className``, ``Spec`` lookup).
    class_names: Mapping[str, str] = field(default_factory=dict)
    #: class_id -> the tree's numeric class ID (``Spec@classId``).
    class_tree_ids: Mapping[str, int] = field(default_factory=dict)
    #: ascendancy_id -> PoB ``ascendClassName``.
    ascendancy_names: Mapping[str, str] = field(default_factory=dict)
    #: ascendancy_id -> numeric ``Spec@ascendClassId``.
    ascendancy_tree_ids: Mapping[str, int] = field(default_factory=dict)
    #: passive catalog ID -> native tree node ID. PoB parses ``Spec@nodes``
    #: with ``%d+``, so a node that has no native ID cannot be written at all.
    node_ids: Mapping[str, int] = field(default_factory=dict)
    #: Which passive catalog IDs are ascendancy nodes. PoB keeps both kinds in
    #: one ``nodes`` list, so without this the split cannot be read back.
    ascendancy_node_ids: frozenset[str] = frozenset()
    #: passive choice option ID -> ``Strength``, ``Dexterity`` or
    #: ``Intelligence``; PoB's ``AttributeOverride`` carries only these three.
    attribute_options: Mapping[str, str] = field(default_factory=dict)
    #: equipment slot ID -> PoB slot name (``Slot@name``).
    slot_names: Mapping[str, str] = field(default_factory=dict)
    #: weapon set ID -> PoB weapon set number (1 or 2).
    weapon_set_numbers: Mapping[str, int] = field(default_factory=dict)
    #: item base ID -> PoB base type line.
    base_names: Mapping[str, str] = field(default_factory=dict)
    #: skill catalog ID -> PoB ``Gem@skillId``.
    skill_ids: Mapping[str, str] = field(default_factory=dict)
    #: gem catalog ID -> PoB ``Gem@gemId``.
    gem_ids: Mapping[str, str] = field(default_factory=dict)
    #: Which skill catalog IDs are support gems. A socket group is a flat gem
    #: list, so this is what splits it back into actives and their supports.
    support_skill_ids: frozenset[str] = frozenset()

    def resolve(self, table: str, key: str):
        """The PoB name for one catalog ID, or :class:`UnresolvedName`."""
        mapping = getattr(self, table)
        try:
            return mapping[key]
        except KeyError:
            raise UnresolvedName(table, key) from None

    def reverse(self, table: str, value) -> str:
        """The catalog ID for one PoB name, or :class:`UnresolvedName`."""
        inverse = self._inverse(table)
        try:
            return inverse[value]
        except KeyError:
            raise UnresolvedName(table + " (reverse)", str(value)) from None

    def _inverse(self, table: str) -> dict[object, str]:
        return _invert(getattr(self, table), table)

    def check_invertible(self) -> None:
        """Raise if any table would be undecidable on the way back."""
        for table in ("class_names", "class_tree_ids", "ascendancy_names",
                      "ascendancy_tree_ids", "node_ids", "attribute_options",
                      "slot_names", "weapon_set_numbers", "base_names",
                      "skill_ids", "gem_ids"):
            self._inverse(table)
