"""Damage ownership for flicker_sustained_v1 (P07-T02, D07 item 3).

One table, keyed by the coverage registry's damage-source mechanic ids, is
used both by coverage (the attribution rule's assignments) and by scoring.
Every source has exactly one class: ``flicker_direct`` and
``flicker_secondary`` enter the score, ``unrelated`` is reported separately.
A source listed twice is refused, so no damage can be counted twice. A source
with no class is never scored.

The table is persisted as JSON and identified by ``table_hash`` over its id,
version and classes. A reviewer's acceptance names that hash; the evaluator
refuses an objective unless the coverage rule carries exactly this table's
classes and cites this hash (review PR-18-22 R4).

The proposed table follows P09-T01.2 (``mechanics-rules.json#/attribution``):
Flicker Strike hits count, including the Charged Staff buff's added lightning
as PoB applies it to them; every other skill is reported separately. It is a
proposal until a reviewer accepts it.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Mapping

from ..domain.identity import content_hash

FLICKER_HIT = "skill/FlickerStrikePlayer"
WHIRLING_HIT = "skill/WhirlingAssaultPlayer"
SCORED = ("flicker_direct", "flicker_secondary")
CLASSES = SCORED + ("unrelated",)

#: Evidence id a coverage rule cites to bind itself to one table.
BINDING_PREFIX = "attribution-table:"
PROPOSED_PATH = (Path(__file__).resolve().parents[3]
                 / "benchmarks/p09-flicker-v1-attribution/proposed-v1.json")

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
    version: str = "1"
    evidence: tuple[str, ...] = ()
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

    @classmethod
    def load(cls, path: str | Path) -> "AttributionTable":
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        table = cls.from_rows(data["table_id"], [tuple(r) for r in data["rows"]],
                              version=str(data["version"]),
                              evidence=tuple(data.get("evidence") or ()),
                              notes=dict(data.get("notes") or {}))
        recorded = data.get("table_hash")
        if recorded is not None and recorded != table.table_hash():
            raise ValueError("%s records table_hash %s, content hashes to %s"
                             % (path, recorded, table.table_hash()))
        return table

    def table_hash(self) -> str:
        return "sha256:" + content_hash({"table_id": self.table_id, "version": self.version,
                                         "classes": dict(sorted(self.classes.items()))})

    def binding_id(self) -> str:
        return BINDING_PREFIX + self.table_hash()

    def owner(self, source: str) -> str | None:
        return self.classes.get(source)

    def scores(self, source: str) -> bool:
        return self.classes.get(source) in SCORED

    def to_json(self) -> dict:
        return {"table_id": self.table_id, "version": self.version,
                "table_hash": self.table_hash(),
                "rows": [[s, c] for s, c in sorted(self.classes.items())],
                "evidence": list(self.evidence),
                "not_modelled": dict(sorted(NOT_MODELLED.items())), "notes": dict(self.notes)}


def proposed_table() -> AttributionTable:
    """The persisted P09-T01.2 proposal (``PROPOSED_PATH``)."""
    return AttributionTable.load(PROPOSED_PATH)
