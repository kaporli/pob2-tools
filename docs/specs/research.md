# Research and repository findings

Inspection date: 2026-10-04. This is a bounded source and code inspection. No PoB calculations, authenticated trade requests, broad website crawl, or gameplay measurements were performed. The current patch number has not been established from an authoritative complete patch chain; the implementation must resolve it in P02.

## Repository evidence

Paths are relative to repository root. The listed problems are observations from source inspection, not all reproduced defects. P00 and P02 must characterize behavior before repair.

| ID | Location | Observed behavior | Original proposed response |
|---|---|---|---|
| F01 | `external/PathOfBuilding-PoE2`, `.gitmodules` | Tracked submodule is absent in this working tree; no `POB2_ROOT` override was found during inspection. | P00 documents restoration/configuration; real engine tests remain unexecuted until available. |
| F02 | `pob2opt/phases.py`, `task_tier` | Final concentration input prefers raw `realistic_dps` over rotation-adjusted DPS. | Reproduce loss of action-time penalties and establish one evaluation path. |
| F03 | `pob2opt/policy.py` | Keyword condition caps, assumed recast periods, default gauge durations and an uptime floor. | Replace production uses with evidenced rules or explicit unsupported status. |
| F04 | `pob2opt/lua/tree_lib.lua`, `opt_helpers.lua` | Greedy supports and immediate DPS tree growth; objective differs from balanced clear/boss behavior. | Retain as baseline; replace production search and rank separately. |
| F05 | `pob2opt/cli.py` | Small finalist lists, hardcoded league, point/reward assumptions, phase caching by filename. | Versioned manifest, derived budgets, larger adaptive search and cache identity. |
| F06 | `pob2opt/calibration.json`, `ladder.py` | One checked-in observation; ladder conversion returns an empty list. | No broad calibration claims; independent observations project. |
| F07 | `pob2opt/harvest.py` | Small weapon-only samples, 60 exalted upper query, excludes other listing currencies, deduplicates by item name. | Unlimited-budget all-slot pool with correct identity and known sampling limits. |
| F08 | `pob2mcp/trade.py` | Uses website trade endpoints and session cookie; fixed waits and capped retry delay. | Establish supported access and rebuild status/rate handling; no assumed live capability. |
| F09 | `pob2mcp/poe_api.py` | Uses client ID `pob` and fixed scopes/callback assumptions. | Do not reuse another application's identity in the new integration; provide own accepted identity or import fallback. |
| F10 | `pob2mcp/engine.py` | Native Lua state and process-wide `os.chdir`; lifecycle/exception behavior needs characterization. | Worker isolation, deterministic close/restart and timeout handling. |
| F11 | `pob2opt/lua/opt_helpers.lua`, `OPT_setup` | Resets nodes and equipment and disables groups. | Separate blank candidate construction from faithful imported-build evaluation. |
| F12 | `pob2mcp/bootstrap.lua`, item conversion | Several modifier arrays are initialized but not emitted in the inspected conversion path. | Golden fixtures for every supported modifier category; no silent loss. |
| F13 | `pob2-mcp/test_engine.py` | Print-based smoke script with a machine-specific import path. | Assertion-based portable fixture tests and separate engine marker. |

## External evidence

| Source | What was observed | What remains unverified |
|---|---|---|
| [GGG developer overview](https://www.pathofexile.com/developer/docs) | Only documented resources are supported; internal endpoint access is excluded. New application registration was unavailable on the inspected page. | A permitted automated listing-access route for this application. |
| [GGG API reference](https://www.pathofexile.com/developer/docs/reference) | Documents PoE 2 account characters, league information and currency history, with limited PoE 2 coverage. | None of this proves arbitrary public character or live item-listing access. |
| [PoB upstream](https://github.com/PathOfBuildingCommunity/PathOfBuilding-PoE2) | Existing calculation engine; upstream distinguishes supported and unsupported modifiers. | Compatibility and exact mechanics behavior for our future pinned revision. |
| [poe.ninja source description](https://poe.ninja/posts/launching-builds) | Describes character configurations and PoB-derived statistics, with build sharing. | A documented complete acquisition interface and present-day field coverage. |
| [poe.ninja builds page](https://poe.ninja/poe2/builds) | Browser extraction returned no body content. | Do not infer data absence or API access from that result. |
| [Mobalytics listing](https://mobalytics.gg/poe-2/builds) | Public listing exposes patch/type labels and favorites metadata. | Bulk export, pagination completeness, and complete structured item/tree data. |
| [Mobalytics representative guide](https://mobalytics.gg/poe-2/builds/twister-gemling-legionnaire) | A guide page was accessible with substantial content. | A parser has not been written or shown to reconstruct its full build. |
| [Maxroll guide index](https://maxroll.gg/poe2/build-guides) | The research browser could not open this URL. | Layout, permitted automation, exports and coverage all need a bounded capability study. |

The source findings justify separate adapter capability studies. They do not justify inventing private endpoint URLs or declaring an integration complete from a fetched title. No provider is assumed to expose votes, DPS, rotations and full equipment in the same format.

## Follow-up references

These findings describe the 2026-10-04 inspection. Current task/decision disposition is maintained in the [GitHub delivery index](https://github.com/kaporli/pob2-tools/issues/23); [decision records](../decisions/README.md) preserve dated rationale.
