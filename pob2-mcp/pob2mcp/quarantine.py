"""Quarantine for the legacy live-network paths (D01).

Two clients in this package predate the access investigation and are not
usable under its findings:

* ``poe_api.PoeApi`` authenticates as Path of Building's registered OAuth
  identity. That identity belongs to another project. D01 says account
  character import needs a ``client_id`` registered to this project, and that
  it must not be implemented against a borrowed one.
* ``trade.Trade2Client`` calls the undocumented ``/api/trade2/*`` endpoints and
  can carry a ``POESESSID`` website cookie. D01 records public market
  acquisition as ``unsupported_access``: there is no documented PoE 2 item
  listing route, and a session cookie is a website credential, not an
  application one.

The decision recorded in ``docs/reviews/P05-T01.md`` is quarantine rather than
deletion. The files, their endpoint knowledge and their data conversions stay
in the tree and in the history. What changes is that the MCP server's default
surface cannot reach them: the six tools below refuse before any network
request, any token read and any cookie read, and the client factories refuse
before constructing a client at all.

There is deliberately no environment variable or flag that lifts this. A
runtime override would make the quarantine advisory, and the condition for
restoring these paths is not a local setting: it is a project-owned route that
has been separately approved. Restoring them means editing this module, with
that approval on the record.

No credential, cached token or user file is touched. Quarantine disables entry
points; it does not delete anything.
"""

from __future__ import annotations

from mcp.server.mcpserver.exceptions import ToolError

DECISION = "docs/decisions/D01-trade-access.md"
REVIEW = "docs/reviews/P05-T01.md"

#: Tool name to the reason it is unavailable. The keys are exactly the
#: registered MCP entry points that reach a quarantined client.
QUARANTINED: dict[str, str] = {
    "authenticate_poe":
        "OAuth here authenticates as Path of Building's registered client, "
        "which belongs to another project. This project has no registered "
        "client of its own.",
    "list_characters":
        "Reaching the account API requires the borrowed OAuth identity above.",
    "import_character":
        "Reaching the account API requires the borrowed OAuth identity above. "
        "Local build import is unaffected: use import_build_code, or load a "
        "build file.",
    "trade_leagues":
        "The trade2 endpoints are undocumented and D01 records live market "
        "access as unsupported_access.",
    "trade_search":
        "The trade2 endpoints are undocumented and D01 records live market "
        "access as unsupported_access. No documented PoE 2 item listing route "
        "exists, and a POESESSID cookie is a website credential, not an "
        "application credential.",
    "trade_evaluate":
        "It is trade_search followed by an engine evaluation, so it inherits "
        "the refusal above. Evaluating an item you already hold is "
        "unaffected: use test_item with the item text.",
}

#: Client classes no quarantined path may construct.
QUARANTINED_CLIENTS = ("PoeApi", "Trade2Client")


class CapabilityUnavailable(ToolError):
    """An intentional MCP refusal, raised before network or credential use.

    ToolError preserves this safe explanation through the MCP handler.
    RuntimeError would instead be wrapped as an unexpected crash whose
    explanation is hidden from callers.
    """

    def __init__(self, operation: str, reason: str) -> None:
        self.operation = operation
        self.reason = reason
        super().__init__(
            "%s is unavailable: %s This is a recorded decision, not a "
            "transient failure. See %s and %s. Restoring it requires a "
            "project-owned route that has been separately approved, not a "
            "local setting."
            % (operation, reason, DECISION, REVIEW))


def refuse(operation: str) -> "CapabilityUnavailable":
    """The error for ``operation``. Raise it; do not return it to a caller."""
    reason = QUARANTINED.get(
        operation,
        "it reaches a quarantined legacy client (%s)."
        % ", ".join(QUARANTINED_CLIENTS))
    return CapabilityUnavailable(operation, reason)


def is_quarantined(operation: str) -> bool:
    return operation in QUARANTINED
