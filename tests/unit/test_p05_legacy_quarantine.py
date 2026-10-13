"""The quarantined legacy network paths cannot be reached (D01, P05-T01).

Offline, and no PoB. Importing ``pob2mcp.server`` constructs the MCP server
object and nothing else; none of these tests starts an engine.

What the review asked these tests to prove is narrow and worth stating: not
that the quarantined tools fail, but that they cannot construct or invoke the
old clients. A tool that built a ``Trade2Client`` and then errored would still
have read a cookie file on the way.
"""

from __future__ import annotations

import ast
import asyncio
import base64
import inspect
import sys
import zlib
from pathlib import Path

import pytest
from mcp.types import CallToolRequestParams

import pob2mcp.server as server
from pob2mcp.quarantine import (
    QUARANTINED,
    QUARANTINED_CLIENTS,
    CapabilityUnavailable,
    is_quarantined,
    refuse,
)

QUARANTINED_TOOLS = (
    "authenticate_poe", "list_characters", "import_character",
    "trade_leagues", "trade_search", "trade_evaluate",
)

#: Everything else the server registers. These are local engine operations and
#: must keep working: quarantine is about the network surface, not the engine.
LOCAL_TOOLS = (
    "new_build", "import_build_code", "export_build_code", "get_build_info",
    "get_stats", "set_level", "get_skills", "set_main_skill", "get_items",
    "equip_item", "test_item", "get_tree", "search_passives",
    "alloc_passives", "dealloc_passives", "get_config", "set_config",
    "eval_lua",
)


def _call(name: str):
    """Call a tool with the minimum arguments its signature demands."""
    function = getattr(server, name)
    arguments = {}
    for parameter, spec in inspect.signature(function).parameters.items():
        if spec.default is not inspect.Parameter.empty:
            continue
        arguments[parameter] = ({} if spec.annotation is dict
                                else "x" if spec.annotation is str else 1)
    return function(**arguments)


@pytest.mark.parametrize("name", QUARANTINED_TOOLS)
def test_every_quarantined_tool_refuses(name: str):
    with pytest.raises(CapabilityUnavailable) as refused:
        _call(name)
    message = str(refused.value)
    assert refused.value.operation == name
    assert "docs/decisions/D01-trade-access.md" in message
    assert "not a transient failure" in message


@pytest.mark.parametrize("name", QUARANTINED_TOOLS)
def test_a_quarantined_tool_constructs_no_legacy_client(name: str, monkeypatch):
    """The refusal comes first. Nothing is built, so nothing is read."""
    import pob2mcp.poe_api
    import pob2mcp.trade

    def explode(*args, **kwargs):
        raise AssertionError("%s constructed a quarantined client" % name)

    monkeypatch.setattr(pob2mcp.poe_api, "PoeApi", explode)
    monkeypatch.setattr(pob2mcp.trade, "Trade2Client", explode)
    for attribute in QUARANTINED_CLIENTS:
        if hasattr(server, attribute):
            monkeypatch.setattr(server, attribute, explode)

    with pytest.raises(CapabilityUnavailable):
        _call(name)


def test_the_server_module_does_not_import_the_legacy_clients():
    """A default server process never loads the module holding the borrowed
    client id, so there is no cached token to read even by accident."""
    source = Path(server.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)
        elif isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
    assert ".poe_api" not in imported
    assert ".trade" not in imported
    # Names, not raw text: the class names still appear in the docstrings that
    # explain why they are gone, and that is the point of quarantining rather
    # than deleting.
    referenced = {
        node.id for node in ast.walk(tree) if isinstance(node, ast.Name)
    } | {
        node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)
    }
    for name in QUARANTINED_CLIENTS:
        assert name not in referenced, name


def test_importing_the_server_loads_neither_legacy_module():
    """In a clean interpreter, because this one may have imported them above."""
    import os
    import subprocess

    result = subprocess.run(
        [sys.executable, "-c",
         "import sys; import pob2mcp.server; "
         "print('pob2mcp.poe_api' in sys.modules, 'pob2mcp.trade' in sys.modules)"],
        capture_output=True, text=True,
        cwd=str(Path(server.__file__).resolve().parents[2]),
        env={**os.environ,
             "PYTHONPATH": str(Path(server.__file__).resolve().parents[1])})
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "False False", result.stdout


def test_the_client_factories_refuse_before_constructing_anything():
    for factory in (server.poe_api, server.trade):
        with pytest.raises(CapabilityUnavailable):
            factory()


def test_the_local_engine_tools_are_not_quarantined():
    for name in LOCAL_TOOLS:
        assert hasattr(server, name), name
        assert not is_quarantined(name), name
    assert set(QUARANTINED) == set(QUARANTINED_TOOLS)


def test_the_quarantine_has_no_runtime_override(monkeypatch):
    """An environment variable that lifted this would make it advisory. The
    condition for restoring these paths is an approved project-owned route,
    which is not something a local setting can assert."""
    source = Path(
        Path(server.__file__).with_name("quarantine.py")).read_text(
            encoding="utf-8")
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and node.attr in ("getenv", "environ"):
            raise AssertionError("quarantine.py reads the environment")
    for variable in ("POB2_ALLOW_LEGACY", "POB2_ENABLE_TRADE", "POB2_UNSAFE"):
        monkeypatch.setenv(variable, "1")
    with pytest.raises(CapabilityUnavailable):
        _call("trade_search")


def test_refuse_names_an_unknown_operation_without_pretending_to_know_it():
    error = refuse("something_else")
    assert isinstance(error, CapabilityUnavailable)
    assert "something_else" in str(error)
    assert "Trade2Client" in str(error)


def test_the_legacy_modules_are_kept_not_deleted():
    """Quarantine preserves the endpoint knowledge and the conversions. It is
    not a deletion, and no credential or user file is touched by it."""
    package = Path(server.__file__).parent
    assert (package / "poe_api.py").is_file()
    assert (package / "trade.py").is_file()


@pytest.fixture(scope="module")
def mcp_loop():
    # Windows asyncio creates a loopback socket pair for its wake-up pipe.
    # Construct that infrastructure before the function-scoped network guard;
    # every actual tool call still runs with outbound connections prohibited.
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.mark.parametrize("name,arguments", [
    ("authenticate_poe", {}),
    ("list_characters", {}),
    ("import_character", {"name": "fixture"}),
    ("trade_leagues", {}),
    ("trade_search", {"league": "fixture", "query": {}}),
    ("trade_evaluate", {"league": "fixture", "query": {}, "slot": "Weapon 1"}),
])
def test_registered_mcp_refusal_preserves_explanation(name, arguments, monkeypatch, mcp_loop):
    def forbidden(*args, **kwargs):
        pytest.fail("quarantined MCP call reached a client or engine factory")

    for factory in ("poe_api", "trade", "engine"):
        monkeypatch.setattr(server, factory, forbidden)
    result = mcp_loop.run_until_complete(server.mcp._handle_call_tool(
        None, CallToolRequestParams(name=name, arguments=arguments)))
    assert result.is_error
    text = " ".join(block.text for block in result.content)
    assert name in text
    assert QUARANTINED[name] in text
    assert "docs/decisions/D01-trade-access.md" in text
    assert "not a transient failure" in text


def test_local_import_item_evaluation_and_export_still_dispatch_through_mcp(monkeypatch, mcp_loop):
    calls = []

    class Engine:
        def call(self, command, params=None):
            calls.append((command, params))
            return {"xml": "<PathOfBuilding/>"} if command == "save_build_xml" else {"ok": True}

    monkeypatch.setattr(server, "_engine", Engine())
    code = base64.b64encode(zlib.compress(b"<PathOfBuilding/>")).decode()

    async def run():
        for name, args in [
            ("import_build_code", {"code": code}),
            ("test_item", {"item_text": "fixture item", "slot": "Weapon 1"}),
            ("export_build_code", {}),
        ]:
            result = await server.mcp._handle_call_tool(None, CallToolRequestParams(name=name, arguments=args))
            assert not result.is_error

    mcp_loop.run_until_complete(run())
    assert calls == [
        ("load_build_xml", {"xml": "<PathOfBuilding/>"}),
        ("test_item", {"raw": "fixture item", "slot": "Weapon 1", "keys": None}),
        ("save_build_xml", None),
    ]
