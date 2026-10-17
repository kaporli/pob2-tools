# Build source acquisition

Project ID: P03. Dependencies: G0 and P01-T01/T03. Goal: obtain versioned source material from Mobalytics, Maxroll and poe.ninja with an honest record of what is accessible. Acquisition does not normalize builds or certify mechanics claims.

## P03-T01 Produce per source capability manifests

For each named provider, inspect its documented interfaces, public export/share options and representative pages. Limit the initial study to five representative records: current endgame, multiple variants, old patch, sparse/incomplete and unusual build. If a category is unavailable, record that rather than substituting it invisibly.

Save `docs/evidence/P03/<provider>-capabilities.json` with inspection date, source links, permitted access method/evidence, fields visible, structured export formats, pagination behavior, authentication, rate/size limits if known, blocked cases and recommended adapter path. Do not reverse-engineer undocumented service endpoints as a shortcut. Browser-visible text is not evidence that complete item/tree data is exportable.

Acceptance: every provider has either a reproducible acquisition example or a specific `unsupported_access`/blocked finding. Listing metadata, full build data and explanatory prose have separate support flags. Reviewer selects the first usable provider from evidence; Mobalytics is the initial candidate, not a guaranteed winner.

## P03-T02 Implement local acquisition and shared HTTP behavior

Implement file/code/URL input handling and immutable SourceDocument writes. Build a shared HTTP layer with explicit host policy, typed failure statuses, request limits, size limits, conditional requests when supported and provider-specific scheduling. Follow the interface timeout/retry rules. Acquisition must work independently of PoB.

Acceptance: saved XML, build code, HTML and JSON each become raw records with matching hashes. Repeated input is idempotent. Simulated 403, 404, 429, oversized payload, timeout and malformed content never become successful empty builds. Credentials are absent from blobs/logs/exported URLs.

## P03-T03 Implement the first approved provider adapter

Use the accepted capability manifest. Implement URL discovery/pagination only through its accepted method. Keep guide IDs, variant links, authors, timestamps, declared patches, popularity field names and export references. Store guide text and structured export as separate linked documents. Allow explicit URLs so a full crawl is never required.

Acceptance: golden saved fixtures and an opt-in small live smoke check agree on metadata extraction. All five inspected categories are processed or produce a documented partial status. Interrupted acquisition resumes from cursor without duplicating raw records. Missing patch/update date remains null.

## P03-T04 Implement the other two provider paths

Create independent adapters for the remaining named sources using their manifests. If automatic access is unresolved, deliver local provider-export/manual-capture import with a clear capability flag and keep the automatic-adapter task portion blocked. Do not mark three live integrations complete because all use the same generic HTML importer.

Acceptance: a cross-provider matrix lists acquired fields, formats, live status, limitations and evidence. Sources without votes use absent popularity metadata. A character snapshot remains a snapshot; do not synthesize guide explanations for it.

## P03-T05 Build a diverse versioned corpus

For the first corpus target, acquire 30 usable endgame build variants from at least two sources and six build families where available. Prioritize complete Flicker Strike exports and at least three independently reviewed interaction variants within that skill where available (D07); surrounding families may supply controls and enabling-mechanic evidence. This is an engineering coverage target, not statistical proof. Do not count synthetic fixtures as source builds or renamed duplicates as distinct variants. If availability prevents the target, report actual coverage and seek scope review; local-file collection may proceed while automatic providers are blocked.

Store a corpus manifest with selection strategy, patch distribution, creator/family counts, failures and source limitations. At most half the collection budget should be popularity-prioritized; spend the rest on distinct mechanics and less represented families. Deduplicate source IDs during acquisition; semantic family deduplication belongs to P04.

Acceptance: every corpus entry has raw evidence and source provenance; no inaccessible source is counted as represented. Import can be replayed offline. Corpus selection does not use claimed DPS or votes as ground-truth performance labels.
