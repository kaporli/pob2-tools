# PoB adapter and correctness repairs

Project ID: P02. Dependencies: G0 and P01-T01/T02. P02-T04/T05 also require P01 storage. Goal: faithfully evaluate a declared build with a pinned engine, and stop treating legacy heuristic scores as trustworthy combat results.

## P02-T01 Isolate and control the engine lifecycle

Refactor engine calls behind `EngineAdapter` and one-engine-per-process workers. Add deterministic close/error handling for native state and worker replacement after timeout/crash. Keep the parent's working directory unchanged. Resolve fixture/output paths before spawn. Define `load_exact_build` separately from `create_blank_build`; exact loading must not call `OPT_setup`.

Acceptance: A-B-A results agree within `1e-6` relative or `1e-9` absolute tolerance for deterministic primitives. Imported gear/tree/groups remain present. Forced worker termination creates a typed error and permits a fresh worker to finish a subsequent task. No reset masquerades as a new process after a native crash.

## P02-T02 Export a versioned catalog and patch profile

Implement `catalog export` using typed Lua bridge operations to enumerate catalog entities, IDs, configuration metadata and tree relationships. Record actual upstream commit and working-tree hash. Resolve current game patch from official release evidence; store that evidence. Compare catalog availability and behavior against a fixed compatibility fixture set; a matching version label alone is insufficient.

Create explicit class/ascendancy, level, quest-reward and support-slot rules. If upstream data lacks an unlock/reward rule, record a gap and a sourced rule task. Do not preserve the existing level-based reward guesses as validated rules.

Acceptance: exported entities resolve sample imported builds; duplicate display names remain distinct; changing upstream commit changes context identity. Unknown current patch or unsupported new content yields `partial`/`unknown`, not verified compatibility. Historical pinned profiles remain usable as historical profiles.

## P02-T03 Implement legality validation

Validate class/ascendancy membership, point budgets, connected passive allocation, attribute choices, equipment/hand conflicts, level and attribute requirements, skill/support restrictions, reservation resources, and weapon-set-specific constraints from catalog rules. Validate socketed items and item-granted skills when present. Verify allocation and equipment after PoB import, because permissive import is not proof of legality.

Return illegal versus unknown separately. Attribute/Spirit checks alone cannot establish overall legality. Detect unsupported theoretical item construction; sourced market items still require level/slot checks.

Acceptance: independent fixtures violate each listed rule individually and in a combined case; validator names each violation without silently repairing the build. Legal boundary values pass. Unknown unlock rule gives `unknown`, never automatic acceptance.

## P02-T04 Expose primitive semantics and repair scoring paths

Inventory every consumed PoB output: damage per hit/use, damage over time units, attack/cast time, resource cost, cooldown, hit probability, target count and defenses. For each record units, included effects and excluded effects in `docs/evidence/P02/primitives.md`. Confirm with controlled fixtures whether projectile overlap, trigger cadence and DoT duration are already included; do not infer from a field name.

Reproduce and fix the F02 path that drops rotation correction. Centralize legacy arithmetic enough to prevent that regression while P07 replaces it. Rename legacy floor/ceiling outputs to condition-off/condition-on estimates; retain deprecated aliases only with explicit legacy status. Remove production fallbacks that replace unknown metrics with favorable constants.

Acceptance: increasing setup time reduces sustained performance in a controlled fixture; enabling an unrelated condition does not reset timing penalties; each primitive used by P07 has one declared owner and units. Missing native output is a gap. No new production report reads a legacy `honest_*` field as validated truth.

## P02-T05 Verify build and item round trips

Implement export/import checks against semantic BuildSpec identity. Test enabled/disabled groups, multiple variants, main skill, trigger nesting, passive attribute choices, socketed items, weapon sets and every supported modifier category. Repair item conversion where fields are omitted; preserve unsupported fields and report them. Parsing and conversion must not mutate the source object.

Acceptance: supported fixtures retain gameplay semantics and deterministic primitives after export/reimport. For unsupported fields, export is labelled incomplete and cannot be the recommended deliverable. The editor may assign new internal numeric IDs; compare canonical semantics, not XML byte equality. Gate evidence includes exported XML that a reviewer loads in the pinned PoB.
