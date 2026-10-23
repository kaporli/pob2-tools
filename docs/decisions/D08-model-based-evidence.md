# D08 Model based evidence and delivery

- Date: 2026-10-23.
- Authority: the owner states that no in-game clips or measurements can be supplied, asks about REA as an alternative, and requests migration of all outstanding work to GitHub Issues following that discussion.
- Product direction: pursue useful model-based optimization without owner-supplied gameplay recordings. This record accepts no implementation or empirical-accuracy claim.

## Evidence approach

Use versioned PoE 2 data, inspectable PoB source, analytical reference cases and carefully scoped recovered-code evidence. PoB already documents a [game-data exporter](https://github.com/PathOfBuildingCommunity/PathOfBuilding-PoE2/blob/dev/CONTRIBUTING.md). [REA](https://github.com/morluto/rea) may help investigate specific native functions after data/source inspection; it does not guarantee access to server-only logic or prove that a client tooltip reproduces combat.

For each rule retain exact input versions, source/function references, assumptions, boundaries and tests. Distinguish extracted values, PoB-derived behavior, inferred/reconstructed rules and independently observed outcomes. Never promote decompiler output to a gameplay-checked rule by default.

## Delivery and reporting

G3M is a separate model-based offline acceptance tier. It retains faithful input, legality, critical mechanics coverage, time/resource/attribution accounting, search validation, reliability and export requirements. Clear/boss results are explicitly modeled predictions, with assumptions and sensitivity reported. Unknown critical mechanics remain blocking gaps; no default positive constant replaces them.

Original G3 empirical gameplay acceptance remains a separate tier. Suitable third-party observations may later support it, but user recordings, a recording quota and user-supplied encounter names are not prerequisites for G3M. This does not relabel model results as gameplay validated or automatically change persisted schema semantics.

D07's sustained `[0,120)` and burst `[0,5)` windows and accepted community-PoB charge/Charged Staff method remain. Further condition assumptions need explicit versioned definitions; an assumption cannot stand in for missing item-transformation code.

## Implementation references

Work and review are tracked in [model acceptance](https://github.com/kaporli/pob2-tools/issues/132), [targeted data/reverse engineering](https://github.com/kaporli/pob2-tools/issues/36), and the [G3M review](https://github.com/kaporli/pob2-tools/issues/40). Contracts and benchmark bundles change only through those reviewed implementations. Old evidence and results retain their historical meaning.
