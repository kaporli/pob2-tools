# pob2-tools

Tooling that drives the **Path of Building 2** calculation engine headlessly to
analyze and optimize Path of Exile 2 builds — with special focus on **minion /
companion (summoner) DPS**, which the PoB UI does not surface in aggregate.

It is a **calculation & automation layer on top of PoB**. It does **not** fork
or modify PoB — both packages here are external clients that load PoB's own
patched LuaJIT (`runtime/lua51.dll`) through `ctypes` and call into its Lua.

```
┌─ pob2-optimizer  — exhaustive build-space search / optimization
│    domain/  — validated records, canonical hashing, cache identity (P01)
│    storage/ — SQLite repositories, immutable blobs, run bundles, task state
│    schemas/v1/ — the JSON Schemas, generated from domain/records.py
│    cli.py · engine_worker.py (one engine per worker process) · concentration.py
│    policy.py · calibration.py · ladder.py · harvest.py · lua/opt_helpers.lua
│    └── imports ▼
├─ pob2-mcp        — the engine bridge + interfaces
│    engine.py   → ctypes; loads PoB's runtime/lua51.dll, runs its Lua headless
│    bootstrap.lua · server.py (MCP server) · trade.py (PoE2 trade API) · poe_api.py (GGG OAuth)
│    └── drives, via POB2_ROOT ▼
└─ external/PathOfBuilding-PoE2   — THIRD-PARTY, unmodified (git submodule)
     the actual damage/defense engine + patched LuaJIT
     © 2016 David Gowor, Path of Building Community license
```

## Packages

Work tracking and historical deliveries are in the [GitHub delivery index](https://github.com/kaporli/pob2-tools/issues/23). Technical requirements remain in [the specifications](docs/specs/README.md).
It includes project tasks, shared contracts, acceptance gates, and an engineering review process.

| Package | What it is | Entry point |
|---|---|---|
| [`pob2-mcp`](pob2-mcp/) | ctypes bridge to PoB's headless engine, exposed as an MCP server; also a PoE2 trade client and GGG OAuth helper. | `pob2-mcp` |
| [`pob2-optimizer`](pob2-optimizer/) | Search layer on top of the bridge: enumerates skills/supports/companions, scores single-target vs clear ("concentration" model), and ranks upgrades. | `pob2opt` |

## Setup

Requires **Python 3.10+** and a **Windows** environment (PoB's `lua51.dll` is a
Windows build; the ctypes bridge uses `os.add_dll_directory`).

```bash
# clone with the PoB submodule
git clone --recurse-submodules <this-repo-url>
cd pob2-tools
# or, if already cloned:  git submodule update --init

# install both packages (editable)
pip install -e ./pob2-mcp
pip install -e ./pob2-optimizer
```

**Pointing at PoB.** By default the tools use the `external/PathOfBuilding-PoE2`
submodule. To use a different checkout, set:

```bash
export POB2_ROOT="/path/to/PathOfBuilding-PoE2"   # must contain runtime/lua51.dll and src/
```

## Usage

```bash
# run the optimizer over a build
pob2opt all --level 90 --out runs/mybuild --build "C:/…/Builds/My Build.xml"

# run the MCP server (for use from an MCP client)
pob2-mcp
```

The trade client works anonymously for simple searches; weighted-sum ("weight2")
searches are gated by GGG and need a session cookie:

```bash
export POESESSID="…"     # from your pathofexile.com session
```

## Development

```bash
LOCK=requirements/lock-py312-win_amd64.txt   # or lock-py310-win_amd64.txt
python -m venv .venv
source .venv/Scripts/activate                 # Git Bash on Windows
python -m pip install --upgrade pip setuptools wheel  # unpinned bootstrap tools
python -m pip install --no-deps -r "$LOCK"
python -m pip install --no-deps --no-build-isolation -e ./pob2-mcp -e ./pob2-optimizer
python scripts/lock_dependencies.py --check

python -m pob2opt.cli doctor --json          # what can this machine do?
python scripts/generate_schemas.py --check   # schemas/v1 matches domain/records.py
python -m pytest tests/unit                  # offline; no PoB, no network
python -m pytest -m engine -ra               # needs a PoB checkout, else skips
```

`doctor` exits `0` when every blocking check passes and `3` when a missing
dependency blocks something; `summary.blocked_capabilities` says which. Test
groups, markers, prerequisites and recorded results are in
[`tests/MANIFEST.md`](tests/MANIFEST.md).

Engine tests skip with a reason when no PoB runtime is configured. **A skip is
not a pass** — no gate that needs real engine behaviour may be accepted from a
run where they skipped.

## Notes

- No secrets are stored in-tree. GGG OAuth tokens (if you use `poe_api.py`) cache
  to `~/.pob2-mcp/token.json`, outside this repo.
- PoB is pinned as a submodule at a specific commit; bump it with
  `git submodule update --remote external/PathOfBuilding-PoE2`.
