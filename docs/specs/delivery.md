# Delivery tracking

[GitHub delivery index](https://github.com/kaporli/pob2-tools/issues/23) is the sole source of task status, assignment order, dependencies, blockers, historical handoffs and acceptance verdicts. [All issues](https://github.com/kaporli/pob2-tools/issues?q=is%3Aissue) include completed deliveries as closed issues; [milestones](https://github.com/kaporli/pob2-tools/milestones) group the release tracks.

Implementation tasks are maintained in issue bodies. Engineers post handoffs on the corresponding issue and link their PR. Review findings and follow-up assignments belong on issues or PRs. Do not add repository task ledgers, project task lists, TODO documents or worklogs.

The repository retains [product requirements](product.md), [contracts](contracts.md), [interfaces](interfaces.md), [acceptance definitions](acceptance-gates.md), decision rationale, fixtures and durable evidence. Historical reviews are dated evidence snapshots, not current trackers. Runtime DataGap records describe evaluated builds and remain part of the application; they are not project-management tickets.

Use the [handoff](templates/handoff.md) and [review](templates/review.md) formats in GitHub discussions on the relevant issue/PR. Request scoped review before closing an implementation issue; a green CI result alone is not acceptance.
