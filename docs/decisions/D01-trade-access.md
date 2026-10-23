# D01 Trade access and application identity

- Decision ID: D01
- Raised by: `docs/specs/research.md`, decision table
- Task: P05-T01
- Date proposed: 2026-10-10
- Proposed by: P05 engineer
- Reviewer: external review, 2026-10-11
- Status: accepted

## Question

Is there a supported live route by which this software may obtain Path of Exile
2 market listings and character builds, under its own application identity, and
what are the allowed operations, identity requirements, limits, payload shape
and failure behaviour of that route?

The question splits in two. They have different permissions and different
answers, and must not be reported as one.

- Route A, account-character import: read a character and its equipment from an
  account that has authorised this software.
- Route B, public market acquisition: search and refresh item listings offered
  for sale by other players.

## Sources consulted

| ID | Source | Read on |
|---|---|---|
| S1 | https://www.pathofexile.com/developer/docs | 2026-10-10 |
| S2 | https://www.pathofexile.com/developer/docs/reference | 2026-10-10 |
| S3 | https://www.pathofexile.com/developer/docs/authorization | 2026-10-10 |
| S4 | https://www.pathofexile.com/legal/terms-of-use-and-privacy-policy | 2026-10-10 |
| S5 | https://www.pathofexile.com/developer/docs/changelog | 2026-10-10 |
| S6 | `pob2-mcp/pob2mcp/trade.py` at `c2c2d02` | 2026-10-10 |
| S7 | `pob2-mcp/pob2mcp/poe_api.py` and `server.py` at `c2c2d02` | 2026-10-10 |
| S8 | `docs/specs/research.md`, findings F07, F08, F09 and the external evidence table | 2026-10-10 |

Saved detail: `docs/evidence/P05/access-observations.md` (documentary,
`restricted`) and `docs/evidence/P05/transport-assumptions.md` (source
inspection).

## What was actually observed

All of it is reading. No request was authenticated, no token or cookie was used,
no provider was contacted, and no module in `pob2-mcp` was executed. Nothing
below is a demonstrated route.

1. New developer application registration is closed. S1: "We are currently
   unable to process new applications."
2. Only documented resources are supported. S1 cites terms section 7(i) against
   using endpoints outside the documentation. S4 7(c) prohibits bots, 7(f)
   prohibits data extraction tools against the website.
3. S2 documents, for realm `poe2`: `GET /character[/poe2]/<name>` with scope
   `account:characters`, `GET /league` with `service:leagues`,
   `GET /league/<league>/ladder` with `service:leagues:ladder`, and a public
   `GET https://web.poecdn.com/api/currency-exchange/poe2` needing no OAuth.
4. S2 documents no trade search, item search or listing endpoint for any realm.
   The Public Stash API (`service:psapi`) does not accept `poe2` as a realm. S2
   states "There are currently limited APIs that return PoE2 game information."
5. The currency exchange response carries `markets` entries with `league`,
   `market_id`, `market_pair`, `volume_traded`, stock and ratio bounds. It
   contains no item, no listing id and no seller. It cannot populate a
   `Listing`.
6. S3 lists every scope. There is no trade or listing scope. `account:trade`,
   which `poe_api.py` requests, is not among them.
7. S1 requires `User-Agent: OAuth {clientId}/{version} (contact: {contact})` and
   defines limits as dynamic per-response `X-Rate-Limit-*` rules with
   `Retry-After`. No numeric limit is published; it is read from live headers.
   S1 warns that frequent excess revokes application access.
8. S6: the existing trade client calls undocumented `/api/trade2/*` website
   endpoints, carries a `POESESSID` website cookie from the environment, sets
   website `Origin`/`Referer`, invents fixed 1 to 2 second intervals, caps
   `Retry-After` at 120 s, and tells the user to supply a cookie when it sees a
   403.
9. S7: the account client authenticates as `client_id=pob`, Path of Building's
   registered identity, on localhost redirect ports registered to that
   application, and asks for the undocumented `account:trade` scope. Its
   character endpoint paths and `account:characters` scope do match S2.

Inferred, not observed: that no permitted listing route exists today. The
inference is from the absence of any documented endpoint plus the explicit
prohibition on undocumented ones. It is not proof that none will exist.

## Proposed choice

### Route A, account-character import: supported subject to a named registration condition

A documented endpoint exists and is the right one:
`GET https://api.pathofexile.com/character/poe2/<name>`, scope
`account:characters`, OAuth 2.1 authorization code with PKCE for a public
client.

- Allowed operations: list the authorising account's PoE 2 characters, and read
  one of them with equipment, skills, inventory, jewels and passives. Nothing
  else. Not another player's character; S2's endpoint is scoped to the
  authenticated account.
- Identity requirement, and the condition: a `client_id` registered to this
  project, used in both the OAuth request and the required `User-Agent`.
  **We do not have one, and S1 says new applications are not being processed.**
  Route A is therefore approved in principle and unavailable in practice until
  that registration exists. It must not be implemented against a borrowed
  identity.
- Limits: whatever the live `X-Rate-Limit-*` headers say, read per response.
  Treat `Retry-After` as a scheduling delay in full, never truncated. These are
  conditions to check at implementation time, not satisfied conditions.
- Redirect URI: settled, and not a blocker. The two rules S3 states apply to
  different client types. The HTTPS-and-registered-domain requirement, which
  rules out localhost, is in the **Confidential Clients** section. The
  **Public Clients** section says a public client must use the authorization
  code grant with PKCE and a local redirect URI. A desktop tool holding no
  client secret is a public client, so it registers its own local redirect
  URI. S3 gives one as an example; the specific host and port this project
  would register is a registration-time detail and is not inferred here.
  Nothing about this is in tension, and it was wrong to record it as a
  blocker: the open condition is the registration itself, not the redirect
  form.

Until the condition is met, account-character import is served by P05-T02 file
import: a build or item document the user exports themselves and passes to
`pob2opt market import`. That is a local file, not a provider route, and carries
`access_method: local_file`.

### Route B, public market acquisition: `unsupported_access`

There is no supported live route. Recorded as `unsupported_access`.

- No documented endpoint returns item listings for PoE 2, or for any realm.
- The `/api/trade2/*` endpoints the existing client uses are undocumented, and
  S1 and S4 7(i) prohibit using them.
- A `POESESSID` cookie is a website session credential, not an application
  credential. Supplying one is the workaround P05-T01 forbids.
- No scope exists that could authorise it even with our own registered client.

Consequence: R05 live-market acceptance stays blocked, and gate G4 in P05-T04
cannot be met. P05-T02 and P05-T03 continue on imported items, which is what the
project text already anticipates.

### Adjacent, and explicitly not a listing route

`GET https://web.poecdn.com/api/currency-exchange/poe2` is public, documented
and needs no OAuth or registration. It may be used later for the timestamped
conversion rate P05-T05 allows, and for nothing else. It yields no item, no
price for an item and no availability. Approving it is not approving Route B.
It is named here so a reviewer does not have to rediscover it, and it needs its
own small record before any code calls it.

### What the existing transport becomes

`pob2-mcp/pob2mcp/trade.py` is not repairable into an approved adapter; its
premise is the undocumented endpoint. It should be quarantined behind the
unsupported-provider path and kept out of `pob2opt`. `poe_api.py` has the
correct endpoint and scope for characters but the wrong identity; its endpoint
shape may be reused, its `client_id`, its `account:trade` scope and its redirect
ports may not.

### Failure behaviour to implement

`MarketProvider.query` and `MarketProvider.refresh` have no approved provider,
so both return a typed unsupported result rather than raising or returning an
empty success. `pob2opt market refresh --snapshot ID --corpus DIR` exits `3`
(missing dependency, access or coverage prevents the requested operation, per
`interfaces.md`) and emits:

```json
{
  "schema_version": 1,
  "status": "unsupported_access",
  "provider": "poe2_trade",
  "operation": "market.refresh",
  "snapshot_id": "<snapshot>",
  "http_status": null,
  "retry_eligible": false,
  "decision_ref": "D01",
  "reason": "No documented PoE 2 listing endpoint and no registered application identity.",
  "listings_rechecked": 0,
  "availability": "unknown",
  "observed_at": "<rfc3339>"
}
```

Rules this encodes, for P05-T04 to honour:

- `retry_eligible` is false. Absence of a route is not a transient failure, so
  the three-attempt retry policy does not apply and no backoff is scheduled.
- No `SourceDocument` is written. A failed acquisition fabricates nothing.
- Every listing in the snapshot keeps its stored `availability` or moves to
  `unknown`. None moves to `unavailable`: a refresh that could not run is not
  evidence of a sale.
- Snapshot availability for reporting is `unknown`, never
  `verified_at_snapshot`. No output may call the build currently obtainable.
- Exit `0` is not permitted for this path. An empty result set is not a
  successful refresh.

## Contracts affected

| Contract | Effect |
|---|---|
| `AcquisitionResult.status` | `unsupported_access` becomes the live status for the market provider. No new status value is needed. |
| `SourceDocument.access_method` | Route A would be `documented_api` once registered. Today's import path is `local_file`. The trade client would have been `public_page`, and is not approved. |
| `Listing.availability` | Stays `observed`, `rechecked`, `unavailable` or `unknown`. Without a route, refreshed listings land on `unknown`, never `unavailable`. |
| `MarketProvider.query` / `.refresh` | Implemented against no approved provider; both return the unsupported result above. P05-T04's live transport is not started. |
| `pob2opt market refresh` | Exit code `3`, payload above. P05-T04 owns the implementation. |
| P05-T05 availability labels | `verified_at_snapshot` and `partially_verified` are unreachable while D01 stands. `unknown` is the only honest snapshot label. |
| `RunManifest.availability mode` | A run requesting `market` mode must be told the mode is unavailable rather than silently downgraded. |
| Gate R05 / G4 | Remain blocked. |

No schema change is proposed. Every value used already exists.

## Follow-up references

Current implementation and access work: [project identity](https://github.com/kaporli/pob2-tools/issues/122), [listing access](https://github.com/kaporli/pob2-tools/issues/123), and [live transport](https://github.com/kaporli/pob2-tools/issues/72). The original alternatives remain in the [historical decision](https://github.com/kaporli/pob2-tools/blob/ae8d890f243d93e8c6c61de9eec23bbcd6edd72c/docs/decisions/D01-trade-access.md).

Not an alternative: a cookie, a borrowed `client_id`, a headless browser, or any other means of passing the gate. Each is excluded by S1 and S4, and by the task.

## Review

- Reviewer: external review (`docs/reviews/P05-T01.md`)
- Verdict: accepted
- Date resolved: 2026-10-11

A reviewer accepting this record accepts two dispositions, not one: Route A
supported subject to registration, Route B `unsupported_access`.

What the reviewer accepted, in their terms:

- **Route A.** Documented in principle, unavailable to this project until it
  has its own registered public client and completes implementation and
  verification. A `client_id` is not evidence of working import.
- **Route B.** `unsupported_access` under the currently documented interfaces.
  Obtaining a `client_id` does not open this route. R05 and G4 stay blocked.
- **Unavailable refresh.** A typed failure, never a fabricated successful
  acquisition. Current availability is unknown rather than sold or
  unavailable, and historical observations stay distinct from a current
  verification.
- **Sequencing.** Registration is a Route A dependency, not the critical path.
  P05-T02 item and listing file import and P05-T03 pools proceed on the
  existing fidelity contracts, with unknown availability where evidence is
  absent. P05-T04 live listing transport stays blocked.

Acceptance of this record is not acceptance of any live market capability, and
no earlier gate is passed by it.
