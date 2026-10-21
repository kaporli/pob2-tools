"""Ask the pinned PoB engine which seed modifier lines it parses (P06-T02).

Loads the P09-T01.1 seed export exactly as stored and records, per equipped
item modifier line and per allocated passive line, whether PoB's parser
produced a modifier list and whether text was left over. PoB marks
unparsed text as ``extra`` (Classes/Item.lua, Classes/PassiveTree.lua).
A parsed line is not proof of a correct implementation; an unparsed line is
proof that PoB does not calculate it.

The capture is bound to the document hash, the selected sets, the clean
engine identity, each equipped item's id and text hash, the allocated nodes
and the selected config inputs. It refuses to write when the engine's loaded
state differs from the document's.

Also records every config variable holding an input or placeholder value and
whether PoB's own config tab shows it for this build (``control.shown``).
PoB applies count-type placeholders when no input is set
(ConfigTab:BuildModList), so placeholders are assumptions too.

Refuses a dirty or unpinned checkout. Needs the engine; run it alone:

    POB2_ROOT=external/PathOfBuilding-PoE2 python scripts/p06_seed_engine_mod_support.py
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SEED = REPO / "docs/evidence/P09-T01.1/seed/export-flicker-main.xml"
OUT = REPO / "docs/evidence/P06/seed-engine-mod-support.json"
PIN = "ce566eac45ea8a86477f513c7ee65a1ebe60014e"

def _git(root: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(root), *args], check=True,
                          capture_output=True, text=True).stdout.strip()


def main() -> int:
    root = Path(os.environ.get("POB2_ROOT") or REPO / "external/PathOfBuilding-PoE2").resolve()
    head = _git(root, "rev-parse", "HEAD")
    dirty = _git(root, "status", "--porcelain")
    if head != PIN or dirty:
        print("refused: checkout %s at %s, dirty=%s" % (root, head, bool(dirty)))
        return 2
    sys.path.insert(0, str(REPO / "pob2-mcp"))
    from pob2mcp.engine import Pob2Engine

    xml = SEED.read_bytes()
    sys.path.insert(0, str(REPO / "pob2-optimizer"))
    from pob2opt.coverage.capture import PARSE_SUPPORT_LUA, CaptureRefused, bind_capture
    with Pob2Engine(str(root)) as engine:
        engine.call("load_build_xml", {"xml": xml.decode("utf-8"), "name": "seed"})
        result = engine.eval_lua(PARSE_SUPPORT_LUA)
    # Bind the verdicts to what the engine actually held, and refuse when that
    # differs from the document's own selection, items, nodes or inputs.
    try:
        bound = bind_capture(xml, result, pob_commit=head, pob_dirty=False)
    except CaptureRefused as exc:
        print("refused: " + str(exc))
        return 2
    result = bound
    payload = {
        "task": "P06-T02",
        "kind": "engine_parse_support",
        "not_a_claim": ("Parsed means PoB produced a modifier list; it does not "
                        "mean the modifier is implemented correctly."),
        "seed_xml": str(SEED.relative_to(REPO)).replace("\\", "/"),
        "seed_sha256": hashlib.sha256(xml).hexdigest(),
        "generated_by": "scripts/p06_seed_engine_mod_support.py",
        **result,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    unparsed = sum(1 for e in result["items"] for r in e["lines"] if not r["parsed"] or r.get("extra"))
    print("items %d, nodes %d, unparsed item lines %d" % (
        len(result["items"]), len(result["nodes"]), unparsed))
    return 0


if __name__ == "__main__":
    sys.exit(main())
