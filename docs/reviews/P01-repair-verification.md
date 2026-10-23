# P01 repair verification

> Historical review of the commits named below. Current task state and follow-ups are on [GitHub Issues](https://github.com/kaporli/pob2-tools/issues/23); this snapshot is not a current assignment list.

- Tasks: P01-T01 through P01-T05, specification 1.0.
- Implementation reviewed: `fcf1c5a09e687516018201da2c6b0a98f2fde31f`.
- Author/reviewer: Codex, 2026-10-05. This is verification of my own repairs, not a separate engineer's review.
- Verdict: **accepted for the specified P01 scope**. Merge recommendation is conditional on hosted checks passing for the PR head.

## Findings and acceptance mapping

No remaining blocking finding was identified in the repair diff and regression checks. The historical reviews remain unchanged apart from the current-disposition pointer.

| Task | Disposition | Evidence and limits |
|---|---|---|
| P01-T01 | accepted | Wrong-kind document references are rejected. The schema/codec/reference suites and namespace agreement regression pass. |
| P01-T02 | accepted for synthetic projections | Previous acceptance retained; identity regressions pass. Real catalog/parser semantics remain future evidence. |
| P01-T03 | accepted | Evaluation batch imports preserve uniqueness and legacy eligibility, reject conflicting retries and roll back atomically. Existing persistence tests pass. |
| P01-T04 | accepted | Both ingestion orders produce complete snapshots. Aggregate and reference-result dependencies copy idempotently and reopen without the source corpus. Legacy results remain cache-ineligible. Missing dependencies are reported. |
| P01-T05 | accepted for local fault injection | Earlier acceptance retained; completion/recovery/context/checkpoint tests pass after sharing the evaluation writer. Real crashes and concurrent writers remain P08 work. |

R06, R07 and R08 are resolved, closing the remaining R03 scope. R01, R02, R04 and R05 remain resolved.

## Evidence and adversarial checks

- Full offline unit/local-integration suite: **562 passed, 8 expected failures**, separately on Python 3.10.22 and 3.12.4.
- New snapshot regressions: **15 passed**; all **20 generated schemas match**.
- [Repair handoff and exact commands](https://github.com/kaporli/pob2-tools/issues/136).
- [Independent probes replayed against the repair](../evidence/P01/snapshot-repair-probes.json); [original failed probes](../evidence/P01/review-5068871.json) preserved for comparison.
- [Disconnected-corpus, cache and recovery demonstration](../evidence/P01/snapshot-repair-demo.json).
- Adversarial cases include a wrong-kind source reference, reversed listing/item insertion order, a missing transitive target, direct raw-blob evidence, normal/legacy evaluation dependencies, conflicting batch imports and a cyclic gap/evaluation reference.
- Inspected the final changes to namespace ownership, SQL kind filters, traversal, shared evaluation writing, task completion and tests. No engine or provider runs were needed for this change.

## Reassessment

G0 remains accepted. P01 is now accepted within its foundational synthetic-data and local recovery scope. Dependent P02/P03/P05/P09 work may proceed according to the delivery plan; G1 still requires its other prerequisites and is not granted by P01 acceptance.

The remaining eight expected failures belong to later P02/P08 work. Production dispatch must supply task context and attempt IDs. Real provider output, live trade, numerical game fidelity, held-out observations, search performance and learning claims remain outside this acceptance. No schema migration or product-scope decision was needed.

The user retains approval and merge. This verification does not submit a GitHub approval or merge the PR.
