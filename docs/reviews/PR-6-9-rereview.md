# PRs 6–9: follow-up review, 2026-10-12

Reviewer: Codex. Specification version 1.0. This report is the reviewer verdict for the exact heads below, superseding the earlier verdicts only where explicitly stated. Engineer-authored repair notes in earlier reports are implementation claims, not independent reviewer acceptance.

| PR / task | Reviewed head | Verdict |
|---|---|---|
| #6 / P03-T01, P03-T02 | `377c45f29800d33fad5f8f6b72d37ebc2408c17b` | **changes_required** for T02; T01's documentary repair accepted, named-source live acquisition still blocked |
| #7 / P05-T01, D01 | `541f214d88fe014d1804b4da252eda0d59501787` | **accepted**, access investigation and unsupported-market disposition only |
| #8 / P09-T01, D04 | `8521348a91ed207d490245c60c478a5529da02af` | **accepted**, synthetic protocol only; practical half remains blocked |
| #9 / legacy quarantine | `76e64a2a93f60c60c692b87a46cca8ed36eba122` | **changes_required**, expected error is lost at MCP boundary |

All four heads were open, mergeable against their current base, and green on GitHub's Python 3.10/3.12 checks when inspected. That is not a substitute for the behavioral findings below. No changes were pushed, no GitHub review/comment was posted, and no PR was merged.

## Verification

Inspected repair diffs against the previously reviewed heads, surrounding implementation, tests, decision records and handoff notes. Used detached worktrees for #6–#8 and the existing #9 checkout. Preserved the pre-existing deletion of `external/PathOfBuilding-PoE2`.

| Check | Python 3.12.4 | Python 3.10.22 |
|---|---|---|
| #6 five focused P03 unit files, including repairs | 167 passed | 167 passed |
| #7 `test_p05_t01_access_decision.py` | 9 passed | 9 passed |
| #8 `test_p09_t01_protocol.py` and `test_p09_t01_scenarios.py` | 32 passed | 32 passed |
| #9 `test_p05_legacy_quarantine.py` | 19 passed | 19 passed |
| #6 all offline unit/integration tests | 1,018 passed, 1 xfailed | Not repeated beyond focused suite; head CI green |
| #9 all offline unit/integration tests | 870 passed, 1 xfailed | Not repeated beyond focused suite; head CI green |

Full-suite command: `python -m pytest tests/unit tests/integration -m 'not engine and not network and not longrun' -q`. The expected failure is pending P08 preparation contract binding. The alternate interpreter was `.venv/pr2-validation/py310-a/Scripts/python.exe` from the workspace root. #8 schema generation check: 20 schema files match. No real network acquisition, gameplay or native engine evaluation was needed or performed; local engine dispatch was checked with a stub and the unchanged tool implementations were inspected.

Independent probes, run on both interpreters except the existing #8 arithmetic probe:

- `python docs/evidence/PR-6/review_followup.py runs/review-pr6`. Outputs: `docs/evidence/PR-6/followup-py312.json`, `followup-py310.json`.
- `python docs/evidence/PR-9/review_mcp_boundary.py`. Outputs: `docs/evidence/PR-9/review-mcp-py312.json`, `review-mcp-py310.json`.
- From the #8 worktree: `python docs/evidence/PR-8/review_adversarial.py`. Reconfirmed 20/115/190-second completion examples and a valid low-output timeout.

The new probes are review observations, not regression tests asserting that the current defects are correct. They open no sockets and use no credentials.

## Remaining merge blockers

### F1 — P2 — #6: Bind validators and cached documents to the exact final resource

Locations: `pob2-optimizer/pob2opt/acquisition/http.py:152` and `:191`; `service.py:378`; `state.py:95`.

The repair binds validators to an origin rather than a full resource, then compares redacted final URLs when accepting a 304. Reproduction:

1. `/start` redirects to `/export?variant=first`; the server returns the first build and ETag `v1`.
2. The redirect changes to `/export?variant=second` on the same host.
3. The client sends the old ETag to the changed target. That different resource can legitimately have its own ETag `v1` and answer 304.
4. Both final URLs redact to `variant=REDACTED`, so the check passes. Acquisition returns the **first build**, unchanged, with status **ok**.

Both interpreters reproduce this silent wrong-build reuse. The repaired changed-target test covers different paths, not different redacted values. Sending a validator to every path on its issuer's origin also incorrectly sends the export's validator to the initial redirect endpoint.

Required repair: persist a secret-safe identity for the complete final representation separately from its display URL; offer its validators only to that exact normalized resource. A changed destination must be fetched without the old validator; an unexpected 304 must not reuse the old document. Preserve raw query ordering unless a provider contract proves it irrelevant: the new request-key code at `state.py:196` sorts duplicate query keys, making `?id=1&id=2` and `?id=2&id=1` collide even though a provider may select the first value.

Regression acceptance: stable redirect→200→304 still reuses one document; changed path, changed redacted query value and reordered duplicate values never reuse another representation or send its validator. No plaintext credential may be persisted to implement the fix.

### F2 — P2 — #6: Restore saved cooldowns in the production acquisition path

Locations: `pob2-optimizer/pob2opt/acquisition/service.py:114` and `:343`; test-only restoration at `tests/unit/test_p03_t02_repairs.py:438`.

`restore_cooldowns` has no production caller. The regression test restores the scheduler itself, which makes the helper pass while bypassing the missing integration. After a first service persists a 120-second Retry-After, a fresh service using the same corpus immediately sends another request at elapsed time zero. `_save_cooldowns` then overwrites the stored future deadline with an empty mapping. This is also the construction pattern used by a new CLI invocation.

Required repair: wire saved deadlines into the real service/CLI initialization before any request is allowed. Preserve any stricter live deadline when merging state. Do not clear persisted future cooldowns merely because a newly constructed scheduler starts empty.

Regression acceptance: instantiate a second service/CLI against the same persisted corpus without manually calling scheduler helpers. Before the deadline it must defer with zero sends; after 120 seconds it may send. A separate provider remains usable. Repeat with the first request exhausting its retry budget.

### F3 — P2 — #6: Read the XML declaration before decoding a non-UTF-8 body

Location: `pob2-optimizer/pob2opt/acquisition/content.py:234`–245.

The new encoding check decodes the entire document as UTF-8 before reading its encoding declaration. A well-formed ISO-8859-1 document containing `café` therefore returns `invalid_response` with a UTF-8 decoding error, even though ISO-8859-1 is listed as supported and the pre-repair ElementTree path accepts it. ASCII-only fixtures conceal the bug. The same issue affects other declared supported single-byte encodings with non-ASCII content.

Required repair: inspect the encoding signature/declaration safely before decoding the full body, then strictly decode once using the accepted encoding. Preserve the repaired encoding-independent DOCTYPE/entity rejection. If a format is intentionally unsupported, document that scope explicitly rather than claiming support in the allowlist.

Regression acceptance: supported Latin-1 and Windows-1252 XML containing non-ASCII notes imports byte-for-byte, directly and through a compressed build code; malformed encoding remains a typed failure and the unsafe UTF-8/UTF-16 cases remain refused.

### F4 — P2 — #9: Surface quarantine as an intentional MCP tool error

Locations: `pob2-mcp/pob2mcp/quarantine.py:68` (`CapabilityUnavailable`); the six registered refusal entry points in `server.py`.

The refusal is a RuntimeError. The installed MCP SDK wraps it as UnexpectedToolError, discards its message from the client response, and logs it as a crash. Invoking the actual registered `tools/call` handler returns only `Error executing tool authenticate_poe` (and corresponding generic messages for the other five tools). The decision reference, reason, non-transient status and local alternatives never reach the caller. Direct-function tests see the original exception and consequently miss the product behavior.

The quarantine itself works: the independent boundary probe confirms no legacy client modules were loaded and no engine was constructed by these calls. Local import, item evaluation and export still dispatch correctly through MCP with a stubbed engine.

Required repair: map CapabilityUnavailable to the SDK's intentional ToolError at the MCP boundary, or return an explicit error result whose safe message contains the operation, unavailability reason and decision reference. Keep unexpected exceptions generic; do not expose all tracebacks to fix this one expected refusal.

Regression acceptance: call all six registered tools through the MCP handler on both interpreters. Assert an error response containing the reason and D01 reference, not just generic execution failure, while legacy modules remain unloaded and no network/credential/engine work occurs. Retain local-tool dispatch checks. A permanent unsupported capability must not appear as a transient server crash.

## Accepted repairs and residual scope

### #6 / P03-T01

The Mobalytics decision now distinguishes robots instructions, unread terms and observed 403 responses without claiming that an unknown means permission. The cause remains unknown and no named provider is automatically approved. Accept that documentary correction. The old acquisition security fixes for cross-origin headers, UTF-16 declarations, response closure, dot-path checks and JSON depth are implemented and their focused regression tests pass. The remaining cache and cooldown integration cases above prevent T02 acceptance. Unrelated PR5 artifacts were removed.

### #7 / P05-T01

Accept the corrected distinction between confidential-client HTTPS redirects and public-client local redirects, with no guessed project port or borrowed identity. This is reviewer acceptance as of 2026-10-12; the engineer's earlier `accepted` annotation was not independent re-review. Account import still requires project registration, implementation and verification. The unsupported live-market disposition remains; acquiring a client ID does not create a listing API. Offline item/pool work can proceed. This accepts no live capability and does not pass R05/G4.

### #8 / P09-T01

Accept the synthetic protocol repair: horizon totals are separated from elapsed time, death stops the clock, low-output timeout remains a valid failed evaluation, and the worked examples are recomputed. The build export no longer closes a reference-observation gap; absolute enemy life no longer follows from a fractional health bar. Scenario/rotation identity is unchanged; updated fixture bytes are covered by new content hashes. D04's representative encounters, families and practical validation remain blocked.

Nonblocking documentation cleanup: `docs/decisions/D04-encounter-suite.md:121` calls the movement gap `gap-p09-t01-route-timing`, which does not exist; use the actual `gap-p09-t01-movement-model`. The incoming-damage row should also identify the **character's** life/ES and mitigation/recovery context, rather than ambiguously referring to the enemy-life row below. Do not use this shorthand table to close a practical-data gap without its full record's evidence requirements. These do not block synthetic-only adoption.

## Sequencing and next review

#7 and #8 are ready for approval within the scopes above. #6 and #9 need F1–F4 repaired first. The planned #6 → #7 → #8 merge sequence can remain, with #9 independent after its repair; #7's documentary acceptance does not depend on #6's HTTP code being fixed. If following the chosen order, hold merging until #6 is ready rather than treating CI green as acceptance.

Rebase remaining PRs after each merge, preserve the union of tests/MANIFEST.md entries, and rerun CI on each resulting head. This review did not perform an integration merge and cannot certify that the eventual conflict is exactly one line. No earlier P01/P02 gate is reopened. P03 automatic acquisition and P05 live trade remain constrained by their separate access decisions; synthetic P06/P07 work and local P04/P05 imports can continue.
