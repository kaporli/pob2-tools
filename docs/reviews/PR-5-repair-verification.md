# PR #5 repair verification

Date: 2026-10-10. Base revision: `3d7ba53cb703e4794755c083da443019ab30bbe7`. Target: the repair commit containing this verification note.

This supplements the [original review](PR-5.md); its observed-defect probe and JSON are historical evidence for that revision. Run the regression tests below against the repaired tree, not the original probe's deliberately defective-behavior assertions.

## Changes

- R1: imports now retain the exact source XML, its content hash and structured losses. Unknown references remain in `BuildSpec.unresolved_refs`; a partial parse or unresolved reference blocks export recommendation even when the caller passes only the BuildSpec to the exporter. The caller must persist `BuildImport.source_document` under `build.raw_blob_hashes[0]` alongside normalized records.
- R2: support settings remain unsupported by the existing P01 schema. Import preserves their source XML and reports partial gameplay data. Every export containing supports is now incomplete and cannot be recommended. Preview XML still uses PoB defaults; it is explicitly not a faithful deliverable. No schema migration is introduced in this repair. Full support fidelity requires a later versioned support representation.
- R3: skill/item/config sets use their selected IDs; tree specs use the selected one-based position, following the upstream loader. Additional variants are retained in losses and make the result partial. Invalid or ambiguous selectors do not fall back to the first variant.
- R4: requirements from imported equipment take precedence for validation, and differences in either direction produce explicit post-import violations. Validator version is `p02-t03.1`.
- R5: applicable release publication timestamps determine the current patch independently of retrieval order. Missing, invalid or conflicting chronology produces an unknown current patch. Capture evidence is retained, repeated captures do not duplicate record IDs, and historical pins remain separate. Exporter version is `p02-t02.1`.

## Validation

After the session permissions changed, the complete offline suites and real-engine suite ran successfully. Commands from repository root:

```powershell
python -m pytest tests/unit tests/integration -q -p no:cacheprovider --tb=short
.venv/pr2-validation/py310-a/Scripts/python.exe -m pytest tests/unit tests/integration -q -p no:cacheprovider --tb=short
$env:POB2_ROOT = 'C:/Users/Elias/PycharmProjects/PathOfBuilding-PoE2'
python -m pytest tests/engine -q -p no:cacheprovider --tb=short
```

Results: **851 passed, 1 xfailed** on each of Python 3.12 and Python 3.10, and **99 engine tests passed** on Python 3.12. The expected failure is the existing P08-T01 production contract-binding case. There were no engine skips or deselected temporary-directory cases in these runs. The 23 new regression cases cover unknown reference retention, faithful controls, both support enabled states, all four active selectors, invalid selectors, variant reordering, capture order, release scope/ambiguity, requirement disagreements and a legal boundary.

Logs: [Python 3.12 offline](../evidence/PR-5/offline-py312.txt), [Python 3.10 offline](../evidence/PR-5/offline-py310.txt), [engine](../evidence/PR-5/engine-py312.txt), and [checkout context](../evidence/PR-5/verification-context.json). The engine used commit `ce566eac45ea8a86477f513c7ee65a1ebe60014e` with the existing dirty-status hash `063ac7ef27e11e3cb6ad942374129fbd11ef1869666bbbb59682fd395c1e3181`; this is not a claim of a clean upstream checkout. LuaJIT's native unwinding diagnostics were captured by the existing test fixture; pytest exited successfully. These are PoB-derived checks, not gameplay validation.

`git diff --check` passed. The pre-existing deletion of `external/PathOfBuilding-PoE2` is unrelated and excluded from this commit. The four accidental `.claude/worktrees/agent-*` gitlinks were removed from the index; their local working directories were preserved.

## Reassessment

The five reviewed defects are repaired and verified. The prior environment block on P02-T04 is resolved, including its controlled engine tests. P02-T02 through T05 are accepted for the declared implementation scope with the unsupported support-settings and multi-variant preservation limits above; this does not establish current-game compatibility, gameplay accuracy or acceptance of downstream gates. The PR is ready for approval and merge once CI passes on the pushed repair commit.

Recompute affected parsed records and evaluations; old complete/export flags are not trustworthy for documents containing unresolved content, support settings or multiple variants. Re-resolve patch profiles produced from mixed historical captures. A later support-schema extension must version identity and add real-engine support-state comparisons; it must not relax the current incomplete-deliverable guard.

## Earlier delivery block

Earlier staging failed with `Unable to create .git/index.lock: Permission denied`, and network access was blocked. After the permission change, GitHub confirmed PR #5's head still matched the reviewed base, fetching succeeded, and the formerly blocked verification ran as recorded above. The original review and its defect reproductions are retained as historical evidence.
