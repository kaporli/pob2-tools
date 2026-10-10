# P05-T01 access observations

Kind of evidence: documentary. Published vendor documentation and terms, read
over HTTPS without authentication on 2026-10-10. Not synthetic, not PoB-derived,
not independently measured, and not a live provider test.

Classification: `restricted`. The quoted fragments are third-party text, kept
short and only where the wording is the finding. Everything else is linked, not
copied. No credential, cookie, token, account name or seller identity appears
here or was used to obtain any of it.

## What was and was not done

Done: fetched the four public pages listed below and read them.

Not done: no authenticated request, no OAuth flow, no token use, no request to
`pathofexile.com/api/trade2/*`, no provider contact, no application for a
developer programme, no account login. No route below has been demonstrated by
executing it. Every capability statement here is a reading of documentation.

## Sources consulted

| ID | Source | Fetched |
|---|---|---|
| S1 | https://www.pathofexile.com/developer/docs | 2026-10-10 |
| S2 | https://www.pathofexile.com/developer/docs/reference | 2026-10-10 |
| S3 | https://www.pathofexile.com/developer/docs/authorization | 2026-10-10 |
| S4 | https://www.pathofexile.com/legal/terms-of-use-and-privacy-policy | 2026-10-10 |
| S5 | https://www.pathofexile.com/developer/docs/changelog | 2026-10-10 |

S1 to S3 and S5 are the vendor's own developer documentation. S4 is the
site terms the developer documentation points at.

## Observations

### O1. Application registration is closed (S1)

S1 states "We are currently unable to process new applications." Existing
applications are managed from an account profile page.

Observed: the registration page says new applications are not being processed.
Inferred: this repository therefore has no route to obtain its own `client_id`
at this time. Not observed: any alternative or exception path, because asking
for one is outside this task.

### O2. Only documented resources are supported (S1)

S1 states "It is against our Terms of Use (section 7i) to reverse-engineer
endpoints outside of this documentation." Support is limited to the API
Reference and the Data Exports.

### O3. Terms of use clauses that bear on automated access (S4)

- 7(c): "Utilise any automated software or 'bots' in relation to your access or
  use of the Website, Materials or Services."
- 7(f): "Use any data gathering and extraction tools or software to extract
  information from the Website or utilize framing techniques".
- 7(i): "Reverse engineer, de-compile or disassemble the Website, Materials or
  Services or seek to establish the technical processes, operations and
  communication protocols".

These are prohibitions. S1 cites 7(i) specifically against undocumented
endpoints.

### O4. Documented PoE 2 endpoints (S2)

| Endpoint | Realm | Scope | Note |
|---|---|---|---|
| `GET /character[/<realm>]/<name>` | `poe2` | `account:characters` | The authenticated account's own character, with equipment, skills, inventory, jewels and passives. |
| `GET /league` | `poe2` | `service:leagues` | League list. |
| `GET /league/<league>/ladder` | `poe2` | `service:leagues:ladder` | Top 1000 entries, enabled for PoE 2 in the 0.5.0 entry of S5. |
| `GET https://web.poecdn.com/api/currency-exchange[/<realm>][/<id>]` | `poe2` | none | Public, no OAuth. S5 records it being made public in the 3.29.0 entry. |

Base host for the OAuth endpoints is `https://api.pathofexile.com`.

### O5. No documented item search or listing endpoint (S2)

S2 documents no trade search, no item search and no listing fetch, for any
realm including `poe2`. S2 states "There are currently limited APIs that return
PoE2 game information."

The Public Stash API (`service:psapi`) is documented for the PoE 1 PC, `xbox`
and `sony` realms. `poe2` is not an accepted realm for it. An `Item` returned
anywhere in the API may carry `realm: poe2`, which is a property of an item, not
a PoE 2 stash feed.

Observed: no listing endpoint is documented. Inferred: a public market
acquisition route does not exist in the supported surface today.

### O6. Currency exchange is aggregate, not listings (S2)

The currency exchange response documents `next_change_id` and `markets`, each
market carrying `league`, `market_id`, `market_pair`, `volume_traded`,
`lowest_stock`, `highest_stock`, `lowest_ratio` and `highest_ratio`.

That is an aggregate exchange rate series. It carries no item, no price for an
item, no listing identifier and no seller. It cannot populate a `Listing`.

### O7. Scopes available (S3)

Account: `account:profile`, `account:leagues`, `account:stashes`,
`account:characters`, `account:league_accounts`, `account:item_filter`.
Service: `service:leagues`, `service:leagues:ladder`, `service:pvp_matches`,
`service:pvp_matches:ladder`, `service:psapi`, `service:cxapi`.

No trade scope and no item-listing scope is documented. The `account:trade`
scope that `pob2-mcp/pob2mcp/poe_api.py` requests does not appear in S3.

### O8. Redirect URI rules (S3)

S3 states "Any redirect URIs must point to a secure (HTTPS-enabled) URI with a
registered domain controlled by the application owner. We cannot accept IP
addresses or localhost domains even for in-development projects." Public clients
"Must only use the Authorization Code (with PKCE) grant type and must use a
local redirect URI."

Observed: the two statements are both on S3 and they read as being in tension
for a public client. Inferred: nothing. Which redirect form a public client may
actually register is a registration-time question, and registration is closed
(O1), so it cannot be settled here.

### O9. Identification and rate limits (S1)

Required header format: `User-Agent: OAuth {$clientId}/{$version} (contact:
{$contact})`. The identifier is the application's own registered client id.

Limits are dynamic and carried per response in `X-Rate-Limit-Policy`,
`X-Rate-Limit-Rules`, `X-Rate-Limit-{rule}` (max hits : period seconds :
restricted seconds), `X-Rate-Limit-{rule}-State` and `Retry-After`. S1 states
"Exceeding these limits frequently will result in your application access being
revoked", and that repeated 4xx responses restrict access.

Observed: the header contract. Not observed: any concrete numeric limit, because
reading one requires issuing a request. Numbers must be read from live response
headers at implementation time, not assumed.

## What this evidence does not establish

- That any route works. Nothing here was executed.
- That registration will reopen, or on what terms.
- That the existing `pob2-mcp` transport would succeed if run. It was not run.
- Anything about third-party aggregators as a market source. Those are P03 and
  D02 territory, not this record.
