# Reports and end to end delivery

Project ID: P10. Dependencies: accepted contracts; report fixtures can start early, integration depends on P05/P06/P07/P08/P09. Goal: users receive reproducible builds with understandable strengths and limitations.

## P10-T01 Implement one report model

Generate `report.json` from stored immutable results, then render Markdown from that same object. Include request, exact scope, patch/PoB revisions, scenario/reference IDs, search budget/coverage, status counts, best-found/proof status, market snapshot and unresolved gaps. Regenerating a report must not silently reacquire or recompute anything.

Acceptance: JSON and Markdown numbers agree; a failed evaluation is never omitted from counts; no eligible results produces `no_recommendation` with actionable gaps; legacy scores cannot populate validated fields.

## P10-T02 Implement candidate explanations and exports

For every recommended candidate show: PoB XML/code export where supported, complete gear/passives/gems, clear and boss raw times/scores, relative strength label, survival/resource results, rotation steps, preparation time, execution rate, timing requirements, missed-action sensitivity and unsupported scope.

Show market items and links with native-currency prices, final refresh state/time, required rolls and evaluated substitutes. Explain theoretical/unverified items explicitly. Render source claim links and evidence status. Use deterministic templates initially; generated prose is optional and cannot invent numbers or mechanics.

Acceptance: a reviewer loads the export and repeats its measurements; text describes the exact evaluated configuration. If export loses a required mechanic, withhold the recommendation export and show the blocker. Strength labels follow the shared formula.

## P10-T03 Implement progress and cancellation presentation

Report progress at least every 30 seconds during active runs: elapsed/remaining budget, current best eligible scores, completed/error counts, family coverage, expensive evaluation count, gaps and last checkpoint. Avoid an invented percentage of all possible builds searched. Display waiting/rate-limited status when relevant.

Cancellation creates a final partial report with best verified candidates and unfinished-work count. Resuming uses the original context, not a silently refreshed market. Offer explicit new preparation to use new data.

Acceptance: simulated long task and provider delay do not suppress coordinator progress/cancellation; partial report is valid and clearly labelled; exit codes match interfaces.

## P10-T04 Deliver a reproducible offline walkthrough

Provide a small distributable fixture bundle and commands to import, parse, prepare, evaluate, search, resume and report. The offline walkthrough must require neither credentials nor source-site availability. Label synthetic/sample inputs and supported scope. Provide a separate real-engine walkthrough with setup prerequisites.

Acceptance: an engineer unfamiliar with the implementation follows the commands without editing source paths. Pure-fixture walkthrough works on a clean environment; real-engine walkthrough is exercised on Windows. Document exactly which commands are now implemented versus deferred.

## P10-T05 Run release review and capability audit

Submit all requirement IDs R01-R12 with evidence links, implementation task statuses and residual limitations. Mark live trade and each named source adapter separately. A limited offline or partial-source release requires explicit scope labelling; it cannot close the full product requirements by implication.

Acceptance: G3 accepts the validated offline scope and G4 accepts supported live acquisition separately. New source/parser/patch support cannot be advertised from an unreviewed branch. Update root and package README usage to the actual delivered commands at implementation time, retaining legacy migration notes.
