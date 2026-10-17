# D07: first target is maximum Flicker Strike DPS

- Date: 2026-10-17.
- Specification: 1.1; supersedes the initial Huntress scope and default balanced-winner objective in 1.0.
- Authority: Elias requested that the initial Huntress build be replaced with a build maximizing Flicker Strike DPS.
- Status: **product direction accepted; implementation and gameplay evidence pending**.
- This record changes requirements. It does not certify a build, a game mechanic, a class choice or an implemented optimizer.

## Target and retained requirements

Find the highest supported, evaluated **Flicker Strike sustained single-target DPS** within the declared search space. Resolve Flicker Strike to exact gem/granted-skill IDs from the accepted PoE 2 patch catalog. A missing or ambiguous match blocks preparation; never substitute the PoE 1 skill or another main skill.

The class is no longer fixed to Huntress. P09-T01 must propose an explicit list of compatible classes/ascendancies and Flicker Strike variants from evidence. Prepare one class-bound search context per approved class and compare results only under the same objective, patch, item universe and benchmark. Report classes excluded or not searched. Do not claim an unrestricted class optimum from one class's run. The four-hour budget applies to the whole campaign, including its class contexts and final verification, unless the user explicitly changes it.

No equipment budget cap, current-patch compatibility, demanding manual execution with disclosed costs, and the requirement to be capable of clearing and bossing remain. The default winner changes from maximum balanced score to maximum Flicker Strike DPS **among candidates passing the existing clear/boss, legality, coverage, survival and resource gates**. A high-DPS build failing those gates can appear as a diagnostic specialist, not as the recommendation.

## Exact initial DPS benchmark

These are versioned engineering defaults, not assertions about game mechanics:

1. Add a separately versioned `flicker_sustained_v1` benchmark alongside the four clear/boss scenarios. Use one non-dying, continuously targetable enemy with explicit, evidenced level and defenses. This is a controlled damage benchmark, not a claim about a real boss encounter. Unknown target properties block a comparable score.
2. Use a fixed 120-second window starting at scenario time zero. Count preparation, support actions, movement required by the policy, resource generation and all waiting inside that window. Initial resources, buffs and other state must be stated and obtainable under the scenario rules; no free maximum-state toggles.
3. Define `flicker_sustained_dps = attributed_damage_in_[0,120) / 120`. Attribute direct Flicker Strike hits and attributable secondary/ailment damage only through reviewed ownership rules. Include a contribution breakdown. Damage from unrelated skills is reported separately, while the time spent using those skills still counts. Ambiguous ownership is a blocking gap; no effect may be counted twice.
4. Use no adds or kill events in this benchmark. Any dependency on such events must be unavailable unless an explicitly different, versioned scenario supplies them. Investigate the actual skill's activation, repeat-use, targeting, resource and enabling conditions from the pinned catalog and evidence; do not guess them from a guide or another game version.
5. Report `flicker_burst_dps` separately as damage in `[0,5)` divided by five, under the same initial conditions. Do not select the most favorable five-second segment. Burst is not the ranking objective.
6. Report resource depletion and whether the rotation has an evidenced repeatable sustain cycle. A 120-second measurement alone does not establish indefinite sustain. Missing critical sustain mechanics block a supported score.
7. Rank eligible candidates by descending sustained DPS. Within relative tolerance `1e-6`, prefer higher `min(C,B)` from the four-scenario suite, then canonical build-plus-rotation hash. Preserve C, B, balanced score and strength labels as diagnostics; do not put DPS into the balanced-score field.

PoB's displayed DPS is a screening/consistency input. It is not automatically this time-accounted benchmark result. Until the detailed evaluator exists, a PoB number must stay `proxy_only`. Synthetic targets can test software, but cannot establish practical superiority.

## Required implementation work

| Task | Deliverable / acceptance |
|---|---|
| P08-T01.1, with P01 contract review | Versioned request, objective and aggregate representation that pins objective ID/version, skill IDs, class scope, benchmark hash, attribution rules and windows. Preserve v1 decoding/hashes; add migration and unknown-objective refusal tests. Freeze these values into manifest/cache identity. Current RunRequest v1 cannot express this target. |
| P09-T01 follow-up / D04 | One complete Flicker Strike export to start, its actual rotation, approved class/variant scope, and real encounter/target evidence. Propose three distinct interaction variants within Flicker Strike for the initial validation split; do not relabel near-duplicates to satisfy a quota. |
| P06-T01/T02 | Registry and coverage checks for every dependency needed to use and sustain the skill. Missing data, missing implementation and unvalidated behavior produce different actionable requests. |
| P07-T02/T03/T05 | Traceable time-accounted damage attribution, sustained/burst metrics and objective-specific ranking. Existing clear/boss gates remain enforced. |
| P08-T02/T03 | Preserve the Flicker Strike main-skill constraint through mutations; search approved classes and enabling combinations without collapsing to one imported variant. |
| P09-T02/T03 | Independent measurements, leakage-resistant splits and DPS-specific accuracy checks. Kill time without evidenced enemy health/defenses cannot be relabelled measured DPS. |
| P10-T01/T02 | Show objective, benchmark conditions, damage breakdown, burst versus sustained results, clear/boss strengths, setup, sustain limits, execution and missing evidence. |

## Required adversarial fixtures

- A higher burst build loses to a higher sustained-DPS build under identical conditions.
- Waiting for a missing activation resource or enabling condition reduces DPS; it is never assumed away.
- Preparation and off-skill actions consume time even if they improve later Flicker damage.
- An on-kill-dependent candidate cannot obtain kills from a single non-dying target.
- Double-attributed damage is rejected; unrelated skill damage cannot win the Flicker objective.
- A higher-DPS candidate failing clear/survival gates is not the recommendation.
- Missing objective metrics stay null with gaps; no fallback to balanced score or displayed PoB DPS.
- Changing the main skill or objective/window changes identity or is rejected; existing v1 records retain their old meaning.

## Historical evidence and open access decisions

Keep accepted `p09-synthetic-v1` artifacts, hashes and previous review reports unchanged. They remain evidence for spec 1.0 software behavior, not a Flicker Strike benchmark or the new objective. D04's old three-Huntress-family requirement is superseded; its missing encounter/measurement evidence remains open. D01 trade and D02 source access dispositions are unaffected.
