# Product requirements

Build a local tool that can spend hours searching PoE 2 configurations, return playable candidates strong in clearing and bossing, and explain exactly where its evidence is insufficient. Community builds supply examples and mechanics claims. They do not define the maximum possible performance.

## Confirmed requirements

| ID | Requirement | Acceptance evidence |
|---|---|---|
| R01 | Support PoE 2 first, starting with a user-selected class such as Huntress. | Class restriction enforced on every candidate and exported build. |
| R02 | A recommended build must be capable of both clearing and bossing. | Pass all scenario and category floors in `scenarios.md`; retain separate scores. |
| R03 | Communicate each build's strengths, weaknesses, and execution demands. | Report includes relative strengths, rotation, preparation, timing and failure costs. |
| R04 | No equipment spending cap by default. | `budget` is null; no hidden price filter, currency exclusion, or cheap-gear weighting. |
| R05 | Integrate current trade availability. | Accepted live connector, timestamped listings, candidate equipment evaluation and finalist refresh. Fallback alone does not pass. |
| R06 | Target the current game patch. | Official patch evidence and pinned compatible PoB/catalog versions in run manifest; stale coverage is explicit. |
| R07 | Permit demanding manual execution. | No complexity penalty in default score; all time and resource costs still counted. |
| R08 | Ingest community builds and their explanations. | Per-source capability manifests, normalized configurations, provenance and sourced claims. |
| R09 | Identify missing data or unsupported mechanics and specify the next evidence required. | Structured gaps tied to affected candidates and actionable collection requests. |
| R10 | Run long searches with recovery. | Checkpoint, resume, cancellation, bounded workers and repeatability checks. |
| R11 | Permit discovery beyond existing builds. | Explicit exploration allocation, coordinated mutations and diversity measurements. |
| R12 | Every deliverable is reviewable and reassessed before dependent work. | Task evidence packages, reviewer verdicts, milestone reassessment records. |

## Default product decisions

These are implementation defaults, not claims about PoE mechanics. Record changes in a versioned decision record and rerun affected checks.

| Decision | Default |
|---|---|
| Platform | Local Windows CLI, retaining the existing Python and Lua bridge. |
| Character | Huntress, level 100 for unconstrained endgame searches; derive valid level cap and quest/ascendancy budgets from the pinned catalog. If 100 is invalid in the target version, reject the profile for review instead of clamping it. |
| Game mode | Solo softcore, current PC challenge trade league. Resolve exact league ID once during preparation. Ambiguous or unavailable league resolution requires explicit selection. |
| Equipment universe | Owned items plus observed listings in a frozen snapshot. No budget cap. A theoretical legal-item mode is separate. |
| Configuration | One gear/passive/gem configuration across scenarios. In-game weapon-set changes are allowed when represented and timed. No between-scenario respecs or external equipment swaps in the default profile. |
| External support | No party buffs or outside resource generation. Scenario-supplied enemies/resources must be explicit. |
| Objectives | Equal clearing and bossing category weights after hard legality, capability and survival gates. |
| Execution | Skilled manual execution, including all action delays. No automated in-game play component. |
| Initial search duration | Four hours wall time including search startup and finalist verification, excluding explicit data acquisition. Configurable. |
| Search result | Best evaluated candidates within the recorded search scope. No global optimum claim without a certificate for a finite enumerated/modelled space. |
| Initial report | Best balanced candidate plus up to two alternatives emphasizing clear or boss performance; all must pass the both-capable gates to be recommendations. |

The level default does not mean skill levels, gem slots, quest rewards or ascendancy points can be inferred from level using current hardcoded thresholds. P02 must derive those constraints from an approved patch profile.

## Product behavior when evidence is incomplete

- Missing critical legality data: candidate status `legality_unknown`; never recommend it as legal.
- Missing combat mechanics: candidate may remain an exploration hypothesis, but it cannot receive a comparable production score.
- Insufficient independent validation: report `model_estimate` or `proxy_only`; do not advertise validated practical superiority.
- No current market access: allow an explicitly offline run using imported items. State that current availability is unverified and R05 is incomplete.
- No qualifying candidate: return `no_recommendation`, list the best partial candidates and concrete gaps. Never lower gates silently.
- New game patch: invalidate current-patch approval for affected coverage and preserve old reproducible results as historical.

## First release and expansion

The first vertical slice evaluates imported Huntress builds with a small, reviewer-approved mechanics subset, two clear scenarios and two boss scenarios. It must search equipment, supports, passives, allowed ascendancies and supported rotations within that subset. Document every excluded family and modifier.

After this slice is independently validated, expand by mechanics families and repeat coverage and validation gates. Full PoE 2 coverage remains an explicit backlog. A new class is another validated capability expansion; supporting arbitrary games is outside this implementation series.

## Non goals for the initial implementation

Do not build a website, hosted service, autonomous trading/buying bot, real-time game controller, whole-game physics engine, distributed compute cluster, language model from scratch, or mandatory fine-tuning pipeline. Do not add those as prerequisites. A model-assisted search experiment is allowed only in P11 after the deterministic system is useful.

## Rules for honest claims

Legality, mechanics coverage, performance validation, search completeness and equipment availability are separate statuses. None implies the others. Numerical uncertainty ranges are sensitivity ranges unless a justified probability model or mathematical bound establishes stronger semantics. Popularity, PoB DPS, and character level are not labels for measured combat quality.
