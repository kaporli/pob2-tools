"""Research finding F12, characterized from the handler source (P00-T04).

``pob2mcp/bootstrap.lua`` ``convert_trade_item`` normalizes seven modifier
arrays but only emits four of them into the item string it returns. The other
three - fractured, desecrated and crafted modifiers - are read, defaulted and
then dropped, so a converted item silently loses real affixes.

This file reads the handler source: it needs no Lua and no PoB.
``tests/integration/test_f12_item_conversion_luajit.py`` executes the handler to
show the loss on real output; ``tests/engine/test_f12_item_conversion_golden.py``
repeats it inside the pinned engine. The repair is P02-T05 ("Repair item
conversion where fields are omitted; preserve unsupported fields and report
them").
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

HANDLER = re.compile(
    r"handlers\.convert_trade_item\s*=\s*function\(args\)(.*?)\nend\n", re.S)
NORMALIZED = re.compile(r"item\.(\w+Mods)\s*=\s*item\.\1\s*or\s*\{\}")
EMITTED = re.compile(r"for\s+_,\s*modLine\s+in\s+ipairs\(item\.(\w+Mods)\)")

EXPECTED_DROPPED = {"fracturedMods", "desecratedMods", "craftedMods"}
EXPECTED_EMITTED = {"enchantMods", "runeMods", "implicitMods", "explicitMods"}


@pytest.fixture(scope="module")
def handler_source(repo_root: Path) -> str:
    text = (repo_root / "pob2-mcp" / "pob2mcp" / "bootstrap.lua").read_text(encoding="utf-8")
    match = HANDLER.search(text)
    assert match, "convert_trade_item not found in bootstrap.lua"
    return match.group(1)


# ------------------------------------------------------- current behaviour

def test_every_expected_modifier_array_is_normalized(handler_source: str):
    normalized = set(NORMALIZED.findall(handler_source))
    assert normalized == EXPECTED_EMITTED | EXPECTED_DROPPED


def test_three_normalized_modifier_arrays_are_never_emitted(handler_source: str):
    normalized = set(NORMALIZED.findall(handler_source))
    emitted = set(EMITTED.findall(handler_source))

    assert emitted == EXPECTED_EMITTED
    assert normalized - emitted == EXPECTED_DROPPED
    for dropped in EXPECTED_DROPPED:
        # The name appears exactly once: the line that defaults it to {}.
        assert handler_source.count("item." + dropped) == 2, dropped


def test_dropped_arrays_do_not_reach_the_implicit_count(handler_source: str):
    """The declared implicit count would also be wrong if they were appended."""
    counted = re.search(r'"Implicits: "\s*\.\.\s*\((.*?)\)', handler_source)
    assert counted, "implicit count expression not found"
    expression = counted.group(1)
    assert set(re.findall(r"#item\.(\w+Mods)", expression)) == {
        "enchantMods", "runeMods", "implicitMods"}


def test_no_unsupported_field_is_reported_to_the_caller(handler_source: str):
    """A dropped affix produces no warning, status or residual field."""
    assert "unsupported" not in handler_source.lower()
    assert "dropped" not in handler_source.lower()
    assert re.search(r"return\s*\{\s*item_string\s*=", handler_source)


def test_fixture_matches_the_arrays_the_handler_reads(fixtures_dir: Path,
                                                      handler_source: str):
    fixture = json.loads(
        (fixtures_dir / "trade" / "item_all_mod_categories.json").read_text(encoding="utf-8"))
    item = fixture["item"]
    normalized = set(NORMALIZED.findall(handler_source))

    assert normalized <= set(item), "fixture is missing a modifier array the handler reads"
    assert set(fixture["emitted_by_current_code"]) == EXPECTED_EMITTED
    assert set(fixture["normalized_but_dropped_by_current_code"]) == EXPECTED_DROPPED


# ------------------------------------------------------- repaired behaviour

@pytest.mark.xfail(
    strict=True,
    reason="F12 repair is P02-T05: every normalized modifier category must be "
           "emitted, or explicitly reported as unsupported.",
)
def test_repaired_handler_emits_every_normalized_modifier_array(handler_source: str):
    normalized = set(NORMALIZED.findall(handler_source))
    emitted = set(EMITTED.findall(handler_source))
    assert normalized - emitted == set()
