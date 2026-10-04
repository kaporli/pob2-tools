# Evidence

Durable artifacts a reviewer can inspect without rerunning the work, organised
by task or gate: `docs/evidence/P00/`, `docs/evidence/G0/`, and so on.
`docs/specs/review.md` requires this, because ignored `runs/` files alone are
not enough for another engineer's handoff.

What belongs here: environment records, characterization results, measurement
JSON, fixture inventories, and content-addressed references (path plus SHA-256)
to anything too large to commit.

What must never go here: credentials, cookies, OAuth tokens, or any redistributed
third-party data this repository has no right to publish. Mark anything
`redacted` or `restricted` when it may be reviewed locally but not shared.

Every artifact must say what kind of evidence it is - synthetic, PoB-derived, or
independently measured. Those are different claims and the specification keeps
them separate.

## Current contents

| Path | Task | What it is |
|---|---|---|
| `P00/environment.md` | P00-T01 | Machine, Python, packages, PoB checkout, existing runs |
| `P00/baseline/` | P00-T01 | Inventory and copies of pre-existing legacy run output; historical, not validated |
| `P00/findings.md` | P00-T04 | Characterization of research findings F02, F05, F10, F11, F12 and four new observations |
| `P00/measurements.json` | P00-T04 | Engine timings, memory and A-B-A, with hardware |
