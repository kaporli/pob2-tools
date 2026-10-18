"""Evaluate one build on flicker_sustained_v1 (P07-T01, milestone 1).

``evaluate_flicker`` first runs P06 coverage (``analyse``) under the
resolutions this slice may apply, then ``decide``. Only an eligible decision
puts a number in the objective field. The timeline is still computed for an
ineligible build and returned as a labelled diagnostic, never as the
objective. Missing engine values produce a typed missing-input result with
null metrics.

Method ``pob-community-v2`` (D07 amendment 2026-10-18 (2)): per-use damage is
PoB's at maximum Power Charges with the Charged Staff buff as PoB applies it;
every action and wait counts inside [0, 120); burst is [0, 5).
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any, Callable, Mapping

from ..coverage import CoverageLedger, analyse, decide
from ..coverage.flicker_v1 import build_registry
from ..coverage.inputs import (EngineState as CoverageEngine, ScenarioFacts,
                               build_facts_from_pob_xml, load_mod_support, load_scenarios)
from ..coverage.registry import PATCH_PROFILE_ID
from ..domain.codec import to_jsonable
from ..domain.identity import content_hash
from ..domain.objectives import FLICKER_SUSTAINED_DPS_V1
from ..domain.records import RotationPolicy
from . import resolutions as res
from .attribution import AttributionTable, proposed_table
from .policy import PolicyError, seed_rotation
from .timeline import repeatable_cycle, simulate, summary
from .values import CycleValues, MissingValue, benchmark_document

SCENARIO_ID = "flicker_sustained_v1"
PIN = "ce566eac45ea8a86477f513c7ee65a1ebe60014e"
REPO = Path(__file__).resolve().parents[3]


@dataclass
class FlickerEvaluation:
    evaluation_id: str
    status: str
    method: str
    objective: dict
    decision: dict
    diagnostic: dict | None
    timeline: dict | None
    mana_ignored: dict | None
    repeatable: dict | None
    values: dict | None
    coverage: dict
    attribution: dict
    rotation: dict
    notes: list[str] = field(default_factory=list)

    def to_json(self) -> dict:
        return {k: getattr(self, k) for k in (
            "evaluation_id", "status", "method", "objective", "decision", "diagnostic",
            "repeatable", "values", "coverage", "attribution", "rotation", "notes",
            "mana_ignored", "timeline")}


def _inputs(values: CycleValues) -> dict[str, Any]:
    return {
        "/pob/FlickerStrikePlayer/AverageBurstDamage": values.pob_burst_damage_per_use,
        "/pob/FlickerStrikePlayer/AverageBurstHits": values.flicker_strikes_per_use,
        "/pob/FlickerStrikePlayer/Speed": values.flicker_strike_rate,
        "/pob/FlickerStrikePlayer/ManaCost": values.flicker_mana,
        "/pob/WhirlingAssaultPlayer/Time": values.whirling_time_s,
        "/pob/WhirlingAssaultPlayer/ManaCost": values.whirling_mana,
        "/pob/PowerChargesMax": values.charges,
    }


def _with_gaps(scenario: ScenarioFacts, ledger: CoverageLedger) -> ScenarioFacts:
    gaps = tuple(ledger.gaps.get(g.gap_id, g) for g in scenario.protocol_gaps)
    return replace(scenario, protocol_gaps=gaps)


def _rotation_hash(policy: RotationPolicy) -> str:
    data = to_jsonable(policy)
    for key in ("record_id", "created_at", "provenance_ids"):
        data.pop(key, None)
    return content_hash(data)


def evaluate_flicker(xml: str, values_source: Callable[[], CycleValues] | CycleValues, *,
                     policy: RotationPolicy | None = None,
                     method: str = res.METHOD_ID,
                     scenarios_path: str | Path = REPO / "benchmarks/p09-flicker-v1/scenarios.json",
                     mod_support_path: str | Path | None = REPO / "docs/evidence/P06/seed-engine-mod-support.json",
                     p09_resolutions: list[Mapping] | None = None,
                     attribution: AttributionTable | None = None,
                     attribution_acceptance: Mapping | None = None,
                     engine_commit: str | None = PIN, engine_dirty: bool | None = False,
                     patch_compatibility: str = "partial",
                     patch_profile_id: str = PATCH_PROFILE_ID,
                     config_options: Mapping | None = None,
                     window_s: float = 120.0, burst_s: float = 5.0,
                     registry=None) -> FlickerEvaluation:
    policy = policy or seed_rotation()
    attribution = attribution or proposed_table()
    notes: list[str] = []
    xml_hash = hashlib.sha256(xml.encode("utf-8")).hexdigest()

    values: CycleValues | None = None
    missing: MissingValue | None = None
    try:
        values = values_source() if callable(values_source) else values_source
    except MissingValue as exc:
        missing = exc

    document = values.document if values is not None else "benchmark"
    scored_xml = benchmark_document(xml) if document == "benchmark" else xml
    facts = build_facts_from_pob_xml(scored_xml.encode("utf-8"),
                                     engine=CoverageEngine(engine_commit, engine_dirty))
    registry = registry or build_registry()
    scenario = load_scenarios(scenarios_path)[SCENARIO_ID]
    mods = load_mod_support(mod_support_path) if mod_support_path else None
    inputs = _inputs(values) if values is not None else {}

    def run(reg, scen):
        return analyse(facts, scen, reg, rotation=policy, mod_support=mods,
                       config_options=config_options,
                       patch_profile_id=patch_profile_id, patch_compatibility=patch_compatibility,
                       pinned_commit=PIN, inputs=inputs)

    ledger = CoverageLedger(registry, scenario.protocol_gaps)
    first = run(registry, scenario)
    ledger.add_gaps(first.gaps())
    applied: list[res.Applied] = []
    if p09_resolutions:
        res.apply_p09_t012(ledger, first, p09_resolutions, applied)
    res.apply_implementation(ledger, first, applied)
    res.apply_method(ledger, first, method, applied)
    res.apply_attribution(ledger, first, attribution_acceptance,
                          {"skill/FlickerStrikePlayer": "flicker_direct",
                           "skill/WhirlingAssaultPlayer": "unrelated",
                           "skill/ChargedStaffPlayer": "unrelated",
                           "skill/MeleeQuarterstaffPlayer": "unrelated",
                           "support/SupportLivingLightningPlayerTwo": "unrelated"},
                          applied)
    scenario_now = _with_gaps(scenario, ledger)
    report = run(ledger.registry, scenario_now)
    decision = decide(report, ledger.registry)
    extra_blocking = []
    if document != "benchmark":
        # P09-T01.2 rule pounce-predators-mark: the as-imported document has
        # Pounce enabled and PoB applies its Predator's Mark (x1.24 damage
        # taken), a state the rotation does not generate. Coverage walks only
        # weapon set 1 and does not see that group, so the refusal is here.
        extra_blocking.append({
            "gap_id": "gap-p07-not-scoring-document", "class": "hidden_assumption",
            "domain": "config", "mechanics": ["skill/WolfPouncePlayer", "config/condition-sustain"],
            "explanation": "Values come from document %r, not the scoring document with Pounce "
                           "disabled; PoB applies Predator's Mark there." % document,
            "needed_evidence": "Values from the benchmark document (Pounce disabled)."})

    blocking = [{"gap_id": f.gap_id, "class": f.gap_class, "domain": f.domain,
                 "mechanics": list(f.mechanic_ids), "subjects": list(f.subject_ids),
                 "fields": list(f.field_paths), "explanation": f.explanation,
                 "needed_evidence": f.needed_evidence}
                for f in report.findings if f.severity.value == "blocking"]
    blocking += [{"gap_id": g.gap_id, "class": "protocol:" + g.kind.value, "domain": "protocol",
                  "explanation": g.explanation, "needed_evidence": g.needed_evidence}
                 for g in report.protocol_gaps
                 if g.status.value == "open" and g.severity.value == "blocking"]
    coverage = {
        "registry_id": ledger.registry.registry_id, "registry_version": ledger.registry.version,
        "registry_hash": ledger.registry.registry_hash(),
        "rule_closure_hash": report.rule_closure_hash, "rule_ids": list(report.rule_ids),
        "applied_resolutions": [a.__dict__ for a in applied],
        "ledger_history": [e.__dict__ for e in ledger.history],
        "ranking_sensitive": [{"gap_id": f.gap_id, "class": f.gap_class, "mechanics": list(f.mechanic_ids),
                               "explanation": f.explanation}
                              for f in report.findings if f.severity.value == "ranking_sensitive"],
        "report_notes": list(report.notes),
    }
    blocking = extra_blocking + blocking
    eligible = decision.eligible and not extra_blocking
    decision_json = {"eligible": eligible, "reasons": list(decision.reasons) + [
                         b["explanation"] for b in extra_blocking],
                     "unsettled_critical": list(decision.unsettled_critical),
                     "blocking_gap_ids": sorted(set(decision.blocking_gap_ids)
                                                | {b["gap_id"] for b in extra_blocking}),
                     "blocking": blocking}
    objective = {"objective_id": FLICKER_SUSTAINED_DPS_V1.objective_id,
                 "objective_version": FLICKER_SUSTAINED_DPS_V1.version,
                 "metrics": {"flicker_sustained_dps": None, "flicker_burst_dps": None},
                 "score": None, "label": "proxy_only: PoB-derived, model_estimate at best"}
    rotation_json = {"rotation_id": policy.rotation_id, "rotation_hash": _rotation_hash(policy),
                     "record": to_jsonable(policy)}

    if values is None:
        eid = content_hash({"xml": xml_hash, "rotation": rotation_json["rotation_hash"],
                            "method": method, "values": None,
                            "registry": coverage["registry_hash"]})
        decision_json["eligible"] = False
        decision_json["reasons"].insert(0, "missing engine value: %s" % missing)
        decision_json["blocking"].insert(0, {"gap_id": "gap-p07-missing-value-" + content_hash(
            {"path": missing.path})[:10], "class": "missing_data", "domain": "engine",
            "fields": [missing.path], "explanation": missing.why,
            "needed_evidence": "The engine output %s for this build." % missing.path})
        return FlickerEvaluation(eid, "missing_inputs", method, objective, decision_json,
                                 None, None, None, None, None, coverage,
                                 attribution.to_json(), rotation_json, notes)

    try:
        timeline = simulate(values, policy, attribution, window_s=window_s, burst_s=burst_s,
                            enforce_mana=True)
    except PolicyError as exc:
        eid = content_hash({"xml": xml_hash, "rotation": rotation_json["rotation_hash"],
                            "method": method, "values": values.to_json(),
                            "registry": coverage["registry_hash"]})
        decision_json["eligible"] = False
        decision_json["reasons"].insert(0, "rotation refused: %s" % exc)
        return FlickerEvaluation(eid, "invalid_rotation", method, objective, decision_json,
                                 None, None, None, None, values.to_json(), coverage,
                                 attribution.to_json(), rotation_json, list(exc.problems))
    main = summary(timeline, values, attribution)
    loose = simulate(values, policy, attribution, window_s=window_s, burst_s=burst_s,
                     enforce_mana=False)
    loose_summary = summary(loose, values, attribution)
    if eligible:
        objective["metrics"] = {"flicker_sustained_dps": main["flicker_sustained_dps"],
                                "flicker_burst_dps": main["flicker_burst_dps"]}
        objective["score"] = main["flicker_sustained_dps"]
        status = "eligible"
        label = "eligible: objective value"
    else:
        status = "blocked"
        label = "NOT ELIGIBLE: diagnostic only; not the objective and not a supported score"
    diagnostic = {"label": label, **{k: main[k] for k in (
        "flicker_sustained_dps", "flicker_burst_dps", "attributed_damage_0_120",
        "attributed_damage_0_5", "contributions", "time_in_window_s", "flicker_uses_started",
        "preparation_time_s")},
        "pob_plain": {"TotalDPS": values.pob_total_dps,
                      "AverageBurstDamage": values.pob_burst_damage_per_use,
                      "IgniteDPS": values.flicker_ignite_dps,
                      "note": "PoB's own numbers at the method's charges; no rotation time; proxy_only"}}
    values_json = values.to_json()
    # Which worker processes produced the values is provenance, not identity.
    identity_values = dict(values_json, engine={k: v for k, v in values_json["engine"].items()
                                                if k != "worker_pids"})
    eid = content_hash({"xml": xml_hash, "rotation": rotation_json["rotation_hash"],
                        "method": method, "values": identity_values,
                        "registry": coverage["registry_hash"],
                        "attribution": attribution.to_json()})
    return FlickerEvaluation(
        evaluation_id=eid, status=status, method=method, objective=objective,
        decision=decision_json, diagnostic=diagnostic, timeline=timeline.to_json(),
        mana_ignored={"note": "same rotation without waiting for mana; balance goes negative; "
                              "comparison only, not attainable as written",
                      **{k: loose_summary[k] for k in ("flicker_sustained_dps", "flicker_burst_dps",
                                                       "flicker_uses_started", "mana")}},
        repeatable=repeatable_cycle(timeline, values), values=values_json,
        coverage=coverage, attribution=attribution.to_json(), rotation=rotation_json,
        notes=notes)


def load_p09_resolutions(path: str | Path = REPO / res.RULES_FILE) -> list[Mapping]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return list(data.get("p06_ledger_resolutions") or [])
