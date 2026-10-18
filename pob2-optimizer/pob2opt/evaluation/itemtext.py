"""An ItemInstance as PoB item text, and back again (P02-T05).

PoB's item format is a line list: a rarity line, a name, a base type, keyed
property lines, an ``Implicits: N`` count and then the modifier lines, the
first ``N`` of which are the implicit-like ones. Category is carried by the
``{enchant}``, ``{rune}``, ``{fractured}``, ``{crafted}`` and ``{desecrated}``
markers PoB itself writes in ``Item:BuildRaw``; an implicit has no marker and
is identified by sitting inside the counted block.

What round trips, and what does not, is declared in :data:`SUPPORT` below and
reported per item rather than discovered later. Nothing here parses PoB's
modifier text into effects: that is P04's work, and guessing it would be the
silent-fill failure the parsers layer is told not to commit.

Neither direction mutates its input. The records are frozen, the mappings are
copied before use, and ``tests/unit/test_p02_t05_no_mutation.py`` hashes the
source before and after.
"""

from __future__ import annotations

from typing import Any, Sequence

from ..domain.enums import ModifierCategory, ModifierParseStatus, RecordParseStatus
from ..domain.records import ItemInstance, ItemModifier, Socket
from .naming import CatalogNaming, UnresolvedName
from .support import (NOT_REPRESENTABLE, PARTIAL, UNRESOLVED_NAME,
                      LossCollector, source_int, source_number)

#: Category to the marker PoB writes for it. ``implicit`` and ``explicit`` have
#: none: their block decides. ``unknown`` has no marker at all, which is why an
#: unknown-category modifier cannot be written.
CATEGORY_MARKER: dict[ModifierCategory, str] = {
    ModifierCategory.ENCHANT: "{enchant}",
    ModifierCategory.RUNE: "{rune}",
    ModifierCategory.IMPLICIT: "",
    ModifierCategory.EXPLICIT: "",
    ModifierCategory.FRACTURED: "{fractured}",
    ModifierCategory.CRAFTED: "{crafted}",
    ModifierCategory.DESECRATED: "{desecrated}",
}

#: Categories PoB counts inside ``Implicits: N``.
IMPLICIT_BLOCK = (ModifierCategory.ENCHANT, ModifierCategory.RUNE,
                  ModifierCategory.IMPLICIT)

#: PoB line flags that are not a category. ``prefix``/``suffix``/``custom`` are
#: writable too but belong to PoB's crafting state, so they stay out.
MODIFIER_LINE_FLAGS = ("disabled", "mutated", "unscalable")

#: property key -> the PoB line that carries it.
NUMERIC_PROPERTY_LINES = {
    "quality": "Quality",
    "armour": "Armour",
    "evasion": "Evasion",
    "energy_shield": "Energy Shield",
    "spirit": "Spirit",
    "charm_slots": "Charm Slots",
    "limit": "Limited to",
    "runic_ward": "Runic Ward",
}
TEXT_PROPERTY_LINES = {"radius": "Radius"}

#: Header lines PoB writes that identify one physical copy, not its stats.
#: Read and dropped: an item is its stats, so two copies are one item.
INSTANCE_LINES = ("Unique ID",)

#: Item flags PoB writes as their own line.
FLAG_LINES = {
    "mirrored": "Mirrored",
    "sanctified": "Sanctified",
    "double_corrupted": "Twice Corrupted",
    "corrupted": "Corrupted",
}

#: Rarities PoB writes a separate title line for.
TITLED_RARITIES = ("rare", "unique", "relic")

SUPPORT = {
    "round_trips": (
        "rarity", "display_name", "base_id (through CatalogNaming.base_names)",
        "item_level", "requirements['level']", "sockets (colour and order)",
        "every ModifierCategory except unknown", "modifier text",
        "modifier line flags disabled/mutated/unscalable",
        "item variants and the selected variant",
        "the item flags corrupted, double_corrupted, mirrored, sanctified",
        "PoB's per-socket rune names (properties['runes'])",
    ),
    "not_representable": (
        "ModifierCategory.unknown: PoB has no marker for it",
        "ItemModifier.native_id, resolved_effect_ids, parse_status: PoB text "
        "carries no catalog resolution",
        "ItemModifier.values: a roll range can only be written in PoB's "
        "advanced-copy form, which marks the whole item crafted",
        "a flag recorded false: PoB writes only the positive line, so false "
        "and absent become the same document",
        "requirements other than level",
        "Socket.contents_id and a socket_id that is not its index",
        "modifier source positions that are not 0..n-1 in block order",
        "PoB's per-copy Unique ID line: read and dropped, never a modifier",
    ),
}


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _format_number(value: Any) -> str:
    if isinstance(value, int) and not isinstance(value, bool):
        return str(value)
    if isinstance(value, float) and value.is_integer():
        return "%g" % value
    return repr(value)


def _block_of(category: ModifierCategory) -> int:
    return 0 if category in IMPLICIT_BLOCK else 1


def _modifier_line(modifier: ItemModifier, losses: LossCollector,
                   index: int) -> str | None:
    path = "/modifiers/%d" % index
    marker = CATEGORY_MARKER.get(modifier.category)
    if marker is None:
        losses.add(path + "/category", NOT_REPRESENTABLE,
                   "PoB item text has no marker for the %s category"
                   % modifier.category.value, modifier.text, True)
        return None
    prefix = marker
    for name, value in sorted(modifier.flags.items()):
        if name.startswith("variant:"):
            continue
        if not value:
            losses.add(path + "/flags/" + name, NOT_REPRESENTABLE,
                       "PoB writes only the positive line flag, so a flag "
                       "recorded false cannot be told from an absent one",
                       False, True)
            continue
        if name not in MODIFIER_LINE_FLAGS:
            losses.add(path + "/flags/" + name, NOT_REPRESENTABLE,
                       "not one of the PoB modifier line flags %s"
                       % (MODIFIER_LINE_FLAGS,), True, True)
            continue
        prefix += "{%s}" % name
    variants = sorted(int(k.split(":", 1)[1]) for k, v in modifier.flags.items()
                      if k.startswith("variant:") and v)
    if variants:
        prefix = "{variant:%s}" % ",".join(str(v) for v in variants) + prefix
    if modifier.native_id is not None:
        losses.add(path + "/native_id", NOT_REPRESENTABLE,
                   "PoB item text carries no catalog modifier ID",
                   modifier.native_id, True)
    if modifier.resolved_effect_ids:
        losses.add(path + "/resolved_effect_ids", NOT_REPRESENTABLE,
                   "PoB item text carries no resolved effect references",
                   list(modifier.resolved_effect_ids), True)
    if modifier.values:
        losses.add(path + "/values", NOT_REPRESENTABLE,
                   "a roll range is writable only in PoB's advanced-copy form, "
                   "which marks the whole item crafted",
                   [[v.rolled, v.minimum, v.maximum] for v in modifier.values],
                   True)
    if modifier.parse_status is not ModifierParseStatus.RESOLVED:
        losses.add(path + "/parse_status", NOT_REPRESENTABLE,
                   "a PoB document records no parse status; every line reads "
                   "back as resolved", modifier.parse_status.value, True)
    if "\n" in modifier.text:
        losses.add(path + "/text", NOT_REPRESENTABLE,
                   "a modifier line cannot contain a newline", modifier.text,
                   True)
        return None
    return prefix + modifier.text


def _socket_lines(item: ItemInstance, losses: LossCollector) -> list[str]:
    if not item.sockets:
        return []
    letters = []
    for index, socket in enumerate(item.sockets):
        path = "/sockets/%d" % index
        if socket.socket_id != str(index):
            losses.add(path + "/socket_id", NOT_REPRESENTABLE,
                       "PoB numbers sockets by position; only the index reads "
                       "back", socket.socket_id, True)
        if socket.group != index:
            losses.add(path + "/group", NOT_REPRESENTABLE,
                       "PoE 2 sockets are not linked, so PoB writes one group "
                       "per socket", socket.group, True)
        if socket.contents_id is not None:
            losses.add(path + "/contents_id", NOT_REPRESENTABLE,
                       "socketed contents are a separate item reference, not "
                       "part of the socket line", socket.contents_id, True)
        letters.append(socket.colour or "S")
    return ["Sockets: " + " ".join(letters)]


def export_item(item: ItemInstance, naming: CatalogNaming,
                prefix: str = "") -> tuple[str, LossCollector]:
    """One ItemInstance as PoB item text, plus everything it could not carry."""
    losses = LossCollector(prefix)
    if item.parse_status is not RecordParseStatus.COMPLETE:
        losses.add("/parse_status", PARTIAL,
                   "the item's source import has unresolved gameplay content",
                   item.parse_status.value, False)
    lines: list[str] = []
    rarity = str(item.rarity).upper()
    lines.append("Rarity: " + rarity)
    base_line = None
    if item.base_id is None:
        losses.add("/base_id", UNRESOLVED_NAME,
                   "the item has no resolved base; PoB needs a base type line",
                   None, True)
    else:
        try:
            base_line = naming.resolve("base_names", item.base_id)
        except UnresolvedName:
            losses.add("/base_id", UNRESOLVED_NAME,
                       "CatalogNaming.base_names has no PoB base type for this "
                       "base ID", item.base_id, True)
    if str(item.rarity).lower() in TITLED_RARITIES:
        lines.append(item.display_name)
        lines.append(base_line if base_line is not None else item.display_name)
    else:
        lines.append(base_line if base_line is not None else item.display_name)

    properties = dict(item.properties)
    runes = properties.pop("runes", None)
    variants = properties.pop("variants", None)
    selected_variant = properties.pop("selected_variant", None)
    if item.item_level is not None:
        lines.append("Item Level: %d" % item.item_level)
    for key, label in NUMERIC_PROPERTY_LINES.items():
        if key in properties:
            value = properties.pop(key)
            if not _is_number(value):
                losses.add("/properties/" + key, NOT_REPRESENTABLE,
                           "%s is written as a number" % label, value, True)
                continue
            lines.append("%s: %s" % (label, _format_number(value)))
    for key, label in TEXT_PROPERTY_LINES.items():
        if key in properties:
            lines.append("%s: %s" % (label, properties.pop(key)))
    for key, value in sorted(properties.items()):
        losses.add("/properties/" + key, NOT_REPRESENTABLE,
                   "PoB item text has no line for this property", value, True)

    socket_lines = _socket_lines(item, losses)
    lines.extend(socket_lines)
    for name in runes or ():
        lines.append("Rune: " + str(name))

    requirements = dict(item.requirements)
    if "level" in requirements:
        lines.append("LevelReq: %d" % requirements.pop("level"))
    for key, value in sorted(requirements.items()):
        losses.add("/requirements/" + key, NOT_REPRESENTABLE,
                   "PoB item text carries only the level requirement", value,
                   True)

    if variants:
        for name in variants:
            lines.append("Variant: " + str(name))
        if selected_variant is not None:
            lines.append("Selected Variant: %d" % int(selected_variant))
    elif selected_variant is not None:
        losses.add("/properties/selected_variant", NOT_REPRESENTABLE,
                   "a selected variant without a variant list has nothing to "
                   "select", selected_variant, True)

    ordered = list(item.modifiers)
    positions = [m.source_position for m in ordered]
    blocks = [_block_of(m.category) for m in ordered]
    if positions != list(range(len(ordered))) or blocks != sorted(blocks):
        losses.add("/modifiers", NOT_REPRESENTABLE,
                   "PoB writes the implicit block first and renumbers lines "
                   "from zero, so these source positions cannot be read back",
                   positions, True)
    implicit_count = sum(1 for m in ordered if _block_of(m.category) == 0)
    lines.append("Implicits: %d" % implicit_count)
    for index, modifier in enumerate(ordered):
        line = _modifier_line(modifier, losses, index)
        if line is not None:
            lines.append(line)

    for key, label in FLAG_LINES.items():
        if key in item.flags:
            if item.flags[key]:
                lines.append(label)
            else:
                losses.add("/flags/" + key, NOT_REPRESENTABLE,
                           "PoB writes only the positive line, so a flag "
                           "recorded false cannot be told from an absent one",
                           False, True)
    for key, value in sorted(item.flags.items()):
        if key not in FLAG_LINES:
            losses.add("/flags/" + key, NOT_REPRESENTABLE,
                       "PoB item text has no line for this flag", value, True)
    if item.source_document_id is not None:
        losses.add("/source_document_id", NOT_REPRESENTABLE,
                   "provenance is not part of a PoB document; identity "
                   "excludes it", item.source_document_id, False)
    return "\n".join(lines), losses


def _split_marker(line: str) -> tuple[dict[str, bool], list[int], str]:
    flags: dict[str, bool] = {}
    variants: list[int] = []
    rest = line
    while rest.startswith("{"):
        end = rest.find("}")
        if end < 0:
            break
        token = rest[1:end]
        rest = rest[end + 1:]
        if token.startswith("variant:"):
            variants = [source_int(part, "/text/{variant}")
                        for part in token.split(":", 1)[1].split(",")
                        if part.strip()]
        else:
            flags[token] = True
    return flags, variants, rest


def import_item(text: str, naming: CatalogNaming, *, record_id: str,
                created_at: str, catalog_hash: str,
                provenance_ids: Sequence[str] = (),
                source_document_id: str | None = None) -> ItemInstance:
    """Read PoB item text back into an ItemInstance.

    Only the document decides the result: nothing is carried over from the
    record the text was written from, so a round trip measures the document
    rather than the caller's memory of it.
    """
    from ..domain.identity import item_hash as _item_hash

    # PoB reads item text with "%s*([^\n]*%S)": blank lines are dropped and
    # each line is trimmed. A document indents the text inside its Item
    # element, so matching that is what makes PoB's own files readable.
    lines = [line.strip() for line in text.replace("\r\n", "\n").split("\n")]
    lines = [line for line in lines if line]
    if not lines:
        raise ValueError("empty item text")
    index = 0
    rarity = "unique"
    if lines[0].startswith("Rarity: "):
        rarity = lines[0][len("Rarity: "):].strip().lower()
        index = 1
    display_name = lines[index] if index < len(lines) else ""
    index += 1
    base_name: str | None = None
    if rarity in TITLED_RARITIES and index < len(lines):
        base_name = lines[index]
        index += 1
    else:
        base_name = display_name

    item_level: int | None = None
    properties: dict[str, Any] = {}
    requirements: dict[str, int] = {}
    sockets: list[Socket] = []
    flags: dict[str, bool] = {}
    variants: list[str] = []
    runes: list[str] = []
    selected_variant: int | None = None
    implicit_count = 0
    modifier_lines: list[str] = []

    numeric_by_label = {v: k for k, v in NUMERIC_PROPERTY_LINES.items()}
    text_by_label = {v: k for k, v in TEXT_PROPERTY_LINES.items()}
    flag_by_line = {v: k for k, v in FLAG_LINES.items()}

    known_labels = (
        {"Item Level", "LevelReq", "Sockets", "Implicits", "Variant",
         "Selected Variant", "Rune"}
        | set(numeric_by_label) | set(text_by_label) | set(INSTANCE_LINES))

    for line in lines[index:]:
        if line in flag_by_line:
            flags[flag_by_line[line]] = True
            continue
        label, separator, value = line.partition(": ")
        # A modifier line can contain a colon of its own, so only the declared
        # header labels are read as headers.
        if not separator or label not in known_labels:
            modifier_lines.append(line)
            continue
        if label in INSTANCE_LINES:
            continue
        if label == "Item Level":
            item_level = source_int(value, "/text/Item Level", minimum=0)
        elif label == "LevelReq":
            requirements["level"] = source_int(value, "/text/LevelReq", minimum=0)
        elif label == "Sockets":
            sockets = [Socket(socket_id=str(i), group=i, colour=letter,
                              contents_id=None)
                       for i, letter in enumerate(value.split())]
        elif label == "Implicits":
            implicit_count = source_int(value, "/text/Implicits", minimum=0)
        elif label == "Variant":
            variants.append(value)
        elif label == "Rune":
            runes.append(value)
        elif label == "Selected Variant":
            selected_variant = source_int(value, "/text/Selected Variant", minimum=1)
        elif label in numeric_by_label:
            properties[numeric_by_label[label]] = source_number(value, "/text/" + label)
        else:
            properties[text_by_label[label]] = value

    # PoB writes one ``Rune:`` line per socket, ``None`` for an empty one.
    # The rune's effect is in the ``{rune}`` modifier lines; the names are kept
    # only when a socket names a rune, so an all-empty list adds nothing.
    if any(name != "None" for name in runes):
        properties["runes"] = runes
    if variants:
        properties["variants"] = variants
        if selected_variant is not None:
            properties["selected_variant"] = selected_variant

    modifiers: list[ItemModifier] = []
    for position, raw in enumerate(modifier_lines):
        line_flags, variant_ids, body = _split_marker(raw)
        if line_flags.pop("rune", False):
            # PoB writes a rune line as ``{enchant}{rune}``: rune implies
            # enchant there, so the enchant marker is not a separate flag.
            line_flags.pop("enchant", None)
            category = ModifierCategory.RUNE
        elif line_flags.pop("enchant", False):
            category = ModifierCategory.ENCHANT
        elif line_flags.pop("fractured", False):
            category = ModifierCategory.FRACTURED
        elif line_flags.pop("crafted", False):
            category = ModifierCategory.CRAFTED
        elif line_flags.pop("desecrated", False):
            category = ModifierCategory.DESECRATED
        elif position < implicit_count:
            category = ModifierCategory.IMPLICIT
        else:
            category = ModifierCategory.EXPLICIT
        mod_flags = {name: True for name in line_flags}
        for variant_id in variant_ids:
            mod_flags["variant:%d" % variant_id] = True
        modifiers.append(ItemModifier(
            category=category, source_position=position, text=body,
            native_id=None, resolved_effect_ids=[], values=[],
            flags=mod_flags, parse_status=ModifierParseStatus.RESOLVED))

    base_id = None if base_name is None else base_id_for_name(
        base_name, rarity, naming)

    item = ItemInstance(
        schema_version=1, record_id=record_id, created_at=created_at,
        provenance_ids=list(provenance_ids), item_hash="",
        catalog_hash=catalog_hash, base_id=base_id,
        display_name=display_name, rarity=rarity, item_level=item_level,
        requirements=requirements, properties=properties, modifiers=modifiers,
        sockets=sockets, flags=flags, raw_text=text,
        source_document_id=source_document_id,
        parse_status=RecordParseStatus.COMPLETE)
    return _replace_hash(item, _item_hash(item))


def base_id_for_name(name: str, rarity: str,
                     naming: CatalogNaming) -> str | None:
    """The base for an item's base line, or None.

    A normal or magic item has no separate base line: its name carries the
    base, with a magic item's affixes around it. As PoB does, the longest
    base name inside it is taken; two bases of that length are ambiguous and
    resolve to nothing.
    """
    if name in naming.base_names.values():
        return naming.reverse("base_names", name)
    if rarity not in ("normal", "magic"):
        return None
    found = [(len(base), key) for key, base in naming.base_names.items()
             if base and base in name]
    if not found:
        return None
    longest = max(length for length, _ in found)
    keys = sorted({key for length, key in found if length == longest})
    return keys[0] if len(keys) == 1 else None


def _replace_hash(item: ItemInstance, value: str) -> ItemInstance:
    from dataclasses import replace
    return replace(item, item_hash=value)
