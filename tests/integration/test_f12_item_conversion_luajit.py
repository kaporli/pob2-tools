"""Research finding F12, executed (P00-T04).

Runs the real ``convert_trade_item`` handler from ``pob2mcp/bootstrap.lua`` under
a stock LuaJIT and inspects the item string it produces. The handler is pure
string assembly over the table it is handed, so the two PoB globals it touches
(``escapeGGGString`` and ``dkjson``) are stubbed by ``lua/convert_probe.lua``.

Scope of this evidence: it shows that three normalized modifier categories never
reach the output. It is NOT evidence about the pinned PoB engine or about how
PoB would parse the resulting string - that is
``tests/engine/test_f12_item_conversion_golden.py``.

Skips with a reason when no ``luajit`` is on PATH.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

LUAJIT = shutil.which("luajit") or shutil.which("lua51") or shutil.which("lua")

pytestmark = pytest.mark.skipif(
    LUAJIT is None,
    reason="no luajit/lua interpreter on PATH; this probe runs the handler source directly",
)

DROPPED_CATEGORIES = ("fractured", "desecrated", "crafted")
EMITTED_CATEGORIES = ("enchant", "rune", "implicit", "explicit")


def to_lua(value) -> str:
    """Serialize JSON-ish Python data as a Lua literal.

    Keeps the fixture in JSON (one source of truth) while letting the probe stay
    free of a Lua JSON decoder.
    """
    if isinstance(value, bool):
        return "true" if value else "false"
    if value is None:
        return "nil"
    if isinstance(value, (int, float)):
        return repr(value)
    if isinstance(value, str):
        return '"' + value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n") + '"'
    if isinstance(value, list):
        return "{" + ", ".join(to_lua(v) for v in value) + "}"
    if isinstance(value, dict):
        return "{" + ", ".join(
            "[%s] = %s" % (to_lua(k), to_lua(v)) for k, v in value.items()) + "}"
    raise TypeError(type(value))


@pytest.fixture(scope="module")
def fixture_item(fixtures_dir: Path) -> dict:
    payload = json.loads(
        (fixtures_dir / "trade" / "item_all_mod_categories.json").read_text(encoding="utf-8"))
    return payload["item"]


@pytest.fixture(scope="module")
def converted(repo_root: Path, fixture_item: dict, tmp_path_factory) -> str:
    tmp = tmp_path_factory.mktemp("f12")
    item_lua = tmp / "item_table.lua"
    item_lua.write_text("return " + to_lua(fixture_item) + "\n", encoding="utf-8")

    probe = repo_root / "tests" / "integration" / "lua" / "convert_probe.lua"
    bootstrap = repo_root / "pob2-mcp" / "pob2mcp" / "bootstrap.lua"
    proc = subprocess.run(
        [LUAJIT, str(probe), str(bootstrap), str(item_lua)],
        capture_output=True, text=True, timeout=60,
    )
    assert proc.returncode == 0, proc.stderr
    return proc.stdout


# ------------------------------------------------------- current behaviour

def test_the_probe_reproduces_the_supported_categories(converted: str):
    for category in EMITTED_CATEGORIES:
        assert "FIXTUREMOD %s line one" % category in converted, category
    assert "FIXTUREMOD explicit line two" in converted


def test_header_fields_survive_conversion(converted: str):
    lines = converted.splitlines()
    assert lines[0] == "Rarity: Rare"
    assert lines[1] == "FIXTURE Mod Category Probe"
    assert lines[2] == "Long Quarterstaff"
    assert "Item Level: 82" in lines
    assert "Quality: 20" in lines
    assert "LevelReq: 65" in lines


def test_fractured_desecrated_and_crafted_modifiers_are_lost(converted: str):
    """CURRENT behaviour (F12): three real affix categories vanish silently."""
    for category in DROPPED_CATEGORIES:
        assert "FIXTUREMOD %s line one" % category not in converted, category
    # Nothing in the output hints that anything was discarded.
    assert "unsupported" not in converted.lower()
    assert "dropped" not in converted.lower()


def test_implicit_count_matches_only_the_emitted_implicit_categories(converted: str):
    count_line = next(l for l in converted.splitlines() if l.startswith("Implicits: "))
    assert count_line == "Implicits: 3"  # 1 enchant + 1 rune + 1 implicit


def test_conversion_does_not_mutate_the_fixture_on_disk(fixtures_dir: Path, converted: str):
    payload = json.loads(
        (fixtures_dir / "trade" / "item_all_mod_categories.json").read_text(encoding="utf-8"))
    assert payload["item"]["craftedMods"] == [{"description": "FIXTUREMOD crafted line one"}]


# ------------------------------------------------------- repaired behaviour

@pytest.mark.xfail(
    strict=True,
    reason="F12 repair is P02-T05: fractured, desecrated and crafted modifiers "
           "must be preserved in the converted item, or reported as unsupported.",
)
def test_repaired_conversion_preserves_every_modifier_category(converted: str):
    for category in DROPPED_CATEGORIES:
        assert "FIXTUREMOD %s line one" % category in converted, category
