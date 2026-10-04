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

## Recorded output from the example run

Three tasks were queued. One completed, one was interrupted while running and
recovered, one was never dispatched. A duplicate completion message for the
finished task was delivered after the restart.

### `task_counts_by_state`

| run_id | state | tasks |
|---|---|---|
| fixture-run-1 | completed | 1 |
| fixture-run-1 | queued | 2 |

### `unfinished_tasks`

| task_id | generation | candidate | state | attempt | dispatched_at |
|---|---|---|---|---|---|
| demo-task-2 | 1 | demo-candidate-2 | queued | 1 | null |
| demo-task-3 | 1 | demo-candidate-3 | queued | 0 | null |

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
| fixture-run-1 | normalized | 5 |
| fixture-run-1 | source | 1 |

The corpus was deleted after this copy and the bundle still read every one of
them: see `corpus_disconnected` in `demo-run.json`.

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
