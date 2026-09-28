"""MCP server exposing the Path of Building 2 calculation engine, GGG character
import, and the PoE2 trade API.

Run:  python -m pob2mcp.server
Register with Claude Code:
  claude mcp add pob2 -- python -m pob2mcp.server
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
from .poe_api import PoeApi
from .trade import Trade2Client

mcp = MCPServer("pob2")

_engine: Pob2Engine | None = None
_poe_api: PoeApi | None = None
_trade: Trade2Client | None = None


def engine() -> Pob2Engine:
    global _engine
    if _engine is None:
        _engine = Pob2Engine()
        _engine.call("new_build")
    return _engine


def poe_api() -> PoeApi:
    global _poe_api
    if _poe_api is None:
        _poe_api = PoeApi()
    return _poe_api


def trade() -> Trade2Client:
    global _trade
    if _trade is None:
        _trade = Trade2Client()
    return _trade


# ------------------------------------------------------------------ account


@mcp.tool()
def authenticate_poe() -> str:
    """Authenticate with pathofexile.com (opens the user's browser for OAuth).
    Needed once before list_characters/import_character; the token is cached."""
    return poe_api().authenticate()


@mcp.tool()
def list_characters() -> list[dict]:
    """List the authenticated account's PoE2 characters (name, class, level, league)."""
    chars = poe_api().list_characters()
    return [
        {
            "name": c.get("name"),
            "class": c.get("class"),
            "level": c.get("level"),
            "league": c.get("league"),
        }
        for c in chars
    ]


@mcp.tool()
def import_character(name: str) -> dict:
    """Import a PoE2 character (items, skills, passive tree, level) into the
    Path of Building engine and return a build summary. After importing, use
    get_skills + set_main_skill to select the damage skill, then get_stats."""
    char = poe_api().get_character(name)
    return engine().call("import_character", {"character": char})


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
    """List current PoE2 trade leagues."""
    return trade().leagues()


@mcp.tool()
def trade_search(league: str, query: dict, max_results: int = 10) -> list[dict]:
    """Search the PoE2 trade site. `query` is a full trade2 API body:
    {"query": {"status": {"option": "online"}, "stats": [...], "filters": {...}},
     "sort": {"price": "asc"}}.
    Returns listings with price and PoB-format item text (usable with test_item
    / equip_item)."""
    result = trade().search(league, query)
    hashes = result.get("result", [])[:max_results]
    if not hashes:
        return []
    listings = trade().fetch(hashes, result["id"])
    out = []
    for entry in listings:
        converted = engine().call("convert_trade_item", {"item": entry["item"]})
        price = entry.get("listing", {}).get("price") or {}
        out.append(
            {
                "id": entry.get("id"),
                "price_amount": price.get("amount"),
                "price_currency": price.get("currency"),
                "seller": entry.get("listing", {}).get("account", {}).get("name"),
                "whisper": entry.get("listing", {}).get("whisper"),
                "item_text": converted["item_string"],
            }
        )
    return out


@mcp.tool()
def trade_evaluate(
    league: str,
    query: dict,
    slot: str,
    max_results: int = 10,
    sort_stat: str = "CombinedDPS",
) -> list[dict]:
    """Search trade, then evaluate every result in the PoB engine as if equipped
    in `slot`, WITHOUT modifying the build. Returns listings ranked by the delta
    of `sort_stat` (any PoB output key, e.g. CombinedDPS, FullDPS, TotalEHP),
    with price. This is the main tool for finding best-upgrade-per-cost."""
    listings = trade_search(league, query, max_results)
    evaluated = []
    for listing in listings:
        try:
            diff = engine().call(
                "test_item", {"raw": listing["item_text"], "slot": slot}
            )
        except PobEngineError as exc:
            listing["error"] = str(exc)
            evaluated.append(listing)
            continue
        listing["stat_diff"] = diff["diff"]
        stat = diff["diff"].get(sort_stat)
        listing["sort_delta"] = stat["delta"] if stat else 0
        evaluated.append(listing)
    evaluated.sort(key=lambda x: x.get("sort_delta", 0), reverse=True)
    return evaluated


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
