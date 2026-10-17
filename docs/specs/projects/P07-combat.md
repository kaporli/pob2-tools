# Encounter and rotation evaluation

Project ID: P07. Dependencies: P01, P02 primitives/legality, P06 registry and P09-T01 scenario protocol. Goal: measure modeled completion over time without double-counting damage or inventing uptime. Implement synthetic fixtures before representative PoE encounters.

## P07-T01 Implement the deterministic event loop

Use integer microseconds and a priority queue ordered by `(time, phase, insertion_id)`. At a timestamp process expiration, scheduled state changes, completed actions/impacts, periodic effects, then policy decisions. Buff intervals are half-open `[start,end)` unless a documented mechanic overrides this. Process existing impacts/effects at exactly the duration limit, then terminate without another policy decision. Clamp damage to remaining target health for effective-damage metrics while retaining raw overkill in traces.

State includes time, actor resources, cooldowns, animation availability, buffs/debuffs, target health/status, summons/persistent entities and active weapon set. The scenario defines initial state. Bound events at 500,000 per scenario by default; hitting the bound produces a resource-limit error, not a successful infinite-DPS result.

Acceptance: hand-computed fixtures cover simultaneous expiry/hit, cooldown readiness, periodic ticks, delayed projectiles, multiple targets and target death. Same seed/input yields identical event traces. No negative time, free zero-time action loop or damage after termination.

## P07-T02 Integrate owned damage and resource mechanics

Use P02 primitive semantic contracts to calculate per-action hits and owned persistent effects. Explicitly choose which layer owns crit averaging/sampling, accuracy, projectile hit count, DoT stacking, trigger rate, buffs and defenses. Never multiply a PoB sustained DPS value by an independently modeled attack rate.

Implement resource expenditure at the documented event, regeneration/recovery, reservations, cooldowns, duration and supported charges. Implement a small set of certified mechanics modules first; an unsupported mechanic causes a coverage gap. Model minion/persistent uptime only when supported; do not assume permanent damage while the entity is absent or unable to target.

Acceptance: constant-rate toy damage matches an analytical solution; doubling an action time affects throughput once; refresh/stack/overwrite DoT fixtures differ correctly; insufficient resources produce waiting or policy changes. Out-of-scope mechanics return unsupported status.

## P07-T03 Implement rotations and bounded policy search

Implement the RotationPolicy vocabulary from contracts. Validate actions, predicates and state references before a run. Provide hand-authored reference policies first. Record setup, enabling actions, main actions, movement, waits and weapon switches. An action cannot use two mutually exclusive sets simultaneously.

For the first rotation optimizer, start from accepted policy templates and vary ordering plus evidenced threshold values. Enumerate at most 32 deterministic variants per candidate, record that scope and keep the best eligible policy by the same suite objective. Each variant is an explicit pair of clear/boss policies evaluated over the full suite; do not mix best per-scenario outcomes from mutually incompatible preparation rules. Count every variant's detailed evaluations against the search budget. Do not generate arbitrary code or claim global optimality of play. P08 can later mutate these templates while preserving rule validity.

Acceptance: an enabler/payoff fixture spends time on both; unreachable predicates are reported; a missing enabling action reduces performance; unknown recast interval does not become six seconds. Same gear may use different accepted clear/boss policies.

## P07-T04 Implement scenario geometry and survival scope

Implement dense/spread workloads using explicit target layout and a declared supported hit/coverage model. A fixed route may represent movement. Record hit overlap and target caps from verified rules. Implement boss targetability windows and relevant incoming-damage/resource pressure as specified by P09.

Do not label an uncalibrated geometry approximation actual map clear time. A scenario lacking a survival model remains proxy-only. Avoid unexplained multipliers shared across unrelated skills. Record precision limits and validate units from PoB before using radius values.

Acceptance: movement contributes to clear time; damage during invulnerability contributes zero; multi-target effects cannot hit more targets than allowed; a build dying before completion fails. If survival mechanics cannot be modeled, the suite cannot pass the practical gate.

## P07-T05 Aggregate and expose evaluation

Implement `evaluate`, per-scenario artifacts and Ranker exactly as `scenarios.md` and [D07](../../decisions/D07-flicker-strike-objective.md). The active target is sustained Flicker Strike DPS after all recommendation gates; balanced score remains diagnostic or an explicitly selected legacy objective. Depend on P08-T01.1's reviewed objective contracts before storing objective-aware aggregates. Preserve screening proxies separately from detailed results. Apply legality/coverage before scoring and include unresolved assumptions. For each finalist produce full traces or a compressed trace plus summary that can reconstruct event totals, damage attribution, setup and resource downtime.

Acceptance: every scoring fixture in the shared spec and D07 passes, including burst/sustain reversal, unavailable enabling conditions and off-skill attribution. Changing preparation cost affects final rank consistently. Missing, timed-out, crashed and legitimately zero-damage evaluations remain distinct. Supported build export retains Flicker Strike as the evaluated main skill and the exact configuration. A result cannot be `gameplay_validated` before P09 approves matching mechanics/scenario evidence.
