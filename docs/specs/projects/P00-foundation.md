# Reproducible foundation and characterization

Project ID: P00. Dependencies: none. Goal: establish a repeatable development environment and preserve evidence of current behavior before replacement. This project does not claim correct game modeling.

Read [research findings](../research.md), [architecture](../architecture.md) and [review procedure](../review.md). Do tasks in order. Use `tests/unit/`, `tests/fixtures/`, `tests/engine/`, and `tests/integration/` at repository root; fixtures carry a small provenance manifest.

## P00-T01 Record the environment and current baseline

1. Record git commit/status, OS, Python architecture/version, package versions, PoB path and runtime presence in `docs/evidence/P00/environment.md`. Do not record secrets or environment variables unrelated to this project.
2. Identify local changes, especially the absent submodule. Do not overwrite or restore user changes without first determining whether they are intentional. A separately configured PoB checkout is acceptable.
3. Document exact clean-install commands for both editable packages and test dependencies. Pin tested dependencies and record upstream PoB commit. Do not auto-update upstream during tests.
4. Capture one existing run if available. Otherwise record its absence; never fabricate a baseline output.

Acceptance: another engineer can follow the recorded setup; absence of PoB is a named blocker for engine tests, while offline tests can run. Existing user modifications remain intact.

## P00-T02 Introduce an assertion based test harness

Add pytest configuration with markers `engine`, `network` and `longrun`. Default test invocation excludes network and long runs; engine tests explicitly skip with a reason when runtime is absent. Add portable fixture paths and remove machine-specific assumptions from the smoke-test path when converting it to assertions.

Create synthetic fixtures for malformed build data, legitimate zero DPS, a two-choice synergy search space and a deterministic tiny combat sequence. Clearly mark them synthetic. Make no claims about current PoE mechanics from these fixtures.

Acceptance: `python -m pytest tests/unit` runs offline; `python -m pytest -m engine` reports an actual failure/pass or an explicit skip; no print-only script can report a passing gate. Test collection does not boot PoB or contact a website.

## P00-T03 Add environment diagnostics

Implement `doctor` from the interface spec. Return named checks for Python version/bitness, package importability, selected PoB directory, DLL presence, tree/catalog evidence, configured provider capabilities and writable run location. Check existence without installing, downloading, opening a browser or starting OAuth.

Acceptance: fixture tests cover missing directory, missing DLL, incompatible profile and valid offline environment. Diagnostics never print cookies/tokens. Calling from a directory containing spaces works. Parent working directory does not change.

## P00-T04 Characterize engine and scoring behavior

Add regression reproductions for F02, F05, F10, F11 and F12 from research. Use synthetic doubles for scoring/control-flow bugs and pinned engine fixtures for real conversion/state behavior. Record current outcome and expected repaired outcome separately. Mark known failing expectations with strict xfail linked to the repair task; remove the xfail when the repair lands.

Measure engine cold start, warm reset, representative evaluation time and peak worker memory. Use at least ten warm evaluations and record hardware; report measured values, not universal throughput claims. Verify an A-B-A evaluation sequence to identify state leakage.

Acceptance: every investigated finding has either a reproduction, evidence of nonreproduction or a specific blocker. No speculative defect is silently treated as proven.

## P00-T05 Establish verification and review artifacts

Create the future `docs/worklog/` and `docs/reviews/` structure and a test manifest listing commands and prerequisites. Configure the repository's chosen CI runner for offline tests; document a Windows engine lane if its external runtime cannot be provisioned in CI. Live provider tests remain opt-in and redacted.

Acceptance: offline CI or an equivalent reproducible local script passes; engine absence is visible and not counted as integration success; P00 handoff includes timings, fixture inventory, dependency versions and untouched-worktree evidence. Request G0 review before foundational dependent work is accepted.
