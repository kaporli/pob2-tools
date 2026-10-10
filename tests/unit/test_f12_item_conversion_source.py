"""Research finding F12 and its repair (P00-T04 characterization, P02-T05 fix).

``pob2mcp/bootstrap.lua`` ``convert_trade_item`` used to read seven modifier
arrays and emit four of them. Fractured, desecrated and crafted modifiers were
defaulted to ``{}`` and never referenced again, so a converted item lost real
affixes and nothing said so.

P02-T05 repaired the handler: every array it reads is emitted, with the same
markers PoB's own ``Item:BuildRaw`` writes, and the result carries a
completeness report. The assertions that pinned the loss were migrated rather
than deleted, because the previous behaviour is the defect:

* "three arrays are never emitted" became "every array read is emitted";
* "nothing is reported to the caller" became "the result names what it could
  not place";
* the implicit count is unchanged and still counts only the three
  implicit-like categories, which is correct: PoB reads the lines after
  ``Implicits: N`` as explicits, which is where the other four belong.

This file reads the handler source: it needs no Lua and no PoB.
``tests/integration/test_f12_item_conversion_luajit.py`` executes the handler
to show the repair on real output; ``tests/engine/test_f12_item_conversion_golden.py``
repeats it inside the pinned engine.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

HANDLER = re.compile(
    r"handlers\.convert_trade_item\s*=\s*function\(args\)(.*?)\nend\n", re.S)
#: Every modifier array the handler reads, however it reads it.
READ = re.compile(r"item\.(\w+Mods)")
#: Every modifier array the handler writes a line for. The repaired handler
#: reads each one with ``or {}`` at the point of use, so it never writes a
#: default back into the caller's table.
EMITTED = re.compile(r"for\s+_,\s*modLine\s+in\s+ipairs\(item\.(\w+Mods)\s*or\s*\{\}\)")
MUTATED = re.compile(r"item\.(\w+Mods)\s*=")

#: Categories the original handler dropped. They are emitted now.
REPAIRED_CATEGORIES = {"fracturedMods", "desecratedMods", "craftedMods"}
ALWAYS_EMITTED = {"enchantMods", "runeMods", "implicitMods", "explicitMods"}
EVERY_CATEGORY = ALWAYS_EMITTED | REPAIRED_CATEGORIES


@pytest.fixture(scope="module")
def handler_source(repo_root: Path) -> str:
    text = (repo_root / "pob2-mcp" / "pob2mcp" / "bootstrap.lua").read_text(encoding="utf-8")
    match = HANDLER.search(text)
    assert match, "convert_trade_item not found in bootstrap.lua"
    return match.group(1)


# ------------------------------------------------------- repaired behaviour

def test_every_expected_modifier_array_is_read(handler_source: str):
    assert set(READ.findall(handler_source)) == EVERY_CATEGORY


def test_the_handler_does_not_write_into_the_caller_item(handler_source: str):
    """The seven ``item.xMods = item.xMods or {}`` defaults are gone."""
    assert MUTATED.findall(handler_source) == []


def test_dropped_arrays_do_not_reach_the_implicit_count(handler_source: str):
    """Unchanged by the repair, and still correct.

    ``Implicits: N`` tells PoB how many of the following lines are implicit.
    The four explicit-area categories must not be counted, or PoB would read
    explicits as implicits.
    """
    counted = re.search(r'"Implicits: "\s*\.\.\s*\((.*?)\)\)', handler_source)
    assert counted, "implicit count expression not found"
    expression = counted.group(1)
    assert set(re.findall(r"#\(item\.(\w+Mods)", expression)) == {
        "enchantMods", "runeMods", "implicitMods"}


def test_each_repaired_category_is_written_with_its_pob_marker(handler_source: str):
    """The markers are the ones PoB's own Item:BuildRaw writes."""
    for array, marker in (("fracturedMods", "{fractured}"),
                          ("desecratedMods", "{desecrated}"),
                          ("craftedMods", "{crafted}")):
        line = re.search(
            r"for\s+_,\s*modLine\s+in\s+ipairs\(item\.%s\s*or\s*\{\}\)(.*)" % array,
            handler_source)
        assert line, array
        assert marker in line.group(1), array


def test_unsupported_fields_are_reported_to_the_caller(handler_source: str):
    """Was: a dropped affix produced no warning, status or residual field."""
    assert re.search(r"return\s*\{\s*item_string\s*=", handler_source)
    assert "unsupported = unsupported" in handler_source
    assert "complete = #unsupported == 0" in handler_source
    assert "emitted_mod_counts = emitted" in handler_source


def test_fixture_matches_the_arrays_the_handler_reads(fixtures_dir: Path,
                                                      handler_source: str):
    fixture = json.loads(
        (fixtures_dir / "trade" / "item_all_mod_categories.json").read_text(encoding="utf-8"))
    item = fixture["item"]
    read = set(READ.findall(handler_source))

    assert read <= set(item), "fixture is missing a modifier array the handler reads"
    assert set(fixture["emitted_by_current_code"]) == ALWAYS_EMITTED
    assert set(fixture["normalized_but_dropped_by_current_code"]) == REPAIRED_CATEGORIES


def test_repaired_handler_emits_every_normalized_modifier_array(handler_source: str):
    """Was an xfail naming P02-T05. The repair makes it a pass."""
    read = set(READ.findall(handler_source))
    emitted = set(EMITTED.findall(handler_source))
    assert emitted == EVERY_CATEGORY
    assert read - emitted == set()
