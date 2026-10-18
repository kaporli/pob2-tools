"""P02-T03.1 parser `.6`: real item lines that `.5` misread or left unknown.

* PoB's `Unique ID:` line is a per-copy header, not a modifier; read as a
  modifier it shifted every item's implicit block by one line.
* `Runic Ward:` is a property line.
* A line no single affix explains, whose text is a catalog modifier's and
  whose value is within what those modifiers sum to, is `stat_resolved`. The
  item stays partial (P04 review R2); the pool may place it, marked.
"""

from __future__ import annotations

from dataclasses import replace

import p04_fixtures as fx
from pob2opt.domain.enums import ModifierCategory, ModifierParseStatus, RecordParseStatus
from pob2opt.evaluation.itemtext import import_item
from pob2opt.evaluation.naming import CatalogNaming
from pob2opt.market.pools import stat_known
from pob2opt.parsers import resolve_item_modifiers
from pob2opt.parsers import parse_document
from pob2opt.parsers.pob import PARSER_VERSION
from pob2opt.market.importer import IMPORTER_VERSION

HEADER = "\n".join([
    "Rarity: RARE",
    "Fixture Braid",
    "Absent Amulet",
    "Unique ID: 15e795124bfd749ea423d17561c0b99128a961f537a737e2cff577db4a8eea94",
    "Runic Ward: 105",
    "Item Level: 81",
    "LevelReq: 50",
    "Implicits: 1",
    "Grants Skill: Level 18 Trinity",
    "+50 to Spirit",
])


def test_versions_are_bumped():
    assert PARSER_VERSION == "p04-t01.6"
    assert IMPORTER_VERSION == "p05-t02.2"


def _parse(text):
    naming = CatalogNaming(
        base_names={"poe2/item_bases/Absent Amulet": "Absent Amulet"})
    return import_item(text, naming, record_id="item/x",
                       created_at="2026-10-18T00:00:00Z", catalog_hash="c" * 64)


def test_unique_id_is_a_dropped_header_and_the_implicit_block_holds():
    item = _parse(HEADER)
    texts = [(m.category, m.text) for m in item.modifiers]
    assert all("Unique ID" not in text for _, text in texts)
    assert texts == [(ModifierCategory.IMPLICIT, "Grants Skill: Level 18 Trinity"),
                     (ModifierCategory.EXPLICIT, "+50 to Spirit")]
    assert item.properties.get("runic_ward") == 105


def _rare_with_exclusive_clone(value_factor):
    item = next(i for i in parse_document(
        fx.source(fx.document_bytes("b01")), fx.document_bytes("b01"),
        fx.context()).items if i.rarity == "rare")
    _, matches = resolve_item_modifiers(item, fx.entities())
    entity = next(e for e in fx.entities()["item_modifiers"]
                  if e.entity_id == matches[0].candidates[0])
    line = entity.raw_reference["lines"][0]
    import re
    number = re.search(r"\d+", item.modifiers[0].text).group(0)
    # SYNTHETIC: a non-affix catalog line of the same text with a high range,
    # standing in for a unique or corrupted modifier of the same stat.
    exclusive = replace(entity, entity_id=entity.entity_id + "-exclusive",
                        raw_reference={**entity.raw_reference, "type": "Exclusive",
                                       "lines": [re.sub(r"\(\d+-\d+\)|\d+",
                                                        "(1000-2000)", line,
                                                        count=1)]})
    entities = dict(fx.entities())
    entities["item_modifiers"] = list(entities["item_modifiers"]) + [exclusive]
    text = item.modifiers[0].text.replace(number, str(value_factor), 1)
    changed = replace(item, modifiers=[replace(item.modifiers[0], text=text)]
                      + list(item.modifiers[1:]))
    return resolve_item_modifiers(changed, entities)


def test_a_value_only_a_sum_of_catalog_lines_reaches_is_stat_resolved():
    resolved, matches = _rare_with_exclusive_clone(1500)
    assert matches[0].status == "stat_resolved"
    assert matches[0].candidates == ()
    assert resolved.parse_status is RecordParseStatus.PARTIAL
    assert stat_known(resolved)


def test_a_value_beyond_every_sum_stays_unresolved():
    resolved, matches = _rare_with_exclusive_clone(999999)
    assert matches[0].status == "unresolved"
    assert not stat_known(resolved)

