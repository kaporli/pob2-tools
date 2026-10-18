# Evidence

Durable artifacts a reviewer can inspect without rerunning the work, organised
by task or gate: `docs/evidence/P00/`, `docs/evidence/G0/`, and so on.
`docs/specs/review.md` requires this, because ignored `runs/` files alone are
not enough for another engineer's handoff.

What belongs here: environment records, characterization results, measurement
JSON, fixture inventories, and content-addressed references (path plus SHA-256)
to anything too large to commit.

What must never go here: credentials, cookies, OAuth tokens, or any redistributed
third-party data this repository has no right to publish. Mark anything
`redacted` or `restricted` when it may be reviewed locally but not shared.

Every artifact must say what kind of evidence it is - synthetic, PoB-derived, or
independently measured. Those are different claims and the specification keeps
them separate.

## Current contents

| Path | Task | What it is |
|---|---|---|
| `P00/environment.md` | P00-T01 | Machine, Python, packages, PoB checkout, existing runs |
| `P00/baseline/` | P00-T01 | Inventory and copies of pre-existing legacy run output; historical, not validated |
| `P00/findings.md` | P00-T04 | Characterization of research findings F02, F05, F10, F11, F12 and four new observations |
| `P00/measurements.json` | P00-T04 | Engine timings, memory and A-B-A, with hardware |
| `P01/validation.json` | P01 | Offline test runs on CPython 3.10 and 3.12, plus the schema, lock, packaging and example checks |
| `P01/demo-run.json` | P01 | Recorded output of the end-to-end example: ingest, bundle, corpus disconnect, interruption, resume, cache and legacy import |
| `P01/inspection-queries.md` | P01-T05 | The documented read-only queries a reviewer runs against a run database, with the example's output |
| `P01/review-ae4303e-probes.py` | P01 review | The reviewer's adversarial probe script for commit `ae4303e`; kept unchanged |
| `P01/review-ae4303e.json` | P01 review | The observations that script recorded, which the repair reproduced before fixing |
| `P01/review-repair-probes.py` | P01 repair | The same questions asked of the repaired code |
| `P02/lifecycle.json` | P02-T01 | Engine boundary behaviour: the three offline failure probes (synthetic), then real-engine identity, exact versus blank loading, A-B-A with B read, state isolation, document provenance and forced termination (PoB-derived) |
| `P02/review-eca7afe-adversarial-probes.py` | P02-T01 review | The seven adversarial probes run against `eca7afe`; kept unchanged |
| `P02/review-eca7afe-adversarial.json` | P02-T01 review | What those probes recorded before the repairs, mapped to findings R01 and R03 to R06 |
| `P02/review-eca7afe-probes.json` | P02-T01 review | A parallel review's probe output for the same commit, written by another run; the source of findings R10 and R11. Its probe script was lost (see the review) |
| `P02/review_eca7afe_workers.py` | P02-T01 review | The slow-load synthetic worker that parallel set used |
| `P02/review-eca7afe-recovery-probes.py` | P02-T01 repair | Reproduction of R10 and R11 at HEAD |
| `P02/review-eca7afe-recovery.json` | P02-T01 repair | Those two cases before and after the repair |
| `P02/catalog-export.json` | P02-T02 | PoB-derived. What one real `catalog export` produced: entity counts, catalog hash, evaluation context hash, the compatibility report and why the verdict is `partial`, the character rules, and every gap with its needed evidence |
| `P02/catalog-rows-slice.json` | P02-T02 | PoB-derived, and a slice, not the catalog. Bounded engine rows so the offline tests run the real export with no PoB. A catalog hash computed from it is not an export's catalog hash. Marked `restricted`: third-party game data, reviewable locally. Regenerated in P02-T02.1 from a clean checkout with adapter `p02.2` |
| `P02/catalog-profile-request.json` | P02-T02 | The `--profile` request the reference export uses |
| `P02/release/` | P02-T02 | Captures of official Path of Exile 2 patch-notes pages, one file per page, `restricted`. The export resolves the live patch from these and from nothing else; see the README there |
| `P02-T02.1/README.md` | P02-T02.1 | Current-patch and Flicker Strike compatibility: official pages fetched, upstream PoB check, the clean export's verdict and every retained gap, test runs |
| `P02-T02.1/catalog-export.json` | P02-T02.1 | PoB-derived. The export from a clean checkout of the pinned commit with the verbatim capture; same format as `P02/catalog-export.json`, which is kept as P02-T02's record |
| `P02-T02.1/flicker-coverage.json` | P02-T02.1 | PoB-derived. Flicker Strike's catalog rows, its support list compared with PoB's answer in a build, and the three behaviour fixture documents and values |
| `P02-T02.1/official/` | P02-T02.1 | Byte captures of the official patch-notes index and the 0.5.5b, 0.5.5c and 0.5.5d staff posts, `restricted` |
| `P02/sample-build-ranger-quarterstaff.xml` | P02-T02 | PoB-derived. A build the pinned engine saved itself, used to show the exported entities resolve a real saved build. Its weapon rolls are invented |
| `P02/legality.json` | P02-T03 | Mixed, labelled per section. `synthetic`: the verdict, violations, unknowns and cited gaps for every fixture case, validated against a profile exported from invented rows. `pob_derived`: one exact import of the sample build in the pinned engine, the state the engine reported back, and the verdict on it. Neither section is a gameplay measurement, and an `unknown` verdict is a statement about this software's evidence |
| `P02/primitives.md` | P02-T04 | The primitive inventory: units, included and excluded effects, one owner per primitive, the controlled fixtures that settled each semantic, and the gaps that remain. PoB-derived, not gameplay evidence |
| `P02/primitives.json` | P02-T04 | What those thirteen fixtures returned, with the engine identity that produced them. Regenerated by `python scripts/p02_t04_primitive_fixtures.py` |
| `P02/roundtrips.json` | P02-T05 | Build and item round trips. The `synthetic` section is invented fixtures compared by our exporter against our importer; the `pob` section is a build PoB saved, exported, loaded back into the pinned engine and compared on canonical identity and deterministic primitives (PoB-derived) |
| `P02/roundtrip-synthetic.xml` | P02-T05 | The synthetic supported fixture's exported document. Synthetic: its class, skills and bases are invented, so the pinned PoB will load the file and find none of those entities. It is here to be read, not loaded |
| `P02/roundtrip-pob-export.xml` | P02-T05 | PoB-derived. Our export of a build PoB itself wrote; this is the document a reviewer loads in the pinned PoB. `docs/worklog/P02-T05.md` gives the two ways to load it |
| `P09/protocol-fields.json` | P09-T01 | Synthetic. Every `ScenarioSpec` field of the `p09-synthetic-v1` suite with where its value comes from: a specification source, a product default, a declared synthetic test constant, or an unresolved input naming its `DataGap`. 17 of the 26 rows are unresolved and none claims a direct measurement, because nothing in this suite was measured. Regenerated by `python scripts/p09_t01_suite.py` |
| `P09-T01.1/seed/` | P09-T01.1 | PoB-derived configuration from account-character import (D01: not market access, not a provider source). The owner's Flicker Strike export: two PoB documents, share code, raw items, socket groups, passive nodes, config input, PoB stats (`proxy_only`), and `manifest.json` with provenance, hashes and the owner's rotation verbatim. Not a trial; closes no performance gap |
| `P09-T01.1/mechanics.json` | P09-T01.1 | PoB-derived. Verbatim lines and passive nodes from a clean checkout of `ce566ea` for the Flicker Strike charge mechanics, with file hashes and line numbers. Regenerated by `python scripts/p09_t01_1_mechanics.py` |
| `P06/seed-engine-mod-support.json` | P06-T02 | PoB-derived. Per seed item and passive line whether PoB `ce566ea` (clean) parses it, and every applied config value with PoB's visibility test. Regenerated by `python scripts/p06_seed_engine_mod_support.py` |
| `P06/seed-coverage-*.json` | P06-T02 | Coverage of the seed for each of the five P09 scenarios under registry `p06-flicker-v1`: findings, DataGaps and the eligibility decision. No score. Regenerated by `python scripts/p06_seed_coverage.py` |
| `P06/offline-py312.txt`, `P06/offline-py310.txt` | P06 | Offline suite logs on Python 3.12 and 3.10 |
| `P06/repair-*` | P06, PR #19 repair | Negative control on `3cc334d`, the reviewer's probes on the repaired tree, and the native loadout check |
| `P07-T01/seed-evaluation.json`, `P07-T01/seed-as-imported-evaluation.json` | P07-T01 | PoB-derived, method `pob-community-v2`. The seed's coverage decision (not eligible), blocking gaps, labelled diagnostic, full action/impact trace and mana ledger. Regenerated by `python scripts/p07_t01_flicker_cycle.py` |
| `P07-T01/benchmark-parse-capture.json` | P07-T01 | PoB-derived parse verdicts and config rows for the scoring document, bound to it (P06 binding); carried by the frozen bundle |
| `P07-T01/fresh-worker-agreement.json` | P07-T01 | Two live captures on clean `ce566ea` in separate worker processes: identical values and evaluations, equal to the frozen bundle |
| `P07-T01/engine-py312.txt`, `P07-T01/offline-py312.txt`, `P07-T01/offline-py310.txt` | P07-T01 | Test logs |
| `P07-T01/repairs/*` | P07-T01 | Review PR-18-22 R4 to R7 regression cases on `db40827` (11 fail) and after repair (12 pass) |
| `P09-T01.1/scope-proposal.json` | P09-T01.1 | Proposal. Every ascendancy marked evidenced by seed, catalog possible or excluded, and three Flicker Strike variants with cited required mechanics. Product scope is the owner's decision |
| `P09-T01.1/pob-charge-table.json` | P09-T01.1 | PoB-derived. Seed Flicker Strike outputs at 0 to 5 forced charges, Charged Staff on and off, Whirling Assault use time and mana, Pinnacle enemy values. Inputs to `pob-cycle-v1`, not a result |
| `P09-T01.1/reference-ninja-25c49/` | P09-T01.1 | Community build from poe.ninja (share code, decode, PoB evaluation). Not a measurement |
| `P09-T01.1/README.md` | P09-T01.1 | What was captured, how, and the test runs |
| `P09-T01.2/replay.json` | P09-T01.2 | PoB-derived. The seed replayed through `EngineAdapter` on a clean checkout of `ce566ea`: 0 differences from P09-T01.1, a socket-group sweep, benchmark documents and read-only diagnostics. Regenerated by `python scripts/p09_t01_2_seed_replay.py` |
| `P09-T01.2/mechanics-rules.json` | P09-T01.2 | Cycle rules (resolved, conditional, blocking) with pinned engine citations, and the proposed damage ownership table. Regenerated by `python scripts/p09_t01_2_mechanics_rules.py` |
| `P09-T01.2/community-cycle.json` | P09-T01.2 | PoB-derived computation by the owner's method `pob-community-v2` (D07 amendment 2): 120 s timeline, burst, mana ledger, plain PoB numbers beside. Not a supported score. Regenerated by `python scripts/p09_t01_2_community_cycle.py` |
| `P09-T01.2/web-evidence.json` | P09-T01.2 | Secondary web text with URL and date; pages that refused automated access |
| `P09-T01.2/README.md`, `offline-py312.txt`, `engine-py312.txt` | P09-T01.2 | Summary and test logs |
| `P05/access-observations.md` | P05-T01 | Documentary, `restricted`. The five published developer-documentation and terms pages read unauthenticated on 2026-10-10, with observed separated from inferred. Short quotes only where the wording is the finding; otherwise linked, not copied. No request was authenticated and no provider was contacted |
| `P05/transport-assumptions.md` | P05-T01 | Source inspection of `pob2-mcp/pob2mcp/trade.py` and `poe_api.py` at `c2c2d02`: twenty-two assumptions each module would make if run, checked against the published documentation. Neither module was imported or executed |
| `P03/mobalytics-capabilities.json` | P03-T01 | Independently observed external. What seven requests to mobalytics.gg on 2026-10-10 returned: robots.txt permits the build paths, every HTML path answered 403 to this client. No field, export, pagination or record of any category was confirmed. No provider content is stored; redistribution `unknown`, handled as `restricted` |
| `P03/maxroll-capabilities.json` | P03-T01 | Independently observed external. One request, to robots.txt, and nothing else on that host on purpose. It prohibits automated retrieval without written permission, disallows this client's agent family from the whole site and disallows `/poe2/planner/*` for every agent. Redistribution `restricted` on the operator's own statement |
| `P03/poe-ninja-capabilities.json` | P03-T01 | Independently observed external. Nine requests on 2026-10-10. The builds page serves a shell with no records, and the provider's API reference states in writing that the builds and profiles API is not available for third-party use. Carries the study's only reproducible acquisition, `GET /poe2/api/economy/leagues`, which is economy data and not a build |
| `P03/acquisition.json` | P03-T02 | Synthetic. What acquisition did with invented payloads and a scripted transport: the four input kinds and their hashes, the idempotency counts, the seven refusal cases with the blobs and documents each wrote (none), the credential probe, the limits actually applied, the retry schedule and the host policy's refusals. No provider was contacted. Regenerated by `python scripts/p03_t02_evidence.py` |
| `P04/parse-and-audit.json` | P04 | PoB-derived. Parse status, issues, coverage and variants for every P04 fixture, and the field audit: ten complete variants at 100% exact agreement, every partial and ambiguous case with all differences declared. Regenerated by `python scripts/p04_evidence.py` |
| `P04/offline-py312.txt`, `P04/offline-py310.txt` | P04 | Offline suite logs on Python 3.12 and 3.10 |
| `P04/engine-py312.txt` | P04 | Engine suite log against PoB `ce566ea`, including the P04 round trips |
| `P04/verification-context.json` | P04 | Branch, base commit, PoB checkout identity, interpreters and the commands behind the logs |
| `P05-T02/offline-py312.txt`, `P05-T02/offline-py310.txt` | P05-T02 | Offline suite logs on Python 3.12 and 3.10 after the item and listing import |
| `P05-T02/engine-py312.txt`, `P05-T02/engine-py312-run2.txt` | P05-T02 | Engine suite logs against PoB `ce566ea`: the first run stopped by the test-session memory guard in an existing P02 test, the second complete. Synthetic items, no gameplay measurement |
| `P05-T03/offline-py312.txt`, `P05-T03/offline-py310.txt` | P05-T03 | Offline suite logs on Python 3.12 and 3.10 after the equipment pools |
