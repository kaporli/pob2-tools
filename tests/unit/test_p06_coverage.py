"""P06-T01 to T03: mechanics registry, coverage analysis, evidence resolution.

Synthetic fixtures test the machinery; the last section runs the real seed
export against the seeded registry and the committed engine parse evidence.
Nothing here starts the engine.
"""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest

from pob2opt.coverage import (CoverageLedger, EntityDiff, RegistryError,
                              Resolution, ResolutionRefused, analyse, decide)
from pob2opt.coverage.flicker_v1 import POB_CYCLE_INPUT_RULES, build_registry
from pob2opt.coverage.inputs import (BuildFacts, EngineState, GemFacts,
                                     GroupFacts, ItemFacts, LineSupport,
                                     ModSupport, ScenarioFacts,
                                     build_facts_from_pob_xml, load_mod_support,
                                     load_scenarios, parse_config_options)
from pob2opt.coverage.registry import MechanicsRegistry, RuleEntry, make_rule
from pob2opt.domain.absent import ABSENT
from pob2opt.domain.enums import (ActionKind, GapKind, GapSeverity, GapStatus,
                                  RuleOwner, RuleSupport, RuleValidation,
                                  ScenarioCategory)
from pob2opt.domain.records import (Predicate, PredicateOperator, RotationPolicy,
                                    RotationRule)
from pob2opt.domain.validation import validate_record

REPO = Path(__file__).resolve().parents[2]
SEED = REPO / "docs/evidence/P09-T01.1/seed/export-flicker-main.xml"
PROBE = REPO / "docs/evidence/P06/seed-engine-mod-support.json"
SCENARIOS = REPO / "benchmarks/p09-flicker-v1/scenarios.json"
PIN = "ce566eac45ea8a86477f513c7ee65a1ebe60014e"
PROFILE = "profile/test"

POB, SIM, SCN = RuleOwner.POB, RuleOwner.SIMULATOR, RuleOwner.SCENARIO
IMPL, UNSUP, UNK = RuleSupport.IMPLEMENTED, RuleSupport.UNSUPPORTED, RuleSupport.UNKNOWN
CHECKED, UNTESTED = RuleValidation.FIXTURE_CHECKED, RuleValidation.UNTESTED


# ------------------------------------------------------------- fixtures ===

def entry(mid, *, owner=POB, support=IMPL, validation=CHECKED, domain="damage",
          subjects=(), deps=(), inputs=(), evidence=("ev/" ,), reviewed="reviewer",
          title=None, **kw):
    return RuleEntry(
        rule=make_rule(mid, owner=owner, support=support, validation=validation,
                       dependency_ids=deps, required_input_paths=inputs,
                       evidence_ids=[e + mid for e in evidence] if evidence else [],
                       patch_profile_ids=(PROFILE,)),
        title=title or mid, domain=domain, subject_ids=tuple(subjects),
        reviewed_by=reviewed, **kw)


def settled_registry(**overrides) -> MechanicsRegistry:
    """A registry in which every rule the fixture build needs is settled."""
    entries = {
        "skill/Strike": entry("skill/Strike", subjects=("skill:Strike",),
                              damage_source=True, inputs=("/pob/Strike/Duration",),
                              provides_paths=("skill.Strike.ready",)),
        "skill/Builder": entry("skill/Builder", subjects=("skill:Builder",),
                               damage_source=True),
        "resource/charges": entry("resource/charges", owner=SIM, domain="resource",
                                  subjects=("skill:Builder",),
                                  provides_paths=("state.charges",)),
        "activation/gate": entry("activation/gate", owner=SIM, domain="activation",
                                 subjects=("support:SupportGate",), critical="activation",
                                 satisfied_by=("skill:Strike",)),
        "support/SupportGate": entry("support/SupportGate", subjects=("support:SupportGate",),
                                     deps=("activation/gate",)),
        "attribution/bench": entry("attribution/bench", owner=SIM, domain="attribution",
                                   subjects=("scenario:bench",), critical="attribution",
                                   assignments={"skill/Strike": "flicker_direct",
                                                "skill/Builder": "unrelated"}),
        "action/move": entry("action/move", owner=SIM, domain="timing",
                             provides_paths=("action.move.duration",)),
    }
    for key, value in overrides.items():
        key = key.replace("__", "/")
        if value is None:
            entries.pop(key)
        else:
            entries[key] = value
    return MechanicsRegistry("test", "1", entries.values())


def gem(skill_id, support=False):
    return GemFacts(skill_id=skill_id, name=skill_id, enabled=True, support=support)


def build(*, extra_groups=(), engine=EngineState(PIN, False), items=(), passives=(),
          config=None, name_suffix=""):
    groups = (
        GroupFacts(1, True, None, frozenset({1}),
                   (gem("Strike"), gem("SupportGate", True))),
        GroupFacts(2, True, None, frozenset({1}), (gem("Builder"),)),
    ) + tuple(extra_groups)
    return BuildFacts(build_id="build/test", class_name="Monk", ascendancy=None,
                      level=90, declared_patch=None, main_group=1, groups=groups,
                      passive_ids=tuple(passives), items=tuple(items),
                      config_explicit={}, config_effective=None, engine=engine)


def mods(items=None, nodes=None, config=()):
    return ModSupport(source="test", pob_commit=PIN, items=items or {},
                      nodes=nodes or {}, config=tuple(config))


def cmp(path, op=PredicateOperator.GTE, value=0):
    return Predicate(operator=op, operands=ABSENT, path=path, value=value)


def rule(i, action, skill=None, predicate=None, action_id=None):
    return RotationRule(rule_index=i, action_id=action_id or "a%d" % i,
                        action=ActionKind(action), skill_id=skill,
                        target_selector="target", weapon_set_id=None,
                        predicate=predicate or cmp("state.charges"))


def rotation(*rules):
    record = RotationPolicy(schema_version=1, record_id="rot", created_at="2026-10-18T00:00:00Z",
                            provenance_ids=["test"], rotation_id="rot", version="1",
                            name="test", category=ScenarioCategory.BOSS, rules=list(rules))
    assert validate_record(record).ok
    return record


ROT = (rule(0, "use_skill", "Builder"), rule(1, "use_skill", "Strike"))
SCENARIO = ScenarioFacts("bench", "dps_benchmark", frozenset(), {})
INPUTS = {"/pob/Strike/Duration": 0.5}


def run(registry=None, *, b=None, rot=ROT, scenario=SCENARIO, ms=None, inputs=INPUTS,
        compatibility="verified"):
    registry = registry or settled_registry()
    report = analyse(b or build(), scenario, registry,
                     rotation=rotation(*rot) if rot is not None else None,
                     mod_support=ms if ms is not None else mods(),
                     patch_profile_id=PROFILE, patch_compatibility=compatibility,
                     pinned_commit=PIN, inputs=inputs)
    return report, decide(report, registry)


def classes(report, severity=GapSeverity.BLOCKING):
    return sorted({f.gap_class for f in report.findings if f.severity is severity})


# ------------------------------------------------------- P06-T01 registry ===

def test_baseline_fixture_is_eligible():
    report, decision = run()
    assert decision.eligible, (decision.reasons, report.to_json()["findings"])
    assert report.domains["damage"]["coverage"] == "supported"


def test_duplicate_mechanic_is_refused():
    reg = settled_registry()
    with pytest.raises(RegistryError, match="duplicate"):
        MechanicsRegistry("x", "1", list(reg) + [reg["skill/Strike"]])


def test_unregistered_dependency_and_static_cycle_are_refused():
    with pytest.raises(RegistryError, match="unregistered"):
        settled_registry(skill__Strike=entry("skill/Strike", deps=("nope",)))
    with pytest.raises(RegistryError, match="cycle"):
        MechanicsRegistry("x", "1", [entry("a", deps=("b",)), entry("b", deps=("a",))])


def test_changing_a_rule_changes_the_registry_hash_but_a_title_does_not():
    base = settled_registry()
    changed = settled_registry(skill__Strike=replace(
        base["skill/Strike"], rule=replace(base["skill/Strike"].rule, limitations=["x"])))
    retitled = settled_registry(skill__Strike=replace(base["skill/Strike"], title="Other"))
    assert changed.registry_hash() != base.registry_hash()
    assert retitled.registry_hash() == base.registry_hash()
    ids = ["skill/Strike"]
    assert retitled.closure_hash(ids) == base.closure_hash(ids)
    assert changed.closure_hash(ids) != base.closure_hash(ids)
    # An unrelated rule change leaves this closure's identity alone.
    other = settled_registry(skill__Builder=replace(
        base["skill/Builder"], rule=replace(base["skill/Builder"].rule, limitations=["y"])))
    assert other.closure_hash(ids) == base.closure_hash(ids)


def test_guide_derived_rule_without_checks_stays_unvalidated():
    reg = settled_registry(skill__Builder=entry("skill/Builder", subjects=("skill:Builder",),
                                                validation=UNTESTED, damage_source=True))
    report, decision = run(reg)
    assert "unvalidated" in classes(report, GapSeverity.RANKING_SENSITIVE)
    assert decision.eligible  # ranking sensitive only; reported, not hidden
    assert report.domains["damage"]["validation"] == "unvalidated"


def test_seed_registry_is_valid_and_owns_every_cycle_input():
    reg = build_registry()
    assert len(reg) > 50
    for name, mid in POB_CYCLE_INPUT_RULES.items():
        assert mid in reg, name
    for record in reg.records():
        assert validate_record(record).ok
    assert {e.mechanic_id for e in reg.critical("activation")} == {"activation/hit-and-run-reuse"}
    assert {e.mechanic_id for e in reg.critical("attribution")} == {"attribution/flicker-sustained-v1"}


def test_seed_registry_names_every_open_benchmark_gap():
    reg = build_registry()
    scenario = load_scenarios(SCENARIOS)["flicker_sustained_v1"]
    named = {g for e in reg for g in e.protocol_gap_ids}
    named |= {g for gaps in scenario.missing_fields.values() for g in gaps}
    open_blocking = {g.gap_id for g in scenario.protocol_gaps
                     if g.status is GapStatus.OPEN and g.severity is GapSeverity.BLOCKING}
    assert open_blocking - named <= {"gap-p09-t011-rotation-details", "gap-p09-t011-patch-profile"}
    assert "gap-p09-t011-hit-and-run-movement" in named
    assert "gap-p09-t011-attribution-rules" in named


# ------------------------------------------------------ P06-T02 analysis ===

def test_removing_a_duration_input_names_the_field_and_skill():
    report, decision = run(inputs={})
    gaps = [f for f in report.findings if f.gap_class == "missing_data"]
    assert len(gaps) == 1
    assert gaps[0].field_paths == ("/pob/Strike/Duration",)
    assert "skill:Strike" in gaps[0].subject_ids
    assert not decision.eligible
    datagap = report.gaps()[0]
    assert datagap.kind is GapKind.MISSING_INPUT and datagap.field_paths == ["/pob/Strike/Duration"]


def test_unsupported_trigger_is_unsupported_and_unknown_rule_is_distinct():
    reg = settled_registry(resource__charges=entry(
        "resource/charges", owner=SIM, support=UNSUP, domain="resource",
        subjects=("skill:Builder",), provides_paths=("state.charges",)))
    report, decision = run(reg)
    assert report.domains["resource"]["coverage"] == "unsupported"
    assert classes(report) == ["missing_implementation"]
    reg2 = settled_registry(resource__charges=entry(
        "resource/charges", owner=SIM, support=UNK, domain="resource",
        subjects=("skill:Builder",), provides_paths=("state.charges",)))
    report2, _ = run(reg2)
    assert classes(report2) == ["unknown_rule"]
    assert not decision.eligible


def test_missing_data_and_missing_implementation_produce_different_requests():
    reg = settled_registry(resource__charges=entry(
        "resource/charges", owner=SIM, support=UNSUP, domain="resource",
        subjects=("skill:Builder",), provides_paths=("state.charges",)))
    report, _ = run(reg, inputs={})
    by_class = {f.gap_class: f for f in report.findings}
    gaps = {g.gap_id: g for g in report.gaps()}
    data = gaps[by_class["missing_data"].gap_id]
    impl = gaps[by_class["missing_implementation"].gap_id]
    assert data.kind is GapKind.MISSING_INPUT and impl.kind is GapKind.UNSUPPORTED_RULE
    assert data.collection_method != impl.collection_method
    assert data.needed_evidence != impl.needed_evidence


def test_display_name_omission_does_not_change_blocking():
    named = build(items=(ItemFacts("Ring 1", "1", "Some Ring"),))
    unnamed = build(items=(ItemFacts("Ring 1", "1", ""),))
    ms = mods(items={"Ring 1": (LineSupport("+10 to Strength", True, None),)})
    a, da = run(b=named, ms=ms)
    b, db = run(b=unnamed, ms=ms)
    assert [f.gap_id for f in a.findings] == [f.gap_id for f in b.findings]
    assert da.eligible and db.eligible


def test_unknown_skill_item_line_and_hidden_toggle_are_detected():
    b = build(extra_groups=(GroupFacts(3, True, None, frozenset({1}), (gem("Mystery"),)),),
              items=(ItemFacts("Ring 1", "1", "Ring"),))
    ms = mods(items={"Ring 1": (LineSupport("Strikes deal double damage on Tuesdays", False,
                                            "Strikes deal double damage on Tuesdays"),)},
              config=[{"var": "conditionOnslaught", "shown": True, "input": True}])
    report, decision = run(b=b, ms=ms)
    got = classes(report)
    assert {"unknown_entity", "missing_implementation", "hidden_assumption"} <= set(got)
    hidden = [f for f in report.findings if f.gap_class == "hidden_assumption"]
    assert hidden[0].field_paths == ("/config/conditionOnslaught",)
    assert not decision.eligible


def test_hidden_config_option_is_informational_and_quests_are_ignored():
    ms = mods(config=[{"var": "conditionOnslaught", "shown": False, "input": True},
                      {"var": "questAct 1X", "shown": True, "input": True},
                      {"var": "enemyLevel", "shown": True, "placeholder": 82}])
    report, decision = run(ms=ms)
    assert decision.eligible
    assert [f.gap_class for f in report.findings] == ["not_applicable"]


def test_missing_engine_parse_data_is_missing_data_not_a_pass():
    b = build(items=(ItemFacts("Ring 1", "1", "Ring"),), passives=("123",))
    report = analyse(b, SCENARIO, settled_registry(), rotation=rotation(*ROT),
                     mod_support=None, patch_profile_id=PROFILE,
                     patch_compatibility="verified", pinned_commit=PIN, inputs=INPUTS)
    fields = {p for f in report.findings for p in f.field_paths}
    assert {"/engine_parse/items", "/engine_parse/nodes", "/config/effective"} <= fields


def test_rotation_inputs_must_be_produced():
    report, decision = run(rot=(rule(0, "use_skill", "Strike", cmp("state.rage")),))
    f = [f for f in report.findings if f.gap_class == "missing_implementation"]
    assert f and f[0].field_paths == ("state.rage",)
    assert not decision.eligible
    report2, _ = run(rot=None)
    assert any(f.field_paths == ("/rotation",) for f in report2.findings)


def test_on_kill_effect_supplies_nothing_without_kills():
    reg = settled_registry(resource__charges=entry(
        "resource/charges", owner=SIM, domain="resource", subjects=("skill:Builder",),
        provides_paths=("state.charges",), requires_events=("kill",)))
    report, decision = run(reg)
    assert not decision.eligible
    waits = [f for f in report.findings if f.field_paths == ("state.charges",)]
    assert waits and waits[0].severity is GapSeverity.BLOCKING
    clear = ScenarioFacts("bench", "clear", frozenset({"kill"}), {})
    report2, _ = run(reg, scenario=clear)
    assert not [f for f in report2.findings if f.field_paths == ("state.charges",)]


def test_stale_profile_blocks_whatever_the_build_declares():
    b = replace(build(), declared_patch="0.5.5e")
    report, decision = run(b=b, compatibility="stale")
    assert "stale_patch" in classes(report)
    assert any("does not override" in n for n in report.notes)
    assert not decision.eligible


# ---------------------------------------- P09-T01.1 R1: activation, attribution ===

def test_unresolved_activation_blocks_even_with_everything_else_resolved():
    reg = settled_registry(activation__gate=entry(
        "activation/gate", owner=SIM, support=UNK, validation=UNTESTED, domain="activation",
        subjects=("support:SupportGate",), critical="activation", reviewed=None))
    report, decision = run(reg)
    assert not decision.eligible
    assert "activation/gate" in decision.unsettled_critical
    # Lowering every finding's severity cannot make it eligible.
    softened = replace(report, findings=tuple(replace(f, severity=GapSeverity.INFORMATIONAL)
                                              for f in report.findings))
    again = decide(softened, reg)
    assert not again.eligible and "activation/gate" in again.unsettled_critical


def test_movement_not_re_enabling_the_skill_blocks():
    moved = entry("activation/gate", owner=SIM, domain="activation",
                  subjects=("support:SupportGate",), critical="activation",
                  satisfied_by=("move",))
    reg = settled_registry(activation__gate=moved)
    report, decision = run(reg)
    assert "activation_unmet" in classes(report)
    assert not decision.eligible
    with_move = ROT + (rule(2, "move", predicate=cmp("state.charges")),)
    report2, decision2 = run(reg, rot=with_move)
    assert "activation_unmet" not in classes(report2)
    assert decision2.eligible
    no_timing = settled_registry(activation__gate=moved, action__move=None)
    report3, decision3 = run(no_timing, rot=with_move)
    assert any(f.field_paths == ("action.move.duration",) for f in report3.findings)
    assert not decision3.eligible


def test_unassigned_secondary_damage_blocks():
    reg = settled_registry(
        support__SupportSpark=entry("support/SupportSpark", subjects=("support:SupportSpark",),
                                    damage_source=True))
    b = build(extra_groups=(GroupFacts(3, True, None, frozenset({1}),
                                       (gem("Strike"), gem("SupportSpark", True))),))
    report, decision = run(reg, b=b)
    unassigned = [f for f in report.findings if f.gap_class == "unassigned_damage"]
    assert [f.subject_ids for f in unassigned] == [("support:SupportSpark",)]
    assert not decision.eligible


def test_attribution_unsettled_blocks_with_all_sources_assigned():
    reg = settled_registry(attribution__bench=entry(
        "attribution/bench", owner=SIM, domain="attribution", subjects=("scenario:bench",),
        critical="attribution", validation=UNTESTED, reviewed=None,
        assignments={"skill/Strike": "flicker_direct", "skill/Builder": "unrelated"}))
    report, decision = run(reg)
    assert "unassigned_damage" not in classes(report)
    assert "attribution/bench" in decision.unsettled_critical
    assert not decision.eligible


def test_report_from_an_older_registry_is_not_accepted():
    report, _ = run()
    newer = settled_registry(skill__Builder=entry("skill/Builder", subjects=("skill:Builder",),
                                                  damage_source=True, evidence=("ev2/",)))
    assert not decide(report, newer).eligible


# ---------------------------------------------------- P06-T03 resolution ===

def _gap_ledger(registry):
    report, _ = run(registry)
    ledger = CoverageLedger(registry, report.gaps())
    return ledger, report


def unknown_gate_registry():
    return settled_registry(activation__gate=entry(
        "activation/gate", owner=SIM, support=UNK, validation=UNTESTED, domain="activation",
        subjects=("support:SupportGate",), critical="activation", reviewed=None))


def _activation_gap(report):
    return next(f.gap_id for f in report.findings if "activation/gate" in f.mechanic_ids)


def test_resolution_needs_evidence_a_correction_and_a_known_gap():
    ledger, report = _gap_ledger(unknown_gate_registry())
    gid = _activation_gap(report)
    base = dict(resolution_id="r1", gap_id=gid, author="eng", resolved_at="2026-10-18T00:00:00Z",
                mechanic_id="activation/gate")
    with pytest.raises(ResolutionRefused, match="evidence"):
        ledger.resolve(Resolution(evidence_ids=(), rule_changes={"support": IMPL}, **base))
    with pytest.raises(ResolutionRefused, match="corrected"):
        ledger.resolve(Resolution(evidence_ids=("trial-1",), **base))
    with pytest.raises(ResolutionRefused, match="unknown gap"):
        ledger.resolve(Resolution(evidence_ids=("trial-1",), rule_changes={"support": IMPL},
                                  **dict(base, gap_id="nope")))


def test_resolved_gap_is_traceable_and_the_rule_plugs_in():
    ledger, report = _gap_ledger(unknown_gate_registry())
    gid = _activation_gap(report)
    reg = ledger.resolve(Resolution(
        resolution_id="r1", gap_id=gid, evidence_ids=("trial-1",), author="eng",
        reviewer="rev", resolved_at="2026-10-18T01:00:00Z", mechanic_id="activation/gate",
        rule_changes={"support": IMPL, "validation": CHECKED},
        entry_changes={"satisfied_by": ("skill:Strike",)}, outcome="teleport_satisfies=true"))
    gap = ledger.gaps[gid]
    assert gap.status is GapStatus.RESOLVED and gap.resolution_evidence_ids == ["trial-1"]
    event = ledger.history[-1]
    assert event.kind == "resolved" and "eng" in event.detail and "rev" in event.detail
    assert reg["activation/gate"].rule.version == "2"
    assert "trial-1" in reg["activation/gate"].rule.evidence_ids
    _, decision = run(reg)
    assert decision.eligible


def test_changing_a_dependency_supersedes_only_affected_evaluations():
    reg = settled_registry()
    ledger = CoverageLedger(reg, run(reg, inputs={})[0].gaps())
    gid = next(iter(ledger.gaps))
    ledger.track_evaluation("eval-gate", reg.closure(["support/SupportGate"]))
    ledger.track_evaluation("eval-builder", reg.closure(["skill/Builder"]))
    before = reg.closure_hash(["support/SupportGate"])
    reg2 = ledger.resolve(Resolution(
        resolution_id="r1", gap_id=gid, evidence_ids=("doc-1",), author="eng",
        reviewer="rev", resolved_at="2026-10-18T02:00:00Z", mechanic_id="activation/gate",
        rule_changes={"limitations": ["narrowed"]}))
    assert ledger.current_evaluations() == ["eval-builder"]
    assert "eval-gate" in ledger.superseded
    assert reg2.closure_hash(["support/SupportGate"]) != before
    assert reg2.closure_hash(["skill/Builder"]) == reg.closure_hash(["skill/Builder"])


def test_contradicting_evidence_reopens_instead_of_averaging():
    ledger, report = _gap_ledger(unknown_gate_registry())
    gid = _activation_gap(report)
    common = dict(gap_id=gid, author="eng", reviewer="rev", mechanic_id="activation/gate")
    ledger.resolve(Resolution(resolution_id="r1", evidence_ids=("trial-1",),
                              resolved_at="2026-10-18T01:00:00Z",
                              rule_changes={"support": IMPL, "validation": CHECKED},
                              entry_changes={"satisfied_by": ("skill:Strike",)},
                              outcome="teleport_satisfies=true", **common))
    reg = ledger.resolve(Resolution(resolution_id="r2", evidence_ids=("trial-2",),
                                    resolved_at="2026-10-18T02:00:00Z",
                                    rule_changes={"support": IMPL, "validation": CHECKED},
                                    entry_changes={"satisfied_by": ("move",)},
                                    outcome="teleport_satisfies=false", **common))
    assert reg["activation/gate"].rule.validation is RuleValidation.CONTRADICTED
    assert reg["activation/gate"].satisfied_by == ("skill:Strike",)
    gap = ledger.gaps[gid]
    assert gap.kind is GapKind.CONFLICTING_EVIDENCE and gap.status is GapStatus.OPEN
    assert ledger.history[-1].kind == "contradicted"
    _, decision = run(reg)
    assert not decision.eligible


def test_patch_invalidation_marks_changed_rules_and_dependents_stale():
    reg = settled_registry()
    ledger = CoverageLedger(reg, [])
    ledger.track_evaluation("e-gate", reg.closure(["support/SupportGate"]))
    ledger.track_evaluation("e-builder", reg.closure(["skill/Builder"]))
    new = ledger.invalidate_for_patch("profile/next", EntityDiff(
        changed=frozenset({"support:SupportGate"})), at="2026-10-19T00:00:00Z")
    assert new["activation/gate"].rule.validation is RuleValidation.STALE
    assert new["support/SupportGate"].rule.validation is RuleValidation.STALE
    assert "profile/next" in new["skill/Builder"].rule.patch_profile_ids
    assert ledger.current_evaluations() == ["e-builder"]


def test_display_only_patch_changes_invalidate_nothing():
    reg = settled_registry()
    ledger = CoverageLedger(reg, [])
    ledger.track_evaluation("e1", reg.closure(["support/SupportGate"]))
    new = ledger.invalidate_for_patch("profile/next", EntityDiff(
        display_only=frozenset({"skill:Strike"})), at="2026-10-19T00:00:00Z")
    assert all(e.rule.validation is not RuleValidation.STALE for e in new)
    assert ledger.current_evaluations() == ["e1"]


def test_unknown_impact_marks_the_family_or_everything_stale():
    reg = settled_registry()
    ledger = CoverageLedger(reg, [])
    new = ledger.invalidate_for_patch("profile/next", EntityDiff(
        unknown_families=frozenset({"support:"})), at="2026-10-19T00:00:00Z")
    stale = {e.mechanic_id for e in new if e.rule.validation is RuleValidation.STALE}
    assert stale == {"support/SupportGate", "activation/gate"}
    everything = CoverageLedger(reg, []).invalidate_for_patch("profile/next", None,
                                                              at="2026-10-19T00:00:00Z")
    assert all(e.rule.validation is RuleValidation.STALE for e in everything)
    report = analyse(build(), SCENARIO, everything, rotation=rotation(*ROT), mod_support=mods(),
                     patch_profile_id="profile/next", patch_compatibility="verified",
                     pinned_commit=PIN, inputs=INPUTS)
    assert "stale_patch" in classes(report)


# ------------------------------------------------------- config options ===

def test_config_option_headers_are_read_without_apply_bodies():
    source = "\n".join([
        '\t{ var = "FlickerStrikeBypassCD", type = "check", label = "Bypass CD?", ifSkill = "Flicker Strike", includeTransfigured = true, defaultState = true, apply = function(val, modList, enemyModList)',
        '\t{ var = "multiplierCombo", type = "count", label = "Combo:", ifMult = "ComboStacks", apply = function(val)',
        '\t{ var = "x", type = "list", ifSkill = { "A", "B" }, defaultIndex = 2, apply = function() end },',
    ])
    options = parse_config_options(source)
    assert options["FlickerStrikeBypassCD"].gates == {"ifSkill": ("Flicker Strike",)}
    assert options["FlickerStrikeBypassCD"].default is True
    assert options["multiplierCombo"].default is None
    assert options["x"].gates == {"ifSkill": ("A", "B")} and options["x"].default == ("index", 2)


# ------------------------------------------------------ the real seed ===

def seed_report(**kw):
    facts = build_facts_from_pob_xml(SEED.read_bytes())
    scenario = load_scenarios(SCENARIOS)["flicker_sustained_v1"]
    reg = build_registry()
    report = analyse(facts, scenario, reg, mod_support=load_mod_support(PROBE),
                     patch_profile_id="patch-profile/0.5.5e/ac0e930898cb3951",
                     patch_compatibility="partial", pinned_commit=PIN, **kw)
    return report, decide(report, reg), reg


def test_seed_is_not_eligible_and_names_the_r1_rules():
    report, decision, _ = seed_report()
    assert not decision.eligible
    assert set(decision.unsettled_critical) == {"activation/hit-and-run-reuse",
                                                "attribution/flicker-sustained-v1"}
    mechanics = {m for f in report.blocking() for m in f.mechanic_ids}
    for mid in ("passive/41751", "passive/61586", "support/SupportAilithLineagePlayer",
                "resource/power-charges", "config/FlickerStrikeBypassCD",
                "activation/hit-and-run-reuse", "resource/mana-sustain"):
        assert mid in mechanics, mid
    assert not [f for f in report.findings if f.gap_class == "unknown_entity"]


def test_seed_parse_evidence_findings():
    report, _, _ = seed_report()
    by_field = {f.field_paths[0]: f for f in report.findings if f.field_paths}
    stonefist = by_field["Ignore Attribute Requirements to equip Gloves"]
    assert stonefist.severity is GapSeverity.BLOCKING and stonefist.subject_ids == ("passive:39595",)
    onkill = by_field["25% Chance to gain a Charge when you kill an enemy"]
    assert onkill.gap_class == "not_applicable"
    bypass = [f for f in report.findings if "config/FlickerStrikeBypassCD" in f.mechanic_ids]
    assert bypass and bypass[0].gap_class == "unknown_rule"
    assert len(report.gaps()) == len(report.findings)


def test_seed_evidence_file_matches_the_committed_report():
    path = REPO / "docs/evidence/P06/seed-coverage-flicker_sustained_v1.json"
    stored = json.loads(path.read_text(encoding="utf-8"))
    report, decision, reg = seed_report(inputs=stored["inputs"])
    assert stored["registry_hash"] == reg.registry_hash()
    assert stored["report"]["findings"] == report.to_json()["findings"]
    assert stored["decision"]["eligible"] is decision.eligible is False
