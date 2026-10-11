"""MCP server exposing the Path of Building 2 calculation engine.

Run:  python -m pob2mcp.server
Register with Claude Code:
  claude mcp add pob2 -- python -m pob2mcp.server

GGG character import and the PoE2 trade tools are quarantined: they are
registered, they are documented, and they refuse before touching the network.
See ``quarantine.py`` for why and for what would restore them. Everything the
engine does locally is unaffected.
"""

from __future__ import annotations

import base64
import json
import os
import sys
import zlib
from typing import Any

from mcp.server.mcpserver import MCPServer

from .engine import Pob2Engine, PobEngineError
from .quarantine import QUARANTINED, CapabilityUnavailable, refuse

mcp = MCPServer("pob2")

_engine: Pob2Engine | None = None


def engine() -> Pob2Engine:
    global _engine
    if _engine is None:
        _engine = Pob2Engine()
        _engine.call("new_build")
    return _engine


def poe_api():
    """Quarantined. Refuses before constructing the legacy account client.

    This module no longer imports ``.poe_api`` at all, so a default server
    process never loads the module holding the borrowed OAuth client id, let
    alone reads a cached token.
    """
    raise refuse("authenticate_poe")


def trade():
    """Quarantined. Refuses before constructing the legacy trade client.

    ``.trade`` is likewise not imported, so no ``POESESSID`` cookie is read.
    """
    raise refuse("trade_search")


# ------------------------------------------------------------------ account


@mcp.tool()
def authenticate_poe() -> str:
    """UNAVAILABLE. Authenticating here would use Path of Building's own
    registered OAuth client, which belongs to another project. This project has
    no registered client id yet, so the operation refuses immediately."""
    raise refuse("authenticate_poe")


@mcp.tool()
def list_characters() -> list[dict]:
    """UNAVAILABLE. Listing the account's characters needs the account API,
    which needs the borrowed OAuth identity above."""
    raise refuse("list_characters")


@mcp.tool()
def import_character(name: str) -> dict:
    """UNAVAILABLE. Importing from the account needs the account API, which
    needs the borrowed OAuth identity above.

    Local import still works: `import_build_code` takes a Path of Building
    share code, and the engine's own import path is unchanged."""
    raise refuse("import_character")


# ------------------------------------------------------------------- build


@mcp.tool()
def new_build() -> dict:
    """Reset the engine to an empty build."""
    return engine().call("new_build")


@mcp.tool()
def import_build_code(code: str) -> dict:
    """Load a Path of Building 2 build share code (base64 string, e.g. from
    pobb.in or the game community) into the engine."""
    xml = zlib.decompress(base64.b64decode(code.strip().replace("-", "+").replace("_", "/")))
    return engine().call("load_build_xml", {"xml": xml.decode("utf-8")})


@mcp.tool()
def export_build_code() -> str:
    """Export the current build as a PoB2 share code the user can paste into
    Path of Building 2 (Import/Export Build > Import from code)."""
    xml = engine().call("save_build_xml")["xml"]
    code = base64.b64encode(zlib.compress(xml.encode("utf-8"), 9)).decode()
    return code.replace("+", "-").replace("/", "_")


@mcp.tool()
def get_build_info() -> dict:
    """Summary of the current build: class, ascendancy, level, points used, main skill."""
    return engine().call("get_build_info")


@mcp.tool()
def get_stats(keys: list[str] | None = None, all: bool = False) -> dict:
    """Calculated character stats (DPS, life, resists, EHP...). Default returns a
    curated set; pass keys for specific ones or all=true for every scalar output
    (large). Key names follow PoB's internal output table, e.g. TotalDPS,
    CombinedDPS, FullDPS, Life, TotalEHP, FireResist."""
    return engine().call("get_stats", {"keys": keys, "all": all})


@mcp.tool()
def set_level(level: int) -> dict:
    """Set the character level (affects base life/mana and stat requirements)."""
    return engine().call("set_level", {"level": level})


# ------------------------------------------------------------------ skills


@mcp.tool()
def get_skills() -> dict:
    """List socket groups, their gems and active skills, and which is the main
    (DPS) skill. Group/skill indices are used by set_main_skill."""
    return engine().call("get_skills")


@mcp.tool()
def set_main_skill(group: int, skill: int | None = None) -> dict:
    """Select the socket group (and optionally which active skill in it) whose
    DPS the calculations should report."""
    return engine().call("set_main_skill", {"group": group, "skill": skill})


# ------------------------------------------------------------------- items


@mcp.tool()
def get_items(include_raw: bool = False) -> dict:
    """Equipped items by slot name. include_raw adds each item's full text."""
    return engine().call("get_items", {"raw": include_raw})


@mcp.tool()
def equip_item(item_text: str, slot: str | None = None) -> dict:
    """Add an item (PoB/game copy-paste text format) to the build and equip it.
    If slot is omitted PoB auto-equips it into its natural slot. Returns the new
    stats so you can see the effect."""
    return engine().call("equip_item", {"raw": item_text, "slot": slot})


@mcp.tool()
def test_item(item_text: str, slot: str, keys: list[str] | None = None) -> dict:
    """Non-destructively evaluate an item: computes stat deltas as if it were
    equipped in the given slot (e.g. 'Weapon 1', 'Body Armour', 'Ring 1')
    WITHOUT modifying the build. Ideal for comparing trade candidates."""
    return engine().call("test_item", {"raw": item_text, "slot": slot, "keys": keys})


# -------------------------------------------------------------------- tree


@mcp.tool()
def get_tree(include_nodes: bool = False) -> dict:
    """Passive tree summary; include_nodes lists every allocated node."""
    result = engine().call("get_tree")
    if not include_nodes:
        result = {k: v for k, v in result.items() if k != "allocated"}
    return result


@mcp.tool()
def search_passives(text: str, limit: int = 50) -> list[dict]:
    """Search passive tree nodes by name or stat text. Returns node ids, whether
    they're allocated, and path distance from the current tree."""
    return engine().call("search_nodes", {"text": text, "limit": limit})


@mcp.tool()
def alloc_passives(node_ids: list[int]) -> dict:
    """Allocate passive tree nodes by id (paths to them are allocated too).
    Returns new points used and stats."""
    return engine().call("alloc_nodes", {"ids": node_ids})


@mcp.tool()
def dealloc_passives(node_ids: list[int]) -> dict:
    """Deallocate passive tree nodes by id. Returns new points used and stats."""
    return engine().call("dealloc_nodes", {"ids": node_ids})


# ------------------------------------------------------------------ config


@mcp.tool()
def get_config() -> dict:
    """Current calculation config (enemy type, buffs active, etc.)."""
    return engine().call("get_config")


@mcp.tool()
def set_config(name: str, value: Any) -> dict:
    """Set a calculation config option, e.g. ('enemyIsBoss', 'Pinnacle'),
    ('conditionEnemyShocked', true), ('multiplierGrievousWounds', 3)."""
    return engine().call("set_config", {"name": name, "value": value})


# ------------------------------------------------------------------- trade


@mcp.tool()
def trade_leagues() -> list[dict]:
    """UNAVAILABLE. The trade2 endpoints are undocumented and live market
    access is recorded as unsupported."""
    raise refuse("trade_leagues")


@mcp.tool()
def trade_search(league: str, query: dict, max_results: int = 10) -> list[dict]:
    """UNAVAILABLE. There is no documented PoE 2 item listing route, the
    trade2 endpoints this used are undocumented, and a POESESSID cookie is a
    website credential rather than an application one.

    The request body this took was a full trade2 API body
    ({"query": {"status": ..., "stats": [...], "filters": {...}},
    "sort": {"price": "asc"}}), and the conversion from a listing to
    PoB item text is `convert_trade_item` in the engine. Both are kept here
    and in `trade.py` because they are the reusable knowledge; neither is
    reachable from this surface."""
    raise refuse("trade_search")


@mcp.tool()
def trade_evaluate(
    league: str,
    query: dict,
    slot: str,
    max_results: int = 10,
    sort_stat: str = "CombinedDPS",
) -> list[dict]:
    """UNAVAILABLE. This was trade_search followed by an engine evaluation, so
    it inherits that refusal.

    Evaluating an item you already have the text of is unaffected: `test_item`
    takes the item text and a slot and returns the stat delta without
    modifying the build."""
    raise refuse("trade_evaluate")


# -------------------------------------------------------------------- misc


@mcp.tool()
def eval_lua(code: str) -> Any:
    """Escape hatch: run arbitrary Lua inside the PoB2 engine and return the
    result (must be JSON-encodable). The loaded build is the global `build`;
    recalc with: build.buildFlag = true; runCallback("OnFrame")."""
    return engine().eval_lua(code)


def main() -> None:
    # The Lua engine printf-spams the C-level stdout, which would corrupt the
    # MCP stdio protocol. Hand the real stdout to Python only, and point fd 1
    # (shared by the Lua DLL through the UCRT) at stderr.
    real_stdout = os.dup(1)
    os.dup2(2, 1)
    sys.stdout = os.fdopen(real_stdout, "w", encoding="utf-8", buffering=1)
    mcp.run()


if __name__ == "__main__":
    main()
