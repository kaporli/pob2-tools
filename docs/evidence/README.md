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
| `P01/validation.json` | P01 | Offline test runs on CPython 3.10 and 3.12, plus the schema, lock, packaging and example checks |
| `P01/demo-run.json` | P01 | Recorded output of the end-to-end example: ingest, bundle, corpus disconnect, interruption, resume, cache and legacy import |
| `P01/inspection-queries.md` | P01-T05 | The documented read-only queries a reviewer runs against a run database, with the example's output |
| `P01/review-ae4303e-probes.py` | P01 review | The reviewer's adversarial probe script for commit `ae4303e`; kept unchanged |
| `P01/review-ae4303e.json` | P01 review | The observations that script recorded, which the repair reproduced before fixing |
| `P01/review-repair-probes.py` | P01 repair | The same questions asked of the repaired code |
| `P02/lifecycle.json` | P02-T01 | Engine boundary behaviour: the three offline failure probes (synthetic), then real-engine identity, exact versus blank loading, A-B-A with B read, state isolation, document provenance and forced termination (PoB-derived) |
| `P02/review-eca7afe-adversarial-probes.py` | P02-T01 review | The seven adversarial probes run against `eca7afe`; kept unchanged |
| `P02/review-eca7afe-adversarial.json` | P02-T01 review | What those probes recorded before the repairs, mapped to findings R01 and R03 to R06 |
| `P02/review-eca7afe-probes.json` | P02-T01 review | A parallel review's probe output for the same commit, written by another run; the source of findings R10 and R11. Its probe script was lost (see the review) |
| `P02/review_eca7afe_workers.py` | P02-T01 review | The slow-load synthetic worker that parallel set used |
| `P02/review-eca7afe-recovery-probes.py` | P02-T01 repair | Reproduction of R10 and R11 at HEAD |
| `P02/review-eca7afe-recovery.json` | P02-T01 repair | Those two cases before and after the repair |
| `P02/catalog-export.json` | P02-T02 | PoB-derived. What one real `catalog export` produced: entity counts, catalog hash, evaluation context hash, the compatibility report and why the verdict is `partial`, the character rules, and every gap with its needed evidence |
| `P02/catalog-rows-slice.json` | P02-T02 | PoB-derived, and a slice, not the catalog. Bounded engine rows so the offline tests run the real export with no PoB. A catalog hash computed from it is not an export's catalog hash. Marked `restricted`: third-party game data, reviewable locally |
| `P02/catalog-profile-request.json` | P02-T02 | The `--profile` request the reference export uses |
| `P02/release/` | P02-T02 | Captures of official Path of Exile 2 patch-notes pages, one file per page, `restricted`. The export resolves the live patch from these and from nothing else; see the README there |
| `P02/sample-build-ranger-quarterstaff.xml` | P02-T02 | PoB-derived. A build the pinned engine saved itself, used to show the exported entities resolve a real saved build. Its weapon rolls are invented |
| `P02/legality.json` | P02-T03 | Mixed, labelled per section. `synthetic`: the verdict, violations, unknowns and cited gaps for every fixture case, validated against a profile exported from invented rows. `pob_derived`: one exact import of the sample build in the pinned engine, the state the engine reported back, and the verdict on it. Neither section is a gameplay measurement, and an `unknown` verdict is a statement about this software's evidence |
| `P02/primitives.md` | P02-T04 | The primitive inventory: units, included and excluded effects, one owner per primitive, the controlled fixtures that settled each semantic, and the gaps that remain. PoB-derived, not gameplay evidence |
| `P02/primitives.json` | P02-T04 | What those thirteen fixtures returned, with the engine identity that produced them. Regenerated by `python scripts/p02_t04_primitive_fixtures.py` |
| `P02/roundtrips.json` | P02-T05 | Build and item round trips. The `synthetic` section is invented fixtures compared by our exporter against our importer; the `pob` section is a build PoB saved, exported, loaded back into the pinned engine and compared on canonical identity and deterministic primitives (PoB-derived) |
| `P02/roundtrip-synthetic.xml` | P02-T05 | The synthetic supported fixture's exported document. Synthetic: its class, skills and bases are invented, so the pinned PoB will load the file and find none of those entities. It is here to be read, not loaded |
| `P02/roundtrip-pob-export.xml` | P02-T05 | PoB-derived. Our export of a build PoB itself wrote; this is the document a reviewer loads in the pinned PoB. `docs/worklog/P02-T05.md` gives the two ways to load it |
| `P03/acquisition.json` | P03-T02 | Synthetic. What acquisition did with invented payloads and a scripted transport: the four input kinds and their hashes, the idempotency counts, the seven refusal cases with the blobs and documents each wrote (none), the credential probe, the limits actually applied, the retry schedule and the host policy's refusals. No provider was contacted. Regenerated by `python scripts/p03_t02_evidence.py` |
