# P01 follow-up implementation review

## Review identity

- Tasks: P01-T01 through P01-T05; specification 1.0.
- PR: [#3](https://github.com/kaporli/pob2-tools/pull/3).
- Reviewed head: `506887127021a7f6b1516f9e4fd361aad4ae6292`; implementation repairs in `46c50a1`.
- Previous reviewed implementation: `ae4303ee8db334c6d07a73f92a606dd77d5649f5`.
- Reviewer/date: Codex, 2026-10-05.
- Verdict: **changes_required. Do not approve or merge this revision.**

## Findings

All three findings below are independently reproduced gaps in the P01-R03 repair. Other original findings are resolved within the scope described below.

### P01-R06 — P1: Restrict source-document references to source documents

Location: [index.py](../../pob2-optimizer/pob2opt/storage/index.py), `source_document_ids` at line 32, `_KIND_FILTER` at lines 46–54 and its use at lines 112–114.

Both SourceDocument and AcquisitionResult live in `source_record`. The SQL-backed index checks only the record ID for `source_document_ids`, so an acquisition attempt can satisfy a field that requires a source document. The in-memory index correctly distinguishes them.

Reproduction: populate a valid fixture store; replace a BuildSpec's `source_document_ids` with the existing AcquisitionResult ID and give the build a new record ID. Validation with `record_index()` rejects `/source_document_ids/0`. Validation with `reference_index()` accepts it, `put_normalized` persists it, and the containing bundle reports `readable=True`. Thus default storage validation and readiness accept a reference to the wrong record type. A parser following that reference will obtain acquisition metadata instead of the promised document.

Required repair:

1. Apply a `kind = 'source_document'` restriction when resolving `source_document_ids` against `source_record`.
2. Check that each typed namespace has identical semantics in RecordIndex and StoreIndex, including pending batches. Preserve the broader semantics of fields explicitly using ANY_RECORD.
3. Add a regression through storage and bundle readiness, not only the in-memory validator.

Acceptance: the mutated build is rejected with `/source_document_ids/0`, no row is inserted, and explicitly staging that build makes `self_check()['readable']` false. A valid SourceDocument reference remains accepted. AcquisitionResult IDs remain usable where the contract actually permits them.

### P01-R07 — P2: Resolve snapshot dependencies by provider kind and namespace

Location: [runbundle.py](../../pob2-optimizer/pob2opt/storage/runbundle.py), `_identifiers_of` at lines 392–396; `_CorpusLookup.locate` at lines 365–368 and first-wins insertion at lines 379–380.

The lookup indexes attributes such as `item_hash` on every record kind, including records that merely cite that identity. It also ignores its `namespace` argument. A Listing inserted before its ItemInstance therefore becomes the lookup's provider for that item hash. Walking the listing's item reference loops back to the already-seen listing and never copies the item.

Reproduction: import the same closed fixture graph with Listing first in the validated batch, then request the build and scenario for a new bundle. Every source record validates. Copying returns `complete=True`, but the ItemInstance is absent and bundle readiness fails on the build's equipped item and the listing's `/item_hash`. The same operation succeeds with the original item-first fixture order. Valid ingestion order must not determine snapshot completeness.

Required repair:

1. Index providers by `(namespace, identity)` with explicit record-kind ownership. Only ItemInstance provides an item hash; Listing cites it. Apply this rule to all typed identities, rather than special-casing only catalog hashes.
2. Have `locate` use its namespace; define ANY_RECORD lookup consistently with validation.
3. Record unresolved transitive references in CopyReport when lookup fails. Do not return `complete=True` for an omitted dependency.

Acceptance: importing listing-before-item and item-before-listing produces equally complete, readable snapshots containing the actual item. Reopen each snapshot after disconnecting its corpus. Include a missing transitive target and assert both `CopyReport.complete=False` and failed readiness.

### P01-R08 — P2: Support evaluation records reached during snapshot copying

Location: [runbundle.py](../../pob2-optimizer/pob2opt/storage/runbundle.py), lines 219–222; [repositories.py](../../pob2-optimizer/pob2opt/storage/repositories.py), unsupported-kind error at lines 277–279 and writer registry at lines 713–718.

The transitive walk correctly reaches an AggregateResult's EvaluationResult, but copying routes every non-source record through `import_batch`. That API has no evaluation writer. Requesting the existing valid aggregate fixture from a fully validated corpus raises `StorageError: evaluation_result cannot be imported in a batch`. Consequently, snapshots containing aggregate dependencies cannot be created even when every required record is available. An evaluation may also be required by a scenario's reference result.

Required repair:

1. Provide a transaction-safe import path for evaluation records reached by the snapshot graph. Preserve unique cache keys, identical-retry behavior, conflicting-payload rejection and legacy-cache exclusion.
2. Support evaluation IDs in batch and copied-record identity helpers; they currently omit `evaluation_id`.
3. Preserve evaluation storage metadata needed for correct cache eligibility. Copying historical records must not turn legacy evaluations into eligible cache hits.
4. Avoid closing or creating worker tasks merely to import historical evaluation dependencies.

Acceptance: request the aggregate fixture by ID, copy all referenced evaluations and their dependencies, disconnect the corpus, reopen the bundle and require readability. Repeat the copy idempotently. Cover a scenario referencing an evaluation and verify that a copied legacy evaluation remains ineligible for cache reuse.

## Evidence inspected and reproduced

- Inspected the repair diff, updated handoff, record validation, reference indexes, batch writers, bundle traversal/readiness, task completion/migration and aggregate identity changes against the P01 spec and previous review.
- `python -m pytest tests/unit tests/integration -q`: **547 passed, 8 xfailed**, Python 3.12.4.
- `.venv/pr2-validation/py310-a/Scripts/python.exe -m pytest tests/unit tests/integration -q`: **547 passed, 8 xfailed**, Python 3.10.22.
- `python scripts/generate_schemas.py --check`: **20 schemas match**.
- `python docs/evidence/P01/review-repair-probes.py`: the submitted repair probes demonstrate cancellation refusal without result insertion, multiple scenario tasks, nullable round trips, newly checked references, rejection of incomplete bundles, the original transitive-copy happy path and distinct aggregate identities when the seed changes.
- New independent cases: [executable probes](../evidence/P01/review-5068871-probes.py) and [recorded results](../evidence/P01/review-5068871.json). All database writes use temporary directories. These exercise the public APIs with a changed batch order, an aggregate seed and a wrong-kind reference.
- Hosted [CI run 37363548887](https://github.com/kaporli/pob2-tools/actions/runs/37363548887) for this exact head reports success in both offline interpreter jobs. This status was checked directly; hosted execution was not rerun by the reviewer.
- No engine/provider/gameplay check was needed for these storage changes. This review supplies no new evidence of numerical game accuracy or live trade access.

## Acceptance mapping

| Task | Verdict | Evidence and limits |
|---|---|---|
| P01-T01: records and validation | changes_required | R02's null/type round-trip repair passes. R06 still violates typed reference validation at the storage boundary. |
| P01-T02: canonical identity | accepted for the existing synthetic projection scope | Previous acceptance retained; identity regression tests pass. |
| P01-T03: immutable persistence | changes_required | R01's transactional state enforcement passes; R06 admits a wrong-kind reference, and R08 prevents importing required evaluation dependencies. |
| P01-T04: snapshots and cache boundaries | changes_required | R05's constituent evaluation identity repair passes. R06–R08 still prevent reliable snapshot closure. |
| P01-T05: atomic task persistence | accepted for the specified local fault-injection scope | Terminal completion rejection, duplicate completion, migration, context separation, recovery and checkpoint checks pass. Real process crashes and concurrent writers remain P08 evidence requirements. |

Original finding disposition: **R01, R02, R04 and R05 resolved; R03 partially repaired and still open**, with R06–R08 identifying the remaining concrete failures. Task context and attempt protection are conditional on callers supplying `context_key` and `attempt`; production P08 evaluation dispatch/completion must populate them.

## Reassessment and final disposition

The fixes establish useful storage checks, but the reference provider mapping still differs between in-memory validation, SQL validation and snapshot copying. Define shared namespace ownership and test agreement across all three. No public game-record schema change or user scope decision is needed to repair these failures.

Repair R06 and R07 together in P01-T01/T03/T04, then complete evaluation import for R08 in P01-T03/T04. Add the acceptance cases above to ordinary tests, rerun both supported interpreter lanes and the snapshot demonstration, and submit a new head for review before merge. Preserve this probe output as evidence for 5068871.

G0 remains accepted. P01 remains unaccepted and G1 is not eligible from this submission. Independent investigations may continue, but dependent production features must not assume P01 storage acceptance. Game fidelity/coverage, numerical correctness, independent observations, search quality, market availability, product recommendations and learning effectiveness retain their later gates; passing synthetic storage tests does not establish them.

Only review documentation and evidence were written. No application fixes, commit, push, GitHub review submission, approval or merge were performed. The pre-existing deleted submodule working-tree entry was preserved.
