"""Game clipboard item text into an ItemInstance (P05-T02).

The game copies an item as sections separated by ``--------``: a header
(``Item Class``, ``Rarity``, name and base), displayed properties,
requirements, sockets, item level, then modifier sections, then item flags.
A modifier's category is the suffix marker the game writes after it:
``(implicit)``, ``(enchant)``, ``(rune)``, ``(fractured)``, ``(crafted)`` or
``(desecrated)``. These are the markers PoB's own reader accepts
(``Item.lua`` ``lineFlags``).

Rules, kept narrow so nothing is guessed:

* An unmarked line in the **first** section holding unmarked modifier lines
  is ``explicit``. ``Grants Skill:`` lines are ``implicit``, as PoB reads them.
  An unmarked line in any later section (a unique's flavour text, or anything
  else this reader cannot place) is kept with category ``unknown`` and
  ``parse_status: unresolved``, and the item is ``partial``.
* Displayed weapon and defence values (``Physical Damage``, ``Armour``,
  ``Evasion Rating`` ...) are totals the game computed from the base and the
  modifiers. They are not stored as properties, where PoB would read them as
  base values; ``raw_text`` keeps them. ``Quality``, ``Limited to`` and
  ``Radius`` are stored.
* Requirements keep level and every attribute (``str``, ``dex``, ``int``).
* A ``Note:`` line is a seller's price note: acquisition metadata, never an
  item property. It stays in ``raw_text`` and is reported.
* Unrevealed ``Desecrated Prefix``/``Suffix`` lines are ``desecrated``
  modifiers with ``parse_status: unresolved``.
* PoB's advanced copy (``{ Prefix Modifier ... }`` headers) is refused.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, replace
from typing import Any, Sequence

from ..domain.enums import ModifierCategory, ModifierParseStatus, RecordParseStatus
from ..domain.records import ItemInstance, ItemModifier, Socket
from ..evaluation.itemtext import (FLAG_LINES, TITLED_RARITIES,
                                   base_id_for_name)
from ..evaluation.naming import CatalogNaming
from ..evaluation.support import MalformedSource, source_int, source_number

SEPARATOR = "--------"

#: Suffix marker -> category, in the order a line with several is decided.
#: PoB reads ``(rune)`` as an enchant too; the record keeps it as ``rune``.
CATEGORY_MARKERS = (
    ("rune", ModifierCategory.RUNE),
    ("enchant", ModifierCategory.ENCHANT),
    ("fractured", ModifierCategory.FRACTURED),
    ("crafted", ModifierCategory.CRAFTED),
    ("desecrated", ModifierCategory.DESECRATED),
    ("implicit", ModifierCategory.IMPLICIT),
)
#: Suffix markers that are line flags, not categories.
FLAG_MARKERS = ("mutated", "unscalable", "disabled")

#: Displayed values the game computes. Kept in raw_text only.
DISPLAYED_LABELS = frozenset({
    "Physical Damage", "Elemental Damage", "Chaos Damage", "Fire Damage",
    "Cold Damage", "Lightning Damage", "Critical Hit Chance",
    "Critical Hit Range", "Attacks per Second", "Reload Time",
    "Weapon Range", "Armour", "Evasion Rating", "Evasion", "Energy Shield",
    "Block chance", "Chance to Block", "Spirit", "Charm Slots", "Stack Size",
})
STORED_LABELS = {"Quality": "quality", "Limited to": "limit"}
TEXT_LABELS = {"Radius": "radius"}
ATTRIBUTES = {"Str": "str", "Dex": "dex", "Int": "int",
              "Strength": "str", "Dexterity": "dex", "Intelligence": "int"}
#: Item flags the game writes as their own line, beyond PoB's.
GAME_FLAG_LINES = dict({v: k for k, v in FLAG_LINES.items()},
                       Unidentified="unidentified")
UNREVEALED = ("Desecrated Prefix", "Desecrated Suffix")
EQUIPMENT_RARITIES = ("normal", "magic", "rare", "unique", "relic")

_ANNOTATION = re.compile(r"\s*\((augmented|unmet)\)")
_SUFFIX = re.compile(r"^(.*\S) \(([a-z]+)\)$")


class GameTextRefused(ValueError):
    """Item text this reader will not interpret. ``reason`` is a short code."""

    def __init__(self, reason: str, detail: str) -> None:
        super().__init__("%s: %s" % (reason, detail))
        self.reason = reason
        self.detail = detail


@dataclass(frozen=True)
class GameTextNote:
    """Something the reader kept out of the item, or could not place."""

    code: str
    locator: str
    explanation: str


@dataclass(frozen=True)
class GameTextRead:
    item: ItemInstance
    notes: tuple[GameTextNote, ...]


def is_game_text(text: str) -> bool:
    """True for game clipboard text; PoB's own item text has no separator."""
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    return bool(lines) and (lines[0].startswith("Item Class:")
                            or SEPARATOR in lines)


def _sections(text: str) -> list[list[tuple[int, str]]]:
    sections: list[list[tuple[int, str]]] = [[]]
    for number, raw in enumerate(text.replace("\r\n", "\n").split("\n"), 1):
        line = raw.strip()
        if not line:
            continue
        if line == SEPARATOR:
            sections.append([])
            continue
        sections[-1].append((number, line))
    return [section for section in sections if section]


def _plain(value: str) -> str:
    return _ANNOTATION.sub("", value).strip()


def _requirement_list(value: str, locator: str) -> dict[str, int]:
    """``Level 59, 33 Str, 81 (unmet) Dex`` -> requirements."""
    out: dict[str, int] = {}
    for part in _plain(value).split(","):
        words = part.split()
        if len(words) == 2 and words[0] == "Level":
            out["level"] = source_int(words[1], locator, minimum=0)
        elif len(words) == 2 and words[1] in ATTRIBUTES:
            out[ATTRIBUTES[words[1]]] = source_int(words[0], locator, minimum=0)
        else:
            raise MalformedSource(locator, part.strip(), "a requirement")
    return out


def _split_markers(line: str) -> tuple[str, list[str]]:
    markers: list[str] = []
    body = line
    while True:
        match = _SUFFIX.match(body)
        if match is None or match.group(2) not in (
                {name for name, _ in CATEGORY_MARKERS} | set(FLAG_MARKERS)):
            return body, markers
        body = match.group(1)
        markers.append(match.group(2))


def import_game_item(text: str, naming: CatalogNaming, *, record_id: str,
                     created_at: str, catalog_hash: str,
                     provenance_ids: Sequence[str] = (),
                     source_document_id: str | None = None) -> GameTextRead:
    """Read game clipboard text. Raises :class:`GameTextRefused` or
    :class:`MalformedSource`; never fills a value the text does not hold."""
    from ..domain.identity import item_hash as _item_hash

    sections = _sections(text)
    if not sections:
        raise GameTextRefused("empty_item_text", "the item text has no lines")
    for number, line in (entry for section in sections for entry in section):
        if line.startswith("{ "):
            raise GameTextRefused(
                "advanced_copy_unsupported",
                "line %d is an advanced-copy modifier header; copy the item "
                "without the advanced format" % number)

    header = [line for _, line in sections[0]
              if not line.startswith("Item Class:")]
    if not header or not header[0].startswith("Rarity: "):
        raise GameTextRefused("no_rarity", "the header has no Rarity line")
    rarity = header[0][len("Rarity: "):].strip().lower()
    if rarity not in EQUIPMENT_RARITIES:
        raise GameTextRefused("not_equipment",
                              "rarity %r is not an equipment item" % rarity)
    names = header[1:]
    if rarity in TITLED_RARITIES and len(names) == 2:
        display_name, base_name = names
    elif len(names) == 1:
        display_name = base_name = names[0]
    else:
        raise GameTextRefused("header_unrecognized",
                              "expected a name and a base, found %d lines"
                              % len(names))

    item_level: int | None = None
    properties: dict[str, Any] = {}
    requirements: dict[str, int] = {}
    sockets: list[Socket] = []
    flags: dict[str, bool] = {}
    modifiers: list[ItemModifier] = []
    notes: list[GameTextNote] = []
    explicit_section: int | None = None
    partial = False

    for index, section in enumerate(sections[1:], 1):
        in_requirements = False
        reminder_depth = 0
        for number, line in section:
            locator = "/text/line/%d" % number
            if reminder_depth or (line.startswith("(") and not _split_markers(line)[1]):
                reminder_depth += line.count("(") - line.count(")")
                if reminder_depth < 0 or (reminder_depth == 0 and not line.endswith(")")):
                    raise GameTextRefused(
                        "malformed_reminder",
                        "reminder parentheses must balance and close at the end of a line")
                continue
            if line in GAME_FLAG_LINES:
                flags[GAME_FLAG_LINES[line]] = True
                continue
            if line == "Requirements:":
                in_requirements = True
                continue
            label, separator, value = line.partition(": ")
            if in_requirements and separator and label in ("Level", *ATTRIBUTES):
                key = "level" if label == "Level" else ATTRIBUTES[label]
                requirements[key] = source_int(_plain(value), locator, minimum=0)
                continue
            if line.startswith("Requires"):
                rest = line[len("Requires"):].lstrip(":").strip()
                requirements.update(_requirement_list(rest, locator))
                continue
            if separator and label == "Item Level":
                item_level = source_int(_plain(value), locator, minimum=0)
                continue
            if separator and label == "Sockets":
                sockets = [Socket(socket_id=str(i), group=i, colour=letter,
                                  contents_id=None)
                           for i, letter in enumerate(value.split())]
                continue
            if separator and label in STORED_LABELS:
                number_text = _plain(value).lstrip("+").rstrip("%")
                properties[STORED_LABELS[label]] = source_number(number_text,
                                                                 locator)
                continue
            if separator and label in TEXT_LABELS:
                properties[TEXT_LABELS[label]] = _plain(value)
                continue
            if separator and label in DISPLAYED_LABELS:
                continue
            if separator and label == "Note":
                notes.append(GameTextNote(
                    "price_note_not_item_data", locator,
                    "a seller's note is acquisition metadata, not an item "
                    "property; raw_text keeps it"))
                continue
            if line in UNREVEALED:
                partial = True
                modifiers.append(ItemModifier(
                    category=ModifierCategory.DESECRATED,
                    source_position=len(modifiers), text=line, native_id=None,
                    resolved_effect_ids=[], values=[], flags={},
                    parse_status=ModifierParseStatus.UNRESOLVED))
                notes.append(GameTextNote(
                    "unrevealed_modifier", locator,
                    "an unrevealed desecrated modifier has no stats yet"))
                continue

            body, markers = _split_markers(line)
            category = next((cat for name, cat in CATEGORY_MARKERS
                             if name in markers), None)
            status = ModifierParseStatus.RESOLVED
            if category is None and body.startswith("Grants Skill: "):
                category = ModifierCategory.IMPLICIT
            if category is None:
                if explicit_section is None:
                    explicit_section = index
                if explicit_section == index:
                    category = ModifierCategory.EXPLICIT
                else:
                    category = ModifierCategory.UNKNOWN
                    status = ModifierParseStatus.UNRESOLVED
                    partial = True
                    notes.append(GameTextNote(
                        "unclassified_line", locator,
                        "an unmarked line after the explicit section (flavour "
                        "text or an unplaced modifier); kept as category "
                        "unknown"))
            modifiers.append(ItemModifier(
                category=category, source_position=len(modifiers), text=body,
                native_id=None, resolved_effect_ids=[], values=[],
                flags={name: True for name in markers if name in FLAG_MARKERS},
                parse_status=status))

        if reminder_depth:
            raise GameTextRefused(
                "unterminated_reminder",
                "a reminder must close before the end of its section; "
                "otherwise subsequent modifiers cannot be read safely")

    item = ItemInstance(
        schema_version=1, record_id=record_id, created_at=created_at,
        provenance_ids=list(provenance_ids), item_hash="",
        catalog_hash=catalog_hash,
        base_id=base_id_for_name(base_name, rarity, naming),
        display_name=display_name, rarity=rarity, item_level=item_level,
        requirements=requirements, properties=properties, modifiers=modifiers,
        sockets=sockets, flags=flags, raw_text=text,
        source_document_id=source_document_id,
        parse_status=(RecordParseStatus.PARTIAL if partial
                      else RecordParseStatus.COMPLETE))
    return GameTextRead(replace(item, item_hash=_item_hash(item)), tuple(notes))
