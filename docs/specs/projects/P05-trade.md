# Trade access and equipment candidates

Project ID: P05. Dependencies: P01 records/storage; item normalization needs P04-T03; exact item evaluation needs P02. Goal: remove hidden budget restrictions, preserve item fidelity and integrate real availability. A functioning manual import is an intermediate deliverable, not completion of live trade.

## P05-T01 Resolve access and application identity

Review the current provider interfaces and the [access findings](../research.md). Record an accepted integration route with allowed operations, identity requirements, limits, payload example and failure behavior. Do not assume the current website endpoints or another application's OAuth identity are a supported contract.

Separate account-character import from public market acquisition. If no supported live route is available, return `unsupported_access`, leave live acceptance blocked and continue P05-T02/T03 with imported items. Do not attempt token/cookie workarounds to pass the gate. Source restrictions and application registration conditions must be checked at implementation time.

Acceptance: reviewer approves a concrete route or records D01 as unresolved. No provider implementation receives live-capable status from code inspection alone. This task does not authorize messages to providers or seller contact.

## P05-T02 Implement the item and listing import path

Support explicit item text and approved provider export JSON. Preserve base/rarity/quality, requirements, sockets, modifier categories, flags and original item text. Use P04 entity resolution and P02 conversion tests. Store item properties separately from listing ID, price and acquisition metadata.

Remove assumptions that price is exalted or bounded. Keep unknown/unpriced items with `price: null`; unlimited budget must not exclude them automatically. Deduplicate listings by provider/league/listing ID and items by canonical stats, never display name. An item imported without listing evidence has unknown availability.

Acceptance: same-name different-roll items remain distinct; equal-stat separate listings can both exist; a high-price non-exalted listing survives import; missing price is not zero. Modifier conversion fixtures include all categories supported by the target patch and round-trip without silent loss.

## P05-T03 Build equipment pools across all supported slots

Replace the weapon-only harvester with a catalog-driven slot pool: weapons/sets, armor, jewelry, socketed equipment and auxiliary slots as supported by the accepted catalog. For each slot, combine owned items, imported listings and approved queries. No hidden monetary cap, price-based outlier rejection or fixed eight-item restriction.

Initial retrieval budget: up to 500 listings per slot plus at most 100 explicit enabling-interaction queries per run, configurable and manifest-recorded. These are sampling bounds, not an exhaustive-market claim. Retain required enabling items even if their standalone DPS is poor. Select diverse candidates by base, special effects and relevant stat combinations; do not retain only highest weapon DPS. Report truncation, missing categories and query coverage.

Acceptance: a synthetic fixture with a weak standalone enabler survives pool construction and enables the best pair; a listing cannot occupy both ring slots simultaneously without sufficient quantity; changed equipment rechecks full-build requirements and resources. No-budget mode never generates a price maximum. Pairwise/full configuration evaluation is deferred to P08, not replaced by adding per-slot gains.

## P05-T04 Implement the approved live transport and refresh

Only after T01 accepts a route, implement MarketProvider query and refresh. Use provider limits across the entire coordinator, not per worker. Schedule full retry delays without blocking cancellation. Handle authentication failure, explicit missing listing, empty legitimate results, truncation, transient failure and schema drift distinctly. Network calls never run inside PoB workers.

Every snapshot stores request scope and observation time. Before final market-mode output, refresh all selected listings and substitute only through reevaluation. A unavailable/failed refresh is not proof of a sale. Without successful refresh, mark current availability unknown; never describe the build as currently obtainable.

Acceptance: simulated rate-limit bursts produce no early retry; 403 cannot become empty success; pagination deduplicates; partial refresh preserves per-item states. A small approved live test produces usable listings with evidence. Automatic buying and seller messaging are absent.

## P05-T05 Integrate unlimited budget and acquisition reporting

Remove medium/cheap/BiS tier weighting from new search. Price is descriptive unless a future explicit spending constraint is selected. Report native-currency totals grouped by currency; optional conversion requires a timestamped rate and never implies a guaranteed purchase price. Display actual item/query links when available, required rolls and substitutes that have been evaluated.

Define availability labels: `verified_at_snapshot`, `partially_verified`, `unknown`, `unavailable`. Choose `verified_at_snapshot` only when every required non-owned listing was successfully rechecked in the final refresh session; show the time and never guarantee purchase. Do not merge historical best listings into a fictional current snapshot.

Acceptance: completed candidate resolves every equipped ItemInstance; observed-market mode contains no invented rares; removing a crucial listing either produces a reevaluated substitute or downgrades availability. G4 requires the accepted live route and successful live evidence, not only mocks.
