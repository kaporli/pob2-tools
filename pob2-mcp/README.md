# pob2-mcp

MCP server that gives Claude full access to the **Path of Building 2**
calculation engine: load a build, evaluate it, compare items against it and
export the result.

The account import and trade tools are **quarantined**. They are still
registered and still documented, and they refuse before touching the network.
See "Quarantined tools" below.

## How it works

- Loads PoB2's own patched LuaJIT (`runtime/lua51.dll`, stock LuaJIT cannot
  parse PoB2's `??` operator) into the Python process via ctypes and boots
  `HeadlessWrapper.lua`. Full calc engine, no GUI.
- Builds come in locally: `import_build_code` takes a Path of Building share
  code, and `equip_item` and `test_item` take item text.

## Setup

```
pip install -e .
claude mcp add pob2 --scope user -- python -m pob2mcp.server
```

Requires a checkout of
[PathOfBuilding-PoE2](https://github.com/PathOfBuildingCommunity/PathOfBuilding-PoE2)
at `C:\Users\Elias\PycharmProjects\PathOfBuilding-PoE2` (override with the
`POB2_ROOT` env var). Update it with `git pull` to track new game patches.

## Tools

| Area | Tools |
|---|---|
| Build | `new_build`, `import_build_code`, `export_build_code`, `get_build_info`, `get_stats`, `set_level` |
| Skills | `get_skills`, `set_main_skill` |
| Items | `get_items`, `equip_item`, `test_item` (non-destructive compare) |
| Tree | `get_tree`, `search_passives`, `alloc_passives`, `dealloc_passives` |
| Config | `get_config`, `set_config` |
| Escape hatch | `eval_lua` (arbitrary Lua inside the engine) |

Typical upgrade-hunt flow:
`import_build_code` -> `set_main_skill` -> per slot: `test_item(item_text,
slot)` for each candidate you already have the text of -> `equip_item` the
winners -> `export_build_code` to load the result in PoB2.

## Quarantined tools

| Area | Tools | Why |
|---|---|---|
| Account | `authenticate_poe`, `list_characters`, `import_character` | OAuth here authenticates as Path of Building's registered client, which belongs to another project. This project has no registered client id. |
| Trade | `trade_leagues`, `trade_search`, `trade_evaluate` | The `/api/trade2/*` endpoints are undocumented, there is no documented PoE 2 item listing route, and a `POESESSID` cookie is a website credential rather than an application one. |

Each raises an explicit capability error before any network request, token
read or cookie read. The server does not import `poe_api.py` or `trade.py` at
all, so a default process never loads the module holding the borrowed client
id.

There is no environment variable or flag that lifts this. The condition for
restoring these paths is a project-owned route that has been separately
approved, which is not something a local setting can assert.

`poe_api.py` and `trade.py` stay in the tree: they hold the endpoint knowledge
and the listing-to-PoB-item conversion, which remain useful. No cached token
and no user file is deleted or touched.

Recorded in `docs/decisions/D01-trade-access.md` and
`docs/reviews/P05-T01.md`. Checked by
`tests/unit/test_p05_legacy_quarantine.py`.

## Development

`python test_engine.py` smoke-tests the engine layer (no MCP, no auth needed).
