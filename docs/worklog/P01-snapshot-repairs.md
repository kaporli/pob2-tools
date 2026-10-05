# P01 snapshot and reference repairs

- Tasks: P01-T01/T03/T04; spec 1.0.
- Starting commit: `506887127021a7f6b1516f9e4fd361aad4ae6292`.
- Findings addressed: P01-R06, P01-R07, P01-R08 (remaining P01-R03 closure defects).
- Author/date: Codex, 2026-10-05.

## Changes and acceptance evidence

| Finding | Change | Regression evidence |
|---|---|---|
| R06 | SQL source-document references require the source_document kind. | Wrong-kind reference is refused before insertion; explicitly staged invalid data fails readiness. Memory, SQL, pending and traversal namespace membership agree across the fixture identities. |
| R07 | Memory validation and snapshot traversal share explicit provider ownership. Traversal keys include the namespace, records unresolved transitive targets and handles direct blob evidence. | Both item-first and listing-first batches copy the actual item and reopen after corpus disconnection. Missing targets fail CopyReport completeness and readiness. |
| R08 | Batch import and task completion share a transactional evaluation writer. Snapshot import preserves legacy cache exclusion and does not touch tasks. | Aggregate and scenario reference-result snapshots copy twice idempotently and reopen without their corpus, for both normal and legacy evaluations. Conflicting cache keys, IDs, payloads and eligibility roll back the whole batch. Evaluation/gap cycles import together. |

Tests: [test_p01_snapshot_repairs.py](../../tests/unit/test_p01_snapshot_repairs.py), 15 cases.

## Validation

- `python -m pytest tests/unit/test_p01_snapshot_repairs.py -q`: 15 passed.
- `python -m pytest tests/unit tests/integration -q`: 562 passed, 8 xfailed on Python 3.12.4.
- `.venv/pr2-validation/py310-a/Scripts/python.exe -m pytest tests/unit tests/integration -q`: 562 passed, 8 xfailed on Python 3.10.22.
- `python scripts/generate_schemas.py --check`: 20 schema files match.
- Re-ran both the prior repair probes and the independent 5068871 probes. [Current results](../evidence/P01/snapshot-repair-probes.json); the original failing results remain unchanged.
- `python scripts/p01_demo_run.py --out docs/evidence/P01/snapshot-repair-demo.json`: successful [demonstration](../evidence/P01/snapshot-repair-demo.json), including disconnected corpus, task recovery and legacy-cache exclusion.
- `git diff --check`: passed.

The current independent probe reports `bundle_readable=True` after the wrong-kind insert is refused: the valid pre-existing bundle remains unchanged. The separate regression explicitly stages the wrong-kind record and verifies that readiness fails.

## Scope and compatibility

No record schema, migration, game rule or numerical evaluator changed. Evaluation imports now reject a duplicate whose legacy eligibility differs from the stored row; historical cache exclusion cannot silently change. Source documents and acquisitions still use dedicated ingestion APIs. Snapshots preserve evaluation payloads and legacy status; historical task state is not imported.

The existing eight expected failures concern future P02/P08 work. Concurrent writers and real process crashes remain P08 validation requirements. Provider/gameplay accuracy and production dispatcher population of task context/attempt remain outside this repair. No product decision or approval exception is needed.
