# Implementation review

Post this format on the relevant GitHub issue or pull request. Link durable evidence files and the exact reviewed commit.

## Review identity

- Task or gate:
- Specification version:
- Reviewed implementation commit:
- Reviewer and date:
- Verdict: accepted, changes_required, blocked, or superseded

## Evidence inspected

List files, commands actually run, results, fixtures and artifacts. Explicitly identify evidence not independently reproduced and why.

## Acceptance mapping

| Criterion | Evidence | Verdict and limitations |
|---|---|---|
| One criterion per row | Stable references | Pass, fail or blocked |

## Findings

For each finding: severity, location, observed behavior, impact, required change and regression case. Separate confirmed failures from concerns needing more evidence.

## Adversarial check

Record the independent challenge case and result. Explain what it tests that ordinary happy-path checks do not.

## Scope and residual limitations

State supported mechanics/sources/platforms and outstanding access/data gaps. Separate implementation quality from product capability achieved.

## Reassessment

- Assumptions confirmed or contradicted:
- Contracts or tasks to revise:
- Prior gates invalidated, if any:
- Required revalidation:
- Next task IDs and ordering:
- Owner decision needed, only if a concrete product choice remains:

## Final disposition

State exactly what is accepted or blocked and whether dependent implementation may proceed. If a repair is needed, give an executable acceptance case.
