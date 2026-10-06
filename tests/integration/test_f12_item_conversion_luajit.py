"""Research finding F12 and its repair, executed (P00-T04, P02-T05).

Runs the real ``convert_trade_item`` handler from ``pob2mcp/bootstrap.lua``
under a stock LuaJIT and inspects the item string it produces. The handler is
pure string assembly over the table it is handed, so the two PoB globals it
touches (``escapeGGGString`` and ``dkjson``) are stubbed by
``lua/convert_probe.lua``.

The characterization here was that three normalized modifier categories never
reached the output. P02-T05 repaired that, so the assertions were migrated:
"fractured, desecrated and crafted are lost" is now "they are written with
PoB's own markers", and "nothing hints that anything was discarded" is now
"the handler reports what it could not place". The reason is written here
rather than in a deleted file.

Scope of this evidence: it shows which lines the handler produces. It is NOT
evidence about the pinned PoB engine or about how PoB parses the resulting
string - that is ``tests/engine/test_f12_item_conversion_golden.py``.

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

#: Categories the original handler dropped, with the marker PoB writes.
REPAIRED_CATEGORIES = (("fractured", "{fractured}"),
                       ("desecrated", "{desecrated}"),
                       ("crafted", "{crafted}"))
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


def run_probe(repo_root: Path, item: dict, tmp_path: Path, mode=None) -> str:
    item_lua = tmp_path / "item_table.lua"
    item_lua.write_text("return " + to_lua(item) + "\n", encoding="utf-8")
    probe = repo_root / "tests" / "integration" / "lua" / "convert_probe.lua"
    bootstrap = repo_root / "pob2-mcp" / "pob2mcp" / "bootstrap.lua"
    command = [LUAJIT, str(probe), str(bootstrap), str(item_lua)]
    if mode is not None:
        command.append(mode)
    proc = subprocess.run(command, capture_output=True, text=True, timeout=60)
    assert proc.returncode == 0, proc.stderr
    return proc.stdout


@pytest.fixture(scope="module")
def converted(repo_root: Path, fixture_item: dict, tmp_path_factory) -> str:
    return run_probe(repo_root, fixture_item, tmp_path_factory.mktemp("f12"))


@pytest.fixture(scope="module")
def report(repo_root: Path, fixture_item: dict, tmp_path_factory) -> str:
    return run_probe(repo_root, fixture_item,
                     tmp_path_factory.mktemp("f12-report"), mode="report")


# ------------------------------------------------------- repaired behaviour

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


def test_fractured_desecrated_and_crafted_modifiers_are_preserved(converted: str):
    """Was the F12 characterization: the three categories vanished silently."""
    for category, marker in REPAIRED_CATEGORIES:
        line = marker + "FIXTUREMOD %s line one" % category
        assert line in converted.splitlines(), line


def test_the_repaired_categories_sit_after_the_implicit_block(converted: str):
    """PoB reads the lines after ``Implicits: N`` as explicit-area lines."""
    lines = converted.splitlines()
    first_explicit = lines.index("FIXTUREMOD explicit line one")
    for category, marker in REPAIRED_CATEGORIES:
        assert lines.index(marker + "FIXTUREMOD %s line one" % category) > first_explicit


def test_implicit_count_matches_only_the_emitted_implicit_categories(converted: str):
    count_line = next(l for l in converted.splitlines() if l.startswith("Implicits: "))
    assert count_line == "Implicits: 3"  # 1 enchant + 1 rune + 1 implicit


def test_conversion_does_not_mutate_the_fixture_on_disk(fixtures_dir: Path, converted: str):
    payload = json.loads(
        (fixtures_dir / "trade" / "item_all_mod_categories.json").read_text(encoding="utf-8"))
    assert payload["item"]["craftedMods"] == [{"description": "FIXTUREMOD crafted line one"}]


def test_the_handler_reports_what_it_emitted(report: str):
    lines = report.splitlines()
    assert "complete=true" in lines
    for array in ("enchantMods", "runeMods", "implicitMods", "fracturedMods",
                  "desecratedMods", "craftedMods"):
        assert "emitted %s=1" % array in lines, array
    assert "emitted explicitMods=2" in lines


def test_an_unknown_item_field_is_reported_rather_than_dropped(
        repo_root: Path, fixture_item: dict, tmp_path: Path):
    """Was: a dropped field left no trace at all."""
    extended = dict(fixture_item, scourgeMods=[{"description": "FIXTUREMOD scourge"}],
                    note="~price 1 exalted")
    report = run_probe(repo_root, extended, tmp_path, mode="report")
    lines = report.splitlines()
    assert "complete=false" in lines
    assert "unsupported scourgeMods" in lines
    assert "unsupported note" in lines


def test_repaired_conversion_preserves_every_modifier_category(converted: str):
    """Was an xfail naming P02-T05. The repair makes it a pass."""
    for category, _marker in REPAIRED_CATEGORIES:
        assert "FIXTUREMOD %s line one" % category in converted, category
