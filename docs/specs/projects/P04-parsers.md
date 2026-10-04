# Parsing and build normalization

Project ID: P04. Dependencies: P01-T01/T02/T03 and stored P03 fixtures. Catalog resolution needs P02-T02; raw parsing can proceed with a synthetic catalog before it is accepted. Goal: turn heterogeneous inputs into faithful, explicitly incomplete where necessary, BuildSpec records.

## P04-T01 Implement format dispatch and PoB import parsing

Create format detection for XML, supported encoded PoB builds, provider JSON/export, item text and saved HTML. Choose a parser by explicit provider/format signature, not filename alone. Decode PoB sharing codes using the pinned upstream format; check compressed and expanded size and reject malformed/unsafe XML. Do not evaluate Lua or remote scripts from inputs.

Preserve build variants and selected equipment/tree/skill sets. Never merge a leveling tree with endgame equipment just because both occur on one page. Return ParseResult with exact field paths and original blob references.

Acceptance: valid round trip, truncated encoding, decompression limit, malformed XML, unknown format and multiple variants have fixtures. Parsing is deterministic and offline. Each variant has its own BuildSpec and links to the shared guide.

## P04-T02 Implement source parsers

Implement a separate parser for each P03-approved provider representation. Extract author/title/patch metadata, configuration references, gear, skills, supports, passives, rotations and explanatory claims only where present. Put unrecognized fields in preserved raw extensions and flag gameplay-relevant omissions.

Required fixtures per supported parser: complete build, missing gear, multiple variants, old patch, renamed/unknown entity, layout change and absent popularity. Actual structured data takes priority over display labels; conflicting sources create issues rather than overwrite one another.

Acceptance: hand-annotated expected records match extracted fields. A title plus a list of skill names is `partial`, not a complete build. Missing passive allocation blocks legal evaluation. A layout change creates a recognizable parser failure, not a zero-item complete build.

## P04-T03 Resolve entities against the patch catalog

Map native IDs first. For names, use patch-specific exact aliases with locale and entity type. If multiple candidates remain, return `ambiguous` with candidate IDs; no fuzzy automatic choice. Cross-patch migration creates a new BuildSpec and records changes; keep the original immutable. No silent substitution of a removed gem or passive.

Resolve item modifiers without collapsing their categories or inventing roll values. An item name without actual stats is a template claim, not an ItemInstance ready for calculation. Preserve unknown granted skills and weapon-set choices as gaps.

Acceptance: ambiguous names, renamed entities, stale tree IDs, unknown affixes and duplicate item names are covered. Complete supported imports pass P02 semantic round-trip checks. Partial records remain searchable in the corpus but do not enter recommendation evaluation.

## P04-T04 Extract and retrieve mechanics claims

Start with deterministic extraction of guide sections and explicit references. Store short sourced claims, subject entities, source locators and patch declarations. Add SQLite text search over titles/claim text and entity filters; no embedding service is required. If an LLM extraction experiment is later added, it emits the same unverified records and cannot create MechanicRules directly.

Acceptance: a reviewer can retrieve the original passage for each claim. Conflicting statements coexist with conflict status. No claim receives `gameplay_checked` because a guide has many favorites. Guide prose containing imperative instructions cannot alter acquisition policy or execute code.

## P04-T05 Deduplicate and audit the corpus

Exact dedup uses canonical gameplay hash. Family grouping initially uses reviewed labels based on main damage mechanism and enabling interactions; an engineer proposes labels and a domain reviewer checks them. Preserve individual variants, source lineage and creators even within a family. Family IDs serve sampling and holdout splits, not correctness decisions.

Audit ten complete variants plus every partial/ambiguous fixture. Compare against original source/export and list missing fields. Measure field-level exact agreement for gear rolls, skill levels/supports, allocations and set bindings.

Acceptance: all audited required gameplay fields match; any mismatch blocks parser acceptance until fixed or explicit partial status is returned. Identical copies from different creators do not count as independent evidence. A complete normalized build can be exported and inspected in the pinned PoB through P02.
