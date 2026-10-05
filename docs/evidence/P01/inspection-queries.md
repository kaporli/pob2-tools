# Inspecting a P01 database by hand

P01-T05 requires that a reviewer can inspect the database without going
through application code. These are the queries, all read-only, all defined in
[`pob2opt/storage/queries.py`](../../../pob2-optimizer/pob2opt/storage/queries.py).

Run one by hand:

```
sqlite3 runs/<run_id>/run.sqlite
```

or run all of them and get JSON:

```
python -m pob2opt.storage.queries runs/<run_id>/run.sqlite
```

The output below comes from the end-to-end example in
[`demo-run.json`](demo-run.json), regenerated with
`python scripts/p01_demo_run.py`. Everything in it is synthetic.

## The queries and what they answer

| Name | Question it answers |
|---|---|
| `schema_version` | Which migrations this database has, and when they were applied. |
| `task_counts_by_state` | How much work is queued, running, completed, failed and cancelled. |
| `unfinished_tasks` | Exactly which tasks a resume will pick up, with their attempt counts. |
| `task_history` | Every state transition, with the reason and the attempt it belonged to. |
| `completed_results_once_each` | Whether any completed task carries more than one result row. |
| `duplicate_evaluations_by_cache_key` | Whether two evaluations ever claimed one cache key. Must be empty. |
| `cache_decisions` | Why the run hit or missed the cache, counted by reason. |
| `cache_misses_in_detail` | Each miss, including the key that was found and refused. |
| `orphan_blob_rows` | Blob rows nothing references. Must be empty in a healthy run. |
| `source_versions_per_external_id` | How many times one external source was acquired, and how many distinct payloads that produced. |
| `open_blocking_gaps` | The gaps that block a recommendation. |
| `legacy_imports_are_labelled` | Historical phase output, with the note that marks it unusable. |
| `evaluations_marked_legacy` | Evaluations flagged legacy, which the cache always refuses. |
| `run_declared_references` | What the run copied into its own bundle. |

`orphan_blob_rows` and `duplicate_evaluations_by_cache_key` are checks, not
defences. The defences are the transaction boundary in
`RunStore.ingest_source` and the `UNIQUE` index on `evaluation.cache_key`;
these queries confirm they held.

`schema_version` now reports two migrations. Migration 2 replaced the unique
`(run_id, generation_id, candidate_id)` index with a non-unique grouping
index plus a unique `(run_id, generation_id, candidate_id, context_key)`.
Migration 1 was not edited: a database already at v1 upgrades in place, and
`tests/unit/test_p01_t03_storage.py::test_a_v1_database_upgrades_to_v2_without_losing_tasks`
proves the existing rows survive with an empty context key.

## Recorded output from the example run

Three tasks were queued: two evaluation contexts for one candidate and a
third for another candidate. One completed, one was interrupted while
running and recovered, and the third was cancelled and then had a late
result delivered to it. A duplicate completion message for the finished
task was delivered after the restart.

### `task_counts_by_state`

| run_id | state | tasks |
|---|---|---|
| fixture-run-1 | cancelled | 1 |
| fixture-run-1 | completed | 1 |
| fixture-run-1 | queued | 1 |

The cancelled task stayed cancelled. The late result delivered to it was
refused with `TaskStateError` and left no evaluation row, which is review
finding P01-R01.

### `unfinished_tasks`

| task_id | generation | candidate | state | attempt | dispatched_at |
|---|---|---|---|---|---|
| demo-task-2 | 1 | demo-candidate-1 | queued | 1 | null |

`demo-task-1` and `demo-task-2` are two evaluation contexts for the same
candidate in the same generation, which migration 2 allows and migration 1
refused (review finding P01-R04). They are distinguished by `context_key`,
not by inventing a second candidate id.

`demo-task-2` is queued again with `attempt = 1`: the interrupted attempt is
still counted, so a candidate that keeps crashing stays visible rather than
looking fresh on every restart.

### `completed_results_once_each`

| task_id | evaluation_id | rows_per_task |
|---|---|---|
| demo-task-1 | fixture-evaluation-1 | 1 |

One row, after the duplicate completion message. `duplicate_evaluations_by_cache_key`
is empty.

### `cache_decisions`

| reason | outcome | decisions |
|---|---|---|
| no_entry | miss | 2 |
| exact_match | hit | 1 |

The two misses are the cold detailed lookup before any work was done and a
screen-fidelity lookup afterwards. The hit is the detailed lookup after the
result was committed.

### `run_declared_references`

| run_id | kind | refs |
|---|---|---|
| fixture-run-1 | blob | 1 |
| fixture-run-1 | normalized | 11 |
| fixture-run-1 | source | 2 |

Two records were asked for, `fixture-build-1` and `fixture-clear-dense`;
eleven were copied, because `copy_references` closes over the reference
graph. The corpus was then deleted and the bundle still resolved every
reference: `corpus_disconnected` in `demo-run.json` records
`require_readable()`, which raises rather than returning an optimistic
answer (review finding P01-R03).

### `legacy_imports_are_labelled`

One row, `legacy:gems:51511a9d69099169`, carrying the note that it has no
manifest, no dependency hashes and no recorded inputs, and is not
cache-eligible. `evaluations_marked_legacy` is empty, because nothing promoted
it into an evaluation.

### `open_blocking_gaps`

| gap_id | kind | severity |
|---|---|---|
| fixture-gap-1 | unsupported_rule | blocking |

This is the synthetic gap from the fixture corpus, not a finding about PoE 2.
