# P03-T02 follow-up acceptance

> Historical review of the commits named below. Current task state and follow-ups are on [GitHub Issues](https://github.com/kaporli/pob2-tools/issues/23); this snapshot is not a current assignment list.

- Reviewer: Codex, 2026-10-13; specification 1.0.
- Reviewed repair implementation: `2e2fada116f6af778dff27bd3c285999485e8961`, following PR6 head `377c45f`.
- Verdict: **accepted** for local acquisition and shared HTTP behavior. Supersedes the remaining P03-T02 findings from the October 12 review. No live provider or corpus coverage is accepted by this record.

Exact final-resource keys now bind both validator dispatch and 304 reuse. Query order is preserved, redacted URLs are display-only, and pre-repair cache entries lacking an exact identity are refetched. Saved provider cooldowns are restored during normal service construction and merged with stricter live deadlines. XML signatures/declarations are resolved before non-ASCII bodies are decoded; unsafe declarations and incompatible encodings still produce typed refusals.

`python -m pytest tests/unit tests/integration -m 'not engine and not network and not longrun' -q` passed **1,040 tests with one expected P08 failure** on Python 3.12.4 and 3.10.22. The acquisition-focused subset passed 134 tests on both interpreters. No live acquisition or native engine run was used.

Independent reproduction: `python docs/evidence/PR-6/review_followup.py <checkout>`. Before/after JSON is retained beside that script for both interpreters. After repair: changed redirect queries return the second build with no foreign validator; duplicate query order has distinct keys; fresh services send zero requests during cooldown and retain the deadline; declared Latin-1 imports successfully.

Behavioral regressions additionally cover unexpected 304 responses, normal redirected cache hits, exact-key persistence without storing tokens, stale cache metadata, exhausted-attempt cooldowns, independent providers, stricter existing deadlines, UTF-16/Latin-1/Windows-1252 direct and compressed inputs, and malformed encodings. Existing cross-origin credential, response-close, unsafe XML, path-policy and JSON-depth tests remain passing.

Reassessment: P03-T03 may consume the repaired transport once a provider-specific manifest is accepted. The existing blocked findings for named-source automatic retrieval remain; a supplemental pobb.in explicit-link adapter and local-import parsers are separate deliverables. No earlier P01/P02 gate is reopened.
