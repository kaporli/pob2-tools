# Command and service interfaces

These are target interfaces for implementation, not commands available today. Preserve legacy commands under their existing paths until migration review. New commands must not silently invoke the old phase pipeline.

## CLI

Implement argparse subcommands. JSON is the machine-readable output; status prose goes to stderr. Paths resolve against the caller's working directory before engine startup.

| Command | Input and output | Owning task |
|---|---|---|
| `pob2opt doctor --json` | Inspect Python, paths, runtime and selected profile; output structured checks without modifying a checkout. | P00-T03 |
| `pob2opt source inspect --provider NAME --out DIR` | Bounded capability report; never an automatic full crawl. | P03-T01 |
| `pob2opt ingest --provider NAME --input PATH_OR_URL --corpus DIR` | Acquire permitted input, preserve raw payload; return source IDs/status. | P03-T02 |
| `pob2opt parse --source ID --corpus DIR` | Create canonical records and ParseResult from stored bytes. No network needed. | P04-T01 |
| `pob2opt catalog export --profile FILE --out DIR` | Export pinned PoB entities and compatibility evidence. | P02-T02 |
| `pob2opt market import --input FILE --corpus DIR` | Import item/listing records, preserving original currency and observed status. | P05-T02 |
| `pob2opt market refresh --snapshot ID --corpus DIR` | Use approved provider; otherwise return `unsupported_access`. | P05-T04 |
| `pob2opt prepare --request FILE --out DIR` | Resolve patch, league, catalog, corpus and item snapshots; write immutable manifest and gaps. Does not start search. | P08-T01 |
| `pob2opt evaluate --build FILE --manifest FILE --out DIR` | Validate and evaluate exact build/rotations over the pinned suite. | P07-T05 |
| `pob2opt search --manifest FILE` | Resume or start the run's search; write database/checkpoints/artifacts. | P08-T04 |
| `pob2opt resume --run DIR` | Validate original manifest and restore unfinished generation. | P08-T04 |
| `pob2opt report --run DIR` | Regenerate JSON/Markdown from stored accepted evaluations; no hidden network calls. | P10-T01 |
| `pob2opt observe import --input FILE --corpus DIR` | Validate independent observations and retain raw evidence. | P09-T02 |
| `pob2opt benchmark --suite FILE --out DIR` | Run frozen evaluation/search campaign and compare baselines. | P09-T04 |

The accepted setup must provide `python -m pob2opt.cli ...` with equivalent behavior for environments without a console-script entry point.

Exit codes: `0` requested operation completed, `2` invalid request/schema, `3` missing dependency/access/coverage prevents requested operation, `4` operational/internal failure, `5` completed search with no eligible recommendation, `130` user cancellation after checkpoint. A diagnostic doctor result can use `3` for missing engine while reporting passing offline checks.

## Request file

Required request keys: `schema_version`, `game`, `class`, `level`, `patch_selection`, `league_selection`, `mode`, `budget`, `scenario_suite`, `catalog_profile`, `corpus_path`, `item_pool_ids`, `seed`, `time_budget_s`, `workers`, `memory_limit_mb`, `allow_weapon_switch`, `allow_external_gear_swap`, `execution_profile`.

Product defaults are in `product.md`. `patch_selection` may be `current` only at prepare time; resolve to an immutable PatchProfile before search. `league_selection` works similarly. `workers` may be `auto` at prepare time and must become a measured bounded integer in the manifest. `mode` is `market`, `offline_items`, or `theoretical`. Null `budget` means no spending limit. Empty required item pool is an explicit unresolved input, not a request to invent equipment.

`theoretical` mode requires item-generation legality rules and its own accepted scope; disable it until those rules are present. Do not reuse hand-written rare-item strings as proof of craftability.

## Python boundaries

Use these names and parameter meanings. All return validated records, not loosely interpreted dictionaries at call sites.

| Boundary | Contract |
|---|---|
| `SourceAdapter.inspect()` | Return capability manifest with supported methods, fields, limitations and evidence. |
| `SourceAdapter.acquire(source_ref, context)` | Return AcquisitionResult with immutable payload reference or typed failure. |
| `Parser.parse(document, catalog)` | Return ParseResult and proposed normalized records; no network side effects. |
| `CatalogProvider.export(profile)` | Return GameCatalog plus compatibility evidence. |
| `MarketProvider.query(query_spec, context)` | Return listings, pagination state, truncation and scope; supported providers only. |
| `MarketProvider.refresh(listing_ids, context)` | Return per-listing state, preserving failures separately from absence. |
| `LegalityValidator.validate(build, profile)` | Return violations, unknowns and derived resource/point constraints. |
| `CoverageAnalyzer.analyze(build, rotation, scenario, registry)` | Return dependency closure, support states and DataGaps. |
| `EngineAdapter.primitives(build, state, profile)` | Return per-action primitive values with units, provenance and semantic ownership. |
| `Evaluator.evaluate(build, rotation, scenario, context)` | Return EvaluationResult and trace reference. |
| `Ranker.aggregate(results, suite, objective)` | Return AggregateResult, never fill missing scenarios implicitly. |
| `CandidateGenerator.propose(archive, catalog, pool, rng)` | Return immutable BuildSpec/rotation pairs and mutation lineage. |
| `RunStore.commit_evaluation(task_id, result)` | Transactional idempotent write; coordinator only. |

These can be protocols or simple interfaces. Do not require remote RPC. MCP server tools should call the same application services when added; no separate ranking implementation in `server.py`.

## Operational defaults

HTTP acquisition uses 10-second connection and 30-second read timeouts, size limit 20 MiB and at most three attempts for classified transient failures. Provider-imposed stricter limits take precedence. Respect full advertised retry delays by scheduling work later; do not truncate them. Resume cursors and cached unchanged pages avoid repeated acquisition.

For compressed build codes, cap expanded payload at 20 MiB and reject malformed encoding or unsafe XML constructs. Follow only approved provider/link hosts; local imports remain possible. Never execute scripts, Lua or shell text contained in a guide or imported record.

Engine evaluation default timeout is 120 seconds per detailed scenario and 30 seconds per screen, configurable and recorded. P00 measurement may justify revised defaults through review. Long provider waits and individual evaluation timeouts must not freeze coordinator cancellation or progress reporting.
