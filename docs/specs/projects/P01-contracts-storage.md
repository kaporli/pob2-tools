# Shared records and persistence

Project ID: P01. Dependency: G0. Goal: all components exchange the same versioned records and long runs preserve immutable evidence. Implement [contracts](../contracts.md) before source-specific assumptions.

## P01-T01 Implement schemas and domain records

Create the named dataclasses/enums in `pob2opt/domain/` and JSON Schema files in `schemas/v1/`. Implement `validate_record` with both schema errors and semantic reference errors. Separate unknown/null, absent, zero and false. Reject unknown schema versions with a supported-version message. Add a RunRequest schema matching `interfaces.md`.

Acceptance: each record has one valid and at least two invalid examples. Tests include negative duration, NaN, missing provenance, duplicated passive IDs, unresolved item reference, unknown status and nullable price. Errors include a field path. No provider parser adds its own incompatible BuildSpec.

## P01-T02 Implement canonical identity

Create canonical serializers and hashing functions for documents, item properties, builds, rotations, scenarios and evaluation context. Explicitly list included/excluded fields in module documentation. Treat unordered allocations as sets after duplicate validation; preserve action/support-group order where semantics require it.

Acceptance: reordered JSON keys and display-name changes keep build identity; changed support, passive choice, item roll, progression flag or set binding changes identity. Changed listing price preserves combat identity but changes listing snapshot data. Round-trip serialization is stable on Windows newline variations in metadata; raw-byte document hashes still preserve byte differences.

## P01-T03 Implement immutable storage and migrations

Implement blob writes/reads and SQLite repositories for source records, normalized records, evaluations, gaps, observations, runs and task state. Store full JSON records with indexed IDs/hashes; avoid creating one SQL column per game stat. Enforce unique evaluation cache keys. Create migration version 1 and an explicit migration runner.

Acceptance: repeated ingestion of identical bytes reuses the blob; same external source updated later creates a new record; missing/corrupt blobs produce typed errors; duplicate completion messages cannot create duplicate results. Fault injection between blob write and transaction completion leaves a recoverable orphan, not a false successful record.

## P01-T04 Implement snapshot and cache boundaries

Implement immutable run bundles and evaluation keys using every dependency in architecture. Persist cache-hit/miss reason. Copy required raw/normalized references into run scope before execution. Implement a loader for historical legacy phase outputs that labels them legacy and never grants cache eligibility.

Acceptance: each of patch, catalog, engine, calibration, rotation, scenario, registry, fidelity and seed changes forces a miss. Source popularity alone does not change combat result. A run remains readable after its corpus is changed or disconnected.

## P01-T05 Implement atomic task persistence

Task states are `queued`, `running`, `completed`, `failed`, `cancelled`. Use unique task IDs plus generation and candidate IDs. Coordinator marks dispatch and completion transactionally. On restart, unfinished running tasks return to queued with an incremented attempt record; completed tasks remain completed. Implement checkpoint validation against manifest hash.

Acceptance: fault-injection tests interrupt before dispatch, after dispatch, after result write and before checkpoint replacement. Resume neither loses a completed result nor counts it twice. A mismatched manifest is rejected. Reviewer can inspect the database using documented queries.
