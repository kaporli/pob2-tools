# Implementation handoff

## Identity

- Task IDs: P01-T01, P01-T03, P01-T04, P01-T05 (repairs to the submitted work). P01-T02 was accepted and is unchanged except where the reference index needed it.
- Specification version: 1.0.
- Engineer: Claude implementation assistant, 2026-10-05.
- Starting commit: `ae4303e` (the reviewed revision), on branch `p01-contracts-storage`.
- Implementation commit or working-tree diff reference: the follow-up commit on the same branch and PR [#3](https://github.com/kaporli/pob2-tools/pull/3).
- Status: review_ready.
- Dependencies and their accepted review records: [docs/reviews/P01.md](../reviews/P01.md), verdict `changes_required`, 2026-10-05.

## What the review found, and what changed

All five findings reproduced exactly as recorded before anything was touched. The reviewer's probe script was run unchanged first; its output matched `docs/evidence/P01/review-ae4303e.json` line for line.

### P01-R01 P1 Enforce task transitions when committing results

`RunStore._close_task` moved any non-completed task to `completed`. A cancelled task given a late result became completed.

Changed: `_close_task` now checks `TASK_TRANSITIONS` inside the transaction that writes the evaluation, so only a `running` task can complete and a refusal rolls the evaluation insert back with it. Three further rules the finding asked for:

- **Task/result association.** `TaskStore.enqueue` takes a `context_key`, normally the `EvaluationKey.cache_key()` the task is expected to produce. When set, a result whose `cache_key` differs is refused with `TaskResultMismatch`. A worker cannot close a boss task with a clear result.
- **Late results after recovery.** `commit_evaluation` takes `attempt`. A result from a superseded dispatch raises `StaleAttempt` instead of being attributed to the attempt now running. Omitting it keeps the old behaviour and is documented as "the caller does not know which attempt this came from".
- An exact repeat of a completed task is still a no-op; a *different* result for one is `TaskResultMismatch`.

### P01-R02 P1 Make accepted records survive JSON round trips

Two separate defects, both fixed:

- `from_jsonable` rejected `None` before checking whether the annotation was `Any`. A free-form JSON value is allowed to be null, the encoder writes it and the schema permits it, so a stored `ItemInstance` could not be read back. Null is now accepted for `Any` and still rejected for a declared non-nullable field.
- `validate_record` skipped the decode pass for dataclass inputs, so a hand-built record holding `status="ok"` reached the semantic pass and raised `AttributeError`. The shape pass now always runs, semantics only ever see a decoded record, and `ValidationReport.record` is the canonical instance. `RunStore._require_valid` returns it, so storage persists the decoded record rather than the loose one.

### P01-R03 P1 Require a complete reference graph

The largest change, in four parts matching the finding:

1. **The inventory is complete and provably so.** `_references` now walks every cross-record and blob reference, nested evidence inside `character_rules` and catalog `rule_references` included. Everything it does not walk is in `UNCHECKED_REFERENCE_FIELDS` with a reason, and `own_identity_fields()` covers the ones a record provides rather than cites. `tests/unit/test_p01_t03_references.py::test_every_identifier_field_is_classified` fills every identifier field on every record and fails unless each one is resolved or listed, so a field added later cannot quietly go unchecked. It found six I had missed while I was writing it.
2. **An empty index is an empty corpus.** `RecordIndex.enabled` is gone. `index=None` means "do not check"; any index, empty included, means "resolve against this corpus".
3. **Storage requires closure.** `put_normalized`, `put_gap`, `put_observation`, `put_run` and `commit_evaluation` resolve references by default. `import_batch` validates a set of records against the store plus the batch and writes them in one transaction, which is what the cyclic cases need: a patch profile cites the catalog that cites it and also cites a gap in another table, so no insertion order works. `require_references=False` is the explicit staging escape hatch, and raw acquisition still does not resolve references, as contracts.md allows.
4. **Bundles freeze the graph they promise.** `copy_references` closes over the reference graph from its seeds: asking for a build brings its catalog, items, listings, rotation, rules, gaps, source documents and raw payloads. A dependency the corpus cannot supply lands in `CopyReport.unresolved`. `self_check` answers three questions separately (blobs present, blobs intact, every reference resolving) and `readable` requires all three; `require_readable()` raises `IncompleteBundle` with the detail.

One modelling decision inside this: **only a `GameCatalog` provides a catalog hash.** A patch profile pins one and an item cites one. Treating a citation as a provider was how a bundle believed it held a catalog it had never copied.

### P01-R04 P2 Allow multiple evaluations of one candidate per generation

Migration **2**, not an edit to migration 1, as the finding required. It drops the unique `(run_id, generation_id, candidate_id)` index, adds `context_key TEXT NOT NULL DEFAULT ''`, recreates the old index as a non-unique grouping index and adds a unique `(run_id, generation_id, candidate_id, context_key)`.

One candidate in one generation can now carry a clear and a boss task, a screen and a detailed task, and several seeds. Repeating the same task id is still idempotent, and the same context for the same candidate is still refused. No candidate ids were invented to get around the constraint.

### P01-R05 P2 Include constituent evaluation identities in aggregate keys

`AggregateKey.from_manifest` is gone. `AggregateKey.from_components` takes the set of `AggregateComponent(scenario_id, evaluation_cache_key)` the score was computed from, plus the objective and baseline-suite hashes. Every other dependency reaches the key through the component keys, so changing the run seed, a scenario, a rotation, the fidelity or the calibration now moves the aggregate key. Components are sorted, so reordering an unordered set is not a miss. An aggregate with no components raises: it has no identity without the evaluations it came from.

## Acceptance evidence

| Finding | Acceptance case from the review | Test | Result |
|---|---|---|---|
| R01 | dispatched/running completion succeeds | `test_p01_review_regressions.py::test_a_running_task_completes_and_an_exact_retry_is_a_no_op` | passed |
| R01 | identical retry is a no-op | same test | passed |
| R01 | a different result for a completed task fails | `::test_a_different_result_for_a_completed_task_is_refused` | passed |
| R01 | cancelled, queued and failed completions rejected, both tables unchanged | `::test_only_a_running_task_may_complete` (3 cases) | passed |
| R01 | cancellation / late worker result through `commit_evaluation` | `::test_a_cancelled_task_is_not_completed_by_a_late_result`, `::test_a_result_from_a_superseded_attempt_is_rejected` | passed |
| R01 | task/result association validated | `::test_a_task_bound_to_a_context_refuses_an_unrelated_result` | passed |
| R02 | null, zero, false and nested nulls behave consistently | `::test_every_json_value_survives_a_free_form_field` (6 cases) | passed |
| R02 | full put/get round trip | `::test_a_null_in_a_free_form_field_survives_the_round_trip` | passed |
| R02 | non-nullable fields still reject null | `::test_a_non_nullable_field_still_rejects_null` | passed |
| R02 | bad dataclass types do not escape as AttributeError | `::test_a_wire_value_in_a_dataclass_does_not_escape_as_an_attribute_error`, `::test_an_undecodable_value_is_a_report_not_an_exception` | passed |
| R03 | importing a build without its graph fails validation | `test_p01_t04_cache.py::test_a_dangling_record_cannot_be_stored_without_saying_so` | passed |
| R03 | the three missing-reference cases report at their field paths | `test_p01_t03_references.py::test_the_reviews_unchecked_fields_are_now_reported` (3 cases) | passed |
| R03 | a closed graph stays valid and readable after disconnection | `test_p01_t04_cache.py::test_a_run_stays_readable_after_its_corpus_is_disconnected` | passed |
| R03 | omitted dependencies detected | `::test_copying_a_build_without_its_graph_is_not_a_readable_bundle`, `::test_a_transitive_copy_reports_a_dependency_the_corpus_lacks` | passed |
| R03 | checks run through storage and bundle APIs | all of the above call `put_normalized`, `copy_references`, `self_check` | passed |
| R04 | clear and boss tasks for one candidate complete independently | `::test_one_candidate_can_carry_a_clear_and_a_boss_task`, `::test_recovery_preserves_every_completed_evaluation` | passed |
| R04 | screen/detail and different seeds | `::test_one_candidate_can_carry_a_screen_and_a_detailed_task`, `::test_one_candidate_can_carry_several_seeds` | passed |
| R04 | recovery preserves completed evaluations | `::test_recovery_preserves_every_completed_evaluation` | passed |
| R04 | repeating a task identity is still idempotent | `::test_repeating_a_task_id_is_still_idempotent`, `::test_the_same_context_for_one_candidate_is_still_refused` | passed |
| R04 | the over-restrictive test is revised | `test_p01_t05_tasks.py::test_task_ids_generations_and_candidates_are_unique` rewritten | passed |
| R04 | migration policy followed | `test_p01_t03_storage.py::test_a_v1_database_upgrades_to_v2_without_losing_tasks` | passed |
| R05 | any constituent dependency moves aggregate identity | `::test_any_evaluation_dependency_moves_the_aggregate_key` (9 cases), `test_p01_t04_cache.py::test_a_changed_constituent_evaluation_changes_aggregate_identity` (13 cases) | passed |
| R05 | objective and baseline changes still force a miss | `test_p01_t04_cache.py::test_the_aggregate_key_adds_objective_and_baselines` | passed |
| R05 | reordering identical components is not a miss | `::test_component_order_does_not_change_aggregate_identity` | passed |

## Reproduction

```
python -m pytest tests/unit -q
python docs/evidence/P01/review-repair-probes.py
python scripts/p01_demo_run.py
python scripts/generate_schemas.py --check
```

Expected: 542 passed, 7 xfailed; every probe observation flipped; the demo regenerating `docs/evidence/P01/demo-run.json` unchanged; 20 schemas matching.

Recorded in [validation.json](../evidence/P01/validation.json):

| Run | Result |
|---|---|
| `tests/unit`, CPython 3.10.22, clean locked venv | 542 passed, 7 xfailed |
| `tests/unit`, CPython 3.12.4, clean locked venv | 542 passed, 7 xfailed |
| the nine P01 modules only | 431 passed |
| default selection | 547 passed, 34 engine skips, 8 xfailed |

Hosted CI for this commit, [run 37362031537](https://github.com/kaporli/pob2-tools/actions/runs/37362031537),
succeeded on both interpreters with the same counts: 542 passed and 7
xfailed, 41 and 39 locked distributions, 20 schemas matching, and 34 engine
tests collected and skipped for the missing-runtime reason. The lane
provisions no PoB runtime, so it is evidence about the offline foundation
only. A skip is not an engine pass.

## Adverse cases

Each finding has its original probe as a test, plus the cases the review asked to be added: the three previously unchecked reference fields and seven more like them, nested evidence inside `character_rules`, a catalog entity rule reference, an item and a patch profile that cite a catalog without providing one, a source document naming a blob whose bytes are absent, a transitive copy whose payload was deleted behind the repository, a v1 database upgrading to v2 with its rows intact, and a stale attempt after recovery.

Still not tested, unchanged from the first submission and still carried to P08: concurrent writers, and real process crashes as opposed to simulated interruption points. Also untested: whether the reference inventory matches what a real parser or catalog produces, since neither exists until P04 and P02-T02.

## Artifacts and provenance

| Artifact | Kind |
|---|---|
| `docs/evidence/P01/review-ae4303e-probes.py` and `review-ae4303e.json` | The reviewer's own script and recorded results for `ae4303e`. Unchanged. |
| `docs/evidence/P01/review-repair-probes.py` | The same questions asked of the repaired code. |
| `docs/evidence/P01/validation.json` | Recorded runs and checks, including the repair probe output. |
| `docs/evidence/P01/demo-run.json` | Regenerated end-to-end example, now exercising all five findings. |

The reviewer's script is kept because it is the evidence about the reviewed revision. Run against the repaired code it stops at its first probe, because an empty bundle no longer accepts an evaluation whose build, rotation and scenario it does not hold. That refusal is the R03 fix, not a broken script, and `validation.json` records it as such.

All synthetic. No PoB, no provider, no gameplay measurement.

## Deviations and unresolved questions

1. **`AggregateKey.from_manifest` was removed rather than deprecated.** It cannot produce a correct key, and P01 is the only caller. Anything that needs an aggregate identity must now name the evaluations it used.
2. **`context_key` defaults to empty**, which preserves the old one-task-per-candidate behaviour for tasks that are not evaluations. The unique index still applies to the empty key, so that case is unchanged rather than unconstrained.
3. **`StoreIndex` resolves a rotation hash by scanning rotation policies**, because the hash is derived rather than stored. There are few rotations per run; if that stops being true it wants an indexed column, which is a migration.
4. **Evidence fields resolve against the union of namespaces** (`ANY_RECORD`), because a source document, a parse result, a claim or an observation can all be cited as evidence. A narrower rule would need contracts.md to say which kinds count as evidence for what.
5. The fixture graph gained two records, `fixture-acquisition-2` and `fixture-source-2`, so the observation's raw evidence resolves. The placeholder ids `fixture-evidence-1` and `fixture-evidence-2` are gone: they were exactly the dangling references the review was pointing at.

None of this is a game-rule interpretation or a threshold change, so no decision record is requested.

## Request for review

Requested verdict: accepted for P01-T01, P01-T03, P01-T04 and P01-T05, completing the project. P01-T02 was already accepted for the submitted synthetic projection scope and is unchanged in substance.

Residual limits to carry forward: concurrent writers and real-crash recovery, both for P08-T04/T05; and the reference inventory not yet having met real parser or catalog output, for P04 and P02-T02.
