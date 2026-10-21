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
from pob2opt.coverage.inputs import (BuildFacts, CaptureBinding, EngineState,
                                     GemFacts, GroupFacts, ItemFacts, LineSupport,
                                     ModSupport, ScenarioFacts,
                                     build_facts_from_pob_xml, item_text_hash,
                                     load_mod_support, load_scenarios,
                                     parse_config_options)
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
                      config_explicit=dict(config or {}), config_effective=None,
                      engine=engine, document_hash="doc-test", selection=dict(SELECTION))


SELECTION = {"Tree": "1", "Skills": "1", "Items": "1", "Config": "1"}


def item(slot, item_id, name, text=None):
    """An equipped item whose identity is its id and text hash."""
    return ItemFacts(slot, item_id, name, item_text_hash(text or "%s\n%s" % (item_id, name)))


def mods(items=None, nodes=None, config=(), binding=None):
    """A capture as given; unbound unless ``binding`` is supplied."""
    return ModSupport(source="test", pob_commit=PIN, items=items or {},
                      nodes=nodes or {}, config=tuple(config), binding=binding)


def capture(b, *, items=None, nodes=None, config=(), commit=PIN, dirty=False, of=None):
    """A complete capture bound to build ``of`` (default ``b``) on ``commit``.

    Every equipped item and allocated node gets a verified (possibly empty)
    line set unless given; config rows hold the build's inputs plus ``config``.
    """
    source = of or b
    rows = [{"var": k, "shown": True, "input": v} for k, v in source.config_explicit.items()]
    rows += list(config)
    binding = CaptureBinding(
        document_hash=source.document_hash, selection=dict(source.selection),
        pob_commit=commit, pob_dirty=dirty,
        items={i.slot: (i.item_id, i.text_sha256) for i in source.items},
        nodes=tuple(source.passive_ids), config=dict(source.config_explicit),
        custom_mods=tuple(source.custom_mods))
    item_lines = {i.slot: () for i in source.items}
    item_lines.update(items or {})
    node_lines = {n: () for n in source.passive_ids}
    node_lines.update(nodes or {})
    return ModSupport(source="test", pob_commit=commit, items=item_lines, nodes=node_lines,
                      config=tuple(rows), binding=binding)


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
TARGETED = ScenarioFacts("bench", "dps_benchmark", frozenset(), {},
                         target_config={"enemyLevel": 82})
INPUTS = {"/pob/Strike/Duration": 0.5}


def run(registry=None, *, b=None, rot=ROT, scenario=SCENARIO, ms=None, inputs=INPUTS,
        compatibility="verified"):
    registry = registry or settled_registry()
    b = b or build()
    report = analyse(b, scenario, registry,
                     rotation=rotation(*rot) if rot is not None else None,
                     mod_support=ms if ms is not None else capture(b),
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
    named = build(items=(item("Ring 1", "1", "Some Ring", "Ring text"),))
    unnamed = build(items=(item("Ring 1", "1", "", "Ring text"),))
    lines = {"Ring 1": (LineSupport("+10 to Strength", True, None),)}
    a, da = run(b=named, ms=capture(named, items=lines))
    b, db = run(b=unnamed, ms=capture(unnamed, items=lines))
    assert [f.gap_id for f in a.findings] == [f.gap_id for f in b.findings]
    assert da.eligible and db.eligible


def test_unknown_skill_item_line_and_hidden_toggle_are_detected():
    b = build(extra_groups=(GroupFacts(3, True, None, frozenset({1}), (gem("Mystery"),)),),
              items=(item("Ring 1", "1", "Ring"),))
    ms = capture(b, items={"Ring 1": (LineSupport("Strikes deal double damage on Tuesdays",
                                                  False, "Strikes deal double damage on Tuesdays"),)},
                 config=[{"var": "conditionOnslaught", "shown": True, "input": True}])
    report, decision = run(b=b, ms=ms)
    got = classes(report)
    assert {"unknown_entity", "missing_implementation", "hidden_assumption"} <= set(got)
    hidden = [f for f in report.findings if f.gap_class == "hidden_assumption"]
    assert hidden[0].field_paths == ("/config/conditionOnslaught",)
    assert not decision.eligible


def test_hidden_config_option_is_informational_and_quests_are_ignored():
    ms = capture(build(), config=[{"var": "conditionOnslaught", "shown": False, "input": True},
                                  {"var": "questAct 1X", "shown": True, "input": True},
                                  {"var": "enemyLevel", "shown": True, "placeholder": 82}])
    report, decision = run(ms=ms, scenario=TARGETED)
    assert decision.eligible
    assert [f.gap_class for f in report.findings] == ["not_applicable"]


def test_missing_engine_parse_data_is_missing_data_not_a_pass():
    b = build(items=(item("Ring 1", "1", "Ring"),), passives=("123",))
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
    report = analyse(build(), SCENARIO, everything, rotation=rotation(*ROT),
                     mod_support=capture(build()),
                     patch_profile_id="profile/next", patch_compatibility="verified",
                     pinned_commit=PIN, inputs=INPUTS)
    assert "stale_patch" in classes(report)


# ------------------------------------------- PR #19 R1: selected loadout ===

def loadout_doc(*, skill_sets, item_sets, specs, config_sets, active, items=None, titles=None):
    """A PoB document with explicit sets. ``active`` maps tab to selector value."""
    titles = titles or {}
    items = items or {}

    def title(tag, key):
        return ' title="%s"' % titles[(tag, key)] if (tag, key) in titles else ""

    parts = ['<PathOfBuilding2><Build level="90" mainSocketGroup="1"/>']
    parts.append('<Skills activeSkillSet="%s">' % active["Skills"])
    for sid, gems in skill_sets.items():
        parts.append('<SkillSet id="%s"%s>' % (sid, title("Skills", sid)))
        for group in gems:
            parts.append('<Skill enabled="true">' + "".join(
                '<Gem enabled="true" skillId="%s"/>' % g for g in group) + "</Skill>")
        parts.append("</SkillSet>")
    parts.append('</Skills><Tree activeSpec="%s">' % active["Tree"])
    for index, nodes in enumerate(specs, 1):
        parts.append('<Spec nodes="%s"%s/>' % (",".join(nodes), title("Tree", str(index))))
    parts.append('</Tree><Items activeItemSet="%s">' % active["Items"])
    for iid, text in items.items():
        parts.append('<Item id="%s">%s</Item>' % (iid, text))
    for sid, slots in item_sets.items():
        parts.append('<ItemSet id="%s"%s>' % (sid, title("Items", sid)) + "".join(
            '<Slot name="%s" itemId="%s"/>' % kv for kv in slots.items()) + "</ItemSet>")
    parts.append('</Items><Config activeConfigSet="%s">' % active["Config"])
    for sid, inputs in config_sets.items():
        parts.append('<ConfigSet id="%s"%s>' % (sid, title("Config", sid)) + "".join(
            '<Input name="%s" boolean="true"/>' % k for k in inputs) + "</ConfigSet>")
    parts.append("</Config></PathOfBuilding2>")
    return "".join(parts)


GOOD = [["Strike", "SupportGate"], ["Builder"]]
BAD = [["Strike", "SupportGate"], ["Builder"], ["Mystery"]]
RING_A = "Rarity: RARE\nA\nGold Ring"
RING_B = "Rarity: RARE\nB\nGold Ring"


def two_loadouts(active, titles=None, config_b=("conditionOnslaught",)):
    return loadout_doc(
        skill_sets={"3": GOOD, "7": BAD}, specs=[["10"], ["10", "11"]],
        item_sets={"4": {"Ring 1": "21"}, "9": {"Ring 1": "22"}},
        config_sets={"2": [], "5": list(config_b)},
        items={"21": RING_A, "22": RING_B}, active=active, titles=titles)


FIRST = {"Skills": "3", "Tree": "1", "Items": "4", "Config": "2"}
SECOND = {"Skills": "7", "Tree": "2", "Items": "9", "Config": "5"}


def analyse_doc(doc, *, loadout=None, registry=None):
    facts = build_facts_from_pob_xml(doc, loadout=loadout, engine=EngineState(PIN, False))
    return run(registry, b=facts)


def test_r1_unsupported_state_only_in_the_selected_second_loadout_blocks():
    facts = build_facts_from_pob_xml(two_loadouts(SECOND))
    assert dict(facts.selection) == SECOND
    assert [g.skill_id for grp in facts.groups for g in grp.gems][-1] == "Mystery"
    assert facts.passive_ids == ("10", "11")
    assert [(i.slot, i.item_id) for i in facts.items] == [("Ring 1", "22")]
    assert dict(facts.config_explicit) == {"conditionOnslaught": True}
    report, decision = analyse_doc(two_loadouts(SECOND))
    assert not decision.eligible
    assert {"unknown_entity", "hidden_assumption"} <= set(classes(report))


def test_r1_selecting_the_supported_first_loadout_analyses_it():
    facts = build_facts_from_pob_xml(two_loadouts(FIRST))
    assert dict(facts.selection) == FIRST
    assert [(i.slot, i.item_id) for i in facts.items] == [("Ring 1", "21")]
    report, decision = analyse_doc(two_loadouts(FIRST))
    assert decision.eligible, report.to_json()["findings"]


def test_r1_missing_selector_target_blocks_instead_of_falling_back():
    for tab, bad in (("Skills", "8"), ("Items", "5"), ("Config", "9"), ("Tree", "3")):
        active = dict(FIRST, **{tab: bad})
        facts = build_facts_from_pob_xml(two_loadouts(active))
        assert tab not in facts.selection
        assert any(p.startswith("/%s" % tab) for p in facts.loadout_problems), tab
        report, decision = analyse_doc(two_loadouts(active))
        assert "loadout" in classes(report) and not decision.eligible


LINKED = {("Tree", "1"): "Boss {1}", ("Tree", "2"): "Map {2}",
          ("Skills", "3"): "a {1}", ("Skills", "7"): "b {2}",
          ("Items", "4"): "a {1}", ("Items", "9"): "b {2}",
          ("Config", "2"): "a {1}", ("Config", "5"): "b {2}"}


def test_r1_named_loadout_uses_pob_links_and_ambiguity_blocks():
    doc = two_loadouts(FIRST, titles=LINKED)
    assert dict(build_facts_from_pob_xml(doc, loadout="Map {2}").selection) == SECOND
    assert dict(build_facts_from_pob_xml(doc, loadout="Boss {1}").selection) == FIRST
    missing = build_facts_from_pob_xml(doc, loadout="Nope")
    assert missing.loadout_problems and not missing.selection
    ambiguous = {**LINKED, ("Items", "9"): "b {1}"}
    facts = build_facts_from_pob_xml(two_loadouts(FIRST, titles=ambiguous), loadout="Boss {1}")
    assert any("ambiguous" in p for p in facts.loadout_problems)
    report, decision = run(b=replace(facts, engine=EngineState(PIN, False)))
    assert "loadout" in classes(report) and not decision.eligible


def test_r1_capture_of_another_loadout_is_not_used():
    second = build_facts_from_pob_xml(two_loadouts(SECOND), engine=EngineState(PIN, False))
    first = build_facts_from_pob_xml(two_loadouts(FIRST), engine=EngineState(PIN, False))
    report, decision = run(b=first, ms=capture(second))
    assert "unbound_evidence" in classes(report) and not decision.eligible


# ----------------------------------------- PR #19 R2: bound parse evidence ===

def r2_build(**kw):
    defaults = dict(items=(item("Ring 1", "1", "Ring", "ring text"),), passives=("5",),
                    config={"conditionX": False})
    defaults.update(kw)
    return build(**defaults)


def unbound_fields(report):
    return {p for f in report.findings if f.gap_class == "unbound_evidence" for p in f.field_paths}


def test_r2_complete_bound_capture_passes():
    b = r2_build()
    report, decision = run(b=b, ms=capture(b))
    assert decision.eligible, report.to_json()["findings"]
    assert not unbound_fields(report)


def test_r2_changed_item_passive_config_or_engine_invalidates():
    old = r2_build()
    old_capture = capture(old)
    baseline = run(b=old, ms=old_capture)[0].input_identity
    cases = {
        "item text": (r2_build(items=(item("Ring 1", "1", "Ring", "other text"),)),
                      "/engine_parse/items/Ring 1"),
        "item id": (r2_build(items=(item("Ring 1", "2", "Ring", "ring text"),)),
                    "/engine_parse/items/Ring 1"),
        "passive": (r2_build(passives=("5", "6")), "/engine_parse/nodes/6"),
        "config": (r2_build(config={"conditionX": True}), "/config"),
    }
    for name, (new, field) in cases.items():
        report, decision = run(b=new, ms=old_capture)
        assert field in unbound_fields(report), name
        assert not decision.eligible, name
        assert report.input_identity != baseline, name
    for commit, dirty in (("wrong-commit", False), (PIN, True), (PIN, None)):
        report, decision = run(b=old, ms=capture(old, commit=commit, dirty=dirty))
        assert "/engine_parse/binding/engine" in unbound_fields(report)
        assert not decision.eligible
        assert report.input_identity != baseline
    other_doc = replace(old, document_hash="doc-other")
    report, decision = run(b=other_doc, ms=old_capture)
    assert "/engine_parse/binding/document" in unbound_fields(report) and not decision.eligible


def test_r2_absent_node_entry_is_not_a_verified_empty_set():
    b = r2_build(passives=("5", "99999999"))
    ms = capture(b)
    nodes = {k: v for k, v in ms.nodes.items() if k != "99999999"}
    report, decision = run(b=b, ms=replace(ms, nodes=nodes))
    missing = [f for f in report.findings if f.field_paths == ("/engine_parse/nodes/99999999",)]
    assert missing and missing[0].severity is GapSeverity.BLOCKING and not decision.eligible
    assert run(b=b, ms=ms)[1].eligible  # present and empty is verified
    reg = settled_registry(**{"passive/99999999": entry("passive/99999999",
                                                        subjects=("passive:99999999",))})
    assert run(reg, b=b, ms=replace(ms, nodes=nodes))[1].eligible


def test_r2_absent_item_entry_and_unknown_item_identity_block():
    b = r2_build()
    ms = capture(b)
    report, decision = run(b=b, ms=replace(ms, items={}))
    assert any(f.field_paths == ("/engine_parse/items/Ring 1",)
               and f.severity is GapSeverity.BLOCKING for f in report.findings)
    assert not decision.eligible
    unknown = r2_build(items=(ItemFacts("Ring 1", "1", "Ring"),))
    report, decision = run(b=unknown, ms=capture(unknown))
    assert "/engine_parse/items/Ring 1" in unbound_fields(report) and not decision.eligible


def test_r2_seed_capture_is_bound_and_complete():
    ms = load_mod_support(PROBE)
    facts = build_facts_from_pob_xml(SEED.read_bytes())
    assert ms.binding is not None
    assert ms.binding.document_hash == facts.document_hash
    assert dict(ms.binding.selection) == dict(facts.selection)
    assert ms.binding.pob_commit == PIN and ms.binding.pob_dirty is False
    assert set(ms.binding.items) == {i.slot for i in facts.items}
    assert all(tuple(ms.binding.items[i.slot]) == (i.item_id, i.text_sha256)
               for i in facts.items)
    assert any(i.slot.startswith("Jewel ") for i in facts.items)
    assert set(ms.nodes) == set(facts.passive_ids) == set(ms.binding.nodes)
    report, _, _ = seed_report()
    assert not unbound_fields(report)


# ------------------------------------------- PR #19 R3: target bindings ===

BENCH_TARGET = {"enemyIsBoss": "Pinnacle", "enemyLevel": 82, "enemyArmour": 8063}
TARGET_SCENARIO = ScenarioFacts("bench", "dps_benchmark", frozenset(), {},
                                target_config=BENCH_TARGET)


def target_rows(**values):
    rows = {"enemyIsBoss": {"input": "Pinnacle"}, "enemyLevel": {"placeholder": 82},
            "enemyArmour": {"placeholder": 8063}}
    rows.update(values)
    return [dict(var=k, shown=True, **v) for k, v in rows.items() if v is not None]


def target_registry(**extra):
    target = entry("target/bench", owner=SCN, domain="target", subjects=("scenario:bench",))
    return settled_registry(**{"target/bench": target}, **extra)


def test_r3_exact_target_values_pass():
    b = build()
    report, decision = run(target_registry(), ms=capture(b, config=target_rows()),
                           scenario=TARGET_SCENARIO)
    assert decision.eligible, report.to_json()["findings"]
    assert "target/bench" in report.rule_ids


def test_r3_mismatched_or_absent_target_values_block():
    b = build()
    for rows, var in ((target_rows(enemyLevel={"placeholder": 83}), "enemyLevel"),
                      (target_rows(enemyArmour={"placeholder": 5000}), "enemyArmour"),
                      (target_rows(enemyIsBoss={"input": "Uber"}), "enemyIsBoss"),
                      (target_rows(enemyArmour=None), "enemyArmour")):
        report, decision = run(target_registry(), ms=capture(b, config=rows),
                               scenario=TARGET_SCENARIO)
        hits = [f for f in report.findings if f.gap_class == "target_mismatch"]
        assert [f.field_paths for f in hits] == [("/config/" + var,)], var
        assert not decision.eligible


def test_r3_unproven_critical_weakness_stacks_block():
    b = build()
    rows = target_rows(enemyCriticalWeaknessStacks={"input": 20})
    report, decision = run(target_registry(), ms=capture(b, config=rows),
                           scenario=TARGET_SCENARIO)
    hidden = [f for f in report.findings if f.gap_class == "hidden_assumption"]
    assert [f.field_paths for f in hidden] == [("/config/enemyCriticalWeaknessStacks",)]
    assert not decision.eligible


def test_r3_debuff_rule_must_establish_magnitude_and_be_settled():
    b = build()
    rows = target_rows(enemyCriticalWeaknessStacks={"input": 20})

    def with_rule(**kw):
        rule = entry("debuff/critical-weakness", owner=SIM, domain="config",
                     subjects=("config:enemyCriticalWeaknessStacks",), **kw)
        return target_registry(**{"debuff/critical-weakness": rule})

    ok = with_rule(config_values={"enemyCriticalWeaknessStacks": 20})
    report, decision = run(ok, ms=capture(b, config=rows), scenario=TARGET_SCENARIO)
    assert decision.eligible, report.to_json()["findings"]
    more = target_rows(enemyCriticalWeaknessStacks={"input": 25})
    report, decision = run(ok, ms=capture(b, config=more), scenario=TARGET_SCENARIO)
    assert "hidden_assumption" in classes(report) and not decision.eligible
    report, decision = run(with_rule(), ms=capture(b, config=rows), scenario=TARGET_SCENARIO)
    assert "hidden_assumption" in classes(report) and not decision.eligible
    unsettled = with_rule(config_values={"enemyCriticalWeaknessStacks": 20},
                          support=UNK, validation=UNTESTED, reviewed=None)
    report, decision = run(unsettled, ms=capture(b, config=rows), scenario=TARGET_SCENARIO)
    assert "unknown_rule" in classes(report) and not decision.eligible


def test_r3_seed_scenario_target_binding_is_explicit():
    scenarios = load_scenarios(SCENARIOS)
    assert dict(scenarios["flicker_sustained_v1"].target_config) == {
        "enemyIsBoss": "Pinnacle", "presetBossSkills": "None", "enemyLevel": 82,
        "enemyFireResist": 50, "enemyColdResist": 50, "enemyLightningResist": 50,
        "enemyChaosResist": 0, "enemyArmour": 8063, "enemyEvasion": 1175}
    assert not scenarios["p09-flk-boss-short"].target_config
    report, _, _ = seed_report()
    assert not [f for f in report.findings if f.gap_class == "target_mismatch"]


# ------------------------------- PR #19 re-review F1: custom modifiers ===

def custom_doc(blocks_1="", blocks_2="", active="1", inputs_1=""):
    return ('<PathOfBuilding2><Build level="90" mainSocketGroup="1"/>'
            '<Skills><Skill enabled="true"><Gem skillId="Strike" enabled="true"/>'
            '<Gem skillId="SupportGate" enabled="true"/></Skill>'
            '<Skill enabled="true"><Gem skillId="Builder" enabled="true"/></Skill></Skills>'
            '<Tree><Spec nodes=""/></Tree><Config activeConfigSet="%s">'
            '<ConfigSet id="1">%s%s</ConfigSet><ConfigSet id="2">%s</ConfigSet>'
            '</Config></PathOfBuilding2>' % (active, inputs_1, blocks_1, blocks_2))


def custom_run(doc):
    facts = build_facts_from_pob_xml(doc, engine=EngineState(PIN, False))
    return facts, run(b=facts, ms=capture(facts))


def modifier_findings(report):
    return [f for f in report.findings if f.gap_class == "unsupported_modifier"]


ENABLED = '<CustomModifierBlock enabled="true" title="Boost">1000% more Damage</CustomModifierBlock>'


def test_f1_enabled_block_is_read_and_blocks():
    facts, (report, decision) = custom_run(custom_doc(ENABLED))
    assert facts.custom_mods == (("Boost", True, "1000% more Damage"),)
    found = modifier_findings(report)
    assert [f.field_paths for f in found] == [("/config/custom_mods/0",)]
    assert found[0].severity is GapSeverity.BLOCKING
    gap = next(g for g in report.gaps() if g.gap_id == found[0].gap_id)
    assert gap.kind is GapKind.UNSUPPORTED_RULE
    assert not decision.eligible
    # An absent enabled attribute means enabled, as in PoB.
    facts, (report, _) = custom_run(custom_doc("<CustomModifierBlock>10% more Damage</CustomModifierBlock>"))
    assert facts.custom_mods == (("Default", True, "10% more Damage"),)
    assert modifier_findings(report)


def test_f1_disabled_and_empty_blocks_stay_inactive():
    disabled = '<CustomModifierBlock enabled="false">1000% more Damage</CustomModifierBlock>'
    empty = '<CustomModifierBlock enabled="true">  \n  </CustomModifierBlock>'
    for doc, blocks in ((custom_doc(disabled), (("Default", False, "1000% more Damage"),)),
                        (custom_doc(empty), (("Default", True, ""),)),
                        (custom_doc(), (("Default", True, ""),))):
        facts, (report, decision) = custom_run(doc)
        assert facts.custom_mods == blocks
        assert not modifier_findings(report)
        assert decision.eligible, report.to_json()["findings"]


def test_f1_legacy_custom_mods_input_migrates_like_pob():
    legacy = '<Input name="customMods" string="50% more Damage"/>'
    facts, (report, decision) = custom_run(custom_doc(inputs_1=legacy))
    assert facts.custom_mods == (("Default", True, "50% more Damage"),)
    assert "customMods" not in facts.config_explicit
    assert modifier_findings(report) and not decision.eligible
    # A block with text wins; the legacy input is dropped.
    facts, (report, _) = custom_run(custom_doc(
        '<CustomModifierBlock enabled="false">x</CustomModifierBlock>', inputs_1=legacy))
    assert facts.custom_mods == (("Default", False, "x"),)
    assert not modifier_findings(report)


def test_f1_block_in_the_inactive_config_set_is_not_read():
    facts, (report, decision) = custom_run(custom_doc(blocks_2=ENABLED, active="1"))
    assert facts.custom_mods == (("Default", True, ""),)
    assert decision.eligible
    facts, (report, decision) = custom_run(custom_doc(blocks_2=ENABLED, active="2"))
    assert modifier_findings(report) and not decision.eligible


def test_f1_custom_blocks_are_part_of_the_capture_binding():
    plain = build_facts_from_pob_xml(custom_doc(), engine=EngineState(PIN, False))
    boosted = build_facts_from_pob_xml(custom_doc(ENABLED), engine=EngineState(PIN, False))
    report, decision = run(b=replace(boosted, document_hash=plain.document_hash),
                           ms=capture(plain))
    assert "/config/custom_mods" in unbound_fields(report) and not decision.eligible
    assert run(b=plain, ms=capture(plain))[0].input_identity != \
        run(b=boosted, ms=capture(boosted))[0].input_identity
    unrecorded = capture(plain)
    unrecorded = replace(unrecorded, binding=replace(unrecorded.binding, custom_mods=None))
    report, decision = run(b=plain, ms=unrecorded)
    assert "/config/custom_mods" in unbound_fields(report) and not decision.eligible


def test_f1_seed_capture_records_its_custom_blocks():
    ms = load_mod_support(PROBE)
    facts = build_facts_from_pob_xml(SEED.read_bytes())
    assert ms.binding.custom_mods == facts.custom_mods == (("Default", True, ""),)


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
