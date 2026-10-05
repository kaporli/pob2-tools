"""Independent follow-up probes; writes only to temporary databases.

Run: python docs/evidence/P01/review-5068871-probes.py
"""
from __future__ import annotations

import json
import sys
import tempfile
from dataclasses import replace
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
sys.path[:0] = [str(REPO / "pob2-optimizer"), str(REPO / "tests")]

import record_fixtures as fixtures
from pob2opt.domain import validate_record
from pob2opt.storage import RunBundle, RunStore


def probe():
    results = {}
    with tempfile.TemporaryDirectory(prefix="p01-followup-") as temporary:
        root = Path(temporary)
        with RunStore.open(root / "corpus") as corpus:
            records = fixtures.seed_corpus(corpus)
            results["source_corpus_valid"] = all(
                report.ok for report in corpus.validate_stored().values())
            with RunBundle.create(root / "aggregate", records["run_manifest"]) as bundle:
                try:
                    report = bundle.copy_references(
                        corpus, normalized_ids=[records["aggregate_result"].record_id])
                    results["copy_aggregate"] = {"complete": report.complete}
                except Exception as exc:
                    results["copy_aggregate"] = {
                        "error": type(exc).__name__, "message": str(exc)}

        # Batch order is not a semantic dependency: listings may precede items.
        original_order = fixtures.CORE_BATCH
        fixtures.CORE_BATCH = ("listing",) + tuple(
            kind for kind in original_order if kind != "listing")
        try:
            with RunStore.open(root / "listing-first") as corpus:
                records = fixtures.seed_corpus(corpus, with_results=False)
                with RunBundle.create(root / "ordered-copy", records["run_manifest"]) as bundle:
                    report = bundle.copy_references(corpus, normalized_ids=[
                        records["build_spec"].record_id,
                        records["scenario_spec"].record_id])
                    check = bundle.self_check()
                    results["listing_before_item"] = {
                        "source_corpus_valid": all(
                            r.ok for r in corpus.validate_stored().values()),
                        "copy_complete": report.complete,
                        "item_copied": bundle.store.has_record(records["item_instance"].record_id),
                        "readable": check["readable"],
                        "unresolved": check["unresolved_references"],
                    }
        finally:
            fixtures.CORE_BATCH = original_order

        with RunBundle.create(root / "wrong-kind", records["run_manifest"]) as bundle:
            records = fixtures.seed_corpus(bundle.store, with_results=False)
            wrong = replace(records["build_spec"], record_id="wrong-source-kind",
                            source_document_ids=[records["acquisition_result"].record_id])
            memory = validate_record(wrong, index=bundle.store.record_index())
            sql = validate_record(wrong, index=bundle.store.reference_index())
            try:
                inserted = bundle.store.put_normalized(wrong)
            except Exception as exc:
                inserted = type(exc).__name__
            results["acquisition_as_source_document"] = {
                "memory_index_ok": memory.ok,
                "memory_errors": [e.field_path for e in memory.errors],
                "sql_index_ok": sql.ok,
                "inserted": inserted,
                "bundle_readable": bundle.self_check()["readable"],
            }
    return results


if __name__ == "__main__":
    print(json.dumps(probe(), indent=2))
