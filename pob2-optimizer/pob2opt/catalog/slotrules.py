"""Which base categories each equipment slot accepts (P02-T03.1).

Read from the engine's own ``ItemsTab:IsItemValidForSlot`` through the
``slotAcceptance`` rule source: one probe item per base, asked against every
slot. This module only turns those counts into rules. It never widens a
category the engine split, and it never fills in a slot the engine accepts
nothing for under the probe; both become gaps.

A base category is the base's ``type``, or ``type/subType`` when the base has
a subtype. The engine splits flasks by subtype (life flasks in ``Flask 1``,
mana flasks in ``Flask 2``), so the subtype has to be part of the key. Some
sockets also refuse unique and relic items; the probe asks at each rarity and
a slot refusing one for every category records it in ``refused_rarities``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping

#: Main-hand category the engine uses for an empty main hand.
UNARMED = "Unarmed"
#: Flag value of an off-hand rule that assumes no keystone.
NO_FLAG = "none"


def base_category(raw: Mapping[str, Any] | None) -> str | None:
    """The category key of one item base row, or None when it has no type."""
    if not raw:
        return None
    kind = raw.get("type")
    if not kind:
        return None
    sub = raw.get("subType")
    return "%s/%s" % (kind, sub) if sub else str(kind)


def _mapping(value: Any) -> dict:
    # The engine's JSON encoder writes an empty Lua table as a list.
    return dict(value) if isinstance(value, Mapping) else {}


def _full(categories: Mapping[str, Any]) -> tuple[list[str], list[str]]:
    """Categories every base of which is accepted, and partially accepted ones."""
    full, partial = [], []
    for key, count in sorted(_mapping(categories).items()):
        accepted, total = int(count.get("accepted", 0)), int(count.get("total", 0))
        if accepted and accepted == total:
            full.append(key)
        elif accepted:
            partial.append(key)
    return full, partial


@dataclass(frozen=True)
class OffHandContext:
    off_slot: str
    main_slot: str
    flag: str
    main_category: str
    accepted: tuple[str, ...]
    partial: tuple[str, ...]
    uniform: bool
    refused_rarities: tuple[str, ...] = ()
    #: Rarities refused for only some of the accepted categories.
    rarity_partial: tuple[str, ...] = ()


@dataclass
class SlotAcceptance:
    """The probe, decoded. Slot names are the engine's, not entity ids."""

    probe_count: int
    probe_failures: list[str]
    accepted: dict[str, list[str]] = field(default_factory=dict)
    partial: dict[str, list[str]] = field(default_factory=dict)
    off_hand: list[OffHandContext] = field(default_factory=list)
    #: Slot name -> rarities the slot refuses for every accepted category.
    refused_rarities: dict[str, list[str]] = field(default_factory=dict)
    #: Slot name -> rarities refused for only some accepted categories.
    rarity_partial: dict[str, list[str]] = field(default_factory=dict)

    @property
    def off_hand_slots(self) -> dict[str, str]:
        return {c.off_slot: c.main_slot for c in self.off_hand}

    def off_hand_union(self, off_slot: str) -> list[str]:
        """Every category some main hand and flag state lets ``off_slot`` hold."""
        out: set[str] = set()
        for context in self.off_hand:
            if context.off_slot == off_slot and context.uniform:
                out.update(context.accepted)
        return sorted(out)

    def off_hand_refused(self, off_slot: str) -> list[str]:
        """Rarities every context that accepts something in ``off_slot`` refuses."""
        sets = [set(c.refused_rarities) for c in self.off_hand
                if c.off_slot == off_slot and c.uniform and c.accepted]
        return sorted(set.intersection(*sets)) if sets else []


def _rarities(full: list[str], by_rarity: Any) -> tuple[list[str], list[str]]:
    """Rarities refused outright, and rarities refused for only some categories.

    A rarity whose probe accepts exactly the normal categories is not refused.
    One accepting none of them, while normal items are accepted, is refused.
    Anything in between cannot be said with a rarity list.
    """
    refused, partial = [], []
    for rarity, categories in sorted(_mapping(by_rarity).items()):
        accepted, some = _full(categories)
        if accepted == full and not some:
            continue
        if full and not accepted and not some:
            refused.append(str(rarity))
        elif full:
            partial.append(str(rarity))
    return refused, partial


def read_acceptance(source: Mapping[str, Any] | None) -> SlotAcceptance | None:
    """Decode ``rule_sources['slotAcceptance']``; None when the engine sent none."""
    if not source or not isinstance(source, Mapping):
        return None
    result = SlotAcceptance(
        probe_count=int(source.get("probeCount") or 0),
        probe_failures=sorted(str(n) for n in source.get("probeFailures") or ()))
    for row in source.get("slots") or ():
        full, partial = _full(row.get("categories"))
        result.accepted[str(row["slot"])] = full
        if partial:
            result.partial[str(row["slot"])] = partial
        refused, rarity_partial = _rarities(full, row.get("byRarity"))
        if refused:
            result.refused_rarities[str(row["slot"])] = refused
        if rarity_partial:
            result.rarity_partial[str(row["slot"])] = rarity_partial
    for row in source.get("offHand") or ():
        uniform = int(row.get("variants") or 0) == 1
        full, partial = _full(row.get("categories") if uniform else {})
        refused, rarity_partial = _rarities(
            full, row.get("byRarity") if uniform else {})
        result.off_hand.append(OffHandContext(
            off_slot=str(row["offSlot"]), main_slot=str(row["mainSlot"]),
            flag=str(row["flag"]), main_category=str(row["mainCategory"]),
            accepted=tuple(full), partial=tuple(partial), uniform=uniform,
            refused_rarities=tuple(refused),
            rarity_partial=tuple(rarity_partial)))
    return result


def accepts(accepted: Iterable[str], raw: Mapping[str, Any] | None,
            rarity: str | None = None, refused: Iterable[str] = ()) -> bool:
    """Does a slot with these categories and refused rarities take this base?"""
    category = base_category(raw)
    if category is None or category not in set(accepted):
        return False
    return not (rarity and str(rarity).lower() in set(refused))
