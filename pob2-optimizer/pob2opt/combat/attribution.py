"""Damage ownership for flicker_sustained_v1 (P07-T02, D07 item 3).

Every damage source in a timeline has exactly one class: ``flicker_direct``
and ``flicker_secondary`` enter the score, ``unrelated`` is reported
separately. A source listed in two classes is refused, so no damage can be
counted twice. A source with no class is never scored; the coverage report
carries its gap.

The proposed table follows P09-T01.2 (``mechanics-rules.json#/attribution``):
Flicker Strike hits count, including the Charged Staff buff's added lightning
as PoB applies it to them; Whirling Assault and every other skill are
reported separately. It is a proposal until a reviewer accepts it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping

FLICKER_HIT = "flicker_strike_hit"
WHIRLING_HIT = "whirling_assault_hit"
SCORED = ("flicker_direct", "flicker_secondary")
CLASSES = SCORED + ("unrelated",)

#: Damage the P09-T01.2 table names but this slice does not put on the
#: timeline. Reported as not modelled, never scored.
NOT_MODELLED = {
    "flicker_strike_ignite": "unrelated: excluded from the v1 score, PoB IgniteDPS reported",
    "charged_shockwave": "unrelated: owned by Charged Staff",
    "living_lightning": "unrelated: minion damage",
    "herald_of_ice": "unrelated: needs shatters or kills, absent on the benchmark",
    "herald_of_thunder": "unrelated",
}


class DoubleAttribution(ValueError):
    pass


@dataclass(frozen=True)
class AttributionTable:
    table_id: str
    classes: Mapping[str, str]
    evidence: tuple[str, ...] = ()
    #: Who accepted the table; None while it is a proposal.
    accepted_by: str | None = None
    notes: Mapping[str, str] = field(default_factory=dict)

    def __post_init__(self):
        for source, cls in self.classes.items():
            if cls not in CLASSES:
                raise ValueError("source %s has unknown class %r" % (source, cls))

    @classmethod
    def from_rows(cls, table_id: str, rows: list[tuple[str, str]], **kw) -> "AttributionTable":
        seen: dict[str, str] = {}
        for source, klass in rows:
            if source in seen and seen[source] != klass:
                raise DoubleAttribution("%s is listed as both %s and %s"
                                        % (source, seen[source], klass))
            if source in seen:
                raise DoubleAttribution("%s is listed twice" % source)
            seen[source] = klass
        return cls(table_id=table_id, classes=seen, **kw)

    def owner(self, source: str) -> str | None:
        return self.classes.get(source)

    def scores(self, source: str) -> bool:
        return self.classes.get(source) in SCORED

    def to_json(self) -> dict:
        return {"table_id": self.table_id, "classes": dict(sorted(self.classes.items())),
                "accepted_by": self.accepted_by, "evidence": list(self.evidence),
                "not_modelled": dict(sorted(NOT_MODELLED.items())), "notes": dict(self.notes)}


def proposed_table() -> AttributionTable:
    return AttributionTable.from_rows(
        "p09-t012-attribution-proposed",
        [(FLICKER_HIT, "flicker_direct"), (WHIRLING_HIT, "unrelated")],
        evidence=("docs/evidence/P09-T01.2/mechanics-rules.json#/attribution",),
        notes={FLICKER_HIT: "PoB AverageDamage per strike at the method's charges; includes the "
                            "Charged Staff buff lightning while the buff is up",
               WHIRLING_HIT: "PoB AverageBurstDamage per use; separate skill"})
