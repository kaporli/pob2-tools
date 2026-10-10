# D02: per-source capability manifests

Status: proposed, unresolved. Raised by P03-T01. Specification version 1.0.

## The question

`docs/specs/research.md` holds D02 open: one capability manifest for each named
source, with representative saved input, before that source's automatic adapter
may be built. Which access method is permitted for Mobalytics, Maxroll and
poe.ninja, what can each actually supply, and which provider does P03-T03 build
first?

## Sources consulted

Inspected on 2026-10-10 with the Claude Code fetch tool. No credentials, no
cookies, no login, no crawl, no provider contacted, no undocumented endpoint
called. Seventeen requests in total across the three provider hosts.

- `https://mobalytics.gg/robots.txt`, `/poe-2/builds`, `/poe-2/builds/`,
  `/poe-2/builds/twister-gemling-legionnaire`, `/terms/`, `/sitemap.xml`,
  `/poe-2/guides/build-files`
- `https://maxroll.gg/robots.txt`, and nothing else on that host, on purpose
- `https://poe.ninja/robots.txt`, `/poe2/builds` twice, `/docs`, `/docs/api`,
  `/docs/pob-rules-poe2`, `/poe1/data`, `/poe2/api/economy/leagues`, `/privacy`
- `https://pobb.in/robots.txt` and the `pasteofexile` README, because a
  Mobalytics guide is reported to link there
- `https://www.ziffdavis.com/terms-of-use`, which this client could not fetch
- Public web search over `mobalytics.gg` and `maxroll.gg`, used only to name
  candidate records, never as an acquisition route
- The prior inspection recorded in `docs/specs/research.md` on 2026-10-04

Full per-request results are in `docs/evidence/P03/mobalytics-capabilities.json`,
`maxroll-capabilities.json` and `poe-ninja-capabilities.json`.

## What was actually observed

**Mobalytics.** `robots.txt` returned 200 and permits `/poe-2/`: `User-agent: *`
with `Allow: /`, no agent-specific group, nothing covering the build paths. Every
HTML path requested then returned HTTP 403 to this client, including the listing,
the guide page that `research.md` recorded as readable on 2026-10-04, the terms
page, and the sitemap that `robots.txt` itself advertises. So the published
policy permits and the edge refuses. No field, no export, no pagination
behaviour and no record of any category was observed. A public search index
shows guide titles carrying a `0.5.5` patch label, authors and October 2026
update dates, and reports that guides offer a build-file download and a pobb.in
link. That index is not an acquisition route and shows no item or tree data.

**Maxroll.** `robots.txt` returned 200 and prohibits this twice over. A header
comment states that using any robot, crawler or other tool to scrape, harvest,
extract or retrieve content by automated means is prohibited without written
permission, and names data-set creation and AI use among the prohibited uses.
One group lists roughly two hundred automation agents, `ClaudeBot`,
`Claude-User`, `Claude-Code`, `Claude-Web`, `anthropic-ai` and `Scrapy` among
them, and ends with `Disallow: /`. Separately, the `User-agent: *` group
disallows `/poe2/planner/*`, which is where this provider holds the structured
build data. No further request was made to that host. The linked Ziff Davis
terms document was not retrievable, which does not matter: the robots comment is
itself the operator's statement.

**poe.ninja.** No `robots.txt` is served, 404. `/poe2/builds` returns 200 with a
navigation and footer shell and no character row, so a public-page adapter would
acquire an empty document from a success status. The provider's own API
reference settles the rest in writing: "The economy overview endpoints documented
on this page are the supported public surface of the poe.ninja API." and "The
builds / profiles API, and every other non-economy endpoint (character, Path of
Building, authentication), are internal. They are undocumented, unsupported, and
not available for third-party use." One stated reason is player privacy: players
who hide their characters would be bypassed. The documented economy surface does
work: `GET /poe2/api/economy/leagues` returned 200 and six league objects. That
is market data, not build data.

Representative records: of the five categories, zero were inspected at any
provider. Mobalytics refused the client, Maxroll was not requested, poe.ninja
served no record. For poe.ninja the `multiple_variants` category is recorded as
not applicable rather than blocked, because that provider publishes ladder
snapshots and a snapshot has no author-declared variants.

## Proposed choice

1. Accept the three manifests as the D02 record for these sources. Each carries
   separate `supported` flags for listing metadata, full build data and
   explanatory prose. All nine are false today.
2. No automatic provider adapter is approved. P03-T03 has no provider to build
   against, and the automatic portion of P03-T04 is blocked for all three.
3. Keep Mobalytics as the first candidate, with the reason stated plainly: it is
   the only one of the three whose published policy permits automated access to
   its build pages. Its block is an edge filter on this client, not a
   prohibition, so it is the only one that evidence could still open. That is a
   ranking of prospects, not a usable integration.
4. Rank poe.ninja second and Maxroll last. poe.ninja permits a documented API but
   has closed the build surface deliberately and for a privacy reason. Maxroll
   prohibits the retrieval itself. Neither can be opened by more inspection.
5. Build the near-term corpus through `local_file` import in P03-T02: build files
   and PoB codes an operator already holds, with provider and redistribution
   recorded per document. P03-T05 corpus targets must be re-scoped against that,
   since 30 variants from at least two sources cannot come from automatic
   acquisition at present.
6. Redistribution: Maxroll `restricted` on the operator's explicit statement,
   Mobalytics `unknown` because its terms page refused this client, poe.ninja
   `unknown` because no licence statement was found. All three are handled as
   `restricted` locally. No provider content is stored in this repository.
7. Refuse, as part of this decision and not by later judgement: retrying the
   Mobalytics 403 under a different user agent, reading the network traffic of
   the poe.ninja builds page to find the endpoint behind it, any request to
   maxroll.gg, and contacting any provider for permission. The last is an owner
   decision.

## Open sub-question for the reviewer

Mobalytics is reachable by a human browser and refuses this toolchain. Deciding
whether a browser-equivalent client is a legitimate adapter, or an attempt to
defeat a filter the operator installed on purpose, is a judgement this task does
not make. If the reviewer wants the question answered, the next step is reading
the Mobalytics terms, which needs a client that page will answer.

## Contracts affected

None changed. The manifests populate existing fields:

- `SourceDocument.access_method`: `local_file` is the only method any provider
  supports today. `public_page` and `documented_api` stay unused for builds.
- `SourceDocument.source_manifest_id`: `p03-t01-mobalytics-2026-10-10`,
  `p03-t01-maxroll-2026-10-10`, `p03-t01-poe-ninja-2026-10-10`.
- `SourceDocument.redistribution`: as item 6.
- `AcquisitionResult.status`: `unsupported_access` for Maxroll and for poe.ninja
  builds, `access_blocked` for Mobalytics. A 200 over an empty page shell is
  `invalid_response`, never `ok` with an empty build.
- `docs/specs/interfaces.md` operational defaults stand. poe.ninja's caching and
  polling rules are stricter and take precedence for that host.

## Reviewer

Unresolved. The reviewing assistant resolves the technical parts. Item 3 and the
open sub-question may need Elias, as concrete alternatives, if the reviewer
judges that evidence cannot settle them.

## Date

Proposed 2026-10-10 by the P03-T01 engineer.
