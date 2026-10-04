# Path of Exile 2 optimizer implementation specifications

This specification defines a PoE 2 build optimizer that searches for builds capable of both clearing and bossing, explains their strengths and execution requirements, and exposes missing evidence instead of inventing performance. It is an implementation plan, not a claim that these capabilities already exist.

Specification version: 1.0. Prepared on 2026-10-04. Status: ready for staged implementation; external access and game-specific benchmark decisions have explicit gates. No application implementation is included in this documentation change.

## Read in this order

1. [Product requirements](product.md): what the system must accomplish and the defaults to implement.
2. [Research and repository findings](research.md): observed facts, source limitations, and unresolved dependencies.
3. [Architecture](architecture.md): module ownership, storage, and execution boundaries.
4. [Data contracts](contracts.md) and [command interfaces](interfaces.md): shared implementation contracts.
5. [Scenarios and scoring](scenarios.md): the definition of performance and the ranking formula.
6. [Delivery plan](delivery.md): task order, dependencies, and acceptance gates.
7. The assigned project below, [concrete acceptance examples](acceptance-examples.md), then [review procedure](review.md).

When documents conflict, product requirements take priority, then contracts and scenarios, then project tasks. Record a conflict as a decision request; do not silently choose an interpretation. Task IDs are permanent references for implementation and review.

## Projects

| ID | Project | Specification |
|---|---|---|
| P00 | Reproducible foundation and characterization | [Tasks](projects/P00-foundation.md) |
| P01 | Shared records and persistence | [Tasks](projects/P01-contracts-storage.md) |
| P02 | PoB adapter and correctness repairs | [Tasks](projects/P02-engine.md) |
| P03 | Build source acquisition | [Tasks](projects/P03-acquisition.md) |
| P04 | Parsing and build normalization | [Tasks](projects/P04-parsers.md) |
| P05 | Trade access and equipment candidates | [Tasks](projects/P05-trade.md) |
| P06 | Mechanics coverage and missing evidence | [Tasks](projects/P06-coverage.md) |
| P07 | Encounter and rotation evaluation | [Tasks](projects/P07-combat.md) |
| P08 | Build search and resumable runs | [Tasks](projects/P08-search.md) |
| P09 | Benchmarks and independent validation | [Tasks](projects/P09-validation.md) |
| P10 | Reports and end to end delivery | [Tasks](projects/P10-reporting.md) |
| P11 | Optional learning experiments | [Tasks](projects/P11-learning.md) |

## Instructions for an assigned engineer

1. Select one task whose dependencies have passed review. Read its entire project and the shared contracts before changing code.
2. Create or update `docs/worklog/TASK-ID.md` from the [handoff template](templates/handoff.md). Record the specification version and starting commit.
3. Implement only the assigned task and necessary tests. Reuse the prescribed modules; do not create alternative schemas, scoring systems, or services.
4. Exercise every acceptance case and attach commands, fixture IDs, and results. A test that never ran is not a pass.
5. Mark the task `review_ready`, not `accepted`. Use the [review request](templates/review-request.md) when returning work to the reviewing assistant.
6. If blocked, record the exact missing input and the work it blocks. Continue only with independent tasks in the delivery plan. Unknown game rules must never be replaced with guessed constants to make a test pass.

All implementation tasks start in `planned`. The specifications themselves do not approve any implementation gate. Technical acceptance belongs to the reviewing assistant when the engineer supplies the changes and evidence. Product-scope changes belong to the owner, Elias. Routine implementation inside these requirements does not need additional owner permission.

## Completion boundaries

The offline research milestone can finish without automated website access. The full requested live-market product cannot: manual item import is a useful fallback, not acceptance of live trade integration. Similarly, successful PoB calculations establish engine consistency; independent gameplay evidence is required for claims about practical performance.

The initial release covers a documented subset of Huntress mechanics. Expansion is a required staged project outcome, not permission to call that subset all PoE 2 builds. P11 is optional and must not delay a useful, validated non-learning optimizer.
