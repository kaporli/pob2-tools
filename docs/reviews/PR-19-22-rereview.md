# PR #19/#21/#22 repair review — 2026-10-19

> Historical review of the commits named below. Current task state and follow-ups are on [GitHub Issues](https://github.com/kaporli/pob2-tools/issues/23); this snapshot is not a current assignment list.

Reviewer: Codex. Specification 1.1 and the two recorded D07 amendments.

| PR | Reviewed head | Verdict |
|---|---|---|
| #19 | `128064ce40c10be47234dde48bee053fd1eb74d4` | **changes_required**: F1 below |
| #21 | `f73a7501de635f7b17acc0d797fe01b69120d78a` | **changes_required**: F1 inherited through coverage/capture |
| #22 | `c04d1c5bcb5f758f71aa52e15032cc2aa5c1f261` | **changes_required**: F2 below |

#18 and #20 are unchanged from the [previous review](PR-18-22.md) and retain their scoped acceptance. No production fixes, pushes, merge or external comment was made during this review.

## Original findings

The submitted regression cases for R1–R8 now pass. Active loadout selection uses the established P04 rules; stale/missing evidence blocks; target fields are explicitly matched; attribution is bound by content hash; engine/document provenance comes from capture; alternative windows cannot populate the v1 objective; unsupported methods are refused. The original mixed-rarity and partial-category probes now propagate uncertainty. These are substantive repairs.

The documented refusal of multi-loadout live captures with repeated skill names is an acceptable temporary limitation because it fails closed. It is not general multi-loadout evaluation support. Two further adverse cases prevent accepting the complete boundary.

## F1 — P1 — Enabled custom modifier blocks escape coverage (#19 and #21)

Locations:

- `pob2-optimizer/pob2opt/coverage/inputs.py:220`: reads only ConfigSet `Input` elements.
- #21 `pob2-optimizer/pob2opt/coverage/capture.py:66`: reads `cfg.varControls`, omitting the selected set's `customModsList`.
- #21 `coverage/capture.py:121`: binding verifies only the resulting explicit input map.

A selected config set containing `<CustomModifierBlock enabled="true">1000% more Damage</CustomModifierBlock>` produces an empty explicit config map and no blocking coverage finding. On #19 the independent settled coverage case returns `eligible=true`. On #21 a bound settled evaluator case also returns `eligible`, with no blocking gaps and an empty captured config list.

This is not merely an unknown XML tag. The pinned PoB loads these blocks in `src/Classes/ConfigTab.lua:941` and applies their parsed modifiers in `BuildModList` around line 1200. A native probe against the real seed confirms that adding this block changes Flicker `AverageDamage` from **136,232.22167473** to **1,507,975.8514644**, while `bind_capture` succeeds and captures no custom config row. The native example establishes the effect; the synthetic example isolates the eligibility bypass. The real seed remains blocked by its other gaps.

Impact: an author-supplied custom damage/resource modifier can enter captured values without any coverage rule establishing it. Binding the entire document hash establishes which document was loaded; it does not establish coverage of the omitted state inside that document.

Required repair:

1. Read custom blocks from the selected config set, including text and enabled state, and preserve them in capture/binding identity.
2. Until a specific supported mechanism covers them, make enabled nonempty custom blocks a typed blocking unsupported-config/modifier gap. Do not silently accept arbitrary modifiers because PoB parses them. Rejecting unsupported blocks is sufficient for this slice.
3. Preserve a known-disabled/empty block as inactive; respect active config-set selection. Handle the legacy customMods form and its PoB migration consistently.

Acceptance: extend both P06 coverage and P07 evaluation with the supplied custom-block case; it must yield a blocking gap and null objective even when every other rule is settled. Test enabled, disabled, empty, legacy and inactive-loadout blocks. Include native confirmation that an enabled block is represented in the capture or explicitly refused. Existing clean captures must remain reproducible.

## F2 — P2 — Reverse rarity uncertainty is still converted into a refusal (#22)

Location: `pob2-optimizer/pob2opt/catalog/slotrules.py:220–230` (`decide`).

The repair checks membership in the normal accepted-category set before consulting `undecided_rarities`. When the normal probe refuses Bow but the unique probe accepts it, the exporter correctly records `undecided_rarities['unique'] = ['Bow']`. Nevertheless, `decide` returns `refused`, and a unique Adherent Bow receives `CHECK_SLOTS=illegal` with `base_category_not_accepted`.

This is the reverse direction of the earlier mixed-rarity probe. It is a synthetic test of the promised uncertainty contract, not a claim that the current pin has that particular weapon rule. The real native matrix still passes.

Impact: a recorded unknown special-rarity combination is rejected as definitely impossible, and pool selection excludes it rather than marking it exploratory. R8 is not fully repaired for all exported uncertainty shapes.

Required repair: account for the applicable category/rarity uncertainty before returning a normal-category refusal. Keep unaffected combinations definite and preserve more specific known refusals. Make legality and pools use the same tri-state result.

Acceptance: normal-refused/unique-accepted and normal-accepted/unique-refused probe differences must both yield unknown for the affected special-rarity item, with the gap cited and any retained pool candidate explicitly exploratory. Normal/refused unaffected cases must stay refused. Re-run the existing native slot matrix.

## Requested decisions

**Broader community-PoB assumptions:** no blanket approval is recorded here. The current D07 amendment specifically adopts charges, Charged Staff and Hit and Run, not all condition toggles. A deliberate versioned method may assume specified Rage/Trinity states, provided their exact values, applicability to the build and limitations are exposed. That is a model-policy choice, not validation of sustain. Way of the Stonefist needs a separate check of glove/base/modifier transformation and requirements; classifying an absent implementation as an assumed toggle does not implement its effect. First establish what the pinned engine actually computes, then decide how to handle any gap.

**Proposed attribution table** (`sha256:b0a9fd762ab6991447140bd247c0a6efe85e66f0d4e0e887df90735175a9ef6e`): the direct-hit ownership is sensible—Flicker hits including buff damage already included in those hits count once; Whirling Assault, separate Charged Staff attacks and Living Lightning damage remain separate. I do **not** approve the table unchanged for the full stated objective: its accompanying `not_modelled` metadata calls Flicker-generated ignite "unrelated" and excludes it. D07 explicitly accommodates attributable secondary/ailment damage. Keep this as unresolved attribution/implementation, or obtain an explicit decision to define a separately identified hit-only benchmark. The table being a proposal is not itself a production-code defect; it must remain unaccepted until the scope is clear.

**The two decisions alone are insufficient for a supported score.** The stored seed has 22 blocking entries (some are duplicate manifestations of one gap), including current-patch compatibility, reference build/result/conditions, Stonefist, Rage, Trinity, Bhatair's Vengeance, Blazing Critical, Concussive Runes and Living Lightning. A reference gap still explicitly requires `pob-cycle-v1` even though the selected method is `pob-community-v2`; revise that obsolete prerequisite rather than satisfying it by pretending a generated-charge run exists. Accepted ownership can remove attribution duplicates but does not implement the other effects. Q11 map/boss selections remain milestone-2 work.

The unchanged **231,631.3984 sustained / 241,702.3288 burst** result is a Pounce-off diagnostic, not an accepted prediction or optimum.

## Verification and scope

[Evidence and reproduction](../evidence/PR-19-22-rereview/README.md).

- Current GitHub heads are green on both interpreters.
- Focused Python 3.12 tests: #19 **53 passed**, #21 **44 passed**, #22 **32 passed**.
- Combined tree (#21 plus #22, both manifest entries retained): **1,839 passed, one expected prepare-service xfail on each of Python 3.10 and 3.12**.
- Clean pinned native run: **7 submitted tests passed** (loadout selection, evaluator capture/agreement, slot rules). The initial additional reviewer probe failed its overly precise expectation of exactly 11x damage; its output still showed the missing custom-block coverage. After correcting the probe to test the actual hypothesis—materially increased damage with no captured custom block—it passed separately. Both logs are retained.
- No memory/time guard fired. Native maximum observed process-tree RSS was about 1.24 GiB. No full native suite, live trade, gameplay measurements or campaign soak was rerun.

## Next work

Fix F1 on coverage and propagate it into #21; fix F2 on #22; then re-review and rerun checks on the final heads. Retain scoped acceptance of #18/#20. Afterward, resolve attribution scope and the explicitly listed seed mechanics/protocol gaps before promoting diagnostic DPS to an objective. Do not unblock the score by blanket-settling the 22 entries.
