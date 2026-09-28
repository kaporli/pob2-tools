# pob2-mcp

MCP server that gives Claude full access to the **Path of Building 2** calculation
engine, official GGG character import, and the PoE2 trade API — so it can import
your character, evaluate real trade listings against your actual build, and
optimize DPS under a budget.

## How it works

- Loads PoB2's own patched LuaJIT (`runtime/lua51.dll` — stock LuaJIT cannot
  parse PoB2's `??` operator) into the Python process via ctypes and boots
  `HeadlessWrapper.lua`. Full calc engine, no GUI.
- Character import uses GGG's OAuth API (`client_id=pob`, PKCE, same flow PoB2
  itself uses). Run the `authenticate_poe` tool once; the token is cached in
  `~/.pob2-mcp/token.json`.
- Trade search hits `pathofexile.com/api/trade2` with throttling and 429
  handling. Anonymous works; set the `POESESSID` env var if you hit 403s.

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
| Account | `authenticate_poe`, `list_characters`, `import_character` |
| Build | `new_build`, `import_build_code`, `export_build_code`, `get_build_info`, `get_stats`, `set_level` |
| Skills | `get_skills`, `set_main_skill` |
| Items | `get_items`, `equip_item`, `test_item` (non-destructive compare) |
| Tree | `get_tree`, `search_passives`, `alloc_passives`, `dealloc_passives` |
| Config | `get_config`, `set_config` |
| Trade | `trade_leagues`, `trade_search`, `trade_evaluate` (search + rank by DPS delta) |
| Escape hatch | `eval_lua` (arbitrary Lua inside the engine) |

`trade_evaluate` is the optimizer workhorse: it searches trade with a budget
filter, converts each listing to PoB item text, and computes the exact stat
delta of equipping it — without modifying the build.

Typical upgrade-hunt flow:
`authenticate_poe` → `import_character` → `set_main_skill` → per slot:
`trade_evaluate(league, query, slot)` → pick the best combination under budget
→ `equip_item` the winners → `export_build_code` to load the result in PoB2.

## Development

`python test_engine.py` smoke-tests the engine layer (no MCP, no auth needed).
