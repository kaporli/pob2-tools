# PR #19/#21/#22 final repair review — 2026-10-20

> Historical review of the commits named below. Current task state and follow-ups are on [GitHub Issues](https://github.com/kaporli/pob2-tools/issues/23); this snapshot is not a current assignment list.

Reviewer: Codex. Specification 1.1 and the recorded D07 amendments.

| PR | Reviewed head | Verdict |
|---|---|---|
| #19 coverage | `96d891489f236462c3cdd4f49fad5bd8fa54ff82` | **accepted within delivered coverage scope** |
| #21 evaluator | `9ee474e61c85ea0545b4b2b4bedb37785ea7d3fd` | **accepted within the declared first evaluator slice** |
| #22 slot rules | `321cc2ae01a5c94e96e37cf0bac92856a0f24a61` | **accepted within delivered slot-rule scope** |

This supersedes the changes-required verdicts in [the previous re-review](PR-19-22-rereview.md). #18 `4434cbe` and #20 `74369ff` are unchanged and retain their scoped acceptance. No further blocking findings were identified in the repair diffs.

## Repair acceptance

| Finding | Independent verification | Disposition |
|---|---|---|
| F1: custom modifier blocks escape coverage (#19) | The original probe now returns `eligible=false` with `unsupported_modifier`. Selected-set blocks, legacy migration, enabled/default-enabled, disabled, empty and inactive-set cases are covered. Missing or mismatched captured blocks invalidate the binding. | **Closed** |
| F1: the omission reaches eligible scoring (#21) | The original settled evaluator probe now returns `status=blocked`, `score=null`, and the explicit custom-modifier gap. Native capture preserves selected block text/title/enabled state. Clean frozen/live values and fresh-worker evaluations still agree. | **Closed** |
| F2: reverse rarity uncertainty becomes a definite refusal (#22) | The unchanged independent probe now returns `undecided`, legality `unknown`, and no violation. Both directions of rarity disagreement retain exploratory candidates and cite gaps; unaffected refusals remain refused. | **Closed** |

The repairs preserve the original R1–R8 regression coverage. They introduce no blanket approval of PoB config assumptions or arbitrary custom modifiers. Enabled nonempty custom blocks remain unsupported until an explicitly implemented mechanism covers them; disabling a block and recapturing is supported.

## Verification

[Durable evidence and commands](../evidence/PR-19-22-final-review/README.md).

- GitHub CI is green on Python 3.10 and 3.12 at each reviewed head.
- Focused Python 3.12 checks: #19 **60 passed**, #21 **51 passed**, #22 **35 passed**.
- Original independent F1/F2 probes were rerun unchanged against the three new worktrees and now show the required behavior.
- **Nine native checks passed** against clean pinned PoB `ce566eac45ea8a86477f513c7ee65a1ebe60014e`: loadout selection, custom-block state/capture, frozen/live evaluator values, fresh-worker agreement, and the real item slot matrix. Parent monitor reported no guard event and approximately 1,003 MiB peak process-tree RSS.
- Combined offline suites: **1,856 passed, one expected prepare-service xfail on each of Python 3.10 and 3.12**. Complete logs are in the evidence directory. The combined checkout contains all five deliveries: #21 includes #18/#20 and the repaired #19; #22 was merged into it locally without committing. Only `tests/MANIFEST.md` conflicted; both native-test rows were retained.
- No full native suite, campaign soak, live trade or gameplay validation was repeated. This review does not claim the historical native memory issue is fixed.

## Merge disposition

Code review is approved for all five PRs within their delivered scopes. Merge **#18 → #20 → #19 → #21 → #22**. When reconciling #22 with the preceding merges, retain both new native-test rows in `tests/MANIFEST.md` and obtain green checks on the resulting head. No production branches were modified or pushed during this review; the conflict was resolved only in the isolated test checkout.

## Residual scope and next work

Merging these deliveries does not accept the seed's diagnostic DPS as a supported objective, approve the proposed attribution table, or complete milestone 1. Existing typed blockers remain intentional. In particular:

1. Settle attribution scope, including Flicker-generated ailments. Do not call a genuinely attributable but unmodelled contribution unrelated merely to close a gap.
2. Define any additional community-PoB state assumptions explicitly and version them. Verify Way of the Stonefist's item transformation separately; an assumption cannot implement a missing effect.
3. Resolve the seed's remaining mechanics and current-patch/protocol/reference gaps, including obsolete generated-charge prerequisites under the selected community method. Re-evaluate using bound captures and reviewed rules.
4. Then finish production preparation/search integration and milestone-2 clear/boss/survival work. Q11 encounter names are still needed there.

Multi-loadout live capture with repeated skill names is still refused rather than mapped. Partial/stat-known items remain exploratory, not recommendation-ready. Parent-item jewel sockets, unresolved keystone contexts, live-market access and broad game coverage retain their stated limits. These limits are explicit and do not reopen the closed F1/F2 code defects.
