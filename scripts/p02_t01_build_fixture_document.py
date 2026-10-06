"""Save a populated PoB build document to a file (not a test).

Exists so the engine test suite never hosts a second ``Pob2Engine`` in the
pytest process. Two native engines in one process share state through PoB's
runtime, and closing one has been observed to leave the session engine
unusable for every test that follows. Building the fixture document out of
process removes that interaction and keeps the pytest process's working
directory where it started, which is what the coordinator-cwd assertions in
``tests/engine/test_p02_t01_engine_adapter.py`` depend on.

Usage:
    POB2_ROOT=... python scripts/p02_t01_build_fixture_document.py OUT.xml

The build is a Ranger with two projectile-damage nodes and the synthetic
fixture weapon equipped: a tree, an item and a socket group, which is what an
import has to carry. It is PoB-derived, not a gameplay measurement.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
for path in (REPO / "pob2-mcp", REPO / "tests"):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from engine_helpers import FIXTURE_WEAPON  # noqa: E402


def resolve_pob_root() -> Path:
    env = os.environ.get("POB2_ROOT")
    candidates = [Path(env)] if env else []
    candidates.append(REPO / "external" / "PathOfBuilding-PoE2")
    for candidate in candidates:
        if (candidate / "runtime" / "lua51.dll").is_file():
            return candidate.resolve()
    raise SystemExit("no usable PathOfBuilding-PoE2 runtime; set POB2_ROOT")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("out", type=Path)
    args = parser.parse_args(argv)

    from pob2mcp.engine import Pob2Engine

    engine = Pob2Engine(str(resolve_pob_root()))
    try:
        engine.call("new_build")
        nodes = engine.call("search_nodes", {"text": "projectile damage",
                                             "limit": 5})
        engine.call("alloc_nodes", {"ids": [n["id"] for n in nodes[:2]]})
        engine.call("equip_item", {"raw": FIXTURE_WEAPON, "slot": "Weapon 1"})
        xml = engine.call("save_build_xml")["xml"]
    finally:
        engine.close()

    # Resolved before the engine moved this process's directory.
    args.out.write_text(xml, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
