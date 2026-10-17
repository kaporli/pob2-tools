"""Regenerate the P02-T02 evidence artifacts.

Writes two files under `docs/evidence/P02/`:

* `catalog-export.json` - what one real export produced: entity counts, the
  catalog hash, the compatibility report, the gap list, a summary of the
  rules and the resolution of two sample builds. PoB-derived; nothing in it
  is a gameplay measurement.
* `catalog-rows-slice.json` - a bounded slice of the engine rows, so the
  offline lane can run the same export code with no PoB and no network. Also
  PoB-derived, and explicitly not the whole catalog.

Without `POB2_ROOT` the summary records `unavailable` and the slice is left
alone, the way `scripts/p02_t01_evidence.py` does.

Usage:
    python scripts/p02_t02_evidence.py [--summary PATH]

``--summary`` writes the export summary somewhere other than
`docs/evidence/P02/catalog-export.json`, so a later task can record its own
export without rewriting the historical one. The slice is always rewritten.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
for _pkg in ("pob2-optimizer", "pob2-mcp"):
    sys.path.insert(0, str(REPO_ROOT / _pkg))

EVIDENCE = REPO_ROOT / "docs" / "evidence" / "P02"
REQUEST = EVIDENCE / "catalog-profile-request.json"
RELEASE_DIR = EVIDENCE / "release"
SUMMARY = EVIDENCE / "catalog-export.json"
SLICE = EVIDENCE / "catalog-rows-slice.json"
SAMPLE_BUILDS = (
    REPO_ROOT / "tests" / "fixtures" / "builds" / "zero_dps_huntress.xml",
    EVIDENCE / "sample-build-ranger-quarterstaff.xml",
)

#: Rows kept per large table in the slice, after the ones the fixture set and
#: the sample builds need. Enough to exercise the export, far short of the
#: catalog, and small enough to commit.
SLICE_EXTRA_ROWS = 40


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Regenerate the P02-T02 evidence.")
    parser.add_argument("--summary", type=Path, default=SUMMARY)
    summary_path = parser.parse_args(argv).summary
    pob_root = os.environ.get("POB2_ROOT")
    if not pob_root or not Path(pob_root).is_dir():
        summary_path.write_text(json.dumps(
            {"kind": "PoB-derived", "status": "unavailable",
             "reason": "POB2_ROOT is not set to a PoB checkout, so no catalog "
                       "was exported and nothing here was measured",
             "written_at": _now()}, indent=1) + "\n", encoding="utf-8")
        print("no POB2_ROOT; recorded 'unavailable' in %s" % summary_path,
              file=sys.stderr)
        return 0

    from pob2opt.catalog import (EngineCatalogReader, ExportRequest,
                                 PobCatalogProvider, evaluation_context_hash,
                                 load_release_capture, resolve_build_document)
    from pob2opt.catalog.export import EXPORTER_VERSION
    from pob2opt.catalog.sources import citations_to_payload, read_citations
    from pob2opt.evaluation import (BuildDocument, EngineAdapter, EngineState,
                                    pob_worker_spec, protocol, resolve_checkout)

    request = ExportRequest.from_file(REQUEST)
    captures = [load_release_capture(path)
                for path in sorted(RELEASE_DIR.glob("*.json"))]
    checkout = resolve_checkout(pob_root)
    citations = read_citations(pob_root)

    before = os.getcwd()
    adapter = EngineAdapter(pob_worker_spec(pob_root), checkout=checkout,
                            start_timeout_s=600.0, screen_timeout_s=300.0,
                            detailed_timeout_s=300.0)
    try:
        reader = EngineCatalogReader(adapter, timeout_s=300.0)

        def behaviour(fixture):
            document = BuildDocument(
                build_hash="compat/%s" % fixture["fixture_id"],
                xml=fixture["document"])
            state = EngineState(
                stat_keys=tuple(sorted(fixture.get("expected") or {})))
            return adapter.probe(document, state, timeout_s=300.0)

        provider = PobCatalogProvider(
            reader, citations=citations, release_captures=captures,
            pob_commit=checkout.commit, pob_dirty_hash=checkout.dirty_hash,
            behaviour=behaviour)
        export = provider.export(request)
        rows = {table: reader.rows(table) for table in protocol.CATALOG_HANDLERS}
        rule_sources = reader.rule_sources()
    finally:
        adapter.close()
        os.chdir(before)

    for path in SAMPLE_BUILDS:
        export.resolutions[path.name] = resolve_build_document(
            path.read_text(encoding="utf-8"), export.catalog.entities).to_dict()

    _write_slice(rows, rule_sources, citations_to_payload(citations), checkout,
                 export)
    _write_summary(summary_path, export, checkout,
                   evaluation_context_hash(export.profile), EXPORTER_VERSION)
    print("wrote %s and %s" % (summary_path, SLICE), file=sys.stderr)
    return 0


def _keep_ids(export) -> set[str]:
    """Entity ids the fixture set and the sample builds depend on."""
    from pob2opt.catalog import compatibility_fixtures, resolve_build_document

    wanted: set[str] = set()
    for fixture in compatibility_fixtures().get("fixtures") or ():
        if fixture.get("entity_id"):
            wanted.add(fixture["entity_id"])
    for path in SAMPLE_BUILDS:
        resolution = resolve_build_document(path.read_text(encoding="utf-8"),
                                            export.catalog.entities)
        wanted.update(resolution.resolved.values())
    return wanted


def _write_slice(rows, rule_sources, citations, checkout, export) -> None:
    from pob2opt.catalog.entities import entities_from_rows

    wanted = _keep_ids(export)
    kept: dict[str, list] = {}
    for table, table_rows in rows.items():
        # Small tables are kept whole. Large ones keep the rows the fixtures
        # and the sample builds need, found by building each row's entity on
        # its own, plus a few more so the table is not degenerate.
        if len(table_rows) <= 200:
            kept[table] = table_rows
            continue
        needed, extra = [], []
        for row in table_rows:
            built = entities_from_rows(table, [row])
            if built and built[0].entity_id in wanted:
                needed.append(row)
            elif len(extra) < SLICE_EXTRA_ROWS:
                extra.append(row)
        kept[table] = needed + extra
    payload = {
        "capture_version": 1,
        "kind": "PoB-derived",
        "redistribution": "restricted",
        "not_a_claim": (
            "A bounded slice of the pinned engine's catalog rows, kept so the "
            "offline tests can run the real export with no PoB. It is not the "
            "catalog: large tables hold only the rows the compatibility "
            "fixtures and the sample builds need, plus a few more. A catalog "
            "hash computed from this slice is not the catalog hash of a real "
            "export. The rows are third-party game data read out of Path of "
            "Building: reviewable locally, not for republication."),
        "recorded_from": {"pob_commit": checkout.commit,
                          "pob_dirty_hash": checkout.dirty_hash},
        "pob_commit": checkout.commit,
        "pob_dirty_hash": checkout.dirty_hash,
        "adapter_version": export.profile.adapter_version,
        "citations": citations,
        "rule_sources": rule_sources,
        "tables": kept,
    }
    SLICE.write_text(json.dumps(payload, indent=1, sort_keys=True,
                                ensure_ascii=False) + "\n", encoding="utf-8")


def _write_summary(path, export, checkout, context_hash,
                   exporter_version) -> None:
    rules = export.profile.character_rules
    summary = export.summary()
    summary.update({
        "kind": "PoB-derived",
        "not_a_claim": (
            "Read out of the pinned Path of Building checkout. Nothing here "
            "is a gameplay measurement, and a matching catalog is not "
            "evidence that the engine models the live game patch."),
        "written_at": _now(),
        "pob_commit": checkout.commit,
        "pob_dirty_hash": checkout.dirty_hash,
        "evaluation_context_hash": context_hash,
        "exporter_version": exporter_version,
        "character_rules": {
            "level_range": [rules.level_range.minimum, rules.level_range.maximum],
            "class_ascendancies": {k: list(v) for k, v
                                   in rules.class_ascendancies.items()},
            "gem_level_limit": rules.gem_level_limit,
            "skill_level_limit": rules.skill_level_limit,
            "point_budget_count": len(rules.point_budgets),
            "point_budget_rule_ids_sample": [
                b.rule_id for b in rules.point_budgets[:3]] + [
                b.rule_id for b in rules.point_budgets[-3:]],
            "slot_count": len(rules.slots),
            "support_restrictions": [
                {"restriction_id": r.restriction_id,
                 "max_supports": r.max_supports,
                 "description": r.description}
                for r in rules.support_restrictions],
            "weapon_sets": {"set_ids": list(rules.weapon_sets.set_ids),
                            "hands_per_set": dict(rules.weapon_sets.hands_per_set),
                            "swap_allowed": rules.weapon_sets.swap_allowed},
            "missing_rule_gap_ids": list(rules.missing_rule_gap_ids),
        },
        "gaps": [{"gap_id": gap.gap_id, "kind": gap.kind.value,
                  "severity": gap.severity.value,
                  "explanation": gap.explanation,
                  "needed_evidence": gap.needed_evidence,
                  "collection_method": gap.collection_method}
                 for gap in export.gaps],
    })
    path.write_text(json.dumps(summary, indent=1, sort_keys=True,
                               ensure_ascii=False) + "\n", encoding="utf-8")


if __name__ == "__main__":
    import multiprocessing as mp

    mp.freeze_support()
    sys.exit(main())
