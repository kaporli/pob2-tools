# Implementation handoff

Post this format as a comment on the assigned GitHub issue and link the implementation PR. Replace placeholders; retain every section. Use `not applicable` with a reason rather than deleting an evidence section.

## Identity

- GitHub issue URL and permanent task IDs:
- Specification version:
- Engineer:
- Starting commit:
- Implementation commit or working-tree diff reference:
- Status: in_progress, review_ready, or blocked
- Dependencies and their accepted review records:

## Implemented behavior

Describe the concrete input, previous behavior and resulting behavior. List changed files and why each is needed.

## Acceptance evidence

| Criterion from task | Command or artifact | Result | Fixture or context IDs |
|---|---|---|---|
| Replace with one criterion per row | Exact command/path | passed, failed, skipped, unexecuted or blocked | Include versions/hashes |

## Reproduction

Provide ordered setup and execution commands, working directory, prerequisites and expected output. Identify commands requiring PoB or live credentials. Never include tokens/cookies. Include a minimal end-to-end example where relevant.

## Adverse cases

Describe malformed input, missing data, unsupported mechanics, failure/recovery or other relevant negative cases exercised. State which important cases remain untested.

## Artifacts and provenance

List raw source references, normalized records, traces, exported builds, benchmark results and durable artifact paths/hashes. Distinguish synthetic, PoB-derived and independently measured evidence.

## Deviations and unresolved questions

List every contract/default/threshold change proposed. Link a decision record. Identify blockers, affected tasks and independent work that can continue.

## Request for review

State the requested task verdict, any gate requested and the next task proposed. Do not state that the task is accepted before review.
