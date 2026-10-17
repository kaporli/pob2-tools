# Mechanics coverage and missing evidence

Project ID: P06. Dependencies: P01, P02 catalog/primitive semantics, P04 claim/normalization records and P09-T01 initial scope. Goal: explain whether a result can be trusted and what work would resolve a gap.

## P06-T01 Create the mechanics registry

For the initial approved Flicker Strike class/interaction scope ([D07](../../decisions/D07-flicker-strike-objective.md)), enumerate damage, defenses, costs, reservations, action timing, cooldowns, durations, stacking, triggers, target selection, repeat-use/sustain conditions and enabling interactions. Verify which conditions actually apply from the pinned PoE 2 catalog and evidence; do not assume PoE 1 behavior. Store MechanicRules with dependencies, owner, required inputs, patch scope, tests and limitations. Damage attribution and initial-state/renewal assumptions for sustained DPS must have explicit owners too.

Do not treat a modifier parsed by PoB as necessarily implemented correctly. Validate dependency closure and reject cycles in static requirements; temporal trigger loops belong to explicit bounded simulator rules. Unknown rules are registry entries with unsupported status, not dropped entries.

Acceptance: every primitive/effect consumed in the initial benchmark links to a rule; each effect has exactly one calculation owner. A guide-derived interaction remains unverified until implementation and evidence are attached. Changing a rule changes registry hash.

## P06-T02 Implement candidate coverage analysis

Walk equipped modifiers, allocated nodes, skills, supports, rotation predicates and scenario requirements. Resolve transitive mechanic/input dependencies. Produce per-domain support and validation states plus concrete DataGaps. Unknown item modifiers, hidden build config assumptions and unavailable rotation inputs must be detected.

Acceptance: removing a duration field creates a gap naming that field and dependent skill; unsupported trigger produces unsupported status; a harmless display-name omission does not block scoring. All tested known unsupported input categories are detected. Do not claim detection of mechanics absent from both source data and registry.

## P06-T03 Implement evidence resolution and patch invalidation

Allow a gap to be resolved only by linking evidence and a corrected input/rule. Keep history and supersede old evaluations. New patches mark affected rules stale using entity/rule diffs; if impact cannot be determined, mark the relevant family stale conservatively. Imported build patch declarations do not override official profile compatibility.

Acceptance: a resolved gap can be traced to its evidence and author/reviewer; changing a dependency invalidates cached affected results; unrelated display metadata changes do not. Contradictory measurements reopen validation rather than averaging contradictions into a hidden constant.

## P06-T04 Implement finalist sensitivity evaluation

For up to ten unresolved numeric/behavior assumptions affecting finalists, collect evidenced alternatives. Evaluate one-at-a-time alternatives first, then combinations for interacting assumptions within a recorded evaluation budget. If the space is not covered, report sensitivity coverage as partial. No defensible alternatives means unbounded uncertainty and a blocking gap, not guessed plus/minus ten percent.

Rank gaps by observed winner reversal first, largest measured score spread second, then explicit collection effort if known. This is an engineering priority heuristic, not a formal expected-value guarantee.

Acceptance: a synthetic unknown interaction that reverses two candidates is labelled ranking-sensitive; a tested irrelevant field is informational only within that tested scope; no range is labelled a confidence interval or proof without appropriate justification.

## P06-T05 Generate actionable evidence requests

Render structured requests naming affected build/rule, the unresolved question, why it matters, exact expected input format, collection steps, comparison/control conditions and resolution test. Examples include an item export, source parser fix, PoB support task or manually recorded interaction trial.

Acceptance: an engineer can resolve a fixture gap by following the request without guessing a schema. Missing data and missing implementation produce different requests. Report output links to these requests and does not hide blocked candidates. Reviewer signs coverage scope before practical ranking proceeds.
