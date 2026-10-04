# Request to the reviewing assistant

Use the following message when submitting engineering work. Replace the bracketed entries and attach or point to the actual repository changes and artifacts.

> Review the implementation of [task IDs] against `docs/specs/README.md` and the corresponding project specs, specification version [version]. The implementation is at [commit/diff]; handoffs are [paths]; evidence bundles are [paths]. Inspect the code, reproduce the required checks where possible, and challenge it with independent adverse cases. Do not accept skipped engine/live/gameplay checks as passes. Write a verdict and findings under `docs/reviews/`. Reassess the architecture, remaining tasks and prior gate validity in light of what was learned, and recommend the next concrete tasks. Do not assume the engineer's completion claim means the task passed.

A future review requires access to those changes and evidence. This template does not schedule background work or imply that the assistant will monitor the repository automatically.
