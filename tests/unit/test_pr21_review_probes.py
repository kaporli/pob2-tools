"""PR #21 review R4 to R7 (docs/reviews/PR-18-22.md) as regression tests.

Each case is the reviewer's independent probe from
docs/evidence/PR-18-22/review_probes.py, on the settled synthetic fixture of
test_p07_t01_flicker_cycle. Every case returned an eligible objective on the
reviewed head db40827.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path

import pytest
from pob2opt.combat import AttributionTable
from pob2opt.combat.attribution import FLICKER_HIT, WHIRLING_HIT
from pob2opt.combat.values import benchmark_document

_spec = importlib.util.spec_from_file_location(
    "p07_fixtures", Path(__file__).with_name("test_p07_t01_flicker_cycle.py"))
f = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(f)

OTHER_XML = f.SYNTH_XML % f.LIVING_LIGHTNING
PIN_HEAD = "ce566eac45ea8a86477f513c7ee65a1ebe60014e"


def identity(xml: str) -> dict:
    """Engine identity a clean pinned capture of ``xml``'s scoring document records."""
    return {"head": PIN_HEAD, "dirty_hash": None,
            "document_sha256": hashlib.sha256(benchmark_document(xml).encode("utf-8")).hexdigest()}


@pytest.fixture()
def bench(tmp_path):
    path = tmp_path / "scenarios.json"
    path.write_text(json.dumps({"data_gaps": [], "scenarios": [
        {"scenario_id": "flicker_sustained_v1", "category": "dps_benchmark", "fields": {}}]}),
        encoding="utf-8")
    return path


def blocked(result) -> bool:
    return (result.status != "eligible" and result.objective["score"] is None
            and all(v is None for v in result.objective["metrics"].values()))


# R4: the scored attribution table is the approved one ------------------------

def test_r4_unaccepted_table_on_a_settled_registry_is_refused(bench):
    table = AttributionTable.from_rows("unaccepted-different-table",
                                       [(FLICKER_HIT, "flicker_direct"),
                                        (WHIRLING_HIT, "flicker_secondary")])
    result = f.evaluate(bench, f.settled(), source=f.values(whirling_damage_per_use=1e12),
                        attribution=table)
    assert blocked(result)


def test_r4_acceptance_of_another_table_does_not_approve_this_one(bench):
    table = AttributionTable.from_rows("unaccepted-different-table",
                                       [(FLICKER_HIT, "flicker_direct"),
                                        (WHIRLING_HIT, "flicker_secondary")])
    unsettled = f.settled(**{"attribution/flicker-sustained-v1": lambda e: f.replace(
        e, reviewed_by=None, rule=f.replace(e.rule, support=f.RuleSupport.UNSUPPORTED))})
    result = f.evaluate(bench, unsettled, source=f.values(whirling_damage_per_use=1e12),
                        attribution=table,
                        attribution_acceptance={"reviewer": "r", "evidence_ids": ["x"],
                                                "table_id": "p09-t012-attribution-proposed",
                                                "table_hash": "sha256:" + "0" * 64})
    assert blocked(result)


def test_r4_unrelated_damage_leaves_an_eligible_objective_unchanged(bench):
    quiet = f.evaluate(bench, f.settled())
    loud = f.evaluate(bench, f.settled(), source=f.values(whirling_damage_per_use=1e12))
    assert quiet.status == loud.status == "eligible"
    assert quiet.objective["score"] == loud.objective["score"]


# R5: provenance comes from the capture ---------------------------------------

@pytest.mark.parametrize("engine", [
    {"head": "wrong-commit", "dirty_hash": None},
    {"head": PIN_HEAD, "dirty_hash": "dirty"},
    {"head": "wrong-commit", "dirty_hash": "dirty"},
    {},
], ids=["wrong-commit", "dirty", "both", "absent"])
def test_r5_foreign_or_missing_engine_identity_blocks(bench, engine):
    ident = dict(identity(f.SYNTH_XML % ""))
    ident.update(engine)
    if not engine:
        ident = {}
    result = f.evaluate(bench, f.settled(), source=f.values(engine=ident))
    assert blocked(result)


def test_r5_values_from_another_document_block(bench):
    result = f.evaluate(bench, f.settled(), source=f.values(engine=identity(OTHER_XML)))
    assert blocked(result)


# R6: fixed v1 windows and complete identity ----------------------------------

def test_r6_alternate_windows_are_not_the_v1_objective(bench):
    base = f.evaluate(bench, f.settled())
    short = f.evaluate(bench, f.settled(), window_s=12.0)
    burst = f.evaluate(bench, f.settled(), burst_s=1.0)
    assert base.status == "eligible"
    for other in (short, burst):
        assert blocked(other)
        assert other.evaluation_id != base.evaluation_id
    assert short.evaluation_id != burst.evaluation_id


def test_r6_changed_scenario_changes_identity(bench, tmp_path):
    other = tmp_path / "other.json"
    other.write_text(json.dumps({"data_gaps": [], "scenarios": [
        {"scenario_id": "flicker_sustained_v1", "category": "dps_benchmark",
         "fields": {"note": {"value": "changed", "gap_ids": []}}}]}), encoding="utf-8")
    a = f.evaluate(bench, f.settled())
    b = f.evaluate(other, f.settled())
    assert a.evaluation_id != b.evaluation_id


# R7: unsupported methods are refused at the boundary -------------------------

@pytest.mark.parametrize("method", ["pob-cycle-v1", "no-such-method"])
def test_r7_unsupported_method_is_refused_with_a_settled_registry(bench, method):
    result = f.evaluate(bench, f.settled(), method=method)
    assert blocked(result)
    assert result.status == "unsupported_method"
