"""Write docs/evidence/P04/parse-and-audit.json from the committed fixtures.

Offline: no PoB, no network. Usage from the repository root:

    python scripts/p04_evidence.py

Records, for every P04 fixture document, the parse status, issues, field
coverage and variants, and the field audit of every variant against its
source. The documents are synthetic compositions saved by PoB; this is
evidence about the parser, not about the game.
"""

from __future__ import annotations

import copy
import json
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(REPO / "tests"), str(REPO / "pob2-optimizer")]

import p04_fixtures as fx  # noqa: E402
from pob2opt.parsers import (audit_summary, audit_variant,  # noqa: E402
                             naming_from_catalog, parse_document)
from pob2opt.parsers.resolve import class_for_document_name  # noqa: E402


def cases():
    for name in fx.COMPLETE_BUILDS + fx.PARTIAL_BUILDS + ("variants",):
        yield name, fx.document_bytes(name)
    root = ET.fromstring(fx.document_bytes("variants"))
    items = root.find("Items")
    twin = copy.deepcopy(items.find("ItemSet[@id='2']"))
    twin.set("id", "4")
    items.append(twin)
    yield "variants-ambiguous", ET.tostring(root, encoding="utf-8",
                                            xml_declaration=True)
    for name, section in (("b04", "Items"), ("b05", "Tree"),
                          ("b08", "Skills")):
        root = ET.fromstring(fx.document_bytes(name))
        root.remove(root.find(section))
        yield "%s-without-%s" % (name, section.lower()), ET.tostring(
            root, encoding="utf-8", xml_declaration=True)


def main() -> int:
    records, audits = [], {"complete": [], "partial": []}
    for name, data in cases():
        outcome = parse_document(fx.source(data, record_id="src/" + name),
                                 data, fx.context())
        root = ET.fromstring(data)
        class_id = class_for_document_name(
            fx.entities(), root.find("Build").get("className"))
        naming = naming_from_catalog(fx.entities(), class_id=class_id).naming
        items = {i.item_hash: i for i in outcome.items}
        variants = []
        for variant in outcome.split.variants:
            build = next((b for b in outcome.builds
                          if b.variant_id == variant.variant_id), None)
            entry = {"label": variant.label, "variant_id": variant.variant_id,
                     "selection": dict(variant.selection)}
            if build is not None:
                result = audit_variant(data.decode("utf-8"),
                                       variant.selection, build, items, naming)
                entry.update(parse_status=build.parse_status.value,
                             build_hash=build.build_hash,
                             audit=result.as_dict())
                bucket = ("complete" if name in fx.COMPLETE_BUILDS
                          else "partial")
                audits[bucket].append(result)
            variants.append(entry)
        records.append({
            "case": name,
            "status": outcome.result.status.value,
            "issues": [{"code": i.code, "field_path": i.field_path,
                        "explanation": i.explanation}
                       for i in outcome.result.issues],
            "field_coverage": [{"domain": c.domain, "present": c.present,
                                "resolved": c.resolved, "missing": c.missing}
                               for c in outcome.result.field_coverage],
            "variants": variants,
        })
    payload = {
        "kind": "PoB-derived",
        "not_a_claim": ("Parser and audit behaviour on synthetic compositions "
                        "saved by the pinned PoB. Says nothing about the "
                        "game."),
        "pob_commit": fx.slice_data()["pob_commit"],
        "catalog_slice_hash": fx.slice_catalog_hash(),
        "audit": {"ten_complete_variants": audit_summary(audits["complete"]),
                  "partial_and_ambiguous": audit_summary(audits["partial"])},
        "cases": records,
    }
    out = REPO / "docs" / "evidence" / "P04" / "parse-and-audit.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=1, sort_keys=True) + "\n",
                   encoding="utf-8")
    print(json.dumps(payload["audit"]["ten_complete_variants"]["agreement"],
                     indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
