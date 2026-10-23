# PRs 6–9: repair acceptance, 2026-10-13

> Historical review of the commits named below. Current task state and follow-ups are on [GitHub Issues](https://github.com/kaporli/pob2-tools/issues/23); this snapshot is not a current assignment list.

Reviewer and repair author: Codex. Specification version 1.0. Verdict: **accepted within the scope below**. This supersedes the remaining F1–F4 findings in [the October 12 review](PR-6-9-rereview.md). No GitHub PR was merged by this work.

| PR | Reviewed implementation / integration | Accepted scope |
|---|---|---|
| #6 | Repairs `2e2fada116f6af778dff27bd3c285999485e8961`; branch head `7a2c83c46c01b1fb4dcb1b23558dd3dd4006a96a` | P03-T01 capability records and P03-T02 local/shared HTTP acquisition; no named-source live acquisition |
| #7 | `f2051d40d7d358e1a05e0431cdc1f2c55fad9011`, including #6 | P05-T01 access investigation and D01 unsupported-market disposition; no live trade capability |
| #8 | `67b49888e0d7943bcd679ffa9f89c9f5f63047a7`, including #7 | P09-T01 synthetic protocol and D04 collection instructions; no representative gameplay acceptance |
| #9 | MCP repair `415c44436fb3dfa9faf4853d5aec35cffe3dd6a3`; combined implementation `787e0e0b0d39fd115bac734e9386a1e583d3df82` | Legacy quarantine with explanatory MCP errors and retained local engine dispatch |

## Repairs and evidence

- F1: Exact opaque resource identities bind validators and cached documents, including query order. A changed redirect cannot return another build through a redacted-URL collision. Legacy cache identities are refetched. Regression tests cover normal 304 reuse, changed destinations, unsolicited 304s, duplicate query order and secret-free persistence.
- F2: Service initialization restores saved provider cooldowns before the first request, preserving stricter live deadlines. Restart, exhausted-retry, independent-provider and expiry cases exercise the production path.
- F3: XML signatures and declarations determine the encoding before decoding non-ASCII body text. Supported Latin-1, Windows-1252 and UTF-16 payloads retain their original bytes, directly and compressed. Unsafe declarations and conflicting/invalid encodings remain typed refusals.
- F4: `CapabilityUnavailable` uses the MCP SDK's intentional `ToolError` boundary. All six quarantined registered tools return the operation, reason, D01 reference and permanent-failure explanation. Client/engine factories remain unreachable; import, item evaluation and export dispatch locally with a stub engine.
- D04: Corrected the movement-model gap identifier and incoming-damage collection prerequisites. Character life/energy shield, mitigation and recovery context are relevant; enemy health is not required for that measurement.

The independent before/after probes are retained under `docs/evidence/PR-6/` and `docs/evidence/PR-9/`, including results for both interpreters. Commands: `python docs/evidence/PR-6/review_followup.py <checkout>` and `python docs/evidence/PR-9/review_mcp_boundary.py`. These use scripted transports and a stub engine, with no provider requests or credentials. Windows asyncio uses a local socket pair for its wake-up pipe.

## Combined validation

At combined implementation `787e0e0b0d39fd115bac734e9386a1e583d3df82`:

| Check | Python 3.12.4 | Python 3.10.22 |
|---|---|---|
| Offline unit and integration suite | 1,107 passed, 1 xfailed | 1,107 passed, 1 xfailed |
| Six registered MCP refusals and existing quarantine checks | Included; 26 tests | Included; 26 tests |
| P09 protocol/scenarios | Included; 32 tests | Included; 32 tests |

Full command: `python -m pytest tests/unit tests/integration -m 'not engine and not network and not longrun' -q`. The expected failure is the existing pending P08-T01 prepare contract binding. `python scripts/generate_schemas.py --check` reports all 20 schema files matching. `git diff --check` is clean. The shared test inventory retains the entries from all four branches; independent additions were preserved when resolving conflicts.

No live provider, gameplay or native-engine test was run for these repairs. Those capabilities are not established by the offline checks. The pre-existing local deletion of `external/PathOfBuilding-PoE2` was preserved and excluded from every commit.

## Merge and reassessment

Merge **#6 → #7 → #8 → #9**. Each later branch contains the preceding branch through normal merges, so the shared manifest conflicts are already resolved. All branch updates are ordinary fast-forward pushes. CI must be green for each pushed head before merging; GitHub check results are the authoritative record of those runs.

P03 provider adapters/parsers and local corpus work can build on the repaired acquisition layer. Named-source acquisition remains blocked until its access and capability evidence is accepted. A project-owned registration remains a prerequisite for account import; it does not create a supported public listing API. The synthetic protocol supports P06/P07 development, while representative scenarios, measured constants and real build comparisons still require the documented evidence. Quarantined clients stay disabled. No earlier engine gate is reopened and no live-market or gameplay gate is accepted by this review.
