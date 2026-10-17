# Scenarios and scoring

The optimizer must reward builds that can clear and boss with the same equipment. This document specifies ranking mechanics. The actual PoE 2 encounter data is selected and evidenced in P09, not invented here.

## Active objective in specification 1.1

[D07](../decisions/D07-flicker-strike-objective.md) changes the default winner to maximum **sustained single-target Flicker Strike DPS**, measured over its fixed 120-second controlled benchmark with all setup/downtime counted. Burst is the first five seconds under the same conditions and is reported separately. This benchmark is additional to the four completion scenarios below; it does not replace their gates or claim to be a real boss.

Compute C, B and S below as clear/boss diagnostics and enforce every existing eligibility gate. Then rank eligible candidates by D07's sustained DPS, with D07's deterministic tie-break. If the DPS benchmark or any required gate lacks evidence, do not fall back to S, a burst value or PoB's displayed DPS. A supported diagnostic benchmark result may be displayed without becoming a recommendation.

The balanced objective below remains a named legacy objective for existing fixtures and comparisons, not the new default. Give the Flicker objective its own version/hash and aggregate fields before implementation. Never rewrite accepted `p09-synthetic-v1` artifacts or hashes to look like evidence for D07.

## Initial suite

Use four versioned scenarios: `clear_dense`, `clear_spread`, `boss_short`, and `boss_sustained`. Each has explicit enemy entities, health/defenses, positions or supported spatial relationships, movement/targetability windows, incoming damage, initial resources, legal preparation, completion rule and time limit.

Synthetic fixtures implement these shapes first with invented, clearly labelled numbers to test the simulator. Representative scenarios are a separate dataset based on recorded encounters. Synthetic results must never be reported as measured map clear speed or actual boss kill time.

Dense and spread scenarios measure time to finish their fixed enemy/route workload, including movement, targeting, preparation and cleanup. Boss scenarios measure time from scenario start to kill, including preparation and invulnerability windows. If actual pathfinding is not implemented, use an explicit replayed route/action-time model with a declared applicability limit. Area of effect multiplied by DPS is a screen proxy, not an encounter completion measure.

Each scenario has one approved reference build/result. References must be legal, complete and evaluated under identical scenario rules. They need not all be the same build. Freeze references before a comparison campaign; never renormalize against the highest candidate discovered in that campaign.

## Clear/boss diagnostics, gates and legacy balanced objective

For a successful candidate result in scenario `i`, define `r_i = reference_time_i / candidate_time_i`. Positive finite times are required. For stochastic scenarios, use the median over the same fixed seed set for reference and candidate. Death and timeout are failures, not missing trials to discard. A failed detailed trial disqualifies the default deterministic suite; stochastic suites specify a minimum success fraction before data collection.

Compute `C = geometric_mean(r_clear_dense, r_clear_spread)` and `B = geometric_mean(r_boss_short, r_boss_sustained)`. The balanced diagnostic score is `S = sqrt(C * B)`. The ratios are dimensionless. Equal category weighting is a product default, not a property of the game. If any required result is missing/unknown, set C, B and S to null; partial per-scenario metrics may still be displayed separately. Missing recommendation gates also leave the active objective's eligible ranking unresolved.

Before computing a recommendation, require:

1. Legal configuration, supported required mechanics and known required inputs.
2. Successful completion and declared survival/resource gates in every scenario.
3. Every scenario ratio at least `0.50`.
4. Both category scores at least `0.80`.
5. Detailed evaluations using one coherent context and no unresolved ranking-blocking gap.

These floors mean at most twice the reference time in any scenario and reasonable category performance relative to the selected baselines. They are provisional product settings. P09 reviews whether the chosen real references make them meaningful; engineers cannot relax them to produce a winner.

Keep the Pareto set of eligible `(C, B)` results: a candidate dominates another when it is no worse in both and strictly better in at least one. For an explicitly selected legacy balanced objective, rank by `S`, then higher `min(C,B)` within relative tolerance `1e-6`, then canonical build-plus-rotation hash. For the default Flicker objective, use D07's ranking instead and retain this set for clear/boss alternatives; do not discard a DPS winner solely because it is dominated on C/B. Preserve exact raw times alongside scores.

## Strength labels

For qualifying candidates only, label `clear_focused` if `C / B >= 1.25`, `boss_focused` if `B / C >= 1.25`, otherwise `balanced`. Explain that these are strengths relative to this suite's references. Show both category scores and raw completion times; the label does not replace them.

An exceptionally high score in one category does not override a failed floor in the other. Nonqualifying specialists can appear in a separate diagnostic section labelled not recommended for the requested combined objective.

## Survival and execution

Each approved representative scenario must specify its damage input and exact pass conditions. Static life/resistance/EHP numbers alone do not certify encounter survival. Do not assume perfect dodging unless the scenario explicitly supplies avoidable windows and the action policy spends time avoiding them.

No default complexity penalty applies. Report number of active actions, actions per minute, setup duration, weapon switches, required maintained conditions, timing windows and recovery after one missed enabling action. Evaluate a missed-action sensitivity case for finalists; keep it separate from the ideal-execution score.

Resource use is simulated. A temporarily empty resource pool is not automatically illegal; it creates downtime. Requirements that need impossible initial resources or unavailable regeneration are unsupported/illegal. No arbitrary minimum uptime is allowed.

## Uncertainty and stopping claims

If a parameter has evidenced alternative values, reevaluate finalists under those alternatives. Report the resulting sensitivity range and whether winner order changes. Do not call this a confidence interval without a statistical model. Do not call extrema a guaranteed bound unless the tested set or monotonicity argument establishes that claim.

If rank changes across plausible settings, return a conditional result and the highest-value evidence request. No sensitivity result can establish protection against entirely unrepresented mechanics. Overlapping statistical uncertainty means no demonstrated superiority, even if point estimates differ.

No score plateau, number of generations or elapsed hours proves optimality. `proven_optimal_within_scope` requires complete enumeration of the declared finite space or an independently verified optimization certificate. The default label is `best_found`.

## Required scoring fixtures

| Case | Expected behavior |
|---|---|
| All four ratios are 1 | C, B and S are 1; balanced; eligible if other gates pass. |
| C is 0.5 and B is 2 | S would be 1, but clear-category floor fails; not recommended. |
| One clear ratio is 0.4 and the other is 4 | Per-scenario floor fails despite a good clear average. |
| Missing boss result | Scores unresolved; do not replace with zero or drop that scenario. |
| Valid zero damage until timeout | Valid failed evaluation; not an engine error and not eligible. |
| Same build with different display name | Same combat identity and score. |
| Expensive listing replaces equal-stat cheaper listing | Same combat score; acquisition metadata differs. |
| Reference or scenario version changes | Different aggregate identity; no mixed leaderboard. |
