"""Which base categories each equipment slot accepts (P02-T03.1).

Read from the engine's own ``ItemsTab:IsItemValidForSlot`` through the
``slotAcceptance`` rule source: one probe item per base, asked against every
slot. This module turns those counts into rules and decides one item against
one rule. It never widens a category the engine split, and it never fills in
a slot the engine accepts nothing for under the probe.

A base category is the base's ``type``, or ``type/subType`` when the base has
a subtype. The engine splits flasks by subtype (life flasks in ``Flask 1``,
mana flasks in ``Flask 2``), so the subtype has to be part of the key. Some
sockets also refuse unique and relic items; the probe asks at each rarity and
a slot refusing one for every category records it in ``refused_rarities``.

What the probe cannot decide is carried in the rule, not only in a gap: a
category accepted for some of its bases (``undecided_categories``), a
category whose answer at a rarity differs from normal rarity while the slot
does not refuse that rarity outright (``undecided_rarities``), a base whose
probe item could not be built (``undecided_bases``) and an off-hand context
whose main-hand bases disagree (``undecided``). ``decide`` answers
``undecided`` for exactly those combinations and cites the rule's
``gap_ids``; every other combination keeps a definite answer.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping

#: Main-hand category the engine uses for an empty main hand.
UNARMED = "Unarmed"
#: Flag value of an off-hand rule that assumes no keystone.
NO_FLAG = "none"
#: In ``undecided_categories``: every category the rule does not accept is
#: undecided (an off-hand slot with a main hand whose bases disagree).
ANY_OTHER = "*"

ACCEPTED, REFUSED, UNDECIDED = "accepted", "refused", "undecided"


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


def _rarities(full: list[str], partial: list[str], by_rarity: Any
              ) -> tuple[list[str], dict[str, list[str]]]:
    """Rarities refused outright, and per rarity the undecided categories.

    A rarity whose probe accepts exactly the normal categories is decided by
    the normal rule. One accepting none of them, while normal items are
    accepted, is refused. Anything in between leaves each category whose
    answer differs undecided at that rarity: probe items are not real uniques,
    so a category-level difference is not proof for an individual item.
    """
    refused: list[str] = []
    undecided: dict[str, list[str]] = {}
    for rarity, categories in sorted(_mapping(by_rarity).items()):
        accepted, some = _full(categories)
        if accepted == full and some == partial:
            continue
        if full and not accepted and not some:
            refused.append(str(rarity))
            continue
        differ = (set(full) ^ set(accepted)) | set(some) | set(partial)
        differ -= set(full) & set(accepted)
        if differ:
            undecided[str(rarity)] = sorted(differ)
    return refused, undecided


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
    #: Rarity -> categories undecided at that rarity.
    rarity_undecided: Mapping[str, tuple[str, ...]] = field(default_factory=dict)


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
    #: Slot name -> rarity -> categories undecided at that rarity.
    rarity_undecided: dict[str, dict[str, list[str]]] = field(
        default_factory=dict)

    @property
    def failed_bases(self) -> list[str]:
        """Base names with a probe failure at any rarity."""
        return sorted({name.split(":", 1)[-1] for name in self.probe_failures})

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

    def off_hand_undecided(self, off_slot: str) -> list[str]:
        """Categories no context accepts but some context leaves undecided."""
        contexts = [c for c in self.off_hand if c.off_slot == off_slot]
        if any(not c.uniform for c in contexts):
            return [ANY_OTHER]
        accepted = set(self.off_hand_union(off_slot))
        return sorted({p for c in contexts for p in c.partial} - accepted)


def read_acceptance(source: Mapping[str, Any] | None) -> SlotAcceptance | None:
    """Decode ``rule_sources['slotAcceptance']``; None when the engine sent none."""
    if not source or not isinstance(source, Mapping):
        return None
    result = SlotAcceptance(
        probe_count=int(source.get("probeCount") or 0),
        probe_failures=sorted(str(n) for n in source.get("probeFailures") or ()))
    for row in source.get("slots") or ():
        full, partial = _full(row.get("categories"))
        slot = str(row["slot"])
        result.accepted[slot] = full
        if partial:
            result.partial[slot] = partial
        refused, undecided = _rarities(full, partial, row.get("byRarity"))
        if refused:
            result.refused_rarities[slot] = refused
        if undecided:
            result.rarity_undecided[slot] = undecided
    for row in source.get("offHand") or ():
        uniform = int(row.get("variants") or 0) == 1
        full, partial = _full(row.get("categories") if uniform else {})
        refused, undecided = _rarities(
            full, partial, row.get("byRarity") if uniform else {})
        result.off_hand.append(OffHandContext(
            off_slot=str(row["offSlot"]), main_slot=str(row["mainSlot"]),
            flag=str(row["flag"]), main_category=str(row["mainCategory"]),
            accepted=tuple(full), partial=tuple(partial), uniform=uniform,
            refused_rarities=tuple(refused),
            rarity_undecided={r: tuple(c) for r, c in undecided.items()}))
    return result


def _list(rule: Any, name: str) -> list:
    value = getattr(rule, name, None)
    return list(value) if isinstance(value, (list, tuple)) else []


def _dict(rule: Any, name: str) -> dict:
    value = getattr(rule, name, None)
    return dict(value) if isinstance(value, Mapping) else {}


def rule_gaps(rule: Any) -> tuple[str, ...]:
    return tuple(_list(rule, "gap_ids"))


def decide(rule: Any, raw: Mapping[str, Any] | None,
           rarity: str | None = None) -> str:
    """``accepted``, ``refused`` or ``undecided`` for one base row in one rule.

    ``rule`` is a ``SlotRule`` or an ``OffHandRule``. Undecided only where
    the rule records that the probe could not decide; a category the probe
    saw refused for every base stays ``refused``.
    """
    if getattr(rule, "undecided", None) is True:
        return UNDECIDED
    category = base_category(raw)
    if category is None:
        return UNDECIDED
    name = str((raw or {}).get("name") or "")
    if name and name in _list(rule, "undecided_bases"):
        return UNDECIDED
    accepted = set(_list(rule, "accepted_base_categories"))
    undecided = set(_list(rule, "undecided_categories"))
    if category not in accepted:
        if category in undecided or ANY_OTHER in undecided:
            return UNDECIDED
        return REFUSED
    if category in undecided:
        return UNDECIDED
    rarity = str(rarity).lower() if rarity else None
    if rarity and rarity in _list(rule, "refused_rarities"):
        return REFUSED
    if rarity and category in _dict(rule, "undecided_rarities").get(rarity, ()):
        return UNDECIDED
    return ACCEPTED


def accepts(accepted: Iterable[str], raw: Mapping[str, Any] | None,
            rarity: str | None = None, refused: Iterable[str] = ()) -> bool:
    """Does a slot with these categories and refused rarities take this base?"""
    category = base_category(raw)
    if category is None or category not in set(accepted):
        return False
    return not (rarity and str(rarity).lower() in set(refused))
