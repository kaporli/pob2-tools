# Shared data contracts

P01 implements these contracts as Python dataclasses plus JSON Schema files in `schemas/v1/`. A record not passing schema and semantic validation is not accepted into the normalized store. Raw acquisition is allowed before normalization. Every field listed below is required unless explicitly nullable or optional. Implement the named types first; adding a field requires a schema change and a migration test.

## Common conventions

- Persist UTF-8 JSON. Object keys use snake case. UTC timestamps use RFC 3339 with `Z`. Durations use seconds; internal scheduling uses integer microseconds. Distances must carry a declared unit and conversion evidence, never assume PoB radius is metres.
- Every persisted domain record has `schema_version: 1` (BuildSpec: 1 or 2, see below), `record_id`, `created_at` and `provenance_ids: string[]`. Use UUIDs for event/record IDs, SHA-256 for content identities. Lists may be empty only when semantically valid.
- Null means unknown/not supplied, never zero or false. Unknown required facts also produce a `DataGap`. Reject NaN, Infinity, negative durations and duplicate allocation IDs. Monetary values are decimal strings with original currency identifiers.
- Hash canonical JSON with sorted object keys, compact separators, no NaN, and UTF-8 encoding. Preserve order for rotations and skill groups; sort sets such as passive allocations by stable ID. Hash gameplay fields separately from metadata and source popularity.
- All cross-record references must resolve within the exported run or corpus. Validate them in a second semantic pass after schema validation.
- Human display names are not stable identifiers. Catalog IDs are namespaced by patch/catalog and native entity ID. Ambiguous names must remain unresolved.

## SourceDocument

| Field | Type and meaning |
|---|---|
| `provider`, `source_url`, `external_id` | Strings; URL and external ID may be null for local files. |
| `acquired_at`, `published_at`, `updated_at` | UTC; publication/update nullable and never copied from acquisition time. |
| `access_method` | `local_file`, `public_page`, `documented_api`, `provider_export`, `manual_capture`. |
| `media_type`, `blob_hash`, `byte_count` | Original payload descriptor; store original bytes once. |
| `acquisition_version`, `source_manifest_id` | Adapter version and capability record. |
| `declared_patch`, `author_id`, `locale` | Nullable metadata. Patch declaration is not verified compatibility. |
| `popularity` | List of `{kind, value, observed_at}`; empty means absent. Never interpret missing favorites as zero. |
| `redistribution` | `allowed`, `restricted`, `unknown`; preserve provenance even when only local storage is allowed. |

Network failure is an `AcquisitionResult` with status `ok`, `not_found`, `access_blocked`, `rate_limited`, `invalid_response`, `timeout`, or `unsupported_access`. A failed result has no fabricated SourceDocument. Store HTTP status when available, retry eligibility and redacted diagnostics.

## PatchProfile and GameCatalog

`PatchProfile` contains `game: poe2`, `realm`, `league_id`, `patch_id`, `patch_evidence_ids`, `resolved_at`, `pob_commit`, `pob_dirty_hash` (nullable), `catalog_hash`, `adapter_version`, `compatibility: verified|partial|unknown|stale`, `compatibility_evidence_ids` and a structured `character_rules` record.

`character_rules` includes legal level range, class/ascendancy relationships, skill/gem level limits, point budgets as functions/tables of explicit progression flags, slot definitions, support restrictions and weapon-set semantics. Each rule references evidence. Missing rules are gaps, not permissive defaults.

`GameCatalog` contains entity tables for classes, ascendancies, passive nodes/edges, gems and granted skills, items/bases/modifiers, slots and configuration variables. Each entity has a stable ID, display names/aliases, raw reference, and rule references. Preserve upstream data needed to reconstruct an entity; do not flatten modifiers into a few DPS totals.

## ItemInstance and Listing

`ItemInstance` contains `item_hash`, `catalog_hash`, `base_id` (nullable until resolved), `display_name`, `rarity`, `item_level` (nullable), `requirements`, `properties`, `modifiers`, `sockets`, `flags`, `raw_text`, `source_document_id` and `parse_status`.

Each modifier includes `category`, `source_position`, `text`, `native_id` (nullable), `resolved_effect_ids`, and `parse_status: resolved|unresolved|ambiguous`. Categories preserve implicit, explicit, enchant, rune, fractured, crafted, desecrated and unknown source categories. Preserve flags and ranges. Do not sum modifiers during parsing. Validate the actual categories present in the pinned data rather than assuming all exist in every patch.

`Listing` contains `listing_id`, `provider`, `realm`, `league_id`, `item_hash`, `price_amount` (nullable decimal string), `price_currency` (nullable), `listed_at` (nullable), `observed_at`, `last_checked_at`, `availability: observed|rechecked|unavailable|unknown`, `listing_url` (nullable) and `source_document_id`. Listing identity is separate from item identity. Two equal-stat items can be distinct purchasable instances; one listing cannot fill two slots simultaneously unless explicit quantity supports it.

## BuildSpec

| Field | Meaning |
|---|---|
| `build_hash`, `catalog_hash`, `declared_patch` | Identity and nullable source patch. |
| `name`, `class_id`, `ascendancy_id`, `level` | Ascendancy nullable when explicitly unallocated; unknown class prevents evaluation. |
| `progression` | Quest/reward flags and resulting normal/ascendancy budgets. No inferred full completion from level alone. |
| `equipment` | Map of slot ID to `{item_hash, listing_id: nullable}`. Explicit empty slot is null. |
| `weapon_sets` | Set IDs, hand-slot references and per-set passive allocations; supported rules come from catalog. |
| `passives` | Ordinary allocations, ascendancy allocations, choices such as attribute selection, and socketed entities. |
| `skill_groups` | Ordered groups with IDs, enabled flags, skill/gem IDs, levels, quality, support IDs, source item references and set bindings. Preserve trigger nesting and main-skill selection. |
| `config` | Typed imported PoB variables with origins `source`, `scenario`, `derived`, or `manual`. Imported conditions are claims until verified. |
| `rotation_ids` | Named clear and boss policies. May be empty on import, which creates a missing-rotation gap. |
| `source_document_ids`, `variant_id`, `family_id` | Provenance and deduplication metadata; variant/family nullable until assigned. |
| `parse_status`, `unresolved_refs` | `complete`, `partial`, or `invalid`; structured unresolved paths. |
| `main_skill_group` | Schema version 2. Index of the skill group PoB evaluates as main; null when there are no groups or the source does not say. |

BuildSpec schema version 2 adds `main_skill_group` and, on every skill entry, `supports`: one `{support_id, gem_id, level, quality, enabled}` per `support_ids` entry, in the same order. A null setting is unknown, makes the record `partial` and blocks a recommended export; it is never filled with a PoB default. Version 1 records stay readable and keep their hashes. Upgrading one (`domain/migrate.py`) creates a new record whose support settings are unknown. The version 2 identity adds `identity_version: 2`, `main_skill_group` and the support settings.

Hash equipment properties, allocations, progression, enabled groups, set bindings and gameplay config. Exclude name, creator, popularity, listing price and timestamps. Rotation identity is separate but included in evaluation identity. Preserve original XML/code blobs so metadata-only import never masquerades as a reconstructed build.

## ParseResult

Fields: `status: complete|partial|invalid|unsupported_format`, `parser_id`, `parser_version`, `source_document_id`, `record_ids`, `field_coverage`, `issues` and `raw_extensions`. Each issue has `code`, JSON field path, source locator and explanation. `field_coverage` records present/resolved/missing counts by domain, not a single misleading percentage. Unknown additional source fields remain in raw data; critical unknown fields create issues.

## MechanicClaim and MechanicRule

A `MechanicClaim` has `subject_ids`, `claim_text`, `source_document_id`, `source_locator`, `applies_to_patch`, `dependencies`, `status: unverified|corroborated|contradicted|superseded`, and `evidence_ids`. Automatic text extraction always creates `unverified` claims. Exact source excerpts are short and retain attribution; extracted text must not become executable Lua or Python.

A `MechanicRule` has `mechanic_id`, `version`, `patch_profile_ids`, `required_input_paths`, `dependency_ids`, `implementation_ref`, `owner: pob|simulator|scenario`, `support: implemented|partial|unsupported|unknown`, `validation: untested|fixture_checked|gameplay_checked|contradicted|stale`, `evidence_ids`, `limitations`, and `tolerances`. One owner calculates each effect to prevent double counting.

## DataGap

Fields: `gap_id`, `kind: missing_input|unresolved_entity|unsupported_rule|conflicting_evidence|stale_patch|unvalidated_prediction|access_blocked`, `subject_ids`, `field_paths`, `mechanic_ids`, `severity: blocking|ranking_sensitive|informational`, `explanation`, `needed_evidence`, `collection_method`, `affected_evaluation_ids`, `sensitivity_result_id` (nullable), `status: open|resolved|superseded`, `resolution_evidence_ids`.

`needed_evidence` must be specific: for example, damage events and timestamps for a named interaction under stated conditions. “Need more data” is not acceptable. `collection_method` can be an import request, source lookup, parser implementation, engine implementation or manual measurement procedure. Unknown interactions that have never been represented cannot be guaranteed detectable; reports must state scope.

## ScenarioSpec and RotationPolicy

`ScenarioSpec` includes `scenario_id`, `version`, `category: clear|boss`, `kind: synthetic|representative`, `patch_profile_id`, `target_entities`, `initial_state`, `event_schedule`, `spatial_model_id`, `movement_model_id`, `duration_limit_s`, `completion_condition`, `incoming_damage_model_id`, `allowed_preparation`, `rng_seeds`, `reference_build_id`, `reference_result_id`, `capability_floor_ratio`, `survival_gates`, `resource_gates`, `evidence_ids` and `validation_status`.

`RotationPolicy` is a bounded priority list, not arbitrary source code. Each rule contains a stable action ID, allowed target selector, weapon set, and structured predicates using `all`, `any`, comparisons and catalog state paths. Actions are `use_skill`, `switch_weapon_set`, `move`, or `wait`. Costs and durations come from mechanic rules. An unavailable action is skipped with a reason. If none can execute, advance to the next relevant event or end at the limit; never busy-loop.

P07 implements the finite predicate vocabulary and rejects unknown operators. Support scheduled rotations as a simple fixture representation. Default encounter policies may differ between clear and boss while equipment remains the same.

## EvaluationResult

Fields: `evaluation_id`, `cache_key`, `build_hash`, `rotation_hash`, `scenario_id`, `manifest_id`, `fidelity: screen|detailed`, `seed`, `status`, `legality: legal|illegal|unknown`, `coverage: supported|partial|unsupported`, `validation: synthetic_only|model_estimate|gameplay_validated|stale`, `metrics`, `gap_ids`, `assumption_ids`, `rule_ids`, `trace_blob_hash`, `duration_ms`, `error` (nullable).

Metrics include `completion: success|timeout|death|unknown`, `completion_time_s` (nullable), `damage_dealt`, `resource_starvation_s`, `preparation_time_s`, `actions_per_minute`, `weapon_switches`, `minimum_resources`, and declared survival outputs. Metrics absent from the implementation are null with gaps. A calculation of peak DPS cannot populate completion time without an encounter model.

An `AggregateResult` contains category scores, balanced score, per-scenario gates, `eligible`, `strength_label`, `recommendation_status`, sensitivity references and evaluation IDs. Invalid/unknown candidates have nullable scores and explicit exclusion reasons. Search uses provisional estimates in a separate archive; only qualified detailed results enter recommendation ranking.

**Spec 1.1 extension (P08-T01.1, repaired and self-verified in PR #11):** AggregateResult schema version 2 adds `objective_version`, `objective_hash`, `objective_metrics`, `objective_score` and `objective_gap_ids`. `objective_id`/`objective_version` must name a registered objective (`pob2opt/domain/objectives.py`: `balanced_score` v1, `flicker_sustained_dps` v1); unknown pairs are refused. `objective_metrics` holds exactly the objective's metric names (`flicker_sustained_dps`, `flicker_burst_dps`). `objective_score` must equal the objective's score metric, or `balanced_score` for the balanced objective; it is never filled from another score. A null metric or score needs a gap, and an eligible candidate needs a score. Version 1 aggregates keep their free-form `objective_id` and are not ranked by a version 2 objective. Keep `balanced_score` dimensionless; never store DPS there. Reference-checked storage resolves the manifest from the store or pending batch and enforces objective ID/version/hash binding. Corpus and bundle validation expose conflicts left through explicit staging. Ranking and damage attribution remain P07 work.

## Observation

Fields: `observation_id`, `build_hash`, `patch_profile_id`, `scenario_id`, `rotation_id`, `operator_id` (pseudonymous), `trial_id`, `measured_at`, `measurement_method`, `metrics`, `raw_evidence_ids`, `measurement_uncertainty`, `deviations`, `dataset_split: calibration|validation|holdout`, `build_family_id`, `review_status`.

PoB outputs, guide claims and ladder level are not independent gameplay observations. Store failed and censored trials; no selecting only the fastest kill. An unknown enemy health value cannot produce a measured DPS label from kill time alone.

## RunManifest and Checkpoint

`RunManifest` includes `run_id`, `spec_version`, `software_commit`, `software_dirty_hash`, `resolved_request`, `patch_profile_id`, all dependency hashes from architecture, ordered source/market snapshot IDs, RNG seed, search parameters, worker and memory limits, time budget, hardware summary, scenario suite ID, accepted review-gate references, creation timestamp and availability mode.

`Checkpoint` contains manifest hash, completed generation, candidate archive hashes, queued/completed task IDs, RNG state per generator, accumulated search time, next generation ID, and stop status. Store an atomic checkpoint after each generation and at cancellation. The database holds task results so losing the newest checkpoint does not lose completed evaluations.

## ReviewRecord

Fields: `task_or_gate_id`, `spec_version`, `implementation_commit`, `verdict: accepted|changes_required|blocked|superseded`, `reviewer`, `reviewed_at`, `commands_run`, `evidence_paths`, `findings`, `residual_limits`, `invalidated_gates`, `next_task_ids`. Engineer completion and reviewer acceptance are distinct records.
