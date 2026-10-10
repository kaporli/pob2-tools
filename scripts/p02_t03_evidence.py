"""Regenerate the P02-T03 evidence artifact.

Writes `docs/evidence/P02/legality.json`: what the validator answered for
every fixture case, and what it answered for a build the pinned engine loaded
itself.

Two sections, labelled separately because they are different claims.

* `synthetic`: the invented world and the invented builds in
  `tests/fixtures/legality/`, validated against a profile the real P02-T02
  exporter produced from those invented rows. Synthetic throughout.
* `pob_derived`: one exact load of the committed PoB-saved sample build in
  the pinned engine, the state the engine reported back, and the verdict.
  PoB-derived. Without `POB2_ROOT` the section records `unavailable`, the
  way `scripts/p02_t01_evidence.py` and `scripts/p02_t02_evidence.py` do.

Nothing here is a gameplay measurement, and an `unknown` verdict is a
statement about this software's evidence, not about Path of Exile 2.

Usage:
    python scripts/p02_t03_evidence.py
"""

from __future__ import annotations

import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
for _pkg in ("pob2-optimizer", "pob2-mcp", "tests"):
    sys.path.insert(0, str(REPO_ROOT / _pkg))

import legality_fixtures as fixtures  # noqa: E402

from pob2opt.evaluation.legality import (DECLARED_CHECKS,  # noqa: E402
                                         LegalityValidator, TEMPLATES)

EVIDENCE = REPO_ROOT / "docs" / "evidence" / "P02"
OUT = EVIDENCE / "legality.json"
SAMPLE_BUILD = EVIDENCE / "sample-build-ranger-quarterstaff.xml"

START_TIMEOUT_S = 600.0
REQUEST_TIMEOUT_S = 300.0


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _case_rows() -> dict:
    world = fixtures.load_world()
    cases = fixtures.load_cases()
    items = fixtures.make_items(cases, world.catalog.catalog_hash)
    rows = []
    for case in cases["cases"]:
        spec = {**cases["base"], **case["build"]}
        build = fixtures.make_build(spec,
                                    catalog_hash=world.catalog.catalog_hash)
        validator = LegalityValidator(
            catalog=world.catalog, items=items,
            imported=fixtures.make_imported(case.get("imported"),
                                            build_hash=build.build_hash),
            measured=fixtures.make_measured(case.get("measured")),
            clock=lambda: "2026-10-06T00:00:00Z")
        report = validator.validate(build, world.profile)
        rows.append({
            "case": case["id"],
            "why": case["why"],
            "legality": report.legality.value,
            "violations": sorted(set(report.violation_codes)),
            "unknowns": sorted(set(report.unknown_codes)),
            "cited_gaps": list(report.cited_gap_ids),
        })
    return {
        "kind": "synthetic",
        "catalog_hash": world.catalog.catalog_hash,
        "patch_profile_id": world.profile.record_id,
        "world": "tests/fixtures/legality/p02_t03_world.json",
        "cases_file": "tests/fixtures/legality/p02_t03_cases.json",
        "case_count": len(rows),
        "cases": rows,
    }


def _pob_section() -> dict:
    pob_root = os.environ.get("POB2_ROOT")
    if not pob_root or not Path(pob_root).is_dir():
        return {"kind": "PoB-derived", "status": "unavailable",
                "reason": "POB2_ROOT is not set to a PoB checkout, so no "
                          "build was imported and nothing here was measured"}
    from pob2opt.catalog import (EngineCatalogReader, ExportRequest,
                                 PobCatalogProvider)
    from pob2opt.catalog.sources import read_citations
    from pob2opt.evaluation import (BuildDocument, EngineAdapter,
                                    pob_worker_spec, resolve_checkout)
    from pob2opt.evaluation.legality import read_imported_state

    xml = SAMPLE_BUILD.read_text(encoding="utf-8")
    nodes = [int(value) for value
             in re.search(r'nodes="([0-9,]*)"', xml).group(1).split(",") if value]
    checkout = resolve_checkout(pob_root)
    adapter = EngineAdapter(pob_worker_spec(pob_root),
                            screen_timeout_s=REQUEST_TIMEOUT_S,
                            detailed_timeout_s=REQUEST_TIMEOUT_S,
                            start_timeout_s=START_TIMEOUT_S)
    try:
        export = PobCatalogProvider(
            EngineCatalogReader(adapter, timeout_s=REQUEST_TIMEOUT_S),
            citations=read_citations(pob_root),
            pob_commit=checkout.commit, pob_dirty_hash=checkout.dirty_hash,
            fixtures=fixtures.NO_FIXTURES).export(ExportRequest())
        item = fixtures.make_item("sample-stave", {
            "catalog_hash": export.catalog.catalog_hash,
            "base_id": "Long Quarterstaff", "display_name": "Fixture Stave",
            "requirements": {}, "source_document_id": "source/sample-build"})
        build = fixtures.make_build(
            {"class_id": "poe2/classes/2", "level": 29, "allocated": nodes,
             "equipment": {"Weapon 1": {"item": item.item_hash}}},
            catalog_hash=export.catalog.catalog_hash,
            build_hash="p02t03/evidence-sample")
        state = read_imported_state(
            adapter, build, export.profile,
            document=BuildDocument(build_hash=build.build_hash, xml=xml),
            timeout_s=REQUEST_TIMEOUT_S)
        report = LegalityValidator(catalog=export.catalog,
                                   items={item.item_hash: item},
                                   imported=state).validate(build,
                                                            export.profile)
    finally:
        adapter.close()
    return {
        "kind": "PoB-derived",
        "status": "measured",
        "document": "docs/evidence/P02/sample-build-ranger-quarterstaff.xml",
        "pob_commit": checkout.commit,
        "pob_dirty_hash": checkout.dirty_hash,
        "catalog_hash": export.catalog.catalog_hash,
        "imported_state": state.to_dict(),
        "report": report.to_dict(),
    }


def main() -> int:
    payload = {
        "kind": "mixed",
        "not_a_claim": (
            "A record of what the legality validator answered. The synthetic "
            "section is invented input validated against a profile exported "
            "from invented rows. The PoB-derived section is one real import "
            "in the pinned checkout. Neither is a gameplay measurement, and "
            "an `unknown` verdict is a statement about this software's "
            "evidence rather than about Path of Exile 2."),
        "written_at": _now(),
        "declared_checks": list(DECLARED_CHECKS),
        "validator_gap_templates": sorted(TEMPLATES),
        "synthetic": _case_rows(),
        "pob_derived": _pob_section(),
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(payload, indent=1, sort_keys=True,
                                ensure_ascii=False) + "\n")
    print("wrote %s (%d cases, pob section %s)"
          % (OUT, payload["synthetic"]["case_count"],
             payload["pob_derived"]["status"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
