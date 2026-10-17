# P09-T01.1 evidence: Flicker Strike seed export and scope

Captured 2026-10-17 on Windows 11, CPython 3.12.4. Nothing here is a gameplay
measurement. Everything read out of Path of Building is PoB-derived.

## Seed export (`seed/`)

Account-character import of the owner's Forbidden Rites character (Monk /
Martial Artist, level 93, 116 passive points) through the operator's `pob2`
MCP server (`python -m pob2mcp.server`, package at
`C:/Users/Elias/PycharmProjects/pob2-mcp`). D01 keeps this apart from market
access; no provider build source was used. The call sequence is in
`seed/manifest.json`. The character name is recorded there only.

| File | What |
|---|---|
| `export-as-imported.xml` | `build:SaveDB("code")` right after import; main skill Herald of Ice (group 5) |
| `export-as-imported.code.txt` | Share code of that document, with the server's encoding; decodes to it byte for byte |
| `export-flicker-main.xml` | Same build with Flicker Strike (group 6) as main skill |
| `items-raw.json` | Raw item text per slot |
| `skill-groups.json` | Socket groups with gem ids, granted-effect ids, levels, quality, descriptions |
| `passive-nodes.json` | The 126 allocated nodes with names and stats |
| `config-input.json` | PoB config input after import |
| `stats-flicker-main.json` | PoB scalar outputs with Flicker Strike selected. `proxy_only` |
| `manifest.json` | Provenance, SHA-256 of every file, the owner's rotation verbatim |

The engine was the operator's checkout `C:/Users/Elias/PycharmProjects/PathOfBuilding-PoE2`,
HEAD `ce566eac45ea8a86477f513c7ee65a1ebe60014e` (read from `.git/refs/heads/dev`),
engine version 0.23.1. Its working tree was not checked
(`gap-p09-t011-engine-checkout-state`).

Share code check: the code regenerated from `export-as-imported.xml` has the
same length (11 752 characters), first 80 and last 40 characters as the
`export_build_code` output of the same session.

## Mechanics extract (`mechanics.json`)

```
python scripts/p09_t01_1_mechanics.py
```

Run against `external/PathOfBuilding-PoE2` initialised at the pin
`ce566ea`, `git status` empty. 25 entries: Flicker Strike, Whirling Assault,
Charged Staff, Siphoning Strike, Killing Palm, Culmination II, Ailith's
Chimes, Hit and Run, Perpetual Charge, six stat descriptions, two engine
locations, eight passive nodes, and the class and ascendancy list of tree
0_5.

## Scope proposal (`scope-proposal.json`)

Written by `python scripts/p09_t01_1_flicker_suite.py`. Proposal only.

## Tests

| Command | Result |
|---|---|
| `python -m pytest tests/unit/test_p09_t01_1_flicker_suite.py tests/unit/test_p09_t01_scenarios.py tests/unit/test_p09_t01_protocol.py -q` | 58 passed |
| `python -m pytest tests/unit -q` | 1549 passed, 1 xfailed |
| `python scripts/generate_schemas.py --check` | 20 schema files match |

No engine test was run: this task adds no engine code and no engine test.
