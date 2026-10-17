"""R2: enforce objective binding at real persistence and bundle boundaries."""
from dataclasses import replace

import pytest

from objective_fixtures import v2_aggregate, v2_manifest
from record_fixtures import seed_corpus
from pob2opt.domain import RECORD_TYPES, from_jsonable
from pob2opt.domain.validation import RecordInvalid
from pob2opt.domain.objectives import OBJECTIVES, FLICKER_SUSTAINED_DPS_V1
from pob2opt.storage import RunBundle, RunStore
from pob2opt.storage.errors import IncompleteBundle


def manifest():
    data = v2_manifest()
    data.update(record_id="binding-run", run_id="binding-run")
    return from_jsonable(RECORD_TYPES["run_manifest"], data)


def aggregate(defect=None):
    data = v2_aggregate(record_id="binding-aggregate", aggregate_id="binding-aggregate",
                        manifest_id="binding-run")
    if defect == "hash":
        data["objective_hash"] = "d" * 64
    elif defect == "objective":
        data.update(objective_id="balanced_score", objective_metrics={},
                    objective_score=None, objective_gap_ids=["fixture-gap-1"])
    elif defect == "version":
        data["objective_version"] = 2
    elif defect == "legacy":
        data["schema_version"] = 1
        for key in ("objective_version", "objective_hash", "objective_metrics",
                    "objective_score", "objective_gap_ids"):
            del data[key]
    return from_jsonable(RECORD_TYPES["aggregate_result"], data)


@pytest.mark.parametrize("defect", ["hash", "objective", "version", "legacy"])
@pytest.mark.parametrize("route", ["single", "batch_manifest_first", "batch_aggregate_first"])
def test_conflicts_are_rejected_atomically_with_reference_checks(tmp_path, defect, route,
                                                                monkeypatch):
    # A known alternative version passes record validation but must still
    # fail binding to this run's v1 selection.
    monkeypatch.setitem(OBJECTIVES, ("flicker_sustained_dps", 2),
                        replace(FLICKER_SUSTAINED_DPS_V1, version=2))
    with RunStore.open(tmp_path) as store:
        seed_corpus(store)
        man, agg = manifest(), aggregate(defect)
        if route == "single":
            store.put_run(man)
        with pytest.raises(RecordInvalid):
            if route == "single":
                store.put_normalized(agg)
            else:
                batch = [man, agg] if route == "batch_manifest_first" else [agg, man]
                store.import_batch(batch)
        assert not store.has_record(agg.record_id)
        if route != "single":
            assert not store.has_record(man.run_id)


@pytest.mark.parametrize("route", ["single", "batch_manifest_first", "batch_aggregate_first"])
def test_matching_aggregate_and_legacy_corpus_remain_valid(tmp_path, route):
    with RunStore.open(tmp_path) as store:
        seed_corpus(store)  # Includes a valid v1 aggregate and v1 run.
        man, agg = manifest(), aggregate()
        if route == "single":
            store.put_run(man)
            store.put_normalized(agg)
        else:
            store.import_batch([man, agg] if route == "batch_manifest_first" else [agg, man])
        assert all(r.ok for r in store.validate_stored().values())


@pytest.mark.parametrize("defect,code", [("hash", "objective_hash_mismatch"),
                                        ("objective", "objective_mismatch"),
                                        ("legacy", "unbound_objective")])
def test_staged_conflicts_are_visible_and_make_bundle_unreadable(tmp_path, defect, code):
    with RunBundle.create(tmp_path, manifest()) as bundle:
        seed_corpus(bundle.store)
        agg = aggregate(defect)
        bundle.store.put_normalized(agg, require_references=False)
        report = bundle.store.validate_stored()[agg.record_id]
        assert code in report.codes()
        check = bundle.self_check()
        assert not check["readable"]
        assert agg.record_id in check["validation_errors"]
        assert any(code in error for error in check["validation_errors"][agg.record_id])
        with pytest.raises(IncompleteBundle, match=code):
            bundle.require_readable()


def test_valid_binding_makes_bundle_readable(tmp_path):
    with RunBundle.create(tmp_path, manifest()) as bundle:
        seed_corpus(bundle.store)
        bundle.store.put_normalized(aggregate())
        assert bundle.self_check()["readable"]


def test_v2_aggregate_cannot_be_assigned_to_legacy_run(tmp_path):
    with RunStore.open(tmp_path) as store:
        old = seed_corpus(store)
        agg = replace(aggregate(), manifest_id=old["run_manifest"].run_id)
        with pytest.raises(RecordInvalid) as exc:
            store.put_normalized(agg)
        assert "objective_not_in_run" in exc.value.report.codes()
