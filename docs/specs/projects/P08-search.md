# Build search and resumable runs

Project ID: P08. Dependencies: P01 persistence, P02 catalog/legality, P05 imported equipment pools, P06 coverage and P07 evaluation. Search-kernel work can start earlier against synthetic evaluators after P01. Goal: spend compute on diverse legal combinations and recover without changing the optimization problem.

## P08-T01 Prepare immutable run contexts

**P08-T01.1, prerequisite contract delivery (done for contract scope in PR #11, `p08-t01.1-contracts`, repair `740e2f0`):** versioned request/objective/aggregate records, migration, objective hashes, catalog-backed Flicker identity checks and persisted aggregate binding are implemented. R1/R2 are closed by [repair self-verification](../../reviews/P08-T01.1-repair-verification.md); require green CI before merge. V1 records retain their meaning and unknown objectives are refused. This child task does not complete prepare: the service must still invoke the resolver, approve/freeze class scope, resolve benchmark/attribution content hashes and create immutable contexts.

Implement `prepare` and RunRequest resolution. Freeze selected class/progression, current patch/league, catalog, source builds, market/imported item pool, scenario suite, objective and all versions. Validate access/coverage separately; market mode requires accepted market capability, while explicitly offline mode can proceed with imports. Current-patch resolution failure cannot fall back to an old patch silently.

For D07, prepare one class-bound context per approved class and a campaign manifest sharing the objective, benchmark, item universe and total time budget. Do not silently constrain the campaign to Huntress or a seed build's class. Report excluded classes and incomplete coverage. Do not grant four hours to every class when the requested campaign budget is four hours total.

Determine worker count using P00 measured peak worker memory: reserve at least 2 GiB for the coordinator/OS and allocate at least 1.5 times measured worker peak per worker, constrained by user limit and available memory. Use one worker until measurements exist. Log all resolved values and unresolved gaps.

Acceptance: same explicit inputs produce the same context hashes; ambiguity blocks preparation with specific fields. Four-hour default is a search budget, not permission to run acquisitions indefinitely. A changed corpus cannot affect an already prepared run.

## P08-T02 Implement candidate generation and coordinated mutations

Represent candidates as immutable build/rotation pairs plus lineage. Start with accepted imported builds and legal generated candidates from the approved mechanics subset. Implement mutation operators for item replacement, paired item replacement, support replacement, two-support replacement, passive subtree removal/addition, allowed ascendancy change with compatible tree rebuild, main-skill/enabler change and rotation-template variation.

After mutation, run legality and coverage. A bounded repair may choose attribute nodes or required enabling gear, but must record each change and stop after ten attempts. Unrepairable candidates remain rejected with reasons. Do not silently enable arbitrary conditions. Evaluate equipment combinations jointly instead of summing standalone upgrades.

Acceptance: a toy pair that is harmful individually but beneficial together can be generated; different item rolls and rotations retain distinct identities; repeated identical candidates are deduplicated; mutated trees remain connected or are rejected. Search can generate a supported skill family absent from the seed builds.

For the Flicker objective, every mutation must preserve the resolved Flicker Strike main-skill constraint. Explore interaction variants/classes beyond the seeds within approved scope; unrestricted main-skill replacement belongs only to a different explicitly selected objective. A constraint-breaking candidate is rejected, not silently scored on its stronger alternate skill.

## P08-T03 Implement a deterministic diverse search kernel

Initial configurable defaults: population 64; 128 proposals per generation; proposal allocations 50% local mutations, 30% coordinated mutations and 20% fresh supported candidates. Keep 16 elite eligible candidates plus representatives from supported families. If a source cannot fill its allocation, record the reason and use fresh proposals; never silently convert all exploration into elite copies.

Screen proposed candidates cheaply. Detailed-evaluate up to 64 unique candidates per generation: up to 48 promising candidates stratified by family/approved Flicker interaction variant and at least 16 unexplored/uncertain candidates selected by seeded sampling. Reserve this exploration quota even when screening score is poor. Unsupported critical mechanics enter the gap queue, not a fake numeric ranking. Use the active objective among eligible detailed results: D07 sustained Flicker DPS by default, balanced score only for an explicitly selected legacy objective. Retain clear/boss Pareto diversity without pruning the DPS winner solely on C/B dominance. Keep provisional noneligible candidates separately for exploration.

Merge evaluations at generation boundaries in stable candidate-ID order, regardless of worker completion order. Track unique legal proposals, rejection reasons, family coverage, screening/detail counts, cache hits and best score over evaluations and time. These defaults are engineering choices, adjustable only through recorded configuration and comparisons.

Acceptance: at least 20 synthetic seeds run on finite spaces; exhaustive enumeration establishes the actual optimum for those fixtures. A deliberate synergy trap is solved by coordinated exploration while the greedy baseline fails. A single imported family cannot consume the entire proposal budget. No optimum claim is made for normal heuristic runs.

## P08-T04 Implement scheduling and recovery

Dispatch only immutable evaluation tasks. Use P01 transactional states and checkpoint RNG state, generation archive and queued tasks. Count elapsed search time across resumes using accumulated monotonic durations; downtime does not count. Reserve the final 10% of the configured time budget for detailed finalist verification and report preparation. Stop launching work when remaining budget cannot accommodate its timeout; checkpoint unfinished work at the boundary.

Handle Ctrl+C by stopping submissions, recording state and terminating workers after a bounded grace period of ten seconds. Persist partial results. If a worker crashes, replace it and retry the evaluation once; a second failure remains visible. Memory threshold breach reduces concurrency or stops cleanly; never spawn repeatedly without limit.

Acceptance: kill/restart during each task transition and compare with an uninterrupted deterministic evaluation-count-budget run. Completed results are not repeated; hashes and RNG evolution agree. Wall-clock-limited runs may finish different amounts of work and must report that limitation. Resume with changed context is rejected.

## P08-T05 Benchmark improvement and run endurance checks

Compare imported seeds only, repaired legacy greedy search, random legal search and the new search on identical pools/suites. Report both equal expensive-evaluation budget and equal wall-clock comparisons. Include generation, legality, proxy and PoB overhead. Run at least five seeds; preserve all outcomes rather than only the best run.

Run a four-hour Windows soak with recorded hardware and memory. Verify cancellation, resume, plateau reporting and final recomputation. A plateau means no recent improvement, not optimality.

Acceptance: finite fixtures pass exact checks; the search never loses its best accepted seed under identical context; real benchmark gains and failures are reported with variation. If gains are not demonstrated, P09 records that outcome and P11 is not justified as an automatic remedy. Deliver candidate lineage and performance traces for review.
