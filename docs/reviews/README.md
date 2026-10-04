# Reviews

One file per reviewed task or gate, written by the **reviewing assistant**, not
by the engineer who did the work. Use [the review template](../specs/templates/review.md).

Naming: `P00-T01.md` for a task, `G0.md` for a gate. A verdict is one of
`accepted`, `changes_required`, `blocked` or `superseded`.

Only a reviewer records `accepted`. An engineer may set a task to
`review_ready` or `blocked` in its worklog and nothing else. Blocked access
never becomes accepted by waiting.

The procedure, the mandatory milestone questions and the regression
invalidation rules are in [`docs/specs/review.md`](../specs/review.md).
