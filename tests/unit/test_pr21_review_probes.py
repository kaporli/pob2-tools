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


# Inherited R1 to R3 (PR #19) through evaluate_flicker -------------------------

def _two_loadouts(active: str) -> str:
    one = f.SYNTH_XML % ""
    start, end = one.index("<SkillSet id=\"1\">"), one.index("</SkillSet>") + len("</SkillSet>")
    first = one[start:end]
    second = first.replace('<SkillSet id="1">', '<SkillSet id="7">').replace(
        '<Gem skillId="ChargedStaffPlayer"',
        '<Gem skillId="UnknownActiveSkill" nameSpec="Unknown" enabled="true"/>\n'
        '   <Gem skillId="ChargedStaffPlayer"')
    return one[:start].replace("<Skills>", '<Skills activeSkillSet="%s">' % active) \
        + first + "\n " + second + one[end:]


def _evaluate_doc(bench, xml, **kw):
    return f.evaluate(bench, f.settled(), xml=xml,
                      source=f.values(engine=f.identity(xml, **kw)))


def test_r1_unsupported_state_in_the_selected_loadout_blocks(bench):
    assert _evaluate_doc(bench, _two_loadouts("1")).status == "eligible"
    result = _evaluate_doc(bench, _two_loadouts("7"))
    assert blocked(result)
    assert any(b["class"] == "unknown_entity" for b in result.decision["blocking"])


def test_r2_capture_from_an_unclean_or_other_engine_blocks(bench):
    for kw in ({"pob_commit": "wrong-commit"}, {"pob_dirty": True}, {"pob_dirty": None}):
        result = _evaluate_doc(bench, f.SYNTH_XML % "", **kw)
        assert blocked(result), kw
        assert any(b["class"] == "unbound_evidence" for b in result.decision["blocking"]), kw


def test_r2_capture_of_another_document_blocks(bench):
    xml = f.SYNTH_XML % ""
    ident = f.identity(xml)
    ident["parse_capture"] = f.identity(OTHER_XML)["parse_capture"]
    result = f.evaluate(bench, f.settled(), xml=xml, source=f.values(engine=ident))
    assert blocked(result)
    assert any(b["class"] == "unbound_evidence" for b in result.decision["blocking"])


def test_r2_missing_capture_blocks(bench):
    xml = f.SYNTH_XML % ""
    ident = {k: v for k, v in f.identity(xml).items() if k != "parse_capture"}
    result = f.evaluate(bench, f.settled(), xml=xml, source=f.values(engine=ident))
    assert blocked(result)


def test_r3_unearned_enemy_debuff_blocks(bench):
    xml = (f.SYNTH_XML % "").replace(
        "</PathOfBuilding2>",
        '<Config><Input name="enemyCriticalWeaknessStacks" number="20"/></Config>\n'
        "</PathOfBuilding2>")
    result = _evaluate_doc(bench, xml)
    assert blocked(result)
    assert any(b["class"] == "hidden_assumption"
               and b["fields"] == ["/config/enemyCriticalWeaknessStacks"]
               for b in result.decision["blocking"])


# Re-review F1: custom modifier blocks (PR-19-22-rereview.md) ----------------

def _with_config(body: str) -> str:
    return (f.SYNTH_XML % "").replace(
        "</PathOfBuilding2>", "<Config>%s</Config>\n</PathOfBuilding2>" % body)


def test_f1_enabled_custom_block_blocks_with_everything_else_settled(bench):
    xml = _with_config('<ConfigSet id="1"><CustomModifierBlock enabled="true">'
                       "1000% more Damage</CustomModifierBlock></ConfigSet>")
    result = _evaluate_doc(bench, xml)
    assert blocked(result)
    assert any(b["class"] == "unsupported_modifier" for b in result.decision["blocking"])


@pytest.mark.parametrize("body", [
    '<ConfigSet id="1"><CustomModifierBlock enabled="false">1000% more Damage'
    "</CustomModifierBlock></ConfigSet>",
    '<ConfigSet id="1"><CustomModifierBlock enabled="true"></CustomModifierBlock></ConfigSet>',
    '<ConfigSet id="1"><CustomModifierBlock enabled="true">   </CustomModifierBlock></ConfigSet>',
], ids=["disabled", "empty", "whitespace"])
def test_f1_inactive_custom_blocks_do_not_block(bench, body):
    assert _evaluate_doc(bench, _with_config(body)).status == "eligible"


def test_f1_legacy_custom_mods_input_blocks(bench):
    xml = _with_config('<ConfigSet id="1"><Input name="customMods" string="1000% more Damage"/>'
                       "</ConfigSet>")
    result = _evaluate_doc(bench, xml)
    assert blocked(result)
    assert any(b["class"] == "unsupported_modifier" for b in result.decision["blocking"])


@pytest.mark.parametrize("active,eligible", [("1", True), ("4", False)])
def test_f1_only_the_selected_config_set_counts(bench, active, eligible):
    xml = (f.SYNTH_XML % "").replace(
        "</PathOfBuilding2>",
        '<Config activeConfigSet="%s"><ConfigSet id="1"/><ConfigSet id="4">'
        '<CustomModifierBlock enabled="true">1000%% more Damage</CustomModifierBlock>'
        "</ConfigSet></Config>\n</PathOfBuilding2>" % active)
    result = _evaluate_doc(bench, xml)
    assert (result.status == "eligible") is eligible, result.decision["reasons"]
