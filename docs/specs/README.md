# Path of Exile 2 optimizer specifications

These documents define the technical behavior of a PoE 2 optimizer targeting maximum sustained Flicker Strike DPS, with clearing, bossing, survival and resource requirements. Implementation work and historical completion are tracked exclusively in the [GitHub delivery index](https://github.com/kaporli/pob2-tools/issues/23).

Specification 1.1 retains its schema and objective contracts. [D07](../decisions/D07-flicker-strike-objective.md) records the Flicker objective and accepted PoB method; [D08](../decisions/D08-model-based-evidence.md) records the model-based evidence direction without owner gameplay recordings. This documentation migration changes no runtime schemas or numerical results.

## Read in this order

1. [Product requirements](product.md) and applicable decision amendments.
2. [Architecture](architecture.md), [contracts](contracts.md) and [interfaces](interfaces.md).
3. [Scenarios](scenarios.md), [acceptance examples](acceptance-examples.md) and [acceptance definitions](acceptance-gates.md).
4. The assigned GitHub issue, its dependencies and [review procedure](review.md).
5. [Historical research](research.md) when investigating the original findings.

When documents conflict, owner decisions and product requirements take priority, then contracts and scenarios, then implementation tasks. Raise concrete unresolved conflicts on the issue. Task IDs remain permanent references even though their descriptions moved to GitHub.

## Project navigation

| Project issue | Scope |
|---|---|
| [P00](https://github.com/kaporli/pob2-tools/issues/24) | Reproducible foundation and characterization |
| [P01](https://github.com/kaporli/pob2-tools/issues/25) | Shared records and persistence |
| [P02](https://github.com/kaporli/pob2-tools/issues/26) | PoB adapter and correctness repairs |
| [P03](https://github.com/kaporli/pob2-tools/issues/27) | Build source acquisition |
| [P04](https://github.com/kaporli/pob2-tools/issues/28) | Parsing and build normalization |
| [P05](https://github.com/kaporli/pob2-tools/issues/29) | Trade access and equipment candidates |
| [P06](https://github.com/kaporli/pob2-tools/issues/30) | Mechanics coverage and missing evidence |
| [P07](https://github.com/kaporli/pob2-tools/issues/31) | Encounter and rotation evaluation |
| [P08](https://github.com/kaporli/pob2-tools/issues/32) | Build search and resumable runs |
| [P09](https://github.com/kaporli/pob2-tools/issues/33) | Benchmarks and independent validation |
| [P10](https://github.com/kaporli/pob2-tools/issues/34) | Reports and end to end delivery |
| [P11](https://github.com/kaporli/pob2-tools/issues/35) | Optional learning experiments |
| [P12](https://github.com/kaporli/pob2-tools/issues/36) | Game-data and targeted reverse-engineering evidence |

## Working with issues

Select a bounded task whose prerequisites are accepted. Read the full issue and shared contracts; reuse existing modules and records. Post the [handoff](templates/handoff.md) as an issue comment, naming commits, exact commands, evidence, negative cases and remaining limits. Submit the linked PR for independent review before merge. Keep all current status and follow-up assignments on GitHub.

Store redacted durable fixtures and logs under `docs/evidence/`; retain exact artifact and context hashes. Do not recreate `docs/worklog/` or in-repository project task lists. The issue's live state supersedes historical review wording.

## Claim boundaries

The model-based offline tier can be delivered without owner recordings, automatic source access or live trade. It must identify predictions and assumptions and preserve critical coverage/legality refusals. Empirical gameplay superiority and live availability require their own evidence. A successful PoB comparison establishes PoB consistency, not independent game accuracy. Optional learning must not delay the non-learning optimizer.
