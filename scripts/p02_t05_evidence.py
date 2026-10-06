"""Record what the P02-T05 round trips actually did (not a test).

Writes three artifacts under `docs/evidence/P02/`:

``roundtrips.json``             both lanes, with every reported loss.
``roundtrip-synthetic.xml``     the synthetic supported fixture's export.
                                SYNTHETIC: its class, skills and bases are
                                invented, so the pinned PoB will load it as a
                                document and find none of those entities. It
                                is here to be read, not to be loaded.
``roundtrip-pob-export.xml``    our export of a build PoB itself wrote. This
                                is the one a reviewer loads in the pinned PoB.

The ``synthetic`` section compares our exporter against our importer and needs
no PoB. The ``pob`` section starts from a document PoB wrote, exports it,
loads ours back in the engine and compares the canonical identity and the
deterministic primitives. Nothing in either section is a gameplay measurement.

Usage:
    python scripts/p02_t05_evidence.py [--out-dir DIR]
    POB2_ROOT must be set (or the submodule present) for the ``pob`` section.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
for path in (REPO / "pob2-optimizer", REPO / "pob2-mcp", REPO / "tests"):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

import p02_t05_fixtures as fixtures  # noqa: E402
from pob2opt.domain.identity import build_identity  # noqa: E402
from pob2opt.evaluation import (export_build, export_item, import_build,  # noqa: E402
                                round_trip)
from pob2opt.evaluation.builddoc import SUPPORT as BUILD_SUPPORT  # noqa: E402
from pob2opt.evaluation.itemtext import SUPPORT as ITEM_SUPPORT  # noqa: E402
from pob2opt.evaluation.roundtrip import diff_identity  # noqa: E402

DEFAULT_OUT_DIR = REPO / "docs" / "evidence" / "P02"
REL_TOLERANCE = 1e-6
ABS_TOLERANCE = 1e-9
CREATED_AT = "2026-10-06T00:00:00Z"
CATALOG_HASH = "e" * 64

BUILD_CASES = {
    "supported": fixtures.supported_build,
    "trigger_nested": fixtures.trigger_nested_build,
    "progression": fixtures.progression_build,
    "item_granted_group": fixtures.item_granted_group_build,
    "unresolved_catalog": fixtures.unresolved_catalog_build,
}
ITEM_CASES = {
    "every_category_weapon": fixtures.every_category_weapon,
    "variant_helmet": fixtures.variant_helmet,
    "socketed_jewel": fixtures.socketed_jewel,
    "unknown_category": fixtures.unknown_category_item,
    "resolved_modifier": fixtures.resolved_modifier_item,
    "false_flag": fixtures.false_flag_item,
}

FIXTURE_WEAPON = "\n".join([
    "Rarity: RARE",
    "FIXTURE P02-T05 Quarterstaff",
    "Long Quarterstaff",
    "Item Level: 80",
    "Quality: 20",
    "LevelReq: 60",
    "Implicits: 0",
    "Adds 60 to 90 Physical Damage",
    "{crafted}Adds 20 to 30 Fire Damage",
])


def synthetic_section(out_dir: Path) -> dict:
    builds = {}
    for name, factory in sorted(BUILD_CASES.items()):
        report = round_trip(*factory(), fixtures.SYNTHETIC_NAMING)
        payload = report.as_dict()
        payload["differences"] = payload["differences"][:20]
        builds[name] = payload
        if name == "supported":
            (out_dir / "roundtrip-synthetic.xml").write_text(
                report.document, encoding="utf-8")
    items = {}
    for name, factory in sorted(ITEM_CASES.items()):
        source = factory()
        text, losses = export_item(source, fixtures.SYNTHETIC_NAMING)
        report = losses.report()
        items[name] = {"text": text, **report.as_dict()}
    return {
        "what_this_is": "SYNTHETIC. Invented catalog IDs, PoB names, modifier "
                        "text and numbers, compared by our exporter against "
                        "our importer. No PoB, no network, no game value.",
        "declared_support": {"build": BUILD_SUPPORT, "item": ITEM_SUPPORT},
        "builds": builds,
        "items": items,
    }


def pob_section(out_dir: Path) -> dict:
    root = os.environ.get("POB2_ROOT")
    candidates = [Path(root)] if root else []
    candidates.append(REPO / "external" / "PathOfBuilding-PoE2")
    checkout = next((c for c in candidates
                     if (c / "runtime" / "lua51.dll").is_file()), None)
    if checkout is None:
        return {"status": "unavailable",
                "reason": "no PoB checkout: set POB2_ROOT or restore the "
                          "external/PathOfBuilding-PoE2 submodule"}

    from pob2mcp.engine import Pob2Engine

    before_cwd = os.getcwd()
    engine = Pob2Engine(str(checkout.resolve()))
    try:
        engine.call("new_build")
        nodes = engine.call("search_nodes", {"text": "projectile damage",
                                             "limit": 5})
        engine.call("alloc_nodes", {"ids": [n["id"] for n in nodes[:2]]})
        engine.call("equip_item", {"raw": FIXTURE_WEAPON, "slot": "Weapon 1"})
        pob_xml = engine.call("save_build_xml")["xml"]

        naming = fixtures.naming_from_document(pob_xml)
        first = import_build(pob_xml, naming, record_id="p02t05-a",
                             created_at=CREATED_AT, catalog_hash=CATALOG_HASH)
        export = export_build(first.build, first.items, naming)
        (out_dir / "roundtrip-pob-export.xml").write_text(export.xml,
                                                          encoding="utf-8")

        original_summary = engine.call("load_build_xml", {"xml": pob_xml})
        original_stats = engine.call("get_stats", {"all": True})
        our_summary = engine.call("load_build_xml", {"xml": export.xml})
        our_stats = engine.call("get_stats", {"all": True})
        resaved = engine.call("save_build_xml")["xml"]
        second = import_build(resaved, naming, record_id="p02t05-b",
                              created_at=CREATED_AT,
                              catalog_hash=CATALOG_HASH)
        differences = diff_identity(build_identity(first.build),
                                    build_identity(second.build))
        return {
            "status": "recorded",
            "what_this_is": "PoB-derived. A build PoB saved, exported by "
                            "pob2opt, loaded back into the pinned engine and "
                            "compared on canonical identity. Not a gameplay "
                            "measurement.",
            "pob_root": str(checkout.resolve()),
            "exported_document": "roundtrip-pob-export.xml",
            "export": export.report.as_dict(),
            "summary_before": original_summary,
            "summary_after": our_summary,
            "summary_matches": original_summary == our_summary,
            "primitives": compare(original_stats, our_stats),
            "identity": {
                "build_hash_before": first.build.build_hash,
                "build_hash_after": second.build.build_hash,
                "differences": [d.as_dict() for d in differences][:20],
                "identical": not differences,
            },
            "xml_bytes_identical": export.xml == resaved,
            "xml_byte_note": "PoB assigns its own internal numeric item and "
                             "node IDs, so byte equality is not the test.",
        }
    finally:
        engine.close()
        os.chdir(before_cwd)


def compare(before: dict, after: dict) -> dict:
    compared = 0
    worst_abs = 0.0
    worst_rel = 0.0
    missing = []
    for key, value in sorted(before.items()):
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            continue
        if key not in after:
            missing.append(key)
            continue
        other = after[key]
        if not isinstance(other, (int, float)):
            missing.append(key)
            continue
        delta = abs(float(other) - float(value))
        worst_abs = max(worst_abs, delta)
        if value:
            worst_rel = max(worst_rel, delta / abs(float(value)))
        compared += 1
    return {"keys_compared": compared, "keys_missing_after": missing[:10],
            "worst_absolute_delta": worst_abs,
            "worst_relative_delta": worst_rel,
            "tolerance": {"relative": REL_TOLERANCE,
                          "absolute": ABS_TOLERANCE},
            "within_tolerance": (worst_abs <= ABS_TOLERANCE
                                 or worst_rel <= REL_TOLERANCE)}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    args = parser.parse_args(argv)
    out_dir: Path = args.out_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    payload = {
        "task": "P02-T05",
        "spec_version": "1.0",
        "generated_at": dt.datetime.now(dt.timezone.utc).strftime(
            "%Y-%m-%dT%H:%M:%SZ"),
        "comparison": "canonical identity from pob2opt.domain.identity, not "
                      "XML bytes: the editor assigns new internal numeric IDs",
        "synthetic": synthetic_section(out_dir),
        "pob": pob_section(out_dir),
    }
    target = out_dir / "roundtrips.json"
    target.write_text(json.dumps(payload, indent=1, sort_keys=False) + "\n",
                      encoding="utf-8")
    print(target)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
