# P05-T01 existing transport assumptions

Kind of evidence: source inspection of this repository at commit `c2c2d02`. No
module below was imported, instantiated or executed, and no request was issued.
Statements are about what the code would do if run, read from its text.

Files read: `pob2-mcp/pob2mcp/trade.py` (81 lines),
`pob2-mcp/pob2mcp/poe_api.py` (204 lines), and the call sites in
`pob2-mcp/pob2mcp/server.py`.

This extends research findings F08 and F09 with the specific assumptions, so
D01 can name them.

## `trade.py` (`Trade2Client`) - the public market path

| # | Assumption in the code | Status against the published documentation |
|---|---|---|
| A1 | `https://www.pathofexile.com/api/trade2/data/leagues`, `/api/trade2/search/poe2/<league>` and `/api/trade2/fetch/<ids>?query=<id>&realm=poe2` are callable interfaces. | Undocumented. None appears in the API reference. Covered by the prohibition in observation O2/O3. |
| A2 | Anonymous access is a supported mode. The module docstring says anonymous "works for search/fetch". | Not a documented mode. The documented API requires OAuth for every non-public resource, and these are not documented resources at all. |
| A3 | A `POESESSID` cookie is a credential the client may carry, read from the environment and set on the session for `www.pathofexile.com`. | A website session cookie, not an API credential. No documented flow issues it to an application. This is the implicit credential `architecture.md` forbids. |
| A4 | `Origin` and `Referer` headers are set to the trade site so the request looks like the website. | Presenting as the website is the pattern the terms treat as automated access to the website. |
| A5 | `User-Agent: pob2-mcp/0.1 (...)`. | Does not match the required `OAuth {clientId}/{version} (contact: {contact})` form, and there is no client id to put in it. |
| A6 | Rate limiting is a fixed client-side minimum interval: 2.0 s for search, 1.0 s for fetch, 1.0 s for misc, per kind, in one process. | Invented numbers. The documented contract is dynamic per-response rules in `X-Rate-Limit-*`. The code never reads those headers. |
| A7 | On HTTP 429, sleep `min(Retry-After, 120)` and retry, at most three attempts. | Truncates the advertised delay at 120 s. `interfaces.md` requires respecting the full advertised delay by scheduling work later. The sleep also blocks the calling thread, which `interfaces.md` forbids for coordinator cancellation. |
| A8 | HTTP 403 means "set `POESESSID`". | Encodes cookie supply as the remedy for being blocked, which is the workaround this task must not bless. 403 is an access-blocked result, not a prompt for a cookie. |
| A9 | Any non-200 that is not 429 or 403 raises one untyped `TradeError` carrying 300 characters of the body. | Collapses `not_found`, `invalid_response`, `timeout` and schema drift into one failure. P05-T04 requires these kept distinct. |
| A10 | `fetch` silently drops falsy entries from `result` and chunks ids by 10. | An absent listing becomes a shorter list with no record that it was absent. Absence and failure are indistinguishable to the caller. |
| A11 | 30 s total request timeout, no connect timeout, no response size limit. | `interfaces.md` sets 10 s connect, 30 s read and a 20 MiB cap. |
| A12 | Pagination and truncation are not modelled. `search` returns the raw body; the caller sees `total` but no scope, no cursor and no truncation flag. | `MarketProvider.query` must return pagination state, truncation and scope. |
| A13 | No observation time is recorded anywhere. | Every snapshot must store request scope and observation time. |

`pob2-optimizer/pob2opt/harvest.py` is the separate legacy harvester and is
finding F07. It is not this client, and P05-T03 replaces it.

## `poe_api.py` (`PoeApi`) - the account path

| # | Assumption in the code | Status against the published documentation |
|---|---|---|
| B1 | `CLIENT_ID = "pob"`. The docstring says this is "the same flow Path of Building 2 uses". | Another application's registered identity. F09 already forbids reusing it, and the required `User-Agent` would have to carry that same borrowed id. This is the specific thing P05-T01 must not accept. |
| B2 | `SCOPES = ["account:profile", "account:leagues", "account:characters", "account:trade"]`. | `account:trade` is not in the documented scope list. The other three are documented. A request for an undocumented scope is not a supported request. |
| B3 | Redirect URI is `http://localhost:{49082,49083,49084}`, ports chosen because the borrowed client is registered for them. | Depends entirely on B1. The published rules state registered redirect URIs must be HTTPS on a domain the application owner controls, and name localhost as unacceptable. |
| B4 | Tokens are cached unencrypted at `~/.pob2-mcp/token.json` and reloaded on construction. | A credential on disk, outside the repository. This task read neither the path nor any token. `docs/evidence/P00/environment.md` recorded `POESESSID` as not set and no provider contacted. |
| B5 | `authenticate()` opens a browser and runs a PKCE authorization-code flow against `https://www.pathofexile.com/oauth/authorize` and `/oauth/token`. | The grant type and PKCE use are correct in form. The identity it presents is not ours, so the flow's correctness does not make it a permitted route. |
| B6 | On 429, sleep `min(Retry-After, 60)` once and retry once. | Same truncation and blocking problem as A7, with a tighter cap. |
| B7 | On 401, refresh once and retry; a failed refresh clears the cached token. | Reasonable shape. Still an untyped `PoeApiError` at the boundary rather than a typed `AcquisitionResult`. |
| B8 | `list_characters(realm="poe2")` calls `GET /character/poe2`; `get_character(name, realm="poe2")` calls `GET /character/poe2/<name>`. | These paths and the `account:characters` scope match the documented reference. The endpoint shape is the one part of this module that is documented. |
| B9 | `get_character` reaches an arbitrary named character. | The documented endpoint returns the authenticated account's own characters. A name belonging to another account is not a documented capability. |

## Summary for D01

- The public market path in `trade.py` rests on undocumented website endpoints,
  a website session cookie and invented rate numbers. Nothing in it can be
  promoted to an approved adapter. It must be quarantined, not repaired.
- The account path in `poe_api.py` has the right endpoint and the right scope
  for characters, wrapped around a borrowed `client_id`, an undocumented
  `account:trade` scope and a redirect registration that is not ours. The
  endpoint survives review; the identity does not.
- Neither module was executed, so neither has live-capable status. Code
  inspection cannot grant it.
