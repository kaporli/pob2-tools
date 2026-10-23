# PR #5 review

> Historical review of the commits named below. Current task state and follow-ups are on [GitHub Issues](https://github.com/kaporli/pob2-tools/issues/23); this snapshot is not a current assignment list.

This is the original review of `3d7ba53`. The [repair verification](PR-5-repair-verification.md) records the subsequent fixes, successful full test runs and updated disposition.

- Scope: P02-T02 through P02-T05, specification 1.0.
- Reviewed revision: `3d7ba53cb703e4794755c083da443019ab30bbe7`, local `p02-engine-remaining` and cached remote ref.
- Base: `0df64ddf338e64ce3affdce1da0a6769934f6db5`.
- Reviewer: Codex, 2026-10-10.
- Verdict: **changes_required**. Do not merge this revision.
- Access limitation: GitHub API access failed through the environment's network proxy; the web fallback did not return the PR. Live head, PR metadata and CI were not verified. This verdict applies to the local revision above.

## Confirmed findings

### R1 — P1: Unknown gameplay content is discarded and then recommended

Locations: `pob2-optimizer/pob2opt/evaluation/builddoc.py:649`, `:715`, `:803`.

`_import_tree` and `_import_skills` skip unresolved native IDs. `import_build` nevertheless sets `parse_status=COMPLETE`, clears `unresolved_refs`, and retains no raw source blob. Adding one unknown passive and one unknown enabled skill to the supported XML fixture produces a complete BuildSpec with neither entity. Running the public round-trip check on that imported build returns `faithful` and `recommended_deliverable=True`.

This defeats the project's central missing-data requirement: the resulting build cannot tell downstream code which catalog data to ingest. A hash comparison after the lossy import cannot establish fidelity to the original document.

Required repair: retain unresolved IDs and source content, produce structured import losses, and propagate them into export/recommendation eligibility. Do not mark an import complete when gameplay content was skipped. Apply this to unresolved nodes, gems, slots, classes, ascendancies and socket references, not just the two demonstrated fields.

Acceptance: import XML containing a known skill plus an unknown enabled skill and an unknown passive. The unknown native IDs must remain recoverable; status must be incomplete/partial and a later round trip must not recommend it. A fully resolved control must still pass.

### R2 — P1: Support settings are lost and disabled supports are re-enabled

Locations: `pob2-optimizer/pob2opt/evaluation/builddoc.py:805` and `:328`–`:342`.

Import reduces each support to its ID before reading its `enabled`, `level` or `quality` attributes. Export hardcodes `enabled=true`, omits level/quality and classifies missing support data as non-identity metadata. In the independent probe, a support with `enabled=false`, level 7 and quality 19 becomes enabled with neither numerical attribute. The round-trip report still says `faithful` and recommends the result.

This changes combat configuration. The existing `support_ids: list[str]` contract cannot express the input, so equality of its reduced identity is insufficient evidence of preserved gameplay semantics.

Required repair: either extend/version the support representation and canonical identity to preserve these settings, or retain them as unsupported gameplay data and block recommendation. Do not classify missing combat settings as harmless metadata. Update the P01 contract explicitly if extending the record.

Acceptance: round-trip disabled and enabled supports with distinct numerical settings. Preserve each setting or report an incomplete, non-recommended result. Include an engine comparison for the supported representation.

### R3 — P1: Active build variants are ignored

Locations: `pob2-optimizer/pob2opt/evaluation/builddoc.py:683`, `:709`, `:785`, `:832`.

The importer selects the first `ItemSet`, `Spec`, `SkillSet` and `ConfigSet` without consulting the active selectors. The probe appends a second known skill set, marks `activeSkillSet=2`, and imports it. The first set is returned and marked complete. Real multi-variant documents can therefore load a different tree, equipment, skill configuration or conditions from those selected in PoB.

Required repair: resolve each container's active selector according to PoB's format, and explicitly handle missing/invalid selectors. Preserve additional variants or report that they are unsupported instead of silently erasing them.

Acceptance: provide two distinct sets in each container, select the second, and verify that import agrees with PoB. Reordering inactive sets must not change the selected build. Test an invalid selector and report incompleteness rather than silently choosing the first set.

### R4 — P1: Normalized requirements override stricter imported requirements

Location: `pob2-optimizer/pob2opt/evaluation/legality/context.py:122`–`:131`; post-import comparison in `checks.py:1291` does not catch this disagreement.

`Equipped.requirement` trusts the normalized record before the engine's imported item. The probe supplies a level-4 character with 120 Strength, a normalized ring requiring level 1/Strength 1, and the imported ring requiring level 90/Strength 999. Both `item_requirements` and `post_import_verification` report `legal`, with no violations. Overall legality is currently `unknown` because of the unrelated slot-category gap; that gap does not make these successful checks correct.

Required repair: compare item requirements between the record and the imported state, report a mismatch explicitly, and validate the actual imported requirements. Do not silently select the more permissive source. Cover the reverse disagreement as well.

Acceptance: the demonstrated case must report unmet requirements and/or explicit state mismatches, never legal requirement/import checks. Equal requirements at the boundary must pass. Retain an unknown result when neither source establishes a required value.

### R5 — P2: Recapturing an older release changes the alleged current patch

Locations: `pob2-optimizer/pob2opt/catalog/release.py:140` and `catalog/export.py:358`.

Release captures are sorted by retrieval time, then the last capture is declared live. An older release retrieved after a newer release consequently wins. The probe supplies patch 0.5.5e published October 1/captured October 2 and patch 0.5.4 published September 1/captured October 3. The exported current profile declares 0.5.4. These dates are synthetic, not release-history claims.

Required repair: resolve the live release from applicable publication/release evidence, independently of acquisition order. Filter by the requested game/realm; handle ambiguous or missing chronology as a gap. Preserve capture timestamps for provenance and keep historical pins separate from live resolution.

Acceptance: reversing capture order or recapturing an older patch must not change live resolution. Include missing-date and conflicting-evidence cases, plus historical pinned-profile coverage.

## Reproductions and checks

- Independent, offline probes: `python docs/evidence/PR-5/reproduce.py`. All five observed-defect assertions reproduced. Inputs are synthetic, using existing fixture builders; no engine/gameplay claim is made. [Observed results](../evidence/PR-5/observed.json), [probe source](../evidence/PR-5/reproduce.py).
- Focused command: `python -m pytest tests/unit/test_p02_t03_legality.py tests/unit/test_p02_t04_primitive_semantics.py tests/unit/test_p02_t04_rotation_estimates.py tests/unit/test_p02_t05_build_round_trip.py tests/unit/test_p02_t05_item_round_trip.py tests/unit/test_p02_t05_no_mutation.py -q -p no:cacheprovider --tb=short`: **128 passed**.
- Catalog command: `python -m pytest tests/unit/test_p02_t02_catalog.py -q -p no:cacheprovider --tb=short`: **47 passed, 3 setup errors**, all three at pytest temporary-directory access (`WinError 5`).
- Broad unit/integration attempt: 592 passed, 1 xfailed, 30 failed, 206 errors. This is **not a green run**. Temporary-directory access and multiprocessing pipe permissions prevent meaningful complete-suite verification; these counts are not presented as 236 PR defects. Retrying with workspace-local basetemp and Python 3.10 also encountered access denial.
- T04 engine attempt without `POB2_ROOT`: 18 skipped because the workspace submodule is absent. With `POB2_ROOT=C:/Users/Elias/PycharmProjects/PathOfBuilding-PoE2`, fixture boot emitted native exception diagnostics and execution stopped at `multiprocessing.Pipe` with `WinError 5`. Engine assertions were not independently reproduced. The submitted engine evidence is not a substitute for a successful reviewer run.
- Read the P02 specification, review procedure, four task handoffs, catalog/legality/primitive/round-trip implementation and relevant tests/evidence. Existing deletion of `external/PathOfBuilding-PoE2` was preserved. No implementation changes, commits, pushes or GitHub review submission were made.

## Task verdicts and reassessment

| Task | Verdict | Acceptance assessment |
|---|---|---|
| P02-T02 | changes_required | Offline entity/context/compatibility checks largely pass; current-patch resolution fails R5. Live catalog export remains unverified here. |
| P02-T03 | changes_required | Existing rule fixtures pass; independent post-import requirement case fails R4. Do not rely on unrelated unknown checks to mask an incorrect legal check. |
| P02-T04 | blocked | Offline semantics and timing regression checks pass. No confirmed implementation defect from this review; controlled engine acceptance remains unverified because execution is blocked. |
| P02-T05 | changes_required | Existing supported fixtures pass, but R1–R3 violate gameplay preservation and incomplete-deliverable requirements. |

Repair T02 patch selection and T03 comparison independently. Resolve the support-data contract before extending T05 import/export and identity tests. Then rerun the focused tests, the full unit/integration suite, controlled engine fixtures, and PoB XML round trips on a runnable environment at the final PR head.

Recompute affected imported builds, identities and evaluations after parser changes. Re-resolve live profiles produced from mixed historical release captures. No accepted P02-T01/P01 gate is revoked by these findings, but P01 support-schema changes require explicit revalidation if chosen. Do not advance G1 or downstream parser/evaluator release claims using the affected evidence. No user product decision is needed to fix these correctness failures.

Additional cleanup: four `.claude/worktrees/agent-*` gitlinks are included in the diff and should be removed from the delivery. This is separate from the five correctness findings.
