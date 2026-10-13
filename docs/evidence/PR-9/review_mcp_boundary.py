"""Review MCP calls without provider access, auth, or a PoB engine.

Windows asyncio uses a local socket pair for its event-loop wake-up pipe.
"""
import asyncio
import base64
import json
import logging
import sys
import zlib
from pathlib import Path

root = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(root / "pob2-mcp"))
import pob2mcp.server as server
from mcp.types import CallToolRequestParams

logging.disable(logging.CRITICAL)  # expected SDK exception logging, no secrets

class Engine:
    def __init__(self): self.calls = []
    def call(self, command, params=None):
        self.calls.append((command, params))
        if command == "save_build_xml":
            return {"xml": "<PathOfBuilding/>"}
        return {"review_stub": True}

async def main():
    observed = {}
    operations = {
        "authenticate_poe": {}, "list_characters": {},
        "import_character": {"name": "review-placeholder"},
        "trade_leagues": {},
        "trade_search": {"league": "fixture", "query": {}},
        "trade_evaluate": {"league": "fixture", "query": {}, "slot": "Weapon 1"},
    }
    for name, arguments in operations.items():
        # This is the handler installed for tools/call. No request context is
        # needed by these functions, so no session/transport is constructed.
        result = await server.mcp._handle_call_tool(None, CallToolRequestParams(name=name, arguments=arguments))
        observed[name] = result.model_dump(mode="json", exclude_none=True)
    observed["legacy_modules_loaded"] = [name for name in ("pob2mcp.poe_api", "pob2mcp.trade") if name in sys.modules]
    assert not observed["legacy_modules_loaded"]
    assert server._engine is None
    stub = Engine()
    server._engine = stub
    code = base64.b64encode(zlib.compress(b"<PathOfBuilding/>")).decode()
    await server.mcp.call_tool("import_build_code", {"code": code})
    await server.mcp.call_tool("test_item", {"item_text": "synthetic item", "slot": "Weapon 1"})
    await server.mcp.call_tool("export_build_code", {})
    observed["local_engine_commands"] = [call[0] for call in stub.calls]
    assert observed["local_engine_commands"] == ["load_build_xml", "test_item", "save_build_xml"]
    print(json.dumps(observed, indent=2, sort_keys=True))

asyncio.run(main())
